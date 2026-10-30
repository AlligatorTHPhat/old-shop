# Ngày 5 — ETL và transactional outbox

Thực hiện 30/10/2026, theo D1/D2/D4/D6. Code, kiểm thử độc lập và **rollout local đã hoàn tất**
sau khi người dùng đồng ý bảo trì. Stack chạy migration 005 và worker ETL; backup/restore,
full hai lần và đối soát nguồn đạt. [Bằng chứng rollout](../evidence/day5_rollout.json).
[Nhật ký](../DAY5_FINDINGS_LOG.md), [luồng PUML](../diagram/05_etl_flow.puml),
[validator BSON hiện tại](05_mongo_validators.json).

## Thành phần

- `backend/etl/extract.py`: allowlist cột, snapshot PG REPEATABLE READ, stream khóa theo lô.
- `transform.py`: tiền nguyên VND, thời gian aware UTC, dimensions và text công khai.
- `load.py`: upsert theo khóa nguồn, partial `$set`, giữ `_id` cũ nếu business key đã có.
- `pipelines/documents.py`: product/order/review/audit/contact; `media.py`: file;
  `aggregate.py`: báo cáo PG. `quality.py`, `errors.py`, `run.py`: đối soát/retry/CLI/daemon.
- `database/04_migrations/005_etl_outbox.sql`: outbox + origin timestamp + run/state + report,
  trigger trên 10 bảng nguồn. Không sửa các migration 001–004 đã áp dụng.
- `etl-worker` Compose dùng image backend, một process, poll mặc định 60 giây.
  `etl-test` chỉ trong profile test, dùng quyền Mongo admin để tạo DB test riêng;
  worker thật dùng Mongo readWrite và MinIO user giới hạn bucket như backend.

## Sáu pipeline

| Pipeline | Nguồn → đích | Quy tắc |
|---|---|---|
| Product | product + product_image → product_details | Mô tả/video/weight/dimensions/condition từ PG; ảnh bucket/key lấy đúng image_url và FK. Không suy product_id từ filename. attributes/tags không bị ghi đè |
| Order | order + order_detail + transaction + voucher + product → order_snapshots | Nhúng items/payments, tiền giá mua lấy order_detail. title/category/seller và voucher có hậu tố current. Không đọc địa chỉ, số dư hay provider token |
| Review/report | review → reviews | rating=0 là report, rating=1..5 là review. Giữ moderation/status/evidence do Mongo quản lý; bản ghi mới có status pending |
| Log/audit/contact | system_log / violation_log / system_feedback → collections tương ứng | Log giữ danh tính (log_id,created_at), action/actor/resource; không copy raw details/IP. Violation giữ target/action/time, reason dẫn về PG. Contact chỉ metadata, không copy guest_email/nội dung riêng tư |
| Media | seed media + volume media → MinIO | Chỉ thêm object thiếu; giữ URL PG, alias legacy/canonical. Ảnh mới từ local được copy đúng key trước ACK; ảnh đã upload MinIO không cần một bản local khác |
| Aggregate | delivered order + order_detail + product → report_daily_sales trên PG primary | Theo ngày kinh doanh Asia/Ho_Chi_Minh, seller/category **hiện tại**, tổng subtotal của dòng hàng, orders_count distinct trong từng nhóm |

`report_daily_sales.gross_sales_vnd` là **giá trị hàng đã giao**, chưa trừ discount, chưa cộng
shipping; khác `admin.total_revenue` vốn cộng final_amount. Không cộng final_amount lặp lại
trên từng dòng hàng. Một order nhiều category/seller được tính trong nhiều nhóm nên tổng
orders_count giữa các nhóm không phải tổng order độc lập. PG replica nhận bảng này qua WAL;
API đọc dashboard từ report là bước tích hợp Ngày 6. Không tự thay đường đọc ví/tồn kho.

Voucher hiện tại gồm ID, mã loại giảm giá gốc, giá trị dạng decimal string, active/deleted;
không tự tính lại đơn cũ khi voucher thay đổi. Fraud lấy score đã lưu, không chạy lại model
bằng số dư hiện tại. transaction_status=4 được giữ nguyên, D8 chưa remap.

## Outbox, replay và phụ thuộc

Outbox chỉ chứa table, source key, entity/key, operation và trạng thái. Không nhét whole-row,
password/token/address/balance vào payload. AFTER I/U/D trigger ghi cùng transaction nguồn:
rollback nguồn cũng rollback event và timestamp origin.

Phụ thuộc được bắt cả hai FK cũ/mới khi đổi quan hệ:

| Thay đổi | Bản đọc |
|---|---|
| product | product_details và mọi order chứa product (trường current) |
| product_image | product của FK cũ và mới |
| order | snapshot của khóa cũ/mới |
| order_detail / transaction | order cũ/mới |
| voucher | các order tham chiếu voucher (metadata current) |
| review / system_feedback / violation_log | bản đọc có ID tương ứng |
| system_log | khóa log_id + timestamp gốc, kể cả qua partition |

