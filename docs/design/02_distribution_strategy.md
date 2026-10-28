# Ngày 2 — Chiến lược phân tán và hạ tầng một máy

Ngày: 28/10/2026. Căn cứ: [D1–D6](../decisions.md), [audit Ngày 1](../DAY1_REVIEW.md).
Sơ đồ: [02_distribution_diagram.puml](../diagram/02_distribution_diagram.puml).
Phân mảnh/allocation: [02_fragmentation_matrix.md](02_fragmentation_matrix.md),
[02_fragmentation_model.puml](../diagram/02_fragmentation_model.puml).
Nhật ký thực nghiệm: [DAY2_FINDINGS_LOG.md](../DAY2_FINDINGS_LOG.md).

## 1. Phạm vi và trạng thái

Ngày 2 dựng nền PG/Mongo/MinIO và replication tùy chọn, giữ nguyên ứng dụng hiện tại.
Database vẫn có **18 bảng baseline**; các fragment và user split trong sơ đồ là mô hình đích,
chưa được tạo bằng Compose. D7/D8 chưa chốt và không có chuyển timestamp/status dữ liệu cũ ở bước này.

| Thành phần | Ngày 2 | Bước tiếp theo |
|---|---|---|
| PG primary + role replication + standby | Compose/scripts + kiểm tra streaming | Ngày 4: partition/index/user split, Ngày 6: read routing |
| Mongo replica set + keyfile + user ứng dụng | 1 member, profile thêm 2 data-bearing member | Ngày 3: collection/validator/client; Ngày 5: ETL |
| MinIO single-node | Volume riêng + readiness + console/S3 endpoint | Ngày 3: bucket/policy/user ứng dụng/upload client |
| Backend/frontend | Build từ source, baseline PG và local media | Ngày 3–6: hợp nhất Mongo/MinIO, thay readiness |
| ETL outbox/worker | Thiết kế D2, chưa có service chạy | Ngày 5: mã worker và service; không tạo container ngủ giả làm worker |

Base stack gồm pg-primary, mongo1, mongo-init (one-shot), minio, backend, frontend.
Profile `resilience` thêm pg-replica, mongo2, mongo3, mongo-expand (one-shot).
Mọi container/volume nằm cùng một máy; profile kiểm chứng replication, không chứng minh HA nhiều máy.

## 2. Tính nhất quán và truy vấn

- Checkout/cart/stock/ví đọc và ghi PG primary. SELECT FOR UPDATE hiện tại vẫn dùng primary.
- Replica PG streaming async, read-only; chưa thêm get_read_db hoặc tự chuyển khi primary lỗi.
- Mongo lưu document BSON; thuộc tính động mới ghi trực tiếp khi client được triển khai.
  Bản đọc order/review/log eventual qua outbox Ngày 5, poll 60 giây, mục tiêu dưới 5 phút
  ở tải bình thường. Đây là mục tiêu thiết kế, chưa có số đo ETL.
- Product query/ILIKE vẫn ở PG; không đưa truy vấn tồn kho/checkout sang Mongo.
- MinIO lưu byte file; metadata/key có một chủ sở hữu PG/Mongo theo D1. Chưa dual-write
  object và metadata như thể một transaction ACID đa kho.
- Truy vấn parent PG che chi tiết partition; full view tái tạo user là read-only.
  FDW theo vùng và shard key Mongo chỉ nghiên cứu cho giai đoạn nhiều máy.

## 3. Khởi tạo và khởi động lại

**PostgreSQL:** image postgres:16-alpine. Init hook tạo role oldshop_repl chỉ có LOGIN/REPLICATION,
thêm HBA replication scram; primary bật wal_level/max_wal_senders/wal_keep_size.
Backend chạy bootstrap baseline trên DB mới; restart bỏ qua init theo hành vi đã audit.
Standby trên volume mới chạy pg_basebackup với write-recovery-conf, nhận WAL từ pg-primary;
volume đã có PG_VERSION chỉ tiếp tục nếu còn standby.signal. Không tự xóa volume hoặc reseed.
Không dùng replication slot giữ WAL vô hạn; wal_keep_size=256MB là retention hữu hạn,
standby nghỉ lâu có thể cần quy trình rebuild có kiểm soát, không hứa bắt kịp mọi độ trễ.

