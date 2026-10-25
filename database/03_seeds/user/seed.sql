-- seed.sql
-- Insert users with properly hashed passwords
INSERT INTO "user" (username, email, password_hash, random_key, full_name, phone_number, address, email_verified, trust_score, avatar_url) 
VALUES 
('admin', 'admin@oldshop.com', crypt('admin123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Quản trị viên', '0901234567', '123 Lê Lợi, Q.1, TP.HCM', TRUE, NULL, '/media/users/user_1_admin.png'),
('mod1', 'mod1@oldshop.com', crypt('mod123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Trần Kim Lộc', '0912345678', '45 Nguyễn Huệ, Q.1, TP.HCM', TRUE, NULL, '/media/users/user_2_mod1.png'),
('user1', 'user1@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Nguyễn Văn An', '0908111222', '10 Pasteur, Q.1, TP.HCM', TRUE, 100.0, '/media/users/user_3_user1.png'),
('user2', 'user2@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Đoàn Thị Chí', '0908333444', '22 Võ Văn Tần, Q.3, TP.HCM', TRUE, 100.0, '/media/users/user_4_user2.png'),
('mod2', 'mod2@oldshop.com', crypt('mod123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Trần Văn Cường', '0907555666', '88 CMT8, Q.3, TP.HCM', TRUE, NULL, '/media/users/user_5_mod2.png'),
('mod3', 'mod3@oldshop.com', crypt('mod123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Lê Thị Mai', '0907778889', '12 Điện Biên Phủ, Bình Thạnh, TP.HCM', TRUE, NULL, '/media/users/user_6_mod3.png'),
('user3', 'user3@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Hoàng Văn Nam', '0933112233', '50 Nguyễn Đình Chiểu, Q.3, TP.HCM', TRUE, 95.0, '/media/users/user_7_user3.png'),
('user4', 'user4@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Đặng Ngọc Hân', '0933445566', '15 Nguyễn Thị Minh Khai, Q.1, TP.HCM', TRUE, 100.0, '/media/users/user_8_user4.png'),
('user5', 'user5@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Vũ Đình Phong', '0933667788', '200 Phan Xích Long, Phú Nhuận, TP.HCM', TRUE, 90.0, '/media/users/user_9_user5.png'),
('user6', 'user6@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Trần Hoàng Yến', '0944112233', '99 Hoàng Diệu, Q.4, TP.HCM', TRUE, 98.0, '/media/users/user_10_user6.png'),
('user7', 'user7@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Lý Quốc Bảo', '0944445566', '5 Lý Tự Trọng, Q.1, TP.HCM', TRUE, 92.0, '/media/users/user_11_user7.png'),
('user8', 'user8@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Phạm Minh Thư', '0955112233', '88 Đinh Tiên Hoàng, Q.1, TP.HCM', TRUE, 100.0, '/media/users/user_12_user8.png'),
('user9', 'user9@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Ngô Văn Tùng', '0955334455', '30 Nguyễn Huệ, Q.1, TP.HCM', TRUE, 88.0, '/media/users/user_13_user9.png'),
('user10', 'user10@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Đỗ Thị Lan', '0966112233', '120 Cách Mạng Tháng Tám, Q.10, TP.HCM', TRUE, 95.0, '/media/users/user_14_user10.png'),
('user11', 'user11@gmail.com', crypt('user123', gen_salt('bf', 8)), encode(gen_random_bytes(32), 'hex'), 'Bùi Văn Duy', '0966445566', '45 Lê Văn Sỹ, Q.3, TP.HCM', TRUE, 100.0, '/media/users/user_15_user11.png');

-- 1 = admin | 2 = moderator | 3 = seller/customer
INSERT INTO user_role (user_id, role_id) VALUES 
(1,1), (2,2), (3,3), (4,3), (5,2), (6,2), (7,3), (8,3), (9,3), (10,3), (11,3), (12,3), (13,3), (14,3), (15,3);