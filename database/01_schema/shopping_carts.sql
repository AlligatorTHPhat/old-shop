-- shopping_carts.sql
CREATE TABLE shopping_cart (
    cart_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES "user"(user_id)
);