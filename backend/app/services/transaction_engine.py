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

    def correct_last_expense(
        self,
        *,
        business_id: str,
        user_id: str,
        expense_id: str,
        operation_id: str,
        transaction_date: str,
        new_category: str | None = None,
        new_amount: float | None = None,
        new_payment_method: str | None = None,
        new_description: str | None = None,
    ) -> dict[str, Any]:
        old_rows = (
            self.db.table("expenses")
            .select("*")
            .eq("id", expense_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not old_rows:
            raise PolicyBlockedError("Previous expense not found to correct.")
        old = old_rows[0]
        final_cat = new_category.strip() if new_category is not None else str(old["category"])
        final_amount = float(new_amount) if new_amount is not None else float(old["amount"])
        final_method = new_payment_method or str(old["payment_method"])
        final_desc = new_description or str(old["description"])

        self.db.table("expenses").update({"status": "corrected"}).eq("id", expense_id).eq(
            "business_id", business_id
        ).execute()

        inserted = (
            self.db.table("expenses")
            .insert(
                {
                    "business_id": business_id,
                    "category": final_cat,
                    "description": final_desc,
                    "amount": final_amount,
                    "payment_method": final_method,
                    "transaction_date": transaction_date,
                    "status": "active",
                    "parent_expense_id": expense_id,
                    "operation_id": operation_id,
                    "created_by": user_id,
                }
            )
            .execute()
            .data[0]
        )
        return {
            "new_expense_id": inserted["id"],
            "old_amount": float(old["amount"]),
            "new_amount": final_amount,
            "old_method": str(old["payment_method"]),
            "new_method": final_method,
            "category": final_cat,
            "description": final_desc,
        }

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
        pay_data = dict(res.data or {})
        payment_id = pay_data.get("payment_id")

        method_tag = "ONLINE" if payment_method == "upi" else ("BANK" if payment_method == "bank" else "CASH")
        remaining = max(0.0, float(amount))
        settled_entries: list[str] = []
        prior_collected = 0.0
        same_day_settled = 0.0

        # 1. FIFO-settle this customer's active unpaid/partial sales so Sales Ledger, Revenue & Paid status stay accurate
        unpaid_sales = (
            self.db.table("sales")
            .select("id, total_amount, paid_amount, payment_status, transaction_date, notes")
            .eq("business_id", business_id)
            .eq("customer_id", customer_id)
            .eq("status", "active")
            .in_("payment_status", ["credit", "partial"])
            .order("transaction_date", desc=False)
            .order("created_at", desc=False)
            .execute()
            .data
            or []
        )
        for s in unpaid_sales:
            if remaining <= 0.009:
                break
            tot = float(s.get("total_amount") or 0)
            old_paid = float(s.get("paid_amount") or 0)
            due = max(0.0, tot - old_paid)
            if due <= 0.009:
                continue
            apply_amt = min(remaining, due)
            new_paid = round(old_paid + apply_amt, 2)
            old_status = str(s.get("payment_status") or "credit")
            new_status = "paid" if new_paid >= tot - 0.009 else "partial"

            raw_notes = str(s.get("notes") or "")
            cleaned_notes = (
                raw_notes.replace("[UDHAAR]", "")
                .replace("[CASH]", "")
                .replace("[ONLINE]", "")
                .replace("[BANK]", "")
                .strip()
            )
            new_notes = f"[{method_tag}] {cleaned_notes}".strip()
            if "Udhaar paid" not in new_notes:
                new_notes = f"{new_notes} · Udhaar paid ({transaction_date})".strip(" ·")

            self.db.table("sales").update(
                {
                    "paid_amount": new_paid,
                    "payment_status": new_status,
                    "notes": new_notes,
                }
            ).eq("id", s["id"]).eq("business_id", business_id).execute()

            remaining = round(remaining - apply_amt, 2)
            s_date = str(s.get("transaction_date") or transaction_date)
            if s_date == transaction_date:
                same_day_settled = round(same_day_settled + apply_amt, 2)
            else:
                prior_collected = round(prior_collected + apply_amt, 2)
            settled_entries.append(f"{s['id']}|{old_paid:g}|{old_status}|{apply_amt:g}|{s_date}")

        # 2. If customer paid off an Opening Balance or unbilled balance (no prior sale row), record a paid sale entry
        new_sale_created = 0.0
        if remaining > 0.01:
            self.db.table("sales").insert(
                {
                    "business_id": business_id,
                    "customer_id": customer_id,
                    "total_amount": remaining,
                    "paid_amount": remaining,
                    "payment_status": "paid",
                    "transaction_date": transaction_date,
                    "status": "active",
                    "operation_id": operation_id,
                    "notes": f"[{method_tag}] Udhaar settlement",
                    "created_by": user_id,
                }
            ).execute()
            new_sale_created = remaining

        if payment_id:
            note_parts = ["Payment recorded"]
            if prior_collected > 0:
                note_parts.append(f"[PRIOR_COLLECTED:{prior_collected:g}]")
            if settled_entries:
                note_parts.append(f"[SETTLED:{';'.join(settled_entries)}]")
            self.db.table("customer_payments").update({"notes": " ".join(note_parts)}).eq("id", payment_id).eq(
                "business_id", business_id
            ).execute()

        pay_data["settled_sales_count"] = len(settled_entries)
        pay_data["same_day_settled"] = same_day_settled
        pay_data["prior_day_collected"] = prior_collected
        pay_data["new_sale_created"] = new_sale_created
        return pay_data

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

    def correct_sale_payment(
        self,
        *,
        business_id: str,
        user_id: str,
        sale_id: str,
        operation_id: str,
        transaction_date: str,
        new_payment_method: str | None = None,
        new_payment_status: str | None = None,
    ) -> dict[str, Any]:
        old_rows = (
            self.db.table("sales")
            .select("*")
            .eq("id", sale_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not old_rows:
            raise PolicyBlockedError("Previous sale not found to correct.")
        old = old_rows[0]
        old_notes = str(old.get("notes") or "")
        if old.get("payment_status") == "credit":
            old_method_label = "Udhaar"
        elif "[ONLINE]" in old_notes or "online" in old_notes.lower():
            old_method_label = "Online"
        else:
            old_method_label = "Cash"

        final_status = "credit" if new_payment_status == "credit" else "paid"
        if final_status == "credit":
            new_method_label = "Udhaar"
            tag = "[UDHAAR]"
            paid_amt = 0.0
        elif new_payment_method == "upi":
            new_method_label = "Online"
            tag = "[ONLINE]"
            paid_amt = float(old["total_amount"])
        elif new_payment_method == "bank":
            new_method_label = "Bank"
            tag = "[BANK]"
            paid_amt = float(old["total_amount"])
        else:
            new_method_label = "Cash"
            tag = "[CASH]"
            paid_amt = float(old["total_amount"])

        # Adjust customer Udhaar if toggling between paid <-> credit
        if old.get("customer_id"):
            old_unpaid = max(0.0, float(old["total_amount"]) - float(old["paid_amount"]))
            new_unpaid = max(0.0, float(old["total_amount"]) - paid_amt)
            bal_delta = new_unpaid - old_unpaid
            if abs(bal_delta) > 0.001:
                c_rows = (
                    self.db.table("customers")
                    .select("outstanding_balance")
                    .eq("id", old["customer_id"])
                    .eq("business_id", business_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if c_rows:
                    updated_bal = max(0.0, float(c_rows[0]["outstanding_balance"]) + bal_delta)
                    self.db.table("customers").update(
                        {"outstanding_balance": updated_bal, "updated_at": "now()"}
                    ).eq("id", old["customer_id"]).eq("business_id", business_id).execute()

        self.db.table("sales").update({"status": "corrected"}).eq("id", sale_id).eq(
            "business_id", business_id
        ).execute()

        new_sale = (
            self.db.table("sales")
            .insert(
                {
                    "business_id": business_id,
                    "customer_id": old.get("customer_id"),
                    "total_amount": float(old["total_amount"]),
                    "paid_amount": paid_amt,
                    "payment_status": final_status,
                    "transaction_date": transaction_date,
                    "status": "active",
                    "parent_sale_id": sale_id,
                    "operation_id": operation_id,
                    "notes": f"{tag} Corrected payment ({old_method_label} -> {new_method_label})",
                    "created_by": user_id,
                }
            )
            .execute()
            .data[0]
        )

        # Copy sale_items to the corrected versioned sale so Revenue & Profit stay accurate
        items = (
            self.db.table("sale_items")
            .select("*")
            .eq("business_id", business_id)
            .eq("sale_id", sale_id)
            .execute()
            .data
            or []
        )
        for it in items:
            self.db.table("sale_items").insert(
                {
                    "business_id": business_id,
                    "sale_id": new_sale["id"],
                    "product_id": it["product_id"],
                    "quantity": float(it["quantity"]),
                    "unit": it["unit"],
                    "unit_price": float(it["unit_price"]),
                    "line_total": float(it["line_total"]),
                }
            ).execute()

        return {
            "new_sale_id": new_sale["id"],
            "total_amount": float(old["total_amount"]),
            "old_method": old_method_label,
            "new_method": new_method_label,
        }

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

    def create_customer(
        self,
        *,
        business_id: str,
        name: str,
        phone: str = "",
        area_note: str = "",
        opening_balance: float = 0.0,
    ) -> dict[str, Any]:
        norm = " ".join(name.lower().split())
        res = (
            self.db.table("customers")
            .insert(
                {
                    "business_id": business_id,
                    "name": name.strip(),
                    "normalized_name": norm,
                    "phone": phone.strip(),
                    "area_note": area_note.strip(),
                    "outstanding_balance": max(0.0, opening_balance),
                }
            )
            .execute()
        )
        return res.data[0]

    def update_customer(
        self,
        *,
        business_id: str,
        customer_id: str,
        name: str | None = None,
        phone: str | None = None,
        area_note: str | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {"updated_at": "now()"}
        if name is not None and name.strip():
            patch["name"] = name.strip()
            patch["normalized_name"] = " ".join(name.lower().split())
        if phone is not None:
            patch["phone"] = phone.strip()
        if area_note is not None:
            patch["area_note"] = area_note.strip()
        res = (
            self.db.table("customers")
            .update(patch)
            .eq("id", customer_id)
            .eq("business_id", business_id)
            .execute()
        )
        return res.data[0]

    def record_direct_udhaar(
        self,
        *,
        business_id: str,
        user_id: str,
        customer_id: str,
        amount: float,
        transaction_date: str,
        operation_id: str,
        notes: str = "Direct Khata udhaar",
    ) -> dict[str, Any]:
        cust = (
            self.db.table("customers")
            .select("outstanding_balance")
            .eq("id", customer_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data[0]
        )
        before_bal = float(cust["outstanding_balance"] or 0)
        after_bal = before_bal + amount
        self.db.table("customers").update(
            {"outstanding_balance": after_bal, "updated_at": "now()"}
        ).eq("id", customer_id).eq("business_id", business_id).execute()

        sale = (
            self.db.table("sales")
            .insert(
                {
                    "business_id": business_id,
                    "customer_id": customer_id,
                    "total_amount": amount,
                    "paid_amount": 0,
                    "payment_status": "credit",
                    "transaction_date": transaction_date,
                    "status": "active",
                    "operation_id": operation_id,
                    "notes": notes,
                    "created_by": user_id,
                }
            )
            .execute()
        )
        return {"sale_id": sale.data[0]["id"], "before_balance": before_bal, "after_balance": after_bal}

    def update_product_settings(
        self,
        *,
        business_id: str,
        product_id: str,
        cost_price: float | None = None,
        selling_price: float | None = None,
        low_stock_threshold: float | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {"updated_at": "now()"}
        if cost_price is not None:
            patch["default_cost_price"] = cost_price
        if selling_price is not None:
            patch["default_selling_price"] = selling_price
        if low_stock_threshold is not None:
            patch["low_stock_threshold"] = low_stock_threshold
        res = (
            self.db.table("products")
            .update(patch)
            .eq("id", product_id)
            .eq("business_id", business_id)
            .execute()
        )
        return res.data[0]

    def edit_product(
        self,
        *,
        business_id: str,
        user_id: str,
        product_id: str,
        name: str | None = None,
        category: str | None = None,
        base_unit: str | None = None,
        cost_price: float | None = None,
        selling_price: float | None = None,
        stock: float | None = None,
        low_stock_threshold: float | None = None,
        aliases: list[str] | None = None,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {"updated_at": "now()"}
        if name is not None and name.strip():
            patch["name"] = name.strip()
            patch["normalized_name"] = " ".join(name.lower().split())
        if category is not None:
            patch["category"] = category.strip() or "General"
        if base_unit is not None:
            patch["base_unit"] = base_unit
        if cost_price is not None:
            patch["default_cost_price"] = cost_price
        if selling_price is not None:
            patch["default_selling_price"] = selling_price
        if low_stock_threshold is not None:
            patch["low_stock_threshold"] = low_stock_threshold

        updated_prod = (
            self.db.table("products")
            .update(patch)
            .eq("id", product_id)
            .eq("business_id", business_id)
            .execute()
            .data[0]
        )

        if stock is not None:
            inv_rows = (
                self.db.table("inventory")
                .select("current_quantity")
                .eq("business_id", business_id)
                .eq("product_id", product_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            old_stock = float(inv_rows[0]["current_quantity"]) if inv_rows else 0.0
            delta = float(stock) - old_stock
            if abs(delta) > 0.0001:
                if inv_rows:
                    self.db.table("inventory").update(
                        {"current_quantity": float(stock), "updated_at": "now()"}
                    ).eq("business_id", business_id).eq("product_id", product_id).execute()
                else:
                    self.db.table("inventory").insert(
                        {"business_id": business_id, "product_id": product_id, "current_quantity": float(stock)}
                    ).execute()
                self.db.table("inventory_movements").insert(
                    {
                        "business_id": business_id,
                        "product_id": product_id,
                        "movement_type": "adjustment",
                        "quantity_delta": delta,
                        "unit": str(updated_prod.get("base_unit") or "piece"),
                        "operation_id": operation_id,
                        "transaction_date": transaction_date,
                        "notes": "Manual edit adjustment",
                        "created_by": user_id,
                    }
                ).execute()

        if aliases is not None:
            self.db.table("product_aliases").delete().eq("business_id", business_id).eq(
                "product_id", product_id
            ).execute()
            for al in aliases:
                if al.strip():
                    self.save_verified_alias(
                        business_id=business_id, product_id=product_id, alias_text=al.strip()
                    )

        return {"product": updated_prod}

    def archive_product(self, *, business_id: str, product_id: str) -> None:
        self.db.table("products").update({"is_active": False, "updated_at": "now()"}).eq(
            "id", product_id
        ).eq("business_id", business_id).execute()

    def archive_unused_products(self, *, business_id: str) -> int:
        prods = (
            self.db.table("products")
            .select("id")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        if not prods:
            return 0
        mv_rows = (
            self.db.table("inventory_movements")
            .select("product_id")
            .eq("business_id", business_id)
            .execute()
            .data
            or []
        )
        si_rows = (
            self.db.table("sale_items")
            .select("product_id")
            .eq("business_id", business_id)
            .execute()
            .data
            or []
        )
        used_ids = {str(r["product_id"]) for r in mv_rows if r.get("product_id")} | {
            str(r["product_id"]) for r in si_rows if r.get("product_id")
        }
        unused_ids = [str(p["id"]) for p in prods if str(p["id"]) not in used_ids]
        if not unused_ids:
            return 0
        self.db.table("products").update({"is_active": False, "updated_at": "now()"}).eq(
            "business_id", business_id
        ).in_("id", unused_ids).execute()
        return len(unused_ids)

    def reverse_operation(
        self,
        *,
        business_id: str,
        user_id: str,
        operation_id: str,
        reversal_operation_id: str,
        transaction_date: str,
    ) -> dict[str, Any]:
        reversed_parts: list[str] = []

        # 1. Reverse active sale (and unpaid Udhaar balance if credit)
        sales_rows = (
            self.db.table("sales")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", operation_id)
            .eq("status", "active")
            .execute()
            .data
            or []
        )
        for sale in sales_rows:
            self.db.table("sales").update({"status": "voided"}).eq("id", sale["id"]).eq(
                "business_id", business_id
            ).execute()
            unpaid = max(0.0, float(sale["total_amount"]) - float(sale["paid_amount"]))
            if sale.get("customer_id") and unpaid > 0:
                cust_rows = (
                    self.db.table("customers")
                    .select("outstanding_balance")
                    .eq("id", sale["customer_id"])
                    .eq("business_id", business_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if cust_rows:
                    new_bal = max(0.0, float(cust_rows[0]["outstanding_balance"]) - unpaid)
                    self.db.table("customers").update(
                        {"outstanding_balance": new_bal, "updated_at": "now()"}
                    ).eq("id", sale["customer_id"]).eq("business_id", business_id).execute()
            reversed_parts.append(f"Sale ₹{float(sale['total_amount']):,.0f}")

        # 2. Reverse active expense
        exp_rows = (
            self.db.table("expenses")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", operation_id)
            .eq("status", "active")
            .execute()
            .data
            or []
        )
        for ex in exp_rows:
            self.db.table("expenses").update({"status": "voided"}).eq("id", ex["id"]).eq(
                "business_id", business_id
            ).execute()
            reversed_parts.append(f"Expense ₹{float(ex['amount']):,.0f}")

        # 2b. Reverse active customer payment (and restore settled sales + Khata due)
        pay_rows = (
            self.db.table("customer_payments")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", operation_id)
            .eq("status", "active")
            .execute()
            .data
            or []
        )
        for py in pay_rows:
            self.db.table("customer_payments").update({"status": "voided"}).eq("id", py["id"]).eq(
                "business_id", business_id
            ).execute()
            amt = float(py.get("amount") or 0)
            if py.get("customer_id") and amt > 0:
                cust_rows = (
                    self.db.table("customers")
                    .select("outstanding_balance")
                    .eq("id", py["customer_id"])
                    .eq("business_id", business_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if cust_rows:
                    restored_bal = round(float(cust_rows[0]["outstanding_balance"] or 0) + amt, 2)
                    self.db.table("customers").update(
                        {"outstanding_balance": restored_bal, "updated_at": "now()"}
                    ).eq("id", py["customer_id"]).eq("business_id", business_id).execute()

            for tok in str(py.get("notes") or "").split():
                if tok.startswith("[SETTLED:") and tok.endswith("]"):
                    entries_str = tok[len("[SETTLED:") : -1]
                    for entry in entries_str.split(";"):
                        parts = entry.split("|")
                        if len(parts) >= 3:
                            sid, old_paid_s, old_stat = parts[0], parts[1], parts[2]
                            try:
                                self.db.table("sales").update(
                                    {"paid_amount": float(old_paid_s), "payment_status": old_stat}
                                ).eq("id", sid).eq("business_id", business_id).execute()
                            except Exception:
                                pass
            reversed_parts.append(f"Payment ₹{amt:,.0f}")

        # 3. Compensate inventory movements (append-only reversal)
        mv_rows = (
            self.db.table("inventory_movements")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", operation_id)
            .neq("movement_type", "reversal")
            .execute()
            .data
            or []
        )
        for mv in mv_rows:
            delta = float(mv["quantity_delta"])
            inv_rows = (
                self.db.table("inventory")
                .select("current_quantity")
                .eq("business_id", business_id)
                .eq("product_id", mv["product_id"])
                .limit(1)
                .execute()
                .data
                or []
            )
            if inv_rows:
                curr_qty = float(inv_rows[0]["current_quantity"])
                new_qty = max(0.0, curr_qty - delta)
                self.db.table("inventory").update(
                    {"current_quantity": new_qty, "updated_at": "now()"}
                ).eq("business_id", business_id).eq("product_id", mv["product_id"]).execute()
            self.db.table("inventory_movements").insert(
                {
                    "business_id": business_id,
                    "product_id": mv["product_id"],
                    "movement_type": "reversal",
                    "quantity_delta": -delta,
                    "unit": mv["unit"],
                    "reference_type": "reversal",
                    "reference_id": mv["id"],
                    "operation_id": reversal_operation_id,
                    "transaction_date": transaction_date,
                    "notes": f"Reversal of {operation_id[:8]}",
                    "created_by": user_id,
                }
            ).execute()
            if not sales_rows:
                reversed_parts.append(f"Stock {-delta:+g} {mv['unit']}")

        # 4. Mark voice_transactions audit status
        self.db.table("voice_transactions").update({"validation_status": "undone"}).eq(
            "business_id", business_id
        ).eq("operation_id", operation_id).execute()

        return {
            "reversed": bool(reversed_parts),
            "summary": ", ".join(reversed_parts) if reversed_parts else "No active records to reverse",
        }
