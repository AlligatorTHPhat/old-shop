# Pre-Implementation Audit & 7-Day Plan --- Epic-Ecommerce-FastAPI

> **Trạng thái:** `REVIEW REQUIRED`. Chưa được phép chốt implementation
> cho đến khi hoàn tất toàn bộ file audit, data ownership, workload
> analysis, ERD, fragmentation và indexing review.

## 1. Mục tiêu

Yêu cầu mới cần đánh giá/triển khai:

-   PostgreSQL: dữ liệu quan hệ có cấu trúc, đặc biệt dữ liệu nghiệp
    vụ/transaction.
-   MongoDB: dữ liệu bán cấu trúc/JSON có schema linh hoạt.
-   MinIO: ảnh/file/object phi cấu trúc.
-   Indexing có lý do dựa trên workload.
-   Phân mảnh ngang và dọc.
-   Kiến trúc dữ liệu phân tán có chiến lược và sơ đồ.
-   JSON schema + ví dụ.
-   Test, migration, backup/rollback.
-   Báo cáo và PPT.

**Nguyên tắc:** không đánh dấu hoàn thành chỉ vì container/database chạy
được. Mỗi hạng mục phải có thiết kế → code/config → test → evidence.

------------------------------------------------------------------------

# 2. Những phát hiện đã xác nhận

## F-001 --- PostgreSQL hiện là nguồn dữ liệu chính

`PROJECT_GUIDE.md` xác nhận PostgreSQL 16 là database hiện tại; schema,
function/trigger và seed được quản lý SQL-first trong `database/`.

**Ảnh hưởng:** không nên chuyển toàn bộ dữ liệu sang MongoDB. MongoDB
phải có vai trò bổ sung.

## F-002 --- SQL-first

Schema chuẩn nằm trong `database/`; ORM chỉ mapping.

**Ảnh hưởng:** thay đổi DB phải bắt đầu từ SQL, sau đó đồng bộ
ORM/Pydantic/CRUD/API/test.

## F-003 --- `init_db.py` không phải migration system

Nếu `public."user"` đã tồn tại, script bỏ qua `init.sql`.

**Ảnh hưởng:** thay đổi schema phải có migration/update SQL có kiểm
soát.

## F-004 --- Media hiện có local filesystem flow

Project có `backend/app/services/storage.py`, `/media`, seed media và
Docker volume `media`.

**Ảnh hưởng:** MinIO migration phải kiểm tra backend + frontend media
URL + Nginx + Docker.

## F-005 --- Test backend dùng PostgreSQL thật

Integration tests dùng PostgreSQL với schema/seed thật.

**Ảnh hưởng:** MongoDB/MinIO phải được bổ sung vào integration-test
strategy, không thay thế PostgreSQL test.

## F-006 --- Chưa có bằng chứng MongoDB/MinIO trong repository hiện được cung cấp

Cấu trúc/tài liệu hiện có chưa chứng minh các service này đã được tích
hợp.

**Ảnh hưởng:** coi đây là phần xây mới, không mô tả như tính năng đã tồn
tại.

## F-007 --- Chưa đủ bằng chứng để chốt fragmentation

Chưa audit nội dung toàn bộ schema/query/index trong tài liệu hiện có.

**Hành động:** đọc toàn bộ SQL + CRUD/API query trước khi chọn fragment
key.

## F-008 --- Chưa đủ bằng chứng để chốt index

Phải đối chiếu existing indexes với workload và EXPLAIN ANALYZE.

## F-009 --- Phải phân biệt distributed architecture với PostgreSQL sharding

PostgreSQL + MongoDB + MinIO là polyglot/distributed data architecture,
nhưng chưa đồng nghĩa PostgreSQL đã sharding multi-node.

**Hành động:** chỉ gọi là distributed sharding/multi-node khi thực sự có
nhiều database nodes và routing/partitioning tương ứng.

## F-010 --- Transaction boundary là rủi ro chính

Cart/inventory/order/payment có logic nghiệp vụ quan trọng.

