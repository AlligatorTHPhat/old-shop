# BÁO CÁO GIẢI PHÁP VÀ KIẾN TRÚC CƠ SỞ DỮ LIỆU OLDSHOP

**Phạm vi:** kết quả nâng cấp hệ thống trong kế hoạch 7 ngày và phần bổ sung cấu hình indexing bằng JSON.  
**Thời điểm tổng hợp:** 03/11/2026.  
**Căn cứ:** mã nguồn, cấu hình triển khai và các bằng chứng kiểm thử/benchmark đang lưu trong repository.

## 1. Bài toán OldShop và định hướng giải pháp cơ sở dữ liệu

### 1.1. Mô tả bài toán

OldShop là hệ thống thương mại điện tử dành cho việc mua bán đồ cũ. Một người dùng có thể vừa mua sản phẩm của người khác, vừa đăng bán sản phẩm của mình. Vì hàng hóa do nhiều người dùng tự đăng, hệ thống cần cơ chế kiểm duyệt trước khi đưa sản phẩm ra danh sách bán công khai.

Hệ thống có ba nhóm vai trò chính:

| Vai trò | Trách nhiệm nghiệp vụ |
|---|---|
| Admin | Quản lý người dùng, theo dõi và xử lý tài khoản theo quyền được cấp |
| Moderator | Xem sản phẩm người dùng đăng, duyệt hoặc từ chối sản phẩm |
| User | Quản lý tin đăng của bản thân, cung cấp mô tả/ảnh/video và mua hàng của người dùng khác |

Luồng nghiệp vụ tiêu biểu: user đăng sản phẩm → moderator kiểm duyệt → sản phẩm được duyệt xuất hiện để mua → người mua tạo đơn → hệ thống xử lý các thay đổi liên quan đến đơn hàng, tồn kho và giao dịch. Việc đăng sản phẩm và việc mua hàng thuộc cùng một tài khoản, không cần tách thành hai loại tài khoản người mua/người bán độc lập.

### 1.2. Các vấn đề dữ liệu cần giải quyết

OldShop phát sinh đồng thời nhiều loại dữ liệu có yêu cầu lưu trữ khác nhau:

| Nhóm dữ liệu | Ví dụ | Yêu cầu |
|---|---|---|
| Dữ liệu nghiệp vụ có cấu trúc | User, role, giá, số lượng, trạng thái duyệt, đơn hàng, thanh toán | Quan hệ rõ ràng, ràng buộc khóa và xử lý giao dịch |
| Dữ liệu bán cấu trúc | Thuộc tính theo loại hàng, tags, danh sách tham chiếu ảnh, document đơn hàng | Cho phép object/array lồng nhau và các khóa thuộc tính thay đổi |
| Nội dung phi cấu trúc | Ảnh sản phẩm, avatar, video MP4, file đính kèm | Lưu và truy xuất nội dung file bằng object key |
| Dữ liệu phục vụ vận hành | Sự kiện đồng bộ, lần chạy ETL, lỗi, báo cáo tổng hợp | Có khả năng theo dõi, retry và đối soát |

Ví dụ, điện thoại có RAM và dung lượng lưu trữ; quần áo có kích thước và chất liệu. Nếu mọi thuộc tính đều trở thành cột cố định trong bảng `product`, schema sẽ khó mở rộng. Ngược lại, nếu toàn bộ dữ liệu đơn hàng và tồn kho chỉ là document linh hoạt, việc bảo vệ các quan hệ và giao dịch nghiệp vụ sẽ phức tạp hơn.

Khi số lượng tin đăng tăng, hệ thống còn phải tránh quét toàn bộ dữ liệu cho mỗi lần xem danh sách, tra cứu ảnh hoặc xử lý hàng đợi ETL. Việc bổ sung index phải dựa trên truy vấn thực tế và có bằng chứng đo, vì mỗi index cũng làm tăng dung lượng và chi phí ghi.

### 1.3. Giải pháp đề xuất và đã triển khai

OldShop sử dụng phối hợp ba công nghệ lưu trữ:

- **PostgreSQL:** nguồn dữ liệu chuẩn cho các trường nghiệp vụ/giao dịch và quan hệ có cấu trúc.
- **MongoDB:** nguồn chuẩn cho thuộc tính động/tags và nơi lưu các document bản đọc được ETL tạo từ dữ liệu cho phép của PostgreSQL.
- **MinIO:** nơi lưu nội dung thực của file; PostgreSQL/MongoDB giữ các tham chiếu theo quyền sở hữu dữ liệu.

