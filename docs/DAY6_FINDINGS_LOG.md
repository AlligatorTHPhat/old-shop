# Ngày 6 — Tích hợp, kiểm thử, kế hoạch hoàn thiện (30/10/2026)

**Ngày 6 hoàn tất: code, kiểm thử và rollout vào stack local oldshop-data đều đã đạt.**
[Kế hoạch hoàn thiện và contract](design/06_completion_plan.md).

## Thay đổi

- GET product detail bổ sung attributes/tags từ Mongo, fallback PG khi lỗi/thiếu projection.
  Không ghi đè giá, stock, description hoặc ảnh nguồn bằng snapshot có độ trễ.
- Lọc thuộc tính scalar an toàn; kết hợp PG visibility/search/category/seller trước phân trang.
  Cap 5000 candidate + timeout, trả lỗi rõ nếu Mongo lỗi hoặc bộ lọc quá rộng.
- Giữ net total_revenue; thêm sales_report gross theo ngày/năm từ ETL trên PG primary.
  Angular model cập nhật, dashboard bỏ số giả/ngẫu nhiên, có as_of/stale và chọn năm/tháng.
- Product detail hiển thị thông số/tag và dùng media-url.ts cho URL hiện tại.
- Migration 006 tạo queue xóa ảnh, trigger trong transaction unlink/đổi avatar;
  endpoint xóa ảnh kiểm quyền. Worker kiểm tham chiếu, đợi projection rồi xóa idempotent/retry.
  Run partial khi cleanup lỗi, status hiển thị pending/failed media; không báo xanh giả.
- Giữ log/violation ghi PG + outbox, kiểm thử moderation → ETL không copy raw reason/PII.
- /ready alias của /health/ready; /health giữ liveness. Production Compose ép DEBUG=false.
- Runner test có project/database/volume riêng; CI có services qua Compose và frontend test.

## Kiểm thử và phát hiện

- Lượt regression đầu: **96 passed in 17.74s**.
- ETL với migration 006: **28 passed in 97.36s**.
- API integration đầu: **20 passed in 56.68s**; sau đó thêm ca giữ object dùng chung,
  bổ sung assertion cleanup lỗi → partial và chạy lại phần worker/API liên quan: **21 passed in 43.85s**.
  ETL chạy lại sau thay worker: **28 passed in 92.25s**. Tổng **146 trường hợp backend khác nhau đạt**
  (96 + 28 + 21 + 1 ca status bổ sung), không cộng lượt chạy lại vào số ca khác nhau.
- Angular: **15 passed**, 12 file; production image build đạt. Test biểu đồ kiểm tháng/năm,
  ngày nhuận, thiếu báo cáo phân biệt với doanh thu bằng 0.
- Ruff check/format backend và diff whitespace đạt trước nghiệm thu cuối.

Phát hiện trong quá trình làm:

1. Dashboard cũ dùng số hard-code/Math.random; số ETL gross khác total_revenue net.
   Đã giữ contract net và bổ sung báo cáo riêng có nhãn, không đổi ý nghĩa field cũ.
2. Seller exclusion trước đây xảy ra sau limit, search bỏ category/sort. Đã hợp nhất predicate
   và sort có product_id phá hòa trước pagination; test kiểm tra trang và seller exclusion.
3. Không replace PG-owned fields từ Mongo vì ETL chậm. Response chỉ merge allowlist metadata.
4. Không thể xóa object và commit PG nguyên tử. Queue 006 giữ intent qua lỗi/restart;
   không xóa file khi PG/Mongo còn tham chiếu, rollback không để lại intent đã commit.
5. Worker cũ có connect PG ngoài try trong vòng lặp; đã đưa vào try để retry cycle khi mất kết nối.
6. Lệnh Angular test cũ dùng --code-coverage không được builder hiện tại hỗ trợ; bật --coverage
   lại thiếu @vitest/coverage-v8. Chọn ng test chạy toàn suite, chưa tuyên bố có frontend coverage report.
   Fixture smoke cũ gọi HTTP thật/thiếu route, App spec còn đòi 'Hello, frontend'; đã dùng
   HTTP testing backend/router riêng và kiểm shell thực tế.
7. Compose --wait với init job kết thúc 0 khi chưa có consumer có thể báo lỗi runner.
   Tách infrastructure wait và run --rm job khởi tạo trước các phase test.
8. Sau khởi động lại toàn Mongo, container ping thành công trước khi replica set bầu PRIMARY.
   Lượt đầu các scenario lỗi đạt nhưng probe recovery gọi quá sớm; đã bổ sung retry readiness
   tối đa 60 giây và chạy lại, không coi lỗi recovery ban đầu là PASS.

9. Lượt rollout đã áp 006, full/reconcile và đối soát xong nhưng CLI status thất bại:
   dùng chỉ số tuple trên RealDictCursor (`KeyError: 0`), rồi cần alias riêng cho hai count.
   Script giữ bảo trì đúng thiết kế; sửa Python, không thay SQL migration/checksum.
   [Test status mới](evidence/day6_status_regression.txt) trên DB riêng:
   **1 passed, 21 deselected in 4.67s**, kiểm pending/failed có dữ liệu và đúng kiểu số.
   CLI DB chính sau sửa trả outbox/media pending=0; snapshot 18 bảng được kiểm lại trước mở dịch vụ.

## Bảo mật và giới hạn

