# OldShop — Nâng cấp hệ thống dữ liệu đa mô hình

Báo cáo kỹ thuật và kiểm chứng đồ án • 30/10/2026

PostgreSQL 16 · MongoDB · MinIO · Transactional outbox · FastAPI · Angular

## Tóm tắt

OldShop là hệ thống mua bán hàng đã qua sử dụng. Phạm vi nâng cấp gồm phân loại dữ liệu,
thiết kế phân mảnh, bổ sung MongoDB và MinIO, tối ưu chỉ mục, đồng bộ ETL và tích hợp lại
ứng dụng. Giao dịch tiền và tồn kho tiếp tục sử dụng PostgreSQL. MongoDB giữ thuộc tính
động và các bản đọc có kiểm soát; MinIO giữ byte ảnh. Đây là mô hình đa dịch vụ trên
một máy, có profile replication để thực nghiệm lỗi dịch vụ; chưa phải hệ thống chịu mất máy.

Kết quả Ngày 6 đã kiểm chứng: 146 trường hợp backend khác nhau, 15 test frontend và
9 kịch bản lỗi/phục hồi đạt; schema 001–006 và 64 path API cũ được giữ. Benchmark ILIKE
trên dữ liệu thử có trung vị 316,562 → 0,372 ms, đồng thời ghi nhận một số truy vấn chậm hơn
và chi phí dung lượng index tăng. Các số đo là thực nghiệm cục bộ, không phải SLA production.

Nguồn chính: docs/DAY6_FINDINGS_LOG.md; docs/evidence/day6_stack.json;
docs/benchmark/pg/summary.json. Bằng chứng tổng duyệt mới nằm trong docs/evidence/day7_*.

## 1. Giới thiệu và bài toán

### 1.1 Ngữ cảnh nghiệp vụ

Người bán đăng sản phẩm kèm ảnh; moderator phê duyệt hoặc từ chối; người mua tìm kiếm,
giữ hàng trong giỏ và đặt đơn. Hệ thống hỗ trợ voucher, COD/PayPal, đánh giá và báo cáo
vi phạm. Admin quản lý tài khoản, phản hồi và thống kê. Các chức năng hiện có không được
đổi enum hay ý nghĩa giá trị tài chính chỉ để phù hợp mô hình dữ liệu mới.

Ba nhóm dữ liệu có yêu cầu khác nhau: quan hệ giao dịch cần ràng buộc và khóa dòng;
thuộc tính sản phẩm khác nhau giữa danh mục cần cấu trúc linh hoạt; ảnh cần object storage.
Thêm nhiều hệ quản trị tạo ra chi phí vận hành và nhất quán, vì vậy thiết kế xác định
chủ sở hữu từng field, tránh giả định một transaction ACID trải qua PostgreSQL, MongoDB và S3.

### 1.2 Mục tiêu và phạm vi nghiệm thu

| Mục tiêu | Cách kiểm chứng |
|---|---|
| Phân loại và thiết kế dữ liệu | Inventory, ERD DBML, schema SQL, ma trận phân mảnh |
| Phân mảnh và replication | HASH order, RANGE log, user split, trạng thái WAL/replica set |
| Document và object storage | Validator strict, index Mongo, private buckets, gateway ảnh |
| ETL và tính nhất quán | Outbox cùng transaction, replay idempotent, count/field/media quality |
| Tích hợp ứng dụng | Chi tiết sản phẩm hợp nhất, lọc, dashboard, fallback, test hồi quy |
| Khả năng trình bày và tái lập | Báo cáo, slide, SQL demo, video, manifest và gói release |

FDW theo vùng, Mongo sharding, Patroni, MinIO distributed và CDC/Debezium nằm ngoài MVP.
Không dùng kết quả dừng một container để chứng minh hệ thống chịu mất một máy vật lý.

## 2. Thiết kế dữ liệu

### 2.1 Kiểm kê và phân loại

Baseline có 18 bảng nghiệp vụ. Seed có 15 user, 16 product, 32 product_image, 30 order,
30 transaction, 11 violation_log; review/system_log/contact form ban đầu rỗng. Các con số
seed khác với dữ liệu benchmark được sinh riêng; không trộn hai tập để báo cáo quy mô hệ thật.

