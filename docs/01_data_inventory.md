# 01 — Bảng kiểm kê dữ liệu OldShop (Ngày 1)

> Nguồn: `database/01_schema/*.sql`, `02_functions/**`, `03_seeds/**`, `backend/app/models/*.py` (đọc ngày 27/10/2026).
> Phân loại: **C** = có cấu trúc (PG), **B** = bán cấu trúc (JSON/Mongo), **P** = phi cấu trúc (file/URL → MinIO; PG chỉ giữ khóa/metadata).
> Ước lượng kích thước = *số dòng mục tiêu (benchmark Ngày 4: ≥100k orders, 50k products)* × *byte/dòng ước lượng (gồm overhead tuple ~24B, chưa tính index)*. Đây là **ước lượng thô**, cần đo lại bằng `pg_total_relation_size` sau khi sinh dữ liệu.
> Review bổ sung 28/10/2026: đã đọc CRUD/API và kiểm số dòng seed bằng PostgreSQL 16.15;
> xem [DAY1_REVIEW.md](DAY1_REVIEW.md). Tần suất R/W vẫn là **đánh giá định tính**, chưa đo tải thực.
> Ký hiệu B/P thể hiện nội dung và mô hình đích đề xuất. Các cột int/varchar hiện tại
> vẫn là scalar có cấu trúc; lưu vào Mongo hoặc là văn bản tự do không tự biến kiểu SQL thành JSON.
> **D1–D6 đã chốt:** bảng đích dưới được đồng bộ với decisions.md; phần chi tiết product cũ
> vẫn PG ghi/Mongo nhận bản đọc trong MVP, chưa bỏ cột PG. Dung lượng chưa tính các bảng
> outbox/phân mảnh đích mới, cần đo lại sau migration.

## 1. Kiểm kê mức bảng

| Bảng | Dòng seed | Dòng mục tiêu | B/dòng | Ước lượng (MB) | Đọc/Ghi | Loại chủ đạo | Nhà đích |
|---|---:|---:|---:|---:|---|---|---|
| `user` | 15 | 50,000 | 700 | 35.0 | R cao / W thấp (last_login W vừa) | CP | PG (core + profile + secret + wallet) |
| `role` | 3 | 3 | 150 | 0.0 | R rất cao (cache) / W ~0 | C | PG |
| `user_role` | 15 | 50,000 | 8 | 0.4 | R cao / W thấp | C | PG, giữ nhiều role/user; FK về user_core |
| `category` | 8 | 50 | 200 | 0.0 | R rất cao / W ~0 | C | PG |
| `product` | 16 | 50,000 | 900 | 45.0 | R rất cao / W vừa (view_count, quantity) | BCP | PG lõi + Mongo product_details |
| `product_image` | 32 | 150,000 | 300 | 45.0 | R cao / W thấp | CP | PG (metadata + key) ; file -> MinIO |
| `voucher` | 4 | 100 | 150 | 0.0 | R vừa / W thấp | C | PG |
| `payment_method` | 5 | 5 | 60 | 0.0 | R cao / W ~0 | C | PG |
| `contact_info` | 15 | 100,000 | 350 | 35.0 | R vừa / W thấp | C | PG (nhóm PII, không sang Mongo) |
| `order` | 30 | 100,000 | 350 | 35.0 | W cao (tạo) + W vừa (đổi status) / R cao | BC | PG HASH(order_id), 4 partition; bản đọc -> Mongo order_snapshots |
| `order_detail` | 30 | 200,000 | 50 | 10.0 | W cao / R cao | C | PG chưa partition, giữ FK order_id |
| `transaction` | 30 | 120,000 | 300 | 36.0 | W vừa / R vừa | C | PG chưa partition, giữ UNIQUE reference_number; tóm tắt -> snapshot |
| `shopping_cart` | 11 | 50,000 | 24 | 1.2 | W rất cao / R cao | C | PG (reserve tồn kho -> không rời PG) |
| `shopping_cart_item` | 0 | 100,000 | 40 | 4.0 | W rất cao / R cao | C | PG |
| `review` | 0 | 150,000 | 400 | 60.0 | R cao / W vừa | BC | PG + Mongo reviews (bản đọc, thêm type/evidence) |
| `system_log` | 0 | 2,000,000 | 200 | 400.0 | W rất cao / R thấp | BC | PG RANGE(created_at)/tháng + Mongo bản sao TTL; chưa dọn PG trước khi xác minh đồng bộ |
| `violation_log` | 11 | 20,000 | 200 | 4.0 | W thấp / R vừa | C | PG (bản gốc) + Mongo (thêm actor/payload) |
| `system_feedback` | 0 | 20,000 | 500 | 10.0 | W thấp / R thấp | BC | PG + Mongo contact_messages (có file đính kèm -> MinIO) |
| **Tổng** | | | | **721** | | | |

