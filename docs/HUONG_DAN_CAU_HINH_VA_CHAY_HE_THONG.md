# Hướng dẫn cấu hình, khởi tạo dữ liệu và chạy OldShop

Tài liệu dành cho phiên bản sau Ngày 7: PostgreSQL + MongoDB + MinIO + FastAPI + Angular
và ETL. Các lệnh dùng Bash trên Linux hoặc WSL, chạy từ **thư mục gốc dự án**, trừ khi có
ghi `cd` sang thư mục khác. Cập nhật theo mã nguồn ngày 30/10/2026, migration 001–006.

## 1. Chọn đúng cách chạy

| Cách chạy | File Compose / cấu hình | Phạm vi |
|---|---|---|
| **Stack đầy đủ của đồ án — hướng dẫn chính bên dưới** | `deploy/docker-compose.distributed.yml` + `deploy/.env.data` | PG, Mongo, MinIO, backend, frontend, ETL; profile `resilience` thêm replica |
| Stack local ban đầu | `docker-compose.yml` tại root | PG + backend + frontend; chưa đủ hệ thống dữ liệu sau nâng cấp |
| VPS | `deploy/docker-compose.yml` + `deploy/.env` | Caddy, domain/TLS và cấu hình production riêng; xem [deployment.md](deployment.md) |
| Backend/frontend chạy bằng Python/Node trên host | `backend/.env` + Angular environment | Dùng khi phát triển, xem mục 12 |

**Nếu máy đã chạy `oldshop-data` và có dữ liệu:** đi thẳng mục 10. Không làm lại phần tạo
credentials/seed như cài mới. Các lệnh ở mục 3–7 dành cho môi trường mới, chưa có dữ liệu cần giữ.

pgAdmin4 là công cụ quản trị PostgreSQL; Compass là công cụ quản trị MongoDB.
Không cần cài PostgreSQL/MongoDB trực tiếp trên host nếu dùng Docker theo hướng dẫn chính.

## 2. Chuẩn bị môi trường

Cần Docker Engine hoặc Docker Desktop đang chạy, Compose plugin có hỗ trợ `--wait` và
`depends_on.required`, Python 3.11+ để chạy script chuẩn bị cấu hình/kiểm tra và Bash.
Docker sẽ build Python 3.13 và Node 20 bên trong image; cách chạy chính không cần pip/npm trên host.

```bash
cd "/duong-dan-den/Epic-Ecommerce-FastAPI-main"
docker version
docker compose version
python3 --version
```

Thay đường dẫn mẫu bằng vị trí clone/giải nén thực tế. `docker version` phải có phần Server.
Nếu Docker cần quyền trên máy, cấu hình quyền truy cập Docker trước khi tiếp tục.

Stack từng được kiểm chứng trên Docker có khoảng 7,5 GiB RAM và 8 CPU; đây là cấu hình
thực nghiệm, không phải kết luận tài nguyên tối thiểu. Profile đầy đủ chạy chín dịch vụ thường trực.

## 3. Tạo và cấu hình `.env`

### 3.1. Phương án nên dùng: sinh credentials tự động

Từ root dự án:

```bash
python3 deploy/scripts/prepare-data-env.py
```

Script đọc `deploy/.env.data.example`, sinh giá trị ngẫu nhiên cho các dòng `=CHANGE_ME`,
tạo `deploy/.env.data` với quyền file `0600`. Script **không ghi đè file đã tồn tại**.
Nếu báo `FileExistsError`, giữ file hiện tại và kiểm tra/cấu hình nó; không xóa file để sinh lại
password của các database đã khởi tạo.

Mở file bằng editor:

```bash
nano deploy/.env.data
```

### 3.2. Phương án thay thế: `cp` từ file mẫu

Chỉ chọn phương án này nếu chưa dùng 3.1 và chưa có `.env.data` cần giữ:

```bash
cp -n deploy/.env.data.example deploy/.env.data
chmod 600 deploy/.env.data
nano deploy/.env.data
```

`cp -n` giữ file đích nếu nó đã tồn tại. Bản copy mẫu **chưa chạy được**: phải thay đủ các
giá trị dưới đây bằng secrets riêng trước khi khởi động.

