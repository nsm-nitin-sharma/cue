from typing import Any
from app.core.time_utils import get_business_today
from app.services.entity_resolver import resolve_product


class QueryEngine:
    """Read-only deterministic business query engine (never executes AI-generated SQL)."""

    def __init__(self, db: Any):
        self.db = db

    def answer_query(
        self,
        *,
        business_id: str,
        topic: str | None,
        product_query: str | None = None,
        customer_query: str | None = None,
        products: list[dict[str, Any]] | None = None,
        aliases: list[dict[str, Any]] | None = None,
        timezone_name: str = "Asia/Kolkata",
    ) -> dict[str, Any]:
        today_str = get_business_today(timezone_name).isoformat()

        if topic == "stock_check":
            prods = products or []
            als = aliases or []
            if product_query:
                pres = resolve_product(product_query, prods, als)
                if pres.status in {"exact", "verify_alias"} and pres.product:
                    p = pres.product
                    qty = float(p.get("current_stock") or 0)
                    unit = p.get("base_unit", "piece")
                    return {
                        "reply": f"Inventory mein abhi {qty:g} {unit} {p['name']} available hain.",
                        "lines": [
                            {"label": p["name"], "value": f"{qty:g} {unit}", "tone": "sage" if qty > float(p.get("low_stock_threshold") or 5) else "crimson"},
                            {"label": "Selling Price", "value": f"₹{float(p.get('default_selling_price') or 0):g}", "tone": "neutral"},
                        ],
                        "amount_inr": None,
                    }
                if pres.status == "ambiguous" and pres.candidates:
                    summary = ", ".join(f"{c['name']}: {float(c.get('current_stock') or 0):g} {c.get('base_unit', 'piece')}" for c in pres.candidates)
                    return {
                        "reply": f"Inventory mein {summary} available hain.",
                        "lines": [
                            {"label": c["name"], "value": f"{float(c.get('current_stock') or 0):g} {c.get('base_unit', 'piece')}", "tone": "neutral"}
                            for c in pres.candidates
                        ],
                        "amount_inr": None,
                    }
                tokens = [t for t in product_query.lower().replace("-", " ").split() if len(t) > 1]
                token_matches = [
                    p
                    for p in prods
                    if tokens and all(t in p["name"].lower().replace("-", " ") for t in tokens)
                ]
                if token_matches:
                    summary = ", ".join(f"{p['name']}: {float(p.get('current_stock') or 0):g} {p.get('base_unit', 'piece')}" for p in token_matches)
                    return {
                        "reply": f"Inventory mein {summary} available hain.",
                        "lines": [
                            {"label": p["name"], "value": f"{float(p.get('current_stock') or 0):g} {p.get('base_unit', 'piece')}", "tone": "sage"}
                            for p in token_matches
                        ],
                        "amount_inr": None,
                    }
                return {
                    "reply": f"Inventory mein '{product_query}' naam ka koi product nahi mila.",
                    "lines": [],
                    "amount_inr": None,
                }

            low = [p for p in prods if float(p.get("current_stock") or 0) <= float(p.get("low_stock_threshold") or 5)]
            if not prods:
                return {"reply": "Aapki inventory abhi khaali hai. Naya stock bol kar add karein.", "lines": [], "amount_inr": None}
            return {
                "reply": f"Inventory mein total {len(prods)} items hain" + (f", jinmein se {len(low)} low-stock hain." if low else " aur sabhi stock healthy hain."),
                "lines": [
                    {"label": p["name"], "value": f"{float(p.get('current_stock') or 0):g} {p.get('base_unit', 'piece')}", "tone": "crimson" if p in low else "sage"}
                    for p in prods[:6]
                ],
                "amount_inr": None,
            }

        if topic in {"pending_payments", "customer_balance"}:
            cust_res = (
                self.db.table("customers")
                .select("id, name, outstanding_balance, area_note")
                .eq("business_id", business_id)
                .eq("is_active", True)
                .order("outstanding_balance", desc=True)
                .execute()
            )
            all_custs = cust_res.data or []
            if customer_query:
                q = customer_query.lower()
                matched = [c for c in all_custs if q in c["name"].lower()]
                if matched:
                    summary = ", ".join(f"{c['name']}: ₹{float(c['outstanding_balance']):,.0f}" for c in matched)
                    return {
                        "reply": f"Khata balance — {summary}.",
                        "lines": [{"label": c["name"], "value": f"₹{float(c['outstanding_balance']):,.0f}", "tone": "ochre" if float(c["outstanding_balance"]) > 0 else "sage"} for c in matched],
                        "amount_inr": sum(float(c["outstanding_balance"]) for c in matched),
                    }
                return {"reply": f"Khata mein '{customer_query}' naam ka customer nahi mila.", "lines": [], "amount_inr": 0}

            pending = [c for c in all_custs if float(c["outstanding_balance"]) > 0]
            total_due = sum(float(c["outstanding_balance"]) for c in pending)
            if not pending:
                return {"reply": "Abhi kisi bhi customer ka payment pending nahi hai.", "lines": [], "amount_inr": 0}
            details = ", ".join(f"{c['name']} (₹{float(c['outstanding_balance']):,.0f})" for c in pending[:5])
            return {
                "reply": f"{len(pending)} customers ka total ₹{total_due:,.0f} payment pending hai: {details}.",
                "lines": [{"label": c["name"], "value": f"₹{float(c['outstanding_balance']):,.0f}", "tone": "ochre"} for c in pending[:6]],
                "amount_inr": total_due,
            }

        if topic == "expenses_summary":
            exp_res = (
                self.db.table("expenses")
                .select("category, description, amount, payment_method, status")
                .eq("business_id", business_id)
                .eq("transaction_date", today_str)
                .neq("status", "voided")
                .execute()
            )
            exps = exp_res.data or []
            if not exps:
                return {
                    "reply": "Aaj abhi tak koi expense record nahi hua hai.",
                    "lines": [{"label": "Total Expenses", "value": "₹0", "tone": "sage"}],
                    "amount_inr": 0.0,
                }
            exp_total = sum(float(e["amount"]) for e in exps)
            return {
                "reply": f"Aaj abhi tak {len(exps)} expenses hue hain, total ₹{exp_total:,.0f}.",
                "lines": [
                    {
                        "label": str(e.get("description") or e.get("category") or "Expense"),
                        "value": f"₹{float(e['amount']):,.0f} ({str(e.get('payment_method') or 'cash').upper()})",
                        "tone": "crimson",
                    }
                    for e in exps[:6]
                ],
                "amount_inr": exp_total,
            }

        if topic == "daily_summary":
            sales_res = (
                self.db.table("sales")
                .select("total_amount, paid_amount, status")
                .eq("business_id", business_id)
                .eq("transaction_date", today_str)
                .neq("status", "voided")
                .execute()
            )
            exp_res = (
                self.db.table("expenses")
                .select("amount, status")
                .eq("business_id", business_id)
                .eq("transaction_date", today_str)
                .neq("status", "voided")
                .execute()
            )
            s_rows = sales_res.data or []
            e_rows = exp_res.data or []
            s_tot = sum(float(r["total_amount"]) for r in s_rows)
            e_tot = sum(float(r["amount"]) for r in e_rows)
            net = s_tot - e_tot
            return {
                "reply": f"Aaj ka hisaab: {len(s_rows)} sales (₹{s_tot:,.0f}), {len(e_rows)} expenses (₹{e_tot:,.0f}), net balance ₹{net:,.0f}.",
                "lines": [
                    {"label": "Sales Revenue", "value": f"₹{s_tot:,.0f}", "tone": "sage"},
                    {"label": "Expenses", "value": f"₹{e_tot:,.0f}", "tone": "crimson"},
                    {"label": "Net", "value": f"₹{net:,.0f}", "tone": "ochre" if net < 0 else "sage"},
                ],
                "amount_inr": net,
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
