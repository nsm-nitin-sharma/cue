from typing import Any
from app.core.time_utils import get_business_today


class QueryEngine:
    """Read-only deterministic business query engine (never executes AI-generated SQL)."""

    def __init__(self, db: Any):
        self.db = db

    def answer_query(
        self,
        *,
        business_id: str,
        topic: str | None,
        customer_query: str | None = None,
        timezone_name: str = "Asia/Kolkata",
    ) -> dict[str, Any]:
        today_str = get_business_today(timezone_name).isoformat()

        if topic == "pending_payments" or topic == "customer_balance":
            cust_res = (
                self.db.table("customers")
                .select("id, name, outstanding_balance, area_note")
                .eq("business_id", business_id)
                .gt("outstanding_balance", 0)
                .order("outstanding_balance", desc=True)
                .execute()
            )
            pending = cust_res.data or []
            if customer_query:
                q = customer_query.lower()
                matched = [c for c in pending if q in c["name"].lower()]
                if matched:
                    summary = ", ".join(f"{c['name']}: ₹{float(c['outstanding_balance']):,.0f}" for c in matched)
                    return {
                        "reply": f"{summary} payment pending hai.",
                        "lines": [{"label": c["name"], "value": f"₹{float(c['outstanding_balance']):,.0f}", "tone": "ochre"} for c in matched],
                        "amount_inr": sum(float(c["outstanding_balance"]) for c in matched),
                    }

            total_due = sum(float(c["outstanding_balance"]) for c in pending)
            if not pending:
                return {"reply": "Abhi kisi bhi customer ka payment pending nahi hai.", "lines": [], "amount_inr": 0}
            details = ", ".join(f"{c['name']} (₹{float(c['outstanding_balance']):,.0f})" for c in pending[:5])
            return {
                "reply": f"{len(pending)} customers ka total ₹{total_due:,.0f} payment pending hai: {details}.",
                "lines": [{"label": c["name"], "value": f"₹{float(c['outstanding_balance']):,.0f}", "tone": "ochre"} for c in pending[:6]],
                "amount_inr": total_due,
            }

        # Default: today's sales summary
        sales_res = (
            self.db.table("sales")
            .select("total_amount, paid_amount, payment_status, status")
            .eq("business_id", business_id)
            .eq("transaction_date", today_str)
            .neq("status", "voided")
            .execute()
        )
        rows = sales_res.data or []
        total = sum(float(r["total_amount"]) for r in rows)
        cash = sum(float(r["paid_amount"]) for r in rows)
        credit = total - cash
        return {
            "reply": f"Aaj abhi tak {len(rows)} sales hui hain, total ₹{total:,.0f} (Cash ₹{cash:,.0f}, Udhaar ₹{credit:,.0f}).",
            "lines": [
                {"label": "Total Bills", "value": str(len(rows)), "tone": "neutral"},
                {"label": "Cash Collected", "value": f"₹{cash:,.0f}", "tone": "sage"},
                {"label": "Udhaar", "value": f"₹{credit:,.0f}", "tone": "ochre"},
            ],
            "amount_inr": total,
        }
