# Kế hoạch thiết kế cấu trúc indexing cho OldShop

**Ngày lập:** 01/11/2026. **Căn cứ:** mã nguồn `database/`, migration `001`–`006`,
truy vấn backend/ETL và benchmark đã lưu. **Trạng thái thực hiện:** đã có migration 007 (9 index PostgreSQL), M01 MongoDB,
benchmark và kiểm thử trên môi trường tách biệt. **Chưa áp vào DB người dùng** theo lựa chọn
của người dùng. [Quyết định đủ 16 ứng viên và bằng chứng](benchmark/indexing_v2/2026-11-01/README.md),
[hướng dẫn tự áp dụng](benchmark/indexing_v2/README.md).

Nội dung thiết kế bên dưới giữ mốc baseline 001–006 để đối chiếu. Các DDL `Ixx` là danh
sách ứng viên lịch sử; chỉ I02/I04/I05/I07/I08/I09/I10/I11/I12 được đưa vào 007. I01/I03/
I06/I13/I14 và M02 được hoãn với lý do trong báo cáo; không chạy toàn bộ DDL minh họa.

## 1. Mục tiêu và phạm vi

Thiết kế index theo đường truy cập dữ liệu thực tế: catalogue, tìm kiếm, tài khoản,
giỏ hàng, đơn hàng, ETL và thu gom ảnh. Mỗi index cần xác định **bảng → cột/biểu thức →
thứ tự khóa → cấu trúc → predicate → truy vấn hưởng lợi → chi phí ghi → cách nghiệm thu**.

Kết quả cần đạt:

- Giữ tính duy nhất và toàn vẹn giao dịch hiện có.
- Tận dụng index đã triển khai, đánh giá khoảng trống thay vì thêm một index cho mọi cột.
- Đo cả đọc, ghi, kích thước index và độ trễ ETL trước khi chọn ứng viên.
- Phân biệt index theo thiết kế SQL với index thực sự đang có trên DB chạy.
- Có lộ trình migration, đối soát và thu hồi index mới nếu kết quả không đạt.

Trọng tâm là PostgreSQL trong `database/`. Mongo được đối chiếu thêm vì lọc thuộc tính
và cleanup có truy vấn sang Mongo; MinIO được xét ở quy ước object key/metadata.
PostgreSQL/Mongo tự xây và quản lý cấu trúc vật lý. Phương án tự lập trình cấu trúc dữ
liệu cho mục đích học tập nằm ở mục 14, tách khỏi đường giao dịch của ứng dụng.

Đây là kế hoạch tiếp theo của [thiết kế indexing Ngày 4](design/04_indexing.md), không
thay thế bằng chứng lịch sử hoặc sửa migration đã áp dụng. Việc đọc mã nguồn chưa
chứng minh index đã tồn tại trên database cụ thể của người chạy.

## 2. Cơ sở dữ liệu dùng để thiết kế

### 2.1. Ba lớp schema cần đọc cùng nhau

| Lớp | Nguồn | Ý nghĩa với indexing |
|---|---|---|
| Baseline | `database/01_schema/*.sql` | PK, UNIQUE và index ban đầu trên 18 bảng |
| Nâng cấp | `database/04_migrations/001`–`006` | Index bổ sung, partition, user split, ETL và cleanup |
| Khởi tạo/vận hành | `database/init.sql`, `backend/scripts/{init_db,migrate}.py` | Baseline nạp trước, runner áp version sau; schema_migrations được runner tạo |

Các điểm quan trọng sau migration:

- `"user"` được đổi thành `user_core`, thêm `user_profile`, `user_secret`, `user_wallet`.
  `users_full` là JOIN view chỉ đọc, không có index riêng như bảng vật lý.
- `"order"` HASH theo `order_id`, bốn partition; index trên parent được triển khai ở các
  partition. Index name sau clone/rename có thể khác tên trong baseline.
- `system_log` RANGE theo `created_at`, có partition tháng và DEFAULT; PK là
  `(log_id, created_at)`, không còn PK đơn cột như baseline.
- `product_image` có thêm `content_type`, `size_bytes`; byte ảnh ở MinIO/local storage.
- Có thêm năm bảng ETL, `media_deletions` và lịch sử `schema_migrations`.

### 2.2. Dữ liệu seed và dữ liệu đo tải

Bộ seed hiện tại có 1.000 product, 2.000 product_image dùng lại 32 URL ảnh; 33 product
xóa mềm, 967 chưa xóa. Order/detail/transaction vẫn 30/30/30, user 15, category 8.
Đây là cơ sở smoke test, không đủ để kết luận index cho hàng trăm nghìn đơn hàng.

Cần hai tập dữ liệu kiểm tra riêng:

| Tập | Quy mô dự kiến | Mục đích |
|---|---|---|
| S — seed | Bộ seed hiện tại | Đúng kết quả, constraint, predicate và ứng dụng |
| L — đại diện tải | Tối thiểu 50.000 product, 100.000 order; tăng ảnh/log/event theo tình huống | Plan, đọc/ghi và dung lượng ở quy mô có ý nghĩa |

Tập L chỉ tạo trên database/collection benchmark riêng. Đây là dữ liệu đo, không phải
đề xuất tăng seed mặc định của ứng dụng vượt giới hạn 10.000 dòng mỗi bảng.
Dữ liệu cũ đang chạy có thể chưa nhận seed mới; luôn đếm thực tế trước khi đo.

## 3. Chọn cấu trúc dữ liệu và hình thức index

| Cấu trúc/hình thức | Dùng trong dự án | Quyết định thiết kế |
|---|---|---|
| B-tree | PK/UNIQUE, equality, range, khóa JOIN, ORDER BY | Lựa chọn chính cho dữ liệu giao dịch và thời gian |
| B-tree nhiều cột | category/date, buyer/date, cart/product | Cột equality thường đứng trước khóa sắp xếp/range; khớp chiều ASC/DESC |
| Partial index | Approved/chưa xóa, pending/dead queue | Chỉ chứa dòng thỏa predicate; phải khớp tập dữ liệu truy vấn |
| GIN trigram | title/description ILIKE `%từ-khóa%` | Giữ hai index cho hai nhánh OR của search |
| GIN tsvector | Index title full-text baseline | Khác trigram; rà soát việc sử dụng trước khi đề xuất bỏ |
| UNIQUE | Cart/product, email, username, mã tham chiếu | Vừa là cấu trúc truy cập vừa thực thi ràng buộc |
| INCLUDE | Chỉ cân nhắc cho truy vấn đọc cột hẹp | Không tự đưa text dài hoặc cột cập nhật liên tục vào index |
| BRIN | Có thể nghiên cứu với log rất lớn, thời gian tương quan thứ tự lưu | Chưa chọn trong bản kế hoạch cơ sở |
| Hash index PostgreSQL | Equality đơn thuần | Chưa có lý do thay B-tree hiện hữu |

**Partition HASH không đồng nghĩa Hash index.** Partition chọn bảng con; B-tree/GIN
trong bảng con phục vụ tìm dòng. Không coi phân vùng là thay thế indexing.

Minh họa logic index catalogue hiện có:

```text
B-tree: (category_id, created_at DESC)
  category 1 → mới nhất → cũ hơn → ...
  category 2 → mới nhất → cũ hơn → ...
  khóa index → vị trí phiên bản dòng dữ liệu PostgreSQL
  chỉ chứa product có status=1 và is_deleted=false
```

