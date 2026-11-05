# Tự định nghĩa index bằng JSON cho OldShop

## 1. Phạm vi đã triển khai

`database/indexing/catalog.json` là đầu vào thực sự cho bộ quản lý index, áp dụng
**cả PostgreSQL và MongoDB**. PostgreSQL vẫn giữ dữ liệu nghiệp vụ quan hệ;
MongoDB giữ document bán cấu trúc/projection và log ETL. MinIO không thuộc phạm vi index.

| Nhóm | Số lượng ban đầu | Cách quản lý |
|---|---:|---|
| PostgreSQL, index ứng dụng/ETL cấp gốc | 61 | JSON → kiểm tra → sinh SQL mới → migration runner |
| PostgreSQL, index thuộc PK/UNIQUE cấp gốc | 37 | JSON kiểm kê/đối soát; constraint và migration schema quản lý vòng đời |
| PostgreSQL, index con của partition | Phụ thuộc partition hiện có | Đối soát attachment, cấu trúc và validity theo cây; DB tự sinh khi tạo index trên parent |
| MongoDB, ứng dụng và `etl_errors` | 19 | JSON → PyMongo → đối soát catalog |
| `_id_`, `schema_migrations_pkey`, index bên ngoài | Không tự quản lý | Báo trong `unmanaged`; không xóa |

Các số PostgreSQL được lấy từ DB test nạp baseline và migration 001–007, không chỉ
đếm câu `CREATE INDEX` trong source. Sau `LIKE INCLUDING ALL` và rename partition,
tên index trên bảng `order` có thể do PostgreSQL sinh; manifest giữ tên thực tế đó.
Các bảng user đã tách nên index nhắm `user_core`, `user_secret`, v.v.

Giữ nguyên SQL baseline, migration 001–007, validator document và truy vấn nghiệp vụ.
Không có migration 008 chỉ để chuyển định dạng khai báo: DB đã qua 007 khớp cấu trúc
sẽ được tiếp nhận bằng snapshot `index-v1`, không build lại index.

## 2. Các file chính

| File | Vai trò |
|---|---|
| `database/indexing/catalog.json` | Cấu hình đang đề xuất, có `schema_version` và `revision` |
| `database/indexing/catalog.schema.json` | JSON Schema sinh từ chính các model kiểm tra trong Python, dùng cho editor |
| `database/indexing/snapshots/index-v1.json` | Định nghĩa cố định tương ứng PostgreSQL sau 007 |
| `database/indexing/releases.json` | Liên kết migration, revision, SHA-256 và checksum baseline |
| `backend/app/services/index_config.py` | Parse nghiêm ngặt, kiểm cấu hình, adapter tương thích `INDEXES` |
| `backend/app/services/index_postgres.py` | Sinh DDL và đối soát catalog, gồm opclass/null ordering/partition |
| `backend/app/services/index_mongo.py` | Plan/apply additive, chuẩn hóa text index và lưu snapshot Mongo đã áp |
| `backend/scripts/indexes.py` | CLI `validate`, `plan`, `apply`, `verify` |
| `backend/scripts/generate_index_migration.py` | Sinh migration PostgreSQL mới cùng snapshot |

`mongo_schema.INDEXES` vẫn tồn tại cho archive/benchmark nhưng được đọc từ JSON,
không chứa bộ định nghĩa Python độc lập. `etl.errors.initialize()` cũng dùng cùng nguồn.
`init_mongo` tiếp tục cài validator; công cụ `apply_indexes` chỉ quản lý index.

## 3. Cấu hình được hỗ trợ

PostgreSQL phiên bản đầu giới hạn ở schema `public`, B-tree và GIN đang dùng trong
dự án: khóa đơn/ghép, ASC/DESC, NULLS FIRST/LAST, unique, `gin_trgm_ops`, biểu thức
`to_tsvector` với `english`/`simple`, predicate `all`/`any` và các phép
`eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`, `has_key` JSONB. Không nhận SQL tùy ý,
`INCLUDE`, expression khác, collation/storage option tùy chỉnh hay CONCURRENTLY.
Catalog DB có cấu trúc ngoài khả năng đối soát sẽ báo conflict.

