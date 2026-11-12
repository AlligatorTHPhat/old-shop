# Kế hoạch sửa fragmentation và indexing theo CookBook

Ngày lập: 10/11/2026. Trạng thái: đã triển khai mã nguồn và kiểm chứng local; xem [kết quả triển khai](KET_QUA_FRAGMENTATION_INDEXING.md). Các mục chưa đánh dấu cần số đo/workload thực tế hoặc rollout đúng topology VPN.

Tài liệu gốc: [CookBook.md](CookBook.md). Phần thiết kế dưới đây được giữ làm tiêu chí đối chiếu. Kết quả, bằng chứng và phạm vi đã áp dụng được ghi riêng trong báo cáo triển khai; không xem benchmark giả lập là số đo production.

## 1. Mục tiêu và phạm vi

Sửa cơ chế xác định mảnh, định tuyến đọc/ghi và lựa chọn index để đáp ứng ba yêu cầu: dữ liệu phân mảnh đầy đủ, tái tạo chính xác và tách biệt; truy vấn có khóa định tuyến chỉ truy cập mảnh cần thiết; index phục vụ workload thực tế với chi phí ghi và lưu trữ được đo.

Phạm vi triển khai chính là catalogue PostgreSQL hai site A/B, các partition và mảnh dọc hiện có, cùng chỉ mục PostgreSQL/MongoDB. Không mặc định chuyển checkout thành giao dịch đa site hoặc xây MongoDB sharded cluster. Các việc mở rộng này cần thiết kế riêng vì thay đổi ranh giới nhất quán và giao dịch của hệ thống.

## 2. Hiện trạng đã đọc từ mã nguồn

| Thành phần | Hiện trạng | Hướng sửa/kiểm chứng |
| --- | --- | --- |
| Product A/B | `database/distributed/01_site_schema.sql` dùng `seller_site`, `site_id`, FK và trigger kiểm site; product ID lẻ ở A, chẵn ở B | Giữ bảng ánh xạ seller làm căn cứ sở hữu; tách rõ khóa phân mảnh và quy tắc cấp ID |
| Product image | FK local tới product; trigger kiểm ID ảnh và chặn đổi chủ sở hữu | Chứng minh ảnh nằm cùng mảnh product; ID ảnh không thay thế quan hệ dẫn xuất |
| View toàn cục | `05_global_views.sql` hợp product/ảnh bằng `UNION ALL`; category lấy bản tại A | Kiểm tra không trùng ID, không mất hàng và dữ liệu tham chiếu nhất quán |
| Gateway catalogue | `backend/app/catalogue_gateway.py` truy vấn global view và luôn kiểm cả hai site qua `v_site_health` | Hiện chưa có nhánh đọc một site độc lập; thiết kế contract lỗi trước khi tối ưu định tuyến |
| Order và log | Migration `002_partitioning.sql`: order HASH(order_id), 4 partition; log RANGE(created_at) theo tháng, có DEFAULT | Đo pruning theo truy vấn thật; partition cùng DB không đồng nghĩa phân tán nhiều site |
| User | Migration `003_vertical_split.sql`: core/profile/secret/wallet, tái tạo bằng `users_full` | Kiểm đủ hàng ở mọi mảnh, giao dịch nguyên tử và quyền đọc |
| Index | `database/indexing/catalog.json`, schema, releases và snapshots; có planner/apply/verifier cho PG và Mongo | Mở rộng quy trình hiện có, tránh tạo bộ khai báo index thứ hai |
| Migration index | Có migration `007_indexing_v2.sql`; generator PG chỉ cho thay đổi bổ sung | Không sửa lịch sử; thay thế/xóa index phải có migration tường minh |
| Bootstrap hai site | `deploy/scripts/sites.py` dựng schema từ SQL và migrations, có manifest/checksum | Bổ sung đường nâng cấp site đã có dữ liệu; không dùng bootstrap để migrate tại chỗ |

Nguồn kiểm chứng hiện có cần kế thừa: `deploy/scripts/verify_sites.py`, `deploy/scripts/verify_catalogue.py`, `backend/tests/test_day4_migrations.py`, `backend/tests/test_index_config*.py`, `backend/tests/test_indexing_v2.py` và `docs/runbooks/indexing_v2.md`.

## 3. Cách diễn giải CookBook khi triển khai

