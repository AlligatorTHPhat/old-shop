# KẾ HOẠCH NÂNG CẤP VÀ HOÀN THIỆN OLDSHOP

**Ngày lập:** 08/11/2026, múi giờ Việt Nam (UTC+7).  
**Mục tiêu:** đồ án môn học; nhóm 3 người; hoàn tất trước ngày 10/11/2026.  
**Mốc bàn giao đề xuất:** 23:59 ngày 09/11/2026; không mặc định có thêm ngày 10/11 để triển khai.  
**Phạm vi tài liệu:** kế hoạch và thiết kế mục tiêu. Tài liệu này không xác nhận các nâng cấp đã được triển khai hoặc kiểm thử. Các sơ đồ được diễn giải bằng chữ, không vẽ hình.  
**Căn cứ:** [báo cáo kiến trúc hiện tại](report/BAO_CAO_KIEN_TRUC_CO_SO_DU_LIEU_OLDSHOP.md), mã nguồn trong repository và các quyết định đã thống nhất trong trao đổi ngày 06–08/11/2026.

## 1. Quyết định phạm vi và nguyên tắc nghiệm thu

### 1.1. Các quyết định đã thống nhất

| Mã | Nội dung | Phạm vi áp dụng |
|---|---|---|
| D01 | Hai site PostgreSQL: máy thật A và máy ảo B | Bắt buộc; hai môi trường máy chủ có địa chỉ truy cập riêng, cùng một host vật lý |
| D02 | Danh mục đọc/ghi đa site qua một API | Bắt buộc: tạo, xem, sửa, xóa mềm sản phẩm; frontend không chọn database |
| D03 | Checkout xuyên site | Tùy chọn; không được làm hỏng checkout hiện hữu hoặc âm thầm xử lý sai sản phẩm B |
| D04 | Chấp nhận đồng bộ trễ | Bảo đảm nhất quán nghiệp vụ bằng transaction cục bộ, outbox, retry, xử lý lặp an toàn và thao tác bù |
| D05 | JSON có thể thay đổi so với API cũ | Phải cập nhật đồng bộ model, validator, ETL và frontend; có phiên bản và ánh xạ rõ ràng |
| D06 | Nhóm tự thiết kế indexing, có chiến lược và lý do | Được dùng cơ chế index của PostgreSQL/MongoDB; không yêu cầu tự lập trình B+ tree/bộ máy indexing |
| D07 | Dữ liệu seed dùng cho demo và benchmark | Quy tắc định tuyến phải áp dụng cho cả seed và dữ liệu mới |
| D08 | Phân mảnh dọc đặt trên hai máy | Mục tiêu chuyển hồ sơ người dùng sang B; dữ liệu xác thực và ví giữ tại A |
| D09 | Site cần thiết bị lỗi thì thao tác trả lỗi | Không trả danh mục toàn cục thiếu dữ liệu mà coi là đầy đủ; dùng lỗi có cấu trúc |
| D10 | Cho phép dựng sạch môi trường đồ án | Xóa chỉ khi gọi rõ thao tác reset; restart/up bình thường giữ dữ liệu |
| D11 | Có backup và restore tùy tình huống | Phải diễn tập restore, không dùng seed hoặc Mongo replica set thay backup toàn hệ thống |
| D12 | HA nhiều host và Mongo failover nâng cao | Tùy chọn cuối cùng; không thuộc điều kiện hoàn thành bắt buộc |

### 1.2. Lựa chọn kỹ thuật của kế hoạch

Để phù hợp tài nguyên, kế hoạch chọn một MongoDB dùng chung và một MinIO dùng chung cho cả A/B, đặt trên máy thật. B chạy PostgreSQL; không nhân toàn bộ stack lên VM. Đây là lựa chọn thiết kế từ giới hạn tài nguyên, không phải yêu cầu mỗi site phải có đủ mọi loại CSDL.

Nguồn PostgreSQL nghiệp vụ hiện tại và module `oldshop_1`/`oldshop_2` đang là các đường triển khai khác nhau. Khi tích hợp, chọn PostgreSQL A làm nguồn nghiệp vụ chuẩn trong **môi trường đồ án mới**: schema ứng dụng được dựng tại A, có extension danh mục phân tán. Không duy trì thêm một database commerce thứ ba rồi để frontend đọc ba tập sản phẩm không thống nhất. Tên database có thể giữ `oldshop_1` ở A và `oldshop_2` ở B; kết nối ứng dụng phải trỏ đúng nguồn đã chọn.

Không sửa checksum hoặc nội dung migration 001–007 để che thay đổi. Phần bootstrap phân tán và migration mới phải có lịch sử riêng, khai báo rõ schema nào chạy tại A, schema nào chạy tại B. Chưa ấn định số migration tiếp theo trước khi kiểm tra repository lúc triển khai.

### 1.3. Mức ưu tiên

- **P0:** luồng bắt buộc, sơ đồ bằng chữ, phân mảnh, hợp đồng JSON, thiết kế index, bằng chứng before/after, reset và backup/restore.
- **P1:** tăng kích thước benchmark, tối ưu thêm index/ETL khi có số đo, hoàn thiện trình bày và tổng duyệt.
- **P2:** checkout xuyên site, Mongo failover nâng cao, tự động failover PostgreSQL, HA nhiều host.

Không bỏ phân mảnh dọc khác máy rồi ghi hoàn tất. Nếu P0 không đạt trước hạn, giữ phiên bản demo ổn định và ghi rõ phần chưa đạt; không thay đổi tiêu chí bằng cách sửa mô tả kết quả.

## 2. Hiện trạng đối chiếu và khoảng cách cần hoàn thiện

| Hạng mục | Có trong repository | Cần làm trong đợt này |
|---|---|---|
| PostgreSQL nghiệp vụ | DDL, migration 001–007, ORM, partition order/log, bốn bảng user | Chọn A làm nguồn chuẩn; giải quyết schema/ORM khi profile chuyển sang B |
| MongoDB/MinIO/ETL | Document model, validator, metadata service, outbox, worker, media cleanup | Mở đường ghi metadata có kiểm quyền; nhận product events từ A và B; cleanup kiểm cả hai nguồn |
| JSON | `documents.py`, schema API và bộ chuyển BSON | Thống nhất phiên bản, quy tắc ID/tiền/thời gian, cập nhật frontend và ví dụ sinh từ model |
| Indexing | Catalog JSON, snapshot, release, CLI apply/verify, migration và evidence | Chọn workload cần bảo vệ, rà index thừa/trùng, đo before/after trên môi trường riêng |
| Hai site | SQL ownership/ID, FDW, global views, gateway chỉ đọc, kiểm chứng cùng Docker host | Kết nối máy thật–VM; tích hợp API đọc/ghi và frontend; quản lý reference data |
| Phân mảnh dọc | `user_core/profile/secret/wallet` trong cùng PostgreSQL | Chuyển profile thật sang B, xử lý toàn vẹn logic và lỗi mạng, loại phụ thuộc ORM cùng DB |
| Backup | `backup-db.sh`/`restore-db.sh` cho stack cũ | Bộ backup đồng bộ cho PG A/B, Mongo và object MinIO; restore và đối soát |

Evidence lịch sử chỉ chứng minh lượt chạy và phạm vi ghi trong evidence. Không dùng PASS của module hai container cùng host làm bằng chứng đã triển khai qua VM; không dùng benchmark after-only hiện tại làm số đo before/after mới.

## 3. Khái quát các sơ đồ bằng chữ

### 3.1. Sơ đồ ngữ cảnh hệ thống

Tác nhân gồm khách xem tin, người dùng mua/bán, moderator và admin. Tất cả truy cập Angular qua một địa chỉ ứng dụng. Angular gọi FastAPI; FastAPI xác thực, kiểm quyền và điều phối dữ liệu. Client không biết credential database và không kết nối trực tiếp PostgreSQL, MongoDB hoặc MinIO.

Người bán gửi dữ liệu sản phẩm; hệ thống xác định site từ tài khoản và ghi đúng mảnh. Người xem gửi điều kiện danh mục; hệ thống hợp sản phẩm A/B rồi lọc, sắp xếp và phân trang. Moderator thay trạng thái tin ở site sở hữu. Admin quản lý tài khoản, cấu hình site và kiểm tra tình trạng đồng bộ. Luồng thanh toán cũ vẫn thuộc A, trừ khi hoàn thành phần mở rộng checkout xuyên site.

### 3.2. Sơ đồ thành phần

Theo chiều từ ngoài vào trong: Angular; API router và DTO; service nghiệp vụ; lớp catalogue repository/site router, profile service, metadata service, storage service; các adapter PostgreSQL A/B, MongoDB và MinIO.

