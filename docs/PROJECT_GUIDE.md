# OldShop — Project Structure & Engineering Notes

> **Mục đích:** tài liệu ngữ cảnh cho các tác vụ AI/dev tiếp theo. Đọc file này trước khi sửa mã để hiểu các tầng kiến trúc, vị trí chức năng, cách chạy/test và các quy ước quan trọng.
>
> **Phạm vi:** được tổng hợp từ mã nguồn trong `Epic-Ecommerce-FastAPI-main(1).zip`. Tên nhánh, cấu hình triển khai hoặc trạng thái thực tế của máy chủ có thể khác với bản ZIP.

## 1. Tổng quan dự án

**OldShop** là marketplace bán hàng đã qua sử dụng, gồm frontend Angular và REST API FastAPI. Người mua duyệt sản phẩm, quản lý giỏ hàng, đặt đơn COD/PayPal; người bán đăng sản phẩm và xử lý đơn; moderator duyệt sản phẩm/đánh giá và xử lý vi phạm; admin quản lý moderator, voucher, phản hồi và thống kê.

**Stack chính**

- Backend: Python, FastAPI, SQLAlchemy, Pydantic Settings, JWT, pytest, Ruff.
- Database: PostgreSQL 16; schema, PL/pgSQL functions/triggers, dữ liệu mẫu được quản lý bằng SQL trong `database/`.
- Frontend: Angular 21 standalone components, TypeScript, RxJS, Bootstrap 5, Bootstrap Icons, Chart.js, SweetAlert2.
- Tích hợp: PayPal Orders API, SMTP/OTP, Google Apps Script relay cho form liên hệ, mô hình scikit-learn tùy chọn để chấm điểm rủi ro.
- Hạ tầng: Docker Compose, Nginx, Caddy, GitHub Actions, Prometheus/Grafana; Loki/Promtail mặc định và tùy chọn ELK.

## 2. Bản đồ kiến trúc

```text
Browser
  │ HTTPS (production) / HTTP (local)
  ▼
Caddy (TLS, production)
  ▼
Nginx + Angular SPA
  ├── /api/*   ───────────────► FastAPI / Uvicorn
  └── /media/* ───────────────► FastAPI static media
                                   ├── PostgreSQL
                                   ├── PayPal Orders API
                                   ├── SMTP (tùy chọn)
                                   ├── Google Apps Script (tùy chọn, HMAC-signed)
                                   └── fraud model artifacts (tùy chọn)

FastAPI metrics/logs ──► Prometheus / Grafana
Docker logs ──────────► Promtail + Loki (mặc định) hoặc Filebeat + ELK
```

Luồng API thường gặp:

1. Angular component gọi service trong `frontend/src/app/core/services/` hoặc `frontend/src/app/shared/services/`.
2. Request đi qua `authInterceptor` để gắn Bearer token (nếu có).
3. FastAPI router xử lý request; dependencies kiểm tra phiên đăng nhập và vai trò.
4. CRUD layer thực hiện truy vấn/nghiệp vụ với SQLAlchemy; service layer xử lý tích hợp bên ngoài hoặc tác vụ chuyên biệt.
5. PostgreSQL là nguồn dữ liệu chính; schema và trigger được định nghĩa bằng SQL trong `database/`.

## 3. Cấu trúc thư mục cấp cao