MongoDB hỗ trợ khóa `1`/`-1`/`text`, compound, wildcard, unique, sparse, hidden,
partial và TTL đơn trường. Partial filter có allowlist operator, không nhận `$where`.
TTL giới hạn số nguyên 0–2147483647; partial và sparse không được dùng đồng thời.
Một collection chỉ có một text index. Không nhận tùy chọn lạ rồi bỏ qua âm thầm.
Plan kiểm đường dẫn trường theo document contract hiện có, gồm field trong array;
`attributes` và các dictionary mở vẫn cho phép khóa động. TTL trên field có contract
phải nhắm kiểu ngày giờ. Collection mới chưa có document contract phải được tạo và
thiết kế schema riêng trước khi công cụ index có thể tiếp nhận.

Thứ tự key là array có thứ tự; thứ tự property của object JSON không làm đổi hash.
Tên index phải rõ ràng, kể cả tên trước đây driver tự sinh như
`product_id_1_created_at_-1`. Hash được tính từ cấu hình đã chuẩn hóa, gồm các giá trị mặc định.

Ví dụ thêm một index PostgreSQL cho demo trên **DB test**:

```json
{
  "schema": "public",
  "table": "product",
  "name": "idx_json_demo_price",
  "method": "btree",
  "unique": false,
  "managed_by": "application",
  "keys": [
    { "column": "price", "order": "DESC", "nulls": "FIRST" },
    { "column": "product_id", "order": "ASC", "nulls": "LAST" }
  ],
  "predicate": { "column": "is_deleted", "op": "eq", "value": false }
}
```

Đây là ví dụ chứng minh chuỗi cấu hình → DDL, chưa phải index được chọn cho hiệu năng
ứng dụng. Trước khi bổ sung thật, phải xác định truy vấn và đo chi phí đọc/ghi/dung lượng.

Ví dụ MongoDB trong mảng `mongodb`:

```json
{
  "collection": "product_details",
  "keys": [["attributes.color", 1]],
  "options": { "name": "idx_json_color", "sparse": true }
}
```

## 4. Validate, plan, apply và verify

