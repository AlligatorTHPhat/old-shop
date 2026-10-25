# OldShop — Gate A Audit Report
## Repository, Runtime & Build Configuration

> **Gate:** A — Repository / Runtime / Build Configuration
> **Kết quả:** `CONDITIONAL PASS`
> **Phiên bản:** 2 (đã hợp nhất kết quả kiểm tra lại trực tiếp trên nội dung 9 file)
> **Trạng thái:** Đã ghi nhận baseline và các finding; chưa chốt `READY FOR IMPLEMENTATION`.
> **Phạm vi:** Báo cáo dựa trên nội dung 9 file được cung cấp trong phiên làm việc. Đây không phải kết quả chạy Docker/CI hoặc xác minh trực tiếp môi trường production. Các điểm chưa xác minh được đánh dấu rõ là **cần xác minh**.

### Lịch sử phiên bản

| Phiên bản | Nội dung |
|---|---|
| 1 | Kết quả Gate A ban đầu (F-A-001 → F-A-010) |
| 2 | Kiểm tra lại trực tiếp 9 file. **Sửa** F-A-004 (nguồn dẫn) và F-A-010 (phạm vi `.dockerignore`); **bổ sung** mục Network/Port/Startup order, F-A-011 → F-A-022 và D-A-009 → D-A-014; điều chỉnh trạng thái `frontend/Dockerfile` |

---

## 1. Mục tiêu và phạm vi

Gate A xác lập baseline repository/runtime trước khi thiết kế tích hợp PostgreSQL, MongoDB và MinIO. Các file đã được đánh giá:

- `.gitignore`
- `.dockerignore`
- `README.md`
- `PROJECT_GUIDE.md`
- `docker-compose.yml` (Compose **local**, `name: oldshop-local`)
- `backend/Dockerfile`
- `backend/docker-entrypoint.sh`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

Nội dung xem xét: build context, service, network, port, volume, thứ tự khởi động, healthcheck, bootstrap database, cách phục vụ media, runtime privilege và sự phù hợp với quy ước SQL-first.

### Giới hạn

- Gate A **không** audit toàn bộ schema/query, không xác định fragment key hoặc index cụ thể, và không triển khai MongoDB/MinIO. Các quyết định đó chờ các Gate liên quan.
- **Chưa được xem** (ảnh hưởng độ chắc chắn của một số finding): `backend/scripts/init_db.py`, `frontend/.dockerignore`, `deploy/docker-compose.yml`, `docs/deployment.md`, `backend/app/core/config.py`.
- Chưa chạy Docker; các kiểm chứng cần chạy thử nằm ở mục 7.

---

## 2. Tóm tắt kết quả

| File / thành phần | Trạng thái | Kết luận |
|---|---|---|
| `.gitignore` | PASS | Loại trừ secrets, cache, runtime media, artifact ML, dump/backup. Lưu ý: loại mọi file Office/PDF (F-A-021) |
| `.dockerignore` | CONDITIONAL PASS | `*.md`/`*.docx` chỉ khớp ở gốc context (F-A-010); không áp dụng cho build context `frontend` (F-A-011) |
| `README.md` | PASS | Mô tả baseline PostgreSQL và luồng API/media; có vài chênh lệch nhỏ so với PROJECT_GUIDE (F-A-020) |
| `PROJECT_GUIDE.md` | PASS | Xác nhận SQL-first, vai trò bootstrap của `init_db.py` |
| `docker-compose.yml` | PASS WITH FINDINGS | Chỉ có PostgreSQL, Backend, Frontend; chưa có MongoDB/MinIO (F-A-001); cổng/credential local (F-A-014); chưa dùng healthcheck cho thứ tự khởi động (F-A-018) |
| `backend/Dockerfile` | PASS | Build context root, copy `database/`, non-root |
| `backend/docker-entrypoint.sh` | PASS WITH RISK | Gọi bootstrap DB, không phải migration (F-A-002); có thể nạp seed ở production (F-A-013); nhiều replica cùng chạy init (F-A-022) |
| `frontend/Dockerfile` | CONDITIONAL PASS | Angular build, Nginx unprivileged; phụ thuộc `frontend/.dockerignore` chưa xác minh (F-A-011) |
| `frontend/nginx.conf` | PASS WITH FOLLOW-UP | `/api/` và `/media/` proxy tới backend; cần đánh giá khi có MinIO (F-A-003) và các điểm F-A-012, 016, 017, 019 |

