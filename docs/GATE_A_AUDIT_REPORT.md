# OldShop — Gate A Audit Report
## Repository, Runtime & Build Configuration

> **Gate:** A — Repository / Runtime / Build Configuration  
> **Kết quả:** `CONDITIONAL PASS`  
> **Trạng thái:** Đã ghi nhận baseline và các finding; chưa chốt `READY FOR IMPLEMENTATION`.  
> **Phạm vi:** Báo cáo này ghi lại kết quả Gate A được cung cấp trong phiên làm việc. Đây không phải kết quả chạy lại toàn bộ repository hoặc xác minh trực tiếp môi trường production.

---

## 1. Mục tiêu và phạm vi

Gate A xác lập baseline repository/runtime trước khi thiết kế tích hợp PostgreSQL, MongoDB và MinIO. Các hạng mục đã được đánh giá trong kết quả audit được cung cấp:

- `.gitignore`
- `.dockerignore`
- `README.md`
- `PROJECT_GUIDE.md`
- `docker-compose.yml`
- `backend/Dockerfile`
- `backend/docker-entrypoint.sh`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

Các nội dung được xem xét gồm cấu hình build context, service và volume, bootstrap database, cách phục vụ media, runtime privilege và sự phù hợp với quy ước SQL-first.

### Giới hạn

Gate A **không** audit toàn bộ schema/query, không xác định fragment key hoặc index cụ thể, và không triển khai MongoDB/MinIO. Các quyết định đó phải chờ các Gate liên quan hoàn tất.

---

## 2. Tóm tắt kết quả

| File / thành phần | Trạng thái | Kết luận |
|---|---|---|
| `.gitignore` | PASS | Có các quy tắc loại trừ secrets, cache, runtime media và artifact |
| `.dockerignore` | CONDITIONAL PASS | Quy tắc `*.md` loại Markdown khỏi build context; hiện chưa được xác định là lỗi build |
| `README.md` | PASS | Mô tả baseline PostgreSQL và luồng API/media hiện tại |
| `PROJECT_GUIDE.md` | PASS | Xác nhận SQL-first và vai trò bootstrap của `init_db.py` |
| `docker-compose.yml` | PASS WITH FINDING | Hiện chỉ có PostgreSQL, Backend, Frontend; chưa có MongoDB/MinIO |
| `backend/Dockerfile` | PASS | Build context root và copy `database/` phù hợp với SQL-first |
| `backend/docker-entrypoint.sh` | PASS WITH RISK | Gọi bootstrap DB; không phải migration system |
| `frontend/Dockerfile` | PASS | Angular build, Nginx unprivileged runtime |
| `frontend/nginx.conf` | PASS WITH FOLLOW-UP | `/api/` và `/media/` proxy tới backend; cần đánh giá lại media flow khi có MinIO |

**Kết luận:** Không có lỗi kiến trúc nghiêm trọng cần sửa ngay theo kết quả audit đã cung cấp. Các khoảng trống MongoDB/MinIO là khoảng cách so với kiến trúc mục tiêu, chưa phải bug của baseline hiện tại.

---

## 3. Findings chi tiết

### F-A-001 — Compose chưa có MongoDB và MinIO

- **Mức độ:** Medium / Architecture gap
- **Bằng chứng được ghi nhận:** `docker-compose.yml` hiện có các service `postgres`, `backend`, `frontend`; volume hiện có `pg_data` và `media`.
- **Ảnh hưởng:** Chưa thể chạy hoặc kiểm thử tích hợp đa kho dữ liệu trong local Compose.
- **Quyết định:** Không thêm service tại Gate A. Trước hết phải hoàn thành data ownership và các thiết kế ở Gate B–H, gồm collection MongoDB, object/bucket MinIO, metadata/reference, network, volume và backup.
- **Trạng thái:** OPEN — chuyển tiếp sang các Gate thiết kế.

### F-A-002 — `init_db.py` là bootstrap, không phải migration

- **Mức độ:** High / Data integrity risk
- **Bằng chứng được ghi nhận:** `backend/docker-entrypoint.sh` chạy `python -m scripts.init_db` trừ khi `SKIP_DB_INIT=true`. Theo `PROJECT_GUIDE.md`, script bootstrap bỏ qua `init.sql` nếu schema hiện hữu đã được nhận diện.
- **Ảnh hưởng:** Sửa SQL source rồi restart container không đảm bảo schema của database đang tồn tại được cập nhật. Có nguy cơ code mới chạy với schema cũ hoặc migration không được áp dụng.
- **Quyết định bắt buộc:** Thiết kế quy trình migration/update SQL có kiểm soát, có version/history, precondition, backup, verify và rollback/recovery plan.
- **Trạng thái:** OPEN — là điều kiện trước khi áp dụng thay đổi schema lên database đã có dữ liệu.