| Biến cần thay `CHANGE_ME` | Ý nghĩa |
|---|---|
| `DB_PASSWORD` | Password PostgreSQL của `DB_USER` |
| `PG_REPLICATION_PASSWORD` | Password tài khoản replication PG |
| `SECRET_KEY` | Khóa ký JWT của ứng dụng |
| `MONGO_ROOT_PASSWORD` | Password quản trị Mongo, dùng cho init/schema |
| `MONGO_APP_PASSWORD` | Password role ứng dụng Mongo |
| `MONGO_KEYFILE` | Khóa xác thực nội bộ chung giữa các Mongo member |
| `MINIO_ROOT_PASSWORD` | Password quản trị MinIO Console |
| `MINIO_APP_SECRET_KEY` | Secret key S3 của tài khoản ứng dụng MinIO |

Sinh một secret hex mới cho một biến thông thường:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Sinh riêng `MONGO_KEYFILE` theo đúng cách script dự án đang dùng:

```bash
python3 -c 'import secrets; print(secrets.token_hex(384))'
```

Chạy lệnh sinh riêng cho từng secret, chép kết quả vào editor. Các chuỗi hex thuận tiện cho
URI Mongo. Không giữ `CHANGE_ME`, không dùng seed password của tài khoản web làm password DB.

### 3.3. Những giá trị cần kiểm tra

| Biến | Giá trị mẫu / tác dụng |
|---|---|
| `DB_NAME`, `DB_USER` | `oldshop`, `oldshop` |
| `MONGO_DB` | `oldshop` |
| `MONGO_ROOT_USER`, `MONGO_APP_USER` | `oldshop_admin`, `oldshop_app` |
| `MINIO_ROOT_USER` | `oldshop_minio`; username Console |
| `MINIO_APP_ACCESS_KEY` | `oldshop_media`; tài khoản S3 cho backend/worker |
| `STORAGE_BACKEND` | Giữ `local` lúc chuẩn bị; chuyển sang `minio` ở mục 6 sau khi copy ảnh thành công |
| `POSTGRES_IMAGE` | `postgres:16-alpine` |
| `MONGO_IMAGE` | Mặc định `mongo:8.0.32`; xem ghi chú tương thích bên dưới |
| `MINIO_IMAGE` | Giữ digest đã ghim trong mẫu, tương ứng release MinIO của dự án |
| `ETL_POLL_SECONDS` | `60`, thời gian nghỉ giữa các chu kỳ worker |
| `ETL_BATCH_SIZE`, `ETL_MAX_ATTEMPTS` | `100`, `5` |

**Mongo8 và môi trường local:** máy kiểm thử hiện tại đã gặp guard kernel khi chạy
Mongo8.0.32; bằng chứng nghiệm thu dùng Mongo7.0.43. Trên máy mới tương thích, có thể giữ
`MONGO_IMAGE=mongo:8.0.32` và kiểm thử lại. Nếu cùng môi trường đã ghi nhận lỗi này, đặt:

```ini
MONGO_IMAGE=mongo:7.0
```

Đây là tag 7.0, không đảm bảo mọi lần pull đều nhận đúng bản vá 7.0.43. Xem phiên bản thực
bằng checker ở mục 8. Không đổi tag giữa Mongo7/8 trên volume đang chứa dữ liệu để thử vận may;
nâng phiên bản dữ liệu hiện hữu cần quy trình backup và kiểm thử riêng.

Các cổng mặc định trên host:

| Biến | Port | Dịch vụ |
|---|---:|---|
| `PG_PRIMARY_PORT` | 55432 | PostgreSQL primary |
| `PG_REPLICA_PORT` | 55433 | PostgreSQL replica |
| `BACKEND_PORT` | 58000 | FastAPI / Swagger |
| `FRONTEND_PORT` | 58080 | Website Angular |
| `MINIO_API_PORT` | 59000 | API S3 của MinIO |
| `MINIO_CONSOLE_PORT` | 59001 | MinIO Console |

Nếu cổng đã được dùng, sửa **cổng host** tương ứng trong `.env.data` trước khi chạy, rồi dùng
cổng mới ở các URL bên dưới. Các port nội bộ vẫn là PG `5432`, backend `8000`, frontend `8080`,
MinIO `9000/9001`. Mongo chưa publish cổng host trong Compose chính.

**File nào được đọc?** Compose bên dưới đọc `deploy/.env.data` qua `--env-file` và truyền biến
vào container. Nó không tự đọc `backend/.env` hoặc `deploy/.env`. File `backend/.env` chỉ dùng
cho cách chạy backend trực tiếp ở mục 12. Không phải cứ thêm một biến vào `.env.data` là biến
đó tự được truyền vào backend; phải có mapping trong Compose.