Nhận xét: bảng lớn nhất khi scale là `system_log` (ghi liên tục, nhiều thao tác phát sinh log trong hàm/trigger), tiếp đến `order_detail`, `review`, `product_image`. Ảnh nhị phân (hàng chục KB–MB mỗi file; seed: 16 sản phẩm × 2 ảnh + 5 avatar ≈ 4,7 MB nén trong `database.zip`) **không** nằm trong PG — chỉ có đường dẫn.

## 2. Loại dữ liệu theo cột (chỉ các cột KHÔNG phải “cấu trúc thuần”)

| Bảng.cột | Loại | Hiện tại | Đích | Ghi chú |
|---|---|---|---|---|
| `user.avatar_url` | P | varchar(500) | MinIO `user-avatars/users/{id}/avatar.ext` + PG lưu key | /media/users/... |
| `product.description` | B | text | Mongo `product_details.description` | mô tả tự do -> Mongo |
| `product.video_url` | P | varchar(500) | Mongo `media.video_url` (link Drive ngoài; cân nhắc MinIO) | link Drive ngoài |
| `product.weight_grams` | B | int | Mongo `attributes.weight_g` | -> attributes |
| `product.dimensions` | B | varchar(50) | Mongo `attributes.dimensions{l,w,h,unit}` (parse chuỗi '35x24x2 cm') | chuỗi '35x24x2 cm' -> object |
| `product.condition_rating` | B | smallint | Mongo `condition.grade` | 1..10 -> condition |
| `product.warranty_months` | B | int | Mongo `condition.warranty_months` | -> condition |
| `product_image.image_url` | P | varchar(500) | MinIO `product-images/products/{product_id}/{uuid}.ext` + PG lưu key | /media/... -> MinIO key |
| `order.notes` | B | text | PG (ghi chú đơn) – không đưa sang Mongo trừ snapshot ẩn danh | ghi chú tự do |
| `review.content` | B | text | Mongo (review/contact) – giữ bản gốc ở PG | văn bản tự do |
| `system_log.details` | B | text | Mongo `payload` (parse JSON nếu có) | text tự do |
| `system_feedback.content` | B | text | Mongo (review/contact) – giữ bản gốc ở PG | form liên hệ |

**Phát hiện quan trọng:** `product` KHÔNG có cột JSON/thuộc tính động. “Thuộc tính động” (RAM/CPU/size/màu…) là dữ liệu **mới** cho Mongo, không phải di trú từ PG. Chỉ có 4 cột bán cấu trúc có sẵn (`weight_grams`, `dimensions`, `condition_rating`, `warranty_months`) + mô tả văn bản.

## 3. Dữ liệu nhạy cảm (phục vụ phân mảnh dọc & phân quyền)

