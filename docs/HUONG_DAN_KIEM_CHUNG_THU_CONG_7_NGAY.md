# Hướng dẫn kiểm chứng thủ công: dữ liệu hợp nhất, ETL và indexing

Tài liệu dành cho người đã kết nối PostgreSQL bằng **pgAdmin 4**, MongoDB **8.0.32**
bằng Compass/mongosh và MinIO bằng Console. Đối chiếu với
[kế hoạch 7 ngày](KE_HOACH_NANG_CAP_7_NGAY.md), baseline migration `001`–`006` và bản bổ sung
indexing `007`. Các mục theo ngày được giữ để tra cứu; nghiệm thu ưu tiên bốn trục ở mục 0.
Cập nhật ngày **01/11/2026**; bộ seed mới có **1.000 sản phẩm**.

Mục tiêu là tự quan sát dữ liệu, chạy truy vấn, thử một luồng nghiệp vụ và lưu bằng chứng.
Đánh dấu **Đạt / Không đạt / Chưa kiểm / Không áp dụng**, không xem việc đã kết nối được
ba công cụ là bằng chứng toàn bộ hệ thống đã hoạt động đúng.

**Phạm vi hiện tại:** kiểm chứng tích hợp ba kho dữ liệu, ETL và indexing trên môi trường
bạn đang chạy. Phân tán qua nhiều máy được giữ thành hạng mục mở, **chưa triển khai/chưa
kiểm chứng**. Có nhiều container hoặc partition trên một máy chưa chứng minh chịu lỗi host.

**Trạng thái indexing:** mã nguồn đã có 007 và M01 MongoDB, nhưng lần thực hiện trước
chỉ áp trên stack kiểm thử riêng. Không mặc định DB của bạn đã nâng cấp. Xem
[runbook tự áp dụng](benchmark/indexing_v2/README.md) và
[bằng chứng thử nghiệm 01/11/2026](benchmark/indexing_v2/2026-11-01/README.md).

## Mục lục