## 4. Định nghĩa lệnh Compose và build image

Các bước chính dùng profile `resilience`: PG primary + replica, ba Mongo member cùng host,
MinIO, backend, frontend và worker. Profile này dùng để kiểm lỗi dịch vụ trên một máy;
chưa chịu mất cả máy hoặc tự promote PG.

Để tránh gõ thiếu `--env-file`, file Compose hoặc profile, định nghĩa hàm trong terminal hiện tại:

```bash
dc() {
  docker compose \
    --env-file deploy/.env.data \
    -f deploy/docker-compose.distributed.yml \
    --profile resilience "$@"
}

dc config --quiet
dc build backend frontend
```

Các mục 5–11 dùng `dc`. Mỗi terminal mới cần `cd` về root và định nghĩa lại hàm này.
`config --quiet` kiểm cấu hình mà không in secrets đã nội suy. Image mặc định sau build là
`oldshop-data-backend:day6` và `oldshop-data-frontend:day6`; tên day6 là tag hiện có trong Compose.

## 5. Khởi động dịch vụ dữ liệu và tạo database

### 5.1. Khởi động PostgreSQL, MongoDB và MinIO

```bash
dc up -d --wait --wait-timeout 240 \
  pg-primary pg-replica mongo1 mongo2 mongo3 minio
```

Lần đầu Docker pull image và tạo named volumes của project `oldshop-data`.
PostgreSQL image khởi tạo cluster, role `DB_USER` và database `DB_NAME` từ biến Compose.
PG replica lấy base backup từ primary; không cần tự `CREATE DATABASE` trên replica.

### 5.2. Khởi tạo Mongo replica set, users và MinIO buckets

Chạy đúng thứ tự:

```bash
dc run --rm --no-deps mongo-init
dc run --rm --no-deps mongo-expand
dc run --rm --no-deps minio-init
dc run --rm --no-deps mongo-schema-init
```

| Job | Công việc |
|---|---|
| `mongo-init` | Tạo replica set `oldshop-rs` và role ứng dụng trên DB `MONGO_DB` |
| `mongo-expand` | Thêm mongo2/mongo3, chờ secondary; giữ cấu hình nếu đã có |
| `minio-init` | Tạo ba bucket private và tài khoản ứng dụng có quyền trong các bucket |
| `mongo-schema-init` | Tạo/cập nhật collection validators, indexes và collection lỗi ETL |

Mongo không dùng `CREATE DATABASE` như SQL. Job init tạo user/collection trên DB đã chọn;
dữ liệu nghiệp vụ được ETL nạp ở mục 7. MinIO không có database SQL, nó dùng bucket/object.

### 5.3. Tạo schema và seed PostgreSQL

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.init_db
```

`--entrypoint python` chạy riêng bootstrap, không mở Uvicorn trong bước này. Script:

1. Chờ PG kết nối được và tạo DB nếu chưa có.
2. Nếu chưa có bảng `user`/`user_core`, chạy `database/init.sql` bằng `psql`.
3. `init.sql` nạp schema, functions/triggers và toàn bộ seed được include.
4. Migration runner kiểm baseline/checksum rồi áp lần lượt 001–006.
5. Chép file ảnh seed vào volume media, giữ file đã tồn tại.

Không chạy seed từng bảng sau bước này. Nếu DB đã có schema, bootstrap bỏ qua `init.sql`
nhưng vẫn kiểm tra/áp migration còn thiếu. Vì vậy không dùng bootstrap như công cụ reseed,
hoặc tự chạy migration trên dữ liệu đang phục vụ mà bỏ quy trình bảo trì ở mục 10.

Kiểm phiên bản schema và số lượng seed:

```bash
dc exec -T pg-primary sh -c \
  'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT version FROM schema_migrations ORDER BY version;
