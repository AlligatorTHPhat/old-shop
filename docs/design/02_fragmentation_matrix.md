# Ngày 2 — Ma trận phân mảnh và phân bổ dữ liệu

Nguồn: [D1–D6](../decisions.md), [inventory](../01_data_inventory.md), schema SQL hiện tại.
**Đây là mô hình đích.** Compose Ngày 2 nạp baseline 18 bảng; partition/tách user là migration Ngày 4.
Sơ đồ nguồn: [02_fragmentation_model.puml](../diagram/02_fragmentation_model.puml).

## Phân mảnh ngang

| Fragment | Vị từ định tuyến | Khóa tại fragment/parent | Nơi ghi | Nơi đọc |
|---|---|---|---|---|
| order_h0..order_h3 | PostgreSQL HASH(order_id), modulus 4, remainder 0..3 | PK(order_id) | PG primary | Parent order trên primary; replica nếu bật và chấp nhận trễ |
| system_log_YYYYMM | created_at thuộc [đầu tháng UTC, đầu tháng kế tiếp UTC) | PK(log_id,created_at) | PG primary | Parent system_log; bản sao Mongo qua ETL |
| system_log_default | Không thuộc khoảng tháng đã tạo | PK(log_id,created_at) | PG primary | Như trên; giám sát để chuyển dữ liệu sang đúng tháng |

**Đầy đủ:** order_id NOT NULL được bộ định tuyến HASH của PostgreSQL đưa tới đúng một
remainder 0..3. Với log, các khoảng tháng cùng DEFAULT nhận mọi created_at hợp lệ, không mất dòng.
Không dùng order_id % 4 làm vị từ thay cho hash PostgreSQL.

**Không chồng lặp:** mỗi khóa order đi tới một partition; các khoảng log nửa mở không giao nhau;
DEFAULT là phần bù các khoảng đang tồn tại. PK order_id được giữ vì chính order_id là khóa partition.
Log dùng PK ghép; sequence không thay thế bảo đảm unique(log_id) trên toàn parent.

**Tái tạo:** bảng cha tương đương UNION ALL các partition theo cùng tập cột.
App truy vấn bảng cha; không tự ghép tên partition theo ngày trong API.
Khi thêm tháng mới, phải kiểm tra/chuyển dòng liên quan ra khỏi DEFAULT trước khi attach khoảng.

**Không phân mảnh ngang trong MVP:** transaction (giữ UNIQUE reference_number), product
(giữ FK product_id), order_detail, cart/item, voucher và các bảng user đích.
Chưa shard Mongo; replica set là sao chép, không phải phân mảnh ngang.

## Phân mảnh dọc user — đủ 20 cột nguồn

| Fragment | Cột nguồn | Khóa và quan hệ | Phân bổ |
|---|---|---|---|
| user_core | user_id, username, email, is_active, is_deleted, email_verified, trust_score, created_at, updated_at, last_login | PK user_id; UNIQUE username/email | PG primary; streaming replica nếu bật |
| user_profile | user_id, full_name, phone_number, address, avatar_url | PK/FK user_id→core | PG, không ETL PII sang Mongo |
| user_secret | user_id, password_hash, random_key, email_verification_token, password_reset_token, password_reset_expires | PK/FK user_id→core; UNIQUE random_key | PG, chỉ đường truy cập xác thực được phép đọc |
| user_wallet | user_id, balance | PK/FK user_id→core | PG primary cho đọc/ghi tiền |
| user_role (giữ nguyên) | user_id, role_id | PK(user_id,role_id); FK user_id đổi sang core | PG, giữ hỗ trợ nhiều role/user |

Đặt C là tập cột của user hiện tại, Ci là tập cột mỗi fragment.
Hợp Ci = C; giao hai fragment khác nhau chỉ là {user_id}. Bỏ 3 lần lặp khóa thu được đúng 20 cột.
PK đảm bảo mỗi fragment tối đa một dòng/user, FK ngăn dòng con mồ côi.
Invariant **mọi core đều có đủ profile/secret/wallet** còn cần tạo đồng thời trong transaction
và kiểm tra đối soát; không suy ra invariant này chỉ từ FK một chiều.