Theo chiều xử lý nền: transaction PostgreSQL tạo outbox; worker lấy event từ từng nguồn; transformer tạo document; loader upsert MongoDB; ACK ghi về đúng nguồn. Media cleanup chỉ xóa object sau khi kiểm tra đầy đủ tham chiếu. Index catalog và model JSON là đầu vào cấu hình/kiểm tra; chúng không thay thế DBMS hoặc kho lưu byte.

### 3.3. Sơ đồ triển khai

Máy thật Linux Mint 22.3, kernel người dùng cung cấp `6.17.0-40-generic`, RAM tổng 8 GB, ổ tổng 234 GB. Máy này chạy A, API/frontend, worker, Mongo một member và MinIO. VM Ubuntu 24.04.4 LTS, kernel người dùng cung cấp `6.8.0-14-generic`, RAM 2 GB, ổ tổng 12 GB, chạy PostgreSQL B. Các thông số này phải được kiểm tra lại khi triển khai, không phải số tài nguyên còn trống.

A kết nối B bằng endpoint VM truy cập được qua mạng host-only hoặc bridge theo môi trường. Không dùng IP Docker bridge cũ làm IP liên máy. Khai báo `SITE_A_ENDPOINT`, `SITE_B_ENDPOINT`, database identity, site marker và role trong cấu hình môi trường. Dùng script khởi tạo FDW, user mapping, view và quyền; không nhập credential/tạo foreign table thủ công sau mỗi lần reset.

### 3.4. Sơ đồ đọc danh mục hợp nhất

Angular gửi bộ lọc; API kiểm cú pháp/quyền; nếu lọc attributes thì Mongo trả tập ID phù hợp; PostgreSQL A đọc view hợp local A và foreign table B; điều kiện visibility, category, giá, seller và candidate ID áp dụng trước pagination. Sau đó lấy ảnh theo batch và ghép metadata. API trả items, total, pagination và trạng thái nguồn.

Không lấy một trang riêng tại mỗi site rồi ghép thành trang toàn cục. Không dùng Mongo projection giá/stock thay giá/stock PostgreSQL. Các trường sort của hợp đồng phải khớp SQL: không gọi sort theo view_count là sort rating. Khi B lỗi, truy vấn toàn cục trả 503, không trả một nửa danh mục.

### 3.5. Sơ đồ ghi và đồng bộ

Request đã xác thực đi qua site router; seller mapping xác định owner; transaction tại owner ghi product, quan hệ ảnh và outbox. Metadata/attributes được xử lý qua operation có trạng thái, version và idempotency key. Worker đọc đúng nguồn, upsert các trường được phép và ACK nguồn đó. Retry không tạo sản phẩm/document trùng và không ghi đè metadata mới bằng event cũ.

Upload byte vào object key bất biến trước khi liên kết nghiệp vụ. Nếu liên kết thất bại, đánh dấu object tạm để dọn; nếu một bước chưa xong, phản hồi trạng thái pending thay vì tuyên bố toàn bộ dữ liệu đã hoàn tất. Không giữ transaction PostgreSQL mở trong lúc gọi Mongo/MinIO qua mạng.

### 3.6. Sơ đồ vận hành và phục hồi

Một bộ cấu hình xác định môi trường; thao tác up/restart giữ dữ liệu; reset xóa đúng dữ liệu của môi trường rồi dựng schema và seed; backup tạo bộ snapshot logic có manifest; restore nạp lại từng kho, cấu hình lại kết nối và chạy đối soát. Backup đặt ngoài volume bị reset. Khi site chỉ bị dừng, khởi động lại và kiểm tra kết nối; chỉ restore khi dữ liệu đã mất/hỏng hoặc cần quay lại bản backup.

## 4. ERD khái niệm: gói gọn dữ liệu theo thực thể nghiệp vụ

### 4.1. Thực thể khái niệm

ERD khái niệm mô tả ý nghĩa và quan hệ, không coi mỗi bảng kỹ thuật là một thực thể độc lập. Các nhóm dưới đây ánh xạ về ERD vật lý hiện có; không tạo thêm bảng chỉ vì có tên khái niệm.

| Thực thể khái niệm | Ý nghĩa | Bảng/kho hiện có hoặc mục tiêu |
|---|---|---|
| Tài khoản | Danh tính, hồ sơ, xác thực, ví và quyền của một người dùng | `user_core`, `user_profile`, `user_secret`, `user_wallet`, `role`, `user_role` |
| Tin đăng/Sản phẩm | Hàng hóa được seller đăng bán, trạng thái kiểm duyệt, giá, stock, mô tả và thuộc tính | PG `product`; Mongo `product_details` cho attributes và projection |
| Danh mục | Phân loại tin đăng, có thể có danh mục cha | `category`; hợp đồng attributes theo category là thiết kế bổ sung |
| Tài nguyên số | Byte media và metadata/tham chiếu dùng bởi sản phẩm hoặc hồ sơ | `product_image`, `avatar_url`, reference trong Mongo, object MinIO |
| Giỏ hàng | Danh sách sản phẩm người mua dự định mua | `shopping_cart`, `shopping_cart_item` |
| Đơn hàng | Một lần đặt mua gồm nhiều dòng hàng, địa chỉ nhận, giảm giá | `order`, `order_detail`, `contact_info`, `voucher`; Mongo `order_snapshots` chỉ là bản đọc |
| Thanh toán/Giao dịch | Phương thức và kết quả chuyển tiền liên quan đơn/tài khoản | `transaction`, `payment_method`, dữ liệu ví trong Tài khoản |
| Tương tác và kiểm duyệt | Đánh giá, báo cáo, xử lý vi phạm, yêu cầu hỗ trợ | `review`, `violation_log`, `system_feedback`; các projection Mongo tương ứng |
| Site và phân bổ | Vị trí sở hữu dữ liệu và quy tắc định tuyến | `site_config`, `seller_site`, installation/site identity, reference version |
| Vận hành dữ liệu | Sự kiện, lần chạy ETL, lỗi, trạng thái đồng bộ và báo cáo | `etl_outbox`, `etl_runs`, `etl_state`, `etl_time_origin`, `media_deletions`, `system_log`, `report_daily_sales`, `etl_errors` |

### 4.2. Quan hệ khái niệm bằng chữ

1. Một Tài khoản đăng bán không hoặc nhiều Sản phẩm; mỗi Sản phẩm có đúng một seller. Tài khoản có thể đồng thời mua và bán.
2. Một Danh mục chứa không hoặc nhiều Sản phẩm; mỗi Sản phẩm thuộc một Danh mục. Một Danh mục có không hoặc một cha và có thể có nhiều con.
3. Một Sản phẩm có không hoặc nhiều quan hệ ảnh/media. Một object có thể được tham chiếu nhiều lần; không suy ra quan hệ 1–1 giữa object và bản ghi ảnh.
4. Một Tài khoản có tối đa một Giỏ hàng; Giỏ hàng và Sản phẩm liên hệ nhiều–nhiều qua dòng giỏ và số lượng.
5. Một Tài khoản đặt không hoặc nhiều Đơn hàng. Đơn hàng hợp lệ có ít nhất một dòng; mỗi dòng tham chiếu một Sản phẩm. Quy tắc ít nhất một dòng do nghiệp vụ kiểm soát, không suy từ FK.
6. Một Đơn hàng có không hoặc nhiều Giao dịch. Một phương thức thanh toán phục vụ nhiều giao dịch/đơn. Một voucher có thể áp dụng nhiều đơn theo chính sách.
7. Một Tài khoản viết nhiều đánh giá/báo cáo; một Sản phẩm nhận nhiều đánh giá/báo cáo. Dùng `type`/rating phù hợp thay vì biến mọi review thành report.
8. Một Tài khoản có nhiều quyền qua membership. Moderator/admin là vai trò, không phải thực thể người dùng riêng.
9. Một seller được gán đúng một Site trong phiên bản này; một Site sở hữu nhiều Sản phẩm. Ảnh thuộc cùng mảnh với Sản phẩm.
10. Một sự thay đổi nguồn có thể tạo event đồng bộ; event/runs liên quan dữ liệu bằng ID logic, không giả định có FK xuyên PostgreSQL–MongoDB–MinIO.

Ở mức khái niệm, Tài khoản vẫn là một thực thể dù các cột đặt ở hai máy. `product_details` và `order_snapshots` không tạo thêm một Sản phẩm hay Đơn hàng nghiệp vụ mới. Contact/address là nhóm phụ thuộc Tài khoản/Đơn hàng; không đưa địa chỉ nhận hàng vào Mongo chỉ để làm document đầy đủ hơn.

## 5. Hợp nhất ba kho và chiến lược cấu trúc JSON

### 5.1. Nguồn ghi chuẩn

