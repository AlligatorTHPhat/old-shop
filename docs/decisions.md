# decisions.md — Quyết định thiết kế (Ngày 1, 27/10/2026)

> Trạng thái: **ĐỀ XUẤT sau audit — chờ nhóm review & chốt**. Mỗi quyết định ghi: đề xuất, lý do, **điều chỉnh so với kế hoạch gốc** (do phát hiện khi đọc schema thật), rủi ro.
> Căn cứ: `01_data_inventory.md`, `DAY1_FINDINGS_LOG.md` (mục C).
> **Review bổ sung 28/10/2026:** đã đối chiếu mã đầy đủ, init trên PostgreSQL 16.15
> và SQL thuần qua driver pgAdmin4 9.18; xem [DAY1_REVIEW.md](DAY1_REVIEW.md).
> Chốt baseline audit; các phương án thiết kế dưới đây chưa được coi là đã triển khai/phê duyệt.

## D1 — Nguồn sự thật
**Đề xuất:** PostgreSQL là SoT cho mọi dữ liệu giao dịch: `user_wallet.balance`, `product.quantity`, `shopping_cart*`, `order*`, `transaction`, `voucher.usage_count`.
**Điều chỉnh:** tách 2 loại Mongo:
- **Read model** (sinh bằng ETL, có thể xóa dựng lại): `order_snapshots`, `reviews` (bản đọc), `system_logs` (bản sao).
- **Authoritative trong Mongo** (SoT mới): `product_details.attributes/tags` (dữ liệu *mới*, không có trong PG) và `contact_messages.attachments`.
Với mô tả/kích thước/tình trạng/bảo hành (đang là cột PG): dùng **expand/contract** — giữ cột PG đến khi API Ngày 6 đọc từ Mongo ổn định, rồi mới bỏ (migration riêng).
**Lý do:** trigger/reserve tồn kho nằm ở app + PG; Mongo không bảo đảm ACID đa tài liệu theo cách đồng bộ với PG.
**Rủi ro:** hai nguồn cho cùng một field trong giai đoạn chuyển tiếp → ghi rõ field nào “PG ghi, Mongo đọc”.

## D2 — Đồng bộ PG → Mongo
**Đề xuất:** ETL batch + incremental theo watermark (MVP); CDC là hướng mở rộng.
**Điều chỉnh bắt buộc (phát hiện khi audit):** watermark `updated_at` **không dùng được nguyên trạng**:
| Bảng | Vấn đề | Giải pháp (migration 001) |
|---|---|---|
| `"order"` | **không có** `updated_at`/`created_at` | thêm `updated_at` + trigger `set_updated_at()` |
| `order_detail` | không có timestamp; app hiện tạo một lần nhưng DB không cấm sửa/xóa | lan truyền thay đổi tới order hoặc cơ chế dirty/outbox; quy định tính bất biến nếu chọn |
| `product` | `updated_at` chỉ do trigger khi `quantity` đổi; SQL thô không set | thêm trigger `BEFORE UPDATE` chung `set_updated_at()` cho product/user/review/… |
| `system_log`, `violation_log` | chỉ `created_at`; sequence cấp ID không theo thứ tự commit | thiết kế cửa sổ quét lại + đối soát hoặc outbox/CDC; không dùng MAX(id) đơn thuần làm bảo đảm không mất log |
| `system_feedback`, `shopping_cart_item` | chỉ `created_at`/`added_at` nhưng có sửa/xóa | bổ sung theo dõi cập nhật/xóa nếu đồng bộ; không chỉ watermark id/created_at |
**Snapshot đơn:** thay đổi transaction/order_detail phải làm snapshot được dựng lại;
chỉ thêm trigger updated_at trên order không đủ. Product attributes/tags do Mongo quản lý
phải được giữ khi ETL cập nhật phần có nguồn từ PG.
**Múi giờ:** xem D7 — nếu không xử lý, watermark so sánh trên dữ liệu trộn UTC/UTC+7.
**Thứ tự với `clean_old_audit_logs(90)`:** ETL log phải chạy trước hàm này, hoặc vô hiệu hóa hàm khi Mongo TTL tiếp quản.
**Xóa mềm:** `is_deleted` được ETL chuyển thành `deleted: true` (upsert), không xóa document.

