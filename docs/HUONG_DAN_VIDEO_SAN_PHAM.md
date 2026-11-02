# Video sản phẩm: Google Drive và MP4

Mỗi sản phẩm có tối đa một video. Người bán chọn **Không có video**, **Liên kết Google
Drive/YouTube** hoặc **Upload MP4** trong form đăng/sửa sản phẩm. Đây là hai nguồn thay
thế nhau; hệ thống không tự upload sang Drive khi upload MP4 thất bại.

## 1. Dữ liệu và lưu trữ

- PostgreSQL tiếp tục lưu `product.video_url`, không cần bảng video hoặc migration mới.
- API trả thêm `video_source`: `google_drive`, `upload`, `external` hoặc `null`. Giá trị
  được tính từ URL khi trả response, không thêm cột có thể bị lệch với URL.
- MP4 người dùng nằm trong bucket **private** `product-videos`, key
  `videos/products/<product_id>/<uuid>.mp4`; URL ứng dụng là `/media/videos/products/...`.
- Backend phục vụ video công khai qua media gateway giống ảnh sản phẩm; private ở đây
  có nghĩa không cho truy cập trực tiếp bucket, không có nghĩa video chỉ chủ sản phẩm xem được.
- Drive vẫn nằm ở tài khoản Drive của người bán. Chỉ lưu URL; không cần OAuth/Drive API.
  Backend chuẩn hóa link `/file/d/.../view`, `/open?id=...`, `/uc?id=...` và giữ `resourcekey`.
  Các link YouTube cũ vẫn dùng được. Không nhận URL máy chủ tùy ý hoặc URL upload của sản phẩm khác.
- ETL giữ tham chiếu MP4 nội bộ và các tham số cần để xem Drive trong `product_details.video_url`
  của MongoDB. Với upload local, ETL copy MP4 sang MinIO trước khi xác nhận sự kiện như với ảnh.

Trang chi tiết khách hàng, cửa sổ moderator và phần xem video hiện tại trong form seller
dùng chung component: MP4 có trình phát với controls; Drive có nút mở tab mới.
Drive phải cho phép người xem truy cập qua link; chủ file có thể thu hồi quyền hoặc xóa video.

## 2. Yêu cầu MP4

- Tối đa **50 MiB/file** mặc định; biến backend `MAX_VIDEO_UPLOAD_BYTES=52428800`.
- Nội dung MP4 thực tế, video H.264; audio AAC hoặc không có audio. Backend dùng `ffprobe`
  để kiểm tra container/codec, không chỉ tin đuôi file và MIME. Không tự chuyển codec.
- Docker backend đã cài FFmpeg/ffprobe. Chạy backend trực tiếp trên host thì phải cài
  FFmpeg và kiểm tra `ffprobe -version` (Ubuntu/Debian: `sudo apt install ffmpeg`).
- Nginx frontend cho phép tổng request **64 MiB**, gồm video, ảnh và multipart overhead.
  Nếu tăng giới hạn backend, cần điều chỉnh đồng bộ giới hạn Nginx và nhãn giới hạn trên form.
- GET media hỗ trợ `Range`, trả `206`, `Content-Range`, `Accept-Ranges`; range không hợp lệ
  trả `416`. HEAD trả kích thước file mà không tải toàn bộ nội dung. Video dùng `video/mp4`.

## 3. Tạo/sửa và vòng đời file

`POST /api/v1/products` tiếp tục nhận multipart ảnh và các trường sản phẩm; bổ sung
`video_file` tùy chọn. Không gửi đồng thời file và `video_url` có nội dung.

`PUT /api/v1/products/{id}/listing` nhận multipart:

| Trường | Ý nghĩa |
|---|---|
| `details` | Chuỗi JSON theo `ProductUpdate`: title, price, quantity… |
| `details.video_url` được bỏ qua | Giữ video hiện tại |
| `details.video_url = null` | Bỏ video hiện tại |
| `details.video_url = "https://drive.google.com/..."` | Thay bằng link |
| `video_file` | Thay bằng MP4; lúc này không gửi `details.video_url` |

API JSON cũ `PUT /api/v1/products/{id}` vẫn hoạt động cho cập nhật trường và link/bỏ video.
Seller chỉ sửa sản phẩm của mình; admin có quyền sửa. Thông tin sản phẩm và tham chiếu
video được commit cùng nhau. Lỗi kiểm tra/upload/commit giữ dữ liệu cũ và dọn file mới.
Chỉ sau commit thành công mới dọn video upload cũ không còn được sản phẩm nào tham chiếu.
Nếu storage không cho xóa, backend ghi log để quản trị dọn sau; không báo thất bại giả cho
giao dịch DB đã thành công. Xóa mềm sản phẩm giữ file để bảo toàn dữ liệu; không tự xóa
file Drive hay video mẫu dùng chung.