SELECT 'users' AS entity, count(*) AS total FROM user_core
UNION ALL SELECT 'products', count(*) FROM product
UNION ALL SELECT 'product_images', count(*) FROM product_image
UNION ALL SELECT 'orders', count(*) FROM "order"
UNION ALL SELECT 'transactions', count(*) FROM "transaction";
SQL
```

DB mới theo seed hiện có: 15 user, 16 product, 32 product_image, 30 order, 30 transaction;
migration đủ `001` đến `006`. Các số này sẽ thay đổi sau khi bạn thao tác ứng dụng.
User sau migration nằm trong `user_core`, `user_profile`, `user_secret`, `user_wallet`;
`users_full` là view đọc kết hợp. Không tìm bảng `user` cũ để kết luận seed bị mất.

## 6. Seed ảnh và chuyển storage sang MinIO

Bucket đã tạo ở 5.2, ảnh local đã chép ở 5.3. Bây giờ copy object:

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.seed_media
```

Kết quả cần có `missing: []`. `uploaded`/`skipped` phụ thuộc đã chạy trước hay chưa.
Script thêm object còn thiếu, không ghi đè object đã có và không sửa URL ảnh trong PG.
Seed có cả alias legacy/canonical và avatar nên tổng số object không bằng 32 product_image.

Sau khi copy thành công:

```bash
python3 deploy/scripts/prepare-media-env.py --enable-minio
```

Script giữ các secrets hiện tại và đặt `STORAGE_BACKEND=minio`. Lệnh `dc` tiếp theo sẽ đọc
cấu hình mới; không cần `source deploy/.env.data`. Trình tự này tránh bật storage MinIO khi
ảnh còn chỉ nằm trên đĩa local. Với ứng dụng đã có người dùng/upload, chuyển storage phải
có thời gian bảo trì để không phát sinh file mới giữa lúc copy và đổi cấu hình.

Ba bucket là `product-images`, `user-avatars`, `attachments`. Backend/ETL dùng
`MINIO_APP_ACCESS_KEY`/`MINIO_APP_SECRET_KEY`, không dùng root credentials để phục vụ request.

## 7. Nạp dữ liệu Mongo bằng ETL và mở ứng dụng

### 7.1. Full ETL lần đầu và đối soát

Lúc này chưa khởi động worker nên CLI không tranh advisory lock với daemon:

```bash
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc run --rm --no-deps --entrypoint python backend -m etl.run status
```

`full` và `reconcile` cần trả `status: success`. Status cần `pending: 0`, `dead: 0`,
`last_run.status: success`. Nếu có `partial`/lỗi, xử lý theo mục 13 trước khi mở ứng dụng.
Có thể chạy lại `full` thêm một lần để kiểm replay; số document nghiệp vụ không nhân đôi.

Với seed ban đầu, các collection nghiệp vụ có 16 `product_details`, 30 `order_snapshots`,
11 `violation_logs`; `reviews`, `system_logs`, `contact_messages` ban đầu rỗng.
`attributes`/`tags` của sản phẩm có thể rỗng: seed quan hệ không tự tạo thông số RAM/brand
giả như bộ metadata riêng dùng trong video demo. Không import JSON ví dụ thiết kế như một
bộ seed bổ sung vào DB đã ETL.

### 7.2. Chạy backend, frontend và ETL daemon

```bash
dc up -d --wait --wait-timeout 240 backend etl-worker frontend
dc ps --all
```

Backend có entrypoint bootstrap nên sẽ kiểm lại schema/migration khi start; DB đã nạp sẽ
không bị seed lại. Các init job xuất hiện `Exited (0)` là hoàn thành bình thường, không cần
biến chúng thành service chạy mãi.

Worker chạy liên tục, full khi chưa có trạng thái khởi tạo, sau đó incremental theo outbox
và đối soát sâu theo lịch. `ETL_POLL_SECONDS=60` là khoảng nghỉ giữa chu kỳ, không phải cam kết
mọi bản ghi luôn đồng bộ trong tối đa 60 giây. Không mở thêm worker thủ công cùng daemon.

## 8. Truy cập và kiểm tra hệ thống

### 8.1. URL và tài khoản

| Mục đích | URL mặc định |
|---|---|
| Website | http://localhost:58080 |
| Swagger | http://localhost:58000/api/docs |
| OpenAPI JSON | http://localhost:58000/api/openapi.json |
| Liveness | http://localhost:58000/health |
| Readiness PG/Mongo/storage | http://localhost:58000/health/ready |
| MinIO Console | http://localhost:59001 |
| MinIO S3 API | http://localhost:59000 |

Tài khoản web seed:

| Vai trò | Email | Password seed |
|---|---|---|
| Admin | `admin@oldshop.com` | `admin123` |
| Moderator | `mod1@oldshop.com` | `mod123` |
| Người dùng | `user1@gmail.com` | `user123` |