Một session advisory lock cho mỗi lượt full/incremental/reconcile, xuyên suốt các commit;
full và daemon không ghi chồng nhau. Khóa ở cấp DB; daemon nhả giữa các chu kỳ để CLI có thể chạy.
Không thiết kế nhiều worker đồng thời. Worker chọn mọi pending/dead đã đến hạn, sắp xếp event_id
để tiện xử lý, **không dùng điều kiện event_id > MAX(last_id)**. Transaction có ID nhỏ commit muộn
vẫn được chọn ở lượt sau.

Mỗi event dựng lại trạng thái mới nhất trong snapshot PG của batch, upsert Mongo bằng majority
write concern, rồi ACK đúng event_id. Crash sau Mongo trước ACK được replay, không tạo bản sao.
Đây là at-least-once, không phải transaction nguyên tử PG+Mongo hay exactly-once.

Full bật sau migration/outbox, đọc snapshot nguồn, rồi xử lý bù tối đa 20 batch; nếu còn backlog
thì run partial và daemon tiếp tục. Soft delete giữ deleted=true. Hard delete ẩn document đã có,
giữ metadata Mongo-owned; absence cũng là trạng thái đã xóa hợp lệ. System log là bản sao không có
metadata sở hữu riêng nên có thể xóa bản đọc theo khóa ghép. Full/reconcile còn sweep các bản đọc
ETL đã có nhưng không còn nguồn; không xóa metadata hay document chưa từng được ETL quản lý.

`etl_errors` chứa event ID, entity key, run_id, error code, attempts và thời điểm; không lưu exception
text/source payload. PG outbox giữ lỗi ngay cả khi Mongo không nhận được dead-letter.
Backoff 15,30,60... giây, tối đa 900 giây. Từ lần lỗi thứ 5 đánh dấu dead, **vẫn giữ và retry** khi đến hạn;
CLI retry-dead đưa các event dead đến hạn ngay. Sửa dữ liệu nguồn cũng phát sự kiện mới.
Không TTL event chưa ACK hoặc error chưa xử lý. Không tự gọi clean_old_audit_logs trong ETL;
retention PG phải có quy trình đối soát trước khi bật, không dựa vào TTL của Mongo để xóa nguồn.

## D7 — Thời gian đã thống nhất cho ETL

Người dùng xác nhận ngày 30/10: **toàn bộ dữ liệu cũ là giờ Việt Nam**.
Migration ghi provenance vào etl_time_origin, không UPDATE timestamp gốc và không đổi kiểu cột PG.
Chuyển toàn bộ PG sang timestamptz vẫn là migration riêng, chưa làm ở Ngày 5.

- Dữ liệu trước 005: origin Asia/Ho_Chi_Minh theo xác nhận trên, không suy luận theo serial ID.
- Giao dịch SQLAlchemy Session mới: `SET LOCAL TIME ZONE 'UTC'`; datetime.utcnow và SQL
  CURRENT_TIMESTAMP trong transaction đó cùng hệ UTC. Không đổi TimeZone toàn server/pgAdmin.
- SQL viết trực tiếp: timestamp mới/đổi theo múi giờ phiên SQL; dùng tên IANA như
  Asia/Ho_Chi_Minh hoặc UTC. Nếu nhập một naive timestamp ở múi giờ khác phiên, người vận hành
  phải đặt TimeZone đúng trước khi ghi. Trigger không thể đoán ý nghĩa một giờ nhập tay.
- Field không đổi giữ origin cũ; đổi PK mang origin theo. Thiếu origin/value không khớp thì lỗi,
  không tự gán múi giờ để qua kiểm tra. Origin giữ lại cho khóa cũ để xử lý delete/rekey.
- Khi ghi Mongo dùng aware datetime UTC/BSON Date. So sánh dữ liệu chuẩn hóa về độ chính xác
  millisecond của BSON; report_date đổi từ UTC về ngày kinh doanh VN.

Tiền nguồn phải nguyên, không âm và trong int64. Fraction, NaN, số âm, NULL tiền hoặc sai số
subtotal/final bị giữ lỗi, không làm tròn hoặc giả định 0. Bản ghi order thiếu items, voucher thiếu,
hoặc tổng line không khớp không được đưa lên snapshot; các FK PG tiếp tục bảo vệ quan hệ nguồn.

Không chọn cột bí mật/PII giao dịch. Text công khai của product/review che email, số điện thoại,
URL; đây là heuristic, không bảo đảm xóa mọi tên/địa chỉ tự do. Raw contact, violation reason và
log details được giữ ở PG; Mongo nhận metadata/placeholder. API hiện tại vẫn đọc nội dung này từ
PG; không dùng placeholder Mongo để thay thế nội dung hiển thị khi chưa thiết kế phân quyền.

## Kiểm tra chất lượng và lịch

