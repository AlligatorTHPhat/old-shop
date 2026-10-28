# decisions.md — Quyết định thiết kế (Ngày 1, 27/10/2026)

> Trạng thái: **ĐÃ CHỐT D1–D6 cho giai đoạn đồ án chạy một máy**, sau các câu trả lời của người dùng.
> Việc chốt thiết kế không đồng nghĩa đã triển khai hoặc kiểm thử kiến trúc mới.
> Các chi tiết DDL/Compose/API phải tuân thủ các quyết định này và được kiểm thử ở Ngày 2–6.
> Căn cứ: `01_data_inventory.md`, `DAY1_FINDINGS_LOG.md` (mục C).
> **Review bổ sung 28/10/2026:** đã đối chiếu mã đầy đủ, init trên PostgreSQL 16.15
> và SQL thuần qua driver pgAdmin4 9.18; xem [DAY1_REVIEW.md](DAY1_REVIEW.md).
> D7–D11 vẫn là đề xuất/phụ thuộc cần xử lý, không được tự đánh dấu đã chốt cùng D1–D6.

## Bảng chốt D1–D6

| Quyết định | Trạng thái | Kết luận / thông tin còn thiếu |
|---|---|---|
| D1 | **ĐÃ CHỐT** | PG làm nguồn sự thật cho giao dịch và dữ liệu nhạy cảm; Mongo lưu bản đọc và thuộc tính linh hoạt mới; MinIO giữ nội dung file. Chi tiết bên dưới. |
| D2 | **ĐÃ CHỐT** | Metadata mới do Mongo quản lý được ghi trực tiếp; bản đọc từ PG dùng full load + ETL qua transactional outbox, poll 60 giây, mục tiêu độ trễ dưới 5 phút khi hệ thống hoạt động bình thường. |
| D3 | **ĐÃ CHỐT** | Order HASH(order_id), 4 partition; system_log RANGE(created_at) theo tháng. Transaction giữ nguyên PK/UNIQUE; product dùng phân mảnh dọc, chưa partition theo category. FDW và Mongo sharding để giai đoạn mở rộng. |
| D4 | **ĐÃ CHỐT** | User tách 4 bảng PG, giữ user_role; product giữ lõi PG, thuộc tính động/chi tiết dạng document ở Mongo theo lộ trình expand/contract. View tái tạo chỉ đọc; ghi qua service tới bảng gốc. |
| D5 | **ĐÃ CHỐT** | Một máy: PG primary, Mongo một member replica set, MinIO single-node, ETL và ứng dụng; profile dự phòng tùy chọn thêm PG replica và 2 Mongo member. Chưa cam kết chịu mất máy. |
| D6 | **ĐÃ CHỐT** | Migration có version/checksum/lock/transaction; bảo toàn dữ liệu phát sinh, maintenance mode dừng ghi và ETL trong lúc chuyển đổi; backup và đối soát trước/sau. |

**Căn cứ chốt từ người dùng:** RANGE/LIST/FDW là phương án mặc định, chưa có ràng buộc
bắt buộc cụ thể; ưu tiên một máy và chuẩn bị mở rộng sau. Người dùng xác nhận:
“Cứ chốt giai đoạn hiện tại là đồ án chạy một máy trước”. Dữ liệu ban đầu là seed
nhưng có thể có thao tác phát sinh nên phải giữ; cho phép chọn maintenance migration
và yêu cầu giải thích. Không có SLA đồng bộ đã định trước, vì vậy chu kỳ 60 giây/mục tiêu
5 phút là lựa chọn thiết kế của người thực hiện, chưa phải số đo hoặc bảo đảm khi có sự cố.