```text
.
├── README.md                     # Giới thiệu, hướng dẫn chạy nhanh
├── docker-compose.yml            # Stack local: PostgreSQL, backend, frontend
├── .github/workflows/
│   ├── ci.yml                    # Lint/test/build
│   └── deploy.yml                # Build/push images và deploy VPS
├── backend/                      # FastAPI
│   ├── app/
│   │   ├── api/                  # Dependencies và router tổng
│   │   │   └── v1/               # REST endpoints theo domain
│   │   ├── core/                 # Settings, DB engine, security, logging, errors
│   │   ├── crud/                 # Truy vấn dữ liệu và nghiệp vụ
│   │   ├── models/               # SQLAlchemy ORM mapping
│   │   ├── schemas/              # Pydantic request/response schema
│   │   ├── services/             # Tích hợp và dịch vụ chuyên biệt
│   │   └── main.py               # Tạo FastAPI app, middleware, probes, media, metrics
│   ├── scripts/init_db.py        # Bootstrap database + seed media
│   ├── tests/                    # API integration tests
│   ├── .env.example
│   ├── requirements*.txt         # Dependencies khai báo và bản lock
│   └── Dockerfile
├── database/                     # Nguồn schema/seed chính thức (SQL-first)
│   ├── init.sql                  # Đầu mối nạp toàn bộ SQL theo thứ tự
│   ├── config/
│   ├── 01_schema/                # Tables, indexes, constraints
│   ├── 02_functions/             # PL/pgSQL functions/triggers
│   └── 03_seeds/                 # Seed data và ảnh mẫu
├── frontend/                     # Angular SPA và Nginx
│   ├── src/app/core/             # Auth, guards, interceptor, models, utils
│   ├── src/app/features/         # UI theo nhóm người dùng/chức năng
│   ├── src/app/shared/services/  # API clients theo domain
│   ├── src/environments/         # API/media URL local và production
│   ├── nginx.conf
│   ├── package.json
│   └── Dockerfile
├── integrations/google-apps-script/ # Apps Script relay cho contact/helpdesk
├── deploy/                      # Compose production, Caddy, monitoring, logging, scripts
└── docs/deployment.md            # Runbook triển khai VPS
```

## 4. Backend: nơi cần tìm khi làm việc

### 4.1 API và quyền truy cập

- `backend/app/main.py`: khởi tạo ứng dụng, CORS, access log/request ID, exception handlers, health/readiness, `/media` và `/metrics`.
- `backend/app/api/router.py`: include router v1. Khi thêm domain/router mới, kiểm tra cả file này.
- `backend/app/api/deps.py`: dependency lấy DB session, current user, optional user và guard theo vai trò.
- `backend/app/api/v1/`: endpoint theo domain.

API được gắn prefix tổng `settings.API_V1_STR`, mặc định là **`/api/v1`**. Các router hiện có:

| Router | Prefix | Trách nhiệm chính |
|---|---|---|
| `auth.py` | `/auth` | Register, login, `/me`, quên/đặt lại mật khẩu, OTP |
| `users.py` | `/users` | Hồ sơ, đổi mật khẩu, avatar, sổ địa chỉ, dashboard seller và quản lý user |
| `categories.py` | `/categories` | Category tree, tạo/sửa/xóa/restore |
| `products.py` | `/products` | Catalogue, chi tiết, đăng/sửa sản phẩm, review, trạng thái/moderation |
| `cart.py` | `/cart` | Đọc giỏ hàng, thêm/sửa/xóa item, xóa giỏ |
| `orders.py` | `/orders` | Đơn hàng, payment methods, voucher, checkout và PayPal capture |
| `moderator.py` | `/moderator` | Duyệt sản phẩm, báo cáo vi phạm, ban/lock user, violation logs |
| `admin.py` | `/admin` | Thống kê, moderator, voucher, feedback và violation logs |
| `system.py` | `/system` | System feedback và contact form |

Các URL cụ thể nên được xác nhận trong router tương ứng trước khi dùng, vì cùng domain có thể có nhiều route và quyền khác nhau. API docs mặc định ở **`/api/docs`**, ReDoc ở `/api/redoc`, OpenAPI JSON ở `/api/openapi.json`.

### 4.2 Các tầng backend

