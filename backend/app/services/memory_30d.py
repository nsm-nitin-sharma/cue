from datetime import date, timedelta
from typing import Any

from app.core.time_utils import get_business_today


class Memory30DService:
    """
    Day-grouped conversational memory & 30-day rolling cross-day retrieval.
    One chat per calendar day (Asia/Kolkata), retrieving context up to 30 days back.
    """

    def __init__(self, db: Any):
        self.db = db

    def get_or_create_day_conversation(
        self,
        *,
        business_id: str,
        conv_date: date | None = None,
        timezone_name: str = "Asia/Kolkata",
    ) -> dict[str, Any]:
        target_date = conv_date or get_business_today(timezone_name)
        date_str = target_date.isoformat()

        existing = (
            self.db.table("conversations")
            .select("*")
            .eq("business_id", business_id)
            .eq("conversation_date", date_str)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        created = (
            self.db.table("conversations")
            .insert(
                {
                    "business_id": business_id,
                    "conversation_date": date_str,
                    "title": f"Ledger · {date_str}",
                    "daily_summary": "New business day thread",
                    "context_state": {},
                }
            )
            .execute()
        )
        return created.data[0]

    def append_message(
        self,
        *,
        conversation_id: str,
        business_id: str,
        conversation_date: str,
        role: str,
        content: str,
        language: str = "hinglish",
        linked_operation_id: str | None = None,
        ui_payload: dict[str, Any] | None = None,
    ) -> None:
        self.db.table("conversation_messages").insert(
            {
                "conversation_id": conversation_id,
                "business_id": business_id,
                "conversation_date": conversation_date,
                "role": role,
                "content": content,
                "language": language,
                "linked_operation_id": linked_operation_id,
                "ui_payload": ui_payload,
            }
        ).execute()

    def update_context_state(self, *, conversation_id: str, state: dict[str, Any]) -> None:
        self.db.table("conversations").update({"context_state": state, "updated_at": "now()"}).eq(
            "id", conversation_id
        ).execute()

    def list_30d_conversations(self, *, business_id: str, timezone_name: str = "Asia/Kolkata") -> list[dict[str, Any]]:
        today = get_business_today(timezone_name)
        cutoff = (today - timedelta(days=30)).isoformat()
        res = (
            self.db.table("conversations")
            .select("id, conversation_date, title, daily_summary, updated_at")
            .eq("business_id", business_id)
            .gte("conversation_date", cutoff)
            .order("conversation_date", desc=True)
            .execute()
        )
        return res.data or []

    def get_30d_context_for_llm(
        self,
        *,
        business_id: str,
        today_conversation: dict[str, Any],
        target_date: date | None = None,
        timezone_name: str = "Asia/Kolkata",
    ) -> dict[str, Any]:
        today = get_business_today(timezone_name)
        cutoff = (today - timedelta(days=30)).isoformat()

        recent_msgs = (
            self.db.table("conversation_messages")
            .select("conversation_date, role, content")
            .eq("business_id", business_id)
            .gte("conversation_date", cutoff)
            .order("created_at", desc=True)
            .limit(12)
            .execute()
        )

        # If referencing a specific day within 30d (e.g., "kal"), pull that day's movements too
        day_movements: list[dict[str, Any]] = []
        if target_date and (today - target_date).days <= 30:
            mov_res = (
                self.db.table("inventory_movements")
                .select("id, product_id, movement_type, quantity_delta, unit, unit_cost, transaction_date, notes")
                .eq("business_id", business_id)
                .eq("transaction_date", target_date.isoformat())
                .order("created_at", desc=True)
                .limit(15)
                .execute()
            )
            day_movements = mov_res.data or []

        return {
            "today_date": today.isoformat(),
            "context_state": today_conversation.get("context_state") or {},
            "recent_turns": list(reversed(recent_msgs.data or [])),
            "target_date_movements": day_movements,
        }
