-- contact_info.sql
CREATE TABLE contact_info (
    contact_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(15) NOT NULL,
    address VARCHAR(255) NOT NULL,
    province VARCHAR(100),
    district VARCHAR(100),
    ward VARCHAR(100),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(user_id)
);

-- Indexes for performance
CREATE INDEX idx_contact_info_user ON contact_info(user_id);
CREATE INDEX idx_contact_info_default ON contact_info(is_default) WHERE is_deleted = FALSE;