- Không commit .env/secrets; env test sinh ngẫu nhiên, quyền 0600, dọn sau thử.
  Probe authenticated chỉ bật cho stack thử; token không xuất vào evidence.
- Mongo không publish port host; PG/MinIO/API local bind 127.0.0.1; bucket private,
  app dùng credential phạm vi bucket, root chỉ job provision/test.
- Mongo đọc projection allowlist, không đưa password/token/email/địa chỉ/số dư vào metadata response;
  ETL giữ allowlist/redaction Ngày 5, violation reason đầy đủ vẫn trong PG có phân quyền.
  Attributes do Mongo quản lý là dữ liệu công khai, không dùng để lưu PII.
- Chưa kiểm Mongo8 trên kernel local; tiếp tục Mongo7.0.43 theo ngoại lệ đã thống nhất.
- Một máy, không chứng minh mất host, tự failover PG hay MinIO HA.
  CI remote chưa chạy trong tác vụ; chưa thực hiện báo cáo/PPT/video của Ngày 7.

## Kết quả lỗi/phục hồi dịch vụ

[Bằng chứng](evidence/day6_failover.json): **9 scenario PASS** ở project riêng
`oldshop-day6-test-961bcab6`. Baseline; mongo2 dừng/phục hồi; pg-replica dừng/phục hồi;
MinIO dừng/phục hồi; toàn Mongo dừng/phục hồi. Có xác thực seed chỉ trong project thử:
cart/order/admin report vẫn 200; MinIO dừng trả media/upload 503 và giữ avatar cũ;
Mongo dừng trả detail PG 200 với metadata unavailable, filter attributes 503.
Readiness xuống 503 đúng dịch vụ phụ lỗi, liveness vẫn 200; phục hồi về readiness 200.
Runner đã dọn container/network/volume của project thử, không dọn stack oldshop-data.

Bằng chứng kiểm thử: [regression và lượt đầu](evidence/day6_backend_tests.txt),
[ETL/API cuối](evidence/day6_final_tests.txt), [frontend test](evidence/day6_frontend_tests.txt),
[frontend build](evidence/day6_frontend_build.txt), [security review](evidence/day6_security_review.json).
Build production frontend có cảnh báo initial bundle 750,45 kB vượt warning budget 500 kB,
chưa vượt error budget 1 MB; không tăng budget để che cảnh báo.

## Rollout local hoàn tất

Lớp xét duyệt ban đầu chặn rollout trước khi chạy do cần phê duyệt rõ đợt bảo trì.
Sau đó người dùng xác nhận: **“Đồng ý triển khai Ngày 6 và bảo trì tạm thời”**.
Đã triển khai đúng quy trình đã trình bày, không vượt chặn hoặc đổi phạm vi.

- Backup riêng: `deploy/backups/day6_20261030_134922/`; PG restore rehearsal giữ tại
  `day6_restore_20261030_134922`. Backup/restore **18 bảng PG**, **7 collection/57 document Mongo**
  và **95 object MinIO** đạt; object restore thử được kiểm SHA-256 rồi dọn.
- Migration áp mới đúng `006`; thêm wildcard attribute index, không sửa lịch sử 001–005.
- Full `819cbad7-3a94-441e-8003-f2922074be5d`: **57 in/57 out, errors=0**;
  reconcile `720c9810-2e19-4cf8-8b7b-41127beedddc`: **0 in/0 out, errors=0**.
  Sáu collection count khớp, field mismatch=0, 32/32 tham chiếu ảnh hợp lệ;
  report 2 nhóm gross 13.100.000 VND, không nhân bản document.
- Lượt script đầu exit 1 ở CLI status sau khi migration/full/reconcile đã xong, không phải lỗi DDL
  hay mất dữ liệu. Sửa cursor aliases và thêm test hồi quy như mục 9; build lại backend.
  So snapshot trước/sau ETL/**sau sửa CLI**: count/digest cả 18 bảng nguồn **khớp hoàn toàn**.
  Sau đó tiếp tục mở dịch vụ; không áp lại/sửa migration, không reset/reseed.
- Backend/frontend image day6 đã chạy; worker incremental thành công,
  outbox pending/dead=0, media_cleanup pending/failed=0.
- [Checker --resilience --day6](evidence/day6_stack.json) **PASS**: HTTP qua frontend,
  detail metadata/ảnh/readiness đều đúng; PG replica streaming async, 30 order khớp;
  Mongo 1 PRIMARY/2 SECONDARY. Probe detail làm tăng view_count bình thường và worker đã ACK event
  phát sinh; snapshot bảo toàn nguồn nêu trên được lấy **trước** probe này.
- [OpenAPI trước/sau](evidence/day6_api_contract.json): giữ **64 path cũ**, không mất method/trường;
  thêm 1 path xóa ảnh, 4 trường metadata product detail, sales_report ở admin stats.
  Không sửa enum/constants; /ready là alias ẩn khỏi OpenAPI.

[Bằng chứng rollout và phục hồi CLI](evidence/day6_rollout.json),
[snapshot stack trước bảo trì](evidence/day6_current_stack_unchanged.json) là lịch sử schema 001–005,
không phải trạng thái hiện tại. Không sửa `.env.data`, lab03-mongo hay minio-local.
DB thử status `day5_test_day6_status_20261030135315` (PG/Mongo) giữ lại để xem ca hồi quy.
Backup vẫn cùng host, chưa thay thế bản sao ngoài máy. CI remote và hạng mục Ngày 7 chưa thực hiện.