FastAPI cung cấp API để người dùng thao tác với các kho này thông qua ứng dụng. ETL tạo và cập nhật các bản đọc/tổng hợp. Index được thiết kế theo workload và quản lý thêm bằng catalog JSON. Hạ tầng Docker có PostgreSQL standby và MongoDB replica set để mô phỏng nhiều node, trong phạm vi một máy chủ.

Giải pháp này là tích hợp nhiều hệ lưu trữ ở tầng ứng dụng và đồng bộ dữ liệu. Không có một bộ máy truy vấn SQL chung hay một transaction ACID duy nhất bao trùm cả PostgreSQL, MongoDB và MinIO.

## 2. Kiến trúc hệ thống cơ sở dữ liệu

### 2.1. Các thành phần và hướng kết nối

```text
Trình duyệt: Admin / Moderator / User
                   |
            Angular + Nginx
                   |
                FastAPI
          /        |        \
 PostgreSQL     MongoDB     MinIO
   primary     replica set  single-node
      |
      +-- WAL bất đồng bộ --> PostgreSQL standby
      |
      +-- dữ liệu nguồn + outbox --> ETL worker
                                      |
                         +------------+------------+
                         |            |            |
                      MongoDB    Báo cáo trên PG   MinIO
                     bản đọc      ACK/đối soát    media/cleanup
```

Ứng dụng đọc/ghi nghiệp vụ cốt lõi tại PostgreSQL primary. Các thuộc tính động được xử lý tại MongoDB. Upload và phát nội dung file đi qua lớp storage/media của ứng dụng tới MinIO khi cấu hình storage là `minio`.

PG standby nhận WAL từ primary. MongoDB gồm `mongo1`, `mongo2`, `mongo3` trong replica set `oldshop-rs`; vai trò PRIMARY/SECONDARY được xác định theo trạng thái replica set, không nên coi tên `mongo1` luôn đồng nghĩa với PRIMARY.

### 2.2. Triển khai vật lý hiện tại

File [docker-compose.distributed.yml](../../deploy/docker-compose.distributed.yml) định nghĩa stack `oldshop-data`. Profile `resilience` bổ sung PostgreSQL replica và hai MongoDB member so với cấu hình cơ sở.

| Thành phần | Trạng thái triển khai | Cổng host mặc định |
|---|---|---|
| Frontend | Angular/Nginx | `58080` |
| Backend | FastAPI | `58000` |
| PostgreSQL primary | Nơi ghi nghiệp vụ | `55432` |
| PostgreSQL standby | Bản sao streaming, chỉ đọc | `55433` |
| MongoDB | Replica set ba member khi bật profile | `57017` cho mongo1 nếu mở theo cấu hình GUI |
| MinIO | Một node lưu object | `59000` API, `59001` Console |
| ETL worker | Một process đồng bộ theo chu kỳ | Không cần cổng công khai |

Các cổng trên là cổng để công cụ trên host kết nối. Bên trong Docker network, ứng dụng sử dụng hostname/cổng nội bộ, ví dụ `pg-primary:5432`, `mongo1:27017`, `minio:9000`. pgAdmin4 và MongoDB Compass là công cụ quản trị, không phải nơi trực tiếp lưu dữ liệu.

Toàn bộ container và volume hiện vẫn nằm trên cùng một Docker host. Các node được tách về tiến trình/network/volume nhưng chưa được tách thành các miền lỗi vật lý độc lập.

### 2.3. Các hình minh họa cần chèn khi hoàn thiện báo cáo

Chưa tạo thêm hình trong báo cáo này. Có thể sử dụng các nguồn sau để xuất hình và chèn vào bản trình bày:

| Hình | Nguồn hiện có | Đường dẫn ảnh dự kiến do người biên soạn chuẩn bị |
|---|---|---|
| Kiến trúc tổng thể | `docs/diagram/07_architecture_current.puml` | `docs/report/assets/oldshop_database_architecture.png` |
| ERD PostgreSQL | `docs/diagram/07_erd_current.dbml` | `docs/report/assets/oldshop_postgres_erd.png` |
| Topology replication | `docs/diagram/02_distribution_diagram.puml` | `docs/report/assets/oldshop_replication_topology.png` |
| Luồng ETL | `docs/diagram/05_etl_flow.puml` | `docs/report/assets/oldshop_etl_flow.png` |

Các đường dẫn ảnh dự kiến chưa phải file đã được tạo. Một số sơ đồ nguồn được lập ở giai đoạn trước; khi xuất hình cần cập nhật nội dung video MP4/bucket `product-videos`, cấu hình JSON và trạng thái triển khai hiện tại.

## 3. Thiết kế và thực thi giải pháp cơ sở dữ liệu

