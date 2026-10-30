# Bộ bàn giao Ngày 7

Đọc `07_report.md` để xem báo cáo nguồn; `07_slides.md` là 18 slide kèm lời dẫn.
DOCX/PDF/PPTX, video MP4 không tiếng có phụ đề Việt và SRT nằm trong `generated/` sau build;
các binary này được đưa vào ZIP release, không commit vào Git.

| Đầu ra | Tệp |
|---|---|
| Báo cáo chỉnh sửa / trình chiếu | generated/oldshop_report.docx / oldshop_report.pdf |
| Slide chỉnh sửa / bản PDF | generated/oldshop_slides.pptx / oldshop_slides.pdf |
| Demo dự phòng | generated/oldshop_demo.mp4 / oldshop_demo.srt |
| Lời dẫn, thao tác và tái lập | 07_demo_script.md |
| Bộ phản biện | 07_qa.md |
| SQL pgAdmin4 / Mongo Compass Shell | demo_pgadmin.sql / demo_mongo.js |
| Ảnh dự phòng | screenshots/*.png |
| Dữ liệu biểu đồ từ benchmark thật | 07_facts.json; ../benchmark/pg, ../benchmark/mongo |

Sơ đồ đầy đủ dùng DBML/PUML ở `../diagram/07_*`; SVG trong `assets/` dùng cho báo cáo,
không cần xuất sơ đồ PNG. Ảnh PNG trong screenshots là ảnh chụp trình diễn thực tế.

Tái lập report/demo theo [07_demo_script.md](07_demo_script.md). Ngày 7 không đổi ứng dụng,
schema hoặc dữ liệu người dùng; demo tự tạo và dọn project riêng với credentials tạm.
Một lượt quay cần thêm tài nguyên cho stack seed, không quay trực tiếp trên dữ liệu thật.

Đóng gói sau khi commit toàn bộ source/evidence và tạo tag local:

```bash
# Chỉ thực hiện khi Ngày 7 đã kiểm chứng và worktree sạch.
git tag -a v0.7.0-data-upgrade -m "OldShop data upgrade: Day 7 handoff"
python3 deploy/scripts/package-day7.py --tag v0.7.0-data-upgrade
cd dist/releases
sha256sum -c oldshop-v0.7.0-data-upgrade.zip.sha256
```

Không tạo lại tag đã tồn tại; packager cũng kiểm CRC và SHA-256 toàn bộ file trong ZIP.
Gói chứa source commit đã tag, sáu binary được allowlist và `RELEASE_MANIFEST.json` có hash
từng file. Không chứa `.env` thật, backup, dump, volumes, `.git`, raw video hoặc node_modules.
Giữ seed account để chạy đồ án; các account này không dùng cho triển khai công khai.

Phạm vi đã kiểm chứng là một máy, Mongo7 local; Mongo8, CI remote và chịu mất host chưa kiểm chứng.
Các bảng SQL/API trong video ghi rõ nguồn, không giả giao diện pgAdmin/Compass.