**Kết luận:** Không có lỗi kiến trúc nghiêm trọng cần sửa ngay. Các khoảng trống MongoDB/MinIO là khoảng cách so với kiến trúc mục tiêu, chưa phải bug của baseline hiện tại. Các finding mới (Medium trở xuống) không đổi kết luận này nhưng phải được xử lý hoặc xác minh ở các Gate sau.

---

## 3. Baseline runtime (Compose local)

Mục này bổ sung các hạng mục plan yêu cầu kiểm tra ("service, network, volume, port, startup order, media path").

| Hạng mục | Thực tế |
|---|---|
| **Service** | `postgres` (`postgres:16-alpine`), `backend` (build từ root repo, `backend/Dockerfile`), `frontend` (build từ `./frontend`) |
| **Network** | Không khai báo; dùng network mặc định của project `oldshop-local` |
| **Port (host → container)** | `5433→5432` (PostgreSQL), `8000→8000` (backend), `8080→8080` (frontend) |
| **Startup order** | `postgres` (chờ `service_healthy`) → `backend` (`depends_on` có điều kiện healthy của postgres) → `frontend` (`depends_on: [backend]`, dạng ngắn, chỉ chờ khởi động) |
| **Healthcheck** | Compose chỉ định nghĩa cho PostgreSQL (`pg_isready`). Backend (`curl /health`) và frontend (`wget /healthz`) có `HEALTHCHECK` trong Dockerfile nhưng compose không dùng chúng làm điều kiện |
| **Volume** | `pg_data` → `/var/lib/postgresql/data`; `media` → `/data/media` (khớp `MEDIA_DIR=/data/media` trong Dockerfile) |
| **Media path** | Upload ghi vào `/data/media` → FastAPI phục vụ `/media` → Nginx proxy `/media/` |
| **Fraud artifacts** | `FRAUD_MODEL_DIR=/data/ml` có trong Dockerfile nhưng compose local không mount → local dùng rule-based |
| **Restart policy** | Không có |
| **Cấu hình DB cho backend** | Compose đặt `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`; **không** đặt `DB_PORT` hay `DATABASE_URL` (dựa vào mặc định). Phù hợp cảnh báo bootstrap trong PROJECT_GUIDE §8 |
| **Biến môi trường dev** | `ENVIRONMENT=development`, `DEBUG=true`, `LOG_FORMAT=text`, `WEB_CONCURRENCY=1`, `CORS_ORIGINS` gồm `:8080` và `:4200` |

---

## 4. Findings chi tiết

### F-A-001 — Compose chưa có MongoDB và MinIO

- **Mức độ:** Medium / Architecture gap
- **Bằng chứng:** `docker-compose.yml` có các service `postgres`, `backend`, `frontend`; volume `pg_data` và `media`.
- **Ảnh hưởng:** Chưa thể chạy hoặc kiểm thử tích hợp đa kho dữ liệu trong local Compose.
- **Quyết định:** Không thêm service tại Gate A. Trước hết hoàn thành data ownership và các thiết kế ở Gate B–H (collection MongoDB, object/bucket MinIO, metadata/reference, network, volume, backup). Khi thêm: dùng credential qua biến môi trường, không đặt mật khẩu mặc định, cân nhắc bind `127.0.0.1` (xem F-A-014) và `healthcheck` (xem F-A-018).
- **Trạng thái:** OPEN — chuyển tiếp sang các Gate thiết kế.

### F-A-002 — `init_db.py` là bootstrap, không phải migration