| Nhóm | Ví dụ | Nguồn chính hiện hành |
|---|---|---|
| Có cấu trúc | User/role, giá, tồn kho, đơn, dòng hàng, ví, payment, voucher, cart | PostgreSQL |
| Bán cấu trúc | attributes/tags, document nhúng items/payments, payload log đã allowlist | MongoDB BSON |
| Phi cấu trúc | Byte ảnh sản phẩm/avatar, file đính kèm | MinIO |
| Metadata file | URL, bucket/key, content-type, size, FK product_id | PG hoặc Mongo theo field ownership |

pgAdmin4 là công cụ quản trị PostgreSQL; Compass là công cụ quản trị MongoDB. MongoDB lưu
document BSON, không yêu cầu mỗi document phải là một file .json. URL ảnh là metadata,
khác với byte ảnh phi cấu trúc.

### 2.2 Mô hình quan hệ và ràng buộc

![ERD rút gọn của luồng giao dịch](assets/07_erd_summary.svg)

User có nhiều role thông qua user_role. Product thuộc seller và category; product_image
tham chiếu product_id thực tế, không suy FK từ tên file seed. Order tham chiếu buyer,
contact, payment_method và voucher; order_detail chứa giá tại lúc mua. Transaction giữ
UNIQUE(reference_number). API kiểm tra quyền sở hữu contact vì FK đơn thuần chưa đủ.

Cart giữ tồn kho ngay khi thêm hàng bằng khóa dòng PostgreSQL; checkout không đọc stock
từ snapshot Mongo. Giá mua lịch sử nằm tại order_detail.price_at_purchase, không tính lại
từ giá product hiện tại. Soft-delete giữ nguồn cần cho lịch sử và đối soát.

ERD đầy đủ hiện hành: docs/diagram/07_erd_current.dbml. Các bảng vận hành thêm bởi 005/006
gồm etl_time_origin, etl_outbox, etl_runs, etl_state, report_daily_sales và media_deletions;
schema_migrations ghi phiên bản/checksum. JSON key trong outbox là tham chiếu logic, không
phải FK SQL xuyên hai hệ quản trị. Sơ đồ 01/02/04 là mốc lịch sử, không dùng làm sơ đồ cuối.

### 2.3 Ownership và bảo vệ thông tin

PG là nguồn sự thật của dữ liệu tài chính, định danh và các cột product cũ. Mongo sở hữu
attributes/tags mới và metadata mở rộng; các bản sao từ PG chỉ được cập nhật bằng allowlist.
Không ETL password hash, token, số dư, địa chỉ hay provider payment token. Nội dung contact,
violation reason và audit details riêng tư tiếp tục ở PG; Mongo nhận metadata/placeholder.
Redaction text công khai chỉ là heuristic, chưa phải cơ chế bảo đảm mọi PII được phát hiện.

## 3. Thiết kế hệ thống phân tán

### 3.1 Kiến trúc triển khai thực tế

![Kiến trúc hiện hành, tất cả dịch vụ cùng một Docker host](assets/07_architecture.svg)

Angular/Nginx chuyển /api và /media tới FastAPI. API đọc/ghi core trên PG primary,
đọc attributes/tags Mongo và truyền ảnh qua MinioStorage. Worker chạy độc lập cùng image
backend. Profile resilience thêm PG standby và hai Mongo member; MinIO vẫn single-node.
Ports quản trị local bind 127.0.0.1; Mongo không publish ra host. Caddy/observability của
VPS là cấu hình khác, không tự coi chúng đã nằm trong stack polyglot demo.

### 3.2 Phân mảnh ngang

| Bảng/fragment | Khóa định tuyến | Bảo đảm và giới hạn |
|---|---|---|
| order_h0..order_h3 | PostgreSQL HASH(order_id), modulus 4 | PK(order_id) giữ được; lookup PK prune; buyer/seller history không prune theo hash này |
| system_log_YYYYMM | RANGE(created_at), khoảng nửa mở theo tháng | PK(log_id,created_at); chỉ đọc tháng liên quan khi predicate tương thích |
| system_log_default | Phần bù của các tháng đã tạo | Tránh mất dòng ngoài lịch; cần bảo trì chuyển dòng khi thêm partition |
| transaction/product/order_detail | Chưa partition ngang | Giữ UNIQUE/FK và hợp đồng nghiệp vụ; không ép phân mảnh mọi bảng |

