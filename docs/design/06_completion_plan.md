# Ngày 6 — Tích hợp và kế hoạch hoàn thiện

Thực hiện ngày 30/10/2026, sớm hơn lịch dự kiến 01/11. Căn cứ D1–D6 và xác nhận D7;
không thay enum thanh toán D8, không chuyển giao dịch sang MongoDB.
Đã rollout local với migration 006, bảo toàn 18 bảng nguồn và checker PASS.
Trạng thái nghiệm thu và bằng chứng xem [nhật ký Ngày 6](../DAY6_FINDINGS_LOG.md).

## Phạm vi tích hợp

| Luồng | Nguồn đọc/ghi | Khi dịch vụ phụ lỗi |
|---|---|---|
| Giá, tồn kho, catalogue, cart, checkout, tài khoản, kiểm duyệt | PostgreSQL primary | Không phụ thuộc Mongo/replica cho giao dịch |
| Chi tiết sản phẩm | PG + attributes/tags Mongo | HTTP 200 từ PG, attributes/tags rỗng, metadata_status=unavailable |
| Lọc thuộc tính | Mongo tìm product_id, PG kiểm trạng thái/category/seller rồi sort/page | HTTP 503; không tự bỏ bộ lọc để trả sản phẩm sai |
| Dashboard | Giữ total_revenue từ PG; thêm sales_report từ bảng ETL trên primary | Không phụ thuộc PG replica; báo as_of/stale/available |
| Upload/media | MinioStorage qua /media, bucket private | HTTP 503 riêng ảnh/upload; catalogue và giao dịch vẫn phục vụ |
| Log/violation | Ghi PG và outbox cùng transaction, ETL sang Mongo | Giữ event để retry; không dual-write trực tiếp trong request |
| Xóa ảnh | Unlink PG + hàng đợi media_deletions, ETL refresh Mongo rồi xóa object | Retry 60 giây; lỗi được ghi và run partial, không mất yêu cầu xóa |

Profile một máy hiện dùng báo cáo **trên primary**. Không tự bật read routing sang replica:
replica async có thể trễ và profile có thể không được chạy. Không có cơ chế promote PG tự động.

## API và giới hạn

- Giữ path/method/trường/enum cũ. `GET /products/{id}` thêm attributes, tags,
  metadata_status (available/missing/unavailable), metadata_synced_at; không ghi đè description,
  giá, tồn kho, ảnh hiện tại bằng bản sao ETL. Chỉ lấy Mongo document còn sống và đúng category.
- `GET /products?attributes={"ram_gb":8,"brand":"Demo"}`: JSON được URL-encode,
  AND các điều kiện bằng nhau trên giá trị scalar. Tối đa 16 khóa đơn giản, 4096 ký tự;
  không nhận toán tử `$`, đường dẫn có dấu chấm, nested filter hoặc NaN/Infinity.
  Tối đa 5000 Mongo candidate; vượt ngưỡng trả 422 để thu hẹp, không cắt ngầm kết quả.
  Search/category/seller exclusion/visibility/sort đều áp trước skip/limit ở PG, có khóa ID phá hòa.
  Metadata là eventual consistency; sản phẩm chưa ETL có thể chưa xuất hiện trong bộ lọc.
- Mongo có wildcard index `attributes.$**`; không hứa index bao phủ mọi tổ hợp lọc.
  [Tài liệu MongoDB](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/).
- `GET /admin/stats?sales_year=2025` vẫn yêu cầu admin và giữ total_revenue theo final_amount
  đơn đã giao. sales_report là gross giá hàng đã giao trước giảm giá/chưa gồm shipping,
  nhóm ngày Việt Nam theo category/seller hiện tại. Không cộng orders_count các nhóm thành tổng đơn.
  Frontend chọn năm/tháng, không còn số ngẫu nhiên; stale khi quá 5 phút, available=false khi chưa ETL.
- `DELETE /products/{product_id}/images/{image_id}`: chỉ seller sở hữu/admin; HTTP 204 xác nhận
  unlink PG, không hứa object đã xóa tức thì. Trigger 006 enqueue trong cùng transaction.
  Worker đợi outbox/quality đạt, kiểm PG và Mongo không còn tham chiếu rồi mới xóa idempotent.
  Soft-delete sản phẩm giữ ảnh. Avatar cũ dạng seed/shared giữ nguyên; avatar upload bất biến
  được enqueue sau thay URL thành công. Không scan bucket để tự xóa orphan hoặc file đính kèm.