**Mongo:** script start tạo keyfile mode 400/chủ mongodb trong /run/oldshop-mongo,
official entrypoint bootstrap root khi volume rỗng. mongo-init xác thực root,
init oldshop-rs nếu chưa có rồi tạo user readWrite chỉ trong database oldshop.
Profile thêm từng voting member một lần reconfigure và chờ SECONDARY/committed config trước lần tiếp theo.
Rerun init không xóa user, không hạ set 3 member về 1.
Mongo healthcheck ping chỉ đo tiến trình, không thay thế rs.status và kiểm chứng user/primary;
job init/expand cùng verifier là gate topology thực tế.
Backend có optional dependency service_completed_successfully tới mongo-expand để
Compose --wait xử lý đúng job one-shot khi profile được bật.

**MinIO:** image ghim digest của release người dùng cung cấp,
RELEASE.2025-09-07T16-13-09Z. Readiness HTTP kiểm server; chưa coi đó là test upload/S3 policy.
App chưa được cấp root MinIO; STORAGE_BACKEND vẫn local, user scoped theo bucket sẽ tạo Ngày 3.

Đổi password trong .env.data sau khi DB đã init **không tự rotate credential trong DB**.
Giữ file này để restart dùng lại; rotate phải có quy trình thay credential của các thành viên/client.

## 4. Chạy từ repository root

```bash
python3 deploy/scripts/prepare-data-env.py
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml config --quiet
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml up -d --build
python3 deploy/scripts/check-data-stack.py --output docs/day2/base-verification.json
```

Generator tạo credential ngẫu nhiên trong deploy/.env.data mode 600, từ chối ghi đè.
Nếu file đã có, bỏ qua lệnh generator và dùng credential hiện hữu. .env.data không được commit;
.env.data.example chứa placeholder nên không dùng trực tiếp để chạy stack.

**Ngoại lệ kernel trên máy kiểm thử:** Mongo8.0.32 không khởi động được trên kernel hiện tại,
đã được người dùng đồng ý kiểm thử bằng Mongo7 riêng. Trước lần chạy đầu tiên, chỉnh
`MONGO_IMAGE=mongo:7.0` trong .env.data nếu gặp cùng vấn đề.
Không chuyển image Mongo8→7 trên volume đã có WiredTiger/data Mongo8.
Chi tiết và nguồn lỗi nằm trong DAY2_FINDINGS_LOG; không dùng GLIBC tunable để bypass guard.
Khi triển khai trên máy tương thích Mongo8, dùng volume mới và mặc định 8.0.32, kiểm tra lại toàn bộ.

**Địa chỉ local mặc định:**

| Dịch vụ | Địa chỉ | Credential |
|---|---|---|
| Shop | http://localhost:58080 | Tài khoản dev seed baseline |
| API docs | http://localhost:58000/api/docs | — |
| PG primary / pgAdmin desktop | 127.0.0.1:55432, database oldshop | DB_USER/DB_PASSWORD trong .env.data |
| PG replica (profile) | 127.0.0.1:55433 | User PG tương ứng; read-only |
| MinIO S3 / console | http://localhost:59000 / http://localhost:59001 | MINIO_ROOT_USER/PASSWORD cho quản trị |
| Mongo | Nội bộ mongo1:27017 | App user readWrite; dùng compose exec/mongosh khi quản trị |

Mongo hostname trong replica config chỉ resolve trong network Compose. Không hứa host Compass
truy cập full replica set chỉ bằng publish một port; cần thiết kế hostname/split-horizon riêng nếu muốn.
Compose không publish Mongo, không nối vào lab03-mongo/minio-local.

**Profile dự phòng:**

