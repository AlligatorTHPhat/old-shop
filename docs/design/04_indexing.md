# Ngày 4 — Index, partition, tách user và benchmark

Thực hiện 29/10/2026, theo D3/D4/D6 đã chốt. DDL chuẩn nằm trong
`database/04_migrations`; [ERD sau migration](../diagram/04_erd_target.dbml) mô tả
bảng cha logic, không vẽ lặp mỗi partition.

## Truy vấn nóng → chỉ mục → lý do → chi phí ghi

Tên bảng/cột dùng đúng nguồn SQL: `product.title`, `"order".buyer_id/order_date`,
`order_detail`; không có products.name hay orders.user_id/created_at/seller_id.

| Nguồn / truy vấn | Trường và index giữ/thêm | Lý do và bằng chứng | Chi phí ghi |
|---|---|---|---|
| CRUDProduct.get_by_category, catalogue theo category + mặc định mới nhất | **Thêm** partial `idx_product_catalogue(category_id,created_at DESC) WHERE status=1 AND is_deleted=false` | Index Scan lấy 20 dòng; ngày càng nhiều category vẫn có thứ tự. API category nay thực sự áp dụng sort_by; trước đó không ORDER BY | Một B-tree cho sản phẩm approved; đổi status/is_deleted phải thêm/xóa entry |
| CRUDProduct.search, ILIKE title **OR** description | **Thêm** hai GIN trigram partial cho title và description cùng predicate visible | BitmapOr của cả hai GIN; một GIN title không đủ cho OR description | Tốn dung lượng/CPU khi sửa text, GIN pending list/VACUUM; không chỉ mục text mọi trạng thái |
| CRUDOrder.get_by_buyer, pending PayPal reuse | **Thêm** partial `idx_order_buyer_date(buyer_id,order_date DESC) WHERE is_deleted=false` | Index Scan trên mỗi hash partition, Merge Append lấy 20; buyer_id không phải partition key | Một B-tree/partition; update buyer/date/delete làm đổi entry |
| CRUDOrder.get_by_seller: product → order_detail → order | **Thêm** `idx_order_detail_product_order(product_id,order_id)`; giữ idx_product_seller và idx_order_detail_order | Index Only Scan nhánh product→order_detail; order không có seller_id vì một đơn có thể nhiều seller | Một B-tree; FK product và join đổi entry khi sửa product_id/order_id |
| CRUDShoppingCart.add_item tìm cặp cart/product | **Thêm** UNIQUE `uq_cart_product(cart_id,product_id)` | Vừa lookup vừa chống trùng do ghi đồng thời/bypass API; test thực chứng SQLSTATE 23505 | Kiểm tra unique mỗi insert/update, không phải tự sửa mọi race reserve stock |
| CRUDProduct.reviews / CRUDModerator.get_reported_reviews | **Giữ** idx_review_product / idx_review_rating | Thử composite product/date và partial rating=0 nhưng planner vẫn dùng index hiện có ở workload này, nên bỏ hai đề xuất khỏi migration cuối | Không thêm chi phí ghi cho hai ứng viên chưa có bằng chứng |
| Transaction theo order_id / reference_number | **Giữ** idx_transaction_order, UNIQUE(reference_number) | Đã có từ baseline, không tạo trùng; transaction không partition | Chi phí như trước |
| Admin count/sum nhiều trạng thái, catalogue giá, moderation | **Giữ** status/price/date/category/seller indexes hiện hữu | Tổng hợp toàn bộ có thể Seq Scan hợp lý; chưa đủ bằng chứng thêm covering/status index | Tránh tăng chi phí balance/quantity/view_count và cache vô ích |
| System log tháng / actor/action | **Giữ** các B-tree user/action/created_at trên parent, clone xuống children | Prune chỉ tháng liên quan; có thể Seq Scan trong một tháng khi cần đọc phần lớn partition | Tạo index theo mỗi partition; chưa thêm BRIN trùng khi không có chứng cứ lợi ích |

Không xóa index baseline để tạo hình ảnh Seq Scan giả; không dùng enable_seqscan=off/hint.
Các index cùng chức năng chỉ tồn tại một lần. Những truy vấn đã nhanh không được hứa nhanh hơn.

## Chuỗi migration và tính an toàn

- `001_indexes.sql`: sáu index mới. Nếu có cặp cart/product trùng, UNIQUE thất bại
  và rollback cả version; không tự gộp dữ liệu hoặc hoàn tồn kho.
