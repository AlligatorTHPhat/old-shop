# Hướng dẫn cấu hình, khởi tạo dữ liệu và chạy OldShop

Tài liệu dành cho phiên bản sau Ngày 7: PostgreSQL + MongoDB + MinIO + FastAPI + Angular
và ETL. Mỗi nhóm lệnh có hai bản: **Linux/WSL dùng Bash**, **Windows dùng PowerShell 7.3+**.
Chỉ chạy bản tương ứng với terminal của bạn, không chạy cả hai bản liên tiếp.
Các lệnh chạy từ **thư mục gốc dự án**, trừ khi có ghi đổi thư mục.
Cập nhật indexing ngày 01/11/2026: mã nguồn có migration 001–007.
DB hiện hữu chỉ có 007 sau khi bạn tự áp dụng; xem [runbook indexing v2](runbooks/indexing_v2.md).
Cập nhật 03/11/2026: cấu hình index nằm ở `database/indexing/catalog.json`.
**Để chạy indexing JSON trên stack đang có, xem mục 18.2–18.3; để xử lý lỗi
`email-validator` khi chạy pytest, xem mục 18.5.** Không cần chạy pytest để khởi động website.

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
`depends_on.required`, Python 3.11+ để chạy script chuẩn bị cấu hình/kiểm tra.
Bash dùng cho nhánh Linux/WSL; các bước Docker chính trên Windows dùng PowerShell.
Trên Windows, dùng Docker Desktop ở chế độ **Linux containers**, bật WSL 2 engine.
Nếu chạy các bước bảo trì/test bằng WSL, bật thêm tích hợp Docker cho distro đang dùng tại
**Settings → Resources → WSL Integration**. [Hướng dẫn chính thức Docker](https://docs.docker.com/desktop/features/wsl/).
Docker sẽ build Python 3.13 và Node 20 bên trong image; cách chạy chính không cần pip/npm trên host.

Các khối Windows hướng tới **PowerShell 7.3+ (`pwsh`)**, không phải CMD hay Windows PowerShell 5.1.
Phiên bản này giữ cách truyền dấu nháy vào native command phù hợp với lệnh Docker/SQL bên dưới;
đầu ví dụ đặt `$PSNativeCommandArgumentPassing = "Windows"` cho phiên terminal hiện tại.
[Tài liệu PowerShell về truyền tham số](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing?view=powershell-7.5).
Nếu dùng WSL terminal thì làm theo toàn bộ nhánh Linux; Python cài trong Windows và Python trong
WSL là hai môi trường riêng. Trên Windows cần Python launcher `py`; nếu máy chỉ có `python`,
kiểm tra đúng phiên bản rồi thay `py -3` bằng `python` cho các script cấu hình/kiểm tra.

**Linux / WSL — Bash**

```bash
cd "/duong-dan-den/Epic-Ecommerce-FastAPI-main"
docker version
docker compose version
python3 --version
```

**Windows — PowerShell 7.3+**

```powershell
Set-Location "C:\Projects\Epic-Ecommerce-FastAPI-main"
$PSVersionTable.PSVersion
if ($PSVersionTable.PSVersion -lt [version]"7.3") {
    throw "Mo PowerShell 7.3+ (pwsh) hoac dung nhanh Linux trong WSL."
}
$PSNativeCommandArgumentPassing = "Windows"
docker version
docker compose version
py -3 --version
```

Thay đường dẫn mẫu bằng vị trí clone/giải nén thực tế. `docker version` phải có phần Server.
Nếu Docker cần quyền trên máy, cấu hình quyền truy cập Docker trước khi tiếp tục.
Ví dụ đường dẫn Windows là `C:\Projects\Epic-Ecommerce-FastAPI-main`; trong WSL cùng thư mục đó
là `/mnt/c/Projects/Epic-Ecommerce-FastAPI-main`. Thay các đường dẫn mẫu bằng đường dẫn thật.
Windows dùng dấu `\` trong đường dẫn host; các đường dẫn `/app`, `/opt`, `/data` và lệnh `sh`
bên trong container vẫn là Linux. Các block INI/YAML/SQL dùng chung cho hai hệ điều hành.
Sau mỗi lệnh build/init/ETL, chỉ tiếp tục khi lệnh đã thành công; PowerShell không tự dừng toàn bộ
một nhóm lệnh chỉ vì native executable trả mã lỗi.

Stack từng được kiểm chứng trên Docker có khoảng 7,5 GiB RAM và 8 CPU; đây là cấu hình
thực nghiệm, không phải kết luận tài nguyên tối thiểu. Profile đầy đủ chạy chín dịch vụ thường trực.

## 3. Tạo và cấu hình `.env`

### 3.1. Phương án nên dùng: sinh credentials tự động

Từ root dự án:

**Linux / WSL — Bash**

```bash
python3 deploy/scripts/prepare-data-env.py
```

**Windows — PowerShell 7.3+**

```powershell
py -3 deploy/scripts/prepare-data-env.py
```

Script đọc `deploy/.env.data.example`, sinh giá trị ngẫu nhiên cho các dòng `=CHANGE_ME`,
tạo `deploy/.env.data`; trên Linux file có quyền `0600`. Trên Windows, quản lý quyền truy cập
bằng ACL của NTFS (Properties → Security), không coi mode POSIX là ACL tương đương.
[Python: os.chmod trên Windows](https://docs.python.org/3/library/os.html#os.chmod).
Script **không ghi đè file đã tồn tại**.
Nếu báo `FileExistsError`, giữ file hiện tại và kiểm tra/cấu hình nó; không xóa file để sinh lại
password của các database đã khởi tạo.

Mở file bằng editor:

**Linux / WSL — Bash**

```bash
nano deploy/.env.data
```

**Windows — PowerShell 7.3+**

```powershell
notepad .\deploy\.env.data
```

### 3.2. Phương án thay thế: `cp` từ file mẫu

Chỉ chọn phương án này nếu chưa dùng 3.1 và chưa có `.env.data` cần giữ:

**Linux / WSL — Bash**

```bash
cp -n deploy/.env.data.example deploy/.env.data
chmod 600 deploy/.env.data
nano deploy/.env.data
```

**Windows — PowerShell 7.3+**

```powershell
if (-not (Test-Path -LiteralPath ".\deploy\.env.data")) {
    Copy-Item -LiteralPath ".\deploy\.env.data.example" -Destination ".\deploy\.env.data"
}
notepad .\deploy\.env.data
```

`cp -n` trên Linux và điều kiện `Test-Path` trên Windows đều giữ file đích đã tồn tại.
Windows không có bước `chmod 600`; dùng quyền truy cập thư mục/file của Windows.
Bản copy mẫu **chưa chạy được**: phải thay đủ các
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

**Linux / WSL — Bash**

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

**Windows — PowerShell 7.3+**

```powershell
py -3 -c "import secrets; print(secrets.token_hex(32))"
```

Sinh riêng `MONGO_KEYFILE` theo đúng cách script dự án đang dùng:

**Linux / WSL — Bash**

```bash
python3 -c 'import secrets; print(secrets.token_hex(384))'
```

**Windows — PowerShell 7.3+**

```powershell
py -3 -c "import secrets; print(secrets.token_hex(384))"
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

**Linux / WSL — Bash**

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

**Windows — PowerShell 7.3+**

```powershell
function dc {
    $composeArgs = @(
        "compose",
        "--env-file", "deploy/.env.data",
        "-f", "deploy/docker-compose.distributed.yml",
        "--profile", "resilience"
    )
    & docker @composeArgs @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose that bai, exit code: $LASTEXITCODE"
    }
}

dc config --quiet
dc build backend frontend
```

Các mục 5–11 dùng `dc`. Mỗi terminal mới cần về root (`cd` / `Set-Location`) và định nghĩa lại
đúng phiên bản hàm cho shell đó. Hàm Bash dùng `"$@"`, PowerShell dùng `@args` để truyền
nguyên danh sách tham số sang Docker. Hàm PowerShell ném lỗi nếu Compose trả exit code khác 0.
Đây là hàm tạm của terminal, không phải file executable. Bản truyền SQL bằng pipeline ở mục 5.3
sẽ gọi trực tiếp `docker compose` để đưa stdin đến đúng tiến trình.
`config --quiet` kiểm cấu hình mà không in secrets đã nội suy. Image mặc định sau build là
`oldshop-data-backend:day6` và `oldshop-data-frontend:day6`; tên day6 là tag hiện có trong Compose.

## 5. Khởi động dịch vụ dữ liệu và tạo database

### 5.1. Khởi động PostgreSQL, MongoDB và MinIO

**Linux / WSL — Bash**

```bash
dc up -d --wait --wait-timeout 240 \
  pg-primary pg-replica mongo1 mongo2 mongo3 minio
```

**Windows — PowerShell 7.3+**

```powershell
dc up -d --wait --wait-timeout 240 pg-primary pg-replica mongo1 mongo2 mongo3 minio
```

Lần đầu Docker pull image và tạo named volumes của project `oldshop-data`.
PostgreSQL image khởi tạo cluster, role `DB_USER` và database `DB_NAME` từ biến Compose.
PG replica lấy base backup từ primary; không cần tự `CREATE DATABASE` trên replica.

### 5.2. Khởi tạo Mongo replica set, users và MinIO buckets

Chạy đúng thứ tự:

**Linux / WSL — Bash**

```bash
dc run --rm --no-deps mongo-init
dc run --rm --no-deps mongo-expand
dc run --rm --no-deps minio-init
dc run --rm --no-deps mongo-schema-init
```

**Windows — PowerShell 7.3+**

```powershell
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

Từ phiên bản indexing JSON, `mongo-schema-init` đọc `database/indexing/catalog.json`
đã được đóng gói trong image và ghi snapshot Mongo tại `_index_catalog_state` sau khi
đối soát thành công. Phải build image ở mục 4 trước bước này; sửa JSON trên host không
tự cập nhật container. Nếu job báo index conflict, xem mục 18.6 thay vì xóa collection.

Mongo không dùng `CREATE DATABASE` như SQL. Job init tạo user/collection trên DB đã chọn;
dữ liệu nghiệp vụ được ETL nạp ở mục 7. MinIO không có database SQL, nó dùng bucket/object.

### 5.3. Tạo schema và seed PostgreSQL

**Linux / WSL — Bash**

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.init_db
```

**Windows — PowerShell 7.3+**

```powershell
dc run --rm --no-deps --entrypoint python backend -m scripts.init_db
```

`--entrypoint python` chạy riêng bootstrap, không mở Uvicorn trong bước này. Script:

1. Chờ PG kết nối được và tạo DB nếu chưa có.
2. Nếu chưa có bảng `user`/`user_core`, chạy `database/init.sql` bằng `psql`.
3. `init.sql` nạp schema, functions/triggers và toàn bộ seed được include.
4. Migration runner kiểm baseline/checksum rồi áp lần lượt 001–007.
5. Chép file ảnh seed vào volume media, giữ file đã tồn tại.

Không chạy seed từng bảng sau bước này. Nếu DB đã có schema, bootstrap bỏ qua `init.sql`
nhưng vẫn kiểm tra/áp migration còn thiếu. Vì vậy không dùng bootstrap như công cụ reseed,
hoặc tự chạy migration trên dữ liệu đang phục vụ mà bỏ quy trình bảo trì ở mục 10.

Kiểm phiên bản schema và số lượng seed:

**Linux / WSL — Bash**

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

**Windows — PowerShell 7.3+**

```powershell
$seedSql = @'
SELECT version FROM schema_migrations ORDER BY version;
SELECT 'users' AS entity, count(*) AS total FROM user_core
UNION ALL SELECT 'products', count(*) FROM product
UNION ALL SELECT 'product_images', count(*) FROM product_image
UNION ALL SELECT 'orders', count(*) FROM "order"
UNION ALL SELECT 'transactions', count(*) FROM "transaction";
'@
$seedSql | docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience exec -T pg-primary sh -c 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
if ($LASTEXITCODE -ne 0) { throw "Kiem tra seed PostgreSQL that bai." }
```

Trên Windows, here-string `@' ... '@` giữ nguyên dấu nháy của SQL; dòng đóng `'@` phải đứng
riêng ở đầu dòng. Chỉ `$POSTGRES_USER`/`$POSTGRES_DB` trong `sh -c` được mở rộng bên trong
container. Không đổi here-string thành chuỗi double-quote làm PowerShell nội suy trước.

DB mới theo seed hiện có: 15 user, 1.000 product, 2.000 product_image, 30 order, 30 transaction;
migration đủ `001` đến `007`. Các số này sẽ thay đổi sau khi bạn thao tác ứng dụng.
Catalogue giữ 16 sản phẩm gốc và thêm 984 biến thể có tên/mã riêng (`SP-00017`–`SP-01000`),
phủ đủ 8 danh mục, 4 trạng thái, nhiều mức giá, tồn kho và người bán. Một phần sản phẩm
được đánh dấu xóa mềm để thử bộ lọc; vì vậy danh sách công khai không hiển thị đủ 1.000 dòng.
Mỗi sản phẩm có 2 bản ghi ảnh; toàn bộ dùng lại 32 file ảnh sản phẩm có sẵn.
User sau migration nằm trong `user_core`, `user_profile`, `user_secret`, `user_wallet`;
`users_full` là view đọc kết hợp. Không tìm bảng `user` cũ để kết luận seed bị mất.

## 6. Seed ảnh và chuyển storage sang MinIO

Bucket đã tạo ở 5.2, ảnh local đã chép ở 5.3. Bây giờ copy object:

**Linux / WSL — Bash**

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.seed_media
```

**Windows — PowerShell 7.3+**

```powershell
dc run --rm --no-deps --entrypoint python backend -m scripts.seed_media
```

Kết quả cần có `missing: []`. `uploaded`/`skipped` phụ thuộc đã chạy trước hay chưa.
Script thêm object còn thiếu, không ghi đè object đã có và không sửa URL ảnh trong PG.
Seed có cả alias legacy/canonical và avatar nên tổng số object không bằng 32 product_image.

Sau khi copy thành công:

**Linux / WSL — Bash**

```bash
python3 deploy/scripts/prepare-media-env.py --enable-minio
```

**Windows — PowerShell 7.3+**

```powershell
py -3 deploy/scripts/prepare-media-env.py --enable-minio
```

Script giữ các secrets hiện tại và đặt `STORAGE_BACKEND=minio`. Lệnh `dc` tiếp theo sẽ đọc
cấu hình mới; không cần `source deploy/.env.data` trên Bash hoặc dot-source file env trên PowerShell.
Trình tự này tránh bật storage MinIO khi
ảnh còn chỉ nằm trên đĩa local. Với ứng dụng đã có người dùng/upload, chuyển storage phải
có thời gian bảo trì để không phát sinh file mới giữa lúc copy và đổi cấu hình.

Bốn bucket là `product-images`, `product-videos`, `user-avatars`, `attachments`. Backend/ETL dùng
`MINIO_APP_ACCESS_KEY`/`MINIO_APP_SECRET_KEY`, không dùng root credentials để phục vụ request.

## 7. Nạp dữ liệu Mongo bằng ETL và mở ứng dụng

### 7.1. Full ETL lần đầu và đối soát

Lúc này chưa khởi động worker nên CLI không tranh advisory lock với daemon:

**Linux / WSL — Bash**

```bash
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc run --rm --no-deps --entrypoint python backend -m etl.run status
```

**Windows — PowerShell 7.3+**

```powershell
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc run --rm --no-deps --entrypoint python backend -m etl.run status
```

`full` và `reconcile` cần trả `status: success`. Status cần `pending: 0`, `dead: 0`,
`last_run.status: success`. Nếu có `partial`/lỗi, xử lý theo mục 13 trước khi mở ứng dụng.
Có thể chạy lại `full` thêm một lần để kiểm replay; số document nghiệp vụ không nhân đôi.

Với seed ban đầu, các collection nghiệp vụ có 1.000 `product_details`, 30 `order_snapshots`,
11 `violation_logs`; `reviews`, `system_logs`, `contact_messages` ban đầu rỗng.
`attributes`/`tags` của sản phẩm có thể rỗng: seed quan hệ không tự tạo thông số RAM/brand
giả như bộ metadata riêng dùng trong video demo. Không import JSON ví dụ thiết kế như một
bộ seed bổ sung vào DB đã ETL.

### 7.2. Chạy backend, frontend và ETL daemon

**Linux / WSL — Bash**

```bash
dc up -d --wait --wait-timeout 240 backend etl-worker frontend
dc ps --all
```

**Windows — PowerShell 7.3+**

```powershell
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

**Linux / WSL — Bash**

```bash
curl -fsS http://localhost:58000/health
curl -fsS http://localhost:58000/health/ready
curl -fsS http://localhost:58080/api/v1/categories
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

**Windows — PowerShell 7.3+**

```powershell
curl.exe -fsS http://localhost:58000/health
curl.exe -fsS http://localhost:58000/health/ready
curl.exe -fsS http://localhost:58080/api/v1/categories
py -3 deploy/scripts/check-data-stack.py --resilience --day6
```

Checker cần trả `result: PASS`: chín service khỏe, schema 001–007 khi đã nâng indexing, PG replica streaming,
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

**Linux / WSL — Bash**

```bash
python3 database/build_pgadmin_init.py --output /tmp/oldshop-init-pgadmin.sql
```

**Windows — PowerShell 7.3+**

```powershell
py -3 database/build_pgadmin_init.py --output (Join-Path $env:TEMP "oldshop-init-pgadmin.sql")
```

Tạo một database rỗng bằng pgAdmin trước, chọn đúng DB rồi mở/chạy SQL vừa sinh trong Query Tool.
Trên Linux output ở `/tmp/oldshop-init-pgadmin.sql`; trên Windows nằm trong thư mục tạm
`$env:TEMP`, ví dụ `C:\Users\<user>\AppData\Local\Temp\oldshop-init-pgadmin.sql`.
File output phải chưa tồn tại; đổi tên nếu sinh lại. `init.sql` gốc có `\i` của psql nên không
paste trực tiếp vào Query Tool. SQL sinh ra chỉ là baseline + seed Ngày 1, **chưa áp 001–007**.
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

**Linux / WSL — Bash**

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

**Windows — PowerShell 7.3+**

```powershell
function dc {
    $composeArgs = @(
        "compose",
        "--env-file", "deploy/.env.data",
        "-f", "deploy/docker-compose.distributed.yml",
        "-f", "deploy/docker-compose.gui.yml",
        "--profile", "resilience"
    )
    & docker @composeArgs @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose that bai, exit code: $LASTEXITCODE"
    }
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

**Linux / WSL — Bash**

```bash
# Định nghĩa lại dc nếu đây là terminal mới.
dc up -d --wait --wait-timeout 240
dc ps --all
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

**Windows — PowerShell 7.3+**

```powershell
# Định nghĩa lại dc nếu đây là terminal mới.
dc up -d --wait --wait-timeout 240
dc ps --all
py -3 deploy/scripts/check-data-stack.py --resilience --day6
```

Không cần `cp` env, tạo DB, seed hoặc full ETL lại mỗi lần bật máy. Các init job được thiết kế
để chạy lại; worker tiếp tục từ trạng thái/outbox. Khi đã mở rộng Mongo thành ba voting member,
tiếp tục dùng profile `resilience`; không bỏ profile rồi chỉ chạy mongo1 và kỳ vọng giữ quorum.

### 10.2. Thay cấu hình hoặc cập nhật code

Nếu cập nhật bộ cấu hình indexing JSON trên DB đã qua 007, dùng mục 18.2–18.3.
Nếu thay đổi định nghĩa index, dùng thêm mục 18.4 trước khi triển khai.

`restart` không nạp lại biến môi trường mới vào container. Với thay đổi thông thường không
liên quan schema/storage/secrets, dùng `dc up -d --wait` để Compose áp cấu hình container.
Nếu backend bị recreate, Nginx có thể giữ IP backend cũ; sau khi backend khỏe, restart frontend:

**Linux / WSL — Bash**

```bash
dc restart frontend
dc up -d --no-deps --wait --wait-timeout 90 frontend
```

**Windows — PowerShell 7.3+**

```powershell
dc restart frontend
dc up -d --no-deps --wait --wait-timeout 90 frontend
```

Với DB đã dùng mà cần nâng cấp schema/app lên bộ migration hiện tại, xem
[quy trình tích hợp](design/06_completion_plan.md), rồi thực hiện trong thời gian bảo trì:

**Linux / WSL — Bash**

```bash
bash deploy/scripts/apply-day6.sh --resilience
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

**Windows — PowerShell 7.3+**

```powershell
# Vi du repo Windows nam o C:\Projects\Epic-Ecommerce-FastAPI-main.
# Ubuntu la distro WSL da cai va da bat Docker Desktop WSL Integration.
wsl --distribution Ubuntu --cd "/mnt/c/Projects/Epic-Ecommerce-FastAPI-main" --exec bash deploy/scripts/apply-day6.sh --resilience
if ($LASTEXITCODE -ne 0) { throw "Apply Day 6 that bai; kiem tra trang thai bao tri." }
py -3 deploy/scripts/check-data-stack.py --resilience --day6
```

Trên Windows, `apply-day6.sh` vẫn chạy bằng **Bash trong WSL**, không chạy trực tiếp bằng
PowerShell. Thay `Ubuntu` và đường dẫn `/mnt/c/...` bằng distro/thư mục thật; xem danh sách distro
bằng `wsl --list --verbose`. Distro phải có `python3`, Bash, Docker CLI thông qua Docker Desktop
Integration và truy cập cùng repository/daemon/volumes với phiên PowerShell.
Giữ `.sh` ở line ending **LF** theo `.gitattributes` của repo; lỗi `\r`/`bad interpreter` thường
cần đổi line ending trong editor. [Các lệnh WSL](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

Script build image, dừng frontend/backend/worker, backup và thử restore, chạy migration/index,
full/reconcile, đối chiếu 18 bảng nguồn và chỉ mở lại khi thành công. Backup nằm trong
`deploy/backups/`; lỗi sẽ giữ trạng thái bảo trì. Script dành cho stack local với các điều kiện
trong runbook, không thay thế quy trình nâng cấp mọi DB tùy biến. Nếu đang dùng override riêng,
cần kiểm tra vì script apply dùng Compose chính, không tự ghép file GUI override.

Đổi `DB_PASSWORD`, `MONGO_APP_PASSWORD`, `MINIO_APP_SECRET_KEY` trong file env không tự đổi
password đã lưu trong PG/Mongo/MinIO. Không sinh lại credentials cho volume cũ. Việc rotate
secret, đổi major Mongo hoặc chuyển storage là thao tác riêng cần kế hoạch bảo toàn dữ liệu.

### 10.3. Nâng indexing v2 từ schema 006

Bản cập nhật có `007_indexing_v2.sql` (9 index PostgreSQL) và M01 MongoDB. Không thêm
bảng/cột, không đổi seed hoặc PK/UNIQUE; schema vẫn 28 bảng logic/222 cột. Không sửa file
migration đã áp hoặc reseed DB đang dùng. [Kết quả đo dữ liệu hiện tại](benchmark/README.md)
được tạo trên môi trường riêng; DB của bạn chưa tự nhận thay đổi này.

- Backend chạy trực tiếp: dùng cấu hình kết nối trong `backend/.env`, làm backup/thử
  restore và dừng nguồn ghi, rồi chạy runner theo [hướng dẫn tự áp](runbooks/indexing_v2.md).
- Stack Compose chính đã qua 006: dùng `bash deploy/scripts/apply-indexing-v2.sh`
  (thêm `--resilience` nếu đang dùng profile đó). Script backup/thử restore, migrate,
  ANALYZE, init index Mongo và kiểm postflight/reconcile trước khi mở lại ứng dụng.
- Kiểm chỉ đọc từ môi trường backend sau áp: `python -m scripts.verify_indexing_v2 --mongo`.
  Trước áp dùng `--preflight` để kiểm lịch sử/checksum tối thiểu 006.

Không dùng script Compose cho DB native hoặc stack có override/project name riêng.
Các index cũ được giữ để theo dõi usage trước khi cân nhắc thu hồi ở version tiếp theo.

## 11. Xem log, dừng hệ thống và chạy ETL thủ công

**Linux / WSL — Bash**

```bash
dc logs --tail 100 backend
dc logs --tail 100 etl-worker
dc logs --tail 100 mongo-init mongo-expand mongo-schema-init minio-init
dc logs -f --tail 100 backend etl-worker
```

**Windows — PowerShell 7.3+**

```powershell
dc logs --tail 100 backend
dc logs --tail 100 etl-worker
dc logs --tail 100 mongo-init mongo-expand mongo-schema-init minio-init
dc logs -f --tail 100 backend etl-worker
```

`Ctrl+C` thoát lệnh xem log, không dừng container đang chạy nền.

Dừng tạm, giữ container và dữ liệu:

**Linux / WSL — Bash**

```bash
dc stop
```

**Windows — PowerShell 7.3+**

```powershell
dc stop
```

Dừng và gỡ container/network, giữ named volumes để lần sau chạy tiếp:

**Linux / WSL — Bash**

```bash
dc down
```

```xoá hết
dc down --volumes --remove-orphans
```

**Windows — PowerShell 7.3+**

```powershell
dc down
```

Không thêm `--volumes`/`-v` vào lệnh dừng hằng ngày: cờ đó xóa volumes chứa PG, Mongo,
MinIO và media của project. Không dùng reset volume làm cách sửa password hoặc lỗi schema.

Nếu cần full ETL/đối soát thủ công khi daemon đang chạy:

**Linux / WSL — Bash**

```bash
dc stop etl-worker
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc up -d --no-deps --wait --wait-timeout 180 etl-worker
dc exec -T etl-worker python -m etl.run status
```

**Windows — PowerShell 7.3+**

```powershell
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

**Linux / WSL — Bash**

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --only-binary=:all: --require-hashes -r requirements-dev.lock
python -m pip check
cp -n .env.example .env
```

**Windows — PowerShell 7.3+**

```powershell
Set-Location .\backend
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --only-binary=:all: --require-hashes -r requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw "Cai dependencies that bai; chua chay backend/test." }
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependencies chua nhat quan." }
if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
}
```

Trên Linux khối trên activate venv; trên Windows khối trên gọi trực tiếp
`.venv\Scripts\python.exe`, nên không bắt buộc activate và không cần đổi execution policy
để chạy `Activate.ps1`. Mở `backend/.env` bằng editor (Linux: `nano .env`, Windows: `notepad .env`).

`requirements-dev.lock` chứa cả dependencies runtime và kiểm thử, bao gồm
`email-validator`. Dùng `python -m pip` của cùng venv để tránh cài vào Conda `(base)`
nhưng lại chạy bằng Python khác. Python 3.11+ ở mục 2 chỉ dành cho script điều phối;
backend native theo hướng dẫn này dùng Python 3.13 giống Docker. Nếu chưa có Python
3.13, có thể dùng luồng Docker mà không cần cài dependencies backend trên host.

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

**Linux / WSL — Bash**

```bash
python -m scripts.init_db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Windows — PowerShell 7.3+**

```powershell
& .\.venv\Scripts\python.exe -m scripts.init_db
if ($LASTEXITCODE -ne 0) { throw "Kiem tra DB that bai; chua khoi dong API." }
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

DB Docker ở ví dụ đã seed/migrate nên init_db kiểm lại và chép ảnh seed vào `backend/media`.
Ví dụ chạy backend trực tiếp trên Windows yêu cầu DB đã bootstrap theo mục 5 trong Linux container.
Nhánh `load_schema()` của bootstrap dùng file tạm đang mở để gọi `psql`, chưa được xác minh cho
khởi tạo database rỗng bằng Python Windows; nếu cần cài mới, dùng quy trình Docker ở mục 5.
Đây không phải khẳng định toàn bộ backend native Windows đã được kiểm thử end-to-end.
Nếu đổi sang PG cài trực tiếp, sửa `DB_*` đúng role/DB; bootstrap cần quyền tạo DB nếu chưa có,
tạo schema/extensions và áp migration. Không bootstrap thử trên DB production đang dùng.
Không chạy thêm `python -m etl.run worker` trỏ cùng DB nếu worker Docker vẫn hoạt động.

### 12.2. Frontend

Mở terminal khác, từ root:

**Linux / WSL — Bash**

```bash
cd frontend
node --version
npm --version
npm ci --ignore-scripts --no-audit --no-fund
npm start
```

**Windows — PowerShell 7.3+**

```powershell
Set-Location .\frontend
node --version
npm.cmd --version
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd start
```

Theo `frontend/package-lock.json`, Angular hiện yêu cầu Node `^20.19.0 || ^22.12.0 || >=24.0.0`.
Windows dùng `npm.cmd` để gọi executable shim của npm, tránh chọn nhầm script `npm.ps1`
khi execution policy không cho chạy script. Mở http://localhost:4200. File `src/environments/environment.ts` trỏ API/media tới
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
| PowerShell không hiểu `source`, `chmod`, `<<SQL` | Chọn khối Windows thay vì copy khối Bash; hoặc chuyển hẳn sang WSL |
| `py` không được nhận diện | Kiểm Python launcher/PATH; dùng đúng Python 3.11+ hoặc Python 3.13 cho nhánh dev |
| PowerShell 5.1 làm mất dấu nháy khi gọi Docker | Dùng PowerShell 7.3+ và thiết lập native argument passing ở mục 2, hoặc dùng nhánh WSL |
| `npm.ps1`/`Activate.ps1` bị chặn | Dùng `npm.cmd` và `.venv\Scripts\python.exe` như ví dụ Windows |
| Pytest báo `No module named 'email_validator'` | Python đang chạy thiếu dependency runtime; chuẩn bị venv đầy đủ theo mục 18.5, không sửa catalog/index để chữa lỗi import |
| `No module named scripts.indexes` | Kiểm thư mục làm việc `backend/` nếu chạy host, hoặc build lại image backend nếu chạy Docker; xem mục 18.2 |
| Index CLI báo `No applied index snapshot` | PostgreSQL phải qua 007; Mongo cần init/apply snapshot bằng image mới; xem mục 18.3 |
| WSL không tìm được repo / distro | Kiểm `wsl --list --verbose`, đổi tên distro và đường dẫn `/mnt/c/...` theo máy |
| Container báo `bad interpreter` / `\r` | Đổi `.sh` sang LF; giữ quy tắc `.gitattributes` khi clone/edit trên Windows |

## 14. Kiểm thử và tài liệu tiếp theo

Swagger dùng để kiểm API; DB constraints, Mongo validators, ETL replay và lỗi/phục hồi cần
runner tích hợp riêng. Runner Ngày 6 tự tạo project/DB/volumes tạm và dọn sau kiểm thử:

**Linux / WSL — Bash**

```bash
bash deploy/scripts/test-day6.sh --mongo-image mongo:7.0
```

**Windows — PowerShell 7.3+**

```powershell
# Thay distro va duong dan bang noi luu repo cua ban.
wsl --distribution Ubuntu --cd "/mnt/c/Projects/Epic-Ecommerce-FastAPI-main" --exec bash deploy/scripts/test-day6.sh --mongo-image mongo:7.0
if ($LASTEXITCODE -ne 0) { throw "Kiem thu Day 6 that bai; xem log WSL." }
```

Trên Windows, lệnh test `.sh` ở trên chạy qua WSL giống quy trình bảo trì ở mục 10.2;
không dùng `bash` từ Git Bash thay cho distro WSL được cấu hình Docker Integration.
Với host đã xác minh tương thích Mongo8, có thể dùng image mặc định của runner.
Không chạy `pytest` tùy ý với `DB_NAME=oldshop` đang sử dụng: tests có ghi dữ liệu.
Xem các điều kiện và cách chạy ở [06_completion_plan.md](design/06_completion_plan.md).
Riêng bộ unit test indexing JSON không kết nối DB có quy trình chuẩn bị môi trường
và lệnh giới hạn đúng file ở mục 18.5. `--noconftest` không thay thế việc cài dependencies.

- [PROJECT_GUIDE.md](PROJECT_GUIDE.md): bản đồ mã nguồn và kiến trúc.
- [Thiết kế Mongo/MinIO](design/03_json_design.md): validators, indexes và seed media.
- [Migration/indexing](design/04_indexing.md): quản lý schema, partition và rollback.
- [ETL](design/05_etl.md): ownership, provenance thời gian và đối soát.
- [Hồ sơ Ngày 7](report/README.md): báo cáo, slide, video và kịch bản demo.
- [Deployment VPS](deployment.md): tài liệu cho profile VPS riêng.

Luồng cài mới cần nhớ: **env → build → hạ tầng → init users/buckets/validators → PG seed và
migration → copy ảnh → bật MinIO → full ETL/reconcile → backend/frontend/worker → checker**.

## 15. Phạm vi kiểm tra hai nền tảng

Nhánh Linux dựa trên stack local và script đã có bằng chứng các ngày trước. Ở lần bổ sung
hướng dẫn hai nền tảng trước đây, **29 khối Bash** đã qua `bash -n`; **29 khối PowerShell** đã qua parser PowerShell 7.6.9
chạy trên Linux. Hai hàm `dc` và luồng SQL here-string/pipeline còn được kiểm bằng Docker giả lập:
giữ tham số/dấu nháy, chuyển SQL vào stdin và báo lỗi khi native command trả mã khác 0.

Chưa có lượt cài mới end-to-end trên máy Windows trong tác vụ này. Trước khi kết luận máy
Windows đã chạy thành công, thực hiện đến checker ở mục 8 trên chính máy đó.

Lần bổ sung indexing JSON ngày 03/11/2026 đã tái hiện lỗi môi trường Conda, rồi chạy
**53 unit test PASS** và CLI `validate` PASS bằng Python 3.13 với dependencies đã khóa
trong container riêng, không có kết nối mạng tới DB. Các bước apply ở mục 18 là hướng
dẫn để người vận hành thực hiện; lần sửa tài liệu này không áp index vào DB đang dùng.
Các lệnh PowerShell mới ở mục 18 chưa được chạy trên Windows.

## 16. Video Google Drive và upload MP4

Người bán có thể chọn liên kết Google Drive/YouTube hoặc upload MP4 tối đa 50 MiB.
MP4 được lưu trong bucket private `product-videos` và phát qua media gateway.
Xem [hướng dẫn video sản phẩm](HUONG_DAN_VIDEO_SAN_PHAM.md) để áp dụng vào stack hiện hữu,
chuẩn bị video seed, cài ffprobe khi chạy host và kiểm chứng tạo/sửa/xóa video.
Không cần thêm bảng hoặc chạy lại seed SQL trên DB đang dùng.

## 17. Danh sách kiểm duyệt sản phẩm đầy đủ

Moderator tải từng trang từ backend thay vì chia trang trên 100 bản ghi đầu tiên.
API mới `GET /api/v1/products/moderation/page` nhận `status` (0/1/2), `skip`, `limit`,
`search` và trả `{items, total, skip, limit}`. Mỗi lần tải mặc định trên giao diện là 5
sản phẩm; chuyển trang sẽ yêu cầu trang tương ứng trên server, kể cả các bản ghi sau mốc 100.

Tìm kiếm áp dụng trên toàn bộ danh sách theo tên sản phẩm, username người bán hoặc danh mục.
Tên người bán và danh mục được API trả kèm; màn hình không cần tải trước danh sách user.
Thứ tự là ID sản phẩm giảm dần để hiển thị tin đăng mới trước. Không so sánh trực tiếp
`created_at` của seed theo giờ Việt Nam với timestamp UTC của ORM. Dữ liệu thời gian nguồn
và provenance ETL được giữ nguyên. API danh sách dạng mảng cũ vẫn dùng được.

Sau khi duyệt/từ chối, tổng số được tải lại; nếu trang cuối không còn sản phẩm, giao diện
quay về trang hợp lệ trước đó. Nút **Tải lại** đưa về trang đầu để thấy tin đăng mới.
Không có thay đổi schema, bảng `product_image` hoặc dữ liệu seed.

Để áp dụng, từ thư mục gốc với hàm `dc` đã định nghĩa ở mục 4, chạy từng lệnh sau và
chỉ tiếp tục khi lệnh trước thành công (Bash hoặc PowerShell 7.3+):

```text
dc build backend frontend
dc up -d --no-deps --force-recreate --wait --wait-timeout 180 backend
dc up -d --no-deps --force-recreate --wait --wait-timeout 90 frontend
```

Tải lại trình duyệt bằng Ctrl+Shift+R. Cần cập nhật cả backend và frontend; không cần
reset DB hoặc xóa volume. Backend được khởi động trước; frontend được tạo lại sau đó
để Nginx nhận địa chỉ backend hiện tại.

Kiểm chứng: đăng một sản phẩm bằng user, chuyển sang moderator và bấm **Tải lại** ở
tab chờ duyệt. Sản phẩm mới đứng đầu; chuyển đến trang cuối, kiểm tổng số và thử tìm tên
sản phẩm nằm ngoài 100 bản ghi đầu. Kiểm tiếp hai tab đã duyệt và từ chối.
Xem [bằng chứng kiểm thử](evidence/moderator_pagination_tests.txt).


## 18. Cấu hình và chạy indexing JSON

### 18.1. Chọn đúng môi trường và bước cần chạy

Phần này là quy trình vận hành. Chi tiết định dạng/giới hạn thiết kế xem
[Hướng dẫn indexing JSON](HUONG_DAN_INDEXING_JSON.md).

| Bạn đang cần | Thực hiện |
|---|---|
| Cài stack mới | Mục 3–8 đã bootstrap PostgreSQL và init Mongo; kiểm lại bằng mục 18.2 và lệnh verify ở 18.3 |
| Stack đã có dữ liệu, đã qua migration 007, mới cập nhật code indexing JSON | Mục 18.2 rồi 18.3; giữ env và volumes |
| Muốn thay trường/chiều/loại index trong JSON | Mục 18.4; chỉnh JSON chưa đồng nghĩa DB đã đổi |
| Muốn chạy unit test hoặc đang gặp lỗi thiếu `email_validator` | Mục 18.5; đây là bước phát triển tùy chọn |
| DB còn ở 006 hoặc thấp hơn | Nâng theo quy trình bảo trì mục 10 trước khi tiếp nhận snapshot `index-v1` |

Phân biệt ba môi trường:

| Cách gọi | Code/config được sử dụng | Địa chỉ DB |
|---|---|---|
| `dc run ... backend ...` | Image backend mới nhất và env Compose từ `deploy/.env.data` | PG `pg-primary:5432`, Mongo `mongo1:27017` trong Docker network |
| `dc exec ... backend ...` | Container backend **đang chạy**, có thể vẫn giữ image/env cũ | Env tại thời điểm container được tạo |
| `python -m scripts...` trong `backend/` | Source trên host, dependencies của Python đang gọi và `backend/.env`/environment | PG host thường `127.0.0.1:55432`; Mongo dùng cổng host theo mục 9.2 |

Không đưa `127.0.0.1:55432` vào cấu hình backend chạy bên trong container: địa chỉ
loopback ở đó là chính container. Không dùng hostname `mongo1` trong terminal host.
Các lệnh Docker dưới đây không cần activate Conda/venv hoặc cài pip trên host.

### 18.2. Chuẩn bị image và kiểm tra cấu hình không ghi DB

Từ **root dự án**, dùng hàm `dc` đã định nghĩa ở mục 4 (hoặc bản có GUI override ở
mục 9.2 nếu stack đang dùng override đó). Mỗi terminal mới cần định nghĩa lại hàm.
Chạy lần lượt, chỉ tiếp tục khi lệnh trước thành công. Dùng được trong Bash và
PowerShell 7.3+:

```text
dc config --quiet
dc build backend frontend
dc ps --all
dc run --rm --no-deps --entrypoint python backend -m scripts.indexes validate
```

`validate` chỉ đọc JSON; không kết nối hoặc tạo index trong DB. Với catalog hiện tại,
kết quả cần có `result: PASS`, `desired_revision: index-v1`, `counts.postgresql: 98`
và `counts.mongodb: 19`. PostgreSQL gồm 61 index ứng dụng/ETL và 37 index của
PK/UNIQUE trong danh mục; số index con của partition được quản lý riêng.
Không cần sửa các con số vào file JSON nếu chúng khác sau một revision mới có chủ đích.

Image chứa `catalog.json`, `catalog.schema.json`, `releases.json`, snapshots và SQL
ở `/opt/database`. `dc build` đóng gói code/JSON mới nhưng chưa thay container đang
chạy; `dc run` tạo container một lần từ image vừa build. Không mount riêng catalog
mới vào image đang thiếu snapshot/SQL tương ứng.

Sau khi PG và Mongo đã sẵn sàng (mục 5.1–5.2), xem kế hoạch chỉ đọc:

```text
dc run --rm --no-deps --entrypoint python backend -m scripts.plan_indexes --engine all
```

Ý nghĩa kết quả:

| Giá trị | Cách hiểu |
|---|---|
| `matched` | Index thực tế khớp định nghĩa mong muốn |
| `missing` | Chưa có index; plan chỉ báo, chưa tạo |
| `conflict` | Cùng tên nhưng khác khóa/options, tên trường sai hoặc có định nghĩa tương đương dưới tên khác; cần xử lý trước apply |
| `unmanaged` | Index ngoài danh mục, chẳng hạn `_id_`; công cụ không tự xóa |
| Plan `result: PASS` | Không có conflict; **vẫn có thể còn `missing`**, chưa chứng minh triển khai hoàn tất |

Nếu muốn giữ báo cáo ngay trên host, dùng stdout redirect. Ví dụ Bash:

```bash
mkdir -p docs/evidence
dc run --rm -T --no-deps --entrypoint python backend -m scripts.plan_indexes --engine all > docs/evidence/index_plan_local.json
```

PowerShell 7.3+:

```powershell
New-Item -ItemType Directory -Force docs/evidence | Out-Null
dc run --rm -T --no-deps --entrypoint python backend -m scripts.plan_indexes --engine all > docs/evidence/index_plan_local.json
```

Kiểm exit code và đọc `result` trong file. Dùng `--output /tmp/plan.json` bên trong
container `--rm` sẽ tạo file trong container và mất khi container bị xóa; đường dẫn
`docs/...` trong container cũng không tự trỏ tới thư mục docs trên host.

### 18.3. Tiếp nhận cấu hình hiện tại trên DB đã qua 007 và chạy ứng dụng

Điều kiện: đã build image mới, PostgreSQL có lịch sử migration 001–007, Mongo replica
set/users đã init, plan không có conflict. Giữ nguyên `catalog.json` revision `index-v1`
khi thực hiện luồng này. Nếu DB chưa đủ điều kiện, quay lại mục 5 cho DB mới hoặc
quy trình bảo trì mục 10 cho DB hiện hữu.

Các lệnh sau có ghi metadata/index Mongo; kiểm tra đúng project/env trước khi chạy.
Thực hiện lần lượt trong Bash hoặc PowerShell 7.3+:

```text
dc run --rm --no-deps mongo-schema-init
dc run --rm --no-deps --entrypoint python backend -m scripts.apply_indexes --engine postgresql
dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexes --engine all
dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexes --engine all --desired
```

- `mongo-schema-init` dùng tài khoản quản trị Mongo của job Compose để cập nhật
  validators, bổ sung index còn thiếu và ghi snapshot `_index_catalog_state`.
  Không thay job này bằng `init_mongo` trong container dùng user ứng dụng có ít quyền hơn.
- PostgreSQL hiện tại đã có các index tương ứng sau 007; apply đối soát và không cần
  sinh migration 008 chỉ để chuyển cách khai báo sang JSON. Nếu kết quả khác dự kiến,
  dừng và đọc báo cáo trước khi nâng tiếp.
- `verify` không có `--desired` kiểm theo snapshot **đã áp** của từng DB. Thêm
  `--desired` để kiểm theo catalog **đang muốn áp**. Hai lệnh đều phải `PASS` nếu
  muốn kết luận cấu hình hiện tại đã triển khai đầy đủ.

Nếu chỉ kiểm chứng một stack đã init thành công, chạy hai lệnh verify, không cần
chạy lại toàn bộ init. CLI trả exit code 1 khi `FAIL`; không tiếp tục bỏ qua lỗi.

Sau khi các bước thành công, cập nhật các container thường trực để chúng dùng code
và env mới. Chạy tuần tự, backend khỏe rồi mới tạo lại worker/frontend:

```text
dc up -d --no-deps --force-recreate --wait --wait-timeout 180 backend
dc up -d --no-deps --force-recreate --wait --wait-timeout 120 etl-worker
dc up -d --no-deps --force-recreate --wait --wait-timeout 90 frontend
dc ps --all
```

Chạy checker từ root:

```bash
python3 deploy/scripts/check-data-stack.py --resilience --day6
```

PowerShell 7.3+:

```powershell
py -3 deploy/scripts/check-data-stack.py --resilience --day6
```

Checker đánh giá stack, không thay hai lệnh verify index ở trên. Mở
http://localhost:58080, tải lại bằng Ctrl+Shift+R. Luồng này giữ nguyên dữ liệu,
không chạy lại seed SQL và không dùng `down --volumes`.

### 18.4. Khi cần thay đổi định nghĩa index trong JSON

Các file cần đi cùng nhau:

| File | Vai trò |
|---|---|
| `database/indexing/catalog.json` | Cấu hình mong muốn: trường, thứ tự key, chiều, loại/options |
| `database/indexing/catalog.schema.json` | Schema hỗ trợ editor/kiểm tra cấu hình; không phải dữ liệu sản phẩm |
| `database/indexing/snapshots/*.json` | Bản cấu hình được đóng băng theo revision |
| `database/indexing/releases.json` | Gắn revision/hash với migration PostgreSQL |
| `database/04_migrations/*.sql` | DDL PostgreSQL thực sự được migration runner áp |
| JSON trong `docs/evidence/`, `docs/benchmark/` | Kết quả chạy/đo, không phải đầu vào tạo index |

Không sửa migration 001–007 hoặc snapshot đã phát hành. Luồng bổ sung PostgreSQL index:

1. Làm trên worktree và DB kiểm thử đã qua các migration hiện có; chuẩn bị Python
   native theo mục 12.1 và cấu hình `backend/.env` trỏ đúng DB kiểm thử.
2. Sửa catalog, đặt revision mới, ví dụ `index-v2`. Xem ví dụ đúng định dạng ở
   [hướng dẫn JSON](HUONG_DAN_INDEXING_JSON.md); không chép một index demo vào DB thật
   chỉ để đạt đủ số lượng.
3. Từ `backend/`, dùng Python của venv để validate, plan và sinh artifact:

   **Linux / WSL — Bash**

   ```bash
   .venv/bin/python -m scripts.indexes validate
   .venv/bin/python -m scripts.plan_indexes --engine postgresql
   .venv/bin/python -m scripts.generate_index_migration
   ```

   **Windows — PowerShell 7.3+**

   ```powershell
   & .\.venv\Scripts\python.exe -m scripts.indexes validate
   if ($LASTEXITCODE -ne 0) { throw "Catalog khong hop le." }
   & .\.venv\Scripts\python.exe -m scripts.plan_indexes --engine postgresql
   if ($LASTEXITCODE -ne 0) { throw "Plan that bai." }
   & .\.venv\Scripts\python.exe -m scripts.generate_index_migration
   if ($LASTEXITCODE -ne 0) { throw "Sinh migration that bai." }
   ```

   Chỉ chạy lệnh tiếp nếu lệnh trước thành công. Generator đọc DB nhưng ghi SQL,
   snapshot và release binding vào worktree. Vì vậy không chạy generator trong
   container runtime rồi kỳ vọng file mới xuất hiện ở source host.
4. Review các artifact cùng nhau. Khi bổ sung index đầu tiên sau 007, tên SQL có
   dạng `008_indexes_index-v2.sql`; công cụ chọn số tiếp theo thực tế. Nếu không đổi
   PostgreSQL index, generator có thể trả `generated: false`, không sinh SQL giả.
5. Kiểm thử trên DB riêng; khi triển khai vào DB hiện hữu, thực hiện backup/thử restore
   và dừng nguồn ghi theo quy trình bảo trì mục 10. Build lại image từ bộ artifact
   đã review trước khi apply. Index build có thể giữ lock, không mặc định là DDL online.
6. Từ root, sau build, chạy lần lượt:

   ```text
   dc run --rm --no-deps --entrypoint python backend -m scripts.plan_indexes --engine all
   dc run --rm --no-deps --entrypoint python backend -m scripts.apply_indexes --engine all
   dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexes --engine all
   dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexes --engine all --desired
   ```

   Sau đó mở lại/cập nhật ứng dụng theo mục 18.3. `apply --engine all` preflight cả
   hai DB, nhưng không có transaction chung cho PostgreSQL và Mongo. Nếu lỗi giữa
   chừng, kiểm kết quả từng engine rồi plan lại; không reset dữ liệu để thử lại.

Nếu chỉ bổ sung index Mongo, không cần SQL PostgreSQL mới; dùng plan/apply với
`--engine mongodb`, sau đó verify Mongo với cả snapshot đã áp và `--desired`.
Đổi khóa/chiều/unique/TTL của index cùng tên cần migration/quy trình riêng; công cụ
hiện tại chủ yếu tự động bổ sung index, không tự drop/rebuild index gây conflict.

### 18.5. Chạy unit test indexing và xử lý lỗi `email-validator`

Log ngày 03/11/2026 có **44 passed, 9 failed**. Cả 9 lỗi đều xảy ra khi import
document contract: `index_mongo` → `app.schemas.documents` → `app.schemas.__init__`
→ các model có `EmailStr` → thiếu module `email_validator`. Đây là lỗi dependencies
của Python đang chạy, chưa phải kết quả cho thấy index trong DB sai. Package này đã
khai báo trong `requirements.txt` và các lock file; không cần thêm dependency mới.

Terminal `(base)` đang dùng Python 3.14 không tự có đủ thư viện backend. Cờ
`--noconftest` chỉ ngăn nạp `conftest.py`, không ngăn các import runtime của test.
Chuẩn bị **Python 3.13 riêng của dự án** thay vì cài rời từng package vào base.
Unit test này không cần sửa `.env`, không cần PG/Mongo/MinIO và không cần chạy API.

**Cách A — chạy native, từ `backend/`**, sau khi đã có Python 3.13. Nếu `.venv` đã tồn
tại, kiểm tra `.venv/bin/python --version` (Windows: `.venv\Scripts\python.exe --version`)
trước. Tái sử dụng nếu đúng 3.13; nếu khác phiên bản, chọn thư mục venv mới, chẳng hạn
`.venv-indexing`, và thay đường dẫn trong các lệnh. Không tạo đè môi trường Python khác.

Linux / WSL — Bash:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: --require-hashes -r requirements-dev.lock
.venv/bin/python -m pip check
.venv/bin/python -c 'import sys, email_validator, pydantic, pytest; print(sys.executable); print(sys.version)'
.venv/bin/python -m pytest --noconftest -o addopts= tests/test_index_config.py -q
```

Chạy từng lệnh, dừng nếu cài dependencies hoặc kiểm tra import lỗi.

Windows — PowerShell 7.3+:

```powershell
py -3.13 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Can Python 3.13 de tao venv." }
& .\.venv\Scripts\python.exe -m pip install --only-binary=:all: --require-hashes -r requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw "Cai dependencies that bai." }
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependencies chua nhat quan." }
& .\.venv\Scripts\python.exe -c 'import sys, email_validator, pydantic, pytest; print(sys.executable); print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw "Import runtime that bai." }
& .\.venv\Scripts\python.exe -m pytest --noconftest -o addopts= tests/test_index_config.py -q
if ($LASTEXITCODE -ne 0) { throw "Unit test indexing that bai." }
```

`python -m pip check` phải báo không có dependency lỗi; kết quả hiện tại cần
**53 passed**. Chạy `python -m pip ...` và `python -m pytest ...` bằng đúng executable
đã in ra. Cài package ở venv A không sửa được test đang chạy ở Conda/base B.

**Cách B — không có Python 3.13 trên host: dùng Docker.** Từ root, đã định nghĩa `dc`
và build backend ở mục 18.2. Runtime image không chứa pytest/test source, nên mount
đúng file và cài bộ dev vào venv tạm của container:

Linux / WSL — Bash:

```bash
dc run --rm -T --no-deps \
  --volume "${PWD}/backend/tests:/app/tests:ro" \
  --volume "${PWD}/backend/pytest.ini:/app/pytest.ini:ro" \
  --volume "${PWD}/backend/requirements-dev.lock:/tmp/requirements-dev.lock:ro" \
  --entrypoint sh backend -c 'python -m venv --system-site-packages /tmp/index-test-venv && /tmp/index-test-venv/bin/python -m pip install --require-hashes -r /tmp/requirements-dev.lock && /tmp/index-test-venv/bin/python -m pytest --noconftest -o addopts= -o cache_dir=/tmp/index-pytest-cache tests/test_index_config.py -q'
```

Windows — PowerShell 7.3+:

```powershell
dc run --rm -T --no-deps `
  --volume "${PWD}/backend/tests:/app/tests:ro" `
  --volume "${PWD}/backend/pytest.ini:/app/pytest.ini:ro" `
  --volume "${PWD}/backend/requirements-dev.lock:/tmp/requirements-dev.lock:ro" `
  --entrypoint sh backend -c 'python -m venv --system-site-packages /tmp/index-test-venv && /tmp/index-test-venv/bin/python -m pip install --require-hashes -r /tmp/requirements-dev.lock && /tmp/index-test-venv/bin/python -m pytest --noconftest -o addopts= -o cache_dir=/tmp/index-pytest-cache tests/test_index_config.py -q'
```

Docker cần truy cập package registry để cài dependencies dev. Venv này bị xóa cùng
container; không cài vào Conda, không sửa image runtime và không ghi DB. Giữ nguyên
đường dẫn unit test, không thay bằng toàn bộ `tests/` trên cấu hình DB đang dùng.

Test tích hợp DB thật là bước riêng: xem mục 6 của
[hướng dẫn JSON](HUONG_DAN_INDEXING_JSON.md). Nó cần PG/Mongo kiểm thử riêng, quyền
tạo/xóa DB và biến opt-in; 53 unit test qua không chứng minh DB thật đã áp index.

### 18.6. Lỗi indexing thường gặp và bước tiếp theo

| Lỗi / hiện tượng | Xử lý |
|---|---|
| `No module named 'email_validator'` | Dùng đủ quy trình 18.5; kiểm `sys.executable`, cài lock file bằng Python đó |
| `python3.13: command not found` hoặc launcher không tìm thấy 3.13 | Dùng Docker ở 18.5 cách B, hoặc cài Python 3.13 trước khi tạo venv; không tự đổi backend sang Python base |
| `No module named scripts.indexes` | Host: chạy từ `backend/`. Docker: build lại từ root; `restart` không nạp source mới |
| Không thấy `/opt/database/indexing/catalog.json` | Kiểm đang dùng đúng Dockerfile/build context root; build bộ code + database cùng nhau |
| `failed_engine: postgresql`, `OperationalError` | Kiểm PG khỏe, DB/user/password, host/port và lịch sử migration; backend host đọc `.env`, Compose đọc env riêng |
| `failed_engine: mongodb`, `ServerSelectionTimeoutError` | Kiểm PRIMARY/quorum/auth; hostname nội bộ chỉ dùng trong Docker, kết nối host xem mục 9.2 |
| `No applied index snapshot; migrate through 007 first` | Kiểm/nâng migration qua quy trình bảo trì; không tự thêm row vào `schema_migrations` |
| Mongo chưa có snapshot đã áp | Chạy job `mongo-schema-init` bằng image mới sau khi plan không conflict; hoặc apply Mongo để ghi snapshot nếu validators đã sẵn sàng |
| Plan có `conflict` | Đọc `name`, `reasons`, `expected`, `actual`; xác định migration thay đổi có chủ đích, không tự drop index |
| `Generate and review a migration ... before PostgreSQL apply` | JSON có thay đổi chưa được đóng băng: sinh SQL/snapshot/release trên worktree rồi build lại image |
| Checksum/hash mismatch | Khôi phục đúng bộ artifact đã phát hành; không sửa checksum DB hoặc snapshot lịch sử để lách kiểm tra |
| `verify` PASS nhưng `verify --desired` FAIL | Snapshot đang chạy vẫn đúng, nhưng catalog mong muốn chưa triển khai hết; plan và xử lý phần thiếu/conflict |
| `plan` PASS nhưng `verify --desired` FAIL | Plan có thể PASS khi index còn missing; phải apply đúng quy trình rồi verify lại |
| `--output` không tạo file trên host | File đang ở container tạm; dùng redirect với `-T` như mục 18.2 hoặc mount thư mục output có quyền ghi |

Nếu CLI chỉ báo lỗi tổng quát, dùng `dc ps --all`, `dc logs --tail 100 pg-primary mongo1`
và `dc logs --tail 100 backend mongo-schema-init` để phân biệt lỗi kết nối/quyền/schema.
Lệnh `dc run --rm` in lỗi trực tiếp ở terminal rồi xóa container, nên cần giữ output
của lần chạy đó. Không đăng URI có password hoặc nội dung `.env` khi gửi log.

Các số đo indexing v2/007 ở mục trước là bằng chứng lịch sử. Sửa JSON cấu hình không
tự làm truy vấn nhanh hơn; cần index vật lý được áp và đo trên workload phù hợp.
