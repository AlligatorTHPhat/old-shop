# OldShop — Kế hoạch nâng cấp 7 ngày: Polyglot Persistence + ETL + Phân mảnh + Phân tán

> **Thời gian:** Thứ Ba 27/10/2026 → Thứ Hai 02/11/2026 (7 ngày)
> **Căn cứ:** `PROJECT_GUIDE.md` + cấu trúc thư mục dự án OldShop (FastAPI + Angular + PostgreSQL SQL-first).
> **Cách dùng:** mỗi ngày gồm *Mục tiêu → File cần đọc trước → Việc cần làm (checklist) → Sản phẩm đầu ra → Tiêu chí hoàn thành*. Tick `[x]` khi xong.
> **D1–D6 đã chốt sau audit và trả lời của người dùng:** ưu tiên đồ án một máy;
> [decisions.md](decisions.md) là đặc tả thiết kế hiện hành. D7–D11 vẫn cần chốt theo phụ thuộc.
> Số thứ tự/tên migration minh họa bên dưới được xếp lại khi triển khai D6, không ghi đè version đã áp dụng.

---

## 0. Hiểu yêu cầu và chốt phạm vi

### 0.1 Diễn giải yêu cầu của bạn

Nâng hệ thống từ **một CSDL quan hệ duy nhất (PostgreSQL)** thành hệ **đa mô hình dữ liệu (polyglot persistence)**:

| Loại dữ liệu | Công nghệ | Nội dung trong OldShop |
|---|---|---|
| **Có cấu trúc** | PostgreSQL | users, roles, categories, products (lõi), orders, order_details, transactions, vouchers, payment_methods, carts |
| **Bán cấu trúc** | MongoDB | thuộc tính động của sản phẩm (RAM/CPU/size/màu…), review + báo cáo vi phạm (rating=0), system_logs, violation_logs, audit trail, contact form, snapshot đơn hàng cho analytics |
| **Phi cấu trúc** | MinIO (S3) | ảnh sản phẩm, avatar user, file seed media, (tùy chọn) file đính kèm khiếu nại |
| **ETL** | Python (script + scheduler) | PG → Mongo (read model/analytics), seed media → MinIO, tổng hợp thống kê |
| **Indexing** | PG + Mongo (+ quy ước key MinIO) | B-tree, partial, composite, GIN/trgm, Mongo compound/text/TTL |
| **Phân mảnh ngang** | PG partitioning | Order HASH(order_id); system_log RANGE(created_at)/tháng; FDW/sharding để mở rộng |
| **Phân mảnh dọc** | PG tách bảng + Mongo | users lõi vs hồ sơ/nhạy cảm; products lõi vs mô tả/thuộc tính/ảnh |
| **Phân tán** | Compose một máy, profile dự phòng tùy chọn | PG primary, Mongo replica set một member, MinIO single-node; profile thêm PG replica + hai Mongo member |

> **Lưu ý thuật ngữ:** *pgAdmin4 chỉ là công cụ GUI quản trị*, không phải CSDL. Trong báo cáo, ghi "PostgreSQL (quản trị bằng pgAdmin4)". Nên thêm container pgAdmin4 vào Compose để demo.

### 0.2 Quyết định thiết kế đã chốt ở Ngày 1

| # | Quyết định | Phương án hiện hành | Lý do |
|---|---|---|---|
| D1 | Nguồn sự thật | PG cho giao dịch/PII; Mongo cho bản đọc + metadata/thuộc tính mới; MinIO cho file | Giữ ACID của app + PG; phân biệt nguồn ghi từng field |
| D2 | Đồng bộ | Full load + ETL transactional outbox; poll 60s, mục tiêu dưới 5 phút; metadata mới ghi Mongo trực tiếp | Không mất thay đổi vì watermark cũ thiếu; retry idempotent |
| D3 | Phân mảnh ngang | order HASH(order_id), 4 partition; system_log RANGE(created_at)/tháng; transaction/product chưa partition ngang | Giữ PK/FK/UNIQUE tài chính, demo hai kiểu pruning có giới hạn rõ |
| D4 | Phân mảnh dọc | user_core/profile/secret/wallet + user_role; product PG + Mongo expand/contract | Đủ 20 cột user; view tái tạo chỉ đọc; giữ cột product cũ trong MVP |
| D5 | Phân tán | Base stack một máy; profile thêm PG replica/Mongo3; MinIO single-node | Chạy trước với tài nguyên thực; chưa cam kết chịu mất máy |
| D6 | Migration | SQL đánh số + checksum + advisory lock + transaction; maintenance window và giữ dữ liệu phát sinh | Không reseed DB đã dùng; backup/đối soát trước–sau |

> Ngoài MVP: CDC/Debezium, FDW theo vùng, Mongo sharding và MinIO distributed.
> Profile dự phòng bật sau khi base stack/test xanh và đo đủ tài nguyên; nhiều máy là giai đoạn sau.

### 0.3 Kiến trúc MVP một máy đã chốt

```text
Angular SPA ──► Nginx ──► FastAPI
                           ├── PostgreSQL PRIMARY ──► PG REPLICA (profile tùy chọn)
                           │        └─ order HASH + system_log RANGE + user tách dọc
                           ├── MongoDB (1 member; profile mở rộng thành 3)
                           │        └─ product_details, reviews, logs, audit, order_snapshots
                           ├── MinIO single-node: product-images, user-avatars, attachments
                           └── ETL worker (Python)
                                    PG outbox ──► Mongo (at-least-once, idempotent)
                                    seed/media ──► MinIO
                                    PG ──► bảng tổng hợp (daily_sales...)
pgAdmin4 ──► PG primary / replica tùy chọn  |  Compass ──► Mongo
```