- `002_partitioning.sql`: order HASH(order_id), bốn phần; system_log RANGE(created_at)
  theo tháng, PK(log_id,created_at), có DEFAULT nhận ngày ngoài lịch. Không đổi timestamp.
- `003_vertical_split.sql`: rename user→user_core để FK giữ nguyên OID; copy ba bảng con,
  giữ mọi 20 cột, UNIQUE/default/NOT NULL và user_role. View users_full tái tạo đúng thứ tự cột.
- `004_media_metadata.sql`: thêm content_type/size_bytes nullable, CHECK size>=0 cho
  product_image. Không đổi image_url; chỉ backfill file thực sự đọc được.

`schema_migrations(version,applied_at,checksum)` ghi cùng transaction DDL/DML từng file.
Runner dùng một connection và session advisory lock xuyên suốt các version, dừng nếu checksum
khác hoặc lịch sử không phải prefix hợp lệ. Với DB chưa có lịch sử, kiểm tra fingerprint v0:
167 cột gồm kiểu/default/nullability, 62 constraint, 71 index và hai trigger. Schema lệch phải
review, không coi có bảng user là đủ. DDL ngoài transaction không được dùng trong MVP.

Version trước đã commit không rollback nếu version sau lỗi: giữ bảo trì, sửa bằng migration mới
hoặc khôi phục backup có kiểm soát, không ép sửa checksum. SQL-first baseline `init.sql` giữ
nguyên v0; `init_db.py` chạy runner cả DB mới và DB đã có. CI cũng chạy migrate trước pytest.
`DATABASE_URL` ưu tiên và được normalize/escape; engine, bootstrap, pg connection và runner
cùng thông tin, kể cả query sslmode/options. psql nhận service file tạm 0600, không đưa secret vào argv.

### Order: HASH và toàn vẹn

PK(order_id), sequence hiện hữu và mọi CHECK/NOT NULL/FK được giữ. Migration clone index,
copy và so sánh hai chiều EXCEPT ALL trước swap. LIKE không copy FK nên outbound FK được
chép riêng, inbound FK được lưu định nghĩa rồi trỏ lại parent mới, kể cả ON DELETE CASCADE
của transaction. Không dùng DROP CASCADE. Sequence giữ nguyên giá trị/gap, không reset MAX(id).
Trigger order_detail chống tự mua vẫn hoạt động; lỗi trigger rollback cả log cùng transaction,
không tuyên bố log chặn đã được ghi bền vững độc lập (D11 còn nguyên).

Order lookup có order_id prune 3/4 partition. Lịch sử buyer/seller không prune theo hash này,
phải đọc/merge các partition; đây là giới hạn của quyết định HASH(order_id).

### System log: danh tính ghép và vòng đời partition

Giữ BIGSERIAL log_id; PK gồm created_at vì unique/PK trên parent phải chứa partition key.
ORM dùng cả hai trường, không dùng session.get(SystemLog,log_id). SQL get_audit_trail đã
trả cả log_id/log_time, khi ETL Ngày 5 tạo nguồn log phải dùng cặp này. Không có FK vào log_id.
Giữ TIMESTAMP naive, không tự chốt D7 hay diễn giải lại giờ cũ.

Migration tạo tháng từ dữ liệu sớm nhất đến tháng hiện tại + ba tháng tương lai, cộng DEFAULT.
Kiểm tra span quá 200 năm thì dừng để review. Không retention/delete PG log. Chạy định kỳ:

```bash
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --entrypoint python backend -m scripts.maintain_log_partitions --month 2027-02
```

Script có lock, dọn đúng khoảng ngày từ DEFAULT vào tháng mới trong cùng transaction rồi
ATTACH; chạy lại bỏ qua partition có sẵn. Có thể khóa ghi ngắn, chạy lúc ít tải. DEFAULT
không thay thế lịch bảo trì: phải theo dõi số dòng ở đó. Test đã kiểm chứng di chuyển và giữ log.

### Tách user và đường ghi

User ORM map **user_core**, ba model UserProfile/Secret/Wallet ghi bảng vật lý. Association
proxy giữ contract Python/API cũ; constructor luôn tạo đủ bốn dòng trong một transaction
cả đăng ký lẫn tạo moderator. Lỗi một mảnh rollback tất cả. FK giữ user_role nhiều role.
users_full là JOIN view chỉ đọc, không map ghi, không INSTEAD OF trigger. SQL helper
create_user_with_hash/authenticate_user/log_user_login/get_audit_trail đã cập nhật tương ứng.