### 3.1. Cơ sở dữ liệu hợp nhất

#### 3.1.1. PostgreSQL: dữ liệu có cấu trúc và nguồn nghiệp vụ

PostgreSQL quản lý các dữ liệu có quan hệ rõ ràng: người dùng, vai trò, danh mục, sản phẩm, quan hệ sản phẩm–ảnh, giỏ hàng, đơn hàng, chi tiết đơn, giao dịch và voucher. Các khóa chính, khóa ngoại, ràng buộc và transaction bảo vệ tính toàn vẹn của dữ liệu trong phạm vi PostgreSQL.

Dữ liệu người dùng được tách thành `user_core`, `user_profile`, `user_secret`, `user_wallet`, liên kết bằng `user_id`. Mục đích là phân chia các nhóm thông tin theo chức năng và đường truy cập. Việc tách bảng tự nó không tạo ra phân quyền bảo mật hay phân tán vật lý; vẫn cần kiểm soát truy cập tại ứng dụng/database.

Các thao tác nhạy cảm với tính nhất quán như tồn kho, ví và giao dịch sử dụng primary. Không coi bản sao PostgreSQL bất đồng bộ là nơi mặc định để quyết định số dư hoặc số lượng hàng khả dụng.

#### 3.1.2. MongoDB: dữ liệu bán cấu trúc

MongoDB lưu document BSON với object và array lồng nhau. Dữ liệu không hoàn toàn tùy ý: các model Pydantic được dùng để xây validator, còn các dictionary như `attributes` cho phép khóa linh hoạt.

Các nhóm document nghiệp vụ gồm `product_details`, `order_snapshots`, `reviews`, `system_logs`, `violation_logs`, `contact_messages`. Collection `etl_errors` phục vụ vận hành ETL.

Ví dụ thuộc tính có thể khác nhau theo sản phẩm:

```json
{
  "product_id": 123,
  "attributes": {
    "brand": "Thuong hieu A",
    "ram_gb": 8,
    "storage_gb": 256
  },
  "tags": ["dien-thoai", "da-qua-su-dung"]
}
```

Đây là ví dụ rút gọn để giải thích các trường, không phải document đầy đủ để insert trực tiếp qua validator.

`attributes` và `tags` là dữ liệu do MongoDB sở hữu. Các trường bản đọc khác, chẳng hạn mô tả, danh mục và tham chiếu ảnh, có thể được chiếu từ PostgreSQL qua ETL. Vì vậy, không phải mọi trường trong MongoDB đều là nguồn dữ liệu độc lập với PostgreSQL.

Tags là metadata mô tả nghiệp vụ. Ngoài tags, MongoDB còn chứa thuộc tính động, dữ liệu nhúng và metadata tham chiếu file. Các document contract nằm trong [documents.py](../../backend/app/schemas/documents.py).

#### 3.1.3. MinIO: nội dung phi cấu trúc

MinIO lưu các byte thực của ảnh, video và file đính kèm dưới dạng object trong bucket. Một object được xác định bằng bucket và key. Metadata kỹ thuật như content type và kích thước hỗ trợ việc lưu/phát file.

Các bucket phục vụ ảnh sản phẩm, video sản phẩm, avatar và attachment. Bucket được cấu hình private; ứng dụng dùng credentials được cấp để upload hoặc đọc nội dung qua media gateway.

Video sản phẩm có thể là liên kết Google Drive/YouTube hoặc MP4 upload. Với MP4, file nằm trong MinIO khi dùng storage backend MinIO; với liên kết bên ngoài, nội dung file vẫn ở dịch vụ bên ngoài. Không tuyên bố mọi video liên kết đã được sao chép vào MinIO.

Lớp truy cập storage nằm trong [storage.py](../../backend/app/services/storage.py).

#### 3.1.4. Vì sao vẫn giữ `product_image` trong PostgreSQL?

`product_image` quản lý quan hệ có cấu trúc giữa sản phẩm và ảnh. Nó không chỉ chứa đường dẫn:

| Trường/nhóm trường | Ý nghĩa |
|---|---|
| `image_id` | Định danh bản ghi ảnh |
| `product_id` | Khóa ngoại xác định sản phẩm sở hữu ảnh |
| `image_url` | Tham chiếu đường dẫn phục vụ nội dung ảnh |
| `is_primary`, `display_order` | Vai trò và thứ tự hiển thị ảnh |
| Metadata khác | Các thông tin đi kèm như loại nội dung/kích thước nếu có |

Ví dụ quan hệ tham chiếu:

