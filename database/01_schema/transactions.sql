CREATE TABLE transaction (
    transaction_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL,
    user_id INT NOT NULL,
    payment_method_id INT NOT NULL,
    
    -- Dữ liệu tài chính (Chuẩn PaySim: amount, oldbalanceOrg, newbalanceOrig)
    amount DECIMAL(18, 4) NOT NULL CHECK (amount >= 0),
    balance_before DECIMAL(18, 4) DEFAULT 0.0000, 
    balance_after DECIMAL(18, 4) DEFAULT 0.0000,
    
    -- Trạng thái
    -- 0: Pending (Khởi tạo)
    -- 1: Success (Thành công)
    -- 2: Flagged (Nghi vấn gian lận - Do AI đánh dấu)
    -- 3: Fraud (Xác nhận gian lận - Chặn giao dịch)
    -- 4: Failed (Lỗi hệ thống/PayPal từ chối)
    transaction_status SMALLINT NOT NULL DEFAULT 0,
    
    -- AI & Security
    fraud_score DECIMAL(5, 2) DEFAULT 0.00, -- Thang điểm rủi ro
    
    -- Identity & Tracking
    reference_number VARCHAR(100) UNIQUE,   -- Mã đơn hàng nội bộ (ví dụ: ORD-12345)
    provider_transaction_id VARCHAR(100),    -- ID trả về từ PayPal (Capture ID)
    address TEXT,
    
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (order_id) REFERENCES "order"(order_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES "user"(user_id),
    FOREIGN KEY (payment_method_id) REFERENCES payment_method(payment_method_id)
);

CREATE INDEX idx_transaction_order ON transaction(order_id);
CREATE INDEX idx_transaction_user ON transaction(user_id);
CREATE INDEX idx_transaction_status ON transaction(transaction_status);
CREATE INDEX idx_transaction_fraud_score ON transaction(fraud_score);