Nếu chạy stack Docker hoặc cần hướng dẫn từ đầu, dùng
[mục 18 của hướng dẫn cấu hình/chạy hệ thống](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md#18-cấu-hình-và-chạy-indexing-json).
Phần đó có lệnh build, chạy CLI qua Compose, tiếp nhận snapshot trên DB hiện hữu,
lưu output trên host và cách xử lý lỗi môi trường.

Chạy từ `backend/`, dùng môi trường Python có dependencies của dự án. Các lệnh kết nối
DB đọc cấu hình `.env`/environment như backend hiện tại. `validate` không kết nối DB
và không yêu cầu credentials. Chỉ định database test trước khi thử thay đổi.

```bash
python -m scripts.indexes validate
python -m scripts.plan_indexes --engine all --output /tmp/index-plan.json
python -m scripts.verify_indexes --engine all --output /tmp/index-applied.json
python -m scripts.verify_indexes --engine all --desired
```

`plan` so cấu hình đang đề xuất với DB, báo `matched`, `missing`, `conflict`, cùng
`unmanaged`. Thiếu index là một kế hoạch có thể áp; conflict trả exit code 1.
`verify` yêu cầu mọi index trong snapshot đã áp phải matched; `--desired` chuyển sang
kiểm cấu hình đề xuất. Các lệnh đọc không chạy DDL, collMod hoặc seed.

Với DB hiện có sau 007, bước tiếp nhận Mongo có thể chạy qua đường khởi tạo cũ:

```bash
python -m scripts.init_mongo
python -m scripts.apply_indexes --engine all
python -m scripts.verify_indexes --engine all
```

`init_mongo` cài validator và index từ JSON, đồng thời ghi snapshot đã áp của Mongo.
PostgreSQL phải có baseline và migration hiện tại qua `scripts.init_db`/`scripts.migrate`
trước khi tiếp nhận. Chạy lặp giữ nguyên index đã khớp; không reset collection.

Khi **thêm index PostgreSQL**:

1. Sửa `catalog.json`, thêm khai báo và đổi `revision` sang tên chưa dùng, ví dụ `index-v2`.
2. Chạy validate và plan trên DB test đã áp đủ migration hiện tại.
3. Sinh SQL, đọc lại SQL và snapshot được tạo:

   ```bash
   python -m scripts.generate_index_migration
   ```

   Chạy bước sinh trên host/worktree có quyền ghi; thư mục source trong image runtime
   vốn được giữ chỉ đọc cho user ứng dụng.

4. Công cụ tạo version tiếp theo còn trống, ví dụ `008_indexes_index-v2.sql`, snapshot
   `snapshots/index-v2.json` và binding trong `releases.json`. Không ghi đè file có sẵn.
5. Áp và kiểm chứng:

   ```bash
   python -m scripts.apply_indexes --engine postgresql
   python -m scripts.verify_indexes --engine postgresql
   python -m scripts.apply_indexes --engine mongodb
   python -m scripts.verify_indexes --engine all
   ```

Có thể dùng `--catalog /path/to/catalog.json` cho validate/plan/apply/generate.
Verify snapshot đã áp độc lập với catalog đang sửa; muốn dùng đường dẫn đó để verify
thì thêm `--desired`. Generator ghi artifact về `DATABASE_SRC` của dự án hiện tại.

## 5. Phiên bản, xung đột và lỗi một phần

PostgreSQL áp **SQL đã đóng băng**, không đọc JSON đang thay đổi để tạo lại DDL của
migration cũ. Runner giữ advisory lock, transaction từng file, checksum và lịch sử
prefix; thêm kiểm tra header `index-catalog` với hash snapshot trước khi chạy SQL.
`verify` xác định snapshot qua migration đã áp, không lấy release chưa triển khai.
Snapshot đầu có checksum gắn với toàn bộ migration 001–007.

MongoDB lưu snapshot của riêng phần Mongo cùng hash tại
`_index_catalog_state`, document `_id: mongodb`, sau khi toàn bộ index đã đối soát
thành công. `_id_` của collection metadata do DB quản lý. Không ghi snapshot mới nếu
tạo unique thất bại hoặc gặp conflict. Mongo apply không có transaction DDL chung:
index tạo thành công trước lỗi vẫn có thể còn đó; sửa nguyên nhân rồi chạy plan/apply
lại để tiếp tục. Các index đã khớp được giữ nguyên.

Không có transaction chung giữa hai database. CLI preflight cả hai hệ trước apply,
và báo kết quả từng hệ nếu hệ tiếp theo lỗi; snapshot áp dụng của mỗi hệ độc lập.
Nếu preflight lỗi kết nối hoặc cấu hình, chưa chạy apply ở hệ nào.

**Giới hạn vòng đời ở bản này:** generator tự động chỉ xử lý bổ sung index. Đổi khóa,
chiều, unique, TTL hoặc partial của index cùng tên phải báo conflict. Thay đổi/xóa index
hoặc constraint cần migration SQL/qui trình Mongo riêng được review. Việc bỏ mục khỏi
Mongo JSON để lại index trong `unmanaged`; PostgreSQL generator/apply từ chối bỏ/thay
khai báo thuộc snapshot trước. Không có `drop_all`, reset, tự sửa TTL hoặc xóa PK/UNIQUE.
Tiếp nhận thêm index đã tồn tại bên ngoài lịch sử release cũng cần review riêng.

`verify_indexing_v2.py`, `SPECS` và `apply-indexing-v2.sh` là công cụ lịch sử cho 007;
không đại diện cho catalog mới. Dùng `verify_indexes` cho cấu hình JSON và các revision sau.

## 6. Kiểm thử và demo

Kiểm thử contract/compiler không cần database hoặc khởi động ứng dụng, nhưng vẫn
**cần đủ dependencies runtime và dev**. Chạy từ `backend/` bằng Python 3.13 trong venv
đã cài `requirements-dev.lock` theo
[mục 18.5 hướng dẫn hệ thống](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md#185-chạy-unit-test-indexing-và-xử-lý-lỗi-email-validator).
Không dùng Python Conda `(base)` chưa cài dependencies. `--noconftest` không bỏ qua
import các model có `EmailStr`; thiếu `email_validator` là lỗi môi trường, package
đã có trong requirements. Khi venv đã active:

```bash
python -m pytest --noconftest -o addopts= tests/test_index_config.py -q
```

Kiểm thử DB thật tạo database có tên UUID và chỉ xóa database do test tạo ra.
Tài khoản PostgreSQL dùng để kiểm thử cần quyền CREATE/DROP DATABASE:

```bash
INDEX_CONFIG_INTEGRATION=1 \
INDEX_TEST_PG_DSN=postgresql://test_user@127.0.0.1:55439/postgres \
INDEX_TEST_MONGO_URI=mongodb://127.0.0.1:55440 \
python -m pytest --noconftest -o addopts= tests/test_index_config_integration.py -q
```

Test chứng minh: parity sau 007, GIN/tsvector/opclass/partition/constraint, apply lặp,
thêm PostgreSQL index từ JSON → sinh 008 → áp qua runner → verify, rollback khi DDL lỗi,
snapshot sửa trái lịch sử bị từ chối, Mongo text/wildcard/TTL/partial/unique/sparse,
xung đột TTL không làm sửa DB, và snapshot applied khác desired chưa áp.

Để trình bày theo Lab03: mở JSON chỉ thứ tự khóa ghép và options, chạy validate/plan,
thêm index thử nghiệm trên DB riêng, apply, mở kết quả verify và EXPLAIN tự nhiên.
Các script benchmark Mongo hiện có import `INDEXES` nên dùng trực tiếp cấu hình JSON;
ví dụ `python -m scripts.benchmark_current --output /tmp/oldshop-current-benchmark`.
Chúng dùng collection tạm riêng. JSON trong output là bằng chứng đo, khác JSON đầu vào.
Không dùng số đo Lab03 để tuyên bố hiệu năng OldShop; chuyển định dạng khai báo nhưng
giữ nguyên index vật lý không tự làm truy vấn nhanh hơn.

## 7. Container và đóng gói

Loader đọc `DATABASE_SRC/indexing`, mặc định là `database/indexing` ở repository.
Dockerfile hiện có `COPY database /opt/database` và `DATABASE_SRC=/opt/database`,
nên catalog, schema, release binding và snapshots cùng đi vào image. Các file JSON
không bị `.dockerignore` loại bỏ. Dịch vụ `mongo-schema-init` dùng cùng image backend.

Khi sinh revision mới, cần đưa cả SQL, catalog, snapshot, schema và `releases.json`
vào cùng commit rồi build image. Không chỉ mount catalog mới vào image có migration cũ.
`package-day7.py` đóng gói file đã commit bằng `git ls-files` và yêu cầu worktree sạch;
file mới chưa được Git theo dõi sẽ chưa có trong gói release. Quy trình đóng gói Day7
vẫn giữ hợp đồng tag/commit và bằng chứng cũ; không tự tạo lại báo cáo/video lịch sử.

Kết quả kiểm chứng lần triển khai này được lưu tại
[`evidence/index_config_validation.json`](evidence/index_config_validation.json).
