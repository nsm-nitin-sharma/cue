import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_active_business_id, get_current_user
from app.core.config import get_settings
from app.core.time_utils import get_business_today
from app.db.supabase_client import get_admin_supabase
from app.domain.schemas.intents import (
    ManualCustomerPaymentRequest,
    ManualExpenseRequest,
    ManualProductRequest,
    OnboardStoreRequest,
)
from app.services.analytics_foundation import AnalyticsFoundationService
from app.services.memory_30d import Memory30DService
from app.services.transaction_engine import TransactionEngine

router = APIRouter(tags=["workspace"])


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    db_ready = False
    try:
        db = get_admin_supabase()
        db.table("subscription_plans").select("code").limit(1).execute()
        db_ready = True
    except Exception:
        db_ready = False
    return {
        "status": "ok",
        "stt_provider": settings.STT_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
        "database_schema_ready": db_ready,
    }


@router.get("/subscriptions/plans")
def list_plans() -> dict:
    db = get_admin_supabase()
    res = db.table("subscription_plans").select("*").eq("is_active", True).execute()
    return {"plans": res.data or []}


@router.post("/onboarding/store")
def onboard_store(
    req: OnboardStoreRequest,
    user: dict = Depends(get_current_user),
) -> dict:
    db = get_admin_supabase()
    existing = (
        db.table("business_members")
        .select("business_id")
        .eq("user_id", user["user_id"])
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {"business_id": existing.data[0]["business_id"], "already_onboarded": True}

    res = db.rpc(
        "rpc_onboard_business",
        {
            "p_user_id": user["user_id"],
            "p_name": req.name,
            "p_city": req.city,
            "p_plan_code": req.plan_code,
            "p_seed_sample_catalog": req.seed_sample_catalog,
        },
    ).execute()
    return res.data


@router.get("/workspace/bootstrap")
def get_workspace_bootstrap(
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    db = get_admin_supabase()
    biz = db.table("businesses").select("*").eq("id", business_id).limit(1).execute().data[0]
    sub = (
        db.table("business_subscriptions")
        .select("*, subscription_plans(*)")
        .eq("business_id", business_id)
        .limit(1)
        .execute()
        .data
    )
    prods = (
        db.table("products")
        .select("*, inventory(current_quantity), product_aliases(alias_text)")
        .eq("business_id", business_id)
        .eq("is_active", True)
        .order("name")
        .execute()
        .data
        or []
    )
    movements = (
        db.table("inventory_movements")
        .select("*, products(name)")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(80)
        .execute()
        .data
        or []
    )
    customers = (
        db.table("customers")
        .select("*")
        .eq("business_id", business_id)
        .eq("is_active", True)
        .order("name")
        .execute()
        .data
        or []
    )
    sales = (
        db.table("sales")
        .select("*, customers(name), sale_items(*, products(name))")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(80)
        .execute()
        .data
        or []
    )
    expenses = (
        db.table("expenses")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(80)
        .execute()
        .data
        or []
    )

    mem = Memory30DService(db)
    convs = mem.list_30d_conversations(business_id=business_id, timezone_name=biz.get("timezone", "Asia/Kolkata"))
    if not convs:
        mem.get_or_create_day_conversation(business_id=business_id, timezone_name=biz.get("timezone", "Asia/Kolkata"))
        convs = mem.list_30d_conversations(business_id=business_id, timezone_name=biz.get("timezone", "Asia/Kolkata"))

    msgs = (
        db.table("conversation_messages")
        .select("*")
        .eq("business_id", business_id)
        .in_("conversation_date", [c["conversation_date"] for c in convs])
        .order("created_at", desc=False)
        .execute()
        .data
        or []
    )

    return {
        "business": biz,
        "subscription": sub[0] if sub else None,
        "products": prods,
        "movements": movements,
        "customers": customers,
        "sales": sales,
        "expenses": expenses,
        "conversations": convs,
        "messages": msgs,
        "bi_foundation": AnalyticsFoundationService(db).get_readiness_summary(business_id=business_id),
    }


@router.post("/inventory/products")
def add_manual_product(
    req: ManualProductRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    db = get_admin_supabase()
    tx = TransactionEngine(db)
    op_id = str(uuid.uuid4())
    created = tx.create_product_and_stock(
        business_id=business_id,
        user_id=user["user_id"],
        name=req.name,
        category=req.category,
        base_unit=req.base_unit,
        cost_price=req.cost_price,
        selling_price=req.selling_price,
        low_stock_threshold=req.low_stock_threshold,
        opening_qty=req.stock,
        transaction_date=get_business_today().isoformat(),
        operation_id=op_id,
    )
    for al in req.aliases:
        tx.save_verified_alias(business_id=business_id, product_id=created["product"]["id"], alias_text=al)
    return created


@router.post("/expenses")
def add_manual_expense(
    req: ManualExpenseRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    tx = TransactionEngine(get_admin_supabase())
    return tx.record_expense(
        business_id=business_id,
        user_id=user["user_id"],
        category=req.category,
        description=req.description,
        amount=req.amount,
        payment_method=req.payment_method,
        transaction_date=req.transaction_date or get_business_today().isoformat(),
        operation_id=str(uuid.uuid4()),
    )


@router.post("/customers/payments")
def add_manual_payment(
    req: ManualCustomerPaymentRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    tx = TransactionEngine(get_admin_supabase())
    return tx.record_customer_payment(
        business_id=business_id,
        user_id=user["user_id"],
        customer_id=req.customer_id,
        amount=req.amount,
        payment_method=req.payment_method,
        transaction_date=get_business_today().isoformat(),
        operation_id=str(uuid.uuid4()),
    )


@router.post("/inventory/products/{product_id}/archive")
def archive_inventory_product(
    product_id: str,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    tx = TransactionEngine(get_admin_supabase())
    tx.archive_product(business_id=business_id, product_id=product_id)
    return {"status": "archived", "product_id": product_id}


@router.post("/inventory/clear-unused")
def clear_unused_inventory_products(
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    tx = TransactionEngine(get_admin_supabase())
    archived_count = tx.archive_unused_products(business_id=business_id)
    return {"status": "ok", "archived_count": archived_count}
