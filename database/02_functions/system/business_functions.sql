-- =
-- BUSINESS FUNCTIONS
-- ==============================================================================
-- Core business logic functions for e-commerce operations
-- ==============================================================================

-- Function to calculate order total with voucher discount
-- Handles percentage and fixed amount discounts with validation
CREATE OR REPLACE FUNCTION calculate_order_total(
    p_subtotal DECIMAL(18,2),
    p_voucher_id INT DEFAULT NULL,
    p_shipping_fee DECIMAL(18,2) DEFAULT 0
)
RETURNS DECIMAL(18,2) AS $$
DECLARE
    discount_amount DECIMAL(18,2) := 0;
    voucher_record RECORD;
    final_total DECIMAL(18,2);
BEGIN
    -- Validate inputs
    IF p_subtotal < 0 THEN
        RAISE EXCEPTION 'Subtotal cannot be negative';
    END IF;

    IF p_shipping_fee < 0 THEN
        RAISE EXCEPTION 'Shipping fee cannot be negative';
    END IF;

    -- Get voucher details if provided
    IF p_voucher_id IS NOT NULL THEN
        SELECT * INTO voucher_record
        FROM voucher
        WHERE voucher_id = p_voucher_id
        AND is_active = TRUE
        AND valid_to > CURRENT_TIMESTAMP;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Invalid or expired voucher';
        END IF;

        -- Check usage limit
        IF voucher_record.max_usage IS NOT NULL AND voucher_record.usage_count >= voucher_record.max_usage THEN
            RAISE EXCEPTION 'Voucher usage limit exceeded';
        END IF;

        -- Check minimum order value
        IF p_subtotal < voucher_record.min_order_amount THEN
            RAISE EXCEPTION 'Order value does not meet voucher minimum requirement of %', voucher_record.min_order_amount;
        END IF;

        -- Calculate discount
        IF voucher_record.discount_type = 1 THEN
            -- Percentage discount
            discount_amount := p_subtotal * voucher_record.discount_value / 100;
        ELSE
            -- Fixed amount discount
            discount_amount := voucher_record.discount_value;
        END IF;

        -- Ensure discount doesn't exceed subtotal
        discount_amount := LEAST(discount_amount, p_subtotal);
    END IF;

    -- Calculate final total
    final_total := GREATEST(p_subtotal - discount_amount + p_shipping_fee, 0);

    RETURN final_total;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to validate and apply voucher to order
-- Returns: Discount amount applied
CREATE OR REPLACE FUNCTION apply_voucher_to_order(
    p_order_id INT,
    p_voucher_code VARCHAR(20)
)
RETURNS DECIMAL(18,2) AS $$
DECLARE
    voucher_record RECORD;
    order_record RECORD;
    v_discount_amount DECIMAL(18,2) := 0;
    final_total DECIMAL(18,2);
BEGIN
    -- Get order details
    SELECT * INTO order_record FROM "order" WHERE order_id = p_order_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order not found';
    END IF;

    -- Get voucher details
    SELECT * INTO voucher_record FROM voucher WHERE code = p_voucher_code;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Voucher not found';
    END IF;

    -- Validate voucher
    IF NOT voucher_record.is_active THEN
        RAISE EXCEPTION 'Voucher is not active';
    END IF;

    IF voucher_record.valid_to < CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'Voucher has expired';
    END IF;

    -- Check if voucher already applied to this order
    IF order_record.voucher_id IS NOT NULL THEN
        RAISE EXCEPTION 'Order already has a voucher applied';
    END IF;

    -- Calculate discount
    v_discount_amount := calculate_order_total(order_record.total_amount, voucher_record.voucher_id, order_record.shipping_fee)
                     - order_record.total_amount + order_record.discount_amount;

    -- Update order with voucher
    UPDATE "order"
    SET voucher_id = voucher_record.voucher_id,
        discount_amount = v_discount_amount,
        final_amount = total_amount - v_discount_amount + shipping_fee,
        updated_at = CURRENT_TIMESTAMP
    WHERE order_id = p_order_id;

    -- Update voucher usage
    UPDATE voucher
    SET usage_count = usage_count + 1
    WHERE voucher_id = voucher_record.voucher_id;

    -- Log the voucher application
    PERFORM log_system_action(
        order_record.buyer_id,
        'VOUCHER_APPLIED',
        'order',
        p_order_id,
        'Applied voucher ' || p_voucher_code || ' with discount ' || v_discount_amount
    );

    RETURN v_discount_amount;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to update product status based on quantity changes
