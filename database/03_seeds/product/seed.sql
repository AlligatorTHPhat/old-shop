-- Reset và chèn dữ liệu mới với link video Drive thống nhất
INSERT INTO product (
    seller_id, 
    category_id, 
    title, 
    description, 
    price, 
    quantity, 
    weight_grams, 
    dimensions, 
    condition_rating, 
    warranty_months, 
    status, 
    transfer_method, 
    reject_reason,
    video_url
) VALUES
-- Status 1: Đang bán (Seller 3)
(3, 1, 'Laptop Dell Inspiron 15', 'Laptop đã qua sử dụng, cấu hình ổn định cho văn phòng và học tập.', 8500000.00, 55, 2200, '35x24x2 cm', 8, 6, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 1, 'iPhone 12 Pro Max 256GB', 'iPhone 12 Pro Max màu xanh Pacific, máy đẹp không vết xước.', 18500000.00, 42, 228, '16x7.8x0.7 cm', 9, 12, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 3, 'Áo khoác mùa đông', 'Áo khoác len dày, giữ ấm tốt cho mùa đông lạnh giá.', 350000.00, 100, 800, NULL, 7, 0, 1, 2, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 7, 'Tội ác và Hình phạt', 'Tác phẩm hiện sinh kinh điển của Dostoevsky, sách bìa cứng.', 800000.00, 35, 3500, '25x18x10 cm', 8, 0, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 6, 'Bếp điện cũ', 'Bếp điện gia dụng 2 vòng nhiệt, công suất lớn, nấu nhanh.', 500000.00, 31, 3000, '50x30x10 cm', 7, 0, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),

-- Status 1: Đang bán (Seller 4)
(4, 2, 'Bể cá thủy tinh', 'Bể cá cảnh kèm máy lọc mini, phù hợp để bàn làm việc.', 300000.00, 60, 5000, '40x25x25 cm', 8, 0, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 8, 'Giày sneakers cũ', 'Giày thể thao size 40, đế còn chắc chắn, ít sử dụng.', 200000.00, 45, 600, '30x15x10 cm', 6, 0, 1, 2, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 2, 'Bộ sofa cũ', 'Sofa da 3 chỗ ngồi, màu nâu sang trọng, còn mới 80%.', 2500000.00, 32, 45000, '200x80x80 cm', 7, 0, 1, 2, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(4, 6, 'Tủ lạnh cũ', 'Tủ lạnh mini 90L, tiết kiệm điện, phù hợp cho sinh viên.', 1200000.00, 38, 20000, '50x50x80 cm', 8, 3, 1, 2, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(4, 1, 'Bộ loa vi tính', 'Loa 2.1 âm thanh tốt, bass mạnh, nghe nhạc giải trí tuyệt vời.', 450000.00, 50, 2500, '30x20x20 cm', 8, 0, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 1, 'Máy ảnh cũ', 'Máy ảnh kỹ thuật số cầm tay, độ phân giải cao, kèm thẻ nhớ.', 1500000.00, 33, 400, '12x8x5 cm', 7, 0, 1, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),

-- Status 2: Bị từ chối (Rejected)
(3, 3, 'Áo sơ mi cũ', 'Áo sơ mi nam size M, chất liệu cotton thoáng mát.', 100000.00, 40, 200, NULL, 8, 0, 2, 1, 'Sản phẩm vi phạm quy định về chất lượng hình ảnh...', 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 2, 'Đèn ngủ cũ', 'Đèn bàn cổ điển, ánh sáng vàng ấm cúng.', 150000.00, 35, 800, '20x20x30 cm', 9, 0, 2, 1, 'Mô tả sản phẩm không trùng khớp với danh mục...', 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),

-- Status 3: Đã bán hết (Sold Out)
(3, 8, 'Giày tây cũ', 'Giày da nam size 41, phù hợp đi tiệc hoặc công sở.', 300000.00, 0, 700, '32x15x12 cm', 7, 0, 3, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),

-- Status 0: Đang chờ duyệt (Pending)
(3, 1, 'Flycam cũ', 'Drone DJI cũ hoạt động tốt, kèm 2 pin dự phòng.', 5500000.00, 31, 1200, '25x25x10 cm', 9, 6, 0, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link'),
(3, 8, 'Tai nghe Sony WH-1000XM4', 'Tai nghe chống ồn đỉnh cao, đầy đủ phụ kiện cáp sạc.', 4500000.00, 36, 254, '30x26x7 cm', 9, 24, 0, 1, NULL, 'https://drive.google.com/file/d/1XSL6bU3sBJRAs6o3zg4BcFiH8V9zsmCL/view?usp=drive_link');