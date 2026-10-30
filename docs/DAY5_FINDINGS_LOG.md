# Ngày 5 — ETL/outbox, 30/10/2026

**Ngày 5 đã hoàn tất trên stack local: code, kiểm thử và rollout đều đạt.**
Người dùng trả lời **“đồng ý”** sau khi được giải thích quy trình bảo trì. Đã chạy
`apply-day5.sh --resilience`, áp migration 005, full ETL hai lần, đối soát rồi mở lại dịch vụ.
[Bằng chứng rollout](evidence/day5_rollout.json), [kiểm tra stack](evidence/day5_stack.json).

Trước đó automatic approval review từ chối bước rollout vì chưa có chấp thuận rõ gây gián đoạn.
Trong thời gian chờ chỉ chạy DB thử và kiểm tra chỉ đọc; sau xác nhận mới chạy lại quy trình
đã trình bày. Không vượt từ chối bằng cách đổi cách gọi.

## D7 đã làm rõ với người dùng

Người dùng trả lời: **“Tôi xác nhận toàn bộ dữ liệu cũ là giờ Việt Nam”.**
Migration 005 ghi provenance Asia/Ho_Chi_Minh cho dữ liệu trước migration; không UPDATE
cột timestamp gốc. Backend Session mới dùng SET LOCAL TIME ZONE UTC; SQL trực tiếp ghi nhận
múi giờ phiên. Field không đổi giữ origin cũ, thiếu origin/value không khớp thì giữ lỗi.
Phần chuyển schema PG sang timestamptz chưa làm, tách khỏi quyết định chuẩn hóa bản đọc ETL.

## Đầu ra đã triển khai trong repository

- `backend/etl/`: extract, transform, load, pipelines, quality, errors, run/worker.
- `005_etl_outbox.sql`: etl_outbox, etl_time_origin, etl_runs, etl_state, report_daily_sales;
  I/U/D trigger trên product/image/order/detail/transaction/voucher/review/log/violation/feedback.
- Sáu pipeline, upsert theo unique business key, bảo toàn `_id` cũ/attributes/tags/moderation/
  evidence/attachments. Có partial update và tombstone, giữ log identity ghép.
- Retry/backoff, dead-letter có mã lỗi an toàn, ACK sau write; không MAX-ID cursor.
  Khóa một worker, daemon 60 giây, daily deep reconciliation, CLI status/retry/full.
- Compose có etl-worker và profile etl-test dùng DB riêng. Image `oldshop-data-backend:day5` build đạt.
- `test-day5.sh` tạo cặp PG/Mongo mới cho regression và một cặp khác cho ETL;
  `apply-day5.sh` đã chuẩn bị backup/restore/migrate/full hai lần/đối soát rồi mới mở ghi.
- [Thiết kế và lệnh chạy](design/05_etl.md), [PUML](diagram/05_etl_flow.puml),
  [BSON validators](design/05_mongo_validators.json).

## Kết quả kiểm thử

**124 trường hợp đạt** qua các lượt kiểm tra có phạm vi riêng:

- [96 regression + 26 trường hợp ETL](evidence/day5_tests.txt): 96 passed in 14.89s
  và 26 passed in 56.51s; hai cặp DB mới, không chạy regression trên DB ứng dụng.
- [Một test bổ sung về tiến độ run thất bại](evidence/day5_failure_progress_test.txt):
  1 passed; kiểm tra Mongo đã ghi/PG đã ACK nhưng quality-check mất kết nối, run phải giữ
  rows_in/out thực tế và dữ liệu không bị nhân bản khi chạy tiếp.
- [Một test bổ sung về tiền NULL](evidence/day5_null_money_test.txt): 1 passed;
  không tự gán phí NULL thành 0, sửa nguồn và replay thì cập nhật thành công.
- Ruff check + format cho app/tests/scripts/etl, shell syntax và diff whitespace đều đạt.
  CI đã thêm lint package etl; chưa tuyên bố đã chạy CI remote/Mongo8.

Các ca quan trọng đã chạy thật: rollback nguồn không có event/provenance; transaction ID nhỏ
commit sau không bị bỏ qua; write Mongo thành công trước ACK bị crash vẫn replay đúng; Mongo
lỗi giữ event, dead-letter và khôi phục; child đổi FK cập nhật aggregate cũ/mới; product/voucher
fan-out vẫn giữ giá mua lịch sử; full hai lần giữ ID/metadata Mongo; soft/hard-delete giữ attributes;
log trùng log_id khác ngày được phân biệt; log >90 ngày không mất nguồn PG; contact/log không
copy raw PII; phát hiện corruption và full sửa; khóa worker ngăn full chồng nhau; transfer ảnh
local trước ACK, object MinIO thật không cần bản local; báo cáo delivered/cancel và múi giờ UTC/VN.

DB regression: `day5_test_20261030091807_26227_regression`.
DB ETL: `day5_test_20261030091807_26227_etl` (PG và Mongo cùng tên).
Các tên test có guard prefix; dữ liệu MinIO thử dùng UUID và được dọn đúng key.

## Full và daemon trên DB thử riêng

[Run mẫu](evidence/day5_isolated_runs.json) ở `day5_test_worker_20261030_a`:

- Daemon tự chọn **full** khi chưa có full_initialized, không phải gọi full từ API.
- Snapshot duy nhất: **16 product, 30 order, 11 violation**, các collection review/log/contact rỗng.
- Full run đầu: rows_in=89, rows_out=89, errors=0. Có 57 source rows và 32 event phát từ backfill
  metadata ảnh; 89 là thao tác gồm replay, **không** phải 89 document khác nhau.