Với B-tree nhiều cột trên PostgreSQL 16, điều kiện trên cột đầu có ảnh hưởng lớn đến
phạm vi phải quét. `(category_id, created_at)` không tự tạo thứ tự created_at chung
cho toàn bộ category. [Tài liệu multicolumn indexes](https://www.postgresql.org/docs/16/indexes-multicolumn.html).

Partial index chỉ phù hợp khi planner chứng minh điều kiện truy vấn bao hàm predicate.
Cần kiểm cả SQL tham số do ORM/driver phát ra; không mặc định generic prepared plan biết
`status = $1` luôn bằng 1. [Tài liệu partial indexes](https://www.postgresql.org/docs/16/indexes-partial.html).

PK/UNIQUE tạo index hỗ trợ; FK ở phía tham chiếu không tự có index. Vì vậy không tạo
thêm index trùng PK, nhưng phải rà soát FK theo workload. [Tài liệu constraints](https://www.postgresql.org/docs/16/ddl-constraints.html).

## 4. Kiểm kê index PostgreSQL sau migration

Tất cả các bảng dưới đây có PK theo DDL/runner. Bảng liệt kê khóa chính và index phụ
quan trọng; tên UNIQUE tự sinh cần kiểm bằng catalog, không suy tên sau rename.
`BT` = B-tree; `ND` = predicate `is_deleted=false`.

| Bảng logic | PK/UNIQUE cần giữ | Index phụ đang được khai báo / cách xử lý |
|---|---|---|
| user_core | PK user_id; UNIQUE username/email | Partial UNIQUE username/email ND; BT created_at, is_active ND, email_verified ND; rà soát chồng lặp |
| user_profile | PK user_id, cũng là FK tới core | Chưa có index avatar_url; ứng viên cleanup I05 |
| user_secret | PK user_id; UNIQUE random_key | Chưa có index password_reset_token; chỉ cân nhắc I13 nếu luồng token có tải |
| user_wallet | PK user_id | Không thêm index balance cho cập nhật ví theo user_id |
| user_role | PK (user_id,role_id) | Chưa có role_id đứng đầu; ứng viên I12 |
| role | PK role_id; UNIQUE role_name | BT role_name ND, created_at; bảng rất nhỏ, rà soát dư thừa |
| category | PK category_id; UNIQUE name | Partial UNIQUE name ND; BT parent_id ND, is_active ND, created_at |
| product | PK product_id | BT seller/category/status/price/created_at ND; GIN tsvector title; ba index catalogue/trigram từ 001 |
| product_image | PK image_id | BT product_id; chưa có image_url/khóa thứ tự ảnh, ứng viên I04/I06 |
| voucher | PK voucher_id; UNIQUE code | Partial UNIQUE code khi active; BT valid_to active, created_at |
| payment_method | PK payment_method_id; UNIQUE method_name | Chưa cần thêm vì bảng seed có 5 dòng |
| contact_info | PK contact_id | BT user_id; BT is_default ND; không index PII chỉ vì cột tồn tại |
| order | PK order_id trên parent HASH | BT buyer/status/date ND; buyer/date ND từ 001 được clone xuống children |
| order_detail | PK order_detail_id | BT order_id; BT (product_id,order_id) từ 001 |
| transaction | PK transaction_id; UNIQUE reference_number | BT order_id, user_id, transaction_status, fraud_score |
| shopping_cart | PK cart_id; UNIQUE user_id | UNIQUE user_id đã phục vụ tìm giỏ của user |
| shopping_cart_item | PK cart_item_id; UNIQUE (cart_id,product_id) | BT cart_id, product_id; rà soát index cart_id với prefix của UNIQUE |
| review | PK review_id | BT product_id, buyer_id, rating; chưa thêm lại index review bị loại ở benchmark cũ |
| system_log | PK (log_id,created_at) | BT user_id/action/created_at trên cây partition; ứng viên audit I14 |
| violation_log | PK log_id | BT user_id, created_at |
| system_feedback | PK feedback_id | BT user_id, status, created_at |
| etl_time_origin | PK (source_table,source_key,field_name) | Equality JSONB source_key được phục vụ bằng BT của PK; chưa cần GIN |
| etl_outbox | PK event_id | BT (available_at,event_id), partial pending/dead; ứng viên I10/I11 |
| etl_runs | PK run_id UUID | Chưa có started_at/ended_at index; ứng viên I08/I09 |
| etl_state | PK name | Truy cập theo name; chưa cần thêm |
| report_daily_sales | PK (report_date,seller_id,category_id) | Prefix report_date đã phục vụ khoảng ngày/năm |
| media_deletions | PK deletion_id; UNIQUE url_path | BT (available_at,deletion_id), partial pending |
| schema_migrations | PK version | Bảng nhỏ do runner tạo; chưa cần index applied_at/checksum |

### 4.1. Rà soát FK chưa được bao phủ đầy đủ

| Đường truy cập | Hiện trạng | Hướng xử lý |
|---|---|---|
| order.voucher_id | Chưa có index; trigger ETL tìm mọi order có voucher | I07 ưu tiên đo khi số order lớn |
| order.contact_id/payment_method_id | Chưa có index phụ | Chỉ thêm khi kiểm FK/delete/update parent hoặc query thực tế tốn chi phí |
| order.buyer_id | Index hiện tại partial ND | Đủ cho lịch sử đang hoạt động; không bao phủ mọi dòng deleted khi kiểm FK |
| product.category_id/seller_id | Index hiện tại partial ND | Query không có predicate ND có thể không dùng được; xem cả has_products và soft-delete category |
| product.approved_by | Chưa có index | Chưa có truy vấn nóng theo người duyệt được xác nhận |
| user_role.role_id | Nằm cột thứ hai trong PK | I12 cho liệt kê theo role khi dữ liệu tăng |
| transaction.payment_method_id | Chưa có index | Cân nhắc theo truy vấn/chi phí FK, không thêm vì bảng lookup có FK đơn thuần |

Không kết luận mọi FK thiếu index đều là lỗi. Ưu tiên theo số dòng con, tần suất truy vấn
và hành vi sửa/xóa bảng cha; partial index phải được phân biệt với index toàn bộ FK.

## 5. Ma trận truy vấn → index

| Mã | Nguồn truy vấn | Predicate / JOIN / ORDER BY | Thiết kế sử dụng |
|---|---|---|---|
| Q01 | CRUDProduct.catalogue | category tùy chọn, status=1, ND; category đang active; created_at DESC, product_id ASC | Giữ catalogue hiện tại, đo I01/I02 |
| Q02 | Catalogue theo giá | Predicate visible; price ASC, product_id ASC | BT price ND hiện tại; I03 nếu category+price có tải |
| Q03 | Search sản phẩm | title ILIKE OR description ILIKE, visible | Hai GIN trigram partial |
| Q04 | Detail / giữ chỗ cart | product_id equality, có FOR UPDATE khi giữ chỗ | PK product; index không thay thế khóa dòng/giao dịch |
| Q05 | Ảnh sản phẩm ETL | product_id equality; display_order,image_id ASC | BT product_id; I06 khi nhiều ảnh/sản phẩm |
| Q06 | Lịch sử buyer | buyer_id equality, ND; order_date DESC | Buyer/date trên các partition; không hash-prune theo buyer |
| Q07 | Đơn seller | product.seller_id → detail.product_id → order_id; date DESC | Seller ND + detail(product_id,order_id) + order PK |
| Q08 | Cart item | cart_id/product_id equality | UNIQUE uq_cart_product |
| Q09 | Login | email hoặc username equality; join các mảnh user theo user_id | UNIQUE trên core và PK các mảnh |
| Q10 | Dùng lại đơn PayPal | buyer_id, payment_method_id, status=0, ND; date DESC LIMIT 1 | Buyer/date trước; composite riêng chỉ khi đo cho thấy lọc dư lớn |
| Q11 | Snapshot order ETL | detail.order_id; transaction.order_id | BT order_id ở hai bảng; sort ngắn nếu ít item/payment |
| Q12 | Poll outbox | pending/dead; available_at <= clock_timestamp(); ORDER BY event_id | Đo index sẵn có với I11 và ảnh hưởng volatility |
| Q13 | Retry full error | entity_type + entity_key JSONB equality, status<>done; event_id LIMIT 1 | I10; không GIN cho equality toàn JSONB này |
| Q14 | CLI status / dashboard report time | etl_runs.started_at DESC; hoặc success+aggregate rồi ended_at DESC | I08/I09 |
| Q15 | Cleanup reference | image_url/avatar_url equality; Mongo deleted=false + images.key | I04/I05 và ứng viên Mongo M01 |
| Q16 | Audit trail | resource_type/resource_id equality; created_at DESC LIMIT | I14 trên partition log nếu dùng thường xuyên |
| Q17 | Voucher thay đổi | Trigger SELECT order_id WHERE voucher_id=... không lọc deleted | I07 index toàn phần |
| Q18 | Report theo năm | report_date range, GROUP BY ngày | PK report_date prefix, không thêm BT report_date trùng |

`sort_by=rating` của catalogue hiện sắp theo **view_count DESC**, chưa phải điểm review
trung bình. Không thiết kế index trên một cột `rating` không tồn tại trong product.
Index cho view_count cần cân nhắc riêng vì mỗi lượt đọc detail lại cập nhật bộ đếm này.

## 6. Thiết kế cơ sở: giữ các index đã có bằng chứng

### 6.1. Catalogue theo danh mục

```sql
-- ĐÃ CÓ trong migration 001, không chạy lại để tạo trùng.
CREATE INDEX idx_product_catalogue
ON product (category_id, created_at DESC)
WHERE status = 1 AND is_deleted = FALSE;
```

Predicate nằm trong product; điều kiện category active/ND vẫn được kiểm qua JOIN.
Index không chứa kết quả JOIN category. Index này hỗ trợ category+date, chưa bao phủ
đầy đủ khóa phá hòa product_id ASC của catalogue hiện tại; xem I01.

### 6.2. Search chuỗi con

```sql
-- ĐÃ CÓ trong migration 001.
CREATE INDEX idx_product_title_trgm
ON product USING gin (title gin_trgm_ops)
WHERE status = 1 AND is_deleted = FALSE;
CREATE INDEX idx_product_description_trgm
ON product USING gin (description gin_trgm_ops)
WHERE status = 1 AND is_deleted = FALSE;
```

GIN tổ chức khóa trigram và các tham chiếu tới dòng phù hợp. Planner có thể BitmapOr
hai nhánh search; không bảo đảm mọi input dùng index, đặc biệt mẫu quá ngắn hoặc ít chọn lọc.
[Tài liệu pg_trgm](https://www.postgresql.org/docs/16/pgtrgm.html).

Index `idx_product_title` baseline dùng `to_tsvector('english', title)`: cần truy vấn
full-text tương ứng mới có lợi; nó không phục vụ trực tiếp ILIKE như hai trigram index.
Backend/SQL functions đã đọc chưa thấy dùng `@@`; kiểm thêm consumer ngoài app trước
khi đề xuất thu hồi. Không đồng nhất tsvector tiếng Anh với tìm chuỗi tiếng Việt không dấu.

### 6.3. Buyer, seller, cart và định danh

- Giữ buyer/date ND; lookup order_id dùng PK và prune một hash partition.
- Giữ detail(order_id) vì `(product_id,order_id)` không thay thế đường tra theo order_id.
- Giữ detail(product_id,order_id) cho seller và fan-out ETL khi product thay đổi.
- Giữ UNIQUE cart/product để chống dòng trùng. Khóa dòng product và transaction vẫn cần
  để giữ chỗ tồn kho; index không tự xử lý toàn bộ race condition.
- Giữ PK/UNIQUE identity, mã voucher, mã giao dịch, user wallet; không thêm UNIQUE mới
  lên transaction.order_id/provider_transaction_id khi nghiệp vụ chưa quyết định miền duy nhất.

### 6.4. Cấu trúc ETL sẵn có

- `etl_time_origin` dùng khóa ghép có equality source_table/source_key, rồi field_name;
  phù hợp truy vấn provenance hiện tại, không cần index riêng trên từng thành phần.
- `report_daily_sales` dùng ngày làm prefix PK, phù hợp dashboard lọc một năm.
- Queue dùng partial index để tập trung dòng chưa hoàn tất. Việc chuyển pending/dead/done
  làm thay đổi thành viên index, cần đo chi phí ghi và vacuum khi lịch sử tăng.

## 7. Các ứng viên thiết kế bổ sung

**P1:** đo trước vì đường vận hành quan trọng hoặc khoảng trống rõ. **P2:** đo theo tải
thực tế. **P3:** chỉ mở khi có query/tập dữ liệu đủ lớn. P1 không có nghĩa tự động triển
khai. Mỗi ứng viên có thể bị loại sau benchmark.

### 7.1. I01–I03: thứ tự catalogue và giá

| Mã | Ưu tiên | Cấu trúc đề xuất | Khi chọn / rủi ro |
|---|---|---|---|
| I01 | P2 | product(category_id,created_at DESC,product_id ASC), partial visible | Category+date có nhiều dòng trùng thời gian; nếu chọn, đánh giá thay index catalogue hai cột |
| I02 | P2 | product(created_at DESC,product_id ASC), partial visible | Trang đầu/all-category dùng mới nhất; đo cạnh index created_at ND hiện tại |
| I03 | P2 | product(category_id,price ASC,product_id ASC), partial visible | Category+giá phổ biến; không tự phục vụ price sort toàn category |

```sql
-- ỨNG VIÊN: chỉ tạo trên database benchmark trước.
CREATE INDEX idx_product_catalogue_order_v2
ON product (category_id, created_at DESC, product_id ASC)
WHERE status = 1 AND is_deleted = FALSE;

CREATE INDEX idx_product_visible_date_id
ON product (created_at DESC, product_id ASC)
WHERE status = 1 AND is_deleted = FALSE;

CREATE INDEX idx_product_visible_category_price_id
ON product (category_id, price ASC, product_id ASC)
WHERE status = 1 AND is_deleted = FALSE;
```

Không triển khai cả ba mặc định. Cần đo cùng SQL JOIN category, seller exclusion,
product_ids từ Mongo, OFFSET/LIMIT và tải cập nhật thực. Nếu thêm keyset pagination sau
này, `(created_at DESC,product_id ASC)` có chiều trộn: điều kiện trang kế tiếp phải khớp
thứ tự, không thay tuple comparison tùy ý. Đó là thay đổi API riêng, chưa nằm trong DDL này.

### 7.2. I04–I06: metadata ảnh và cleanup

| Mã | Ưu tiên | Cấu trúc đề xuất | Điều kiện chọn |
|---|---|---|---|
| I04 | P1 | product_image(image_url), BT toàn phần, KHÔNG UNIQUE | EXISTS image_url trong cleanup; phải hỗ trợ key được nhiều product dùng chung |
| I05 | P2 | user_profile(avatar_url), BT toàn phần | Avatar reference check thực sự tốn chi phí khi user tăng |
| I06 | P3 | product_image(product_id,display_order,image_id) | Mỗi product có nhiều ảnh hoặc ETL sort ảnh trở thành nút thắt |

```sql
-- ỨNG VIÊN; image_url không được đặt UNIQUE.
CREATE INDEX idx_product_image_url ON product_image (image_url);
CREATE INDEX idx_user_profile_avatar_url ON user_profile (avatar_url);
CREATE INDEX idx_product_image_display
ON product_image (product_id, display_order, image_id);
```

Bộ seed tái sử dụng 32 URL trên 2.000 dòng nên UNIQUE image_url sẽ phá dữ liệu hợp lệ.
Cleanup còn kiểm bản sao Mongo và backlog; index PG chỉ tối ưu phần tra cứu, không thay
quy tắc chờ đồng bộ trước khi xóa file. I06 không tự làm thumbnail/network nhanh hơn;
đo trước khi giữ thêm index cạnh product_id hiện tại.

### 7.3. I07: fan-out voucher sang order

```sql
-- I07, P2; tăng lên P1 nếu fan-out voucher đã được đo là chậm.
CREATE INDEX idx_order_voucher_lookup ON "order" (voucher_id);
```

Trigger trong migration 005 tìm order theo voucher_id mà không lọc is_deleted. Chọn
index toàn phần để bao phủ đúng tập dòng; partial ND không đủ cho truy vấn gồm cả
order đã xóa mềm, nên planner không thể dùng nó làm nguồn đầy đủ cho truy vấn này.
Index được tạo qua parent và triển khai trên bốn partition; voucher_id không hash-prune.
Đo cả trường hợp voucher không tồn tại trong order, phổ biến và có nhiều đơn liên quan.
Index giảm chi phí tìm ID; không loại bỏ số event cần tạo hoặc N+1 của pipeline.

### 7.4. I08–I10: truy vấn vận hành ETL

```sql
-- I08, P1: status() đọc run mới nhất.
CREATE INDEX idx_etl_runs_started ON etl_runs (started_at DESC);

-- I09, P1: sales_report.read() tìm lần aggregate thành công mới nhất.
CREATE INDEX idx_etl_runs_aggregate_success ON etl_runs (ended_at DESC)
WHERE status = 'success' AND details ? 'aggregate';

-- I10, P2: retry_full_error() tìm event chưa ACK của cùng entity.
CREATE INDEX idx_etl_outbox_entity_pending
ON etl_outbox (entity_type, entity_key, event_id)
WHERE status <> 'done';
```

`entity_key` là JSONB nhưng truy vấn so equality toàn object; B-tree ghép phù hợp dạng
so sánh đó. Không thêm GIN toàn bộ JSONB chỉ vì kiểu dữ liệu là JSONB. Kiểm kích thước
key và phân bố theo entity; key hiện chứa ID hoặc ID/thời gian log, không chứa cả document.

Không cần GIN `etl_runs.details` để lấy một run mới nhất khi I09 có predicate cụ thể.
Mỗi chu kỳ ETL sinh thêm run nên cần đo trên lịch sử nhiều ngày, không chỉ vài dòng.
I10 có thêm chi phí mỗi lần event đổi trạng thái; nếu đường retry hiếm, có thể không giữ.

### 7.5. I11: thiết kế poll queue phải khớp thứ tự và thời gian

Hiện tại:

```text
index: (available_at, event_id) WHERE status IN ('pending','dead')
query: available_at <= clock_timestamp(), ORDER BY event_id, LIMIT batch
```

Có hai điểm cần kiểm:

1. Range theo available_at đứng trước event_id không bảo đảm thứ tự event_id chung mà
   query yêu cầu; có thể cần Sort hoặc planner chọn đường PK.
2. `clock_timestamp()` là VOLATILE, không được coi như một mốc thời gian ổn định cho
   Index Cond. Xem plan thật, không mặc định index available_at đã chặn được range.
   [Tài liệu function volatility](https://www.postgresql.org/docs/16/xfunc-volatility.html).

**I11, P1 — so sánh thiết kế trên benchmark**, chưa chọn thay thế ngay:

```sql
-- ỨNG VIÊN ưu tiên thứ tự event; available_at là điều kiện kiểm thêm.
CREATE INDEX idx_etl_outbox_pending_event
ON etl_outbox (event_id, available_at)
WHERE status IN ('pending', 'dead');
```

So sánh bốn cấu hình: index hiện tại/query hiện tại; I11/query hiện tại; index hiện tại
với mốc `statement_timestamp()`; I11 với mốc `statement_timestamp()`.
Thay clock_timestamp bằng statement_timestamp là thay đổi code/ngữ nghĩa thời gian
trong một statement, phải review riêng; không sửa worker chỉ để đạt một plan đẹp.
Không đổi ORDER BY sang available_at nếu chưa đánh giá thứ tự xử lý/fairness.

Mô phỏng phần lớn event done, một phần pending, một phần deferred/retry nằm ở tương
lai. Đo event phải bỏ qua, Sort, buffer, thời gian claim batch và độ trễ event. Queue
media_deletions có cùng cặp khóa/thời gian; thực hiện phép so sánh tương tự khi queue
xóa có tải, không tự thêm index thứ hai cho queue chỉ vài dòng.

Không tạo partial index có predicate `available_at <= now()`/`clock_timestamp()`:
đó là điều kiện thay đổi theo thời gian, không phải predicate cố định hợp lệ cho thiết
kế này. Predicate index chỉ dùng trạng thái; mốc due-time nằm ở query.

### 7.6. I12–I14: role, token và audit

```sql
-- I12, P2: liệt kê user theo role, đảo prefix của PK hiện tại.
CREATE INDEX idx_user_role_role_user ON user_role (role_id, user_id);

-- I13, P3: chỉ cho luồng reset_password(token) nếu vẫn sử dụng và có tải.
CREATE INDEX idx_user_secret_reset_token ON user_secret (password_reset_token)
WHERE password_reset_token IS NOT NULL;

-- I14, P2: truy vấn SQL helper get_audit_trail().
CREATE INDEX idx_system_log_resource_date
ON system_log (resource_type, resource_id, created_at DESC);
```

I13 không UNIQUE: cùng cột đang chứa cả OTP 6 chữ số và token reset; OTP giữa hai user
có thể giống nhau. Không dùng index để tự áp một ràng buộc nghiệp vụ chưa có. Luồng
OTP theo email đã lookup user_core bằng UNIQUE email rồi lấy secret theo PK user_id.
Không index password_hash, không đưa token thật vào log benchmark.

I14 triển khai theo cây partition. Vì helper không lọc khoảng ngày, vẫn có thể đọc nhiều
partition; muốn prune thêm cần thay đổi hợp đồng query có biên thời gian. Dữ liệu audit
rộng theo tháng có thể Seq Scan hợp lý. Không thêm BRIN hoặc đổi khóa log trong bước này.

## 8. Index MongoDB và đường tra file

### 8.1. Cấu trúc hiện tại cần giữ/đối chiếu

Nguồn: [mongo_schema.py](../backend/app/services/mongo_schema.py),
[init_mongo.py](../backend/scripts/init_mongo.py), [etl/errors.py](../backend/etl/errors.py).
Mongo có index `_id` mặc định; bảng dưới liệt kê index ứng dụng ngoài `_id`.

| Collection | Index được khai báo | Mục đích / giới hạn |
|---|---|---|
| product_details | UNIQUE product_id; (category_id,attributes.brand); attributes.$**; text(description,tags) | Detail theo ID, thuộc tính động; text index không tự phục vụ API đang dùng equality |
| reviews | UNIQUE review_id; (product_id,created_at DESC); partial (type,status) cho report/pending | Read model review/report, không thay index PG của endpoint đang đọc PG |
| order_snapshots | UNIQUE order_id; (buyer.id,order_date DESC); (order_status,order_date DESC) | Snapshot/analytics; không chuyển giao dịch order sang Mongo |
| system_logs | UNIQUE (log_id,created_at); created_at TTL 90 ngày; (action,actor_id,created_at DESC) | Danh tính ghép, tra log, retention bản sao |
| violation_logs | UNIQUE log_id; (target_user_id,created_at DESC) | Nhật ký vi phạm theo user, không TTL tự động |
| contact_messages | UNIQUE feedback_id; (status,created_at DESC) | Hàng đợi xử lý contact metadata |
| etl_errors | (resolved,last_at ASC) | Theo dõi lỗi unresolved; _id giữ định danh event |

Không thêm UNIQUE `(product_id,category_id)` để thay UNIQUE product_id: identity của
sản phẩm phải duy nhất toàn collection, kể cả khi chuyển category.

### 8.2. M01 — tra tham chiếu ảnh còn sống, P1 đo cùng I04

```javascript
// ỨNG VIÊN: tạo trên collection benchmark trước.
db.product_details.createIndex(
  {"images.key": 1},
  {name: "idx_live_product_image_key", partialFilterExpression: {deleted: false}}
)
```

`images` là mảng nên đây là multikey index. Predicate khớp query cleanup hiện tại
`{deleted:false,"images.key":path}`. Không UNIQUE vì seed dùng lại ảnh giữa product.
Đo cả key còn nhiều tham chiếu, key một tham chiếu và key không còn tồn tại.

### 8.3. M02 — targeted attribute index theo truy vấn phổ biến, P2

`matching_ids()` hiện lọc `deleted:false` và AND các thuộc tính, không luôn đưa category_id
vào truy vấn Mongo. Vì vậy index category+brand hiện có không mặc định là lựa chọn tối
ưu cho mọi lần lọc brand. Giữ wildcard để hỗ trợ tên thuộc tính thay đổi, đồng thời đo
compound cụ thể khi một nhóm filter được dùng thường xuyên, ví dụ:

```javascript
// ỨNG VIÊN cho filter brand + ram_gb, không áp dụng cho mọi category/filter.
db.product_details.createIndex(
  {"attributes.brand": 1, "attributes.ram_gb": 1, product_id: 1},
  {name: "idx_live_product_brand_ram", partialFilterExpression: {deleted: false}}
)
```

Đo trên Mongo **8.0.32** đang dùng, có document chứa metadata thực; seed SQL không tự
điền brand/RAM. Không tạo compound cho mọi tổ hợp thuộc tính. Wildcard hỗ trợ trường
không cố định nhưng không bảo đảm tối ưu mọi AND/filter/sort hoặc covered query.
[Tài liệu wildcard index MongoDB 8.0](https://www.mongodb.com/docs/v8.0/core/indexes/index-types/index-wildcard/).

Index mới không loại bỏ giới hạn 5.000 candidate, bước kiểm visibility/sort/page ở PG
hoặc độ trễ eventual consistency của metadata.

### 8.4. MinIO và metadata

Không có `CREATE INDEX` SQL cho bucket. Thiết kế đường truy cập:

```text
PG product_id → product_image → image_url → bucket + object key → MinIO GET/STAT
Mongo images[].bucket/key → tham chiếu cùng object
```

Giữ key bất biến `products/{id}/{uuid}.ext`, `users/{id}/avatar-{uuid}.ext`, và alias seed
đang được tham chiếu. Không đổi tên file hàng loạt để giả lập index. Catalogue không
nên list toàn bucket để tìm ảnh; metadata nằm ở PG/Mongo, truy cập object theo key.

2.000 tham chiếu chỉ có 32 URL seed khác nhau là trường hợp phải đo riêng: có thể giảm
STAT lặp bằng cache/deduplicate trong một lượt kiểm ảnh nếu còn nút thắt. Đó là tối ưu
pipeline riêng, không phải lợi ích của một B-tree mới và không làm mất kiểm chứng mỗi
tham chiếu theo image_id.

## 9. Kế hoạch kiểm soát index chồng lặp và chi phí ghi

### 9.1. Danh sách cần rà soát, chưa quyết định DROP

| Nhóm | Vì sao cần xem lại? | Điều kiện trước khi bỏ |
|---|---|---|
| Partial UNIQUE username/email ND | Đã có UNIQUE toàn phần trên cùng cột | Global UNIQUE vẫn giữ nghiệp vụ; đo kích thước/usage và plan trước khi bỏ partial |
| Partial UNIQUE category.name ND, voucher.code active | Đã có UNIQUE toàn phần | Không đổi khả năng tái sử dụng tên/mã sau soft delete |
| role_name ND BT | Đã có UNIQUE role_name, bảng nhỏ | Kiểm consumer/plan, không tự xóa constraint |
| shopping_cart_item(cart_id) | UNIQUE(cart_id,product_id) có prefix cart_id | Đo lookup/load giỏ và chi phí index rộng; không drop UNIQUE |
| order buyer ND đơn cột | Buyer/date ND có cùng prefix/predicate | Đánh giá index trên mọi partition, kích thước và plan FK/query thực |
| idx_product_title GIN tsvector | Chưa thấy consumer full-text trong mã đã đọc | Kiểm SQL ngoài ứng dụng và usage đủ chu kỳ |
| product(category_id) ND | Có catalogue category/date nhưng predicate khác | Không xem là bản trùng: moderation và all-status cần tập dòng rộng hơn |
| Index boolean/status | Có thể ít chọn lọc | Đo trạng thái hiếm và count/moderation, không bỏ chỉ vì cardinality thấp |
| Index date đơn cột và candidate compound | Có thể cùng phục vụ ORDER BY nhưng predicate/chiều khác | Đo các query không được ứng viên mới bao phủ |

Global UNIQUE hiện chặn trùng cả dòng đã xóa mềm. Nếu muốn cho phép tái dùng email,
username, tên category hoặc voucher code, đó là thay đổi nghiệp vụ/constraint riêng;
không được lẫn với tối ưu dung lượng index.

Không dùng `idx_scan=0` trong vài phút để quyết định xóa: số liệu có thể vừa reset,
workload theo mùa chưa xuất hiện hoặc index phục vụ integrity thay vì SELECT thường.

### 9.2. Tính chi phí trên product và ETL

GET detail cập nhật view_count; cart cập nhật quantity; moderation đổi status; mỗi thay
đổi còn có trigger tạo event/fan-out. Vì vậy cần đo:

- Chi phí tăng view_count, giữ chỗ/restock, tạo product và duyệt/ẩn product.
- GIN khi sửa title/description, chuyển trạng thái vào/ra partial index.
- Số index entry/WAL/dead tuple, kích thước tổng, vacuum và HOT update.
- Số event phát sinh và backlog/latency worker, không chỉ thời gian SELECT.

Không đưa view_count/quantity vào khóa hoặc INCLUDE theo mặc định. Khi cột được cập
nhật thuộc index, khả năng HOT có thể giảm; HOT còn phụ thuộc chỗ trống trên page.
[Tài liệu HOT](https://www.postgresql.org/docs/16/storage-hot.html).

Index Only Scan không được hứa chỉ vì đủ cột: vẫn phụ thuộc visibility map và mức cập
nhật. Chỉ thử INCLUDE trên projection nhỏ sau khi đo heap fetch; không INCLUDE mô tả
hay URL dài vào nhiều index để đạt một ví dụ SELECT được cover.

## 10. Lộ trình thực hiện và đầu ra

Lộ trình thiết kế ban đầu được giữ để đối chiếu. Kết quả thực hiện A–D/F nằm trong báo cáo; bước E chỉ lập danh sách theo dõi, chưa DROP index cũ vì thiếu usage thực tế.

| Giai đoạn | Công việc | Đầu ra | Điều kiện chuyển bước |
|---|---|---|---|
| A — inventory | Xác nhận version/schema, liệt kê catalog index/constraint, SQL ORM/ETL, thống kê usage | Inventory có nguồn, query Q01–Q18 và distribution | Không nhầm baseline với schema sau 006; xác định query có/không predicate |
| B — baseline | Đo S/L bằng schema hiện có, warmup, đọc/ghi/queue riêng | Before plans, latency, buffers, bytes và môi trường | Kết quả tái lập được; không dùng thời gian ngẫu nhiên làm bằng chứng |
| C — vận hành | Đo I04, I08/I09, thiết kế queue I11; M01 nếu cleanup có tải | Bảng so sánh từng ứng viên | Chỉ giữ ứng viên có lợi cho workload mục tiêu và không phá integrity |
| D — nghiệp vụ | Đo I01–I03, I07, I10/I12/I14 theo tần suất; P3 chỉ khi cần | Danh sách chọn/loại và lý do | Không triển khai cả danh sách DDL một lượt |
| E — tinh gọn | Đánh giá index chồng lặp sau khi lựa chọn mới ổn định | Danh sách DROP được chứng minh an toàn | Kiểm dependency/constraint, đủ chu kỳ query và có phương án phục hồi |
| F — rollout | Migration mới, thời gian bảo trì, kiểm trước/sau và giám sát | Version/checksum mới, evidence và kế hoạch rollback | Test sạch + ứng dụng/ETL đạt; không sửa 001–006 |

**Gói lựa chọn ban đầu để đo, không phải migration mặc định:** I04 + I08/I09, phép so
sánh I11 và M01 nếu cleanup thực sự dùng Mongo. Sau đó mới xét catalogue ba cột hoặc
FK voucher theo số liệu. Giữ các index cơ sở từ 001 trong giai đoạn thu thập baseline.

Đề xuất tổ chức đầu ra khi triển khai thật:

```text
docs/benchmark/indexing_v2/<ngay-do>/
  environment.json
  inventory.csv
  workload.md
  before/
  after/
  summary.csv
  decisions.md

database/04_migrations/<version_moi>_indexing_v2.sql
```

Đã tạo `007_indexing_v2.sql` theo tập index được chọn sau đo; không sửa 001–006. Các đường dẫn output thực tế được liệt kê trong báo cáo ngày 01/11/2026.

## 11. Kế hoạch benchmark và tiêu chí chọn index

### 11.1. Thiết kế thí nghiệm

1. Dùng DB benchmark riêng đã khởi tạo/migrate, lưu phiên bản PG, Mongo, commit,
   CPU/RAM, cấu hình container, collation, múi giờ, số dòng và thống kê phân bố.
2. Cố định dữ liệu và query parameter giữa before/after. Đo SQL đơn giản để hiểu plan,
   rồi đo SQL thật do ORM phát ra, kể cả eager-load ảnh/review và LIMIT/OFFSET.
3. Warmup, chạy ít nhất năm lượt SELECT cho median/min/max. Muốn báo p95 phải có đủ
   mẫu request/transaction, đề xuất ít nhất 100 lần mỗi scenario; không lấy p95 của năm lần.
4. So từng index/nhóm có lý do chung. Không đồng thời đổi query, dữ liệu, cấu hình và
   nhiều index rồi quy mọi cải thiện cho một index.
5. Sau khi tạo index/đổi dữ liệu benchmark, ANALYZE phù hợp và lưu raw plan JSON/text.
   Không tắt seqscan, không hint để tạo kết quả thắng giả.
6. Với DML/queue, dùng môi trường riêng vì EXPLAIN ANALYZE thực thi thật. Giữ cùng số
   worker/concurrency và cùng thứ tự truy vấn; không tăng worker chỉ để giảm backlog.
7. Chạy lại functional regression có ý nghĩa: unique cart, self-buy, stock, user split,
   full/replay ETL, cleanup ảnh dùng chung, orphan/FK, và API catalogue/attribute filter.

### 11.2. Phân bố bắt buộc

| Workload | Các trường hợp cần có |
|---|---|
| Catalogue | Category lớn/nhỏ, không category, cùng created_at nhiều dòng, giá trùng, skip nhỏ/lớn, seller exclusion |
| Search | Từ dài/hiếm/phổ biến, chuỗi 1–2 ký tự, tiếng Việt có dấu; title OR description |
| Seller/buyer | Một user ít/nhiều đơn, một đơn nhiều seller, có dòng deleted |
| Ảnh | URL dùng chung nhiều product, URL riêng và URL không tồn tại |
| Queue | Nhiều done; pending ít/nhiều; retry deferred; backlog lớn; claim batch không đọc nhầm event tương lai |
| ETL runs | Lịch sử nhiều ngày; success/partial/failed; run đang chạy; aggregate cũ/mới |
| Mongo | Metadata thay đổi theo category, brand phổ biến/hiếm, nhiều điều kiện, soft delete, array images |
| Ghi | Xem detail, thêm giỏ, cập nhật trạng thái, sửa mô tả, insert/log/outbox; có contention ở cùng product |

Không suy ra hiệu quả BRIN từ seed có thời gian sinh theo công thức đảo ngày; cần đo
correlation vật lý thực và tải log append của môi trường đại diện.

### 11.3. Số đo và ngưỡng nghiệm thu dự kiến

Các ngưỡng sau là **tiêu chí đề xuất để chốt trước lần đo**, chưa phải kết quả hay SLA:

| Tiêu chí | Điều kiện xem xét đạt |
|---|---|
| Đúng kết quả | Tập ID/thứ tự/tiền và ràng buộc không thay đổi; predicate không loại nhầm dòng |
| Đọc | Với query đủ tốn chi phí, mục tiêu giảm median/p95 khoảng 20% hoặc giảm rõ IO/rows examined; query vốn dưới 1 ms cần nhìn cả biến thiên/chi phí ghi |
| Ghi | Không chấp nhận suy giảm đáng kể mà chưa được đánh đổi rõ; mức rà soát ban đầu là >10% latency/throughput so baseline |
| Dung lượng | Ghi số byte tăng/giảm theo từng index và tổng; phải đủ disk/WAL cho rollout, không mặc định thêm index luôn rẻ |
| Queue | Không xử lý event chưa due, giữ retry/ACK, giảm chi phí claim hoặc latency ở cùng tải; theo dõi mục tiêu đồng bộ dưới 5 phút của kế hoạch |
| Toàn hệ | Functional checks đạt; PG/Mongo/MinIO đối soát đúng; không chỉ một EXPLAIN thắng |

Constraint/UNIQUE có thể được giữ dù không tăng tốc SELECT vì đảm bảo nghiệp vụ.
Một ứng viên không đạt có thể bị loại; không tạo migration chỉ để khớp danh sách dự kiến.

### 11.4. Bằng chứng cũ chỉ dùng làm baseline tham khảo

[Benchmark Ngày 4](benchmark/README.md) đã ghi PG 50.016 product/100.030 order, search
316,562 → 0,372 ms, seller order 44,052 → 17,521 ms; cũng ghi query review/cart/pruning
không nhanh hơn và index vật lý tăng 35.225.600 → 58.736.640 byte.
Đây là phép đo lịch sử trên môi trường riêng; không chuyển thành cam kết hiện tại.

Mongo benchmark cũ chạy 7.0.43; môi trường người dùng là 8.0.32 nên phải lưu phiên bản
mới khi đo lại. Không đổi nhãn các JSON cũ thành Mongo 8. Dữ liệu seed mới 1.000 product
khác workload lớn cũ nên không so thời gian hai bộ trực tiếp để kết luận regression.

## 12. Truy vấn khảo sát và EXPLAIN mẫu

Các SELECT khảo sát có thể chạy bằng pgAdmin trên DB đã migrate. Các DDL ứng viên ở
mục 7/8 chỉ chạy trên môi trường benchmark trước; không dán toàn bộ tài liệu để Execute.
Giá trị ID bên dưới là ví dụ theo seed, cần chọn thêm ID từ phân bố thật.

### 12.1. Catalog index, constraint và thống kê

```sql
SELECT t.relname AS table_name, ix.relname AS index_name,
       am.amname AS index_method, ix.relkind AS index_kind,
       i.indisprimary, i.indisunique, i.indisvalid, i.indisready,
       pg_get_expr(i.indpred, i.indrelid) AS predicate,
       pg_get_indexdef(i.indexrelid) AS definition,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS relation_bytes
FROM pg_index i
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_class ix ON ix.oid = i.indexrelid
JOIN pg_am am ON am.oid = ix.relam
WHERE n.nspname = 'public'
ORDER BY t.relname, ix.relname;

SELECT conrelid::regclass AS table_name, conname, contype,
       NULLIF(conindid, 0)::regclass AS supporting_index,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;

SELECT relname, indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes ORDER BY relname, indexrelname;

SELECT datname, stats_reset FROM pg_stat_database WHERE datname = current_database();

SELECT relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd, n_tup_hot_upd,
       last_analyze, last_autoanalyze, last_autovacuum
FROM pg_stat_user_tables ORDER BY relname;

SELECT tablename, attname, null_frac, n_distinct, correlation
FROM pg_stats WHERE schemaname = 'public'
  AND tablename IN ('product','product_image','etl_outbox','etl_runs')
  AND attname IN ('category_id','status','is_deleted','created_at','price',
                 'image_url','available_at','started_at','ended_at');
```

`index_kind='I'` là parent partitioned index, không chứa dữ liệu vật lý như index con
`'i'`. Tổng dung lượng phải cộng các index vật lý phù hợp, tránh coi parent 0 byte là
không có index. Usage/statistics là tích lũy từ thời điểm reset, không phải riêng lượt đo.
FK `supporting_index` trong catalog không tự chứng minh phía bảng con có index tương ứng.

### 12.2. Query đọc đại diện

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT p.product_id, p.title, p.price
FROM product p JOIN category c USING (category_id)
WHERE p.status = 1 AND p.is_deleted = FALSE
  AND c.is_active = TRUE AND c.is_deleted = FALSE
  AND p.category_id = 1
ORDER BY p.created_at DESC, p.product_id ASC LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id FROM product
WHERE status = 1 AND is_deleted = FALSE
  AND (title ILIKE '%laptop%' OR description ILIKE '%laptop%');

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, order_date FROM "order"
WHERE buyer_id = 7 AND is_deleted = FALSE
ORDER BY order_date DESC LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT EXISTS (SELECT 1 FROM product_image
               WHERE image_url = '/media/products/prod_1_1_laptop.jpg');

EXPLAIN (ANALYZE, BUFFERS)
SELECT ended_at FROM etl_runs
WHERE status = 'success' AND details ? 'aggregate'
ORDER BY ended_at DESC LIMIT 1;

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id FROM etl_outbox
WHERE entity_type = 'product' AND entity_key = '{"id":1}'::jsonb
  AND status <> 'done' ORDER BY event_id LIMIT 1;
```

Bổ sung phép đo all-category, price sort và query eager-load thực tế từ ORM; không
suy toàn bộ thời gian API từ các projection hẹp trên đây.

### 12.3. Queue và ghi: chỉ trên DB benchmark

```sql
-- EXPLAIN ANALYZE có FOR UPDATE sẽ lấy khóa; chỉ dùng trên DB benchmark.
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM etl_outbox
WHERE status IN ('pending','dead') AND available_at <= clock_timestamp()
ORDER BY event_id LIMIT 100 FOR UPDATE SKIP LOCKED;
ROLLBACK;

-- Phép đo ghi có trigger thật; rollback không làm biến mất chi phí/WAL đã tạo.
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE product SET view_count = view_count + 1 WHERE product_id = 1;
ROLLBACK;
```

Đo thêm bản statement_timestamp và DML giữ chỗ ở cùng dữ liệu khi xét I11. Index có thể
giúp tìm dòng nhưng không loại bỏ độ trễ do khóa của transaction khác.

### 12.4. Mongo explain

```javascript
// Chọn đúng database trong mongosh/Compass Shell trước.
db.product_details.getIndexes()
db.product_details.find({deleted: false, "images.key": "products/prod_1_1_laptop.jpg"})
  .limit(1).explain("executionStats")
db.product_details.find({deleted: false, "attributes.brand": "Manual7D", "attributes.ram_gb": 16},
  {_id: 0, product_id: 1}).limit(5001).explain("executionStats")
```

Lưu winningPlan, nReturned, totalKeysExamined, totalDocsExamined và thời gian. Metadata
cần có thật trong tập benchmark; trả 0 vì không có brand chưa chứng minh hiệu năng lọc.

## 13. Migration, rollback và giám sát

### 13.1. Triển khai theo runner hiện tại

1. Chốt tập index chọn sau đo; ghi quyết định từng ứng viên giữ/loại, index cũ dự kiến
   thu hồi và query/constraint bị ảnh hưởng.
2. Tạo **version SQL mới**, không sửa 001–006 hoặc baseline_v0.json để vượt checksum.
3. Test migration trên DB sạch và bản sao dữ liệu có deleted/shared URL/retry; kiểm
   index definition, validity, constraint và partition children trước/sau.
4. Theo cơ chế maintenance hiện có, dừng ghi/worker phù hợp; backup và kiểm khả năng
   khôi phục trên DB riêng. Tạo index mới, ANALYZE, đối soát rồi mở dịch vụ.
5. Theo dõi đọc/ghi/ETL trước khi thu hồi index chồng lặp; ưu tiên bước DROP ở version
   sau để có thời gian quan sát, không bỏ index cũ chỉ vì index mới tạo thành công.

Runner bọc mỗi version trong transaction. `CREATE INDEX CONCURRENTLY` không chạy
trong transaction block; không chèn vào runner hiện tại. Nếu cần online build trên bảng
lớn, phải thiết kế quy trình riêng có theo dõi trạng thái, lỗi/invalid index và lịch sử
migration. PostgreSQL cũng không hỗ trợ concurrent build trực tiếp trên parent partitioned
như bảng thường; cần kế hoạch theo partition nếu chọn hướng đó.
[Tài liệu CREATE INDEX](https://www.postgresql.org/docs/16/sql-createindex.html).

Không dùng `IF NOT EXISTS` để coi index trùng tên là đúng cấu trúc: tên tồn tại có thể
khác cột/predicate. So pg_get_indexdef, dependency và validity trước khi chuyển trạng thái.

### 13.2. Rollback

- Migration tạo index thất bại: transaction/version đó rollback; version cũ đã commit
  vẫn giữ. Không sửa checksum để bỏ qua lỗi.
- Index mới gây chậm sau rollout: giữ evidence, cân nhắc migration bù DROP đúng index
  mới; kiểm dependency/constraint và tên index parent/children trước thao tác.
- Nếu đã bỏ index cũ, phương án quay lại cần DDL tái tạo đã lưu và thời gian build,
  không giả định có thể khôi phục tức thì.
- Không DROP PK/UNIQUE hoặc dùng CASCADE chỉ để thu hồi một index hiệu năng.

### 13.3. Theo dõi sau áp dụng

| Chỉ số | Cách quan sát |
|---|---|
| Latency/throughput đọc và ghi | Cùng workload so baseline, ghi median/p95 và lỗi |
| Index dùng/không dùng | pg_stat_user_indexes + đủ chu kỳ nghiệp vụ + dependency |
| Disk/WAL/vacuum | Size index con, dead tuple, HOT ratio, thời gian vacuum |
| Queue | pending/dead/oldest event, available_at, attempts; cùng cấu hình worker |
| ETL correctness | quality.mismatches, field mismatch, duplicate key, media errors |
| Ảnh dùng chung | Xóa một liên kết không xóa object vẫn được sản phẩm khác tham chiếu |
| Mongo | executionStats và chi phí update metadata/ảnh; không chỉ số index |

Bảng quyết định sau đo: xem [báo cáo thực hiện](benchmark/indexing_v2/2026-11-01/README.md),
bao gồm đủ I01–I14 và M01/M02, bytes/chi phí ghi và các trường hợp hoãn.

## 14. Nhánh tùy chọn: tự lập trình cấu trúc dữ liệu indexing

Nếu mục tiêu học phần yêu cầu tự xây thuật toán, dùng một prototype riêng đọc snapshot
product/ảnh từ DB test. Đây là hướng mở rộng, không phải phần index PostgreSQL đã có.

| Prototype | Khóa → dữ liệu | Cấu trúc tự cài đặt | Phép kiểm |
|---|---|---|---|
| Tra product theo mã | product_id → record/offset | Hash table | So mọi lookup tồn tại/không tồn tại với snapshot |
| Catalogue theo category/giá | (category_id,price,product_id) → vị trí product | B+ tree có leaf liên kết | Equality/range, thứ tự, split/merge và insert/delete |
| Tìm chuỗi | trigram → danh sách product_id | Inverted index/posting list | Giao/hợp posting, kiểm lại chuỗi gốc để loại false positive |
| Ảnh theo product | product_id → image records | Hash map/multimap | Cho phép nhiều ảnh và nhiều product cùng URL |

Lộ trình prototype: nạp snapshot → bulk build → lookup/range/search → insert/update/
delete → kiểm nhất quán với snapshot → đo build time/memory/latency. Không lưu dữ liệu
nhạy cảm hoặc cho bộ nhớ prototype quyết định tồn kho/số dư.

Muốn dùng thực tế còn phải giải quyết transaction commit/rollback, đồng thời, lưu bền,
khôi phục sau crash và đồng bộ với DB. Một B+ tree Python trong RAM không tự được planner
PostgreSQL dùng cho SELECT; muốn tích hợp như access method cần extension và phạm vi
triển khai riêng. Không đặt tên một dict cache là index native của PostgreSQL.

## 15. Tiêu chí hoàn tất kế hoạch

- [x] Inventory bao phủ 28 bảng logic sau migration và index Mongo thực sự sử dụng.
- [x] Mỗi query Q01–Q18 có plan/phân bố/thông số và chủ sở hữu dữ liệu đúng.
- [x] Từng I01–I14, M01/M02 có quyết định chọn/loại, không để DDL minh họa thành áp dụng mặc định.
- [x] Đo cả predicate, thứ tự phá hòa, shared image URL, retry deferred và partition.
- [x] Có before/after thô, môi trường/version rõ; không dùng số lịch sử làm phép đo mới.
- [x] Có chi phí ghi/disk và functional checks, không chỉ latency SELECT.
- [x] Migration mới có checksum/rollback, không thay lịch sử 001–006.
- [x] Cập nhật runbook tự áp dụng/rollback; nhánh prototype là tùy chọn, chưa triển khai.
- [ ] Người dùng áp DB đang dùng, kiểm postflight/reconcile và giám sát tải thật (người dùng tự thực hiện).

## Nguồn đối chiếu trong repository

- [Baseline schema](../database/01_schema/), [functions/triggers](../database/02_functions/),
  [seed](../database/03_seeds/), [migrations](../database/04_migrations/),
  [config](../database/config/database_config.sql), [init](../database/init.sql).
- [Product CRUD](../backend/app/crud/product.py), [order CRUD](../backend/app/crud/order.py),
  [cart CRUD](../backend/app/crud/shopping_cart.py), [user CRUD](../backend/app/crud/user.py),
  [moderator CRUD](../backend/app/crud/moderator.py), [category CRUD](../backend/app/crud/category.py).
- [ETL extract](../backend/etl/extract.py), [runner](../backend/etl/run.py),
  [cleanup](../backend/etl/pipelines/media_cleanup.py),
  [sales report](../backend/app/services/sales_report.py),
  [migration runner](../backend/scripts/migrate.py).
- [Thiết kế Ngày 4](design/04_indexing.md), [benchmark](benchmark/README.md),
  [hướng dẫn kiểm chứng thủ công](HUONG_DAN_KIEM_CHUNG_THU_CONG_7_NGAY.md).