- **Mức độ:** High / Data integrity risk
- **Bằng chứng:** `backend/docker-entrypoint.sh` chạy `python -m scripts.init_db` trừ khi `SKIP_DB_INIT=true` (đã xác nhận trực tiếp trong file). README mô tả "idempotent bootstrap: create DB, load schema/seed once, copy seed images". Theo `PROJECT_GUIDE.md`, script bỏ qua `init.sql` nếu `public."user"` đã tồn tại.
- **Lưu ý về độ chắc chắn:** Hành vi "bỏ qua `init.sql`" hiện dựa vào tài liệu (PROJECT_GUIDE, README), **chưa xác minh trực tiếp từ mã `init_db.py`**.
- **Ảnh hưởng:** Sửa SQL source rồi restart container không đảm bảo schema của database đang tồn tại được cập nhật. Có nguy cơ code mới chạy với schema cũ hoặc migration không được áp dụng. Chữ "idempotent" trong README dễ bị hiểu nhầm là migration.
- **Quyết định bắt buộc:** Thiết kế quy trình migration/update SQL có kiểm soát, có version/history, precondition, backup, verify và rollback/recovery plan.
- **Trạng thái:** OPEN — là điều kiện trước khi áp dụng thay đổi schema lên database đã có dữ liệu.

### F-A-003 — `/media/` đang proxy trực tiếp tới Backend

- **Mức độ:** Medium / Architecture follow-up
- **Bằng chứng:** `frontend/nginx.conf` có `location ^~ /media/ { proxy_pass http://backend; ... }`; baseline dùng filesystem/Docker volume `media`. `^~` bảo đảm location này ưu tiên hơn regex file tĩnh, nên ảnh `.png/.jpg` dưới `/media/` đi tới backend.
- **Ảnh hưởng:** Khi chuyển sang MinIO, phải bảo đảm URL media hiện có (`/media/...`), quyền truy cập, upload/download/delete và frontend vẫn tương thích. Các chi tiết Nginx cần tính thêm: F-A-016 (header bảo mật), F-A-017 (cache 7 ngày, kết nối upstream).
- **Quyết định:** Chưa sửa Nginx ở Gate A. Gate G đánh giá `Angular → FastAPI → MinIO` hoặc presigned URL phù hợp yêu cầu bảo mật và API contract.
- **Trạng thái:** OPEN — Gate G.

### F-A-004 — PostgreSQL là database chính hiện tại

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng:** `PROJECT_GUIDE.md` mô tả PostgreSQL 16 là database chính và `docker-compose.yml` dùng `postgres:16-alpine`. README chỉ nêu "PostgreSQL" (không ghi version). Schema, function/trigger và seed được quản lý trong `database/`.
- **Ảnh hưởng:** Logic nghiệp vụ và transaction hiện hữu phụ thuộc PostgreSQL.
- **Quyết định:** Giữ PostgreSQL làm relational/transactional source of truth. Không chuyển dữ liệu giao dịch sang MongoDB chỉ để đáp ứng yêu cầu đa mô hình.
- **Trạng thái:** CONFIRMED.

### F-A-005 — SQL-first architecture phải được giữ nguyên

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng:** `database/` là nguồn schema chính; ORM chỉ mapping (README mục "Notes on design choices", PROJECT_GUIDE §5).
- **Ảnh hưởng:** Thay đổi bảng, constraint, index, function hoặc trigger cần bắt đầu từ SQL, rồi đồng bộ ORM/Pydantic/CRUD/API/test.
- **Quyết định:** Giữ quy ước SQL-first trong các Gate tiếp theo.
- **Trạng thái:** CONFIRMED.

### F-A-006 — Backend Docker build context là repository root

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng:** Compose dùng `context: .` và `dockerfile: backend/Dockerfile`; Dockerfile `COPY database /opt/database` và đặt `DATABASE_SRC=/opt/database`. Dockerfile cũng copy `backend/requirements.lock`, `backend/app`, `backend/scripts`, `backend/docker-entrypoint.sh`.
- **Ảnh hưởng:** Đổi build context mà không cập nhật đường dẫn/copy có thể làm image thiếu SQL source. SQL được "nướng" vào image lúc build, nên đổi `database/` cần build lại image.
- **Quyết định:** Giữ root build context, trừ khi có thiết kế build mới được kiểm thử đầy đủ.
- **Trạng thái:** CONFIRMED.