Phân mảnh phải đầy đủ, không chồng lặp và tái tạo được. Bộ định tuyến HASH PostgreSQL
đưa một order_id vào đúng một partition; không thay bằng order_id % 4. Các khoảng log
không giao nhau và DEFAULT nhận phần còn lại. Bảng cha tái tạo dữ liệu như UNION ALL
các partition. Theo tài liệu PostgreSQL 16, UNIQUE/PK của parent partitioned phải bao gồm
partition key; quyết định HASH(order_id) giữ khóa đơn hiện có [S1].

### 3.3 Phân mảnh dọc

| Fragment | Nội dung | Ràng buộc |
|---|---|---|
| user_core | ID, username/email, trạng thái, trust, thời gian | PK user_id; UNIQUE username/email |
| user_profile | Tên, điện thoại, địa chỉ, avatar | PK/FK user_id |
| user_secret | Hash, random key, verification/reset token | PK/FK user_id; không ETL |
| user_wallet | Số dư | PK/FK user_id; giao dịch primary |

Hợp cột của bốn mảnh tái tạo đủ 20 cột user cũ; giao nhau chỉ có khóa user_id.
users_full là JOIN view chỉ đọc. Service phải tạo đủ bốn hàng trong một transaction:
FK một chiều không tự bảo đảm mọi core đều có đủ ba mảnh con. Tách bảng chưa tự tạo
phân quyền vật lý khi runtime còn dùng chung một DB principal.

Product dùng expand/contract: các cột mô tả/kích thước/tình trạng cũ vẫn ở PG; Mongo có
bản đọc và thuộc tính mới. Đây chưa phải phân rã hoàn toàn không trùng lặp; không tuyên bố
đã DROP các cột cũ hay đã mở API/UI ghi metadata tùy ý.

### 3.4 Allocation, replication và nhất quán

| Thành phần | Ghi | Đọc hiện hành | Khi lỗi |
|---|---|---|---|
| PG primary | Giao dịch, outbox, aggregate | Core và dashboard | Mất primary gây downtime, chưa tự promote |
| PG standby | Nhận WAL async | Kiểm chứng replication | Dừng standby không làm API chuyển DB |
| Mongo replica set | Metadata và projection, write majority | Metadata/filter | Mất cả set: detail fallback; filter trả 503 |
| MinIO | Byte object trong bucket private | /media gateway | Media/upload 503, phần PG tiếp tục |

Ba Mongo member là replication, không phải sharding. Write majority giảm rủi ro mất write
đã xác nhận nhưng không tạo atomicity với PG [S2]. Khi xảy ra network partition,
thiết kế ưu tiên giữ quyết định giao dịch ở primary, không ghi tiền lên bản đọc có thể cũ.
PG replica async có thể trễ; backup cùng host không thay thế off-host recovery.

## 4. Thiết kế JSON và object

### 4.1 Các collection

| Collection | Khóa nguồn/unique | Dữ liệu nhúng hoặc mở rộng |
|---|---|---|
| product_details | product_id | attributes/tags, condition/dimensions, image references |
| order_snapshots | order_id | items/payments, buyer ID, số tiền VND, voucher/current product fields |
| reviews | review_id | type=report khi rating=0, moderation/evidence |
| system_logs | log_id + created_at | action/actor/resource, payload allowlist, TTL 90 ngày |
| violation_logs | log_id | target/action/time, reason placeholder; không TTL |
| contact_messages | feedback_id | metadata, attachments references; không copy nội dung riêng |
| etl_errors | Event error key | Code lỗi an toàn, attempts, resolved; không raw exception |

Ví dụ sau chỉ là dữ liệu mô phỏng đúng hình dạng hợp đồng, không phải ảnh chụp document đang chạy:

