-- categories.sql
CREATE TABLE category (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INTEGER REFERENCES category(category_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Indexes for performance
CREATE UNIQUE INDEX idx_category_name_active ON category(name) WHERE is_deleted = FALSE;
CREATE INDEX idx_category_parent ON category(parent_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_category_is_active ON category(is_active) WHERE is_deleted = FALSE;
CREATE INDEX idx_category_created_at ON category(created_at);