```text
PG product_image:
  product_id = 123
  image_url = /media/products/123/abc.jpg
  is_primary = true

MinIO:
  bucket = product-images
  key = products/123/abc.jpg
  content = dữ liệu nhị phân của ảnh

Mongo product_details.images:
  bản tham chiếu bucket/key và metadata được ETL đồng bộ
```

Đường dẫn `/media/...` là địa chỉ qua gateway của ứng dụng; không nhất thiết là URL trực tiếp do MinIO trả về. Ứng dụng ánh xạ đường dẫn tới bucket/key để đọc object. Cách này cũng giúp đường dẫn nghiệp vụ không phải phụ thuộc trực tiếp vào hostname/cổng MinIO.

MinIO quản lý object nhưng không thay PostgreSQL bảo đảm khóa ngoại tới sản phẩm, trạng thái ảnh chính hoặc thứ tự ảnh trong danh sách nghiệp vụ. Việc PostgreSQL lưu tham chiếu không đồng nghĩa PostgreSQL lưu nội dung ảnh, cũng không vi phạm phân chia ba loại dữ liệu.

Có thể thiết kế quan hệ ảnh hoàn toàn trong MongoDB, nhưng đó là phương án khác, cần thay đổi API, ownership, ETL và quy trình dọn file. Trong thiết kế hiện tại, PostgreSQL là nguồn chuẩn cho quan hệ ảnh; MongoDB có bản đọc; MinIO là nguồn chuẩn cho nội dung file. Cơ chế cleanup kiểm tra tham chiếu trước khi xóa để bảo vệ file còn được sử dụng, bao gồm các ảnh seed dùng chung.

#### 3.1.5. ETL kết nối các kho dữ liệu như thế nào?

ETL là Extract–Transform–Load: trích xuất dữ liệu nguồn, chuyển đổi sang dạng phù hợp và nạp vào đích. Trong OldShop, ETL không chỉ là chép nguyên một hàng SQL sang JSON.

| Bước | Ví dụ với sản phẩm |
|---|---|
| Extract | Đọc `product` và các dòng `product_image` liên quan từ PostgreSQL |
| Transform | Chuẩn hóa thời gian, chuyển các trường thành object/array, ánh xạ đường dẫn ảnh thành bucket/key, kiểm tra dữ liệu |
| Load | Upsert vào `product_details` trên MongoDB, giữ các trường Mongo-owned như `attributes` và `tags` |

Đồng bộ thay đổi được thực hiện bằng transactional outbox:

1. Khi dữ liệu nguồn thay đổi, trigger PostgreSQL ghi sự kiện outbox trong cùng transaction.
2. Nếu transaction nghiệp vụ rollback, sự kiện tương ứng cũng rollback.
3. Worker lấy sự kiện đến hạn, đọc trạng thái nguồn và xử lý các bản đọc liên quan.
4. Sau khi nạp thành công, worker đánh dấu sự kiện đã xử lý. Nếu lỗi, giữ trạng thái để retry và theo dõi lỗi.

Worker có cơ chế khóa để tránh các lượt đồng bộ ghi chồng nhau. Upsert theo khóa nguồn cho phép xử lý lại sự kiện mà không mặc định tạo thêm document trùng. Tuy nhiên, đây không phải bảo đảm exactly-once hay một transaction chung xuyên PostgreSQL–MongoDB–MinIO.

Các luồng ETL chính gồm sản phẩm, đơn hàng, review/report, log/contact, media và tổng hợp doanh số. Luồng media đưa file local/seed còn thiếu lên MinIO; ảnh/video upload mới có thể được ứng dụng ghi trực tiếp lên MinIO mà không chờ ETL. Báo cáo tổng hợp doanh số được ghi về PostgreSQL.

Bản đọc MongoDB có thể trễ so với PostgreSQL vì worker xử lý theo chu kỳ. Đây là nhất quán cuối cùng đối với dữ liệu sao chép. Nếu một kho lỗi, phải theo dõi backlog, retry và đối soát thay vì giả định tất cả kho luôn đồng bộ tức thì.

Chi tiết mã nguồn và ownership: [ETL](../../backend/etl), [thiết kế ETL/outbox](../design/05_etl.md).

### 3.2. Hệ thống cơ sở dữ liệu phân tán

#### 3.2.1. Bài toán và phạm vi lựa chọn

Hệ thống cần giảm phụ thuộc vào một tiến trình database, chuẩn bị khả năng sao chép dữ liệu và kiểm tra cách ứng dụng phản ứng khi một dịch vụ dừng. Trong phạm vi đồ án, các node được mô phỏng bằng container trên một máy để phù hợp tài nguyên và khả năng kiểm thử.