---

## 1. Phân công (điền tên thực tế)

| Vai trò | Người | Trách nhiệm chính |
|---|---|---|
| **A — Data Architect / PG** | ___ | ERD, phân mảnh ngang/dọc, partitioning, migration, indexing PG |
| **B — NoSQL & Storage** | ___ | Thiết kế JSON, MongoDB, MinIO, `services/storage.py` |
| **C — ETL & Backend** | ___ | ETL, tích hợp API, test, CI |
| **D — Infra & Báo cáo** | ___ | Docker Compose phân tán, sơ đồ, báo cáo, PPT, demo |

> Nhóm ít người hơn: gộp A+C và B+D. Mọi mốc ngày giữ nguyên, bớt song song.

---

## 2. Bảng tổng quan 7 ngày

| Ngày | Ngày tháng | Trọng tâm | Yêu cầu gốc |
|---|---|---|---|
| 1 | Thứ Ba 27/10 | Audit hệ thống + thiết kế dữ liệu, ERD | **#1** |
| 2 | Thứ Tư 28/10 | Chiến lược phân tán + phân mảnh + hạ tầng Compose | **#2** |
| 3 | Thứ Năm 29/10 | Thiết kế JSON + MongoDB + MinIO | **#3** |
| 4 | Thứ Sáu 30/10 | Indexing + partitioning + benchmark | **#4** |
| 5 | Thứ Bảy 31/10 | ETL | (ETL — ý hiểu của bạn) |
| 6 | Chủ Nhật 01/11 | Tích hợp backend/frontend, test, kế hoạch hoàn thiện | **#5** |
| 7 | Thứ Hai 02/11 | Báo cáo + PPT + demo + buffer | **#6** |

---

## NGÀY 1 — Thứ Ba 27/10: Audit & thiết kế dữ liệu (Yêu cầu #1)

**Mục tiêu:** hiểu đúng schema hiện tại, phân loại dữ liệu (cấu trúc / bán cấu trúc / phi cấu trúc), vẽ ERD và chốt các quyết định D1–D6.

> **Review 28/10:** đã kiểm chứng baseline PostgreSQL 16.15, sửa DBML và đọc các file từng thiếu.
> Kết quả tại [DAY1_REVIEW.md](DAY1_REVIEW.md), bằng chứng tại [day1/verification.txt](day1/verification.txt).
> Đầu ra thực tế nằm trong `docs/` và `docs/diagram/`.
> Các tên bảng/cột và giả định kỹ thuật trong phần kế hoạch chưa cập nhật bên dưới
> phải được hiệu chỉnh theo inventory/decisions/review trước khi thực hiện.

### 📖 File cần đọc trước
- `docs/PROJECT_GUIDE.md` (mục 4, 5, 7, 12)
- `database/init.sql`, `database/config/database_config.sql`
- Toàn bộ `database/01_schema/*.sql` (đặc biệt `users.sql`, `user_roles.sql`, `products.sql`, `product_images.sql`, `orders.sql`, `order_details.sql`, `transactions.sql`, `reviews.sql`, `shopping_carts.sql`, `shopping_cart_items.sql`, `violation_logs.sql`, `system_logs.sql`, `system_feedback.sql`, `contact_info.sql`, `vouchers.sql`, `payment_methods.sql`)
- `database/02_functions/order_detail/triggers.sql`, `system/business_functions.sql`, `system/audit_functions.sql`
- `backend/app/models/*.py`, `backend/app/core/constants.py`
- `backend/scripts/init_db.py`

### ✅ Checklist
- [x] Đọc xong danh sách file ở trên, ghi chú các ràng buộc/trigger quan trọng (tồn kho, audit)
- [x] Lập **bảng kiểm kê dữ liệu**: mỗi bảng/cột → loại (cấu trúc/bán/phi), kích thước ước tính, tần suất đọc/ghi
- [x] Vẽ **ERD hiện tại** → đã có PNG + DBML; DBML đã sửa theo DB thật 28/10, PNG cần tái xuất
- [x] Vẽ **mô hình quan niệm (conceptual)** và **mô hình ứng dụng**: đã có bản PNG; cần đồng bộ khi chốt kiến trúc đích
- [x] Phân chia thành phần: *PG lõi / Mongo / MinIO* (inventory đã có bảng ánh xạ hiệu chỉnh)
- [x] Chốt D1–D6 sau audit và câu trả lời người dùng; đặc tả tại `docs/decisions.md`
- [x] Xác định **dữ liệu nhạy cảm** (password hash, địa chỉ, SĐT, email) để phục vụ phân mảnh dọc
- [x] Ghi lại các rủi ro đã biết trong guide (bootstrap `DATABASE_URL` vs `DB_*`, ngưỡng fraud 0.9, enum PaymentMethod chưa triển khai đủ)
- [x] Chạy init.sql và smoke SQL trên PG16; đối chiếu DBML với catalog thật; kiểm tra SQL thuần cho pgAdmin4 9.18

### 📦 Sản phẩm đầu ra
`docs/design/01_erd_current.png`, `01_data_inventory.md`, `01_conceptual_model.png`, `decisions.md`

### Bảng ánh xạ đề xuất (điền/hiệu chỉnh sau khi đọc schema)