| Nhóm dữ liệu | Nguồn chuẩn | Nơi khác được giữ gì? |
|---|---|---|
| Product ID, owner/site, category, title, description, price, quantity, visibility, moderation | PostgreSQL tại owner A hoặc B | Mongo giữ projection allowlist; API lấy giá/stock/trạng thái từ PG |
| Attributes và tags do seller nhập | MongoDB dùng chung | API validate và trả về; ETL không ghi đè bằng giá trị rỗng |
| Quan hệ ảnh và metadata upload | PG tại owner; avatar reference ở profile B | Mongo giữ reference cần thiết, không sở hữu byte |
| Byte ảnh/video/avatar | MinIO | PG/Mongo chỉ giữ reference; không nhúng base64 vào document sản phẩm |
| Core/xác thực/ví | PostgreSQL A | Không xuất secret/token/balance sang Mongo projection công khai |
| Hồ sơ người dùng | PostgreSQL B trong mô hình đích | API riêng tư trả trường theo quyền; không replicate toàn PII về A |
| Order/payment hiện có | PostgreSQL A | Mongo snapshot phục vụ đọc/báo cáo, không quyết định số dư hoặc thanh toán |

### 5.2. JSON tương tác với những gì?

| Hợp đồng | Bên tạo và bên nhận | Mục đích | Nguồn định nghĩa |
|---|---|---|---|
| JSON request/response | Angular và FastAPI | Truyền lệnh nghiệp vụ và mô hình hiển thị | DTO Pydantic, OpenAPI; TypeScript được sinh hoặc đối soát cùng phiên bản |
| JSON/document contract | ETL/metadata service và MongoDB | Document ổn định, nested attributes/media, validation | `backend/app/schemas/documents.py`; BSON validator sinh qua `mongo_schema.py` |
| Event/outbox contract | PG nguồn, worker, retry/replay | Nhận diện nguồn, entity, thao tác, version | Schema sự kiện cần bổ sung, lưu JSONB trong PG theo thiết kế |
| JSON index catalog | Công cụ validate/plan/apply và PG/Mongo | Cấu hình index mong muốn, version, snapshot | `database/indexing/catalog.json` và schema/parser |
| Manifest backup/evidence | Script vận hành và người kiểm chứng | Ghi phiên bản, nguồn, checksum, kết quả | Schema manifest riêng; không chứa credential |

JSON là hợp đồng biểu diễn và trao đổi; PostgreSQL vẫn lưu bảng, Mongo lưu BSON, MinIO lưu byte. Không ép các kho có hình dạng vật lý giống nhau. Không có một schema duy nhất dùng chung nguyên xi cho request ghi, document ETL và response công khai.

### 5.3. Khung cấu trúc sản phẩm mục tiêu

Document `product_details` tiếp tục tận dụng các trường hiện có: `_id`, `schema_version`, `product_id`, `category_id`, `description`, `attributes`, `tags`, `images`, `updated_at`, `deleted`, `etl`. Bổ sung `source_site` và revision nguồn nếu triển khai hai nguồn. Khi đổi required/kiểu phải tăng version và cập nhật dữ liệu seed/validator tương ứng; không gắn nhãn một payload mới là schema v1 hiện hành.

| Nhóm field | Thiết kế và mục đích |
|---|---|
| Identity | Product ID duy nhất toàn cục; `_id` có namespace rõ; `source_site` kiểm tra đúng owner, không là nguồn thứ hai thay `seller_site` |
| Attributes | Object có key được kiểm soát, giá trị theo hợp đồng danh mục; ví dụ điện thoại có brand/ram_gb/storage_gb, quần áo có size/material |
| Tags | Array chuỗi chuẩn hóa, giới hạn số lượng/độ dài, loại trùng |
| Images | Array reference gồm image ID, bucket, key, MIME, size, primary/order; không lưu byte |
| ETL | Thời gian đồng bộ UTC, nguồn, revision, run ID; nguồn nào cập nhật projection nào phải truy vết được |
| Lifecycle | Tombstone/deleted, source revision, trạng thái operation; chống event cũ làm sống lại sản phẩm đã xóa |

Request ghi không được nhận tùy ý `seller_id`, `site_id`, trạng thái duyệt hoặc field ETL từ client. Các field này được server quyết định. Frontend gửi attributes hợp lệ nhưng không gửi toán tử MongoDB. Giữ giới hạn lọc hiện có hoặc thay đổi có kiểm chứng; không bỏ cap candidate và không cắt ngầm kết quả.

API sản phẩm đề xuất có các nhóm `identity`, `catalogue`, `pricing`, `metadata`, `media`, `sync`; đây là **DTO mục tiêu**, không khẳng định endpoint hiện tại đã có các object đó. Có thể giữ response phẳng để giảm thay đổi nếu vẫn mô tả hợp đồng đầy đủ; chọn một cách trước khi frontend tích hợp. Trong đợt này ưu tiên giữ phần core DTO hiện có, chỉ thêm field site/sync và sửa phần thực sự cần thiết.

### 5.4. Quy tắc xuyên tầng

- ID JSON dùng chuỗi thập phân ở các hợp đồng mới để tránh giới hạn số nguyên JavaScript; adapter chuyển về kiểu số PostgreSQL/BSON phù hợp. Nếu giữ ID số cũ, phải ràng buộc trong miền số nguyên an toàn của JavaScript. Không trộn hai cách trong cùng endpoint/version.
- Tiền API dùng chuỗi thập phân kèm currency `VND`; PG giữ NUMERIC. Snapshot `_vnd` hiện là số nguyên: phải kiểm tra giá trị không có phần lẻ hoặc từ chối/chuyển version rõ ràng; không âm thầm làm tròn NUMERIC(18,4).
- Thời gian API dùng ISO 8601 UTC có offset; BSON dùng date; báo cáo ngày theo Asia/Ho_Chi_Minh. Các timestamp PG cũ chưa có timezone cần quy tắc chuyển đổi tường minh.
- Phân biệt field thiếu, `null`, object rỗng và array rỗng. PATCH chỉ cập nhật field thực sự được gửi. Unknown field ngoài attributes bị từ chối hoặc xử lý theo policy đã khai báo.
- Bảo vệ secret, token, địa chỉ và số điện thoại trong cả response, log, event và evidence. Public seller DTO không tái dùng nguyên `UserResponse` hiện có.
- Model sinh JSON Schema/BSON validator là nguồn chính; ví dụ trong tài liệu phải kiểm tra lại bằng model. Frontend và ETL dùng cùng release hợp đồng, không duy trì snapshot rời không rõ phiên bản.

### 5.5. Quy trình nhất quán nghiệp vụ

1. API xác thực và validate; cấp operation ID/idempotency key. Với request lặp cùng key nhưng payload khác, báo conflict.
2. Owner PG ghi core và outbox trong một transaction. Nếu có file, upload vào key tạm/bất biến trước và ghi reference bằng luồng có trạng thái; không trả URL như đã công bố khi chưa liên kết xong.
3. Worker nhận event có khóa `(source_site, event_id)` và identity entity. Revision lấy từ nguồn theo cơ chế tăng đơn điệu, không dùng clock giữa hai máy làm thứ tự duy nhất.
4. Mongo partial upsert projection; attributes/tags có đường ghi riêng và revision riêng. Không dùng replace toàn document làm mất dữ liệu Mongo sở hữu.
5. Operation chỉ chuyển ready khi đủ core, metadata cần thiết và media reference. Nếu chưa hoàn tất, trả 202/pending có đường tra cứu; không trả thành công giả. Có thể giữ bản công khai cũ trong lúc sửa bằng staged update; nếu chưa làm staging thì ẩn/báo đang xử lý và ghi rõ hành vi.
6. Lỗi tạm thời: retry có backoff và giới hạn; lỗi dai dẳng: failed/dead kèm lý do; có lệnh replay. Không tự rollback core đã commit bằng một transaction khác mà coi như ACID chung.
7. ACK chỉ sau bước ghi đích cần thiết; crash sau ghi trước ACK được xử lý lặp an toàn. Event đến muộn không ghi đè revision mới/tombstone.
8. Cleanup chỉ xóa object khi kiểm tra cả A, B, Mongo và hàng đợi pending không còn tham chiếu. Không kết nối được một nguồn thì trì hoãn xóa; không suy nguồn lỗi thành không có tham chiếu.

Các trạng thái/field mới và endpoint tra cứu operation ở trên là việc phải triển khai, không phải chức năng đã xác nhận tồn tại.

## 6. Hệ phân tán và lớp tích hợp

### 6.1. Phân bổ dữ liệu mục tiêu

| Dữ liệu | A | B | Mongo/MinIO dùng chung |
|---|---|---|---|
| Core tài khoản, secret, ví, quyền | Nguồn chuẩn | Không sao chép secret/ví | Không đưa vào public projection |
| Profile | Không giữ bản ghi nguồn sau chuyển đổi | Nguồn chuẩn | Chỉ byte avatar ở MinIO; không copy PII sang Mongo |
| Seller mapping/category | Nguồn quản lý chuẩn, có version | Reference tối thiểu phục vụ kiểm owner/FK local | Schema attributes nhận version tương ứng |
| Product/ảnh thuộc seller A | Nguồn chuẩn | Không giữ bản sao product A | Attributes/projection và byte theo ID toàn cục |
| Product/ảnh thuộc seller B | Foreign table để đọc, không copy bảng nguồn | Nguồn chuẩn | Như trên |
| Cart/order/payment hiện hữu | Giữ tại A | Không mở đa site trong P0 | Snapshot A nếu pipeline hiện hữu cần |
| Outbox/runs/checkpoint | Phần của A | Outbox/checkpoint cho nguồn B | Consumer ACK về đúng nguồn |