Cần phân biệt ba khái niệm: replication sao chép cùng dữ liệu sang node khác; partitioning chia một bảng thành các phần; sharding phân bổ các phần dữ liệu tới các shard. Có nhiều container không tự chứng minh dữ liệu đã được sharding hoặc hệ thống chịu được mất máy chủ.

#### 3.2.2. Những phần đã triển khai

| Hạng mục | Cách thực hiện | Giới hạn |
|---|---|---|
| PostgreSQL replication | Một primary và một standby, truyền WAL bằng streaming bất đồng bộ | Standby chỉ đọc; có thể trễ so với primary |
| MongoDB replication | Replica set `oldshop-rs` với ba data-bearing member khi bật profile | Cùng dữ liệu của replica set, không chia mỗi member giữ một phần |
| Phân hoạch PostgreSQL | `order` phân hoạch HASH theo `order_id`; `system_log` phân hoạch RANGE theo thời gian | Các partition vẫn trong cùng instance/site hiện tại |
| Tách nhóm dữ liệu user | `user_core/profile/secret/wallet`, tái tạo bằng quan hệ theo `user_id` | Là phân rã bảng, chưa phân bổ sang các máy khác nhau |
| Network và lưu trữ | Các service có hostname/volume riêng, cấu hình credentials và healthcheck | Cùng Docker host, còn chung miền lỗi vật lý |
| Theo dõi ứng dụng | Readiness kiểm tra các phụ thuộc; verifier kiểm replication/topology | Healthcheck không thay bài kiểm thử failover và tính đúng dữ liệu |

Log vận hành do người dùng cung cấp trong phiên kiểm tra ngày 03/11/2026 ghi nhận PostgreSQL `streaming:async`, MongoDB một PRIMARY/hai SECONDARY và checker tổng thể `PASS`. Đây là quan sát vận hành đã cung cấp; không phải một lượt fault injection mới được thực hiện để lập báo cáo này.

#### 3.2.3. Những phần đã có bằng chứng kiểm thử và phạm vi bằng chứng

[day6_failover.json](../evidence/day6_failover.json) lưu các tình huống trên môi trường riêng, trong đó có dừng một MongoDB secondary, dừng PostgreSQL replica và kiểm tra ứng dụng/phục hồi.

Môi trường của bằng chứng này sử dụng MongoDB 7. Không dùng kết quả đó để khẳng định đã kiểm thử đầy đủ election/failover trên stack MongoDB 8.0.32 hiện tại. Việc các member đang PRIMARY/SECONDARY chứng minh topology replication đang hoạt động ở thời điểm kiểm tra, chưa chứng minh mọi tình huống mất primary hoặc phân hoạch mạng đều được xử lý đúng.

#### 3.2.4. Những phần chưa hoàn thành

- Chưa phân bổ các node trên nhiều máy vật lý/VM độc lập và kiểm chứng lỗi mất cả máy.
- Chưa có cơ chế tự động failover PostgreSQL, fencing primary cũ và chuyển endpoint ứng dụng một cách hoàn chỉnh.
- Chưa có MongoDB sharded cluster; replica set hiện tại phục vụ sao chép, không phải chia tải lưu trữ theo shard.
- MinIO vẫn single-node, chưa triển khai distributed object storage chịu mất node/máy.
- Chưa có tự động định tuyến đọc ứng dụng sang PostgreSQL standby; biến cấu hình replica không đồng nghĩa đường đọc đã được triển khai.
- Chưa có site thứ hai/FDW phân bổ dữ liệu theo vùng trong luồng nghiệp vụ.
- Chưa kiểm chứng toàn diện RPO/RTO, độ trễ replication và phục hồi dưới tải trên nhiều máy.

MongoDB replica set có cơ chế bầu PRIMARY, nhưng vẫn cần kiểm thử với topology, phiên bản và client thực tế trước khi cam kết thời gian phục hồi. Docker restart policy khởi động lại container cũng không thay thế một cơ chế failover database.

Kết luận về phạm vi: **OldShop đã mô phỏng kiến trúc nhiều node có replication trên một host; chưa hoàn thành hệ thống phân tán chịu lỗi nhiều máy.** Mất host hiện tại vẫn làm toàn bộ stack không phục vụ. Sao chép dữ liệu cũng không thay thế backup vì thao tác xóa/sai dữ liệu có thể được sao chép sang các bản dự phòng.

Các file liên quan: [Compose](../../deploy/docker-compose.distributed.yml), [khởi tạo PostgreSQL replication](../../deploy/data/postgres/init-replication.sh), [khởi tạo standby](../../deploy/data/postgres/start-replica.sh), [Mongo replica set init](../../deploy/data/mongo/init.js), [ma trận phân mảnh](../design/02_fragmentation_matrix.md).

