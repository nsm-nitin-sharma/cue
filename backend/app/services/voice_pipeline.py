from datetime import timedelta
from typing import Any
import uuid

from app.core.config import get_settings
from app.core.entitlements import assert_voice_quota
from app.core.exceptions import InsufficientStockError, PolicyBlockedError
from app.core.policy import SecurityPolicyEngine
from app.core.security import canonical_payload_hash, validate_audio_upload
from app.core.time_utils import (
    check_memory_window_days,
    detect_over_30_day_reference,
    get_business_today,
    resolve_relative_date,
)
from app.domain.indian_numbers import extract_post_negation_number, parse_indian_number
from app.domain.schemas.intents import (
    ConfirmOperationRequest,
    CreateProductAndExecuteRequest,
    VoiceOperationItem,
    VoiceTurnResult,
)
from app.domain.unit_converter import convert_to_base_quantity
from app.providers.llm.factory import get_llm_provider
from app.providers.stt.factory import get_stt_provider
from app.services.entity_resolver import (
    resolve_customer,
    resolve_product,
    resolve_short_variant_reply,
)
from app.services.memory_30d import Memory30DService
from app.services.query_engine import QueryEngine
from app.services.transaction_engine import TransactionEngine


class VoicePipelineService:
    """
    End-to-end Voice-First Pipeline:
    MediaRecorder -> FastAPI -> STT -> SecurityPolicyEngine -> 30-Day Memory ->
    Gemini (Untrusted JSON Parser) -> EntityResolver -> Slot Filling / Tier-3 Gate ->
    Atomic Supabase RPC -> Spoken Reply + Receipt Slips.
    """

    def __init__(self, db: Any):
        self.db = db
        self.memory = Memory30DService(db)
        self.tx = TransactionEngine(db)
        self.queries = QueryEngine(db)

    def _load_catalog(self, business_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        prods_res = (
            self.db.table("products")
            .select("*, inventory(current_quantity)")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
        )
        products = []
        for p in prods_res.data or []:
            inv = p.get("inventory")
            stock = 0.0
            if isinstance(inv, list) and inv:
                stock = float(inv[0].get("current_quantity") or 0)
            elif isinstance(inv, dict):
                stock = float(inv.get("current_quantity") or 0)
            p["current_stock"] = stock
            products.append(p)

        aliases = (
            self.db.table("product_aliases")
            .select("*")
            .eq("business_id", business_id)
            .execute()
            .data
            or []
        )
        customers = (
            self.db.table("customers")
            .select("*")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        return products, aliases, customers

    def _load_business_and_sub(self, business_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        biz = (
            self.db.table("businesses")
            .select("*")
            .eq("id", business_id)
            .limit(1)
            .execute()
            .data[0]
        )
        sub_res = (
            self.db.table("business_subscriptions")
            .select("*, subscription_plans(*)")
            .eq("business_id", business_id)
            .limit(1)
            .execute()
        )
        return biz, (sub_res.data[0] if sub_res.data else None)

    async def process_audio_turn(
        self,
        *,
        business_id: str,
        user_id: str,
        audio_bytes: bytes,
        filename: str,
        content_type: str | None,
        operation_id: str,
        language: str = "hinglish",
    ) -> VoiceTurnResult:
        validate_audio_upload(audio_bytes, content_type)
        stt = get_stt_provider()
        stt_res = await stt.transcribe(
            audio_bytes,
            filename=filename,
            content_type=content_type or "audio/webm",
            language_hint=language,
        )
        if stt_res.is_unclear or not stt_res.text:
            return VoiceTurnResult(
                operation_id=operation_id,
                status="retry_audio",
                transcript="",
                reply="Awaaz clear nahi thi ya background noise zyada tha. Kripya dobara bolein.",
                language=language if language in {"hinglish", "hi", "en"} else "hinglish",  # type: ignore[arg-type]
            )

        return await self.process_text_turn(
            business_id=business_id,
            user_id=user_id,
            text=stt_res.text,
            operation_id=operation_id,
            language=stt_res.detected_language,
            stt_provider=stt_res.provider,
            stt_confidence=stt_res.confidence,
        )

    async def process_text_turn(
        self,
        *,
        business_id: str,
        user_id: str,
        text: str,
        operation_id: str,
        language: str = "hinglish",
        stt_provider: str = "text",
        stt_confidence: float | None = None,
    ) -> VoiceTurnResult:
        clean_text = text.strip()
        payload_hash = canonical_payload_hash({"text": clean_text, "language": language})

        cached = self.tx.check_idempotency(
            business_id=business_id, operation_id=operation_id, payload_hash=payload_hash
        )
        if cached:
            return VoiceTurnResult(**cached)

        biz, sub = self._load_business_and_sub(business_id)
        assert_voice_quota(sub)
        tz_name = biz.get("timezone", "Asia/Kolkata")
        today_date = get_business_today(tz_name)
        today_str = today_date.isoformat()

        conv = self.memory.get_or_create_day_conversation(business_id=business_id, conv_date=today_date, timezone_name=tz_name)
        conv_id = conv["id"]
        context_state: dict[str, Any] = dict(conv.get("context_state") or {})

        self.memory.append_message(
            conversation_id=conv_id,
            business_id=business_id,
            conversation_date=today_str,
            role="user",
            content=clean_text,
            language=language,
            linked_operation_id=operation_id,
        )

        # 1. Hardcore Security Firewall: reject destructive / prompt-injection attempts immediately
        try:
            SecurityPolicyEngine.assert_safe_utterance(clean_text)
        except PolicyBlockedError as exc:
            result = VoiceTurnResult(
                operation_id=operation_id,
                status="policy_blocked",
                transcript=clean_text,
                reply=exc.message,
                language=language if language in {"hinglish", "hi", "en"} else "hinglish",  # type: ignore[arg-type]
                receipts=[
                    {
                        "id": f"slip-{operation_id}",
                        "operationId": operation_id,
                        "kind": "blocked",
                        "title": "Action Blocked · Security Policy",
                        "subtitle": "AI has zero destructive permissions",
                        "transactionDate": today_str,
                        "lines": [{"label": "Rule", "value": "POLICY_BLOCKED", "tone": "crimson"}],
                        "status": "blocked",
                    }
                ],
            )
            self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, clean_text, language, stt_provider, stt_confidence, {}, "policy_blocked", "blocked", [], result, context_state, user_id)
            return result

        # 2. > 30 Days Memory Boundary Guard
        over_days = detect_over_30_day_reference(clean_text, today_date)
        if over_days is not None and over_days > get_settings().CONVERSATION_MEMORY_DAYS:
            reply = (
                "Conversational chat memory sirf pichle 30 dinon (1 mahine) tak ki available hai, "
                "isliye main itni purani chat context ko yaad nahi kar sakta. Permanent records Reports & Ledger mein safe hain."
            )
            result = VoiceTurnResult(
                operation_id=operation_id,
                status="memory_boundary",
                transcript=clean_text,
                reply=reply,
                language=language if language in {"hinglish", "hi", "en"} else "hinglish",  # type: ignore[arg-type]
                clarification={"kind": "memory_boundary", "prompt": reply},
            )
            self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, clean_text, language, stt_provider, stt_confidence, {"boundary_days": over_days}, "needs_clarification", "tier2", [], result, context_state, user_id)
            return result

        products, aliases, customers = self._load_catalog(business_id)

        # 3. Check pending multi-turn clarification / disambiguation / slot-fill BEFORE re-parsing from scratch
        pending_flow = context_state.get("pending_flow")
        if pending_flow:
            handled = await self._handle_pending_flow(
                pending_flow=pending_flow,
                reply_text=clean_text,
                business_id=business_id,
                user_id=user_id,
                conv_id=conv_id,
                today_str=today_str,
                tz_name=tz_name,
                operation_id=operation_id,
                payload_hash=payload_hash,
                language=language,
                stt_provider=stt_provider,
                stt_confidence=stt_confidence,
                products=products,
                customers=customers,
                context_state=context_state,
            )
            if handled is not None:
                return handled

        # 4. Untrusted LLM Parsing (with 30-day rolling context + catalog hints)
        target_hint_date = resolve_relative_date("kal" if "kal" in clean_text.lower() else None, tz_name)
        llm_ctx = self.memory.get_30d_context_for_llm(
            business_id=business_id,
            today_conversation=conv,
            target_date=target_hint_date,
            timezone_name=tz_name,
        )
        catalog_hints = [{"name": p["name"], "unit": p["base_unit"], "stock": p["current_stock"]} for p in products]
        customer_hints = [{"name": c["name"], "area": c["area_note"], "due": float(c["outstanding_balance"])} for c in customers]

        llm = get_llm_provider()
        proposal = await llm.parse_utterance(
            utterance=clean_text,
            language_hint=language,
            context_summary=llm_ctx,
            catalog_hints=catalog_hints,
            customer_hints=customer_hints,
        )

        # 4b. Zero-Assumption Background Noise / Low-Confidence Guard
        if proposal.has_ambiguity_or_noise_conflict or proposal.confidence < 0.85:
            clar_msg = (
                proposal.clarification_question
                or "Mujhe thoda confusion hai (background awaaz ya unclear intent ke kaaran). Kripya dubara confirm karein ki aap kya record karna chahte hain?"
            )
            res = VoiceTurnResult(
                operation_id=operation_id,
                status="needs_clarification",
                transcript=clean_text,
                reply=clar_msg,
                language=proposal.detected_language,
                clarification={"kind": "missing_slot", "prompt": clar_msg},
            )
            self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, clean_text, proposal.detected_language, stt_provider, stt_confidence, proposal.model_dump(), "needs_clarification", "tier2", [], res, context_state, user_id)
            return res

        # 5. Execute parsed operations sequentially (supports single AND multi-command batch!)
        return await self._execute_operations_batch(
            operations=proposal.operations,
            business_id=business_id,
            user_id=user_id,
            conv_id=conv_id,
            today_str=today_str,
            tz_name=tz_name,
            operation_id=operation_id,
            payload_hash=payload_hash,
            raw_transcript=clean_text,
            language=proposal.detected_language,
            stt_provider=stt_provider,
            stt_confidence=stt_confidence,
            products=products,
            aliases=aliases,
            customers=customers,
            context_state=context_state,
        )

    async def _handle_pending_flow(
        self,
        *,
        pending_flow: dict[str, Any],
        reply_text: str,
        business_id: str,
        user_id: str,
        conv_id: str,
        today_str: str,
        tz_name: str,
        operation_id: str,
        payload_hash: str,
        language: str,
        stt_provider: str,
        stt_confidence: float | None,
        products: list[dict[str, Any]],
        customers: list[dict[str, Any]],
        context_state: dict[str, Any],
    ) -> VoiceTurnResult | None:
        flow_type = pending_flow.get("type")
        lower = reply_text.lower().strip()

        if flow_type == "verify_alias":
            if any(lower.startswith(w) for w in ("yes", "haan", "ha ", "ha", "ji", "bilkul", "correct", "ok")):
                cand = next((p for p in products if str(p["id"]) == pending_flow["candidate_id"]), None)
                if cand:
                    self.tx.save_verified_alias(
                        business_id=business_id,
                        product_id=str(cand["id"]),
                        alias_text=pending_flow["spoken"],
                        language=language,
                    )
                    draft = dict(pending_flow["draft"])
                    draft["product_id"] = str(cand["id"])
                    draft["product_name"] = cand["name"]
                    draft["unit"] = cand["base_unit"]
                    draft["verified_alias"] = pending_flow["spoken"]
                    context_state.pop("pending_flow", None)
                    return await self._complete_single_draft(
                        draft=draft,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=operation_id,
                        payload_hash=payload_hash,
                        raw_transcript=reply_text,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        products=products,
                        customers=customers,
                        context_state=context_state,
                    )
            if any(lower.startswith(w) for w in ("no", "nahi", "na ", "galat")):
                context_state.pop("pending_flow", None)
                msg = "Theek hai, kaunsa product tha? Kripya sahi naam ya size batayein."
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=reply_text,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, reply_text, language, stt_provider, stt_confidence, pending_flow, "needs_clarification", "tier2", [], res, context_state, user_id)
                return res

        if flow_type == "disambiguate_product":
            cands = [p for p in products if str(p["id"]) in pending_flow.get("candidate_ids", [])]
            matched = resolve_short_variant_reply(reply_text, cands)
            if matched:
                draft = dict(pending_flow["draft"])
                draft["product_id"] = str(matched["id"])
                draft["product_name"] = matched["name"]
                draft["unit"] = matched["base_unit"]
                context_state.pop("pending_flow", None)
                return await self._complete_single_draft(
                    draft=draft,
                    business_id=business_id,
                    user_id=user_id,
                    conv_id=conv_id,
                    today_str=today_str,
                    operation_id=operation_id,
                    payload_hash=payload_hash,
                    raw_transcript=reply_text,
                    language=language,
                    stt_provider=stt_provider,
                    stt_confidence=stt_confidence,
                    products=products,
                    customers=customers,
                    context_state=context_state,
                )

        if flow_type == "disambiguate_customer":
            cands = [c for c in customers if str(c["id"]) in pending_flow.get("candidate_ids", [])]
            matched_cust = next(
                (
                    c
                    for c in cands
                    if any(part in lower for part in c["name"].lower().split() if len(part) > 2)
                    or (c.get("area_note") and c["area_note"].lower() in lower)
                    or (c.get("phone") and c["phone"][-4:] in lower)
                ),
                None,
            )
            if matched_cust:
                draft = dict(pending_flow["draft"])
                draft["customer_id"] = str(matched_cust["id"])
                draft["customer_name"] = matched_cust["name"]
                context_state.pop("pending_flow", None)
                return await self._complete_single_draft(
                    draft=draft,
                    business_id=business_id,
                    user_id=user_id,
                    conv_id=conv_id,
                    today_str=today_str,
                    operation_id=operation_id,
                    payload_hash=payload_hash,
                    raw_transcript=reply_text,
                    language=language,
                    stt_provider=stt_provider,
                    stt_confidence=stt_confidence,
                    products=products,
                    customers=customers,
                    context_state=context_state,
                )

        if flow_type == "missing_slot":
            val = parse_indian_number(reply_text)
            draft = dict(pending_flow["draft"])
            missing_field = pending_flow.get("missing_field")
            prod = next((p for p in products if str(p["id"]) == str(draft.get("product_id"))), None)

            # Natural Hinglish/English references for "same price par", "purane rate pe", "wahi", "free"
            if val is None and missing_field in {"purchase_price", "selling_price"}:
                if any(w in lower for w in ("same", "wahi", "purana", "purane", "pichla", "pichle", "last")):
                    if prod:
                        val = float(
                            prod.get("default_cost_price" if missing_field == "purchase_price" else "default_selling_price")
                            or 0
                        )
                elif any(w in lower for w in ("free", "bonus", "muft")):
                    val = 0.0

            # Agentic LLM fallback for nuanced Hinglish pending replies
            if val is None and missing_field in {"purchase_price", "selling_price", "quantity"}:
                llm = get_llm_provider()
                proposal = await llm.parse_utterance(
                    utterance=reply_text,
                    language_hint=language,
                    context_summary={"pending_flow": pending_flow, "product": prod},
                    catalog_hints=[{"name": prod["name"], "last_cost": prod.get("default_cost_price")}] if prod else [],
                    customer_hints=[],
                )
                if proposal.operations:
                    op0 = proposal.operations[0]
                    if missing_field in {"purchase_price", "selling_price"}:
                        val = op0.unit_price if op0.unit_price is not None else op0.total_amount
                        if val is None and op0.is_affirmative and prod:
                            val = float(prod.get("default_cost_price") or 0)
                    elif missing_field == "quantity":
                        val = op0.quantity

            if missing_field in {"purchase_price", "selling_price"} and val is not None:
                draft["unit_price"] = val
                context_state.pop("pending_flow", None)
            elif missing_field == "quantity" and val is not None:
                draft["quantity"] = val
                context_state.pop("pending_flow", None)
            elif missing_field == "payment_method":
                if "upi" in lower:
                    draft["payment_method"] = "upi"
                elif "bank" in lower:
                    draft["payment_method"] = "bank"
                else:
                    draft["payment_method"] = "cash"
                context_state.pop("pending_flow", None)
            else:
                return None

            return await self._complete_single_draft(
                draft=draft,
                business_id=business_id,
                user_id=user_id,
                conv_id=conv_id,
                today_str=today_str,
                operation_id=operation_id,
                payload_hash=payload_hash,
                raw_transcript=reply_text,
                language=language,
                stt_provider=stt_provider,
                stt_confidence=stt_confidence,
                products=products,
                customers=customers,
                context_state=context_state,
            )

        return None

    async def _complete_single_draft(
        self,
        *,
        draft: dict[str, Any],
        business_id: str,
        user_id: str,
        conv_id: str,
        today_str: str,
        operation_id: str,
        payload_hash: str,
        raw_transcript: str,
        language: str,
        stt_provider: str,
        stt_confidence: float | None,
        products: list[dict[str, Any]],
        customers: list[dict[str, Any]],
        context_state: dict[str, Any],
    ) -> VoiceTurnResult:
        intent = draft["intent"]
        txn_date = draft.get("transaction_date", today_str)
        product = next((p for p in products if str(p["id"]) == str(draft.get("product_id"))), None)

        # Enforce Schema-Driven Slot-Filling for Purchase Price on Stock Receive
        if intent == "inventory_receive" and product and draft.get("unit_price") is None:
            last_cost = float(product.get("default_cost_price") or 0)
            msg = f"{draft['quantity']:g} {product['name']} kis purchase price par aayi hain? (Last rate ₹{last_cost:g}/{product['base_unit']} tha)"
            context_state["pending_flow"] = {
                "type": "missing_slot",
                "missing_field": "purchase_price",
                "draft": draft,
            }
            res = VoiceTurnResult(
                operation_id=operation_id,
                status="needs_clarification",
                transcript=raw_transcript,
                reply=msg,
                language=language,  # type: ignore[arg-type]
                clarification={
                    "kind": "missing_slot",
                    "prompt": msg,
                    "candidates": [
                        {"id": "same", "label": f"Same ₹{last_cost:g}/{product['base_unit']}", "value": str(last_cost)},
                        {"id": "zero", "label": "Free Bonus (₹0)", "value": "0"},
                    ],
                },
            )
            self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, draft, "needs_clarification", "tier2", [], res, context_state, user_id)
            return res

        # Tier-3 Check (>= ₹5,000)
        qty = float(draft.get("quantity") or 0)
        unit_price = float(
            draft.get("unit_price")
            if draft.get("unit_price") is not None
            else (product.get("default_selling_price", 0) if product else 0)
        )
        total_val = float(draft.get("total_amount") or (qty * unit_price))
        risk = SecurityPolicyEngine.classify_risk_tier(intent=intent, amount_inr=total_val)
        if risk == "tier3":
            token = self.tx.issue_confirmation_token(
                business_id=business_id,
                user_id=user_id,
                operation_id=operation_id,
                proposed_action=draft,
            )
            msg = f"Yeh ₹{total_val:,.0f} ka high-value transaction hai. Confirm karne ke liye 'Yes' bolein ya Confirm dabayein."
            res = VoiceTurnResult(
                operation_id=operation_id,
                status="needs_confirmation",
                transcript=raw_transcript,
                reply=msg,
                language=language,  # type: ignore[arg-type]
                confirmation={
                    "operationId": operation_id,
                    "token": token,
                    "title": f"High-Value {intent.replace('_', ' ').title()}",
                    "description": f"{product['name'] if product else draft.get('customer_name', '')} · {qty:g}",
                    "amountINR": total_val,
                    "impactSummary": f"Total value ₹{total_val:,.0f} requires Tier-3 authorization",
                    "payload": draft,
                },
            )
            self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, draft, "needs_confirmation", "tier3", [], res, context_state, user_id)
            return res

        # Execute atomically!
        receipt, reply = self._commit_draft_now(
            draft=draft,
            business_id=business_id,
            user_id=user_id,
            operation_id=operation_id,
            txn_date=txn_date,
            product=product,
            context_state=context_state,
        )

        # Resume any remaining queued batch items if this came from a multi-command utterance!
        pending_batch = context_state.pop("pending_batch_items", [])
        if pending_batch:
            batch_items = [VoiceOperationItem.model_validate(item) for item in pending_batch]
            follow = await self._execute_operations_batch(
                operations=batch_items,
                business_id=business_id,
                user_id=user_id,
                conv_id=conv_id,
                today_str=today_str,
                tz_name=get_settings().DEFAULT_TIMEZONE,
                operation_id=str(uuid.uuid4()),
                payload_hash=canonical_payload_hash({"batch_resume": operation_id}),
                raw_transcript=raw_transcript,
                language=language,
                stt_provider=stt_provider,
                stt_confidence=stt_confidence,
                products=products,
                aliases=[],
                customers=customers,
                context_state=context_state,
                prefix_receipts=[receipt],
                prefix_replies=[reply],
            )
            return follow

        res = VoiceTurnResult(
            operation_id=operation_id,
            status="executed",
            transcript=raw_transcript,
            reply=reply,
            language=language,  # type: ignore[arg-type]
            receipts=[receipt],
        )
        self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, draft, "executed", "tier1", [{"receipt": receipt["id"]}], res, context_state, user_id)
        return res

    def _commit_draft_now(
        self,
        *,
        draft: dict[str, Any],
        business_id: str,
        user_id: str,
        operation_id: str,
        txn_date: str,
        product: dict[str, Any] | None,
        context_state: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        intent = draft["intent"]
        if intent == "inventory_receive" and product:
            qty = float(draft["quantity"])
            unit_cost = float(draft["unit_price"])
            rpc = self.tx.receive_stock(
                business_id=business_id,
                user_id=user_id,
                product_id=str(product["id"]),
                quantity=qty,
                unit=product["base_unit"],
                unit_cost=unit_cost,
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_product_id"] = str(product["id"])
            context_state["last_product_name"] = product["name"]
            context_state["last_receive_qty"] = qty
            context_state["last_operation_id"] = operation_id

            total = qty * unit_cost
            alias_note = draft.get("verified_alias")
            lines = []
            if alias_note:
                lines.append({"label": "Verified Alias Saved", "value": f'"{alias_note}" → {product["name"]}', "tone": "sage"})
            lines.append({"label": "Received", "value": f"+{qty:g} {product['base_unit']} @ ₹{unit_cost:g}", "tone": "sage"})
            lines.append({"label": "Stock Level", "value": f"{rpc['before_qty']:g} → {rpc['after_qty']:g}", "tone": "neutral"})

            reply = f"{qty:g} {product['name']} ₹{unit_cost:g} ke rate par receive hui hain (Total ₹{total:,.0f})."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "receive",
                "title": f"Stock Added · {product['name']}",
                "subtitle": f'Alias "{alias_note}" verified' if alias_note else "Verified Inventory Receipt",
                "transactionDate": txn_date,
                "amountINR": total,
                "lines": lines,
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "record_sale" and product:
            qty = float(draft["quantity"])
            unit_price = float(draft.get("unit_price") or product.get("default_selling_price") or 0)
            p_status = draft.get("payment_status") or "paid"
            p_method = draft.get("payment_method") or "cash"
            cust_name = draft.get("customer_name")
            total = qty * unit_price
            paid = total if p_status == "paid" else float(draft.get("paid_amount") or 0)
            rpc = self.tx.record_sale(
                business_id=business_id,
                user_id=user_id,
                product_id=str(product["id"]),
                product_name=product["name"],
                quantity=qty,
                unit=product["base_unit"],
                unit_price=unit_price,
                payment_status=p_status,
                paid_amount=paid,
                customer_id=draft.get("customer_id"),
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_product_id"] = str(product["id"])
            context_state["last_product_name"] = product["name"]
            context_state["last_sale_id"] = str(rpc["sale_id"])
            context_state["last_operation_kind"] = "record_sale"
            context_state["last_operation_id"] = operation_id
            method_label = "Online" if p_method == "upi" else ("Bank" if p_method == "bank" else "Cash")
            if p_status == "credit":
                who = cust_name or "Customer"
                reply = f"{qty:g} {product['name']} {who} ke Khata mein Udhaar (₹{total:,.0f}) add ho gayi. Revenue mein abhi add nahi hua."
                subtitle = f"Udhaar · {who} (Unpaid)"
                extra_lines = [{"label": "Khata Udhaar", "value": f"₹{total:,.0f} (Not in revenue)", "tone": "ochre"}]
            else:
                reply = f"{qty:g} {product['name']} ki {method_label} sale (₹{total:,.0f}) save ho gayi."
                subtitle = f"{cust_name + ' · ' if cust_name else ''}{method_label} Sale"
                extra_lines = [{"label": "Payment", "value": method_label, "tone": "sage"}]
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "sale",
                "title": f"Sale · {product['name']}",
                "subtitle": subtitle,
                "transactionDate": txn_date,
                "amountINR": total,
                "lines": [
                    {"label": product["name"], "value": f"-{qty:g} {product['base_unit']} @ ₹{unit_price:g}", "tone": "sage"},
                    *extra_lines,
                    {"label": "Stock Level", "value": f"{rpc['before_qty']:g} → {rpc['after_qty']:g}", "tone": "neutral"},
                ],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent in {"inventory_damage", "inventory_expiry"} and product:
            qty = float(draft["quantity"])
            mtype = "expiry" if intent == "inventory_expiry" else "damage"
            rpc = self.tx.deduct_damage_or_expiry(
                business_id=business_id,
                user_id=user_id,
                product_id=str(product["id"]),
                product_name=product["name"],
                quantity=qty,
                unit=product["base_unit"],
                movement_type=mtype,
                transaction_date=txn_date,
                operation_id=operation_id,
                notes=draft.get("notes") or f"Voice {mtype} deduction",
            )
            reply = f"{qty:g} {product['name']} {mtype} mark ho gaya. Remaining stock: {rpc['after_qty']:g}."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": mtype,
                "title": f"{mtype.title()} Deduction · {product['name']}",
                "subtitle": "Linked Stock Adjustment",
                "transactionDate": txn_date,
                "lines": [
                    {"label": mtype.title(), "value": f"-{qty:g} {product['base_unit']}", "tone": "crimson"},
                    {"label": "Stock Level", "value": f"{rpc['before_qty']:g} → {rpc['after_qty']:g}", "tone": "neutral"},
                ],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "record_expense":
            amt = float(draft["total_amount"])
            cat = draft.get("expense_category") or "Shop Expense"
            desc = draft.get("description") or cat
            method = draft.get("payment_method") or "cash"
            exp = self.tx.record_expense(
                business_id=business_id,
                user_id=user_id,
                category=cat,
                description=desc,
                amount=amt,
                payment_method=method,
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_expense_id"] = str(exp["id"])
            context_state["last_operation_kind"] = "record_expense"
            context_state["last_operation_id"] = operation_id
            method_label = "Online" if method == "upi" else method.title()
            reply = f"₹{amt:,.0f} ka {cat} expense ({method_label}) save ho gaya."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "expense",
                "title": f"Expense · {cat}",
                "subtitle": desc,
                "transactionDate": txn_date,
                "amountINR": amt,
                "lines": [{"label": "Paid Via", "value": method_label, "tone": "neutral"}],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "archive_product" and product:
            self.tx.archive_product(business_id=business_id, product_id=str(product["id"]))
            reply = f"{product['name']} ko catalog se archive kar diya gaya hai (purane records safe rahenge)."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "damage",
                "title": f"Archived SKU · {product['name']}",
                "subtitle": "Soft-archived from active catalog",
                "transactionDate": txn_date,
                "lines": [{"label": "Catalog Status", "value": "Archived", "tone": "neutral"}],
                "status": "saved",
            }
            return slip, reply

        raise PolicyBlockedError("Unsupported draft payload")

    async def _execute_operations_batch(
        self,
        *,
        operations: list[VoiceOperationItem],
        business_id: str,
        user_id: str,
        conv_id: str,
        today_str: str,
        tz_name: str,
        operation_id: str,
        payload_hash: str,
        raw_transcript: str,
        language: str,
        stt_provider: str,
        stt_confidence: float | None,
        products: list[dict[str, Any]],
        aliases: list[dict[str, Any]],
        customers: list[dict[str, Any]],
        context_state: dict[str, Any],
        prefix_receipts: list[dict[str, Any]] | None = None,
        prefix_replies: list[str] | None = None,
    ) -> VoiceTurnResult:
        receipts: list[dict[str, Any]] = list(prefix_receipts or [])
        replies: list[str] = list(prefix_replies or [])

        for idx, op in enumerate(operations):
            SecurityPolicyEngine.assert_allowed_intent(op.intent)
            if op.has_ambiguity_or_noise_conflict or op.confidence < 0.85:
                clar_msg = (
                    op.clarification_question
                    or "Thoda confusion hai — kripya sahi product, customer, ya quantity dubara confirm karein."
                )
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=raw_transcript,
                    reply=clar_msg,
                    language=language,  # type: ignore[arg-type]
                    receipts=receipts,
                    clarification={"kind": "missing_slot", "prompt": clar_msg},
                )
                return res

            sub_op_id = operation_id if idx == 0 and not prefix_receipts else str(uuid.uuid4())
            txn_date = resolve_relative_date(op.relative_date, tz_name)
            within_30d, days_ago = check_memory_window_days(txn_date, get_business_today(tz_name), 30)
            if not within_30d:
                msg = "Conversational chat memory sirf pichle 30 dinon (1 mahine) tak ki available hai."
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="memory_boundary",
                    transcript=raw_transcript,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                    clarification={"kind": "memory_boundary", "prompt": msg},
                )
                return res
            txn_date_str = txn_date.isoformat()

            if op.intent == "query_business":
                qres = self.queries.answer_query(
                    business_id=business_id,
                    topic=op.query_topic,
                    product_query=op.product_query,
                    customer_query=op.customer_query,
                    products=products,
                    aliases=aliases,
                    timezone_name=tz_name,
                )
                replies.append(qres["reply"])
                topic_titles = {
                    "stock_check": "Stock Query Result",
                    "expenses_summary": "Expenses Summary",
                    "daily_summary": "Daily Ledger Summary",
                    "pending_payments": "Pending Khata Dues",
                    "customer_balance": "Customer Khata Balance",
                    "sales_summary": "Today's Sales Summary",
                }
                receipts.append(
                    {
                        "id": f"slip-{sub_op_id}",
                        "operationId": sub_op_id,
                        "kind": "query",
                        "title": topic_titles.get(op.query_topic or "general", "Ledger Query Result"),
                        "subtitle": f"{txn_date_str} · Read-Only",
                        "transactionDate": txn_date_str,
                        "amountINR": qres["amount_inr"],
                        "lines": qres["lines"],
                        "status": "saved",
                    }
                )
                continue

            if op.intent in {"correct_last_sale", "correct_last_operation"}:
                last_kind = context_state.get("last_operation_kind")
                exp_id = context_state.get("last_expense_id")
                sale_id = context_state.get("last_sale_id")

                # Expense correction (e.g., "cash nahi, UPI se kiya tha" or "1000 nahi 500 tha")
                if last_kind == "record_expense" and exp_id and (
                    op.payment_method is not None or op.total_amount is not None or op.description is not None
                ):
                    corr_exp = self.tx.correct_last_expense(
                        business_id=business_id,
                        user_id=user_id,
                        expense_id=str(exp_id),
                        operation_id=sub_op_id,
                        transaction_date=today_str,
                        new_amount=op.total_amount,
                        new_payment_method=op.payment_method,
                        new_description=op.description,
                    )
                    context_state["last_expense_id"] = str(corr_exp["new_expense_id"])
                    old_m = "Online" if corr_exp["old_method"] == "upi" else corr_exp["old_method"].title()
                    new_m = "Online" if corr_exp["new_method"] == "upi" else corr_exp["new_method"].title()
                    replies.append(
                        f"{corr_exp['category']} expense update ho gaya: ₹{corr_exp['new_amount']:,.0f} ({old_m} → {new_m})."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": f"Corrected Expense · {corr_exp['category']}",
                            "subtitle": "Previous entry marked corrected (Audit Trail)",
                            "transactionDate": today_str,
                            "amountINR": corr_exp["new_amount"],
                            "lines": [
                                {"label": "Method", "value": f"{old_m} → {new_m}", "tone": "sage"},
                                {"label": "Amount", "value": f"₹{corr_exp['new_amount']:,.0f}", "tone": "neutral"},
                            ],
                            "status": "corrected",
                        }
                    )
                    continue

                new_qty = op.quantity if op.quantity is not None else extract_post_negation_number(raw_transcript)
                if sale_id and new_qty is not None:
                    corr = self.tx.correct_sale_quantity(
                        business_id=business_id,
                        user_id=user_id,
                        sale_id=sale_id,
                        new_quantity=float(new_qty),
                        operation_id=sub_op_id,
                        transaction_date=today_str,
                    )
                    replies.append(
                        f"Sale correct ho gayi: {corr['old_quantity']:g} se {corr['new_quantity']:g} (₹{corr['new_total']:,.0f}). Audit trail updated."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": "Audited Sale Correction",
                            "subtitle": "Compensating stock reversal logged",
                            "transactionDate": today_str,
                            "amountINR": corr["new_total"],
                            "lines": [
                                {"label": "Quantity", "value": f"{corr['old_quantity']:g} → {corr['new_quantity']:g}", "tone": "ochre"},
                                {"label": "Stock Adjusted", "value": f"{corr['stock_delta']:+g}", "tone": "sage"},
                            ],
                            "status": "corrected",
                        }
                    )
                    continue

                return VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=raw_transcript,
                    reply="Kaunse pichle transaction ko correct karna hai? Kripya item ya amount saaf batayein.",
                    language=language,  # type: ignore[arg-type]
                )

            if op.intent == "create_product":
                if not op.product_query:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Naye product ka naam, quantity aur price batayein.",
                        language=language,  # type: ignore[arg-type]
                    )
                pres_new = resolve_product(op.product_query, products, aliases)
                if pres_new.status == "exact" and pres_new.product:
                    replies.append(f"{pres_new.product['name']} pehle se inventory mein maujood hai.")
                    continue
                unit_val = op.unit if op.unit in {"piece", "packet", "kg", "litre", "box"} else "packet"
                item_name = op.product_query.title()
                msg = f"Naya product '{item_name}' add karne ke liye details confirm karein:"
                popup = {
                    "name": item_name,
                    "category": "General",
                    "baseUnit": unit_val,
                    "quantity": op.quantity or 1,
                    "costPrice": str(op.cost_price or op.unit_price or 0),
                    "sellingPrice": str(op.unit_price or 0),
                    "lowStockThreshold": "5",
                    "actionKind": "receive",
                }
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="new_product_popup",
                    transcript=raw_transcript,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                    receipts=receipts,
                    new_product_draft=popup,
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, op.model_dump(), "needs_clarification", "tier2", [], res, context_state, user_id)
                return res

            # Resolve Product (for stock & sale intents)
            if op.intent in {"inventory_receive", "inventory_damage", "inventory_expiry", "record_sale"}:
                target_prod: dict[str, Any] | None = None
                if op.uses_prior_context and not op.product_query and context_state.get("last_product_id"):
                    target_prod = next(
                        (p for p in products if str(p["id"]) == str(context_state["last_product_id"])), None
                    )
                else:
                    pres = resolve_product(op.product_query, products, aliases)
                    if pres.status == "exact":
                        target_prod = pres.product
                    elif pres.status == "verify_alias" and pres.product:
                        remaining = [item.model_dump() for item in operations[idx + 1 :]]
                        if remaining:
                            context_state["pending_batch_items"] = remaining
                        draft = {
                            "intent": op.intent,
                            "quantity": op.quantity or 1,
                            "unit_price": op.unit_price,
                            "payment_status": op.payment_status or "paid",
                            "transaction_date": txn_date_str,
                        }
                        context_state["pending_flow"] = {
                            "type": "verify_alias",
                            "spoken": pres.spoken_term,
                            "candidate_id": str(pres.product["id"]),
                            "draft": draft,
                        }
                        qty_disp = f"{float(op.quantity or 1):g}"
                        unit_disp = pres.product.get("base_unit", "piece")
                        action_disp = (
                            "sold"
                            if op.intent == "record_sale"
                            else (
                                "received (stock add)"
                                if op.intent == "inventory_receive"
                                else ("expired" if op.intent == "inventory_expiry" else "damaged")
                            )
                        )
                        msg = f"Do you mean {qty_disp} {unit_disp} {pres.product['name']} {action_disp}?"
                        res = VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=(f"{' '.join(replies)} {msg}".strip()),
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            clarification={
                                "kind": "verify_alias",
                                "prompt": msg,
                                "candidates": [
                                    {"id": "yes", "label": f"Yes, {pres.product['name']} (Remember alias)", "value": "Yes"},
                                    {"id": "no", "label": "No, different product", "value": "No"},
                                ],
                            },
                        )
                        self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, op.model_dump(), "needs_clarification", "tier2", [], res, context_state, user_id)
                        return res
                    elif pres.status == "ambiguous" and pres.candidates:
                        remaining = [item.model_dump() for item in operations[idx + 1 :]]
                        if remaining:
                            context_state["pending_batch_items"] = remaining
                        draft = {
                            "intent": op.intent,
                            "quantity": op.quantity or 1,
                            "unit_price": op.unit_price,
                            "payment_status": op.payment_status or "paid",
                            "transaction_date": txn_date_str,
                        }
                        context_state["pending_flow"] = {
                            "type": "disambiguate_product",
                            "candidate_ids": [str(c["id"]) for c in pres.candidates],
                            "draft": draft,
                        }
                        names = " ya ".join(c["name"] for c in pres.candidates)
                        qty_disp = f"{float(op.quantity or 1):g}"
                        action_disp = (
                            "sale"
                            if op.intent == "record_sale"
                            else ("receive" if op.intent == "inventory_receive" else op.intent.replace("inventory_", ""))
                        )
                        msg = (
                            f"'{op.product_query}' ke {len(pres.candidates)} options mile: {names} "
                            f"({qty_disp} {action_disp}). Screen se select karein ya exact naam bolein."
                        )
                        res = VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=(f"{' '.join(replies)} {msg}".strip()),
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            clarification={
                                "kind": "disambiguate_product",
                                "prompt": msg,
                                "candidates": [
                                    {
                                        "id": str(c["id"]),
                                        "label": c["name"],
                                        "meta": f"Stock: {c['current_stock']:g} · ₹{float(c['default_selling_price']):g}",
                                        "value": c["name"],
                                    }
                                    for c in pres.candidates
                                ],
                            },
                        )
                        self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, op.model_dump(), "needs_clarification", "tier2", [], res, context_state, user_id)
                        return res
                    else:
                        # Brand-new unlisted product -> Voice prompt + interactive screen pop-up!
                        item_name = (op.product_query or "New Product").title()
                        msg = f"{item_name} inventory mein nahi mila — kya naya product add karun?"
                        unit_val = op.unit if op.unit in {"piece", "packet", "kg", "litre", "box"} else "piece"
                        popup = {
                            "name": item_name,
                            "category": "General",
                            "baseUnit": unit_val,
                            "quantity": op.quantity or 1,
                            "costPrice": str(op.unit_price or 0),
                            "sellingPrice": str(op.unit_price or 0),
                            "lowStockThreshold": "5",
                            "actionKind": "sale" if op.intent == "record_sale" else "receive",
                        }
                        res = VoiceTurnResult(
                            operation_id=operation_id,
                            status="new_product_popup",
                            transcript=raw_transcript,
                            reply=(f"{' '.join(replies)} {msg}".strip()),
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            new_product_draft=popup,
                        )
                        self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, op.model_dump(), "needs_clarification", "tier2", [], res, context_state, user_id)
                        return res

                if not target_prod:
                    continue

                if op.quantity is None:
                    msg = f"{target_prod['name']} ki kitni quantity hai?"
                    context_state["pending_flow"] = {
                        "type": "missing_slot",
                        "missing_field": "quantity",
                        "draft": {"intent": op.intent, "product_id": str(target_prod["id"]), "transaction_date": txn_date_str},
                    }
                    res = VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=msg,
                        language=language,  # type: ignore[arg-type]
                        receipts=receipts,
                    )
                    return res

                conv_qty, unit_err = convert_to_base_quantity(
                    quantity=float(op.quantity),
                    spoken_unit=op.unit,
                    base_unit=target_prod["base_unit"],
                )
                if unit_err or conv_qty is None:
                    res = VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=unit_err or "Unit clear nahi hai.",
                        language=language,  # type: ignore[arg-type]
                        receipts=receipts,
                    )
                    return res

                if op.intent == "inventory_receive" and op.unit_price is None:
                    remaining = [item.model_dump() for item in operations[idx + 1 :]]
                    if remaining:
                        context_state["pending_batch_items"] = remaining
                    draft = {
                        "intent": "inventory_receive",
                        "product_id": str(target_prod["id"]),
                        "product_name": target_prod["name"],
                        "quantity": conv_qty,
                        "unit": target_prod["base_unit"],
                        "transaction_date": txn_date_str,
                    }
                    return await self._complete_single_draft(
                        draft=draft,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=operation_id,
                        payload_hash=payload_hash,
                        raw_transcript=raw_transcript,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        products=products,
                        customers=customers,
                        context_state=context_state,
                    )

                try:
                    resolved_customer_id: str | None = None
                    resolved_customer_name: str | None = None
                    if op.intent == "record_sale" and op.customer_query:
                        cres_sale = resolve_customer(op.customer_query, customers)
                        if cres_sale.status == "ambiguous" and cres_sale.candidates:
                            names = " ya ".join(c["name"] for c in cres_sale.candidates)
                            msg = f"Khata mein {len(cres_sale.candidates)} {op.customer_query} hain ({names}). Kaunse customer ke liye?"
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=msg,
                                language=language,  # type: ignore[arg-type]
                                receipts=receipts,
                                clarification={
                                    "kind": "disambiguate_customer",
                                    "prompt": msg,
                                    "candidates": [
                                        {
                                            "id": str(c["id"]),
                                            "label": c["name"],
                                            "meta": f"Due ₹{float(c['outstanding_balance']):,.0f}",
                                            "value": c["name"],
                                        }
                                        for c in cres_sale.candidates
                                    ],
                                },
                            )
                        if cres_sale.status == "exact" and cres_sale.customer:
                            resolved_customer_id = str(cres_sale.customer["id"])
                            resolved_customer_name = cres_sale.customer["name"]
                        elif op.payment_status == "credit":
                            new_cust = self.tx.create_customer(
                                business_id=business_id,
                                name=op.customer_query.title(),
                            )
                            customers.append(new_cust)
                            resolved_customer_id = str(new_cust["id"])
                            resolved_customer_name = new_cust["name"]

                    draft = {
                        "intent": op.intent,
                        "product_id": str(target_prod["id"]),
                        "product_name": target_prod["name"],
                        "quantity": conv_qty,
                        "unit": target_prod["base_unit"],
                        "unit_price": op.unit_price,
                        "payment_status": op.payment_status or "paid",
                        "payment_method": op.payment_method or "cash",
                        "paid_amount": op.paid_amount,
                        "customer_id": resolved_customer_id,
                        "customer_name": resolved_customer_name,
                        "transaction_date": txn_date_str,
                        "notes": op.notes,
                    }
                    slip, rep = self._commit_draft_now(
                        draft=draft,
                        business_id=business_id,
                        user_id=user_id,
                        operation_id=sub_op_id,
                        txn_date=txn_date_str,
                        product=target_prod,
                        context_state=context_state,
                    )
                    # Refresh in-memory stock for subsequent items in the same multi-command breath!
                    delta = conv_qty if op.intent == "inventory_receive" else -conv_qty
                    target_prod["current_stock"] = float(target_prod["current_stock"]) + delta
                    receipts.append(slip)
                    replies.append(rep)
                except InsufficientStockError as exc:
                    res = VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=exc.message,
                        language=language,  # type: ignore[arg-type]
                        receipts=receipts,
                        clarification={"kind": "negative_stock", "prompt": exc.message},
                    )
                    return res

            elif op.intent == "record_expense" and op.total_amount:
                slip, rep = self._commit_draft_now(
                    draft={
                        "intent": "record_expense",
                        "total_amount": float(op.total_amount),
                        "expense_category": op.expense_category or "Shop Expense",
                        "description": op.description or raw_transcript,
                        "payment_method": op.payment_method or "cash",
                    },
                    business_id=business_id,
                    user_id=user_id,
                    operation_id=sub_op_id,
                    txn_date=txn_date_str,
                    product=None,
                    context_state=context_state,
                )
                receipts.append(slip)
                replies.append(rep)

            elif op.intent in {"create_customer", "update_customer", "record_udhaar_credit", "record_customer_payment"}:
                if op.intent == "create_customer" and op.customer_query:
                    new_c = self.tx.create_customer(
                        business_id=business_id,
                        name=op.customer_query,
                        phone=op.phone or "",
                        area_note=op.area_note or "",
                        opening_balance=float(op.total_amount or 0),
                    )
                    customers.append(new_c)
                    rep = f"Customer {new_c['name']} Khata mein add ho gaya hai."
                    replies.append(rep)
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "payment",
                            "title": f"Customer Added · {new_c['name']}",
                            "subtitle": new_c.get("area_note") or "Khata Profile Created",
                            "transactionDate": txn_date_str,
                            "lines": [{"label": "Opening Balance", "value": f"₹{float(new_c['outstanding_balance']):,.0f}", "tone": "neutral"}],
                            "status": "saved",
                        }
                    )
                else:
                    cres = resolve_customer(op.customer_query, customers)
                    if cres.status == "ambiguous" and cres.candidates:
                        names = " ya ".join(c["name"] for c in cres.candidates)
                        msg = f"Khata mein {len(cres.candidates)} {op.customer_query} hain ({names}). Kaunse customer ke liye?"
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=msg,
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            clarification={
                                "kind": "disambiguate_customer",
                                "prompt": msg,
                                "candidates": [
                                    {"id": str(c["id"]), "label": c["name"], "meta": f"Due ₹{float(c['outstanding_balance']):,.0f}", "value": c["name"]}
                                    for c in cres.candidates
                                ],
                            },
                        )
                    if cres.status != "exact" or not cres.customer:
                        msg = f"'{op.customer_query}' Khata mein nahi mila. Kya naya customer add karun?"
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=msg,
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                        )
                    cust = cres.customer
                    if op.intent == "update_customer":
                        self.tx.update_customer(
                            business_id=business_id,
                            customer_id=str(cust["id"]),
                            phone=op.phone,
                            area_note=op.area_note,
                        )
                        rep = f"{cust['name']} ki Khata details update ho gayi hain."
                        replies.append(rep)
                    elif op.intent == "record_udhaar_credit":
                        amt = float(op.total_amount or op.unit_price or 0)
                        if amt <= 0:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=f"{cust['name']} ke khate mein kitne rupaye udhaar likhne hain?",
                                language=language,  # type: ignore[arg-type]
                            )
                        ud = self.tx.record_direct_udhaar(
                            business_id=business_id,
                            user_id=user_id,
                            customer_id=str(cust["id"]),
                            amount=amt,
                            transaction_date=txn_date_str,
                            operation_id=sub_op_id,
                            notes=op.description or "Voice Khata entry",
                        )
                        rep = f"{cust['name']} ke khate mein ₹{amt:,.0f} udhaar likh diya gaya (Balance ₹{ud['after_balance']:,.0f})."
                        replies.append(rep)
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "sale",
                                "title": f"Khata Udhaar · {cust['name']}",
                                "subtitle": "Direct Credit Entry",
                                "transactionDate": txn_date_str,
                                "amountINR": amt,
                                "lines": [{"label": "New Balance", "value": f"₹{ud['after_balance']:,.0f}", "tone": "ochre"}],
                                "status": "saved",
                            }
                        )
                    elif op.intent == "record_customer_payment":
                        amt = float(op.total_amount or op.paid_amount or op.unit_price or 0)
                        if amt <= 0:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=f"{cust['name']} se kitne rupaye receive hue?",
                                language=language,  # type: ignore[arg-type]
                            )
                        pay = self.tx.record_customer_payment(
                            business_id=business_id,
                            user_id=user_id,
                            customer_id=str(cust["id"]),
                            amount=amt,
                            payment_method=op.payment_method or "cash",
                            transaction_date=txn_date_str,
                            operation_id=sub_op_id,
                        )
                        rep = f"{cust['name']} se ₹{amt:,.0f} receive ho gaya. Remaining balance: ₹{pay['after_balance']:,.0f}."
                        replies.append(rep)
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "payment",
                                "title": f"Payment Received · {cust['name']}",
                                "subtitle": f"Via {'Online' if (op.payment_method or 'cash') == 'upi' else (op.payment_method or 'cash').title()}",
                                "transactionDate": txn_date_str,
                                "amountINR": amt,
                                "lines": [{"label": "Remaining Balance", "value": f"₹{pay['after_balance']:,.0f}", "tone": "sage"}],
                                "status": "saved",
                            }
                        )

            elif op.intent == "update_product_settings":
                if not op.product_query:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Kis product ka price ya low-stock limit update karna hai?",
                        language=language,  # type: ignore[arg-type]
                    )
                pres = resolve_product(op.product_query, products, aliases)
                if pres.status == "ambiguous":
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{op.product_query}' mein multiple items mile. Kaunsa item update karna hai?",
                        language=language,  # type: ignore[arg-type]
                        clarification={
                            "kind": "disambiguate_product",
                            "prompt": f"Select item for '{op.product_query}'",
                            "options": [{"id": str(c["id"]), "label": c["name"], "value": c["name"]} for c in pres.candidates],
                        },
                    )
                if pres.status in {"exact", "verify_alias"} and pres.product:
                    p = pres.product
                    self.tx.update_product_settings(
                        business_id=business_id,
                        product_id=str(p["id"]),
                        cost_price=op.cost_price,
                        selling_price=op.unit_price,
                        low_stock_threshold=op.low_stock_threshold,
                    )
                    rep = f"{p['name']} ki settings update ho gayi hain."
                    replies.append(rep)
                else:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{op.product_query}' inventory mein nahi mila. Kripya sahi naam bolein.",
                        language=language,  # type: ignore[arg-type]
                    )

            elif op.intent == "archive_product":
                if not op.product_query:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Kis item ko catalog se archive karna hai?",
                        language=language,  # type: ignore[arg-type]
                    )
                pres = resolve_product(op.product_query, products, aliases)
                if pres.status == "ambiguous":
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{op.product_query}' mein multiple variants hain. Kaunse item ko archive karna hai?",
                        language=language,  # type: ignore[arg-type]
                        clarification={
                            "kind": "disambiguate_product",
                            "prompt": f"Kaunsa '{op.product_query}' archive karna hai?",
                            "options": [{"id": str(c["id"]), "label": c["name"], "value": c["name"]} for c in pres.candidates],
                        },
                    )
                if pres.status not in {"exact", "verify_alias"} or not pres.product:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{op.product_query}' catalog mein nahi mila.",
                        language=language,  # type: ignore[arg-type]
                    )
                p = pres.product
                draft = {
                    "intent": "archive_product",
                    "product_id": str(p["id"]),
                    "transaction_date": txn_date_str,
                }
                token = self.tx.issue_confirmation_token(
                    business_id=business_id,
                    user_id=user_id,
                    operation_id=operation_id,
                    draft_payload=draft,
                    risk_reason=f"Archive SKU {p['name']} from active catalog",
                )
                return VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_confirmation",
                    transcript=raw_transcript,
                    reply=f"Confirm karein: Kya aap '{p['name']}' ko active inventory catalog se archive karna chahte hain?",
                    language=language,  # type: ignore[arg-type]
                    confirmation_token=token,
                    confirmation_summary={
                        "title": f"Archive {p['name']}",
                        "subtitle": "Soft-archive only (ledger history stays intact)",
                        "amount_inr": 0,
                        "reason": "Catalog visibility change requires owner confirmation",
                    },
                )

        final_reply = " ".join(replies) if replies else "Kripya item aur quantity saaf bolein."
        status_out = "query_answered" if all(r.get("kind") == "query" for r in receipts) and receipts else "executed"
        res = VoiceTurnResult(
            operation_id=operation_id,
            status=status_out,  # type: ignore[arg-type]
            transcript=raw_transcript,
            reply=final_reply,
            language=language,  # type: ignore[arg-type]
            receipts=receipts,
        )
        self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, {"ops_count": len(operations)}, "executed", "tier1", receipts, res, context_state, user_id)
        return res

    def confirm_tier3(
        self,
        *,
        business_id: str,
        user_id: str,
        req: ConfirmOperationRequest,
    ) -> VoiceTurnResult:
        biz, _ = self._load_business_and_sub(business_id)
        tz_name = biz.get("timezone", "Asia/Kolkata")
        today_str = get_business_today(tz_name).isoformat()
        if not req.accept:
            return VoiceTurnResult(
                operation_id=req.operation_id,
                status="executed",
                transcript="Cancelled",
                reply="Transaction cancel kar diya gaya hai.",
                receipts=[],
            )
        draft = self.tx.verify_and_consume_confirmation_token(
            business_id=business_id,
            user_id=user_id,
            operation_id=req.operation_id,
            raw_token=req.confirmation_token,
        )
        products, _, _ = self._load_catalog(business_id)
        product = next((p for p in products if str(p["id"]) == str(draft.get("product_id"))), None)
        conv = self.memory.get_or_create_day_conversation(business_id=business_id, timezone_name=tz_name)
        ctx = dict(conv.get("context_state") or {})
        slip, reply = self._commit_draft_now(
            draft=draft,
            business_id=business_id,
            user_id=user_id,
            operation_id=req.operation_id,
            txn_date=draft.get("transaction_date", today_str),
            product=product,
            context_state=ctx,
        )
        self.memory.update_context_state(conversation_id=conv["id"], state=ctx)
        res = VoiceTurnResult(
            operation_id=req.operation_id,
            status="executed",
            transcript="Confirmed",
            reply=reply,
            receipts=[slip],
        )
        self.memory.append_message(
            conversation_id=conv["id"],
            business_id=business_id,
            conversation_date=today_str,
            role="assistant",
            content=res.reply,
            language="hinglish",
            linked_operation_id=req.operation_id,
            ui_payload=res.model_dump(),
        )
        return res

    def create_product_and_execute(
        self,
        *,
        business_id: str,
        user_id: str,
        req: CreateProductAndExecuteRequest,
    ) -> VoiceTurnResult:
        biz, _ = self._load_business_and_sub(business_id)
        tz_name = biz.get("timezone", "Asia/Kolkata")
        today_str = get_business_today(tz_name).isoformat()
        conv = self.memory.get_or_create_day_conversation(business_id=business_id, timezone_name=tz_name)
        self.tx.create_product_and_stock(
            business_id=business_id,
            user_id=user_id,
            name=req.name,
            category=req.category,
            base_unit=req.base_unit,
            cost_price=req.cost_price,
            selling_price=req.selling_price,
            low_stock_threshold=req.low_stock_threshold,
            opening_qty=req.quantity,
            transaction_date=today_str,
            operation_id=req.operation_id,
        )
        reply = f"Naya product {req.name} ({req.quantity:g} {req.base_unit}) catalog aur stock mein add ho gaya hai."
        slip = {
            "id": f"slip-{req.operation_id}",
            "operationId": req.operation_id,
            "kind": "receive",
            "title": f"New SKU Added · {req.name}",
            "subtitle": "Confirmed via Voice / Screen Pop-up",
            "transactionDate": today_str,
            "amountINR": req.quantity * req.cost_price,
            "lines": [
                {"label": "Opening Stock", "value": f"+{req.quantity:g} {req.base_unit}", "tone": "sage"},
                {"label": "Cost / Sell", "value": f"₹{req.cost_price:g} / ₹{req.selling_price:g}", "tone": "neutral"},
            ],
            "status": "saved",
            "reversible": True,
        }
        res = VoiceTurnResult(
            operation_id=req.operation_id,
            status="executed",
            transcript=f"Add {req.name}",
            reply=reply,
            receipts=[slip],
        )
        self.memory.append_message(
            conversation_id=conv["id"],
            business_id=business_id,
            conversation_date=today_str,
            role="assistant",
            content=res.reply,
            language="hinglish",
            linked_operation_id=req.operation_id,
            ui_payload=res.model_dump(),
        )
        return res

    def _finalize_turn(
        self,
        conv_id: str,
        business_id: str,
        today_str: str,
        operation_id: str,
        payload_hash: str,
        raw_transcript: str,
        language: str,
        stt_provider: str,
        stt_confidence: float | None,
        parsed_intent: dict[str, Any],
        validation_status: str,
        risk_tier: str,
        affected_records: list[dict[str, Any]],
        result: VoiceTurnResult,
        context_state: dict[str, Any],
        user_id: str,
    ) -> None:
        self.memory.update_context_state(conversation_id=conv_id, state=context_state)
        self.memory.append_message(
            conversation_id=conv_id,
            business_id=business_id,
            conversation_date=today_str,
            role="assistant",
            content=result.reply,
            language=language,
            linked_operation_id=operation_id,
            ui_payload=result.model_dump(),
        )
        self.tx.log_voice_transaction(
            business_id=business_id,
            conversation_id=conv_id,
            operation_id=operation_id,
            payload_hash=payload_hash,
            transaction_date=today_str,
            raw_transcript=raw_transcript,
            detected_language=language,
            stt_provider=stt_provider,
            stt_confidence=stt_confidence,
            parsed_intent=parsed_intent,
            validation_status=validation_status,
            risk_tier=risk_tier,
            affected_records=affected_records,
            response_payload=result.model_dump(),
            audit_trail=[{"action": validation_status, "timestamp": today_str}],
            user_id=user_id,
        )
        if validation_status in {"executed", "auto_executed"}:
            self.tx.increment_voice_quota(business_id=business_id)
