# Hướng dẫn khởi động, triển khai hai máy và demo toàn bộ OldShop

Ngày đối chiếu mã nguồn: **17/11/2026**. Luồng chính của tài liệu là **bucket v2**: `seller → bucket → site`, PostgreSQL + MongoDB + media + Neo4j. Đây là hướng dẫn thao tác; việc viết tài liệu **không thực hiện drop, migration hay triển khai lên máy B**.

Hai mẫu Compose A/B đã được kiểm cấu hình và đường định tuyến môi trường; các truy vấn SQL/Cypher ở phần bucket đã được kiểm chỉ đọc trên stack local. Kết nối hai máy thật cần kiểm lại bằng mục 5.2 và 11.4, vì tài liệu không triển khai máy B thay người vận hành.

Tài liệu dùng Bash trên Linux/Ubuntu; máy Windows dùng WSL2 cho các lệnh shell, hoặc thực hiện qua SSH vào Ubuntu. Các đoạn SQL, JavaScript và Cypher chạy trong công cụ tương ứng, không dán vào Bash. Thay IP ví dụ bằng IP thật trước khi chạy.

## 1. Chọn đúng quy trình

| Nhu cầu | Đọc mục | Đích thao tác |
|---|---|---|
| Chạy nhanh trên một máy | 3 | Compose bucket có sẵn trong repository |
| Chạy thực sự trên máy A và máy B | 4–5 | Hai project Docker riêng; cấu hình đầy đủ được cung cấp bên dưới |
| Hiểu schema, seed và migration | 6 | Core + các owner site + Mongo + graph |
| Thao tác qua giao diện/Swagger | 7 | Nghiệp vụ mua/bán, duyệt, metadata, video |
| Chứng minh hợp nhất ba dạng dữ liệu | 8–9 | SQL, JSON/BSON, file ảnh/video, graph |
| Chứng minh indexing | 10 | PostgreSQL, MongoDB, Neo4j |
| Demo phân tán, mất kết nối và chuyển bucket | 11 | Hai máy A/B, có thể mở rộng C |
| Theo dõi, backup/restore, chạy lại | 12–14 | Có tách restart, reset toàn bộ và DROP DATABASE |
| Demo các thành phần legacy/định hướng mở rộng | 15 | Lab riêng cho replication, FDW, MinIO, ETL đầy đủ |
| Kịch bản thuyết trình và xử lý lỗi | 16–17 | Checklist và kết quả mong đợi |

**Không trộn hợp đồng:** `deploy/sites/compose.site-a.yml`, `compose.site-b.yml` và `fragment_router.py` phục vụ lab phân mảnh cũ. Chúng không thay thế cấu hình bucket v2 ở mục 4. Không chạy seed SQL cũ `database/init.sql` lên core/site đã bootstrap bucket.

Nguồn liên quan: [runbook bucket](runbooks/bucket_site_neo4j.md), [kế hoạch](KE_HOACH_TAI_CAU_TRUC_SEEDING_BUCKET_SITE_NEO4J.md), [báo cáo đã kiểm chứng local](BAO_CAO_TRIEN_KHAI_BUCKET_SITE_NEO4J.md).

## 2. Mô hình và chuẩn bị máy

### 2.1. Phân công service trên hai máy

```mermaid
flowchart LR
  Browser[Trình duyệt / Swagger] --> FE
  subgraph MA[Máy A]
    FE[Frontend + Nginx] --> API[FastAPI]
    API --> CORE[(PostgreSQL core)]
    API --> SA[(PostgreSQL site A)]
    API --> M[(MongoDB metadata)]
    API --> N[(Neo4j projection)]
    API --> MEDIA[Media volume: ảnh/video]
    W[Worker + CLI tools] --> CORE
    W --> SA
    W --> M
    W --> N
    W --> MEDIA
  end
  subgraph MB[Máy B]
    SB[(PostgreSQL site B)]
  end
  API -->|IP B:57632| SB
  W -->|IP B:57632| SB
```

| Dữ liệu | Nơi làm nguồn chính | Bản chiếu/tham chiếu |
|---|---|---|
| User/role/contact/category, order/detail/payment/review | Core trên A | Graph; một số reference được cấp sang site khi cần |
| Product, image membership, quantity, reservation | Site sở hữu bucket: A hoặc B | Directory tại core; Mongo/Neo4j |
| Caption/description từng ảnh, attributes/tags | MongoDB trên A | Neo4j tìm kiếm; API hợp nhất với SQL |
| Byte ảnh, MP4 | Media volume trên A trong cấu hình này | SQL/Mongo lưu URL/key, không lưu byte ảnh trong graph |
| Quan hệ, full-text index ảnh | Neo4j trên A | Dựng lại được từ SQL/Mongo |

A giữ nhiều service để dễ trình diễn; B giữ một shard dữ liệu thật. **Đây là phân tán catalogue, chưa phải HA của core/Mongo/Neo4j**. Một user vừa mua vừa bán không tạo một server riêng.

### 2.2. Máy, mạng và phiên bản

