-- ============================================================================
-- Cue Voice-First Business OS - 002 Row Level Security & Tenant Isolation
-- ============================================================================

CREATE OR REPLACE FUNCTION public.is_business_member(target_business_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.business_members bm
        WHERE bm.business_id = target_business_id
          AND bm.user_id = auth.uid()
          AND bm.is_active = TRUE
    );
$$;

-- Enable RLS on all tables
ALTER TABLE public.subscription_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_unit_conversions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sale_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pending_confirmations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.business_insights_events ENABLE ROW LEVEL SECURITY;

-- Public read-only access to active subscription plans
CREATE POLICY plans_read_active ON public.subscription_plans
    FOR SELECT USING (is_active = TRUE);

-- Businesses: members can read; owner can update
CREATE POLICY businesses_select ON public.businesses
    FOR SELECT USING (public.is_business_member(id) OR owner_id = auth.uid());

CREATE POLICY businesses_insert ON public.businesses
    FOR INSERT WITH CHECK (owner_id = auth.uid());

CREATE POLICY businesses_update ON public.businesses
    FOR UPDATE USING (owner_id = auth.uid());

-- Business Members
CREATE POLICY members_select ON public.business_members
    FOR SELECT USING (public.is_business_member(business_id) OR user_id = auth.uid());

-- Business Subscriptions
CREATE POLICY subscriptions_select ON public.business_subscriptions
    FOR SELECT USING (public.is_business_member(business_id));

-- Standard Business-Scoped Policies (Read/Write restricted strictly to active members)
CREATE POLICY products_tenant ON public.products
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY aliases_tenant ON public.product_aliases
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY conversions_tenant ON public.product_unit_conversions
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY inventory_tenant ON public.inventory
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

-- Append-Only Ledger Tables: SELECT & INSERT allowed for members, NO client DELETE
CREATE POLICY movements_select ON public.inventory_movements
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY movements_insert ON public.inventory_movements
    FOR INSERT WITH CHECK (public.is_business_member(business_id));

CREATE POLICY customers_tenant ON public.customers
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY sales_select ON public.sales
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY sales_insert ON public.sales
    FOR INSERT WITH CHECK (public.is_business_member(business_id));
CREATE POLICY sales_update ON public.sales
    FOR UPDATE USING (public.is_business_member(business_id));

CREATE POLICY sale_items_select ON public.sale_items
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY sale_items_insert ON public.sale_items
    FOR INSERT WITH CHECK (public.is_business_member(business_id));

CREATE POLICY payments_select ON public.customer_payments
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY payments_insert ON public.customer_payments
    FOR INSERT WITH CHECK (public.is_business_member(business_id));

CREATE POLICY expenses_select ON public.expenses
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY expenses_insert ON public.expenses
    FOR INSERT WITH CHECK (public.is_business_member(business_id));
CREATE POLICY expenses_update ON public.expenses
    FOR UPDATE USING (public.is_business_member(business_id));

CREATE POLICY conversations_tenant ON public.conversations
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY conv_messages_tenant ON public.conversation_messages
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));

CREATE POLICY voice_txn_select ON public.voice_transactions
    FOR SELECT USING (public.is_business_member(business_id));
CREATE POLICY voice_txn_insert ON public.voice_transactions
    FOR INSERT WITH CHECK (public.is_business_member(business_id));
CREATE POLICY voice_txn_update ON public.voice_transactions
    FOR UPDATE USING (public.is_business_member(business_id));

CREATE POLICY pending_conf_tenant ON public.pending_confirmations
    FOR ALL USING (public.is_business_member(business_id) AND user_id = auth.uid())
    WITH CHECK (public.is_business_member(business_id) AND user_id = auth.uid());

CREATE POLICY bi_events_tenant ON public.business_insights_events
    FOR ALL USING (public.is_business_member(business_id))
    WITH CHECK (public.is_business_member(business_id));