### F-A-003 — `/media/` đang proxy trực tiếp tới Backend

- **Mức độ:** Medium / Architecture follow-up
- **Bằng chứng được ghi nhận:** `frontend/nginx.conf` proxy `/media/` tới backend; baseline dùng local filesystem/Docker media volume.
- **Ảnh hưởng:** Khi chuyển object storage sang MinIO, phải bảo đảm URL media hiện có, quyền truy cập, upload/download/delete và frontend vẫn tương thích.
- **Quyết định:** Chưa sửa Nginx ở Gate A. Gate G phải đánh giá phương án `Angular → FastAPI → MinIO` hoặc luồng presigned URL phù hợp với yêu cầu bảo mật và API contract.
- **Trạng thái:** OPEN — Gate G.

### F-A-004 — PostgreSQL là database chính hiện tại

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng được ghi nhận:** README và PROJECT_GUIDE mô tả PostgreSQL 16 là database chính; schema, function/trigger và seed được quản lý trong `database/`.
- **Ảnh hưởng:** Logic nghiệp vụ và transaction hiện hữu phụ thuộc PostgreSQL.
- **Quyết định:** Giữ PostgreSQL làm relational/transactional source of truth. Không chuyển dữ liệu giao dịch sang MongoDB chỉ để đáp ứng yêu cầu đa mô hình.
- **Trạng thái:** CONFIRMED.

### F-A-005 — SQL-first architecture phải được giữ nguyên

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng được ghi nhận:** `database/` là nguồn schema chính; ORM chỉ mapping.
- **Ảnh hưởng:** Thay đổi bảng, constraint, index, function hoặc trigger cần bắt đầu từ SQL, rồi đồng bộ ORM/Pydantic/CRUD/API/test.
- **Quyết định:** Giữ quy ước SQL-first trong các Gate tiếp theo.
- **Trạng thái:** CONFIRMED.

### F-A-006 — Backend Docker build context là repository root

- **Mức độ:** Baseline / Confirmed
- **Bằng chứng được ghi nhận:** Compose dùng `context: .` và `dockerfile: backend/Dockerfile`; Dockerfile copy `database/` vào image.
- **Ảnh hưởng:** Đổi build context mà không cập nhật đường dẫn/copy có thể làm backend image thiếu SQL source.
- **Quyết định:** Giữ root build context, trừ khi có thiết kế build mới được kiểm thử đầy đủ.
- **Trạng thái:** CONFIRMED.

### F-A-007 — Backend runtime chạy non-root

- **Mức độ:** Security positive
- **Bằng chứng được ghi nhận:** `backend/Dockerfile` chuyển sang user `app`.
- **Ảnh hưởng:** Giảm quyền mặc định của tiến trình ứng dụng.
- **Quyết định:** Giữ hành vi non-root; khi thêm volume/bucket/client phải kiểm tra quyền truy cập tương thích.
- **Trạng thái:** CONFIRMED.

### F-A-008 — Frontend Nginx chạy unprivileged

- **Mức độ:** Security positive
- **Bằng chứng được ghi nhận:** Frontend runtime dùng `nginx-unprivileged` và expose port 8080.
- **Ảnh hưởng:** Phù hợp với runtime không cần quyền root.
- **Quyết định:** Giữ cấu hình này; kiểm thử lại nếu thay đổi port hoặc proxy.
- **Trạng thái:** CONFIRMED.

### F-A-009 — `.gitignore` bảo vệ secrets/runtime artifacts

- **Mức độ:** Positive
- **Bằng chứng được ghi nhận:** Có quy tắc loại `.env`/`.env.*` nhưng giữ `.env.example`, private keys, cache/virtualenv, `backend/media/`, ML artifacts, dumps, backups và file IDE/system.
- **Ảnh hưởng:** Giảm nguy cơ commit nhầm secrets hoặc dữ liệu runtime.
- **Quyết định:** Không cần sửa ở Gate A theo kết quả hiện có. Khi bổ sung cấu hình MongoDB/MinIO, vẫn phải dùng biến môi trường/secret management và cập nhật example không chứa credential thật.
- **Trạng thái:** PASS.

### F-A-010 — `.dockerignore` loại `*.md`

