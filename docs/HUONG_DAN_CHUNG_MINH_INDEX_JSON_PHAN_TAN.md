# HƯỚNG DẪN CHỨNG MINH INDEXING, CẤU TRÚC JSON VÀ HỆ PHÂN TÁN A–B
Ngày tổng hợp: 12/11/2026

Tài liệu tổng hợp theo source hiện tại của dự án. Các kết quả ghi là
“mong đợi” cần được đối chiếu bằng cách chạy trên môi trường của bạn.


# 1. CHỌN ĐÚNG CÔNG CỤ VÀ DATABASE


- idx_product_catalogue: PostgreSQL, dùng psql hoặc pgAdmin Query Tool.
- idx_product_title_trgm: PostgreSQL.
- uq_cart_product: PostgreSQL.
- idx_product_attributes: MongoDB, dùng mongosh hoặc Shell của Compass.
- Document và JSON Schema validator: MongoDB.
- Phân tán A–B: terminal hai máy, PostgreSQL FDW và HTTP API.

Với MongoDB, sử dụng mongosh. Không chạy SQL PostgreSQL trong mongosh.

Phân biệt hai môi trường:
- Database ứng dụng commerce: dùng để kiểm tra các index, dữ liệu giỏ hàng
  và MongoDB đã nạp dữ liệu.
- Project oldshop-vm-demo: catalogue PostgreSQL A–B theo tài liệu Site B.
  Fixture ban đầu có 5 sản phẩm mỗi site; B không cần MongoDB/backend.
  Không mặc định database demo catalogue có đủ bảng commerce để test giỏ.

Chỉ sử dụng tài khoản/mật khẩu của đúng môi trường. Không chụp hoặc gửi
file env, mật khẩu, hay user mapping chứa credentials.


## 2. CHỨNG MINH INDEXING TRONG POSTGRESQL


Định nghĩa tham khảo: database/04_migrations/001_indexes.sql.

Phân biệt ba mức bằng chứng:
1) Index tồn tại: xem catalog của database.
2) Truy vấn dùng index: xem execution plan.
3) Index cải thiện hiệu năng: đo so sánh có kiểm soát trên cùng dữ liệu.
Chỉ thấy tên index chưa chứng minh truy vấn nhanh hơn.


### 2.1. Xác nhận ba index tồn tại


Kết nối database ứng dụng có dữ liệu commerce rồi chạy:

```text
SELECT current_database();

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'idx_product_catalogue',
    'idx_product_title_trgm',
    'uq_cart_product'
  )
ORDER BY indexname;

```
Mong đợi:
- idx_product_catalogue: B-tree (category_id, created_at DESC), partial
```text
  WHERE status = 1 AND is_deleted = false.
```
- idx_product_title_trgm: GIN (title gin_trgm_ops), cùng điều kiện partial.
- uq_cart_product: UNIQUE (cart_id, product_id).


### 2.2. idx_product_catalogue


Chọn category có dữ liệu:

```text
SELECT category_id, count(*)
FROM product
WHERE status = 1 AND is_deleted = false
GROUP BY category_id
ORDER BY count(*) DESC;

```
Thay category_id = 1 bằng category phù hợp rồi chạy:

```text
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, title, created_at
FROM product
WHERE category_id = 1
  AND status = 1
  AND is_deleted = false
ORDER BY created_at DESC
LIMIT 20;

```
Bằng chứng truy vấn dùng index: trong plan xuất hiện tên
idx_product_catalogue, ví dụ “Index Scan using idx_product_catalogue”.

Giải thích: index hỗ trợ lọc theo category và lấy sản phẩm mới nhất trong
phạm vi sản phẩm công khai. Điều kiện truy vấn cần phù hợp partial index.


### 2.3. idx_product_title_trgm


Chọn từ khóa có trong dữ liệu, ví dụ laptop:

```text
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, title
FROM product
WHERE status = 1
  AND is_deleted = false
  AND title ILIKE '%laptop%';

```
Bằng chứng: plan xuất hiện idx_product_title_trgm, thường trong node
“Bitmap Index Scan on idx_product_title_trgm”.

Giải thích: GIN trigram hỗ trợ tìm chuỗi con trong tiêu đề.

Nếu thấy Seq Scan:
- Không kết luận ngay index hỏng. Bảng nhỏ hoặc truy vấn trả nhiều dòng
  có thể khiến PostgreSQL chọn quét bảng.
- Báo cáo hiện có trong dự án cũng ghi nhận ca không chọn index này.
- Giữ lại kết quả thực tế; không trình bày rằng truy vấn dùng index khi
  plan không có tên index đó.