```json
{
  "_id": "p_1", "schema_version": 1,
  "product_id": 1, "category_id": 1,
  "attributes": {"brand": "Demo", "ram_gb": 8},
  "tags": ["used"], "images": [],
  "updated_at": "2026-10-30T00:00:00Z", "deleted": false
}
```

JSON schema/Pydantic strict kiểm kiểu và field ngoài hợp đồng. BSON Date có múi giờ UTC
ở tầng Python; khi đối soát dùng độ chính xác millisecond. Ví dụ đầy đủ của sáu collection
ở docs/design/03_document_examples.json; validator hiện tại gồm etl_errors ở
docs/design/05_mongo_validators.json. Validator không thể tự xác nhận field text không chứa PII.

### 4.2 Nhúng và tham chiếu

Order snapshot nhúng items/payments vì thường được đọc cùng nhau, trong khi buyer/seller
chỉ giữ ID và field allowlist để không nhân bản PII. Product nhúng attributes có cấu trúc
thay đổi theo danh mục và các image reference. Không nhúng byte ảnh trong document.
Danh tính và quyền sửa field vẫn do PG/Mongo ownership xác định, không theo vị trí nhúng.

MinIO có ba bucket private: product-images, user-avatars và attachments. PG giữ quan hệ ảnh
với product, Mongo có bucket/key bản đọc; /media giữ URL API cũ. Avatar mới dùng key UUID
bất biến. Unlink ảnh phát sinh queue cùng transaction PG; worker kiểm không còn tham chiếu
PG/Mongo rồi xóa idempotent. Nếu S3 lỗi, queue giữ lại và run partial. Soft-delete giữ ảnh.

TTL 90 ngày chỉ áp dụng system_logs Mongo, không xóa violation log hay source PG.
TTL chạy nền nên không hứa xóa đúng từng giây tại mốc hết hạn [S3].

## 5. Chỉ mục và benchmark

### 5.1 Chỉ mục theo truy vấn

| Truy vấn | Chỉ mục/chính sách | Lý do và chi phí |
|---|---|---|
| Catalogue category + newest | Partial B-tree (category_id,created_at DESC) | Đúng predicate approved/nondeleted, tăng chi phí ghi/index |
| ILIKE title OR description | Hai GIN trigram partial + BitmapOr | Phục vụ substring search, thêm WAL và dung lượng |
| Buyer history | B-tree (buyer_id,order_date DESC) trên partitions | Merge dữ liệu, không hash-prune theo buyer |
| Seller order join | order_detail(product_id,order_id) | Giảm chi phí join, vẫn phải xét nhiều partition |
| Cart/product | UNIQUE(cart_id,product_id) | Bảo đảm toàn vẹn, không hứa nhanh hơn baseline |
| Mongo product/category/brand | Compound category_id/attributes.brand; wildcard attributes | Truy vấn field động; wildcard không bao phủ mọi tổ hợp |
| Mongo review/order history | product_id/created_at; buyer.id/order_date | Phù hợp filter/sort; unique khóa nguồn chống nhân bản |

### 5.2 Phương pháp đo PostgreSQL

Đo Ngày 4 trên PostgreSQL 16.15, DB riêng day4_bench_20261029_final: 50.016 product,
100.030 order, 100.000 log, 100.000 review. Trước/sau trên cùng DB, ANALYZE và warmup,
trung vị ba lượt EXPLAIN ANALYZE BUFFERS; không ép planner, không xóa index baseline để
làm chậm giả. Lượt text thêm dùng để đọc plan có thể khác trung vị; không trộn số text
316,549/0,385 ms với số median trong bảng dưới.

![Thời gian PG, trục log, gồm cả truy vấn chậm hơn](assets/07_pg_benchmark.svg)

<!-- BEGIN PG_BENCHMARK_TABLE -->
| Query | Trước (ms) | Sau (ms) |
|---|---:|---:|
| Catalogue | 0.261 | 0.166 |
| ILIKE search | 316.562 | 0.372 |
| Lịch sử buyer | 0.730 | 0.436 |
| Đơn seller | 44.052 | 17.521 |
| Review history | 0.085 | 0.158 |
| Report rating=0 | 0.145 | 0.327 |
| Cart lookup | 0.048 | 0.114 |
| Order PK | 0.050 | 0.088 |
| Log theo tháng | 4.410 | 4.582 |
<!-- END PG_BENCHMARK_TABLE -->

