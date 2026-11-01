-- Seed cho DB mới: giữ 16 sản phẩm gốc để các đơn hàng mẫu giữ đúng tham chiếu.
-- Phần generate_series bên dưới bổ sung 984 sản phẩm, tổng cộng đúng 1.000.
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

-- Tái sử dụng 16 mẫu hàng và ảnh gốc, thay tên/mã, giá, tồn kho và thông tin bán.
-- Mã SP-00017 .. SP-01000 nằm trong title vì schema hiện không có cột SKU.
-- Công thức chọn mẫu phải khớp 03_seeds/product_images/seed.sql:
-- source_product_id = 1 + ((product_id - 17) % 16).
-- Không dùng random(): mỗi lần khởi tạo mới có cùng phân bố dữ liệu.
WITH samples AS (
    SELECT
        n AS sample_no,
        1 + ((n - 1) % 16) AS source_product_id,
        (n - 1) / 16 AS batch_no,
        ((n - 1) * 7 + (n - 1) / 16) % 20 AS status_bucket,
        CURRENT_TIMESTAMP
            - (7 + (n * 13) % 359) * INTERVAL '1 day'
            - (n % 24) * INTERVAL '1 hour' AS listed_at
    FROM generate_series(1, 984) AS series(n)
), variants AS (
    SELECT samples.*,
        CASE
            WHEN status_bucket < 14 THEN 1  -- phần lớn đang bán
            WHEN status_bucket < 17 THEN 0  -- chờ duyệt
            WHEN status_bucket < 19 THEN 2  -- bị từ chối
            ELSE 3                         -- đã bán hết
        END AS product_status
    FROM samples
)
INSERT INTO product (
    seller_id, category_id, title, description, price, quantity, view_count,
    video_url, status, reject_reason, approved_by, is_deleted,
    created_at, updated_at, sold_at, weight_grams, dimensions,
    condition_rating, warranty_months, transfer_method
)
SELECT
    (ARRAY[3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15])[1 + (v.sample_no * 7) % 11],
    CASE
        -- Thêm hàng thời trang và đồ chơi để phủ đủ 8 danh mục hiện có.
        WHEN v.source_product_id IN (3, 14) AND v.batch_no % 2 = 1 THEN 4
        WHEN v.source_product_id = 15 THEN 5
        ELSE source.category_id
    END,
    format('%s - %s - SP-%s', source.title,
        (ARRAY['Bản tiêu chuẩn', 'Bản tiết kiệm', 'Bản sưu tầm', 'Bản kèm phụ kiện'])
            [1 + v.batch_no % 4],
        lpad((v.sample_no + 16)::text, 5, '0')),
    format('%s Mã hàng SP-%s. Tình trạng %s/10; %s. Dữ liệu mẫu phục vụ tìm kiếm, lọc và phân trang.',
        source.description, lpad((v.sample_no + 16)::text, 5, '0'),
        5 + (v.sample_no * 7) % 6,
        CASE WHEN v.sample_no % 2 = 0 THEN 'có thể giao hàng' ELSE 'ưu tiên nhận trực tiếp' END),
    round(source.price * (60 + (v.sample_no * 17) % 81) / 100.0, -3),
    CASE WHEN v.product_status = 3 THEN 0 ELSE 1 + (v.sample_no * 7) % 80 END,
    (v.sample_no * 37) % 5001,
    CASE WHEN v.sample_no % 3 = 0 THEN NULL ELSE source.video_url END,
    v.product_status,
    CASE WHEN v.product_status = 2 THEN
        (ARRAY['Ảnh chưa thể hiện đầy đủ tình trạng sản phẩm.',
               'Cần bổ sung thông tin nguồn gốc và phụ kiện.',
               'Mô tả cần được điều chỉnh trước khi đăng bán.'])[1 + v.sample_no % 3]
    END,
    CASE WHEN v.product_status IN (1, 3) THEN (ARRAY[2, 5, 6])[1 + v.sample_no % 3] END,
    v.sample_no % 29 = 0,
    v.listed_at,
    CASE WHEN v.sample_no % 4 <> 0 THEN v.listed_at + INTERVAL '1 day' END,
    CASE WHEN v.product_status = 3 THEN v.listed_at + INTERVAL '2 days' END,
    source.weight_grams,
    source.dimensions,
    5 + (v.sample_no * 7) % 6,
    CASE WHEN source.warranty_months > 0 THEN
        (ARRAY[0, 3, 6, 12, 24])[1 + v.batch_no % 5]
        ELSE 0
    END,
    1 + v.sample_no % 2
FROM variants v
JOIN product source ON source.product_id = v.source_product_id
ORDER BY v.sample_no;