- Có thể khảo sát riêng trong transaction với:
```text
  BEGIN;
  SET LOCAL enable_seqscan = off;
  EXPLAIN (ANALYZE, BUFFERS) ...;
  ROLLBACK;
  Thay dấu ... bằng SELECT đầy đủ. Đây chỉ là khảo sát planner, không phải
  bằng chứng index nhanh hơn trong điều kiện bình thường, và không bảo đảm
  planner chọn đúng index bạn muốn nếu có nhiều index khác.

```
Muốn kết luận cải thiện hiệu năng: dùng database benchmark riêng, so sánh
cùng truy vấn/dataset trước và sau khi có index, lặp nhiều lần và ghi nhận
plan, buffers, thời gian. Không drop index trên database đang sử dụng.


### 2.4. uq_cart_product


Chạy trên database demo commerce có ít nhất một dòng giỏ hàng:

```text
SELECT cart_id, product_id, quantity
FROM shopping_cart_item
LIMIT 1;

```
Sau đó chạy từng lệnh:

```text
BEGIN;

INSERT INTO shopping_cart_item(cart_id, product_id, quantity)
SELECT cart_id, product_id, quantity
FROM shopping_cart_item
ORDER BY cart_item_id
LIMIT 1;

ROLLBACK;

```
Mong đợi thao tác INSERT bị từ chối:
ERROR: duplicate key value violates unique constraint "uq_cart_product"
DETAIL: Key (cart_id, product_id)=(...) already exists.

Sau lỗi vẫn chạy ROLLBACK để kết thúc transaction. Nếu bảng trống, cần
tạo một dòng hợp lệ trước; INSERT ... SELECT trên bảng trống không chứng
minh được việc chặn trùng. Thử nghiệm có thể tiêu thụ một giá trị sequence
cho cart_item_id ngay cả khi rollback; không cần chỉnh lại sequence.

Giải thích: database không cho cùng một sản phẩm thành hai dòng trong một
giỏ, kể cả khi thao tác ghi bỏ qua API.


## 3. CHỨNG MINH idx_product_attributes TRONG MONGODB


Kết nối mongosh/Compass Shell, chọn database chứa product_details.
Nếu chưa biết tên database, kiểm tra cấu hình kết nối của môi trường;
không mặc định tên MongoDB giống tên PostgreSQL.

```text
db.getName()
db.product_details.getIndexes()

```
Mong đợi index có:
  name: "idx_product_attributes"
  key: { "attributes.$**": 1 }

Đây là wildcard index cho các trường bên trong attributes.

Tìm dữ liệu có thuộc tính thực tế:

```text
db.product_details.find(
  { attributes: { $exists: true, $ne: {} } },
  { _id: 0, product_id: 1, attributes: 1 }
).limit(5)

```
Chọn một key/giá trị có thật. Nếu có attributes.color = "black", chạy:

```text
db.product_details
  .find({ "attributes.color": "black" })
  .explain("executionStats")

```
Tìm IXSCAN và indexName: "idx_product_attributes" trong winning plan.
Ghi nhận nReturned, totalKeysExamined, totalDocsExamined.

Nếu optimizer chọn index khác, khảo sát riêng wildcard index bằng:

```text
db.product_details
  .find({ "attributes.color": "black" })
  .hint("idx_product_attributes")
  .explain("executionStats")

```
Ghi rõ đây là truy vấn chỉ định index bằng hint, không phải lựa chọn tự
nhiên của optimizer. Wildcard index không bao phủ mọi tổ hợp lọc/sort.

Nếu mọi attributes đều là {}, bạn mới chứng minh được index tồn tại.
Cần dữ liệu mẫu có thuộc tính trong môi trường demo để chứng minh tra cứu.


## 4. CHỨNG MINH CẤU TRÚC JSON/DOCUMENT


Cách nói chính xác: MongoDB lưu BSON document có cấu trúc tương tự JSON,
với thêm các kiểu dữ liệu như Date.

Source tham khảo:
- backend/app/schemas/documents.py: hợp đồng document.
- backend/app/services/mongo_schema.py: sinh BSON validator.
- docs/report/demo_mongo.js: truy vấn đọc mẫu.


### 4.1. Chứng minh document có object lồng nhau và array


Trong mongosh:

```text
db.product_details.findOne(
  { product_id: 1 },
  {
    _id: 0,
    product_id: 1,
    attributes: 1,
    images: 1,
    tags: 1,
    etl: 1
  }
)

```
Giải thích trên kết quả:
- product_id: giá trị số.
- attributes: object chứa thuộc tính động.
- images: array chứa các object ảnh.
- tags: array chuỗi.
- etl: object metadata đồng bộ.

Đọc thêm document đơn hàng:

```text
db.order_snapshots.findOne(
  { order_id: 1 },
  { _id: 0, order_id: 1, items: 1, final_amount_vnd: 1, etl: 1 }
)

```
items thể hiện các dòng hàng được nhúng trong một document.
Nếu ID 1 không tồn tại, dùng findOne({}) để chọn document đang có.


### 4.2. Chứng minh database có validator


Dùng tài khoản có quyền xem metadata collection:

```text
db.getCollectionInfos({ name: "product_details" })

```
Xem options.validator.$jsonSchema, gồm required, properties, bsonType.
Kiểm tra validationAction và validationLevel nếu được khai báo.

Giải thích: cấu trúc document hỗ trợ object/array lồng nhau; validator
kiểm soát trường bắt buộc và kiểu dữ liệu. attributes vẫn cho phép các
key động theo thiết kế.

Nếu không thấy validator trên collection, file schema trong source chỉ
chứng minh thiết kế, chưa chứng minh validator đã áp dụng trong database.


## 5. ĐĂNG NHẬP POSTGRESQL TRÊN SITE A VÀ SITE B


Các lệnh sau giả định đã dựng môi trường đúng theo:
docs/HUONG_DAN_SITE_B_UBUNTU_24_04.md


### 5.1. Trên máy B: đăng nhập writer B


```text
docker exec -it oldshop-vm-demo-pg-b-1 \
  psql -h 127.0.0.1 -U site_writer -d oldshop_2 -W

```
Nhập SITE_B_WRITER_PASSWORD từ deploy/sites/.env.vm-demo trên B.


### 5.2. Trên máy A: đăng nhập writer A


```text
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -h 127.0.0.1 -U site_writer -d oldshop_1 -W

```
Nhập SITE_A_WRITER_PASSWORD từ deploy/sites/.env.vm-demo trên A.

Kiểm tra trong psql:

```text
SELECT current_database(), current_user, site_id
FROM site_identity;

```
Mong đợi tại A: oldshop_1 | site_writer | A.
Mong đợi tại B: oldshop_2 | site_writer | B.

127.0.0.1 ở đây là loopback bên trong container được docker exec chọn.
pg-a là A; pg-b là B. Dùng \q để thoát psql về terminal hệ điều hành.


### 5.3. Đăng nhập admin A để kiểm tra FDW/view toàn cục


```text
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -U site_admin -d oldshop_1

```
Lệnh dùng Unix socket nội bộ theo cấu hình demo, không cần -W.
Các truy vấn v_product bên dưới thực hiện với admin A theo hướng dẫn.


## 6. CHỨNG MINH HỆ PHÂN TÁN A–B


Đọc tài liệu Site B để dựng mạng, database, FDW và gateway trước.
Địa chỉ 192.168.56.101 là IP B trong ví dụ; thay nếu VM dùng IP khác.


### 6.1. Chứng minh hai môi trường lưu dữ liệu


Trên terminal của mỗi máy:

```text
hostname
ip -br address
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'

```
Trong PostgreSQL từng site (có thể dùng admin tương ứng):

```text
SELECT current_database(), site_id FROM site_identity;

SELECT product_id, seller_id, site_id, title
FROM product
ORDER BY product_id;

SELECT * FROM v_fragment_identity;

```
Mong đợi:
- A lưu sản phẩm ID lẻ, B lưu sản phẩm ID chẵn.
- rules_valid = true.
- Quyền sở hữu sản phẩm theo seller_site; lẻ/chẵn là quy tắc cấp ID tránh
  đụng nhau. Không giải thích rằng chỉ dựa ID lẻ/chẵn để xác định seller.


### 6.2. Chứng minh A truy vấn B qua mạng bằng FDW


Tại psql admin A:

```text
SELECT srvname, srvoptions FROM pg_foreign_server;

SELECT product_id, site_id, title
FROM site_b.product
ORDER BY product_id;

SELECT product_id, site_id, title
FROM v_product
ORDER BY product_id;

```
srvoptions của server_b phải trỏ đúng IP VM B và port 56632.
site_b.product đọc dữ liệu từ B; v_product tái hợp dữ liệu A và B.
Chỉ thấy nhãn site_id = B chưa đủ; cần đối chiếu endpoint với IP VM thật.