Đây là tài khoản đồ án, khác với DB role và MinIO user. MinIO Console đăng nhập bằng
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` trong `.env.data`. Có thể cần đóng bảng thông tin
license lần đầu, sau đó mở `product-images` → `products` → chọn JPEG → **Preview**.
Website lấy ảnh qua `/media/...`, không truy cập bucket anonymous.

### 8.2. Kiểm tra bằng lệnh và Swagger

```bash
curl -fsS http://localhost:58000/health
curl -fsS http://localhost:58000/health/ready
curl -fsS http://localhost:58080/api/v1/categories
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

Checker cần trả `result: PASS`: chín service khỏe, schema 001–006, PG replica streaming,
Mongo một PRIMARY/hai SECONDARY, ETL bắt kịp nguồn và media đọc được. Checker `--day6` có
GET product detail nên tăng `view_count` theo hành vi API bình thường và chờ ETL xử lý event đó.
Nếu chỉ muốn kiểm hạ tầng/ETL/readiness, dùng `--resilience --day5` thay cho `--day6`;
tên flag `day5` không có nghĩa hạ schema từ 006 xuống 005.

Trong Swagger:

1. Gọi `GET /api/v1/categories` và `GET /api/v1/products`.
2. Mở **Authorize**; trường `username` của OAuth2 nhận **email** seed và password tương ứng.
3. Gọi `GET /api/v1/auth/me` để xác nhận token/quyền.
4. Xem `GET /api/v1/products/1`: core từ PG, `attributes`/`tags` từ Mongo.
5. Mở giao diện web, xem ảnh và dashboard admin. Nếu thử giỏ hàng/đơn hàng, đó là thao tác
   ghi dữ liệu thật trong DB local, số lượng seed và tồn kho có thể thay đổi.

SMTP, PayPal, Apps Script là tích hợp tùy chọn; Compose dữ liệu hiện không truyền credentials
các tích hợp này. Chạy core/đăng nhập seed không đồng nghĩa email OTP hoặc PayPal đã được cấu hình.

## 9. Dùng pgAdmin4 và MongoDB Compass

### 9.1. pgAdmin4 kết nối vào PG Docker

Trong **Register → Server → Connection**:

| Trường | Primary | Replica |
|---|---|---|
| Host | `127.0.0.1` | `127.0.0.1` |
| Port | `55432` | `55433` |
| Maintenance database | Giá trị `DB_NAME`, mặc định `oldshop` | Cùng DB |
| Username | Giá trị `DB_USER`, mặc định `oldshop` | Cùng user đã có trên primary |
| Password | `DB_PASSWORD` trong `.env.data` | Cùng password |

Bảng áp dụng khi pgAdmin chạy trực tiếp trên host. Nếu pgAdmin ở container khác,
`127.0.0.1` là chính container pgAdmin; cần đặt cùng Docker network hoặc cấu hình địa chỉ host phù hợp.

Mở Query Tool trên DB `oldshop`, chạy các nhóm trong [demo_pgadmin.sql](report/demo_pgadmin.sql).
`pg_is_in_recovery()` cần false trên primary và true trên replica; replica chỉ đọc.
DB Docker đã seed/migrate ở mục 5 thì **không chạy lại init.sql trong pgAdmin**.

Nếu bạn chọn khởi tạo **một PostgreSQL database rỗng riêng ngoài quy trình Docker chính**:

```bash
python3 database/build_pgadmin_init.py --output /tmp/oldshop-init-pgadmin.sql
```

Tạo một database rỗng bằng pgAdmin trước, chọn đúng DB rồi mở/chạy SQL vừa sinh trong Query Tool.
File output phải chưa tồn tại; đổi tên nếu sinh lại. `init.sql` gốc có `\i` của psql nên không
paste trực tiếp vào Query Tool. SQL sinh ra chỉ là baseline + seed Ngày 1, **chưa áp 001–006**.
Muốn dùng DB đó với backend hiện tại cần cấu hình backend trỏ đúng DB và chạy migration runner
theo quy trình phù hợp; không coi file sinh SQL này là cách migration DB đã có dữ liệu.

### 9.2. Compass: mở cổng quản trị Mongo tùy chọn

