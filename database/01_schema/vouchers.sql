-- vouchers.sql
CREATE TABLE voucher (
    voucher_id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255),
    discount_type SMALLINT NOT NULL DEFAULT 0,
    discount_value DECIMAL(18, 2) NOT NULL,
    max_usage INT,
    usage_count INT NOT NULL DEFAULT 0,
    min_order_amount DECIMAL(18, 2),
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE UNIQUE INDEX idx_voucher_code_active ON voucher(code) WHERE is_active = TRUE;
CREATE INDEX idx_voucher_valid_to ON voucher(valid_to) WHERE is_active = TRUE;
CREATE INDEX idx_voucher_created_at ON voucher(created_at);