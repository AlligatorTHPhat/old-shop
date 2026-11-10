# ERD PostgreSQL hiện tại

- [`erd.dbml`](erd.dbml): schema ứng dụng sau khi chạy `init.sql` và toàn bộ migration `001`–`007`, gồm 28 bảng, 222 cột và 28 quan hệ khóa ngoại.
- [`distributed/erd.dbml`](distributed/erd.dbml): schema trên **mỗi site** sau bước trên và `distributed/01_site_schema.sql`, gồm 31 bảng, 232 cột và 30 quan hệ khóa ngoại. Phù hợp với cách dựng schema trong `deploy/scripts/sites.py`; không biểu diễn hai site thành một database vật lý.

Mở file tương ứng trong công cụ hỗ trợ DBML (ví dụ dbdiagram.io) để xem ERD. Hai file là các sơ đồ độc lập.

## Phạm vi và cách đối chiếu

Các file được đối chiếu với catalog của PostgreSQL 16 dựng tạm từ SQL trong repository, gồm kiểu dữ liệu, NULL/NOT NULL, default, PK, UNIQUE, CHECK, index và FK cùng hành vi ON DELETE/ON UPDATE. `schema_migrations` lấy định nghĩa từ `backend/scripts/migrate.py`. Đây là schema suy ra từ mã nguồn, không khẳng định trạng thái migration của một server đang chạy.

`init.sql` riêng lẻ chỉ tạo schema ban đầu và **không tự chạy migration**. Sau migration `003`, bảng `"user"` đổi thành `user_core` và tách thêm `user_profile`, `user_secret`, `user_wallet`; các FK cũ theo bảng được đổi tên. PK đồng thời là FK được thể hiện bằng quan hệ 1–1, không ngụ ý mọi user bắt buộc phải có dòng con.

`order` được phân vùng HASH thành `order_h0`–`order_h3`; `system_log` được phân vùng RANGE theo tháng và có partition DEFAULT. ERD biểu diễn bảng cha; không lặp lại các partition hoặc các constraint nội bộ PostgreSQL sinh cho partition. PK của `system_log` là **(log_id, created_at)**.

`users_full` là view JOIN chỉ đọc, không phải bảng. Ở mô hình phân tán, `site_identity` và các `v_*` là view; `site_b.*` là foreign tables qua FDW. Chúng được ghi chú trong DBML thay vì biểu diễn thành các bảng nghiệp vụ mới. Xem `distributed/04_fdw.sql` và `distributed/05_global_views.sql` để biết cấu trúc truy cập liên site.

DBML không biểu diễn đầy đủ partial index, GIN, operator class hay thứ tự DESC. Mỗi index có `note` chứa nguyên định nghĩa PostgreSQL; partial UNIQUE không được đánh dấu thành UNIQUE toàn bảng. Dùng SQL gốc khi cần tái tạo chính xác database.

Các cột như `etl_outbox.last_run_id`, các ID trong JSONB và các chiều của `report_daily_sales` không có FK trong SQL, vì vậy không tự thêm đường quan hệ. Các bảng vận hành không có FK có thể đứng độc lập trên sơ đồ. Trigger, quyền truy cập, sequence tùy chỉnh và dữ liệu seed không thuộc ERD; xem SQL gốc để biết hành vi đầy đủ. Không bao gồm MongoDB, MinIO hay các bảng tạm dùng trong migration.
