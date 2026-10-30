# Demo OldShop — 6 phút 05 giây

Mục tiêu: trình bày đầu ra đang chạy, chỉ ra nguồn sự thật và giới hạn. Không dùng video
hoặc SQL snapshot để khẳng định production HA. Script quay tự động dùng project riêng;
không dừng `oldshop-data`, không chạy lại init.sql trên dữ liệu đang dùng.

## Chuẩn bị

```bash
# Python 3.11+; chạy tại root, một virtualenv riêng.
python3 -m venv --system-site-packages /tmp/oldshop-day7-tools
/tmp/oldshop-day7-tools/bin/pip install -r docs/report/requirements.txt
# Linux cần LibreOffice, ffmpeg/ffprobe, font DejaVu/Noto, Chrome.
PLAYWRIGHT_BROWSERS_PATH=/tmp/oldshop-day7-pw /tmp/oldshop-day7-tools/bin/playwright install ffmpeg
/tmp/oldshop-day7-tools/bin/python deploy/scripts/build-day7.py
PLAYWRIGHT_BROWSERS_PATH=/tmp/oldshop-day7-pw /tmp/oldshop-day7-tools/bin/python deploy/scripts/demo-day7.py
# Sau khi quay và build lần cuối:
/tmp/oldshop-day7-tools/bin/python deploy/scripts/validate-day7.py
```

Hai image `oldshop-data-backend:day6` và `oldshop-data-frontend:day6` cần đã build từ source.
Nếu chưa có: build backend với `docker build -t oldshop-data-backend:day6 -f backend/Dockerfile .`
và frontend với `docker build -t oldshop-data-frontend:day6 frontend`. Mongo7 được chọn cho kernel
local đã kiểm chứng; `--mongo-image mongo:8.0.32` chỉ dùng trên host tương thích, phải kiểm thử lại.

Script tạo credentials tạm, loopback ports tự cấp, network/volumes riêng và dọn đúng project
sau quay. Không cần dùng `.env.data` thật. Video không có giọng nói, có phụ đề tiếng Việt;
người trình bày dùng lời dẫn dưới đây. Chrome chạy headless; đường dẫn executable có thể
điều chỉnh trong script nếu máy khác dùng Chromium. Không quay lại password/token vào artifact.

Nếu tiến trình bị ngắt trước cleanup, ghi lại lỗi và chỉ dùng cặp `--resume-owned-project`
với `--resume-env` trỏ `.env` tạm gốc để chạy lại toàn bộ demo của chính runner.
Không truyền tên `oldshop-data`, không dùng `.env.data` thật; không xóa volumes bằng lệnh tổng quát.

## Lời dẫn theo mốc

| Mốc | Thao tác / nội dung trên màn hình | Lời dẫn |
|---|---|---|
| 0:00–0:35 | Dịch vụ thực sau Compose up, sơ đồ cuối | “Đây là stack demo riêng trên một máy. PG, Mongo replica set, MinIO và worker cùng chạy; chưa chứng minh chịu mất host.” |
| 0:35–1:15 | pg_partition_tree và pg_stat_replication | “Order HASH theo order_id giữ PK. Log RANGE theo tháng dùng khóa ghép. Standby nhận WAL async; không tự promote khi primary mất.” |
| 1:15–1:55 | Document Mongo và JSON response sản phẩm | “RAM/brand là metadata Mongo. Giá và quantity vẫn từ PG; không dùng snapshot cũ để quyết định tồn kho.” |
| 1:55–2:30 | Trang sản phẩm thật, thông số/ảnh | “Frontend hiển thị dữ liệu hợp nhất qua contract bổ sung. Ảnh vẫn dùng /media gateway, không đưa credential S3 ra browser.” |
| 2:30–3:05 | MinIO console thật trong project demo | “Bucket private giữ byte object; PG giữ quan hệ ảnh. Key UUID khác filename cũ; không suy product_id từ filename.” |
| 3:05–3:50 | Full ETL hai lượt, count/quality/metadata | “At least once: write Mongo xong mới ACK. Upsert theo key và partial update khiến replay không nhân bản, không xóa attributes/tags.” |
| 3:50–4:35 | EXPLAIN PK hiện hành + chart nguồn Ngày 4 | “Query seed minh họa pruning, không phải benchmark 100k. Chart là median ba lượt đã lưu; một số query không nhanh hơn, dung lượng index tăng.” |
| 4:35–5:20 | Dừng mongo2, query app/replica set | “Một member đang dừng. Các member còn lại đủ quorum, API sản phẩm vẫn phục vụ. Đây là lỗi dịch vụ trong cùng host.” |
| 5:20–6:05 | Mở mongo2, chờ SECONDARY/ready, tổng kết | “Phục hồi cần chờ topology, không chỉ ping container. Mongo8, remote CI và HA đa máy chưa được chứng minh.” |

Thời điểm thực tế có thể lệch vài giây do thời gian truy vấn/phục hồi; evidence ghi mốc thực tế,
phụ đề theo các khoảng của kịch bản. Không kéo nhanh video để che thời gian phục hồi hoặc fake kết quả.

## Trình diễn bằng công cụ quản trị của người dùng

- **pgAdmin4 9.18:** mở Query Tool với PostgreSQL demo, chạy từng nhóm trong
  `demo_pgadmin.sql`. Không mở tab chứa password hash, token, email/địa chỉ hoặc backup thật.
  Query primary kiểm `pg_is_in_recovery()=false`; connection replica riêng phải trả true.
- **Compass/mongosh:** chọn DB demo, chạy `demo_mongo.js`; chỉ trình bày projection đã allowlist.
  Không hiển thị URI có password trên máy chiếu.
- **MinIO console:** đăng nhập demo, mở product-images và một ảnh; không mở màn hình access-key.
- **Bản quay tự động:** các màn PG/Mongo là bảng SQL/API được gắn nhãn rõ, không giả giao diện
  pgAdmin4/Compass. Có trang sản phẩm thật và MinIO console thật.

## Kiểm chứng sau tổng duyệt

`docs/evidence/day7_rehearsal.json` phải PASS, video dài 300–420 giây, full hai lượt có
counts bằng nhau/metadata giữ được, mongo2 OFF được ghi nhận rồi phục hồi đủ 1 PRIMARY/2 SECONDARY.
Kiểm `docs/evidence/day7_stack.json` để xác nhận stack người dùng vẫn khỏe sau dọn demo.
Ảnh dự phòng nằm ở `docs/report/screenshots/`; không dùng ảnh cũ thay cho tình trạng hiện tại.

## Phương án dự phòng

Nếu Docker chưa sẵn sàng: mở video MP4 đã kiểm duration và ảnh chụp, nói rõ đó là lượt tổng
duyệt có evidence, không gọi là demo live. Nếu host không chạy Mongo8: dùng đúng ngoại lệ
Mongo7 đã ghi nhận, không thay tag giữa buổi. Nếu một bước lỗi: ghi mã lỗi, giữ kết quả thật,
không reset dữ liệu nguồn để làm màn hình xanh. Gói ZIP có source SQL/PUML/DBML và raw explain.