-- Automatically marks product as sold out when quantity reaches 0
CREATE OR REPLACE FUNCTION update_product_status_on_quantity()
RETURNS TRIGGER AS $$
BEGIN
    -- Only process if quantity actually changed
    IF NEW.quantity != OLD.quantity THEN
        -- Mark as sold out if quantity reaches 0
        IF NEW.quantity = 0 AND OLD.quantity > 0 THEN
            NEW.status := 3; -- Sold Out
            NEW.sold_at := CURRENT_TIMESTAMP;

            -- Log the status change
            PERFORM log_system_action(
                NULL,
                'PRODUCT_SOLD_OUT',
                'product',
                NEW.product_id,
                'Product marked as sold out (quantity: 0)'
            );
        END IF;

        -- Update timestamp
        NEW.updated_at := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to get product availability status
-- Returns: Human-readable status string
CREATE OR REPLACE FUNCTION get_product_status_text(p_status SMALLINT)
RETURNS TEXT AS $$
BEGIN
    RETURN CASE p_status
        WHEN 0 THEN 'Pending Review'
        WHEN 1 THEN 'Active'
        WHEN 2 THEN 'Rejected'
        WHEN 3 THEN 'Sold Out'
        ELSE 'Unknown'
    END;
END;
$$ LANGUAGE plpgsql
IMMUTABLE
SECURITY DEFINER
SET search_path = public;

-- Function to get order status text
-- Returns: Human-readable status string
CREATE OR REPLACE FUNCTION get_order_status_text(p_status SMALLINT)
RETURNS TEXT AS $$
BEGIN
    RETURN CASE p_status
        WHEN 0 THEN 'Pending'
        WHEN 1 THEN 'Confirmed'
        WHEN 2 THEN 'Shipping'
        WHEN 3 THEN 'Delivered'
        WHEN 4 THEN 'Cancelled'
        ELSE 'Unknown'
    END;
END;
$$ LANGUAGE plpgsql
IMMUTABLE
SECURITY DEFINER
SET search_path = public;

-- Function to calculate product rating average
-- Returns: Average rating for a product
CREATE OR REPLACE FUNCTION get_product_average_rating(p_product_id INT)
RETURNS DECIMAL(3,2) AS $$
DECLARE
    avg_rating DECIMAL(3,2);
BEGIN
    SELECT COALESCE(AVG(rating)::DECIMAL(3,2), 0)
    INTO avg_rating
    FROM review
    WHERE product_id = p_product_id AND is_deleted = FALSE;

    RETURN avg_rating;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to get user's total spending
-- Returns: Total amount spent by user
CREATE OR REPLACE FUNCTION get_user_total_spending(p_user_id INT)
RETURNS DECIMAL(18,2) AS $$
DECLARE
    total_spent DECIMAL(18,2);
BEGIN
    SELECT COALESCE(SUM(final_amount), 0)
    INTO total_spent
    FROM "order"
    WHERE buyer_id = p_user_id
    AND order_status IN (1, 2, 3) -- Confirmed, Shipping, Delivered
    AND is_deleted = FALSE;

    RETURN total_spent;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to get seller's total revenue
-- Returns: Total revenue earned by seller
CREATE OR REPLACE FUNCTION get_seller_total_revenue(p_seller_id INT)
RETURNS DECIMAL(18,2) AS $$
DECLARE
    total_revenue DECIMAL(18,2);
BEGIN
    SELECT COALESCE(SUM(od.price_at_purchase * od.quantity), 0)
    INTO total_revenue
    FROM order_detail od
    JOIN product p ON od.product_id = p.product_id
    JOIN "order" o ON od.order_id = o.order_id
    WHERE p.seller_id = p_seller_id
      AND o.order_status IN (1, 2, 3) -- Confirmed, Shipping, Delivered
      AND o.is_deleted = FALSE;

    RETURN total_revenue;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Create trigger for product status update
CREATE TRIGGER trg_update_product_status
BEFORE UPDATE ON product
FOR EACH ROW
WHEN (OLD.quantity != NEW.quantity)
EXECUTE FUNCTION update_product_status_on_quantity();