## D3 — Phân mảnh ngang
**Đề xuất gốc:** `orders`, `transactions` RANGE theo thời gian; `products` LIST theo `category_id`.
**Vấn đề thực tế:**
1. `"order"` PK=`order_id`; `order_detail`/`transaction` có FK → `"order"(order_id)`. PG yêu cầu PK/UNIQUE của bảng partition **chứa khóa phân mảnh** ⇒ PK phải thành `(order_id, order_date)` và **FK đơn cột sẽ hỏng**.
2. `transaction.reference_number UNIQUE` không còn duy nhất toàn cục nếu partition theo `created_at`.
3. Seed: mọi `order_date`/`created_at` = lúc seed ⇒ chỉ 1 partition có dữ liệu (cần generator Ngày 4).
4. `product` seed phân bố category lệch (cat1:5, cat2:3, cat8:3, cat4/5: 0); LIST theo category cần DDL mỗi khi admin thêm category; đổi `category_id` làm dòng **di chuyển giữa partition**.
5. `HASH(seller_id)` lệch nặng (seller 3 có 13/16 sản phẩm).
6. Partition `product` theo category_id cũng xung đột PK(product_id) và FK từ
   product_image/review/shopping_cart_item/order_detail. DEFAULT partition chỉ xử lý
   category mới, không giải quyết khóa. Partition transaction theo thời gian còn
   phải sửa PK(transaction_id), ngoài vấn đề reference_number.

**Phương án cho `order` (chọn 1, nhóm quyết định):**
| | Mô tả | Giữ FK | Pruning thời gian | Chi phí |
|---|---|---|---|---|
| **A (đề xuất)** | RANGE(`order_date`) theo quý; PK `(order_id, order_date)`; thêm `order_date` vào `order_detail` & `transaction` (co-located, partition cùng RANGE), FK composite `(order_id, order_date)` | Có | Có | Sửa ORM/CRUD (thêm cột), backfill, reference_number cần bảng phụ/chấp nhận unique theo partition |
| B | HASH(`order_id`) | Có (PK chứa order_id) | Không | Ít thay đổi nhất, nhưng không demo được pruning theo thời gian/archival |
| C | Không partition `order`; chỉ partition `system_log`/`transaction` | Một phần | Có (log) | Yếu về yêu cầu “phân mảnh đơn hàng” |
**Trigger `trg_no_self_buying`** tra `"order"` theo `order_id` đơn thuần → với A sẽ quét index mọi partition (không pruning) — chấp nhận ở quy mô đồ án; có thể đổi truy vấn thành join theo `(order_id, order_date)` mới.

**`product`:** đề xuất **LIST(`category_id`) kèm partition DEFAULT** (category mới không gây lỗi) để minh họa phân mảnh theo vị từ; *hoặc* không partition và chỉ phân mảnh dọc (hợp lý hơn kỹ thuật với 50k dòng). Ghi rõ trade-off trong báo cáo.
**Phân vùng địa lý (Nam/Bắc, FDW):** hiện **không có cột `region`**; chỉ suy ra từ text `order.shipping_address` (seed: 4/30 đơn Hà Nội) hoặc `contact_info.province`. Nếu làm, cần thêm cột `region` (derive khi insert) — để dưới thứ tự cắt giảm.
**Mongo:** shard key `product_details {category_id:1, product_id:1}`; logs hashed `_id` (chỉ trình bày thiết kế nếu không đủ thời gian).

## D4 — Phân mảnh dọc
**Điều chỉnh so với kế hoạch (2 → 4 mảnh cho users):**
| Mảnh | Cột | Lý do |
|---|---|---|
| `user_core` | user_id, username, email, is_active, is_deleted, email_verified, trust_score, created_at, updated_at, last_login, (role_id) | Nóng, đọc mỗi request, hẹp |
| `user_profile` | user_id, full_name, phone_number, address, avatar_key | PII, nguội |
| `user_secret` | user_id, password_hash, random_key, email_verification_token, password_reset_token, password_reset_expires | Bí mật, quyền tối thiểu |
| `user_wallet` | user_id, balance, updated_at | Tài chính, tranh chấp khóa dòng riêng |
View `users_full` ghép lại để ORM/CRUD thay đổi ít.
**Kiểm tra 3 tính chất cần hoàn tất ở Ngày 2:** bảng phân bổ cột phải chứng minh
đầy đủ/tái tạo/không chồng lặp. Bản dự kiến trên thêm updated_at cho wallet và cân nhắc role_id;
email là PII đang được giữ trong core. Chưa đánh dấu đã chứng minh cho mô hình đích.
**`product`:** `product_core` (PG) + `product_details` (Mongo: description, attributes, condition, dimensions parse thành object, tags, images[]) + ảnh (MinIO). `view_count` → xem D10.
**Lưu ý ORM:** `User` hiện map một bảng; đổi sang view cần `Table`/mapper mới hoặc viết `INSTEAD OF` trigger — phải thử với toàn bộ test.

## D5 — Phân tán
**Đề xuất giữ nguyên:** PG primary + 1 streaming replica (đọc/báo cáo); Mongo replica set 3 node; MinIO 4 drive (erasure coding). Node-B FDW chỉ làm nếu D3 chọn phân vùng địa lý (đầu danh sách cắt giảm).
**Lưu ý từ audit:** replica PG là *async* → báo cáo đọc có độ trễ; dữ liệu giao dịch/ví/tồn kho luôn đọc từ primary.

