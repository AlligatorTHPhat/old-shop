# Ngày 2 — Nhật ký phát hiện và kiểm chứng

Ngày: 28/10/2026, Asia/Ho_Chi_Minh. Quyết định đầu vào: [decisions.md](decisions.md).

## F1 — Môi trường Docker thực tế

- Docker Engine/client 29.7.2, Compose v5.5.0.
- Docker báo 8 CPU, 8.053.366.784 byte RAM (xấp xỉ 7,5 GiB).
- Kernel Docker: **7.0.0-30-generic**.
- Container sẵn có: lab03-mongo dùng mongo:8.0.32, publish loopback 27017;
  minio-local dùng MinIO RELEASE.2025-09-07T16-13-09Z, cổng 9090/9091.
- Không restart/sửa/xóa các container/volume này; stack mới là project oldshop-data,
  volume riêng, cổng 55432/55433/58000/58080/59000/59001.

## F2 — MongoDB 8.0.32 bị startup guard chặn kernel

Khi khởi động mongo1 mới từ image mongo:8.0.32, mongod dừng trước khi bootstrap DB:

```text
MongoDB cannot start: Linux kernel versions 6.19 and newer has a known
incompatibility with this version of MongoDB.
See https://jira.mongodb.org/browse/SERVER-121912 for more information.
```

Đã xác nhận image 8.0.32 và gitVersion khớp phiên bản người dùng cung cấp.
Container lab03-mongo đang chạy có `GLIBC_TUNABLES=glibc.pthread.rseq=1`.
Đây là quan sát cấu hình, không phải bằng chứng workaround an toàn cho mọi workload.
Không sao chép thiết lập này sang stack mới để bỏ qua guard.

MongoDB ghi nhận vấn đề TCMalloc/kernel tại [SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912).
Issue [SERVER-136848](https://jira.mongodb.org/browse/SERVER-136848) mô tả trường hợp
MongoDB 8.0.32 đọc uname của Ubuntu không phản ánh đầy đủ phiên bản upstream kernel.
Chưa xác minh kernel máy này chứa bản vá upstream nào, nên không kết luận guard ở đây là false positive.

**Xử lý được người dùng đồng ý:** dùng MongoDB 7.0 riêng để kiểm thử trên máy hiện tại,
ghi lại phát hiện bằng Markdown. `deploy/.env.data` chọn mongo:7.0;
Compose và `.env.data.example` vẫn mặc định mongo:8.0.32 cho môi trường tương thích.
Không gắn volume Mongo8 đã có dữ liệu vào Mongo7; volume mới bị lỗi phải được kiểm tra
trước khi chuyển image. Không nâng/hạ phiên bản DB đã sử dụng một cách tự động.
Kiểm thử Mongo7 không được dùng làm bằng chứng Mongo8 đã chạy thành công.

## F3 — Keyfile cần tạo lại được sau restart

Lần khởi động đầu ghi keyfile vào /tmp rồi chown mongodb/mode 400.
Khi restart, ghi đè file khác chủ trong thư mục sticky /tmp bị Permission denied.
Đã chuyển sang `/run/oldshop-mongo/keyfile`, thư mục riêng mode 755, key mode 400,
chủ mongodb; key không nằm trong Git hoặc log.

## Phạm vi

- Ngày 2 tạo thiết kế đích và hạ tầng; schema ứng dụng vẫn là baseline đã audit.
- Partition/tách user thực hiện Ngày 4, collection/storage client Ngày 3,
  ETL outbox/worker Ngày 5 và hợp nhất API Ngày 6.
- Chưa tạo idle worker để giả lập ETL hoạt động; readiness API hiện chỉ kiểm PG.
- API readiness hiện chỉ kiểm PG; Mongo/MinIO được verifier hạ tầng kiểm riêng.

## F4 — Compose wait cần nhận diện job one-shot

Lượt đầu `up --wait` đã khởi động app nhưng trả lỗi khi mongo-expand kết thúc exit 0,
vì job không có dependent yêu cầu service_completed_successfully.
Đã khai báo backend chờ mongo-expand với required=false: base không cần profile này,
resilience chờ topology mở rộng hoàn tất. Chạy lại `up --wait` thành công.
Không đổi job thành container ngủ chỉ để có trạng thái running.

## F5 — Kết quả đã kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Compose base và profile config | PASS, không xuất credential ra log |
| Build backend/frontend từ source | PASS; backend download apt chậm (~12 phút), build hoàn tất |
| Mongo7 khởi tạo một member | PASS; mongo-init log PRIMARY mongo1 trước mở rộng |
| Mongo profile 3 member | PASS: PRIMARY mongo1, SECONDARY mongo2/mongo3 |
| Phiên bản Mongo thực nghiệm | **7.0.43**, từ image mongo:7.0 có sẵn; không phải 8.0.32 |
| Auth ứng dụng Mongo | PASS, user readWrite trong database oldshop |
| PostgreSQL | **16.15**, primary không recovery, replica recovery và streaming async |
| WAL replay / dữ liệu replica | PASS, replica đạt LSN lấy từ primary; cùng 30 order baseline |
| API readiness/catalogue | HTTP 200 |
| Frontend health + proxy catalogue | HTTP 200 |
| MinIO readiness | HTTP 200, đúng RELEASE.2025-09-07T16-13-09Z |
| Dừng Mongo secondary | PRIMARY còn ghi majority; tạo/xóa probe riêng thành công; secondary đã start lại |
| Dừng PG replica | Primary vẫn phục vụ; replica đã start lại |
| PlantUML syntax | PASS cho cả 2 sơ đồ, bằng PlantUML 1.2025.10 -checkonly; không xuất PNG |
| Baseline schema | Vẫn 18 bảng; chưa áp partition/user split/ETL outbox |

Bằng chứng máy đọc được: [day2/resilience-verification.json](day2/resilience-verification.json),
[day2/fault-verification.json](day2/fault-verification.json).
Resource sample của profile sau kiểm tra: các service mới dùng tổng xấp xỉ 318 MiB theo docker stats
tại thời điểm đo; đây là tải seed nhẹ, không suy ra mức dùng khi benchmark hoặc load thật.
PG/Mongo/MinIO đều dùng volume mới; container lab03-mongo và minio-local còn chạy nguyên trạng.

Khởi tạo/reconfigure được chạy lại khi Compose up lần hai mà không reset dữ liệu hoặc hạ
replica set về một member. Keyfile restart đã được kiểm tra qua stop/start secondary.
Chưa test tắt Mongo PRIMARY, promote PG, mất máy, backup/restore, S3 upload hay ETL.

## Bàn giao Ngày 2

- Hoàn tất tài liệu chiến lược, chứng minh trên mô hình và allocation matrix.
- Hoàn tất hạ tầng + profile dự phòng trên **Mongo7 theo ngoại lệ đã được đồng ý**.
- Mongo8 vẫn là mục tiêu cấu hình cho kernel tương thích; phải kiểm tra lại trước triển khai thực.
- Stack oldshop-data đang chạy profile resilience để người dùng xem/demo;
  hướng dẫn stop/down giữ volume trong docs/design/02_distribution_strategy.md.
- Ngày 3 tiếp tục validator/collection, client Mongo/MinIO, bucket-scoped application credentials.
- Trước Ngày 4/5 cần chốt D7/D8 và thực hiện migration runner; không dựa vào restart để migrate.