- `/ready` là alias mới của `/health/ready`: PG/Mongo/MinIO configured, lỗi phụ trả 503.
  `/health` vẫn 200 khi process sống; Nginx tiếp tục proxy được các API còn phục vụ.
  Health container Mongo chỉ ping được, chưa đủ kết luận replica set đã bầu PRIMARY sau restart.
  [Thứ tự startup Compose](https://docs.docker.com/compose/how-tos/startup-order/).

## Kiểm thử có thể chạy lại

```bash
# Default Mongo8 cho host/kernel tương thích; máy local hiện tại dùng ngoại lệ Mongo7.
bash deploy/scripts/test-day6.sh --mongo-image mongo:7.0
# Cờ --skip-build chỉ dùng khi hai image day6 đã build từ source hiện tại.
# Worker vừa thay đổi: --skip-regression chạy lại ETL + API + outage.

cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm test -- --watch=false
npm run build -- --configuration production
```

Runner tạo project `oldshop-day6-test-<random>` với credentials sinh tạm, network/volumes
và port loopback tự cấp; không đọc secrets hay dừng stack oldshop-data. Mỗi phase có PG/Mongo DB riêng.
Kết thúc dọn đúng project/volumes do lần chạy tạo, kể cả khi lỗi. Không dùng script này để giữ dữ liệu.
CI thêm job Compose có PG/Mongo/MinIO, toàn bộ regression/ETL/API và failure scenarios;
job frontend chạy test. Cấu hình CI đã sửa không đồng nghĩa đã có kết quả GitHub Actions remote.

Các scenario: baseline; dừng/khôi phục mongo2, pg-replica, MinIO; dừng/khôi phục toàn Mongo.
Chỉ chứng minh chịu lỗi dịch vụ trong **một máy**, không chứng minh chịu mất host hoặc tự promote PG.
Ảnh không thể tiếp tục trả byte khi MinIO single-node mất; mong đợi đúng là 503 cho ảnh và 200 cho phần còn lại.

## Tiến độ và phân công

Phần trăm là tiến độ đầu ra trong phạm vi MVP, không phải coverage hay khả năng production.
A/B/C/D là **vai trò** từ kế hoạch, chưa có tên thành viên thực tế để gán.

| Hạng mục | Trạng thái | % | Phụ trách | Hạn theo kế hoạch | Ghi chú |
|---|---|---:|---|---|---|
| Audit, inventory, ERD, D1–D6 | Đạt | 100 | A | 27/10 | DAY1_REVIEW/inventory/decisions |
| Chiến lược phân tán và Compose | Đạt local | 100 | A/D | 28/10 | Một máy, profile PG/Mongo replica |
| JSON và Mongo | Đạt local Mongo7 | 100 | B | 29/10 | Mongo8/kernel khác chưa kiểm chứng |
| MinIO và storage | Đạt local | 100 | B | 29/10 | Private buckets, gateway media |
| Index, partitioning, migration | Đạt | 100 | A | 30/10 | Bằng chứng Ngày 4, không sửa lịch sử 001–005 |
| ETL, outbox, đối soát | Đạt local | 100 | C | 31/10 | Ngày 5 rollout, poll 60 giây |
| Backend/frontend và regression | Đạt và rollout local | 100 | C | 01/11 | 146 backend + 15 FE; 9 outage scenario; checker PASS |
| CI service integration | Đã cấu hình | 90 | C/D | 01/11 | Cần một lượt remote sau push được người dùng cho phép |
| Báo cáo, PPT, demo tổng duyệt | Đạt Ngày 7 local | 100 | D | 02/11 | PDF 15 trang, 18 slide, demo 6:06; DAY7_FINDINGS_LOG |
| CDC/Patroni/sharding/đa máy | Ngoài MVP | 0 | A/B/D | Sau đồ án | Cần yêu cầu và tài nguyên riêng |

## Công việc còn lại / nợ kỹ thuật

| Ưu tiên | Việc | Phụ trách | Thời điểm/tiêu chí |
|---|---|---|---|
| P0 | Báo cáo, PPT, script demo, video dự phòng và tổng duyệt | D + A/B/C | Ngày 7; số liệu nhất quán evidence |
| P0 | Chạy CI remote sau push/PR được cho phép | C/D | Trước release; không tự push trong tác vụ này |
| P1 | Đo Mongo8 trên kernel tương thích | B/D | Trước chuyển phiên bản; chạy lại suite |
| P1 | Backup ngoài host và diễn tập khôi phục định kỳ | D | Trước dữ liệu thật; kiểm RPO/RTO |
| P1 | Rotate seed passwords/app keys, giới hạn login, TLS production, tách PG migration/runtime roles | C/D | Trước public Internet |
| P1 | Metadata write UI/API có kiểm quyền, quy tắc nội dung công khai | B/C | Hiện đọc attributes/tags có sẵn; chưa mở endpoint ghi tùy ý |
| P1 | Xử lý lặp thao tác moderation, rà soát public user DTO/PII | C | Trước production; không phá contract trong Ngày 6 |
| P1 | Quét/giải mã file upload, private attachment authorization | B/C | Trước nhận file thật; hiện kiểm MIME/đuôi/size |
| P2 | ETL batch/N+1, giảm fan-out view-count, đo tải 100k | A/C | Có benchmark ETL riêng, không suy từ benchmark index |
| P2 | Retention outbox/origin/runs và media deletion history, GC có review | A/B/C | Không purge event chưa ACK; không tự xóa seed/shared |
| P2 | Metadata search nhiều candidate, pagination quy mô lớn | A/B/C | Trước vượt 5000 candidate; không nới cap vô hạn |
| P2 | Timezone PG timestamptz, enum D8, PayPal idempotency/fraud model | A/C | Quyết định và migration riêng; giữ nguyên dữ liệu cũ |
| P3 | CDC/Debezium, Mongo shard, FDW vùng, Patroni, MinIO distributed | A/B/D | Sau MVP, có máy độc lập/quorum/fencing |

Giới hạn media cleanup: một worker, kiểm tham chiếu của ứng dụng PG/Mongo hiện hành;
không đảm bảo trước thao tác SQL đặc quyền tái gắn URL đồng thời ngoài quy trình ứng dụng.
Hàng đợi giữ yêu cầu khi còn tham chiếu, có thể cần xử lý khi nguồn/bản sao bị sai lệch.