View users_full JOIN theo user_id tái tạo hình dạng dữ liệu cũ khi invariant được giữ.
View chỉ đọc; ORM/service cập nhật bảng vật lý trong một transaction.
Giữ nguyên kiểu/null/default/unique cũ, chưa tự đổi tên avatar_url hay thêm role_id vào core.
Email ở core là PII phục vụ login; tách bảng không tự tạo quyền truy cập riêng.

## Product và dữ liệu phi cấu trúc

| Nhóm field/nội dung | Nguồn ghi chính trong MVP | Bản đọc/tham chiếu | Tính chất |
|---|---|---|---|
| product_id/seller/category/title/price/quantity/status/moderation/timestamps/transfer_method/view_count | PG product | Mongo chỉ nhận phần field cho phép nếu cần | Dữ liệu giao dịch/lõi có cấu trúc |
| description, weight_grams, dimensions, condition_rating, warranty_months, video_url hiện có | PG product | Mongo product_details, theo ETL outbox Ngày 5 | Expand/contract: vẫn có bản nguồn PG |
| attributes động/tags mới | Mongo product_details | API đọc/ghi trực tiếp Mongo | Document linh hoạt, không có bản nguồn trong PG |
| product_image và avatar_url | PG metadata/quan hệ | Mongo có thể chứa bucket/key được ETL cập nhật | Không suy product_id từ tên file |
| Byte ảnh/avatar/attachment | MinIO | Key tham chiếu trong PG hoặc document Mongo theo D1 | Object, không phải cột BLOB trong PG |

Product ở giai đoạn chuyển tiếp **có sao chép phần dữ liệu**, nên không tuyên bố đây là phép
phân rã vật lý hoàn toàn không chồng lặp. Thuộc tính động mới nằm riêng trong Mongo;
các cột PG cũ chưa bị DROP trong 7 ngày. Metadata object key là dữ liệu có cấu trúc;
document có thuộc tính thay đổi/nhúng mảng là mô hình bán cấu trúc; byte ảnh là phi cấu trúc.

## Allocation matrix — một site vật lý

| Dữ liệu | pg-primary | pg-replica (profile) | Mongo replica set | MinIO |
|---|---|---|---|---|
| Fragment order/log; user_core/profile/secret/wallet và bảng PG còn lại | Authoritative R/W | Bản sao vật lý async, read-only | Chỉ bản đọc đã allowlist, không secret/wallet/địa chỉ | — |
| Outbox PG (Ngày 5) | Ghi cùng transaction nguồn; ACK khi load thành công | Bản sao WAL | Không quyết định ACK thay PG | — |
| Product attributes/tags/metadata mới | ID quan hệ nếu cần, không dual-write cùng field | — | Authoritative; 1 member hoặc 3 member cùng site | — |
| Order/review/log read model | Nguồn structured của ETL | Không dùng làm nguồn ETL mặc định | Upsert eventual, có thể rebuild trong giới hạn retention nguồn | — |
| Nội dung file | Metadata/key | Metadata/key sao chép | Metadata/key theo quyền sở hữu | Authoritative object bytes, single-node |

Mỗi PG replica sao chép **toàn cluster**, không phải chỉ một fragment và không che giấu PII
khỏi người vận hành replica. Mongo2/3 sao chép dữ liệu Mongo; không tăng phạm vi dữ liệu được ETL.
Tất cả container ở cùng máy: mất máy làm toàn site không phục vụ.

## Truy vấn và tiêu chí kiểm chứng Ngày 4

- Order theo order_id: pruning tới HASH partition tương ứng; buyer history theo ngày
  không tự pruning theo order_date, cần index đúng workload.
- Log theo khoảng created_at: pruning RANGE; toàn bộ thời gian vẫn phải quét các partition liên quan.
- users_full: JOIN phục vụ đọc/đối soát; auth/cart/checkout dùng service phù hợp và primary.
- Catalogue: PG lọc lõi; Mongo bổ sung thuộc tính, chưa chuyển search description khỏi PG.
- Benchmark với dữ liệu lớn, EXPLAIN trước/sau và kiểm FK/trigger; kết quả đo quyết định
  tuyên bố hiệu năng, không dùng seed vài chục dòng để kết luận.
- FDW/vùng chỉ là hướng mở rộng: chưa có region chuẩn hóa, site thứ hai hoặc allocation qua nhiều máy.

Nguồn quy tắc partition: [PostgreSQL 16](https://www.postgresql.org/docs/16/ddl-partitioning.html).
