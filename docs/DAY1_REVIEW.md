# Ngày 1 — Review và kiểm chứng hiện trạng (28/10/2026)

## Kết luận

**Đã hoàn tất phần audit hiện trạng của Ngày 1:** đọc các file từng thiếu,
sửa ERD theo catalog PostgreSQL thật, chạy bootstrap và kiểm tra SQL trên database riêng.
Các thay đổi thiết kế D1–D11 là đầu vào cho Ngày 2; chưa có migration hoặc thay đổi hành vi ứng dụng.
Việc nhóm phê duyệt thiết kế không được suy ra từ kết quả kiểm tra kỹ thuật này.

## Môi trường và bằng chứng

- Ngày kiểm tra: 28/10/2026, Asia/Ho_Chi_Minh.
- PostgreSQL **16.15**; pgAdmin4 cài tại `/usr/pgadmin4`, `web/version.py` xác nhận **9.18**.
- Hai database mới trong cluster tạm `/tmp/oldshop-day1-pg-V5CDut`, Unix socket riêng,
  port 55418, role thử nghiệm `oldshop_audit`, không mở TCP.
- `oldshop_day1_audit`: chạy `init.sql` bằng psql với `ON_ERROR_STOP=1` và `--single-transaction`.
- `oldshop_day1_pgadmin`: chạy SQL đã mở rộng include bằng **psycopg 3.3.4 đi kèm pgAdmin4**.
- Hai cách tạo ra cùng columns, constraints, indexes, triggers, functions và extensions.
- Đối chiếu DBML với catalog: đủ 18 bảng/167 cột; khớp kiểu, nullability, default,
  PK, UNIQUE, CHECK và FK cùng hành vi delete/update.
- Bằng chứng và SHA-256: [day1/verification.txt](day1/verification.txt).
- Chưa thao tác tự động trên GUI pgAdmin, chưa chạy backend pytest hoặc Docker runtime.
  Kiểm tra SQL không chứng minh luồng API, cạnh tranh đồng thời, replication hay ETL hoạt động đúng.
- Cluster thử nghiệm được dừng sau khi kiểm tra; dữ liệu tạm không phải hạ tầng chạy ứng dụng.

| Đối tượng | Số lượng thực đo |
|---|---:|
| Bảng / cột | 18 / 167 |
| PRIMARY KEY / FOREIGN KEY | 18 / 25 |
| UNIQUE constraint / CHECK | 9 / 10 |
| Index, gồm cả index hỗ trợ PK/UNIQUE | 71 |
| Trigger ứng dụng / function ứng dụng | 2 / 25 |

Extensions: `uuid-ossp` 1.1, `pgcrypto` 1.3, `pg_trgm` 1.6, `plpgsql` 1.0.
Số dòng seed được kiểm tra đủ 18 bảng trong `verify_day1.sql`;
**violation_log = 11**, không phải 10 như lần đếm trước. Các ước lượng dung lượng/tần suất R/W
trong inventory vẫn chưa phải benchmark thực nghiệm.

## Review ERD

Đã sửa [diagram/01_erd_current.dbml](diagram/01_erd_current.dbml):

1. Bổ sung độ dài `varchar` theo SQL, như username(50), email(100), title(255),
   random_key(64), reference_number(100), subject(200), reason(500).
2. `transaction.reference_number` là **UNIQUE, nullable**. Hai giá trị NULL cùng tồn tại được.
3. `user_role` dùng **một PK ghép `(user_id, role_id)`**, hai cột NOT NULL;
   không diễn đạt thành hai PK riêng. Schema cho phép nhiều role/user dù seed mỗi user một role.
4. Thể hiện quan hệ user–shopping_cart là một–một với FK UNIQUE;
   mỗi user có thể chưa có cart, không bắt buộc mọi user đều có một cart.
5. Thêm defaults và đủ 10 CHECK. `transaction_status` hiện **không có CHECK**,
   nên chú thích 0..4 không được coi là ràng buộc đã triển khai.
6. Thêm hành vi FK: product_image→product và transaction→order DELETE CASCADE;
   system_feedback→user DELETE SET NULL; các FK khác NO ACTION.
7. Giữ định nghĩa SQL của các index bổ sung trong comment, nhất là partial/GIN;
   không biến partial UNIQUE thành UNIQUE toàn bảng khi xuất sơ đồ.
8. Chú thích rõ schema hiện tại và đề xuất Mongo/MinIO; ghi nhận tracking_number
   hiện được app dùng để chứa số điện thoại người nhận trước khi có mã vận đơn.