Áp dụng nguyên tắc trong CookBook, đồng thời làm rõ các điểm sau để tránh biến mô hình giảng dạy thành cam kết sai:

- **Chi phí index:** không dùng công thức “1 triệu document chỉ cần 19 phép so sánh” làm tiêu chí nghiệm thu. Truy vấn còn chịu chi phí quét khóa kết quả, FETCH, I/O và sort; mỗi lần ghi bảo trì các entry index liên quan, không mặc định xây lại toàn bộ cây.
- **Thứ tự compound index:** ưu tiên thử Equality → Sort → Range khi cần tránh sort; so sánh Equality → Range → Sort nếu điều kiện khoảng chọn lọc hơn. Chọn bằng explain và benchmark, không áp dụng duy nhất E→R→S. Xem [MongoDB ESR](https://www.mongodb.com/docs/v8.0/tutorial/equality-sort-range-guideline/).
- **Covered query:** không có SORT chưa đủ để gọi là covered. Query cần được đáp ứng hoàn toàn bởi index, bao gồm projection; trường hợp còn FETCH như ví dụ CookBook chưa phải covered query. Xem [MongoDB Query Optimization](https://www.mongodb.com/docs/v8.0/core/query-optimization/).
- **Tách biệt dọc:** cho phép lặp khóa tái tạo; các thuộc tính không phải khóa không lặp trong thiết kế không dư thừa. Đây là ngoại lệ có chủ đích, không phải lỗi phân mảnh.
- **Phân mảnh dẫn xuất:** dùng semijoin hoặc chọn các hàng con có khóa cha thuộc mảnh; không dùng join trả thêm cột cha như thể đó là lược đồ nguyên bản của bảng con.
- **Replication:** Read-one Write-all là một chiến lược lý thuyết. Mongo `w: majority` không có nghĩa chờ tất cả member; không chuyển sang ghi tất cả bản sao chỉ để khớp CookBook. Xem [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- **Di chuyển hàng:** `DELETE` rồi `INSERT` xuyên hai DB không tự tạo giao dịch nguyên tử. Cần cơ chế điều phối, phục hồi và xử lý phụ thuộc trước khi cho phép đổi khóa phân mảnh.

## 4. Thiết kế fragmentation mục tiêu

### 4.1. Chuẩn hóa hợp đồng phân mảnh

- [x] Lập một hợp đồng có phiên bản, dự kiến `database/distributed/fragmentation.json`, chứa loại mảnh, quan hệ chủ/con, vị từ, khóa tái tạo, site sở hữu, quy tắc ID và chính sách đổi chủ.
- [x] Hợp đồng chỉ chứa metadata; DSN và thông tin xác thực lấy từ cấu hình môi trường. Không cho cấu hình chạy SQL tùy ý.
- [x] Quy định `seller_site` là nguồn ánh xạ có thẩm quyền; metadata ở ứng dụng mô tả quy tắc, không duy trì bản ánh xạ seller độc lập dễ lệch.
- [x] Validator từ chối seller thiếu owner, site không hợp lệ, phiên bản không hỗ trợ và cấu hình thiếu mảnh. Với A/B, mỗi seller phải ánh xạ đúng một site.
- [x] Phát hiện lệch giữa hợp đồng, `site_config`, constraint/trigger và manifest; không định tuyến theo phỏng đoán khi phát hiện lệch.

Định nghĩa quan hệ mục tiêu:

```text
P_A = {p thuộc Product | seller_site(p.seller_id) = A}
P_B = {p thuộc Product | seller_site(p.seller_id) = B}
I_A = {i thuộc ProductImage | i.product_id thuộc keys(P_A)}
I_B = {i thuộc ProductImage | i.product_id thuộc keys(P_B)}

Product = P_A UNION ALL P_B
ProductImage = I_A UNION ALL I_B
User = UserCore JOIN UserProfile JOIN UserSecret JOIN UserWallet ON user_id
```

ID lẻ/chẵn là cơ chế tránh xung đột và hỗ trợ suy ra site khi invariant còn đúng, không phải định nghĩa seller thuộc site nào. Không tự chuyển sang chia seller ID chẵn/lẻ: phải đối chiếu fixture, `seller_site` và dữ liệu thực tế trước.

### 4.2. Sửa thuật toán định tuyến đọc

Module dự kiến: `backend/app/services/fragment_router.py`, được gateway gọi qua lớp truy cập catalogue. Client dùng định danh nghiệp vụ, không cần truyền tên database hay địa chỉ site.

| Đầu vào truy vấn | Quyết định | Dữ liệu cần truy cập |
| --- | --- | --- |
| Có seller_id | Tra owner từ ánh xạ có thẩm quyền | Một mảnh product và ảnh tương ứng |
| Có product_id hợp lệ | Suy site theo quy tắc ID đã kiểm chứng; không có hàng thì trả 404 | Một mảnh product và ảnh tương ứng |
| Có khóa định tuyến nhưng không xác định được owner | Trả lỗi ánh xạ hoặc kết quả không tồn tại theo contract đã định | Không âm thầm dò mọi site để che sai dữ liệu |
| Không có khóa định tuyến | Truy vấn global view hoặc tổng hợp cả hai mảnh | A và B, lọc/sort tại site khi có thể |
| Đọc danh sách ảnh | Nhóm product theo site, tải ảnh theo lô | Các mảnh chứa product trong trang kết quả |

- [x] Kiểm tra filter, projection và sort thực sự được đẩy xuống remote bằng `EXPLAIN (ANALYZE, VERBOSE, FORMAT JSON)` và `Remote SQL`; không suy ra từ tên view. Xem [PostgreSQL postgres_fdw](https://www.postgresql.org/docs/16/postgres-fdw.html).
- [x] Giữ thứ tự ổn định với khóa phụ `product_id`; lọc trước phân trang, tổng số đếm phải dùng cùng điều kiện.
- [ ] Nếu tổng hợp tại ứng dụng, mỗi site cần tối đa `skip + limit` hàng theo cùng thứ tự rồi merge, sau đó mới lấy trang; không áp OFFSET riêng tại từng site. Trang sâu cần đánh giá keyset pagination ở bước sau.
- [x] Thống nhất contract lỗi: truy vấn toàn cục thiếu một site trả 503, không trả trang thiếu dữ liệu như thành công. Truy vấn đã định tuyến được phép thành công khi site ngoài phạm vi bị lỗi.
- [x] Để đạt contract trên, thay health check “luôn chạm hai site” hiện tại bằng kiểm tra theo phạm vi truy vấn; `/ready` toàn cục vẫn kiểm cả hai. Cập nhật test và mô tả hành vi API trong cùng thay đổi.
- [x] Không tuyên bố snapshot toàn cục nguyên tử chỉ vì connection tại A dùng REPEATABLE READ; mô tả giới hạn nhất quán giữa các DB độc lập và khi đếm/lấy trang đồng thời có ghi.

### 4.3. Ghi dữ liệu và đổi khóa phân mảnh

- [ ] INSERT product: xác định owner → ghi site sở hữu → constraint/trigger kiểm lại → sinh ID đúng dải. Sai site phải bị từ chối ngay cả khi bỏ qua ứng dụng.
- [x] INSERT/DELETE ảnh: theo site của product; giữ FK local và quy tắc media cleanup/outbox hiện có.
- [x] UPDATE thuộc tính thường: cập nhật tại site sở hữu trong transaction local.
- [x] Giai đoạn chính tiếp tục chặn đổi `product_id`, `seller_id`, `site_id`, phù hợp trigger hiện tại. Trả lỗi nghiệp vụ rõ ràng; không bỏ trigger để mô phỏng DELETE–INSERT.
- [x] Category và seller mapping đang được nạp giống nhau lúc bootstrap: xác định nguồn chủ, phiên bản và checksum; phát hiện drift trước khi cho phép cập nhật reference. Nếu cần ghi tất cả bản reference, phải thiết kế retry và trạng thái hoàn tất, không coi hai lần ghi độc lập là nguyên tử.

Nhánh mở rộng sau khi phần chính nghiệm thu: thiết kế migration job chuyển owner có `operation_id`, khóa/chặn ghi đồng thời, kiểm tra FK, staging, chuyển quyền hiển thị, retry idempotent và đối soát. Phải kiểm kê order/cart/review, ảnh, outbox và projection trước; thử lỗi ở từng bước. Chỉ bật đổi chủ khi chứng minh phục hồi được mà không mất hàng hoặc hiển thị trùng. Đây chưa phải cam kết triển khai trong đợt chính.

### 4.4. Partition và phân mảnh dọc

- [x] Giữ HASH(order_id) làm baseline; đo lookup order_id và danh sách theo buyer/seller. Truy vấn không lọc order_id có thể phải đọc cả bốn partition; index local không thay partition pruning.
- [x] Với log, thử điều kiện thời gian dạng khoảng nửa mở; kiểm biên tháng, dữ liệu ngoài khoảng và partition DEFAULT. Đối chiếu timezone với kiểu timestamp thực tế trước khi sửa.
- [x] Đo việc tách user giúp truy vấn thường tránh đọc secret/wallet; kiểm mỗi core có đủ các hàng profile/secret/wallet. FK chỉ ngăn hàng con mồ côi, chưa bảo đảm chiều ngược lại.
- [x] Duy trì ghi cả bốn mảnh user trong một transaction và kiểm rollback khi một mảnh lỗi; `users_full` dùng để tái tạo/đối soát với quyền phù hợp.

## 5. Thiết kế indexing mục tiêu

### 5.1. Lập ma trận query → index

- [ ] Thu SQL/Mongo filter, sort, projection, limit, tần suất và tỷ lệ đọc/ghi từ code và workload đại diện.
- [ ] Lưu baseline trong `docs/benchmark/fragmentation_indexing/`: phiên bản DB, commit, seed, phân bố dữ liệu, cache, số lượt chạy, concurrency và cấu hình máy.
- [ ] Kiểm kê index vật lý ở commerce PG, từng site A/B và Mongo; phân biệt khai báo trong JSON với trạng thái đã áp dụng.
- [ ] Mỗi index đề xuất có query đích, số đo trước/sau, chi phí ghi và quyết định giữ/thay/bỏ. Không chọn index chỉ vì field xuất hiện trong schema.

| Workload cần đo | Ứng viên/hướng kiểm tra, chưa phải DDL chốt |
| --- | --- |
| Catalogue visible, mới nhất | Đối chiếu index `idx_product_visible_date_id` hiện có với predicate và thứ tự thực tế |
| Catalogue theo category | Thử category_id + created_at + product_id với partial predicate visible nếu query suy ra được predicate |
| Catalogue sort giá | Thử price + product_id; thêm category_id ở đầu cho biến thể có equality category, tránh coi hai query là một |
| Seller catalogue | Thử seller_id + khóa sort + product_id; không thêm site_id ở đầu chỉ để biểu diễn phân tán |
| Product detail/ảnh | Tận dụng PK/unique hiện có; đo product_id + display_order + image_id cho ảnh theo lô |
| Tìm title/description ILIKE | Đối chiếu GIN/trigram và SQL hiện có; B-tree thông thường không giải quyết mọi tìm kiếm `%term%` |
| Mongo product_details | Giữ unique product_id; với attribute/tag phải lấy đúng query shape từ service trước khi chọn compound/multikey index |
| Mongo logs/reviews | Đối chiếu equality actor/product/status và sort thời gian; giữ TTL/unique có vai trò riêng |

### 5.2. Sửa quy trình lựa chọn và quản lý index

- [x] Dùng `index_config.py`, `index_postgres.py`, `index_mongo.py` và `scripts/plan_indexes.py` làm nền; planner tiếp tục chỉ đọc, không tự tạo/xóa index theo query nhận được.
- [x] Giữ thứ tự key trong JSON; validate tên trường, hướng sort, partial/sparse/unique/TTL và các kết hợp được DB version thực tế hỗ trợ.
- [ ] Kiểm query có bao hàm partial predicate; phân biệt field thiếu với field null khi đánh giá sparse. Không dùng hint làm sai tập kết quả để lấy số đo đẹp.
- [x] Kiểm duplicate/null trước khi thêm unique; xử lý vi phạm dữ liệu bằng quy trình riêng, không xóa document tự động.
- [x] Dùng catalog theo phạm vi triển khai hoặc tập con được khai báo rõ để kiểm từng DB; một site thiếu index phải thể hiện thiếu tại site đó. Foreign table không phải nơi tạo index cho dữ liệu remote.
- [x] Giữ snapshot/release cũ bất biến; phát hành revision mới và migration mới theo số tiếp theo thực tế. Generator chỉ bổ sung; thay thế/xóa dùng migration tường minh và kiểm dependency/constraint.
- [x] Tạo index thay thế, đo và chuyển query trước khi cân nhắc bỏ index cũ. Không tự xóa index unmanaged hoặc index PK/UNIQUE/FK-support chỉ vì ít scan trong thời gian ngắn.
- [x] Không gọi reIndex định kỳ. Với runner transaction hiện tại, dùng cửa sổ bảo trì; nếu cần build concurrently phải có quy trình riêng, không nhét CONCURRENTLY vào transaction.

### 5.3. Đo hiệu quả

PostgreSQL lưu explain JSON, buffer reads/hits, actual rows/loops, sort, partition được đọc và remote SQL. Mongo lưu `nReturned`, `totalKeysExamined`, `totalDocsExamined`, winning plan, SORT và FETCH. Chỉ gọi covered query khi projection được index đáp ứng và không cần đọc document; không ép toàn bộ endpoint thành covered query.

Chạy workload trước/sau trên dữ liệu giống nhau, có dữ liệu lệch giữa seller/site, query phổ biến và query ít chọn lọc. Đo p50/p95 đọc, p95 ghi, throughput, dung lượng index và thời gian build. Thử tối thiểu 30 lượt đo sau warm-up cho mỗi query chính, tách lượt cache lạnh nếu môi trường cho phép. Không dùng số mili giây trong CookBook làm kết quả của OldShop; không ép IXSCAN khi optimizer chọn quét toàn bộ hợp lý trên tập nhỏ.

## 6. Kế hoạch triển khai theo thứ tự phụ thuộc

| Bước | Công việc | Đầu ra và điều kiện chuyển bước |
| --- | --- | --- |
| 1 | Inventory topology, mapping, index, query và baseline | Báo cáo phạm vi từng DB, dữ liệu chuẩn đối chiếu và số đo có thể lặp lại |
| 2 | Hợp đồng fragmentation và validator | Vị từ A/B đầy đủ, loại trừ nhau; cấu hình lệch bị phát hiện |
| 3 | Router và truy vấn catalogue | Detail/ảnh đúng một site; global trả đủ dữ liệu, sort/page đúng; contract lỗi được kiểm thử |
| 4 | Kiểm chứng integrity, partition và vertical split | Không mất/trùng hàng, không orphan, pruning và rollback có bằng chứng |
| 5 | Thử index theo workload ở môi trường tách biệt | Ma trận query/index có explain và số đo đọc/ghi; chọn revision đề xuất |
| 6 | Đóng gói migration và đường nâng cấp A/B | Dry-run/plan sạch, snapshot/checksum hợp lệ, có thử rollback/restore |
| 7 | Rollout và cập nhật tài liệu | Verification từng DB PASS, API và ETL đối soát đúng, có số đo sau triển khai |

Các file dự kiến sửa khi triển khai: `backend/app/catalogue_gateway.py`; module router mới; `database/distributed/` và công cụ nâng cấp site; `deploy/scripts/verify_sites.py`, `verify_catalogue.py`; catalog/schema/snapshot/release index nếu cần; migration mới và các test liên quan. Tên file migration chỉ chốt sau inventory để tránh trùng số.

## 7. Kiểm thử và tiêu chí nghiệm thu

### 7.1. Tính đúng đắn

- [ ] **Đầy đủ ngang:** tập dữ liệu chuẩn trước phân chia bằng hợp các mảnh sau chia; so sánh hai chiều bằng `EXCEPT ALL` hoặc công cụ tương đương. So với nguồn chuẩn độc lập, không chỉ so view với chính hai bảng tạo view.
- [x] **Tách biệt ngang:** giao product_id và image_id giữa A/B rỗng; mỗi product thỏa đúng một vị từ owner, mỗi ảnh có cha local.
- [ ] **Tái tạo:** đối chiếu toàn bộ cột và số lần xuất hiện của hàng; checksum/count chỉ là bằng chứng bổ sung, không thay so sánh hàng ở fixture kiểm thử.
- [x] **Dọc:** hợp các tập cột bằng lược đồ gốc, giao cột chỉ gồm user_id; mỗi user có đủ bốn mảnh; join khớp dữ liệu chuẩn và không nhân hàng.
- [x] **Biên và ghi:** ID không hợp lệ, seller không có mapping, ghi sai site, ảnh mồ côi, đổi owner bị chặn, lỗi giữa transaction và cấp ID đồng thời đều có test.
- [x] **Truy vấn:** lọc/sort/page không mất hoặc lặp product trên dữ liệu cố định; truy vấn global khi B lỗi trả 503; truy vấn chỉ A vẫn thành công khi B lỗi theo contract mới.

### 7.2. Hiệu năng và vận hành

- [x] Query có khóa định tuyến không thực hiện truy cập dữ liệu hoặc health probe tới site ngoài phạm vi; xác minh bằng log/tracing hoặc đếm lời gọi DB.
- [x] Query order theo order_id và log theo khoảng tháng có bằng chứng pruning phù hợp; trường hợp không thể prune được ghi rõ.
- [x] Index khai báo khớp index vật lý ở mọi DB thuộc phạm vi; chạy lại apply không phát sinh index trùng; conflict không gây tự drop/rebuild.
- [ ] Query mục tiêu giảm số hàng/khóa đọc hoặc chi phí sort và có số đo latency tương ứng. Nếu optimizer vẫn chọn scan hợp lý, ghi nhận và không thêm index không có lợi.
- [ ] Ngưỡng đề xuất cho workload đọc được chọn: p95 giảm ít nhất 20%; p95 ghi không tăng quá 10% ở cùng tải. Đây là ngưỡng mục tiêu ban đầu, cần chốt sau baseline; nếu không đạt phải giải thích lợi ích/chi phí trước khi giữ index.
- [ ] Regression test auth/user, product/moderation, cart/order, index config và ETL phù hợp phần thay đổi đều PASS; không yêu cầu benchmark lại phần không đổi nếu không có dấu hiệu ảnh hưởng.

## 8. Rollout, rollback và bằng chứng bàn giao

1. Xác nhận đúng DB/site và revision; backup rồi thử restore trên môi trường riêng. Chụp mapping, schema/index inventory và dữ liệu chuẩn đối chiếu trong cửa sổ không có ghi hoặc snapshot được kiểm soát.
2. Triển khai tại môi trường thử nghiệm trước. Với A/B đã có dữ liệu, dùng migration nâng cấp có version/checksum, không chạy lại bootstrap hoặc reseed để thay cấu trúc.
3. Áp index bổ sung ở từng DB; ghi trạng thái riêng cho mỗi engine/site. Nếu một site lỗi, dừng bước phụ thuộc và giữ khả năng chạy lại, không ghi “toàn hệ thống đã áp” từ một lần thành công.
4. Triển khai router sau khi mapping/schema tương thích; kiểm global query, local query, outage, ETL và dữ liệu. Theo dõi p95, lỗi 5xx, disk/WAL và queue pending/dead.
5. Nếu router lỗi, quay về đường đọc global view và contract cũ bằng cấu hình chuyển đổi dự kiến bổ sung. Nếu index mới gây hại, dùng migration bù có kiểm dependency; không sửa file migration đã áp hoặc xóa lịch sử. Rollback ứng dụng không tự rollback schema.

Bằng chứng dự kiến lưu ở `docs/evidence/fragmentation_indexing/` và `docs/benchmark/fragmentation_indexing/`: inventory đã che thông tin bí mật, báo cáo ba tính chất phân mảnh, explain trước/sau, kết quả regression/outage, bảng đọc/ghi/storage và log rehearsal rollback. Cập nhật hướng dẫn CSDL phân tán, ma trận fragmentation, tài liệu indexing và runbook hiện hành; giữ evidence cũ như lịch sử.

Hoàn thành đợt chính khi các kiểm tra tính đúng đắn đạt, query định tuyến có bằng chứng chỉ dùng site cần thiết, index có kết quả đo chấp nhận được và rollout/rollback được thử. Nhánh chuyển owner xuyên site vẫn được đánh dấu riêng nếu chưa triển khai.

Ghi chú nghiệm thu: checkbox về index vật lý và outage áp dụng stack kiểm chứng local riêng, không suy ra rollout VPN hoặc commerce đã hoàn tất. Query toàn cục vẫn có thể SORT ở A; bằng chứng Remote SQL ghi rõ phần pushdown thực tế. Mục tiêu hiệu năng production chưa được đánh dấu hoàn tất.

Gateway vẫn chỉ đọc. Các phép ghi local được kiểm bằng FK/trigger; chưa bổ sung cổng ghi tập trung tự định tuyến INSERT theo seller.
