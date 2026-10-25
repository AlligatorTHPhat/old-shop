-- ===========================================================================
-- ORDER DETAIL TRIGGERS
-- ===========================================================================
-- Business rules enforced at the database level.
--
-- Stock reservation and voucher usage are handled by the application layer
-- (see backend/app/crud/shopping_cart.py and backend/app/crud/order.py), so no
-- trigger touches product.quantity or voucher.usage_count here; doing it in both
-- places would double-count.
-- ===========================================================================

-- Sellers cannot buy their own products.
CREATE OR REPLACE FUNCTION check_no_self_buying()
RETURNS TRIGGER AS $$
DECLARE
    order_buyer_id INT;
    product_seller_id INT;
BEGIN
    SELECT buyer_id INTO order_buyer_id
    FROM "order"
    WHERE order_id = NEW.order_id;

    SELECT seller_id INTO product_seller_id
    FROM product
    WHERE product_id = NEW.product_id;

    IF order_buyer_id IS NULL OR product_seller_id IS NULL THEN
        RAISE EXCEPTION 'INVALID_ORDER_OR_PRODUCT: Invalid order or product reference';
    END IF;

    IF order_buyer_id = product_seller_id THEN
        PERFORM log_system_action(
            order_buyer_id,
            'SELF_BUY_BLOCKED',
            'order_detail',
            NEW.order_detail_id,
            'Attempted to buy own product (product_id: ' || NEW.product_id || ')'
        );
        RAISE EXCEPTION 'BUSINESS_RULE_VIOLATION: Sellers cannot buy their own products.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

DROP TRIGGER IF EXISTS trg_no_self_buying ON order_detail;
CREATE TRIGGER trg_no_self_buying
BEFORE INSERT ON order_detail
FOR EACH ROW EXECUTE FUNCTION check_no_self_buying();