| Dữ liệu | Hiện tại | Đích | Ghi chú |
|---|---|---|---|
| users, roles, user_roles | PG | PG (tách dọc) | core vs profile |
| categories | PG | PG | cây danh mục |
| products (id, name, price, status, stock, seller, category) | PG | PG (lõi) | giao dịch/tồn kho |
| mô tả dài, thuộc tính động sản phẩm | PG (cột text?) | **Mongo** `product_details` | linh hoạt theo category |
| product_images (đường dẫn) | PG + file đĩa | PG giữ metadata/key; **MinIO** giữ file | |
| orders, order_details, transactions | PG | PG (phân mảnh ngang) | ACID |
| order snapshot cho báo cáo | — | **Mongo** `order_snapshots` | ETL |
| reviews / báo cáo (rating=0) | PG | PG + **Mongo** `reviews` (bản đọc) | tách review thường và report |
| system_logs, violation_logs, audit | PG | **Mongo** (TTL/archival) | log tăng nhanh |
| contact_info, system_feedback | PG | PG + Mongo (bản có file đính kèm) | |
| avatar, ảnh sản phẩm | đĩa `/media` | **MinIO** | |

### 🎯 Tiêu chí hoàn thành
ERD + bảng kiểm kê được cả nhóm review và chốt; mỗi bảng đều có "nhà" ở hệ lưu trữ đích.

---

## NGÀY 2 — Thứ Tư 28/10: Chiến lược phân tán & phân mảnh + hạ tầng (Yêu cầu #2)

**Mục tiêu:** thiết kế chiến lược phân mảnh ngang/dọc + phân tán dữ liệu, dựng base stack một máy và profile replication tùy chọn.

> **Hoàn tất Ngày 2 trên môi trường kiểm thử:** thiết kế/ma trận/sơ đồ nguồn `.puml` và
> Compose/profile đã kiểm chứng. Ngoại lệ được người dùng đồng ý: Mongo7.0.43 thay Mongo8.0.32
> trên kernel hiện tại; xem [DAY2_FINDINGS_LOG.md](DAY2_FINDINGS_LOG.md).
> Đây chưa phải migration partition/user split (Ngày 4), client Mongo/MinIO (Ngày 3), hoặc ETL (Ngày 5).

### 📖 File cần đọc trước
- `docker-compose.yml`, `deploy/docker-compose.yml`, `deploy/.env.example`
- `backend/docker-entrypoint.sh`, `backend/Dockerfile`, `frontend/nginx.conf`
- `backend/app/core/config.py`, `backend/app/core/database.py`
- `docs/deployment.md`
- `database/02_functions/order_detail/triggers.sql` (trigger ảnh hưởng đến partitioning)
- `backend/app/crud/order.py`, `crud/product.py`, `crud/user.py` (kiểu truy vấn thực tế để chọn khóa phân mảnh)

### ✅ Checklist
**Thiết kế**
- [x] **Phân mảnh ngang** (ghi rõ khóa, kiểu, lý do trong docs/design/02_fragmentation_matrix.md):
  - `order`: HASH(order_id), 4 partition; giữ FK/PK đơn cột
  - `system_log`: RANGE(created_at)/tháng, PK(log_id,created_at), DEFAULT và quản lý vòng đời partition
  - `transaction`, `product`, `order_detail`: chưa partition ngang; bảo toàn UNIQUE/FK, index theo truy vấn
  - Mongo sharding/FDW theo vùng: chỉ ghi hướng mở rộng, không thuộc checklist triển khai MVP
- [x] **Phân mảnh dọc** (mô hình đích, chưa áp DDL):
  - user_core/user_profile/user_secret/user_wallet đúng ánh xạ 20 cột D4; giữ user_role
  - product (PG giữ tên/cột hiện có) + product_details (Mongo) + ảnh (MinIO), expand/contract
- [x] Kiểm tra **3 tính chất trên mô hình**: đầy đủ/tái tạo/không chồng lặp user và order/log; product hiện là expand/contract có sao chép, không tuyên bố phân rã vật lý hoàn toàn
- [x] Chiến lược **sao chép**: PG replica/Mongo3 thuộc profile tùy chọn; MinIO single-node trong MVP
- [x] Truy vấn qua bảng cha/partition pruning; thiết kế mở rộng FDW riêng, không tuyên bố đã có phân tán nhiều máy
- [x] Nhất quán: PG giao dịch; metadata Mongo mới ghi trực tiếp; read model eventual qua outbox; mô tả lỗi từng dịch vụ theo D5
- [x] Sơ đồ phân tán/fragment bằng `.puml` và allocation matrix Markdown theo yêu cầu người dùng, không xuất PNG
**Hạ tầng**
- [x] Tạo Compose base: pg-primary, mongo1 (replica set một member), MinIO single-node và app; worker thực hiện Ngày 5, chưa tạo idle container
- [x] Tạo profile dự phòng pg-replica/mongo2-3; script replication/reconfigure và resource sample, đã chạy trên máy hiện tại
- [x] Healthcheck và Compose startup/wait PASS với Mongo7 theo ngoại lệ; init job dùng service_completed_successfully; Mongo8 trên máy tương thích chưa được kiểm chứng
- [x] Thêm biến vào backend/.env.example và Settings; client/read routing được triển khai ở Ngày 3–6

### 📦 Sản phẩm đầu ra
`docs/design/02_distribution_strategy.md`, `docs/design/02_fragmentation_matrix.md`,
`docs/diagram/02_distribution_diagram.puml`, `docs/diagram/02_fragmentation_model.puml`,
`deploy/docker-compose.distributed.yml`, scripts, `docs/DAY2_FINDINGS_LOG.md` và `docs/day2/*verification.json`.