## D6 — Migration
**Đề xuất:** `database/04_migrations/NNN_*.sql` + bảng `schema_migrations(version, applied_at, checksum)` + runner `backend/scripts/migrate.py`.
**Điều chỉnh:**
- `init.sql` coi là **baseline (v0)**; sau baseline (cả DB mới lẫn DB cũ) luôn chạy các migration chưa áp dụng ⇒ một đường duy nhất cho dev/test/CI.
- `init_db.py` hiện: `schema_exists()` (kiểm tra `public."user"`) ⇒ bỏ qua init.sql; thêm bước `run_migrations()` **sau** nhánh này.
- Sửa lệch bootstrap: `init_db.py` đọc `settings.DB_*` (không đọc `DATABASE_URL`) ⇒ parse `DATABASE_URL` vào `DB_*` trong `config.py`, hoặc init_db dùng URL.
- Migration phải idempotent/có khóa advisory để tránh 2 container chạy song song.
- `04_migrations` đi cùng baseline mới cho DB test (CI chạy init.sql rồi migrate).

## Quyết định bổ sung (phát sinh từ audit — đề nghị chốt cùng D1–D6)
### D7 — Chuẩn hóa thời gian
**Vấn đề:** ORM ghi `datetime.utcnow` (UTC), SQL/seed ghi `CURRENT_TIMESTAMP` theo `Asia/Ho_Chi_Minh`; cột là `TIMESTAMP` không tz ⇒ cùng cột chứa 2 hệ giờ.
**Đề xuất:** chuyển sang `timestamptz`, giữ giờ lưu = UTC; ORM dùng `DateTime(timezone=True)`; ETL luôn xuất UTC. Phải làm **trước** khi đặt biên partition theo `order_date`. (Dữ liệu cũ: gán `AT TIME ZONE` theo nguồn ghi — chỉ phân biệt được bằng quy ước; seed = giờ VN.)
### D8 — Enum `TransactionStatus`
**Vấn đề:** SQL comment: 3=Fraud, 4=Failed; `constants.py`: 3=FAILED, không có 4; seed dùng **4** (5 dòng).
**Đã xác minh 28/10:** CRUD tạo PENDING=0; API PayPal ghi SUCCESS=1/FLAGGED=2;
chưa thấy app ghi FAILED=3. Seed có 5 dòng status=4. Chưa tự remap dữ liệu.
**Đề xuất:** chuẩn hóa mapping và migration cho dữ liệu cũ, rồi đồng bộ constants ↔ SQL ↔ seed ↔ FE
và bổ sung CHECK sau khi chốt miền giá trị. Trước đó snapshot giữ giá trị số gốc,
không dùng IntEnum để parse giá trị 4.
### D9 — `contact_info` ở lại PG
Là sổ địa chỉ (PII). Collection `contact_messages` (Mongo) tương ứng `system_feedback`, **không** phải `contact_info`. Sửa bảng ánh xạ trong kế hoạch Ngày 3/5.
### D10 — Bộ đếm `view_count`
Ghi mỗi lượt xem làm tăng dead tuple/khóa dòng `product`. Đề xuất: giữ ở PG giai đoạn này nhưng ghi nhận như rủi ro; phương án sau: counter ở Mongo (`$inc`) đồng bộ định kỳ về PG. Không chặn Ngày 2–4.
### D11 — Dọn dead code DB / quy ước log
**Đã xác minh 28/10:** không thấy backend gọi apply_voucher_to_order; generic_audit_trigger
không gắn vào bảng. Đã tái hiện lỗi undefined_column(updated_at) khi gọi hàm voucher;
chưa sửa baseline. Chuyển việc sửa/xóa sang migration. SELF_BUY_BLOCKED bị rollback
đã được kiểm chứng bằng SQL; thiết kế log chặn độc lập giao dịch ở tầng ứng dụng.

## Rủi ro đã biết (theo checklist Ngày 1)
| Rủi ro | Mô tả | Giảm thiểu |
|---|---|---|
| Bootstrap `DATABASE_URL` vs `DB_*` | `init_db.py` chỉ dùng `DB_*` | D6: chuẩn hóa cả hai trong compose/.env; test với chỉ `DATABASE_URL` |
| `init.sql` bị bỏ qua khi DB đã có | không tự migrate | D6: runner `schema_migrations` |
| Ngưỡng fraud 0.9 | Đã đọc fraud_detection.py 28/10: model score bị chặn 0.9 nhưng is_fraud so sánh >0.9; nhánh hard limit vẫn hoạt động | Không phải trọng tâm; ghi chú nếu đưa fraud.score vào snapshot |
| Enum `PaymentMethodId` | seed có 5 phương thức, guide: chỉ COD/PayPal triển khai; seed lại phân bố 24/30 đơn vào MoMo/VNPay/Bank | Snapshot lưu `method_id` + cờ; không tuyên bố hỗ trợ |
| Trộn múi giờ | D7 | trước partition/ETL |
| Seed lệch dữ liệu | avatar thiếu 11 file; tên ảnh ≠ product_id; voucher đơn vị/hết hạn | ETL media tolerant; sửa seed ở migration/seed mới |
