from datetime import timedelta
import re
from typing import Any
import uuid

from app.core.config import get_settings
from app.core.entitlements import assert_voice_quota
from app.core.exceptions import InsufficientStockError, PolicyBlockedError
from app.core.i18n_replies import localize_reply_async, romanize_devanagari_to_hinglish
from app.core.policy import SecurityPolicyEngine
from app.core.security import canonical_payload_hash, validate_audio_upload
from app.core.time_utils import (
    check_memory_window_days,
    detect_over_30_day_reference,
    get_business_today,
    resolve_relative_date,
)
from app.domain.indian_numbers import (
    extract_post_negation_number,
    extract_post_negation_quantity,
    parse_indian_number,
)
from app.domain.schemas.intents import (
    ConfirmOperationRequest,
    CreateProductAndExecuteRequest,
    VoiceOperationItem,
    VoiceTurnResult,
)
from app.domain.unit_converter import convert_to_base_quantity
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.gemini import deterministic_fallback_parse
from app.providers.stt.factory import get_stt_provider
from app.services.entity_resolver import (
    extract_clause_price_hint,
    extract_product_price_hint,
    filter_candidates_by_price,
    resolve_customer,
    resolve_product,
    resolve_product_guarded,
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

    @staticmethod
    def _split_customers_and_suppliers(
        accounts: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        custs: list[dict[str, Any]] = []
        sups: list[dict[str, Any]] = []
        for row in accounts:
            if "[SUPPLIER]" in str(row.get("area_note") or "").upper():
                sups.append(row)
            else:
                custs.append(row)
        return custs, sups

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
        selected_lang = language if language in {"hinglish", "hi", "en"} else "hinglish"
        stt = get_stt_provider()
        stt_res = await stt.transcribe(
            audio_bytes,
            filename=filename,
            content_type=content_type or "audio/webm",
            language_hint=selected_lang,
        )
        if stt_res.is_unclear or not stt_res.text:
            retry_msg = await localize_reply_async(
                "Awaaz clear nahi thi ya background noise zyada tha. Kripya dobara bolein.",
                selected_lang,
            )
            return VoiceTurnResult(
                operation_id=operation_id,
                status="retry_audio",
                transcript="",
                reply=retry_msg,
                language=selected_lang,  # type: ignore[arg-type]
            )

        return await self.process_text_turn(
            business_id=business_id,
            user_id=user_id,
            text=stt_res.text,
            operation_id=operation_id,
            language=selected_lang,
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
        selected_lang = language if language in {"hinglish", "hi", "en"} else "hinglish"
        clean_text = text.strip()
        if selected_lang == "hinglish":
            clean_text = romanize_devanagari_to_hinglish(clean_text)

        res = await self._process_text_turn_inner(
            business_id=business_id,
            user_id=user_id,
            text=clean_text,
            operation_id=operation_id,
            language=selected_lang,
            stt_provider=stt_provider,
            stt_confidence=stt_confidence,
        )
        res.language = selected_lang  # type: ignore[assignment]
        if selected_lang in {"en", "hi"} and res.reply:
            localized = await localize_reply_async(res.reply, selected_lang)
            if localized and localized != res.reply:
                res.reply = localized
                if res.clarification and isinstance(res.clarification, dict) and res.clarification.get("prompt"):
                    res.clarification["prompt"] = localized
                try:
                    self.db.table("conversation_messages").update(
                        {"content": localized, "language": selected_lang}
                    ).eq("business_id", business_id).eq("linked_operation_id", operation_id).eq(
                        "role", "assistant"
                    ).execute()
                except Exception:
                    pass
        return res

    async def _process_text_turn_inner(
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
        catalog_hints = [
            {
                "name": p["name"],
                "unit": p["base_unit"],
                "price": float(p.get("default_selling_price") or 0),
                "stock": p["current_stock"],
            }
            for p in products
        ]
        customer_hints = [
            {
                "name": c["name"],
                "area": str(c.get("area_note") or "").replace("[SUPPLIER]", "").strip(),
                "type": "supplier" if "[SUPPLIER]" in str(c.get("area_note") or "").upper() else "customer",
                "due": float(c["outstanding_balance"]),
            }
            for c in customers
        ]

        llm = get_llm_provider()
        proposal = await llm.parse_utterance(
            utterance=clean_text,
            language_hint=language,
            context_summary=llm_ctx,
            catalog_hints=catalog_hints,
            customer_hints=customer_hints,
        )

        # Rescue explicit corrections (payment method, sale/damage/expiry/receive quantity)
        # when recent context exists so LLM uncertainty or misrouting doesn't drop/corrupt the update.
        has_recent_op = bool(
            context_state.get("last_operation_kind")
            or context_state.get("last_sale_id")
            or context_state.get("last_expense_id")
            or context_state.get("last_damage_operation_id")
        )
        looks_like_correction = bool(
            re.search(
                r"(?:cash\s+(?:se\s+)?(?:nahi|नहीं)|online\s+(?:se\s+)?(?:nahi|नहीं)|upi\s+(?:se\s+)?(?:nahi|नहीं)"
                r"|last\s+transaction|\b(?:sorry|actually|galti\s+se|ki\s+jagah|instead\s+of)\b"
                r"|(?:\b\d+|\bek\b|\bdo\b|\bteen\b|\bchaar\b|\bpaanch\b)\s+(?:\w+\s+){0,2}(?:nahi|nahin|नहीं)\b"
                r"|\bnot\s+(?:\d+|one|two|three)\b|\bbas\s+(?:\d+|ek|do|teen)\s+hi\b)",
                clean_text,
                re.IGNORECASE,
            )
        )
        if has_recent_op and looks_like_correction:
            top_intent = proposal.operations[0].intent if proposal.operations else "unknown"
            has_expense_words = bool(
                re.search(r"\b(expense|kharcha|kharch|bill|bijli|electricity|rent|kiraya|tea|chai|rupaye|rs)\b|₹", clean_text, re.IGNORECASE)
            )
            if (
                proposal.confidence < 0.85
                or proposal.has_ambiguity_or_noise_conflict
                or top_intent in {"unknown", "clarify_response"}
                or (top_intent == "record_expense" and not has_expense_words)
            ):
                normalized_correction = (
                    romanize_devanagari_to_hinglish(clean_text)
                    .replace("से नहीं", "se nahi")
                    .replace("नहीं", "nahi")
                    .replace("कैश", "cash")
                    .replace("ऑनलाइन", "online")
                )
                rescued = deterministic_fallback_parse(normalized_correction, language)
                if rescued.operations and rescued.operations[0].intent == "correct_last_operation":
                    proposal = rescued
                    proposal.has_ambiguity_or_noise_conflict = False
                    proposal.confidence = 0.95

        # 4b. Zero-Assumption Background Noise / Low-Confidence Guard
        # If the LLM flagged ambiguity solely because multiple catalog variants match (e.g. 70g vs 250g),
        # let _execute_operations_batch handle it so the user gets interactive product chips instead of Yes/No.
        if proposal.has_ambiguity_or_noise_conflict or proposal.confidence < 0.85:
            bypass_to_batch = False
            candidate_ops = proposal.operations
            if not candidate_ops:
                fb = deterministic_fallback_parse(clean_text, language)
                if fb.operations and fb.operations[0].intent != "unknown":
                    candidate_ops = fb.operations
            if len(candidate_ops) == 1 and candidate_ops[0].product_query and candidate_ops[0].intent in {
                "record_sale",
                "inventory_receive",
                "inventory_damage",
                "inventory_expiry",
                "inventory_adjust",
                "update_product_settings",
                "archive_product",
            }:
                pres_check = resolve_product_guarded(
                    candidate_ops[0].product_query,
                    clean_text,
                    products,
                    aliases,
                    price_hint=candidate_ops[0].price_hint,
                )
                if pres_check.status in {"ambiguous", "verify_alias", "not_found"}:
                    proposal.operations = candidate_ops
                    bypass_to_batch = True

            if not bypass_to_batch:
                clar_msg = (
                    proposal.clarification_question
                    or "Mujhe thoda confusion hai (background awaaz ya unclear intent ke kaaran). Kripya dubara confirm karein ki aap kya record karna chahte hain?"
                )
                if proposal.operations:
                    context_state["pending_flow"] = {
                        "type": "confirm_proposed_ops",
                        "operations": [op.model_dump() for op in proposal.operations],
                        "prompt": clar_msg,
                    }
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=clean_text,
                    reply=clar_msg,
                    language=proposal.detected_language,
                    clarification={
                        "kind": "missing_slot",
                        "prompt": clar_msg,
                        **(
                            {
                                "candidates": [
                                    {"id": "yes", "label": "Yes, confirm", "value": "Yes"},
                                    {"id": "no", "label": "No, cancel", "value": "No"},
                                ]
                            }
                            if proposal.operations
                            else {}
                        ),
                    },
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

        # If user abandons pending clarification with a brand-new command (e.g. "2 packets of Maggi masala 70 gram sold")
        # or a payment-method correction ("Last transaction cash se nahi online hua tha"),
        # clear pending_flow and let the main pipeline execute the new command cleanly.
        new_cmd_pattern = re.compile(
            r"(?:\b(?:sold|bik|biki|bika|bech|bechi|aayi|aaya|receive|add|expense|kharcha|udhaar|khata|paid|payment|damage|damaged|demis|expire|expired|inventory|stock|cancel|chhodo|hatao)\b|(?:cash|online|upi)\s+(?:se\s+)?(?:nahi|नहीं)|last\s+transaction)",
            re.IGNORECASE,
        )
        is_short_confirm = any(lower.startswith(w) for w in ("yes", "haan", "ha ", "ha", "ji", "ok", "same", "free", "confirm", "bilkul", "theek"))
        if not is_short_confirm and new_cmd_pattern.search(lower):
            context_state.pop("pending_flow", None)
            if re.search(r"\b(cancel|chhodo|hatao)\b", lower):
                msg = "Theek hai, pichla step cancel kar diya gaya."
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="executed",
                    transcript=reply_text,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, reply_text, language, stt_provider, stt_confidence, pending_flow, "executed", "tier2", [], res, context_state, user_id)
                return res
            return None

        if flow_type == "confirm_proposed_ops":
            if any(lower.startswith(w) for w in ("yes", "haan", "ha ", "ha", "ji", "bilkul", "confirm", "ok", "theek")):
                ops = [VoiceOperationItem.model_validate(item) for item in pending_flow.get("operations", [])]
                context_state.pop("pending_flow", None)
                if ops:
                    _, aliases, _ = self._load_catalog(business_id)
                    return await self._execute_operations_batch(
                        operations=ops,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        tz_name=tz_name,
                        operation_id=operation_id,
                        payload_hash=payload_hash,
                        raw_transcript=reply_text,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        products=products,
                        aliases=aliases,
                        customers=customers,
                        context_state=context_state,
                    )
            if any(lower.startswith(w) for w in ("no", "nahi", "na ", "cancel", "mat", "galat")):
                context_state.pop("pending_flow", None)
                msg = "Theek hai, cancel kar diya gaya. Kripya batayein ab kya karna hai."
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=reply_text,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, reply_text, language, stt_provider, stt_confidence, pending_flow, "needs_clarification", "tier2", [], res, context_state, user_id)
                return res

        if flow_type == "tier3_confirm":
            if any(lower.startswith(w) for w in ("yes", "haan", "ha ", "ha", "ji", "bilkul", "confirm", "ok", "theek")):
                context_state.pop("pending_flow", None)
                pending_batch_t3 = context_state.pop("pending_batch_items", [])
                batch_src_t3 = context_state.pop("pending_batch_source_transcript", None) or reply_text
                self.memory.update_context_state(conversation_id=conv_id, state=context_state)
                t3_res = self.confirm_tier3(
                    business_id=business_id,
                    user_id=user_id,
                    req=ConfirmOperationRequest(
                        operation_id=str(pending_flow["operation_id"]),
                        confirmation_token=str(pending_flow["token"]),
                        accept=True,
                    ),
                )
                if pending_batch_t3:
                    _, real_aliases, _ = self._load_catalog(business_id)
                    batch_items = [VoiceOperationItem.model_validate(item) for item in pending_batch_t3]
                    return await self._execute_operations_batch(
                        operations=batch_items,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        tz_name=tz_name,
                        operation_id=str(uuid.uuid4()),
                        payload_hash=canonical_payload_hash({"t3_batch_resume": operation_id}),
                        raw_transcript=batch_src_t3,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        products=products,
                        aliases=real_aliases,
                        customers=customers,
                        context_state=context_state,
                        prefix_receipts=list(t3_res.receipts or []),
                        prefix_replies=[t3_res.reply] if t3_res.reply else [],
                    )
                return t3_res
            if any(lower.startswith(w) for w in ("no", "nahi", "na ", "cancel", "mat", "galat")):
                context_state.pop("pending_flow", None)
                msg = "High-value transaction cancel kar diya gaya hai. Koi record change nahi hua."
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="executed",
                    transcript=reply_text,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, reply_text, language, stt_provider, stt_confidence, pending_flow, "executed", "tier3", [], res, context_state, user_id)
                return res

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
            _, r_price = extract_product_price_hint(reply_text)
            if r_price is None and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", reply_text.strip()):
                cand_p = float(reply_text.strip())
                if filter_candidates_by_price(cands, cand_p):
                    r_price = cand_p
            if r_price is not None:
                priced_cands = filter_candidates_by_price(cands, r_price)
                if len(priced_cands) > 1:
                    context_state["pending_flow"] = {
                        "type": "disambiguate_product",
                        "candidate_ids": [str(c["id"]) for c in priced_cands],
                        "draft": pending_flow["draft"],
                    }
                    names = " ya ".join(c["name"] for c in priced_cands)
                    msg = f"₹{r_price:g} mein {len(priced_cands)} options mile: {names}. Confirm karein kaunsa wala?"
                    res = VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=reply_text,
                        reply=msg,
                        language=language,  # type: ignore[arg-type]
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
                                for c in priced_cands
                            ],
                        },
                    )
                    self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, reply_text, language, stt_provider, stt_confidence, pending_flow, "needs_clarification", "tier2", [], res, context_state, user_id)
                    return res

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
            cleaned_slot_text = re.sub(
                r"\b\d+(?:\.\d+)?\s*(?:g|gm|gram|grams|kg|kilo|ml|l|litre|liter)\b",
                " ",
                reply_text,
                flags=re.IGNORECASE,
            )
            val = parse_indian_number(cleaned_slot_text)
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
            elif missing_field == "supplier_name" and reply_text.strip():
                names_raw = [n.strip() for n in re.split(r"(?:,|\band\b|\baur\b)", reply_text, flags=re.IGNORECASE) if n.strip()]
                context_state.pop("pending_flow", None)
                sup_intent = str(draft.get("intent") or "record_supplier_payment")
                sup_amt_v = float(draft.get("total_amount") or 0)
                pm_v = str(draft.get("payment_method") or "cash")
                ops_sup: list[VoiceOperationItem] = []
                for nm in names_raw:
                    amt_for_nm = sup_amt_v if sup_amt_v > 0 else None
                    if amt_for_nm is None:
                        hit_s = next(
                            (
                                r for r in customers
                                if "[SUPPLIER]" in str(r.get("area_note") or "").upper()
                                and (nm.lower() in str(r.get("name") or "").lower() or str(r.get("name") or "").lower() in nm.lower())
                            ),
                            None,
                        )
                        if hit_s and float(hit_s.get("outstanding_balance") or 0) > 0:
                            amt_for_nm = float(hit_s["outstanding_balance"])
                    ops_sup.append(
                        VoiceOperationItem(
                            intent=sup_intent,  # type: ignore[arg-type]
                            customer_query=nm,
                            total_amount=amt_for_nm,
                            payment_method=pm_v,  # type: ignore[arg-type]
                        )
                    )
                pending_batch_s = context_state.pop("pending_batch_items", [])
                batch_src_s = context_state.pop("pending_batch_source_transcript", None) or reply_text
                for item in pending_batch_s:
                    ops_sup.append(VoiceOperationItem.model_validate(item))
                if ops_sup:
                    _, real_aliases, _ = self._load_catalog(business_id)
                    return await self._execute_operations_batch(
                        operations=ops_sup,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        tz_name=tz_name,
                        operation_id=operation_id,
                        payload_hash=payload_hash,
                        raw_transcript=batch_src_s,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        products=products,
                        aliases=real_aliases,
                        customers=customers,
                        context_state=context_state,
                    )
                return None
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

    def _issue_tier3_response(
        self,
        *,
        draft: dict[str, Any],
        title: str,
        description: str,
        total_val: float,
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
        context_state: dict[str, Any],
        prefix_receipts: list[dict[str, Any]] | None = None,
    ) -> VoiceTurnResult:
        token = self.tx.issue_confirmation_token(
            business_id=business_id,
            user_id=user_id,
            operation_id=operation_id,
            proposed_action=draft,
        )
        context_state["pending_flow"] = {
            "type": "tier3_confirm",
            "operation_id": operation_id,
            "token": token,
        }
        msg = f"Yeh ₹{total_val:,.0f} ka high-value transaction hai ({description}). Confirm karne ke liye 'Yes' bolein ya Confirm dabayein."
        res = VoiceTurnResult(
            operation_id=operation_id,
            status="needs_confirmation",
            transcript=raw_transcript,
            reply=msg,
            language=language,  # type: ignore[arg-type]
            receipts=list(prefix_receipts or []),
            confirmation={
                "operationId": operation_id,
                "token": token,
                "title": title,
                "description": description,
                "amountINR": total_val,
                "impactSummary": f"Total value ₹{total_val:,.0f} requires Tier-3 authorization",
                "payload": draft,
            },
        )
        self._finalize_turn(
            conv_id,
            business_id,
            today_str,
            operation_id,
            payload_hash,
            raw_transcript,
            language,
            stt_provider,
            stt_confidence,
            draft,
            "needs_confirmation",
            "tier3",
            [],
            res,
            context_state,
            user_id,
        )
        return res

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

        if intent == "record_sale" and draft.get("customer_query") and not draft.get("customer_id"):
            non_sup_draft, _ = self._split_customers_and_suppliers(customers)
            cres_d = resolve_customer(str(draft["customer_query"]), non_sup_draft)
            if cres_d.status == "ambiguous" and cres_d.candidates:
                context_state["pending_flow"] = {
                    "type": "disambiguate_customer",
                    "candidate_ids": [str(c["id"]) for c in cres_d.candidates],
                    "draft": draft,
                }
                names = " ya ".join(c["name"] for c in cres_d.candidates)
                msg = f"Khata mein {len(cres_d.candidates)} {draft['customer_query']} hain ({names}). Kaunse customer ke liye?"
                res = VoiceTurnResult(
                    operation_id=operation_id,
                    status="needs_clarification",
                    transcript=raw_transcript,
                    reply=msg,
                    language=language,  # type: ignore[arg-type]
                    clarification={
                        "kind": "disambiguate_customer",
                        "prompt": msg,
                        "candidates": [
                            {"id": str(c["id"]), "label": c["name"], "meta": f"Due ₹{float(c['outstanding_balance']):,.0f}", "value": c["name"]}
                            for c in cres_d.candidates
                        ],
                    },
                )
                self._finalize_turn(conv_id, business_id, today_str, operation_id, payload_hash, raw_transcript, language, stt_provider, stt_confidence, draft, "needs_clarification", "tier2", [], res, context_state, user_id)
                return res
            if cres_d.status == "exact" and cres_d.customer:
                draft["customer_id"] = str(cres_d.customer["id"])
                draft["customer_name"] = cres_d.customer["name"]
            elif (draft.get("payment_status") in {"credit", "partial"}) and cres_d.status == "not_found":
                new_cust = self.tx.create_customer(
                    business_id=business_id,
                    name=str(draft["customer_query"]).title(),
                )
                customers.append(new_cust)
                draft["customer_id"] = str(new_cust["id"])
                draft["customer_name"] = new_cust["name"]

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
        batch_source_text = context_state.pop("pending_batch_source_transcript", None) or raw_transcript
        if pending_batch:
            _, real_aliases, _ = self._load_catalog(business_id)
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
                raw_transcript=batch_source_text,
                language=language,
                stt_provider=stt_provider,
                stt_confidence=stt_confidence,
                products=products,
                aliases=real_aliases,
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
            context_state["last_receive_cost"] = unit_cost
            context_state["last_operation_kind"] = "inventory_receive"
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
            sale_notes = f"{'[ONLINE]' if p_method == 'upi' else ('[UDHAAR]' if p_status == 'credit' else '[CASH]')} {draft.get('notes') or 'Voice sale'}"
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
                notes=sale_notes,
            )
            context_state["last_product_id"] = str(product["id"])
            context_state["last_product_name"] = product["name"]
            context_state["last_sale_id"] = str(rpc["sale_id"])
            context_state["last_sale_total"] = total
            context_state["last_sale_qty"] = qty
            context_state["last_operation_kind"] = "record_sale"
            context_state["last_operation_id"] = operation_id
            method_label = "Online" if p_method == "upi" else ("Bank" if p_method == "bank" else "Cash")
            if p_status == "credit":
                who = cust_name or "Customer"
                reply = f"{qty:g} {product['name']} {who} ke Khata mein Udhaar (₹{total:,.0f}) add ho gayi. Revenue mein abhi add nahi hua."
                subtitle = f"Udhaar · {who} (Unpaid)"
                extra_lines = [{"label": "Khata Udhaar", "value": f"₹{total:,.0f} (Not in revenue)", "tone": "ochre"}]
            elif p_status == "partial" and 0 < paid < total:
                who = cust_name or "Customer"
                rem_due = round(total - paid, 2)
                reply = (
                    f"{qty:g} {product['name']} ki sale (₹{total:,.0f}): ₹{paid:,.0f} {method_label} aur "
                    f"₹{rem_due:,.0f} {who} ke Khata mein Udhaar save ho gaya."
                )
                subtitle = f"Split · {who} ({method_label} + Udhaar)"
                extra_lines = [
                    {"label": f"Paid ({method_label})", "value": f"₹{paid:,.0f}", "tone": "sage"},
                    {"label": "Khata Udhaar", "value": f"₹{rem_due:,.0f}", "tone": "ochre"},
                ]
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
            context_state["last_product_id"] = str(product["id"])
            context_state["last_product_name"] = product["name"]
            context_state["last_operation_kind"] = intent
            context_state["last_operation_id"] = operation_id
            context_state["last_damage_product_id"] = str(product["id"])
            context_state["last_damage_product_name"] = product["name"]
            context_state["last_damage_qty"] = qty
            context_state["last_damage_type"] = mtype
            context_state["last_damage_operation_id"] = operation_id
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

        if intent == "settle_all_suppliers":
            pm_sup = str(draft.get("payment_method") or "cash")
            pm_lbl = "Online" if pm_sup == "upi" else ("Bank" if pm_sup == "bank" else "Cash")
            st = self.tx.settle_all_suppliers(
                business_id=business_id,
                user_id=user_id,
                payment_method=pm_sup,
                transaction_date=txn_date,
                operation_id=operation_id,
                supplier_ids=draft.get("supplier_ids"),
            )
            context_state["last_operation_kind"] = "record_supplier_payment"
            context_state["last_operation_id"] = operation_id
            names_paid = ", ".join(s["name"] for s in st["settled_suppliers"]) or "Suppliers"
            reply = f"Sabhi suppliers ({names_paid}) ka total ₹{st['total_paid']:,.0f} ({pm_lbl}) udhaar settle ho gaya."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "expense",
                "title": f"All Suppliers Settled · {st['settled_count']}",
                "subtitle": f"Via {pm_lbl}",
                "transactionDate": txn_date,
                "amountINR": st["total_paid"],
                "lines": [
                    {"label": s["name"], "value": f"Paid ₹{s['paid_amount']:,.0f}", "tone": "sage"}
                    for s in st["settled_suppliers"]
                ],
                "status": "saved",
                "reversible": True,
                "_supplier_ops": st["supplier_ops"],
            }
            return slip, reply

        if intent == "record_supplier_credit":
            sup_id = str(draft["supplier_id"])
            sup_name = str(draft["supplier_name"])
            amt = float(draft["total_amount"])
            sc = self.tx.record_supplier_credit(business_id=business_id, supplier_id=sup_id, amount=amt)
            context_state["last_operation_kind"] = "record_supplier_credit"
            context_state["last_operation_id"] = operation_id
            reply = f"Supplier {sup_name} ke Khata mein ₹{amt:,.0f} payable add ho gaya (Total Payable: ₹{sc['after_balance']:,.0f})."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "receive",
                "title": f"Supplier Credit · {sup_name}",
                "subtitle": "Wholesale Accounts Payable",
                "transactionDate": txn_date,
                "amountINR": amt,
                "lines": [
                    {"label": "Credit Added", "value": f"+₹{amt:,.0f}", "tone": "ochre"},
                    {"label": "Total Payable", "value": f"₹{sc['after_balance']:,.0f}", "tone": "neutral"},
                ],
                "status": "saved",
                "reversible": True,
                "_supplier_op": {"type": "credit", "supplier_id": sup_id, "amount": amt},
            }
            return slip, reply

        if intent == "record_supplier_payment":
            sup_id = str(draft["supplier_id"])
            sup_name = str(draft["supplier_name"])
            amt = float(draft["total_amount"])
            pm_sup = str(draft.get("payment_method") or "cash")
            pm_lbl = "Online" if pm_sup == "upi" else ("Bank" if pm_sup == "bank" else "Cash")
            sp = self.tx.record_supplier_payment(
                business_id=business_id,
                user_id=user_id,
                supplier_id=sup_id,
                supplier_name=sup_name,
                amount=amt,
                payment_method=pm_sup,
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_operation_kind"] = "record_supplier_payment"
            context_state["last_operation_id"] = operation_id
            reply = f"Supplier {sup_name} ko ₹{amt:,.0f} ({pm_lbl}) pay kar diya gaya. Remaining Payable: ₹{sp['after_balance']:,.0f}."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "expense",
                "title": f"Supplier Paid · {sup_name}",
                "subtitle": f"Via {pm_lbl}",
                "transactionDate": txn_date,
                "amountINR": amt,
                "lines": [
                    {"label": "Paid Amount", "value": f"₹{amt:,.0f} ({pm_lbl})", "tone": "sage"},
                    {"label": "Remaining Payable", "value": f"₹{sp['after_balance']:,.0f}", "tone": "ochre" if sp["after_balance"] > 0 else "sage"},
                ],
                "status": "saved",
                "reversible": True,
                "_supplier_op": {"type": "payment", "supplier_id": sup_id, "amount": amt},
            }
            return slip, reply

        if intent == "record_udhaar_credit":
            cust_id = str(draft["customer_id"])
            cust_name = str(draft["customer_name"])
            amt = float(draft["total_amount"])
            ud = self.tx.record_direct_udhaar(
                business_id=business_id,
                user_id=user_id,
                customer_id=cust_id,
                amount=amt,
                transaction_date=txn_date,
                operation_id=operation_id,
                notes=str(draft.get("notes") or "Voice Khata entry"),
            )
            context_state["last_operation_kind"] = "record_udhaar_credit"
            context_state["last_operation_id"] = operation_id
            context_state["last_customer_id"] = cust_id
            context_state["last_customer_name"] = cust_name
            reply = f"{cust_name} ke khate mein ₹{amt:,.0f} udhaar likh diya gaya (Balance ₹{ud['after_balance']:,.0f})."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "sale",
                "title": f"Khata Udhaar · {cust_name}",
                "subtitle": "Direct Credit Entry",
                "transactionDate": txn_date,
                "amountINR": amt,
                "lines": [{"label": "New Balance", "value": f"₹{ud['after_balance']:,.0f}", "tone": "ochre"}],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "record_customer_payment":
            cust_id = str(draft["customer_id"])
            cust_name = str(draft["customer_name"])
            amt = float(draft["total_amount"])
            pm = str(draft.get("payment_method") or "cash")
            pay = self.tx.record_customer_payment(
                business_id=business_id,
                user_id=user_id,
                customer_id=cust_id,
                amount=amt,
                payment_method=pm,
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_operation_kind"] = "record_customer_payment"
            context_state["last_operation_id"] = operation_id
            context_state["last_customer_id"] = cust_id
            context_state["last_customer_name"] = cust_name
            method_label = "Online" if pm == "upi" else ("Bank" if pm == "bank" else "Cash")
            reply = (
                f"{cust_name} se ₹{amt:,.0f} ({method_label}) receive ho gaya aur Sales ledger mein include ho gaya. "
                f"Remaining balance: ₹{pay['after_balance']:,.0f}."
            )
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "payment",
                "title": f"Payment Received · {cust_name}",
                "subtitle": f"Via {method_label} · Included in Sales & Revenue",
                "transactionDate": txn_date,
                "amountINR": amt,
                "lines": [
                    {"label": "Sales Ledger", "value": "Updated & Included", "tone": "sage"},
                    {"label": "Remaining Balance", "value": f"₹{pay['after_balance']:,.0f}", "tone": "ochre" if pay["after_balance"] > 0 else "sage"},
                ],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "record_split_customer_sale":
            cust_id = str(draft["customer_id"])
            cust_name = str(draft["customer_name"])
            pm = str(draft.get("payment_method") or "cash")
            sp_res = self.tx.record_split_customer_sale(
                business_id=business_id,
                user_id=user_id,
                customer_id=cust_id,
                total_amount=float(draft["total_amount"]),
                paid_amount=float(draft["paid_amount"]),
                payment_method=pm,
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_sale_id"] = str(sp_res["sale_id"])
            context_state["last_sale_total"] = float(sp_res["total_amount"])
            context_state["last_sale_qty"] = 1.0
            context_state["last_operation_kind"] = "record_sale"
            context_state["last_operation_id"] = operation_id
            pm_lbl = "Online" if pm == "upi" else ("Bank" if pm == "bank" else "Cash")
            reply = (
                f"{cust_name} ki ₹{sp_res['total_amount']:,.0f} sale save ho gayi: ₹{sp_res['paid_amount']:,.0f} {pm_lbl} aur ₹{sp_res['credit_amount']:,.0f} Udhaar (New Balance: ₹{sp_res['after_balance']:,.0f})."
            )
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "sale",
                "title": f"Split Sale · {cust_name}",
                "subtitle": f"{pm_lbl} + Khata Udhaar",
                "transactionDate": txn_date,
                "amountINR": sp_res["total_amount"],
                "lines": [
                    {"label": f"Paid ({pm_lbl})", "value": f"₹{sp_res['paid_amount']:,.0f}", "tone": "sage"},
                    {"label": "Khata Udhaar", "value": f"₹{sp_res['credit_amount']:,.0f}", "tone": "ochre"},
                    {"label": "Total Khata Balance", "value": f"₹{sp_res['after_balance']:,.0f}", "tone": "neutral"},
                ],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "record_combined_bill":
            bill_cust_name = draft.get("customer_name")
            pm = str(draft.get("payment_method") or "cash")
            cb = self.tx.record_combined_bill(
                business_id=business_id,
                user_id=user_id,
                items=list(draft["items"]),
                customer_id=draft.get("customer_id"),
                bill_total_amount=draft.get("bill_total_amount"),
                paid_amount=draft.get("paid_amount"),
                payment_status=str(draft.get("payment_status") or "paid"),
                payment_method=pm,
                transaction_date=txn_date,
                operation_id=operation_id,
                notes=str(draft.get("notes") or "Combined bill"),
            )
            context_state["last_sale_id"] = str(cb["sale_id"])
            context_state["last_sale_total"] = float(cb["total_amount"])
            context_state["last_sale_qty"] = sum(float(it["quantity"]) for it in cb["items"])
            context_state["last_operation_kind"] = "record_sale"
            context_state["last_operation_id"] = operation_id
            items_summary = ", ".join(f"{it['quantity']:g} {it['product_name']}" for it in cb["items"])
            disc_txt = f" (₹{cb['discount_amount']:,.0f} discount)" if cb["discount_amount"] > 0 else ""
            reply = f"Combined bill ({items_summary}) ₹{cb['total_amount']:,.0f}{disc_txt} save ho gaya."
            bill_lines = [
                {"label": it["product_name"], "value": f"-{it['quantity']:g} {it['unit']} @ ₹{it['unit_price']:g} = ₹{it['line_total']:,.0f}", "tone": "sage"}
                for it in cb["items"]
            ]
            if cb["discount_amount"] > 0:
                bill_lines.append({"label": "Discount", "value": f"-₹{cb['discount_amount']:,.0f}", "tone": "ochre"})
            if cb["payment_status"] == "partial":
                bill_lines.append({"label": "Paid / Udhaar", "value": f"₹{cb['paid_amount']:,.0f} / ₹{cb['credit_amount']:,.0f}", "tone": "ochre"})
            elif cb["payment_status"] == "credit":
                bill_lines.append({"label": "Khata Udhaar", "value": f"₹{cb['total_amount']:,.0f}", "tone": "ochre"})
            else:
                pm_lbl = "Online" if pm == "upi" else ("Bank" if pm == "bank" else "Cash")
                bill_lines.append({"label": "Payment", "value": pm_lbl, "tone": "sage"})
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "sale",
                "title": f"Combined Bill · {len(cb['items'])} Items",
                "subtitle": f"{bill_cust_name + ' · ' if bill_cust_name else ''}Single Invoice",
                "transactionDate": txn_date,
                "amountINR": cb["total_amount"],
                "lines": bill_lines,
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        if intent == "customer_return" and product:
            ret_qty = float(draft["quantity"])
            refund_m = str(draft.get("refund_method") or "cash")
            ret_cust_name = draft.get("customer_name")
            ret_res = self.tx.record_customer_return(
                business_id=business_id,
                user_id=user_id,
                product_id=str(product["id"]),
                product_name=product["name"],
                quantity=ret_qty,
                unit=product["base_unit"],
                refund_amount=float(draft["total_amount"]),
                refund_method=refund_m,
                customer_id=draft.get("customer_id"),
                transaction_date=txn_date,
                operation_id=operation_id,
            )
            context_state["last_product_id"] = str(product["id"])
            context_state["last_product_name"] = product["name"]
            context_state["last_operation_kind"] = "customer_return"
            context_state["last_operation_id"] = operation_id
            refund_lbl = "Khata Udhaar" if refund_m == "credit" else ("Online" if refund_m == "upi" else ("Bank" if refund_m == "bank" else "Cash"))
            reply = f"{ret_qty:g} {product['name']} wapas li gayi, ₹{ret_res['refund_amount']:,.0f} {refund_lbl} adjust hua. Updated stock: {ret_res['after_stock']:g}."
            slip = {
                "id": f"slip-{operation_id}",
                "operationId": operation_id,
                "kind": "receive",
                "title": f"Customer Return · {product['name']}",
                "subtitle": f"{ret_cust_name + ' · ' if ret_cust_name else ''}Wapsi & Refund",
                "transactionDate": txn_date,
                "amountINR": ret_res["refund_amount"],
                "lines": [
                    {"label": "Returned Stock", "value": f"+{ret_qty:g} {product['base_unit']}", "tone": "sage"},
                    {"label": f"Refund ({refund_lbl})", "value": f"₹{ret_res['refund_amount']:,.0f}", "tone": "ochre"},
                    {"label": "Stock Level", "value": f"{ret_res['before_stock']:g} → {ret_res['after_stock']:g}", "tone": "neutral"},
                ],
                "status": "saved",
                "reversible": True,
            }
            return slip, reply

        raise PolicyBlockedError("Unsupported draft payload")

    def _apply_damage_correction(
        self,
        *,
        business_id: str,
        user_id: str,
        new_qty: float,
        operation_id: str,
        txn_date: str,
        old_operation_id: str | None,
        product_id: str | None,
        movement_type: str | None,
        context_state: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        corr = self.tx.correct_damage_or_expiry(
            business_id=business_id,
            user_id=user_id,
            new_quantity=float(new_qty),
            operation_id=operation_id,
            transaction_date=txn_date,
            old_operation_id=old_operation_id,
            product_id=product_id,
            movement_type=movement_type,
        )
        mtype = corr["movement_type"]
        context_state["last_product_id"] = corr["product_id"]
        context_state["last_product_name"] = corr["product_name"]
        context_state["last_operation_kind"] = f"inventory_{mtype}"
        context_state["last_operation_id"] = corr["new_operation_id"]
        context_state["last_damage_product_id"] = corr["product_id"]
        context_state["last_damage_product_name"] = corr["product_name"]
        context_state["last_damage_qty"] = corr["new_quantity"]
        context_state["last_damage_type"] = mtype
        context_state["last_damage_operation_id"] = corr["new_operation_id"]
        reply = (
            f"{corr['product_name']} ka {mtype} update ho gaya: "
            f"{corr['old_quantity']:g} se {corr['new_quantity']:g}. Remaining stock: {corr['after_stock']:g}."
        )
        slip = {
            "id": f"slip-{corr['new_operation_id']}",
            "operationId": corr["new_operation_id"],
            "kind": "correction",
            "title": f"Corrected {mtype.title()} · {corr['product_name']}",
            "subtitle": "Previous entry reversed & updated (Audit Trail)",
            "transactionDate": txn_date,
            "lines": [
                {
                    "label": mtype.title(),
                    "value": f"{corr['old_quantity']:g} → {corr['new_quantity']:g} {corr['unit']}",
                    "tone": "crimson" if corr["new_quantity"] > corr["old_quantity"] else "sage",
                },
                {
                    "label": "Stock Level",
                    "value": f"{corr['before_stock']:g} → {corr['after_stock']:g}",
                    "tone": "neutral",
                },
            ],
            "status": "corrected",
            "reversible": True,
        }
        return slip, reply

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
        supplier_ops: list[dict[str, Any]] = []
        processed_indices: set[int] = set()
        non_supplier_customers, suppliers_list = self._split_customers_and_suppliers(customers)

        for idx, op in enumerate(operations):
            if idx in processed_indices:
                continue
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
                q_price_hint = op.price_hint if op.price_hint is not None else extract_clause_price_hint(op.product_query, raw_transcript)
                qres = self.queries.answer_query(
                    business_id=business_id,
                    topic=op.query_topic,
                    product_query=op.product_query,
                    customer_query=op.customer_query,
                    products=products,
                    aliases=aliases,
                    timezone_name=tz_name,
                    relative_date=op.relative_date,
                    date_range=op.date_range,
                    price_hint=q_price_hint,
                )
                replies.append(qres["reply"])
                topic_titles = {
                    "stock_check": "Stock Query Result",
                    "expenses_summary": "Expenses Summary",
                    "daily_summary": "Ledger Summary",
                    "pending_payments": "Pending Khata Dues",
                    "customer_balance": "Customer Khata Balance",
                    "supplier_balance": "Supplier Khata Payables",
                    "sales_summary": "Sales Summary",
                }
                period_sub = qres.get("period_label") or txn_date_str
                receipts.append(
                    {
                        "id": f"slip-{sub_op_id}",
                        "operationId": sub_op_id,
                        "kind": "query",
                        "title": topic_titles.get(op.query_topic or "general", "Ledger Query Result"),
                        "subtitle": f"{period_sub} · Read-Only",
                        "transactionDate": txn_date_str,
                        "amountINR": qres["amount_inr"],
                        "lines": qres["lines"],
                        "status": "saved",
                    }
                )
                continue

            if op.intent == "undo_last_operation":
                target_op = context_state.get("last_operation_id")
                if not target_op:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Abhi koi pichla transaction reverse karne ke liye active nahi hai.",
                        language=language,  # type: ignore[arg-type]
                    )
                rev = self.tx.reverse_operation(
                    business_id=business_id,
                    user_id=user_id,
                    operation_id=str(target_op),
                    reversal_operation_id=sub_op_id,
                    transaction_date=today_str,
                )
                context_state.pop("last_operation_id", None)
                context_state.pop("last_operation_kind", None)
                if str(context_state.get("last_damage_operation_id") or "") == str(target_op):
                    context_state.pop("last_damage_operation_id", None)
                    context_state.pop("last_damage_qty", None)
                replies.append(f"Pichla operation reverse ho gaya ({rev['summary']}).")
                receipts.append(
                    {
                        "id": f"slip-{sub_op_id}",
                        "operationId": sub_op_id,
                        "kind": "correction",
                        "title": "Operation Reversed",
                        "subtitle": "Compensating reversal committed",
                        "transactionDate": today_str,
                        "lines": [{"label": "Reversed", "value": rev["summary"], "tone": "ochre"}],
                        "status": "undone",
                    }
                )
                continue

            if op.intent in {"correct_last_sale", "correct_last_operation"}:
                last_kind = context_state.get("last_operation_kind")
                exp_id = context_state.get("last_expense_id")
                sale_id = context_state.get("last_sale_id")
                dmg_op_id = context_state.get("last_damage_operation_id")
                dmg_pid = context_state.get("last_damage_product_id")

                loss_cue = bool(
                    re.search(r"\b(damage|damaged|demis|kharab|toot|expire|expired)\b", raw_transcript, re.IGNORECASE)
                )
                receive_cue = bool(
                    re.search(r"\b(aayi|aaya|aaye|receive|received|stock\s+add)\b", raw_transcript, re.IGNORECASE)
                ) and not loss_cue
                expense_cue = bool(
                    re.search(r"\b(expense|kharcha|kharch|bill|bijli|electricity|rent|kiraya|tea|chai)\b", raw_transcript, re.IGNORECASE)
                )
                sale_cue = bool(
                    re.search(r"\b(sale|biki|bika|bike|sold|becha|bechi)\b", raw_transcript, re.IGNORECASE)
                )

                # Ignore size/weight numbers like "250 gram" / "70g" accidentally parsed as quantity
                raw_op_qty = op.quantity
                if raw_op_qty is not None and raw_op_qty == int(raw_op_qty):
                    if re.search(
                        rf"\b{int(raw_op_qty)}\s*(?:g|gm|gms|grams?|ml|mls|ltr|litres?|liters?)\b",
                        raw_transcript,
                        re.IGNORECASE,
                    ):
                        raw_op_qty = None
                new_qty = raw_op_qty if raw_op_qty is not None else extract_post_negation_quantity(raw_transcript)

                swap_supported_kinds = {"record_sale", "customer_return", "inventory_receive", "inventory_damage", "inventory_expiry"}
                resolved_corr_pid: str | None = None
                resolved_corr_prod: dict[str, Any] | None = None
                resolved_corr_status: str = "not_found"
                resolved_corr_candidates: list[dict[str, Any]] = []
                variant_cue = bool(
                    re.search(
                        r"\b\d+\s*(?:g|gm|gms|grams?|ml|mls|kg|kilo|ltr|litres?|liters?)\b|(?:wal[aei]|val[aei])\s+(?:thi|tha)\b|\b\d+(?:\.\d+)?\s*(?:rupaye|rupaiye|rupe|rs|₹)\s*(?:wal[aei]|val[aei])?",
                        raw_transcript,
                        re.IGNORECASE,
                    )
                )
                swap_query = op.product_query
                if not swap_query and (variant_cue or op.price_hint is not None) and last_kind in swap_supported_kinds:
                    neg_swap = re.search(
                        r"(?:nahi|nahin|not|ki\s+jagah|instead\s+of)\s+([a-z0-9\s]+?)(?:\s+wali|\s+vali|\s+wala|\s+thi|\s+tha|[.,]|$)",
                        raw_transcript,
                        re.IGNORECASE,
                    )
                    if neg_swap:
                        tail = neg_swap.group(1).strip()
                        last_pname = str(context_state.get("last_product_name") or "").strip()
                        brand_prefix = last_pname.split()[0] if last_pname else ""
                        swap_query = f"{brand_prefix} {tail}".strip() if (brand_prefix and brand_prefix.lower() not in tail.lower()) else tail
                    elif op.price_hint is not None:
                        last_pname = str(context_state.get("last_product_name") or "").strip()
                        swap_query = last_pname.split()[0] if last_pname else None

                if swap_query:
                    pres_corr = resolve_product_guarded(swap_query, raw_transcript, products, aliases, price_hint=op.price_hint)
                    resolved_corr_status = pres_corr.status
                    resolved_corr_candidates = pres_corr.candidates
                    if pres_corr.status in {"exact", "verify_alias"} and pres_corr.product:
                        resolved_corr_pid = str(pres_corr.product["id"])
                        resolved_corr_prod = pres_corr.product
                    elif pres_corr.status == "ambiguous" and pres_corr.candidates and last_kind in swap_supported_kinds:
                        names = " ya ".join(c["name"] for c in pres_corr.candidates)
                        msg = f"'{swap_query}' mein {len(pres_corr.candidates)} options mile ({names}). Kaunsa variant swap karna hai?"
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=msg,
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            clarification={
                                "kind": "disambiguate_product",
                                "prompt": msg,
                                "candidates": [
                                    {"id": str(c["id"]), "label": c["name"], "meta": f"Stock: {c['current_stock']:g} · ₹{float(c['default_selling_price']):g}", "value": c["name"]}
                                    for c in pres_corr.candidates
                                ],
                            },
                        )

                # 0. Single-Turn Variant Swap Correction across sale, customer_return, receive, damage & expiry
                old_swap_op_id = str(context_state.get("last_operation_id") or "")
                old_swap_pid = str(context_state.get("last_product_id") or "")
                if (
                    last_kind in swap_supported_kinds
                    and old_swap_op_id
                    and resolved_corr_prod is not None
                    and resolved_corr_pid
                    and resolved_corr_pid != old_swap_pid
                    and not expense_cue
                ):
                    try:
                        if last_kind == "record_sale":
                            sw = self.tx.swap_last_sale_variant(
                                business_id=business_id,
                                user_id=user_id,
                                old_operation_id=old_swap_op_id,
                                new_product_id=resolved_corr_pid,
                                new_product_name=str(resolved_corr_prod["name"]),
                                new_unit=str(resolved_corr_prod["base_unit"]),
                                new_unit_price=float(op.unit_price or resolved_corr_prod.get("default_selling_price") or 0),
                                new_quantity=float(new_qty) if new_qty is not None else None,
                                transaction_date=today_str,
                                operation_id=sub_op_id,
                            )
                            for pr in products:
                                if str(pr["id"]) == old_swap_pid:
                                    pr["current_stock"] = float(pr["current_stock"]) + float(sw["old_quantity"])
                                elif str(pr["id"]) == resolved_corr_pid and sw.get("after_stock") is not None:
                                    pr["current_stock"] = float(sw["after_stock"])
                            context_state["last_product_id"] = resolved_corr_pid
                            context_state["last_product_name"] = sw["new_product_name"]
                            context_state["last_sale_id"] = str(sw["sale_id"])
                            context_state["last_operation_kind"] = "record_sale"
                            context_state["last_operation_id"] = sub_op_id
                            replies.append(
                                f"Variant swap ho gaya: {sw['old_product_name']} → {sw['new_product_name']} ({sw['quantity']:g} {sw['unit']}, ₹{sw['new_total']:,.0f})."
                            )
                            receipts.append(
                                {
                                    "id": f"slip-{sub_op_id}",
                                    "operationId": sub_op_id,
                                    "kind": "correction",
                                    "title": f"Variant Swapped · {sw['new_product_name']}",
                                    "subtitle": f"Replaced {sw['old_product_name']} (Old bill voided)",
                                    "transactionDate": today_str,
                                    "amountINR": sw["new_total"],
                                    "lines": [
                                        {"label": "Old SKU Restored", "value": f"+{sw['old_quantity']:g} {sw['old_product_name']}", "tone": "sage"},
                                        {"label": "New SKU Billed", "value": f"-{sw['quantity']:g} {sw['new_product_name']} @ ₹{sw['unit_price']:g}", "tone": "ochre"},
                                        {"label": "New Total", "value": f"₹{sw['new_total']:,.0f}", "tone": "neutral"},
                                    ],
                                    "status": "corrected",
                                    "reversible": True,
                                }
                            )
                        elif last_kind == "customer_return":
                            sw = self.tx.swap_last_return_variant(
                                business_id=business_id,
                                user_id=user_id,
                                old_operation_id=old_swap_op_id,
                                new_product_id=resolved_corr_pid,
                                new_product_name=str(resolved_corr_prod["name"]),
                                new_unit=str(resolved_corr_prod["base_unit"]),
                                new_unit_price=float(op.unit_price or resolved_corr_prod.get("default_selling_price") or 0),
                                new_quantity=float(new_qty) if new_qty is not None else None,
                                transaction_date=today_str,
                                operation_id=sub_op_id,
                            )
                            for pr in products:
                                if str(pr["id"]) == old_swap_pid:
                                    pr["current_stock"] = max(0.0, float(pr["current_stock"]) - float(sw["old_quantity"]))
                                elif str(pr["id"]) == resolved_corr_pid and sw.get("after_stock") is not None:
                                    pr["current_stock"] = float(sw["after_stock"])
                            context_state["last_product_id"] = resolved_corr_pid
                            context_state["last_product_name"] = sw["new_product_name"]
                            context_state["last_operation_kind"] = "customer_return"
                            context_state["last_operation_id"] = sub_op_id
                            replies.append(
                                f"Return variant swap ho gaya: {sw['old_product_name']} → {sw['new_product_name']} ({sw['quantity']:g} {sw['unit']}, ₹{sw['refund_amount']:,.0f})."
                            )
                            receipts.append(
                                {
                                    "id": f"slip-{sub_op_id}",
                                    "operationId": sub_op_id,
                                    "kind": "correction",
                                    "title": f"Return Swapped · {sw['new_product_name']}",
                                    "subtitle": f"Replaced {sw['old_product_name']} return",
                                    "transactionDate": today_str,
                                    "amountINR": sw["refund_amount"],
                                    "lines": [
                                        {"label": "Old Return Reversed", "value": f"-{sw['old_quantity']:g} {sw['old_product_name']}", "tone": "ochre"},
                                        {"label": "New Return Logged", "value": f"+{sw['quantity']:g} {sw['new_product_name']}", "tone": "sage"},
                                        {"label": "Updated Refund", "value": f"₹{sw['refund_amount']:,.0f}", "tone": "neutral"},
                                    ],
                                    "status": "corrected",
                                    "reversible": True,
                                }
                            )
                        else:
                            mv_t = (
                                "receive"
                                if last_kind == "inventory_receive"
                                else ("expiry" if last_kind == "inventory_expiry" else "damage")
                            )
                            sw = self.tx.swap_last_movement_variant(
                                business_id=business_id,
                                user_id=user_id,
                                old_operation_id=old_swap_op_id,
                                movement_type=mv_t,
                                new_product_id=resolved_corr_pid,
                                new_product_name=str(resolved_corr_prod["name"]),
                                new_unit=str(resolved_corr_prod["base_unit"]),
                                new_unit_cost=float(op.cost_price or op.unit_price or resolved_corr_prod.get("default_cost_price") or 0),
                                new_quantity=float(new_qty) if new_qty is not None else None,
                                transaction_date=today_str,
                                operation_id=sub_op_id,
                            )
                            context_state["last_product_id"] = resolved_corr_pid
                            context_state["last_product_name"] = sw["new_product_name"]
                            context_state["last_operation_kind"] = last_kind
                            context_state["last_operation_id"] = sub_op_id
                            if mv_t in ("damage", "expiry"):
                                context_state["last_damage_operation_id"] = sub_op_id
                                context_state["last_damage_product_id"] = resolved_corr_pid
                            replies.append(
                                f"Variant swap ho gaya: {sw['old_product_name']} → {sw['new_product_name']} ({sw['quantity']:g} {sw['unit']})."
                            )
                            receipts.append(
                                {
                                    "id": f"slip-{sub_op_id}",
                                    "operationId": sub_op_id,
                                    "kind": "correction",
                                    "title": f"Variant Swapped · {sw['new_product_name']}",
                                    "subtitle": f"Replaced {sw['old_product_name']} ({mv_t})",
                                    "transactionDate": today_str,
                                    "amountINR": sw["total_amount"],
                                    "lines": [
                                        {"label": "New Item Stock", "value": f"{sw['before_stock']:g} → {sw['after_stock']:g}", "tone": "sage"},
                                    ],
                                    "status": "corrected",
                                    "reversible": True,
                                }
                            )
                    except (InsufficientStockError, PolicyBlockedError) as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=exc.message,
                            language=language,  # type: ignore[arg-type]
                        )
                    continue

                if variant_cue and swap_query and resolved_corr_status == "not_found":
                    hint = (
                        f"Available variants: {', '.join(c['name'] for c in resolved_corr_candidates)}."
                        if resolved_corr_candidates
                        else "Kripya catalog mein maujood sahi variant naam bolein."
                    )
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{swap_query}' inventory mein nahi mila. {hint}",
                        language=language,  # type: ignore[arg-type]
                    )

                # 1. Damage / Expiry Correction
                if not expense_cue and not sale_cue and (
                    last_kind in {"inventory_damage", "inventory_expiry"}
                    or (loss_cue and (dmg_op_id or dmg_pid or resolved_corr_pid))
                ):
                    if new_qty is None:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply="Kitne items damaged ya expired mark karne hain?",
                            language=language,  # type: ignore[arg-type]
                        )
                    target_pid = resolved_corr_pid or (str(dmg_pid) if dmg_pid else None)
                    target_prod_row = next((p for p in products if str(p["id"]) == str(target_pid)), None) if target_pid else None
                    final_loss_qty = float(new_qty)
                    if target_prod_row and final_loss_qty > 0:
                        conv_q, u_err = convert_to_base_quantity(
                            quantity=final_loss_qty,
                            spoken_unit=op.unit,
                            base_unit=target_prod_row["base_unit"],
                        )
                        if u_err or conv_q is None:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=u_err or "Unit clear nahi hai.",
                                language=language,  # type: ignore[arg-type]
                            )
                        final_loss_qty = conv_q
                    target_mtype = (
                        "expiry"
                        if ("expire" in raw_transcript.lower() or last_kind == "inventory_expiry")
                        else ("damage" if (loss_cue or last_kind == "inventory_damage") else None)
                    )
                    try:
                        slip, rep = self._apply_damage_correction(
                            business_id=business_id,
                            user_id=user_id,
                            new_qty=final_loss_qty,
                            operation_id=sub_op_id,
                            txn_date=today_str,
                            old_operation_id=str(dmg_op_id) if (dmg_op_id and (not target_pid or str(target_pid) == str(dmg_pid))) else None,
                            product_id=target_pid,
                            movement_type=target_mtype,
                            context_state=context_state,
                        )
                    except (InsufficientStockError, PolicyBlockedError) as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=exc.message,
                            language=language,  # type: ignore[arg-type]
                        )
                    for p_row in products:
                        if str(p_row["id"]) == str(context_state.get("last_damage_product_id")):
                            # Keep in-memory stock synced for subsequent batch items
                            after_val = next(
                                (ln["value"].split("→")[-1].strip() for ln in slip["lines"] if ln["label"] == "Stock Level"),
                                None,
                            )
                            if after_val is not None:
                                try:
                                    p_row["current_stock"] = float(after_val)
                                except ValueError:
                                    pass
                            break
                    replies.append(rep)
                    receipts.append(slip)
                    continue

                # 2. Stock Receive Correction
                if not expense_cue and not sale_cue and not loss_cue and (
                    last_kind == "inventory_receive" or receive_cue
                ):
                    target_pid = resolved_corr_pid or (
                        str(context_state.get("last_product_id")) if context_state.get("last_product_id") else None
                    )
                    new_cost = op.cost_price if op.cost_price is not None else op.unit_price
                    if new_qty is None and new_cost is None:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply="Stock receive mein sahi quantity ya rate batayein.",
                            language=language,  # type: ignore[arg-type]
                        )
                    try:
                        corr_rec = self.tx.correct_stock_receive(
                            business_id=business_id,
                            user_id=user_id,
                            operation_id=sub_op_id,
                            transaction_date=today_str,
                            old_operation_id=str(context_state.get("last_operation_id")) if last_kind == "inventory_receive" else None,
                            product_id=target_pid,
                            new_quantity=float(new_qty) if new_qty is not None else None,
                            new_unit_cost=float(new_cost) if new_cost is not None else None,
                        )
                    except (InsufficientStockError, PolicyBlockedError) as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=exc.message,
                            language=language,  # type: ignore[arg-type]
                        )
                    context_state["last_product_id"] = corr_rec["product_id"]
                    context_state["last_product_name"] = corr_rec["product_name"]
                    context_state["last_receive_qty"] = corr_rec["new_quantity"]
                    context_state["last_receive_cost"] = corr_rec["new_cost"]
                    context_state["last_operation_kind"] = "inventory_receive"
                    context_state["last_operation_id"] = corr_rec["new_operation_id"]
                    replies.append(
                        f"{corr_rec['product_name']} ka stock receive update ho gaya: "
                        f"{corr_rec['old_quantity']:g} se {corr_rec['new_quantity']:g} (Rate ₹{corr_rec['new_cost']:,.0f}). "
                        f"Remaining stock: {corr_rec['after_stock']:g}."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": f"Corrected Stock Receive · {corr_rec['product_name']}",
                            "subtitle": "Previous receipt reversed & updated (Audit Trail)",
                            "transactionDate": today_str,
                            "amountINR": corr_rec["new_quantity"] * corr_rec["new_cost"],
                            "lines": [
                                {"label": "Received", "value": f"{corr_rec['old_quantity']:g} → {corr_rec['new_quantity']:g} {corr_rec['unit']}", "tone": "sage"},
                                {"label": "Stock Level", "value": f"{corr_rec['before_stock']:g} → {corr_rec['after_stock']:g}", "tone": "neutral"},
                            ],
                            "status": "corrected",
                            "reversible": True,
                        }
                    )
                    continue

                # 3. Expense correction (e.g., "cash nahi, UPI se kiya tha" or "1000 nahi 500 tha")
                if exp_id and not loss_cue and not sale_cue and (last_kind == "record_expense" or expense_cue) and (
                    op.payment_method is not None
                    or op.total_amount is not None
                    or (op.description is not None and expense_cue)
                ):
                    corr_exp = self.tx.correct_last_expense(
                        business_id=business_id,
                        user_id=user_id,
                        expense_id=str(exp_id),
                        operation_id=sub_op_id,
                        transaction_date=today_str,
                        new_amount=op.total_amount,
                        new_payment_method=op.payment_method,
                        new_description=op.description if expense_cue else None,
                    )
                    context_state["last_expense_id"] = str(corr_exp["new_expense_id"])
                    context_state["last_operation_kind"] = "record_expense"
                    context_state["last_operation_id"] = sub_op_id
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

                # 3b. Sale total rupee / bill amount correction (ONLY when not changing qty or cash+udhaar split)
                tlow = raw_transcript.lower()
                is_split_corr_cue = bool(
                    op.payment_status == "partial"
                    or (
                        re.search(r"\b(udhaar|credit)\b", tlow)
                        and re.search(r"\b(cash|online|upi|bank|rupay|rupaye|rupaiye|rupee|rupi|paise|dee?\s*diyae?|diye|diya|paid|aadha|half)\b", tlow)
                    )
                )
                has_qty_corr_cue = bool(
                    op.quantity is not None
                    or re.search(r"\b\d+(?:\.\d+)?\s*(?:kg|kilo|geni|gram|g|packet|packets|piece|pieces|litre|ltr|box)\b", tlow)
                )
                rupee_cue = bool(
                    re.search(
                        r"\b(rupees?|rupaye|rupaiye|rupai|rupi|rs|inr|bill|total|amount|rate|price|quantity\s+nahi|qty\s+nahi)\b",
                        tlow,
                    )
                )
                last_sale_tot = float(context_state.get("last_sale_total") or 0)
                pre_neg_m = re.search(
                    r"\b(\d+(?:\.\d+)?)\s*(?:rupees?|rupaye|rupi)?\s*(?:na\s+hii?|nahi|nahin|not|ki\s+jagah|instead\s+of)\b",
                    tlow,
                )
                matches_prev_total = bool(
                    pre_neg_m and last_sale_tot > 0 and abs(float(pre_neg_m.group(1)) - last_sale_tot) < 0.01
                )
                explicit_amt_target = op.bill_total_amount if op.bill_total_amount is not None else op.total_amount
                post_neg_amt = extract_post_negation_number(raw_transcript)
                is_amount_corr = bool(
                    sale_id
                    and not loss_cue
                    and not expense_cue
                    and not is_split_corr_cue
                    and not has_qty_corr_cue
                    and (last_kind == "record_sale" or sale_cue or last_kind is None)
                    and (rupee_cue or matches_prev_total or explicit_amt_target is not None)
                )
                corr_amt_val = explicit_amt_target if explicit_amt_target is not None else post_neg_amt
                if is_amount_corr and corr_amt_val is not None and float(corr_amt_val) >= 0:
                    try:
                        ca = self.tx.correct_sale_amount(
                            business_id=business_id,
                            user_id=user_id,
                            sale_id=str(sale_id),
                            new_total_amount=float(corr_amt_val),
                            operation_id=sub_op_id,
                            transaction_date=today_str,
                        )
                    except PolicyBlockedError as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=exc.message,
                            language=language,  # type: ignore[arg-type]
                        )
                    context_state["last_sale_id"] = str(ca["new_sale_id"])
                    context_state["last_sale_total"] = float(ca["new_total"])
                    context_state["last_operation_kind"] = "record_sale"
                    context_state["last_operation_id"] = sub_op_id
                    replies.append(
                        f"Sale bill update ho gaya: ₹{ca['old_total']:,.0f} se ₹{ca['new_total']:,.0f}."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": "Corrected Bill Amount",
                            "subtitle": "Previous bill marked corrected (Stock unchanged)",
                            "transactionDate": today_str,
                            "amountINR": ca["new_total"],
                            "lines": [
                                {"label": "Old Amount", "value": f"₹{ca['old_total']:,.0f}", "tone": "ochre"},
                                {"label": "New Amount", "value": f"₹{ca['new_total']:,.0f}", "tone": "sage"},
                            ],
                            "status": "corrected",
                            "reversible": True,
                        }
                    )
                    continue

                # 4. Sale payment method/status correction (require spoken payment/udhaar cue and NOT qty/split edits)
                has_spoken_pm_cue = bool(re.search(r"\b(online|upi|ubi|gpay|phonepe|paytm|cash|bank|udhaar|credit)\b", tlow))
                if sale_id and not loss_cue and not expense_cue and not is_split_corr_cue and new_qty is None and (
                    last_kind == "record_sale" or sale_cue or last_kind is None
                ) and (
                    has_spoken_pm_cue
                    or op.payment_status is not None
                ) and (
                    op.payment_method is not None
                    or op.payment_status is not None
                    or has_spoken_pm_cue
                ):
                    target_pm = op.payment_method
                    target_ps = op.payment_status
                    tlow = raw_transcript.lower()
                    if target_pm is None and target_ps is None:
                        if re.search(r"\b(online|upi)\b", tlow) and not re.search(r"\b(?:online|upi)\s+(?:se\s+)?nahi\b", tlow):
                            target_pm = "upi"
                        elif re.search(r"\bcash\b", tlow) and not re.search(r"\bcash\s+(?:se\s+)?nahi\b", tlow):
                            target_pm = "cash"
                        elif re.search(r"\budhaar\b", tlow):
                            target_ps = "credit"
                    try:
                        corr_pay = self.tx.correct_sale_payment(
                            business_id=business_id,
                            user_id=user_id,
                            sale_id=str(sale_id),
                            operation_id=sub_op_id,
                            transaction_date=today_str,
                            new_payment_method=target_pm,
                            new_payment_status=target_ps,
                        )
                    except RuntimeError as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=f"Payment method update nahi ho paya ({exc}). Kripya receipt par Reverse karke nayi entry bolein.",
                            language=language,  # type: ignore[arg-type]
                        )
                    context_state["last_sale_id"] = str(corr_pay["new_sale_id"])
                    context_state["last_operation_kind"] = "record_sale"
                    context_state["last_operation_id"] = sub_op_id
                    replies.append(
                        f"Sale payment update ho gaya: ₹{corr_pay['total_amount']:,.0f} ({corr_pay['old_method']} → {corr_pay['new_method']})."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": "Corrected Sale Payment",
                            "subtitle": "Previous entry marked corrected (Audit Trail)",
                            "transactionDate": today_str,
                            "amountINR": corr_pay["total_amount"],
                            "lines": [
                                {"label": "Method", "value": f"{corr_pay['old_method']} → {corr_pay['new_method']}", "tone": "sage"},
                                {"label": "Amount", "value": f"₹{corr_pay['total_amount']:,.0f}", "tone": "neutral"},
                            ],
                            "status": "corrected",
                        }
                    )
                    continue

                # 5. Sale quantity & optional split-payment correction
                effective_corr_qty = new_qty
                if effective_corr_qty is None and is_split_corr_cue and context_state.get("last_sale_qty"):
                    effective_corr_qty = float(context_state["last_sale_qty"])
                if sale_id and effective_corr_qty is not None and not loss_cue and not expense_cue and (
                    last_kind == "record_sale" or sale_cue or last_kind is None
                ):
                    corr_target_paid: float | None = None
                    corr_target_status: str | None = None
                    if is_split_corr_cue:
                        corr_target_status = "partial"
                        if op.paid_amount is not None and float(op.paid_amount) > 0:
                            corr_target_paid = float(op.paid_amount)
                        else:
                            paid_qty_c: float | None = None
                            if op.notes and "paid_qty:" in str(op.notes):
                                mq = re.search(r"paid_qty:(\d+(?:\.\d+)?)", str(op.notes))
                                if mq:
                                    paid_qty_c = float(mq.group(1))
                            if paid_qty_c is None:
                                m_fc = re.search(
                                    r"(?:isme\s+se|usne|aur|,)?\s*(\d+(?:\.\d+)?|\bek\b|\bdo\b|\bteen\b|\baadha\b|\bhalf\b)\s*(?:kg|kilo|geni|gram|g|packet|packets|piece|pieces|litre|ltr|box)?\s*(?:chini|sugar)?\s*(?:ke|ki)?\s*(?:rupay|rupaye|rupaiye|rupee|rupi|paise|cash|online|upi|rs)?\s*(?:dee?\s*diyae?|de\s+diye|diye|diya|doei|paid)",
                                    raw_transcript,
                                    re.IGNORECASE,
                                )
                                if m_fc:
                                    paid_qty_c = parse_indian_number(m_fc.group(1))
                            unit_p_est = (
                                float(op.unit_price)
                                if op.unit_price
                                else (
                                    round(float(context_state["last_sale_total"]) / float(context_state["last_sale_qty"]), 2)
                                    if float(context_state.get("last_sale_qty") or 0) > 0 and float(context_state.get("last_sale_total") or 0) > 0
                                    else 0.0
                                )
                            )
                            if paid_qty_c is not None and 0 < paid_qty_c <= float(effective_corr_qty) and unit_p_est > 0:
                                corr_target_paid = round(paid_qty_c * unit_p_est, 2)
                            elif paid_qty_c is not None and 0 < paid_qty_c < float(effective_corr_qty) and op.total_amount:
                                corr_target_paid = round((paid_qty_c / float(effective_corr_qty)) * float(op.total_amount), 2)

                    try:
                        corr = self.tx.correct_sale_quantity(
                            business_id=business_id,
                            user_id=user_id,
                            sale_id=sale_id,
                            new_quantity=float(effective_corr_qty),
                            operation_id=sub_op_id,
                            transaction_date=today_str,
                            new_paid_amount=corr_target_paid,
                            new_payment_status=corr_target_status,
                        )
                    except RuntimeError as exc:
                        err_s = str(exc)
                        if "INSUFFICIENT_STOCK:" in err_s:
                            avail = err_s.split("INSUFFICIENT_STOCK:", 1)[1].split('"', 1)[0].strip()
                            msg = (
                                f"Stock sirf {avail} bacha hai, isliye quantity {float(effective_corr_qty):g} update nahi ho sakti. "
                                "Agar galat variant record hua ho toh receipt par 'Reverse' dabayein aur sahi product bolein."
                            )
                        else:
                            msg = "Last sale quantity update nahi ho payi. Agar product galat tha toh receipt par 'Reverse' dabayein."
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=msg,
                            language=language,  # type: ignore[arg-type]
                        )
                    context_state["last_operation_kind"] = "record_sale"
                    context_state["last_operation_id"] = sub_op_id
                    context_state["last_sale_total"] = float(corr.get("new_total") or 0)
                    context_state["last_sale_qty"] = float(corr.get("new_quantity") or effective_corr_qty)
                    split_note = (
                        f" · Paid ₹{corr['paid_amount']:,.0f}, Udhaar ₹{corr['credit_amount']:,.0f}"
                        if corr.get("payment_status") == "partial" and corr.get("paid_amount") is not None
                        else ""
                    )
                    replies.append(
                        f"Sale correct ho gayi: {corr['old_quantity']:g} se {corr['new_quantity']:g} (₹{corr['new_total']:,.0f}{split_note}). Audit trail updated."
                    )
                    corr_lines = [
                        {"label": "Quantity", "value": f"{corr['old_quantity']:g} → {corr['new_quantity']:g}", "tone": "ochre"},
                        {"label": "Stock Adjusted", "value": f"{corr['stock_delta']:+g}", "tone": "sage"},
                    ]
                    if corr.get("payment_status") == "partial" and corr.get("paid_amount") is not None:
                        corr_lines.append({"label": "Paid / Udhaar", "value": f"₹{corr['paid_amount']:,.0f} / ₹{corr['credit_amount']:,.0f}", "tone": "ochre"})
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "correction",
                            "title": "Audited Sale Correction",
                            "subtitle": "Compensating stock reversal logged",
                            "transactionDate": today_str,
                            "amountINR": corr["new_total"],
                            "lines": corr_lines,
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
                    "sellingPrice": str(op.selling_price or op.unit_price or 0),
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

            # Combined Multi-Item Single Bill ("ek saath", "100 mein bechi", grouped invoice)
            combined_cue = bool(
                op.is_combined_bill
                or op.bill_total_amount is not None
                or re.search(r"\b(ek\s+saath|combined\s+bill|total\s+\d+\s+mein|saare\s+ek)\b", raw_transcript, re.IGNORECASE)
            )
            if op.intent == "record_sale" and combined_cue:
                sale_group_indices = [
                    j for j in range(idx, len(operations))
                    if j not in processed_indices and operations[j].intent == "record_sale" and operations[j].product_query
                ]
                if len(sale_group_indices) >= 2:
                    bill_items: list[dict[str, Any]] = []
                    shared_cust_q = next((operations[j].customer_query for j in sale_group_indices if operations[j].customer_query), None)
                    shared_bill_tot = next((operations[j].bill_total_amount for j in sale_group_indices if operations[j].bill_total_amount is not None), None)
                    shared_pm = next((operations[j].payment_method for j in sale_group_indices if operations[j].payment_method), "cash")
                    shared_ps = next((operations[j].payment_status for j in sale_group_indices if operations[j].payment_status), "paid")
                    shared_paid = next((operations[j].paid_amount for j in sale_group_indices if operations[j].paid_amount is not None), None)

                    for j in sale_group_indices:
                        g_op = operations[j]
                        pres_g = resolve_product_guarded(
                            g_op.product_query,
                            raw_transcript,
                            products,
                            aliases,
                            price_hint=g_op.price_hint,
                        )
                        if pres_g.status == "ambiguous" and pres_g.candidates:
                            names = " ya ".join(c["name"] for c in pres_g.candidates)
                            msg = f"'{g_op.product_query}' ke {len(pres_g.candidates)} options mile: {names}. Combined bill ke liye exact item select karein."
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=msg,
                                language=language,  # type: ignore[arg-type]
                                receipts=receipts,
                                clarification={
                                    "kind": "disambiguate_product",
                                    "prompt": msg,
                                    "candidates": [
                                        {"id": str(c["id"]), "label": c["name"], "meta": f"Stock: {c['current_stock']:g} · ₹{float(c['default_selling_price']):g}", "value": c["name"]}
                                        for c in pres_g.candidates
                                    ],
                                },
                            )
                        if pres_g.status not in {"exact", "verify_alias"} or not pres_g.product:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=f"'{g_op.product_query}' inventory mein nahi mila. Kripya sahi naam bolein.",
                                language=language,  # type: ignore[arg-type]
                                receipts=receipts,
                            )
                        tp = pres_g.product
                        q_conv, u_err = convert_to_base_quantity(
                            quantity=float(g_op.quantity or 1),
                            spoken_unit=g_op.unit,
                            base_unit=tp["base_unit"],
                        )
                        if u_err or q_conv is None:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=u_err or "Unit clear nahi hai.",
                                language=language,  # type: ignore[arg-type]
                            )
                        up = float(g_op.unit_price or tp.get("default_selling_price") or 0)
                        bill_items.append(
                            {
                                "product_id": str(tp["id"]),
                                "product_name": tp["name"],
                                "quantity": q_conv,
                                "unit": tp["base_unit"],
                                "unit_price": up,
                            }
                        )

                    bill_cust_id: str | None = None
                    bill_cust_name: str | None = None
                    if shared_cust_q:
                        cres_b = resolve_customer(shared_cust_q, non_supplier_customers)
                        if cres_b.status == "exact" and cres_b.customer:
                            bill_cust_id = str(cres_b.customer["id"])
                            bill_cust_name = cres_b.customer["name"]
                        elif shared_ps in {"credit", "partial"}:
                            new_bc = self.tx.create_customer(business_id=business_id, name=shared_cust_q.title())
                            customers.append(new_bc)
                            non_supplier_customers.append(new_bc)
                            bill_cust_id = str(new_bc["id"])
                            bill_cust_name = new_bc["name"]

                    est_cb_total = float(
                        shared_bill_tot
                        if shared_bill_tot is not None and shared_bill_tot >= 0
                        else sum(float(it["quantity"]) * float(it["unit_price"]) for it in bill_items)
                    )
                    if SecurityPolicyEngine.classify_risk_tier(intent="record_sale", amount_inr=est_cb_total) == "tier3":
                        cb_draft = {
                            "intent": "record_combined_bill",
                            "items": bill_items,
                            "customer_id": bill_cust_id,
                            "customer_name": bill_cust_name,
                            "bill_total_amount": shared_bill_tot,
                            "paid_amount": shared_paid,
                            "payment_status": shared_ps,
                            "payment_method": shared_pm,
                            "transaction_date": txn_date_str,
                            "notes": f"{bill_cust_name + ' · ' if bill_cust_name else ''}Combined bill",
                        }
                        return self._issue_tier3_response(
                            draft=cb_draft,
                            title=f"High-Value Combined Bill ({len(bill_items)} Items)",
                            description=", ".join(f"{it['quantity']:g} {it['product_name']}" for it in bill_items),
                            total_val=est_cb_total,
                            business_id=business_id,
                            user_id=user_id,
                            conv_id=conv_id,
                            today_str=today_str,
                            operation_id=sub_op_id,
                            payload_hash=payload_hash,
                            raw_transcript=raw_transcript,
                            language=language,
                            stt_provider=stt_provider,
                            stt_confidence=stt_confidence,
                            context_state=context_state,
                            prefix_receipts=receipts,
                        )

                    try:
                        cb = self.tx.record_combined_bill(
                            business_id=business_id,
                            user_id=user_id,
                            items=bill_items,
                            customer_id=bill_cust_id,
                            bill_total_amount=shared_bill_tot,
                            paid_amount=shared_paid,
                            payment_status=shared_ps,
                            payment_method=shared_pm,
                            transaction_date=txn_date_str,
                            operation_id=sub_op_id,
                            notes=f"{bill_cust_name + ' · ' if bill_cust_name else ''}Combined bill",
                        )
                    except InsufficientStockError as exc:
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=exc.message,
                            language=language,  # type: ignore[arg-type]
                        )

                    for res_it in cb["items"]:
                        for pr in products:
                            if str(pr["id"]) == str(res_it["product_id"]):
                                pr["current_stock"] = float(res_it["after_stock"])
                    for j in sale_group_indices:
                        processed_indices.add(j)

                    context_state["last_sale_id"] = str(cb["sale_id"])
                    context_state["last_sale_total"] = float(cb["total_amount"])
                    context_state["last_sale_qty"] = sum(float(it["quantity"]) for it in cb["items"])
                    context_state["last_operation_kind"] = "record_sale"
                    context_state["last_operation_id"] = sub_op_id
                    items_summary = ", ".join(f"{it['quantity']:g} {it['product_name']}" for it in cb["items"])
                    disc_txt = f" (₹{cb['discount_amount']:,.0f} discount)" if cb["discount_amount"] > 0 else ""
                    replies.append(
                        f"Combined bill ({items_summary}) ₹{cb['total_amount']:,.0f}{disc_txt} save ho gaya."
                    )
                    bill_lines = [
                        {
                            "label": it["product_name"],
                            "value": f"-{it['quantity']:g} {it['unit']} @ ₹{it['unit_price']:g} = ₹{it['line_total']:,.0f}",
                            "tone": "sage",
                        }
                        for it in cb["items"]
                    ]
                    if cb["discount_amount"] > 0:
                        bill_lines.append({"label": "Discount", "value": f"-₹{cb['discount_amount']:,.0f}", "tone": "ochre"})
                    if cb["payment_status"] == "partial":
                        bill_lines.append({"label": "Paid / Udhaar", "value": f"₹{cb['paid_amount']:,.0f} / ₹{cb['credit_amount']:,.0f}", "tone": "ochre"})
                    elif cb["payment_status"] == "credit":
                        bill_lines.append({"label": "Khata Udhaar", "value": f"₹{cb['total_amount']:,.0f}", "tone": "ochre"})
                    else:
                        pm_lbl = "Online" if shared_pm == "upi" else ("Bank" if shared_pm == "bank" else "Cash")
                        bill_lines.append({"label": "Payment", "value": pm_lbl, "tone": "sage"})

                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "sale",
                            "title": f"Combined Bill · {len(cb['items'])} Items",
                            "subtitle": f"{bill_cust_name + ' · ' if bill_cust_name else ''}Single Invoice",
                            "transactionDate": txn_date_str,
                            "amountINR": cb["total_amount"],
                            "lines": bill_lines,
                            "status": "saved",
                            "reversible": True,
                        }
                    )
                    continue

            # Un-itemized Split / Partial Customer Sale ("Nitin ne 500 ka saaman liya, 200 cash diye aur 300 udhaar")
            if (
                op.intent == "record_sale"
                and not op.product_query
                and op.customer_query
                and (op.total_amount or op.paid_amount)
            ):
                cres_sp = resolve_customer(op.customer_query, non_supplier_customers)
                if cres_sp.status == "exact" and cres_sp.customer:
                    cust_sp = cres_sp.customer
                elif cres_sp.status == "ambiguous" and cres_sp.candidates:
                    names = " ya ".join(c["name"] for c in cres_sp.candidates)
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"Khata mein {len(cres_sp.candidates)} {op.customer_query} hain ({names}). Kaunse customer?",
                        language=language,  # type: ignore[arg-type]
                        clarification={
                            "kind": "disambiguate_customer",
                            "prompt": f"Select customer for '{op.customer_query}'",
                            "candidates": [
                                {"id": str(c["id"]), "label": c["name"], "meta": f"Due ₹{float(c['outstanding_balance']):,.0f}", "value": c["name"]}
                                for c in cres_sp.candidates
                            ],
                        },
                    )
                else:
                    cust_sp = self.tx.create_customer(business_id=business_id, name=op.customer_query.title())
                    customers.append(cust_sp)
                    non_supplier_customers.append(cust_sp)

                tot_sp = float(op.total_amount or op.paid_amount or 0)
                paid_sp = float(op.paid_amount or 0) if op.payment_status == "partial" else (tot_sp if op.payment_status != "credit" else 0.0)
                pm_sp = op.payment_method or "cash"
                if SecurityPolicyEngine.classify_risk_tier(intent="record_sale", amount_inr=tot_sp) == "tier3":
                    sp_draft = {
                        "intent": "record_split_customer_sale",
                        "customer_id": str(cust_sp["id"]),
                        "customer_name": cust_sp["name"],
                        "total_amount": tot_sp,
                        "paid_amount": paid_sp,
                        "payment_method": pm_sp,
                        "transaction_date": txn_date_str,
                    }
                    return self._issue_tier3_response(
                        draft=sp_draft,
                        title=f"High-Value Split Sale · {cust_sp['name']}",
                        description=f"{cust_sp['name']} · ₹{tot_sp:,.0f}",
                        total_val=tot_sp,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=sub_op_id,
                        payload_hash=payload_hash,
                        raw_transcript=raw_transcript,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        context_state=context_state,
                        prefix_receipts=receipts,
                    )
                sp_res = self.tx.record_split_customer_sale(
                    business_id=business_id,
                    user_id=user_id,
                    customer_id=str(cust_sp["id"]),
                    total_amount=tot_sp,
                    paid_amount=paid_sp,
                    payment_method=pm_sp,
                    transaction_date=txn_date_str,
                    operation_id=sub_op_id,
                )
                context_state["last_sale_id"] = str(sp_res["sale_id"])
                context_state["last_operation_kind"] = "record_sale"
                context_state["last_operation_id"] = sub_op_id
                context_state["last_customer_id"] = str(cust_sp["id"])
                context_state["last_customer_name"] = cust_sp["name"]
                pm_lbl = "Online" if pm_sp == "upi" else ("Bank" if pm_sp == "bank" else "Cash")
                replies.append(
                    f"{cust_sp['name']} ki ₹{sp_res['total_amount']:,.0f} sale save ho gayi: ₹{sp_res['paid_amount']:,.0f} {pm_lbl} aur ₹{sp_res['credit_amount']:,.0f} Udhaar (New Balance: ₹{sp_res['after_balance']:,.0f})."
                )
                receipts.append(
                    {
                        "id": f"slip-{sub_op_id}",
                        "operationId": sub_op_id,
                        "kind": "sale",
                        "title": f"Split Sale · {cust_sp['name']}",
                        "subtitle": f"{pm_lbl} + Khata Udhaar",
                        "transactionDate": txn_date_str,
                        "amountINR": sp_res["total_amount"],
                        "lines": [
                            {"label": f"Paid ({pm_lbl})", "value": f"₹{sp_res['paid_amount']:,.0f}", "tone": "sage"},
                            {"label": "Khata Udhaar", "value": f"₹{sp_res['credit_amount']:,.0f}", "tone": "ochre"},
                            {"label": "Total Khata Balance", "value": f"₹{sp_res['after_balance']:,.0f}", "tone": "neutral"},
                        ],
                        "status": "saved",
                        "reversible": True,
                    }
                )
                continue

            # Resolve Product (for stock & sale intents)
            if op.intent in {"inventory_receive", "inventory_damage", "inventory_expiry", "record_sale"}:
                target_prod: dict[str, Any] | None = None
                if op.uses_prior_context and not op.product_query and context_state.get("last_product_id"):
                    target_prod = next(
                        (p for p in products if str(p["id"]) == str(context_state["last_product_id"])), None
                    )
                else:
                    pres = resolve_product_guarded(
                        op.product_query,
                        raw_transcript,
                        products,
                        aliases,
                        price_hint=op.price_hint,
                    )
                    inferred_pm = op.payment_method or (
                        "upi"
                        if re.search(
                            r"\b(online|upi|ubi|gpay|google\s*paye?|phonepe|paytm)\b",
                            raw_transcript,
                            re.IGNORECASE,
                        )
                        else "cash"
                    )
                    if pres.status == "exact":
                        target_prod = pres.product
                    elif pres.status == "verify_alias" and pres.product:
                        remaining = [item.model_dump() for item in operations[idx + 1 :]]
                        if remaining:
                            context_state["pending_batch_items"] = remaining
                            context_state["pending_batch_source_transcript"] = raw_transcript
                        draft = {
                            "intent": op.intent,
                            "quantity": op.quantity or 1,
                            "unit_price": op.unit_price,
                            "payment_status": op.payment_status or "paid",
                            "payment_method": inferred_pm,
                            "paid_amount": op.paid_amount,
                            "customer_query": op.customer_query,
                            "notes": op.notes,
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
                            context_state["pending_batch_source_transcript"] = raw_transcript
                        draft = {
                            "intent": op.intent,
                            "quantity": op.quantity or 1,
                            "unit_price": op.unit_price,
                            "payment_status": op.payment_status or "paid",
                            "payment_method": inferred_pm,
                            "paid_amount": op.paid_amount,
                            "customer_query": op.customer_query,
                            "notes": op.notes,
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
                        cand_prices = {round(float(c.get("default_selling_price") or 0), 2) for c in pres.candidates}
                        shared_price = next(iter(cand_prices)) if len(cand_prices) == 1 and next(iter(cand_prices)) > 0 else None
                        if shared_price is not None and (
                            op.price_hint is not None or extract_clause_price_hint(op.product_query, raw_transcript) is not None
                        ):
                            msg = (
                                f"₹{shared_price:g} mein '{op.product_query}' ke {len(pres.candidates)} variants mile: {names} "
                                f"({qty_disp} {action_disp}). Confirm karein kaunsa wala?"
                            )
                        else:
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
                    elif pres.status == "not_found" and pres.candidates:
                        remaining = [item.model_dump() for item in operations[idx + 1 :]]
                        if remaining:
                            context_state["pending_batch_items"] = remaining
                            context_state["pending_batch_source_transcript"] = raw_transcript
                        item_name = (op.product_query or "New Product").title()
                        draft = {
                            "intent": op.intent,
                            "quantity": op.quantity or 1,
                            "unit_price": op.unit_price,
                            "payment_status": op.payment_status or "paid",
                            "payment_method": inferred_pm,
                            "paid_amount": op.paid_amount,
                            "customer_query": op.customer_query,
                            "notes": op.notes,
                            "transaction_date": txn_date_str,
                        }
                        context_state["pending_flow"] = {
                            "type": "disambiguate_product",
                            "candidate_ids": [str(c["id"]) for c in pres.candidates],
                            "draft": draft,
                        }
                        names = " ya ".join(c["name"] for c in pres.candidates)
                        msg = (
                            f"'{item_name}' nahi mila, par milta-julta item maujood hai: {names}. "
                            "Kya inmein se kisi ki baat kar rahe hain, ya naya product add karun?"
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
                                    *[
                                        {
                                            "id": str(c["id"]),
                                            "label": c["name"],
                                            "meta": f"Stock: {c.get('current_stock', 0):g} · ₹{float(c.get('default_selling_price', 0)):g}",
                                            "value": c["name"],
                                        }
                                        for c in pres.candidates
                                    ],
                                    {
                                        "id": "add-new",
                                        "label": f"+ Add New: {item_name}",
                                        "value": f"Naya product {item_name} add karo",
                                    },
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
                        context_state["pending_batch_source_transcript"] = raw_transcript
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
                        cres_sale = resolve_customer(op.customer_query, non_supplier_customers)
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
                        elif (op.payment_status in {"credit", "partial"}) or re.search(r"\budhaar\b", raw_transcript, re.IGNORECASE):
                            new_cust = self.tx.create_customer(
                                business_id=business_id,
                                name=op.customer_query.title(),
                            )
                            customers.append(new_cust)
                            non_supplier_customers.append(new_cust)
                            resolved_customer_id = str(new_cust["id"])
                            resolved_customer_name = new_cust["name"]

                    # Deterministic split/partial payment recovery for single-item sales
                    # e.g. "Nitin ko 2 kg chini bechi, usne 1 kg ke rupaye diye aur 1 kg udhaar"
                    eff_unit_price = float(op.unit_price or target_prod.get("default_selling_price") or 0)
                    eff_total = round(conv_qty * eff_unit_price, 2)
                    eff_pstat = op.payment_status or "paid"
                    eff_paid = op.paid_amount
                    split_speech_cue = bool(
                        len(operations) == 1
                        and re.search(r"\b(udhaar|credit)\b", raw_transcript, re.IGNORECASE)
                        and re.search(
                            r"\b(cash|online|upi|bank|rupay|rupaye|rupee|rupi|paise|diye|diya|doei|paid|aadha|half)\b",
                            raw_transcript,
                            re.IGNORECASE,
                        )
                    )
                    if op.intent == "record_sale" and (eff_pstat == "partial" or split_speech_cue) and eff_total > 0:
                        eff_pstat = "partial"
                        if eff_paid is None or float(eff_paid) <= 0 or float(eff_paid) >= eff_total:
                            paid_qty_m = None
                            if op.notes and "paid_qty:" in str(op.notes):
                                mq = re.search(r"paid_qty:(\d+(?:\.\d+)?)", str(op.notes))
                                if mq:
                                    paid_qty_m = float(mq.group(1))
                            if paid_qty_m is None:
                                m_frac = re.search(
                                    r"(?:usne|aur|,)\s*(\d+(?:\.\d+)?|\bek\b|\bdo\b|\bteen\b|\baadha\b|\bhalf\b)\s*(?:kg|kilo|gram|g|packet|packets|piece|pieces|litre|ltr|box)?\s*(?:ke|ki)?\s*(?:rupay|rupaye|rupaiye|rupee|rupi|paise|cash|online|upi|rs)?\s*(?:diye|diya|doei|paid)",
                                    raw_transcript,
                                    re.IGNORECASE,
                                )
                                if m_frac:
                                    paid_qty_m = parse_indian_number(m_frac.group(1))
                            if paid_qty_m is not None and 0 < paid_qty_m < conv_qty:
                                eff_paid = round(paid_qty_m * eff_unit_price, 2)
                            elif re.search(r"\b(aadha|adha|half)\b", raw_transcript, re.IGNORECASE):
                                eff_paid = round(eff_total / 2.0, 2)

                    draft = {
                        "intent": op.intent,
                        "product_id": str(target_prod["id"]),
                        "product_name": target_prod["name"],
                        "quantity": conv_qty,
                        "unit": target_prod["base_unit"],
                        "unit_price": op.unit_price,
                        "payment_status": eff_pstat,
                        "payment_method": op.payment_method or "cash",
                        "paid_amount": eff_paid,
                        "customer_id": resolved_customer_id,
                        "customer_name": resolved_customer_name,
                        "transaction_date": txn_date_str,
                        "notes": op.notes,
                    }
                    # If user explicitly negates/corrects a previously logged damage/expiry count on this item
                    # (e.g. "jo 14 Nescafe gold jars aaye the, unme se 2 damaged the, ek nahi"), update instead of double-deducting.
                    if op.intent in {"inventory_damage", "inventory_expiry"} and re.search(
                        r"(?:\b(?:ek|do|teen|chaar|paanch|\d+)\s+(?:hi\s+)?(?:nahi|nahin|नहीं)\b|\bnot\s+(?:\d+|one|two|three)\b|\b(?:sorry|actually|galti\s+se)\b)",
                        raw_transcript,
                        re.IGNORECASE,
                    ):
                        mtype_corr = "expiry" if op.intent == "inventory_expiry" else "damage"
                        prior_op_id = (
                            str(context_state.get("last_damage_operation_id"))
                            if str(context_state.get("last_damage_product_id") or "") == str(target_prod["id"])
                            and context_state.get("last_damage_operation_id")
                            else None
                        )
                        prior_mv = None
                        if not prior_op_id:
                            prior_mv = self.tx.find_latest_active_loss_movement(
                                business_id=business_id,
                                product_id=str(target_prod["id"]),
                                movement_type=mtype_corr,
                                transaction_date=txn_date_str,
                            )
                        if prior_op_id or prior_mv:
                            corr_raw = extract_post_negation_quantity(raw_transcript)
                            corr_qty = conv_qty
                            if corr_raw is not None and op.quantity is not None and abs(float(corr_raw) - float(op.quantity)) > 1e-6:
                                cq, u_err = convert_to_base_quantity(
                                    quantity=float(corr_raw),
                                    spoken_unit=op.unit,
                                    base_unit=target_prod["base_unit"],
                                )
                                if not u_err and cq is not None:
                                    corr_qty = cq
                            slip, rep = self._apply_damage_correction(
                                business_id=business_id,
                                user_id=user_id,
                                new_qty=float(corr_qty),
                                operation_id=sub_op_id,
                                txn_date=txn_date_str,
                                old_operation_id=prior_op_id or (str(prior_mv["operation_id"]) if prior_mv else None),
                                product_id=str(target_prod["id"]),
                                movement_type=mtype_corr,
                                context_state=context_state,
                            )
                            after_val = next(
                                (ln["value"].split("→")[-1].strip() for ln in slip["lines"] if ln["label"] == "Stock Level"),
                                None,
                            )
                            if after_val is not None:
                                try:
                                    target_prod["current_stock"] = float(after_val)
                                except ValueError:
                                    pass
                            receipts.append(slip)
                            replies.append(rep)
                            continue

                    # Tier-3 check (>= ₹5,000) for direct product sale / stock receive
                    est_val = round(
                        float(conv_qty)
                        * float(
                            op.unit_price
                            if op.unit_price is not None
                            else (target_prod.get("default_selling_price", 0) if op.intent == "record_sale" else target_prod.get("default_cost_price", 0))
                        ),
                        2,
                    )
                    if op.intent in {"record_sale", "inventory_receive"} and SecurityPolicyEngine.classify_risk_tier(
                        intent=op.intent, amount_inr=est_val
                    ) == "tier3":
                        return self._issue_tier3_response(
                            draft=draft,
                            title=f"High-Value {op.intent.replace('_', ' ').title()}",
                            description=f"{target_prod['name']} · {conv_qty:g} {target_prod['base_unit']}",
                            total_val=est_val,
                            business_id=business_id,
                            user_id=user_id,
                            conv_id=conv_id,
                            today_str=today_str,
                            operation_id=sub_op_id,
                            payload_hash=payload_hash,
                            raw_transcript=raw_transcript,
                            language=language,
                            stt_provider=stt_provider,
                            stt_confidence=stt_confidence,
                            context_state=context_state,
                            prefix_receipts=receipts,
                        )

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
                exp_amt = float(op.total_amount)
                exp_draft = {
                    "intent": "record_expense",
                    "total_amount": exp_amt,
                    "expense_category": op.expense_category or "Shop Expense",
                    "description": op.description or raw_transcript,
                    "payment_method": op.payment_method or "cash",
                    "transaction_date": txn_date_str,
                }
                if SecurityPolicyEngine.classify_risk_tier(intent="record_expense", amount_inr=exp_amt) == "tier3":
                    return self._issue_tier3_response(
                        draft=exp_draft,
                        title=f"High-Value Expense · {exp_draft['expense_category']}",
                        description=f"{exp_draft['expense_category']} · ₹{exp_amt:,.0f}",
                        total_val=exp_amt,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=sub_op_id,
                        payload_hash=payload_hash,
                        raw_transcript=raw_transcript,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        context_state=context_state,
                        prefix_receipts=receipts,
                    )
                slip, rep = self._commit_draft_now(
                    draft=exp_draft,
                    business_id=business_id,
                    user_id=user_id,
                    operation_id=sub_op_id,
                    txn_date=txn_date_str,
                    product=None,
                    context_state=context_state,
                )
                receipts.append(slip)
                replies.append(rep)

            elif op.intent == "customer_return":
                if not op.product_query and not context_state.get("last_product_id"):
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Kaunsa product wapas aaya hai aur kitni quantity hai?",
                        language=language,  # type: ignore[arg-type]
                    )
                ret_prod: dict[str, Any] | None = None
                if op.product_query:
                    pres_ret = resolve_product_guarded(
                        op.product_query,
                        raw_transcript,
                        products,
                        aliases,
                        price_hint=op.price_hint,
                    )
                    if pres_ret.status == "ambiguous" and pres_ret.candidates:
                        names = " ya ".join(c["name"] for c in pres_ret.candidates)
                        msg = f"'{op.product_query}' ke {len(pres_ret.candidates)} options mile: {names}. Kaunsa product wapas aaya hai?"
                        return VoiceTurnResult(
                            operation_id=operation_id,
                            status="needs_clarification",
                            transcript=raw_transcript,
                            reply=msg,
                            language=language,  # type: ignore[arg-type]
                            receipts=receipts,
                            clarification={
                                "kind": "disambiguate_product",
                                "prompt": msg,
                                "candidates": [
                                    {"id": str(c["id"]), "label": c["name"], "meta": f"Stock: {c['current_stock']:g} · ₹{float(c['default_selling_price']):g}", "value": c["name"]}
                                    for c in pres_ret.candidates
                                ],
                            },
                        )
                    if pres_ret.status in {"exact", "verify_alias"} and pres_ret.product:
                        ret_prod = pres_ret.product
                else:
                    ret_prod = next((p for p in products if str(p["id"]) == str(context_state.get("last_product_id"))), None)

                if not ret_prod:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"'{op.product_query or 'Product'}' inventory mein nahi mila. Kripya sahi naam bolein.",
                        language=language,  # type: ignore[arg-type]
                    )

                ret_qty, u_err = convert_to_base_quantity(
                    quantity=float(op.quantity or 1),
                    spoken_unit=op.unit,
                    base_unit=ret_prod["base_unit"],
                )
                if u_err or ret_qty is None:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=u_err or "Quantity aur unit saaf bolein.",
                        language=language,  # type: ignore[arg-type]
                    )

                ret_cust_id: str | None = None
                ret_cust_name: str | None = None
                if op.customer_query:
                    cres_ret = resolve_customer(op.customer_query, non_supplier_customers)
                    if cres_ret.status == "exact" and cres_ret.customer:
                        ret_cust_id = str(cres_ret.customer["id"])
                        ret_cust_name = cres_ret.customer["name"]

                refund_amt = (
                    float(op.total_amount)
                    if op.total_amount is not None
                    else round(ret_qty * float(op.unit_price or ret_prod.get("default_selling_price") or 0), 2)
                )
                refund_m = op.payment_method or "cash"
                if SecurityPolicyEngine.classify_risk_tier(intent="customer_return", amount_inr=refund_amt) == "tier3":
                    return self._issue_tier3_response(
                        draft={
                            "intent": "customer_return",
                            "product_id": str(ret_prod["id"]),
                            "product_name": ret_prod["name"],
                            "quantity": ret_qty,
                            "total_amount": refund_amt,
                            "refund_method": refund_m,
                            "customer_id": ret_cust_id,
                            "customer_name": ret_cust_name,
                            "transaction_date": txn_date_str,
                        },
                        title=f"High-Value Return · {ret_prod['name']}",
                        description=f"{ret_qty:g} {ret_prod['name']} · ₹{refund_amt:,.0f}",
                        total_val=refund_amt,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=sub_op_id,
                        payload_hash=payload_hash,
                        raw_transcript=raw_transcript,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        context_state=context_state,
                        prefix_receipts=receipts,
                    )
                ret_res = self.tx.record_customer_return(
                    business_id=business_id,
                    user_id=user_id,
                    product_id=str(ret_prod["id"]),
                    product_name=ret_prod["name"],
                    quantity=ret_qty,
                    unit=ret_prod["base_unit"],
                    refund_amount=refund_amt,
                    refund_method=refund_m,
                    customer_id=ret_cust_id,
                    transaction_date=txn_date_str,
                    operation_id=sub_op_id,
                )
                ret_prod["current_stock"] = float(ret_res["after_stock"])
                context_state["last_product_id"] = str(ret_prod["id"])
                context_state["last_product_name"] = ret_prod["name"]
                context_state["last_operation_kind"] = "customer_return"
                context_state["last_operation_id"] = sub_op_id
                refund_lbl = (
                    "Khata Udhaar"
                    if refund_m == "credit"
                    else ("Online" if refund_m == "upi" else ("Bank" if refund_m == "bank" else "Cash"))
                )
                sale_note = " aur Sales update ho gayi" if ret_res.get("sale_adjusted") else ""
                replies.append(
                    f"{ret_qty:g} {ret_prod['name']} wapas li gayi, ₹{ret_res['refund_amount']:,.0f} {refund_lbl} adjust hua{sale_note}. Updated stock: {ret_res['after_stock']:g}."
                )
                ret_lines = [
                    {"label": "Returned Stock", "value": f"+{ret_qty:g} {ret_prod['base_unit']}", "tone": "sage"},
                    {"label": f"Refund ({refund_lbl})", "value": f"₹{ret_res['refund_amount']:,.0f}", "tone": "ochre"},
                    {"label": "Stock Level", "value": f"{ret_res['before_stock']:g} → {ret_res['after_stock']:g}", "tone": "neutral"},
                ]
                receipts.append(
                    {
                        "id": f"slip-{sub_op_id}",
                        "operationId": sub_op_id,
                        "kind": "receive",
                        "title": f"Customer Return · {ret_prod['name']}",
                        "subtitle": f"{ret_cust_name + ' · ' if ret_cust_name else ''}Wapsi & Refund",
                        "transactionDate": txn_date_str,
                        "amountINR": ret_res["refund_amount"],
                        "lines": ret_lines,
                        "status": "saved",
                        "reversible": True,
                    }
                )

            elif op.intent in {"record_supplier_credit", "record_supplier_payment"}:
                sup_name = (op.customer_query or "").strip()
                payoff_cue = bool(
                    re.search(
                        r"\b(wapas|waapas|vahapas|baapas|chuka|settled?|clear|paid\s+back|dee?\s*diyae?|de\s+diya)\b",
                        raw_transcript,
                        re.IGNORECASE,
                    )
                )
                # Handle single-op compound names like customer_query="Gita and Rahul"
                if (op.intent == "record_supplier_payment" or payoff_cue) and re.search(r"(?:,|\band\b|\baur\b)", sup_name, re.IGNORECASE):
                    split_names = [p.strip() for p in re.split(r"(?:,|\band\b|\baur\b)", sup_name, flags=re.IGNORECASE) if p.strip()]
                    multi_sups = []
                    for nm in split_names:
                        sr = resolve_customer(nm, suppliers_list)
                        if sr.status == "exact" and sr.customer and float(sr.customer.get("outstanding_balance") or 0) > 0.009:
                            multi_sups.append(sr.customer)
                    if multi_sups:
                        total_ms = round(sum(float(s.get("outstanding_balance") or 0) for s in multi_sups), 2)
                        pm_ms = op.payment_method or "cash"
                        ms_ids = [str(s["id"]) for s in multi_sups]
                        if SecurityPolicyEngine.classify_risk_tier(intent="record_supplier_payment", amount_inr=total_ms) == "tier3":
                            return self._issue_tier3_response(
                                draft={
                                    "intent": "settle_all_suppliers",
                                    "supplier_ids": ms_ids,
                                    "total_amount": total_ms,
                                    "payment_method": pm_ms,
                                    "transaction_date": txn_date_str,
                                },
                                title=f"Settle Suppliers ({len(multi_sups)})",
                                description=", ".join(s["name"] for s in multi_sups) + f" · ₹{total_ms:,.0f}",
                                total_val=total_ms,
                                business_id=business_id,
                                user_id=user_id,
                                conv_id=conv_id,
                                today_str=today_str,
                                operation_id=sub_op_id,
                                payload_hash=payload_hash,
                                raw_transcript=raw_transcript,
                                language=language,
                                stt_provider=stt_provider,
                                stt_confidence=stt_confidence,
                                context_state=context_state,
                                prefix_receipts=receipts,
                            )
                        st_ms = self.tx.settle_all_suppliers(
                            business_id=business_id,
                            user_id=user_id,
                            payment_method=pm_ms,
                            transaction_date=txn_date_str,
                            operation_id=sub_op_id,
                            supplier_ids=ms_ids,
                        )
                        supplier_ops.extend(st_ms["supplier_ops"])
                        pm_lbl = "Online" if pm_ms == "upi" else ("Bank" if pm_ms == "bank" else "Cash")
                        names_paid = ", ".join(s["name"] for s in st_ms["settled_suppliers"])
                        replies.append(f"Suppliers ({names_paid}) ka total ₹{st_ms['total_paid']:,.0f} ({pm_lbl}) udhaar settle ho gaya.")
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "expense",
                                "title": f"Suppliers Settled · {st_ms['settled_count']}",
                                "subtitle": f"Via {pm_lbl}",
                                "transactionDate": txn_date_str,
                                "amountINR": st_ms["total_paid"],
                                "lines": [
                                    {"label": s["name"], "value": f"Paid ₹{s['paid_amount']:,.0f}", "tone": "sage"}
                                    for s in st_ms["settled_suppliers"]
                                ],
                                "status": "saved",
                                "reversible": True,
                            }
                        )
                        continue
                # Bundle multi-supplier full payoff ("Gita and Rahul dono ka udhaar waapas kar diya")
                sup_group_indices = [
                    j for j in range(idx, len(operations))
                    if j not in processed_indices
                    and operations[j].intent in {"record_supplier_payment", "record_supplier_credit"}
                    and (operations[j].intent == "record_supplier_payment" or payoff_cue)
                    and operations[j].customer_query
                    and operations[j].total_amount is None
                ]
                if len(sup_group_indices) >= 2:
                    matched_sups: list[dict[str, Any]] = []
                    seen_sids: set[str] = set()
                    for j in sup_group_indices:
                        q_s = str(operations[j].customer_query or "").strip()
                        sres = resolve_customer(q_s, suppliers_list)
                        if sres.status == "exact" and sres.customer and float(sres.customer.get("outstanding_balance") or 0) > 0.009:
                            sid = str(sres.customer["id"])
                            if sid not in seen_sids:
                                seen_sids.add(sid)
                                matched_sups.append(sres.customer)
                    if matched_sups:
                        total_grp_due = round(sum(float(s.get("outstanding_balance") or 0) for s in matched_sups), 2)
                        pm_grp = op.payment_method or "cash"
                        target_ids = [str(s["id"]) for s in matched_sups]
                        for j in sup_group_indices:
                            processed_indices.add(j)
                        if SecurityPolicyEngine.classify_risk_tier(intent="record_supplier_payment", amount_inr=total_grp_due) == "tier3":
                            rem_grp = [item.model_dump() for k, item in enumerate(operations[idx + 1:], start=idx + 1) if k not in processed_indices]
                            if rem_grp:
                                context_state["pending_batch_items"] = rem_grp
                                context_state["pending_batch_source_transcript"] = raw_transcript
                            return self._issue_tier3_response(
                                draft={
                                    "intent": "settle_all_suppliers",
                                    "supplier_ids": target_ids,
                                    "total_amount": total_grp_due,
                                    "payment_method": pm_grp,
                                    "transaction_date": txn_date_str,
                                },
                                title=f"Settle Suppliers ({len(matched_sups)})",
                                description=", ".join(s["name"] for s in matched_sups) + f" · ₹{total_grp_due:,.0f}",
                                total_val=total_grp_due,
                                business_id=business_id,
                                user_id=user_id,
                                conv_id=conv_id,
                                today_str=today_str,
                                operation_id=sub_op_id,
                                payload_hash=payload_hash,
                                raw_transcript=raw_transcript,
                                language=language,
                                stt_provider=stt_provider,
                                stt_confidence=stt_confidence,
                                context_state=context_state,
                                prefix_receipts=receipts,
                            )
                        st_g = self.tx.settle_all_suppliers(
                            business_id=business_id,
                            user_id=user_id,
                            payment_method=pm_grp,
                            transaction_date=txn_date_str,
                            operation_id=sub_op_id,
                            supplier_ids=target_ids,
                        )
                        supplier_ops.extend(st_g["supplier_ops"])
                        context_state["last_operation_kind"] = "record_supplier_payment"
                        context_state["last_operation_id"] = sub_op_id
                        pm_lbl = "Online" if pm_grp == "upi" else ("Bank" if pm_grp == "bank" else "Cash")
                        names_paid = ", ".join(s["name"] for s in st_g["settled_suppliers"])
                        replies.append(f"Suppliers ({names_paid}) ka total ₹{st_g['total_paid']:,.0f} ({pm_lbl}) udhaar settle ho gaya.")
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "expense",
                                "title": f"Suppliers Settled · {st_g['settled_count']}",
                                "subtitle": f"Via {pm_lbl}",
                                "transactionDate": txn_date_str,
                                "amountINR": st_g["total_paid"],
                                "lines": [
                                    {"label": s["name"], "value": f"Paid ₹{s['paid_amount']:,.0f}", "tone": "sage"}
                                    for s in st_g["settled_suppliers"]
                                ],
                                "status": "saved",
                                "reversible": True,
                            }
                        )
                        continue

                is_all_suppliers = bool(
                    (op.intent == "record_supplier_payment" or payoff_cue)
                    and (
                        sup_name.lower() in {"all", "sare", "saare", "sabhi", "every", "everyone", "suppliers", "dono", "both"}
                        or (not sup_name and re.search(r"\b(sare|saare|sabhi|all|dono)\b", raw_transcript, re.IGNORECASE))
                    )
                )
                if is_all_suppliers:
                    due_sups = [
                        row for row in customers
                        if "[SUPPLIER]" in str(row.get("area_note") or "").upper()
                        and float(row.get("outstanding_balance") or 0) > 0.009
                    ]
                    if not due_sups:
                        replies.append("Abhi kisi bhi supplier ka koi udhaar baki nahi hai.")
                        continue
                    total_due = round(sum(float(row.get("outstanding_balance") or 0) for row in due_sups), 2)
                    pm_all = op.payment_method or "cash"
                    if SecurityPolicyEngine.classify_risk_tier(intent="record_supplier_payment", amount_inr=total_due) == "tier3":
                        remaining_all = [item.model_dump() for item in operations[idx + 1 :]]
                        if remaining_all:
                            context_state["pending_batch_items"] = remaining_all
                            context_state["pending_batch_source_transcript"] = raw_transcript
                        return self._issue_tier3_response(
                            draft={
                                "intent": "settle_all_suppliers",
                                "total_amount": total_due,
                                "payment_method": pm_all,
                                "transaction_date": txn_date_str,
                            },
                            title=f"Settle All Suppliers ({len(due_sups)})",
                            description=", ".join(s["name"] for s in due_sups) + f" · ₹{total_due:,.0f}",
                            total_val=total_due,
                            business_id=business_id,
                            user_id=user_id,
                            conv_id=conv_id,
                            today_str=today_str,
                            operation_id=sub_op_id,
                            payload_hash=payload_hash,
                            raw_transcript=raw_transcript,
                            language=language,
                            stt_provider=stt_provider,
                            stt_confidence=stt_confidence,
                            context_state=context_state,
                            prefix_receipts=receipts,
                        )
                    st = self.tx.settle_all_suppliers(
                        business_id=business_id,
                        user_id=user_id,
                        payment_method=pm_all,
                        transaction_date=txn_date_str,
                        operation_id=sub_op_id,
                    )
                    supplier_ops.extend(st["supplier_ops"])
                    context_state["last_operation_kind"] = "record_supplier_payment"
                    context_state["last_operation_id"] = sub_op_id
                    pm_lbl = "Online" if pm_all == "upi" else ("Bank" if pm_all == "bank" else "Cash")
                    names_paid = ", ".join(s["name"] for s in st["settled_suppliers"])
                    replies.append(f"Sabhi suppliers ({names_paid}) ka total ₹{st['total_paid']:,.0f} ({pm_lbl}) udhaar settle ho gaya.")
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "expense",
                            "title": f"All Suppliers Settled · {st['settled_count']}",
                            "subtitle": f"Via {pm_lbl}",
                            "transactionDate": txn_date_str,
                            "amountINR": st["total_paid"],
                            "lines": [
                                {"label": s["name"], "value": f"Paid ₹{s['paid_amount']:,.0f}", "tone": "sage"}
                                for s in st["settled_suppliers"]
                            ],
                            "status": "saved",
                            "reversible": True,
                        }
                    )
                    continue

                if not sup_name:
                    remaining_sup = [item.model_dump() for item in operations[idx + 1 :]]
                    if remaining_sup:
                        context_state["pending_batch_items"] = remaining_sup
                        context_state["pending_batch_source_transcript"] = raw_transcript
                    context_state["pending_flow"] = {
                        "type": "missing_slot",
                        "missing_field": "supplier_name",
                        "draft": {
                            "intent": op.intent,
                            "total_amount": op.total_amount,
                            "payment_method": op.payment_method or "cash",
                            "transaction_date": txn_date_str,
                        },
                    }
                    sup_cands = [
                        {
                            "id": str(r["id"]),
                            "label": str(r["name"]),
                            "meta": f"Payable ₹{float(r.get('outstanding_balance') or 0):,.0f}",
                            "value": str(r["name"]),
                        }
                        for r in customers
                        if "[SUPPLIER]" in str(r.get("area_note") or "").upper()
                    ]
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply="Kis supplier ka naam record karna hai?",
                        language=language,  # type: ignore[arg-type]
                        receipts=receipts,
                        clarification={
                            "kind": "disambiguate_customer",
                            "prompt": "Select supplier",
                            "candidates": sup_cands[:6],
                        } if sup_cands else None,
                    )
                sup_row, created_new = self.tx.find_or_create_supplier(business_id=business_id, name=sup_name)
                if created_new:
                    customers.append(sup_row)
                    suppliers_list.append(sup_row)
                effective_sup_intent = (
                    "record_supplier_payment"
                    if (op.intent == "record_supplier_payment" or (payoff_cue and float(sup_row.get("outstanding_balance") or 0) > 0.009))
                    else "record_supplier_credit"
                )
                sup_amt = float(op.total_amount or op.paid_amount or op.unit_price or 0)
                if effective_sup_intent == "record_supplier_payment" and sup_amt <= 0 and float(sup_row.get("outstanding_balance") or 0) > 0.009:
                    sup_amt = round(float(sup_row["outstanding_balance"]), 2)
                if sup_amt <= 0:
                    return VoiceTurnResult(
                        operation_id=operation_id,
                        status="needs_clarification",
                        transcript=raw_transcript,
                        reply=f"Supplier {sup_name} ke liye kitne rupaye record karne hain?",
                        language=language,  # type: ignore[arg-type]
                    )
                if SecurityPolicyEngine.classify_risk_tier(intent=effective_sup_intent, amount_inr=sup_amt) == "tier3":
                    return self._issue_tier3_response(
                        draft={
                            "intent": effective_sup_intent,
                            "supplier_id": str(sup_row["id"]),
                            "supplier_name": str(sup_row["name"]),
                            "total_amount": sup_amt,
                            "payment_method": op.payment_method or "cash",
                            "transaction_date": txn_date_str,
                        },
                        title=(
                            f"High-Value Supplier Credit · {sup_row['name']}"
                            if effective_sup_intent == "record_supplier_credit"
                            else f"High-Value Supplier Payment · {sup_row['name']}"
                        ),
                        description=f"Supplier {sup_row['name']} · ₹{sup_amt:,.0f}",
                        total_val=sup_amt,
                        business_id=business_id,
                        user_id=user_id,
                        conv_id=conv_id,
                        today_str=today_str,
                        operation_id=sub_op_id,
                        payload_hash=payload_hash,
                        raw_transcript=raw_transcript,
                        language=language,
                        stt_provider=stt_provider,
                        stt_confidence=stt_confidence,
                        context_state=context_state,
                        prefix_receipts=receipts,
                    )
                if effective_sup_intent == "record_supplier_credit":
                    sc = self.tx.record_supplier_credit(
                        business_id=business_id,
                        supplier_id=str(sup_row["id"]),
                        amount=sup_amt,
                    )
                    supplier_ops.append({"type": "credit", "supplier_id": str(sup_row["id"]), "amount": sup_amt})
                    context_state["last_operation_kind"] = "record_supplier_credit"
                    context_state["last_operation_id"] = sub_op_id
                    replies.append(
                        f"Supplier {sup_row['name']} ke Khata mein ₹{sup_amt:,.0f} payable add ho gaya (Total Payable: ₹{sc['after_balance']:,.0f})."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "receive",
                            "title": f"Supplier Credit · {sup_row['name']}",
                            "subtitle": "Wholesale Accounts Payable",
                            "transactionDate": txn_date_str,
                            "amountINR": sup_amt,
                            "lines": [
                                {"label": "Credit Added", "value": f"+₹{sup_amt:,.0f}", "tone": "ochre"},
                                {"label": "Total Payable", "value": f"₹{sc['after_balance']:,.0f}", "tone": "neutral"},
                            ],
                            "status": "saved",
                            "reversible": True,
                        }
                    )
                else:
                    pm_sup = op.payment_method or "cash"
                    pm_lbl = "Online" if pm_sup == "upi" else ("Bank" if pm_sup == "bank" else "Cash")
                    sp = self.tx.record_supplier_payment(
                        business_id=business_id,
                        user_id=user_id,
                        supplier_id=str(sup_row["id"]),
                        supplier_name=str(sup_row["name"]),
                        amount=sup_amt,
                        payment_method=pm_sup,
                        transaction_date=txn_date_str,
                        operation_id=sub_op_id,
                    )
                    supplier_ops.append({"type": "payment", "supplier_id": str(sup_row["id"]), "amount": sup_amt})
                    context_state["last_operation_kind"] = "record_supplier_payment"
                    context_state["last_operation_id"] = sub_op_id
                    replies.append(
                        f"Supplier {sup_row['name']} ko ₹{sup_amt:,.0f} ({pm_lbl}) pay kar diya gaya. Remaining Payable: ₹{sp['after_balance']:,.0f}."
                    )
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "expense",
                            "title": f"Supplier Paid · {sup_row['name']}",
                            "subtitle": f"Via {pm_lbl}",
                            "transactionDate": txn_date_str,
                            "amountINR": sup_amt,
                            "lines": [
                                {"label": "Paid Amount", "value": f"₹{sup_amt:,.0f} ({pm_lbl})", "tone": "sage"},
                                {"label": "Remaining Payable", "value": f"₹{sp['after_balance']:,.0f}", "tone": "ochre" if sp["after_balance"] > 0 else "sage"},
                            ],
                            "status": "saved",
                            "reversible": True,
                        }
                    )

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
                    payoff_cue_c = bool(
                        re.search(
                            r"\b(wapas|waapas|vahapas|baapas|chuka|settled?|clear|paid\s+back|dee?\s*diyae?|de\s+diya)\b",
                            raw_transcript,
                            re.IGNORECASE,
                        )
                    )
                    cres = resolve_customer(op.customer_query, non_supplier_customers)
                    # If user says "Gita and Rahul dono ka udhaar waapas kar diya" (and Gemini routed to customer_payment/udhaar),
                    # check if named party has a pending [SUPPLIER] payable instead of an unpaid Customer balance!
                    if op.intent in {"record_customer_payment", "record_udhaar_credit"} and op.customer_query:
                        cust_due_val = float(cres.customer.get("outstanding_balance") or 0) if (cres.status == "exact" and cres.customer) else 0.0
                        sres_fallback = resolve_customer(op.customer_query, suppliers_list)
                        if (
                            sres_fallback.status == "exact"
                            and sres_fallback.customer
                            and float(sres_fallback.customer.get("outstanding_balance") or 0) > 0.009
                            and (cres.status != "exact" or (cust_due_val <= 0.009 and (op.intent == "record_customer_payment" or payoff_cue_c)))
                        ):
                            # Gather all matching supplier payoff ops in this batch
                            fb_indices = [
                                j for j in range(idx, len(operations))
                                if j not in processed_indices
                                and operations[j].intent in {"record_customer_payment", "record_udhaar_credit", "record_supplier_payment"}
                                and operations[j].customer_query
                            ]
                            fb_sups: list[dict[str, Any]] = []
                            seen_fb: set[str] = set()
                            for j in fb_indices:
                                sr = resolve_customer(str(operations[j].customer_query or ""), suppliers_list)
                                if sr.status == "exact" and sr.customer and float(sr.customer.get("outstanding_balance") or 0) > 0.009:
                                    if str(sr.customer["id"]) not in seen_fb:
                                        seen_fb.add(str(sr.customer["id"]))
                                        fb_sups.append(sr.customer)
                                        processed_indices.add(j)
                            if fb_sups:
                                total_fb_due = round(sum(float(s.get("outstanding_balance") or 0) for s in fb_sups), 2)
                                pm_fb = op.payment_method or "cash"
                                fb_ids = [str(s["id"]) for s in fb_sups]
                                if SecurityPolicyEngine.classify_risk_tier(intent="record_supplier_payment", amount_inr=total_fb_due) == "tier3":
                                    return self._issue_tier3_response(
                                        draft={
                                            "intent": "settle_all_suppliers",
                                            "supplier_ids": fb_ids,
                                            "total_amount": total_fb_due,
                                            "payment_method": pm_fb,
                                            "transaction_date": txn_date_str,
                                        },
                                        title=f"Settle Suppliers ({len(fb_sups)})",
                                        description=", ".join(s["name"] for s in fb_sups) + f" · ₹{total_fb_due:,.0f}",
                                        total_val=total_fb_due,
                                        business_id=business_id,
                                        user_id=user_id,
                                        conv_id=conv_id,
                                        today_str=today_str,
                                        operation_id=sub_op_id,
                                        payload_hash=payload_hash,
                                        raw_transcript=raw_transcript,
                                        language=language,
                                        stt_provider=stt_provider,
                                        stt_confidence=stt_confidence,
                                        context_state=context_state,
                                        prefix_receipts=receipts,
                                    )
                                st_fb = self.tx.settle_all_suppliers(
                                    business_id=business_id,
                                    user_id=user_id,
                                    payment_method=pm_fb,
                                    transaction_date=txn_date_str,
                                    operation_id=sub_op_id,
                                    supplier_ids=fb_ids,
                                )
                                supplier_ops.extend(st_fb["supplier_ops"])
                                context_state["last_operation_kind"] = "record_supplier_payment"
                                context_state["last_operation_id"] = sub_op_id
                                pm_lbl = "Online" if pm_fb == "upi" else ("Bank" if pm_fb == "bank" else "Cash")
                                names_paid = ", ".join(s["name"] for s in st_fb["settled_suppliers"])
                                replies.append(f"Suppliers ({names_paid}) ka total ₹{st_fb['total_paid']:,.0f} ({pm_lbl}) udhaar settle ho gaya.")
                                receipts.append(
                                    {
                                        "id": f"slip-{sub_op_id}",
                                        "operationId": sub_op_id,
                                        "kind": "expense",
                                        "title": f"Suppliers Settled · {st_fb['settled_count']}",
                                        "subtitle": f"Via {pm_lbl}",
                                        "transactionDate": txn_date_str,
                                        "amountINR": st_fb["total_paid"],
                                        "lines": [
                                            {"label": s["name"], "value": f"Paid ₹{s['paid_amount']:,.0f}", "tone": "sage"}
                                            for s in st_fb["settled_suppliers"]
                                        ],
                                        "status": "saved",
                                        "reversible": True,
                                    }
                                )
                                continue
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
                        updated_cust = self.tx.update_customer(
                            business_id=business_id,
                            customer_id=str(cust["id"]),
                            name=op.new_name,
                            phone=op.phone,
                            area_note=op.area_note,
                        )
                        if op.new_name:
                            cust["name"] = updated_cust["name"]
                            rep = f"{cust['name']} ka naam aur details update ho gayi hain."
                        else:
                            rep = f"{cust['name']} ki Khata details update ho gayi hain."
                        replies.append(rep)
                        edit_lines = []
                        if op.new_name:
                            edit_lines.append({"label": "New Name", "value": str(updated_cust["name"]), "tone": "sage"})
                        if op.phone is not None:
                            edit_lines.append({"label": "Phone", "value": str(op.phone), "tone": "sage"})
                        if op.area_note is not None:
                            edit_lines.append({"label": "Note", "value": str(op.area_note), "tone": "neutral"})
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "payment",
                                "title": f"Customer Updated · {updated_cust['name']}",
                                "subtitle": "Voice Profile Update",
                                "transactionDate": txn_date_str,
                                "lines": edit_lines or [{"label": "Profile", "value": "Updated", "tone": "sage"}],
                                "status": "saved",
                            }
                        )
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
                        if SecurityPolicyEngine.classify_risk_tier(intent="record_udhaar_credit", amount_inr=amt) == "tier3":
                            return self._issue_tier3_response(
                                draft={
                                    "intent": "record_udhaar_credit",
                                    "customer_id": str(cust["id"]),
                                    "customer_name": cust["name"],
                                    "total_amount": amt,
                                    "notes": op.description or "Voice Khata entry",
                                    "transaction_date": txn_date_str,
                                },
                                title=f"High-Value Khata Udhaar · {cust['name']}",
                                description=f"{cust['name']} · ₹{amt:,.0f}",
                                total_val=amt,
                                business_id=business_id,
                                user_id=user_id,
                                conv_id=conv_id,
                                today_str=today_str,
                                operation_id=sub_op_id,
                                payload_hash=payload_hash,
                                raw_transcript=raw_transcript,
                                language=language,
                                stt_provider=stt_provider,
                                stt_confidence=stt_confidence,
                                context_state=context_state,
                                prefix_receipts=receipts,
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
                        context_state["last_operation_kind"] = "record_udhaar_credit"
                        context_state["last_operation_id"] = sub_op_id
                        context_state["last_customer_id"] = str(cust["id"])
                        context_state["last_customer_name"] = cust["name"]
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
                        if amt <= 0 and float(cust.get("outstanding_balance") or 0) > 0.009 and re.search(
                            r"\b(pura|poora|sab|all|wapas|waapas|chuka|settle|clear|dono|full)\b", raw_transcript, re.IGNORECASE
                        ):
                            amt = round(float(cust["outstanding_balance"]), 2)
                        if amt <= 0:
                            return VoiceTurnResult(
                                operation_id=operation_id,
                                status="needs_clarification",
                                transcript=raw_transcript,
                                reply=f"{cust['name']} se kitne rupaye receive hue?",
                                language=language,  # type: ignore[arg-type]
                            )
                        if SecurityPolicyEngine.classify_risk_tier(intent="record_customer_payment", amount_inr=amt) == "tier3":
                            return self._issue_tier3_response(
                                draft={
                                    "intent": "record_customer_payment",
                                    "customer_id": str(cust["id"]),
                                    "customer_name": cust["name"],
                                    "total_amount": amt,
                                    "payment_method": op.payment_method or "cash",
                                    "transaction_date": txn_date_str,
                                },
                                title=f"High-Value Payment · {cust['name']}",
                                description=f"{cust['name']} · ₹{amt:,.0f}",
                                total_val=amt,
                                business_id=business_id,
                                user_id=user_id,
                                conv_id=conv_id,
                                today_str=today_str,
                                operation_id=sub_op_id,
                                payload_hash=payload_hash,
                                raw_transcript=raw_transcript,
                                language=language,
                                stt_provider=stt_provider,
                                stt_confidence=stt_confidence,
                                context_state=context_state,
                                prefix_receipts=receipts,
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
                        context_state["last_operation_kind"] = "record_customer_payment"
                        context_state["last_operation_id"] = sub_op_id
                        context_state["last_customer_id"] = str(cust["id"])
                        context_state["last_customer_name"] = cust["name"]
                        method_label = "Online" if (op.payment_method or "cash") == "upi" else (op.payment_method or "cash").title()
                        rep = (
                            f"{cust['name']} se ₹{amt:,.0f} ({method_label}) receive ho gaya aur Sales ledger mein include ho gaya. "
                            f"Remaining balance: ₹{pay['after_balance']:,.0f}."
                        )
                        replies.append(rep)
                        receipts.append(
                            {
                                "id": f"slip-{sub_op_id}",
                                "operationId": sub_op_id,
                                "kind": "payment",
                                "title": f"Payment Received · {cust['name']}",
                                "subtitle": f"Via {method_label} · Included in Sales & Revenue",
                                "transactionDate": txn_date_str,
                                "amountINR": amt,
                                "lines": [
                                    {"label": "Sales Ledger", "value": "Updated & Included", "tone": "sage"},
                                    {"label": "Remaining Balance", "value": f"₹{pay['after_balance']:,.0f}", "tone": "ochre" if pay["after_balance"] > 0 else "sage"},
                                ],
                                "status": "saved",
                                "reversible": True,
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
                pres = resolve_product_guarded(
                    op.product_query,
                    raw_transcript,
                    products,
                    aliases,
                    price_hint=op.price_hint,
                )
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
                if pres.status in {"exact", "verify_alias"} and pres.product:
                    p = pres.product
                    old_pname = str(p["name"])
                    updated_p = self.tx.update_product_settings(
                        business_id=business_id,
                        product_id=str(p["id"]),
                        new_name=op.new_name,
                        cost_price=op.cost_price,
                        selling_price=op.selling_price if op.selling_price is not None else op.unit_price,
                        low_stock_threshold=op.low_stock_threshold,
                    )
                    if op.new_name and updated_p.get("name"):
                        p["name"] = updated_p["name"]
                        rep = f"{old_pname} ka naam badal kar {updated_p['name']} kar diya gaya."
                    else:
                        rep = f"{p['name']} ki settings update ho gayi hain."
                    replies.append(rep)
                    pset_lines = []
                    if op.new_name and updated_p.get("name"):
                        pset_lines.append({"label": "Renamed", "value": f"{old_pname} → {updated_p['name']}", "tone": "sage"})
                    if op.selling_price is not None or op.unit_price is not None:
                        pset_lines.append({"label": "Selling Price", "value": f"₹{float(updated_p.get('default_selling_price') or 0):g}", "tone": "neutral"})
                    if op.cost_price is not None:
                        pset_lines.append({"label": "Cost Price", "value": f"₹{float(updated_p.get('default_cost_price') or 0):g}", "tone": "neutral"})
                    if op.low_stock_threshold is not None:
                        pset_lines.append({"label": "Low-Stock Alert", "value": f"{float(op.low_stock_threshold):g}", "tone": "neutral"})
                    receipts.append(
                        {
                            "id": f"slip-{sub_op_id}",
                            "operationId": sub_op_id,
                            "kind": "receive",
                            "title": f"Product Updated · {updated_p.get('name', p['name'])}",
                            "subtitle": "Catalog & Alias Updated",
                            "transactionDate": txn_date_str,
                            "lines": pset_lines or [{"label": "Catalog", "value": "Updated", "tone": "sage"}],
                            "status": "saved",
                        }
                    )
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
                pres = resolve_product_guarded(
                    op.product_query,
                    raw_transcript,
                    products,
                    aliases,
                    price_hint=op.price_hint,
                )
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
        self._finalize_turn(
            conv_id,
            business_id,
            today_str,
            operation_id,
            payload_hash,
            raw_transcript,
            language,
            stt_provider,
            stt_confidence,
            {"ops_count": len(operations)},
            "executed",
            "tier1",
            receipts,
            res,
            context_state,
            user_id,
            extra_response_fields={"supplier_ops": supplier_ops} if supplier_ops else None,
        )
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
        ctx.pop("pending_flow", None)
        slip, reply = self._commit_draft_now(
            draft=draft,
            business_id=business_id,
            user_id=user_id,
            operation_id=req.operation_id,
            txn_date=draft.get("transaction_date", today_str),
            product=product,
            context_state=ctx,
        )
        sup_op = slip.pop("_supplier_op", None)
        sup_ops_list = slip.pop("_supplier_ops", None) or ([sup_op] if sup_op else [])
        self.memory.update_context_state(conversation_id=conv["id"], state=ctx)
        res = VoiceTurnResult(
            operation_id=req.operation_id,
            status="executed",
            transcript="Confirmed",
            reply=reply,
            receipts=[slip],
        )
        if sup_ops_list:
            try:
                rp = res.model_dump()
                rp["supplier_ops"] = sup_ops_list
                self.db.table("voice_transactions").update(
                    {"validation_status": "executed", "response_payload": rp}
                ).eq("business_id", business_id).eq("operation_id", req.operation_id).execute()
            except Exception:
                pass
        else:
            try:
                self.db.table("voice_transactions").update({"validation_status": "executed"}).eq(
                    "business_id", business_id
                ).eq("operation_id", req.operation_id).execute()
            except Exception:
                pass
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
        extra_response_fields: dict[str, Any] | None = None,
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
        rp = result.model_dump()
        if extra_response_fields:
            rp.update(extra_response_fields)
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
            response_payload=rp,
            audit_trail=[{"action": validation_status, "timestamp": today_str}],
            user_id=user_id,
        )
        if validation_status in {"executed", "auto_executed"}:
            self.tx.increment_voice_quota(business_id=business_id)