- **`core/config.py`**: `Settings` từ biến môi trường / `.env`; gồm DB, secret, CORS, media, SMTP, PayPal, fraud artifacts, Apps Script. `settings` được khởi tạo lúc import.
- **`core/database.py`**: SQLAlchemy `engine`, `SessionLocal`, `get_db()` và `ping_database()`.
- **`core/security.py`**: hash/verify password, tạo và giải mã JWT.
- **`core/constants.py`**: enum số được đồng bộ với DB (role, trạng thái product/order/transaction, payment method).
- **`core/exceptions.py`**: lỗi nghiệp vụ (`AppError` và các lớp con).
- **`core/logging.py`**: cấu hình logging và context request ID.
- **`crud/`**: thao tác dữ liệu và một phần business rule; `base.py` có CRUD generic, các file còn lại theo domain.
- **`models/`**: ORM mapping bảng SQL; `models/__init__.py` gom/re-export models.
- **`schemas/`**: Pydantic input/output; thêm/đổi response cần kiểm tra cả schema và client Angular tương ứng.
- **`services/storage.py`**: validate/ghi/xóa ảnh; media URL thường ở dạng `/media/...`.
- **`services/paypal.py`**: PayPal Orders v2, đổi VND→USD theo tỷ giá cấu hình.
- **`services/fraud_detection.py`**: hard limit và tùy chọn IsolationForest/scaler artifacts.
- **`services/mail.py`**: gửi mail/OTP; phụ thuộc cấu hình SMTP.
- **`services/contact_relay.py`**: relay contact sang Apps Script có chữ ký HMAC.
- **`scripts/init_db.py`**: chờ PostgreSQL, tạo DB nếu cần, nạp `database/init.sql` nếu schema chưa tồn tại, sao chép ảnh mẫu.

### 4.3 Phân quyền và hằng số cần giữ đồng bộ

`RoleId` trong `backend/app/core/constants.py` đang định nghĩa:

- `ADMIN = 1`
- `MODERATOR = 2`
- `USER = 3`

Trạng thái product: `PENDING=0`, `APPROVED=1`, `REJECTED=2`, `SOLD_OUT=3`. Trạng thái order và transaction cũng là enum số. `REPORT_RATING = 0` nghĩa là đánh giá có rating 0 được dùng như **báo cáo vi phạm**, không phải review thông thường.

Khi sửa role/status/payment method, kiểm tra cùng lúc seed SQL, constraint/trigger, API logic, test và frontend. Frontend guard chỉ nhằm điều hướng UI; **không thay thế authorization ở backend**.

## 5. Database: SQL-first, không tự ý coi ORM là schema master

`database/init.sql` điều phối thứ tự nạp:

1. `config/database_config.sql`: timezone/encoding/search path và extension (`uuid-ossp`, `pgcrypto`, `pg_trgm`).
2. `01_schema/`: bảng, khóa ngoại, index và constraint.
3. `02_functions/`: password/business/utility/audit functions và triggers.
4. `03_seeds/`: roles, categories, payment methods, vouchers, users, products/images, contacts, carts, orders, violation logs.
5. `ANALYZE` sau khi nạp dữ liệu.

Các domain/tables chính gồm users/roles, categories/products/product images, vouchers, payment methods, contact info, orders/order details/transactions, shopping carts/items, reviews, system logs/feedback và violation logs.

### Quy tắc thay đổi database

- Thay đổi bảng/constraint/index/function/trigger phải bắt đầu từ SQL trong `database/`, rồi cập nhật ORM mapping, Pydantic schema, CRUD/API và test nếu liên quan.
- `backend/app/models/` **chỉ ánh xạ** schema; README và module models ghi rõ đây là SQL-first, không dùng ORM để tạo schema chuẩn.
- `backend/scripts/init_db.py` kiểm tra `public."user"`; nếu bảng đã tồn tại, script **bỏ qua toàn bộ `init.sql`**. Vì vậy khởi động lại container không phải migration và sẽ không tự áp dụng thay đổi schema cho DB hiện hữu.
- Với thay đổi schema đang phát triển, dùng DB thử nghiệm sạch hoặc chạy migration/SQL cập nhật có kiểm soát. Tránh chạy lại toàn bộ seed/init lên DB có dữ liệu người dùng mà chưa hiểu tác động.
- Seed có tài khoản và dữ liệu dùng để dev/test. Không dùng mật khẩu mặc định ngoài môi trường local/test.
- Seed media được copy chỉ khi file đích chưa tồn tại; media tải lên thật nằm ngoài mã nguồn và thường được lưu trong Docker volume.

