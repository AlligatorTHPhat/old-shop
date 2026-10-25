-- payment_methods.sql
CREATE TABLE payment_method (
    payment_method_id SERIAL PRIMARY KEY,
    method_name VARCHAR(50) NOT NULL UNIQUE,
    is_online BOOLEAN NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);