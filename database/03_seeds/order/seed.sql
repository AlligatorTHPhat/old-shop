-- ===========================================================================
-- FULL SEEDING DATA: ORDERS, DETAILS, TRANSACTIONS (30 Records)
-- Đảm bảo khớp logic Product <-> Seller để né Trigger check_no_self_buying
-- ===========================================================================

-- 1. INSERT ORDERS (30 Records)
INSERT INTO "order" (buyer_id, contact_id, payment_method_id, total_amount, shipping_fee, final_amount, order_status, shipping_address) VALUES 
-- Đơn 1-10: User 7 mua của Seller 3 (Sử dụng Product 1)
(7, 1, 1, 150000, 30000, 180000, 3, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh'),
(7, 1, 2, 200000, 30000, 230000, 3, '45/10 Tô Hiến Thành, Phường 13, Quận 10, TP. Hồ Chí Minh'),
(7, 1, 3, 250000, 30000, 280000, 2, 'Số 8 Đại lộ Thăng Long, Mễ Trì, Nam Từ Liêm, Hà Nội'),
(7, 1, 4, 300000, 30000, 330000, 3, '210 Nguyễn Trãi, Phường Nguyễn Cư Trinh, Quận 1, TP. Hồ Chí Minh'),
(7, 1, 5, 350000, 30000, 380000, 4, 'Chung cư Him Lam, P. Tân Hưng, Quận 7, TP. Hồ Chí Minh'),
(7, 1, 1, 400000, 30000, 430000, 0, 'Sảnh A, Tòa nhà Landmark 81, Bình Thạnh, TP. Hồ Chí Minh'),
(7, 1, 2, 450000, 30000, 480000, 1, 'Số 12 Phan Xích Long, Phường 2, Phú Nhuận, TP. Hồ Chí Minh'),
(7, 1, 3, 500000, 30000, 530000, 2, 'Khu đô thị Sala, Mai Chí Thọ, Quận 2, TP. Hồ Chí Minh'),
(7, 1, 4, 550000, 30000, 580000, 3, '550 Cách Mạng Tháng 8, Phường 11, Quận 3, TP. Hồ Chí Minh'),
(7, 1, 5, 600000, 30000, 630000, 4, 'Hẻm 184 Nguyễn Xí, Phường 26, Bình Thạnh, TP. Hồ Chí Minh'),

-- Đơn 11-20: User 7 mua của Seller 4 (Sử dụng Product 6)
(7, 1, 1, 650000, 30000, 680000, 3, '102 Trần Hưng Đạo, Phường Cầu Ông Lãnh, Quận 1, TP. Hồ Chí Minh'),
(7, 1, 2, 700000, 30000, 730000, 1, 'Số 9 Võ Văn Ngân, Linh Chiểu, Thủ Đức, TP. Hồ Chí Minh'),
(7, 1, 3, 750000, 30000, 780000, 3, 'Biệt thự khu Ciputra, Phú Thượng, Tây Hồ, Hà Nội'),
(7, 1, 4, 800000, 30000, 830000, 3, '32 Đinh Tiên Hoàng, Phường Đa Kao, Quận 1, TP. Hồ Chí Minh'),
(7, 1, 5, 850000, 30000, 880000, 4, '99 Lê Văn Việt, Tăng Nhơn Phú A, Quận 9, TP. Hồ Chí Minh'),
(7, 1, 1, 900000, 30000, 930000, 0, '789 Quang Trung, Phường 12, Gò Vấp, TP. Hồ Chí Minh'),
(7, 1, 2, 950000, 30000, 980000, 1, 'Căn hộ B12, Flora Anh Đào, Quận 9, TP. Hồ Chí Minh'),
(7, 1, 3, 1000000, 30000, 1030000, 2, 'Số 1 Kim Mã, Ba Đình, Hà Nội'),
(7, 1, 4, 1100000, 30000, 1130000, 3, '22 Lý Tự Trọng, Bến Nghé, Quận 1, TP. Hồ Chí Minh'),
(7, 1, 5, 1200000, 30000, 1230000, 0, 'Số 5 Phố Huế, Hoàn Kiếm, Hà Nội'),

-- Đơn 21-25: User 3 (Buyer) mua của Seller 4 (Sử dụng Product 6) -> OK
(3, 2, 5, 2000000, 50000, 2050000, 3, '15 Đặng Văn Ngữ, Phường 10, Phú Nhuận, TP. Hồ Chí Minh'),
(3, 2, 4, 1800000, 50000, 1850000, 3, '442 Hùng Vương, Phường 12, Quận 6, TP. Hồ Chí Minh'),
(3, 2, 2, 1500000, 50000, 1550000, 1, '23 Lạc Long Quân, Phường 5, Quận 11, TP. Hồ Chí Minh'),
(3, 2, 1, 2200000, 50000, 2250000, 3, 'Khu dân cư Trung Sơn, Bình Hưng, Bình Chánh, TP. Hồ Chí Minh'),
(3, 2, 3, 3000000, 50000, 3050000, 4, 'Vinhomes Central Park, Phường 22, Bình Thạnh, TP. Hồ Chí Minh'),

-- Đơn 26-30: User 4 (Buyer) mua của Seller 3 (Sử dụng Product 1) -> OK
(4, 3, 2, 1200000, 40000, 1240000, 3, '88 Nguyễn Đình Chiểu, Phường 6, Quận 3, TP. Hồ Chí Minh'),
(4, 3, 5, 1400000, 40000, 1440000, 3, 'Tòa nhà Bitexco, Hải Triều, Quận 1, TP. Hồ Chí Minh'),
(4, 3, 4, 900000, 40000, 940000, 1, '12A Cao Thắng, Phường 2, Quận 3, TP. Hồ Chí Minh'),
(4, 3, 1, 500000, 40000, 540000, 0, 'Căn hộ Scenic Valley, Phú Mỹ Hưng, Quận 7, TP. Hồ Chí Minh'),
(4, 3, 3, 2500000, 40000, 2540000, 4, 'Số 2 Nguyễn Bỉnh Khiêm, Bến Nghé, Quận 1, TP. Hồ Chí Minh');


-- 2. INSERT ORDER DETAILS (Đã fix product_id theo đúng Seller để né trigger)
INSERT INTO "order_detail" (order_id, product_id, quantity, price_at_purchase, subtotal) VALUES 
-- Đơn 1-10: Buyer 7 mua của Seller 3 (Product 1)
(1, 1, 1, 150000, 150000), (2, 1, 1, 200000, 200000), (3, 1, 1, 250000, 250000), (4, 1, 1, 300000, 300000), (5, 1, 1, 350000, 350000), 
(6, 1, 1, 400000, 400000), (7, 1, 1, 450000, 450000), (8, 1, 1, 500000, 500000), (9, 1, 1, 550000, 550000), (10, 1, 1, 600000, 600000), 
-- Đơn 11-20: Buyer 7 mua của Seller 4 (Product 6)
(11, 6, 1, 650000, 650000), (12, 6, 1, 700000, 700000), (13, 6, 1, 750000, 750000), (14, 6, 1, 800000, 800000), (15, 6, 1, 850000, 850000), 
(16, 6, 1, 900000, 900000), (17, 6, 1, 950000, 950000), (18, 6, 1, 1000000, 1000000), (19, 6, 1, 1100000, 1100000), (20, 6, 1, 1200000, 1200000), 
-- Đơn 21-25: Buyer 3 mua của Seller 4 (Product 6) -> Hợp lệ
(21, 6, 1, 2000000, 2000000), (22, 6, 1, 1800000, 1800000), (23, 6, 1, 1500000, 1500000), (24, 6, 1, 2200000, 2200000), (25, 6, 1, 3000000, 3000000), 
-- Đơn 26-30: Buyer 4 mua của Seller 3 (Product 1) -> Hợp lệ
(26, 1, 1, 1200000, 1200000), (27, 1, 1, 1400000, 1400000), (28, 1, 1, 900000, 900000), (29, 1, 1, 500000, 500000), (30, 1, 1, 2500000, 2500000);


-- 3. INSERT TRANSACTIONS
INSERT INTO "transaction" (order_id, user_id, payment_method_id, amount, transaction_status, fraud_score, reference_number,balance_before,balance_after, address, created_at, updated_at) VALUES 
(1, 7, 1, 180000, 1, 0.05, 'REF-4F8876EB-01',1000000, 820000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(2, 7, 2, 230000, 1, 0.04, 'REF-4F8876EB-02',480000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(3, 7, 3, 280000, 1, 0.01, 'REF-4F8876EB-03',530000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(4, 7, 4, 330000, 1, 0.02, 'REF-4F8876EB-04',580000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(5, 7, 5, 380000, 4, 0.10, 'REF-4F8876EB-05',630000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(6, 7, 1, 430000, 0, 0.01, 'REF-4F8876EB-06', 680000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(7, 7, 2, 480000, 1, 0.00, 'REF-4F8876EB-07', 730000, 250000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(8, 7, 3, 530000, 1, 0.03, 'REF-4F8876EB-08', 830000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(9, 7, 4, 580000, 1, 0.11, 'REF-4F8876EB-09', 880000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(10, 7, 5, 630000, 4, 0.04, 'REF-4F8876EB-10', 930000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(11, 7, 1, 680000, 1, 0.05, 'REF-4F8876EB-11', 980000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(12, 7, 2, 730000, 1, 0.06, 'REF-4F8876EB-12', 1030000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(13, 7, 3, 780000, 2, 0.15, 'REF-4F8876EB-13', 1080000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(14, 7, 4, 830000, 1, 0.07, 'REF-4F8876EB-14', 1130000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(15, 7, 5, 880000, 4, 0.22, 'REF-4F8876EB-15', 1180000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(16, 7, 1, 930000, 0, 0.13, 'REF-4F8876EB-16', 1230000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(17, 7, 2, 980000, 1, 0.09, 'REF-4F8876EB-17', 1280000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(18, 7, 3, 1030000, 1, 0.11, 'REF-4F8876EB-18', 1330000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(19, 7, 4, 1130000, 1, 0.08, 'REF-4F8876EB-19', 1430000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(20, 7, 5, 1230000, 0, 0.12, 'REF-4F8876EB-20', 1530000, 300000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(21, 3, 5, 2050000, 1, 0.44, 'REF-4F8876EB-21', 7050000, 5000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(22, 3, 4, 1850000, 1, 0.33, 'REF-4F8876EB-22', 4850000, 3000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(23, 3, 2, 1550000, 1, 0.20, 'REF-4F8876EB-23', 5550000, 4000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(24, 3, 1, 2250000, 1, 0.11, 'REF-4F8876EB-24', 6250000, 4000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(25, 3, 3, 3050000, 4, 0.12, 'REF-4F8876EB-25', 7050000, 4000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(26, 4, 2, 1240000, 1, 0.13, 'REF-4F8876EB-26', 3240000, 2000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(27, 4, 5, 1440000, 1, 0.14, 'REF-4F8876EB-27', 3440000, 2000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(28, 4, 4, 940000, 1, 0.15, 'REF-4F8876EB-28', 2940000, 2000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(29, 4, 1, 540000, 0, 0.16, 'REF-4F8876EB-29', 2540000, 2000000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW()), 
(30, 4, 3, 2540000, 4, 0.17, 'REF-4F8876EB-30', 2540000, 10000, '123A Lê Lợi, Phường Bến Thành, Quận 1, TP. Hồ Chí Minh', NOW(), NOW());