### 3.3. Indexing: bài toán, giải pháp và thực thi

#### 3.3.1. Bài toán hiệu suất

Các đường truy vấn cần tối ưu gồm danh sách sản phẩm đã duyệt theo danh mục/thời gian, tìm kiếm nội dung, lấy review theo sản phẩm, tìm đơn theo người mua, kiểm tra tham chiếu ảnh dùng chung và lấy sự kiện ETL chưa xử lý.

Một index đơn trên từng cột không mặc định giải quyết được mọi truy vấn ghép điều kiện và sắp xếp. Thiết kế phải xem xét cột đứng đầu, chiều sắp xếp, predicate, kiểu index và độ chọn lọc. Đồng thời phải tính chi phí duy trì khi insert/update/delete, dung lượng và index chồng lặp.

#### 3.3.2. Giải pháp: tự thiết kế cấu hình, sử dụng bộ máy index của DB

OldShop định nghĩa cấu hình index mong muốn trong JSON. Phần tự thiết kế là lựa chọn trường, thứ tự khóa, chiều sắp xếp, loại index và options dựa trên workload. PostgreSQL/MongoDB vẫn trực tiếp xây và duy trì cấu trúc index vật lý.

Do đó, dự án **chưa tự lập trình cây B-tree/B+ tree hay thuật toán index thay thế DBMS**. Cách làm tương đồng về bản chất với Lab 3: khai báo key/options rồi gọi cơ chế tạo index của MongoDB; khác ở chỗ OldShop dùng JSON độc lập và có thêm vòng đời migration/snapshot cho PostgreSQL.

| Thành phần | Vai trò |
|---|---|
| [catalog.json](../../database/indexing/catalog.json) | Cấu hình mong muốn cho PostgreSQL và MongoDB |
| [catalog.schema.json](../../database/indexing/catalog.schema.json) | Schema mô tả định dạng khai báo; hỗ trợ editor/kiểm tra cấu hình |
| [index_config.py](../../backend/app/services/index_config.py) | Đọc và kiểm tra cấu hình bằng model/allowlist, tạo biểu diễn chuẩn hóa |
| [index_postgres.py](../../backend/app/services/index_postgres.py) | Biên dịch khai báo được hỗ trợ thành DDL và đối chiếu catalog PostgreSQL |
| [index_mongo.py](../../backend/app/services/index_mongo.py) | Đối chiếu và bổ sung index MongoDB từ key/options |
| [snapshots](../../database/indexing/snapshots) và [releases.json](../../database/indexing/releases.json) | Ghi phiên bản cấu hình và liên kết với lịch sử migration |

Catalog `index-v1` hiện khai báo 98 index PostgreSQL ở cấp root: 61 index ứng dụng/ETL và 37 index gắn với PK/UNIQUE; cùng 19 index MongoDB. Đây không phải tổng số index relation vật lý vì partition có index con. Các index của constraint được kiểm kê và bảo vệ, không tự tạo lại như standalone application index.

Các dạng được hỗ trợ gồm B-tree và GIN với một số biểu thức/opclass cho PostgreSQL; index đơn/ghép, text, wildcard, unique, sparse, partial, TTL theo các giới hạn của bộ kiểm tra cho MongoDB. Không mặc định chấp nhận mọi tính năng index mà DBMS cung cấp.

#### 3.3.3. Ví dụ cấu hình và ý nghĩa cấu trúc index

Ví dụ rút gọn một phần tử PostgreSQL trong catalog:

```json
{
  "name": "idx_product_visible_date_id",
  "schema": "public",
  "table": "product",
  "method": "btree",
  "unique": false,
  "keys": [
    { "column": "created_at", "order": "DESC", "nulls": "FIRST" },
    { "column": "product_id", "order": "ASC", "nulls": "LAST" }
  ],
  "managed_by": "application",
  "predicate": {
    "all": [
      { "column": "status", "op": "eq", "value": 1 },
      { "column": "is_deleted", "op": "eq", "value": false }
    ]
  }
}
```

Đây là B-tree ghép trên `(created_at DESC, product_id ASC)`, chỉ chứa các dòng sản phẩm đã duyệt và chưa xóa mềm. Thứ tự trong mảng `keys` có ý nghĩa; index `(A, B)` không mặc định tương đương `(B, A)`. Predicate giúp thu hẹp tập dòng được lập chỉ mục.

