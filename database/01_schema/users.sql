-- users.sql
CREATE TABLE "user" (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL, -- Increased length for hashed passwords
    random_key VARCHAR(64) NOT NULL UNIQUE, -- Increased length for better security
    full_name VARCHAR(100) NOT NULL,
    phone_number VARCHAR(15),
    address VARCHAR(255),
    balance DECIMAL(18, 4) NOT NULL DEFAULT 10000000.00,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    last_login TIMESTAMP,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    email_verification_token VARCHAR(255),
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP,
    trust_score DECIMAL(5,2) DEFAULT 0.0,
    avatar_url VARCHAR(500)
);

-- Indexes for performance and constraints
CREATE UNIQUE INDEX idx_user_username_active ON "user"(username) WHERE is_deleted = FALSE;
CREATE UNIQUE INDEX idx_user_email_active ON "user"(email) WHERE is_deleted = FALSE;
CREATE INDEX idx_user_created_at ON "user"(created_at);
CREATE INDEX idx_user_is_active ON "user"(is_active) WHERE is_deleted = FALSE;
CREATE INDEX idx_user_email_verified ON "user"(email_verified) WHERE is_deleted = FALSE;