Compose chính giữ Mongo trong Docker network. Để Compass trên host kết nối, tạo thêm
`deploy/docker-compose.gui.yml` nếu chưa có (nếu đã có thì mở editor và bổ sung cấu hình, giữ nội dung cũ):

```yaml
services:
  mongo1:
    ports:
      - "127.0.0.1:57017:27017"
```

Định nghĩa lại `dc` để giữ cả file override khi quản lý stack:

```bash
dc() {
  docker compose \
    --env-file deploy/.env.data \
    -f deploy/docker-compose.distributed.yml \
    -f deploy/docker-compose.gui.yml \
    --profile resilience "$@"
}

dc up -d --no-deps --wait --wait-timeout 180 mongo1
```

Thao tác publish port có thể recreate mongo1; làm lúc chưa có request cần phục vụ và chờ
replica set ổn định. Sau đó dùng mẫu URI sau trong Compass, thay placeholders bằng giá trị của bạn:

```text
mongodb://<MONGO_APP_USER>:<MONGO_APP_PASSWORD>@127.0.0.1:57017/<MONGO_DB>?authSource=<MONGO_DB>&directConnection=true
```

Secrets do generator tạo là hex; nếu tự đặt password có ký tự đặc biệt thì cần URL-encode
phần user/password của URI. `directConnection=true` giúp client host kết nối một member,
tránh tự resolve các hostname `mongo1`/`mongo2`/`mongo3` chỉ có trong Docker network.
Đây là kết nối quản trị một member, không phải URI ứng dụng có khả năng tự chuyển member;
sau bầu cử cần kiểm member đang kết nối có phải PRIMARY nếu muốn ghi.

Chọn DB `oldshop`, xem `product_details`, `order_snapshots`, indexes hoặc chạy
[demo_mongo.js](report/demo_mongo.js) trong Compass Shell. Không thay `MONGO_URI` nội bộ của
backend sang `localhost:57017`; bên trong container, Compose vẫn dùng hostname Mongo nội bộ.
Giữ file override trong các lần gọi `dc` tiếp theo để cấu hình publish port nhất quán.

## 10. Những lần chạy tiếp theo và nâng cấp DB hiện hữu

### 10.1. Khởi động lại cùng phiên bản

Giữ nguyên `.env.data`, cùng file Compose/profile và volumes:

```bash
# Định nghĩa lại dc nếu đây là terminal mới.
dc up -d --wait --wait-timeout 240
dc ps --all
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

Không cần `cp` env, tạo DB, seed hoặc full ETL lại mỗi lần bật máy. Các init job được thiết kế
để chạy lại; worker tiếp tục từ trạng thái/outbox. Khi đã mở rộng Mongo thành ba voting member,
tiếp tục dùng profile `resilience`; không bỏ profile rồi chỉ chạy mongo1 và kỳ vọng giữ quorum.

### 10.2. Thay cấu hình hoặc cập nhật code

`restart` không nạp lại biến môi trường mới vào container. Với thay đổi thông thường không
liên quan schema/storage/secrets, dùng `dc up -d --wait` để Compose áp cấu hình container.
Nếu backend bị recreate, Nginx có thể giữ IP backend cũ; sau khi backend khỏe, restart frontend:

```bash
dc restart frontend
dc up -d --no-deps --wait --wait-timeout 90 frontend
```

Với DB đã dùng mà cần nâng cấp schema/app lên bộ migration hiện tại, xem
[quy trình tích hợp](design/06_completion_plan.md), rồi thực hiện trong thời gian bảo trì:

```bash
bash deploy/scripts/apply-day6.sh --resilience
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

Script build image, dừng frontend/backend/worker, backup và thử restore, chạy migration/index,
full/reconcile, đối chiếu 18 bảng nguồn và chỉ mở lại khi thành công. Backup nằm trong
`deploy/backups/`; lỗi sẽ giữ trạng thái bảo trì. Script dành cho stack local với các điều kiện
trong runbook, không thay thế quy trình nâng cấp mọi DB tùy biến. Nếu đang dùng override riêng,
cần kiểm tra vì script apply dùng Compose chính, không tự ghép file GUI override.

Đổi `DB_PASSWORD`, `MONGO_APP_PASSWORD`, `MINIO_APP_SECRET_KEY` trong file env không tự đổi
password đã lưu trong PG/Mongo/MinIO. Không sinh lại credentials cho volume cũ. Việc rotate
secret, đổi major Mongo hoặc chuyển storage là thao tác riêng cần kế hoạch bảo toàn dữ liệu.

