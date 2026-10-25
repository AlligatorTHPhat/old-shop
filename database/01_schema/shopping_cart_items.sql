-- shopping_cart_items.sql
CREATE TABLE shopping_cart_item (
    cart_item_id SERIAL PRIMARY KEY,
    cart_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cart_id) REFERENCES shopping_cart(cart_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

-- Indexes for performance
CREATE INDEX idx_shopping_cart_item_cart ON shopping_cart_item(cart_id);
CREATE INDEX idx_shopping_cart_item_product ON shopping_cart_item(product_id);