## 6. Frontend Angular

### 6.1 Khởi động và routing

- `src/main.ts`, `src/app/app.ts`, `app.html`, `app.scss`: bootstrap và shell ứng dụng.
- `src/app/app.config.ts`: router, HttpClient/interceptor và `APP_INITIALIZER` chờ trạng thái xác thực.
- `src/app/app.routes.ts`: route cấp cao; dùng lazy loading cho các nhóm auth/customer/admin/moderator/seller.
- Mỗi component thường có `.ts`, `.html`, `.scss`, đôi khi có `.spec.ts`.

### 6.2 Feature folders

- `features/home/`, `features/shop/`: trang chủ, catalogue và product detail.
- `features/auth/`: login, register và các route xác thực.
- `features/customer/`: cart, checkout, my orders, profile.
- `features/seller/`: dashboard, quản lý sản phẩm/đơn, profile.
- `features/moderator/`: dashboard, product/review/user moderation, profile.
- `features/admin/`: dashboard, category/moderator/voucher management, violation logs, profile.
- `features/contact/`: contact form.
- `layout/components/`: layout components dùng chung như footer/header (kiểm tra thư mục khi cần thêm UI dùng chung).

### 6.3 Core và API services

- `core/guards/auth.guard.ts`: guard đăng nhập/guest/admin/moderator.
- `core/interceptors/auth.interceptor.ts`: lấy token từ `sessionStorage` và gắn `Authorization: Bearer ...`; có whitelist cho một số endpoint auth.
- `core/services/auth.service.ts`: login/logout, profile hiện tại, role, đổi mật khẩu, OTP/reset, avatar.
- `core/services/cart.service.ts`: quản lý state cart và đồng bộ với backend; dùng `localStorage` để cache trạng thái UI.
- `core/services/payment.service.ts`: gọi API capture PayPal.
- `core/services/ui.service.ts`: thông báo/toast/alert chung.
- `core/models/`: TypeScript interfaces/models.
- `core/utils/media-url.ts`: chuyển đường dẫn `/media/...` thành URL phù hợp môi trường.
- `shared/services/`: các API clients theo domain (`admin`, `category`, `contact`, `moderator`, `order`, `product`).

**Lưu ý đồng bộ frontend/backend:** khi đổi path, HTTP method, tên field, enum, pagination hoặc response shape, cập nhật service/component và tests tương ứng. Đừng chỉ đổi API router rồi giả định UI vẫn tương thích.

### 6.4 Environment và media URL

`src/environments/environment.ts` (local):

- `apiUrl = http://localhost:8000/api/v1`
- `imageBaseUrl`/`imageUrl` trỏ `http://localhost:8000`

`environment.prod.ts` (production):

- `apiUrl = /api/v1`
- base URL ảnh để trống vì SPA, `/api` và `/media` cùng origin, Nginx reverse proxy sang backend.

Khi thêm endpoint, tránh hardcode hostname ở component; ưu tiên config và service hiện có. Khi sửa Nginx proxy, lưu ý `/api` phải giữ nguyên prefix theo cấu hình hiện tại.

## 7. Tích hợp và logic nghiệp vụ cần biết

### Giỏ hàng / tồn kho

README mô tả sản phẩm được **reserve tồn kho ngay khi thêm vào giỏ**; backend dùng row-level lock (`SELECT ... FOR UPDATE`) để xử lý cạnh tranh khi chỉ còn ít hàng. Khi sửa cart/order/stock, đọc kỹ CRUD, SQL trigger và integration tests để tránh bán vượt tồn hoặc giải phóng hàng hai lần.