## 11. Xem log, dừng hệ thống và chạy ETL thủ công

```bash
dc logs --tail 100 backend
dc logs --tail 100 etl-worker
dc logs --tail 100 mongo-init mongo-expand mongo-schema-init minio-init
dc logs -f --tail 100 backend etl-worker
```

`Ctrl+C` thoát lệnh xem log, không dừng container đang chạy nền.

Dừng tạm, giữ container và dữ liệu:

```bash
dc stop
```

Dừng và gỡ container/network, giữ named volumes để lần sau chạy tiếp:

```bash
dc down
```

Không thêm `--volumes`/`-v` vào lệnh dừng hằng ngày: cờ đó xóa volumes chứa PG, Mongo,
MinIO và media của project. Không dùng reset volume làm cách sửa password hoặc lỗi schema.

Nếu cần full ETL/đối soát thủ công khi daemon đang chạy:

```bash
dc stop etl-worker
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc up -d --no-deps --wait --wait-timeout 180 etl-worker
dc exec -T etl-worker python -m etl.run status
```

Nếu CLI trả lỗi, xem lỗi/đối soát trước khi kết luận hoàn thành. Advisory lock ngăn hai lượt
ETL ghi chồng nhau; `etl_worker_busy` thường do daemon/lượt CLI khác vẫn đang giữ lock.
Theo dõi `pending`, `dead`, `oldest_pending_seconds`, `last_run.status` và `media_cleanup`.

## 12. Tùy chọn: chạy backend/frontend trực tiếp để phát triển

Phần này là lựa chọn phát triển, không phải bước bắt buộc sau mục 7. Ví dụ tái sử dụng
PostgreSQL của stack Docker đã có, backend host chạy port 8000, Angular host chạy port 4200.

### 12.1. Backend

Cần Python 3.13 và PostgreSQL client có `psql`. Từ root:

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp -n .env.example .env
```

Mở `backend/.env` và sửa:

```ini
ENVIRONMENT=development
DEBUG=true
DB_HOST=127.0.0.1
DB_PORT=55432
DB_USER=oldshop
DB_NAME=oldshop
DB_PASSWORD=<chép DB_PASSWORD từ deploy/.env.data>
SECRET_KEY=<khóa JWT riêng cho backend phát triển>
CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
MONGO_URI=
MONGO_DB=oldshop
STORAGE_BACKEND=local
```

Thay placeholders bằng giá trị thực trong editor, không giữ dấu `< >`. Nếu đã đặt `DATABASE_URL`
thì nó có ưu tiên hơn `DB_*`: xóa/comment URL cũ hoặc sửa cho cùng DB. Chạy từ `backend/` để
Pydantic tìm đúng `.env`; file này không phải `.env.data` của Compose.

Ví dụ trên chạy core PG và local media. Muốn backend host đọc Mongo/MinIO đầy đủ, mở cổng
Mongo theo 9.2, điền URI direct host tương ứng và dùng:

```ini
STORAGE_BACKEND=minio
MINIO_ENDPOINT=127.0.0.1:59000
MINIO_ACCESS_KEY=<MINIO_APP_ACCESS_KEY>
MINIO_SECRET_KEY=<MINIO_APP_SECRET_KEY>
MINIO_SECURE=false
```

`MINIO_ENDPOINT` không có tiền tố `http://`; các credentials lấy từ `.env.data`.
Nếu để `MONGO_URI` rỗng thì không coi bản backend host này là bài kiểm thử tích hợp Mongo.

Sau khi cấu hình đúng, trong `backend/` với venv đang active:

```bash
python -m scripts.init_db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

DB Docker ở ví dụ đã seed/migrate nên init_db kiểm lại và chép ảnh seed vào `backend/media`.
Nếu đổi sang PG cài trực tiếp, sửa `DB_*` đúng role/DB; bootstrap cần quyền tạo DB nếu chưa có,
tạo schema/extensions và áp migration. Không bootstrap thử trên DB production đang dùng.
Không chạy thêm `python -m etl.run worker` trỏ cùng DB nếu worker Docker vẫn hoạt động.

### 12.2. Frontend

Mở terminal khác, từ root:

```bash
cd frontend
node --version
npm --version
npm ci --ignore-scripts --no-audit --no-fund
npm start
```

Theo `frontend/package-lock.json`, Angular hiện yêu cầu Node `^20.19.0 || ^22.12.0 || >=24.0.0`.
Mở http://localhost:4200. File `src/environments/environment.ts` trỏ API/media tới
`http://localhost:8000`, khớp backend host ở trên. Bản build Docker dùng `environment.prod.ts`,
API `/api/v1` và media cùng origin Nginx, nên không chỉnh environment dev để sửa bản Docker.