0. [Trọng tâm và tiêu chí nghiệm thu](#0-trọng-tâm-và-tiêu-chí-nghiệm-thu)
1. [Chuẩn bị và cách chạy các ví dụ](#1-chuẩn-bị-và-cách-chạy-các-ví-dụ)
2. [Ngày 1: schema, phân loại và toàn vẹn dữ liệu](#2-ngày-1-schema-phân-loại-và-toàn-vẹn-dữ-liệu)
3. [Ngày 2: topology và sao chép](#3-ngày-2-topology-và-sao-chép)
4. [Ngày 3: Mongo validator, document và MinIO](#4-ngày-3-mongo-validator-document-và-minio)
5. [Ngày 4: index, phân mảnh và EXPLAIN](#5-ngày-4-index-phân-mảnh-và-explain)
6. [Ngày 5: ETL và đối soát](#6-ngày-5-etl-và-đối-soát)
7. [Ngày 6: ứng dụng, ảnh, đơn hàng và lỗi dịch vụ](#7-ngày-6-ứng-dụng-ảnh-đơn-hàng-và-lỗi-dịch-vụ)
8. [Ngày 7: báo cáo, slide và demo](#8-ngày-7-báo-cáo-slide-và-demo)
9. [Dọn dữ liệu thử và xử lý sai lệch](#9-dọn-dữ-liệu-thử-và-xử-lý-sai-lệch)
10. [Phiếu nghiệm thu](#10-phiếu-nghiệm-thu)

Đi thẳng vào phần chính: [Hợp nhất dữ liệu](#610-bài-tổng-hợp-cùng-một-sản-phẩm-xuyên-pgmongominioapi),
[ETL](#6-ngày-5-etl-và-đối-soát),
[Indexing 007/M01](#56-indexing-v2-kiểm-007-và-m01-trên-db-thực-tế),
[Phân tán nhiều máy — để mở](#34-để-mở-kiểm-chứng-phân-tán-qua-nhiều-máy).

## 0. Trọng tâm và tiêu chí nghiệm thu

### 0.1. Hiểu đúng “cơ sở dữ liệu hợp nhất” trong dự án

**PostgreSQL** là hệ quản trị dữ liệu có cấu trúc; **pgAdmin 4** là công cụ kết nối/quản
trị PostgreSQL. Tương tự, Compass và MinIO Console là công cụ thao tác với các kho tương ứng.

| Kho dữ liệu | Loại dữ liệu chính trong bài kiểm | Phần dữ liệu do kho đó quản lý |
|---|---|---|
| PostgreSQL | Có cấu trúc: bảng/cột, PK/FK/UNIQUE, transaction | Tài khoản, giá, tồn kho, trạng thái, đơn/thanh toán; URL và metadata ảnh tham chiếu; outbox/report ETL |
| MongoDB | Bán cấu trúc: document BSON, object/mảng lồng nhau, validator | `attributes/tags` sản phẩm và các read model như product_details/order_snapshots do ETL cập nhật |
| MinIO | Phi cấu trúc: byte ảnh/file trong object | Nội dung file tại bucket/key; có metadata như Content-Type và kích thước |

Đây là phân loại dữ liệu của bài toán, không có nghĩa PostgreSQL không hỗ trợ JSON hoặc
MongoDB không có schema/validator. Metadata của một ảnh có cấu trúc, còn byte ảnh là dữ
liệu phi cấu trúc. MinIO là object storage, không phải hệ quản trị quan hệ.

**Hợp nhất ở đây là tích hợp dữ liệu tại tầng ứng dụng và ETL.** Các kho cùng phục vụ một
sản phẩm/đơn hàng bằng ID và tham chiếu nhất quán. Không có một SQL JOIN xuyên cả ba kho
trong hệ thống hiện tại. API detail kết hợp trường giao dịch PG với attributes/tags Mongo;
trình duyệt tải byte ảnh bằng URL `/media/...` được backend đọc từ storage.

| Dữ liệu cần kiểm | Nguồn quyết định | Cách chứng minh |
|---|---|---|
| Giá, số lượng, duyệt/xóa mềm | PostgreSQL | API khớp PG; lọc thuộc tính Mongo vẫn phải qua điều kiện visibility/category/seller ở PG |
| Attributes/tags | MongoDB | API khớp Mongo; thay mô tả PG và chạy lại ETL không làm mất metadata Mongo |
| Mô tả/images trong document | Bản chiếu từ PG sang Mongo | Sau ETL, ID/key/metadata khớp và nội dung đúng quy tắc transform/scrub; API vẫn dùng mô tả/ảnh hiện tại từ PG |
| Nội dung ảnh | MinIO khi `STORAGE_BACKEND=minio` | Cùng image_id/URL/key, object đọc được, size/type khớp; file tải về đúng ảnh đã upload |
| Báo cáo tổng hợp | `report_daily_sales` trên PG primary | Tổng hợp khớp dữ liệu nguồn và mốc cập nhật ETL, không chỉ hiển thị biểu đồ |

Giao dịch ghi PG và outbox là atomic trong PostgreSQL. Projection Mongo và vòng đời object
được đồng bộ bất đồng bộ; **không có transaction ACID chung cho PG–Mongo–MinIO**. Vì vậy cần
chứng minh dữ liệu hội tụ sau commit, retry/idempotency và xử lý file dùng chung, thay vì
đòi ba kho thay đổi đồng thời trong một thời điểm.

### 0.2. Bốn trục nghiệm thu

| Trục | Câu hỏi cần trả lời | Mục thực hiện | Điều kiện đạt |
|---|---|---|---|
| HN — dữ liệu hợp nhất | Cùng sản phẩm có dữ liệu đúng tại PG, Mongo, MinIO và API không? | 2.2, 4.3, **6.10**, 7.1–7.3 | Đối chiếu cùng ID/key/giá trị, đúng nguồn quyết định, đọc được byte ảnh và không trả hàng sai quyền nhìn thấy |
| ETL | Commit, transform, load, retry và đối soát có đúng không? | **6.1–6.10**, 7.7 | Rollback không bị đồng bộ; commit hội tụ; full lặp không nhân bản/mất metadata; quality khớp khi yên; phục hồi không mất event |
| IX — indexing | Index đúng cấu trúc và có bằng chứng đánh đổi không? | **5.1–5.6** | Catalog/validity/key order/predicate đúng; quan sát plan; phân biệt seed nhỏ với benchmark tải và đo cả ghi/disk |
| PT — phân tán nhiều máy | Dữ liệu/node thực sự ở các máy khác nhau và phục hồi đúng không? | **3.4 — để mở** | Hiện đánh dấu Chưa kiểm vì chưa triển khai; chỉ nghiệm thu sau khi có topology/endpoint và thử lỗi nhiều máy |

Ràng buộc PG, validator Mongo và quyền truy cập object là kiểm tra nền tảng cho các trục
trên. Kiểm UI, giỏ hàng, đơn hàng dùng để tạo/quan sát dữ liệu thực. Báo cáo/slide ở mục 8
là phần bàn giao, không thay thế bằng chứng cơ sở dữ liệu.

### 0.3. Thứ tự kiểm ưu tiên

1. Ghi đúng môi trường/version/migration (mục 1, 2.1); xác nhận storage thật đang là MinIO.
2. Kiểm schema/validator, object và topology hiện có (2–4); ghi rõ một host hay nhiều máy.
3. Tạo demo 6.2 → rollback/commit 6.3 → giữ metadata 6.4 → duyệt và kiểm API ở 7.1.
4. Chốt **bài hợp nhất 6.10 trước khi unlink ảnh ở 7.2**; dùng cùng bộ ID/key và lưu kết quả.
5. Kiểm full/idempotency/quality/report/retry (6.5–6.9), indexing (5), rồi các ca lỗi được
   phép thực hiện (7.7). Không cần gây gián đoạn để hoàn thành các phép kiểm quan sát.
6. Điền phiếu nghiệm thu theo trục ở mục 10. Ghi kết quả quan sát thực; không đánh dấu phần
   nhiều máy hoặc 007 chưa áp là đã đạt dựa trên mã nguồn/báo cáo kiểm thử riêng.

## 1. Chuẩn bị và cách chạy các ví dụ

### 1.1. Xác định đúng môi trường

Ghi lại trước khi bắt đầu:

| Thông tin | Giá trị của bạn |
|---|---|
| Ngày giờ kiểm tra, múi giờ | … / Asia/Ho_Chi_Minh |
| Commit/source đang chạy; image backend/worker | … |
| PG host, port, database; công cụ pgAdmin 4 | … |
| Migration PG thực tế; đã áp 007 chưa? | … |
| M01 Mongo đã được khởi tạo bằng source mới chưa? | … |
| Mongo host, database, phiên bản | … |
| MinIO endpoint, tên bucket | … |
| Có bật profile `resilience` không? | Có / Không |
| Dịch vụ/node nằm trên những máy/VM nào? | …; nếu một host, ghi rõ |
| Storage backend thực tế | minio / local; cần minio để nghiệm thu byte ảnh trên MinIO |
| Có backend, frontend, ETL worker đang chạy không? | … |
| DB mới dùng seed 1.000 sản phẩm hay DB cũ? | … |

SQL trong tài liệu chạy trong **pgAdmin → chọn database → Tools → Query Tool**.
Chọn một khối lệnh rồi Execute, thường là F5. Dùng tab Data Output để xem dữ liệu,
Messages để xem NOTICE/lỗi; lưu kết quả hoặc chụp màn hình có câu truy vấn.
Không dán lệnh Docker hoặc JavaScript vào Query Tool.

JavaScript chạy trong **Compass → Open MongoDB Shell** hoặc mongosh. Chọn đúng DB:

```javascript
use oldshop
```

Nếu cấu hình `MONGO_DB` khác `oldshop`, thay bằng tên thực tế. Trong tab Documents của
Compass, ô Filter chỉ nhận phần điều kiện như `{ "product_id": 1 }`, không nhận cả
`db.product_details.find(...)`. Các khối đầy đủ bên dưới dành cho Shell.

MinIO: mở **Object Browser/Buckets**, chọn bucket, đi theo key và chọn object để xem
thông tin/Preview/Download. Nhãn nút có thể khác giữa các bản Console. Nếu Console chỉ
cho duyệt object, việc kiểm policy dùng tài khoản quản trị/công cụ quản trị đang có;
không cần đổi policy để thực hiện bài kiểm chứng.

### 1.2. Phân biệt kiểm tra chỉ đọc và thao tác tạo dữ liệu

- Các mục xem schema, đếm dòng, EXPLAIN SELECT và đọc Mongo/MinIO là kiểm tra quan sát.
- Các mục có **GHI THỬ** tạo/sửa dữ liệu demo riêng; ghi lại các ID trả về để dọn đúng dữ liệu.
- Các mục có **GIÁN ĐOẠN DỊCH VỤ** chỉ thực hiện trên môi trường demo hoặc trong thời gian
  bảo trì. Chúng thật sự dừng container; có bước khôi phục ở cùng mục.
- Không chạy lại `init.sql`, không `TRUNCATE`, không xóa volume hay sửa checksum migration
  để chuẩn bị bài kiểm tra trên DB hiện có. DB cũ không tự nhận bộ seed mới.
- Lỗi `permission denied`/`Unauthorized` nghĩa là cần dùng connection có quyền cho phép
  kiểm tra đó; chưa đủ kết luận chức năng bị hỏng. Các lệnh quản trị topology thường cần
  quyền cao hơn tài khoản đọc/ghi dữ liệu ứng dụng.

Các khối `BEGIN ... ROLLBACK` cần chạy đầy đủ trên **cùng một Query Tool connection**.
Sau lỗi mong đợi, chạy `ROLLBACK;` trước khi chạy tiếp. Sequence có thể tăng dù transaction
rollback; ID không liên tiếp là bình thường.

### 1.3. URL ứng dụng và lệnh hỗ trợ

Nếu dùng stack `deploy/docker-compose.distributed.yml` với port mặc định:

| Công cụ | Địa chỉ |
|---|---|
| Website | http://localhost:58080 |
| Swagger | http://localhost:58000/api/docs |
| Liveness | http://localhost:58000/health |
| Readiness | http://localhost:58000/health/ready |
| MinIO Console | http://localhost:59001 |
| MinIO S3 API | http://localhost:59000 |

Thay port/hostname nếu môi trường của bạn khác. GUI kết nối được không có nghĩa backend
và worker đang dùng đúng các endpoint đó. Readiness đầy đủ cần trả HTTP 200 và có cả
`database: up`, `mongo: up`, `minio: up`. Nếu không có trường `minio`, kiểm cấu hình
`STORAGE_BACKEND=minio`; nếu thiếu `mongo`, kiểm `MONGO_URI`.

Chỉ cần terminal cho thao tác worker/container. Từ **root dự án**, chọn một cách định nghĩa
`dc` dưới đây; sau đó các lệnh `dc ...` trong tài liệu dùng chung.

**Bash trên Linux/WSL:**

```bash
dc() {
  docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience "$@"
}
dc ps -a
```

**PowerShell 7.3+:**

```powershell
$PSNativeCommandArgumentPassing = "Windows"
function dc {
    docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience @args
}
dc ps -a
```

Nếu không dùng `resilience`, bỏ `--profile resilience` trong định nghĩa. Việc ghi cờ profile
không tự tạo node khi chỉ chạy `ps`, nhưng các mục replica phải theo topology thực tế.
Nếu chạy dịch vụ trực tiếp ngoài Docker, thay các lệnh container bằng cách quản lý tiến
trình tương ứng; câu SQL/JavaScript và kết quả mong đợi vẫn áp dụng.

Xem [hướng dẫn cài/chạy](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md) nếu cần tìm lại endpoint,
credentials hoặc cách khởi động. Không đưa password/URI chứa secret vào ảnh bằng chứng.

### 1.4. Quy ước ID để thử nghiệp vụ

Từ mục 6.2 sẽ tạo sản phẩm demo có tên **`MANUAL7D-DEMO-A`**. Nếu tên đã tồn tại,
đổi hậu tố và dùng tên mới nhất quán trong các bước sau.

| Ký hiệu | Lấy ở đâu? |
|---|---|
| `<PID_DEMO>` | `product_id` trả về khi tạo sản phẩm demo |
| `<IMAGE_ID_DEMO>` | `image_id` của ảnh upload thuộc sản phẩm demo |
| `<IMAGE_URL_DEMO>` | `image_url` của đúng ảnh đó trong PG/API |
| `<OBJECT_KEY_DEMO>` | Bỏ prefix `/media/` khỏi URL; bucket ảnh sản phẩm là `product-images` |
| `<ORDER_ID_DEMO>` | `order_id` trả về khi buyer đặt đơn demo |
| `<BUYER_CONTACT_ID>` | Địa chỉ thuộc đúng buyer, lấy bằng API/SQL ở mục 7.3 |
| `<REVIEW_ID_DEMO>` | ID review/report trả về khi tạo bằng API |
| `<FEEDBACK_ID_DEMO>` | ID feedback trả về khi tạo bằng API |

**Thay toàn bộ token `<...>` trước khi chạy.** Chúng cố ý không phải số có thể vô tình
trỏ vào một sản phẩm/đơn hàng đang có. Không mặc định sản phẩm tạo mới sẽ mang ID 1001.

## 2. Ngày 1: schema, phân loại và toàn vẹn dữ liệu

### 2.1. Kiểm tra đúng PostgreSQL và đủ migration

Trong Query Tool của **primary**:

```sql
SELECT version(), current_database(), current_user,
       pg_is_in_recovery() AS is_replica;
SELECT to_regclass('public.schema_migrations') AS migrations,
       to_regclass('public.user_core') AS users_after_split,
       to_regclass('public.product') AS products;
```

**Mong đợi:** đúng DB ứng dụng, primary trả `false`; ba relation không NULL.
Nếu `schema_migrations` NULL, dừng các truy vấn sau migration và đối chiếu bước bootstrap
trong hướng dẫn cài/chạy. Không tự nạp baseline vào database này.

```sql
SELECT version, applied_at, length(checksum) AS checksum_length
FROM schema_migrations ORDER BY version;
```

**Mong đợi:** DB baseline 7 ngày có `001`–`006`; nếu bạn đã tự nâng indexing v2 thì có
thêm `007`. Mỗi checksum dài 64 ký tự. Chưa áp 007 thì ghi “Chưa kiểm 007 — chưa áp dụng”,
vẫn có thể kiểm nền tảng/ETL và index cũ. Nếu lịch sử đã có 007 mà thiếu index tương ứng
ở mục 5.6 thì đó là sai lệch cần xử lý.

Lịch sử chỉ chứng minh đã ghi nhận version, chưa chứng minh checksum khớp source hoặc
mọi index còn nguyên. Khi đang ở thư mục `backend/` và đã kích hoạt môi trường Python của backend,
verifier chỉ đọc cho baseline tối thiểu 006:

```bash
python -m scripts.verify_indexing_v2 --preflight
```

Nếu dùng Compose, thay bằng:

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexing_v2 --preflight
```

Không cần chạy migration chỉ để kiểm checksum. Image/source dùng verifier phải chứa các
file migration đang được đối chiếu; không dùng image cũ để kết luận source mới bị lỗi.
Không thử sửa SQL đã áp dụng hoặc giá trị checksum trên DB hiện tại.

### 2.2. Đếm bảng logic và đối chiếu mô hình

```sql
SELECT c.relname AS logical_table
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
ORDER BY c.relname;

SELECT count(*) AS logical_tables,
       sum((SELECT count(*) FROM pg_attribute a
            WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped)) AS columns
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relispartition;
```

**Mong đợi đối với schema nguyên bản sau 006 hoặc 007:** 28 bảng logic, 222 cột; không đếm view
`users_full` hay mỗi partition thành một bảng nghiệp vụ riêng. Nếu DBA đã thêm bảng/cột,
đối chiếu tên cụ thể trước khi kết luận sai.

Mở [ERD cuối](diagram/07_erd_current.dbml),
[bảng kiểm kê](01_data_inventory.md) và [quyết định thiết kế](decisions.md).
Chọn ba ví dụ để giải thích bằng dữ liệu thực:

| Loại | Quan sát | Điều cần chứng minh |
|---|---|---|
| Có cấu trúc | PG `product.price`, `quantity`, `order`, FK | Cột/kiểu/ràng buộc và giao dịch được PG quản lý |
| Bán cấu trúc | Mongo `product_details.attributes`, `order_snapshots.items` | Document có trường lồng nhau/mảng và validator |
| Phi cấu trúc | Byte ảnh trong MinIO | PG/Mongo chỉ giữ URL/key/metadata; object chứa file |

Không kết luận đã chuyển toàn bộ mô tả sản phẩm khỏi PG: bản hiện tại giữ các cột cũ,
đồng thời có bản đọc Mongo và thuộc tính động do Mongo quản lý.

### 2.3. Đếm dữ liệu nguồn và kiểm bộ seed mới

```sql
SELECT 'users' AS entity, count(*) AS total FROM user_core
UNION ALL SELECT 'categories', count(*) FROM category
UNION ALL SELECT 'products_total', count(*) FROM product
UNION ALL SELECT 'products_not_deleted', count(*) FROM product WHERE NOT is_deleted
UNION ALL SELECT 'product_images', count(*) FROM product_image
UNION ALL SELECT 'orders', count(*) FROM "order"
UNION ALL SELECT 'order_details', count(*) FROM order_detail
UNION ALL SELECT 'transactions', count(*) FROM "transaction";

SELECT status, is_deleted, count(*) AS products
FROM product GROUP BY status, is_deleted ORDER BY status, is_deleted;

SELECT c.category_id, c.name, count(p.product_id) AS products,
       count(p.product_id) FILTER (WHERE p.status = 1 AND NOT p.is_deleted) AS visible
FROM category c LEFT JOIN product p USING (category_id)
GROUP BY c.category_id, c.name ORDER BY c.category_id;

SELECT count(DISTINCT title) AS titles, count(DISTINCT seller_id) AS sellers,
       count(DISTINCT price) AS prices FROM product;
```

**DB mới với seed hiện tại, chưa thao tác ứng dụng:**

| Chỉ số | Mong đợi |
|---|---:|
| User / category | 15 / 8 |
| Product tổng / chưa xóa mềm | 1.000 / 967 |
| Product xóa mềm | 33 |
| Product theo status 0 / 1 / 2 / 3, kể cả xóa mềm | 151 / 700 / 100 / 49 |
| Tên sản phẩm khác nhau / người bán | 1.000 / 11 |
| Product image / URL ảnh khác nhau | 2.000 / 32 |
| Order / detail / transaction | 30 / 30 / 30 |

Trạng thái product: `0=pending`, `1=approved`, `2=rejected`, `3=sold out`.
Số trên không phải điều kiện cứng cho DB đã dùng hoặc đã tạo dữ liệu demo. DB cũ có thể
vẫn có 16 sản phẩm/32 ảnh; cập nhật file seed không tự tăng dữ liệu của database cũ.
Mỗi danh mục cần có sản phẩm đang bán trong bộ seed mới. Danh sách API công khai còn
lọc trạng thái, xóa mềm, phân trang và có thể loại hàng của chính người đăng nhập.

Kiểm ảnh đại diện và số ảnh trong bộ seed mới:

```sql
SELECT p.product_id, count(i.image_id) AS images,
       count(*) FILTER (WHERE i.is_primary) AS primary_images
FROM product p LEFT JOIN product_image i USING (product_id)
GROUP BY p.product_id
HAVING count(i.image_id) <> 2 OR count(*) FILTER (WHERE i.is_primary) <> 1;

SELECT count(*) AS image_rows, count(DISTINCT image_url) AS distinct_urls
FROM product_image;
```

**Mong đợi trước khi thêm/xóa ảnh demo:** truy vấn đầu không có dòng, truy vấn sau 2000/32.
Sau khi người dùng tự tạo sản phẩm, không bắt buộc mọi sản phẩm có đúng hai ảnh.

### 2.4. Kiểm FK và dữ liệu mồ côi

Trong pgAdmin có thể mở **Schemas → public → Tables → bảng → Constraints**.
Đối chiếu thêm bằng SQL:

```sql
SELECT conrelid::regclass AS source_table, confrelid::regclass AS referenced_table,
       conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE contype = 'f' AND connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;

SELECT count(*) AS orphan_details
FROM order_detail d
LEFT JOIN "order" o ON o.order_id = d.order_id
LEFT JOIN product p ON p.product_id = d.product_id
WHERE o.order_id IS NULL OR p.product_id IS NULL;
```

**Mong đợi:** FK detail/transaction vẫn trỏ tới bảng cha `"order"`; FK user trỏ `user_core`;
`orphan_details = 0`. Lưu ảnh kết quả và đoạn ERD tương ứng.

## 3. Ngày 2: topology và sao chép

### 3.1. PostgreSQL primary và replica tùy chọn

Trên **primary** trong pgAdmin:

```sql
SELECT pg_is_in_recovery();
SELECT application_name, client_addr, state, sync_state,
       sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;
```

**Base không bật replica:** recovery `false`, bảng replication có thể rỗng và đánh dấu
phần replica **Không áp dụng**. **Profile resilience:** phải thấy replica ở `streaming`,
`sync_state` thường là `async` theo cấu hình hiện tại.

Nếu có replica, đăng ký thêm server/connection trong pgAdmin bằng endpoint replica
(mặc định host port 55433), mở Query Tool riêng và chạy:

```sql
SELECT current_database(), pg_is_in_recovery() AS is_replica,
       current_setting('transaction_read_only') AS read_only,
       pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp();
SELECT count(*) FROM product;
```

**Mong đợi:** recovery `true`, read_only `on`, dữ liệu bắt kịp primary khi hệ thống yên.
Sao chép async có thể trễ; thời gian từ lần replay cuối không tự chứng minh đang bị lag
nếu primary không có transaction mới. Không thử ghi hoặc promote replica trong bài này.

### 3.2. MongoDB 8 và replica set

Trong Mongo Shell, bằng tài khoản có quyền xem topology:

```javascript
db.version()
db.adminCommand({hello: 1})
rs.status().members.map(m => ({
  name: m.name, state: m.stateStr, health: m.health
}))
```

**Mong đợi:** phiên bản môi trường của bạn là `8.0.32`; `hello` có `setName` đúng cấu hình
(thường `oldshop-rs`). Base có một PRIMARY; resilience có một PRIMARY và hai SECONDARY,
health bằng 1 khi ổn định. `rs.status()` không được phép với role hiện tại thì dùng
connection quản trị để kiểm, không đổi role của ứng dụng.

Nếu báo `not running with --replSet`, đó là Mongo standalone: có thể đọc/ghi document
nhưng chưa chứng minh triển khai replica set như kế hoạch. Một replica set, kể cả ba
member, cũng chưa phải Mongo sharding.

Các bằng chứng cũ trong `DAY2`–`DAY7` và benchmark Mongo được ghi trên **Mongo 7.0.43**
theo ngoại lệ kernel khi triển khai. Lần kiểm indexing v2 ngày 01/11/2026 có bằng chứng
riêng trên Mongo **8.0.32** và PostgreSQL **16.15**. Cả hai đều là snapshot của lượt kiểm
tương ứng, không chứng minh DB bạn đang kết nối đã có cùng cấu hình/kết quả.

### 3.3. Kiểm Compose và giới hạn phân tán

Nếu dùng Docker, chạy `dc ps -a` và chụp tên service/trạng thái. Init job `Exited (0)` là
đã hoàn thành, không phải lỗi. Với profile đầy đủ, các service thường trực là
`pg-primary`, `pg-replica`, `mongo1/2/3`, `minio`, `backend`, `frontend`, `etl-worker`.

Đối chiếu [sơ đồ kiến trúc](diagram/07_architecture_current.puml): đây là nhiều dịch vụ
trên một máy. Chưa triển khai tự promote PG, FDW theo vùng, Mongo sharding, MinIO
distributed hoặc khả năng chịu mất toàn bộ host.

### 3.4. ĐỂ MỞ: kiểm chứng phân tán qua nhiều máy

**Trạng thái hiện tại: Chưa kiểm — chưa triển khai nhiều máy.** Không cần tạo thêm máy,
chuyển DB hoặc dừng host để hoàn thành lượt kiểm hiện tại. Các mục 3.1–3.3 chỉ nghiệm thu
topology/replication quan sát được trong môi trường đang có.

Partition HASH/RANGE chia bảng trong một PostgreSQL; user split chia cột thành các bảng.
Cả hai không tự đưa dữ liệu sang máy khác. Replica set nhiều container trên một host có
thể kiểm cơ chế sao chép/bầu chọn trong mô hình đó, chưa chứng minh chịu mất host.

Khi có hạ tầng, bổ sung endpoint và kịch bản được phép vào bảng sau; giữ nguyên kết quả
lượt một host để so sánh:

| Mã mở | Bài kiểm nhiều máy dự kiến | Bằng chứng phải có trước khi đánh dấu Đạt |
|---|---|---|
| PT-01 | Xác nhận nơi đặt từng dịch vụ/node | Host/VM ID, địa chỉ/port thực, vai trò PG/Mongo/MinIO, sơ đồ kết nối từ backend/worker; không chỉ tên container |
| PT-02 | PG replication qua mạng | Primary và replica ở các máy khác nhau, streaming/read-only và dữ liệu commit bắt kịp; ghi độ trễ, không mặc định tự promote |
| PT-03 | Mongo replica set qua mạng | Địa chỉ member truy cập được từ driver, vai trò/quorum đúng topology đã chọn, ghi khi tách/kết nối lại một node và kiểm đồng bộ |
| PT-04 | Object storage trên hạ tầng đã chọn | Đọc/ghi/kiểm file qua mạng; nếu chỉ một MinIO ở máy khác thì chưa được gọi là cụm MinIO distributed chịu lỗi |
| PT-05 | Mất kết nối/node và phục hồi | Tình huống được phép, đồng hồ/múi giờ được đối chiếu, backlog/retry/lag trước–sau, phục hồi không mất event/object còn tham chiếu |
| PT-06 | Phạm vi chịu lỗi thực sự | Ghi máy/VM có chung host vật lý hay không; thử lỗi process, mạng và host là các mức khác nhau; chỉ công bố mức đã kiểm |

Việc đặt PG, Mongo và MinIO trên các máy khác nhau chứng minh triển khai nhiều máy.
Khả năng chịu lỗi còn cần replica/quorum/cấu hình storage và thử phục hồi tương ứng;
không suy ra chỉ từ việc các kho đã tách máy. FDW, sharding, tự failover PG và MinIO
distributed cần thiết kế/triển khai riêng nếu sau này chọn dùng.

## 4. Ngày 3: Mongo validator, document và MinIO

### 4.1. Kiểm sáu collection và hợp đồng dữ liệu

```javascript
db.getCollectionNames()
for (const name of [
  "product_details", "reviews", "order_snapshots",
  "system_logs", "violation_logs", "contact_messages"
]) {
  const info = db.getCollectionInfos({name})[0];
  printjson({name, options: info ? info.options : "MISSING"});
}
```

**Mong đợi:** sáu collection tồn tại, có validator `$jsonSchema`,
`validationLevel: "strict"`, `validationAction: "error"`. `etl_errors` là collection
vận hành bổ sung, không phải collection nghiệp vụ thứ bảy bắt buộc có dữ liệu lỗi.
Collection review/contact/log có thể rỗng trên seed ban đầu.

Trong Compass, chọn collection → Documents để xem document, Validation để xem rule,
Indexes để xem chỉ mục, nếu phiên bản/quyền của GUI có các tab này.

```javascript
db.product_details.findOne({product_id: 1}, {
  product_id: 1, category_id: 1, dimensions: 1, condition: 1,
  attributes: 1, tags: 1, images: 1, updated_at: 1, deleted: 1, etl: 1
})
db.order_snapshots.findOne({order_id: 1}, {
  order_id: 1, buyer: 1, items: 1, payments: 1,
  total_amount_vnd: 1, final_amount_vnd: 1, order_date: 1, etl: 1
})
```

**Mong đợi sau full ETL:** product có ảnh với `bucket/key`, condition có grade số 1–10;
order có mảng items/payments. `_id` do ETL hiện tại tạo là `product:1`, `order:1`;
không dùng `p_1`/`o_1` trong phác thảo ban đầu của kế hoạch để kết luận ETL sai.
Trường `attributes`/`tags` rỗng vẫn hợp lệ vì seed SQL chưa tạo RAM/brand.
Nếu không có ID 1, chọn ID có thật từ PG; `null` trước khi ETL chưa phải lỗi validator.

### 4.2. GHI THỬ: xác nhận validator thật sự chặn dữ liệu sai

Dùng collection tạm để không làm sai số đối soát collection nghiệp vụ. Cần quyền tạo
và xóa collection trong DB đang chọn. Chạy trọn khối trong cùng Shell:

```javascript
{
  const source = db.getCollectionInfos({name: "product_details"})[0];
  if (!source || !source.options.validator) throw new Error("Thiếu validator nguồn");
  const tempName = "manual7d_validator_" + new ObjectId().toHexString();
  let created = false;
  try {
    db.createCollection(tempName, {
      validator: source.options.validator,
      validationLevel: "strict", validationAction: "error"
    });
    created = true;
    const c = db.getCollection(tempName);
    c.createIndex({product_id: 1}, {unique: true});
    c.insertOne({
      _id: "manual-valid", product_id: NumberInt(1), category_id: NumberInt(1),
      attributes: {brand: "Manual7D"}, tags: [], images: [], updated_at: new Date()
    });
    print("PASS: insert document hợp lệ");
    try {
      c.insertOne({_id: "manual-invalid", product_id: "sai-kieu"});
      throw new Error("FAIL: validator đã nhận document sai");
    } catch (e) {
      if (e.code !== 121) throw e;
      print("PASS: document sai bị chặn, code 121");
    }
    try {
      c.insertOne({
        _id: "manual-duplicate", product_id: NumberInt(1), category_id: NumberInt(1),
        updated_at: new Date()
      });
      throw new Error("FAIL: unique index đã nhận product_id trùng");
    } catch (e) {
      if (e.code !== 11000) throw e;
      print("PASS: product_id trùng bị chặn, code 11000");
    }
  } finally {
    if (created) db.getCollection(tempName).drop();
  }
}
```

**Mong đợi:** ba dòng PASS, collection `manual7d_validator_*` được dọn. Bước này kiểm
hợp đồng được sao chép từ validator thật; sự tồn tại của unique index trên collection
thật được kiểm riêng tại mục 5.4. Không dùng `bypassDocumentValidation`.

### 4.3. Kiểm MinIO và ánh xạ một ảnh xuyên ba nơi

1. Trong Console, kiểm ba bucket `product-images`, `user-avatars`, `attachments`.
2. Bucket private; `attachments` rỗng vẫn bình thường, chưa có luồng upload attachment
   công khai hoàn chỉnh. Không dùng `/media/attachments/...` để thử vì gateway hiện chỉ
   nhận prefix `products` và `users`.
3. Lấy một ảnh từ PG bằng Query Tool:

```sql
SELECT image_id, product_id, image_url, content_type, size_bytes,
       regexp_replace(image_url, '^/media/', '') AS object_key
FROM product_image WHERE product_id = 1 ORDER BY display_order;
```

4. Ví dụ URL `/media/products/prod_1_1_laptop.jpg` tương ứng bucket `product-images`,
   key `products/prod_1_1_laptop.jpg`. Trong MinIO, đi theo **đúng key này**, không chỉ
   tìm thư mục `products/1/`: seed có alias legacy và key canonical cùng tồn tại.
5. Preview/Download ảnh. Đối chiếu size (byte) và Content-Type với PG.
6. Mongo: `db.product_details.findOne({product_id:1}, {images:1})`; tìm ảnh cùng `image_id`.
   `images[].key` phải đúng key, `content_type`/`size` khớp PG và object đã được backfill.
7. Mở `http://localhost:58000` + `image_url`, rồi thử cùng path qua port frontend 58080.
   Cả hai phải hiển thị ảnh; DevTools → Network xem HTTP 200, kiểu ảnh và số byte.

**Mong đợi:** file thực đọc được, ba nơi tham chiếu nhất quán. Metadata PG NULL trước
khi backfill là trạng thái chưa hoàn tất kiểm chứng, không được tự điền số byte giả.

Ảnh upload mới có dạng `products/{product_id}/{uuid}.ext`; avatar upload mới có dạng
`users/{user_id}/avatar-{uuid}.ext`. Seed được dùng lại nên **2.000 bản ghi ảnh không
đồng nghĩa 2.000 file vật lý khác nhau**. Script seed media còn tạo alias canonical;
không dùng tổng object trong bucket để so bằng số dòng `product_image`.

Để kiểm private, mở URL S3 trực tiếp trong cửa sổ ẩn danh, chẳng hạn
`http://localhost:59000/product-images/products/prod_1_1_laptop.jpg` bằng key có thật.
**Mong đợi:** yêu cầu không ký bị từ chối, thường 403; `/media/...` qua backend vẫn 200.
Link presigned hoặc phiên Console có quyền tải được không chứng minh bucket public.

## 5. Ngày 4: index, phân mảnh và EXPLAIN

### 5.1. PostgreSQL index: tên, cấu trúc và điều kiện

```sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public' AND tablename IN ('product', 'order_detail', 'shopping_cart_item')
ORDER BY tablename, indexname;
SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_trgm';
```

**Mong đợi:**

| Index | Đặc điểm |
|---|---|
| `idx_product_catalogue` | B-tree `(category_id, created_at DESC)`, partial status=1/chưa xóa |
| `idx_product_title_trgm`, `idx_product_description_trgm` | GIN + `gin_trgm_ops`, partial |
| `idx_order_detail_product_order` | B-tree `(product_id, order_id)` |
| `uq_cart_product` | UNIQUE `(cart_id, product_id)` |

Index buyer/date trên `order` đã được clone khi partition. Xem cả children:

```sql
SELECT tablename, indexname, indexdef FROM pg_indexes
WHERE schemaname = 'public' AND tablename LIKE 'order_h%'
ORDER BY tablename, indexname;
```

Không phải thấy tên index trên file SQL là đã có trên database; phải có trong catalog.

### 5.2. Partition ngang và pruning

```sql
SELECT relid::regclass AS relation, parentrelid::regclass AS parent,
       isleaf, level FROM pg_partition_tree('public."order"'::regclass);
SELECT pg_get_partkeydef('public."order"'::regclass) AS partition_key;
SELECT tableoid::regclass AS physical_partition, count(*)
FROM "order" GROUP BY tableoid ORDER BY 1;

SELECT relid::regclass AS relation, isleaf, level
FROM pg_partition_tree('public.system_log'::regclass);
SELECT pg_get_partkeydef('public.system_log'::regclass) AS partition_key;
SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) AS bounds
FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid
WHERE i.inhparent = 'public.system_log'::regclass ORDER BY c.relname;
```

**Mong đợi:** order HASH(`order_id`) có `order_h0`–`order_h3`; system_log RANGE(`created_at`)
có các partition tháng và `system_log_default`. Log rỗng vẫn phải có cấu trúc partition.
Hash routing không phải phép `order_id % 4` đơn giản; dùng `tableoid` để quan sát.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_status FROM "order" WHERE order_id = 1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM system_log
WHERE created_at >= date_trunc('month', CURRENT_TIMESTAMP)::timestamp
  AND created_at < (date_trunc('month', CURRENT_TIMESTAMP) + interval '1 month')::timestamp;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_date FROM "order"
WHERE buyer_id = 7 AND NOT is_deleted ORDER BY order_date DESC LIMIT 20;
```

**Đọc kết quả:**

- Query theo order_id chỉ thực thi trên một partition. Ghi lại tên relation trong plan.
- Query tháng chỉ cần partition liên quan; với biểu thức thời gian có thể thấy
  `Subplans Removed` hoặc nhánh `never executed`. Nếu tháng chưa có partition riêng,
  DEFAULT có thể là partition phù hợp.
- Query buyer có thể đi qua cả bốn partition: buyer_id không phải khóa phân vùng.
- `Seq Scan` trong một partition hoặc trên seed nhỏ không phải lỗi pruning.

Trong pgAdmin có thể dùng Explain/Explain Analyze để xem sơ đồ, nhưng lưu cả plan text
có `actual rows`, buffers và thời gian. Không dùng EXPLAIN ANALYZE cho lệnh ghi ngoài bài
thử có rollback vì nó thực thi lệnh thật.

### 5.3. Phân mảnh dọc user và view tái tạo

```sql
SELECT (SELECT count(*) FROM user_core) AS core,
       (SELECT count(*) FROM user_profile) AS profile,
       (SELECT count(*) FROM user_secret) AS secret,
       (SELECT count(*) FROM user_wallet) AS wallet,
       (SELECT count(*) FROM users_full) AS reconstructed;

SELECT c.user_id,
       p.user_id IS NULL AS missing_profile,
       s.user_id IS NULL AS missing_secret,
       w.user_id IS NULL AS missing_wallet
FROM user_core c
LEFT JOIN user_profile p USING (user_id)
LEFT JOIN user_secret s USING (user_id)
LEFT JOIN user_wallet w USING (user_id)
WHERE p.user_id IS NULL OR s.user_id IS NULL OR w.user_id IS NULL;

SELECT table_name, ordinal_position, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('user_core', 'user_profile', 'user_secret', 'user_wallet', 'users_full')
ORDER BY table_name, ordinal_position;
```

**Mong đợi:** năm count bằng nhau, không có core thiếu mảnh; `users_full` có đủ 20 cột
của user trước tách. Username/email ở core, hồ sơ ở profile, hash/token ở secret, balance
ở wallet. Không SELECT giá trị hash/token để chụp bằng chứng; chỉ xem tên cột/count.

**Thử view chỉ đọc, không đổi dữ liệu:** chạy hai lệnh đầu, quan sát lỗi, rồi chạy ROLLBACK:

```sql
BEGIN;
UPDATE users_full SET username = username WHERE false;
ROLLBACK;
```

**Mong đợi:** PostgreSQL từ chối cập nhật view JOIN, thường SQLSTATE `55000`. Nếu chạy
cả khối bị dừng ngay khi lỗi, chọn riêng dòng `ROLLBACK;` để kết thúc transaction.
Ứng dụng ghi các bảng vật lý qua service/ORM. Tách dọc và REVOKE PUBLIC không tự tạo
row-level security; owner/superuser vẫn có quyền quản trị.

### 5.4. Mongo index và explain

```javascript
for (const name of ["product_details", "reviews", "order_snapshots", "system_logs"]) {
  print(name);
  printjson(db.getCollection(name).getIndexes());
}
```

Đối chiếu các đặc điểm, không bắt buộc nhớ tên index được sinh tự động:

| Collection | Index cần thấy |
|---|---|
| product_details | unique product_id; category_id + attributes.brand; `attributes.$**`; text description/tags |
| reviews | unique review_id; product_id + created_at giảm dần; partial type=report/status=pending |
| order_snapshots | unique order_id; buyer.id + order_date; order_status + order_date |
| system_logs | unique log_id + created_at; TTL created_at=7776000 giây; action + actor_id + created_at |

```javascript
db.product_details.find({category_id: 1, "attributes.brand": "Manual7D"})
  .limit(20).explain("executionStats")
db.reviews.find({product_id: 1}).sort({created_at: -1})
  .limit(20).explain("executionStats")
db.order_snapshots.find({"buyer.id": 7}).sort({order_date: -1})
  .limit(20).explain("executionStats")
```

Ghi `winningPlan`, `nReturned`, `totalDocsExamined`, `totalKeysExamined`,
`executionTimeMillis`; tìm IXSCAN/FETCH/SORT hoặc cấu trúc plan tương đương trên Mongo 8.
Nếu brand chưa được thêm ở mục 6.2 hoặc review rỗng, query trả 0 vẫn hợp lệ nhưng chưa
đủ dữ liệu để kết luận tăng hiệu năng. TTL chỉ áp dụng `system_logs` Mongo, không xóa
log PG/violation_logs; không cần chờ 90 ngày hoặc sửa thời gian log thật để kiểm.

### 5.5. Kiểm benchmark trước/sau và chi phí index

Chạy thêm trên DB hiện tại:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, title, price FROM product
WHERE category_id = 1 AND status = 1 AND NOT is_deleted
ORDER BY created_at DESC, product_id ASC LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, title FROM product
WHERE status = 1 AND NOT is_deleted
  AND (title ILIKE '%laptop%' OR description ILIKE '%laptop%');

SELECT pg_size_pretty(pg_indexes_size('product')) AS product_index_size;
```

Ở quy mô 1.000 sản phẩm/30 đơn, planner có thể chọn Seq Scan. Không tắt seqscan, không
DROP index để dựng kết quả trước/sau trên database đang dùng.

Để kiểm bằng chứng của kế hoạch, mở [benchmark README](benchmark/README.md),
`benchmark/pg/{before,after}_*.txt`, `benchmark/pg/summary.json` và
`benchmark/mongo/summary.json`. Đối chiếu:

- Bộ PG lịch sử có 50.016 sản phẩm/100.030 đơn, khác seed 1.000 hiện tại.
- Có chín query PG và ba query Mongo; một số query không nhanh hơn sau index.
- Search PG lịch sử 316,562 → 0,372 ms; đó là số đo lưu lại, không phải kết quả máy bạn.
- Index vật lý lịch sử tăng 35.225.600 → 58.736.640 byte, có chi phí ghi/dung lượng.
- Mongo benchmark lịch sử là Mongo 7.0.43; muốn tuyên bố Mongo 8 phải đo mới trên DB/
  collection benchmark riêng. Hướng tái lập có trong README benchmark; không cần tạo
  100.000 dòng vào DB ứng dụng để làm bài kiểm thủ công này.

**Bằng chứng cần lưu:** catalog index, hai cây partition, plan pruning, năm count user,
Mongo explain và bảng so sánh lịch sử có ghi rõ môi trường.

### 5.6. Indexing v2: kiểm 007 và M01 trên DB thực tế

Trước hết đọc lịch sử ở 2.1. SQL 007 và M01 là hai bước riêng: áp migration PostgreSQL
không tự tạo index Mongo. Nếu PG chưa áp 007 hoặc Mongo chưa khởi tạo source có M01,
ghi rõ phần chưa triển khai, không dùng số liệu stack thử nghiệm làm kết quả của DB này.
Việc tự áp dụng thực hiện riêng theo [runbook indexing v2](benchmark/indexing_v2/README.md).

**A. PostgreSQL — có đủ 9 index logical và đúng cấu trúc không?**

Chạy trong Query Tool, chỉ đọc catalog. Query giữ cả dòng MISSING để không bỏ sót index:

```sql
WITH expected(index_name) AS (VALUES
    ('idx_product_visible_date_id'),
    ('idx_product_image_url'),
    ('idx_user_profile_avatar_url'),
    ('idx_order_voucher_lookup'),
    ('idx_etl_runs_started'),
    ('idx_etl_runs_aggregate_success'),
    ('idx_etl_outbox_entity_pending'),
    ('idx_etl_outbox_pending_event'),
    ('idx_user_role_role_user')
)
SELECT e.index_name, t.relname AS table_name, am.amname AS method,
       i.indisunique, i.indisvalid, i.indisready,
       pg_get_indexdef(ix.oid) AS definition,
       pg_get_expr(i.indpred, i.indrelid) AS predicate,
       CASE WHEN ix.oid IS NULL THEN 'MISSING'
            WHEN i.indisvalid AND i.indisready THEN 'READY'
            ELSE 'INVALID/NOT READY' END AS index_state
FROM expected e
LEFT JOIN pg_class ix ON ix.oid = to_regclass('public.' || e.index_name)
LEFT JOIN pg_index i ON i.indexrelid = ix.oid
LEFT JOIN pg_class t ON t.oid = i.indrelid
LEFT JOIN pg_am am ON am.oid = ix.relam
ORDER BY e.index_name;
```

| Index | Khóa theo thứ tự | Predicate |
|---|---|---|
| idx_product_visible_date_id | product(created_at DESC, product_id ASC) | status=1 AND is_deleted=false |
| idx_product_image_url | product_image(image_url) | Toàn phần, cho phép dùng chung URL |
| idx_user_profile_avatar_url | user_profile(avatar_url) | Toàn phần, nonunique |
| idx_order_voucher_lookup | order(voucher_id) | Toàn phần, gồm cả order xóa mềm |
| idx_etl_runs_started | etl_runs(started_at DESC) | Toàn phần |
| idx_etl_runs_aggregate_success | etl_runs(ended_at DESC) | status='success' AND details ? 'aggregate' |
| idx_etl_outbox_entity_pending | etl_outbox(entity_type, entity_key, event_id) | status<>'done' |
| idx_etl_outbox_pending_event | etl_outbox(event_id, available_at) | status IN ('pending','dead') |
| idx_user_role_role_user | user_role(role_id, user_id) | Toàn phần |

**Mong đợi sau 007:** 9 dòng READY, B-tree, nonunique, đúng bảng/khóa/chiều/predicate.
`pg_get_indexdef` có thể bỏ chữ ASC mặc định hoặc thể hiện IN bằng ANY/ARRAY tương đương.
Các PK/UNIQUE và index cũ vẫn giữ. Không thêm UNIQUE cho URL ảnh hoặc token OTP.

Kiểm cây index voucher trên parent HASH và các children:

```sql
WITH RECURSIVE index_tree(oid) AS (
    SELECT to_regclass('public.idx_order_voucher_lookup')::oid
    UNION ALL
    SELECT h.inhrelid FROM pg_inherits h JOIN index_tree p ON h.inhparent = p.oid
)
SELECT ix.relname AS index_name, t.relname AS table_name,
       i.indisvalid, pg_relation_size(ix.oid) AS physical_bytes,
       pg_get_indexdef(ix.oid) AS definition
FROM index_tree n
JOIN pg_class ix ON ix.oid = n.oid
JOIN pg_index i ON i.indexrelid = ix.oid
JOIN pg_class t ON t.oid = i.indrelid
ORDER BY t.relname;
```

**Mong đợi:** 5 relation index hợp lệ: parent + 4 children. Toàn bộ gói thêm 13 relation
index cho 9 index logical; parent có thể 0 byte vì dữ liệu nằm ở children. Khi báo dung
lượng, cộng các relation vật lý, không chỉ đọc kích thước parent.

**B. Quan sát plan, không sửa index để dựng đối chứng trên DB đang dùng**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.product_id, p.title, p.price
FROM product p JOIN category c USING (category_id)
WHERE p.status=1 AND NOT p.is_deleted AND c.is_active AND NOT c.is_deleted
ORDER BY p.created_at DESC, p.product_id ASC LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT started_at, status FROM etl_runs ORDER BY started_at DESC LIMIT 1;

EXPLAIN
SELECT * FROM etl_outbox
WHERE status IN ('pending','dead') AND available_at <= clock_timestamp()
ORDER BY event_id LIMIT 100 FOR UPDATE SKIP LOCKED;
```

Query queue dùng EXPLAIN **không ANALYZE**, không thực thi claim event. Giữ nguyên
clock_timestamp/thứ tự event_id của worker. Seed nhỏ hoặc bảng run/outbox rỗng có thể
cho Seq Scan; đó không tự chứng minh sai index. Lưu plan, số dòng và môi trường thực,
không ép planner hoặc lấy thời gian một SELECT làm SLA toàn bộ ETL.

**C. Mongo — M01 cho tham chiếu ảnh còn sống**

```javascript
db.product_details.getIndexes().filter(i => i.name === "idx_live_product_image_key")
var manualImageKey = "<OBJECT_KEY_DEMO>"; // từ PG, bỏ prefix /media/
db.product_details.find(
  {deleted: false, "images.key": manualImageKey}, {_id: 1}
).limit(1).explain("executionStats")
```

**Mong đợi sau khởi tạo M01:** key `images.key:1`, partialFilterExpression
`{deleted:false}`, unique không bật. Đây là index multikey cho mảng images; nhiều product
vẫn được tham chiếu cùng ảnh. Ghi docs/keys examined và plan; không bắt buộc một plan
cố định khi collection nhỏ. M02 brand/RAM còn hoãn, không yêu cầu xuất hiện để đánh Đạt.

MinIO kiểm đúng bucket/key và đọc byte theo mục 4.3; không chạy CREATE INDEX SQL trong
Console. Index M01 và index URL PG hỗ trợ tìm tham chiếu trước cleanup, không thay object key.

**D. Verifier và bằng chứng tải tách biệt**

Nếu chạy trực tiếp, vào thư mục `backend/` và kích hoạt môi trường Python của backend;
nếu dùng Docker, chọn lệnh Compose thay thế ở khối sau:

```bash
python -m scripts.verify_indexing_v2 --mongo
```

```bash
dc run --rm --no-deps --entrypoint python backend -m scripts.verify_indexing_v2 --mongo
```

Chỉ dùng postflight này khi đã áp 007 **và** khởi tạo M01; cần PASS cho checksum, key order,
predicate, validity, cây voucher và M01. Lệnh chỉ đọc, không tự tạo index hay cập nhật DB.

[Bằng chứng indexing v2](benchmark/indexing_v2/2026-11-01/README.md) có 147 kiểm thử đạt,
PG 16.15/Mongo 8.0.32, 36 biến thể query và phép đo đọc/ghi riêng. Đây là kết quả của
stack thử nghiệm đã dọn, không phải một lượt kiểm trên DB bạn đang dùng. Gói được chọn là
I02/I04/I05/I07/I08/I09/I10/I11/I12 và M01; các ứng viên khác có lý do hoãn.

Khi nghiệm thu hiệu năng, xem cả median/p95, buffers/docs examined, bytes và WAL. Một số
phép ghi vượt ngưỡng rà soát 10% (ví dụ retry/counter update); báo cáo đã ghi đánh đổi và
biến thiên giữa các lần đo. Không kết luận mọi thao tác đều nhanh hơn. Muốn đo trước/sau
mới thì dùng runner/DB tải riêng theo runbook, không DROP index hay tạo 100k dòng vào DB hiện tại.

**Bằng chứng cần lưu thêm:** trạng thái 006/007 và M01 thực tế, 9 định nghĩa index,
cây voucher, plan PG/Mongo và bảng chi phí có nhãn môi trường/thời gian rõ ràng.

## 6. Ngày 5: ETL và đối soát

ETL hiện tại là Python đọc PG → chuẩn hóa → upsert Mongo, đồng bộ/kiểm ảnh MinIO và
xây `report_daily_sales` trên **PG primary**. Nó không chuyển quyền quyết định giá,
tồn kho hoặc số dư sang Mongo.

### 6.1. Quan sát lịch chạy, backlog và kiểm chất lượng

Trong pgAdmin:

```sql
SELECT mode, status, rows_in, rows_out, errors, started_at, ended_at,
       details->'quality' AS quality, details->'backlog' AS backlog,
       details->'media_cleanup' AS media_cleanup
FROM etl_runs ORDER BY started_at DESC LIMIT 10;

SELECT status, count(*) AS events, min(created_at) AS oldest
FROM etl_outbox GROUP BY status ORDER BY status;

SELECT count(*) FILTER (WHERE status <> 'done') AS not_done,
       count(*) FILTER (WHERE status = 'dead') AS dead,
       min(created_at) FILTER (WHERE status <> 'done') AS oldest_not_done
FROM etl_outbox;

SELECT name, value, updated_at FROM etl_state ORDER BY name;
```

**Mong đợi khi hệ thống yên và worker bắt kịp:** có run `success`, errors=0;
quality.mismatches=0, backlog pending/dead=0; `full_initialized` là true, heartbeat mới.
Bảng outbox rỗng là hợp lệ nếu chưa có ghi sau khi cài trigger. Query GROUP BY có thể
không có dòng; query đếm FILTER ở dưới vẫn trả 0.

Mở JSON `details.quality` để xem `pg_active`/`mongo_active`, field_mismatches,
projection_errors và media referenced/found/errors. Một run `running` vừa bắt đầu
không phải lỗi; nếu chạy lâu hoặc `partial/failed`, xem mã lỗi và dependency.

CLI hỗ trợ nếu dùng Docker:

```bash
dc run --rm --no-deps --entrypoint python backend -m etl.run status
dc logs --tail 80 etl-worker
```

`status` chỉ đọc; không cần dừng daemon để xem. Poll mặc định 60 giây giữa các chu kỳ,
không bảo đảm mỗi thay đổi luôn xong trong đúng 60 giây. Ghi lại thời gian bắt đầu/chốt,
mục tiêu kế hoạch là dưới 5 phút khi tải bình thường. Một batch mặc định 100 event;
backlog lớn cần nhiều chu kỳ.

### 6.2. GHI THỬ: tạo một sản phẩm demo đi qua PG → MinIO → Mongo

**A. Chuẩn bị ảnh và đăng nhập**

1. Dùng JPEG/PNG có sẵn dưới 2 MiB, có thể lấy một ảnh từ `database/03_seeds/media/products/`.
2. Mở Swagger. Authorize bằng user seed `user1@gmail.com` / `user123` nếu tài khoản chưa
   được thay đổi; trường OAuth2 `username` nhận email. `GET /api/v1/auth/me` để xác nhận
   user/seller ID. Không dùng tài khoản root Mongo/MinIO để đăng nhập web.
3. Kiểm tên demo chưa dùng:

```sql
SELECT product_id, seller_id, is_deleted FROM product WHERE title = 'MANUAL7D-DEMO-A';
```

Nếu có dòng, đổi tên demo để tránh sửa nhầm dữ liệu lần trước.

**B. Tạo sản phẩm trong Swagger**

`POST /api/v1/products` → Try it out, điền:

| Trường | Giá trị thử |
|---|---|
| title | MANUAL7D-DEMO-A |
| category_id | 1, hoặc danh mục tồn tại |
| description | MANUAL7D initial description |
| price / quantity | 100000 / 10 |
| weight_grams / dimensions | 1000 / 20x10x5 cm |
| condition_rating / warranty_months | 8 / 3 |
| transfer_method | 1 |
| files | Chọn một ảnh thực dưới 2 MiB |

Các trường tùy chọn chưa dùng để trống/không gửi theo Swagger, không gửi chuỗi `null`
vào trường số. Execute và lưu response, đặc biệt `<PID_DEMO>`, `<IMAGE_ID_DEMO>` và URL ảnh.

**Mong đợi:** HTTP 201, status=0 (pending), có bản ghi ảnh và metadata.

```sql
SELECT product_id, seller_id, category_id, title, price, quantity, status,
       created_at, updated_at FROM product WHERE product_id = <PID_DEMO>;
SELECT image_id, image_url, content_type, size_bytes, is_primary
FROM product_image WHERE product_id = <PID_DEMO>;
SELECT event_id, source_table, entity_type, entity_key, operation, status, created_at
FROM etl_outbox WHERE entity_type = 'product'
  AND entity_key = jsonb_build_object('id', <PID_DEMO>)
ORDER BY event_id DESC LIMIT 20;
```

**C. Kiểm ảnh trên MinIO**

Từ URL vừa trả về, bỏ `/media/` để lấy key. Mở `product-images` và tìm đúng
`products/<PID_DEMO>/...`. Preview thành công, size/Content-Type khớp PG. Không tự rename
object trong Console vì PG vẫn giữ key cũ.

**D. Đợi worker và kiểm Mongo**

Trong Shell, thay ID rồi chạy; các bước sau tái sử dụng biến `manualPid` trên cùng phiên:

```javascript
var manualPid = <PID_DEMO>;
if (!Number.isInteger(manualPid) || manualPid <= 0) throw new Error("ID demo không hợp lệ");
db.product_details.findOne({product_id: manualPid}, {
  product_id: 1, category_id: 1, description: 1, dimensions: 1,
  condition: 1, images: 1, deleted: 1, updated_at: 1, etl: 1
})
```

Refresh sau mỗi chu kỳ. **Mong đợi:** đúng ID, mô tả ban đầu, dimensions có length=20,
width=10, height=5, unit=cm; condition.grade=8; ảnh đúng key. Các event liên quan sẽ về
`done`. Nếu worker xử lý rất nhanh, không kịp thấy `pending` vẫn hợp lệ.

Sản phẩm pending vẫn được ETL, nhưng chưa hiện trên catalogue công khai.
`GET /api/v1/products/<PID_DEMO>` hiện có thể đọc detail của sản phẩm chưa xóa;
không dùng detail thành công để suy rằng sản phẩm đã được duyệt.

### 6.3. GHI THỬ: outbox thuộc cùng transaction và rollback không bị đồng bộ

Trước tiên ghi lại `description` và `updated_at` của **sản phẩm demo**. Trong pgAdmin,
chọn chạy trọn khối, không sửa sản phẩm seed:

```sql
BEGIN;
SET LOCAL TIME ZONE 'UTC';
UPDATE product
SET description = 'MANUAL7D SHOULD ROLLBACK',
    updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
WHERE product_id = <PID_DEMO>
RETURNING product_id, description;

SELECT event_id, source_table, entity_key, status
FROM etl_outbox WHERE entity_type = 'product'
  AND entity_key = jsonb_build_object('id', <PID_DEMO>)
ORDER BY event_id DESC LIMIT 5;
ROLLBACK;
```

**Mong đợi:** trong transaction thấy mô tả mới và event mới của UPDATE. Ghi lại event_id
mới nhất của lần UPDATE này. Sau ROLLBACK, chạy ở transaction mới:

```sql
SELECT description, updated_at FROM product WHERE product_id = <PID_DEMO>;
```

Query thêm `etl_outbox WHERE event_id = ...` với ID vừa ghi. **Mong đợi:** mô tả trở về
trước thử, event rollback không còn tồn tại; Mongo không nhận chuỗi `SHOULD ROLLBACK`.
Worker khác connection chỉ nhìn thấy thay đổi đã commit. Gap event_id sau rollback
không phải mất sự kiện nghiệp vụ.

Tiếp theo thử **commit** thật trên sản phẩm demo:

```sql
BEGIN;
SET LOCAL TIME ZONE 'UTC';
UPDATE product
SET description = 'MANUAL7D committed description',
    updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
WHERE product_id = <PID_DEMO>
RETURNING product_id, description, updated_at;
COMMIT;
```

Đợi worker, đọc lại PG/outbox và Mongo. **Mong đợi:** Mongo description thành
`MANUAL7D committed description`, event done; thời gian Mongo là UTC tương ứng PG.
SET LOCAL UTC giúp trigger ghi nguồn múi giờ đúng cho cập nhật SQL thử này. Không tự
chuyển toàn bộ timestamp cũ hoặc sửa bảng `etl_time_origin` để làm kết quả khớp.

### 6.4. GHI THỬ: metadata do Mongo quản lý được giữ qua ETL

Trong Mongo Shell, sau khi document demo đã tồn tại:

```javascript
if (!db.product_details.findOne({product_id: manualPid, deleted: false})) {
  throw new Error("Đợi ETL tạo document demo trước");
}
db.product_details.updateOne(
  {product_id: manualPid, deleted: false},
  {$set: {
    "attributes.brand": "Manual7D",
    "attributes.ram_gb": NumberInt(16),
    tags: ["manual7d", "demo"]
  }}
)
```

**Mong đợi:** matchedCount=1. Chỉ cập nhật attributes/tags của sản phẩm demo; không sửa
các trường PG sở hữu như description/images/deleted/etl trong Mongo để giả lập đồng bộ.

Đổi mô tả demo thêm một lần bằng API PUT sản phẩm hoặc transaction SQL như mục 6.3,
chờ ETL. Đọc Mongo: mô tả được cập nhật, brand/ram/tags vẫn còn. Lặp lại full ETL ở
mục tiếp theo cũng phải giữ metadata này. Đây là bằng chứng partial upsert bảo toàn
trường Mongo sở hữu, không phải ghi đè nguyên document.

### 6.5. GHI THỬ VẬN HÀNH: chạy full hai lần để kiểm idempotency

Nếu daemon đang chạy, không mở thêm full/reconcile cạnh tranh lock. Chọn thời gian
không có người thao tác ứng dụng; ghi count trước từ mục 6.6, rồi dừng **worker**, giữ
backend/PG/Mongo/MinIO để ETL đọc được:

```bash
dc stop -t 120 etl-worker
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run full
dc run --rm --no-deps --entrypoint python backend -m etl.run reconcile
dc run --rm --no-deps --entrypoint python backend -m etl.run status
dc start etl-worker
```

Thực hiện từng lệnh, lưu output của mỗi lượt. Nếu một lượt lỗi, ghi lỗi và **vẫn chạy
`dc start etl-worker` sau khi kiểm tra**, không bỏ hệ thống ở trạng thái quên worker.
Nếu báo `etl_worker_busy`, kiểm daemon/CLI khác còn chạy; không xóa advisory lock bằng
cách sửa dữ liệu. Với worker chạy ngoài Docker, dừng/khởi động tiến trình tương ứng.

**Mong đợi:** full hai lượt và reconcile trả success; cùng tập ID, không nhân đôi
document/object đã có; brand/ram/tags demo được giữ; quality.mismatches=0, media errors=0.
`rows_in/rows_out` là bộ đếm xử lý, có thể gồm cả full scan và event lặp; không yêu cầu
bằng số sản phẩm, không cố làm chúng bằng 1.000 hay số 57 của bằng chứng cũ.
`etl_runs` tăng thêm số dòng là đúng vì mỗi lần chạy có một bản ghi vận hành.

`reconcile` kiểm đối soát sâu và xử lý bản sao không còn nguồn; nó không tự sửa mọi
field sai lệch. Nếu phát hiện field mismatch, kiểm nguồn rồi xử lý event/full phù hợp.

### 6.6. Đối chiếu PG và Mongo đúng theo xóa mềm/TTL

Trong pgAdmin:

```sql
SELECT 'product' AS entity, count(*) AS total,
       count(*) FILTER (WHERE NOT is_deleted) AS active FROM product
UNION ALL
SELECT 'order', count(*), count(*) FILTER (WHERE NOT is_deleted) FROM "order"
UNION ALL
SELECT 'review', count(*), count(*) FILTER (WHERE NOT is_deleted) FROM review;
SELECT count(*) AS violations FROM violation_log;
SELECT count(*) AS contact_messages FROM system_feedback;
```

Trong Mongo Shell:

```javascript
for (const name of ["product_details", "order_snapshots", "reviews"]) {
  const c = db.getCollection(name);
  printjson({name, total: c.countDocuments({}), active: c.countDocuments({deleted: {$ne: true}})});
}
printjson({violations: db.violation_logs.countDocuments({}), contacts: db.contact_messages.countDocuments({})});
```

**Mong đợi trên DB mới, trước khi tạo demo:** product Mongo tổng=1000, active=967;
order tổng/active=30; violation=11. Sau demo phải so theo nguồn thực tế.
Sau hard delete, Mongo có thể giữ tombstone `deleted:true`, nên total không luôn bằng
PG total. So active và các key/field là kiểm tra chính, không chỉ nhìn tổng collection.

Log chỉ tính những dòng PG nằm trong 90 ngày theo nguồn múi giờ:

```sql
SELECT count(*) AS eligible_logs
FROM system_log s JOIN etl_time_origin t
  ON t.source_table = 'system_log'
 AND t.source_key = jsonb_build_object('log_id', s.log_id, 'created_at', s.created_at)
 AND t.field_name = 'created_at' AND t.source_value = s.created_at
WHERE s.created_at AT TIME ZONE t.source_zone >= CURRENT_TIMESTAMP - interval '90 days';
```

```javascript
db.system_logs.countDocuments({
  deleted: {$ne: true},
  created_at: {$gte: new Date(Date.now() - 90 * 86400 * 1000)}
})
```

Thời điểm sát ngưỡng có thể lệch giữa hai lần đếm; dùng report quality của cùng một run
để đối soát. Mongo TTL xóa nền nên tổng log cũ có thể chưa giảm tức thì.

Kiểm duplicate product bằng Mongo:

```javascript
db.product_details.aggregate([
  {$group: {_id: "$product_id", count: {$sum: 1}}},
  {$match: {count: {$gt: 1}}}
]).toArray()
```

**Mong đợi:** mảng rỗng. Unique index và count không thay đổi qua full lặp là hai bằng
chứng bổ sung; vẫn xem field_mismatches trong quality để phát hiện dữ liệu sai nội dung.

### 6.7. Kiểm transform, dữ liệu nhạy cảm và snapshot đơn hàng

1. Mở document demo: `updated_at` là BSON Date, dimensions là object số và unit.
2. Xem `order_snapshots`: tiền là giá trị nguyên VND, subtotal=quantity×price_at_purchase,
   total_amount bằng tổng items; final=total+shipping-discount.
3. Snapshot dùng `title_current/category_id_current/seller_id_current`: đây là metadata
   hiện tại, không phải toàn bộ tiêu đề/danh mục bất biến tại thời điểm mua. Giá mua
   vẫn lấy `price_at_purchase` trong order_detail.
4. Tìm trường nhạy cảm không được phép ở cấp document, chỉ in count:

```javascript
for (const name of [
  "product_details", "reviews", "order_snapshots",
  "system_logs", "violation_logs", "contact_messages"
]) {
  printjson({name, unexpected: db.getCollection(name).countDocuments({$or: [
    {password_hash: {$exists: true}}, {random_key: {$exists: true}},
    {password_reset_token: {$exists: true}}, {email_verification_token: {$exists: true}}
  ]})});
}
```

**Mong đợi:** unexpected=0. Đây là phép kiểm trường cụ thể, không chứng minh tuyệt đối
mọi nội dung tự do không có PII. Không lưu hash, token hoặc dữ liệu cá nhân vào bằng chứng.
Contact/violation projection dùng nội dung thay thế; không mong đợi raw message PG được
chép nguyên sang Mongo. Mật khẩu/wallet không thuộc pipeline sao chép này.

### 6.8. Tổng hợp doanh thu và đối chiếu nguồn

Trong pgAdmin, sau khi worker bắt kịp:

```sql
SELECT report_date, seller_id, category_id, orders_count,
       item_quantity, gross_sales_vnd, refreshed_at
FROM report_daily_sales ORDER BY report_date, seller_id, category_id;

WITH expected AS (
  SELECT (o.order_date AT TIME ZONE t.source_zone
                         AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS report_date,
         p.seller_id, p.category_id,
         count(DISTINCT o.order_id) AS orders_count,
         sum(d.quantity) AS item_quantity, sum(d.subtotal) AS gross_sales_vnd
  FROM "order" o JOIN order_detail d USING (order_id)
  JOIN product p USING (product_id)
  LEFT JOIN etl_time_origin t ON t.source_table = 'order'
    AND t.source_key = jsonb_build_object('order_id', o.order_id)
    AND t.field_name = 'order_date' AND t.source_value = o.order_date
  WHERE o.order_status = 3 AND NOT o.is_deleted
  GROUP BY 1, 2, 3
)
SELECT coalesce(e.report_date, r.report_date) AS report_date,
       coalesce(e.seller_id, r.seller_id) AS seller_id,
       coalesce(e.category_id, r.category_id) AS category_id,
       e.gross_sales_vnd AS source_gross, r.gross_sales_vnd AS report_gross
FROM expected e FULL JOIN report_daily_sales r
  USING (report_date, seller_id, category_id)
WHERE e.orders_count IS DISTINCT FROM r.orders_count
   OR e.item_quantity IS DISTINCT FROM r.item_quantity
   OR e.gross_sales_vnd IS DISTINCT FROM r.gross_sales_vnd;
```

**Mong đợi:** query đối soát cuối không có dòng. Chỉ order DELIVERED=3/chưa xóa được
cộng; nhóm theo ngày Việt Nam, seller/category hiện tại. Tổng gross là tiền hàng trước
giảm giá và chưa gồm ship; khác `total_revenue` cũ lấy final_amount. Không cộng orders_count
qua nhiều nhóm seller/category để suy tổng đơn duy nhất vì một đơn có thể thuộc nhiều nhóm.

### 6.9. Lỗi ETL và cơ chế thử lại

```sql
SELECT event_id, entity_type, entity_key, status, attempts,
       last_error_code, available_at, processed_at
FROM etl_outbox WHERE status <> 'done' ORDER BY event_id LIMIT 30;
```

```javascript
db.etl_errors.find({resolved: false}, {
  event_id: 1, entity_type: 1, code: 1, attempts: 1, last_at: 1
}).limit(20).toArray()
```

**Mong đợi khi khỏe:** không còn lỗi chưa xử lý. Mục 7.7 có bài thử mất dependency để
quan sát retry. Outbox là nguồn giữ sự kiện khi Mongo mất; việc collection etl_errors
chưa ghi được trong thời gian Mongo tắt không làm sự kiện thành done.

Backoff tăng theo số lần lỗi; cấu hình mặc định max attempts=5, sự kiện có thể bị đánh
dấu dead. Mã worker hiện vẫn chọn cả pending/dead khi đến `available_at`; không diễn giải
dead là đã bị xóa hay chắc chắn sẽ không tự thử lại. CLI `retry-dead` có thể đưa lịch thử
về hiện tại sau khi sửa nguyên nhân. Không DELETE outbox để làm backlog bằng 0.

### 6.10. Bài tổng hợp: cùng một sản phẩm xuyên PG–Mongo–MinIO–API

Chạy sau 6.2–6.4 và **7.1**, trước khi unlink ảnh ở 7.2. Nếu ảnh demo trước đã bị xóa,
dùng một demo mới theo 6.2 và ghi bộ ID mới; không sửa key/metadata thật để ép kết quả khớp.
Bài này là bằng chứng chính cho **HN — dữ liệu hợp nhất**.

**A. Chốt các khóa và giá trị từ PG**

```sql
SELECT p.product_id, p.category_id, p.title, p.price, p.quantity, p.status,
       p.is_deleted, p.description, p.updated_at,
       i.image_id, i.image_url, i.content_type, i.size_bytes,
       regexp_replace(i.image_url, '^/media/', '') AS object_key
FROM product p JOIN product_image i USING (product_id)
WHERE p.product_id = <PID_DEMO> AND i.image_id = <IMAGE_ID_DEMO>;
```

Lưu kết quả làm mốc, không so với giá/số lượng hardcode nếu đã đặt đơn/thay dữ liệu demo.
`product_id`, `image_id`, URL và object_key phải thuộc cùng ảnh của cùng sản phẩm.

**B. Đối chiếu projection và metadata Mongo**

```javascript
var manualPid = <PID_DEMO>;
db.product_details.findOne({product_id: manualPid, deleted: false}, {
  _id: 1, product_id: 1, category_id: 1, description: 1,
  attributes: 1, tags: 1, images: 1, updated_at: 1, etl: 1
})
```

Đợi event của lần commit liên quan về done rồi so: ID/category khớp PG; mô tả demo ở
6.3 không có thông tin cần che nên khớp PG. Với dữ liệu khác, so theo quy tắc transform/
scrub ở 6.7, không đòi nguyên văn nội dung nhạy cảm trong Mongo. Trong images tìm đúng
image_id, bucket=`product-images`, key/size/content_type khớp ảnh PG.
Brand/RAM/tags do Mongo sở hữu vẫn còn sau cập nhật mô tả và full lặp. Không yêu cầu
Mongo lưu giá/tồn kho hiện tại để làm nguồn quyết định của API.

**C. Đối chiếu file thực ở MinIO**

Mở object tại `product-images/<OBJECT_KEY_DEMO>` trong Console. Preview/Download và so
Content-Type, size với PG/Mongo. Với ảnh vừa upload, có thể so SHA-256 file gốc với file
tải về bằng `sha256sum` (Linux) hoặc `Get-FileHash -Algorithm SHA256` (PowerShell).
Đây là so hai file thực, không đòi PG/Mongo có sẵn cột checksum ảnh. Không so tổng số
object với tổng dòng ảnh vì seed dùng chung URL và có alias.

**D. Đối chiếu kết quả ứng dụng hợp nhất**

Trong Swagger/website, đọc `GET /api/v1/products/<PID_DEMO>` và lưu JSON:

| Phần response/quan sát | Phải đối chiếu với |
|---|---|
| product_id/category_id/title/price/quantity/status/description | Giá trị PG hiện tại, cùng bộ ID |
| attributes/tags; metadata_status=available | Document Mongo sống, đúng product/category |
| product_images[].image_id/image_url | Ảnh PG hiện tại, chọn đúng image_id và URL |
| Mở URL ảnh `/media/...` | Byte từ đúng object MinIO; HTTP 200 khi dependency khỏe |
| Lọc brand/RAM sau duyệt | Demo chỉ xuất hiện khi điều kiện PG cho phép; kiểm bằng người xem khác seller hoặc chưa đăng nhập |

API detail hiện không xuất content_type/size_bytes trong product_images; hai trường này
đối chiếu qua PG, Mongo, MinIO và response tải ảnh, không đánh lỗi API vì thiếu trường
ngoài contract. So price theo giá trị tiền, không đòi định dạng chuỗi thập phân PG/JSON giống nhau.

Detail thành công cho product pending chưa chứng minh được phép lên catalogue. Khi
kiểm visibility, dùng kết quả duyệt/xóa mềm và filter ở 7.1; không chỉ đọc Mongo để quyết định.
GET detail tăng view_count, nên chờ worker bắt kịp sau khi ngừng refresh trước khi chốt backlog.

**E. Chốt đồng bộ và kết luận**

Ghi event_id của lần thay đổi đã commit, mốc commit/quan sát đã chuẩn hóa UTC, processed_at,
etl.synced_at và run_id/quality ở 6.1. Chọn cùng lần thay đổi, không lấy một run success cũ
hoặc một document trùng ID để kết luận đã đồng bộ lần thử mới. Nếu đo độ trễ, ghi cách đo;
khác cách hiển thị múi giờ không phải bằng chứng mất dữ liệu.

| Kiểm xuyên kho | Kết quả/bằng chứng của lượt bạn |
|---|---|
| PG đúng dòng/ảnh và giá trị nguồn | … |
| Mongo đúng projection, giữ attributes/tags | … |
| MinIO đúng key và file thực/size/type | … |
| API ghép đúng PG + Mongo; URL đọc đúng byte MinIO | … |
| Commit hội tụ, rollback không lọt sang đích, quality khớp khi yên | … |

Chỉ kết luận **hợp nhất dữ liệu đạt** khi có đủ đối chiếu trên. Ba cửa sổ GUI kết nối
được hoặc ba nơi cùng có một ID là chưa đủ. Hành vi khi Mongo/MinIO lỗi kiểm ở 7.7;
nhãn hợp nhất không có nghĩa mọi chức năng vẫn đầy đủ khi một kho ngừng hoạt động.

## 7. Ngày 6: ứng dụng, ảnh, đơn hàng và lỗi dịch vụ

Các bài sau tiếp tục dùng **sản phẩm demo** từ mục 6.2. Đây là thao tác có ghi dữ liệu;
đếm source/đích sau thử theo dữ liệu hiện tại, không tiếp tục so cứng với seed ban đầu.

### 7.1. Duyệt sản phẩm, metadata và bộ lọc

1. Swagger: đăng nhập moderator `mod1@oldshop.com` / `mod123` nếu tài khoản seed chưa đổi.
2. `GET /api/v1/products/pending/all`: tìm sản phẩm demo, lưu status trước duyệt. Danh sách
   có phân trang; dùng skip/limit để tìm nếu seed có nhiều sản phẩm pending.
3. `POST /api/v1/products/<PID_DEMO>/approve`: mong đợi HTTP 200, status=1, approved_by
   là moderator. Thử lại cùng endpoint sẽ bị từ chối vì không còn pending; không coi
   việc duyệt lặp không thành công là lỗi mất dữ liệu.
4. Logout/clear Authorize để xem catalogue công khai, hoặc đăng nhập **buyer khác seller**.
   Seller đang đăng nhập bị loại hàng của chính mình khỏi catalogue là hành vi hiện tại.
5. Gọi `GET /api/v1/products/<PID_DEMO>`: price=100000, quantity hiện tại lấy PG;
   attributes.brand=Manual7D, ram_gb=16, tags từ Mongo; metadata_status=available.
6. Trên website, mở sản phẩm tương ứng, xem thuộc tính/ảnh. DevTools → Network để đối
   chiếu response của API với phần hiển thị.

GET detail tăng `view_count`, commit PG và có thể tạo thêm event ETL. Sau khi xem detail,
backlog xuất hiện ngắn hạn là bình thường; không đòi outbox trống trong lúc liên tục refresh.

Trong Swagger, `GET /api/v1/products`, điền trường `attributes` bằng JSON thô:

```json
{"brand":"Manual7D","ram_gb":16}
```

**Mong đợi:** sản phẩm demo đã duyệt/chưa xóa xuất hiện với đúng quyền nhìn thấy.
Thử thêm filter brand không tồn tại → danh sách rỗng. Thử input sau → HTTP 422:

```json
{"$where":"invalid"}
```

API chỉ hỗ trợ AND các điều kiện bằng nhau trên scalar, khóa đơn giản; không nhận
Mongo operator/nested filter. Nó lấy candidate ID từ Mongo rồi kiểm status/category/
seller, sort và phân trang ở PG. Tối đa 5.000 candidate; vượt ngưỡng phải thu hẹp filter,
không tự cắt để giả là đã có kết quả đầy đủ.

### 7.2. Kiểm upload và hàng đợi xóa ảnh

Ảnh của sản phẩm demo ở mục 6.2 là **object upload riêng**, không phải URL ảnh seed dùng
chung. Ghi lại `<IMAGE_ID_DEMO>` và URL/key trước thử. Nếu muốn thử chọn lại ảnh đại diện,
tạo demo với hai file; bài đơn giản dùng một ảnh chỉ chứng minh unlink và cleanup.

1. Authorize seller sở hữu demo hoặc admin.
2. Gọi `DELETE /api/v1/products/<PID_DEMO>/images/<IMAGE_ID_DEMO>`.
3. **Mong đợi HTTP 204:** xóa liên kết PG thành công, không có nghĩa file đã bị xóa tức thì.
4. Trong pgAdmin:

```sql
SELECT image_id FROM product_image WHERE image_id = <IMAGE_ID_DEMO>;
SELECT deletion_id, url_path, status, attempts, available_at, processed_at, last_error_code
FROM media_deletions ORDER BY deletion_id DESC LIMIT 10;
```

5. Đợi worker bắt kịp. Mongo images không còn ảnh này, queue chuyển done sau khi không
   còn tham chiếu; MinIO không còn object upload đó. URL `/media/...` trả 404 khi file đã xóa.
6. Nếu ảnh còn được PG hoặc Mongo tham chiếu, cleanup phải trì hoãn. Kiểm backlog,
   quality và key trước khi kết luận; không xóa tay object để làm queue đạt.

Đặt bài xóa ảnh này **sau** các bài cần xem ảnh, đặc biệt thử lỗi MinIO ở mục 7.7.
Không dùng ảnh seed chung để chứng minh object phải biến mất: một key có thể được nhiều
sản phẩm sử dụng; cơ chế cleanup giữ file còn tham chiếu là đúng.

**Avatar, tùy chọn:** Swagger `POST /api/v1/users/me/avatar`, dùng tài
khoản demo và ảnh dưới 2 MiB. Đối chiếu URL trả về, `user_profile.avatar_url`, object
`user-avatars/users/{user_id}/avatar-{uuid}.ext` và ảnh trên UI. Thay avatar lần hai rồi
xem media_deletions; avatar upload cũ được thu gom, avatar seed/shared được giữ theo quy tắc.

### 7.3. GHI THỬ: giỏ hàng, đơn hàng và snapshot

Chọn buyer khác seller demo, ví dụ `user2@gmail.com` / `user123` nếu seller là user1.
Không dùng PayPal để kiểm luồng cơ bản; chỉ dùng COD để không phụ thuộc tài khoản sandbox.
Thực hiện trước khi soft-delete demo; sản phẩm phải approved, còn tồn kho.

**A. Giỏ hàng giữ chỗ tồn kho**

1. Authorize buyer, xác nhận `GET /api/v1/auth/me`.
2. Ghi quantity hiện tại `Q` của demo từ PG.
3. `POST /api/v1/cart/items`, body:

```json
{"product_id": <PID_DEMO>, "quantity": 1}
```

4. `GET /api/v1/cart`: có một item; lưu cart_item_id. PG quantity thành Q−1 vì ứng dụng
   giữ chỗ ngay khi thêm giỏ. Đây là hành vi hiện có, không đợi checkout mới trừ tồn.
5. Thử add lần nữa: cập nhật số lượng cùng item, không tạo hai dòng cart/product;
   quantity thành Q−2. Sau đó PUT item quantity về 1 hoặc DELETE item để trả tồn.
6. Thử thêm chính sản phẩm của seller khi đăng nhập seller → HTTP 400.

Bài tối thiểu nên để đúng **một đơn vị demo** trong giỏ trước checkout.

**B. Lấy địa chỉ đúng buyer và phương thức COD**

Dùng `GET /api/v1/users/me/contacts` trong Swagger, hoặc lấy ID qua Query Tool:

```sql
SELECT c.contact_id, c.user_id
FROM contact_info c JOIN user_core u USING (user_id)
WHERE u.email = 'user2@gmail.com' AND NOT c.is_deleted;
SELECT payment_method_id, method_name FROM payment_method WHERE NOT is_deleted;
```

Ghi `<BUYER_CONTACT_ID>` của đúng buyer. Dùng ID method có tên COD, thường 1 trên seed;
không suy rằng các tên phương thức còn lại đã có tích hợp provider hoàn chỉnh.

**C. Tạo đơn**

Swagger `POST /api/v1/orders` dưới token buyer; thay các token số trước Execute:

```json
{
  "contact_id": <BUYER_CONTACT_ID>,
  "payment_method_id": 1,
  "shipping_fee": 30000,
  "notes": "MANUAL7D order demo",
  "order_items": [{"product_id": <PID_DEMO>, "quantity": 1}]
}
```

**Mong đợi:** HTTP 201; lưu `<ORDER_ID_DEMO>`; pending=0, tiền hàng=100000,
shipping=30000, final=130000 nếu chưa sửa giá và không dùng voucher. Item đã mua rời
khỏi giỏ nhưng không trả tồn vì phần giữ chỗ đã được tiêu thụ. Trước thử hãy ghi nhận
số lượng; không dùng bài này để tuyên bố đã kiểm toàn bộ race condition checkout.

```sql
SELECT order_id, buyer_id, order_status, total_amount, shipping_fee,
       discount_amount, final_amount, tableoid::regclass AS physical_partition
FROM "order" WHERE order_id = <ORDER_ID_DEMO>;
SELECT product_id, quantity, price_at_purchase, subtotal
FROM order_detail WHERE order_id = <ORDER_ID_DEMO>;
SELECT transaction_id, amount, transaction_status
FROM "transaction" WHERE order_id = <ORDER_ID_DEMO>;
```

Chờ ETL rồi xem Mongo:

```javascript
db.order_snapshots.findOne({order_id: <ORDER_ID_DEMO>}, {
  order_id: 1, buyer: 1, items: 1, payments: 1,
  total_amount_vnd: 1, shipping_fee_vnd: 1,
  discount_amount_vnd: 1, final_amount_vnd: 1, order_status: 1, etl: 1
})
```

**Mong đợi:** cùng buyer ID, danh sách items/payments và tiền khớp PG; không có địa chỉ/
SĐT đầy đủ bị sao chép vào document snapshot.

**D. Trạng thái và báo cáo**

Authorize seller/admin, dùng `PUT /api/v1/orders/<ORDER_ID_DEMO>` để chuyển confirmed=1,
shipping=2, delivered=3, từng lần quan sát response và snapshot sau ETL. Ví dụ body một bước:

```json
{"order_status": 3, "tracking_number": "MANUAL7D-TRACK"}
```

Sau delivered, chạy đối soát mục 6.8. Report tăng **100000 tiền hàng**, không phải 130000.
Khi thử API lifecycle, lưu cả quyền người gọi; buyer thường không được xác nhận/giao hàng.
Nếu không muốn tạo doanh thu demo, có thể dừng ở pending rồi hủy qua luồng ứng dụng;
không chạy cả hai nhánh và mong đợi cùng tổng doanh thu.

### 7.4. GHI THỬ CÓ ROLLBACK: ràng buộc PG sau partition

Bài này kiểm trigger chống tự mua và unique cart trực tiếp ở DB. Chạy nguyên khối
trong pgAdmin; mọi dữ liệu thử được rollback, nhưng sequence có thể tăng.

```sql
BEGIN;
DO $$
DECLARE
  pid integer; sid integer; cid integer; mid integer; oid integer; cart integer;
BEGIN
  SELECT p.product_id, p.seller_id, c.contact_id INTO pid, sid, cid
  FROM product p JOIN contact_info c ON c.user_id = p.seller_id
  WHERE NOT p.is_deleted AND NOT c.is_deleted
  ORDER BY p.product_id, c.contact_id LIMIT 1;
  SELECT payment_method_id INTO mid FROM payment_method WHERE NOT is_deleted
  ORDER BY payment_method_id LIMIT 1;
  IF pid IS NULL OR mid IS NULL THEN RAISE EXCEPTION 'Thiếu dữ liệu nền để thử'; END IF;

  INSERT INTO "order" (buyer_id, contact_id, payment_method_id, total_amount, final_amount)
  VALUES (sid, cid, mid, 100, 100) RETURNING order_id INTO oid;
  BEGIN
    INSERT INTO order_detail (order_id, product_id, quantity, price_at_purchase, subtotal)
    VALUES (oid, pid, 1, 100, 100);
    RAISE EXCEPTION 'FAIL: self-buy không bị chặn';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM NOT LIKE 'BUSINESS_RULE_VIOLATION:%' THEN RAISE; END IF;
    RAISE NOTICE 'PASS: trigger chặn tự mua sau partition';
  END;

  SELECT cart_id INTO cart FROM shopping_cart WHERE user_id <> sid ORDER BY cart_id LIMIT 1;
  IF cart IS NULL THEN RAISE EXCEPTION 'Thiếu cart để thử'; END IF;
  INSERT INTO shopping_cart_item (cart_id, product_id, quantity) VALUES (cart, pid, 1)
  ON CONFLICT (cart_id, product_id) DO NOTHING;
  BEGIN
    INSERT INTO shopping_cart_item (cart_id, product_id, quantity) VALUES (cart, pid, 1);
    RAISE EXCEPTION 'FAIL: cặp cart/product trùng không bị chặn';
  EXCEPTION WHEN unique_violation THEN
    RAISE NOTICE 'PASS: UNIQUE cart/product chặn dòng trùng';
  END;
END $$;
ROLLBACK;
```

**Mong đợi:** hai NOTICE PASS. Lỗi self-buy rollback cả log chặn trong subtransaction;
không tuyên bố audit của hành động bị từ chối được ghi bền vững độc lập. Test SQL
cart ở đây không giữ chỗ tồn kho như API; chỉ kiểm UNIQUE và rollback toàn bộ.

### 7.5. Review/report và dashboard

**Review/report — GHI THỬ:** đăng nhập buyer đã đặt demo, gọi
`POST /api/v1/products/<PID_DEMO>/reviews` lần lượt với hai body:

```json
{"rating": 4, "title": "MANUAL7D review", "content": "MANUAL7D kiểm thử đánh giá"}
```

```json
{"rating": 0, "title": "MANUAL7D report", "content": "MANUAL7D kiểm thử báo cáo"}
```

Ghi các review_id trả về. Trong PG chọn review theo product_id, trong Mongo chọn:

```javascript
db.reviews.find({product_id: manualPid}, {
  review_id: 1, type: 1, rating: 1, status: 1, created_at: 1, etl: 1
}).toArray()
```

**Mong đợi sau ETL:** rating 4 → type=review, rating 0 → type=report;
review mới có moderation status mặc định pending. Moderator xem danh sách báo cáo qua
`GET /api/v1/moderator/reviews/violations`. Danh sách này phải chứa report vừa tạo;
review rating 4 không thuộc danh sách báo cáo.

**Dashboard:** đăng nhập admin, `GET /api/v1/admin/stats?sales_year=2026`, chọn năm có
đơn trong dữ liệu của bạn. Xem `sales_report.available`, `as_of`, `stale`, daily và gross.
Mở dashboard UI, đổi năm/tháng, so với `report_daily_sales`.

**Mong đợi:** có run aggregate thành công → available=true; nếu quá 5 phút chưa refresh
→ stale=true. Biểu đồ dùng số liệu thực, không số ngẫu nhiên. Không so gross của report
bằng total_revenue cũ vì công thức khác nhau; nguồn report là primary, không cần replica.

### 7.6. GHI THỬ: contact, audit log và violation projection

**Feedback/contact:** Authorize user demo rồi gọi `POST /api/v1/system/feedback`:

```json
{"subject":"MANUAL7D feedback","content":"MANUAL7D nội dung thử pipeline contact"}
```

Lưu `<FEEDBACK_ID_DEMO>`. Endpoint feedback này ghi dữ liệu PG; không dùng endpoint
contact có background relay nếu chỉ muốn kiểm ETL tại chỗ.

```sql
SELECT feedback_id, subject, content, status, created_at
FROM system_feedback WHERE feedback_id = <FEEDBACK_ID_DEMO>;
```

```javascript
db.contact_messages.findOne({feedback_id: <FEEDBACK_ID_DEMO>}, {
  feedback_id: 1, subject: 1, content: 1, status: 1, attachments: 1, created_at: 1, etl: 1
})
```

**Mong đợi sau ETL:** cùng ID/status, thời gian được chuẩn hóa; subject Mongo là
`Contact request`, content là `Message retained in PostgreSQL`. Raw nội dung giữ ở PG,
attachments mặc định rỗng. Không kết luận sai chỉ vì hai bên không chép nguyên văn.

**Audit log:** dùng sản phẩm demo để tạo một log riêng, không chứa dữ liệu cá nhân:

```sql
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SELECT log_system_action(NULL, 'MANUAL7D_CHECK', 'product', <PID_DEMO>, 'MANUAL7D audit demo');
COMMIT;

SELECT log_id, created_at, action, resource_type, resource_id,
       tableoid::regclass AS physical_partition
FROM system_log WHERE action = 'MANUAL7D_CHECK' AND resource_id = <PID_DEMO>
ORDER BY created_at DESC, log_id DESC LIMIT 5;
```

```javascript
db.system_logs.find({action: "MANUAL7D_CHECK", resource_id: manualPid}, {
  log_id: 1, created_at: 1, action: 1, resource_id: 1, payload: 1, etl: 1
}).sort({created_at: -1}).limit(5).toArray()
```

**Mong đợi:** PG định tuyến log vào tháng phù hợp; Mongo có log cùng danh tính
`log_id + created_at` sau chuẩn hóa, payload.event=PG_LOG. Không định danh log chỉ bằng
log_id khi đối soát vì PK PG là khóa ghép. Log mới nằm trong cửa sổ TTL 90 ngày.

**Violation log:** không cần khóa một tài khoản thật để tạo thêm vi phạm. Chọn một ID
seed bằng `SELECT log_id, user_id, action_taken FROM violation_log ORDER BY log_id LIMIT 1;`,
rồi đọc document Mongo có cùng log_id. `target_user_id` khớp user_id PG, action_taken
được giữ; reason là `Violation details retained in PostgreSQL`. Actor có thể NULL vì
nguồn PG không có cột actor; không yêu cầu ETL tự tạo danh tính người xử lý.

### 7.7. GIÁN ĐOẠN DỊCH VỤ: kiểm fallback và phục hồi

Thực hiện trên stack demo/bảo trì, từng tình huống một. Ghi health/API trước khi dừng,
và **start lại đúng service ngay sau bài thử**. Không dùng `down -v`, không dừng PG primary,
không tự promote node. Nếu không quản lý được container, đánh dấu phần này Chưa kiểm;
không suy ra đã đạt từ việc mở được GUI.

| Tình huống | Cách quan sát | Mong đợi khi lỗi | Sau khôi phục |
|---|---|---|---|
| Dừng PG replica nếu có | `dc stop pg-replica` | Catalogue/checkout/report primary vẫn hoạt động | `dc start pg-replica`, streaming trở lại |
| Dừng một Mongo SECONDARY trong bộ 3 | Chọn SECONDARY từ rs.status; ví dụ `dc stop mongo2` chỉ khi mongo2 là secondary | Còn majority, Mongo/app phục vụ; không chứng minh Mongo shard | `dc start mongo2`, chờ SECONDARY khỏe |
| Dừng MinIO | `dc stop minio` | `/health` 200, readiness 503; ảnh/upload 503; catalogue PG vẫn 200 | `dc start minio`, readiness/ảnh phục hồi |
| Dừng toàn Mongo | Base: `dc stop mongo1`; bộ 3: `dc stop mongo1 mongo2 mongo3` | Detail fallback PG, metadata_status=unavailable; lọc attributes 503; outbox giữ event | Start lại cùng danh sách, chờ bầu PRIMARY, ETL bắt kịp |

**Thử MinIO:** lấy URL ảnh có thật trước khi dừng. Trình duyệt có thể cache ảnh một giờ;
bật DevTools → Disable cache và reload, hoặc dùng request HEAD mới:

```bash
curl -I http://localhost:58000/media/products/prod_1_1_laptop.jpg
```

Trên PowerShell dùng `curl.exe -I ...`. Không lấy ảnh còn hiển thị từ cache làm bằng
chứng MinIO vẫn phục vụ khi đã tắt. Đường dẫn ví dụ phải tồn tại trước thử; nếu đang
thử demo, dùng URL upload đã ghi và chưa xóa ở mục 7.2.

**Thử Mongo và outbox không mất thay đổi:**

1. Ghi brand/ram của demo trước khi dừng toàn Mongo.
2. Khi Mongo đã mất, gọi detail demo: vẫn HTTP 200 với dữ liệu PG, attributes/tags rỗng,
   metadata_status=unavailable. Gọi catalogue thường vẫn 200; catalogue có attributes
   filter phải 503, không âm thầm bỏ bộ lọc.
3. Sửa description demo qua API/SQL commit như mục 6.3, đặt chuỗi
   `MANUAL7D change while Mongo unavailable`.
4. Quan sát event PG tồn tại, chưa ACK done nếu chưa ghi được Mongo. Có thể thấy attempts,
   last_error_code và available_at; nếu chưa đến chu kỳ worker thì chưa có attempt là bình thường.
5. Khôi phục Mongo bằng `dc start` cùng service đã dừng; đợi `hello`/rs.status có PRIMARY,
   không chỉ đợi healthcheck ping. Direct connection Compass đang mở vào secondary có
   thể cần kết nối lại vào primary để ghi.
6. Đợi retry/backoff và worker: description mới tới Mongo, metadata brand/ram cũ vẫn giữ,
   event chuyển done, etl_errors tương ứng resolved=true nếu đã tạo được bản ghi lỗi.
7. Chạy status, đối soát và readiness. Mongo=up, minio=up, database=up; backlog về 0
   khi không còn thao tác mới. Kết thúc bằng `dc ps -a`.

Đừng khẳng định mọi request luôn thành công trong lúc chuyển trạng thái/election.
Bài thử chứng minh phục hồi đúng và phần chức năng còn phục vụ; MinIO single-node
không thể tiếp tục trả byte khi node đó mất. Một member Mongo đơn lẻ dừng là mất toàn
Mongo, không thể gọi đó là thử quorum của bộ ba.

## 8. Ngày 7: báo cáo, slide và demo

### 8.1. Kiểm đầu ra trên đĩa

Mở [bộ bàn giao](report/README.md), [báo cáo nguồn](report/07_report.md),
[slide nguồn](report/07_slides.md), [kịch bản demo](report/07_demo_script.md) và
[câu hỏi phản biện](report/07_qa.md).

Nếu đã có bản build, kiểm thủ công các file:

| Đầu ra | Vị trí | Cách kiểm |
|---|---|---|
| Báo cáo | `docs/report/generated/oldshop_report.docx` và `.pdf` | Mở được, đủ 9 chương + phụ lục A/B/C, không lỗi font/cắt bảng |
| Slide | `docs/report/generated/oldshop_slides.pptx` và `.pdf` | 18 slide, có notes ở PPTX, sơ đồ/chữ đọc rõ |
| Video/subtitle | `docs/report/generated/oldshop_demo.mp4` và `.srt` | Phát được, khoảng 5–7 phút, phụ đề đúng; bản lịch sử 6:06, 1280×720 |
| Ảnh dự phòng | `docs/report/screenshots/` | Ảnh đủ chặng, không lộ credentials |
| Sơ đồ cuối | `docs/diagram/07_*` | Tên bảng/node và luồng phù hợp triển khai thực |
| Gói nộp | `dist/releases/` | ZIP mở được; SHA256 khớp file checksum nếu đã đóng gói |

Binary được ignore bởi Git nên clone source có thể chưa có generated/ZIP; khi đó ghi
**Chưa có artifact tại máy này**, không xem checkbox trong kế hoạch là bằng chứng file
đang tồn tại. Cách build/validate/package có trong README bộ bàn giao; tài liệu này
không yêu cầu tự build lại toàn bộ để kiểm dữ liệu.

Kiểm tag local từ terminal nếu cần:

```bash
git tag --list v0.7.0-data-upgrade
```

Tag local tồn tại không chứng minh đã push lên remote. Cấu hình GitHub Actions tồn tại
không chứng minh một lượt CI remote đã chạy thành công; cần URL/run thực và commit tương ứng.

### 8.2. Kiểm tính nhất quán giữa báo cáo và hệ thống hiện tại

- Báo cáo phải phân biệt nguồn giao dịch PG, metadata/read model Mongo và byte MinIO.
- HASH order_id không prune theo buyer; user split có view JOIN chỉ đọc.
- Report trên primary; PG replica async và Mongo replica set là topology tùy chọn.
- Không mô tả FDW, sharding, Patroni, đa máy hoặc MinIO distributed là đã triển khai.
- Số 146 backend/15 frontend/9 tình huống lỗi là kết quả lịch sử Ngày 6. Lượt indexing v2
  riêng có 147 backend test (97 regression, 28 ETL, 22 API) trên Mongo 8.0.32; không bao
  gồm nghiệm thu nhiều máy. Cả hai đều không phải số trường hợp bạn vừa kiểm thủ công.
- Báo cáo/video/gói release lịch sử có thể vẫn chứa seed 16 sản phẩm và Mongo 7.0.43.
  Ghi rõ đó là snapshot cũ. Bộ seed hiện tại 1.000 sản phẩm và lượt kiểm Mongo 8 cần
  bằng chứng mới; không sửa số đo benchmark cũ thành số liệu môi trường mới.

### 8.3. Tổng duyệt thủ công 5–7 phút

Chuẩn bị sẵn các cửa sổ, không gõ password khi quay:

1. **~40 giây:** topology/service khỏe; chỉ rõ base hay resilience, phiên bản thực.
2. **~60 giây:** pgAdmin xem migration, HASH/RANGE và user split.
3. **~50 giây:** Mongo xem product demo, attributes, images và một snapshot đơn hàng.
4. **~40 giây:** MinIO preview đúng key; website đọc cùng ảnh qua gateway.
5. **~60 giây:** event commit → worker → Mongo; cho xem kết quả rollback/idempotency đã lưu.
6. **~45 giây:** catalog index 007/M01 nếu đã áp, một plan và benchmark có nhãn đúng môi trường;
   nêu cả chi phí ghi, không chỉ thời gian SELECT.
7. **~60 giây:** một tình huống lỗi ngắn, khôi phục và status/readiness; kết thúc bằng hạn chế.

Nếu quay bài thử service, phải chọn môi trường cho phép gián đoạn và khôi phục trong
kịch bản. Có thể dùng ảnh bằng chứng đã lưu cho phần full ETL/retry kéo dài; ghi nhãn
đúng là kết quả trước đó, không trình diễn như phép đo đang chạy trực tiếp.

## 9. Dọn dữ liệu thử và xử lý sai lệch

### 9.1. Kết thúc một lượt kiểm

1. Nếu có item giỏ demo chưa checkout, xóa **đúng item** qua API buyer để hoàn phần giữ
   chỗ. Không clear toàn bộ giỏ của người khác hoặc sửa quantity bằng SQL để bù tùy ý.
2. Nếu có đơn demo, giữ lại nhãn notes/ID cho đối soát; hủy/xóa mềm bằng API với đúng
   quyền nếu cần, không hard-delete giao dịch tài chính. Đơn delivered và đơn canceled
   có ảnh hưởng báo cáo khác nhau; ghi trạng thái cuối vào phiếu.
3. Nếu cần kiểm cleanup file, dùng mục 7.2 cho ảnh upload riêng **trước khi** soft-delete
   sản phẩm. Soft-delete sản phẩm giữ ảnh theo thiết kế.
4. Có thể xóa mềm demo bằng `DELETE /api/v1/products/<PID_DEMO>`; đợi Mongo deleted=true.
   Attributes/tags/tombstone được giữ là bình thường; count tổng Mongo có thể không giảm.
5. Review/report demo giữ nhãn MANUAL7D và ID. Không xóa collection thật để đưa count
   về seed. Feedback/log demo cũng giữ ID/nhãn để nhận diện. Collection validator tạm
   ở mục 4.2 đã được finally dọn đúng tên của lần chạy.
6. Start lại mọi service đã dừng, đặc biệt etl-worker; xác nhận PRIMARY/SECONDARY,
   replication streaming nếu có, readiness 200 và ETL bắt kịp.
7. Lưu bằng chứng vào thư mục riêng, ví dụ `docs/manual_checks/<ngay-kiem>/`, sau khi
   kiểm không chứa secret/PII. Đây là nơi gợi ý cho ảnh/log bạn tự tạo, chưa phải dữ liệu
   bằng chứng được tự sinh khi đọc tài liệu.

### 9.2. Bảng chẩn đoán nhanh

| Hiện tượng | Kiểm tra tiếp theo |
|---|---|
| SQL báo thiếu user_core/schema_migrations | Sai DB hoặc chưa migrate; xem to_regclass, không chạy init chồng |
| Count product vẫn 16 | DB cũ; seed mới chỉ áp khi khởi tạo mới, không phải ETL làm mất sản phẩm |
| Mongo chưa có document | Đúng DB/URI chưa, full_initialized, worker, etl_runs/outbox và media có sẵn chưa |
| Mongo total 1000 nhưng active 967 | Đúng với seed mới có 33 sản phẩm xóa mềm |
| Attribute rỗng | Seed chưa tạo metadata; dùng demo Mongo ở mục 6.4, không nhập JSON phác thảo của kế hoạch |
| Metadata_status=missing | Không có document sống đúng product/category; kiểm ID/category/deleted/ETL |
| Metadata_status=unavailable | Mongo chưa cấu hình/lỗi kết nối hoặc document không hợp lệ cho service đọc |
| Full báo etl_worker_busy | Daemon/CLI khác giữ lock; dùng tuần tự, không sửa dữ liệu lock |
| Full/quality báo thiếu ảnh | Lấy đúng key từ PG, kiểm object MinIO/credentials/metadata; không bịa size |
| Count PG/Mongo bằng nhau nhưng quality fail | Xem field_mismatches/projection_errors; count không đủ chứng minh nội dung đúng |
| Seq Scan dù có index | Seed nhỏ/selectivity, predicate có khớp partial index không; xem plan, không ép planner |
| Report khác total_revenue | Gross tiền hàng khác final_amount; kiểm năm, ngày VN và trạng thái delivered |
| Ảnh vẫn hiển thị sau tắt MinIO | Browser cache; dùng Disable cache/HEAD mới trước khi kết luận |
| Ảnh xóa khỏi PG nhưng object còn | Cleanup chờ worker, outbox/quality, tham chiếu PG/Mongo; kiểm media_deletions |
| DB GUI được nhưng readiness thiếu Mongo/MinIO | Backend dùng cấu hình khác hoặc STORAGE_BACKEND vẫn local |
| Replica/Mongo member chưa khỏe sau start | Đợi streaming/election và dùng endpoint primary phù hợp; ping chưa đủ |
| Mongo command Unauthorized | Phân biệt thiếu quyền quản trị với lỗi topology/validator |
| Artifact binary không có trong clone | Xem quy trình build hoặc gói release, binary không được quản lý như source |

Không đánh dấu đạt bằng cách xóa event lỗi, nới validator, tắt constraint, mở bucket public
hoặc sửa dữ liệu đích cho giống nguồn. Ghi nguyên nhân và chạy lại bài kiểm sau khi sửa đúng.

## 10. Phiếu nghiệm thu

Sao chép bảng này sang biên bản của lượt kiểm. Với mỗi hàng ghi **Đạt / Không đạt /
Chưa kiểm / Không áp dụng**, thời gian và tên ảnh/log; không tick sẵn dựa trên kế hoạch.

**Tổng hợp theo trọng tâm trước khi kết luận:**

| Trục | Bằng chứng chính | Kết luận của lượt này |
|---|---|---|
| HN — hợp nhất dữ liệu | Bộ ID/key và bảng đối chiếu 6.10, API ghép đúng nguồn | … |
| ETL | Commit/rollback/idempotency/quality/retry và độ trễ quan sát | … |
| IX — indexing | Baseline hoặc 007/M01 thực tế, plan và đánh đổi đọc/ghi/disk | …; ghi rõ phần chưa áp |
| PT — nhiều máy | Topology và kịch bản 3.4 | Chưa kiểm — chưa triển khai, trừ khi có lượt triển khai/kiểm riêng |

Không lấy “Đạt HN/ETL/IX trên một host” làm “Đạt PT nhiều máy”. Giữ các hàng chi tiết
bên dưới để truy vết nguyên nhân đạt/chưa đạt.

| Mã | Nội dung | Trạng thái | Bằng chứng/ghi chú |
|---|---|---|---|
| N1-01 | Đúng DB/version; ghi baseline 001–006 hay đã áp 007 | … | … |
| N1-02 | Schema/ERD, phân loại PG/Mongo/MinIO đúng | … | … |
| N1-03 | Count seed hoặc nguồn thực tế, ảnh đại diện, FK không mồ côi | … | … |
| N2-01 | Primary PG và topology Mongo 8 thực tế | … | … |
| N2-02 | PG replica streaming/read-only nếu có | … | … |
| N2-03 | Mongo 3 member nếu có, giới hạn một host được ghi rõ | … | … |
| PT-01–06 | Nhiều máy theo mục 3.4; không đồng nhất với partition/container local | Chưa kiểm — chưa triển khai | Hạng mục mở |
| N3-01 | Sáu collection có strict validator | … | … |
| N3-02 | Thử valid/invalid/duplicate trên collection tạm | … | … |
| N3-03 | Bucket private; key/size/type/byte ảnh khớp PG–Mongo–MinIO | … | … |
| N4-01 | PG B-tree/GIN/partial/composite/UNIQUE tồn tại | … | … |
| N4-02 | HASH/RANGE và pruning quan sát được | … | … |
| N4-03 | User bốn mảnh đầy đủ, view 20 cột chỉ đọc | … | … |
| N4-04 | Mongo index/TTL và executionStats | … | … |
| N4-05 | Benchmark trước/sau có môi trường và chi phí ghi/dung lượng | … | … |
| N4-06 | Nếu đã áp 007: 9 index logical, voucher 5 relation, đúng định nghĩa/validity/checksum | … | … |
| N4-07 | Nếu đã khởi tạo M01: live images.key partial/nonunique; M02 không bắt buộc | … | … |
| N5-01 | Tạo sản phẩm qua app, ảnh và document xuất hiện | … | … |
| N5-02 | Rollback không để lại event; commit được đồng bộ | … | … |
| N5-03 | Full hai lần không nhân bản, giữ metadata Mongo | … | … |
| N5-04 | Quality/active count/TTL/media khớp, không sao chép hash/token | … | … |
| N5-05 | Report đối soát đúng theo ngày VN/gross | … | … |
| HN-01 | Bộ ID/key/giá trị khớp PG–Mongo–MinIO–API theo 6.10; đúng quyền sở hữu dữ liệu | … | … |
| HN-02 | Hội tụ bất đồng bộ và fallback đúng; không tuyên bố transaction ACID xuyên ba kho | … | … |
| N6-01 | Detail và attribute filter kết hợp PG/Mongo | … | … |
| N6-02 | Ảnh upload riêng được unlink/cleanup đúng | … | … |
| N6-03 | Cart/order/payment snapshot và trạng thái đồng bộ | … | … |
| N6-04 | Self-buy/UNIQUE PG còn hiệu lực sau partition | … | … |
| N6-05 | Review/report đúng type, dashboard dùng report thực | … | … |
| N6-06 | Feedback/audit/violation projection và che nội dung đúng | … | … |
| N6-07 | Outage/fallback/retry và khôi phục đúng | … | … |
| N7-01 | Báo cáo/slide/video/ZIP thực sự mở được | … | … |
| N7-02 | Phiên bản, số liệu lịch sử/hiện tại và phạm vi khớp | … | … |
| N7-03 | Tổng duyệt; service đã phục hồi, dữ liệu demo được ghi nhận | … | … |

**Kết luận của lượt kiểm:** …

**Môi trường:** Mongo …; PG …; topology …; commit/image …; DB mới/cũ …

**Chưa kiểm/ngoài phạm vi:** …

**Dữ liệu demo còn giữ:** PID …; order …; review …; feedback/log …; ảnh/key …

## Tài liệu và mã nguồn để đối chiếu

- [Kế hoạch 7 ngày](KE_HOACH_NANG_CAP_7_NGAY.md), [decisions](decisions.md),
  [hướng dẫn cấu hình/chạy](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md).
- [Kế hoạch indexing](KE_HOACH_THIET_KE_INDEXING.md),
  [runbook 007/M01](benchmark/indexing_v2/README.md),
  [bằng chứng indexing v2](benchmark/indexing_v2/2026-11-01/README.md).
- [Thiết kế JSON](design/03_json_design.md), [index/phân mảnh](design/04_indexing.md),
  [ETL](design/05_etl.md), [tích hợp và giới hạn](design/06_completion_plan.md).
- [SQL demo ngắn](report/demo_pgadmin.sql), [Mongo demo ngắn](report/demo_mongo.js),
  [bằng chứng benchmark](benchmark/README.md), [bàn giao Ngày 7](report/README.md).
- Nguồn kiểm chứng kỹ thuật: [migrations](../database/04_migrations/),
  [Mongo schema/index](../backend/app/services/mongo_schema.py),
  [document contracts](../backend/app/schemas/documents.py),
  [ETL runner](../backend/etl/run.py), [quality](../backend/etl/quality.py),
  [product metadata](../backend/app/services/product_metadata.py),
  [storage](../backend/app/services/storage.py),
  [Compose](../deploy/docker-compose.distributed.yml).
