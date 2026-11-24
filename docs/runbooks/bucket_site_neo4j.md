# Vận hành bucket/site, seed phân tán và Neo4j

Chạy từ thư mục gốc repository. Stack `oldshop-buckets` có core, site A/B, MongoDB, Neo4j và media volume riêng. Không cần xóa `oldshop`, `oldshop1`, `oldshop2` hoặc chạy `docker compose down -v`.

## 1. Khởi tạo một môi trường mới

```bash
# Chỉ chạy lần đầu: script từ chối ghi đè file credential đã có.
python3 deploy/scripts/prepare-bucket-env.py
dc() { docker compose --env-file deploy/.env.bucket -f deploy/docker-compose.bucket.yml "$@"; }
dc up -d core site-a site-b mongo neo4j
dc build backend
dc --profile tools build tools
dc --profile tools up -d tools
dc exec tools python -m scripts.bucket_setup --sites A B
dc exec tools python -m scripts.graph init
dc exec tools python -m scripts.seed plan --dataset demo-v2 --output /tmp/demo-plan.json
dc exec tools python -m scripts.seed apply --plan /tmp/demo-plan.json
```

Chờ Mongo/Neo4j khởi động xong trước `bucket_setup`/`graph init`; các lệnh lỗi kết nối có thể chạy lại. `bucket_setup` chỉ bootstrap schema/reference contract, không nạp demo. Nó từ chối database legacy không rỗng, kiểm identity/dataset/checksum migration và gắn Mongo/graph với UUID của core.

`apply` trả **run ID thực tế**; chạy lại cùng dataset dùng lại run cũ. Plan mới có thể có UUID dự kiến khác. Thay `<run-id>` bên dưới bằng ID trong kết quả apply:

```bash
dc exec tools python -m scripts.seed resume --run-id <run-id>
dc exec tools python -m scripts.verify_seed --run-id <run-id> --include-graph
dc exec tools python -m scripts.seed manifest --run-id <run-id>
dc --profile app up -d backend worker frontend
```

Nếu fingerprint/mapping/generation đổi, lập **plan mới bằng tên file mới** rồi apply. Seeder kiểm lại từng phase, ID và drift; nó không tự reset dữ liệu đã sửa. Chạy lại sau khi người dùng mua/bán có thể báo drift tồn kho/đơn; đó là bảo vệ dữ liệu, không phải yêu cầu xóa DB. Caption/description do người dùng sửa được giữ nguyên. Manifest nằm bền vững ở core `seed_manifest`, không phụ thuộc file `/tmp` của container.

Các địa chỉ local:

| Dịch vụ | Địa chỉ |
|---|---|
| Giao diện | http://localhost:57600 |
| API / Swagger | http://localhost:57680/api/docs |
| Readiness SQL/sites/Mongo | http://localhost:57680/health/ready |
| Neo4j Browser | http://localhost:57474 |
| Core / A / B / C | localhost:57630 / 57631 / 57632 / 57633 |

Demo đăng nhập `bucket3@example.com`, mật khẩu `BucketDemo123!`; admin `bucket1@example.com`, moderator `bucket2@example.com`. Đây là tài khoản **demo**, chỉ nằm trong stack local này. Credential hạ tầng ở `deploy/.env.bucket` (git ignore, quyền 0600); không đưa file đó vào báo cáo/log.

## 2. Hợp đồng phân bổ và nghiệp vụ

Nguồn hợp đồng: [`bucket-v2.json`](../../database/distributed/contracts/bucket-v2.json), implementation dùng chung: [`allocation.py`](../../backend/app/services/allocation.py).

```text
seller_id → SHA256("oldshop:seller:v1:" + seller_id)
          → 8 byte đầu, unsigned big endian % 256
          → bucket_assignment → owner_site_id + ownership_epoch
```

Ban đầu bucket 0–127 ở A, 128–255 ở B. Seller không phải site: nhiều seller cùng bucket/site, một user vẫn có thể vừa mua vừa bán. Không đổi hash/modulus khi thêm server. Số bucket hai bên bằng nhau không bảo đảm tải/số product bằng nhau; phải đo tải rồi chuyển bucket cần thiết.

Core giữ identity/reference, directory, order/review và operation log. Owner site giữ product/image/reservation/stock operation. Cart giữ hàng, checkout dùng saga có intent bền vững, hủy giải phóng hàng đúng một lần; worker phục hồi intent chưa hoàn tất. Client có thể gửi `Idempotency-Key` UUID khi tạo listing/cart/order/PayPal và **dùng lại cùng key/body khi retry**. Đơn nhiều seller có fulfillment riêng; seller chỉ tiến trạng thái phần của mình.