- **Mức độ:** Low / Conditional
- **Bằng chứng được ghi nhận:** `.dockerignore` có quy tắc `*.md`, nhưng Dockerfile hiện không cần Markdown để build runtime; thư mục `database/` không bị loại.
- **Ảnh hưởng:** Markdown bị loại khỏi Docker build context. Nếu Dockerfile hoặc bước build tương lai cần tài liệu Markdown thì build có thể thiếu file.
- **Quyết định:** Chưa cần sửa ngay. Khi thêm `COPY` hoặc build step phụ thuộc Markdown, rà soát lại `.dockerignore`.
- **Trạng thái:** CONDITIONAL PASS.

---

## 4. Decision log

| ID | Quyết định | Trạng thái |
|---|---|---|
| D-A-001 | Giữ PostgreSQL hiện tại làm relational/transactional source of truth | CONFIRMED |
| D-A-002 | Giữ quy ước SQL-first | CONFIRMED |
| D-A-003 | Không coi `init_db.py`/entrypoint là migration mechanism | CONFIRMED |
| D-A-004 | Chưa thêm MongoDB/MinIO ở Gate A | DEFERRED — thiết kế ở các Gate sau |
| D-A-005 | Chưa thay đổi media routing/Nginx ở Gate A | DEFERRED — Gate G |
| D-A-006 | Giữ root Docker build context cho backend do cần `database/` | CONFIRMED |
| D-A-007 | Giữ backend non-root và frontend Nginx unprivileged | CONFIRMED |
| D-A-008 | Chỉ xem xét thay đổi `.dockerignore` khi có nhu cầu build cụ thể | CONFIRMED |

---

## 5. Việc phải chuyển tiếp sang các Gate sau

| Việc | Gate / giai đoạn | Tiêu chí hoàn tất |
|---|---|---|
| Audit PK/FK/UNIQUE/CHECK/DEFAULT/nullability/index và quan hệ bảng | Gate B | Có inventory dựa trên SQL thực tế |
| Audit functions/triggers và transaction dependencies | Gate C | Xác định business rules bị ảnh hưởng |
| Audit seeds và media assets | Gate D | Có danh sách dữ liệu/asset cần bảo toàn |
| Audit ORM/CRUD/query | Gate E | Có query/workload inventory |
| Audit API contract và schema | Gate F | Biết API nào đọc/ghi store nào |
| Thiết kế MinIO, migration media và URL compatibility | Gate G | Có storage flow, migration/verification/test |
| Thiết kế MongoDB ownership, collections, JSON schema và connection | Gate H–I | Có quyết định data ownership và test |
| Thiết kế index/fragmentation | Gate J–L | Có workload justification, reconstruction và đo lường |
| Compose/deployment/backup/restore/failure model | Gate M | Có sơ đồ và runbook |
| Frontend compatibility | Gate N | API/media contract không bị phá |
| Regression/integration/CI | Gate O | Có test và evidence |

---

## 6. Điều kiện đóng Gate A

Gate A có thể được ghi nhận là `CONDITIONAL PASS` khi lưu audit này cùng các finding và quyết định. Không nên diễn giải `CONDITIONAL PASS` thành việc toàn bộ kiến trúc mục tiêu đã sẵn sàng triển khai.

Trước khi chốt `READY FOR IMPLEMENTATION`, cần ít nhất:

- [ ] Có chiến lược migration database được thiết kế và duyệt.
- [ ] Hoàn tất audit schema, functions/triggers, seeds, CRUD/API và workload.
- [ ] Chốt data ownership giữa PostgreSQL, MongoDB và MinIO.
- [ ] Có ERD, fragmentation/index rationale và kế hoạch kiểm thử.
- [ ] Có backup/restore và rollback/recovery plan đã thử trên môi trường test.

---

## 7. Kết luận

**Gate A = `CONDITIONAL PASS`.**

Baseline hiện tại có các quyết định nền tảng cần giữ: PostgreSQL là nguồn dữ liệu quan hệ chính, SQL-first là quy ước quản lý schema, backend image cần `database/`, và các container ứng dụng chạy bằng user không đặc quyền.

Hai rủi ro quan trọng cần xử lý trong các bước tiếp theo là:

1. `init_db.py` không thể thay thế migration system.
2. Chuyển media sang MinIO sẽ tác động tới backend storage, URL frontend, Nginx, Compose và kiểm thử.

MongoDB/MinIO chưa có trong Compose là gap so với mục tiêu mới, không phải lỗi của kiến trúc cũ. Không thêm service hoặc thay đổi schema vội trước khi hoàn tất các Gate thiết kế.
