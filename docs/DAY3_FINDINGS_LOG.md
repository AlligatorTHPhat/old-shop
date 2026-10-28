# Ngày 3 — JSON, MongoDB và MinIO

Thực hiện ngày 28/10/2026 (kế hoạch dự kiến 29/10). Phạm vi theo checklist Ngày 3;
không chạy ETL Ngày 5, không thay migration/partition Ngày 4.

## Đã triển khai

- Sáu collection: product_details, reviews, order_snapshots, system_logs,
  violation_logs, contact_messages. Pydantic strict, BSON validator strict/error,
  index unique/compound/text/partial; riêng bản sao system_logs TTL 90 ngày.
- `backend/scripts/init_mongo.py` chạy lặp bằng collMod/create_index, không drop dữ liệu.
  Job quản trị riêng; backend dùng quyền readWrite. Mongo client có timeout và majority write concern.
- Ba bucket private, tài khoản ứng dụng giới hạn bucket. SDK pymongo 4.19.0,
  minio 7.2.20 được khóa hash trong cả runtime/dev lock.
- LocalStorage/MinioStorage; giữ URL `/media/...`, FastAPI stream S3 qua SDK,
  Nginx tiếp tục proxy backend. Không cần thay `media-url.ts` hay nginx.conf.
  Readiness kiểm tra PG/Mongo/MinIO; liveness độc lập.
- Seed media giữ alias legacy và tạo key chuẩn, không cập nhật PG/ghi đè object.
  Avatar mới dùng UUID bất biến để rollback/caching an toàn; avatar.ext chỉ là alias seed.
  Upload bù trừ object mới khi commit PG thất bại; avatar cũ không tự xóa.
- Thiết kế, field/type/required và ví dụ: [03_json_design.md](design/03_json_design.md),
  [03_document_examples.json](design/03_document_examples.json),
  [03_mongo_validators.json](design/03_mongo_validators.json).

## Phát hiện và quyết định

1. Mongo 8.0.32 vẫn vướng startup guard kernel như Ngày 2. Kiểm thử trên
   Mongo 7.0.43 đã được người dùng cho phép; không tuyên bố đã test Mongo 8.
   Giữ nguyên lab03-mongo, minio-local và dữ liệu của các container đó.
2. MinIO đúng bản RELEASE.2025-09-07T16-13-09Z bằng digest đã khóa từ Ngày 2.
   Có sẵn `mc` trong image, không cần image mc floating khác.
3. URL seed không khớp quy tắc product ID trong tên file: dùng ProductImage.product_id
   thật để tạo key chuẩn. Còn thiếu 11 avatar trong nguồn seed; chỉ URL seed đã biết
   nhận fallback default.png, không thay thế ảnh upload người dùng bị thiếu bằng seed.
4. Bucket private cần ký S3 request: chọn gateway SDK thay vì Nginx truy cập bucket
   không xác thực. Ảnh sản phẩm/avatar vẫn đọc công khai qua gateway như ứng dụng cũ;
   attachments bị chặn khỏi route này, chưa có API attachment có kiểm quyền.
5. Không tự đổi timezone nguồn (D7), không tự ánh xạ transaction.status=4 (D8).
   Validator chặn field PII ngoài hợp đồng nhưng không lọc PII trong text/attributes;
   ETL sau này phải lọc và chỉ cập nhật trường do PG sở hữu.
6. Test host ban đầu lỗi do DEBUG=release từ môi trường; ghi đè DEBUG=false chỉ cho
   test. Test async host tiếp tục chờ threadpool trong sandbox; chuyển kiểm thử sang
   container cùng runtime của app, không coi lượt host này là PASS.
7. Chạy pytest bằng entrypoint riêng cần tạo /tmp/prometheus. Lượt regression đầu
   sau chỉnh môi trường: 79 passed / 1 failed. Test metrics cũ gọi health bị loại khỏi
   instrumentation; sửa thành request categories để kiểm đúng bộ đếm, không đổi app metrics.

## Bằng chứng thực chạy

- Build image `oldshop-data-backend:day3` thành công với dependency hash-locked.
- Init sáu collection strict/error thành công; job chạy lại cùng stack không lỗi.
- Seed lượt 1: uploaded=95, skipped=0, missing=[], avatar_fallbacks=11.
- Seed lượt 2: uploaded=0, skipped=95, missing=[], avatar_fallbacks=11.
- Stack profile resilience lên healthy, backend MinIO hoạt động; frontend được restart
  để làm mới DNS upstream sau thay container backend.
- `/health/ready`: 200, database=up, mongo=up, minio=up.
- Ảnh legacy qua frontend Nginx: 200 image/jpeg, 188961 bytes.
- Truy cập object bucket trực tiếp không xác thực: 403 Forbidden (đúng policy private).
- Regression/integration cuối: **81 passed in 8.23s**, gồm 24 test Ngày 3; không skip.
  [Log thực chạy](evidence/day3_tests.log). Ruff lint/format và git diff --check đều đạt.
  DB riêng được giữ lại: `day3_test_20261028220621_21914`.

## Kiểm thử lại

Sau build/provision theo tài liệu thiết kế, chạy `bash deploy/scripts/test-day3.sh`.
Script tạo DB PostgreSQL mới theo timestamp/random, seed vào DB này và media /tmp riêng;
không ghi regression lên DB ứng dụng. Mongo test dùng ID ngẫu nhiên rồi dọn đúng document,
MinIO test dùng UUID rồi xóa đúng object. DB test được giữ lại với tên in cuối log để xem xét.
Không chạy nhiều lượt test đồng thời vì suite hiện có dùng dữ liệu seed/trạng thái trong DB test.

Tồn tại ngoài Ngày 3: ETL chưa đưa PG vào các collection, API chưa merge product_details;
GC ảnh cũ và API attachments có phân quyền chưa triển khai. Chuyển local → MinIO thực tế
cần chặn upload khi copy lượt cuối; quay lại local cần copy ảnh mới từ S3 về volume trước.