**Hành động:** giữ dữ liệu transaction-critical ở PostgreSQL; không
chuyển sang MongoDB chỉ để đáp ứng yêu cầu.

------------------------------------------------------------------------

# 3. Danh sách file bắt buộc kiểm tra trước khi chốt

## Gate A --- Repository/runtime

-   [ ] `README.md`
-   [ ] `PROJECT_GUIDE.md`
-   [ ] `docker-compose.yml`
-   [ ] `.dockerignore`
-   [ ] `.gitignore`
-   [ ] `backend/Dockerfile`
-   [ ] `backend/docker-entrypoint.sh`
-   [ ] `frontend/Dockerfile`
-   [ ] `frontend/nginx.conf`

Kiểm tra: service, network, volume, port, startup order, media path.

## Gate B --- PostgreSQL schema

Phải đọc toàn bộ:

-   [ ] `database/init.sql`
-   [ ] `database/config/database_config.sql`
-   [ ] toàn bộ `database/01_schema/*.sql`

Bắt buộc inventory:

-   [ ] PK
-   [ ] FK
-   [ ] UNIQUE
-   [ ] CHECK
-   [ ] DEFAULT
-   [ ] nullable
-   [ ] existing indexes
-   [ ] 1-1 / 1-N / N-N
-   [ ] search/filter/sort/pagination columns
-   [ ] ứng viên fragment/shard key

Không chốt ERD mới trước khi Gate B đạt.

## Gate C --- Functions/triggers

-   [ ] `database/02_functions/order_detail/triggers.sql`
-   [ ] `database/02_functions/system/audit_functions.sql`
-   [ ] `database/02_functions/system/business_functions.sql`
-   [ ] `database/02_functions/system/utility_functions.sql`
-   [ ] `database/02_functions/user/password_functions.sql`

Kiểm tra trigger/business rule/transaction nào phụ thuộc bảng bị phân
mảnh.

## Gate D --- Seeds/media

-   [ ] toàn bộ `database/03_seeds/**/seed.sql`
-   [ ] `database/03_seeds/media/**`

Kiểm tra dữ liệu test, media seed và migration.

## Gate E --- SQLAlchemy/CRUD

-   [ ] `backend/app/core/database.py`
-   [ ] `backend/app/models/__init__.py`
-   [ ] `backend/app/models/cart.py`
-   [ ] `backend/app/models/catalog.py`
-   [ ] `backend/app/models/order.py`
-   [ ] `backend/app/models/system.py`
-   [ ] `backend/app/models/user.py`
-   [ ] `backend/app/crud/base.py`
-   [ ] `backend/app/crud/category.py`
-   [ ] `backend/app/crud/order.py`
-   [ ] `backend/app/crud/product.py`
-   [ ] `backend/app/crud/shopping_cart.py`
-   [ ] `backend/app/crud/user.py`
-   [ ] `backend/app/crud/admin.py`
-   [ ] `backend/app/crud/moderator.py`

Kiểm tra query, transaction boundary, ORM mapping và truy vấn cần
EXPLAIN.

## Gate F --- API contract

-   [ ] `backend/app/api/router.py`
-   [ ] `backend/app/api/deps.py`
-   [ ] toàn bộ `backend/app/api/v1/*.py`
-   [ ] toàn bộ `backend/app/schemas/*.py`

Đặc biệt audit products/users/cart/orders/system/admin/moderator để biết
API nào sẽ đọc store nào.

## Gate G --- MinIO/media

-   [ ] `backend/app/services/storage.py`
-   [ ] `backend/app/main.py`
-   [ ] `frontend/src/app/core/utils/media-url.ts`
-   [ ] `frontend/src/environments/environment.ts`
-   [ ] `frontend/src/environments/environment.prod.ts`
-   [ ] `frontend/nginx.conf`
-   [ ] API upload trong `backend/app/api/v1/`
-   [ ] schemas liên quan image/avatar

Mục tiêu: `Angular → FastAPI → MinIO`, còn PostgreSQL lưu
metadata/object key/reference.

