-- order_details.sql
CREATE TABLE order_detail (
    order_detail_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    price_at_purchase DECIMAL(18, 2) NOT NULL,
    subtotal DECIMAL(18, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES "order"(order_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);

-- Indexes for performance
CREATE INDEX idx_order_detail_order ON order_detail(order_id);