### Thanh toán

- Hỗ trợ luồng COD và PayPal sandbox theo README.
- `services/paypal.py` gọi PayPal Orders v2; PayPal không hỗ trợ VND trong luồng này nên số tiền được đổi sang USD qua `USD_VND_RATE` (mặc định `25400`). Đây là tỷ giá cấu hình cố định, không phải tỷ giá trực tiếp thị trường.
- API capture cần xác thực order ID và xử lý trạng thái capture; không tin dữ liệu do browser gửi mà chưa xác minh ở backend.
- Enum `PaymentMethodId` có thêm MoMo/VNPay/Bank Transfer, nhưng sự hiện diện của enum/seed **không tự chứng minh** rằng các luồng tích hợp đó đã triển khai đầy đủ. Kiểm tra route, service và UI trước khi tuyên bố hỗ trợ.

### Fraud scoring

- `services/fraud_detection.py` dùng hard limit `100,000,000 VND`; mô hình `fraud_model.joblib` và `scaler.joblib` ở `FRAUD_MODEL_DIR` không được commit theo mô tả code.
- Thiếu artifacts thì app fallback về rule-based scoring, nên dev/CI vẫn chạy được.
- **Điểm cần kiểm tra nếu sửa fraud logic:** `_model_score()` chặn điểm tối đa ở `FRAUD_THRESHOLD = 0.9`, trong khi `is_fraud` được tính bằng `score > FRAUD_THRESHOLD`. Vì vậy điểm từ mô hình không thể vượt ngưỡng này theo cách viết hiện tại; nhánh hard limit vẫn đánh dấu fraud. Kiểm tra chủ đích/threshold và test trước khi thay đổi hành vi.

### Contact relay

Luồng: Angular `/contact` → `POST /api/v1/system/contact` → lưu PostgreSQL → background relay sang Apps Script nếu cấu hình. Backend ký HMAC-SHA256 với timestamp + payload; shared secret phải khớp giữa `GAS_SHARED_SECRET` và Script Properties `SHARED_SECRET`. URL Apps Script không nên đưa xuống frontend.

## 8. Cấu hình và chạy dự án

### Nhanh nhất: Docker Compose (local)

Ở thư mục gốc:

```bash
docker compose up --build
```

- Shop: `http://localhost:8080`
- API docs: `http://localhost:8000/api/docs`
- PostgreSQL được expose ra host ở `localhost:5433` (container port `5432`).
- Volume `pg_data` giữ DB; volume `media` giữ ảnh tải lên.

Compose local có secret/password mặc định chỉ dành cho phát triển. Hãy override bằng environment hoặc `.env` phù hợp khi cần.

### Chạy thủ công

```bash
# PostgreSQL: tạo DB rồi nạp schema/seed
createdb oldshop
(cd database && psql -d oldshop -v ON_ERROR_STOP=1 -f init.sql)

# Backend
cd backend
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env           # sửa DB credentials và SECRET_KEY
uvicorn app.main:app --reload

# Frontend (terminal khác)
cd frontend
npm ci
npm start                      # http://localhost:4200
```

Lưu ý: `Settings` đọc `.env` tương đối theo working directory khi được khởi động. Chạy backend từ `backend/` như các lệnh trên để `.env` ở `backend/.env` được nạp đúng.

### Biến môi trường nổi bật

Xem đầy đủ tại `backend/.env.example`, `backend/app/core/config.py` và `deploy/.env.example`.

