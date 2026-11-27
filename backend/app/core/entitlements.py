from typing import Any
from app.core.exceptions import QuotaExceededError


def assert_voice_quota(subscription: dict[str, Any] | None) -> None:
    """Enforce server-side subscription plan limits for voice transactions."""
    if not subscription:
        return
    status = subscription.get("status", "active")
    if status not in {"active", "trialing"}:
        raise QuotaExceededError("Subscription is inactive. Please update your plan in Plans & Billing.")

    used = int(subscription.get("monthly_voice_used") or 0)
    plan = subscription.get("subscription_plans") or {}
    limits = plan.get("limits") or {}
    limit = int(limits.get("monthly_voice_turns") or 250)
    if used >= limit:
        raise QuotaExceededError(
            f"Monthly limit of {limit} voice turns reached on the {plan.get('display_name', 'Free')} plan."
        )
