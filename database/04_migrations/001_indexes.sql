-- SQL-first v1. Existing FK/single-column indexes are retained; no duplicates.
CREATE INDEX idx_product_catalogue ON product(category_id, created_at DESC)
    WHERE status = 1 AND is_deleted = FALSE;
CREATE INDEX idx_product_title_trgm ON product USING gin(title gin_trgm_ops)
    WHERE status = 1 AND is_deleted = FALSE;
CREATE INDEX idx_product_description_trgm ON product USING gin(description gin_trgm_ops)
    WHERE status = 1 AND is_deleted = FALSE;
CREATE INDEX idx_order_buyer_date ON "order"(buyer_id, order_date DESC) WHERE is_deleted = FALSE;
CREATE INDEX idx_order_detail_product_order ON order_detail(product_id, order_id);
-- Do not silently merge duplicate carts: CREATE UNIQUE INDEX aborts this transaction.
CREATE UNIQUE INDEX uq_cart_product ON shopping_cart_item(cart_id, product_id);
-- Benchmarks retained idx_review_product / idx_review_rating; extra review indexes were not selected.