Mỗi cycle kiểm tra count active PG/Mongo cho cả sáu collection và so sánh field PG-owned của
các entity vừa xử lý. Full và reconcile hằng ngày còn kiểm tra mọi source key/field, stat đúng
key của các product_image và đối chiếu content-type/size, không list bucket để trả catalogue.
Không so 32 image reference với tổng object 95 vì có avatar/canonical/legacy aliases.

System log chỉ đối chiếu cửa sổ 90 ngày; log PG cũ vẫn ở PG, không coi bản sao hết retention là
mất dữ liệu. Violation log không TTL. Arrays/field Mongo-owned không bị đưa vào so sánh PG-owned.
Thời điểm đồng bộ/run_id thay đổi giữa lượt không phải nội dung nguồn cần bằng nhau.

etl_runs ghi start/end/status/rows_in/out/errors/details, kể cả tiến độ trước lỗi ở cuối run.
rows_in/out là **số thao tác** (full rows + replay event), không phải số document duy nhất.
Tổng document xem trong details.quality.collections. quality mismatch tách khỏi số exception.
Nếu source đổi trong lúc kiểm tra có thể partial/backlog; daemon xử lý tiếp, không ACK hộ sự kiện mới.
Báo cáo aggregate rebuild transactionally từ PG mỗi cycle; không xóa báo cáo cũ nếu rebuild lỗi.

Daemon: full lần đầu, incremental mỗi 60 giây sau cycle trước, deep reconcile lần đầu mỗi ngày UTC.
Reconcile phát hiện field sai, full dùng để sửa/rebuild. Không đặt một số liệu trễ thành bảo đảm SLA:
độ trễ mục tiêu dưới 5 phút khi tải bình thường; lỗi, batch lớn và backoff có thể vượt mục tiêu.
CLI status cung cấp pending/dead/oldest_pending_seconds và run cuối. Health chỉ kiểm heartbeat
5 phút, **không** đồng nghĩa dữ liệu đã mới hoặc backlog bằng 0; xem cả status và báo cáo quality.

## Chạy thử và vận hành

Từ root, dùng stack dữ liệu riêng `deploy/.env.data` (không in secrets):

```bash
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml build backend
bash deploy/scripts/test-day5.sh
```

Test runner tạo **hai cặp DB PG/Mongo mới**: regression và ETL. Không truncate DB ứng dụng.
Các test MinIO dùng UUID và dọn đúng object thử, giữ object seed đã có. DB test giữ lại để review.
CI lint thêm package etl và chạy unit; integration Mongo/MinIO cần môi trường test stack, không
tuyên bố CI remote đã chạy các service này.

Rollout local đã thực thi sau khi người dùng chấp thuận bảo trì.
`bash deploy/scripts/apply-day5.sh --resilience` dừng backend/frontend/etl-worker;
backup PG/Mongo/MinIO, restore rehearsal vào tên riêng, áp 005, init validator, chạy full hai lần,
so digest/count của 18 bảng nguồn rồi mở lại. Lỗi giữ maintenance. Backup cùng máy là diễn tập,
không thay thế backup ngoài host. Không rollback chỉ bằng đổi tag image sau khi schema đổi.

CLI vận hành sau rollout:

```bash
# Xem trạng thái, không cần Swagger.
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml exec -T etl-worker python -m etl.run status
# CLI có thể gặp etl_worker_busy nếu một cycle đang chạy; chờ cycle xong, không chạy worker thứ hai.
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --entrypoint python backend -m etl.run full
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --entrypoint python backend -m etl.run reconcile
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --entrypoint python backend -m etl.run retry-dead
```

CLI full/incremental/reconcile: exit 0 success, 2 partial, 1 failed/busy. Dùng run_id tra etl_runs,
lỗi event xem etl_outbox.last_error_code/attempts và etl_errors. Sửa nguồn/config trước rồi retry;
không sửa checksum/version, không reset sequence, không xóa pending chỉ để có status xanh.

## Bằng chứng và giới hạn

[Xem nhật ký](../DAY5_FINDINGS_LOG.md) và [run mẫu cô lập](../evidence/day5_isolated_runs.json).
Mongo kiểm thử 7.0.43 theo ngoại lệ kernel đã thống nhất; chưa tuyên bố test Mongo 8.0.32.
MVP một worker, extract theo entity nên có N+1 query, aggregate rebuild toàn bộ; chưa benchmark
thông lượng ETL trên 100k order. Index/partition benchmark Ngày 4 không phải benchmark ETL.
Outbox/processed run/origin chưa có policy GC; cần vận hành retention riêng, không tự xóa lịch sử.
Không chuyển API sang đọc Mongo/dashboard report hoặc triển khai FDW/sharding ở Ngày 5.

Nguồn: [PG 16 trigger cùng transaction](https://www.postgresql.org/docs/16/trigger-definition.html),
[advisory lock](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS),
[PyMongo dates/UTC](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/data-formats/dates-and-times/).
