-- Synthetic accounts only. No usable login password, wallet value, token or PII.
INSERT INTO role (role_id, role_name, description, created_at) VALUES
    (1, 'Admin', 'Synthetic administrator', '2026-11-01'),
    (2, 'Mod', 'Synthetic moderator', '2026-11-01'),
    (3, 'User', 'Synthetic seller', '2026-11-01');
INSERT INTO user_core (user_id, username, email, created_at) VALUES
    (101, 'seller_a', 'seller_a@example.invalid', '2026-11-01'),
    (103, 'empty_seller_a', 'empty_a@example.invalid', '2026-11-01'),
    (105, 'unused_seller_a', 'unused_a@example.invalid', '2026-11-01'),
    (202, 'seller_b', 'seller_b@example.invalid', '2026-11-01'),
    (204, 'empty_seller_b', 'empty_b@example.invalid', '2026-11-01'),
    (206, 'unused_seller_b', 'unused_b@example.invalid', '2026-11-01'),
    (900, 'moderator', 'moderator@example.invalid', '2026-11-01');
INSERT INTO user_profile (user_id, full_name) SELECT user_id, username FROM user_core;
INSERT INTO user_secret (user_id, password_hash, random_key)
    SELECT user_id, '!disabled', 'synthetic-' || user_id::text FROM user_core;
INSERT INTO user_wallet (user_id, balance) SELECT user_id, 0 FROM user_core;
INSERT INTO user_role (user_id, role_id)
    SELECT user_id, CASE WHEN user_id = 900 THEN 2 ELSE 3 END FROM user_core;
INSERT INTO seller_site VALUES (101, 'A'), (103, 'A'), (105, 'A'), (202, 'B'), (204, 'B'), (206, 'B');
INSERT INTO category (category_id, name, description, created_at) VALUES
    (1, 'Electronics', 'Shared reference', '2026-11-01'),
    (2, 'Books', 'Shared reference', '2026-11-01'),
    (3, 'Empty category', 'Intentionally empty', '2026-11-01');