## 13. Lỗi thường gặp

| Hiện tượng | Kiểm tra / xử lý |
|---|---|
| `CHANGE_ME`, thiếu biến hoặc `required variable` | Kiểm `.env.data` đã sinh/sửa đủ, đúng `--env-file`; dùng `dc config --quiet` |
| `FileExistsError` khi prepare env | Giữ file đã có, không tạo lại secrets của DB hiện hữu |
| `port is already allocated` | Sửa cổng host trong env, cập nhật URL kết nối tương ứng |
| Mongo8 thoát ngay với guard kernel | Đọc log `dc logs mongo1`; với DB mới trên môi trường đã ghi nhận, dùng ngoại lệ Mongo7; không đổi image trên dữ liệu cũ |
| Mongo ping được nhưng app chưa kết nối | Kiểm mongo-init/expand thành công, PRIMARY và auth; ping container chưa chứng minh replica set sẵn sàng |
| Compass không resolve `mongo1` | Dùng override port + directConnection như mục 9.2; hostname này dành cho Docker network |
| PG/Mongo/MinIO báo sai password sau đổi env | Env không rotate user đã tồn tại; khôi phục đúng credentials hoặc thực hiện quy trình rotate |
| Backend báo checksum mismatch / schema drift | Kiểm migration history và baseline; không sửa checksum hoặc reseed để vượt gate |
| Ảnh 404/503 | Kiểm minio-init, seed_media `missing`, storage backend, đúng bucket/key và app credentials |
| Website 502 sau recreate backend | Chờ backend khỏe, restart frontend để Nginx resolve lại upstream |
| `/health` 200 nhưng readiness 503 | Xem `/health/ready`; process còn sống nhưng PG/Mongo/storage có thể lỗi |
| `attributes` rỗng | Kiểm document/ETL; seed gốc không tự chứa metadata RAM/brand như demo |
| Lọc thuộc tính trả 503 khi Mongo lỗi | Đây là hành vi đã thiết kế, tránh tự bỏ bộ lọc và trả sản phẩm sai |
| ETL `partial`, `dead > 0`, media missing | Xem log worker/status và dữ liệu nguồn; không coi heartbeat healthy là đối soát thành công |
| Full ETL báo `etl_worker_busy` | Dừng đúng worker/lượt CLI cạnh tranh rồi chạy lại; không chạy nhiều daemon |
| Init job `Exited (0)` | Thành công bình thường của job một lần |

## 14. Kiểm thử và tài liệu tiếp theo

Swagger dùng để kiểm API; DB constraints, Mongo validators, ETL replay và lỗi/phục hồi cần
runner tích hợp riêng. Runner Ngày 6 tự tạo project/DB/volumes tạm và dọn sau kiểm thử:

```bash
bash deploy/scripts/test-day6.sh --mongo-image mongo:7.0
```

Với host đã xác minh tương thích Mongo8, có thể dùng image mặc định của runner.
Không chạy `pytest` tùy ý với `DB_NAME=oldshop` đang sử dụng: tests có ghi dữ liệu.
Xem các điều kiện và cách chạy ở [06_completion_plan.md](design/06_completion_plan.md).

- [PROJECT_GUIDE.md](PROJECT_GUIDE.md): bản đồ mã nguồn và kiến trúc.
- [Thiết kế Mongo/MinIO](design/03_json_design.md): validators, indexes và seed media.
- [Migration/indexing](design/04_indexing.md): quản lý schema, partition và rollback.
- [ETL](design/05_etl.md): ownership, provenance thời gian và đối soát.
- [Hồ sơ Ngày 7](report/README.md): báo cáo, slide, video và kịch bản demo.
- [Deployment VPS](deployment.md): tài liệu cho profile VPS riêng.

Luồng cài mới cần nhớ: **env → build → hạ tầng → init users/buckets/validators → PG seed và
migration → copy ảnh → bật MinIO → full ETL/reconcile → backend/frontend/worker → checker**.
