from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


IntentType = Literal[
    "inventory_receive",
    "inventory_damage",
    "inventory_expiry",
    "inventory_adjust",
    "record_sale",
    "record_expense",
    "record_customer_payment",
    "record_udhaar_credit",
    "customer_return",
    "record_supplier_credit",
    "record_supplier_payment",
    "create_customer",
    "update_customer",
    "update_product_settings",
    "archive_product",
    "correct_last_sale",
    "correct_last_operation",
    "undo_last_operation",
    "business_day_replay",
    "query_business",
    "clarify_response",
    "create_product",
    "unknown",
]


class VoiceOperationItem(StrictModel):
    """Single structured business intent extracted by the untrusted AI parser."""

    intent: IntentType
    product_query: str | None = Field(default=None, max_length=120)
    customer_query: str | None = Field(default=None, max_length=120)
    new_name: str | None = Field(default=None, max_length=120)
    quantity: float | None = Field(default=None, gt=0, le=10000)
    unit: str | None = Field(default=None, max_length=32)
    unit_price: float | None = Field(default=None, ge=0, le=1000000)
    cost_price: float | None = Field(default=None, ge=0, le=1000000)
    selling_price: float | None = Field(default=None, ge=0, le=1000000)
    total_amount: float | None = Field(default=None, ge=0, le=1000000)
    paid_amount: float | None = Field(default=None, ge=0, le=1000000)
    payment_status: Literal["paid", "partial", "credit"] | None = None
    payment_method: Literal["cash", "upi", "bank", "credit"] | None = None
    expense_category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=240)
    phone: str | None = Field(default=None, max_length=32)
    area_note: str | None = Field(default=None, max_length=120)
    low_stock_threshold: float | None = Field(default=None, ge=0, le=10000)
    relative_date: str | None = Field(default=None, max_length=48)
    date_range: Literal[
        "today",
        "yesterday",
        "day_before",
        "this_week",
        "last_week",
        "last_7_days",
        "this_month",
        "last_month",
        "last_30_days",
    ] | None = None
    uses_prior_context: bool = False
    is_combined_bill: bool = False
    bill_total_amount: float | None = Field(default=None, ge=0, le=1000000)
    is_affirmative: bool | None = None
    is_negative: bool | None = None
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    has_ambiguity_or_noise_conflict: bool = False
    clarification_question: str | None = Field(default=None, max_length=240)
    query_topic: Literal[
        "sales_summary",
        "expenses_summary",
        "daily_summary",
        "pending_payments",
        "customer_balance",
        "supplier_balance",
        "stock_check",
        "general",
    ] | None = None
    notes: str | None = Field(default=None, max_length=240)

    @field_validator("product_query", "customer_query", "new_name", "description")
    @classmethod
    def no_sql_injection_chars(cls, v: str | None) -> str | None:
        if v is not None and (";" in v or "--" in v):
            return v.replace(";", " ").replace("--", " ").strip()
        return v


class IntentProposal(StrictModel):
    """
    Untrusted AI parser output schema.
    Supports single command OR multi-command batch in a single breath (up to 25 ops).
    """

    detected_language: Literal["hinglish", "hi", "en"] = "hinglish"
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    has_ambiguity_or_noise_conflict: bool = False
    clarification_question: str | None = Field(default=None, max_length=240)
    operations: list[VoiceOperationItem] = Field(default_factory=list, max_length=25)
    spoken_reply_hint: str | None = Field(default=None, max_length=300)


class TextCommandRequest(StrictModel):
    text: str = Field(min_length=1, max_length=1500)
    operation_id: str = Field(min_length=8, max_length=64)
    language: Literal["hinglish", "hi", "en"] = "hinglish"
    conversation_date: str | None = None


class TtsRequest(StrictModel):
    text: str = Field(min_length=1, max_length=800)
    language: Literal["hinglish", "hi", "en"] = "hinglish"


class ClarificationChoiceRequest(StrictModel):
    operation_id: str = Field(min_length=8, max_length=64)
    choice_value: str = Field(min_length=1, max_length=200)
    language: Literal["hinglish", "hi", "en"] = "hinglish"


class ConfirmOperationRequest(StrictModel):
    operation_id: str = Field(min_length=8, max_length=64)
    confirmation_token: str = Field(min_length=16, max_length=128)
    accept: bool = True


class CreateProductAndExecuteRequest(StrictModel):
    operation_id: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="General", max_length=64)
    base_unit: Literal["piece", "packet", "kg", "litre", "box"] = "piece"
    quantity: float = Field(ge=0, le=10000)
    cost_price: float = Field(ge=0, le=1000000)
    selling_price: float = Field(ge=0, le=1000000)
    low_stock_threshold: float = Field(default=5, ge=0, le=1000)
    action_kind: Literal["receive", "sale"] = "receive"


class OfflineSyncBatchItem(StrictModel):
    operation_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=1500)
    conversation_date: str | None = None
    language: Literal["hinglish", "hi", "en"] = "hinglish"


class OfflineSyncBatchRequest(StrictModel):
    items: list[OfflineSyncBatchItem] = Field(min_length=1, max_length=50)


class OnboardStoreRequest(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    city: str = Field(default="", max_length=80)
    plan_code: Literal["free", "growth", "pro"] = "free"
    seed_sample_catalog: bool = False


class ManualProductRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="General", max_length=64)
    base_unit: Literal["piece", "packet", "kg", "litre", "box"] = "piece"
    cost_price: float = Field(ge=0, le=1000000)
    selling_price: float = Field(ge=0, le=1000000)
    stock: float = Field(default=0, ge=0, le=100000)
    low_stock_threshold: float = Field(default=5, ge=0, le=1000)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class ManualExpenseRequest(StrictModel):
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=240)
    amount: float = Field(gt=0, le=1000000)
    payment_method: Literal["cash", "upi", "bank", "credit"] = "cash"
    transaction_date: str | None = None


class ManualCustomerPaymentRequest(StrictModel):
    customer_id: str = Field(min_length=8, max_length=64)
    amount: float = Field(gt=0, le=1000000)
    payment_method: Literal["cash", "upi", "bank"] = "cash"


class UpdateProductRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=64)
    base_unit: Literal["piece", "packet", "kg", "litre", "box"] | None = None
    cost_price: float | None = Field(default=None, ge=0, le=1000000)
    selling_price: float | None = Field(default=None, ge=0, le=1000000)
    stock: float | None = Field(default=None, ge=0, le=100000)
    low_stock_threshold: float | None = Field(default=None, ge=0, le=1000)
    aliases: list[str] | None = Field(default=None, max_length=20)


class UpdateCustomerRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    area_note: str | None = Field(default=None, max_length=120)


class UpdateExpenseRequest(StrictModel):
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1, max_length=240)
    amount: float | None = Field(default=None, gt=0, le=1000000)
    payment_method: Literal["cash", "upi", "bank", "credit"] | None = None
    transaction_date: str | None = None


class VoiceTurnResult(BaseModel):
    operation_id: str
    status: Literal[
        "executed",
        "needs_clarification",
        "needs_confirmation",
        "new_product_popup",
        "policy_blocked",
        "memory_boundary",
        "retry_audio",
        "query_answered",
    ]
    transcript: str
    reply: str
    language: Literal["hinglish", "hi", "en"] = "hinglish"
    receipts: list[dict[str, Any]] = Field(default_factory=list)
    clarification: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None
    new_product_draft: dict[str, Any] | None = None
