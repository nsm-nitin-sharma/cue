-- ============================================================================
-- Cue Voice-First Business OS - 001 Core Enterprise Schema
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. Subscription Plans (Configurable SaaS Tiers: Free, Growth, Pro)
CREATE TABLE IF NOT EXISTS public.subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (code IN ('free', 'growth', 'pro')),
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    price_display TEXT NOT NULL DEFAULT 'Pilot',
    limits JSONB NOT NULL DEFAULT '{
        "monthly_voice_turns": 250,
        "max_staff": 1,
        "max_stores": 1,
        "replay_enabled": true,
        "bi_insights_enabled": false
    }'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Businesses (Tenants)
CREATE TABLE IF NOT EXISTS public.businesses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    city TEXT DEFAULT '',
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    preferred_language TEXT NOT NULL DEFAULT 'hinglish' CHECK (preferred_language IN ('hinglish', 'hi', 'en')),
    currency TEXT NOT NULL DEFAULT 'INR',
    settings JSONB NOT NULL DEFAULT '{
        "allow_negative_stock": false,
        "high_value_confirm_inr": 5000
    }'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Business Members (Multi-Staff RBAC Foundation)
CREATE TABLE IF NOT EXISTS public.business_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'manager', 'staff')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, user_id)
);

-- 4. Business Subscriptions
CREATE TABLE IF NOT EXISTS public.business_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL UNIQUE REFERENCES public.businesses(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES public.subscription_plans(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('trialing', 'active', 'past_due', 'canceled')),
    monthly_voice_used INTEGER NOT NULL DEFAULT 0 CHECK (monthly_voice_used >= 0),
    current_period_start TIMESTAMPTZ NOT NULL DEFAULT date_trunc('month', NOW()),
    current_period_end TIMESTAMPTZ NOT NULL DEFAULT (date_trunc('month', NOW()) + INTERVAL '1 month'),
    provider_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Products Catalog
CREATE TABLE IF NOT EXISTS public.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    sku_code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    base_unit TEXT NOT NULL DEFAULT 'piece' CHECK (base_unit IN ('piece', 'packet', 'kg', 'litre', 'box')),
    default_cost_price NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (default_cost_price >= 0),
    default_selling_price NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (default_selling_price >= 0),
    low_stock_threshold NUMERIC(12, 3) NOT NULL DEFAULT 5 CHECK (low_stock_threshold >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, normalized_name)
);

-- 6. Product Aliases (Verified Spoken Names -> Product)
CREATE TABLE IF NOT EXISTS public.product_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    alias_text TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'hinglish',
    is_verified BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, normalized_alias)
);

-- 7. Product Unit Conversions (e.g. 1 box/peti -> 24 pieces)
CREATE TABLE IF NOT EXISTS public.product_unit_conversions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    from_unit TEXT NOT NULL,
    to_base_multiplier NUMERIC(12, 4) NOT NULL CHECK (to_base_multiplier > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, product_id, from_unit)
);

-- 8. Inventory (Current Stock Balance per Product)
CREATE TABLE IF NOT EXISTS public.inventory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
    current_quantity NUMERIC(12, 3) NOT NULL DEFAULT 0 CHECK (current_quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, product_id)
);

-- 9. Inventory Movements (Append-Only Immutable Stock Ledger)
CREATE TABLE IF NOT EXISTS public.inventory_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE RESTRICT,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('receive', 'sale', 'damage', 'expiry', 'adjustment', 'reversal')),
    quantity_delta NUMERIC(12, 3) NOT NULL,
    unit TEXT NOT NULL,
    unit_cost NUMERIC(12, 2),
    reference_type TEXT,
    reference_id UUID,
    operation_id UUID NOT NULL,
    transaction_date DATE NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. Customers (Udhaar Khata)
CREATE TABLE IF NOT EXISTS public.customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    area_note TEXT NOT NULL DEFAULT '',
    outstanding_balance NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (outstanding_balance >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. Sales (Append-Only + Correction Versioned)
CREATE TABLE IF NOT EXISTS public.sales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES public.customers(id) ON DELETE RESTRICT,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    paid_amount NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'partial', 'credit')),
    transaction_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'corrected', 'voided')),
    parent_sale_id UUID REFERENCES public.sales(id),
    operation_id UUID NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 12. Sale Items