Ba file PNG là bản xuất trước review; **chưa tái xuất**, không dùng để xác nhận chi tiết
constraint mới sửa. Nguồn ERD hiện hành là DBML đã đối chiếu với PostgreSQL.

## Các file từng thiếu — kết quả đọc

| File / nhóm | Kết quả và tác động |
|---|---|
| `crud/order.py` | Buyer history lọc buyer_id/status, sort order_date DESC. Seller suy ra qua order_detail→product. Voucher được tính trong Python; app không gọi apply_voucher_to_order. Tạo transaction PENDING; cancel hoàn hàng và giảm usage_count. |
| `crud/shopping_cart.py` | `_lock_product()` dùng SELECT FOR UPDATE. Add/update/remove/clear xử lý reserve/release trong app; checkout xóa item mà không hoàn stock. |
| `crud/product.py` | Search dùng ILIKE trên **title OR description**, không dùng to_tsvector. Index GIN FTS hiện có không trực tiếp phục vụ điều kiện này. GET detail tăng view_count bằng đọc–sửa–ghi. |
| `api/v1/products.py` | `search`, `category_id`, `sort_by` là các nhánh ưu tiên, không phải bộ lọc kết hợp. Loại sản phẩm của seller đăng nhập **sau** offset/limit; sort_by chỉ áp dụng nhánh mặc định. Upload multipart lưu PG + local files. |
| `services/storage.py` | Chấp nhận .jpg/.jpeg/.png/.webp/.gif, kiểm MIME khai báo image/* và tối đa 2 MiB. Đọc hết file vào RAM, không giải mã để xác thực nội dung ảnh. Tên prefix+slug có thể trùng/ghi đè; MinIO cần xử lý key mới. |
| `services/fraud_detection.py` | Thiếu model/scaler thì fallback score=0.1. Model bị chặn ở 0.9 trong khi is_fraud so sánh >0.9. Hard limit >100 triệu vẫn trả fraud=True. |
| `core/config.py`, `core/database.py` | DATABASE_URL dùng cho engine; không parse ngược sang DB_*. Bootstrap vẫn dùng DB_* riêng. Pool pre_ping, pool_size=10/max_overflow=20; không đặt timezone phiên kết nối trong engine. |
| `docker-compose.yml` | PG16 local, host port 5433; volumes pg_data/media; chưa có Mongo/MinIO/replica/pgAdmin service. |
| `deploy/docker-compose*.yml` | Production PG16 + application/Caddy; monitoring và lựa chọn Loki/ELK. PG không publish port ra host, có TZ Asia/Ho_Chi_Minh; không có kiến trúc dữ liệu phân tán mới. |
| `frontend/nginx.conf` | /api/ và /media/ proxy sang backend, giữ prefix; multipart limit 12 MiB. Khi thêm MinIO phải giữ hợp đồng URL và xem lại cache ảnh 7 ngày. |

Đã đọc thêm `api/v1/orders.py`, models, init_db, Dockerfile/entrypoint,
`media-url.ts`, CI và SQL functions để kiểm chứng đường gọi xuyên tầng.

## Phát hiện cần đưa sang Ngày 2–6

### Đã kiểm chứng bằng SQL hoặc đối chiếu mã

- **Enum giao dịch:** SQL comment/seed dùng 4=Failed; Python có FAILED=3.
  App hiện chỉ ghi PENDING=0, SUCCESS=1, FLAGGED=2 trong các luồng đã đọc;
  không thấy nhánh ghi FAILED=3. Không tự chuyển 4→3 hoặc diễn giải lại 3 khi chưa có migration.
- **Stock:** insert order_detail không thay đổi quantity. Khi SQL UPDATE quantity→0,
  trigger đặt SOLD_OUT/sold_at; tăng lại quantity không tự phục hồi APPROVED.
- **Audit rollback:** trigger chặn tự mua có chạy, nhưng log SELF_BUY_BLOCKED trong
  cùng giao dịch bị rollback. Init thành công không chứng minh mọi function chạy đúng.
- **Dead/latent code:** không thấy backend gọi apply_voucher_to_order/authenticate_user;
  generic_audit_trigger không được gắn vào bảng nào. Đã gọi thử apply_voucher_to_order
  và tái hiện lỗi cột order.updated_at không tồn tại; công thức discount cũng cần sửa.
- **Contact seed:** cả **30/30** order tham chiếu contact không thuộc buyer.
  API có `_get_own_contact()` bảo vệ yêu cầu mới; FK của DB không bảo vệ quan hệ sở hữu.
- **Watermark:** raw UPDATE title không cập nhật product.updated_at. Không thể dùng
  updated_at hiện tại như bảo đảm đầy đủ cho ETL.
- **Múi giờ:** SQL TIMESTAMP không tz, ORM dùng utcnow; SET timezone trong init chỉ
  tác động phiên chạy init, không cấu hình mặc định cho mọi kết nối app.
  Chưa chứng minh hệ giờ của từng dòng dữ liệu thực tế chỉ bằng đọc default.

### Rủi ro phát hiện khi đọc code, chưa kiểm thử cạnh tranh/API

- Add cart cho user chưa có cart: `get_or_create()` commit cả reservation đang chờ,
  giải phóng khóa trước khi add_item hoàn tất. Cần kiểm tra tính nguyên tử và nhánh thất bại.
- Checkout `_validate_items()` kiểm tồn tại/xóa mềm/tự mua nhưng chưa xác minh số lượng
  đã reserve trong cart. CRUD create_order cũng không reserve thêm stock;
  cần test gọi thẳng checkout ngoài giỏ, nhiều lần checkout và lượng đặt khác giỏ.
- Voucher usage_count đọc–sửa–ghi không thấy row lock; view_count cũng có nguy cơ mất lượt tăng.
- `order_detail` được app hiện tại tạo một lần; DB vẫn cho UPDATE/DELETE.
  Nếu ETL order snapshot phụ thuộc order.updated_at, cần lan truyền thay đổi từ
  transaction/order_detail và định nghĩa cách xử lý thay đổi các trường được nhúng.
- **Sequence không theo thứ tự commit**: transaction lấy log_id nhỏ có thể commit sau
  transaction có ID lớn. Watermark MAX(id) thuần có thể bỏ sót log; cần chiến lược cửa sổ
  quét lại/đối soát hoặc outbox/CDC phù hợp, không chỉ dùng id tăng dần.
- `system_feedback.status` có thể đổi, `shopping_cart_item` có thể sửa/xóa:
  watermark created_at/id đơn thuần không đủ cho các bảng mutable.
- Partition product theo category cũng vướng PK(product_id) và FK từ product_image,
  review, cart item, order_detail. Partition transaction còn vướng PK(transaction_id),
  không chỉ UNIQUE(reference_number). Phải thiết kế đầy đủ trước khi chọn DDL.
- Chuyển description sang Mongo còn ảnh hưởng ILIKE đang tìm cả title/description;
  giữ cột PG trong giai đoạn expand/contract cho đến khi thay truy vấn tương ứng.

## Chạy bằng pgAdmin4 9.18

`init.sql` chứa 35 lệnh include của **psql**. pgAdmin [PSQL Tool](https://www.pgadmin.org/docs/pgadmin4/9.18/psql_tool.html)
cung cấp giao diện psql; [Query Tool](https://www.pgadmin.org/docs/pgadmin4/9.18/query_tool.html)
gửi SQL tới PostgreSQL. Dùng một trong hai cách trên **database mới, rỗng**:

**PSQL Tool**, kết nối database thử nghiệm, chạy các lệnh sau;
đường dẫn phải tồn tại trên máy chạy tiến trình psql của pgAdmin:

```text
\cd /home/phat/Documents/Project/Epic-Ecommerce-FastAPI-main/database
\set ON_ERROR_STOP on
BEGIN;
\i init.sql
COMMIT;
\i verify_day1.sql
```

**Query Tool**, trước tiên sinh SQL thuần từ root dự án:

```bash
python3 database/build_pgadmin_init.py --output /tmp/oldshop-init-pgadmin.sql
```

Mở file vừa sinh trong Query Tool của database rỗng, Execute script toàn bộ.
Sau khi thành công, mở `database/verify_day1.sql` và Execute script.
File sinh đã có BEGIN/COMMIT; nếu lỗi trong transaction thì ROLLBACK trước khi thử lại.
Script kiểm tra rollback thay đổi nhưng sequence vẫn có thể tiêu thụ ID;
chỉ dùng database thử nghiệm.

Generator không sửa SQL nguồn, không ghi đè file đã tồn tại, và từ chối ghi vào database/.
Các thay đổi schema sau này vẫn phải đi qua migration, không chạy lại seed lên database đang dùng.

## Bàn giao

- Hoàn tất audit và kiểm chứng baseline Ngày 1; nhật ký cũ là lịch sử, các đính chính tại đây được ưu tiên.
- Ngày 2: chốt D3 dựa trên toàn bộ PK/FK/unique; thiết kế hạ tầng và tính chất tái tạo phân mảnh.
- Trước ETL/partition: xử lý D7 thời gian, D8 enum, D6 migration và D2 đồng bộ thay đổi.
- Trước tuyên bố ứng dụng tương thích schema mới: chạy bộ integration tests trên DB test sạch.