**Hiểu đúng vai trò lưu trữ:** PostgreSQL chứa dữ liệu có cấu trúc; pgAdmin4 là công cụ quản trị.
MongoDB chứa document BSON biểu diễn metadata/thuộc tính kiểu JSON, không cần lưu từng file .json.
MinIO chứa nội dung ảnh/file, Mongo hoặc PG giữ tham chiếu object key theo quyền sở hữu dữ liệu.
Nguồn: [MongoDB Documents](https://www.mongodb.com/docs/manual/core/document/).

## D1 — Nguồn sự thật
**Trạng thái: ĐÃ CHỐT về trách nhiệm dữ liệu.** Căn cứ: reserve/release nằm ở CRUD + PG,
schema/trigger đã kiểm chứng; giao dịch và tồn kho đang phụ thuộc tính nguyên tử trong PostgreSQL.

**Quyết định:** PostgreSQL là SoT cho mọi dữ liệu giao dịch: `"user".balance`,
`product.quantity`, `shopping_cart*`, `"order"`, `order_detail`, `transaction`, `voucher.usage_count`.
Các tên user_wallet/product_core là mô hình đích phụ thuộc D4, chưa phải bảng hiện có.
Auth, role/quyền, sổ địa chỉ contact_info và PII giao dịch gốc tiếp tục ở PG.

**Mongo có hai trách nhiệm tách biệt:**
- **Read model** (sinh bằng ETL, có thể xóa dựng lại): `order_snapshots`, `reviews` (bản đọc), `system_logs` (bản sao).
- **Authoritative trong Mongo** (SoT mới khi triển khai): thuộc tính động/tags mới của sản phẩm;
  metadata file đính kèm mới của contact_messages. Nội dung file nhị phân ở MinIO.
  Không đưa password/token, địa chỉ/SĐT/email giao dịch vào bản đọc phân tích;
  ETL dùng danh sách field cho phép và giữ nguyên dữ liệu do Mongo quản lý.

**MinIO** giữ byte ảnh/avatar/attachment; PG giữ metadata định danh ảnh/avatar hiện tại,
Mongo chỉ tham chiếu bucket/key trong bản đọc hoặc metadata mới do Mongo quản lý.
ETL không tự xác lập quan hệ product_id từ tên file seed.

**Chuyển tiếp:** mô tả/kích thước/tình trạng/bảo hành hiện có vẫn **PG ghi, Mongo nhận bản đọc**.
Giữ các cột PG để API và ILIKE title/description tiếp tục hoạt động. Chuyển quyền ghi hoặc bỏ cột
phải có quyết định cutover, migration và kiểm thử riêng; chưa cam kết bỏ trong Ngày 6.
Mỗi field có đúng một nơi nhận ghi chính; không thực hiện dual-write hai DB như một transaction nguyên tử.

**Điều kiện nghiệm thu khi triển khai:** lỗi Mongo không cho phép dùng bản đọc cũ để quyết định
tồn kho/ví/checkout; rebuild read model không mất attributes/tags/metadata mới;
các dữ liệu chỉ có ở Mongo/MinIO phải được backup. Retention log và lịch đồng bộ thuộc D2/D5,
chưa cho phép xóa log PG chỉ vì đã có TTL Mongo.

## D2 — Đồng bộ PG → Mongo
**Trạng thái: ĐÃ CHỐT.** Tách hai luồng để việc tạo metadata mới không phải chờ ETL:

- Thuộc tính động/tags do Mongo quản lý: API ghi trực tiếp vào Mongo, báo thành công
  sau khi Mongo xác nhận ghi. Lỗi Mongo thì báo lỗi cho thao tác này; không giả vờ đã lưu
  hoặc âm thầm bỏ field. Dữ liệu này đọc trực tiếp từ Mongo.
- Order snapshots/review/log và phần chi tiết sản phẩm có nguồn PG: full load ban đầu,
  sau đó worker Python poll **60 giây/lần**, xử lý theo lô và upsert idempotent.
  Mục tiêu khi tải bình thường là dữ liệu hiển thị được cập nhật **dưới 5 phút**;
  gắn synced_at và theo dõi event chưa xử lý lâu nhất. Sự cố/downstream chậm có thể vượt mục tiêu.
  Không dùng snapshot trễ để duyệt thanh toán, tồn kho hay số dư.

**Cơ chế bắt thay đổi:** bảng outbox PG được ghi bởi trigger INSERT/UPDATE/DELETE
trong cùng transaction với dữ liệu nguồn. Payload chỉ gồm loại thực thể, khóa định danh,
thao tác và thông tin tối thiểu phục vụ xóa; không sao chép password/token/PII vào outbox.
Transaction rollback thì event cũng rollback; commit thành công để lại event chờ xử lý.

- Một worker MVP xử lý tuần tự, đọc các event có trạng thái chưa hoàn tất, không dùng
  điều kiện `event_id > MAX(last_id)` hoặc timestamp làm bảo đảm đầy đủ.
- Với mỗi event, dựng lại trạng thái mới nhất từ PG và upsert theo khóa ổn định.
  Chỉ đánh dấu hoàn tất **đúng những event đã xử lý** sau khi Mongo ghi thành công.
  Crash sau ghi Mongo nhưng trước ACK sẽ chạy lại; chấp nhận at-least-once, không tuyên bố exactly-once.
- Retry có backoff; event lỗi giữ lại để xử lý lại và ghi run_id/error.
  Chưa cho phép nhiều worker cập nhật cùng một aggregate đồng thời; mở rộng phải có
  khóa/version bảo vệ để bản cũ không ghi đè bản mới.
- Bật outbox trước khi lấy full snapshot; giữ event phát sinh trong full load rồi xử lý bù.
  Reconciliation theo khóa/số lượng/phần dữ liệu nguồn chạy hằng ngày và sau full load/restore.
- Soft-delete chuyển thành deleted=true; hard-delete phát tombstone để xóa/ẩn bản đọc
  tương ứng. Giữ khóa cũ trong event khi dòng nguồn không còn.

**Phạm vi phụ thuộc phải bắt đủ:**

| Nguồn thay đổi | Aggregate/bản đọc cần cập nhật |
|---|---|
| product, product_image | product_details: phần dữ liệu thuộc PG và tham chiếu ảnh |
| order, order_detail, transaction | order_snapshots tương ứng; đổi FK phải cập nhật cả aggregate cũ/mới |
| Các field product/voucher được nhúng vào snapshot | Chốt là snapshot tại thời điểm đặt hàng hay giá trị hiện tại trong thiết kế JSON; field hiện tại cần fan-out/rebuild, không bỏ qua âm thầm |
| review, system_feedback, violation_log | Bản đọc tương ứng nếu collection được triển khai |
| system_log | Bản sao log; event phải giữ thông tin cần thiết nếu nguồn sắp được dọn |
| shopping_cart, shopping_cart_item, contact_info, user_secret, user_wallet | Không ETL sang Mongo trong MVP |

**Không ghi đè dữ liệu Mongo:** ETL chỉ `$set` các field thuộc PG,
không replace cả document làm mất attributes/tags/metadata mới. D2 không chuyển quyền ghi
mô tả từ PG sang Mongo; việc đó tuân thủ D4.

**Retention:** bản sao log Mongo TTL dự kiến 90 ngày; dọn nguồn PG là tác vụ riêng,
chỉ bật sau khi kiểm tra event/bản sao đã hoàn tất. Không giữ event chưa ACK theo TTL.
Chưa triển khai retention thì giữ log PG; không tự chạy clean_old_audit_logs trong pipeline.
Các giá trị thời gian xuất UTC; D7 phải giải quyết nguồn timestamp cũ trước backfill.
CDC/Debezium để hướng mở rộng, không đưa vào MVP.

## D3 — Phân mảnh ngang
**Trạng thái: ĐÃ CHỐT phương án B cho order, điều chỉnh mặc định RANGE/LIST.**
Người dùng xác nhận đây là phương án mặc định, chưa nêu bắt buộc bảng/kiểu cụ thể.
Nhiều cột/thông tin là lý do xem xét tách dọc; phân mảnh ngang cần xem số dòng,
dung lượng và điều kiện truy vấn. Chưa có benchmark để hứa partition luôn nhanh hơn index.

| Bảng | Quyết định MVP | Khóa/ràng buộc và giới hạn |
|---|---|---|
| order | HASH(order_id), 4 partition cùng PG instance | Giữ PK(order_id), FK từ order_detail/transaction và trigger chặn tự mua. Tra theo order_id có thể pruning; buyer/seller history không tự pruning theo ngày. |
| system_log | RANGE(created_at) theo tháng | PK(log_id,created_at); hiện không có FK tới log_id. Giữ sequence log_id, không coi log_id riêng lẻ là unique được DB bảo đảm; D2 xử lý log bằng khóa ghép tương ứng. |
| transaction | Chưa partition; bổ sung index theo truy vấn | Giữ PK(transaction_id) và UNIQUE(reference_number) toàn bảng. Tránh mất tính duy nhất tài chính để đổi lấy demo. |
| product | Chưa partition ngang; thực hiện tách dọc D4 | Giữ PK(product_id), FK hiện có, index catalogue/ILIKE; không thêm composite FK category vào các bảng con trong MVP. |
| order_detail | Chưa partition | Giữ PK(order_detail_id), FK(order_id) tới bảng cha partitioned; index order_id/product_id theo truy vấn. |

**Tính chất phân mảnh:** HASH với modulus=4 và remainder 0..3 bao phủ đủ/không trùng;
truy vấn bảng cha tái tạo bằng hợp các partition. RANGE dùng khoảng [đầu tháng, đầu tháng sau),
tạo trước tháng hiện tại/tháng kế tiếp và các tháng lịch sử cần backfill, có DEFAULT partition
để tiếp nhận ngoài khoảng; giám sát và chuyển dòng khỏi DEFAULT trước khi thêm khoảng chồng dữ liệu.
Biên thời gian dùng timestamptz/UTC sau D7. Không dùng `% 4` trên giá trị order_id để tự định tuyến;
để PostgreSQL áp dụng hash partitioning.

**Không chọn RANGE order trong MVP:** cần PK chứa order_date, thêm composite FK cho bảng con
và giải quyết tính duy nhất order_id toàn cục. RANGE transaction còn vướng cả transaction_id
và reference_number. LIST/HASH category của product tương tự vướng PK/FK.
DEFAULT partition không giải quyết các vấn đề khóa này. Không bỏ FK hoặc giảm UNIQUE để né chúng.
Nguồn quy tắc và pruning: [PostgreSQL 16 — Table Partitioning](https://www.postgresql.org/docs/16/ddl-partitioning.html).

**Nghiệm thu Ngày 4:** dữ liệu tổng hợp đủ lớn/trải thời gian; EXPLAIN theo order_id cho HASH,
theo created_at cho log RANGE; đối soát dữ liệu và FK/trigger sau migration; so với baseline có index.
Nếu benchmark không nhanh hơn vẫn báo cáo số thật và mục đích minh họa phân mảnh.
Kiểm tra mọi nơi dùng log_id khi PK log đổi; API có thể giữ field log_id để tương thích,
nhưng read model/outbox log dùng (log_id,created_at) làm danh tính nguồn.

**Mở rộng:** FDW theo vùng và Mongo sharding không triển khai ở giai đoạn một máy.
Chỉ chọn khóa/vị từ vùng khi có site thứ hai và dữ liệu region chuẩn hóa; không suy diễn tự động
từ địa chỉ tự do. Partitioning trên một instance chưa phải phân tán dữ liệu qua nhiều máy.

## D4 — Phân mảnh dọc
**Trạng thái: ĐÃ CHỐT mô hình đích và lộ trình chuyển tiếp.** User tách 4 bảng PG
để tách thông tin đăng nhập/hồ sơ/bí mật/ví. Toàn bộ vẫn ở cùng PG primary trong MVP.

| Mảnh | Cột | Lý do |
|---|---|---|
| `user_core` | user_id, username, email, is_active, is_deleted, email_verified, trust_score, created_at, updated_at, last_login | Định danh/tra cứu đăng nhập; email ở core có chủ đích vì login hỗ trợ email, vẫn là PII cần bảo vệ |
| `user_profile` | user_id, full_name, phone_number, address, avatar_url | Hồ sơ; giữ tên avatar_url để tránh đổi contract cùng lúc với tách bảng |
| `user_secret` | user_id, password_hash, random_key, email_verification_token, password_reset_token, password_reset_expires | Bí mật, quyền tối thiểu |
| `user_wallet` | user_id, balance | Tiền ở PG, có thể khóa dòng ví riêng; chưa thêm timestamp vào ánh xạ cột nguồn |

**Tính chất trên mô hình:** bỏ 3 lần lặp user_id, hợp cột của 4 bảng là đúng 20 cột nguồn;
chỉ user_id lặp giữa các mảnh. Mỗi bảng con có PK/FK user_id→user_core, giữ quan hệ 1:1,
không có dòng mồ côi; tạo 4 dòng trong cùng transaction đăng ký/backfill.
Một dòng con bị thiếu vẫn có thể xảy ra nếu bỏ qua service: kiểm tra đối soát và quyền ghi
phải bảo vệ invariant này, FK một chiều tự nó không bắt buộc core luôn có đủ 3 con.

**Quyền và tương thích:** giữ user_role và quan hệ nhiều role/user; chuyển FK về user_core,
không nhét role_id đơn vào core. Giữ UNIQUE(username/email/random_key), NOT NULL và defaults nguồn.
View `users_full` JOIN 4 bảng để đọc/đối soát tái tạo. **Không map view JOIN thành bảng ghi tự động**,
không thêm INSTEAD OF trigger ở MVP: ORM/service ghi trực tiếp các bảng đích trong cùng transaction.
Auth chỉ join phần cần thiết; serializer không trả password/token. Tách bảng không tự tạo phân quyền,
phải giới hạn đường truy cập tới secret/wallet. Các FK đang trỏ user được chuyển có kiểm soát trong migration.

**Product:** lõi PG giữ product_id, seller/category, title, price, quantity, status, moderation,
transfer_method và các field giao dịch/thời gian. Mongo product_details lưu thuộc tính động/tags
và bản đọc mô tả/kích thước/tình trạng/bảo hành; ảnh nhị phân MinIO, product_image vẫn giữ quan hệ PG.
view_count ở PG trong MVP. Không rename bảng product hoặc cột API chỉ để đổi nhãn thành product_core.

**Expand/contract:** tạo Mongo và backfill phần chi tiết nhưng giữ cột PG làm nguồn ghi cho dữ liệu cũ.
API đọc kết hợp, có fallback phần PG khi Mongo lỗi. Chỉ dữ liệu mới do Mongo quản lý mới ghi trực tiếp Mongo.
Không DROP description/weight/dimensions/condition/warranty trong phạm vi 7 ngày;
vì search hiện ILIKE cả title/description, bước chuyển hoàn toàn sang Mongo là migration sau,
phải thay truy vấn và xác nhận hành vi tìm kiếm trước.

**Nghiệm thu:** đối soát 20 cột và số dòng qua users_full, không có core thiếu bảng con;
test đăng ký/login/OTP/profile/role/ví và rollback; test đọc product khi Mongo có/lỗi;
không mất dữ liệu người dùng khi backfill hoặc ETL chạy lại. Đây là tiêu chí phải kiểm thử,
chưa phải kết quả đã đạt của schema đích.

## D5 — Phân tán
**Trạng thái: ĐÃ CHỐT một máy cho đồ án; mở rộng nhiều máy là giai đoạn sau.**
Đây là phạm vi người dùng đã xác nhận sau khi làm rõ giới hạn chịu mất máy.

**Topology mặc định:** 1 PostgreSQL primary, 1 MongoDB (replica set một member để chuẩn bị mở rộng),
1 MinIO single-node, 1 ETL worker, FastAPI và Angular/Nginx. pgAdmin4 có thể dùng bản desktop
đã cài; không bắt buộc chạy thêm container GUI. Volume riêng cho từng dịch vụ, URI/credentials
qua biến môi trường, internal network cho DB; backend không hardcode localhost của từng DB.
Metadata/ảnh mới không dùng nhờ container Mongo/MinIO bên ngoài dự án chỉ vì chúng đang chạy.

**Profile dự phòng tùy chọn sau khi core chạy ổn:** thêm 1 PG streaming replica và
mongo2/mongo3 thành replica set 3 member có dữ liệu. Mongo reconfigure và healthcheck phải
hoàn tất trước khi coi profile hoạt động. Không bật thêm ELK để demo dữ liệu khi không cần.
MinIO giữ single-node trong MVP; 4 volume trên cùng máy không được trình bày là chịu mất máy.

**Tài nguyên:** docker stats người dùng cung cấp cho thấy MinIO báo limit 7.5 GiB và Mongo
limit 2 GiB ở thời điểm lấy mẫu; không đủ suy ra tổng RAM còn trống/số CPU hay ngân sách
cho toàn stack. Ngày 2 đo tài nguyên và tải thực trước khi bật profile dự phòng;
CPU 85.14% của một container không cho biết số CPU máy. Không hứa chạy mọi profile đồng thời.

**Giới hạn lỗi và tiêu chí demo:**

| Sự cố | Hành vi phải giải thích/kiểm thử |
|---|---|
| Mongo mặc định dừng | Giao dịch PG và phần product cũ còn phục vụ; thuộc tính mới không ghi được, ETL giữ backlog và chạy bù khi Mongo trở lại |
| MinIO dừng | Ảnh mới/upload không khả dụng; API báo lỗi phù hợp, không coi toàn bộ tính năng media vẫn hoạt động |
| PG replica tùy chọn dừng | Luồng giao dịch vẫn dùng primary; báo cáo có thể fallback primary theo cấu hình |
| Một member Mongo trong profile 3 member dừng | Kiểm tra quorum/election khi triển khai profile; không suy rộng từ replica set một member |
| PG primary dừng | Core có downtime; chưa có Patroni/automatic failover. Profile replica chỉ cho phép promote có quy trình, fencing primary cũ và chuyển kết nối; async có thể mất giao dịch chưa replicate |
| Cả máy dừng | Stack một máy không tiếp tục phục vụ; chỉ có khả năng khôi phục từ backup ngoài máy. Chịu mất máy cần hạ tầng giai đoạn sau |

Backup PG/Mongo và object MinIO phải bao gồm dữ liệu người dùng tạo; bản sao cùng ổ đĩa
không thay thế bản lưu ngoài máy. Cần test restore trước khi tuyên bố khôi phục được.
Read/write giao dịch luôn primary; replica async chỉ phục vụ bản đọc chấp nhận trễ.
Thiết kế giai đoạn nhiều máy phải phân bổ replica/quorum qua các máy độc lập và có cơ chế
chuyển endpoint/failover cho cả ứng dụng, PG, Mongo và object storage; chưa được coi đã hiện thực.
Nguồn về Mongo quorum/topology: [MongoDB Three Member Replica Sets](https://www.mongodb.com/docs/manual/core/replica-set-architecture-three-members/).

## D6 — Migration
**Trạng thái: ĐÃ CHỐT, có maintenance window và bảo toàn dữ liệu phát sinh.**
Căn cứ: init_db.py bỏ qua init.sql khi bảng user tồn tại; PostgreSQL audit xác nhận baseline
nhưng chưa có migration runner. Không cần đổi sang ORM-generated schema.

Người dùng xác nhận ban đầu seed nhưng có thể có thao tác tạo dữ liệu, đồng ý dừng ứng dụng
để tránh xung đột. Vì vậy mọi DB đã được sử dụng được coi là có dữ liệu cần giữ;
không tự reset/reseed dù đang ở môi trường đồ án.

**Quyết định:** `database/04_migrations/NNN_*.sql` + bảng
`schema_migrations(version, applied_at, checksum)` + runner `backend/scripts/migrate.py`.
Runner là hạng mục sắp triển khai, chưa có trong mã hiện tại.

**Hợp đồng bắt buộc khi triển khai:**
- `init.sql` coi là **baseline (v0)**; sau baseline (cả DB mới lẫn DB cũ) luôn chạy các migration chưa áp dụng ⇒ một đường duy nhất cho dev/test/CI.
- `init_db.py` hiện: `schema_exists()` (kiểm tra `public."user"`) ⇒ bỏ qua init.sql; thêm bước `run_migrations()` **sau** nhánh này.
- Cấu hình kết nối chung: DATABASE_URL nếu được cung cấp là nguồn ưu tiên; nếu không thì
  dựng từ DB_*. Engine/bootstrap/migration phải dùng cùng thông tin kết nối đã chuẩn hóa,
  bao gồm host/port/database và tham số kết nối liên quan. Không giữ hai cấu hình độc lập có thể trỏ khác DB.
- Khóa advisory ở cấp session cho toàn bộ lượt migrate trên một connection riêng;
  version được áp dụng theo thứ tự. Với migration SQL thông thường: DDL/DML và ghi nhận
  version/checksum phải commit trong cùng transaction; lỗi phải rollback và dừng khởi động app.
- Runner chạy lại sẽ bỏ qua version đã áp dụng có checksum khớp; phát hiện checksum khác
  phải dừng, không tự sửa migration lịch sử. Không đồng nhất điều này với việc mọi câu DDL phải có IF NOT EXISTS.
- Câu lệnh không chạy được trong transaction phải được khai báo và xử lý riêng;
  chưa đưa vào đường mặc định của MVP.
- `04_migrations` đi cùng baseline mới cho DB test (CI chạy init.sql rồi migrate).
- Trước khi nhận DB cũ vào baseline v0, kiểm tra schema hiện hữu thay vì chỉ thấy bảng user
  là coi tương thích. DB mới chạy baseline/seed một lần; DB đang dùng chỉ chạy migration chưa áp dụng.
- Với DB có dữ liệu cần giữ: phải có backup/restore đã kiểm chứng và đối soát trước/sau;
  chuyển timestamp naive phụ thuộc D7 và nguồn ghi từng nhóm dữ liệu, không tự gán múi giờ hàng loạt.
- D3/D4 quyết định nội dung migration tách bảng/khóa; D6 không tự phê duyệt các DDL đó.

**Trình tự maintenance:** bật trang bảo trì/chặn ghi từ API, drain request còn chạy và dừng
ETL/scheduler; PG/Mongo/MinIO vẫn chạy để backup và migrate. Lưu backup nhất quán dữ liệu
nguồn PG cùng dữ liệu chỉ có trong Mongo/MinIO; xác nhận bản backup có thể restore.
Chạy runner một lần, backfill, kiểm tra số dòng/khóa/tổng tiền/mapping user/metadata ảnh,
chạy smoke test và full load/ETL bù phù hợp, rồi mới mở ghi và khởi động scheduler.
Không chỉ tắt frontend trong khi API vẫn nhận ghi.

Migration lỗi thì giữ maintenance, rollback transaction; nếu phải restore thì dùng backup
tương thích phiên bản ứng dụng và dữ liệu đa kho. Không tự drop cột hay chạy down migration
phá dữ liệu. Thời lượng maintenance sẽ được đo trên DB test có quy mô đại diện ở Ngày 4–6,
không cam kết zero-downtime. Kế hoạch này đơn giản hơn online migration trong phạm vi một máy/7 ngày.

## Quyết định bổ sung (phát sinh từ audit — đề nghị chốt cùng D1–D6)
### D7 — Chuẩn hóa thời gian
**Vấn đề:** ORM ghi `datetime.utcnow` (UTC), SQL/seed ghi `CURRENT_TIMESTAMP` theo `Asia/Ho_Chi_Minh`; cột là `TIMESTAMP` không tz ⇒ cùng cột chứa 2 hệ giờ.
**Đề xuất:** chuyển sang `timestamptz`, giữ giờ lưu = UTC; ORM dùng `DateTime(timezone=True)`; ETL luôn xuất UTC. Phải làm **trước** khi đặt biên partition theo `order_date`. (Dữ liệu cũ: gán `AT TIME ZONE` theo nguồn ghi — chỉ phân biệt được bằng quy ước; seed = giờ VN.)
### D8 — Enum `TransactionStatus`
**Vấn đề:** SQL comment: 3=Fraud, 4=Failed; `constants.py`: 3=FAILED, không có 4; seed dùng **4** (5 dòng).
**Đã xác minh 28/10:** CRUD tạo PENDING=0; API PayPal ghi SUCCESS=1/FLAGGED=2;
chưa thấy app ghi FAILED=3. Seed có 5 dòng status=4. Chưa tự remap dữ liệu.
**Đề xuất:** chuẩn hóa mapping và migration cho dữ liệu cũ, rồi đồng bộ constants ↔ SQL ↔ seed ↔ FE
và bổ sung CHECK sau khi chốt miền giá trị. Trước đó snapshot giữ giá trị số gốc,
không dùng IntEnum để parse giá trị 4.
### D9 — `contact_info` ở lại PG
Là sổ địa chỉ (PII). Collection `contact_messages` (Mongo) tương ứng `system_feedback`, **không** phải `contact_info`. Sửa bảng ánh xạ trong kế hoạch Ngày 3/5.
### D10 — Bộ đếm `view_count`
Ghi mỗi lượt xem làm tăng dead tuple/khóa dòng `product`. Đề xuất: giữ ở PG giai đoạn này nhưng ghi nhận như rủi ro; phương án sau: counter ở Mongo (`$inc`) đồng bộ định kỳ về PG. Không chặn Ngày 2–4.
### D11 — Dọn dead code DB / quy ước log
**Đã xác minh 28/10:** không thấy backend gọi apply_voucher_to_order; generic_audit_trigger
không gắn vào bảng. Đã tái hiện lỗi undefined_column(updated_at) khi gọi hàm voucher;
chưa sửa baseline. Chuyển việc sửa/xóa sang migration. SELF_BUY_BLOCKED bị rollback
đã được kiểm chứng bằng SQL; thiết kế log chặn độc lập giao dịch ở tầng ứng dụng.

## Rủi ro đã biết (theo checklist Ngày 1)
| Rủi ro | Mô tả | Giảm thiểu |
|---|---|---|
| Bootstrap `DATABASE_URL` vs `DB_*` | `init_db.py` chỉ dùng `DB_*` | D6: chuẩn hóa cả hai trong compose/.env; test với chỉ `DATABASE_URL` |
| `init.sql` bị bỏ qua khi DB đã có | không tự migrate | D6: runner `schema_migrations` |
| Ngưỡng fraud 0.9 | Đã đọc fraud_detection.py 28/10: model score bị chặn 0.9 nhưng is_fraud so sánh >0.9; nhánh hard limit vẫn hoạt động | Không phải trọng tâm; ghi chú nếu đưa fraud.score vào snapshot |
| Enum `PaymentMethodId` | seed có 5 phương thức, guide: chỉ COD/PayPal triển khai; seed lại phân bố 24/30 đơn vào MoMo/VNPay/Bank | Snapshot lưu `method_id` + cờ; không tuyên bố hỗ trợ |
| Trộn múi giờ | D7 | trước partition/ETL |
| Seed lệch dữ liệu | avatar thiếu 11 file; tên ảnh ≠ product_id; voucher đơn vị/hết hạn | ETL media tolerant; sửa seed ở migration/seed mới |