Fixture mới ban đầu: v_product có 10 hàng gồm pending/deleted; API danh
sách chỉ trả 6 sản phẩm công khai. Sau khi thêm dữ liệu, số lượng sẽ đổi.


### 6.3. Thêm sản phẩm trên A (tùy chọn)


Đăng nhập writer A, rồi chạy:

```text
BEGIN;
INSERT INTO product(seller_id, category_id, title, price, quantity, status)
```
VALUES(101, 1, 'DEMO-SITE-A-20261112', 120000, 1, 1)
```text
RETURNING product_id, site_id;
COMMIT;

```
Mong đợi ID lẻ, site_id = A. Ghi lại ID trả về.


### 6.4. Ghi trên B, đọc ngay từ A


Đăng nhập writer B trên máy B:

```text
BEGIN;
INSERT INTO product(seller_id, category_id, title, price, quantity, status)
```
VALUES(202, 1, 'DEMO-PHAN-TAN-B-20261112', 120000, 1, 1)
```text
RETURNING product_id, site_id;
COMMIT;

```
Mong đợi ID chẵn, site_id = B. Ghi lại ID thực tế, không tự đoán ID.

Tại psql admin A:

```text
SELECT product_id, site_id, title
FROM v_product
WHERE title = 'DEMO-PHAN-TAN-B-20261112';

```
Bản ghi mới phải xuất hiện mà không chạy seed hoặc copy dữ liệu.
Có thể gọi GET /products/<ID vừa nhận> từ gateway A để đối chiếu.
Mỗi lần INSERT thành công sẽ thêm một bản ghi; dùng tên demo khác nếu
muốn phân biệt các lần chạy.


### 6.5. Kiểm tra gateway trước sự cố


Tại terminal A, khi gateway đã chạy:

```text
curl -i http://127.0.0.1:56680/ready
curl -i http://127.0.0.1:56680/products/1
curl -i http://127.0.0.1:56680/products/2
curl -i 'http://127.0.0.1:56680/products?limit=100'

```
Theo fixture chuẩn, mong đợi HTTP 200; sản phẩm 1 ở A, sản phẩm 2 ở B.
Nếu đã sửa/xóa fixture thì chọn lại các ID công khai có thật ở mỗi site.


### 6.6. Demo sự cố và phục hồi


Trên máy B, từ thư mục source demo (ví dụ ~/oldshop-demo), chỉ dừng site B:

```text
python3 deploy/scripts/sites.py stop \
  --site B \
  --project oldshop-vm-demo \
  --env deploy/sites/.env.vm-demo

```
Tại terminal A:

```text
curl -i http://127.0.0.1:56680/products/1
curl -i http://127.0.0.1:56680/products/2
curl -i http://127.0.0.1:56680/products
curl -i http://127.0.0.1:56680/ready

```
Mong đợi lần lượt: 200, 503, 503, 503.
Detail A vẫn phục vụ được; detail B và danh sách toàn cục báo không sẵn
sàng. Gateway không trả danh sách thiếu dữ liệu như một kết quả thành công.

Trên B phục hồi:

```text
python3 deploy/scripts/sites.py up \
  --site B \
  --project oldshop-vm-demo \
  --env deploy/sites/.env.vm-demo

```
Gọi lại API tại A: mong đợi trở về 200 và sản phẩm demo vẫn còn.
Không bootstrap/reset database để phục hồi; không dùng down -v.

Phạm vi chứng minh:
- Catalogue phân mảnh và truy vấn xuyên hai môi trường A–B.
- Hành vi API khi B không sẵn sàng và khi B phục hồi.
Chưa chứng minh MongoDB sharding, checkout đa site, tự động chuyển đổi
dự phòng hoặc chịu mất host vật lý nếu VM B vẫn chạy trên chính host A.


## 7. SỬA LỖI FDW: PASSWORD AUTHENTICATION FAILED FOR USER b_reader


Lỗi đã gặp tại A:

ERROR: could not connect to server "server_b"
DETAIL: connection to server at "192.168.56.101", port 56632 failed:
FATAL: password authentication failed for user "b_reader"

Ý nghĩa: A đã tới PostgreSQL ở endpoint B, nhưng credentials của b_reader
không được chấp nhận. Đăng nhập bằng site_writer thành công không kiểm
chứng được mật khẩu b_reader vì đây là hai role riêng.


### 7.1. Kiểm tra đăng nhập trực tiếp từ container A tới B


Nếu đang ở psql, thoát bằng \q. Tại terminal A:

