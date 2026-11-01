# Workload indexing v2

Các SELECT đo nhỏ trong pg/before và selected/before là projection đại diện cho đường
truy cập, không đồng nhất latency của toàn bộ endpoint. SQL ORM catalogue đầy đủ cùng
parameters và joinedload ảnh được capture riêng ở selected/{before,after}/orm_catalogue.json.
Mỗi file JSON ghi SQL, tất cả plans và digest kết quả. Không ép planner dùng index.

| Case | Nguồn/ý nghĩa | Số dòng trả về baseline |
|---|---|---:|
| Q01_category | app/crud/product.py: catalogue | 20 |
| Q01_seller_exclusion | app/crud/product.py: catalogue | 20 |
| Q01_offset | app/crud/product.py: catalogue | 20 |
| Q01_candidates | app/crud/product.py: catalogue | 20 |
| Q02_all | app/crud/product.py: catalogue; giá là case thiết kế | 20 |
| Q02_price | app/crud/product.py: catalogue; giá là case thiết kế | 20 |
| Q03_search | app/crud/product.py: search | 41 |
| Q03_short | app/crud/product.py: search | 20 |
| Q03_vietnamese | app/crud/product.py: search | 20 |
| Q04_detail | app/crud/product.py và cart reservation | 1 |
| Q05_images | etl/extract.py: product images | 4 |
| Q06_buyer | app/crud/order.py: buyer history | 20 |
| Q07_seller | app/crud/order.py: seller history | 20 |
| Q08_cart | app/crud/shopping_cart.py: cart/product | 1 |
| Q09_login | app/crud/user.py: login | 1 |
| Q10_paypal_reuse | app/crud/order.py: find_reusable_paypal_order: reuse unpaid order | 0 |
| Q11_items | etl/extract.py: details/payments | 1 |
| Q11_payments | etl/extract.py: details/payments | 1 |
| Q12_poll | etl/run.py: claim pending/dead | 100 |
| Q12_stable | etl/run.py: claim pending/dead | 100 |
| Q13_retry | etl/run.py: retry_full_error | 0 |
| Q14_status | etl/run.py: status; app/services/sales_report.py: latest aggregate | 1 |
| Q14_aggregate | etl/run.py: status; app/services/sales_report.py: latest aggregate | 1 |
| Q15_image_missing | etl/pipelines/media_cleanup.py: shared references | 1 |
| Q15_image_unique | etl/pipelines/media_cleanup.py: shared references | 1 |
| Q15_image_shared | etl/pipelines/media_cleanup.py: shared references | 1 |
| Q15_avatar_missing | etl/pipelines/media_cleanup.py: shared references | 1 |
| Q15_avatar_unique | etl/pipelines/media_cleanup.py: shared references | 1 |
| Q16_audit | database/02_functions/system/audit_functions.sql: audit helper, chưa chứng minh hot API | 2 |
| Q17_voucher | migration 005 trigger: voucher fan-out | 5000 |
| Q18_report | app/services/sales_report.py: report_daily_sales | 74 |
| role_lookup | app/crud/moderator.py: list users by role | 503 |
| token_lookup | app/crud/user.py: legacy reset token | 1 |
| cleanup_poll | etl/pipelines/media_cleanup.py: cleanup queue | 100 |
| cleanup_stable | Case đối chiếu volatility cho cleanup queue | 100 |
| Q17_voucher_missing | migration 005 trigger: voucher fan-out | 0 |

Các case tồn tại/không tồn tại trả một bool khi dùng EXISTS, số dòng trả về luôn là 1;
xem giá trị semantics qua fingerprint và scanned rows trong plan. `Q17_voucher_missing`
trả 0 order. Q04 đo SELECT detail; quyền khóa/tồn kho được xác nhận bằng regression,
không lấy thời gian SELECT này làm thời gian reservation transaction.

Phân bố bổ sung trong fixture:

- Product có ngày tạo trùng để kiểm `created_at DESC, product_id ASC`, seller exclusion,
  category, offset 1.000, tập candidate ID từ metadata, status approved/pending/deleted.
- Search có chuỗi hiếm, một ký tự và tiếng Việt; GIN trigram cũ được giữ.
- 200k ảnh thêm vào 2k seed, một URL dùng chung mỗi 10 dòng; 4 ảnh mỗi product tải.
  Case shared EXISTS có thể chọn seq scan vì gặp rất sớm; không coi đó là lỗi planner.
- 100.030 order qua bốn HASH partition, có voucher/deleted; lookup voucher cần mọi dòng.
- 100k log theo 12 tháng; query audit không có date range nên không hứa partition pruning.
- 20k run, cả success/partial và có/không details.aggregate.
- 200k outbox: 190k done, 10k pending/dead. Ma trận mixed, chỉ đuôi có due và tất cả
  deferred; query ORDER BY event_id với SKIP LOCKED. Timestamps cố định 2020/2100.
- 200k media_deletions, nhiều done và future; không thay clock_timestamp trong source.
- User role có khoảng 1% role 2; token có NULL/không trùng trong L; OTP trùng được kiểm ở upgrade S, không tạo UNIQUE mới.
- Mongo 50k document strict ProductDetails, cả deleted/live; đo tồn tại tham chiếu shared,
  unique, missing và brand+ram trả 323 IDs. Limit candidate không vượt hợp đồng hiện tại.

100 ghi/loại sau warmup: view_count, quantity reservation, moderation đổi status,
description, image insert, avatar, run insert, event ACK; phép đo cả gói thêm order insert
và role insert. Từng DML PG rollback; ghi Mongo lặp cùng một document và kết quả các query sau ghi
được so fingerprint để xác nhận không đổi. Full trigger execution được tính trong server
execution, có riêng trigger times trong raw JSON. Không đo commit/fsync hoặc concurrent
write throughput qua EXPLAIN rollback.

Seed chuẩn vẫn 1.000 product; tập tải này nằm trong DB/collection riêng. Các giả định
chưa có số liệu thực (tần suất category+price, targeted attributes, audit API, token cũ,
index usage/disk lâu dài) được ghi là điều kiện đo tiếp, không tự coi fixture là traffic thật.

Phép đo bổ sung trong `approved_writes/` dùng product approved 1000043 cho view_count,
quantity và description; thêm run finish thành success+aggregate và retry available_at.
200 mẫu/cấu hình theo A–B–B–A; clone riêng được xóa sau đo, không sửa schema_migrations.
Pilot trước đó được giữ ở `approved_writes_pilot/` để thấy biến thiên giữa các lần.