### 🎯 Tiêu chí hoàn thành
Có sơ đồ/giải thích và base stack chạy được; rs.status() xác nhận topology đang bật.
Nếu bật profile dự phòng, thêm bằng chứng pg_stat_replication và Mongo quorum; không tuyên bố chịu mất máy.

---

## NGÀY 3 — Thứ Năm 29/10: Thiết kế JSON + MongoDB + MinIO (Yêu cầu #3)

**Mục tiêu:** chốt cấu trúc JSON, tạo collection + validator, tích hợp lưu trữ file lên MinIO.

### 📖 File cần đọc trước
- `backend/app/schemas/catalog.py`, `schemas/order.py`, `schemas/moderation.py`, `schemas/user.py`, `schemas/common.py`
- `backend/app/models/catalog.py`, `models/system.py`, `models/order.py`
- `backend/app/services/storage.py` (**trọng tâm** — validate/ghi/xóa ảnh)
- `backend/app/api/v1/products.py`, `api/v1/users.py` (upload ảnh/avatar)
- `backend/app/main.py` (mount `/media`), `frontend/src/app/core/utils/media-url.ts`
- `database/03_seeds/product_images/seed.sql`, `database/03_seeds/user/seed.sql`
- `frontend/src/app/core/models/index.ts`, `shared/services/product.service.ts`

### ✅ Checklist
**JSON / MongoDB**
- [x] Định nghĩa JSON cho tối thiểu 5 collection: `product_details`, `reviews`, `order_snapshots`, `system_logs`/`violation_logs`, `contact_messages`
- [x] Với mỗi collection: danh sách field, kiểu, bắt buộc/tùy chọn, ví dụ minh họa, **embedding vs referencing** và lý do
- [x] Tạo **JSON Schema validator** (`$jsonSchema`) cho từng collection
- [x] Viết script `backend/scripts/init_mongo.py` (tạo collection, validator, index)
- [x] Service `backend/app/services/mongo.py` (client, `get_collection`, ping) + `ping_mongo()` cho readiness
- [x] Pydantic schema tương ứng ở `backend/app/schemas/` (ví dụ `product_details.py`)
**MinIO**
- [x] Tạo bucket: `product-images`, `user-avatars`, `attachments` (private; backend SDK ký S3 request và stream ảnh qua `/media/`)
- [x] Quy ước object key: `products/{product_id}/{uuid}.{ext}`, `users/{user_id}/avatar-{uuid}.{ext}` (key bất biến; alias seed `avatar.ext`)
- [x] Refactor `services/storage.py` thành **storage backend trừu tượng** (`LocalStorage` / `MinioStorage`) chọn bằng cấu hình `STORAGE_BACKEND` — giữ nguyên validate (đuôi ảnh, `MAX_UPLOAD_BYTES` 2 MiB)
- [x] Script đẩy `database/03_seeds/media/**` lên MinIO (idempotent: chỉ upload khi chưa tồn tại)
- [x] Quyết định cách trả URL ảnh cho frontend: giữ `/media/...`, Nginx proxy backend, backend SDK đọc MinIO private
- [x] Cập nhật `frontend/nginx.conf` + `media-url.ts` nếu đổi đường dẫn

### 📦 Sản phẩm đầu ra
`docs/design/03_json_design.md` (kèm ví dụ), `backend/scripts/init_mongo.py`, `services/mongo.py`, `services/storage.py` (đa backend)

**Kết quả:** 81/81 test PASS (24 test Ngày 3), seed lại bỏ qua 95/95 object;
readiness PG/Mongo/MinIO đều up. Xem [DAY3_FINDINGS_LOG.md](DAY3_FINDINGS_LOG.md)
và [03_json_design.md](design/03_json_design.md).

### Ví dụ JSON minh họa ban đầu

> Ví dụ bên dưới là phác thảo kế hoạch. Hợp đồng triển khai chính thức, tên field và kiểu
> đã hiệu chỉnh theo nguồn PG nằm trong `design/03_json_design.md` và
> `design/03_document_examples.json`; không dùng các phác thảo này để insert trực tiếp.

**`product_details`** (bán cấu trúc — thuộc tính khác nhau theo danh mục)
```json
{
  "_id": "p_1",
  "product_id": 1,
  "category_id": 3,
  "description": "Laptop đã qua sử dụng, pin còn 85%, kèm sạc gốc.",
  "attributes": {
    "brand": "Dell",
    "cpu": "Intel i5-8250U",
    "ram_gb": 8,
    "storage": { "type": "SSD", "size_gb": 256 },
    "screen_inch": 14.0
  },
  "condition": { "grade": "B+", "usage_months": 30, "defects": ["xước nhẹ nắp máy"] },
  "images": [
    { "bucket": "product-images", "key": "products/1/a1b2.jpg", "is_primary": true, "order": 1 },
    { "bucket": "product-images", "key": "products/1/c3d4.jpg", "is_primary": false, "order": 2 }
  ],
  "tags": ["laptop", "dell", "văn phòng"],
  "updated_at": { "$date": "2026-10-29T08:00:00Z" }
}
```

**`reviews`** (tách review thường và báo cáo vi phạm — `rating = 0`)
```json
{
  "_id": "r_501",
  "review_id": 501,
  "product_id": 1,
  "user_id": 3,
  "type": "review",
  "rating": 4,
  "comment": "Máy đúng mô tả, giao nhanh.",
  "status": "approved",
  "moderation": { "by": 2, "at": { "$date": "2026-10-28T10:00:00Z" } },
  "created_at": { "$date": "2026-10-28T09:30:00Z" }
}
```
```json
{
  "_id": "r_502",
  "review_id": 502,
  "product_id": 7,
  "user_id": 4,
  "type": "report",
  "rating": 0,
  "comment": "Ảnh không đúng hàng thật.",
  "evidence": [{ "bucket": "attachments", "key": "reports/502/proof1.png" }],
  "status": "pending",
  "created_at": { "$date": "2026-10-28T11:00:00Z" }
}
```