- DB: `DATABASE_URL` hoặc `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.
- Security: `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
- App/API: `ENVIRONMENT`, `DEBUG`, `CORS_ORIGINS`, `LOG_LEVEL`, `LOG_FORMAT`.
- Media: `MEDIA_DIR`, `MAX_UPLOAD_BYTES` (mặc định 2 MiB), chỉ cho phép phần mở rộng ảnh được định nghĩa trong `services/storage.py`.
- Tùy chọn: `SMTP_USER`/`SMTP_PASSWORD`, `PAYPAL_CLIENT_ID`/`PAYPAL_SECRET`/`PAYPAL_API_URL`, `GAS_WEBHOOK_URL`/`GAS_SHARED_SECRET`, `FRAUD_MODEL_DIR`.

**Cảnh báo bootstrap:** `core/config.py` hỗ trợ `DATABASE_URL`, nhưng `scripts/init_db.py` mở kết nối bootstrap bằng `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`. Nếu chỉ cấu hình `DATABASE_URL` mà để các `DB_*` mặc định, hãy kiểm tra đường bootstrap DB có đang trỏ đúng máy chủ/database hay không.

## 9. Test, lint và CI

Backend tests là **integration tests dùng PostgreSQL thật** với schema và seed từ `database/init.sql`, không chỉ là mock đơn vị.

```bash
createdb oldshop_test
(cd database && psql -d oldshop_test -v ON_ERROR_STOP=1 -f init.sql)

cd backend
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/oldshop_test pytest
ruff check app tests scripts
ruff format --check app tests scripts
```

Nếu DB test của bạn dùng username/password/port khác, sửa `DATABASE_URL` tương ứng và xác nhận các biến `DB_*` khi cần chạy `scripts/init_db.py`. Không chạy test với DB chứa dữ liệu thật; seed/test có thể tạo hoặc thay đổi dữ liệu.

Frontend:

```bash
cd frontend
npm ci
npm test
npm run build -- --configuration production
```

CI (`.github/workflows/ci.yml`) chạy backend lint/test với PostgreSQL 16, build Angular production và (trên pull request) build Docker images. Python CI đang ghim **3.13**; frontend CI đang dùng **Node 20**. Nên theo version của workflow khi xử lý khác biệt môi trường.

## 10. Deployment và vận hành

- `deploy/docker-compose.yml`: production compose.
- `deploy/caddy/Caddyfile`: HTTPS/TLS và domain routing.
- `deploy/docker-compose.monitoring.yml`, `deploy/prometheus/`, `deploy/grafana/`: metrics, dashboards, alerts.
- `deploy/docker-compose.loki.yml`, `deploy/promtail/`, `deploy/loki/`: log stack mặc định.
- `deploy/docker-compose.elk.yml`, `deploy/elk/`: lựa chọn Elasticsearch/Kibana/Filebeat, tiêu tốn RAM hơn.
- `deploy/scripts/deploy.sh`, `bootstrap-vps.sh`, `backup-db.sh`, `restore-db.sh`, `switch-logging.sh`: các thao tác deploy, sao lưu/khôi phục và đổi log stack.
- `docs/deployment.md`: runbook VPS đầy đủ.

CI/deploy workflow build image và gắn tag theo commit SHA (cùng `latest`); rollback được thực hiện bằng cách deploy lại tag cũ. Trước khi thay đổi hạ tầng, đọc cả Compose, `.env.example`, scripts và runbook; giữ secret thực tế ngoài Git.

## 11. Checklist trước khi sửa một chức năng

1. Xác định domain/luồng UI ở `frontend/src/app/features/` và route của nó.
2. Tìm API client trong `core/services/` hoặc `shared/services/`, kiểm tra URL/method/shape đang dùng.
3. Tìm endpoint trong `backend/app/api/v1/`; kiểm tra dependencies/role guards.
4. Lần theo CRUD → ORM model → schema Pydantic → bảng/function/trigger SQL.
5. Nếu đổi schema hoặc enum, đồng bộ `database/`, `core/constants.py`, seed data, backend logic, frontend models và tests.
6. Kiểm tra tích hợp liên quan: tồn kho, order status, PayPal, media, email, contact relay hoặc fraud scoring.
7. Viết/chỉnh test phù hợp; với API/database, chạy integration tests trên DB test sạch.
8. Kiểm tra cấu hình local và production riêng biệt, đặc biệt `environment*.ts`, Nginx proxy, Compose volumes và secrets.
9. Không coi frontend guard, cache `localStorage`, seed account hay fallback fraud model là cơ chế bảo mật sản xuất.