Auth token lookup chỉ đọc core/role; password/OTP chỉ tải secret khi cần. Serializer hiện có
không trả password/token. Profile/wallet tải theo nhu cầu; service dùng primary cho mọi giao dịch.
Tách bảng không tự cấp row-level security: app hiện dùng một DB principal; owner vẫn có quyền
trên secret/wallet. REVOKE PUBLIC không thay cho việc tách tài khoản DB theo quyền ở giai đoạn sau.
FK một chiều không bắt buộc mọi core có đủ con khi DBA ghi SQL trực tiếp; đối soát phát hiện
thiếu con và service phải giữ invariant. Timestamp updated_at của core vẫn đổi khi sửa mảnh con.

Product giữ đủ cột PG như D4 expand/contract; chưa DROP description/condition/weight/warranty.
FDW/node-b, phân vùng transaction/product, Mongo sharding không triển khai trong MVP.

## MongoDB và MinIO

Index Mongo dùng `services/mongo_schema.py` đã tạo từ Ngày 3, không tạo index sai tên trong
ví dụ kế hoạch: order_snapshots dùng buyer.id/order_date và order_status/order_date;
system_logs dùng action/actor_id/created_at. TTL 90 ngày chỉ cho bản sao system_logs,
không xóa violation audit hoặc PG log. Init lặp cập nhật validator/index, không drop collection.

Benchmark ba collection tạm, mỗi collection 10.000 document, validator như app. Đo trước
chỉ có _id index và sau index thực tế; `explain executionStats`, không hint. Kết quả và giới hạn
phiên bản Mongo 7.0.43 được ghi trong [benchmark](../benchmark/README.md); Mongo 8 chưa được xác minh.
Mọi collection tạm được dọn đúng UUID, không ghi dữ liệu giả vào collection ứng dụng.

Object key mới products/{id}/{uuid}.ext, avatar users/{id}/avatar-{uuid}.ext từ Ngày 3.
content_type/size_bytes của ảnh mới ghi PG trong cùng commit product_image; backfill lấy
stat **đúng key từ image_url**, không list bucket để trả catalogue. Bucket scan chỉ dùng khi backup.
Image Mongo schema đã có bucket/key/content_type/size cho ETL sau này; không dual-write giả
nguyên tử hai DB. Ảnh ngoài /media hay mất file để metadata NULL và báo image_id, không bịa số byte.
Avatar/attachments chưa có metadata bảng riêng, vẫn giữ contract cũ.

## Kiểm thử, vận hành và rollback

```bash
# Build trước để test đúng image có migration.
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml build backend
bash deploy/scripts/test-day4.sh
# Stack đang có profile dự phòng; base mới có thể bỏ --resilience.
bash deploy/scripts/apply-day4.sh --resilience
```

Test runner tạo DB mới, giữ lại để kiểm tra. Không chạy regression ghi trên DB ứng dụng.
Apply dừng frontend + backend (không chỉ frontend); chưa có ETL worker để dừng. Backup PG,
Mongo/BSON và MinIO theo bucket/key vào deploy/backups (ignored, private), restore PG vào DB
mới để đối chiếu digest từng dòng/cột nguồn. Mongo/MinIO phục hồi thử vào tên/prefix UUID,
so sánh bytes rồi dọn đúng dữ liệu thử. Sau migrate/backfill đối chiếu lại 18 bảng nguồn,
chỉ mở lại khi không lệch. Các file backup có dữ liệu nhạy cảm, không đưa vào docs/Git.

Backup hiện ở cùng máy để diễn tập, **chưa là backup ngoài máy/chịu mất máy**. Trước vận hành
thực phải sao chép ra nơi độc lập. Archive MinIO ở đây giữ byte/key/content-type, chưa xuất
version history, tags hoặc toàn bộ cấu hình IAM; bucket/policy tạo lại bằng minio-init hiện tại.

Nếu lỗi: script dừng API/frontend, giữ backup và version đã commit. Kiểm tra log và trạng thái;
không chạy image day3 vào schema đã split. Muốn quay về v0 phải restore PG vào **database mới**,
đối chiếu bằng verify_day4, trỏ cấu hình về DB đó cùng image cũ; không tự drop/reseed DB đang dùng.
Nếu có ghi mới sau cutover, cần kế hoạch hợp nhất dữ liệu trước khi restore backup cũ.

Nguồn kỹ thuật: [PostgreSQL 16 partitioning](https://www.postgresql.org/docs/16/ddl-partitioning.html),
[SQLAlchemy association proxy](https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html).
Các số đo trong repository là kết quả cục bộ, không phải cam kết SLA.
