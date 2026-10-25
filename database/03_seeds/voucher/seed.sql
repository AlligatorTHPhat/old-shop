-- seed.sql
INSERT INTO voucher (code, description, discount_type, discount_value, max_usage, usage_count, min_order_amount, valid_from, valid_to) VALUES
('SAVE10', 'Giảm 10%', 1, 10.00, 100, 0, 100.00, NOW(), '2026-12-31 23:59:59'),
('DISCOUNT50', 'Giảm 50k', 0, 50.00, 50, 0, 200.00, NOW(), '2026-06-30 23:59:59'),
('FREESHIP', 'Miễn phí vận chuyển', 0, 5.00, NULL, 0, 150.00, NOW(), '2026-05-01 23:59:59'),
('WELCOME20', 'Giảm 20%', 1, 20.00, 500, 0, 50.00, NOW(), '2026-12-31 23:59:59');