## 4. Video mẫu cho seeding

File nguồn do người dùng cung cấp:

```text
database/03_seeds/assets/videos/Building_Windows_Apps.mp4
```

File đã kiểm tra là H.264/AAC, khoảng 27 MB. Bootstrap copy thành
`MEDIA_DIR/videos/products/seed/product-demo.mp4` nếu chưa tồn tại. Lệnh
`python -m scripts.seed_media` upload file sang MinIO cùng ảnh seed, không ghi đè object có sẵn.
URL dùng chung là `/media/videos/products/seed/product-demo.mp4`.

Khi khởi tạo **DB mới**, nhóm 984 sản phẩm mở rộng luân phiên: không video, MP4 mẫu,
Google Drive. 16 sản phẩm gốc giữ nguyên link hiện có. DB đang dùng không bị script copy
media đổi URL sản phẩm. Muốn thử MP4 trên DB hiện hữu, sửa một sản phẩm của chính mình
và upload file qua form; không cần reset DB. File seed dùng chung được giữ khi thay/bỏ video.

## 5. Áp dụng vào stack đang chạy

Chạy từ thư mục gốc, với hàm `dc` đã định nghĩa trong
[hướng dẫn cấu hình](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md). Thực hiện lần lượt,
chỉ tiếp tục khi mỗi lệnh thành công. Các lệnh sau dùng được với Bash và PowerShell 7.3+:

```text
dc build backend frontend
dc run --rm --no-deps minio-init
dc run --rm --no-deps --entrypoint python backend -m scripts.seed_media
dc up -d --no-deps --force-recreate --wait --wait-timeout 180 backend etl-worker
dc up -d --no-deps --force-recreate --wait --wait-timeout 90 frontend
```

`minio-init` bổ sung bucket và quyền ứng dụng bằng thao tác idempotent. Cần bước này
trước backend mới: readiness kiểm tra cả bucket video. Giữ `STORAGE_BACKEND=minio`
trong `deploy/.env.data` nếu đang dùng MinIO. Với storage local chỉ cần build/recreate ứng dụng;
`scripts.init_db` khi backend khởi động sẽ copy video seed xuống media volume.

Sau khi hoàn tất, Ctrl+Shift+R ở trình duyệt. Không cần xóa volume để cập nhật video.
Luồng trên không chạy lại seed SQL vào DB hiện hữu.

## 6. Kiểm chứng thủ công

1. Tạo sản phẩm với link Drive có quyền xem công khai; kiểm tra nút mở đúng video ở
   seller, moderator và trang sản phẩm sau khi được duyệt.
2. Tạo sản phẩm với MP4 mẫu; kiểm tra tiến trình upload, phát/dừng/tua video, response
   media có `video/mp4`. Khi tua, các request có Range phải nhận `206`.
3. Sửa tên/giá mà không chọn file mới: video cũ được giữ. Thay bằng MP4 mới rồi bằng
   Drive: mỗi lần lưu thành công hiển thị nguồn mới; file upload cũ không còn được tham chiếu được dọn.
4. Chọn Không có video rồi lưu: `video_url` và `video_source` là null; phần video biến mất.
5. Thử file giả đổi đuôi thành MP4, codec không hỗ trợ và file quá 50 MiB: nhận thông báo
   phù hợp; dữ liệu cũ giữ nguyên. Thử lỗi upload rồi gửi lại với file hợp lệ.
6. Tài khoản khác không sửa được video sản phẩm của chủ cũ (`403`). Thay video của một
   sản phẩm seed không làm mất MP4 mẫu ở các sản phẩm seed khác.

Kiểm thử tự động: `backend/tests/test_product_video.py`, các test component video,
seller form và moderator. Chỉ chạy API test với PostgreSQL test riêng đã seed.
`VIDEO_MINIO_INTEGRATION=1` bật thêm kiểm tra streaming/range với bucket MinIO test riêng.

Runner tạo PostgreSQL và MinIO riêng, build backend có ffprobe, chạy API/storage tests rồi
dọn container/volume tạm; không đọc cấu hình hoặc kết nối stack đang dùng:

```bash
python deploy/scripts/test-product-video.py
```