Dung lượng index vật lý tăng 35.225.600 → 58.736.640 byte. Migration ở tập benchmark mất
11,47 giây, không gồm toàn bộ backup/restore/startup. Review/report/cart/PK/log không có
bằng chứng nhanh hơn trong workload này; partition pruning là bằng chứng định tuyến, không
đồng nghĩa có lợi ích latency. Chưa đo throughput ghi đồng thời hoặc ETL 100k order.

### 5.3 MongoDB và ý nghĩa số liệu

MongoDB 7.0.43, mỗi collection tạm có 10.000 document. Pha trước chỉ có _id index;
pha sau thêm index ứng dụng. Một explain executionStats mỗi pha, không hint; ưu tiên
docs examined vì milliseconds dễ nhiễu.

![MongoDB documents examined trước/sau, trục log](assets/07_mongo_benchmark.svg)

<!-- BEGIN MONGO_BENCHMARK_TABLE -->
| Collection | Docs trước → sau | Returned | ms trước → sau |
|---|---:|---:|---:|
| product_details | 192 → 20 | 20 | 4 → 2 |
| reviews | 10000 → 10 | 10 | 83 → 2 |
| order_snapshots | 10000 → 10 | 10 | 20 → 1 |
<!-- END MONGO_BENCHMARK_TABLE -->

Nguồn đo: docs/benchmark/pg/summary.json, docs/benchmark/mongo/summary.json và các file
before_*/after_*.json/.txt. Collection benchmark tạm đã dọn; không dùng số đo Mongo7 để
tuyên bố Mongo8 đã được kiểm chứng. Số liệu benchmark không phải số liệu của seed demo nhỏ.

## 6. ETL và kiểm tra chất lượng

![Luồng outbox và ownership hiện hành](assets/07_etl.svg)

### 6.1 Sáu pipeline

| Pipeline | Nguồn → đích | Quy tắc quan trọng |
|---|---|---|
| Product | PG product/image → product_details | FK/key thực tế; giữ attributes/tags Mongo-owned |
| Order | order/detail/transaction/voucher/product → snapshot | Giá mua từ line; giữ raw status/fraud score, current fields có nhãn |
| Review/report | review → reviews | rating=0 là report; giữ moderation/evidence |
| Logs/audit/contact | Ba bảng PG → ba collection | Allowlist/placeholder, log dùng khóa ghép |
| Media | seed/volume → MinIO | Chỉ copy key thiếu, stat size/type; không suy FK từ filename |
| Aggregate | delivered line → report_daily_sales | Ngày Việt Nam, gross subtotal, current seller/category |

Outbox được ghi cùng transaction I/U/D của nguồn trước khi full snapshot. Worker chọn
event chưa hoàn tất theo status/due, không lấy MAX(id) làm watermark vì sequence ID không
phải thứ tự commit. Có một advisory lock cho worker; nguồn đọc REPEATABLE READ. Mongo upsert
theo business key bằng partial $set, giữ _id legacy và metadata Mongo-owned.

### 6.2 Replay, lỗi và thời gian

ACK chỉ sau write Mongo thành công. Crash sau write trước ACK dẫn tới replay, không phải
exactly once; idempotence ngăn nhân bản. Retry có backoff, mã lỗi an toàn, dead-letter và
đối soát. Lỗi giữa chừng giữ rows_in/out đã xử lý. Worker poll 60 giây sau cycle trước,
mục tiêu độ trễ dưới 5 phút ở tải bình thường; đây không phải cam kết khi lỗi/tải lớn.

Người dùng đã xác nhận toàn bộ timestamp cũ là giờ Việt Nam. 005 ghi provenance, không
UPDATE timestamp nguồn. Backend mới dùng transaction UTC, SQL trực tiếp theo timezone phiên;
thiếu origin thì quarantine. Tiền copy phải nguyên VND trong int64; NULL/fraction/NaN/sai
tổng bị giữ lỗi, không tự làm tròn hoặc thay 0. D8 transaction_status cũ vẫn giữ nguyên.

### 6.3 Đối soát và báo cáo

