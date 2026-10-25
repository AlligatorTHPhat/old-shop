-- reviews.sql
CREATE TABLE review (
    review_id SERIAL PRIMARY KEY,
    product_id INT NOT NULL,
    buyer_id INT NOT NULL,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 0 AND 5),
    title VARCHAR(255),
    content TEXT,
    is_verified_purchase BOOLEAN NOT NULL DEFAULT FALSE,
    helpful_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (product_id) REFERENCES product(product_id),
    FOREIGN KEY (buyer_id) REFERENCES "user"(user_id)
);

-- Indexes for performance
CREATE INDEX idx_review_product ON review(product_id);
CREATE INDEX idx_review_buyer ON review(buyer_id);
CREATE INDEX idx_review_rating ON review(rating);