### F-A-007 — Backend runtime chạy non-root

- **Mức độ:** Security positive
- **Bằng chứng:** `backend/Dockerfile` tạo user `app` (uid 10001) và `USER app`; mã ứng dụng root-owned/read-only với user runtime; chỉ `/data` thuộc `app`.
- **Ảnh hưởng:** Giảm quyền mặc định của tiến trình ứng dụng. Named volume `media` mount vào `/data/media` khớp quyền sở hữu; bind mount thì có thể lệch quyền.
- **Quyết định:** Giữ hành vi non-root; khi thêm volume/bucket/client phải kiểm tra quyền truy cập tương thích.
- **Trạng thái:** CONFIRMED.

### F-A-008 — Frontend Nginx chạy unprivileged

- **Mức độ:** Security positive
- **Bằng chứng:** `frontend/Dockerfile` dùng `nginxinc/nginx-unprivileged:1.27-alpine`, `EXPOSE 8080`, compose map `8080:8080`; có `HEALTHCHECK` tới `/healthz`.
- **Ảnh hưởng:** Phù hợp với runtime không cần quyền root.
- **Quyết định:** Giữ cấu hình này; kiểm thử lại nếu thay đổi port hoặc proxy.
- **Trạng thái:** CONFIRMED.

### F-A-009 — `.gitignore` bảo vệ secrets/runtime artifacts

- **Mức độ:** Positive
- **Bằng chứng:** Có quy tắc `.env`, `.env.*` (giữ `!.env.example`), `*.pem`, `*.key`, `.clasp.json`, `.clasprc.json`; cache/virtualenv; `backend/media/`, `backend/ml_artifacts/`, `*.joblib`; `*.dump`, `*.sql.gz`, `deploy/backups/`, `deploy/ml/`; file IDE/hệ điều hành.
- **Ảnh hưởng:** Giảm nguy cơ commit nhầm secrets hoặc dữ liệu runtime.
- **Quyết định:** Không cần sửa ở Gate A. Khi bổ sung cấu hình MongoDB/MinIO, dùng biến môi trường/secret management và cập nhật example không chứa credential thật. Xem thêm F-A-021.
- **Trạng thái:** PASS.

### F-A-010 — `.dockerignore`: phạm vi của `*.md` và `*.docx`

