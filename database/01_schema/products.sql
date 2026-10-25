-- products.sql
CREATE TABLE product (
    product_id SERIAL PRIMARY KEY,
    seller_id INT NOT NULL,
    category_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(18, 2) NOT NULL CHECK (price >= 0),
    quantity INT NOT NULL CHECK (quantity >= 0),
    view_count INT NOT NULL DEFAULT 0,
    video_url VARCHAR(500),
    status SMALLINT NOT NULL DEFAULT 0 CHECK (status IN (0, 1, 2, 3)), -- 0: Pending, 1: Approved, 2: Rejected, 3: Sold Out
    reject_reason VARCHAR(500),
    approved_by INT,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    sold_at TIMESTAMP,
    weight_grams INTEGER,
    dimensions VARCHAR(50), -- e.g., "10x20x5 cm"
    condition_rating SMALLINT CHECK (condition_rating BETWEEN 1 AND 10), -- 1-10 scale
    warranty_months INTEGER DEFAULT 0,
    transfer_method SMALLINT NOT NULL DEFAULT 1 CHECK (transfer_method IN (1, 2)),
    FOREIGN KEY (seller_id) REFERENCES "user"(user_id),
    FOREIGN KEY (category_id) REFERENCES category(category_id),
    FOREIGN KEY (approved_by) REFERENCES "user"(user_id)
);

-- Indexes for performance
CREATE INDEX idx_product_seller ON product(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_product_category ON product(category_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_product_status ON product(status) WHERE is_deleted = FALSE;
CREATE INDEX idx_product_price ON product(price) WHERE is_deleted = FALSE;
CREATE INDEX idx_product_created_at ON product(created_at) WHERE is_deleted = FALSE;
CREATE INDEX idx_product_title ON product USING gin(to_tsvector('english', title)) WHERE is_deleted = FALSE;