## Gate H --- MongoDB

Hiện chưa có MongoDB theo tài liệu. Phải audit trước khi thêm:

-   [ ] `backend/requirements.txt`
-   [ ] `backend/requirements-dev.txt`
-   [ ] `backend/requirements.lock`
-   [ ] `backend/requirements-dev.lock`
-   [ ] `backend/app/core/config.py`
-   [ ] `backend/.env.example`
-   [ ] `docker-compose.yml`
-   [ ] `deploy/docker-compose.yml`

Sau khi chốt data ownership mới tạo connection/repository layer.

## Gate I --- MongoDB JSON model

Phải chốt:

-   [ ] collection
-   [ ] document
-   [ ] `_id`
-   [ ] PostgreSQL business key/reference
-   [ ] required/optional fields
-   [ ] nested object/array
-   [ ] version/timestamp
-   [ ] validation
-   [ ] indexes

Không chuyển order/payment/inventory transaction-critical data sang
MongoDB chỉ để "có MongoDB".

## Gate J --- Indexing

Audit:

-   [ ] existing indexes trong `database/01_schema/*.sql`
-   [ ] query trong `backend/app/crud/*.py`
-   [ ] API query
-   [ ] FK columns
-   [ ] filter/search/sort/pagination columns
-   [ ] PostgreSQL extensions trong
    `database/config/database_config.sql`

Mỗi index phải có workload justification + EXPLAIN ANALYZE.

## Gate K --- Horizontal fragmentation

Phải xác định:

-   [ ] fragment key
-   [ ] predicate
-   [ ] completeness
-   [ ] disjointness
-   [ ] reconstruction
-   [ ] query routing
-   [ ] FK implications
-   [ ] transaction implications

Ứng viên cần đánh giá: products theo category/seller/status; orders theo
seller/user/time/status; logs/feedback theo time; reviews theo product.

**Nếu chỉ partition trong một PostgreSQL instance thì ghi đúng là
partitioning/logical fragmentation, không gọi là multi-node sharding.**

## Gate L --- Vertical fragmentation

Đánh giá bảng có nhóm cột thường truy cập và ít truy cập/nặng, ví dụ
`products`.

Mỗi fragment phải có khóa chung để reconstruction.

Chỉ tách khi workload chứng minh có lợi.

## Gate M --- Distributed architecture

-   [ ] `docker-compose.yml`
-   [ ] `deploy/docker-compose.yml`
-   [ ] `docs/deployment.md`
-   [ ] `.github/workflows/ci.yml`
-   [ ] `.github/workflows/deploy.yml`
-   [ ] `deploy/scripts/backup-db.sh`
-   [ ] `deploy/scripts/restore-db.sh`
-   [ ] `deploy/scripts/bootstrap-vps.sh`
-   [ ] `deploy/scripts/deploy.sh`

Phải chốt
PostgreSQL/MongoDB/MinIO/backend/network/volume/healthcheck/backup/restore/failure
model.

## Gate N --- Frontend impact

Audit tối thiểu:

-   [ ] `frontend/src/app/shared/services/product.service.ts`
-   [ ] `frontend/src/app/shared/services/order.service.ts`
-   [ ] `frontend/src/app/core/services/auth.service.ts`
-   [ ] `frontend/src/app/core/services/cart.service.ts`
-   [ ] `frontend/src/app/core/services/payment.service.ts`
-   [ ] `frontend/src/app/core/utils/media-url.ts`
-   [ ] `frontend/src/environments/environment.ts`
-   [ ] `frontend/src/environments/environment.prod.ts`
-   [ ] product detail/shop
-   [ ] seller product management
-   [ ] customer profile/avatar

Mục tiêu: giữ API contract và media URL tương thích.

## Gate O --- Tests/CI

