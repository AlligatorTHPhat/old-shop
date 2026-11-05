# Đo dữ liệu hiện tại của OldShop

Thời điểm bắt đầu: **2026-11-05T13:27:11.991229+07:00** (giờ Việt Nam).
Nguồn: PostgreSQL `oldshop` và MongoDB `oldshop` đang phục vụ dự án.
Đây là dữ liệu seed đã nạp và các thay đổi phát sinh khi dùng ứng dụng, không phải
bộ dữ liệu benchmark được tạo thêm. Runner không sinh bất kỳ dòng/document nào.

## Dữ liệu được đo

| Dữ liệu | PostgreSQL | MongoDB |
|---|---:|---:|
| Sản phẩm / product_details | 1001 | 1001 |
| Ảnh sản phẩm | 2001 | Nhúng trong product_details |
| Đơn hàng / order_snapshots | 31 | 31 |
| Review | 0 | 0 |
| Log hệ thống | 0 | 0 |
| Giỏ hàng / chi tiết giỏ | 13 / 0 | Không lưu |
| Vi phạm / violation_logs | 11 | 11 |

Seed nguồn hiện có 1.000 sản phẩm và 30 đơn; DB đang chạy có thêm dữ liệu phát sinh.
Không reset DB về seed để khớp con số. Số đếm của đủ 28 bảng logic nằm trong
[pg/summary.json](pg/summary.json); số document từng collection trước/sau đo nằm trong
[mongo/summary.json](mongo/summary.json). Các partition không bị cộng đếm hai lần.

## Phương pháp

- PostgreSQL 16.15, migrations 001–007 đang có sẵn;
  MongoDB 8.0.32, giữ nguyên toàn bộ index hiện có.
- Một lượt warmup, năm lượt EXPLAIN cho mỗi truy vấn; báo cáo median thời gian thực thi phía DB.
- PostgreSQL dùng một transaction REPEATABLE READ, READ ONLY (`transaction_read_only=on`).
- Mongo chỉ count/find/listIndexes/explain/buildInfo. Không chung snapshot giữa hai DB
  hoặc các lệnh Mongo; worker vẫn hoạt động. Số document trước/sau bằng nhau không
  chứng minh nội dung mọi document bất biến.
- Tham số category, product, buyer, seller và từ khóa lấy từ bản ghi đang tồn tại.
  Các câu SQL là truy vấn đọc đại diện, chọn một số cột; chưa đo đầy đủ ORM, HTTP hay trình duyệt.
- Không tạo/xóa index, migrate, ANALYZE, seed, full ETL hoặc ghi dữ liệu nghiệp vụ.
- Bảng rỗng và thuộc tính chưa có được ghi **skipped**, không thêm dữ liệu cho đủ ca đo.
- ETL poll chỉ đo SELECT chọn event, bỏ khóa/claim/ACK; hàng đợi không có event đến hạn
  trong lần này nên kết quả không đại diện cho backlog lớn.

## PostgreSQL

| Truy vấn | Median thực thi (ms) | Dòng trả về / trạng thái |
|---|---:|---|
| catalogue | 0.347 | 100 |
| catalogue_category | 0.599 | 100 |
| search | 5.111 | 45 |
| buyer_history | 0.119 | 20 |
| seller_orders | 0.383 | 16 |
| review_history | — | Bỏ qua: No active reviews |
| reports | — | Bỏ qua: No active reports (rating=0) |
| cart_lookup | — | Bỏ qua: shopping_cart_item is empty |
| order_pk_pruning | 0.020 | 1 |
| log_month_pruning | — | Bỏ qua: system_log is empty |
| product_images | 0.081 | 2 |
| etl_status | 0.061 | 1 |
| etl_poll_selection | 0.070 | 0 |

Dung lượng index vật lý hiện tại: **3,489,792 bytes**. Không có mốc trước/sau.
File `pg/<truy_van>.json` chứa SQL, tham số và đủ năm plan ANALYZE/BUFFERS;
file `.txt` chứa SQL đã gắn tham số và plan JSON của mẫu có thời gian ở giữa để đọc.
`pg/indexes.json` lưu định nghĩa index hiện có.

## MongoDB

| Truy vấn | Median ms | Docs examined | Keys examined | Returned |
|---|---:|---:|---:|---:|
| product_details | 0 | 1 | 1 | 1 |
| reviews | — | — | — | Bỏ qua: No existing document/attribute for this query |
| order_snapshots | 0 | 20 | 20 | 20 |
| attribute_search | — | — | — | Bỏ qua: No existing document/attribute for this query |

`mongo/<truy_van>.json` chứa lệnh explain và đủ năm kết quả; `mongo/indexes.json`
lưu index hiện có. **0 ms là độ phân giải nguyên millisecond, không có nghĩa truy vấn
không mất thời gian.** Không so trực tiếp độ chính xác thời gian Mongo với PG.

## Đọc kết quả và giới hạn

Đây là ảnh chụp hiệu năng trên lượng dữ liệu hiện tại. Không có phép đo trước/sau tối ưu,
không công bố tỷ lệ tăng tốc, p95 HTTP, throughput đồng thời hoặc SLA.
Các kết quả trước/sau trên dữ liệu giả lập đã được xóa khỏi thư mục này;
các bộ sinh dữ liệu benchmark lớn cũng đã được gỡ khỏi CLI đo hiện tại.
Log kiểm thử tính năng và triển khai lịch sử nằm ở `docs/evidence/`, không dùng làm
số đo hiệu năng của bộ dữ liệu hiện tại. Hướng dẫn vận hành migration vẫn nằm tại
[runbook indexing v2](../runbooks/indexing_v2.md).

[manifest.json](manifest.json) ghi thời điểm, giới hạn, SHA-256 runner và các file seed SQL
trong image được dùng. Hash seed ghi nhận nguồn, không khẳng định DB chưa bị thay đổi sau seed.

## Chạy lại

Từ `backend/`, dùng môi trường Python/dependencies và cấu hình kết nối của backend:

```bash
python -m scripts.benchmark_current --output ../docs/benchmark/lan-do-moi
```

Output phải là thư mục **chưa tồn tại** để không ghi đè bằng chứng cũ. Cần kết nối được
cả PostgreSQL và MongoDB; script không tạo DB hoặc tự nạp seed. Có thể dùng
`--source-root /duong/dan/repository` nếu chạy script từ vị trí khác.

Để đo qua backend Docker đang chạy (thay tên container nếu dùng project khác), không cần build lại:

```bash
docker cp backend/scripts/benchmark_current.py oldshop-data-backend-1:/tmp/oldshop-benchmark-current.py
docker exec -e PYTHONPATH=/app oldshop-data-backend-1 python /tmp/oldshop-benchmark-current.py --source-root /opt --output /tmp/oldshop-current-new-run
docker cp oldshop-data-backend-1:/tmp/oldshop-current-new-run docs/benchmark/lan-do-moi
```

Thư mục `/tmp/oldshop-current-new-run` trong container và `lan-do-moi` trên host phải mới.
Đo một lần mỗi lúc; kết quả thay đổi theo cache, dữ liệu ứng dụng và tải máy.