**`order_snapshots`** (denormalize phục vụ phân tích, sinh bởi ETL)
```json
{
  "_id": "o_1001",
  "order_id": 1001,
  "buyer": { "id": 3, "region": "south" },
  "items": [
    { "product_id": 1, "name": "Laptop Dell", "category_id": 3, "qty": 1, "unit_price": 6500000 }
  ],
  "voucher": { "code": "WELCOME10", "discount": 650000 },
  "payment": { "method_id": 2, "status": "captured", "amount_vnd": 5850000 },
  "fraud": { "score": 0.12, "is_fraud": false },
  "status": 3,
  "created_at": { "$date": "2026-10-20T03:00:00Z" },
  "etl": { "synced_at": { "$date": "2026-10-31T01:00:00Z" }, "source_updated_at": { "$date": "2026-10-20T03:05:00Z" } }
}
```

**`system_logs` / `violation_logs`** (có TTL)
```json
{
  "_id": { "$oid": "6720a1f3c9a1b2d3e4f50001" },
  "type": "violation",
  "actor_id": 2,
  "target_user_id": 4,
  "action": "ban_user",
  "payload": { "reason": "lừa đảo", "duration_days": 30 },
  "request_id": "9f1c-...",
  "created_at": { "$date": "2026-10-27T12:00:00Z" }
}
```

### 🎯 Tiêu chí hoàn thành
Collection + validator được tạo bằng script; upload/đọc ảnh qua MinIO thành công; tài liệu JSON có ví dụ cho mọi collection.

---

## NGÀY 4 — Thứ Sáu 30/10: Indexing + Partitioning + Benchmark (Yêu cầu #4)

**Mục tiêu:** xác định và tạo chỉ mục có cơ sở, hiện thực phân mảnh trong PG, chứng minh hiệu quả bằng số liệu.

### 📖 File cần đọc trước
- `database/01_schema/*.sql` (xem index hiện có), `database/config/database_config.sql` (extension `pg_trgm`)
- `backend/app/crud/product.py`, `crud/order.py`, `crud/shopping_cart.py`, `crud/admin.py`, `crud/moderator.py` (tìm `WHERE/ORDER BY/JOIN/ILIKE` thực tế)
- `backend/app/api/v1/products.py` (tham số lọc/tìm kiếm/phân trang)
- `database/02_functions/order_detail/triggers.sql` (trigger phải hoạt động đúng trên bảng partition)
- `backend/tests/test_v1_order.py`, `test_v1_cart.py`, `test_v1_product.py`

### ✅ Checklist
**PostgreSQL**
- [ ] Liệt kê **top truy vấn nóng** từ CRUD (catalogue lọc theo category/status/giá, tìm kiếm tên, đơn của user/seller, thống kê admin) → bảng "truy vấn → chỉ mục"
- [ ] Đề xuất/thêm chỉ mục (chỉ giữ cái có lý do):
  - `products (status, category_id, created_at DESC)` — composite cho catalogue
  - `products (name gin_trgm_ops)` — tìm kiếm `ILIKE` (đã có `pg_trgm`)
  - `products (seller_id)` — partial `WHERE status = 1` nếu phù hợp
  - `orders (user_id, created_at DESC)`, `orders (seller_id/status, created_at)` — lịch sử đơn
  - `order_details (order_id)`, `order_details (product_id)` — FK join
  - `shopping_cart_items (cart_id, product_id)` UNIQUE — chống trùng
  - `transactions (order_id)`, `reviews (product_id, created_at)`; partial `reviews WHERE rating = 0` cho moderator
  - BRIN trên `created_at` của bảng partition lớn (tùy chọn)
- [ ] Viết `database/04_migrations/001_indexes.sql`
- [ ] Hiện thực order HASH/order_id và system_log RANGE/created_at theo D3; kiểm tra FK/PK/trigger và mọi nơi dùng khóa log
- [ ] Hiện thực user_core/profile/secret/wallet + view users_full chỉ đọc; ghi bằng ORM/service vào bảng vật lý, đối soát đủ 20 cột
- [ ] Ghi FDW theo vùng vào hướng mở rộng, chưa cấu hình node-b trong MVP
- [ ] Chạy `EXPLAIN (ANALYZE, BUFFERS)` **trước/sau** cho ≥ 5 truy vấn; chụp kết quả (Seq Scan → Index Scan, partition pruning)
- [ ] Sinh dữ liệu giả lớn (≥ 100k orders, 50k products) bằng script để benchmark có ý nghĩa
**MongoDB**
- [ ] `product_details`: unique `{product_id: 1}`; compound `{category_id: 1, "attributes.brand": 1}`; text index `{description, tags}`
- [ ] `reviews`: `{product_id: 1, created_at: -1}`; partial `{type: "report", status: "pending"}`
- [ ] `order_snapshots`: `{"buyer.id": 1, created_at: -1}`; `{status: 1, created_at: -1}`
- [ ] `system_logs`: TTL index `created_at` (vd. 90 ngày); `{type: 1, actor_id: 1, created_at: -1}`
- [ ] `explain("executionStats")` cho 3 truy vấn chính
**MinIO**
- [ ] Quy ước key theo tiền tố (`products/{id}/`) để list nhanh; ghi nhận metadata (content-type, size) vào PG/Mongo thay vì scan bucket
**Chung**
- [ ] Bảng tổng hợp **"trường → chỉ mục → lý do → chi phí ghi"** (cho báo cáo)

