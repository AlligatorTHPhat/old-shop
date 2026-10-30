# Ngày 7 — Báo cáo, slide, demo và bàn giao (30/10/2026)

Thực hiện sớm hơn lịch 02/11. Căn cứ hệ thống đã rollout Ngày 6, migration 001–006,
quyết định D1–D8 và bằng chứng đã lưu; không sửa ứng dụng hoặc migration trong Ngày 7.

**Ngày 7 hoàn tất trong phạm vi đồ án một máy.** Báo cáo PDF **15 trang**, đủ chín chương và
ba phụ lục; **18 slide** có notes; video **366,32 giây (6:06), 1280×720**, phụ đề Việt và
**10 ảnh dự phòng**. Chín chặng tổng duyệt PASS, project tạm đã dọn; checker stack người dùng
PASS với chín service khỏe, PG replica streaming/async, Mongo đủ ba member, ETL pending/dead=0.
Artifact validation PASS; release local và gói nộp theo mục bên dưới.

## Đầu ra

| Nội dung | Vị trí |
|---|---|
| Báo cáo chín chương, ba phụ lục và nguồn tham khảo | report/07_report.md; generated/oldshop_report.docx/.pdf |
| 18 slide, mỗi slide tối đa một sơ đồ chính; benchmark dạng biểu đồ | report/07_slides.json/.md; generated/oldshop_slides.pptx/.pdf |
| Kịch bản 6:05 và 20 câu hỏi phản biện | report/07_demo_script.md; report/07_qa.md |
| Video không tiếng, phụ đề Việt và ảnh dự phòng | report/generated/oldshop_demo.mp4/.srt; report/screenshots/ |
| ERD đầy đủ, kiến trúc và luồng ETL cuối | diagram/07_erd_current.dbml; 07_architecture_current.puml; 07_data_flow_current.puml |
| SQL Query Tool, truy vấn Compass Shell | report/demo_pgadmin.sql; report/demo_mongo.js |
| Tái lập / kiểm tra / đóng gói | deploy/scripts/{build,demo,validate,package}-day7.py (tại root dự án) |

Các đường dẫn generated trong bảng là `docs/report/generated/`. Office/PDF/video/ZIP được
ignore bởi Git, có trong gói nộp; Markdown, PUML, DBML, SVG, screenshot và evidence được quản lý
bằng Git. Không xuất thêm sơ đồ PNG. PNG là ảnh chụp browser thật.

## Kiểm chứng nội dung

- ERD dùng `@dbml/core 11.0.0`, compiler `dbmlv2`: **28 bảng logic, 222 cột**.
  Tên bảng/cột, kiểu và nullability khớp schema PG thực sau chuẩn hóa serial/int;
  bỏ physical partition children khi so sánh. SQL tiếp tục là nguồn chính cho defaults,
  trigger, index và toàn bộ constraint. Evidence: `evidence/day7_schema_review.json`.
  Hai PUML cuối cũng đã qua PlantUML 1.2025.2 `-checkonly`, không sinh ảnh raster.
- File SQL demo chạy thành công bằng `psql -X`, transaction **read-only**, `ON_ERROR_STOP=1`.
  PostgreSQL mới là DB; pgAdmin4 là client. Đây là kiểm SQL tương thích Query Tool,
  không khẳng định đã tự mở GUI pgAdmin4 9.18. Evidence: `evidence/day7_sql_demo.txt`.
- Các projection/index Mongo đã thực hiện đọc bằng role ứng dụng; không đưa password,
  token, địa chỉ hay raw contact/violation vào đầu ra: `evidence/day7_mongo_demo.json`.
- Số **146 backend / 15 frontend / 9 scenario** là bằng chứng Ngày 6, qua nhiều lượt;
  không chạy lại toàn bộ suite hoặc tuyên bố remote CI trong Ngày 7.
- Chart PG lấy median ba lượt từ `benchmark/pg/summary.json`; chart Mongo lấy một lượt
  explain mỗi pha trên Mongo7.0.43. Phân biệt benchmark 100k với pruning trên seed nhỏ.
  Ghi cả query chậm hơn và index bytes tăng; không suy ra SLA hoặc mức tăng tốc toàn hệ.

## Tổng duyệt và video

Runner tạo project `oldshop-day7-demo-<random>` với credentials tạm, port loopback tự cấp,
network và volumes riêng. Seed metadata `OldShop Demo` chỉ ghi trong project này.
Các bước: Compose up; partition/WAL; document Mongo/API; trang sản phẩm thật; MinIO
Console thật; full ETL hai lần; EXPLAIN/benchmark có nhãn nguồn; dừng mongo2; phục hồi
đủ PRIMARY + hai SECONDARY và readiness. Cuối cùng chỉ xóa project/volumes do runner tạo.