Gateway `uvicorn app.catalogue_gateway:app` cũng dùng resolver/repository này khi `BUCKET_MODE=true`; các stack gateway legacy đang chạy tiếp tục giữ cấu hình cũ. Gateway mới chỉ đọc, giữ dạng `{items,total,skip,limit,sites}`; giới hạn tập đếm 100.000 và yêu cầu thu hẹp filter nếu vượt giới hạn.

Metadata ảnh thuộc Mongo `product_details.image_metadata`; SQL giữ image membership. ETL SQL chỉ cập nhật các trường của SQL. Sửa metadata tăng revision và pending trong một update nguyên tử; worker chỉ ACK revision đã xử lý. Bỏ metadata/clear caption cũng được đồng bộ lên graph.

## 3. Tìm ảnh và sản phẩm liên quan

```bash
curl -fsS 'http://localhost:57680/api/v1/images/search?q=alphaonly'
curl -fsS 'http://localhost:57680/api/v1/images/search?q=anh%20tu%20lieu&limit=5'
curl -fsS 'http://localhost:57680/api/v1/products/100004/related'
```

ID ở ví dụ related là ID của demo hiện tại; với môi trường khác lấy ID từ `/products`. Trong Shop chọn “Tìm từng ảnh theo chú thích và mô tả (theo từ khóa)” và nhập từ xuất hiện trong caption/description. API trả từng ảnh phù hợp và `next_cursor`; truyền cursor cùng query để lấy trang sau. Query/cursor bị thay đổi hoặc generation khác sẽ bị từ chối.

Tìm kiếm dùng token AND, không phân biệt hoa/thường và hỗ trợ không dấu tiếng Việt; đây là tìm văn bản metadata, không phải tìm theo pixel hay AI ngữ nghĩa. SQL kiểm lại visibility/owner/image membership và Mongo kiểm lại annotation trước khi trả ảnh. Không trộn mọi ảnh của product vào kết quả. Index trễ có thể làm thiếu kết quả mới; response ghi `consistency=best_effort`, không cam kết tổng số chính xác. Graph không khả dụng trả 503 cho chức năng graph; CRUD SQL vẫn hoạt động.

## 4. Theo dõi, replay và rebuild

```bash
dc exec tools python -m scripts.graph status
dc exec tools python -m scripts.graph incremental
dc exec tools python -m scripts.graph retry-dead
dc exec tools python -m scripts.graph reconcile
```

`app_delivery` có ACK riêng cho Mongo/graph ở mỗi nguồn, retry rồi dead letter; `status` còn đếm metadata pending. Sau khi sửa nguyên nhân lỗi mới retry dead. Backfill/reconcile chạy lại từ nguồn chính, không seed một bộ graph độc lập. Các công cụ hiện tại dành cho lab vừa/nhỏ, backfill chưa có checkpoint theo chunk hay giới hạn bộ nhớ cho hàng triệu dòng.

Rebuild dùng **generation mới** và khóa consumer. Ví dụ đang ở generation 1:

```bash
dc stop worker
dc exec tools python -m scripts.graph rebuild --generation 2
# Sau khi thành công, đặt GRAPH_GENERATION=2 trong deploy/.env.bucket.
dc --profile tools --profile app up -d --force-recreate tools backend worker
```

Nếu rebuild lỗi, chạy lại cùng generation đang `rebuilding`. Trong thời gian đó graph API trả 503; worker cũ không ACK event cho generation mới. Namespace cũ được giữ lại; chưa có tự động dọn generation cũ. Reconcile thông thường không thay generation.

## 5. Thêm site và chuyển bucket

```bash
dc --profile expansion up -d site-c
dc exec tools python -m scripts.bucket_setup --sites A B C
# Thay 94 bằng bucket thực sự muốn chuyển, xem bucket_assignment trước.
dc exec tools python -m scripts.move_bucket plan --bucket 94 --to-site C --output /tmp/move-94.json
dc exec tools python -m scripts.move_bucket apply --plan /tmp/move-94.json
# Nếu bị gián đoạn:
dc exec tools python -m scripts.move_bucket resume --operation-id <operation-id>
```

Quy trình đánh mapping `moving`, đóng lease nguồn và đợi writer cũ, copy product/image/reservation/operation ledger, kiểm snapshot rồi cutover epoch mới. Request gặp bucket đang chuyển trả lỗi tạm thời để retry. Media dùng shared object key/volume, không chứa site trong ID; URL API và product/image ID giữ nguyên.