`deploy/scripts/sites.py` hiện dựng common schema đầy đủ từ ứng dụng tại cả hai site. Không sử dụng nguyên trạng cách đó rồi tuyên bố user đã phân mảnh dọc. Phải tách bootstrap A/B: B chỉ có dữ liệu/bảng cần thiết hoặc các bảng tương thích không mang bản sao nguồn user/secret/wallet. Sau chuyển đổi, kiểm dữ liệu thực và đường đọc thực, không chỉ nhìn tên bảng.

### 6.2. Đọc hợp nhất và ghi định tuyến

**Đọc:** kế thừa `postgres_fdw`, foreign tables và `v_product`/`v_product_image` tại A. Global view dùng UNION ALL vì các mảnh không giao nhau. Reader role chỉ đọc các bảng/view được phép; đường profile dùng role riêng. FDW truy vấn B khi đọc, không sao chép B sang A và không tự đồng bộ reference. Theo tài liệu [PostgreSQL FDW](https://www.postgresql.org/docs/16/postgres-fdw.html), đây là truy cập bảng remote; không suy thành transaction ACID toàn cục hoặc snapshot đồng bộ tuyệt đối giữa hai site.

**Ghi:** API site router lấy owner từ mapping A, xác thực seller/admin rồi mở transaction trên owner. Không INSERT/UPDATE vào UNION view. Không tin site do client truyền và không cho phép thay seller/site của product bằng PATCH thông thường. Các credential writer A/B tách khỏi reader và admin migration.

**Reference:** admin gán seller chưa có sản phẩm vào A hoặc B; tài khoản mới mặc định A. Ghi mapping/version tại A, phát event cập nhật reference tối thiểu ở B; chỉ cho tạo product B khi B đã có version cần thiết. Không hỗ trợ chuyển seller đang có sản phẩm trong P0. Thay category cũng phải có đường cập nhật/version tương tự; không tuyên bố bootstrap giống nhau là replication liên tục.

**ETL:** thêm registry nguồn A/B, checkpoint riêng và tên event đầy đủ namespace. Pipeline product chạy hai nguồn; pipeline order/payment/báo cáo cũ chỉ chạy nguồn A. Không nhân đôi aggregate bằng cách chạy full pipeline commerce trên hai common schema.

**Media:** object key có namespace và định danh bất biến, ví dụ nhóm product/site/product/UUID. Key là quy ước địa chỉ object, không phải cấu trúc index B-tree. Gateway vẫn kiểm quyền khi truy cập dữ liệu private; không mở bucket public để né tích hợp.

### 6.3. Chính sách lỗi

| Thao tác | Khi B mất kết nối | Hành vi bắt buộc |
|---|---|---|
| Danh mục toàn cục/filter/count | Không đủ tập dữ liệu | 503, mã lỗi ổn định, không trả 200 chỉ với dữ liệu A |
| Tạo/sửa/xóa product B | Không xác định commit hoặc không ghi được | Nếu chưa commit thì lỗi; nếu kết quả không rõ thì tra operation/idempotency trước retry; không tạo trùng |
| Thao tác chỉ cần A | Có thể độc lập | Tiếp tục nếu service đã thực sự tách phụ thuộc B; không gọi profile ngầm qua ORM |
| Đọc/sửa profile | Nguồn profile không có | 503 riêng profile; không trả hồ sơ rỗng giả |
| Login core tại A | Không cần profile để kiểm password | Có thể thành công với DTO auth tối thiểu; endpoint `/me` cần profile vẫn có thể lỗi |
| Cleanup media | Không kiểm tra đủ reference | Giữ queue và retry; không xóa object |

Lỗi Mongo/MinIO cũng theo dependency của endpoint: lọc attributes lỗi thì không tự bỏ bộ lọc; upload lỗi không trả thành công; API chỉ cần PG không bị health tổng hợp làm mất chức năng ngoài ý muốn. Phân biệt liveness tiến trình và readiness theo chức năng. Chạy lại bộ outage test vì đây có thể khác hành vi fallback cũ.

### 6.4. Giới hạn tài nguyên và HA

Trước khi dựng: kiểm tra RAM khả dụng, dung lượng trống host/VM, đường mạng, IP/hostname và image/version thực tế. VM 2 GB chỉ chạy PostgreSQL và thành phần quản trị tối thiểu; ưu tiên tái sử dụng image, không build frontend/backend trong VM. Không bật ELK, monitoring nặng, PG standby và Mongo ba member đồng thời khi chưa đo đủ tài nguyên.

Mongo mặc định dùng replica set một member nếu cần giữ topology/transaction API tương thích; cấu hình đó không có redundancy. Profile ba member giữ làm demo replication/election tùy chọn; không tắt hai member của set ba voter rồi kỳ vọng member còn lại vẫn ghi majority.

Ba Mongo member có thể đặt khác site, nhưng sao chép cùng dữ liệu Mongo và không khôi phục PostgreSQL/MinIO. Ba voter cần hai voter còn hoạt động. Host và VM cùng host là một miền lỗi vật lý; mô hình không được gọi là chịu mất host. Xem [MongoDB replica set ba member](https://www.mongodb.com/docs/manual/core/replica-set-architecture-three-members/).

## 7. Chiến lược phân mảnh ngang

### 7.1. Đối tượng, mục đích và vị từ

Đối tượng chính là `product`; `product_image` phân mảnh dẫn xuất. Mục đích: chia quyền sở hữu và thao tác ghi danh mục theo seller/site; chứng minh truy vấn hợp nhất. Chưa có số đo để khẳng định tăng hiệu năng hay cân bằng tải tự động.

Gọi P là tập sản phẩm toàn cục, owner(seller_id) là mapping chuẩn. Mảnh P_A gồm các dòng có owner=A; P_B tương tự B. `site_id` trong product phải khớp owner. Ảnh I_A gồm các dòng ảnh có product_id thuộc P_A; I_B tương tự. Quan hệ ảnh→product có FK trong cùng site.

Seed được phân theo mapping này, không chia tùy tiện 500 dòng đầu/cuối rồi bỏ quy tắc cho dữ liệu mới. Demo cần cả seller A/B, sản phẩm công khai/chờ duyệt/xóa mềm và nhiều sản phẩm trùng ngày/giá để kiểm pagination có tie-break.

### 7.2. ID và reference

Giữ cơ chế ID lẻ A/chẵn B đã có trong module, áp dụng cho product và image khi dựng mới; sequence increment 2 và constraint kiểm owner/remainder. Parity chỉ là cơ chế cấp ID/kiểm tra, mapping owner vẫn là căn cứ nghiệp vụ. Không dùng parity để quyết định product có tồn tại hoặc để bỏ qua quyền.

User ID do A cấp; profile B và seller reference dùng cùng ID. Không cấp user ID riêng ở B. Reference B chỉ chứa các trường cần kiểm owner/active/version, không copy tài khoản kèm password/token. Nếu schema B hiện có FK tới `user_core`, phải thay đường tham chiếu sang reference phù hợp, không đưa toàn bộ core/secret sang B cho tiện bootstrap.

### 7.3. Tính đúng đắn và kiểm chứng

| Tính chất | Điều kiện | Cách kiểm |
|---|---|---|
| Đầy đủ | Mọi product có seller mapping và đúng một owner | Count hợp mảnh bằng expected seed; đối soát IDs cả thao tác mới |
| Không giao nhau | ID duy nhất; constraint owner/parity | Giao tập ID rỗng; ghi sai site/parity bị từ chối |
| Tái tạo | Hình dạng cột hai mảnh tương thích | UNION ALL khớp tập expected, không dùng UNION để giấu duplicate |
| Ảnh đi theo product | FK local và route từ owner product | Ghi ảnh sai mảnh bị chặn; đọc batch đủ ảnh |
| Ghi đúng site | API không tin client site | Tạo/sửa/xóa seller A/B, kiểm DB nguồn và outbox tương ứng |
| Đọc toàn cục đúng | Filter/sort/page toàn tập | So sánh expected/actual nhiều trang, giá/ngày trùng, không duplicate/mất dòng |

Partition `order` HASH và `system_log` RANGE hiện có vẫn là minh họa chia hàng trong một PostgreSQL. Chúng không tự di chuyển dữ liệu sang VM. Giữ để giải thích/pruning nhưng không trộn bằng chứng với phân mảnh product A/B.

## 8. Chiến lược phân mảnh dọc

### 8.1. Phân rã và mục đích

| Mảnh | Cột chính | Nơi nguồn chuẩn | Mục đích |
|---|---|---|---|
| Core | user_id, username, email, trạng thái, trust_score, thời gian | A | Danh tính, login lookup, quan hệ commerce |
| Secret | user_id, password_hash, random_key, verification/reset token/expiry | A, role riêng | Giới hạn đường truy cập xác thực |
| Wallet | user_id, balance | A | Transaction tiền cục bộ, không phân tán ví trong P0 |
| Profile | user_id, full_name, phone_number, address, avatar_url | B | Tách nhóm hồ sơ/PII, truy cập theo nhu cầu và quyền |

Mục đích chính là phân tách trách nhiệm và thu hẹp quyền truy cập; không tuyên bố tách máy tự mã hóa/bảo mật dữ liệu. Email ở core và `contact_info` vẫn là PII tại A. Profile chuyển B không có nghĩa toàn bộ PII đã rời A. B cũng chứa product nên phải dùng role/schema riêng cho profile, không cấp profile SELECT cho catalogue reader.

### 8.2. Tái tạo và toàn vẹn

Gọi U là tập cột user logic ban đầu; các mảnh chứa đủ U, giao nhau về cột chỉ có khóa `user_id` (không tính metadata vận hành bổ sung). Tái tạo bằng JOIN theo user_id khi đủ mảnh và đúng quyền. Phép JOIN để đối soát riêng tư khác DTO public.

Core–secret–wallet ở A vẫn có PK/FK và tạo trong transaction cục bộ. Profile B không có FK xuyên máy tới core A; dùng API, event provisioning và đối soát để bảo đảm toàn vẹn logic. Không mô tả FK local hiện có như vẫn bảo vệ quan hệ sau khi chuyển sang B.

Tạo tài khoản: A tạo core/secret/wallet và event yêu cầu profile, ghi trạng thái provisioning; B upsert profile theo user_id, ACK; API trả pending cho bước hồ sơ nếu chưa hoàn tất. Khi profile chưa có, tái tạo chưa đầy đủ và phải được biểu diễn rõ. Đăng nhập chỉ dùng core/secret không tự đọc association proxy profile. Các chức năng cần hồ sơ chờ ready hoặc trả lỗi tương ứng.

Sửa profile: route tới B, revision và kiểm owner. Xóa tài khoản dùng soft-delete core và event đồng bộ; đối soát để chặn profile mồ côi, không xóa ví/giao dịch lịch sử tùy tiện. Dữ liệu seed tạo đủ các mảnh ngay từ đầu; lỗi giữa chừng phải có retry/replay, không cần DBA ghép tay.

### 8.3. Thay đổi bắt buộc so với code hiện tại

- `backend/app/models/user.py` đang dùng relationship/association_proxy và cascade giữa các bảng cùng DB. Tách profile repository/service, bỏ giả định một SQLAlchemy session ghi nguyên tử sang hai database.
- `users_full` hiện JOIN local và các hàm SQL liên quan cần rà soát. View đối soát có thể dùng profile foreign table với role riêng; không dùng view đầy đủ cho mọi auth query.
- Rà public user DTO, `/me`, đăng ký, login, sửa hồ sơ, avatar và admin list. Không trả hash/token; public seller không lộ phone/address/email/balance chỉ vì model có field.
- B không còn chỉ là site danh mục: thêm schema/role profile và outbox provisioning cần thiết; migration A/B riêng. Không giữ bản profile nguồn local ở A rồi tuyên bố đã chuyển dọc.
- Avatar cleanup phải đọc tham chiếu profile B; B lỗi thì dừng cleanup liên quan. Backup B chứa profile, không chỉ product B.

### 8.4. Tiêu chí nghiệm thu

Core/secret/wallet chỉ có nguồn chuẩn tại A, profile chỉ có nguồn chuẩn tại B; JOIN tập seed khôi phục đủ các trường được phép. Tạo tài khoản và sửa profile qua API thành công; retry không tạo trùng. B lỗi thì profile trả 503, login core hoạt động nếu không có phụ thuộc khác. Catalogue reader không đọc được profile/secret; user khác không sửa được hồ sơ. Không có record thiếu mảnh ở trạng thái ready; provisioning lỗi được thống kê và replay được.

## 9. Chiến lược và thiết kế indexing

### 9.1. Index tương tác qua những thành phần nào?

Người dùng tạo workload qua frontend; API/repository phát SQL hoặc Mongo query. DBMS dùng optimizer để chọn scan/index. Index catalog JSON khai báo định nghĩa mong muốn; công cụ validate/plan sinh hoặc áp thay đổi qua migration/driver; verify kiểm catalog thực; benchmark ghi execution plan và chỉ số. JSON catalog không phải nơi chứa B-tree hay posting list vật lý.

Trình tự thiết kế: chọn truy vấn thực tế; xác định equality/range/order/join; chọn cấu trúc và khóa; dự đoán lợi ích/chi phí; đo before/after; quyết định giữ/sửa/bỏ. Index tại A/B được tạo trên bảng local có dữ liệu. Không tạo B-tree lên UNION view hoặc coi foreign table A có index vật lý của product B; index B phải được tạo tại B và kiểm remote plan.

### 9.2. Cấu trúc tổng quát phải giải thích được

| Cấu trúc | Ý nghĩa cần trình bày | Áp dụng trong đồ án |
|---|---|---|
| B-tree đơn/ghép | Entry khóa có thứ tự, trỏ tới dữ liệu; leading keys ảnh hưởng cách tìm/range/order | Danh mục theo ngày/giá, seller, ảnh theo product, lịch sử đơn |
| Partial index | Chỉ giữ entry của dòng thỏa predicate | Danh mục công khai/chưa xóa, queue chưa xử lý |
| GIN trigram | Tra ngược các đoạn chuỗi tới tập dòng phù hợp | Tìm title/description bằng ILIKE nếu query hiện hành tương thích |
| Mongo compound | Khóa nhiều field theo thứ tự, phục vụ các prefix/pattern phù hợp | category và brand; review theo product/date |
| Mongo wildcard | Index các đường dẫn attributes thay đổi | Lọc thuộc tính ngoài các field phổ biến; không hứa bao phủ mọi tổ hợp |
| Unique/PK | Bảo vệ identity/toàn vẹn, có chi phí duy trì | Giữ trong cả before/after, không lấy tác dụng unique làm bằng chứng tăng tốc |

Theo [PostgreSQL multicolumn indexes](https://www.postgresql.org/docs/16/indexes-multicolumn.html), khóa đầu của B-tree ghép có vai trò quan trọng. Quy tắc thiết kế phải dựa vào query thật, không chỉ đặt các cột hay dùng vào cùng một index. Không lập chỉ mục toàn bộ field, không thêm index boolean riêng mặc định cho mọi bảng.

### 9.3. Workload và index PostgreSQL được chọn

Các định nghĩa có chữ **ứng viên** là đề xuất cần benchmark, chưa phải DDL đã tồn tại. Trước khi thêm phải so với catalog để tránh index trùng. `V` nghĩa là `status=1 AND is_deleted=false`. Danh sách dưới đây tập trung vào các đường chạy cần bảo vệ, không cam kết tất cả index kế thừa đều có ích.

| Mã | Bảng/site | Query/pattern | Khóa, cấu trúc, predicate | Lý do và trạng thái |
|---|---|---|---|---|
| PG01 | product A/B | Danh mục công khai mới nhất, tie-break ID | B-tree `(created_at DESC, product_id ASC)`; V | Có `idx_product_visible_date_id`; khớp thứ tự danh mục toàn cục, giảm sort khi planner chọn |
| PG02 | product A/B | Lọc category rồi sort mới nhất | B-tree `(category_id, created_at DESC, product_id ASC)`; V | Ứng viên mở rộng index category/date hiện có; equality trước order/tie-break, không thêm song song nếu trùng lợi ích |
| PG03 | product A/B | Category và khoảng giá/sort giá | B-tree `(category_id, price ASC, product_id ASC)`; V | Ứng viên cho một mode sort giá cụ thể; không phục vụ tối ưu đồng thời mọi sort ngày/giá |
| PG04 | product A/B | Seller quản lý tin theo trạng thái/ngày | B-tree `(seller_id, status, created_at DESC, product_id ASC)`; `is_deleted=false` | Ứng viên nếu query có seller+status; với mọi status có thể vẫn cần sort. Đo so với seller index hiện có |
| PG05 | product A/B | `title ILIKE` hoặc `description ILIKE` | GIN `title gin_trgm_ops` và `description gin_trgm_ops`; V | Có hai index trigram; OR hai nhánh cần xét cả hai, không dùng index tsvector làm bằng chứng cho ILIKE |
| PG06 | product_image A/B | Batch ảnh theo product IDs, order hiển thị | Index `product_id` hiện có; thử B-tree `(product_id, display_order, image_id)` | Giảm tập đọc và có thể giảm sort; chưa khẳng định thứ tự primary/order của mọi query đều được bao phủ |
| PG07 | product_image A/B; profile B | Kiểm reference trước xóa object/avatar | B-tree `image_url`; B-tree `avatar_url`, không unique | Có trong migration 007 trước chuyển site; kiểm cả bản ghi soft-delete và ảnh dùng chung |
| PG08 | order A | Buyer history theo ngày | B-tree `(buyer_id, order_date DESC)`; `is_deleted=false` | Có index kế thừa trên các HASH partition; buyer query không tự prune theo order_id |
| PG09 | order_detail A | Dòng hàng theo order; sản phẩm liên quan đơn | `order_id`; `(product_id, order_id)` | Có sẵn; hai prefix phục vụ hai hướng JOIN khác nhau |
| PG10 | etl_outbox mỗi nguồn | Event đến hạn, entity retry, thứ tự event | Các index pending/event và entity/key/event hiện có | Phải đo backlog phi rỗng; range available_at và ORDER BY event_id có đánh đổi, không giữ cả hai chỉ vì có sẵn |
| PG11 | user_profile B và user_core A | Ghép user theo ID, login | PK user_id; UNIQUE email/username | Index ràng buộc nền, không cần index phone/address để chứng minh bảo mật |
| PG12 | system_log A | Audit khoảng thời gian | RANGE pruning theo created_at và index partition phù hợp | Workload bổ sung nếu đủ thời gian; tách lợi ích pruning khỏi lợi ích index |

Không thêm `site_id` làm khóa đầu chỉ để “có phân tán”: trong một fragment, site_id gần như hằng số nên ít giá trị chọn lọc. Không dùng index `is_active`/`status` đơn lẻ trên tập nhỏ làm điểm nhấn nếu chưa có số đo. Giá/title/source ở Mongo không thay query PG chỉ để dễ có IXSCAN.

### 9.4. Workload và index MongoDB được chọn

| Mã | Collection | Query/pattern | Khóa/options | Lý do và trạng thái |
|---|---|---|---|---|
| MG01 | product_details | Lookup/upsert một product | `product_id:1`, UNIQUE | Có sẵn; identity toàn cục; `source_site` là provenance, không tạo identity khác cho cùng ID |
| MG02 | product_details | Category + brand, chỉ document sống | `{category_id:1, attributes.brand:1}`, cân nhắc partial `{deleted:false}` | Có compound không partial tương ứng; ứng viên đổi options phải có release/migration rõ, không sửa index cùng tên âm thầm |
| MG03 | product_details | Thuộc tính động như ram_gb/size | `attributes.$**:1` | Có sẵn; benchmark field phổ biến và ít phổ biến; không bảo đảm mọi AND/sort dùng được một wildcard index |
| MG04 | product_details | Shared object reference còn sống | `images.key:1`, partial `{deleted:false}` | Có sẵn; image array tạo multikey; query kiểm cả bucket và key, có thể thử compound bucket/key nếu dữ liệu yêu cầu |
| MG05 | reviews | Review sản phẩm mới nhất | `{product_id:1, created_at:-1}` | Có sẵn; cần seed review nếu dùng làm workload, không đo collection rỗng |
| MG06 | order_snapshots | Buyer history | `{'buyer.id':1, order_date:-1}` | Có sẵn; workload bổ sung từ A, không tuyên bố checkout B hoàn tất |

Compound dành cho field phổ biến và wildcard dành cho phần mở rộng cần được so sánh, không giữ tất cả theo thói quen. Mongo `_id_` và unique product_id có ý nghĩa identity khác nhau; trong before không bỏ ràng buộc cần thiết để làm số đo đẹp hơn. Text index chỉ được đưa vào nhóm nghiệm thu nếu API thật dùng `$text`; TTL là retention, không phải cơ chế backup hay phân mảnh.

### 9.5. Thiết kế benchmark trước/sau

**Môi trường:** database/project benchmark riêng, tên và credential riêng; không drop index ở môi trường demo đang phục vụ. Seed deterministically với seed/version cố định, ghi script hash, query hash, engine/image version, hardware, rows/counts và index inventory trước mỗi lượt.

**Quy mô:** 1.000 sản phẩm để smoke; mục tiêu 10.000 sản phẩm toàn cục chia A/B và số document Mongo tương ứng; 50.000 chỉ khi RAM/đĩa/thời gian cho phép. Phân bố category/seller/giá/visibility có lệch thực tế, có nhiều giá trị trùng và attributes đa dạng. Seed product_image và outbox backlog để PG06/PG10 có ý nghĩa. Nếu chọn PG08/MG05/MG06 thì phải seed đơn/review/snapshot; không tự nhân mọi bảng chỉ để tăng count.

**Before:** giữ PK/UNIQUE và hạ tầng cần tính đúng, bỏ có kiểm soát nhóm application index đang đánh giá trong môi trường benchmark. Lưu chính xác index nào còn lại. Có thể dùng hai dataset clone từ cùng seed hoặc một dataset bất biến; `ANALYZE`/statistics cùng quy trình cho hai pha. Không tắt seqscan hoặc bắt hint ở phép đo chính.

**After:** chỉ thêm nhóm index ứng viên đã định nghĩa; dữ liệu/query/params/engine/tài nguyên không đổi. Đo từng nhóm hoặc giải thích rõ phép đo là cả gói index, không gán lợi ích riêng cho một index khi thay nhiều thứ cùng lúc.

**Lặp:** khởi động workload bằng 3 lượt warm-up không tính; ít nhất 10 lượt đo/query mỗi pha. Ghi toàn bộ mẫu và median; min/max hỗ trợ đọc độ dao động. Không quảng bá p95 ổn định từ số mẫu nhỏ. Chọn warm-cache làm điều kiện chính; không gọi cold-cache nếu chưa kiểm soát cache OS/DB. Chạy hai pha tuần tự trong điều kiện ít tác vụ nền và ghi thứ tự; lặp lại/đảo thứ tự nếu thấy chênh lệch bất thường.

**Chỉ số:** PG `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` cho query đọc, planning/execution, rows/buffers/sort; Mongo explain executionStats, nReturned, totalDocsExamined, totalKeysExamined, winningPlan. Lưu raw plans, không chỉ ảnh chụp hoặc số phần trăm. Ghi dung lượng index, thời gian build và phép ghi batch riêng để minh họa chi phí INSERT/UPDATE; dùng bản clone hoặc reset dữ liệu để before/after ghi có cùng đầu vào.

**Hai site:** đo local A, local B, global FDW và HTTP riêng. Remote SQL/index pushdown phải kiểm bằng plan thích hợp; global time có network và ghép kết quả, không quy toàn bộ chênh lệch cho index. Query trả cùng tập kết quả trước/sau; tổng count/filter/page được kiểm đúng trước khi so thời gian.

**Kết luận:** tỷ lệ cải thiện tính từ median cùng đơn vị khi giá trị after khác 0; với Mongo executionTimeMillis=0 do độ phân giải, báo không đủ độ phân giải thay vì chia 0. Seq Scan thắng trên bảng nhỏ là kết quả hợp lệ. Không có ngưỡng tăng tốc bắt buộc đặt trước; nghiệm thu thiết kế và tính trung thực của phép đo, giữ index khi lợi ích/chi phí có căn cứ.

### 9.6. Cấu hình và vòng đời index

Tái sử dụng `catalog.json`, `catalog.schema.json`, CLI `scripts.indexes`, snapshot/release và các driver PG/Mongo hiện có. Gắn mỗi index được nghiên cứu với workload ID, lý do, dự kiến và evidence trong tài liệu companion; parser đang strict nên không tự thêm field tùy ý vào JSON catalog nếu chưa cập nhật schema/tooling.

Thay đổi index qua migration/release mới; giữ ownership của constraint index. Có bước validate, plan, apply, verify và kiểm đúng database/site. Index phục vụ product phải xuất hiện ở A/B; avatar index ở B sau chuyển profile. Đổi options cùng tên phải báo conflict hoặc có quy trình thay thế rõ; rollback không xóa ràng buộc nghiệp vụ.

## 10. Reset, backup và khôi phục

### 10.1. Giao diện vận hành cần xây dựng

Các tên dưới đây là **giao diện đề xuất**, chưa phải script đã tồn tại:

| Thao tác | Đầu vào | Kết quả |
|---|---|---|
| `up` / `restart` | Environment/site config | Giữ dữ liệu, kiểm dependency và version |
| `reset-demo` | Environment ID, tùy chọn backup trước | Dừng writer/worker, xóa đúng DB/volume của demo, dựng A/B/Mongo/MinIO và seed |
| `backup-all` | Environment ID và thư mục đích | Bộ backup đủ bốn nguồn dữ liệu và manifest |
| `restore-all` | Backup ID, environment đích | Restore từng kho, cấu hình kết nối, đối soát rồi mở phục vụ |
| `verify-demo` | Environment ID | Kết quả identity/schema/count/invariant/API/health |

Reset phải giới hạn theo project/volume/bucket/database được khai báo; không dùng Docker prune toàn máy hoặc xóa mọi bucket. In ra phạm vi xóa; automation có thể dùng cờ explicit cho đúng môi trường. Không xóa source code, cấu hình ngoài phạm vi hoặc thư mục backup. Chạy reset hai lần phải ra cùng dataset logic, không tăng bản ghi trùng.

### 10.2. Bộ backup đầy đủ

1. Tạm dừng request ghi, provisioning, worker và cleanup; drain các operation có thể hoàn thành hoặc ghi rõ pending. Các queue pending được backup để replay được.
2. Dump PostgreSQL A và B kèm schema, constraints, sequence và outbox/state. Lưu cách tái tạo role/FDW từ cấu hình, không công khai password trong manifest.
3. Dump MongoDB: attributes/tags là dữ liệu nguồn không thể tái dựng đầy đủ từ PostgreSQL. Lưu validator/index definitions và catalog state cần thiết.
4. Sao lưu object MinIO cùng bucket/key và metadata cần thiết để phục hồi; PG dump hoặc tar volume media cũ không mặc định chứa object MinIO hiện tại.
5. Manifest ghi backup ID, phiên bản app/schema/seed/index, danh sách artifact, hash, thời gian, identity các DB, counts và trạng thái pending. Không gọi các dump đang có writer chạy độc lập là một snapshot nguyên tử chung.
6. Đặt backup ngoài volume reset, kiểm đủ artifact/checksum rồi mới mở lại writer. Backup cùng host chỉ hỗ trợ reset/hỏng dữ liệu; muốn chịu mất host phải có bản ở nơi độc lập.

Script `deploy/scripts/backup-db.sh` hiện nhắm service `postgres` của stack cũ và archive `oldshop_media_data`; `restore-db.sh` chỉ restore PG. Không tuyên bố hai script này đã bao phủ bộ dữ liệu mới. Có thể tái sử dụng phần dump nhưng phải bổ sung điều phối A/B/Mongo/MinIO và kiểm restore object thật.

### 10.3. Diễn tập bắt buộc

Tạo một sản phẩm và attributes/ảnh mới qua API sau seed, ghi checksum file và ID. Backup toàn bộ; dựng môi trường restore sạch; phục hồi; kiểm tài khoản/profile, mapping, product A/B, attributes và byte ảnh đúng checksum. Replay pending không trùng; sequence cấp ID mới không va chạm; API danh mục và profile hoạt động. Seed lại không được dùng thay cho bước phục hồi dữ liệu phát sinh này.

## 11. Kế hoạch thực hiện cho ba thành viên

### 11.1. Phân công đề xuất

TV1/TV2/TV3 là nhãn vai trò để nhóm gán người thực tế, không suy đoán tên hoặc tình trạng đang làm. Thành viên cùng review hợp đồng trước khi sửa các phần phụ thuộc nhau.

| Vai trò | Chủ trì | Phối hợp và bàn giao |
|---|---|---|
| TV1 — PostgreSQL/phân tán | Bootstrap A/B, mạng VM, FDW, mapping/ID, profile split, quyền và reference | Cung cấp schema/endpoint/repository contract cho TV2; query/index PG cho TV3 |
| TV2 — Tích hợp/JSON | DTO/model/validator, API đọc/ghi, site router, ETL hai nguồn, Mongo/MinIO, frontend | Phối hợp TV1 về provisioning/profile; cung cấp workload thật và luồng restore cho TV3 |
| TV3 — Index/kiểm chứng/vận hành | Chọn workload, catalog/index, seed benchmark, đo before/after, reset/backup/restore, tổng hợp evidence | TV1 hỗ trợ index PG/schema, TV2 hỗ trợ Mongo/ETL và UI demo; cả nhóm cùng restore/tổng duyệt |

Khối lượng TV2 lớn: TV1 phụ trách profile service/repository gắn với schema; TV3 phụ trách script vận hành và evidence để TV2 tập trung catalogue, ETL và frontend. Một file có một người chủ trì chỉnh sửa trong cùng thời điểm để tránh xung đột. Việc chia nhóm không thay yêu cầu review và tích hợp chung.

### 11.2. Lịch đề xuất còn lại

| Mốc giờ Việt Nam | Công việc trọng tâm | Điều kiện bàn giao |
|---|---|---|
| 08/11 — phiên đầu | Audit trạng thái thực, tài nguyên trống, backup hiện có; chốt DTO, phân bổ bảng, mapping, workload và seed | Có commit/version baseline, hợp đồng và danh sách test; VM A↔B kết nối được |
| 08/11 — cuối ngày | TV1 dựng A/B và profile split; TV2 đưa catalogue read/write qua router và nối ETL; TV3 chuẩn bị seed/index before/after và script backup | Có smoke đọc sản phẩm cả hai site, ghi ít nhất một product B, đọc profile B; benchmark chạy thử không đổi dữ liệu demo |
| 09/11 — buổi sáng | Hoàn thiện metadata/media, provisioning/retry, frontend, quyền; chạy benchmark chính trên môi trường riêng | Luồng sản phẩm A/B và tài khoản/profile chạy xuyên suốt; raw before/after đủ workload bắt buộc |
| 09/11 — buổi chiều | Outage/recovery, reset hai lần, backup/restore đủ kho; sửa lỗi P0 | Đạt các gate mục 12; số liệu và giới hạn được thống nhất |
| 09/11 — buổi tối, trước 23:59 | Đóng thay đổi chức năng, tổng duyệt, chốt báo cáo và gói bàn giao | Có phiên bản chạy lại được, evidence, hướng dẫn và danh sách thiếu sót trung thực |

Đây là lịch đề xuất theo thời hạn người dùng, không phải ước lượng bảo đảm hoàn tất. Nếu bắt đầu muộn hơn, giữ thứ tự phụ thuộc và bỏ P2 trước. Không giảm P0 bằng cách chỉ sửa tài liệu; không mở thêm checkout xuyên site khi read/write/restore chưa đạt.

### 11.3. Thứ tự phụ thuộc và quản lý phạm vi

Chốt hợp đồng/identity/phân bổ trước; sau đó schema và bootstrap; tiếp theo repository/site router và ETL; frontend sau khi DTO ổn định; benchmark sau khi query/index ứng viên cố định; cuối cùng outage, restore và tổng duyệt.

Benchmark chuẩn bị song song trên môi trường riêng nhưng kết quả chính phải gắn query/version cuối. Nếu schema/SQL đổi ảnh hưởng workload thì chạy lại đúng phần bị ảnh hưởng. Profile split cần được thử sớm vì tác động tới auth/ORM; không để đến cuối ngày bàn giao mới chuyển máy.

## 12. Ma trận nghiệm thu và bằng chứng

Mọi ô sau là kế hoạch, chưa đánh dấu hoàn thành. Đường evidence đề xuất `docs/evidence/completion-2026-11/`; benchmark `docs/benchmark/completion-2026-11/`. Chỉ tạo output ở đó khi thực sự chạy; không viết PASS giả trong tài liệu.

| Gate | Nội dung kiểm | Điều kiện đạt | Output cần lưu |
|---|---|---|---|
| G01 | Topology/identity | Đúng A máy thật và B VM; DB/site marker, IP/hostname, version được ghi | Inventory tài nguyên khả dụng, endpoint đã che secret, OS/engine/version; ghi cùng host vật lý |
| G02 | Dựng sạch | Reset hai lần ra cùng dataset logic, up/restart giữ dữ liệu | Command/version, seed hash, count/checksum, kết quả idempotency |
| G03 | Ngang/tái tạo | Tập product đầy đủ, không giao, ID đúng owner, ảnh đúng mảnh | Expected/actual IDs/count, negative tests sai site/parity |
| G04 | API danh mục | Read/filter/sort/page toàn cục đúng; create/update/delete A/B đúng quyền | API request/response đã lọc PII, DB reconciliation, frontend smoke |
| G05 | Dọc/tài khoản | Profile nguồn B, core/secret/wallet A; đăng ký/profile/retry chạy, quyền đúng | Phân bố dữ liệu thực, join đối soát, role denial và cross-user denial |
| G06 | JSON | Payload hợp lệ được nhận, sai kiểu/field bị chặn; DTO/validator/frontend cùng release | Schema sinh từ code, version/hash, ví dụ pass/fail, contract test |
| G07 | Hai nguồn ETL | Event A/B ACK đúng nguồn; replay không trùng/ghi đè attributes mới | Event namespace, before/after/replay, backlog, revision và mismatch |
| G08 | Media | Upload/liên kết/gỡ và retry đúng; shared object không bị xóa nhầm | Checksum byte, quyền truy cập, reference test A/B/Mongo; lỗi B giữ queue |
| G09 | Index thiết kế | Mỗi index trọng tâm có query, lý do, loại/khóa/predicate/chi phí; verify đúng site | Catalog/snapshot/plan/apply/verify và bảng workload→index |
| G10 | Benchmark | Có raw before/after cùng điều kiện, cùng kết quả query, không ép index | Manifest, index inventory, raw plans/samples, median, kích thước và phép ghi batch |
| G11 | Lỗi/khôi phục | B dừng thì global/profile lỗi rõ; B lên lại hoạt động; retry không nhân bản | Scenario timeline, HTTP/error code, recovery và data reconciliation |
| G12 | Backup/restore | Dữ liệu thêm sau seed được phục hồi đủ PG A/B, Mongo và byte MinIO | Manifest/hash, restore log, đối soát sequence/attributes/profile/media |
| G13 | Hồ sơ bàn giao | ERD khái niệm, mô tả sơ đồ, giới hạn và số liệu nhất quán với version demo | README/runbook, evidence index, báo cáo cập nhật và kịch bản tổng duyệt |

G04 gồm ít nhất: seller A tạo product A; seller B tạo product B; seller khác sửa bị từ chối; admin/moderator đổi trạng thái đúng owner; ảnh không được gắn vào product người khác; filter attributes kết hợp PG visibility đúng; trang 1/2 không trùng khi nhiều sản phẩm cùng ngày/giá. Không nhận HTML screenshot làm bằng chứng thay cho data reconciliation.

Mục tiêu quan sát đồng bộ cho dataset demo đề xuất không quá 120 giây trong điều kiện dịch vụ khỏe; đây là gate cần đo và điều chỉnh công khai nếu không đạt, không phải SLA hiện có. Đo elapsed từng scenario, backlog và mismatch; không gọi một mẫu đơn lẻ là p95. Timeout endpoint lấy từ cấu hình cụ thể, không để treo vô hạn khi B lỗi.

Checkout cũ được smoke regression trên A. Với product B, nếu checkout đa site chưa làm thì backend phải từ chối rõ bằng mã nghiệp vụ, frontend báo tính năng chưa hỗ trợ; không chỉ ẩn nút trong UI và để API tạo order với FK/product sai. Không sao chép product B vào A để lách FK rồi gọi đó là checkout phân tán.

## 13. Rủi ro và cách xử lý

| Rủi ro | Tác động | Cách xử lý trong phạm vi đồ án |
|---|---|---|
| Chỉ còn 08–09/11, ba người, nhiều phần tích hợp | Không đủ thời gian nếu mở rộng thêm nghiệp vụ | Giữ P0; bỏ checkout/HA trước; thử profile split và VM ngay đầu |
| VM 2 GB/12 GB và host 8 GB | OOM, đầy đĩa, benchmark nhiễu | Kiểm tài nguyên trống; chỉ PG B ở VM; dừng stack phụ không liên quan; tăng seed theo bậc |
| ORM/auth phụ thuộc profile local | Login/list user hỏng khi profile chuyển B | Tách service/profile DTO và rà association_proxy/hàm SQL; test B down sớm |
| Reference A/B lệch version | Ghi product B sai owner/category | Nguồn chuẩn A, version/event/reference check; từ chối ghi khi reference chưa sẵn sàng |
| ETL hai nguồn dùng event_id trùng | ACK nhầm hoặc mất document | Namespace source/event, global entity ID, checkpoint riêng |
| Shared media cleanup chỉ kiểm A | Xóa byte còn được B tham chiếu | Kiểm mọi nguồn; bất kỳ nguồn không truy cập được thì trì hoãn |
| Index hiện có làm mất baseline | Không thể kết luận tăng tốc | Clone/seed benchmark riêng; inventory và bộ index bị thay đổi rõ ràng |
| Tách dọc bị hiểu thành bảo mật hoàn chỉnh | Kết luận vượt bằng chứng | Chỉ ra PII còn ở A, role riêng, DTO private/public, negative tests |
| Replica set bị hiểu là backup mọi kho | Mất dữ liệu PG/object sau reset | Backup/restore từng kho, kiểm byte và attributes nguồn |
| Hai site được trình bày thành hai host vật lý | Báo cáo sai topology | Ghi máy thật + VM cùng host; HA nhiều host là mở rộng |

## 14. Hồ sơ cần hoàn thiện sau triển khai

1. ERD khái niệm theo mục 4 và ERD vật lý cập nhật phân bổ A/B; ghi quan hệ nào là FK local, quan hệ nào được bảo đảm ở tầng ứng dụng.
2. Mô tả sơ đồ ngữ cảnh, thành phần, triển khai, luồng đọc/ghi, JSON/ETL và phục hồi theo mục 3; nếu sau này vẽ hình phải giữ đúng các ranh giới này.
3. Data ownership và allocation matrix; quy tắc mapping/ID, partition trong instance khác phân mảnh giữa site.
4. Hợp đồng JSON/DTO/document/event và ví dụ kiểm bằng model; mapping PostgreSQL–Mongo–API–frontend, không dùng ví dụ giả làm output thực thi.
5. Thiết kế index có workload ID, cấu trúc, khóa/predicate/site, lý do, đối thủ so sánh và kết quả before/after; giải thích ca index không được chọn hoặc không có lợi.
6. Hướng dẫn dựng sạch/up/restart/backup/restore; seed version, endpoint config, danh sách dịch vụ cần bật và tài nguyên tối thiểu đo được.
7. Evidence index liên kết từng gate với output, commit/version và giới hạn; không đưa secret hoặc dữ liệu cá nhân vào bộ bàn giao.
8. Bảng kết quả cuối: đã thiết kế, đã triển khai, đã kiểm chứng, chưa hoàn thành; không giữ phần trăm lịch sử của kế hoạch cũ làm tiến độ mới.

Tài liệu này là kế hoạch mục tiêu cho đợt hoàn thiện mới. [Kế hoạch 7 ngày cũ](KE_HOACH_NANG_CAP_7_NGAY.md), [ma trận phân mảnh cũ](design/02_fragmentation_matrix.md) và [kế hoạch tích hợp Ngày 6](design/06_completion_plan.md) là nguồn lịch sử; các nhận định “một site”, “không đổi API”, “không reseed” trong đó không thay phạm vi mới đã thống nhất. Khi triển khai phải cập nhật tài liệu hiện hành liên quan, không sửa evidence lịch sử để giống kết quả mới.

## 15. Nguồn đối chiếu

### 15.1. Repository

- [Báo cáo kiến trúc và kiểm chứng](report/BAO_CAO_KIEN_TRUC_CO_SO_DU_LIEU_OLDSHOP.md).
- [Schema và migration PostgreSQL](../database/04_migrations), [ORM user](../backend/app/models/user.py).
- [Document models](../backend/app/schemas/documents.py), [BSON validators](../backend/app/services/mongo_schema.py), [API catalogue DTO](../backend/app/schemas/catalog.py), [metadata service](../backend/app/services/product_metadata.py).
- [Distributed SQL](../database/distributed), [site orchestrator](../deploy/scripts/sites.py), [gateway hiện tại](../backend/app/catalogue_gateway.py), [Compose site B](../deploy/sites/compose.site-b.yml).
- [Index catalog](../database/indexing/catalog.json), [schema catalog](../database/indexing/catalog.schema.json), [index CLI](../backend/scripts/indexes.py), [hướng dẫn JSON indexing](HUONG_DAN_INDEXING_JSON.md).
- [Backup cũ](../deploy/scripts/backup-db.sh), [restore cũ](../deploy/scripts/restore-db.sh), [ETL](../backend/etl), [storage](../backend/app/services/storage.py).

### 15.2. Tài liệu kỹ thuật chính thức

- [PostgreSQL 16 — postgres_fdw](https://www.postgresql.org/docs/16/postgres-fdw.html): foreign table, kết nối và giới hạn transaction remote.
- [PostgreSQL 16 — Multicolumn indexes](https://www.postgresql.org/docs/16/indexes-multicolumn.html): thứ tự khóa B-tree và điều kiện query.
- [PostgreSQL 16 — CREATE FOREIGN TABLE](https://www.postgresql.org/docs/16/sql-createforeigntable.html): giới hạn thực thi constraint của foreign table.
- [MongoDB — Schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/): kiểm kiểu/giới hạn document; thiết lập mức kiểm và hành vi từ chối cần đúng cấu hình.
- [MongoDB — Three-member replica sets](https://www.mongodb.com/docs/manual/core/replica-set-architecture-three-members/): dữ liệu replica và election, không thay backup các kho khác.
- [MongoDB — Backup methods](https://www.mongodb.com/docs/manual/core/backups/): backup và phục hồi MongoDB độc lập với PostgreSQL/object storage.

