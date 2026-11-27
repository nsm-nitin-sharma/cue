from typing import Any
from app.core.time_utils import get_business_today


class AnalyticsFoundationService:
    """
    Section 10 Future Business Intelligence Foundation.
    Collects clean daily snapshots and low-stock events now so future updates
    can compute predictive restocking and unusual sales detection without schema rewrites.
    """

    def __init__(self, db: Any):
        self.db = db

    def record_daily_snapshot(self, *, business_id: str, timezone_name: str = "Asia/Kolkata") -> None:
        today_str = get_business_today(timezone_name).isoformat()
        self.db.table("business_insights_events").insert(
            {
                "business_id": business_id,
                "event_type": "daily_snapshot",
                "metric_date": today_str,
                "payload": {"source": "voice_pipeline"},
            }
        ).execute()

    def get_readiness_summary(self, *, business_id: str) -> dict[str, Any]:
        events = (
            self.db.table("business_insights_events")
            .select("event_type, metric_date")
            .eq("business_id", business_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        rows = events.data or []
        return {
            "events_collected": len(rows),
            "low_stock_alerts_logged": sum(1 for r in rows if r["event_type"] == "low_stock_crossed"),
            "status": "collecting_foundation_data",
        }