Nguồn cũ được giữ ở trạng thái frozen. Rollback thực hiện **một move ngược mới**, copy cả ghi đã phát sinh tại đích; không chỉ sửa bảng mapping và không bật lại writer có epoch cũ. C không tự nhận bucket sau khi đăng ký. Không chạy nhiều move chồng nhau cho cùng bucket.

## 6. Backup/restore và nhập dữ liệu cũ

Dừng writer ứng dụng/worker trong cửa sổ bảo trì để lấy snapshot nghiệp vụ nhất quán giữa nhiều nguồn. Ví dụ diễn tập ở stack local:

```bash
dc stop backend worker
dc exec tools python -m scripts.bucket_backup_check --output /tmp/restore-check-01
mkdir -p deploy/backups/buckets
docker cp oldshop-buckets-tools-1:/tmp/restore-check-01 deploy/backups/buckets/
dc --profile app up -d backend worker
```

Script pg_dump/restore vào database mới, so count/hash từng bảng, sao BSON + validator/index Mongo vào database mới, sao binary media và kiểm checksum. Nó giữ database phục hồi để kiểm tra; không xóa nguồn. Với storage MinIO cần backup bucket/object của hệ lưu trữ đó riêng. Graph được phục hồi bằng rebuild từ SQL/Mongo; dữ liệu generation cũ không phải nguồn nghiệp vụ.

Để nhập legacy, chuẩn bị **target trống riêng**, không dùng lại database demo đã seed. Cấu hình `DATABASE_URL`, `BUCKET_SITE_URLS`, `BUCKET_DATASET`, `MONGO_DB`, Neo4j namespace cho target đó, chạy setup/init như trên rồi cấu hình nguồn qua env:

```text
BUCKET_LEGACY_URL=<DSN đọc nguồn, không đưa vào argv/log>
BUCKET_LEGACY_MONGO_URI=<Mongo nguồn nếu có>
BUCKET_LEGACY_MONGO_DB=<database Mongo nguồn>
BUCKET_LEGACY_MEDIA_DIR=<thư mục media nguồn, hoặc shared object store đã có>
```

```bash
python -m scripts.migrate_catalogue_to_buckets plan --assume-naive-zone Asia/Ho_Chi_Minh --output /tmp/import-plan.json
python -m scripts.migrate_catalogue_to_buckets apply --plan /tmp/import-plan.json
```

Chọn timezone theo provenance của nguồn thực tế; không suy ra timezone chỉ vì tên site. Plan chỉ lưu hash/count/violation, không chứa toàn bộ PII hoặc password. Apply đọc lại snapshot và từ chối khi nguồn/đích đổi; cùng plan có thể chạy lại nếu fingerprint vẫn khớp. Công cụ giữ global ID, metadata, object key; không tự đổi traffic ứng dụng.

Nguồn `oldshop-data` được đọc kiểm tra ngày 17/11/2026: 1.001 product, 30 contact–buyer mismatch, 5 transaction status ngoài 0–3. Cần đối soát các dòng này trước khi migration; không tự “sửa” bằng random buyer/contact. Đơn lịch sử không có reservation đáng tin cậy cần đối soát tồn kho trước khi cho hủy qua hệ mới.

## 7. Kiểm thử

```bash
dc exec tools python -m pytest -o addopts= -o cache_dir=/tmp/bucket-pytest-cache --confcutdir=tests/buckets tests/buckets -q
dc exec tools python -m scripts.bucket_regression
cd frontend
npm test -- --watch=false
npm run build -- --configuration production
```

Bucket tests tạo thêm fixture soft delete và database thử riêng; số product toàn hệ sau test lớn hơn 1.000. Manifest phân biệt đúng các ID thuộc seed. Site C cần được setup để chạy bài kiểm tra move; nếu chưa có, bài đó được skip. Bộ legacy regression tạo database mới trong cluster thử, giữ `BUCKET_MODE=false` để kiểm đường cũ.

Chưa coi local rehearsal là nghiệm thu HA, tải production hoặc cutover dữ liệu thực. Xem [báo cáo triển khai](../BAO_CAO_TRIEN_KHAI_BUCKET_SITE_NEO4J.md) và evidence để biết chính xác phạm vi đã kiểm chứng.

`benchmark-v2 --scale N` (1–100) có namespace riêng cho môi trường benchmark mới. Không đổi scale của dataset đã seed trong cùng core: content hash khác sẽ bị từ chối. `scripts.bucket_evidence --base-url http://backend:8000` xuất count/hash và các mẫu thời gian HTTP local; đây không phải kết quả capacity/load test production.
