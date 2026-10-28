# DAY 1 — NHẬT KÝ PHÁT HIỆN (handoff log)

> Cập nhật liên tục. Nếu hết token: đọc file này để biết đã làm gì / còn gì.
> Audit ban đầu: 27/10/2026 từ file upload. Review bổ sung: **28/10/2026**, đã có mã nguồn đầy đủ.
> **Trạng thái mới nhất:** hoàn tất kiểm chứng hiện trạng Ngày 1 trên PostgreSQL 16.15;
> pgAdmin4 cài sẵn là 9.18, SQL thuần được kiểm tra bằng driver đi kèm (chưa tự động thao tác GUI).
> Đọc [DAY1_REVIEW.md](DAY1_REVIEW.md) và [day1/verification.txt](day1/verification.txt)
> để xem kết quả mới nhất; các mục lịch sử bên dưới được hiệu chỉnh bởi bản review này.

## A. TRẠNG THÁI TIẾN ĐỘ
| Hạng mục | Trạng thái |
|---|---|
| Đọc KE_HOACH_NANG_CAP_7_NGAY.md | ✅ |
| Đọc PROJECT_GUIDE.md | ✅ |
| Đọc init.sql + database_config.sql | ✅ |
| Đọc 18/18 file `01_schema/*.sql` | ✅ |
| Đọc `02_functions/**` (password, triggers, audit, business, utility) | ✅ |
| Đọc seeds (11 file) | ✅ |
| Đọc models/*.py (6 file), constants.py, init_db.py | ✅ |
| `docs/01_data_inventory.md` | ✅; đã sửa số dòng violation_log theo DB thật |
| `docs/decisions.md` (D1–D11) | ✅ ĐỀ XUẤT; đã cập nhật căn cứ review, nhóm chưa phê duyệt |
| ERD (.png/.dot/.dbml/.mmd), conceptual model PNG, application model PNG | ✅ |
| Đọc CRUD/API/services/config/Compose/Nginx từng thiếu | ✅ 28/10; xem DAY1_REVIEW.md |
| Chạy init.sql trên PostgreSQL 16 | ✅ 16.15; hai database thử nghiệm riêng |
| Đối chiếu ERD với pg_catalog | ✅ DBML đã sửa: 18 bảng, 167 cột, 25 FK |
| Chạy smoke SQL / SQL thuần cho pgAdmin | ✅; database/verify_day1.sql và driver pgAdmin 9.18 |
| Tái xuất PNG từ DBML đã sửa | ⏳ PNG hiện là bản trước review |

## B. DANH SÁCH FILE ĐÃ ĐỌC
- uploads: KE_HOACH_NANG_CAP_7_NGAY.md, PROJECT_GUIDE.md, constants.py, init_db.py
- models.zip: __init__, user, cart, catalog, order, system
- database.zip: 02_functions/{user/password_functions, order_detail/triggers, system/audit_functions, system/business_functions, system/utility_functions}; 03_seeds/{role,category,payment_method,voucher,user,product,product_images,contact_info,shopping_cart,order,violation_logs}/seed.sql (media chỉ liệt kê tên file)
- database.zip: init.sql, config/database_config.sql, 01_schema/* (roles, users, user_roles, categories, products, product_images, vouchers, payment_methods, contact_info, orders, order_details, transactions, shopping_carts, shopping_cart_items, reviews, system_logs, system_feedback, violation_logs)
- Lúc audit upload ban đầu chưa có CRUD/API/services/config/Compose/frontend. **Đã đọc bổ sung 28/10**:
  `crud/{order,product,shopping_cart}.py`, `api/v1/{products,orders}.py`,
  `services/{storage,fraud_detection}.py`, `core/{config,database}.py`,
  root/deploy `docker-compose*.yml`, `frontend/nginx.conf`, cùng các file đối chiếu trong DAY1_REVIEW.md.

## C. PHÁT HIỆN QUAN TRỌNG (schema thật ≠ giả định trong kế hoạch)

### C1. Tên bảng/cột khác kế hoạch (phải sửa mọi nơi trong plan Ngày 2–5)
- Tên bảng **số ít**: `"user"`, `role`, `user_role`, `category`, `product`, `product_image`, `"order"`, `order_detail`, `transaction`, `shopping_cart`, `shopping_cart_item`, `review`, `system_log`, `system_feedback`, `violation_log`, `voucher`, `payment_method`, `contact_info`. (Kế hoạch dùng số nhiều: users, products, orders…)
- `"user"` và `"order"` là từ khóa SQL → luôn phải quote.
- Cột: `product.title` (plan: name), `product.quantity` (plan: stock), `order.order_date` (plan: created_at), `order.order_status`, `order.buyer_id`, `review.buyer_id` + `review.content` (plan: user_id/comment), `user.avatar_url`.
- `"order"` KHÔNG có `seller_id` và KHÔNG có `created_at/updated_at` → plan "orders (seller_id, status, created_at)" và watermark ETL `updated_at` cho order không dùng được. Seller suy ra qua order_detail→product.seller_id. Các bảng có `updated_at`: user, role, category, product, review, contact_info, transaction. Không có: order, order_detail, shopping_cart_item (chỉ `added_at`), system_log, violation_log, system_feedback, voucher.

### C2. Mâu thuẫn enum TransactionStatus (BUG tiềm ẩn)
- `transactions.sql` comment: 0 Pending, 1 Success, 2 Flagged, **3 Fraud**, **4 Failed**.
- `constants.py`: PENDING=0, SUCCESS=1, FLAGGED=2, **FAILED=3** (không có FRAUD/4).
→ Lệch. Cột không có CHECK constraint. Cần xác nhận với code thật (crud/order.py) trước khi chuẩn hóa. Ảnh hưởng ETL `payment.status` và báo cáo.

### C3. `contact_info` KHÔNG phải form liên hệ
- `contact_info` = **sổ địa chỉ** của user (user_id, full_name, phone, address, province/district/ward, is_default).
- Form liên hệ = `system_feedback` (user_id nullable, guest_email, subject, content, status 0/1/2).
→ Bảng ánh xạ trong plan ("contact_info, system_feedback → PG+Mongo bản có file đính kèm") và collection `contact_messages` cần sửa: contact_info là PII nhạy cảm, **không** đưa sang Mongo.

### C4. PII/nhạy cảm
- `"user"`: password_hash, random_key (UNIQUE, 64), email, phone_number, address, full_name, balance (ví, DEFAULT 10,000,000), email_verification_token, password_reset_token(+expires), trust_score, last_login.
- `contact_info`: full_name, phone_number, address, province/district/ward.
- `"order"`: shipping_address (TEXT snapshot PII), notes, tracking_number.
- `transaction`: address, provider_transaction_id (PayPal capture ID), reference_number, balance_before/after (tài chính), fraud_score.
- `system_log.ip_address`, `system_feedback.guest_email`.
- `user.balance` là dữ liệu tiền → phải ở PG (ACID), KHÔNG sang Mongo.

### C5. `product` đã có nhiều cột "thuộc tính", description là TEXT
- Có sẵn: description TEXT, video_url, weight_grams, dimensions (VARCHAR "10x20x5 cm"), condition_rating 1–10, warranty_months, transfer_method (1/2), reject_reason, approved_by, view_count (cột ghi nóng!), sold_at.
- **Không có** cột JSON/thuộc tính động (RAM/CPU…). → "thuộc tính động" là dữ liệu MỚI cho Mongo, không phải di chuyển từ PG. Mô tả dài + dimensions/weight/condition/warranty nên di chuyển sang `product_details`.
- `view_count`: ghi liên tục → cân nhắc đưa counter sang Mongo/Redis; giữ trong PG sẽ tạo dead tuples.
- Index FTS hiện có: `gin(to_tsvector('english', title))` (không phải pg_trgm) – tiếng Việt nên dùng `simple`/unaccent hoặc trgm. Cần xác minh crud/product.py dùng ILIKE hay FTS (chưa có file).

### C6. Ràng buộc/thiếu sót schema ảnh hưởng thiết kế phân mảnh (Ngày 2/4)
- `"order"` PK = `order_id` SERIAL. `order_detail.order_id` và `transaction.order_id` FK → `"order"(order_id)`. **Partition RANGE theo order_date đòi PK chứa order_date → FK đơn cột từ order_detail/transaction sẽ HỎNG** (PG không cho FK trỏ tới unique không chứa khóa phân mảnh). Giải pháp: PK (order_id, order_date) + thêm cột order_date vào bảng con (composite FK), hoặc bỏ FK/ dùng trigger kiểm tra, hoặc partition theo HASH(order_id)/ không partition order, chỉ partition transaction/log.
- `transaction.reference_number UNIQUE` → với partition theo created_at phải thành UNIQUE(reference_number, created_at) → mất tính duy nhất toàn cục.
- `transaction.order_id ... ON DELETE CASCADE` trong khi order dùng soft-delete (is_deleted).
- `shopping_cart_item`: KHÔNG có UNIQUE(cart_id, product_id) (plan Ngày 4 coi như cần thêm – đúng, nhưng phải dedupe dữ liệu cũ trước).
- `review`: không có UNIQUE(product_id, buyer_id), không có cột status/moderation, không có index (product_id, created_at). `rating=0` = report; không có cột phân biệt → type suy ra từ rating. Không có `evidence`.
- `user_role`: FK role_id không có index; không có `updated_at`.
- Trùng index: `"user".username/email` vừa UNIQUE cột vừa partial UNIQUE index (`WHERE is_deleted=FALSE`) → UNIQUE cột chặn tái sử dụng username của user đã xóa mềm (partial index vô nghĩa).
- `voucher`: `idx_voucher_code_active` unique partial (is_active) + code UNIQUE cột → tương tự.
- `payment_method`: không có created_at; seed order quyết định id (enum PaymentMethodId phụ thuộc thứ tự insert).
- `order.contact_id` FK → contact_info: xóa/sửa contact không được ảnh hưởng đơn cũ → đã có `shipping_address` snapshot (tốt).
- Tiền: `DECIMAL(18,2)` (VND) và `DECIMAL(18,4)` (user.balance, transaction) — không nhất quán scale; ETL phải chuẩn hóa sang integer VND.
- `transaction.fraud_score DECIMAL(5,2)`; `user.trust_score DECIMAL(5,2)`.
- Timestamps đều `TIMESTAMP` (không tz) trong khi session timezone = Asia/Ho_Chi_Minh → ETL sang Mongo phải chuyển UTC tường minh.
- `system_log.details TEXT` (có thể là JSON-as-text), `resource_id INT` — thiếu request_id. `violation_log` thiếu actor (moderator nào xử lý) và target resource.
- `system_log` BIGSERIAL (dự kiến lớn), các log khác SERIAL.

### C7. init.sql / bootstrap
- init.sql thứ tự: config → schema (roles, users, user_roles, categories, products, product_images, vouchers, payment_methods, contact_info, orders, order_details, transactions, carts, cart_items, reviews, system_logs, system_feedback, violation_logs) → functions (password, order_detail triggers, audit, business, utility) → seeds → ANALYZE.
- Dùng `\i` đường dẫn tương đối → phải chạy với cwd=database/ (init_db.py đã làm đúng: cwd=DATABASE_DIR).
- init.sql in ra NOTICE "Default admin: admin@oldshop.com / admin123" → mật khẩu seed lộ trong log/code (rủi ro nếu dùng ngoài dev).
- `init_db.py` (đã đọc): `schema_exists()` kiểm tra `to_regclass('public."user"')`; nếu có → bỏ qua init.sql. Không có bảng `schema_migrations` → cần runner riêng cho D6.
- `init_db.py` dùng `settings.DB_*` (không dùng DATABASE_URL) → rủi ro bootstrap đã nêu trong guide. `connect()` truyền `dbname=settings.DB_NAME`; `psql` cũng dùng DB_*. Nếu chỉ set DATABASE_URL → trỏ nhầm.
- `init_db.py` `sync_seed_media()` copy vào `settings.MEDIA_DIR` (đường dẫn đĩa) → sẽ cần thay bằng MinIO uploader (Pipeline 5) — rewrite thành idempotent theo key tồn tại.
- `init_db.py` phụ thuộc binary `psql` trong image backend.

### C8. Seed media
- 16 sản phẩm × 2 ảnh (`prod_{id}_{n}_{slug}.jpg`), 5 ảnh user (`user_1_admin.png`… `default.png`). Tổng zip database ≈ 4.7 MB. Tên có lỗi chính tả (`oldlamb`).


### C9. Triggers & functions (ràng buộc quan trọng)
- Chỉ có **2 trigger** toàn DB:
  1. `trg_no_self_buying` (BEFORE INSERT ON order_detail): SELECT buyer từ `"order"` WHERE order_id=…, seller từ `product`; chặn seller tự mua. → Nếu partition `"order"` theo `order_date`, truy vấn chỉ theo order_id **không pruning** (quét index của mọi partition) — chấp nhận được nhưng phải ghi chú; trigger vẫn chạy đúng nếu FK/PK được giữ.
  2. `trg_update_product_status` (BEFORE UPDATE ON product WHEN quantity đổi): quantity→0 ⇒ `status=3`, `sold_at=now`, ghi log; luôn set `updated_at`. **Không có** logic tăng lại status khi restock; ghi đè status kể cả khi sản phẩm đang PENDING/REJECTED.
- **KẾ HOẠCH SAI GIẢ ĐỊNH**: plan nói "trigger tồn kho". Thực tế comment trong triggers.sql: reserve/giải phóng tồn kho và `voucher.usage_count` do **tầng ứng dụng** (crud/shopping_cart.py, crud/order.py) xử lý, KHÔNG phải trigger. Trigger chỉ đổi status khi quantity=0.
- `updated_at` của product chỉ tự cập nhật bởi trigger khi quantity đổi (và ORM `onupdate`). UPDATE SQL thô các cột khác không set → **watermark ETL `updated_at` có thể bỏ sót thay đổi**.
- `log_system_action()` (SECURITY DEFINER) ghi vào `system_log` từ trong trigger/hàm. **BUG logic**: `check_no_self_buying` gọi log_system_action('SELF_BUY_BLOCKED') rồi `RAISE EXCEPTION` → rollback cả INSERT log → log chặn **không bao giờ được lưu**. Tương tự `authenticate_user` ghi LOGIN_FAILED rồi RAISE.
- `log_system_action` lấy `inet_client_addr()` = IP của **client DB (container backend)**, không phải IP người dùng; biến `user_agent` tính nhưng không dùng.
- `generic_audit_trigger()` dùng `NEW.id/OLD.id` — **không bảng nào có cột `id`** → sẽ lỗi nếu gắn trigger; hiện không có CREATE TRIGGER nào dùng nó (dead code).
- `clean_old_audit_logs(90)` DELETE cứng `system_log` > 90 ngày → khi ETL sang Mongo phải chạy ETL (watermark log_id) TRƯỚC khi cleanup, hoặc bỏ hàm này khi dùng TTL Mongo.
- `apply_voucher_to_order`: (a) `UPDATE "order" SET updated_at=…` nhưng `"order"` **không có cột updated_at** → lỗi runtime; (b) công thức `v_discount = calculate_order_total(...) - total_amount + discount_amount` cho ra **giá trị âm** (≈ −discount + shipping + discount cũ) → final_amount bị tăng; (c) tham số `VARCHAR(20)` vs voucher.code `VARCHAR(50)`. Nhiều khả năng là **dead code** (app xử lý voucher ở crud/order.py) – cần xác minh bằng grep (file crud không có trong upload).
- `calculate_order_total`: không kiểm tra `valid_from`; `min_order_amount` NULL → bỏ qua kiểm tra.
- `get_product_status_text(1)` = 'Active' (enum là APPROVED); `get_order_status_text` khớp OrderStatus.
- `generate_transaction_code()` = `TXN_YYYYMMDD_HHMMSS_RRRR` (4 số ngẫu nhiên → có thể trùng trong cùng giây, trong khi `reference_number` UNIQUE); seed lại dùng định dạng `REF-4F8876EB-NN`, comment schema ghi `ORD-12345` → 3 định dạng khác nhau.
- `hash_password` = pgcrypto bcrypt cost **8** (thấp); `create_user_with_hash` không gán role (app phải insert user_role); `authenticate_user` JOIN user_role (user nhiều role ⇒ nhiều dòng).
- `get_database_stats()` ước lượng row_count = n_tup_ins − n_tup_del (không chính xác) → dùng làm công cụ kiểm kê nhanh nhưng không dùng làm số đối chiếu ETL.
- `get_user_total_spending` / `get_seller_total_revenue` tính trực tiếp từ order/order_detail (hot aggregate) → ứng viên cho bảng tổng hợp ETL (Pipeline 6).

### C10. Dữ liệu seed — chất lượng & hệ quả cho các ngày sau
Số dòng seed (đã kiểm bằng DB thật 28/10): role 3, user 15, user_role 15, category 8, payment_method 5, voucher 4, product 16, product_image 32, contact_info 15, shopping_cart 11, shopping_cart_item 0, order 30, order_detail 30, transaction 30, **violation_log 11** (đính chính số 10), **review 0, system_log 0, system_feedback 0**.
- Quy mô nhỏ ⇒ benchmark Ngày 4 **bắt buộc sinh dữ liệu giả**.
- **Toàn bộ order_date/created_at = NOW() lúc seed** ⇒ partition RANGE theo thời gian chỉ có 1 partition có dữ liệu; cần generator trải đều thời gian.
- Chỉ 2 sản phẩm (id 1, 6) từng được bán; `price_at_purchase` (150k…3tr) **không khớp** `product.price` (laptop 8.5tr); quantity luôn 1.
- `order.contact_id` trỏ contact của **user khác** (buyer 7→contact 1 của admin; buyer 3→contact 2 của mod1; buyer 4→contact 3 của user1): schema **không ràng buộc** contact thuộc buyer.
- Địa chỉ nhân bản ở 3 nơi: `contact_info`, `order.shipping_address`, `transaction.address` (seed: address transaction giống nhau cho mọi đơn của buyer 7, khác shipping_address). 4/30 đơn giao Hà Nội ⇒ vùng (Nam/Bắc) chỉ suy ra được từ text `shipping_address`; **không có cột region**; contact_info seed toàn TP.HCM ⇒ phân mảnh theo vùng cần thêm cột/derive.
- Phân bố `payment_method_id` đều 6/6/6/6/6 cho COD/MOMO/VNPAY/PAYPAL/BANK ⇒ 24/30 đơn dùng phương thức mà guide nói **chưa triển khai** (MoMo/VNPay/Bank) → seed ≠ thực tế; phân bố order_status: 0:4, 1:5, 2:3, 3:13, 4:5.
- Transaction status trong seed: 1:20, 4:5, 0:4, 2:1 ⇒ **giá trị 4 xuất hiện 5 lần** (khớp 5 đơn cancelled) nhưng `constants.TransactionStatus` không có 4 ⇒ xác nhận C2 (SQL comment: 4=Failed, 3=Fraud; Python: 3=Failed). `TransactionStatus(4)` sẽ ném ValueError nếu dùng để parse.
- `balance_before/after` không nối chuỗi giữa các giao dịch liên tiếp của cùng user (tx1 after 820000, tx2 before 480000).
- Seed `voucher`: `discount_value`/`min_order_amount` là 50.00/200.00… trong khi giá sản phẩm là VND đầy đủ (hàng triệu) ⇒ **lệch đơn vị** ("Giảm 50k" lưu 50.00); `FREESHIP` là fixed discount 5.00 chứ không miễn ship; `DISCOUNT50` (hết hạn 2026-06-30) và `FREESHIP` (2026-05-01) **đã hết hạn** so với hôm nay 27/10/2026; `SAVE10`, `WELCOME20` hết hạn 2026-12-31; `valid_from = NOW()` không tất định. Không có đơn nào dùng voucher (voucher_id NULL toàn bộ).
- `role_name`: 'Admin','Mod','User' (không phải 'Moderator'); id phụ thuộc thứ tự INSERT (SERIAL) — `RoleId`, `PaymentMethodId` dựa vào đó.
- Users: id1 admin, id2/5/6 moderator (mod1–3), id3,4,7–15 role USER; **seller thực tế chỉ user 3 (13 sản phẩm) và user 4 (3 sản phẩm)** ⇒ HASH(seller_id) lệch nặng. Mọi user đúng 1 role (ORM docstring cũng nói vậy).
- Seed user trỏ avatar `/media/users/user_{1..15}_*.png` nhưng thư mục media chỉ có `user_1..user_4` + `default.png` ⇒ **11 avatar tham chiếu file không tồn tại** (user 5–15). ETL media phải xử lý thiếu file (log + fallback default.png), không được crash.
- **Tên file ảnh sản phẩm lệch product_id**: product 3 (áo khoác) → `prod_4_*_coat.jpg`; product 4 → `prod_5_*`; … product 15 → `prod_16_*`; product 16 (tai nghe) → `prod_3_*_headphone.jpg`. ⇒ KHÔNG suy product_id từ tên file; key MinIO `products/{product_id}/{uuid}.{ext}` phải sinh từ bảng `product_image.product_id`.
- 16/16 sản phẩm dùng cùng 1 `video_url` Google Drive (placeholder) — dữ liệu phi cấu trúc nằm ngoài hệ thống (link ngoài).
- Phân bố category sản phẩm: cat1:5, cat2:3, cat3:2, cat6:2, cat7:1, cat8:3; **cat 4 (Thời trang), 5 (Đồ chơi) rỗng**; `category` có `parent_id` nhưng seed không có cây (tất cả root).
- Phân bố status sản phẩm: APPROVED 11 (id1–11), REJECTED 2 (id12–13), SOLD_OUT 1 (id14, qty 0 — nhất quán với trigger), PENDING 2 (id15–16). Tai nghe Sony (id16) nằm category 8 'Phụ kiện' thay vì điện tử.
- `shopping_cart_item` seed rỗng; carts seed cho user 3,4,7–15.
- `violation_log` seed bắt đầu bằng `TRUNCATE TABLE violation_log RESTART IDENTITY` (phá hủy dữ liệu nếu chạy lại seed trên DB đã có dữ liệu); không lưu **actor** (moderator xử lý), `user_id` = đối tượng bị xử lý; action_taken thực tế: DEACTIVATE, ACTIVATE, DEACTIVATE_MODERATOR, ACTIVATE_MODERATOR (comment ORM nói BAN/DEACTIVATE/PRODUCT_REMOVAL).

### C11. Lệch ORM ↔ SQL (cần đồng bộ khi migration Ngày 4)
- **Múi giờ**: ORM `default=datetime.utcnow` (UTC, naive) vs SQL `DEFAULT CURRENT_TIMESTAMP` + `SET timezone='Asia/Ho_Chi_Minh'` (giờ VN, naive) — **cột TIMESTAMP trong cùng bảng trộn UTC (ORM insert) và UTC+7 (seed/SQL/function)**. Nghiêm trọng cho watermark ETL, partition theo thời gian và báo cáo "theo ngày".
- Độ chính xác tiền: SQL `transaction.amount/balance_*` DECIMAL(18,4) ↔ ORM DECIMAL(18,2); `user.balance` (18,4).
- `transaction.reference_number`: SQL UNIQUE ↔ ORM không khai báo; `transaction_status` SQL NOT NULL ↔ ORM nullable; `review.is_verified_purchase`, `helpful_count`, `product.view_count` NOT NULL (SQL) ↔ ORM nullable.
- `SystemLog.log_id` ORM Integer ↔ SQL BIGSERIAL.
- `ProductImage`: SQL `ON DELETE CASCADE` ↔ ORM cascade ở tầng Python. `Product.reviews/cart_items` cascade `all, delete-orphan` trong ORM (nguy hiểm nếu hard-delete).
- ORM Product/Order… không map index GIN FTS `idx_product_title`.
- `User.updated_at`, `Category.updated_at`… dùng `onupdate` ORM ⇒ SQL thô không cập nhật.
- ORM `User.role_id` property: "một user đúng một role" ⇒ có thể denormalize `role_id` vào `users_core` ở phân mảnh dọc nhưng phải giữ `user_role` để tương thích `authenticate_user`.

### C12. Ràng buộc chưa có & việc cần ở Ngày 4
- Không có UNIQUE(cart_id, product_id) → dedupe trước khi thêm; không có UNIQUE(product_id, buyer_id) cho review (có thể cố ý: 1 buyer vừa review vừa report); không có CHECK `transaction_status`, `voucher.discount_type`, `system_feedback.status`; không có index `user_role(role_id)`, `order(contact_id)`, `order(payment_method_id)`, `order(voucher_id)`, `product(approved_by)`, `transaction(reference_number)` (có UNIQUE), `review(product_id, created_at)`.
- Index FTS `to_tsvector('english', title)` không phù hợp tiếng Việt; plan đề xuất trgm GIN (extension đã bật) — cần xác minh truy vấn thực tế (ILIKE vs to_tsquery) ở crud/product.py (**không có trong upload**).
- Cột "nóng" ghi liên tục: `product.view_count`, `product.quantity`, `shopping_cart.last_updated`, `user.last_login`, `voucher.usage_count`.

## D. NHỮNG GÌ TỪNG CHƯA XÁC MINH (audit upload ban đầu)
**Đã bổ sung review 28/10** cho các mục dưới; xem DAY1_REVIEW.md. Những rủi ro
cạnh tranh/API mới ghi nhận từ đọc code chưa được coi là đã kiểm thử runtime.
- Cách app thực sự dùng enum TransactionStatus/voucher/stock (cần crud/order.py, crud/shopping_cart.py).
- Truy vấn nóng thật (crud/product.py…), tham số lọc (api/v1/products.py).
- storage.py: extension cho phép, cách đặt tên file ảnh; `main.py` mount /media; nginx.conf.
- config.py: tên biến DB/DATABASE_URL; database.py: pool, timezone phiên.
- docker-compose*: volume/tuning PG.


## E. SẢN PHẨM ĐÃ TẠO (đường dẫn trong /mnt/user-data/outputs/docs/design/)
- `01_erd_current.png` (+ `.dot`, `.dbml` cho dbdiagram.io, `.mmd` Mermaid) — 18 bảng, PK/FK/UQ/PII/SEC, FK nullable = nét đứt.
- `01_conceptual_model.png` (+ `.dot`) — thực thể–quan hệ–bản số, tô màu theo nơi lưu (PG/Mongo/MinIO/hỗn hợp).
- `01_application_model.png` (+ `.dot`) — router FastAPI → PG/Mongo/MinIO, nét ETL.
- `01_data_inventory.md` — kiểm kê bảng/cột, kích thước ước lượng, nhạy cảm, bảng ánh xạ hiệu chỉnh.
- `decisions.md` — D1–D6 + D7 (timestamptz/UTC), D8 (enum TransactionStatus), D9 (contact_info ở PG), D10 (view_count), D11 (dead code DB).
- `_src/` — script sinh (schema_data.py là nguồn duy nhất; sửa rồi chạy lại gen_*.py; cần graphviz `dot`).

## F. SAI LỆCH SO VỚI KẾ HOẠCH (nhắn các ngày sau)
1. Tên bảng/cột thực tế (số ít; `title`, `quantity`, `order_date`, `buyer_id`…) — sửa SQL migration/ETL mẫu trong plan.
2. Tồn kho/voucher KHÔNG nằm trong trigger (chỉ trigger đổi status khi quantity=0 và chặn tự mua).
3. `contact_info` ≠ form liên hệ.
4. `"order"` không có seller_id/created_at/updated_at.
5. Partition `"order"` phá FK đơn cột (order_detail, transaction) → chọn A/B/C ở D3.
6. Audit ban đầu chưa chạy PG. **Review 28/10 đã chạy init và verify_day1.sql**;
   số dòng seed/schema đã đo thật, còn kích thước và tần suất R/W vẫn là ước lượng.

## G. VIỆC CÒN LẠI CHO NGÀY 1 / HANDOFF
- [ ] Nhóm review ERD + bảng kiểm kê + chốt D1–D11 (đặc biệt D3 phương án A/B/C, D7, D8).
- [x] Đọc các file từng thiếu, xác minh enum/stock/voucher/truy vấn/ảnh/config/Compose/Nginx; kết quả tại DAY1_REVIEW.md.
- [x] Chạy init.sql trên PG16.15; đối chiếu ERD với pg_catalog và sửa DBML.
- [x] Kiểm tra SQL thuần bằng driver pgAdmin4 9.18; lưu script sinh và script kiểm chứng.
- [ ] Ngày 2 bắt đầu từ D3/D4/D5; dùng mục C6, C10 làm đầu vào.