Mỗi cycle kiểm count và field vừa xử lý; full/daily reconcile kiểm mọi key/field PG-owned
và image reference size/type. 32 tham chiếu ảnh không được so trực tiếp với 95 object,
vì object gồm avatar và alias. rows_in/out tính thao tác, không phải số document độc lập.
Full Ngày 6 có 57 in/57 out, gồm 16 product, 30 order, 11 violation; 32/32 ảnh hợp lệ.

gross_sales_vnd cộng subtotal hàng đã giao, chưa trừ discount/chưa cộng shipping;
total_revenue API cũ cộng final_amount. Không cộng orders_count giữa các nhóm seller/category
để suy tổng đơn duy nhất. Dashboard ghi as_of/available/stale; báo cáo hiện đọc primary.

## 7. Triển khai và kiểm thử

### 7.1 Migration và bảo toàn dữ liệu

| Version | Nội dung |
|---|---|
| 001 | Index theo truy vấn, UNIQUE cart/product |
| 002 | HASH order, RANGE system_log, khóa log ghép |
| 003 | User core/profile/secret/wallet, users_full |
| 004 | Metadata content-type/size ảnh |
| 005 | Outbox, provenance, runs/state, aggregate |
| 006 | Durable media cleanup |

SQL-first baseline chỉ nạp một lần khi DB trống; runner áp version/checksum dưới advisory
lock và transaction. DB đang có dữ liệu không được reset/reseed. Rollout dùng maintenance,
backup cả ba kho và thử restore; đối soát count/digest 18 bảng nguồn trước/sau trước khi mở lại.
Lượt Ngày 6 từng giữ bảo trì vì CLI status dùng sai RealDictCursor; đã sửa, test hồi quy và
kiểm lại snapshot rồi mở dịch vụ. Bằng chứng giữ cả lỗi và phục hồi, không báo lần đầu là PASS.

### 7.2 Kết quả kiểm thử và hợp đồng API

| Nhóm | Kết quả và phạm vi |
|---|---|
| Backend regression | 96 trường hợp, DB mới, gồm chức năng cũ và migration |
| ETL | 28 trường hợp, PG/Mongo thật, key MinIO thử riêng |
| API Ngày 6 | 21 trường hợp + 1 hồi quy CLI status = 22 trường hợp khác nhau |
| Frontend | 15 test, gồm biểu đồ và smoke component với HTTP test backend |
| Lỗi/phục hồi | 9 scenario trên project riêng, không dừng oldshop-data |
| API compatibility | Giữ 64 path cũ và mọi method/field cũ; thêm metadata/report/image-delete |

146 backend là số trường hợp khác nhau qua các lượt phạm vi riêng, không phải tuyên bố
một process duy nhất chạy đủ tất cả. CI đã cấu hình PG/Mongo/MinIO integration và frontend
tests; chưa có bằng chứng GitHub Actions remote trong tác vụ này.

### 7.3 Thực nghiệm lỗi dịch vụ

| Kịch bản | Kết quả đã kiểm chứng Ngày 6 |
|---|---|
| Dừng mongo2 rồi mở lại | Catalogue/detail/cart/order/admin vẫn 200; replica set phục hồi |
| Dừng PG replica rồi mở lại | Primary phục vụ giao dịch/báo cáo; standby bắt kịp WAL |
| Dừng MinIO rồi mở lại | Media/upload 503, avatar cũ giữ nguyên; phần PG vẫn 200 |
| Dừng cả Mongo rồi mở lại | Detail fallback PG 200, filter thuộc tính 503, readiness phục hồi |

Container Mongo ping được chưa chắc đã bầu PRIMARY xong; kịch bản chờ readiness hữu hạn
khi phục hồi. /ready 503 báo phụ thuộc xuống, /health 200 chỉ báo process sống. Không có
thí nghiệm mất PG primary tự promote, mất host hay quorum trên nhiều máy.

### 7.4 Tổng duyệt Ngày 7