## 12. Các lưu ý kỹ thuật trọng yếu

- **SQL-first:** schema chuẩn nằm trong `database/`, không được tự động migrate khi container khởi động lại.
- **DB bootstrap:** `init_db.py` chỉ nạp `init.sql` nếu chưa thấy `public."user"`; sửa schema cần có bước cập nhật DB hiện hữu rõ ràng.
- **Auth state:** token ở `sessionStorage`; auth state được làm mới qua `/auth/me`/`/users/me` theo service. `app.config.ts` có initializer chờ trạng thái xác thực với timeout 3 giây; thay đổi auth startup nên được test kỹ.
- **Cart state:** backend là nguồn sự thật cho giỏ hàng/tồn kho; `localStorage` là cache/UI persistence, không phải bằng chứng tồn kho hợp lệ.
- **Role numeric IDs:** phải khớp giữa enum Python, role seed SQL và dữ liệu role trả về UI.
- **Media paths:** API trả path tương đối `/media/...`; local cần base URL backend, production dựa vào Nginx same-origin proxy.
- **External integrations optional:** thiếu SMTP/PayPal/Apps Script credentials có thể làm một số tính năng không hoạt động, nhưng một số dịch vụ được thiết kế để degrade gracefully.
- **Fraud model optional:** artifacts không có trong repository; kiểm tra cả rule fallback và threshold nếu điều chỉnh luồng từ chối/đánh dấu đơn.
- **Error disclosure:** chỉ bật `DEBUG=true` ở local; đảm bảo không để debug ở production và không đưa secret/payload nhạy cảm vào log.
- **Seeds và tài khoản mẫu:** chỉ dành cho dev/test; không coi đây là dữ liệu sản xuất hay thông tin đăng nhập an toàn.

## 13. Tài liệu/thư mục nên đọc theo loại tác vụ

| Tác vụ | Đọc đầu tiên |
|---|---|
| Thêm/sửa API | `backend/app/api/v1/`, `backend/app/api/deps.py`, `backend/app/crud/`, `backend/app/schemas/`, tests domain tương ứng |
| Thêm trường DB | `database/01_schema/`, `database/init.sql`, model, schema, CRUD, API, seed và tests |
| Sửa login/role | `core/security.py`, `api/deps.py`, `api/v1/auth.py`, frontend auth service/guard/interceptor, role seeds/constants |
| Sửa cart/checkout/order | `api/v1/cart.py`, `api/v1/orders.py`, `crud/shopping_cart.py`, `crud/order.py`, models, SQL triggers, frontend cart/checkout/order/payment services |
| Sửa upload/ảnh | `services/storage.py`, `users.py`/`products.py`, `core/utils/media-url.ts`, frontend environments, backend media mount, `frontend/nginx.conf` |
| Sửa PayPal/fraud | `services/paypal.py`, `services/fraud_detection.py`, `api/v1/orders.py`, config/env examples, order tests, checkout/payment UI |
| Sửa contact form | `api/v1/system.py`, `services/contact_relay.py`, `services/mail.py`, `frontend/features/contact/`, `integrations/google-apps-script/README.md` |
| Sửa deploy/monitoring | `docs/deployment.md`, `deploy/`, root/production Compose, `.github/workflows/` |

---

**Nguyên tắc chung cho tác vụ tiếp theo:** lần theo luồng xuyên tầng thay vì sửa một file riêng lẻ; giữ contract frontend/API/DB đồng nhất; ưu tiên test trên PostgreSQL test có schema/seed đúng; không giả định rằng khởi động lại app sẽ cập nhật schema hiện hữu.
