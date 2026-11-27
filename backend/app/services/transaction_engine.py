from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import IdempotencyConflictError, InsufficientStockError, PolicyBlockedError
from app.core.policy import SecurityPolicyEngine
from app.core.security import canonical_payload_hash


class TransactionEngine:
    """
    Deterministic, atomic ledger executor backed by Supabase PostgreSQL RPCs.
    AI NEVER invokes this directly; only validated schemas from VoicePipeline reach here.
    """

    def __init__(self, db: Any):
        self.db = db

    def check_idempotency(
        self, *, business_id: str, operation_id: str, payload_hash: str
    ) -> dict[str, Any] | None:
        res = (
            self.db.table("voice_transactions")
            .select("operation_id, payload_hash, response_payload, validation_status")
            .eq("business_id", business_id)
            .eq("operation_id", operation_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        existing = res.data[0]
        if existing["payload_hash"] != payload_hash:
            raise IdempotencyConflictError()
        return existing.get("response_payload")

    def log_voice_transaction(
        self,
        *,
        business_id: str,
        conversation_id: str | None,
        operation_id: str,
        payload_hash: str,
        transaction_date: str,
        raw_transcript: str,
        detected_language: str,
        stt_provider: str,
        stt_confidence: float | None,
        parsed_intent: dict[str, Any],
        validation_status: str,
        risk_tier: str,
        affected_records: list[dict[str, Any]],
        response_payload: dict[str, Any],
        audit_trail: list[dict[str, Any]],
        user_id: str,
    ) -> None:
        self.db.table("voice_transactions").upsert(
            {
                "business_id": business_id,
                "conversation_id": conversation_id,
                "operation_id": operation_id,
                "payload_hash": payload_hash,
                "transaction_date": transaction_date,
                "raw_transcript": raw_transcript,
                "detected_language": detected_language,
                "stt_provider": stt_provider,
                "stt_confidence": stt_confidence,
                "parsed_intent": parsed_intent,
                "validation_status": validation_status,
                "risk_tier": risk_tier,
                "affected_records": affected_records,
                "response_payload": response_payload,
                "audit_trail": audit_trail,
                "created_by": user_id,
            },
            on_conflict="business_id,operation_id",
        ).execute()

    def increment_voice_quota(self, *, business_id: str) -> None:
        sub = (
            self.db.table("business_subscriptions")
            .select("id, monthly_voice_used")
            .eq("business_id", business_id)
            .limit(1)
            .execute()
        )
        if sub.data:
            row = sub.data[0]
            self.db.table("business_subscriptions").update(
                {"monthly_voice_used": int(row["monthly_voice_used"] or 0) + 1, "updated_at": "now()"}
            ).eq("id", row["id"]).execute()

    def save_verified_alias(
        self,
        *,
        business_id: str,
        product_id: str,
        alias_text: str,
        language: str = "hinglish",
    ) -> None:
        norm = alias_text.strip().lower()
        if not norm:
            return
        self.db.table("product_aliases").upsert(
            {
                "business_id": business_id,
                "product_id": product_id,
                "alias_text": alias_text.strip(),
                "normalized_alias": norm,
                "language": language,
                "is_verified": True,
            },
            on_conflict="business_id,normalized_alias",
        ).execute()

    def create_product_and_stock(
        self,
        *,
        business_id: str,
        user_id: str,
        name: str,
        category: str,
        base_unit: str,
        cost_price: float,
        selling_price: float,
        low_stock_threshold: float,
        opening_qty: float,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        norm = " ".join(name.lower().split())
        sku = f"SKU-{operation_id[:6].upper()}"
        prod_res = (
            self.db.table("products")
            .insert(
                {
                    "business_id": business_id,
                    "sku_code": sku,
                    "name": name.strip(),
                    "normalized_name": norm,
                    "category": category or "General",
                    "base_unit": base_unit,
                    "default_cost_price": cost_price,
                    "default_selling_price": selling_price,
                    "low_stock_threshold": low_stock_threshold,
                }
            )
            .execute()
        )
        product = prod_res.data[0]
        if opening_qty > 0:
            rpc_res = self.receive_stock(
                business_id=business_id,
                user_id=user_id,
                product_id=product["id"],
                quantity=opening_qty,
                unit=base_unit,
                unit_cost=cost_price,
                transaction_date=transaction_date,
                operation_id=operation_id,
                notes="New product created & initial stock received",
            )
        else:
            self.db.table("inventory").insert(
                {"business_id": business_id, "product_id": product["id"], "current_quantity": 0}
            ).execute()
            rpc_res = {"before_qty": 0, "after_qty": 0}
        return {"product": product, "stock": rpc_res}

    def receive_stock(
        self,
        *,
        business_id: str,
        user_id: str,
        product_id: str,
        quantity: float,
        unit: str,
        unit_cost: float,
        transaction_date: str,
        operation_id: str,
        notes: str = "Voice stock receive",
    ) -> dict[str, Any]:
        res = self.db.rpc(
            "rpc_receive_stock",
            {
                "p_business_id": business_id,
                "p_user_id": user_id,
                "p_product_id": product_id,
                "p_quantity": quantity,
                "p_unit": unit,
                "p_unit_cost": unit_cost,
                "p_transaction_date": transaction_date,
                "p_operation_id": operation_id,
                "p_notes": notes,
            },
        ).execute()
        return res.data

    def deduct_damage_or_expiry(
        self,
        *,
        business_id: str,
        user_id: str,
        product_id: str,
        product_name: str,
        quantity: float,
        unit: str,
        movement_type: str,
        transaction_date: str,
        operation_id: str,
        notes: str,
    ) -> dict[str, Any]:
        try:
            res = self.db.rpc(
                "rpc_deduct_damage_or_expiry",
                {
                    "p_business_id": business_id,
                    "p_user_id": user_id,
                    "p_product_id": product_id,
                    "p_quantity": quantity,
                    "p_unit": unit,
                    "p_movement_type": movement_type,
                    "p_transaction_date": transaction_date,
                    "p_operation_id": operation_id,
                    "p_notes": notes,
                },
            ).execute()
            return res.data
        except Exception as exc:
            msg = str(exc)
            if "INSUFFICIENT_STOCK:" in msg:
                avail = float(msg.split("INSUFFICIENT_STOCK:")[1].split()[0].strip("'\""))
                raise InsufficientStockError(avail, product_name) from exc
            raise

    def record_sale(
        self,
        *,
        business_id: str,
        user_id: str,
        product_id: str,
        product_name: str,
        quantity: float,
        unit: str,
        unit_price: float,
        payment_status: str,
        paid_amount: float,
        customer_id: str | None,
        transaction_date: str,
        operation_id: str,
        notes: str = "Voice sale",
    ) -> dict[str, Any]:
        try:
            res = self.db.rpc(
                "rpc_record_sale",
                {
                    "p_business_id": business_id,
                    "p_user_id": user_id,
                    "p_product_id": product_id,
                    "p_quantity": quantity,
                    "p_unit": unit,
                    "p_unit_price": unit_price,
                    "p_payment_status": payment_status,
                    "p_paid_amount": paid_amount,
                    "p_customer_id": customer_id,
                    "p_transaction_date": transaction_date,
                    "p_operation_id": operation_id,
                    "p_notes": notes,
                },
            ).execute()
            return res.data
        except Exception as exc:
            msg = str(exc)
            if "INSUFFICIENT_STOCK:" in msg:
                avail = float(msg.split("INSUFFICIENT_STOCK:")[1].split()[0].strip("'\""))
                raise InsufficientStockError(avail, product_name) from exc
            raise

    def record_expense(
        self,
        *,
        business_id: str,
        user_id: str,
        category: str,
        description: str,
        amount: float,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        res = (
            self.db.table("expenses")
            .insert(
                {
                    "business_id": business_id,
                    "category": category,
                    "description": description,
                    "amount": amount,
                    "payment_method": payment_method,
                    "transaction_date": transaction_date,
                    "operation_id": operation_id,
                    "created_by": user_id,
                }
            )
            .execute()
        )
        return res.data[0]

    def record_customer_payment(
        self,
        *,
        business_id: str,
        user_id: str,
        customer_id: str,
        amount: float,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        res = self.db.rpc(
            "rpc_record_customer_payment",
            {
                "p_business_id": business_id,
                "p_user_id": user_id,
                "p_customer_id": customer_id,
                "p_amount": amount,
                "p_payment_method": payment_method,
                "p_transaction_date": transaction_date,
                "p_operation_id": operation_id,
                "p_notes": "Payment recorded",
            },
        ).execute()
        return res.data

    def correct_sale_quantity(
        self,
        *,
        business_id: str,
        user_id: str,
        sale_id: str,
        new_quantity: float,
        operation_id: str,
        transaction_date: str,
    ) -> dict[str, Any]:
        res = self.db.rpc(
            "rpc_correct_sale_quantity",
            {
                "p_business_id": business_id,
                "p_user_id": user_id,
                "p_sale_id": sale_id,
                "p_new_quantity": new_quantity,
                "p_operation_id": operation_id,
                "p_transaction_date": transaction_date,
            },
        ).execute()
        return res.data

    def issue_confirmation_token(
        self,
        *,
        business_id: str,
        user_id: str,
        operation_id: str,
        proposed_action: dict[str, Any],
    ) -> str:
        raw_token, token_hash = SecurityPolicyEngine.generate_confirmation_token()
        payload_hash = canonical_payload_hash(proposed_action)
        ttl = get_settings().CONFIRMATION_TOKEN_TTL_SECONDS
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()

        self.db.table("pending_confirmations").upsert(
            {
                "business_id": business_id,
                "user_id": user_id,
                "operation_id": operation_id,
                "token_hash": token_hash,
                "payload_hash": payload_hash,
                "proposed_action": proposed_action,
                "expires_at": expires_at,
                "consumed_at": None,
            },
            on_conflict="business_id,operation_id",
        ).execute()
        return raw_token

    def verify_and_consume_confirmation_token(
        self,
        *,
        business_id: str,
        user_id: str,
        operation_id: str,
        raw_token: str,
    ) -> dict[str, Any]:
        token_hash = SecurityPolicyEngine.hash_token(raw_token)
        res = (
            self.db.table("pending_confirmations")
            .select("*")
            .eq("business_id", business_id)
            .eq("user_id", user_id)
            .eq("operation_id", operation_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise PolicyBlockedError("Confirmation record not found.")

        row = res.data[0]
        if row.get("consumed_at") is not None:
            raise PolicyBlockedError("Confirmation token already consumed.")
        if row["token_hash"] != token_hash:
            raise PolicyBlockedError("Invalid confirmation token.")
        exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            raise PolicyBlockedError("Confirmation token expired. Please repeat the request.")

        self.db.table("pending_confirmations").update(
            {"consumed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", row["id"]).execute()
        return row["proposed_action"]