| Nhóm | Cột | Mức | Xử lý đề xuất |
|---|---|---|---|
| **Bí mật xác thực (SEC)** | `user.password_hash`, `user.random_key`, `user.email_verification_token`, `user.password_reset_token/expires` | Rất cao | Bảng riêng user_secret; không sang Mongo/log/ETL |
| **Định danh nhà cung cấp thanh toán** | `transaction.provider_transaction_id` | Cao | Giữ ở transaction/PG; không phải cột user_secret, không đưa vào bản đọc phân tích mặc định |
| **Tài chính (FIN)** | `user.balance`, `transaction.amount/balance_before/balance_after`, `order.*_amount`, `product.price`, `voucher.*` | Cao | Ở PG (ACID). `user.balance` tách `user_wallet`; Mongo chỉ nhận số tiền tổng hợp (integer VND) |
| **PII liên lạc** | `user.email/phone_number/address/full_name`, `contact_info.*`, `order.shipping_address`, `transaction.address`, `system_feedback.guest_email` | Cao | Email giữ user_core phục vụ login; hồ sơ user_profile; sổ địa chỉ/giao dịch giữ PG. Snapshot chỉ giữ vùng đã chuẩn hóa khi có, không suy ra tùy tiện hay đưa địa chỉ/SĐT/email vào Mongo |
| **PII kỹ thuật** | `system_log.ip_address` | Trung bình | Hash/cắt octet cuối khi ETL; lưu ý đây là IP của client DB, không phải end-user |
| **Định danh nội bộ** | `username`, `trust_score`, `is_active` | Thấp–TB | `user_core` |

Địa chỉ giao hàng bị **nhân bản ở 3 nơi** (`contact_info`, `order.shipping_address`, `transaction.address`) và seed cho thấy chúng không đồng nhất → cần chọn 1 nguồn (đề xuất: `order.shipping_address` là snapshot bất biến; `transaction.address` bỏ/ẩn).

## 4. Cột ghi nóng (ảnh hưởng thiết kế)

`product.view_count` (mỗi lượt xem), `product.quantity` (reserve khi thêm giỏ), `shopping_cart.last_updated`, `shopping_cart_item.*`, `user.last_login`, `voucher.usage_count`, `system_log` (append). UPDATE tạo tuple version mới; chi phí thực còn phụ thuộc HOT/index/TOAST, cần benchmark trước khi kết luận lợi ích tách dọc `product_core`/mô tả hoặc `user_secret`/`user_profile`.

## 5. Bảng ánh xạ đã hiệu chỉnh (so với kế hoạch)

| Dữ liệu | Hiện tại | Đích | Hiệu chỉnh sau audit |
|---|---|---|---|
| user, role, user_role | PG | PG (user_core / user_profile / user_secret / user_wallet) | Ánh xạ đủ 20 cột; giữ user_role, không giới hạn mỗi user chỉ một role |
| category | PG | PG | 8 dòng, không có cây thực tế |
| product (id, seller, category, title, price, quantity, status…) | PG | PG, giữ tên bảng product | Nguồn sự thật tồn kho; chưa partition category; view_count giữ PG |
| mô tả dài, kích thước, tình trạng, bảo hành, **thuộc tính động (mới)** | PG (cột có sẵn) | **Mongo `product_details`** | Giai đoạn chuyển tiếp: giữ cột cũ (expand/contract) |
| product_image | PG + đĩa | PG (metadata + `object_key`) ; file → **MinIO** | Tên file ≠ product_id; key sinh từ DB |
| avatar | đĩa | **MinIO** | 11/15 avatar tham chiếu file không tồn tại trong seed |
| order, order_detail, transaction | PG | Order HASH(order_id); hai bảng con chưa partition | Giữ PK/FK và UNIQUE tài chính; xem D3 |
| order snapshot | — | **Mongo `order_snapshots`** | `order` thiếu `updated_at`/`seller_id` → xem D2 |
| review / report (rating=0) | PG | PG + **Mongo `reviews`** | `type` suy ra từ `rating=0`; thêm status/evidence ở Mongo |
| system_log | PG | PG RANGE theo tháng + Mongo bản sao TTL | Danh tính nguồn sau partition là (log_id,created_at); ETL outbox |
| violation_log | PG | PG + Mongo | Thiếu actor → Mongo bổ sung `actor_id` từ ngữ cảnh API |
| **contact_info** | PG | **PG (không sang Mongo)** | **Là sổ địa chỉ**, PII → chỉ PG (user_profile nhóm địa chỉ) |
| system_feedback (form liên hệ) | PG | PG + Mongo `contact_messages` (+ `attachments` MinIO) | Đây mới là “contact form” |
| shopping_cart(+item), voucher, payment_method | PG | PG | Không rời PG (reserve tồn kho) |