```text
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -h 192.168.56.101 -p 56632 \
  -U b_reader -d oldshop_2 -W

```
Nhập SITE_B_READER_PASSWORD trong deploy/sites/.env.vm-demo trên máy B.

Nếu thành công:

```text
SELECT current_database(), current_user, site_id
FROM site_identity;
\q

```
Mong đợi: oldshop_2 | b_reader | B.


### 7.2. Cập nhật env và user mapping FDW tại A


Tại terminal A:

cd /home/phat/Documents/Project/Epic-Ecommerce-FastAPI-main
nano deploy/sites/.env.vm-demo

Đặt SITE_B_READER_PASSWORD tại A giống chính xác mật khẩu đã đăng nhập
thành công ở bước 7.1. Giữ nguyên các password khác.

Chạy:

```text
python3 deploy/scripts/sites.py fdw \
  --site A \
  --project oldshop-vm-demo \
  --env deploy/sites/.env.vm-demo

```
Script cập nhật password trong user mapping của site_admin cho server_b
khi server đã tồn tại, đồng thời cập nhật endpoint theo env.
Chỉ sửa env không tự thay đổi user mapping đang lưu trong PostgreSQL.

Kiểm tra lại bằng một phiên admin A mới:

```text
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -U site_admin -d oldshop_1

SELECT product_id, site_id, title
FROM v_product
ORDER BY product_id;

```

### 7.3. Nếu mật khẩu trong env B cũng không đăng nhập được


Trên máy B:

```text
docker exec -it oldshop-vm-demo-pg-b-1 \
  psql -U site_admin -d oldshop_2

```
Trong psql:

```text
\password b_reader

```
Nhập hai lần mật khẩu bạn chọn. Sau đó cập nhật cùng giá trị vào
SITE_B_READER_PASSWORD trong env cả A và B, rồi làm lại bước 7.1–7.2.

Sửa env B không tự thay mật khẩu role đã được tạo trong database.
Không cần chạy bootstrap lại, xóa volume hoặc mở rộng HBA cho lỗi này.


### 7.4. Phân biệt FDW và gateway


- FDW dùng b_reader với SITE_B_READER_PASSWORD.
- Gateway đọc trực tiếp B dùng global_reader với SITE_B_GLOBAL_PASSWORD.
- Writer B dùng site_writer với SITE_B_WRITER_PASSWORD.

Sửa b_reader giải quyết nhánh FDW. Nếu v_product chạy được nhưng API vẫn
lỗi xác thực, kiểm tra riêng global_reader; không đổi tất cả password
thành một giá trị. Khi dựng ban đầu, hai giá trị READER và GLOBAL của B
cần được chép đúng vào env A theo tài liệu Site B.


## 8. BỘ BẰNG CHỨNG NÊN LƯU KHI BẢO VỆ


1) PostgreSQL catalog: định nghĩa ba index.
2) Execution plan của catalogue và tìm kiếm title.
3) Lỗi unique khi ghi trùng cart/product.
4) MongoDB getIndexes và executionStats cho thuộc tính động.
5) Document có object/array lồng nhau.
6) Validator thực tế của collection.
7) Hostname/IP/container và site_identity tại A/B.
8) Endpoint server_b tại A trỏ đúng VM B.
9) INSERT/COMMIT trên B và cùng product_id đọc được từ A.
10) HTTP trước, trong và sau khi B dừng/phục hồi.

Mỗi ảnh/log nên ghi môi trường, câu lệnh, kết quả và ý nghĩa chứng minh.
Không thay kết quả thực tế bằng kết quả mong đợi trong tài liệu.


## 9. NGUỒN THAM KHẢO


Trong dự án:
- docs/HUONG_DAN_SITE_B_UBUNTU_24_04.md
- database/04_migrations/001_indexes.sql
- database/indexing/catalog.json
- database/distributed/fragmentation.json
- deploy/scripts/sites.py
- backend/app/schemas/documents.py
- backend/app/services/mongo_schema.py
- docs/report/demo_mongo.js
- docs/report/BAO_CAO_KIEN_TRUC_CO_SO_DU_LIEU_OLDSHOP.md

Tài liệu chính thức:
- PostgreSQL: kiểm tra sử dụng index
  https://www.postgresql.org/docs/16/indexes-examine.html
- PostgreSQL: EXPLAIN
  https://www.postgresql.org/docs/16/using-explain.html
- PostgreSQL: partial index
  https://www.postgresql.org/docs/16/indexes-partial.html
- MongoDB: wildcard index
  https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/
- MongoDB: explain
  https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/
- MongoDB: JSON Schema validation
  https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/