Bảng PG/Mongo trên màn hình là console SQL/API gắn nhãn rõ; không giả GUI pgAdmin/Compass.
Video không có giọng nói; SRT và lời dẫn sẵn để người trình bày sử dụng.
Thời gian chờ/query không được tăng tốc để che phục hồi. Evidence cuối ở
`evidence/day7_rehearsal.json`; plan seed thực ở `evidence/day7_current_pruning.json`.

Các phát hiện trong quá trình làm:

1. Lượt quay đầu dừng ở MinIO login: input `accessKey` không ghi rõ thuộc tính HTML
   `type="text"`, nên selector attribute không khớp. Đổi sang `#accessKey`, `#secretKey`;
   project tạm đã được dọn sau lỗi. Không dùng đoạn quay dở để nghiệm thu.
2. Lượt tiếp theo hoàn tất kỹ thuật nhưng cửa sổ thông tin AGPL của MinIO che danh sách.
   Kiểm ảnh bằng mắt phát hiện vấn đề; bổ sung thao tác đóng panel thông tin hiện hữu,
   chọn bucket `product-images` và thư mục `products`; quay lại bản bàn giao.
   Có ảnh bổ sung `05b_minio_preview.png` mở JPEG thật trong cùng project seed.
   Một lượt quay lại bị ngắt với mã 143 (SIGTERM), chưa xác định nguồn tín hiệu;
   không ghi nhận lượt dở này là PASS. Bổ sung handler SIGTERM để chạy cleanup và
   chế độ resume chỉ nhận project `oldshop-day7-demo-*` cùng `.env` tạm dưới `/tmp/oldshop-day7-*`.
   Tiếp tục đúng project do runner tạo, chạy lại toàn bộ kịch bản; không resume stack người dùng.
3. Biểu đồ đầu có ký tự vuông do font thiếu glyph; đổi font chart/diagram sang DejaVu Sans.
   Comment marker sinh bảng Markdown bị hiện trong bản DOCX đầu; bỏ comment trước parse.
   Xuất lại và rà PDF, gồm chart, bảng, sơ đồ và slide có ảnh sản phẩm.
4. LibreOffice headless trong sandbox không xuất PDF được. Chạy với quyền phù hợp và
   profile tạm riêng; không sửa profile Office cá nhân. Cảnh báo `javaldx` không ngăn xuất PDF.
5. Parser DBML API cũ không nhận khối `checks`; compiler DBML V2 kiểm đúng cú pháp hiện hành.
   Không sửa SQL/schema chỉ để phù hợp parser legacy.

## Release và giới hạn

Tên tag local: `v0.7.0-data-upgrade`. Gói: `dist/releases/oldshop-v0.7.0-data-upgrade.zip`,
kèm `.zip.sha256`. Packager yêu cầu source/evidence đã commit, worktree sạch và tag trỏ HEAD;
chỉ thêm sáu generated deliverable đã allowlist, kiểm CRC và hash mọi file theo manifest.
`RELEASE_MANIFEST.json` ghi commit/tag và SHA-256 payload; hash ZIP đặt ngoài archive.
Kết quả đóng gói ở `docs/report/generated/packaging_validation.json` (ignored).

Không đưa `.env` thật, backup/dump, volumes, `.git`, raw video, node_modules, model weights
vào ZIP. Quét các giá trị secret runtime local trong payload và XML Office mà không in giá trị.
Seed credentials trong source chỉ dành cho đồ án. Không push Git hoặc upload gói nộp.

MVP một máy dùng Mongo7.0.43 theo ngoại lệ đã chấp thuận. Mongo8.0.32 trên kernel khác,
GitHub Actions remote và chịu mất cả host chưa được kiểm chứng. PG chưa tự promote;
MinIO single-node chưa chịu lỗi storage; backup hiện cùng host. Các việc này giữ trong
`design/06_completion_plan.md`, không đánh dấu hoàn thành vì đã có báo cáo.

Đọc `evidence/day7_output_validation.json` để kiểm cấu trúc Office/PDF, đủ chương/slide/notes,
duration/kích thước video và hash deliverable; `evidence/day7_stack.json` xác nhận stack
người dùng sau tổng duyệt. Checker này chỉ kiểm hạ tầng/ETL/readiness, không gọi product detail
trên stack người dùng để tránh side effect tăng view_count.