- **Mức độ:** Low / Conditional *(đã sửa so với phiên bản 1)*
- **Bằng chứng:** `.dockerignore` có `*.md` và `*.docx` **không kèm `**/`**, trong khi các mục khác dùng `**/` (ví dụ `**/.git`, `**/.env`). Pattern không có `**/` chỉ khớp ở **thư mục gốc của context**.
- **Ảnh hưởng:** Chỉ `README.md`, `PROJECT_GUIDE.md`… ở gốc repo bị loại khỏi context; Markdown/docx trong thư mục con vẫn được đưa vào. Kết luận "Dockerfile hiện không cần Markdown nên không gây lỗi build" vẫn đúng. Rủi ro "build thiếu Markdown" hẹp hơn mô tả cũ; thư mục `database/` không bị loại.
- **Quyết định:** Chưa cần sửa ngay. Khi thêm `COPY`/build step phụ thuộc Markdown, rà soát lại `.dockerignore`. Nếu muốn loại mọi nơi phải dùng `**/*.md`.
- **Kiểm chứng:** Lệnh ở mục 7 (#1).
- **Trạng thái:** CONDITIONAL PASS.

### F-A-011 — Build context frontend không áp dụng `.dockerignore` ở gốc repo

- **Mức độ:** Medium (cần xác minh)
- **Bằng chứng:** Compose dùng `context: ./frontend`. Docker đọc `.dockerignore` ở gốc context của từng build, nên `.dockerignore` ở gốc repo không áp dụng cho frontend. `frontend/Dockerfile` có `COPY . .` sau `npm ci`.
- **Ảnh hưởng:** Nếu không có `frontend/.dockerignore`, `node_modules`, `dist`, `.angular` trên máy dev có thể bị đưa vào context và `COPY . .` có thể ghi đè `node_modules` vừa cài (khác hệ điều hành → lỗi hoặc build không tái lập).
- **Hành động:** Xác minh sự tồn tại và nội dung `frontend/.dockerignore`. Nếu chưa có, đề xuất tạo (thay đổi cấu hình, không thực hiện ở Gate A).
- **Trạng thái:** OPEN — `frontend/Dockerfile` ở mức CONDITIONAL PASS cho tới khi xác minh.

### F-A-012 — Nginx phân giải `backend` một lần khi khởi động

- **Mức độ:** Medium (cần chạy thử)
- **Bằng chứng:** `upstream backend { server backend:8000; keepalive 16; }` trong `nginx.conf`.
- **Ảnh hưởng:** Nginx mã nguồn mở phân giải tên upstream khi nạp cấu hình. Khi container backend được tạo lại (đổi IP), Nginx có thể giữ IP cũ → 502 cho tới khi reload/restart frontend; nếu `backend` không phân giải được lúc khởi động, Nginx không chạy. Quan trọng với test restart/failure (Gate M) và khi thêm upstream mới.
- **Kiểm chứng:** Lệnh ở mục 7 (#3).
- **Trạng thái:** OPEN → Gate M.

### F-A-013 — Seed (kèm tài khoản mặc định) có thể được nạp ở production

- **Mức độ:** Medium (cần xác minh)
- **Bằng chứng:** Dockerfile đặt `ENVIRONMENT=production`; entrypoint luôn gọi `init_db` (trừ khi `SKIP_DB_INIT=true`); theo PROJECT_GUIDE §5, `init.sql` nạp cả `03_seeds`; README công khai tài khoản seed (`admin@oldshop.com / admin123`, …).
- **Ảnh hưởng:** Lần khởi động đầu trên DB trống ở production có thể tạo tài khoản mặc định đã biết, nếu không có cơ chế tách seed theo môi trường hoặc đổi mật khẩu.
- **Hành động:** Xem `init_db.py` và `docs/deployment.md`. Liên quan Gate D.
- **Trạng thái:** OPEN → Gate D / M.

### F-A-014 — Compose local publish DB và backend ra mọi interface, credential mặc định

- **Mức độ:** Low (chỉ môi trường local)
- **Bằng chứng:** `"5433:5432"` và `"8000:8000"` không giới hạn `127.0.0.1`; mật khẩu mặc định `postgres`; `DEBUG: "true"`; `SECRET_KEY` mặc định `local-dev-secret-change-me`. Compose đã ghi chú đây là giá trị throwaway.
- **Ảnh hưởng:** Máy cùng mạng có thể truy cập Postgres bằng mật khẩu mặc định. Khi thêm MongoDB/MinIO không nên lặp lại mẫu "mở cổng + credential mặc định".
- **Đề xuất khi mở rộng:** bind `127.0.0.1:<port>:<port>`; credential qua `.env` không commit.
- **Trạng thái:** OPEN (thấp).

### F-A-015 — `--forwarded-allow-ips='*'` kết hợp port backend được publish

- **Mức độ:** Low (cần xem compose production)
- **Bằng chứng:** CMD backend có `--proxy-headers --forwarded-allow-ips='*'`; compose local publish cổng `8000`.
- **Ảnh hưởng:** Gọi thẳng cổng 8000 có thể giả `X-Forwarded-For`, làm sai IP trong log và `system_log.ip_address`. Ở production phụ thuộc việc `deploy/docker-compose.yml` có publish cổng backend hay không (chưa xem).
- **Trạng thái:** OPEN → Gate M.

### F-A-016 — Nginx: header bảo mật bị mất ở `/media/` và vị trí file tĩnh

- **Mức độ:** Low (cần `curl -I` xác nhận)
- **Bằng chứng:** `add_header` ở cấp `location` thay thế toàn bộ `add_header` cấp `server`. File đã ghi chú điều này và lặp lại header ở `location /`, nhưng `location ^~ /media/` và regex file tĩnh chỉ có `add_header Cache-Control` mà **không** lặp lại `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
- **Ảnh hưởng:** Nội dung người dùng upload qua `/media/` được phục vụ không kèm `nosniff` từ Nginx (backend có thể tự thêm; chưa xác minh). Cần tính khi chuyển sang MinIO.
- **Kiểm chứng:** Lệnh ở mục 7 (#4).
- **Trạng thái:** OPEN → Gate G.

### F-A-017 — Nginx `/media/`: cache 7 ngày và kết nối upstream

- **Mức độ:** Low
- **Bằng chứng:** `expires 7d` và `Cache-Control: public`; location này không có `proxy_http_version 1.1` và `Connection ""` như `/api/`, nên `keepalive 16` của upstream không phát huy với `/media/`.
- **Ảnh hưởng:** Nếu sau này ghi đè object giữ nguyên URL (ví dụ avatar), client/CDN có thể giữ bản cũ tới 7 ngày. Cần tính chiến lược URL/versioning ở Gate G.
- **Trạng thái:** OPEN → Gate G.

### F-A-018 — Compose chưa dùng healthcheck để điều kiện hóa thứ tự khởi động

- **Mức độ:** Low / Info
- **Bằng chứng:** Backend và frontend có `HEALTHCHECK` trong Dockerfile, nhưng `depends_on` của `frontend` chỉ chờ backend khởi động, không chờ healthy. Backend chờ Postgres healthy (đúng).
- **Ảnh hưởng:** Khi thêm MongoDB/MinIO nên dùng `condition: service_healthy` để thứ tự khởi động có ý nghĩa.
- **Trạng thái:** OPEN → Gate M.

### F-A-019 — `/api/docs` và `/api/openapi.json` đi qua Nginx

- **Mức độ:** Info (cần xác minh cấu hình production)
- **Bằng chứng:** Docs mặc định ở `/api/docs`, `/api/openapi.json` (PROJECT_GUIDE §4.1) nằm dưới `/api/` nên được `location ^~ /api/` proxy. `/metrics`, `/health` không được Nginx proxy (tốt).
- **Hành động:** Xác nhận ở Gate F/M xem production có tắt hoặc hạn chế docs không.
- **Trạng thái:** OPEN → Gate F.

### F-A-020 — Chênh lệch tài liệu giữa README và PROJECT_GUIDE

- **Mức độ:** Info
  - `psql -f init.sql`: README không có `-v ON_ERROR_STOP=1`, PROJECT_GUIDE có (lỗi giữa chừng ở lệnh README có thể để DB nạp dở).
  - Lệnh ruff: README `ruff check . && ruff format --check .`, PROJECT_GUIDE giới hạn `app tests scripts`.
  - README nói "Database tuning is passed to the Postgres container as flags", nhưng compose local không có flag nào (có thể thuộc compose production, chưa xem).
  - README dùng cổng test PostgreSQL 5432, compose local publish 5433 (khác ngữ cảnh, cần phân biệt khi viết test mới).
- **Trạng thái:** Info — thống nhất tài liệu khi cập nhật docs.

### F-A-021 — `.gitignore` loại mọi file Office/PDF

- **Mức độ:** Low / Process
- **Bằng chứng:** `*.docx`, `*.doc`, `*.pptx`, `*.xlsx`, `*.pdf`, `*.local.md` bị ignore (kèm comment "never belong in the repo"). `.dockerignore` chỉ loại `*.docx` ở gốc, không đồng bộ.
- **Ảnh hưởng:** Deliverable **Ngày 7** của plan (báo cáo, PPT) và sơ đồ dạng PDF sẽ không được commit nếu đặt trong repo. Cần quyết định nơi lưu (ngoài repo, `git add -f`, hoặc điều chỉnh quy tắc) trước Ngày 7. Nếu MongoDB/MinIO dùng bind mount thay vì named volume, cần thêm đường dẫn dữ liệu vào `.gitignore`.
- **Trạng thái:** OPEN (thấp).

### F-A-022 — Nhiều replica backend sẽ cùng chạy `init_db`

- **Mức độ:** Low
- **Bằng chứng:** `init_db` chạy trong entrypoint của **mỗi** container trước `exec "$@"`.
- **Ảnh hưởng:** Với 1 replica (compose hiện tại) không có vấn đề; nếu scale nhiều replica lần đầu trên DB trống có thể chạy đua khi nạp schema. Liên quan thiết kế migration (F-A-002).
- **Trạng thái:** OPEN → thiết kế migration.

---

## 5. Decision log

| ID | Quyết định | Trạng thái |
|---|---|---|
| D-A-001 | Giữ PostgreSQL hiện tại làm relational/transactional source of truth | CONFIRMED |
| D-A-002 | Giữ quy ước SQL-first | CONFIRMED |
| D-A-003 | Không coi `init_db.py`/entrypoint là migration mechanism | CONFIRMED |
| D-A-004 | Chưa thêm MongoDB/MinIO ở Gate A | DEFERRED — thiết kế ở các Gate sau |
| D-A-005 | Chưa thay đổi media routing/Nginx ở Gate A | DEFERRED — Gate G |
| D-A-006 | Giữ root Docker build context cho backend do cần `database/` | CONFIRMED |
| D-A-007 | Giữ backend non-root và frontend Nginx unprivileged | CONFIRMED |
| D-A-008 | Chỉ xem xét thay đổi `.dockerignore` khi có nhu cầu build cụ thể; khi xem xét phải kiểm tra riêng context của frontend (F-A-011) | CONFIRMED (cập nhật) |
| D-A-009 | Không thay đổi cấu hình Nginx/Compose/Docker ở Gate A cho các finding F-A-011 → F-A-019; xử lý ở Gate G/M sau khi xác minh | DEFERRED |
| D-A-010 | Dịch vụ mới (MongoDB/MinIO) không dùng credential mặc định, không mở cổng ra mọi interface | PROPOSED |
| D-A-011 | Dịch vụ mới phải có `healthcheck` và `depends_on` dùng `service_healthy` | PROPOSED |
| D-A-012 | Xác minh `init_db.py` và hành vi seed ở production trước khi chốt migration (F-A-002, F-A-013) | REQUIRED |
| D-A-013 | Chốt nơi lưu deliverable Office/PDF (báo cáo, PPT) trước Ngày 7 (F-A-021) | REQUIRED |
| D-A-014 | Test restart/failure phải gồm kịch bản tạo lại backend và kiểm tra Nginx (F-A-012) | REQUIRED |

---

## 6. Việc phải chuyển tiếp sang các Gate sau

| Việc | Gate / giai đoạn | Tiêu chí hoàn tất |
|---|---|---|
| Audit PK/FK/UNIQUE/CHECK/DEFAULT/nullability/index và quan hệ bảng | Gate B | Có inventory dựa trên SQL thực tế |
| Audit functions/triggers và transaction dependencies | Gate C | Xác định business rules bị ảnh hưởng |
| Audit seeds và media assets; xác minh seed ở production (F-A-013) | Gate D | Có danh sách dữ liệu/asset cần bảo toàn; biết seed có chạy ở production không |
| Audit ORM/CRUD/query | Gate E | Có query/workload inventory |
| Audit API contract và schema; docs công khai (F-A-019) | Gate F | Biết API nào đọc/ghi store nào |
| Thiết kế MinIO, migration media và URL compatibility; header bảo mật và cache `/media/` (F-A-003, 016, 017) | Gate G | Có storage flow, migration/verification/test |
| Thiết kế MongoDB ownership, collections, JSON schema và connection | Gate H–I | Có quyết định data ownership và test |
| Thiết kế index/fragmentation | Gate J–L | Có workload justification, reconstruction và đo lường |
| Compose/deployment/backup/restore/failure model; F-A-012, 014, 015, 018, 022 | Gate M | Có sơ đồ, runbook, test restart/failure |
| Frontend compatibility; xác minh `frontend/.dockerignore` (F-A-011) | Gate N | API/media contract không bị phá; build frontend tái lập |
| Regression/integration/CI | Gate O | Có test và evidence |
| Nơi lưu báo cáo/PPT (F-A-021) | Trước Ngày 7 | Có quyết định lưu trữ rõ ràng |

---

## 7. Việc cần chạy thử/xác minh để chốt các finding "cần xác minh"

| # | Kiểm tra | Chốt finding |
|---|---|---|
| 1 | Ở gốc repo: `docker build -f - . <<'EOF'` với nội dung `FROM busybox`, `COPY . /ctx`, `RUN find /ctx -name '*.md' \| head` | F-A-010 |
| 2 | Kiểm tra `frontend/.dockerignore`; chạy tương tự với context `./frontend` | F-A-011 |
| 3 | `docker compose up -d --force-recreate backend` rồi gọi `http://localhost:8080/api/...` | F-A-012 |
| 4 | `curl -sI http://localhost:8080/media/<file>` và `curl -sI` một file JS tĩnh | F-A-016, F-A-017 |
| 5 | Cung cấp `backend/scripts/init_db.py`, `docs/deployment.md`, `deploy/docker-compose.yml` | F-A-002 (xác minh trực tiếp), F-A-013, F-A-015, F-A-019 |
| 6 | `git check-ignore -v <file>` cho vài file mẫu (`.env`, `x.pdf`, `backend/media/a.png`) | F-A-009, F-A-021 |

---

## 8. Điều kiện đóng Gate A

Gate A có thể được ghi nhận là `CONDITIONAL PASS` khi lưu audit này cùng các finding và quyết định. Không nên diễn giải `CONDITIONAL PASS` thành việc toàn bộ kiến trúc mục tiêu đã sẵn sàng triển khai.

Trước khi chốt `READY FOR IMPLEMENTATION`, cần ít nhất:

- [ ] Có chiến lược migration database được thiết kế và duyệt.
- [ ] Hoàn tất audit schema, functions/triggers, seeds, CRUD/API và workload.
- [ ] Chốt data ownership giữa PostgreSQL, MongoDB và MinIO.
- [ ] Có ERD, fragmentation/index rationale và kế hoạch kiểm thử.
- [ ] Có backup/restore và rollback/recovery plan đã thử trên môi trường test.
- [ ] Xác minh các finding "cần xác minh" ở mục 7 (đặc biệt F-A-011, F-A-012, F-A-013).
- [ ] Quyết định nơi lưu deliverable Office/PDF (F-A-021).

---

## 9. Kết luận

**Gate A = `CONDITIONAL PASS`.**

Baseline hiện tại có các quyết định nền tảng cần giữ: PostgreSQL là nguồn dữ liệu quan hệ chính, SQL-first là quy ước quản lý schema, backend image cần `database/`, và các container ứng dụng chạy bằng user không đặc quyền.

Các rủi ro quan trọng cần xử lý trong các bước tiếp theo:

1. `init_db.py` không thể thay thế migration system (F-A-002), và cần xác minh việc nạp seed ở production (F-A-013).
2. Chuyển media sang MinIO sẽ tác động tới backend storage, URL frontend, Nginx (header, cache, upstream), Compose và kiểm thử (F-A-003, 016, 017).
3. Hai điểm vận hành cần chạy thử: Nginx giữ IP upstream cũ khi backend được tạo lại (F-A-012) và `.dockerignore` không áp dụng cho build frontend (F-A-011).

MongoDB/MinIO chưa có trong Compose là gap so với mục tiêu mới, không phải lỗi của kiến trúc cũ. Không thêm service hoặc thay đổi schema vội trước khi hoàn tất các Gate thiết kế.