### 📦 Sản phẩm đầu ra
`database/04_migrations/001_indexes.sql`, `002_partitioning.sql`, `003_vertical_split.sql`, `docs/design/04_indexing.md`, `docs/benchmark/` (ảnh/log EXPLAIN trước–sau)

### 🎯 Tiêu chí hoàn thành
Mỗi chỉ mục có lý do + minh chứng đo; partition pruning được chứng minh; **toàn bộ test PG hiện có vẫn pass** trên DB test đã áp migration.

---

## NGÀY 5 — Thứ Bảy 31/10: ETL

**Mục tiêu:** pipeline ETL chạy được, idempotent, có log và kiểm tra chất lượng dữ liệu.

### 📖 File cần đọc trước
- `backend/app/crud/order.py`, `crud/product.py`, `crud/admin.py` (nguồn thống kê hiện có)
- `backend/app/models/*.py`, `backend/app/core/database.py`, `core/logging.py`
- `backend/app/services/fraud_detection.py` (dữ liệu fraud đưa vào snapshot), `services/contact_relay.py`
- `database/02_functions/system/audit_functions.sql`, `database/03_seeds/*/seed.sql` (dữ liệu nguồn mẫu)
- `backend/scripts/init_db.py` (mẫu script bootstrap)
- `deploy/docker-compose.monitoring.yml`, `deploy/prometheus/prometheus.yml` (nếu muốn xuất metric ETL)

### ✅ Checklist
- [ ] Tạo package `backend/etl/` (hoặc `etl/` ở gốc): `extract.py`, `transform.py`, `load.py`, `pipelines/`, `run.py`
- [ ] **Pipeline 1 — Product:** PG `products` + `product_images` → Mongo `product_details` (merge thuộc tính động, đổi path ảnh → `bucket/key`)
- [ ] **Pipeline 2 — Order snapshot:** PG `orders` + `order_details` + `transactions` + voucher + fraud → Mongo `order_snapshots` (denormalize)
- [ ] **Pipeline 3 — Review/Report:** `reviews` → Mongo `reviews` (gán `type` theo `rating = 0`)
- [ ] **Pipeline 4 — Logs/Audit:** `system_logs`, `violation_logs` → Mongo (TTL), đánh dấu đã chuyển
- [ ] **Pipeline 5 — Media:** `database/03_seeds/media/**` + ảnh trong volume `media` → MinIO; cập nhật key
- [ ] **Pipeline 6 — Aggregate:** doanh thu theo ngày/danh mục/seller → bảng `report_daily_sales` (PG replica/Mongo) phục vụ dashboard admin
- [ ] Incremental qua transactional outbox theo D2; ACK từng event sau Mongo thành công, không dùng MAX(id)/updated_at làm cursor duy nhất; upsert idempotent, giữ attributes/tags do Mongo quản lý
- [ ] **Transform & làm sạch**: chuẩn hóa kiểu tiền (VND integer), thời gian UTC, loại bản ghi mồ côi, che dữ liệu nhạy cảm (không đưa password hash/PII thừa sang Mongo)
- [ ] **Data quality check**: đối chiếu số lượng PG ↔ Mongo ↔ MinIO sau mỗi lần chạy; ghi báo cáo `etl_runs` (start, end, rows_in/out, errors)
- [ ] Lập lịch: etl-worker full lần đầu sau bật outbox, incremental poll 60 giây; mục tiêu dưới 5 phút khi tải bình thường, theo dõi backlog; CLI full và đối soát hằng ngày
- [ ] **Xử lý lỗi**: retry, dead-letter (collection `etl_errors`), log có `run_id`
- [ ] Test ETL: unit (transform) + integration (PG test DB → Mongo test)
- [ ] Vẽ **sơ đồ luồng ETL** (Extract → Transform → Load, nguồn/đích)

### 📦 Sản phẩm đầu ra
Package ETL + `docs/design/05_etl.md` + sơ đồ + log một lần chạy mẫu (số dòng in/out)

### 🎯 Tiêu chí hoàn thành
`docker compose up` → seed PG → chạy ETL → Mongo và MinIO có dữ liệu đúng; chạy lần hai không nhân bản; số liệu đối chiếu khớp.

---

## NGÀY 6 — Chủ Nhật 01/11: Tích hợp, kiểm thử, kế hoạch hoàn thiện (Yêu cầu #5)

**Mục tiêu:** nối hệ mới vào ứng dụng thực, đảm bảo không phá chức năng cũ, và tổng hợp tiến độ/việc còn lại.

### 📖 File cần đọc trước
- `backend/app/api/v1/products.py`, `orders.py`, `cart.py`, `admin.py`, `moderator.py`, `system.py`
- `backend/app/main.py` (health/readiness), `backend/tests/conftest.py`
- `frontend/src/app/shared/services/product.service.ts`, `admin.service.ts`, `moderator.service.ts`, `core/models/index.ts`
- `frontend/src/app/features/shop/product-detail/*`, `features/admin/dashboard/*`, `features/moderator/review-manage/*`
- `.github/workflows/ci.yml`, `deploy/docker-compose.yml`, `docs/deployment.md`