Khái niệm cấu trúc cần phân biệt: JSON có cấu trúc khai báo để diễn đạt thiết kế; B-tree là cấu trúc dữ liệu vật lý do PostgreSQL thực thi. JSON không thay cách PostgreSQL tổ chức nội bộ B-tree. Khi chạy `SELECT`, optimizer xét index vật lý và thống kê DB, không đọc lại file JSON trên host.

Với MongoDB, ví dụ index review theo sản phẩm và thời gian:

```json
{
  "collection": "reviews",
  "keys": [["product_id", 1], ["created_at", -1]],
  "options": { "name": "product_id_1_created_at_-1" }
}
```

Thiết kế đặt `product_id` đứng đầu cho điều kiện bằng, tiếp theo là `created_at` giảm dần để phục vụ lấy review mới. Đây là một phần tử cấu hình, không phải toàn bộ file catalog.

#### 3.3.4. Quy trình thực thi và lý do vẫn giữ SQL migration

```text
PostgreSQL:
JSON → validate/plan → sinh SQL + snapshot + release binding
     → review → migration runner → index vật lý → verify/EXPLAIN

MongoDB:
JSON → validate/plan → create_index(key, options)
     → đối soát → ghi snapshot đã áp → verify/explain
```

Các chức năng CLI gồm `validate`, `plan`, `apply`, `verify`. Plan báo `matched`, `missing`, `conflict`, `unmanaged`; plan PASS vẫn có thể có index missing. Verify mặc định đối chiếu snapshot đã áp, còn `--desired` đối chiếu catalog mong muốn.

PostgreSQL áp DDL qua migration đã đóng băng, giữ kiểm tra checksum và lịch sử. File [001_indexes.sql](../../database/04_migrations/001_indexes.sql) và [007_indexing_v2.sql](../../database/04_migrations/007_indexing_v2.sql) vẫn được giữ vì là lịch sử triển khai. `index-v1` mô tả bộ index tương ứng sau 007; không sinh 008 chỉ để đổi định dạng khai báo. Khi có bổ sung PostgreSQL index thực sự, generator có thể sinh migration tiếp theo cùng snapshot/release mới.

Các index 001–007 là thiết kế SQL đã có trước lớp cấu hình JSON. Không tuyên bố chúng đã được sinh từ JSON ngay từ đầu. Phần bổ sung JSON hiện quản lý cấu hình/đối soát và cung cấp đường sinh migration cho thay đổi tiếp theo.

Công cụ tự động chủ yếu xử lý bổ sung index. Đổi khóa/chiều/unique/TTL của index cùng tên có thể gây conflict và cần quy trình riêng; không tự xóa/rebuild để ép cấu hình khớp. Apply hai engine cũng không có transaction DDL chung xuyên hai DB.