```bash
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience up -d
python3 deploy/scripts/check-data-stack.py --resilience --output docs/day2/resilience-verification.json
```

Nếu cần chạy lại job Mongo theo yêu cầu, dùng `docker compose ... run --rm mongo-init`
hoặc `... run --rm mongo-expand` sau khi các tiến trình DB khỏe; script có kiểm tra trạng thái sẵn có.
Bỏ `--profile resilience` không xóa config/member đã thêm. Sau khi set đã có 3 voting member,
phải tiếp tục chạy đủ member cho quorum hoặc thực hiện reconfigure có kế hoạch;
không đơn giản tắt cả mongo2 và mongo3 rồi kỳ vọng mongo1 tiếp tục ghi.

**Dừng, giữ dữ liệu:**

```bash
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience stop
# Hoặc gỡ container/network, vẫn giữ named volumes:
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience down
```

Không thêm `-v` nếu cần giữ dữ liệu. Docker Compose mặc định name oldshop-data;
nếu đổi project name thì đó là bộ volume khác, không phải mất dữ liệu của project trước.

## 5. Tài nguyên và cô lập

Máy báo 8 CPU/~7.5 GiB; đang có Mongo/MinIO ngoài dự án.
Compose đặt giới hạn: PG mỗi node 512 MiB; Mongo mỗi node 768 MiB/cache 0.25 GiB;
MinIO 512 MiB; backend 768 MiB; frontend 128 MiB; job Mongo 256 MiB.
Tổng limit base tiến trình dài hạn ~2.6 GiB, profile ~4.6 GiB, chưa tính job/build,
container có sẵn, Docker/OS và page cache. Limit không phải lượng RAM được bảo đảm cấp trước.
Chụp docker stats khi kiểm tra; tải seed nhẹ không phải benchmark vận hành.

Data/web là network bridge riêng, DB chỉ công bố PG loopback cho pgAdmin;
MinIO/API/shop cũng chỉ bind 127.0.0.1. Dịch vụ tùy chọn gọi API ngoài vẫn có outbound;
đây không phải cấu hình mạng production hoặc TLS đầy đủ.

## 6. Chịu lỗi và mở rộng

| Sự cố | Cam kết hiện tại |
|---|---|
| PG replica dừng | Primary vẫn phục vụ; standby có thể replay bù nếu WAL còn |
| Mongo secondary trong profile dừng | Hai member còn lại giữ majority; cần test runtime và reconnect |
| Mongo1 mặc định dừng | Không có primary khác; hiện API PG còn chạy, metadata mới/ETL tương lai không khả dụng |
| MinIO dừng | API PG vẫn có thể chạy; media MinIO tương lai không được coi là vẫn phục vụ |
| PG primary dừng | App core mất readiness; không tự promote standby |
| Cả máy dừng | Toàn bộ stack dừng; backup ngoài máy/restore và multi-host là bước sau |

Chưa có Patroni, fencing, service endpoint failover, distributed MinIO hay backup/restore tự động
đa kho trong Ngày 2. Mở rộng nhiều máy phải phân bố quorum và bản sao qua failure domain độc lập,
đồng thời xử lý chuyển kết nối app, bí mật/TLS, storage và backup, không chỉ sửa hostname.

## 7. Nguồn kỹ thuật và kiểm chứng

- [PostgreSQL pg_basebackup](https://www.postgresql.org/docs/16/app-pgbasebackup.html): physical standby và recovery config.
- [MongoDB keyfile replica set](https://www.mongodb.com/docs/v8.0/tutorial/deploy-replica-set-with-keyfile-access-control/): xác thực nội bộ/client.
- [Docker Compose profiles](https://docs.docker.com/compose/how-tos/profiles/): bật các service tùy chọn.
- Các file evidence JSON chỉ chứa trạng thái/version/LSN/count và resource sample, không chứa env/credential.
- Checklist cuối và ngoại lệ phiên bản nằm trong DAY2_FINDINGS_LOG; không lấy thiết kế đích làm bằng chứng migration đã áp dụng.