CREATE TABLE IF NOT EXISTS public.sale_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    sale_id UUID NOT NULL REFERENCES public.sales(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE RESTRICT,
    quantity NUMERIC(12, 3) NOT NULL CHECK (quantity > 0),
    unit TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0)
);

-- 13. Customer Payments (Udhaar Repayments)
CREATE TABLE IF NOT EXISTS public.customer_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES public.customers(id) ON DELETE RESTRICT,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    payment_method TEXT NOT NULL DEFAULT 'cash' CHECK (payment_method IN ('cash', 'upi', 'bank')),
    transaction_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'corrected', 'voided')),
    parent_payment_id UUID REFERENCES public.customer_payments(id),
    operation_id UUID NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. Expenses
CREATE TABLE IF NOT EXISTS public.expenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    payment_method TEXT NOT NULL DEFAULT 'cash' CHECK (payment_method IN ('cash', 'upi', 'bank', 'credit')),
    transaction_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'corrected', 'voided')),
    parent_expense_id UUID REFERENCES public.expenses(id),
    operation_id UUID NOT NULL,
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 15. Conversations (One Chat = One Business Day, 30-Day Rolling Context)
CREATE TABLE IF NOT EXISTS public.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    conversation_date DATE NOT NULL,
    title TEXT NOT NULL DEFAULT 'Daily Ledger Chat',
    daily_summary TEXT NOT NULL DEFAULT '',
    context_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, conversation_date)
);

-- 16. Conversation Messages (Normalized Daily Thread Turns)
CREATE TABLE IF NOT EXISTS public.conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    conversation_date DATE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system_card')),
    content TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'hinglish',
    linked_operation_id UUID,
    ui_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 17. Voice Transactions (Audit Trail + Idempotency Registry)
CREATE TABLE IF NOT EXISTS public.voice_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES public.conversations(id) ON DELETE SET NULL,
    operation_id UUID NOT NULL,
    payload_hash TEXT NOT NULL,
    transaction_date DATE NOT NULL,
    raw_transcript TEXT NOT NULL,
    detected_language TEXT NOT NULL DEFAULT 'hinglish',
    stt_provider TEXT NOT NULL DEFAULT 'text',
    stt_confidence NUMERIC(5, 4),
    parsed_intent JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation_status TEXT NOT NULL CHECK (
        validation_status IN (
            'auto_executed',
            'needs_clarification',
            'needs_confirmation',
            'executed',
            'corrected',
            'undone',
            'failed',
            'policy_blocked'
        )
    ),
    risk_tier TEXT NOT NULL DEFAULT 'tier1' CHECK (risk_tier IN ('tier1', 'tier2', 'tier3', 'blocked')),
    affected_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    response_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    audit_trail JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by UUID REFERENCES auth.users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, operation_id)
);

-- 18. Pending Tier-3 Confirmations (Short-lived Cryptographic Tokens)
CREATE TABLE IF NOT EXISTS public.pending_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL,
    token_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    proposed_action JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, operation_id)
);

-- 19. Business Insights Events (Section 10 Future BI Foundation)
CREATE TABLE IF NOT EXISTS public.business_insights_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id UUID NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
    product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('low_stock_crossed', 'velocity_spike', 'unusual_sale', 'daily_snapshot')),
    metric_date DATE NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- High-Performance Indexes (30-Day Retrieval & Ledger Queries)
CREATE INDEX IF NOT EXISTS idx_products_biz_trgm ON public.products USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_aliases_biz_trgm ON public.product_aliases USING gin (normalized_alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_movements_biz_date ON public.inventory_movements (business_id, transaction_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sales_biz_date ON public.sales (business_id, transaction_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_expenses_biz_date ON public.expenses (business_id, transaction_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_biz_date ON public.conversations (business_id, conversation_date DESC);
CREATE INDEX IF NOT EXISTS idx_conv_msgs_30d ON public.conversation_messages (business_id, conversation_date DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_voice_txn_biz_date ON public.voice_transactions (business_id, transaction_date DESC);