- A: khuyến nghị khoảng 8 GB RAM khi chạy cả build, CLI và các service; B: khoảng 2 GB cho lab PostgreSQL. Đây là dự trù demo, không phải capacity production.
- A cần source hiện tại, Docker Engine, Compose plugin, Python 3, curl. Build frontend dùng Node trong Docker; không bắt buộc cài Node trên host.
- B chỉ cần Docker/Compose và file cấu hình B. A bootstrap schema B qua kết nối PostgreSQL; không cần chạy Python backend trên B.
- Runtime trong cấu hình: PostgreSQL `16-alpine`, MongoDB `8.0.32`, Neo4j `2026.10.2`; Python driver Neo4j được khóa ở `6.4.0`; truy vấn dùng **Cypher 5**.
- IP ví dụ: A `192.168.56.1`, B `192.168.56.101`. Dùng LAN/Bridged, host-only nếu A là host của VM B, hoặc IP VPN có thể truy cập qua lại. IP `127.0.0.1` trong container A không trỏ sang B.
- Docker DNS như `site-a` chỉ dùng trong network Compose tương ứng. Kết nối sang B phải dùng IP/DNS host B và **host port** được publish. Xem [Docker Compose networking](https://docs.docker.com/compose/how-tos/networking/).

Kiểm tra ở cả hai máy:

```bash
hostname
ip -br address
docker version
docker compose version
python3 --version
```

Nếu Ubuntu 24.04 mới chưa có Docker, dùng [hướng dẫn apt repository chính thức](https://docs.docker.com/engine/install/ubuntu/). Bản rút gọn cho máy mới:

```bash
sudo apt update
sudo apt install -y ca-certificates curl python3 openssh-server
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker ssh
sudo usermod -aG docker "$USER"
# Đăng xuất/đăng nhập lại rồi kiểm docker version và docker compose version.
```

Không cài chồng hoặc gỡ Docker đang phục vụ dự án chỉ để làm demo. Cổng DB B chỉ bind vào IP mạng riêng đã chọn; nếu cần hạn chế nguồn truy cập, dùng ACL VPN hoặc quy tắc Docker firewall phù hợp. Không coi `ufw allow/deny` đơn lẻ là đủ bảo vệ port publish: Docker có thể chuyển traffic trước các rule UFW ([Docker firewall](https://docs.docker.com/engine/network/packet-filtering-firewalls/)).

## 3. Chạy trên một máy bằng Compose có sẵn

Bỏ qua mục này nếu dựng hai máy từ đầu; làm mục 4–5 thay thế. Chạy từ root repository:

```bash
cd /duong/dan/Epic-Ecommerce-FastAPI-main
# Chỉ lần đầu, nếu chưa có file; script không ghi đè credential đang có.
python3 deploy/scripts/prepare-bucket-env.py
bucket_local() {
  docker compose -p oldshop-buckets --env-file deploy/.env.bucket \
    -f deploy/docker-compose.bucket.yml "$@"
}
bucket_local config --quiet
bucket_local up -d --wait --wait-timeout 240 core site-a site-b neo4j
bucket_local up -d mongo
bucket_local build backend
bucket_local --profile tools build tools
bucket_local --profile tools up -d tools
bucket_local exec tools python -m scripts.bucket_setup --sites A B
bucket_local exec tools python -m scripts.graph init
bucket_local exec tools python -m scripts.seed plan --dataset demo-v2 --output /tmp/demo-plan-01.json
bucket_local exec tools python -m scripts.seed apply --plan /tmp/demo-plan-01.json
bucket_local exec tools python -m scripts.verify_seed --include-graph
bucket_local build frontend
bucket_local --profile app up -d backend worker frontend
```

Chờ Mongo ping được trước setup nếu Mongo vừa khởi động; lỗi kết nối có thể chạy lại. Không chạy lệnh tạo env nếu file đã tồn tại. **Nếu stack đã có dữ liệu**, kiểm tra `ps`, `health/ready`, `graph status` trước; không reset hoặc apply seed chỉ để khởi động lại.

Frontend `http://localhost:57600`; Swagger `http://localhost:57680/api/docs`; Mongo `localhost:57617`; Neo4j Browser `http://localhost:57474`, Bolt `bolt://localhost:57687`. Các mục demo bên dưới dùng hàm `demo`; ở chế độ một máy đặt:

```bash
demo() { bucket_local "$@"; }
```

Ở terminal mới phải định nghĩa lại hàm. Khi tài liệu ghi `dcb ...`, với chế độ một máy thay bằng `bucket_local ...` cho service `site-b`.

## 4. Tạo cấu hình hai máy cho bucket v2

Hai file Compose trong mục này là **mẫu cần lưu thành file trước khi chạy**, không phải tên file đã có sẵn trong repository. Project A/B dùng volume riêng với stack `oldshop-buckets` một máy. Cổng A trùng lab một máy, vì vậy dừng frontend/backend của lab một máy trước nếu cùng chạy trên A, hoặc chọn port khác trong YAML. Dừng không có `--volumes` sẽ giữ dữ liệu lab đó.

### 4.1. Trên A: tạo env mới, chỉ chuyển credential B sang B

Tại root source hiện tại, bảo đảm có `backend/app/buckets`, `backend/seeding`, `database/distributed/contracts/bucket-v2.json`. Source chưa commit/push có thể không có trong một bản clone mới.

```bash
mkdir -p deploy
umask 077
python3 - <<'PY'
import os, secrets
from pathlib import Path
# Thay IP bên dưới trước khi chạy. Không sửa secret khi đã có volume.
values = {
    'BUCKET_B_HOST': '192.168.56.101',
    'BUCKET_SITE_B_PORT': '57632',
    'BUCKET_DATASET': 'demo-v2',
    'GRAPH_GENERATION': '1',
}
for key in ('BUCKET_PG_PASSWORD', 'BUCKET_SITE_B_PASSWORD', 'BUCKET_MONGO_PASSWORD',
            'BUCKET_GRAPH_PASSWORD', 'BUCKET_SECRET_KEY'):
    values[key] = secrets.token_hex(24)
a = Path('deploy/.env.bucket-ab-a')
b = Path('deploy/.env.bucket-ab-b')
if a.exists() or b.exists():
    raise SystemExit('Env đã tồn tại: tái sử dụng, không tạo lại credential.')
with a.open('x', opener=lambda p, f: os.open(p, f, 0o600)) as out:
    out.write(''.join(f'{k}={v}\n' for k, v in values.items()))
with b.open('x', opener=lambda p, f: os.open(p, f, 0o600)) as out:
    out.write(f"BUCKET_B_BIND_IP={values['BUCKET_B_HOST']}\n")
    out.write(f"BUCKET_SITE_B_PORT={values['BUCKET_SITE_B_PORT']}\n")
    out.write(f"BUCKET_SITE_B_PASSWORD={values['BUCKET_SITE_B_PASSWORD']}\n")
print('Đã tạo hai env riêng; không in password.')
PY
# Đổi TEN_USER_B và IP cho đúng. B chỉ nhận env riêng của B.
ssh TEN_USER_B@192.168.56.101 'mkdir -p ~/oldshop-bucket-demo/deploy'
scp deploy/.env.bucket-ab-b TEN_USER_B@192.168.56.101:~/oldshop-bucket-demo/deploy/
```

Các password sinh bằng hex nên an toàn khi đặt trong URI của mẫu Compose; password tự nhập có ký tự đặc biệt phải URL-encode khi dùng trong DSN. Các file `.env.*` là bí mật local, không commit hoặc trình chiếu nội dung.

### 4.2. Trên B: lưu `deploy/docker-compose.bucket-ab-b.yml`

Trên B làm việc tại `~/oldshop-bucket-demo`, lưu YAML sau vào đúng đường dẫn:

```yaml
name: oldshop-bucket-ab-b
services:
  site-b:
    image: postgres:16-alpine
    command: [postgres, -c, shared_buffers=32MB, -c, max_connections=40, -c, timezone=UTC]
    environment:
      POSTGRES_USER: bucket_admin
      POSTGRES_PASSWORD: ${BUCKET_SITE_B_PASSWORD:?Missing B password}
      POSTGRES_DB: oldshop_2
      POSTGRES_INITDB_ARGS: --auth-host=scram-sha-256
    ports: ["${BUCKET_B_BIND_IP:?Set private IP}:${BUCKET_SITE_B_PORT:-57632}:5432"]
    volumes: [bucket_b:/var/lib/postgresql/data]
    healthcheck:
      test: [CMD-SHELL, 'pg_isready -U bucket_admin -d "$$POSTGRES_DB"']
      interval: 3s
      timeout: 3s
      retries: 30
    mem_limit: 256m
    restart: unless-stopped
volumes:
  bucket_b:
```

### 4.3. Trên A: lưu `deploy/docker-compose.bucket-ab-a.yml`

```yaml
name: oldshop-bucket-ab-a
x-pg: &pg
  image: postgres:16-alpine
  command: [postgres, -c, shared_buffers=32MB, -c, max_connections=40, -c, timezone=UTC]
  environment: &pg-env
    POSTGRES_USER: bucket_admin
    POSTGRES_PASSWORD: ${BUCKET_PG_PASSWORD:?Missing A password}
  healthcheck:
    test: [CMD-SHELL, 'pg_isready -U bucket_admin -d "$$POSTGRES_DB"']
    interval: 3s
    timeout: 3s
    retries: 30
  mem_limit: 256m
  restart: unless-stopped
services:
  core:
    <<: *pg
    environment:
      <<: *pg-env
      POSTGRES_DB: oldshop_core
    ports: ["127.0.0.1:57630:5432"]
    volumes: [bucket_core:/var/lib/postgresql/data]
  site-a:
    <<: *pg
    environment:
      <<: *pg-env
      POSTGRES_DB: oldshop_1
    ports: ["127.0.0.1:57631:5432"]
    volumes: [bucket_a:/var/lib/postgresql/data]
  site-c:
    <<: *pg
    profiles: [expansion]
    environment:
      <<: *pg-env
      POSTGRES_DB: oldshop_3
    ports: ["127.0.0.1:57633:5432"]
    volumes: [bucket_c:/var/lib/postgresql/data]
  mongo:
    image: mongo:8.0.32
    command: [mongod, --wiredTigerCacheSizeGB, "0.25", --bind_ip_all]
    environment:
      MONGO_INITDB_ROOT_USERNAME: bucket_admin
      MONGO_INITDB_ROOT_PASSWORD: ${BUCKET_MONGO_PASSWORD:?Missing Mongo password}
    ports: ["127.0.0.1:57617:27017"]
    volumes: [bucket_mongo:/data/db]
    healthcheck:
      test: [CMD, mongosh, --quiet, --eval, 'quit(db.adminCommand({ping:1}).ok === 1 ? 0 : 1)']
      interval: 5s
      timeout: 5s
      retries: 30
    mem_limit: 512m
    restart: unless-stopped
  neo4j:
    image: neo4j:2026.10.2
    environment:
      NEO4J_AUTH: neo4j/${BUCKET_GRAPH_PASSWORD:?Missing graph password}
      NEO4J_server_memory_heap_initial__size: 256m
      NEO4J_server_memory_heap_max__size: 256m
      NEO4J_server_memory_pagecache_size: 128m
    ports: ["127.0.0.1:57687:7687", "127.0.0.1:57474:7474"]
    volumes: [bucket_graph:/data]
    healthcheck:
      test: [CMD-SHELL, 'wget -q --spider http://localhost:7474 || exit 1']
      interval: 5s
      timeout: 3s
      retries: 40
      start_period: 30s
    mem_limit: 768m
    restart: unless-stopped
  backend:
    image: oldshop-bucket-backend:local
    build: {context: .., dockerfile: backend/Dockerfile}
    profiles: [app]
    environment: &app-env
      DATABASE_URL: postgresql://bucket_admin:${BUCKET_PG_PASSWORD}@core:5432/oldshop_core
      BUCKET_SITE_URLS: '{"A":"postgresql://bucket_admin:${BUCKET_PG_PASSWORD}@site-a:5432/oldshop_1","B":"postgresql://bucket_admin:${BUCKET_SITE_B_PASSWORD}@${BUCKET_B_HOST}:${BUCKET_SITE_B_PORT:-57632}/oldshop_2","C":"postgresql://bucket_admin:${BUCKET_PG_PASSWORD}@site-c:5432/oldshop_3"}'
      BUCKET_MODE: "true"
      BUCKET_DATASET: ${BUCKET_DATASET:-demo-v2}
      GRAPH_ENABLED: "true"
      GRAPH_GENERATION: ${GRAPH_GENERATION:-1}
      SKIP_DB_INIT: "true"
      MONGO_URI: mongodb://bucket_admin:${BUCKET_MONGO_PASSWORD}@mongo:27017/?authSource=admin
      MONGO_DB: oldshop_buckets
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_DATABASE: neo4j
      NEO4J_PASSWORD: ${BUCKET_GRAPH_PASSWORD}
      SECRET_KEY: ${BUCKET_SECRET_KEY:?Missing signing key}
      DEBUG: "false"
      LOG_FORMAT: json
      WEB_CONCURRENCY: "1"
      STORAGE_BACKEND: local
      MEDIA_DIR: /data/media
      DATABASE_SRC: /opt/database
    ports: ["127.0.0.1:57680:8000"]
    volumes: [bucket_media:/data/media]
    depends_on:
      core: {condition: service_healthy}
      site-a: {condition: service_healthy}
      mongo: {condition: service_healthy}
      neo4j: {condition: service_healthy}
    mem_limit: 512m
    restart: unless-stopped
  worker:
    image: oldshop-bucket-backend:local
    profiles: [app]
    environment: *app-env
    entrypoint: [python, -m, scripts.graph, worker]
    healthcheck: {disable: true}
    volumes: [bucket_media:/data/media]
    mem_limit: 256m
    restart: unless-stopped
  frontend:
    image: oldshop-bucket-frontend:local
    build: {context: ../frontend, dockerfile: Dockerfile}
    profiles: [app]
    ports: ["127.0.0.1:57600:8080"]
    depends_on: [backend]
    mem_limit: 256m
    restart: unless-stopped
  tools:
    image: oldshop-bucket-tools:local
    build: {context: .., dockerfile: backend/Dockerfile.bucket-tests}
    profiles: [tools]
    environment:
      <<: *app-env
      DATABASE_SRC: /workspace/database
      PYTHONPATH: /workspace/backend
    healthcheck: {disable: true}
    working_dir: /workspace/backend
    volumes: ["..:/workspace:ro", "bucket_media:/data/media"]
    mem_limit: 512m
volumes:
  bucket_core:
  bucket_a:
  bucket_c:
  bucket_mongo:
  bucket_graph:
  bucket_media:
```

Chú ý A **không khai báo service `site-b` local**. DSN B xuất hiện đồng nhất ở backend, worker, tools qua anchor `app-env`. Media nằm trên A nên B không cần chạy server file. Tài khoản DB quản trị trong mẫu phục vụ lab; production cần tách tài khoản bootstrap/migration khỏi runtime.

## 5. Khởi động hai máy đúng thứ tự

### 5.1. B khởi động trước

**Terminal B**, tại `~/oldshop-bucket-demo`:

```bash
chmod 600 deploy/.env.bucket-ab-b
dcb() {
  docker compose -p oldshop-bucket-ab-b --env-file deploy/.env.bucket-ab-b \
    -f deploy/docker-compose.bucket-ab-b.yml "$@"
}
dcb config --quiet
dcb up -d --wait --wait-timeout 180 site-b
dcb ps
dcb exec site-b psql -U bucket_admin -d oldshop_2 -c 'SELECT current_database(),version();'
```

B lúc này mới có database trống; không chạy `init.sql`, seed cũ hoặc tạo mapping riêng trên B.

### 5.2. A khởi động hạ tầng và kiểm kết nối thực từ container

**Terminal A**, tại root source:

```bash
dca() {
  docker compose -p oldshop-bucket-ab-a --env-file deploy/.env.bucket-ab-a \
    -f deploy/docker-compose.bucket-ab-a.yml "$@"
}
demo() { dca "$@"; }
dca config --quiet
dca up -d --wait --wait-timeout 240 core site-a mongo neo4j
dca build backend
dca --profile tools build tools
dca --profile tools up -d tools
dca exec -T tools python - <<'PY'
import json, psycopg2
from app.core.config import settings
url = json.loads(settings.BUCKET_SITE_URLS)['B']
with psycopg2.connect(url, connect_timeout=5) as connection:
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(),inet_server_addr(),inet_server_port()')
        print('Kết nối site B:', cursor.fetchone())
PY
```

Kết quả phải là database `oldshop_2`. Port trả từ SQL thường là **5432 trong container B**, dù A kết nối host B ở **57632**. Không in toàn bộ DSN hoặc `docker compose config` ra màn hình trình chiếu; dùng `config --quiet` để kiểm cấu hình.

### 5.3. Bootstrap, seed và mở ứng dụng

**Chỉ chạy từ A**:

```bash
dca exec tools python -m scripts.bucket_setup --sites A B
dca exec tools python -m scripts.graph init
dca exec tools python -m scripts.seed plan --dataset demo-v2 --output /tmp/demo-plan-01.json
dca exec tools python -m scripts.seed apply --plan /tmp/demo-plan-01.json
dca exec tools python -m scripts.verify_seed --include-graph
dca build frontend
dca --profile app up -d backend worker frontend
curl -fsS http://localhost:57680/health/ready
curl -fsS 'http://localhost:57600/api/v1/images/search?q=alphaonly'
```

Không tiếp tục nếu apply/verify thất bại. Run ID dùng cho resume/manifest là ID **apply thực tế trả về**, không nhất thiết UUID dự kiến của plan mới khi dataset đã có run cũ.

Kết quả fresh demo: **40 user, 1.000 product, 2.000 image, 120 order, 240 order detail, 56 review**. Core không chứa 1.000 hàng ở bảng `product`; catalogue thực nằm trên A/B. Dataset `contract-small` và `benchmark-v2 --scale N` phải được chọn bằng `BUCKET_DATASET` tương ứng **trước setup một môi trường trống khác**, không đổi profile/scale âm thầm trong core đã seed.

### 5.4. Địa chỉ và công cụ manual

| Công cụ | Kết nối trong cấu hình A/B |
|---|---|
| Frontend | `http://localhost:57600` trên A |
| Swagger | `http://localhost:57680/api/docs` trên A |
| pgAdmin/DBeaver core | A `127.0.0.1:57630`, DB `oldshop_core`, user `bucket_admin`, password A |
| pgAdmin/DBeaver site A | A `127.0.0.1:57631`, DB `oldshop_1`, user `bucket_admin`, password A |
| pgAdmin/DBeaver site B | B IP `192.168.56.101:57632`, DB `oldshop_2`, user `bucket_admin`, password B |
| MongoDB Compass | A `127.0.0.1:57617`, user `bucket_admin`, auth database `admin`, DB làm việc `oldshop_buckets` |
| Neo4j Browser | A `http://localhost:57474`, connection `bolt://localhost:57687`, user `neo4j`, password graph |

GUI chỉ là client; chọn đúng host/port/database trước khi query. Nếu trình duyệt ở máy khác, có thể SSH tunnel thay vì mở toàn bộ port DB:

```bash
# Chạy trên máy trình diễn, kết nối vào A; không cần tunnel cổng nào không dùng.
ssh -N -L 57600:127.0.0.1:57600 -L 57680:127.0.0.1:57680 \
  -L 57474:127.0.0.1:57474 -L 57687:127.0.0.1:57687 \
  TEN_USER_A@IP_A
```

Giữ terminal tunnel mở rồi truy cập localhost trên máy trình diễn. Nếu đổi publish frontend sang IP LAN A, chỉ expose giao diện cần dùng; frontend production gọi `/api/v1` cùng origin qua Nginx.

## 6. Seed, hợp đồng phân bổ và migration schema

Từ đây `demo` là alias tới **A của đúng môi trường đã chọn**: `dca` hoặc `bucket_local`. Không đổi alias giữa chừng khi đã ghi nhận ID/backup.

### 6.1. Trình tự và cách chạy lại an toàn

```text
Schema trống → bucket_setup → graph init → seed plan → seed apply
            → verify + manifest → mở backend/worker/frontend → thao tác nghiệp vụ
```

- `bucket_setup`: nạp schema nền không chứa seed SQL cũ, schema bucket và extension; tạo 256 mapping/lease; gắn identity của Mongo với core.
- Seeder sinh tập logical có kiểm tra nghiệp vụ, cấp global ID qua allocator, nạp product vào owner site, order/review tại core, sao media, chiếu Mongo rồi Neo4j.
- `seed_entities` giữ mapping logical ID → global ID. Logical seller `3` không có nghĩa user ID thực tế là `3`; không lấy chẵn/lẻ global ID để suy site.
- `seed_runs` lưu phase/hash/plan; `seed_manifest` lưu ID/count/checksum media/expected query và verification.
- Cùng dataset chạy lại không nhân đôi. SQL đã bị mua/bán/sửa có thể báo drift; metadata do người dùng sửa được bảo vệ. Không dùng reseed như nút “undo” giao dịch.

```bash
# Thay chuỗi này bằng run_id thực tế từ apply hoặc bảng seed_runs.
DEMO_RUN_ID='RUN_ID_TU_APPLY'
demo exec tools python -m scripts.seed manifest --run-id "$DEMO_RUN_ID"
demo exec tools python -m scripts.seed resume --run-id "$DEMO_RUN_ID"
demo exec tools python -m scripts.verify_seed --run-id "$DEMO_RUN_ID" --include-graph
```

Plan `/tmp` mất khi recreate tools nhưng plan đã apply nằm trong core. Khi target fingerprint, mapping, extension hoặc graph generation thay đổi, tạo **file plan mới** (`/tmp/demo-plan-02.json`) rồi apply; không chỉnh hash/fingerprint trong plan để vượt bảo vệ. Kiểm thử replay ngay sau seed sạch, trước khi thực hiện demo mua/bán.

### 6.2. Chứng minh dữ liệu đã phân tán

Mở SQL core:

```sql
SELECT kind,site_id,dataset_id,instance_id,contract_digest FROM bucket_installation;
SELECT owner_site_id,count(*) AS buckets
FROM bucket_assignment GROUP BY owner_site_id ORDER BY owner_site_id;
SELECT a.owner_site_id,count(*) AS products
FROM catalogue_directory d JOIN bucket_assignment a USING(bucket_id)
WHERE d.lifecycle='active' GROUP BY a.owner_site_id ORDER BY a.owner_site_id;
SELECT entity,count(*) FROM seed_entities GROUP BY entity ORDER BY entity;
SELECT run_id,dataset_id,state,phase,error_code FROM seed_runs;
SELECT count(*) AS local_core_products FROM product;
SELECT logical_key,global_id FROM seed_entities
WHERE entity='user' AND logical_key IN ('3','4') ORDER BY logical_key;
```

Core `product` rỗng với seed bucket mới là đúng. Directory là mục lục định tuyến, không phải bản sao đầy đủ của product. Với mỗi site, chỉ đếm các bucket đang active vì nguồn frozen có thể giữ shadow sau move:

```sql
SELECT i.site_id,l.state,count(DISTINCT p.product_id) AS products
FROM bucket_installation i CROSS JOIN product p
JOIN bucket_lease l ON l.bucket_id=p.bucket_id
GROUP BY i.site_id,l.state ORDER BY i.site_id,l.state;
SELECT p.product_id,p.seller_id,p.bucket_id,p.quantity,p.catalogue_revision
FROM product p JOIN bucket_lease l USING(bucket_id)
WHERE l.state='active' ORDER BY p.product_id LIMIT 10;
```

Ban đầu có 128 bucket mỗi bên, nhưng số product không nhất thiết 50/50. Kiểm đủ/rời nhau/tái tạo bằng `scripts.verify_seed`, không bằng cộng mọi hàng kể cả frozen shadow.

### 6.3. Migration schema khác với seed và migration dữ liệu

| Việc | Công cụ đúng | Không dùng thay thế |
|---|---|---|
| Tạo/cập nhật schema bucket trong phạm vi runner hỗ trợ | `scripts.bucket_setup --sites A B` | Không chạy `database/init.sql` có seed cũ |
| Kiểm history/identity bucket | `bucket_installation`, `bucket_extension` | Không xóa marker/checksum để bootstrap lại |
| Schema graph/index | `scripts.graph init` | Không xóa graph để “chạy migration” |
| Mongo validator/index | `scripts.init_mongo` | Không tự ghi đè index đang conflict |
| Schema legacy | `scripts.migrate` trên DB legacy phù hợp | Không dùng làm runner bucket |
| Chuyển dữ liệu legacy → target bucket mới | `scripts.migrate_catalogue_to_buckets` | Không apply vào target đã seed demo |

`bucket_setup` hiện kiểm digest schema nền và danh sách extension trong source. Nó không phải bộ tự động chuyển mọi schema tùy ý: nếu báo `Installation/schema differs` hoặc checksum đổi, dừng và dùng bản source khớp hoặc viết migration phiên bản mới có review. Không sửa file SQL đã áp hoặc tự xóa lịch sử.

## 7. Demo nghiệp vụ qua frontend và Swagger

### 7.1. Tài khoản và chuẩn bị

Mật khẩu chung seed mới: **`BucketDemo123!`**. Mở ba browser profile/cửa sổ riêng để tránh token tài khoản bị ghi đè:

| Vai trò | Email | Trang chính |
|---|---|---|
| Admin | `bucket1@example.com` | `/admin/dashboard`, `/admin/category-manage`, `/admin/voucher-manage` |
| Moderator | `bucket2@example.com` | `/moderator/product-manage`, `/moderator/review-manage` |
| Seller đồng thời có thể mua | `bucket3@example.com` | `/seller/product-manage`, `/seller/order-manage` |
| Buyer | `bucket4@example.com` | `/shop`, `/customer/cart`, `/customer/my-orders` |

Đây là tài khoản demo, không dùng mật khẩu này cho vận hành thực. Trong Swagger: `POST /api/v1/auth/login`, nhập email vào trường **username** và password; dùng nút Authorize với tài khoản cần thử. Xem response để lấy ID thật, không đoán ID theo email.

### 7.2. Một vòng bán hàng hoàn chỉnh

1. Seller vào `/seller/product-manage`, tạo sản phẩm tên **“Demo hợp nhất dữ liệu”**, giá `100000`, quantity `7`, category đang active, một ảnh thật từ máy. Ghi lại `product_id` và `image_id` trả về.
2. Sản phẩm mới ở trạng thái chờ duyệt. Buyer chưa xem được public; seller/moderator có thể xem theo quyền. Kiểm directory tại core rồi product tại đúng owner site.
3. Chờ worker đồng bộ hoặc chạy `demo exec tools python -m scripts.graph incremental`. Seller mở chức năng **Mô tả từng ảnh sản phẩm**, điền caption/description dựa trên ảnh thực; thêm từ kiểm thử riêng `demometaanh2026`.
4. Moderator duyệt sản phẩm. Trong Swagger có thể dùng `PATCH /api/v1/moderator/products/{product_id}/status`, body `{"status":1}`; từ chối dùng status `2` kèm `reason`.
5. Buyer khác seller tìm sản phẩm, xem chi tiết/ảnh và thêm quantity `2` vào cart. Tồn khả dụng giảm từ `7` xuống `5` vì cart đã giữ hàng.
6. Chọn đúng contact của buyer; nếu chưa có thì thêm ở profile. Checkout **COD**. Order/detail/payment nằm tại core, reservation tại site; checkout không trừ thêm hai đơn vị đã giữ trong cart.
7. Trong seller order manage, tiến phần đơn của seller qua `0 → 1 → 2 → 3`. Với đơn nhiều seller, mỗi người chỉ đổi fulfillment của mình; parent chỉ tiến khi các phần tương ứng đã tiến.
8. Buyer xem đơn đã giao và gửi review 1–5 sao. Kiểm `is_verified_purchase`; thử mua/review sản phẩm của chính seller để thấy quy tắc ngăn self-buy/self-review.
9. Làm **đơn khác còn pending/confirmed** để demo hủy. Buyer/admin hủy: hàng được hoàn đúng một lần. Không dùng đơn đã giao để minh họa hủy thành công.

Trạng thái order: `0` pending, `1` confirmed, `2` shipping, `3` delivered, `4` cancelled. Product dùng `0` pending, `1` approved, `2` rejected, `3` trạng thái seller rút khỏi luồng bán/hết hàng tùy dữ liệu; **không dùng chung enum order và product**.

Nếu muốn trình bày request rõ trong Swagger:

```json
{
  "contact_id": 100003,
  "payment_method_id": 1,
  "shipping_fee": 30000,
  "order_items": [{"product_id": 101000, "quantity": 2}]
}
```

Hai ID trên chỉ minh họa kiểu dữ liệu: thay bằng contact của buyer đang đăng nhập và product thực. Gửi cùng `Idempotency-Key` UUID khi retry cùng body. Đổi body phải dùng thao tác/key mới. Không lấy contact của seller hoặc của user khác để checkout.

### 7.3. Các chức năng bổ sung cần demo

| Chức năng | Thao tác | Bằng chứng cần thấy |
|---|---|---|
| Category/tree | Admin tạo category/parent, sửa/ẩn và khôi phục | Core có parent_id; public listing kiểm active/deleted |
| Profile/avatar/contact | User sửa profile, upload avatar, thêm và chọn contact mặc định | Identity/profile tách bảng; ảnh avatar là file reference |
| Voucher | Admin tạo code mới trên UI, đặt hạn hiệu lực, min amount và usage; buyer kiểm/áp vào đơn mới | Tiền giảm/tổng/usage đúng ở core; baseline bucket seed không có sẵn mọi voucher scenario |
| Moderation | Seller gửi chờ duyệt, mod duyệt/từ chối có lý do | Trạng thái site và projection thay đổi; sản phẩm ẩn không xuất hiện public |
| Report/violation | Buyer report product bằng rating `0`, mod xử lý trong review manage | Report khác review sao; log xử lý và trạng thái seller/product; không report hàng loạt seed seller |
| Dashboard | Seller dashboard, admin dashboard | Count/revenue từ nguồn core/catalogue đúng, đơn delivered tạo tín hiệu doanh thu |
| Contact/feedback | Gửi form Contact, admin xem feedback | Lưu `system_feedback`; relay email/Apps Script cần cấu hình ngoài nếu muốn gửi thật |
| PayPal | Demo bằng `tests/buckets/test_paypal_recovery.py`; sandbox thật chỉ khi đã cấu hình | Retry/đối soát buyer, provider ID, amount/currency; không coi việc có nút là bằng chứng đã thanh toán |
| Video | Upload MP4 thật ở form seller, hoặc dùng link Drive được hỗ trợ | Video phát được; URL trong SQL/Mongo; HTTP Range `206` với MP4 upload |

MP4 mặc định tối đa 50 MiB, H.264/AAC hoặc không audio; backend dùng ffprobe. Không chọn cả file video và `video_url`. Seed bucket hiện không tự gắn video demo cho mọi product; upload qua seller để kiểm chứng, theo [hướng dẫn video](HUONG_DAN_VIDEO_SAN_PHAM.md). Xóa mềm product không tự xóa file dùng chung. OTP/mail/relay/fraud model không phải thành phần Neo4j và cần cấu hình/artifact riêng nếu demo tích hợp thật.

## 8. Hợp nhất dữ liệu có cấu trúc, bán cấu trúc và phi cấu trúc

### 8.1. Theo dấu một product qua bốn kho

Ghi `DEMO_PID` của sản phẩm vừa tạo; ví dụ sau dùng `101000`, phải thay bằng ID thật.

**Core**, định tuyến và snapshot:

```sql
SELECT d.product_id,d.seller_id,d.bucket_id,a.owner_site_id,a.ownership_epoch
FROM catalogue_directory d JOIN bucket_assignment a USING(bucket_id)
WHERE d.product_id=101000;
SELECT order_id,product_id,quantity,price_at_purchase,
       product_snapshot->>'title' AS title_snapshot,
       product_snapshot->>'seller_id' AS seller_snapshot
FROM order_detail WHERE product_id=101000;
```

**Owner site**, structured data và image membership:

```sql
SELECT product_id,seller_id,title,price,quantity,status,bucket_id,catalogue_revision
FROM product WHERE product_id=101000;
SELECT image_id,product_id,image_url,display_order,is_primary
FROM product_image WHERE product_id=101000;
SELECT reservation_id,buyer_id,quantity,state FROM stock_reservation WHERE product_id=101000;
```

**MongoDB Compass**, chọn `oldshop_buckets`, collection `product_details`:

```javascript
db.product_details.findOne({product_id:101000})
db.product_details.find({product_id:101000},
  {product_id:1,attributes:1,tags:1,images:1,image_metadata:1,metadata_revision:1,graph_pending_revision:1})
```

**Binary media**, từ URL của chính ảnh đó:

```bash
# Thay path bằng image_url thực tế từ API/SQL, không dùng nguyên chuỗi minh họa.
curl -I 'http://localhost:57600/media/products/TEN_FILE_THAT.jpg'
# File nằm trong MEDIA_DIR của service A ở cấu hình local media:
demo exec tools find /data/media/products -maxdepth 2 -type f | head -10
```

**Neo4j**, đặt namespace theo generation hiện hành (mục 9):

```cypher
CYPHER 5
MATCH (p:Product {product_id:101000})-[:HAS_IMAGE]->(i:Image)
WHERE p.namespace=$ns
RETURN p,i;
```

**API hợp nhất**: mở `GET /api/v1/products/101000`, so giá/quantity với SQL, attributes và caption với Mongo, URL tải được với media. Không có một SQL JOIN xuyên trực tiếp cả bốn kho; backend resolve nguồn, đọc projection rồi kiểm lại quyền/visibility. Neo4j không quyết định số lượng được bán.

### 8.2. Cấu trúc JSON/BSON và ownership

Hình dạng rút gọn của document (JSON trình bày; ngày thật trong Mongo là BSON Date):

```json
{
  "_id": "product:101000",
  "schema_version": 1,
  "product_id": 101000,
  "category_id": 1,
  "description": "Mô tả sản phẩm từ SQL",
  "attributes": {"brand": "DemoBrand", "ram_gb": 16},
  "tags": ["demo", "dien-tu"],
  "images": [{"image_id": 102000, "bucket": "product-images", "key": "products/ten-file.jpg", "is_primary": true, "display_order": 0}],
  "image_metadata": [{"image_id": 102000, "caption": "Chú thích ảnh đã kiểm tra", "description": "Từ kiểm thử demometaanh2026"}],
  "metadata_revision": 1,
  "graph_pending_revision": null,
  "metadata_seed_owner": null,
  "updated_at": "2026-11-17T00:00:00Z",
  "deleted": false
}
```

- SQL ETL/projection sở hữu `images`, `description` sản phẩm, category và publication/deleted state. Mongo sở hữu `attributes`, `tags`, `image_metadata`, revision/provenance.
- Không ghi `price`/`quantity` vào `attributes` rồi coi đó là giá/tồn chính. Không nhầm `description` product với `image_metadata[].description` của từng ảnh.
- API metadata kiểm owner và image_id thuộc product, giới hạn caption 255/description 4.000 ký tự; không sửa trực tiếp caption trên Neo4j.
- Mongo có validator strict/error theo Pydantic tại [documents.py](../backend/app/schemas/documents.py). JSON không đồng nghĩa “không schema”. `_id`, global ID và kiểu dữ liệu phải nhất quán.
- Binary ảnh/video là dữ liệu phi cấu trúc; caption/description/key là metadata bán cấu trúc; quan hệ/tồn kho/giao dịch trong SQL có cấu trúc. Bản chiếu graph là một mô hình quan hệ truy vấn bổ sung.

Để demo attributes linh hoạt, dùng Compass mongosh trên **product demo mới** (hiện chưa có UI chỉnh toàn bộ attributes):

```javascript
db.product_details.updateOne({product_id:101000},
  {$set:{"attributes.brand":"DemoBrand","attributes.ram_gb":16,tags:["demo","dien-tu"]}})
db.product_details.find({"attributes.ram_gb":16},{product_id:1,attributes:1})
```

Sau đó gọi `GET /api/v1/products?attributes={"brand":"DemoBrand"}` trong Swagger để tránh sai URL-encoding; API lọc ID từ Mongo rồi kiểm SQL. Chạy `demo exec tools python -m scripts.graph reconcile`, kiểm attributes/caption còn giữ nguyên. Với caption dùng UI/API, **không** dùng update Mongo thô vì sẽ bỏ qua quy trình pending/revision.

Kiểm validator bằng cách thử thêm một field ngoài schema trong Compass trên product demo: `{$set:{unknown_demo_field:1}}` phải bị validation từ chối. Không dùng `bypassDocumentValidation` để làm demo hợp đồng.

### 8.3. JSONB trong PostgreSQL khác Mongo document

```sql
SELECT operation_id,kind,state,payload->'body' AS request_body
FROM commerce_operation ORDER BY updated_at DESC LIMIT 5;
SELECT order_id,product_id,jsonb_typeof(product_snapshot),product_snapshot->>'title'
FROM order_detail LIMIT 5;
```

JSONB giữ intent/snapshot nghiệp vụ bên cạnh cột quan hệ; Mongo chứa metadata linh hoạt. `database/indexing/catalog.json` là **cấu hình index khai báo bằng JSON**, không phải dữ liệu hàng hóa và không phải PostgreSQL tự chạy DDL chỉ vì lưu một file JSON.

## 9. Demo Neo4j và tìm ảnh qua metadata

### 9.1. Namespace, schema và quan hệ

Mở core để lấy generation:

```sql
SELECT generation,state FROM graph_projection_state;
```

Neo4j Browser kết nối như mục 5.4. Chạy riêng lệnh `:param` và từng câu query trong Browser; không dán cả block nhiều câu vào một lần Execute nếu chưa bật chế độ nhiều statement. Với môi trường mới generation 1:

```cypher
:param ns => 'demo-v2:g1'
SHOW CONSTRAINTS;
SHOW INDEXES;
CYPHER 5
MATCH (p:Product)-[:HAS_IMAGE]->(i:Image)
WHERE p.namespace=$ns
RETURN p,i LIMIT 20;
```

Nếu core đã ở generation 2, đổi `$ns` thành `demo-v2:g2`. Không dùng namespace cũ để kết luận dữ liệu đang phục vụ. `Product.key`/`Image.key` chứa namespace + global ID, không chứa site; không dùng internal node ID làm product ID.

```cypher
CYPHER 5
MATCH (u:User)-[:SELLS]->(p:Product)-[:IN_CATEGORY]->(c:Category)
WHERE p.namespace=$ns RETURN u,p,c LIMIT 20;

CYPHER 5
MATCH (u:User)-[:PLACED]->(o:Order)-[:HAS_ITEM]->(l:OrderItem)-[:OF_PRODUCT]->(p:Product)
WHERE p.namespace=$ns AND o.status=3
RETURN u,o,l,p LIMIT 30;

CYPHER 5
MATCH (u:User)-[:WROTE]->(r:Review)-[:REVIEWS]->(p:Product)
WHERE p.namespace=$ns AND r.rating>0 AND r.deleted=false
RETURN u,r,p LIMIT 20;
```

Graph hiện chưa chiếu tên category đầy đủ hoặc mọi thông tin user; không tự suy tên bị thiếu là lỗi dữ liệu. Nó chủ ý tránh password, địa chỉ, ví và thông tin không cần cho truy vấn này.

### 9.2. Truy vấn full-text và API an toàn

```cypher
CYPHER 5
CALL db.index.fulltext.queryNodes('image_metadata_text','"alphaonly"')
YIELD node AS i,score
MATCH (p:Product)-[:HAS_IMAGE]->(i)
WHERE i.namespace=$ns AND i.deleted=false AND p.deleted=false AND p.visible=true
RETURN i.image_id,p.product_id,i.caption,i.description,score;
```

Sau seed sạch, chỉ có **một ảnh** khớp `alphaonly`; đây là từ ở description ảnh, không phải title product. Trong frontend vào Shop, chọn **Tìm từng ảnh theo chú thích và mô tả (theo từ khóa)**, tìm `alphaonly`, sau đó thử `anh tu lieu`, `ẢNH TƯ LIỆU` và từ không tồn tại.

```bash
curl -fsS 'http://localhost:57600/api/v1/images/search?q=alphaonly'
curl -fsS 'http://localhost:57600/api/v1/images/search?q=anh%20tu%20lieu&limit=5'
curl -fsS 'http://localhost:57600/api/v1/images/search?q=zznomatchzz'
```

API trả **ảnh khớp**, caption/description, product ID, `next_cursor`, `consistency=best_effort`. Cursor phải đi cùng query ban đầu; không giả định `total` chính xác hay pagination là snapshot. API còn kiểm SQL/Mongo mới nhất; raw Cypher trong Browser là công cụ quản trị, không thay thế kiểm quyền của API.

Full-text dùng AND token, có chuẩn hóa Unicode/hoa-thường/không dấu tiếng Việt. Nó không nhìn pixel, không hiểu đồng nghĩa bằng AI. `image_search` của endpoint `/products` là đường substring Mongo cũ trả **product**, khác `/images/search` trả **image**. Xem [Neo4j full-text](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/); dự án cố định Cypher 5 nên dùng procedure đã kiểm chứng.

### 9.3. Chứng minh update/clear/đồng bộ trễ

1. Tạm dừng worker: `demo stop worker`.
2. Seller sửa caption ảnh của **product demo mới** bằng UI. API phải báo lưu thành công/pending dù worker đang dừng.
3. Mongo: `metadata_revision` tăng, `graph_pending_revision` còn số revision; graph có thể chưa có từ mới. Giao diện product đọc được annotation mới từ Mongo.
4. `demo exec tools python -m scripts.graph incremental`; kiểm cờ pending về null và tìm `demometaanh2026` qua API.
5. Clear caption/description bằng UI hoặc gửi danh sách metadata với giá trị null; chạy incremental lại; từ cũ không còn trả ảnh đó.
6. Mod ẩn/từ chối product trong khi graph còn cũ: API tìm ảnh không được trả product không public. Xóa ảnh qua API cũng phải ngăn trả image đã mất membership.
7. Mở lại worker: `demo --profile app up -d worker`.

`PUT /products/{id}/images/metadata` là thay thế tập annotation, không phải patch một phần tử. Nếu dùng Swagger, giữ các phần tử khác muốn bảo toàn; body `[]` xóa toàn bộ annotation của product đó.

Sản phẩm liên quan: `GET /api/v1/products/{id}/related`. Cypher hiện lọc cùng category/khác seller, xếp hạng theo đơn đã giao có mua chung; API kiểm lại publication/stock. Không có bước train AI. Bản hiện tại cung cấp API related; không mặc định mọi trang frontend đều có widget recommendation riêng.

## 10. Demo thiết kế indexing

### 10.1. Bản đồ chỉ mục và JSON catalog

| Kho / query | Chỉ mục chính cần xem | Ý nghĩa |
|---|---|---|
| PostgreSQL product public/seller/order | B-tree composite + partial, buyer/date | Equality/filter trước, sort/tie-break sau; giảm index trên hàng không public |
| PostgreSQL `ILIKE` title/description | GIN `gin_trgm_ops` | Phục vụ tìm substring; khác full-text ảnh |
| Mongo product_id | Unique index | Không tạo nhiều document projection cùng product |
| Mongo category + brand | Compound `category_id`, `attributes.brand` | Query cố định theo category/brand |
| Mongo attributes linh hoạt | Wildcard `attributes.$**` | Các field thay đổi; không thay thế mọi targeted index |
| Mongo ảnh hiện hành | Partial/multikey `images.key`, `deleted:false` | Tìm reference trong mảng, không bảo đảm image key là unique |
| Mongo text / TTL | `description/tags` text; log `created_at` TTL | Text sản phẩm khác image metadata; TTL cho log Mongo, không xóa order SQL |
| Neo4j key / caption | Unique key constraints, `image_metadata_text` full-text | Seek node định danh; tìm nội dung annotation ảnh |

Mở [catalog.json](../database/indexing/catalog.json), [schema của catalog](../database/indexing/catalog.schema.json) và [migration 008](../database/04_migrations/008_fragmentation_seller_index.sql). Ví dụ: JSON mô tả index seller/date/ID được compiler/runner chuyển thành DDL, không nhận SQL tùy ý từ frontend.

```bash
demo exec tools python -m scripts.indexes validate
demo exec tools python -m scripts.indexes verify --engine mongodb
```

Không áp `scripts.indexes apply` bừa vào toàn bộ bucket stack: runner PostgreSQL legacy dùng history khác. Với bucket, DDL nền do bootstrap/extension quản lý; kiểm đúng scope và thêm migration bucket khi cần. Kiểm catalog PostgreSQL trên cả ba DB bằng CLI chỉ đọc:

```bash
demo exec -T tools python - <<'PY'
import json, os
from app.core.config import settings
from app.services.index_config import DATABASE_DIR, load_catalog
from scripts.plan_scoped_indexes import plan_scopes
urls=json.loads(settings.BUCKET_SITE_URLS)
os.environ['FRAGMENT_COMMERCE_DSN']=settings.DATABASE_URL.replace('postgresql+psycopg2://','postgresql://')
os.environ['FRAGMENT_SITE_A_DSN']=urls['A']
os.environ['FRAGMENT_SITE_B_DSN']=urls['B']
scopes=json.loads((DATABASE_DIR/'indexing/scopes.json').read_text())['postgresql']
print(json.dumps(plan_scopes(load_catalog(),scopes,verify=True),indent=2))
PY
```

Report không in DSN. Catalog chung không liệt kê mọi index nội bộ bucket (`app_delivery_pending`, directory, ledger, lease); xem thêm `pg_indexes` thay vì coi mọi index ngoài catalog là lỗi.

### 10.2. PostgreSQL EXPLAIN đúng site

Trên **owner site có product**, không đo bảng `core.product` rỗng. Chọn seller thực từ bảng `product`, thay ID ví dụ:

```sql
SELECT indexname,indexdef FROM pg_indexes WHERE tablename='product' ORDER BY indexname;
EXPLAIN (ANALYZE,BUFFERS)
SELECT product_id,title,created_at FROM product
WHERE seller_id=100002 AND status=1 AND is_deleted=false
ORDER BY created_at DESC,product_id ASC LIMIT 20;
EXPLAIN (ANALYZE,BUFFERS)
SELECT product_id,title FROM product
WHERE status=1 AND is_deleted=false AND title ILIKE '%mẫu%';
```

Đọc `Index Scan`/`Bitmap Index Scan`, `Seq Scan`, số row, Buffers và Execution Time. Bảng nhỏ có thể chọn Seq Scan hợp lý. Predicate partial phải phù hợp query; index không tự làm mọi query nhanh hơn.

Minh họa kế hoạch khi hạn chế index, không drop index thật:

```sql
BEGIN;
SET LOCAL enable_indexscan=off;
SET LOCAL enable_indexonlyscan=off;
SET LOCAL enable_bitmapscan=off;
EXPLAIN (ANALYZE,BUFFERS)
SELECT product_id FROM product WHERE seller_id=100002 AND status=1 AND is_deleted=false
ORDER BY created_at DESC,product_id ASC LIMIT 20;
ROLLBACK;
```

Đây là so kế hoạch trong session, không phải benchmark chứng minh SLA. Không tắt index toàn server. Với benchmark thực dùng dataset/version riêng, warm/cold cache rõ ràng, nhiều mẫu p50/p95 và cả chi phí ghi.

### 10.3. MongoDB explain và Neo4j PROFILE

Trong Compass mongosh, sau khi đã tạo attributes cho product demo ở mục 8:

```javascript
db.product_details.getIndexes()
db.product_details.find({category_id:1,"attributes.brand":"DemoBrand"}).explain("executionStats")
db.product_details.find({"attributes.ram_gb":16}).explain("executionStats")
db.product_details.find({category_id:1,"attributes.brand":"DemoBrand"})
  .hint("category_id_1_attributes.brand_1").explain("executionStats")
db.product_details.find({category_id:1,"attributes.brand":"DemoBrand"})
  .hint({$natural:1}).explain("executionStats")
```

Đọc `IXSCAN/COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`; dùng category thật của product. Hai `hint` là minh họa cưỡng chế plan, không chứng minh optimizer luôn tự chọn index đó. Wildcard có trade-off và không phục vụ `$text` ([MongoDB wildcard indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/)).

Trong Neo4j Browser, lấy `key` thật của node rồi:

```cypher
CYPHER 5
PROFILE MATCH (p:Product {key:'demo-v2:g1:product:100004'}) RETURN p;
SHOW FULLTEXT INDEXES;
```

Xem seek dựa trên constraint và full-text index trạng thái ONLINE. Đổi key/generation đúng môi trường. Không trộn PostgreSQL GIN, Mongo text/wildcard và Neo4j full-text thành một loại index duy nhất.

## 11. Demo cơ sở dữ liệu phân tán và mở rộng

### 11.1. Ba kiểu chia dữ liệu cần phân biệt

1. **Phân mảnh ngang qua server:** product của seller được hash vào một trong 256 bucket, mapping quyết định A/B. Đây là nội dung demo hai máy.
2. **Partition nội bộ PostgreSQL:** order hash 4 partition, system_log range theo tháng. Các partition có thể ở cùng instance, không tự trở thành server B.
3. **Tách dọc user:** user_core, user_profile, user_secret, user_wallet nối theo user_id; không có nghĩa mỗi bảng nằm trên một máy riêng.

Core SQL để quan sát partition/tách dọc, không hiển thị password/hash:

```sql
SELECT pg_get_partkeydef('public."order"'::regclass);
SELECT tableoid::regclass AS partition_name,count(*) FROM "order" GROUP BY tableoid;
EXPLAIN SELECT order_id,buyer_id FROM "order" WHERE order_id=100000;
SELECT inhparent::regclass AS parent,inhrelid::regclass AS child
FROM pg_inherits ORDER BY inhparent::regclass::text,inhrelid::regclass::text;
SELECT c.user_id,c.username,p.full_name
FROM user_core c JOIN user_profile p USING(user_id) ORDER BY c.user_id LIMIT 5;
```

Các schema nền được tạo ở site cũng có thể chứa bảng commerce rỗng; đó không phải order được phân tán sang site. Dữ liệu commerce chính của bucket mode vẫn tại core.

### 11.2. Chứng minh routing không dựa trên chẵn/lẻ

```bash
demo exec -T tools python - <<'PY'
from app.buckets.db import transaction,rows
from app.services.allocation import bucket_for_seller
print('Test vectors:',{x:bucket_for_seller(x) for x in (3,8,12,101,202)})
with transaction() as core:
    print(rows(core,"SELECT d.product_id,d.seller_id,d.bucket_id,a.owner_site_id,a.ownership_epoch "
                    "FROM catalogue_directory d JOIN bucket_assignment a USING(bucket_id) "
                    "ORDER BY d.product_id LIMIT 12"))
PY
```

Vectors cố định: `3→197`, `8→94`, `12→2`, `101→37`, `202→75`. Hash dùng **seller ID thật**, prefix `oldshop:seller:v1:`, SHA256, 8 byte đầu unsigned big endian `%256`. Thêm server không đổi modulus/hash; chỉ chuyển mapping bucket. Seller lớn vẫn có thể tạo lệch tải vì một seller ở một bucket.

### 11.3. Chuyển bucket A ↔ B, giữ ID/API/metadata

Làm sau khi có backup. Chọn một product seed ổn định bằng logical key; dưới đây dùng hai site đang chạy, không cần máy C:

```bash
DEMO_PID=$(demo exec -T core psql -U bucket_admin -d oldshop_core -Atc \
  "SELECT global_id FROM seed_entities WHERE entity='product' AND logical_key='5'")
DEMO_BUCKET=$(demo exec -T core psql -U bucket_admin -d oldshop_core -Atc \
  "SELECT bucket_id FROM catalogue_directory WHERE product_id=$DEMO_PID")
DEMO_SOURCE=$(demo exec -T core psql -U bucket_admin -d oldshop_core -Atc \
  "SELECT owner_site_id FROM bucket_assignment WHERE bucket_id=$DEMO_BUCKET")
if [ "$DEMO_SOURCE" = A ]; then DEMO_TARGET=B; else DEMO_TARGET=A; fi
printf 'product=%s bucket=%s source=%s target=%s\n' "$DEMO_PID" "$DEMO_BUCKET" "$DEMO_SOURCE" "$DEMO_TARGET"
curl -fsS "http://localhost:57600/api/v1/products/$DEMO_PID"
demo exec tools python -m scripts.move_bucket plan --bucket "$DEMO_BUCKET" \
  --to-site "$DEMO_TARGET" --output /tmp/move-demo-01.json
demo exec tools python -m scripts.move_bucket apply --plan /tmp/move-demo-01.json
curl -fsS "http://localhost:57600/api/v1/products/$DEMO_PID"
curl -fsS 'http://localhost:57600/api/v1/images/search?q=alphaonly'
demo exec tools python -m scripts.verify_seed --include-graph
```

Tên file plan phải mới nếu đã có. Các biến SQL ở đây lấy số ID từ database do lab kiểm soát, không nhập chuỗi tùy ý vào câu SQL.

Quan sát core `bucket_assignment` và `bucket_moves`; tại nguồn lease phải frozen, tại đích active, epoch tăng. Snapshot copy cả product/image/reservation/stock-operation ledger; nguồn được giữ để phục hồi. Raw `SELECT count(*) FROM product` ở cả hai nơi có thể tăng vì shadow, nhưng chỉ owner active phục vụ.

**Rollback phải là move ngược mới**, sau khi tạo một cập nhật hợp lệ qua API ở đích để chứng minh ghi mới được giữ:

```bash
demo exec tools python -m scripts.move_bucket plan --bucket "$DEMO_BUCKET" \
  --to-site "$DEMO_SOURCE" --output /tmp/move-demo-back-01.json
demo exec tools python -m scripts.move_bucket apply --plan /tmp/move-demo-back-01.json
```

Không tự `UPDATE bucket_assignment` để đổi owner/epoch. Không bật lại lease nguồn thủ công. Nếu process bị ngắt, dùng operation ID từ plan/log:

```bash
DEMO_MOVE_ID='OPERATION_ID_TU_PLAN'
demo exec tools python -m scripts.move_bucket resume --operation-id "$DEMO_MOVE_ID"
```

Để thấy DB guard, trên **nguồn frozen sau move**, thử trong transaction `UPDATE product SET quantity=quantity WHERE product_id=...`: phải bị từ chối `bucket_fenced`; chạy `ROLLBACK`. Luồng ứng dụng bình thường cung cấp epoch đúng qua repository. Không bypass bằng `oldshop.maintenance` trong demo mua bán.

### 11.4. Mất kết nối máy B

Trước tiên chọn một product public ở A và một ở B, ghi ID từ directory/API. Thực hiện sau khi đã rollback move về trạng thái mong muốn:

1. **B:** `dcb stop site-b` (một máy: `bucket_local stop site-b`).
2. **A:** gọi `/health/ready` → 503; detail product ở B → lỗi tạm thời. Detail product ở A có thể vẫn đọc được khi core/Mongo/A còn hoạt động.
3. Global listing fan-out có thể trả 503 vì không bảo đảm đủ kết quả; không gọi kết quả thiếu B là hợp nhất đầy đủ.
4. **B:** `dcb up -d --wait site-b`; A kiểm readiness và `scripts.graph status`, đợi worker xử lý lại.
5. Dữ liệu volume B vẫn giữ; không cần reseed sau stop/start.

Dừng B không thử nghiệm HA: hiện chưa có replica tự tiếp quản B. Đừng chứng minh failover bằng cách chuyển owner trong khi chưa copy/verify dữ liệu.

### 11.5. Site C tùy chọn và gateway

C có thể chạy như một instance bổ sung trên A để rehearsal mở rộng logical site, không phải máy vật lý thứ ba:

```bash
demo --profile expansion up -d --wait site-c
demo exec tools python -m scripts.bucket_setup --sites A B C
```

C đã có DSN trong hai mẫu Compose nhưng chưa đăng ký cho đến lệnh trên. Site đăng ký active phải tiếp tục truy cập được; nếu C đã đăng ký, cần khởi động C cùng các lần restart/readiness/backup sau đó. Không tự xóa site_registry để bỏ lỗi readiness.

Gateway read-only dùng `app.catalogue_gateway:app`, cùng resolver khi `BUCKET_MODE=true`. Để demo gateway thật, dùng terminal A riêng với port chưa dùng (không publish lại port của backend đang chạy):

```bash
demo --profile app run --rm --no-deps -p 127.0.0.1:57681:8000 \
  --entrypoint uvicorn backend app.catalogue_gateway:app --host 0.0.0.0 --port 8000
# Terminal khác: curl -fsS http://localhost:57681/products
```

Gateway trả `{items,total,skip,limit,sites}`; POST sản phẩm bị 405. Exact count giới hạn 100.000, khác API chính trả danh sách product. Dừng one-off bằng Ctrl-C, không down toàn stack.

## 12. Theo dõi, backup và phục hồi

### 12.1. Quan sát worker và read models

```bash
demo ps
demo logs --tail 40 backend worker
demo exec tools python -m scripts.graph status
demo exec tools python -m scripts.graph incremental
demo exec tools python -m scripts.verify_seed --include-graph
```

`app_event`/`app_delivery` tồn tại **ở từng nguồn core/site**, ACK `mongo` và `graph` riêng. `graph_pending_revision` là tín hiệu metadata Mongo, không nằm trong SQL outbox. Cờ pending bằng 0 và các delivery done là evidence của thời điểm kiểm tra, không cam kết không còn sự kiện mới về sau.

Chỉ sau khi sửa nguyên nhân dead letter:

```bash
demo exec tools python -m scripts.graph retry-dead
demo exec tools python -m scripts.graph reconcile
```

`reconcile/backfill` hiện quét tập nguồn, phù hợp lab vừa/nhỏ; không coi là backfill có checkpoint từng chunk cho hàng triệu hàng. Không chạy `etl.run worker` legacy đồng thời để chiếu catalogue từ bảng core.product rỗng.

### 12.2. Backup/restore thử trước reset

Dừng tất cả writer ứng dụng và các client SQL ghi ngoài app. Dừng frontend/backend/worker A; **giữ core/A/B/Mongo/Neo4j/tools hoạt động**:

```bash
demo stop frontend backend worker
demo exec tools python -m scripts.bucket_backup_check --output /tmp/demo-backup-01
mkdir -p deploy/backups/buckets
# Compose cp dùng service, không phụ thuộc tên container của project.
demo cp tools:/tmp/demo-backup-01 deploy/backups/buckets/
demo --profile app up -d backend worker frontend
```

Script pg_dump core và từng site, restore vào **database mới trên đúng instance/site đó**, so count/hash; clone BSON + validator/index Mongo, sao binary media và kiểm checksum. Vì vậy B cần quyền tạo database của tài khoản lab, đủ disk; script giữ các database `bucket_restore_*` để kiểm tra. `ok:true` là phục hồi rehearsal thành công, **không tự trỏ app sang database restore**.

Lưu backup ra ổ/máy độc lập trước xóa volume. Credential cần được giữ riêng để mở lại dữ liệu; không đưa dump/BSON vào Git. Với MinIO cần backup object/bucket của MinIO, không chỉ thư mục cache local.

Phục hồi để vận hành thật: dùng bộ backup cùng thời điểm, restore core và tất cả owner site, Mongo và media; cấu hình DSN/volume vào các đích restore, đối soát identity/mapping/hash rồi rebuild graph trước mở writer. Không restore mỗi core trong khi site đang có giao dịch mới. `bucket_backup_check` là diễn tập, không có lệnh tự động cutover toàn hệ.

### 12.3. Graph rebuild sau lỗi hoặc cần dựng lại projection

```bash
demo stop worker
# Đọc generation hiện tại ở core; chọn số lớn hơn, ví dụ 3 nếu đang ở 2.
demo exec tools python -m scripts.graph rebuild --generation 3
```

Sau thành công, đặt `GRAPH_GENERATION=3` trong đúng env A/local, giữ các secret. Recreate backend/worker/tools, rồi restart frontend nếu backend đổi IP Docker:

```bash
demo --profile tools --profile app up -d --force-recreate tools backend worker frontend
demo exec tools python -m scripts.verify_seed --include-graph
```

Khi rebuild lỗi, resume bằng **cùng generation đang rebuilding**, không chọn lùi generation. API graph có thể 503 trong lúc chuyển; worker generation cũ không ACK vào generation mới. Generation cũ được giữ; chưa có garbage collection tự động. Vì backend pin Cypher 5, không tự đổi câu query sang cú pháp Cypher 25 khi đang demo.

## 13. Restart, reset toàn bộ và DROP DATABASE

### 13.1. Restart giữ dữ liệu

**A/B:** khởi động B trước, rồi A. Nếu chỉ sửa code thì build lại image cần thiết và recreate service ứng dụng; không drop DB:

```bash
# B
dcb up -d --wait site-b
# A
dca up -d --wait core site-a mongo neo4j
# Nếu đã đăng ký C: dca --profile expansion up -d --wait site-c
dca --profile tools --profile app up -d tools backend worker frontend
```

`stop`, `start`, `down` không có `--volumes` giữ named volume. Mất file plan `/tmp` không có nghĩa mất dữ liệu: resume từ seed_runs hoặc lập plan mới theo fingerprint.

### 13.2. Reset sạch toàn bộ môi trường demo — cách đơn giản nhất

**Các lệnh sau xóa dữ liệu thật trong đúng project demo đã chọn**, gồm database, Mongo, Neo4j, media. Thực hiện sau backup mục 12. Chọn **một** nhánh, không chạy cả hai để “chắc chắn”. Không dùng `docker system prune --volumes` vì có thể ảnh hưởng project khác.

**Nhánh một máy**:

```bash
bucket_local --profile app --profile tools --profile expansion down --volumes
```

**Nhánh hai máy**:

```bash
# Trên A trước: dừng nguồn ghi và xóa volume của project A.
dca --profile app --profile tools --profile expansion down --volumes
# Trên B: xóa volume shard B của project B, không phải project A.
dcb down --volumes
```

Giữ env/credential. Đưa `GRAPH_GENERATION` về **1** vì core mới mặc định generation 1; env cũ còn 2/3 sẽ làm `graph init` từ chối. Trên A chạy đoạn dưới, chọn đúng env:

```bash
python3 - <<'PY'
from pathlib import Path
# Hai máy: deploy/.env.bucket-ab-a. Một máy: thay thành deploy/.env.bucket.
p=Path('deploy/.env.bucket-ab-a')
lines=[line for line in p.read_text().splitlines() if not line.startswith('GRAPH_GENERATION=')]
p.write_text('\n'.join(lines+['GRAPH_GENERATION=1'])+'\n')
p.chmod(0o600)
print('Đã đặt generation 1; giữ nguyên credential.')
PY
```

Sau đó làm lại mục 5 với B trước/A sau (một máy: mục 3, **bỏ lệnh prepare env đã tồn tại**). Dataset/mapping/global ID được tạo mới trong installation UUID mới. File plan cũ có fingerprint khác, phải tạo plan mới. Nếu đã xóa hết volume và muốn đổi credential, thay đồng bộ A/B trước startup; không chỉ đổi env password trên volume PostgreSQL còn tồn tại.

### 13.3. Reset bằng DROP DATABASE, giữ container/volume

Dùng khi muốn demo thao tác quản trị SQL. Nhánh dưới giả định chỉ A/B, không có C active; nếu có C, phải reset cả `oldshop_3` và projection tương ứng. Chỉ drop core hoặc chỉ B sẽ làm identity/directory/metadata không khớp.

1. Backup và `demo stop frontend backend worker`.
2. Reset **Mongo của môi trường đang chọn và namespace graph của nó**, khi tools còn chạy:

```bash
demo exec -T tools python - <<'PY'
from app.core.config import settings
from app.services.mongo import get_database
from app.services.neo4j import driver
# Thao tác phá hủy trên target cấu hình hiện tại: kiểm env/installation trước!
database=get_database()
database.client.drop_database(database.name)
driver().execute_query(
    'CYPHER 5 MATCH(n) WHERE n.key=$dataset OR n.key STARTS WITH $prefix DETACH DELETE n',
    dataset=settings.BUCKET_DATASET,prefix=settings.BUCKET_DATASET+':',database_=settings.NEO4J_DATABASE)
print('Đã xóa Mongo target và graph namespace; chưa xóa media.')
PY
demo stop tools
```

3. Trên A, drop/create từng DB bằng **các lệnh riêng**, kết nối database `postgres`:

```bash
demo exec -T core psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS oldshop_core WITH (FORCE);'
demo exec -T core psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE oldshop_core OWNER bucket_admin;'
demo exec -T site-a psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS oldshop_1 WITH (FORCE);'
demo exec -T site-a psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE oldshop_1 OWNER bucket_admin;'
```

4. Trên **B** (một máy thì thay `dcb` bằng `bucket_local`):

```bash
dcb exec -T site-b psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE IF EXISTS oldshop_2 WITH (FORCE);'
dcb exec -T site-b psql -U bucket_admin -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE oldshop_2 OWNER bucket_admin;'
```

5. Đặt env generation về 1 theo mục 13.2; recreate tools, chạy setup/init/plan/apply/verify rồi mở app:

```bash
demo --profile tools up -d --force-recreate tools
demo exec tools python -m scripts.bucket_setup --sites A B
demo exec tools python -m scripts.graph init
demo exec tools python -m scripts.seed plan --dataset demo-v2 --output /tmp/drop-reseed-01.json
demo exec tools python -m scripts.seed apply --plan /tmp/drop-reseed-01.json
demo exec tools python -m scripts.verify_seed --include-graph
demo --profile app up -d --force-recreate backend worker frontend
```

Nhánh DROP này **giữ binary media**; file seed trùng key/checksum được dùng lại và file runtime cũ có thể thành orphan. Muốn sạch cả file/object và database restore thử, dùng nhánh xóa volume 13.2. Không `rm -rf` thư mục Docker host. `DROP DATABASE` không chạy trong transaction và không thể thực hiện khi đang kết nối chính DB cần drop ([PostgreSQL 16](https://www.postgresql.org/docs/16/sql-dropdatabase.html)).

## 14. Migration dữ liệu hiện hữu sang bucket

Đây là đường thay thế bước seed demo, không phải bước chạy tiếp sau khi đã seed target. Chuẩn bị môi trường A/B mới/trống theo mục 4–5, đặt `BUCKET_DATASET=legacy-import-v1`, generation 1 trước setup; chạy `bucket_setup`, `graph init`, **bỏ seed plan/apply demo-v2**.

### 14.1. Nguồn, timezone và media

Nguồn cần schema legacy tương thích (các bảng gốc và `etl_time_origin`), DSN đọc được **từ container tools A**. Dùng tài khoản nguồn chỉ đọc. Trong file private `deploy/.env.bucket-legacy`, khai báo:

```dotenv
BUCKET_LEGACY_URL=postgresql://USER_READONLY:PASSWORD_URL_ENCODED@HOST_NGUON:5432/oldshop
BUCKET_LEGACY_MONGO_URI=mongodb://USER:PASSWORD_URL_ENCODED@HOST_MONGO:27017/?authSource=admin
BUCKET_LEGACY_MONGO_DB=oldshop
BUCKET_LEGACY_MEDIA_DIR=/legacy-media
```

Hai dòng Mongo là tùy chọn nếu nguồn không có metadata. `HOST_NGUON` không dùng localhost của A nếu chạy trong tools. Ví dụ nguồn là project `oldshop-data` trên A: có thể nối tools vào external network `oldshop-data_data`, dùng hostname `pg-primary`/`mongo1`; Mongo replica set cần resolve được mọi member mà URI quảng bá.

Lưu override `deploy/docker-compose.bucket-legacy.override.yml` cho **trường hợp nguồn oldshop-data đang chạy, local media volume đã có đủ file**:

```yaml
services:
  tools:
    env_file: [.env.bucket-legacy]
    networks: [default, legacy_data]
    volumes: [legacy_media:/legacy-media:ro]
networks:
  legacy_data:
    external: true
    name: oldshop-data_data
volumes:
  legacy_media:
    external: true
    name: oldshop-data_data_media
```

Tên network/volume phải khớp `docker network ls`/`docker volume ls` trên A. Với nguồn khác, sửa network/mount và DSN tương ứng. Nguồn MinIO cần export byte ảnh đúng key thành `products/...`, `users/...`, `videos/...` trong media root được mount, hoặc provision shared MinIO đích theo importer; không coi cache media chưa đủ là bản export.

```bash
# A: hàm riêng để thêm cấu hình nguồn; target vẫn là project bucket A/B.
dca_import() {
  docker compose -p oldshop-bucket-ab-a --env-file deploy/.env.bucket-ab-a \
    -f deploy/docker-compose.bucket-ab-a.yml \
    -f deploy/docker-compose.bucket-legacy.override.yml "$@"
}
dca_import --profile tools up -d --force-recreate tools
dca_import exec tools python -m scripts.migrate_catalogue_to_buckets plan \
  --assume-naive-zone Asia/Ho_Chi_Minh --output /tmp/legacy-import-01.json
```

Chọn timezone theo nguồn/provenance, không mặc định vì đang ở Việt Nam. Một số nguồn lưu UTC-naive thì cần `UTC`. Plan chỉ xuất count/hash/violation, không dump toàn bộ PII.

### 14.2. Apply và kiểm tra

Dừng writer ở **nguồn cũ** trong cửa sổ migration đã quyết định, giữ database/media nguồn hoạt động. Đọc violation từ plan, đối soát trước apply. Trong lần kiểm tra nguồn `oldshop-data` ngày 17/11/2026 đã có 30 contact–buyer mismatch và 5 payment state ngoài hợp đồng; công cụ sẽ từ chối, không random sửa buyer/contact.

```bash
dca_import exec tools python -m scripts.migrate_catalogue_to_buckets apply --plan /tmp/legacy-import-01.json
dca_import exec tools python -m scripts.verify_seed --include-graph
dca_import exec tools python -m scripts.graph status
```

Nguồn đổi sau plan thì tạo plan mới trong thời gian bảo trì. Cùng import có thể replay khi hash/fingerprint còn khớp; metadata target đã được sửa sẽ được bảo vệ bằng provenance/revision. ID product/image và reference được giữ, allocator/sequence được đưa vượt các ID đã nhập. Đơn lịch sử thiếu reservation đáng tin cậy cần reconciliation trước khi cho hủy.

Sau khi kiểm đủ, bỏ override nguồn khỏi tools để thu hẹp quyền truy cập; mở backend/worker/frontend target và thực hiện smoke test. Chuyển URL/traffic là bước vận hành riêng sau đối soát, không có auto-cutover trong importer. Giữ nguồn/backup để rollback; nếu đích đã có ghi mới thì cần hợp nhất các ghi đó, không restore snapshot cũ đè lên.

## 15. Demo các thành phần khác đã có và giới hạn tích hợp

### 15.1. Ma trận “đã có” và “đang hướng đến”

| Thành phần | Demo trên bucket A/B | Lab riêng / giới hạn cần nói rõ |
|---|---|---|
| SQL giao dịch + partition + user split | Có | Partition không phải replication/HA |
| Product JSON + caption/description | Có, Mongo + API + frontend | Attributes tổng quát demo bằng quản trị Mongo; không có editor toàn bộ JSON ở mọi trang |
| Neo4j metadata/related | Có | Không AI/embedding/pixel search; không HA Neo4j |
| Ảnh/video binary | Có, media A | Media A chưa tự replicate sang B |
| MinIO private object storage | Adapter đã có | Compose bucket/seed/verifier hiện dùng local media; không chỉ bật flag rồi coi đã chuyển toàn bộ object |
| Mongo 3-member replica set | Có trong lab legacy | Compose bucket ở đây là một Mongo instance; 3 container cùng máy chưa chịu mất cả host |
| PostgreSQL primary/read replica | Có trong lab legacy | Replica khác shard; chưa tự failover core/bucket owner |
| FDW/global views/gateway cũ | Có trong lab site cũ | Hợp đồng cũ khác bucket v2; không route checkout mới qua views cũ |
| Sáu read-model collections + ETL errors | Có schema/legacy ETL | Bucket worker tập trung product_details và graph order/review; collection tồn tại không chứng minh đang được populate |
| Logging/metrics/dashboard | Có `/metrics`, Docker logs; stack monitoring riêng | Chưa tự ghép mọi overlay monitoring legacy vào bucket A/B |
| PayPal/email/Apps Script | Có mã tích hợp | Cần credential/provider thật; không gửi giao dịch/email thật chỉ để quay demo |

### 15.2. Khởi động lab legacy đầy đủ khi cần trình bày replication/MinIO

Không làm phần này lên database bucket. File đúng là `deploy/docker-compose.distributed.yml`; **không phải** một file dưới `deploy/data/docker-compose.data.yml`. Nếu stack legacy đã chạy, ưu tiên quan sát nó, không tạo env/seed lại.

Với **lab legacy mới, chưa có dữ liệu và chưa có env**, tại root repository:

```bash
python3 deploy/scripts/prepare-data-env.py
python3 deploy/scripts/prepare-media-env.py
legacy() {
  docker compose -p oldshop-data --env-file deploy/.env.data \
    -f deploy/docker-compose.distributed.yml "$@"
}
legacy config --quiet
legacy build backend frontend
legacy --profile resilience up -d --wait --wait-timeout 240 \
  pg-primary pg-replica mongo1 mongo2 mongo3 minio
legacy run --rm --no-deps mongo-init
legacy --profile resilience run --rm --no-deps mongo-expand
legacy run --rm --no-deps minio-init
legacy run --rm --no-deps mongo-schema-init
legacy run --rm --no-deps --entrypoint python backend -m scripts.init_db
legacy run --rm --no-deps --entrypoint python backend -m scripts.seed_media
# Chỉ chuyển flag sau khi provision/copy media thành công:
python3 deploy/scripts/prepare-media-env.py --enable-minio
legacy --profile resilience up -d backend frontend
legacy exec backend python -m etl.run full
legacy --profile resilience up -d etl-worker
```

Nhánh này dùng seed/tài khoản legacy (`admin@oldshop.com`, các user seed cũ), không phải `bucketN@example.com`. Cổng theo `.env.data`, thường frontend 58080/backend 58000, PostgreSQL 55432/55433, MinIO 59000/59001; kiểm env của lab và `legacy ps`. Nếu các cổng/project đã được dùng, dùng cấu hình lab riêng có port/volume/env riêng theo [hướng dẫn hệ thống hiện có](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md), không đổi credential trên volume đang chạy.

Xem đầy đủ xử lý lần đầu/MinIO tại tài liệu liên kết trên. Đây là **lab bổ sung độc lập**, không phải đã đưa primary/replica hoặc Mongo replica set vào topology bucket A/B.

### 15.3. Các thao tác manual để chứng minh

**PostgreSQL replication**, chỉ đọc trong lab legacy:

```bash
legacy exec pg-primary psql -U oldshop -d oldshop -c 'SELECT application_name,state,sync_state FROM pg_stat_replication;'
legacy --profile resilience exec pg-replica psql -U oldshop -d oldshop -c 'SELECT pg_is_in_recovery(),pg_last_wal_replay_lsn();'
```

Đổi user/DB nếu `.env.data` khác mặc định. Thao tác tạo/sửa product qua **API legacy** rồi đọc primary/replica để quan sát độ trễ. Không ghi trực tiếp trên replica. Việc replica đọc được dữ liệu không chứng minh ứng dụng tự chuyển sang replica khi primary chết.

**Mongo replica set**, mở Compass/mongosh đã xác thực vào replica set của lab:

```javascript
rs.status()
db.hello()
```

Xem PRIMARY/SECONDARY và member host. Không chạy `rs.initiate()` lần hai trên replica set đang có. Từng host/port member phải resolve được từ client; xem [hướng dẫn cấu hình](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md) nếu Compass ở ngoài Docker.

**ETL read models và lỗi**, lab legacy:

```bash
legacy exec backend python -m etl.run status
legacy exec backend python -m etl.run reconcile
```

Trong Compass xem `product_details`, `reviews`, `order_snapshots`, `system_logs`, `violation_logs`, `contact_messages`, `etl_errors`. Query một order ID có thật trong `order_snapshots`; đối chiếu source, `etl.synced_at`, source timezone/provenance và quality errors. Không trình bày một collection rỗng là luồng dữ liệu đã hoàn thiện. SQL ETL bảo toàn các trường Mongo sở hữu; xử lý dead letter theo nguyên nhân rồi mới retry.

**MinIO:** mở Console tại cổng cấu hình, dùng credential lab; xem bucket private, object key, content type và size. Đối chiếu cùng `image_id → image_url → bucket/key → object byte`. Tải qua `/media/...` của app và thử HEAD/Range với MP4. Không lưu signed URL hết hạn làm khóa lâu dài. Không tự xóa object dùng chung để demo CRUD product.

**FDW lab cũ:** tài liệu [CSDL phân tán](HUONG_DAN_CSDL_PHAN_TAN.md), [site B Ubuntu](HUONG_DAN_SITE_B_UBUNTU_24_04.md) và [runbook fragmentation](runbooks/fragmentation_indexing.md) có quy trình riêng. Trong site A của lab đó có thể xem:

```sql
SELECT srvname FROM pg_foreign_server;
SELECT foreign_table_schema,foreign_table_name FROM information_schema.foreign_tables;
SELECT * FROM v_site_health;
```

Các views này **không được bucket_setup tạo**. Bucket v2 routing nằm ở application/repository; không cần FDW để hợp nhất danh sách product.

**Metrics/logs:** mở `/metrics` ở backend đúng môi trường, tạo request rồi quan sát count/duration; `demo logs -f backend worker` cho request ID và lỗi consumer. Các file `deploy/docker-compose.monitoring.yml`, `docker-compose.loki.yml`, `docker-compose.elk.yml` phục vụ stack vận hành có cấu hình riêng; không chạy đồng thời hai log stack hoặc ghép overlay vào bucket mà chưa sửa network/target/port. Xem [deployment](deployment.md), [hướng dẫn cấu hình](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md).

## 16. Kịch bản demo từ đầu đến cuối và evidence

Chuẩn bị trước: seed/verify hoàn tất, có backup, B online, chọn sẵn product/ảnh demo, ba browser profile, pgAdmin core/A/B, Compass, Neo4j Browser. Không reset ngay trong buổi thuyết trình trừ khi đề tài là quy trình quản trị và đã có backup.

| Thứ tự | Thời lượng gợi ý | Thao tác và bằng chứng |
|---|---:|---|
| 1 | 2 phút | Sơ đồ A/B, `hostname` mỗi máy, Docker `ps`, DSN B qua private host port |
| 2 | 3 phút | Contract hash, bucket_assignment, product owner A/B, core.product rỗng, manifest |
| 3 | 4 phút | Seller tạo product + ảnh/MP4, mod duyệt; mở detail như buyer |
| 4 | 4 phút | Theo dấu cùng product/image ID ở SQL, Mongo, file và graph; metadata revision |
| 5 | 3 phút | Tìm `alphaonly`, không dấu/có dấu; sửa/clear caption trên product demo, graph cập nhật |
| 6 | 4 phút | Cart giữ hàng, COD, fulfillment, review; đơn khác hủy và hoàn kho đúng một lần |
| 7 | 4 phút | EXPLAIN PostgreSQL, Mongo explain, Neo4j constraints/full-text; JSON catalog |
| 8 | 4 phút | Move một bucket A↔B, giữ API/ID; move ngược mang theo ghi mới |
| 9 | 2 phút | Stop B → readiness/global query lỗi rõ; start B và chờ retry |
| 10 | 2 phút | Verifier/status, backup report, giới hạn và kế hoạch HA/scale |
| Tùy chọn | 5–10 phút | Legacy replication/FDW/MinIO/ETL/metrics, ghi rõ lab khác |

Evidence tối thiểu, lưu vào thư mục local không chứa secret:

```bash
mkdir -p deploy/backups/demo-evidence
demo exec -T tools python -m scripts.verify_seed --include-graph \
  > deploy/backups/demo-evidence/verify.json
demo exec -T tools python -m scripts.graph status \
  > deploy/backups/demo-evidence/delivery.json
demo exec -T tools python -m scripts.bucket_evidence --base-url http://backend:8000 \
  > deploy/backups/demo-evidence/runtime.json
```

Lưu thêm screenshot query plan, ảnh graph, `bucket_moves` và checksum trước/sau, backup report, HTTP status khi B down/up. `bucket_evidence` là mẫu request tuần tự local, không phải benchmark throughput phân tán. Không đưa dump/PII/password/token hoặc toàn bộ `docker inspect`/`compose config` có secret vào bài thuyết trình.

Kiểm thử có sẵn (chạy trong lab, có tạo thêm fixture/database thử):

```bash
demo exec tools python -m pytest -o addopts= -o cache_dir=/tmp/bucket-pytest-cache \
  --confcutdir=tests/buckets tests/buckets -q
demo exec tools python -m scripts.bucket_regression
# Trên A, nếu đã cài dependency frontend theo package-lock:
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm test -- --watch=false
npm run build -- --configuration production
```

Bài move sang C sẽ skip nếu chưa setup C. Chạy test làm tổng product/DB thử lớn hơn manifest seed; không nói “tổng hệ phải luôn đúng 1.000” sau test hoặc sau tạo product manual. Không chạy suite legacy trực tiếp trên DB ứng dụng có dữ liệu đang dùng; runner regression tạo DB riêng.

## 17. Xử lý lỗi thường gặp và checklist kết thúc

| Hiện tượng | Cách kiểm và xử lý |
|---|---|
| A không tới B | IP/LAN/VPN, B bind IP, published 57632, Docker firewall, test từ tools; localhost không phải B |
| Password đổi mà không login được | Env không tự đổi password PostgreSQL/Mongo trên volume đã khởi tạo; dùng credential cũ hoặc quy trình đổi password có kế hoạch |
| `bucket_setup` từ chối nonempty legacy | Đang trỏ nhầm nguồn hoặc target chưa trống; dùng importer/target mới, không xóa marker |
| `Installation/schema differs` | Source/schema/dataset/identity không khớp; không sửa digest, không chạy seed SQL cũ để chữa |
| `Graph generation differs` | Core generation và env của tools/backend/worker khác nhau; recreate đúng env; reset toàn hệ mới đưa về 1 |
| Fingerprint changed | Site/mapping/schema/graph target đổi; tạo plan mới, không chỉnh fingerprint trong file |
| File plan đã tồn tại | CLI mở file với chế độ tạo mới; chọn tên mới hoặc dùng run_id resume |
| Metadata missing / HTTP 409 khi sửa caption | Product SQL chưa có document Mongo; chạy incremental/status, sửa nguyên nhân projection |
| Caption lưu được nhưng chưa tìm thấy | Pending/index/generation/visibility; graph là eventual consistency; dùng API để kiểm đúng membership |
| Không thấy ảnh/video | Kiểm URL/key, media volume trên A, MIME/codec, Nginx proxy, quyền đọc; không reseed để chữa DNS |
| API listing 503 khi B down | Fan-out không đọc đủ site; khôi phục B; không tự route toàn bộ sang A |
| Gateway 100.000 cap | Thu hẹp filter; đây là giới hạn exact count lab, không phải dữ liệu tự biến mất |
| Seed replay báo quantity/order drift | Đã có thay đổi nghiệp vụ; giữ dữ liệu hoặc chọn reset lab có backup, không force overwrite |
| SQL query không thấy index | Đúng DB/site chưa? predicate/sort phù hợp không? dữ liệu nhỏ có thể Seq Scan; xem explain thực tế |
| `CannotCreateIndex` / index conflict | So tên, keys, unique/partial với JSON catalog; migration phiên bản mới, không drop hàng loạt index |
| HTTP 502 sau recreate backend | Kiểm backend healthy; restart/recreate frontend để Nginx resolve backend lại |
| Graph/container thiếu RAM | Kiểm memory limit/logs, tài nguyên host và stack khác; không coi kernel/port lỗi là lỗi seed |
| Import legacy có violation | Đối soát theo report: contact/buyer, payment enum, totals, self-buy, timezone; không sửa random |

Checklist hoàn tất:

- [ ] Đã ghi rõ topology là một máy hay hai máy, project/env/port dùng cho từng nơi.
- [ ] B là instance trên máy B thật; A kết nối bằng IP B, không có site-b local giả làm remote.
- [ ] Contract và manifest khớp; verifier SQL/Mongo/graph đạt, không có active owner trùng.
- [ ] Cùng product/image ID được theo dấu từ SQL qua JSON/BSON đến file và graph.
- [ ] Trình bày được ownership và độ trễ, không nói mọi JSON/Mongo collection đều là nguồn giao dịch.
- [ ] Demo được tìm đúng ảnh, metadata update/clear, permissions và visibility.
- [ ] Có query plan/index thực tế; không biến số đo máy nhỏ thành cam kết production.
- [ ] Demo order/cart/cancel không làm trừ/hoàn tồn hai lần; PayPal thật không được gọi ngoài ý định.
- [ ] Move/rollback có checksum/epoch/ghi mới; sau demo B/C còn đúng trạng thái hoạt động.
- [ ] Có backup đã restore thử trước reset; phân biệt DROP database, xóa volume và migration nguồn.
- [ ] Đã mở lại worker/frontend/backend và kiểm readiness, pending/dead sau các bài fault injection.
- [ ] Các phần legacy, phần chưa tích hợp và mục tiêu HA/AI/scale được ghi đúng phạm vi.

Báo cáo local đã có trong [evidence bucket/site/Neo4j](evidence/bucket_site_neo4j/); nó chứng minh rehearsal local ngày ghi nhận, không thay thế kiểm chứng hai máy thật của buổi demo mới.
