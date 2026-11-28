import uuid
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

    def _reversed_movement_ids(self, business_id: str) -> set[str]:
        rev_rows = (
            self.db.table("inventory_movements")
            .select("reference_id")
            .eq("business_id", business_id)
            .eq("movement_type", "reversal")
            .execute()
            .data
            or []
        )
        return {str(r["reference_id"]) for r in rev_rows if r.get("reference_id")}

    def _find_active_movement(
        self,
        *,
        business_id: str,
        movement_types: tuple[str, ...],
        operation_id: str | None = None,
        product_id: str | None = None,
        transaction_date: str | None = None,
    ) -> dict[str, Any] | None:
        reversed_ids = self._reversed_movement_ids(business_id)
        q = (
            self.db.table("inventory_movements")
            .select("*")
            .eq("business_id", business_id)
            .in_("movement_type", list(movement_types))
        )
        if operation_id:
            q = q.eq("operation_id", operation_id)
        if product_id:
            q = q.eq("product_id", product_id)
        if transaction_date:
            q = q.eq("transaction_date", transaction_date)
        rows = q.order("created_at", desc=True).limit(25).execute().data or []
        for row in rows:
            if str(row["id"]) not in reversed_ids:
                return row
        return None

    def find_latest_active_loss_movement(
        self,
        *,
        business_id: str,
        product_id: str | None = None,
        movement_type: str | None = None,
        transaction_date: str | None = None,
    ) -> dict[str, Any] | None:
        types = (movement_type,) if movement_type in {"damage", "expiry"} else ("damage", "expiry")
        return self._find_active_movement(
            business_id=business_id,
            movement_types=types,
            product_id=product_id,
            transaction_date=transaction_date,
        )

    def _resolve_target_movement(
        self,
        *,
        business_id: str,
        movement_types: tuple[str, ...],
        old_operation_id: str | None,
        product_id: str | None,
    ) -> dict[str, Any] | None:
        if old_operation_id:
            mv = self._find_active_movement(
                business_id=business_id,
                movement_types=movement_types,
                operation_id=old_operation_id,
                product_id=product_id,
            )
            if mv is not None:
                return mv
        return self._find_active_movement(
            business_id=business_id,
            movement_types=movement_types,
            product_id=product_id,
        )

    def _load_product_and_stock(
        self, *, business_id: str, product_id: str, fallback_unit: str | None
    ) -> tuple[str, str, float]:
        prod_rows = (
            self.db.table("products")
            .select("name, base_unit")
            .eq("id", product_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        prod_name = str(prod_rows[0]["name"]) if prod_rows else "Item"
        unit = str(fallback_unit or (prod_rows[0]["base_unit"] if prod_rows else "piece"))
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
        before_stock = float(inv_rows[0]["current_quantity"]) if inv_rows else 0.0
        return prod_name, unit, before_stock

    def _apply_movement_correction(
        self,
        *,
        business_id: str,
        user_id: str,
        mv: dict[str, Any],
        product_id: str,
        product_name: str,
        unit: str,
        before_stock: float,
        new_stock_delta: float,
        reversal_delta: float,
        new_movement_delta: float,
        new_unit_cost: float | None,
        old_unit_cost: float | None,
        operation_id: str,
        transaction_date: str,
        reversal_note: str,
        new_note: str,
    ) -> float:
        after_stock = before_stock + new_stock_delta
        if after_stock < 0:
            raise InsufficientStockError(before_stock, product_name)

        self.db.table("inventory").update(
            {"current_quantity": after_stock, "updated_at": "now()"}
        ).eq("business_id", business_id).eq("product_id", product_id).execute()

        rev_row: dict[str, Any] = {
            "business_id": business_id,
            "product_id": product_id,
            "movement_type": "reversal",
            "quantity_delta": reversal_delta,
            "unit": unit,
            "reference_type": "reversal",
            "reference_id": mv["id"],
            "operation_id": operation_id,
            "transaction_date": transaction_date,
            "notes": reversal_note,
            "created_by": user_id,
        }
        if old_unit_cost is not None:
            rev_row["unit_cost"] = old_unit_cost
        self.db.table("inventory_movements").insert(rev_row).execute()

        if abs(new_movement_delta) > 1e-6:
            new_row: dict[str, Any] = {
                "business_id": business_id,
                "product_id": product_id,
                "movement_type": str(mv["movement_type"]),
                "quantity_delta": new_movement_delta,
                "unit": unit,
                "reference_type": "voice_correction",
                "reference_id": mv["id"],
                "operation_id": operation_id,
                "transaction_date": transaction_date,
                "notes": new_note,
                "created_by": user_id,
            }
            if new_unit_cost is not None:
                new_row["unit_cost"] = new_unit_cost
            self.db.table("inventory_movements").insert(new_row).execute()

        self.db.table("voice_transactions").update({"validation_status": "corrected"}).eq(
            "business_id", business_id
        ).eq("operation_id", mv["operation_id"]).execute()
        return after_stock

    def correct_damage_or_expiry(
        self,
        *,
        business_id: str,
        user_id: str,
        new_quantity: float,
        operation_id: str,
        transaction_date: str,
        old_operation_id: str | None = None,
        product_id: str | None = None,
        movement_type: str | None = None,
    ) -> dict[str, Any]:
        """Atomically reverse prior damage/expiry movement and log the corrected count."""
        types = (movement_type,) if movement_type in {"damage", "expiry"} else ("damage", "expiry")
        mv = self._resolve_target_movement(
            business_id=business_id,
            movement_types=types,
            old_operation_id=old_operation_id,
            product_id=product_id,
        )
        if mv is None:
            raise PolicyBlockedError("Previous damage or expiry record not found to correct.")

        pid = str(mv["product_id"])
        mtype = str(mv["movement_type"])
        old_qty = abs(float(mv["quantity_delta"]))
        prod_name, unit, before_stock = self._load_product_and_stock(
            business_id=business_id, product_id=pid, fallback_unit=mv.get("unit")
        )
        if abs(float(new_quantity) - old_qty) < 1e-6:
            return {
                "product_id": pid,
                "product_name": prod_name,
                "movement_type": mtype,
                "unit": unit,
                "old_quantity": old_qty,
                "new_quantity": float(new_quantity),
                "before_stock": before_stock,
                "after_stock": before_stock,
                "stock_delta": 0.0,
                "new_operation_id": str(mv["operation_id"]),
                "unchanged": True,
            }

        stock_delta = old_qty - float(new_quantity)
        after_stock = self._apply_movement_correction(
            business_id=business_id,
            user_id=user_id,
            mv=mv,
            product_id=pid,
            product_name=prod_name,
            unit=unit,
            before_stock=before_stock,
            new_stock_delta=stock_delta,
            reversal_delta=old_qty,
            new_movement_delta=-float(new_quantity) if new_quantity > 0 else 0.0,
            new_unit_cost=None,
            old_unit_cost=None,
            operation_id=operation_id,
            transaction_date=transaction_date,
            reversal_note=f"Corrected {mtype} ({old_qty:g} -> {float(new_quantity):g})",
            new_note=f"Corrected {mtype}: {float(new_quantity):g} (was {old_qty:g})",
        )
        return {
            "product_id": pid,
            "product_name": prod_name,
            "movement_type": mtype,
            "unit": unit,
            "old_quantity": old_qty,
            "new_quantity": float(new_quantity),
            "before_stock": before_stock,
            "after_stock": after_stock,
            "stock_delta": stock_delta,
            "new_operation_id": operation_id,
            "unchanged": False,
        }

    def correct_stock_receive(
        self,
        *,
        business_id: str,
        user_id: str,
        operation_id: str,
        transaction_date: str,
        old_operation_id: str | None = None,
        product_id: str | None = None,
        new_quantity: float | None = None,
        new_unit_cost: float | None = None,
    ) -> dict[str, Any]:
        """Atomically reverse prior receive movement and log the corrected quantity/cost."""
        mv = self._resolve_target_movement(
            business_id=business_id,
            movement_types=("receive",),
            old_operation_id=old_operation_id,
            product_id=product_id,
        )
        if mv is None:
            raise PolicyBlockedError("Previous stock receive record not found to correct.")

        pid = str(mv["product_id"])
        old_qty = float(mv["quantity_delta"])
        old_cost = float(mv.get("unit_cost") or 0)
        final_qty = float(new_quantity) if new_quantity is not None else old_qty
        final_cost = float(new_unit_cost) if new_unit_cost is not None else old_cost
        prod_name, unit, before_stock = self._load_product_and_stock(
            business_id=business_id, product_id=pid, fallback_unit=mv.get("unit")
        )
        stock_delta = final_qty - old_qty
        after_stock = self._apply_movement_correction(
            business_id=business_id,
            user_id=user_id,
            mv=mv,
            product_id=pid,
            product_name=prod_name,
            unit=unit,
            before_stock=before_stock,
            new_stock_delta=stock_delta,
            reversal_delta=-old_qty,
            new_movement_delta=final_qty if final_qty > 0 else 0.0,
            new_unit_cost=final_cost,
            old_unit_cost=old_cost,
            operation_id=operation_id,
            transaction_date=transaction_date,
            reversal_note=f"Corrected receive ({old_qty:g} -> {final_qty:g})",
            new_note=f"Corrected receive: {final_qty:g} @ ₹{final_cost:g}",
        )
        return {
            "product_id": pid,
            "product_name": prod_name,
            "unit": unit,
            "old_quantity": old_qty,
            "new_quantity": final_qty,
            "old_cost": old_cost,
            "new_cost": final_cost,
            "before_stock": before_stock,
            "after_stock": after_stock,
            "stock_delta": stock_delta,
            "new_operation_id": operation_id,
        }

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
        new_paid_amount: float | None = None,
        new_payment_status: str | None = None,
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
        data = dict(res.data or {})
        # rpc_correct_sale_quantity updates the sole sale row in-place without inserting a child row;
        # keep status="active" (for new_quantity > 0) so Today/Sales Ledger/QueryEngine include the corrected revenue.
        if new_quantity > 0:
            if new_paid_amount is not None or new_payment_status is not None:
                sale_rows = (
                    self.db.table("sales")
                    .select("*")
                    .eq("id", sale_id)
                    .eq("business_id", business_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
            else:
                sale_rows = []
            if sale_rows and (new_paid_amount is not None or new_payment_status is not None):
                cur_s = sale_rows[0]
                cur_total = float(data.get("new_total") if data.get("new_total") is not None else cur_s.get("total_amount") or 0)
                cur_paid = float(cur_s.get("paid_amount") or 0)
                cur_status = str(cur_s.get("payment_status") or "paid")
                final_paid = (
                    max(0.0, min(cur_total, round(float(new_paid_amount), 2)))
                    if new_paid_amount is not None
                    else (cur_total if new_payment_status == "paid" else (0.0 if new_payment_status == "credit" else cur_paid))
                )
                final_status = (
                    "paid"
                    if final_paid >= cur_total - 0.009
                    else ("credit" if final_paid <= 0.009 else "partial")
                )
                cur_unpaid = max(0.0, round(cur_total - cur_paid, 2))
                new_unpaid = max(0.0, round(cur_total - final_paid, 2))
                bal_delta = round(new_unpaid - cur_unpaid, 2)
                if cur_s.get("customer_id") and abs(bal_delta) > 0.009:
                    c_rows = (
                        self.db.table("customers")
                        .select("outstanding_balance")
                        .eq("id", cur_s["customer_id"])
                        .eq("business_id", business_id)
                        .limit(1)
                        .execute()
                        .data
                        or []
                    )
                    if c_rows:
                        updated_bal = max(0.0, round(float(c_rows[0]["outstanding_balance"] or 0) + bal_delta, 2))
                        self.db.table("customers").update(
                            {"outstanding_balance": updated_bal, "updated_at": "now()"}
                        ).eq("id", cur_s["customer_id"]).eq("business_id", business_id).execute()
                self.db.table("sales").update(
                    {"status": "active", "paid_amount": final_paid, "payment_status": final_status}
                ).eq("id", sale_id).eq("business_id", business_id).execute()
                data["paid_amount"] = final_paid
                data["credit_amount"] = new_unpaid
                data["payment_status"] = final_status
            else:
                self.db.table("sales").update({"status": "active"}).eq("id", sale_id).eq(
                    "business_id", business_id
                ).execute()
        return data

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

    def correct_sale_amount(
        self,
        *,
        business_id: str,
        user_id: str,
        sale_id: str,
        new_total_amount: float,
        operation_id: str,
        transaction_date: str,
    ) -> dict[str, Any]:
        """Version-correct total rupee amount on an active single-item or combined sale without altering stock."""
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
            raise PolicyBlockedError("Previous sale not found to update amount.")
        old = old_rows[0]
        old_total = float(old.get("total_amount") or 0)
        old_paid = float(old.get("paid_amount") or 0)
        old_status = str(old.get("payment_status") or "paid")
        old_notes = str(old.get("notes") or "")
        final_total = max(0.0, round(float(new_total_amount), 2))

        if old_status == "credit":
            new_paid = 0.0
            new_status = "credit"
        elif old_status == "partial":
            new_paid = min(old_paid, final_total)
            new_status = "paid" if new_paid >= final_total - 0.009 else ("credit" if new_paid <= 0.009 else "partial")
        else:
            new_paid = final_total
            new_status = "paid"

        old_unpaid = max(0.0, old_total - old_paid)
        new_unpaid = max(0.0, final_total - new_paid)
        bal_delta = new_unpaid - old_unpaid
        if old.get("customer_id") and abs(bal_delta) > 0.009:
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
                updated_bal = max(0.0, round(float(c_rows[0]["outstanding_balance"] or 0) + bal_delta, 2))
                self.db.table("customers").update(
                    {"outstanding_balance": updated_bal, "updated_at": "now()"}
                ).eq("id", old["customer_id"]).eq("business_id", business_id).execute()

        tag = (
            "[UDHAAR]"
            if new_status == "credit"
            else ("[ONLINE]" if "[ONLINE]" in old_notes.upper() else ("[BANK]" if "[BANK]" in old_notes.upper() else "[CASH]"))
        )
        self.db.table("sales").update({"status": "corrected"}).eq("id", sale_id).eq(
            "business_id", business_id
        ).execute()

        new_sale = (
            self.db.table("sales")
            .insert(
                {
                    "business_id": business_id,
                    "customer_id": old.get("customer_id"),
                    "total_amount": final_total,
                    "paid_amount": new_paid,
                    "payment_status": new_status,
                    "transaction_date": transaction_date,
                    "status": "active",
                    "parent_sale_id": sale_id,
                    "operation_id": operation_id,
                    "notes": f"{tag} Corrected bill amount (₹{old_total:g} -> ₹{final_total:g})",
                    "created_by": user_id,
                }
            )
            .execute()
            .data[0]
        )

        items = (
            self.db.table("sale_items")
            .select("*")
            .eq("business_id", business_id)
            .eq("sale_id", sale_id)
            .execute()
            .data
            or []
        )
        if items:
            raw_sum = sum(float(it.get("line_total") or 0) for it in items)
            running = 0.0
            for idx, it in enumerate(items):
                qty_val = float(it.get("quantity") or 1)
                if idx == len(items) - 1:
                    alloc = max(0.0, round(final_total - running, 2))
                elif raw_sum > 0:
                    alloc = round((float(it.get("line_total") or 0) / raw_sum) * final_total, 2)
                    running = round(running + alloc, 2)
                else:
                    alloc = round(final_total / len(items), 2)
                    running = round(running + alloc, 2)
                eff_unit = round(alloc / qty_val, 2) if qty_val > 0 else float(it.get("unit_price") or 0)
                self.db.table("sale_items").insert(
                    {
                        "business_id": business_id,
                        "sale_id": new_sale["id"],
                        "product_id": it["product_id"],
                        "quantity": qty_val,
                        "unit": it["unit"],
                        "unit_price": eff_unit,
                        "line_total": alloc,
                    }
                ).execute()

        return {
            "new_sale_id": new_sale["id"],
            "old_total": old_total,
            "new_total": final_total,
            "paid_amount": new_paid,
            "payment_status": new_status,
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
        new_name: str | None = None,
        cost_price: float | None = None,
        selling_price: float | None = None,
        low_stock_threshold: float | None = None,
    ) -> dict[str, Any]:
        old_name: str | None = None
        patch: dict[str, Any] = {"updated_at": "now()"}
        if new_name is not None and new_name.strip():
            clean_new = new_name.strip()
            existing = (
                self.db.table("products")
                .select("name")
                .eq("id", product_id)
                .eq("business_id", business_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if existing:
                old_name = str(existing[0].get("name") or "")
            patch["name"] = clean_new
            patch["normalized_name"] = " ".join(clean_new.lower().split())
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
        updated = dict(res.data[0])
        if old_name and new_name and " ".join(old_name.lower().split()) != " ".join(new_name.lower().split()):
            try:
                self.save_verified_alias(
                    business_id=business_id,
                    product_id=product_id,
                    alias_text=old_name,
                )
            except Exception:
                pass
        if old_name is not None:
            updated["_old_name"] = old_name
        return updated

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
        reversed_ids = self._reversed_movement_ids(business_id)
        restored_sale_product_ids: set[str] = set()

        # 1. Reverse active sale (restore exact active sale_items qty to inventory + adjust Udhaar balance)
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

            # Restore inventory for every item on the active sale (handles both direct & payment/qty-corrected sales)
            s_items = (
                self.db.table("sale_items")
                .select("*")
                .eq("business_id", business_id)
                .eq("sale_id", sale["id"])
                .execute()
                .data
                or []
            )
            # Find any active unreversed sale movement linked via operation_id or parent_sale_id chain
            orig_sale_mvs = (
                self.db.table("inventory_movements")
                .select("*")
                .eq("business_id", business_id)
                .eq("movement_type", "sale")
                .eq("operation_id", operation_id)
                .execute()
                .data
                or []
            )
            if not orig_sale_mvs and sale.get("parent_sale_id"):
                orig_sale_mvs = (
                    self.db.table("inventory_movements")
                    .select("*")
                    .eq("business_id", business_id)
                    .eq("movement_type", "sale")
                    .eq("reference_id", sale["parent_sale_id"])
                    .execute()
                    .data
                    or []
                )

            for item in s_items:
                pid = str(item["product_id"])
                qty_to_restore = float(item["quantity"] or 0)
                if qty_to_restore <= 0:
                    continue
                inv_rows = (
                    self.db.table("inventory")
                    .select("current_quantity")
                    .eq("business_id", business_id)
                    .eq("product_id", pid)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                if inv_rows:
                    curr_qty = float(inv_rows[0]["current_quantity"])
                    self.db.table("inventory").update(
                        {"current_quantity": curr_qty + qty_to_restore, "updated_at": "now()"}
                    ).eq("business_id", business_id).eq("product_id", pid).execute()

                matched_mv = next(
                    (m for m in orig_sale_mvs if str(m["product_id"]) == pid and str(m["id"]) not in reversed_ids),
                    None,
                )
                self.db.table("inventory_movements").insert(
                    {
                        "business_id": business_id,
                        "product_id": pid,
                        "movement_type": "reversal",
                        "quantity_delta": qty_to_restore,
                        "unit": item.get("unit") or "piece",
                        "reference_type": "reversal",
                        "reference_id": matched_mv["id"] if matched_mv else sale["id"],
                        "operation_id": reversal_operation_id,
                        "transaction_date": transaction_date,
                        "notes": f"Reversal of {operation_id[:8]}",
                        "created_by": user_id,
                    }
                ).execute()
                if matched_mv:
                    reversed_ids.add(str(matched_mv["id"]))
                restored_sale_product_ids.add(pid)

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
            if str(mv["id"]) in reversed_ids or str(mv["product_id"]) in restored_sale_product_ids:
                continue
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
            reversed_ids.add(str(mv["id"]))
            # Restore customer balance if this was a customer return credited against Khata
            mv_notes = str(mv.get("notes") or "")
            for tok in mv_notes.split():
                if tok.startswith("[RETURN_UDHAAR:") and tok.endswith("]"):
                    parts = tok[len("[RETURN_UDHAAR:") : -1].split("|")
                    if len(parts) >= 2:
                        ret_cid, ret_amt_s = parts[0], parts[1]
                        try:
                            ret_amt = float(ret_amt_s)
                            c_rows = (
                                self.db.table("customers")
                                .select("outstanding_balance")
                                .eq("id", ret_cid)
                                .eq("business_id", business_id)
                                .limit(1)
                                .execute()
                                .data
                                or []
                            )
                            if c_rows and ret_amt > 0:
                                self.db.table("customers").update(
                                    {
                                        "outstanding_balance": round(float(c_rows[0]["outstanding_balance"] or 0) + ret_amt, 2),
                                        "updated_at": "now()",
                                    }
                                ).eq("id", ret_cid).eq("business_id", business_id).execute()
                                reversed_parts.append(f"Return Udhaar ₹{ret_amt:,.0f}")
                        except Exception:
                            pass
                elif tok.startswith("[RETURN_SALE:") and tok.endswith("]"):
                    parts = tok[len("[RETURN_SALE:") : -1].split("|")
                    if len(parts) >= 2:
                        old_sid, new_sid = parts[0], parts[1]
                        try:
                            self.db.table("sales").update({"status": "active"}).eq("id", old_sid).eq(
                                "business_id", business_id
                            ).execute()
                            if new_sid and new_sid != "VOIDED":
                                self.db.table("sales").update({"status": "voided"}).eq("id", new_sid).eq(
                                    "business_id", business_id
                                ).execute()
                            if len(parts) >= 4 and parts[2]:
                                rc_id, rc_delta = parts[2], float(parts[3])
                                c_rows = (
                                    self.db.table("customers")
                                    .select("outstanding_balance")
                                    .eq("id", rc_id)
                                    .eq("business_id", business_id)
                                    .limit(1)
                                    .execute()
                                    .data
                                    or []
                                )
                                if c_rows and abs(rc_delta) > 0.009:
                                    self.db.table("customers").update(
                                        {
                                            "outstanding_balance": max(0.0, round(float(c_rows[0]["outstanding_balance"] or 0) + rc_delta, 2)),
                                            "updated_at": "now()",
                                        }
                                    ).eq("id", rc_id).eq("business_id", business_id).execute()
                            reversed_parts.append("Sale Return Reverted")
                        except Exception:
                            pass
            if not sales_rows:
                reversed_parts.append(f"Stock {-delta:+g} {mv['unit']}")

        # 3b. Reverse any logged supplier credit / supplier payment balance deltas
        try:
            vt_rows = (
                self.db.table("voice_transactions")
                .select("response_payload, validation_status")
                .eq("business_id", business_id)
                .eq("operation_id", operation_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if vt_rows and vt_rows[0].get("validation_status") != "undone":
                rp = vt_rows[0].get("response_payload") or {}
                for sop in (rp.get("supplier_ops") or []):
                    sid = str(sop.get("supplier_id") or "")
                    samt = float(sop.get("amount") or 0)
                    stype = str(sop.get("type") or "")
                    if not sid or samt <= 0:
                        continue
                    s_rows = (
                        self.db.table("customers")
                        .select("outstanding_balance")
                        .eq("id", sid)
                        .eq("business_id", business_id)
                        .limit(1)
                        .execute()
                        .data
                        or []
                    )
                    if s_rows:
                        cur_bal = float(s_rows[0]["outstanding_balance"] or 0)
                        new_bal = (
                            max(0.0, round(cur_bal - samt, 2))
                            if stype == "credit"
                            else round(cur_bal + samt, 2)
                        )
                        self.db.table("customers").update(
                            {"outstanding_balance": new_bal, "updated_at": "now()"}
                        ).eq("id", sid).eq("business_id", business_id).execute()
                        reversed_parts.append(f"Supplier Payable ₹{samt:,.0f}")
        except Exception:
            pass

        # 4. Mark voice_transactions & persisted receipt card status as undone
        self.db.table("voice_transactions").update({"validation_status": "undone"}).eq(
            "business_id", business_id
        ).eq("operation_id", operation_id).execute()
        try:
            msg_rows = (
                self.db.table("conversation_messages")
                .select("id, ui_payload")
                .eq("business_id", business_id)
                .eq("linked_operation_id", operation_id)
                .eq("role", "assistant")
                .execute()
                .data
                or []
            )
            for mr in msg_rows:
                payload = mr.get("ui_payload")
                if isinstance(payload, dict) and isinstance(payload.get("receipts"), list):
                    changed = False
                    for r in payload["receipts"]:
                        if isinstance(r, dict) and str(r.get("operationId") or "") == str(operation_id):
                            r["status"] = "undone"
                            r["reversible"] = False
                            changed = True
                    if changed:
                        self.db.table("conversation_messages").update({"ui_payload": payload}).eq(
                            "id", mr["id"]
                        ).execute()
        except Exception:
            pass

        return {
            "reversed": bool(reversed_parts),
            "summary": ", ".join(reversed_parts) if reversed_parts else "No active records to reverse",
        }

    # ── New Feature Ledger Methods ───────────────────────────────────────────

    SUPPLIER_TAG = "[SUPPLIER]"

    def find_or_create_supplier(
        self,
        *,
        business_id: str,
        name: str,
        phone: str = "",
        area_note: str = "",
    ) -> tuple[dict[str, Any], bool]:
        """Find existing [SUPPLIER]-tagged account or create a wholesale supplier Khata row."""
        clean_name = name.strip()
        norm = " ".join(clean_name.lower().split())
        rows = (
            self.db.table("customers")
            .select("*")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        for r in rows:
            note = str(r.get("area_note") or "")
            if self.SUPPLIER_TAG in note.upper() and str(r.get("normalized_name") or "") == norm:
                return r, False
        for r in rows:
            note = str(r.get("area_note") or "")
            if self.SUPPLIER_TAG in note.upper():
                rn = str(r.get("normalized_name") or "")
                if norm in rn or rn in norm:
                    return r, False
        tagged_note = f"{self.SUPPLIER_TAG} {area_note.strip()}".strip()
        created = (
            self.db.table("customers")
            .insert(
                {
                    "business_id": business_id,
                    "name": clean_name,
                    "normalized_name": norm,
                    "phone": phone.strip(),
                    "area_note": tagged_note,
                    "outstanding_balance": 0.0,
                    "is_active": True,
                }
            )
            .execute()
            .data[0]
        )
        return created, True

    def record_supplier_credit(
        self,
        *,
        business_id: str,
        supplier_id: str,
        amount: float,
    ) -> dict[str, Any]:
        """Increase supplier wholesale payable balance (money owed to supplier)."""
        rows = (
            self.db.table("customers")
            .select("outstanding_balance")
            .eq("id", supplier_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        before_bal = float(rows[0]["outstanding_balance"] or 0) if rows else 0.0
        after_bal = round(before_bal + float(amount), 2)
        self.db.table("customers").update(
            {"outstanding_balance": after_bal, "updated_at": "now()"}
        ).eq("id", supplier_id).eq("business_id", business_id).execute()
        return {"before_balance": before_bal, "after_balance": after_bal}

    def record_supplier_payment(
        self,
        *,
        business_id: str,
        user_id: str,
        supplier_id: str,
        supplier_name: str,
        amount: float,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Record cash/online/bank payment to a wholesale supplier, reducing payable balance."""
        rows = (
            self.db.table("customers")
            .select("outstanding_balance")
            .eq("id", supplier_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        before_bal = float(rows[0]["outstanding_balance"] or 0) if rows else 0.0
        after_bal = max(0.0, round(before_bal - float(amount), 2))
        self.db.table("customers").update(
            {"outstanding_balance": after_bal, "updated_at": "now()"}
        ).eq("id", supplier_id).eq("business_id", business_id).execute()
        exp = self.record_expense(
            business_id=business_id,
            user_id=user_id,
            category="Supplier Payment",
            description=f"Paid supplier {supplier_name}",
            amount=float(amount),
            payment_method=payment_method if payment_method in ("cash", "upi", "bank") else "cash",
            transaction_date=transaction_date,
            operation_id=operation_id,
        )
        return {
            "before_balance": before_bal,
            "after_balance": after_bal,
            "expense_id": exp.get("id"),
        }

    def settle_all_suppliers(
        self,
        *,
        business_id: str,
        user_id: str,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
        supplier_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Settle active [SUPPLIER] payables (all pending or specific supplier_ids) with outstanding_balance > 0."""
        rows = (
            self.db.table("customers")
            .select("*")
            .eq("business_id", business_id)
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        id_filter = {str(s) for s in supplier_ids} if supplier_ids else None
        due_sups = [
            r for r in rows
            if self.SUPPLIER_TAG in str(r.get("area_note") or "").upper()
            and float(r.get("outstanding_balance") or 0) > 0.009
            and (id_filter is None or str(r["id"]) in id_filter)
        ]
        settled: list[dict[str, Any]] = []
        supplier_ops: list[dict[str, Any]] = []
        total_paid = 0.0
        for r in due_sups:
            bal = round(float(r.get("outstanding_balance") or 0), 2)
            self.record_supplier_payment(
                business_id=business_id,
                user_id=user_id,
                supplier_id=str(r["id"]),
                supplier_name=str(r["name"]),
                amount=bal,
                payment_method=payment_method,
                transaction_date=transaction_date,
                operation_id=operation_id,
            )
            settled.append({"supplier_id": str(r["id"]), "name": str(r["name"]), "paid_amount": bal})
            supplier_ops.append({"type": "payment", "supplier_id": str(r["id"]), "amount": bal})
            total_paid = round(total_paid + bal, 2)
        return {
            "settled_count": len(settled),
            "total_paid": total_paid,
            "settled_suppliers": settled,
            "supplier_ops": supplier_ops,
        }

    def record_customer_return(
        self,
        *,
        business_id: str,
        user_id: str,
        product_id: str,
        product_name: str,
        quantity: float,
        unit: str,
        refund_amount: float,
        refund_method: str,
        customer_id: str | None,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Restore returned stock to inventory and update matching active sale (or log return refund/Khata)."""
        _, _, before_stock = self._load_product_and_stock(
            business_id=business_id, product_id=product_id, fallback_unit=unit
        )
        after_stock = round(before_stock + float(quantity), 4)
        self.db.table("inventory").update(
            {"current_quantity": after_stock, "updated_at": "now()"}
        ).eq("business_id", business_id).eq("product_id", product_id).execute()

        refund_val = max(0.0, round(float(refund_amount), 2))
        credit_reduced = 0.0
        cash_refund = 0.0
        after_balance: float | None = None
        return_sale_tag = ""
        adjusted_sale = False

        # 1. Try matching an active sale containing this product so Sales, Revenue, Profit & TODAY update immediately
        try:
            si_rows = (
                self.db.table("sale_items")
                .select("*")
                .eq("business_id", business_id)
                .eq("product_id", product_id)
                .execute()
                .data
                or []
            )
            if si_rows:
                sale_ids = list({str(si["sale_id"]) for si in si_rows if si.get("sale_id")})
                active_sales = (
                    self.db.table("sales")
                    .select("*")
                    .eq("business_id", business_id)
                    .eq("status", "active")
                    .in_("id", sale_ids)
                    .order("created_at", desc=True)
                    .execute()
                    .data
                    or []
                )
                # Prefer customer match, exact total/item match, same day, then most recent sale
                si_by_sale = {str(si["sale_id"]): si for si in si_rows if si.get("sale_id")}
                matched_sale = None
                if active_sales:
                    def _score_sale(s: dict[str, Any]) -> tuple[int, int, int, int]:
                        cust_m = 1 if (customer_id and str(s.get("customer_id") or "") == str(customer_id)) else 0
                        tot_m = 1 if (refund_val > 0 and abs(float(s.get("total_amount") or 0) - refund_val) < 0.01) else 0
                        si = si_by_sale.get(str(s["id"]))
                        qty_m = 1 if (si and float(si.get("quantity") or 0) >= float(quantity) - 1e-6) else 0
                        day_m = 1 if str(s.get("transaction_date") or "") == transaction_date else 0
                        return (cust_m, tot_m, qty_m, day_m)

                    matched_sale = max(active_sales, key=_score_sale)

                if matched_sale:
                    all_s_items = (
                        self.db.table("sale_items")
                        .select("*")
                        .eq("business_id", business_id)
                        .eq("sale_id", matched_sale["id"])
                        .execute()
                        .data
                        or []
                    )
                    target_si = next((x for x in all_s_items if str(x.get("product_id")) == str(product_id)), None)
                    item_qty = float(target_si.get("quantity") or 0) if target_si else 0.0
                    old_total = float(matched_sale.get("total_amount") or 0)
                    old_paid = float(matched_sale.get("paid_amount") or 0)
                    old_unpaid = max(0.0, round(old_total - old_paid, 2))
                    deduct_from_sale = round(min(refund_val if refund_val > 0 else old_total, old_total), 2)
                    new_total = max(0.0, round(old_total - deduct_from_sale, 2))

                    sale_cust_id = str(matched_sale.get("customer_id") or customer_id or "") or None
                    rem_item_qty = round(item_qty - float(quantity), 4)
                    other_items = [x for x in all_s_items if target_si is None or str(x.get("id") or id(x)) != str(target_si.get("id") or id(target_si))]

                    if new_total <= 0.009 or (rem_item_qty <= 1e-6 and not other_items):
                        # Full return of this sale -> void the sale cleanly
                        self.db.table("sales").update({"status": "voided"}).eq("id", matched_sale["id"]).eq(
                            "business_id", business_id
                        ).execute()
                        bal_restore_on_rev = 0.0
                        if sale_cust_id and old_unpaid > 0:
                            c_rows = (
                                self.db.table("customers")
                                .select("outstanding_balance")
                                .eq("id", sale_cust_id)
                                .eq("business_id", business_id)
                                .limit(1)
                                .execute()
                                .data
                                or []
                            )
                            if c_rows:
                                cur_bal = float(c_rows[0]["outstanding_balance"] or 0)
                                red = round(min(cur_bal, old_unpaid), 2)
                                after_balance = max(0.0, round(cur_bal - red, 2))
                                credit_reduced = red
                                bal_restore_on_rev = red
                                self.db.table("customers").update(
                                    {"outstanding_balance": after_balance, "updated_at": "now()"}
                                ).eq("id", sale_cust_id).eq("business_id", business_id).execute()
                        return_sale_tag = f"[RETURN_SALE:{matched_sale['id']}|VOIDED|{sale_cust_id or ''}|{bal_restore_on_rev:g}]"
                        adjusted_sale = True
                    else:
                        # Partial return -> version-correct sale with reduced total & remaining items
                        if refund_method == "credit":
                            new_paid = min(old_paid, new_total)
                        else:
                            new_paid = max(0.0, round(old_paid - deduct_from_sale, 2))
                        new_status = "paid" if new_paid >= new_total - 0.009 else ("credit" if new_paid <= 0.009 else "partial")
                        new_unpaid = max(0.0, round(new_total - new_paid, 2))
                        bal_delta = round(new_unpaid - old_unpaid, 2)
                        if sale_cust_id and abs(bal_delta) > 0.009:
                            c_rows = (
                                self.db.table("customers")
                                .select("outstanding_balance")
                                .eq("id", sale_cust_id)
                                .eq("business_id", business_id)
                                .limit(1)
                                .execute()
                                .data
                                or []
                            )
                            if c_rows:
                                cur_bal = float(c_rows[0]["outstanding_balance"] or 0)
                                after_balance = max(0.0, round(cur_bal + bal_delta, 2))
                                if bal_delta < 0:
                                    credit_reduced = round(-bal_delta, 2)
                                self.db.table("customers").update(
                                    {"outstanding_balance": after_balance, "updated_at": "now()"}
                                ).eq("id", sale_cust_id).eq("business_id", business_id).execute()

                        old_notes = str(matched_sale.get("notes") or "")
                        tag = "[UDHAAR]" if new_status == "credit" else ("[ONLINE]" if "[ONLINE]" in old_notes.upper() else ("[BANK]" if "[BANK]" in old_notes.upper() else "[CASH]"))
                        self.db.table("sales").update({"status": "corrected"}).eq("id", matched_sale["id"]).eq(
                            "business_id", business_id
                        ).execute()
                        new_sale = (
                            self.db.table("sales")
                            .insert(
                                {
                                    "business_id": business_id,
                                    "customer_id": matched_sale.get("customer_id"),
                                    "total_amount": new_total,
                                    "paid_amount": new_paid,
                                    "payment_status": new_status,
                                    "transaction_date": str(matched_sale.get("transaction_date") or transaction_date),
                                    "status": "active",
                                    "parent_sale_id": matched_sale["id"],
                                    "operation_id": str(matched_sale.get("operation_id") or operation_id),
                                    "notes": f"{tag} Partial return (-{quantity:g} {product_name})",
                                    "created_by": user_id,
                                }
                            )
                            .execute()
                            .data[0]
                        )
                        for oi in other_items:
                            self.db.table("sale_items").insert(
                                {
                                    "business_id": business_id,
                                    "sale_id": new_sale["id"],
                                    "product_id": oi["product_id"],
                                    "quantity": float(oi["quantity"]),
                                    "unit": oi["unit"],
                                    "unit_price": float(oi["unit_price"]),
                                    "line_total": float(oi["line_total"]),
                                }
                            ).execute()
                        if target_si and rem_item_qty > 1e-6:
                            rem_line = max(0.0, round(float(target_si.get("line_total") or 0) - deduct_from_sale, 2))
                            rem_unit_price = round(rem_line / rem_item_qty, 2) if rem_item_qty > 0 else float(target_si.get("unit_price") or 0)
                            self.db.table("sale_items").insert(
                                {
                                    "business_id": business_id,
                                    "sale_id": new_sale["id"],
                                    "product_id": target_si["product_id"],
                                    "quantity": rem_item_qty,
                                    "unit": target_si["unit"],
                                    "unit_price": rem_unit_price,
                                    "line_total": rem_line,
                                }
                            ).execute()
                        return_sale_tag = f"[RETURN_SALE:{matched_sale['id']}|{new_sale['id']}|{sale_cust_id or ''}|{-bal_delta:g}]"
                        adjusted_sale = True

                    cash_refund = max(0.0, round(refund_val - deduct_from_sale, 2))
        except Exception:
            adjusted_sale = False

        if not adjusted_sale:
            if customer_id and refund_method == "credit" and refund_val > 0:
                c_rows = (
                    self.db.table("customers")
                    .select("outstanding_balance")
                    .eq("id", customer_id)
                    .eq("business_id", business_id)
                    .limit(1)
                    .execute()
                    .data
                    or []
                )
                cur_bal = float(c_rows[0]["outstanding_balance"] or 0) if c_rows else 0.0
                credit_reduced = round(min(refund_val, cur_bal), 2)
                after_balance = max(0.0, round(cur_bal - credit_reduced, 2))
                if credit_reduced > 0:
                    self.db.table("customers").update(
                        {"outstanding_balance": after_balance, "updated_at": "now()"}
                    ).eq("id", customer_id).eq("business_id", business_id).execute()
                cash_refund = max(0.0, round(refund_val - credit_reduced, 2))
            else:
                cash_refund = refund_val

        note_parts = [f"Customer return: {quantity:g} {unit} {product_name}"]
        if return_sale_tag:
            note_parts.append(return_sale_tag)
        if not adjusted_sale and customer_id and credit_reduced > 0:
            note_parts.append(f"[RETURN_UDHAAR:{customer_id}|{credit_reduced:g}]")
        self.db.table("inventory_movements").insert(
            {
                "business_id": business_id,
                "product_id": product_id,
                "movement_type": "adjustment",
                "quantity_delta": float(quantity),
                "unit": unit,
                "reference_type": "customer_return",
                "operation_id": operation_id,
                "transaction_date": transaction_date,
                "notes": " ".join(note_parts),
                "created_by": user_id,
            }
        ).execute()

        if cash_refund > 0:
            pay_m = refund_method if refund_method in ("cash", "upi", "bank") else "cash"
            self.record_expense(
                business_id=business_id,
                user_id=user_id,
                category="Customer Return",
                description=f"Return refund: {quantity:g} {unit} {product_name}",
                amount=cash_refund,
                payment_method=pay_m,
                transaction_date=transaction_date,
                operation_id=operation_id,
            )

        return {
            "before_stock": before_stock,
            "after_stock": after_stock,
            "refund_amount": refund_val,
            "refund_method": refund_method,
            "credit_reduced": credit_reduced,
            "cash_refund": cash_refund,
            "after_balance": after_balance,
            "sale_adjusted": adjusted_sale,
        }

    def record_split_customer_sale(
        self,
        *,
        business_id: str,
        user_id: str,
        customer_id: str,
        total_amount: float,
        paid_amount: float,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
        notes: str = "Split payment sale",
    ) -> dict[str, Any]:
        """Record an un-itemized customer sale split between immediate paid cash/UPI and Khata Udhaar."""
        total_val = max(0.0, round(float(total_amount), 2))
        paid_val = max(0.0, min(total_val, round(float(paid_amount), 2)))
        credit_val = max(0.0, round(total_val - paid_val, 2))
        status_val = "paid" if credit_val <= 0.009 else ("credit" if paid_val <= 0.009 else "partial")
        tag = "[ONLINE]" if payment_method == "upi" else ("[BANK]" if payment_method == "bank" else "[CASH]")
        if status_val == "partial":
            full_notes = f"{tag} Split ₹{paid_val:g} paid + ₹{credit_val:g} udhaar".strip()
        elif status_val == "credit":
            full_notes = f"[UDHAAR] {notes}".strip()
        else:
            full_notes = f"{tag} {notes}".strip()

        c_rows = (
            self.db.table("customers")
            .select("outstanding_balance")
            .eq("id", customer_id)
            .eq("business_id", business_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        before_bal = float(c_rows[0]["outstanding_balance"] or 0) if c_rows else 0.0
        after_bal = round(before_bal + credit_val, 2)
        if credit_val > 0:
            self.db.table("customers").update(
                {"outstanding_balance": after_bal, "updated_at": "now()"}
            ).eq("id", customer_id).eq("business_id", business_id).execute()

        sale = (
            self.db.table("sales")
            .insert(
                {
                    "business_id": business_id,
                    "customer_id": customer_id,
                    "total_amount": total_val,
                    "paid_amount": paid_val,
                    "payment_status": status_val,
                    "transaction_date": transaction_date,
                    "status": "active",
                    "operation_id": operation_id,
                    "notes": full_notes,
                    "created_by": user_id,
                }
            )
            .execute()
            .data[0]
        )
        return {
            "sale_id": sale["id"],
            "total_amount": total_val,
            "paid_amount": paid_val,
            "credit_amount": credit_val,
            "payment_status": status_val,
            "before_balance": before_bal,
            "after_balance": after_bal,
        }

    def record_combined_bill(
        self,
        *,
        business_id: str,
        user_id: str,
        items: list[dict[str, Any]],
        customer_id: str | None,
        bill_total_amount: float | None,
        paid_amount: float | None,
        payment_status: str,
        payment_method: str,
        transaction_date: str,
        operation_id: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """Atomically record a grouped multi-item bill with optional lump-sum discount and split payment."""
        if not items:
            raise PolicyBlockedError("No items specified for combined bill.")

        # 1. Pre-validate stock across all line items (summing duplicate product_ids)
        req_qty_by_pid: dict[str, float] = {}
        name_by_pid: dict[str, str] = {}
        for it in items:
            pid = str(it["product_id"])
            req_qty_by_pid[pid] = req_qty_by_pid.get(pid, 0.0) + float(it["quantity"])
            name_by_pid[pid] = str(it["product_name"])

        stock_by_pid: dict[str, float] = {}
        for pid, needed in req_qty_by_pid.items():
            _, _, avail = self._load_product_and_stock(
                business_id=business_id, product_id=pid, fallback_unit="piece"
            )
            if avail < needed - 1e-6:
                raise InsufficientStockError(avail, name_by_pid[pid])
            stock_by_pid[pid] = avail

        # 2. Compute line totals and allocate optional lump-sum bill total proportionally
        raw_lines = [round(float(it["quantity"]) * float(it["unit_price"]), 2) for it in items]
        catalog_total = round(sum(raw_lines), 2)
        final_total = (
            round(float(bill_total_amount), 2)
            if bill_total_amount is not None and float(bill_total_amount) >= 0
            else catalog_total
        )

        allocated_lines: list[float] = []
        if len(items) == 1:
            allocated_lines = [final_total]
        elif catalog_total > 0:
            running = 0.0
            for idx, rl in enumerate(raw_lines):
                if idx == len(raw_lines) - 1:
                    allocated_lines.append(max(0.0, round(final_total - running, 2)))
                else:
                    share = round((rl / catalog_total) * final_total, 2)
                    allocated_lines.append(share)
                    running = round(running + share, 2)
        else:
            even = round(final_total / len(items), 2)
            allocated_lines = [even] * (len(items) - 1) + [max(0.0, round(final_total - even * (len(items) - 1), 2))]

        if paid_amount is not None:
            final_paid = max(0.0, min(final_total, round(float(paid_amount), 2)))
        elif payment_status == "credit":
            final_paid = 0.0
        else:
            final_paid = final_total

        credit_val = max(0.0, round(final_total - final_paid, 2))
        final_status = "paid" if credit_val <= 0.009 else ("credit" if final_paid <= 0.009 else "partial")
        tag = "[UDHAAR]" if final_status == "credit" else (
            "[ONLINE]" if payment_method == "upi" else ("[BANK]" if payment_method == "bank" else "[CASH]")
        )
        full_notes = f"{tag} {notes or 'Combined multi-item bill'}".strip()

        # 3. Update customer balance if credit component exists
        before_bal = 0.0
        after_bal = 0.0
        if customer_id:
            c_rows = (
                self.db.table("customers")
                .select("outstanding_balance")
                .eq("id", customer_id)
                .eq("business_id", business_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            before_bal = float(c_rows[0]["outstanding_balance"] or 0) if c_rows else 0.0
            after_bal = round(before_bal + credit_val, 2)
            if credit_val > 0:
                self.db.table("customers").update(
                    {"outstanding_balance": after_bal, "updated_at": "now()"}
                ).eq("id", customer_id).eq("business_id", business_id).execute()

        # 4. Insert single grouped sales header
        sale = (
            self.db.table("sales")
            .insert(
                {
                    "business_id": business_id,
                    "customer_id": customer_id,
                    "total_amount": final_total,
                    "paid_amount": final_paid,
                    "payment_status": final_status,
                    "transaction_date": transaction_date,
                    "status": "active",
                    "operation_id": operation_id,
                    "notes": full_notes,
                    "created_by": user_id,
                }
            )
            .execute()
            .data[0]
        )

        # 5. Deduct stock & insert sale_items + inventory_movements
        item_results: list[dict[str, Any]] = []
        running_stock = dict(stock_by_pid)
        for it, line_tot in zip(items, allocated_lines):
            pid = str(it["product_id"])
            qty = float(it["quantity"])
            before_s = running_stock[pid]
            after_s = max(0.0, round(before_s - qty, 4))
            running_stock[pid] = after_s
            eff_price = round(line_tot / qty, 2) if qty > 0 else float(it["unit_price"])

            self.db.table("inventory").update(
                {"current_quantity": after_s, "updated_at": "now()"}
            ).eq("business_id", business_id).eq("product_id", pid).execute()

            self.db.table("sale_items").insert(
                {
                    "business_id": business_id,
                    "sale_id": sale["id"],
                    "product_id": pid,
                    "quantity": qty,
                    "unit": it["unit"],
                    "unit_price": eff_price,
                    "line_total": line_tot,
                }
            ).execute()

            self.db.table("inventory_movements").insert(
                {
                    "business_id": business_id,
                    "product_id": pid,
                    "movement_type": "sale",
                    "quantity_delta": -qty,
                    "unit": it["unit"],
                    "unit_cost": eff_price,
                    "reference_type": "sale",
                    "reference_id": sale["id"],
                    "operation_id": operation_id,
                    "transaction_date": transaction_date,
                    "notes": f"Combined bill: {qty:g} {it['unit']} {it['product_name']}",
                    "created_by": user_id,
                }
            ).execute()

            item_results.append(
                {
                    "product_id": pid,
                    "product_name": it["product_name"],
                    "quantity": qty,
                    "unit": it["unit"],
                    "unit_price": eff_price,
                    "line_total": line_tot,
                    "before_stock": before_s,
                    "after_stock": after_s,
                }
            )

        return {
            "sale_id": sale["id"],
            "total_amount": final_total,
            "catalog_total": catalog_total,
            "discount_amount": max(0.0, round(catalog_total - final_total, 2)),
            "paid_amount": final_paid,
            "credit_amount": credit_val,
            "payment_status": final_status,
            "before_balance": before_bal,
            "after_balance": after_bal,
            "items": item_results,
        }

    def swap_last_sale_variant(
        self,
        *,
        business_id: str,
        user_id: str,
        old_operation_id: str,
        new_product_id: str,
        new_product_name: str,
        new_unit: str,
        new_unit_price: float,
        new_quantity: float | None = None,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Atomically reverse the last mistaken SKU sale and re-record on the corrected SKU."""
        old_sales = (
            self.db.table("sales")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", old_operation_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not old_sales:
            raise PolicyBlockedError("Previous sale not found to swap variant.")
        old_sale = old_sales[0]
        old_items = (
            self.db.table("sale_items")
            .select("*")
            .eq("business_id", business_id)
            .eq("sale_id", old_sale["id"])
            .execute()
            .data
            or []
        )
        old_qty = float(old_items[0]["quantity"]) if old_items else 1.0
        old_pid = str(old_items[0]["product_id"]) if old_items else ""
        old_prod_name = "previous item"
        if old_pid:
            p_rows = (
                self.db.table("products")
                .select("name")
                .eq("id", old_pid)
                .eq("business_id", business_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if p_rows:
                old_prod_name = str(p_rows[0]["name"])

        qty = float(new_quantity) if new_quantity is not None and float(new_quantity) > 0 else old_qty
        # Pre-check target SKU stock before voiding old sale
        _, resolved_unit, new_avail = self._load_product_and_stock(
            business_id=business_id, product_id=new_product_id, fallback_unit=new_unit
        )
        effective_avail = new_avail + (old_qty if old_pid == new_product_id else 0.0)
        if effective_avail < qty - 1e-6:
            raise InsufficientStockError(effective_avail, new_product_name)

        old_notes = str(old_sale.get("notes") or "")
        tag = "[UDHAAR]" if old_sale.get("payment_status") == "credit" else (
            "[ONLINE]" if "[ONLINE]" in old_notes.upper() else ("[BANK]" if "[BANK]" in old_notes.upper() else "[CASH]")
        )
        new_total = round(qty * float(new_unit_price), 2)
        old_status = str(old_sale.get("payment_status") or "paid")
        old_paid = float(old_sale.get("paid_amount") or 0)
        if old_status == "credit":
            new_paid = 0.0
            new_status = "credit"
        elif old_status == "partial":
            new_paid = min(old_paid, new_total)
            new_status = "paid" if new_paid >= new_total - 0.009 else ("credit" if new_paid <= 0 else "partial")
        else:
            new_paid = new_total
            new_status = "paid"

        self.reverse_operation(
            business_id=business_id,
            user_id=user_id,
            operation_id=old_operation_id,
            reversal_operation_id=str(uuid.uuid4()),
            transaction_date=transaction_date,
        )
        recorded = self.record_sale(
            business_id=business_id,
            user_id=user_id,
            product_id=new_product_id,
            product_name=new_product_name,
            quantity=qty,
            unit=resolved_unit,
            unit_price=float(new_unit_price),
            payment_status=new_status,
            paid_amount=new_paid,
            customer_id=old_sale.get("customer_id"),
            transaction_date=transaction_date,
            operation_id=operation_id,
            notes=f"{tag} Swapped from {old_prod_name}",
        )
        return {
            "old_product_name": old_prod_name,
            "old_quantity": old_qty,
            "old_total": float(old_sale.get("total_amount") or 0),
            "new_product_id": new_product_id,
            "new_product_name": new_product_name,
            "quantity": qty,
            "unit": resolved_unit,
            "unit_price": float(new_unit_price),
            "new_total": new_total,
            "paid_amount": new_paid,
            "payment_status": new_status,
            "sale_id": recorded.get("sale_id"),
            "before_stock": recorded.get("before_stock"),
            "after_stock": recorded.get("after_stock"),
            "new_operation_id": operation_id,
        }

    def swap_last_return_variant(
        self,
        *,
        business_id: str,
        user_id: str,
        old_operation_id: str,
        new_product_id: str,
        new_product_name: str,
        new_unit: str,
        new_unit_price: float,
        new_quantity: float | None = None,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Atomically reverse the last mistaken customer return SKU and re-record on the corrected SKU."""
        mvs = (
            self.db.table("inventory_movements")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", old_operation_id)
            .eq("reference_type", "customer_return")
            .execute()
            .data
            or []
        )
        if not mvs:
            raise PolicyBlockedError("Previous customer return not found to swap variant.")
        mv = mvs[0]
        old_qty = abs(float(mv.get("quantity_delta") or 1))
        old_pid = str(mv.get("product_id") or "")
        old_prod_name = "previous item"
        if old_pid:
            p_rows = (
                self.db.table("products")
                .select("name")
                .eq("id", old_pid)
                .eq("business_id", business_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if p_rows:
                old_prod_name = str(p_rows[0]["name"])

        cust_id: str | None = None
        credit_amt = 0.0
        for tok in str(mv.get("notes") or "").split():
            if tok.startswith("[RETURN_UDHAAR:") and tok.endswith("]"):
                parts = tok[len("[RETURN_UDHAAR:") : -1].split("|")
                if len(parts) >= 2:
                    cust_id = parts[0]
                    try:
                        credit_amt = float(parts[1])
                    except Exception:
                        pass

        exp_rows = (
            self.db.table("expenses")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", old_operation_id)
            .eq("status", "active")
            .execute()
            .data
            or []
        )
        refund_method = "credit" if cust_id and credit_amt > 0 else (
            str(exp_rows[0].get("payment_method") or "cash") if exp_rows else "cash"
        )
        old_refund = credit_amt + (float(exp_rows[0].get("amount") or 0) if exp_rows else 0.0)

        qty = float(new_quantity) if new_quantity is not None and float(new_quantity) > 0 else old_qty
        new_refund = round(qty * float(new_unit_price), 2) if new_unit_price > 0 else old_refund

        self.reverse_operation(
            business_id=business_id,
            user_id=user_id,
            operation_id=old_operation_id,
            reversal_operation_id=str(uuid.uuid4()),
            transaction_date=transaction_date,
        )
        _, resolved_unit, _ = self._load_product_and_stock(
            business_id=business_id, product_id=new_product_id, fallback_unit=new_unit
        )
        ret = self.record_customer_return(
            business_id=business_id,
            user_id=user_id,
            product_id=new_product_id,
            product_name=new_product_name,
            quantity=qty,
            unit=resolved_unit,
            refund_amount=new_refund,
            refund_method=refund_method,
            customer_id=cust_id,
            transaction_date=transaction_date,
            operation_id=operation_id,
        )
        return {
            "old_product_name": old_prod_name,
            "old_quantity": old_qty,
            "new_product_id": new_product_id,
            "new_product_name": new_product_name,
            "quantity": qty,
            "unit": resolved_unit,
            "refund_amount": ret["refund_amount"],
            "refund_method": refund_method,
            "before_stock": ret["before_stock"],
            "after_stock": ret["after_stock"],
            "new_operation_id": operation_id,
        }

    def swap_last_movement_variant(
        self,
        *,
        business_id: str,
        user_id: str,
        old_operation_id: str,
        movement_type: str,
        new_product_id: str,
        new_product_name: str,
        new_unit: str,
        new_unit_cost: float,
        new_quantity: float | None = None,
        transaction_date: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Atomically swap SKU on last stock receive / damage / expiry movement."""
        mvs = (
            self.db.table("inventory_movements")
            .select("*")
            .eq("business_id", business_id)
            .eq("operation_id", old_operation_id)
            .eq("movement_type", movement_type)
            .execute()
            .data
            or []
        )
        if not mvs:
            raise PolicyBlockedError("Previous stock movement not found to swap variant.")
        mv = mvs[0]
        old_qty = abs(float(mv.get("quantity_delta") or 1))
        old_pid = str(mv.get("product_id") or "")
        old_cost = float(mv.get("unit_cost") or 0)
        old_prod_name = "previous item"
        if old_pid:
            p_rows = (
                self.db.table("products")
                .select("name")
                .eq("id", old_pid)
                .eq("business_id", business_id)
                .limit(1)
                .execute()
                .data
                or []
            )
            if p_rows:
                old_prod_name = str(p_rows[0]["name"])

        qty = float(new_quantity) if new_quantity is not None and float(new_quantity) > 0 else old_qty
        _, resolved_unit, new_avail = self._load_product_and_stock(
            business_id=business_id, product_id=new_product_id, fallback_unit=new_unit
        )
        if movement_type in ("damage", "expiry") and new_avail < qty - 1e-6:
            raise InsufficientStockError(new_avail, new_product_name)

        self.reverse_operation(
            business_id=business_id,
            user_id=user_id,
            operation_id=old_operation_id,
            reversal_operation_id=str(uuid.uuid4()),
            transaction_date=transaction_date,
        )
        if movement_type == "receive":
            ucost = float(new_unit_cost) if new_unit_cost > 0 else old_cost
            rec = self.receive_stock(
                business_id=business_id,
                user_id=user_id,
                product_id=new_product_id,
                quantity=qty,
                unit=resolved_unit,
                unit_cost=ucost,
                transaction_date=transaction_date,
                operation_id=operation_id,
            )
            return {
                "old_product_name": old_prod_name,
                "old_quantity": old_qty,
                "new_product_id": new_product_id,
                "new_product_name": new_product_name,
                "quantity": qty,
                "unit": resolved_unit,
                "total_amount": round(qty * ucost, 2),
                "before_stock": rec["before_qty"],
                "after_stock": rec["after_qty"],
                "new_operation_id": operation_id,
            }
        rec = self.deduct_damage_or_expiry(
            business_id=business_id,
            user_id=user_id,
            product_id=new_product_id,
            product_name=new_product_name,
            quantity=qty,
            unit=resolved_unit,
            movement_type=movement_type,
            transaction_date=transaction_date,
            operation_id=operation_id,
        )
        return {
            "old_product_name": old_prod_name,
            "old_quantity": old_qty,
            "new_product_id": new_product_id,
            "new_product_name": new_product_name,
            "quantity": qty,
            "unit": resolved_unit,
            "total_amount": 0.0,
            "before_stock": rec["before_qty"],
            "after_stock": rec["after_qty"],
            "new_operation_id": operation_id,
        }