-   [ ] `backend/tests/conftest.py`
-   [ ] `backend/tests/test_system.py`
-   [ ] `backend/tests/test_v1_admin.py`
-   [ ] `backend/tests/test_v1_auth.py`
-   [ ] `backend/tests/test_v1_cart.py`
-   [ ] `backend/tests/test_v1_category.py`
-   [ ] `backend/tests/test_v1_moderator.py`
-   [ ] `backend/tests/test_v1_order.py`
-   [ ] `backend/tests/test_v1_product.py`
-   [ ] `backend/tests/test_v1_user.py`
-   [ ] frontend test config
-   [ ] `.github/workflows/ci.yml`

Phải có test cho PostgreSQL, MongoDB, MinIO, fragmentation, indexing,
cross-store reference, failure/retry và migration.

------------------------------------------------------------------------

# 4. Gate chốt trước implementation

Tất cả phải đạt:

-   [ ] Data ownership: mỗi dữ liệu có một source of truth.
-   [ ] PostgreSQL giữ business-critical/transaction data.
-   [ ] MongoDB giữ dữ liệu bán cấu trúc đã được xác định.
-   [ ] MinIO giữ binary/object.
-   [ ] ERD hoàn chỉnh.
-   [ ] Vertical fragmentation có lý do và reconstruction.
-   [ ] Horizontal fragmentation có predicate và reconstruction.
-   [ ] Index có workload justification.
-   [ ] Có EXPLAIN ANALYZE.
-   [ ] Có distributed architecture diagram.
-   [ ] Có data flow.
-   [ ] Có failure strategy.
-   [ ] Có backup/restore.
-   [ ] Có JSON schema + example.
-   [ ] Có migration plan.
-   [ ] Có rollback plan.
-   [ ] Có clean test DB.
-   [ ] Không phá SQL-first convention.

**Chỉ khi tất cả đạt mới đổi trạng thái: `READY FOR IMPLEMENTATION`.**

------------------------------------------------------------------------

# 5. Kế hoạch 7 ngày sau khi Gate đạt

## Ngày 1 --- Full audit & freeze architecture

### Checklist

-   [ ] Audit repository/runtime.
-   [ ] Audit toàn bộ PostgreSQL schema.
-   [ ] Audit function/trigger.
-   [ ] Audit ORM/CRUD/query.
-   [ ] Audit API/schema.
-   [ ] Audit storage/media.
-   [ ] Audit Docker/deployment.
-   [ ] Audit tests/CI.
-   [ ] Ghi toàn bộ finding.
-   [ ] Chốt data ownership.
-   [ ] Chưa triển khai production feature.

**Deliverable:** review report + architecture decision.

## Ngày 2 --- ERD + fragmentation design

-   [ ] ERD hiện tại.
-   [ ] ERD sau thay đổi.
-   [ ] Vertical fragmentation.
-   [ ] Horizontal fragmentation.
-   [ ] Predicates.
-   [ ] Reconstruction.
-   [ ] FK/trigger impact.
-   [ ] Transaction impact.
-   [ ] Migration design.

**Deliverable:** ERD + fragmentation specification.

## Ngày 3 --- Indexing + PostgreSQL

-   [ ] Existing index inventory.
-   [ ] Query workload inventory.
-   [ ] Proposed index SQL.
-   [ ] EXPLAIN trước.
-   [ ] EXPLAIN sau.
-   [ ] Fragment test.
-   [ ] Regression test.
-   [ ] Rollback SQL.

**Deliverable:** PostgreSQL migration + index/performance report.

## Ngày 4 --- MongoDB

-   [ ] MongoDB container.
-   [ ] network/volume/healthcheck.
-   [ ] environment.
-   [ ] connection layer.
-   [ ] repository.
-   [ ] collection.
-   [ ] JSON schema.
-   [ ] MongoDB indexes.
-   [ ] API integration.
-   [ ] tests.

**Deliverable:** MongoDB chạy độc lập và qua FastAPI.

## Ngày 5 --- MinIO

-   [ ] MinIO service.
-   [ ] bucket.
-   [ ] credentials qua env.
-   [ ] backend storage client.
-   [ ] upload.
-   [ ] read/download.
-   [ ] delete.
-   [ ] product image integration.
-   [ ] avatar integration.
-   [ ] metadata/reference trong PostgreSQL.
-   [ ] migration sample.
-   [ ] tests.

