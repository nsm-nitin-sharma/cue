-- ============================================================================
-- Cue Voice-First Business OS - 004 Subscription Plans & Store Onboarding RPC
-- ============================================================================

INSERT INTO public.subscription_plans (code, display_name, description, price_display, limits)
VALUES
    (
        'free',
        'Free Pilot',
        'Solo shopkeepers testing voice-first khata and inventory tracking.',
        '₹0 · Free Tier',
        '{"monthly_voice_turns": 250, "max_staff": 1, "max_stores": 1, "replay_enabled": true, "bi_insights_enabled": false}'::jsonb
    ),
    (
        'growth',
        'Growth',
        'Busy kirana and local retailers with multi-staff support and full replay.',
        'Pricing TBD',
        '{"monthly_voice_turns": 2500, "max_staff": 3, "max_stores": 1, "replay_enabled": true, "bi_insights_enabled": true}'::jsonb
    ),
    (
        'pro',
        'Pro',
        'Multi-branch stores and wholesalers with advanced predictive insights.',
        'Custom Enterprise',
        '{"monthly_voice_turns": 15000, "max_staff": 25, "max_stores": 5, "replay_enabled": true, "bi_insights_enabled": true}'::jsonb
    )
ON CONFLICT (code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    price_display = EXCLUDED.price_display,
    limits = EXCLUDED.limits;

-- Atomic Store Onboarding + Subscription Activation + Optional Kirana Seed
CREATE OR REPLACE FUNCTION public.rpc_onboard_business(
    p_user_id UUID,
    p_name TEXT,
    p_city TEXT,
    p_plan_code TEXT DEFAULT 'free',
    p_seed_sample_catalog BOOLEAN DEFAULT TRUE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_business_id UUID;
    v_plan_id UUID;
    v_p1 UUID; v_p2 UUID; v_p3 UUID; v_p4 UUID; v_p5 UUID; v_p6 UUID;
BEGIN
    SELECT id INTO v_plan_id FROM public.subscription_plans WHERE code = p_plan_code AND is_active = TRUE;
    IF v_plan_id IS NULL THEN
        SELECT id INTO v_plan_id FROM public.subscription_plans WHERE code = 'free';
    END IF;

    INSERT INTO public.businesses (owner_id, name, city)
    VALUES (p_user_id, p_name, COALESCE(p_city, ''))
    RETURNING id INTO v_business_id;

    INSERT INTO public.business_members (business_id, user_id, role)
    VALUES (v_business_id, p_user_id, 'owner');

    INSERT INTO public.business_subscriptions (business_id, plan_id, status)
    VALUES (v_business_id, v_plan_id, 'active');

    IF p_seed_sample_catalog THEN
        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'BEV-001', 'Pepsi 500ml', 'pepsi 500ml', 'Beverages', 'piece', 16, 20, 10) RETURNING id INTO v_p1;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p1, 24);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p1, 'chhoti pepsi', 'chhoti pepsi'),
            (v_business_id, v_p1, 'chotti pepsi', 'chotti pepsi');

        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'BEV-002', 'Pepsi 2L', 'pepsi 2l', 'Beverages', 'piece', 72, 90, 6) RETURNING id INTO v_p2;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p2, 8);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p2, 'badi pepsi', 'badi pepsi');

        -- Note: Coca-Cola deliberately omits 'coke' initially so "Do you mean Coca-Cola 750ml?" triggers & learns!
        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'BEV-003', 'Coca-Cola 750ml', 'coca-cola 750ml', 'Beverages', 'piece', 32, 40, 8) RETURNING id INTO v_p3;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p3, 18);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p3, 'coca cola', 'coca cola');

        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'SNK-001', 'Maggi Masala 70g', 'maggi masala 70g', 'Instant Food', 'packet', 11, 14, 15) RETURNING id INTO v_p4;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p4, 36);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p4, 'maggi', 'maggi'),
            (v_business_id, v_p4, 'maggi packet', 'maggi packet');

        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'GRC-001', 'Tata Salt 1kg', 'tata salt 1kg', 'Staples', 'packet', 22, 28, 10) RETURNING id INTO v_p5;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p5, 14);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p5, 'namak', 'namak'),
            (v_business_id, v_p5, 'tata salt', 'tata salt');

        INSERT INTO public.products (business_id, sku_code, name, normalized_name, category, base_unit, default_cost_price, default_selling_price, low_stock_threshold)
        VALUES (v_business_id, 'OIL-001', 'Fortune Sunflower Oil 1L', 'fortune sunflower oil 1l', 'Oils & Ghee', 'litre', 132, 155, 6) RETURNING id INTO v_p6;
        INSERT INTO public.inventory (business_id, product_id, current_quantity) VALUES (v_business_id, v_p6, 5);
        INSERT INTO public.product_aliases (business_id, product_id, alias_text, normalized_alias) VALUES
            (v_business_id, v_p6, 'fortune oil', 'fortune oil'),
            (v_business_id, v_p6, 'tel', 'tel');

        INSERT INTO public.customers (business_id, name, normalized_name, phone, area_note, outstanding_balance) VALUES
            (v_business_id, 'Ramesh Gupta', 'ramesh gupta', '+91 98110 44210', 'Sector 4', 1200),
            (v_business_id, 'Ramesh Yadav', 'ramesh yadav', '+91 98712 90344', 'Station Road', 650),
            (v_business_id, 'Sunita Devi', 'sunita devi', '+91 99104 77812', 'Gandhi Nagar', 350);
    END IF;

    RETURN jsonb_build_object('business_id', v_business_id, 'plan_code', p_plan_code);
END;
$$;