Hướng dẫn lệnh vận hành nằm ở [mục 18 hướng dẫn hệ thống](../HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md#18-cấu-hình-và-chạy-indexing-json) và [hướng dẫn JSON](../HUONG_DAN_INDEXING_JSON.md).

#### 3.3.5. Kiểm chứng và kết quả đo hiệu suất

Phải tách ba loại bằng chứng:

| Loại kiểm tra | Điều được chứng minh | Không tự chứng minh |
|---|---|---|
| Unit/contract test | Parser, validation, compiler và các nhánh xử lý tuân theo test | Hiệu suất DB thật hoặc trạng thái DB đang phục vụ |
| Plan/verify catalog | Định nghĩa index thực tế khớp cấu hình/snapshot | Index được mọi truy vấn sử dụng hoặc làm mọi truy vấn nhanh hơn |
| Benchmark/explain | Cách thực thi và số đo trên workload/môi trường cụ thể | SLA chung, hiệu năng mọi máy hoặc mọi khối lượng dữ liệu |

Bằng chứng triển khai JSON tại [index_config_validation.json](../evidence/index_config_validation.json) ghi nhận kiểm tra trên PG/Mongo riêng, gồm parity sau 007, tạo migration mới trên DB UUID, kiểm tra rollback và xung đột Mongo. Log đi kèm có 92 passed, 31 skipped; đây là phạm vi môi trường kiểm thử được mô tả trong bằng chứng, không phải toàn bộ bài kiểm thử đều đã chạy.

Sau lỗi thiếu dependencies khi dùng Conda base, bộ 53 unit test indexing đã được chạy lại thành công bằng Python 3.13 và dependencies khóa trong container riêng; CLI validate cũng PASS. Hai lượt kiểm tra có môi trường khác nhau, không gộp chúng thành một lượt end-to-end duy nhất.

Benchmark Mongo đọc cấu hình JSON sử dụng 10.000 document trên mỗi collection thử nghiệm. Kết quả lưu trong [summary.json](../benchmark/index_config/mongo/summary.json):

| Truy vấn | Documents examined trước → sau | Số document trả về trước/sau | Execution time trước → sau |
|---|---:|---:|---:|
| Product theo category và `attributes.brand`, limit 20 | 192 → 20 | 20 / 20 | 4 → 8 ms |
| Review theo product, sort thời gian | 10.000 → 10 | 10 / 10 | 12 → 4 ms |
| Order snapshot theo buyer, sort thời gian | 10.000 → 10 | 10 / 10 | 16 → 4 ms |

Số document cần xét giảm trong cả ba trường hợp. Riêng product, thời gian mẫu sau index cao hơn trước; không che giấu kết quả này hoặc suy ra mọi truy vấn đều nhanh hơn. Đây là một explain mỗi pha, có độ phân giải thời gian hạn chế; chưa đủ để kết luận latency ổn định. Chi tiết phương pháp tại [README benchmark JSON](../benchmark/index_config/README.md).

Benchmark PostgreSQL cho việc lựa chọn index v2 lưu tại [báo cáo ngày 01/11/2026](../benchmark/indexing_v2/2026-11-01/README.md). Ví dụ các ứng viên đo riêng trên fixture lớn:

| Truy vấn | Median thời gian trước → sau | Mục đích index |
|---|---:|---|
| Q02_all | 1,086 → 0,213 ms | Danh sách sản phẩm theo thứ tự thời gian/ID |
| Q15_image_missing | 52,626 → 0,069 ms | Tra cứu tham chiếu URL ảnh |
| Q14_status | 21,227 → 0,157 ms | Lấy lần chạy ETL gần nhất |

Các số này thuộc thí nghiệm lịch sử trên môi trường riêng, không phải thời gian cam kết cho DB hiện tại. Việc chuyển cùng định nghĩa index sang JSON không tự thay đổi hiệu suất vật lý.

Các file `before_*.json`, `after_*.json` và `summary.json` dưới `docs/benchmark/` là kết quả chạy công cụ đo, không phải khai báo tạo index. Script chọn workload và cách đo được viết sẵn, nhưng chỉ số kết quả được thu từ lần chạy DB, không phải giá trị hardcode dùng thay phép đo. Khi muốn biết hiệu suất hiện tại phải chạy lại benchmark phù hợp và lưu bằng chứng mới.

## 4. Tổng kết

OldShop giải quyết bài toán người dùng vừa mua vừa bán đồ cũ bằng hệ thống có quản lý tài khoản, kiểm duyệt tin đăng và xử lý giao dịch. Kiến trúc dữ liệu được phân chia theo yêu cầu nghiệp vụ thay vì đưa toàn bộ thông tin vào một loại kho lưu trữ.

| Nội dung | Kết quả đã đạt | Giới hạn cần trình bày rõ |
|---|---|---|
| Hợp nhất dữ liệu | PostgreSQL giữ nghiệp vụ/quan hệ, MongoDB giữ thuộc tính linh hoạt và bản đọc, MinIO giữ file | Có dữ liệu chiếu trùng theo ownership; không có ACID chung cho ba kho |
| ETL | Có extract/transform/upsert, transactional outbox, retry, quality/reconcile và tổng hợp | Bản đọc có độ trễ; vẫn cần vận hành và xử lý backlog/lỗi |
| Phân tán | Có PG streaming replica, Mongo replica set và mô phỏng nhiều node Docker | Một host; chưa HA nhiều máy, PG auto-failover, Mongo sharding, MinIO distributed |
| Indexing | Thiết kế theo workload, cấu hình JSON, migration/snapshot và verify | Dùng bộ máy index của DBMS; chưa tự viết cấu trúc index vật lý |
| Đánh giá hiệu suất | Có explain và benchmark trước/sau, số đo kèm điều kiện thử nghiệm | Không suy rộng mẫu đo thành cam kết hiệu năng cho mọi môi trường |

Hướng tiếp theo là kiểm chứng election/phục hồi trên MongoDB 8 hiện tại, triển khai node qua các máy độc lập, xây quy trình failover PostgreSQL và dự phòng object storage, đồng thời tiếp tục đo index theo tần suất truy vấn thực tế. Các bước mở rộng này cần kiểm tra cả tính đúng dữ liệu và khả năng phục hồi, bên cạnh thời gian truy vấn.

Báo cáo phản ánh trạng thái triển khai và phạm vi bằng chứng đã có; việc tổng hợp báo cáo không tự áp migration, tạo index mới hoặc thay đổi dữ liệu của hệ thống đang chạy.