Ngày 30/10, chín chặng demo trên project seed riêng đạt: partition/WAL, Mongo/API,
trang sản phẩm, MinIO xem JPEG, full ETL hai lần, EXPLAIN, dừng và phục hồi mongo2.
Đối soát 16 product, 30 order, 11 violation không nhân bản; attributes giữ nguyên,
32/32 ảnh tham chiếu hợp lệ. Video 366,32 giây, 1280×720, phụ đề Việt; có 10 ảnh dự phòng.
Sau cleanup, stack người dùng vẫn đủ chín service khỏe, ETL pending/dead=0.
Evidence: docs/evidence/day7_rehearsal.json, day7_stack.json, day7_output_validation.json.

## 8. Kế hoạch hoàn thiện và vận hành

| Hạng mục | Mức hoàn thiện theo phạm vi | Vai trò | Hạn kế hoạch |
|---|---|---|---|
| Audit/ERD/phân loại, D1–D6 | 100% | A | 27/10 |
| Phân mảnh/phân bổ/Compose | 100% local | A/D | 28/10 |
| JSON/Mongo/MinIO | 100% local Mongo7 | B | 29/10 |
| Index/partition/benchmark | 100% workload đã nêu | A | 30/10 |
| ETL/outbox/quality | 100% local | C | 31/10 |
| Tích hợp BE/FE, hồi quy | 100% local | C | 01/11 |
| CI remote | Đã cấu hình, chưa chạy remote | C/D | Trước release công khai |
| Báo cáo/slide/demo | Đạt local: báo cáo, 18 slide, demo 6:06 | D + A/B/C | 02/11 |

Thực hiện báo cáo ngày 30/10, sớm hơn lịch kế hoạch. A/B/C/D là vai trò, chưa có tên
thành viên để gán; phần trăm không phải coverage hoặc mức sẵn sàng production.

Trước production cần rotate seed password/app keys, TLS, phân quyền PG runtime/migration,
backup ngoài host và kiểm RPO/RTO; rà soát public user DTO, PayPal idempotency, moderation
lặp và kiểm nội dung upload. Metadata write UI/API tùy ý chưa mở. Cần retention có kiểm soát
cho outbox/origin/run/cleanup; không purge event chưa ACK.

Hướng mở rộng cần máy độc lập và thử nghiệm riêng: Patroni/fencing, Mongo shard, MinIO
distributed, FDW vùng, CDC/Debezium/Kafka. Một worker/N+1 extract và aggregate rebuild toàn
bộ chưa benchmark tải 100k. Search metadata có cap 5000 candidate, không nới vô hạn để che
giới hạn. Timestamptz PG và enum D8 là quyết định/migration riêng.

## 9. Kết luận

Hệ thống đã hiện thực ba mô hình dữ liệu với chủ sở hữu field rõ, partition/tách user,
ETL replay được và API suy giảm có kiểm soát. Nâng cấp giữ dữ liệu nguồn và hợp đồng cũ,
thay biểu đồ giả bằng aggregate thật, đồng thời chỉ ra giới hạn về consistency và vận hành.
Kết quả có giá trị ở phạm vi một máy và workload đã đo; chưa suy rộng thành HA đa máy,
SLA ETL hay hiệu năng production. Bộ nộp kèm source sơ đồ, evidence và script tái lập.

## Phụ lục A. Chạy và trình diễn

```bash
# Sau khi chuẩn bị report tooling và hai image day6 theo 07_demo_script.md:
python deploy/scripts/build-day7.py
python deploy/scripts/demo-day7.py --mongo-image mongo:7.0
python deploy/scripts/validate-day7.py
```

Script demo tạo secrets ngẫu nhiên và project tạm rồi dọn sau quay. Với stack giữ dữ liệu,
theo runbook docs/design/03_json_design.md: provision bucket/app role, seed_media thành công
rồi mới bật STORAGE_BACKEND=minio; không chỉ đổi biến khi ảnh còn trên đĩa local.
Sau đó theo 05_etl.md và 06_completion_plan.md. DB hiện hữu dùng maintenance apply-day6.sh,
không chạy lại init.sql. Host/kernel tương thích có thể dùng Mongo8 mặc định cấu hình;
demo local kiểm chứng bằng Mongo7 theo ngoại lệ đã ghi nhận.