**Deliverable:** `Angular → FastAPI → MinIO` và metadata/reference →
PostgreSQL.

## Ngày 6 --- Distributed integration + testing

-   [ ] Architecture diagram.
-   [ ] Cross-store integration test.
-   [ ] MongoDB unavailable test.
-   [ ] MinIO unavailable test.
-   [ ] PostgreSQL unavailable test.
-   [ ] retry/error handling.
-   [ ] backup.
-   [ ] restore.
-   [ ] Docker restart.
-   [ ] CI.
-   [ ] regression suite.

**Deliverable:** `TEST_REPORT.md`.

## Ngày 7 --- Report + PPT + final acceptance

-   [ ] ERD.
-   [ ] Distributed architecture.
-   [ ] Data flow.
-   [ ] Fragmentation diagram.
-   [ ] JSON examples.
-   [ ] Index table.
-   [ ] Performance comparison.
-   [ ] Test evidence.
-   [ ] Docker architecture.
-   [ ] Final report.
-   [ ] PPT.
-   [ ] Demo scenario.
-   [ ] Final TODO review.

**Deliverable:** final report + PPT + source + migration + test
evidence.

------------------------------------------------------------------------

# 6. Audit log cần ghi trong quá trình review

  ------------------------------------------------------------------------------------------------------------------
  File                                      Nội dung kiểm tra        Finding     Ảnh hưởng   Action      Status
  ----------------------------------------- ------------------------ ----------- ----------- ----------- -----------
  `database/01_schema/products.sql`         PK/FK/index/columns      TBD         TBD         TBD         TODO

  `database/01_schema/orders.sql`           transaction/order        TBD         TBD         TBD         TODO

  `database/01_schema/order_details.sql`    FK/quantity/price        TBD         TBD         TBD         TODO

  `database/01_schema/product_images.sql`   media reference          TBD         TBD         TBD         TODO

  `backend/app/crud/product.py`             catalogue queries        TBD         TBD         TBD         TODO

  `backend/app/crud/order.py`               order transaction        TBD         TBD         TBD         TODO

  `backend/app/services/storage.py`         media storage            TBD         TBD         TBD         TODO

  `docker-compose.yml`                      service/network/volume   TBD         TBD         TBD         TODO

  `backend/.env.example`                    DB/storage config        TBD         TBD         TBD         TODO

  `backend/tests/conftest.py`               test DB lifecycle        TBD         TBD         TBD         TODO
  ------------------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

# 7. Decision log

  ID      Quyết định                                          Trạng thái
  ------- --------------------------------------------------- ------------
  D-001   PostgreSQL giữ transaction/business-critical data   PROPOSED
  D-002   MongoDB dùng cho dữ liệu bán cấu trúc               PROPOSED
  D-003   MinIO dùng cho binary/object                        PROPOSED
  D-004   PostgreSQL vẫn là relational source of truth        PROPOSED
  D-005   `init_db.py` không được coi là migration            CONFIRMED
  D-006   Không chốt fragmentation trước query audit          REQUIRED
  D-007   Không chốt index trước workload audit               REQUIRED
  D-008   Không gọi multi-store là PostgreSQL sharding        REQUIRED
  D-009   Migration phải có backup/rollback                   REQUIRED

------------------------------------------------------------------------

# 8. Kết luận

Bước tiếp theo **không phải lập tức thêm MongoDB/MinIO**. Đúng quy trình
là:

`Full file audit → data ownership → workload analysis → ERD → fragmentation/index decision → Gate approval → implementation`

Tài liệu hiện tại đã xác nhận kiến trúc PostgreSQL/SQL-first, các vùng
code cần ảnh hưởng và các rủi ro chính. Tuy nhiên, **chưa đủ bằng chứng
để chốt fragment key, index cụ thể hoặc thiết kế MongoDB cụ thể** cho
đến khi đọc nội dung thực tế của các SQL/CRUD/API/query tương ứng.
