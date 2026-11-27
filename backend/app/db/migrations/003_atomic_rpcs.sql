-- ============================================================================
-- Cue Voice-First Business OS - 003 Atomic Row-Locked RPCs
-- ============================================================================

-- 1. Atomic Stock Receive (with SELECT ... FOR UPDATE lock + cost update)
CREATE OR REPLACE FUNCTION public.rpc_receive_stock(
    p_business_id UUID,
    p_user_id UUID,
    p_product_id UUID,
    p_quantity NUMERIC,
    p_unit TEXT,
    p_unit_cost NUMERIC,
    p_transaction_date DATE,
    p_operation_id UUID,
    p_notes TEXT DEFAULT 'Voice stock receive'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before NUMERIC;
    v_after NUMERIC;
    v_movement_id UUID;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;

    INSERT INTO public.inventory (business_id, product_id, current_quantity)
    VALUES (p_business_id, p_product_id, 0)
    ON CONFLICT (business_id, product_id) DO NOTHING;

    SELECT current_quantity INTO v_before
    FROM public.inventory
    WHERE business_id = p_business_id AND product_id = p_product_id
    FOR UPDATE;

    v_after := v_before + p_quantity;

    UPDATE public.inventory
    SET current_quantity = v_after, updated_at = NOW()
    WHERE business_id = p_business_id AND product_id = p_product_id;

    IF p_unit_cost IS NOT NULL AND p_unit_cost >= 0 THEN
        UPDATE public.products
        SET default_cost_price = p_unit_cost, updated_at = NOW()
        WHERE id = p_product_id AND business_id = p_business_id;
    END IF;

    INSERT INTO public.inventory_movements (
        business_id, product_id, movement_type, quantity_delta, unit, unit_cost,
        reference_type, operation_id, transaction_date, notes, created_by
    ) VALUES (
        p_business_id, p_product_id, 'receive', p_quantity, p_unit, p_unit_cost,
        'voice_receive', p_operation_id, p_transaction_date, p_notes, p_user_id
    ) RETURNING id INTO v_movement_id;

    RETURN jsonb_build_object(
        'movement_id', v_movement_id,
        'before_qty', v_before,
        'after_qty', v_after
    );
END;
$$;

-- 2. Atomic Stock Damage / Expiry Deduction (Blocks Negative Stock)
CREATE OR REPLACE FUNCTION public.rpc_deduct_damage_or_expiry(
    p_business_id UUID,
    p_user_id UUID,
    p_product_id UUID,
    p_quantity NUMERIC,
    p_unit TEXT,
    p_movement_type TEXT,
    p_transaction_date DATE,
    p_operation_id UUID,
    p_notes TEXT DEFAULT 'Stock loss recorded'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before NUMERIC;
    v_after NUMERIC;
    v_movement_id UUID;
    v_threshold NUMERIC;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;
    IF p_movement_type NOT IN ('damage', 'expiry', 'adjustment') THEN
        RAISE EXCEPTION 'Invalid deduction movement type';
    END IF;

    SELECT i.current_quantity, p.low_stock_threshold
    INTO v_before, v_threshold
    FROM public.inventory i
    JOIN public.products p ON p.id = i.product_id
    WHERE i.business_id = p_business_id AND i.product_id = p_product_id
    FOR UPDATE;

    IF v_before IS NULL THEN
        RAISE EXCEPTION 'INSUFFICIENT_STOCK:0';
    END IF;
    IF v_before < p_quantity THEN
        RAISE EXCEPTION 'INSUFFICIENT_STOCK:%', v_before;
    END IF;

    v_after := v_before - p_quantity;

    UPDATE public.inventory
    SET current_quantity = v_after, updated_at = NOW()
    WHERE business_id = p_business_id AND product_id = p_product_id;

    INSERT INTO public.inventory_movements (
        business_id, product_id, movement_type, quantity_delta, unit,
        reference_type, operation_id, transaction_date, notes, created_by
    ) VALUES (
        p_business_id, p_product_id, p_movement_type, -p_quantity, p_unit,
        'voice_deduction', p_operation_id, p_transaction_date, p_notes, p_user_id
    ) RETURNING id INTO v_movement_id;

    IF v_after <= COALESCE(v_threshold, 5) THEN
        INSERT INTO public.business_insights_events (business_id, product_id, event_type, metric_date, payload)
        VALUES (p_business_id, p_product_id, 'low_stock_crossed', p_transaction_date, jsonb_build_object('remaining', v_after, 'threshold', v_threshold));
    END IF;

    RETURN jsonb_build_object(
        'movement_id', v_movement_id,
        'before_qty', v_before,
        'after_qty', v_after
    );
END;
$$;

-- 3. Atomic Sale Commit (Blocks Negative Stock, Updates Customer Udhaar)
CREATE OR REPLACE FUNCTION public.rpc_record_sale(
    p_business_id UUID,
    p_user_id UUID,
    p_product_id UUID,
    p_quantity NUMERIC,
    p_unit TEXT,
    p_unit_price NUMERIC,
    p_payment_status TEXT,
    p_paid_amount NUMERIC,
    p_customer_id UUID,
    p_transaction_date DATE,
    p_operation_id UUID,
    p_notes TEXT DEFAULT 'Voice sale'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before NUMERIC;
    v_after NUMERIC;
    v_total NUMERIC;
    v_credit_delta NUMERIC;
    v_sale_id UUID;
    v_movement_id UUID;
    v_threshold NUMERIC;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;

    SELECT i.current_quantity, p.low_stock_threshold
    INTO v_before, v_threshold
    FROM public.inventory i
    JOIN public.products p ON p.id = i.product_id
    WHERE i.business_id = p_business_id AND i.product_id = p_product_id
    FOR UPDATE;

    IF v_before IS NULL OR v_before < p_quantity THEN
        RAISE EXCEPTION 'INSUFFICIENT_STOCK:%', COALESCE(v_before, 0);
    END IF;

    v_after := v_before - p_quantity;
    v_total := ROUND(p_quantity * p_unit_price, 2);
    v_credit_delta := GREATEST(0, v_total - COALESCE(p_paid_amount, 0));

    UPDATE public.inventory
    SET current_quantity = v_after, updated_at = NOW()
    WHERE business_id = p_business_id AND product_id = p_product_id;

    INSERT INTO public.sales (
        business_id, customer_id, total_amount, paid_amount, payment_status,
        transaction_date, status, operation_id, notes, created_by
    ) VALUES (
        p_business_id, p_customer_id, v_total, COALESCE(p_paid_amount, 0), p_payment_status,
        p_transaction_date, 'active', p_operation_id, p_notes, p_user_id
    ) RETURNING id INTO v_sale_id;

    INSERT INTO public.sale_items (
        business_id, sale_id, product_id, quantity, unit, unit_price, line_total
    ) VALUES (
        p_business_id, v_sale_id, p_product_id, p_quantity, p_unit, p_unit_price, v_total
    );

    INSERT INTO public.inventory_movements (
        business_id, product_id, movement_type, quantity_delta, unit, unit_cost,
        reference_type, reference_id, operation_id, transaction_date, notes, created_by
    ) VALUES (
        p_business_id, p_product_id, 'sale', -p_quantity, p_unit, p_unit_price,
        'sale', v_sale_id, p_operation_id, p_transaction_date, p_notes, p_user_id
    ) RETURNING id INTO v_movement_id;

    IF v_credit_delta > 0 AND p_customer_id IS NOT NULL THEN
        UPDATE public.customers
        SET outstanding_balance = outstanding_balance + v_credit_delta, updated_at = NOW()
        WHERE id = p_customer_id AND business_id = p_business_id;
    END IF;

    IF v_after <= COALESCE(v_threshold, 5) THEN
        INSERT INTO public.business_insights_events (business_id, product_id, event_type, metric_date, payload)
        VALUES (p_business_id, p_product_id, 'low_stock_crossed', p_transaction_date, jsonb_build_object('remaining', v_after, 'threshold', v_threshold));
    END IF;

    RETURN jsonb_build_object(
        'sale_id', v_sale_id,
        'movement_id', v_movement_id,
        'total_amount', v_total,
        'before_qty', v_before,
        'after_qty', v_after
    );
END;
$$;

-- 4. Atomic Customer Payment Collection
CREATE OR REPLACE FUNCTION public.rpc_record_customer_payment(
    p_business_id UUID,
    p_user_id UUID,
    p_customer_id UUID,
    p_amount NUMERIC,
    p_payment_method TEXT,
    p_transaction_date DATE,
    p_operation_id UUID,
    p_notes TEXT DEFAULT 'Voice payment received'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_before NUMERIC;
    v_after NUMERIC;
    v_payment_id UUID;
BEGIN
    SELECT outstanding_balance INTO v_before
    FROM public.customers
    WHERE id = p_customer_id AND business_id = p_business_id
    FOR UPDATE;

    IF v_before IS NULL THEN
        RAISE EXCEPTION 'Customer not found';
    END IF;

    v_after := GREATEST(0, v_before - p_amount);

    UPDATE public.customers
    SET outstanding_balance = v_after, updated_at = NOW()
    WHERE id = p_customer_id AND business_id = p_business_id;

    INSERT INTO public.customer_payments (
        business_id, customer_id, amount, payment_method, transaction_date,
        status, operation_id, notes, created_by
    ) VALUES (
        p_business_id, p_customer_id, p_amount, p_payment_method, p_transaction_date,
        'active', p_operation_id, p_notes, p_user_id
    ) RETURNING id INTO v_payment_id;

    RETURN jsonb_build_object(
        'payment_id', v_payment_id,
        'before_balance', v_before,
        'after_balance', v_after
    );
END;
$$;

-- 5. Atomic Sale Quantity Correction (Compensating Stock Reversal + Original Sale Update)
CREATE OR REPLACE FUNCTION public.rpc_correct_sale_quantity(
    p_business_id UUID,
    p_user_id UUID,
    p_sale_id UUID,
    p_new_quantity NUMERIC,
    p_operation_id UUID,
    p_transaction_date DATE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_sale RECORD;
    v_item RECORD;
    v_qty_delta NUMERIC;
    v_new_total NUMERIC;
    v_old_credit NUMERIC;
    v_new_credit NUMERIC;
    v_before_stock NUMERIC;
    v_after_stock NUMERIC;
BEGIN
    SELECT * INTO v_sale FROM public.sales
    WHERE id = p_sale_id AND business_id = p_business_id
    FOR UPDATE;

    IF v_sale IS NULL THEN
        RAISE EXCEPTION 'Sale not found';
    END IF;

    SELECT * INTO v_item FROM public.sale_items
    WHERE sale_id = p_sale_id AND business_id = p_business_id
    LIMIT 1
    FOR UPDATE;

    IF v_item IS NULL THEN
        RAISE EXCEPTION 'Sale item not found';
    END IF;

    v_qty_delta := v_item.quantity - p_new_quantity; -- positive means stock returns to inventory
    v_new_total := ROUND(p_new_quantity * v_item.unit_price, 2);

    SELECT current_quantity INTO v_before_stock
    FROM public.inventory
    WHERE business_id = p_business_id AND product_id = v_item.product_id
    FOR UPDATE;

    v_after_stock := v_before_stock + v_qty_delta;
    IF v_after_stock < 0 THEN
        RAISE EXCEPTION 'INSUFFICIENT_STOCK:%', v_before_stock;
    END IF;

    UPDATE public.inventory
    SET current_quantity = v_after_stock, updated_at = NOW()
    WHERE business_id = p_business_id AND product_id = v_item.product_id;

    UPDATE public.sale_items
    SET quantity = p_new_quantity, line_total = v_new_total
    WHERE id = v_item.id;

    v_old_credit := GREATEST(0, v_sale.total_amount - v_sale.paid_amount);
    UPDATE public.sales
    SET total_amount = v_new_total,
        paid_amount = CASE WHEN v_sale.payment_status = 'paid' THEN v_new_total ELSE LEAST(v_sale.paid_amount, v_new_total) END,
        status = CASE WHEN p_new_quantity = 0 THEN 'voided' ELSE 'corrected' END
    WHERE id = p_sale_id;

    v_new_credit := CASE
        WHEN v_sale.payment_status = 'paid' THEN 0
        ELSE GREATEST(0, v_new_total - LEAST(v_sale.paid_amount, v_new_total))
    END;

    IF v_sale.customer_id IS NOT NULL AND v_new_credit <> v_old_credit THEN
        UPDATE public.customers
        SET outstanding_balance = GREATEST(0, outstanding_balance + (v_new_credit - v_old_credit)),
            updated_at = NOW()
        WHERE id = v_sale.customer_id AND business_id = p_business_id;
    END IF;

    INSERT INTO public.inventory_movements (
        business_id, product_id, movement_type, quantity_delta, unit, unit_cost,
        reference_type, reference_id, operation_id, transaction_date, notes, created_by
    ) VALUES (
        p_business_id, v_item.product_id, 'reversal', v_qty_delta, v_item.unit, v_item.unit_price,
        'sale_correction', p_sale_id, p_operation_id, p_transaction_date,
        format('Corrected sale quantity %s -> %s', v_item.quantity, p_new_quantity), p_user_id
    );

    RETURN jsonb_build_object(
        'sale_id', p_sale_id,
        'product_id', v_item.product_id,
        'old_quantity', v_item.quantity,
        'new_quantity', p_new_quantity,
        'old_total', v_sale.total_amount,
        'new_total', v_new_total,
        'stock_delta', v_qty_delta,
        'after_stock', v_after_stock
    );
END;
$$;
