-- orders.sql
CREATE TABLE "order" (
    order_id SERIAL PRIMARY KEY,
    buyer_id INT NOT NULL,
    contact_id INT NOT NULL,
    payment_method_id INT NOT NULL,
    voucher_id INT,
    order_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(18, 2) NOT NULL,
    shipping_fee DECIMAL(18, 2) DEFAULT 0,
    discount_amount DECIMAL(18, 2) DEFAULT 0,
    final_amount DECIMAL(18, 2) NOT NULL, -- total_amount - discount_amount + shipping_fee
    order_status SMALLINT NOT NULL DEFAULT 0 CHECK (order_status IN (0, 1, 2, 3, 4)), -- 0: Pending, 1: Confirmed, 2: Shipping, 3: Delivered, 4: Cancelled
    shipping_address TEXT,
    tracking_number VARCHAR(100),
    notes TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (buyer_id) REFERENCES "user"(user_id),
    FOREIGN KEY (contact_id) REFERENCES contact_info(contact_id),
    FOREIGN KEY (payment_method_id) REFERENCES payment_method(payment_method_id),
    FOREIGN KEY (voucher_id) REFERENCES voucher(voucher_id)
);

-- Indexes for performance
CREATE INDEX idx_order_buyer ON "order"(buyer_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_order_status ON "order"(order_status) WHERE is_deleted = FALSE;
CREATE INDEX idx_order_date ON "order"(order_date) WHERE is_deleted = FALSE;