import hashlib
import re
import secrets
from typing import Literal

from app.core.config import get_settings
from app.core.exceptions import PolicyBlockedError

ALLOWED_INTENTS = frozenset(
    {
        "inventory_receive",
        "inventory_damage",
        "inventory_expiry",
        "inventory_adjust",
        "record_sale",
        "record_expense",
        "record_customer_payment",
        "correct_last_sale",
        "undo_last_operation",
        "business_day_replay",
        "query_business",
        "clarify_response",
        "create_product",
        "unknown",
    }
)

_DESTRUCTIVE_PATTERNS = re.compile(
    r"("
    r"\bdelete\s+(all|everything|database|table|business|account|records|history)\b|"
    r"\bsab\s*(kuch\s*)?(delete|hata|mita|uda|khatam)\b|"
    r"\bsaara\s*(data|record|hisab|khata)\s*(delete|hata|mita|saaf)\b|"
    r"\b(drop\s+table|truncate\s+table|wipe\s+database|clear\s+database|reset\s+all)\b|"
    r"\b(ignore\s+previous\s+instructions|system\s+prompt|execute\s+sql|run\s+sql)\b"
    r")",
    re.IGNORECASE,
)


class SecurityPolicyEngine:
    """
    Zero-agency AI capability firewall.
    Ensures the AI never executes arbitrary tasks, never triggers destructive deletes,
    and enforces explicit Tier-3 confirmation for >= ₹5,000 or cross-day reversals.
    """

    @staticmethod
    def assert_safe_utterance(text: str) -> None:
        if _DESTRUCTIVE_PATTERNS.search(text):
            raise PolicyBlockedError(
                "Destructive or bulk-delete operations are permanently disabled for voice and AI. "
                "Cue maintains an append-only audit ledger."
            )

    @staticmethod
    def assert_allowed_intent(intent: str) -> None:
        if intent not in ALLOWED_INTENTS:
            raise PolicyBlockedError(f"Intent '{intent}' is not in the allowlisted registry.")

    @staticmethod
    def classify_risk_tier(
        *,
        intent: str,
        amount_inr: float = 0.0,
        is_cross_day_reversal: bool = False,
        high_value_threshold: float | None = None,
    ) -> Literal["tier1", "tier3"]:
        threshold = (
            high_value_threshold
            if high_value_threshold is not None
            else get_settings().HIGH_VALUE_CONFIRM_THRESHOLD_INR
        )
        if amount_inr >= threshold or is_cross_day_reversal:
            return "tier3"
        if intent in {"inventory_adjust", "undo_last_operation"} and amount_inr >= threshold:
            return "tier3"
        return "tier1"

    @staticmethod
    def generate_confirmation_token() -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        return raw_token, token_hash

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