Demo riêng và quay video: deploy/scripts/demo-day7.py. SQL pgAdmin4: docs/report/demo_pgadmin.sql.
Mongo shell/Compass: docs/report/demo_mongo.js. Lời dẫn và câu hỏi: docs/report/07_demo_script.md,
docs/report/07_qa.md. Manifest gói nộp có SHA-256; không chứa .env, private backups, DB volume,
git credentials hoặc model weights ngoài phạm vi source. Tag release chỉ local, không tự push.

## Phụ lục B. Hồ sơ bằng chứng

| Nội dung | Tệp nguồn trong repository |
|---|---|
| Audit/nguồn dữ liệu | docs/01_data_inventory.md, docs/DAY1_REVIEW.md, docs/decisions.md |
| Phân tán/phân mảnh | docs/design/02_distribution_strategy.md, 02_fragmentation_matrix.md |
| Schema và validators | database/04_migrations/*.sql; docs/design/05_mongo_validators.json |
| Mô hình hiện hành | docs/diagram/07_erd_current.dbml; 07_architecture_current.puml; 07_data_flow_current.puml |
| Benchmark PG/Mongo | docs/benchmark/README.md và pg/mongo/summary.json; đủ raw explain |
| ETL | docs/design/05_etl.md; docs/evidence/day5_*.json |
| Tích hợp/lỗi/phục hồi | docs/DAY6_FINDINGS_LOG.md; docs/evidence/day6_*.json/.txt |
| Tổng duyệt Ngày 7 | docs/DAY7_FINDINGS_LOG.md; docs/evidence/day7_rehearsal.json |
| Kế hoạch còn lại | docs/design/06_completion_plan.md |

## Phụ lục C. Trích SQL và cấu hình tái lập

Đoạn sau trích migration 002 để giải thích khóa phân mảnh; không chạy rời trên DB hiện hữu.
Runner đầy đủ còn bảo toàn FK, đối chiếu dữ liệu và đổi tên bảng trong transaction.

```sql
CREATE TABLE order_day4_new (LIKE "order" INCLUDING ALL)
PARTITION BY HASH(order_id);
CREATE TABLE order_h0 PARTITION OF order_day4_new
FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE system_log_day4_new
(LIKE system_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING STORAGE)
PARTITION BY RANGE(created_at);
ALTER TABLE system_log_day4_new ADD PRIMARY KEY(log_id, created_at);
```

Các tệp 001_indexes.sql, 002_partitioning.sql, 003_vertical_split.sql, 004_media_metadata.sql,
005_etl_outbox.sql và 006_media_cleanup.sql trong database/04_migrations là bản thực thi đầy đủ.
Migration runner kiểm checksum và advisory lock; không sửa lịch sử đã áp.

```sql
-- Query Tool: chỉ đọc; kiểm chứng routing thực tế.
SELECT tableoid::regclass, count(*) FROM "order" GROUP BY tableoid;
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_status FROM "order" WHERE order_id=1;
SELECT status, count(*) FROM etl_outbox GROUP BY status;
```

Cấu hình dưới đây chỉ minh họa các giá trị không bí mật. Credentials được sinh riêng bằng
prepare-data-env.py; cấu hình đầy đủ nằm trong deploy/.env.data.example và Compose.

```ini
POSTGRES_IMAGE=postgres:16-alpine
MONGO_IMAGE=mongo:8.0.32
STORAGE_BACKEND=minio
ETL_POLL_SECONDS=60
ETL_BATCH_SIZE=100
ETL_MAX_ATTEMPTS=5
# Local kernel: thay MONGO_IMAGE=mongo:7.0 và ghi nhận phiên bản thực tế.
```

## Tài liệu tham khảo

[S1] PostgreSQL 16, Table Partitioning: https://www.postgresql.org/docs/16/ddl-partitioning.html

[S2] MongoDB, Write Concern for Replica Sets: https://www.mongodb.com/docs/manual/core/replica-set-write-concern/

[S3] MongoDB, TTL Indexes: https://www.mongodb.com/docs/manual/core/index-ttl/

Các claim triển khai và số đo dựa trên source/evidence của chính repository, không lấy số
benchmark từ tài liệu nhà cung cấp. Truy cập tài liệu kỹ thuật ngày 30/10/2026.