- Media: uploaded=0, skipped=95, missing=[], fallback avatar=11;
  metadata PG test updated=32, unavailable=[]; đối soát 32/32 image reference có đúng size/type.
- Quality: sáu count khớp, field_mismatches=0, projection_errors=0; backlog=0, dead=0.
- Report: **2 nhóm, gross_sales_vnd=13.100.000**, tính subtotal hàng đã giao, không nhầm với
  net final_amount gồm shipping/discount của admin dashboard.
- [Đo daemon](evidence/day5_worker_latency.json): poll=60s, no-op UPDATE product trong **DB test**
  tạo 16 event (product + các order liên quan), ACK hết sau **26,06 giây**. Run hoàn tất và đối soát
  trong log mẫu. Đây là số đo cục bộ cho tải nhỏ, không là SLA.

Container daemon thử do tác vụ tạo có tên `oldshop-day5-worker-test`; không phải service
etl-worker của stack hiện tại. Sau thu bằng chứng container thử được dừng/dọn, DB test giữ lại.

## Phát hiện và sửa trong Ngày 5

1. Full không thể replace toàn document: metadata Mongo bị mất. Đã tách allowlist PG-owned
   và `$setOnInsert` cho trường Mongo-owned; giữ `_id` legacy bằng unique key thay vì ép đổi ID.
2. Không thể dùng MAX(event_id) làm watermark: test commit đảo thứ tự chứng minh event ID nhỏ
   xuất hiện muộn. Query theo status/due và ACK từng ID giải quyết trường hợp này.
3. Image/line/payment đổi FK phải phát cả parent cũ/mới; product/voucher current cần fan-out,
   không coi tên/category/seller hiện tại là snapshot lịch sử tại thời điểm mua.
4. Script seed_media cũ báo missing với upload MinIO không có file local. Đã stat đúng key,
   nhận object đã có, không sinh alias seed giả hoặc thay upload người dùng bằng default.
5. Backend local cũng có thể có ảnh mới: load đảm bảo copy đúng file sang MinIO trước ACK,
   không scan bucket trong query catalogue, không suy ID từ tên seed.
6. Tiền fraction/NULL/sai tổng phải quarantine; không round hay gán 0 để đối soát xanh.
7. Nếu run thất bại sau một số ACK, etl_runs vẫn ghi tiến độ thực và error code, không dump
   exception text/payload. Đã bổ sung test lỗi cuối run để chứng minh.
8. TTL audit chỉ cho system_logs Mongo 90 ngày; violation không TTL, PG không bị purge.
9. Không chạy lại fraud model bằng số dư hiện tại hoặc remap transaction_status=4.
10. Nội dung contact, reason và audit details không được tự sao chép nguyên văn sang Mongo;
    giữ PG là nguồn nội dung có phân quyền, Mongo lưu metadata/placeholder.

## Rollout local đã hoàn tất sau chấp thuận

`bash deploy/scripts/apply-day5.sh --resilience` kết thúc exit 0:

- Backup riêng: `deploy/backups/day5_20261030_094800/` (không đưa vào Git).
- PG restore rehearsal: `day5_restore_20261030_094800`; count/digest cả 18 bảng khớp.
- Backup Mongo trước ETL có 6 collection/0 document; restore schema/index đạt.
  MinIO backup và restore kiểm SHA-256 đạt cho 95 object, object tạm đã dọn.
- Migration áp mới đúng `005`; không reset/reseed hay sửa migrations 001–004.
- Full run `dea68aab-91f5-4b11-8493-700c4659561d` và
  `fc9dd766-22df-4ae2-92b7-b8a09e726e12`: mỗi run **57 in/57 out, errors=0**,
  gồm 16 product/30 order/11 violation; review/system_log/contact rỗng.
  Lượt hai không nhân bản; quality mismatch=0, pending=0, dead=0.
- Media: 95 object đã có được giữ, không upload thêm; 32/32 image reference có size/type đúng.
  Không cần cập nhật metadata PG trong rollout này (đã backfill Ngày 4).
- Report: 2 nhóm, tổng gross hàng đã giao **13.100.000 VND**.
- So snapshot trước/sau ETL: **count/digest của 18 bảng nguồn khớp hoàn toàn**.
  Timestamp nguồn không bị đổi, không sửa status tài chính.
- Backend/frontend mở lại, worker incremental chạy thành công; health HTTP và dịch vụ đạt.
  Checker `--resilience --day5` **PASS**: schema 001–005, backlog=0/dead=0;
  PG replica streaming async, 30 order khớp; Mongo có 1 PRIMARY/2 SECONDARY.

[Snapshot trước rollout](evidence/day5_current_stack_unchanged.json) là bằng chứng lịch sử
schema 001–004 trước khi người dùng chấp thuận, không phải trạng thái hiện tại.
Không chỉnh `.env.data` hoặc động vào lab03-mongo/minio-local.

Giới hạn: một worker/N+1 extract, aggregate rebuild toàn bộ; chưa đo ETL 100k orders. Retention
outbox/origin/run chưa có GC; liveness heartbeat không bảo đảm freshness. Backup cùng máy vẫn
cần bản ngoài host. API đọc ghép Mongo/dashboard report, phân quyền metadata mới thuộc Ngày 6.