### ✅ Checklist
**Backend**
- [ ] `GET /products/{id}` hợp nhất dữ liệu lõi (PG) + `product_details` (Mongo) — **fallback** khi Mongo lỗi (graceful degradation)
- [ ] Tìm kiếm/lọc theo thuộc tính động (Mongo) kết hợp phân trang
- [ ] Upload ảnh/avatar đi qua `MinioStorage`; xóa ảnh đồng bộ
- [ ] Ghi log/violation sang Mongo (hoặc dual-write có kiểm soát); thống kê admin đọc từ replica/bảng tổng hợp
- [ ] Ghi/giao dịch đọc primary; báo cáo dùng primary hoặc bản đọc Mongo, chỉ dùng replica nếu profile được bật và chấp nhận trễ
- [ ] Mở rộng `/ready` kiểm tra PG, Mongo, MinIO
- [ ] **Giữ nguyên contract API** (path, method, field, enum); nếu thêm field → cập nhật Pydantic + Angular model
**Frontend**
- [ ] Hiển thị thuộc tính động ở `product-detail`; ảnh tải qua URL mới; kiểm tra `media-url.ts`
- [ ] Dashboard admin dùng số liệu tổng hợp từ ETL (nếu đã làm)
**Kiểm thử**
- [ ] Chạy lại toàn bộ `pytest` (DB test sạch + migration), `ruff check`, `ruff format --check`
- [ ] Thêm test: Mongo/MinIO integration (testcontainers hoặc service trong CI), ETL, fallback
- [ ] Kịch bản **failover**: tắt `mongo2`, tắt `pg-replica`, tắt MinIO → ứng dụng vẫn phục vụ phần còn lại
- [ ] Cập nhật `.github/workflows/ci.yml` thêm service Mongo + MinIO
- [ ] Rà soát bảo mật: secret không commit, Mongo/MinIO không public, không đưa PII/hash sang Mongo, `DEBUG=false` ở prod
**Kế hoạch hoàn thiện (Yêu cầu #5)**
- [ ] Lập bảng **tiến độ**: hạng mục → % hoàn thành → người phụ trách → hạn
- [ ] Liệt kê **công việc còn lại / nợ kỹ thuật** (CDC, Mongo sharding thật, tự động failover PG bằng Patroni, rotation key, ...)
- [ ] Viết `docs/design/06_completion_plan.md` (xem mẫu bên dưới)

### Mẫu bảng kế hoạch hoàn thiện

| Hạng mục | Trạng thái | % | Phụ trách | Hạn | Ghi chú |
|---|---|---|---|---|---|
| ERD + thiết kế dữ liệu | ☐ | | A | 27/10 | |
| Chiến lược phân tán | ☐ | | A/D | 28/10 | |
| JSON + Mongo | ☐ | | B | 29/10 | |
| MinIO + storage | ☐ | | B | 29/10 | |
| Index + partitioning | ☐ | | A | 30/10 | |
| ETL | ☐ | | C | 31/10 | |
| Tích hợp BE/FE | ☐ | | C | 01/11 | |
| Báo cáo + PPT | ☐ | | D | 02/11 | |
| (Còn lại) CDC / Patroni / shard thật | ☐ | | — | Sau đồ án | Hướng mở rộng |

### 🎯 Tiêu chí hoàn thành
Ứng dụng chạy end-to-end trên hạ tầng mới; test xanh; có bảng tiến độ và danh sách việc còn lại.

---

## NGÀY 7 — Thứ Hai 02/11: Báo cáo + PPT + Demo (Yêu cầu #6)

**Mục tiêu:** hoàn thiện báo cáo, slide, kịch bản demo và tổng duyệt.

### 📖 File cần đọc trước
- Toàn bộ `docs/design/*.md`, `docs/benchmark/*` đã tạo
- `README.md`, `docs/deployment.md`, `docs/PROJECT_GUIDE.md` (cập nhật phần kiến trúc mới)

### ✅ Checklist
**Báo cáo (.docx/.pdf)**
- [ ] 1. Giới thiệu & bài toán (OldShop, vì sao cần polyglot + phân tán)
- [ ] 2. Thiết kế dữ liệu: ERD, mô hình quan niệm, phân loại cấu trúc/bán/phi cấu trúc
- [ ] 3. Thiết kế hệ thống phân tán: sơ đồ, phân mảnh ngang/dọc, allocation, replication, nhất quán
- [ ] 4. Thiết kế JSON: cấu trúc + ví dụ + embedding vs referencing
- [ ] 5. Indexing: bảng trường–chỉ mục–lý do + số liệu EXPLAIN trước/sau
- [ ] 6. ETL: sơ đồ, pipeline, kiểm tra chất lượng
- [ ] 7. Triển khai & kiểm thử (Compose, failover, CI)
- [ ] 8. Kế hoạch hoàn thiện: tiến độ, việc còn lại, phân công, thời hạn
- [ ] 9. Kết luận, hạn chế, hướng phát triển (CDC, Patroni, shard thật, Kafka)
- [ ] Phụ lục: SQL migration, script, cấu hình
**PPT (≈ 15–20 slide)**
- [ ] Slide: Bối cảnh → Kiến trúc tổng thể → ERD → Phân loại dữ liệu → Phân mảnh ngang → Phân mảnh dọc → Sơ đồ phân tán → JSON → Indexing (kèm benchmark) → ETL → Demo → Kết quả → Kế hoạch còn lại → Q&A
- [ ] Mỗi slide ≤ 1 sơ đồ chính; số liệu benchmark dạng biểu đồ
**Demo (5–7 phút)**
- [ ] Kịch bản: (1) `docker compose up` (2) xem pgAdmin: partition + replication (3) Mongo: document sản phẩm (4) MinIO console: ảnh (5) chạy ETL, đối chiếu số lượng (6) `EXPLAIN` trước/sau (7) tắt một node → hệ thống vẫn chạy
- [ ] Quay video demo dự phòng; chuẩn bị ảnh chụp màn hình
**Hoàn tất**
- [ ] Tổng duyệt 1 lượt, chuẩn bị Q&A (vì sao Mongo không thay PG cho đơn hàng? CAP? consistency ETL?)
- [ ] Cập nhật `README.md` + `PROJECT_GUIDE.md` cho kiến trúc mới
- [ ] Tag release Git, đóng gói nộp

### 🎯 Tiêu chí hoàn thành
Báo cáo + PPT + demo chạy trơn tru; mọi sơ đồ nhất quán với mã nguồn thật.

---

## 3. Thư mục sản phẩm đề xuất

```text
docs/
├── design/
│   ├── decisions.md
│   ├── 01_erd_current.png / 01_data_inventory.md / 01_conceptual_model.png
│   ├── 02_distribution_strategy.md / 02_distribution_diagram.png / 02_fragmentation_matrix.md
│   ├── 03_json_design.md
│   ├── 04_indexing.md
│   ├── 05_etl.md
│   └── 06_completion_plan.md
├── benchmark/               # log + ảnh EXPLAIN trước/sau
└── report/                  # báo cáo + PPT
database/04_migrations/      # 001_indexes, 002_partitioning, 003_vertical_split ...
backend/etl/                 # extract / transform / load / pipelines / run.py
backend/scripts/init_mongo.py, init_minio.py
backend/app/services/mongo.py, storage.py (đa backend)
deploy/docker-compose.distributed.yml
```

---

## 4. Rủi ro & lưu ý quan trọng (rút từ PROJECT_GUIDE)

| Rủi ro | Biện pháp |
|---|---|
| `init_db.py` bỏ qua `init.sql` nếu bảng `user` đã tồn tại → migration không tự chạy | Dùng `database/04_migrations/` + runner riêng; test trên DB sạch; không chạy lại seed trên DB có dữ liệu |
| `DATABASE_URL` vs `DB_*` khác nhau ở bootstrap | Đặt cả hai nhất quán trong compose/.env mới |
| Partitioning làm PK/FK/unique phải chứa khóa phân mảnh; trigger tồn kho có thể ảnh hưởng | Thử trên DB test, chạy lại `test_v1_order.py`, `test_v1_cart.py` trước khi merge |
| Tồn kho reserve khi thêm giỏ (`SELECT ... FOR UPDATE`) | **Không** chuyển cart/stock sang Mongo; PG vẫn là nguồn sự thật |
| Đổi enum/role/status | Đồng bộ SQL seed + `constants.py` + FE + test |
| Mongo là eventual consistency (ETL trễ) | Ghi rõ trong báo cáo; dữ liệu giao dịch luôn đọc từ PG |
| Mongo/MinIO là dịch vụ mới có thể sập | Fallback graceful, health/readiness, test failover |
| `fraud_detection`: điểm model bị chặn ở 0.9 nên không vượt ngưỡng | Không phải trọng tâm; chỉ ghi chú nếu đưa `fraud.score` vào snapshot |
| Lộ secret | Không commit `.env`; key MinIO/Mongo qua biến môi trường |
| Quá tải phạm vi 7 ngày | Dùng thứ tự cắt giảm ở mục 0.2 |

---

## 5. Tổng hợp danh sách file cần đọc (theo mức ưu tiên)

**Bắt buộc (đọc ở Ngày 1–2):**
`docs/PROJECT_GUIDE.md`, `database/init.sql`, `database/01_schema/*.sql`, `database/02_functions/**/*.sql`, `backend/app/models/*.py`, `backend/app/core/{config,constants,database}.py`, `backend/scripts/init_db.py`, `docker-compose.yml`, `deploy/docker-compose.yml`

**Theo từng chủ đề:**
- *Lưu trữ file/MinIO:* `services/storage.py`, `api/v1/products.py`, `api/v1/users.py`, `main.py`, `frontend/nginx.conf`, `core/utils/media-url.ts`, `database/03_seeds/media/**`
- *Mongo/JSON:* `schemas/*.py`, `core/models/index.ts`, `shared/services/product.service.ts`
- *Index/partition:* `crud/{product,order,shopping_cart,admin,moderator}.py`, `database/02_functions/order_detail/triggers.sql`, `tests/test_v1_*.py`
- *ETL:* `crud/*.py`, `services/fraud_detection.py`, `database/03_seeds/*/seed.sql`
- *Tích hợp/CI/triển khai:* `main.py`, `tests/conftest.py`, `.github/workflows/ci.yml`, `docs/deployment.md`, `deploy/scripts/*.sh`

---

## 6. Định nghĩa "Hoàn thành" của toàn dự án (Definition of Done)

- [ ] Có ERD, mô hình quan niệm, bảng phân loại dữ liệu (#1)
- [ ] Có sơ đồ + giải thích chiến lược phân tán, phân mảnh ngang & dọc (#2)
- [ ] Có cấu trúc JSON, ví dụ, validator Mongo (#3)
- [ ] Có danh sách chỉ mục + lý do + benchmark (#4)
- [ ] Có bảng tiến độ, việc còn lại, phân công, hạn (#5)
- [ ] Có báo cáo + PPT + demo (#6)
- [ ] PostgreSQL (có/structured) + MongoDB (semi-structured) + MinIO (unstructured) cùng chạy trong Compose
- [ ] ETL chạy được, idempotent, có đối chiếu số liệu
- [ ] Test cũ vẫn pass; test mới cho Mongo/MinIO/ETL pass
- [ ] Không lộ secret; tài liệu `PROJECT_GUIDE.md` đã cập nhật
