# OldShop — Chạy và kiểm chứng hai site PostgreSQL

Ngày cập nhật: 04/11/2026. Thiết kế tham khảo: [đánh giá và kế hoạch](DANH_GIA_VA_KE_HOACH_CSDL_PHAN_TAN_LAB02.md).

## 1. Kết quả và phạm vi

Đã triển khai hai PostgreSQL 16 độc lập, phân mảnh ngang `product` theo site quản lý seller, phân mảnh dẫn xuất `product_image`, nhân bản danh mục và FDW chỉ đọc A → B. Mỗi site ghi được dữ liệu của mình. A có các view hợp nhất để truy vấn toàn bộ danh mục.

Theo lựa chọn của người dùng, hai site được kiểm thử bằng **hai IP ảo trên cùng một Docker host**. Đây là kiểm chứng chức năng phân tán qua mạng Docker, chưa phải kiểm chứng chịu lỗi hai máy vật lý.

| Thành phần | Địa chỉ trên máy chủ | Địa chỉ mạng Docker | Database |
|---|---|---|---|
| Site A | `127.0.0.1:56431` | `172.29.82.11:5432` | `oldshop_1` |
| Site B | `127.0.0.1:56432` | `172.29.82.12:5432` | `oldshop_2` |
| API danh mục chỉ đọc | `http://127.0.0.1:56480` | `172.29.82.20:8000` | Đọc global view tại A |

Tên database không chứa từ khóa bài tham khảo. Database, volume và mạng của hệ thống này tách khỏi ứng dụng OldShop hiện hữu. MongoDB/MinIO và các volume cũ không được chuyển đổi.

Phần triển khai này hoàn thành phạm vi M1 trên IP ảo, đồng thời có gateway thử nghiệm phần đọc của P5. Giao dịch giỏ hàng/thanh toán, đồng bộ Mongo/media nhiều site, chuyển dữ liệu thật và frontend hiện hữu vẫn cần các bước M2 trong kế hoạch.

## 2. Chuẩn bị và khởi động

Yêu cầu: Docker Engine/Desktop, Docker Compose hỗ trợ `--wait`, Python 3.11 trở lên. Host không cần cài psycopg2: script quản trị chạy `psql` bên trong container PostgreSQL. Image database mặc định là `postgres:16-alpine`.

Chạy các lệnh từ thư mục repository. Docker phải truy cập được bằng tài khoản đang dùng.

```bash
python3 deploy/scripts/sites.py prepare
python3 deploy/scripts/sites.py up
python3 deploy/scripts/sites.py bootstrap
python3 deploy/scripts/sites.py fdw
python3 deploy/scripts/sites.py status
python3 deploy/scripts/sites.py verify
```

- `prepare` tạo `deploy/sites/.env` với credential ngẫu nhiên và quyền file `600`; từ chối ghi đè. Nếu đã có file thì bỏ qua bước này.
- `up` dựng hai container/volume riêng trong project `oldshop-sites`.
- `bootstrap` ghép schema SQL-first và migrations `001`–`007` từ source, loại toàn bộ include seed cũ, rồi thêm ownership, fixture và role. Cùng một schema được áp trong giao dịch lên từng database mới.
- Database có bảng ứng dụng nhưng không có marker cài đặt sẽ bị từ chối bootstrap. Nếu đã cài đúng source/site, chạy lại không nạp lại fixture. Source thay đổi thì dừng để kiểm tra, không tự ghi đè cấu trúc.
- `fdw` tạo/cập nhật foreign server, user mapping và view toàn cục; kiểm tra server từ xa nhận diện là B.
- `verify` có thao tác tạm dừng từng **site mới**, khôi phục trong `finally`, cấp ID đồng thời và dựng lại một project sạch khác. Chỉ chạy khi đang dùng bộ fixture chuẩn, trước khi thêm dữ liệu thử riêng.

Không chạy `backend/scripts/init_db.py` hoặc ETL worker hiện hữu lên hai database này. Chúng có quy tắc bootstrap/giao dịch khác và chưa được chuyển sang nhiều site.

Nếu cổng hoặc subnet đã có dịch vụ khác sử dụng, chỉnh `.env` trước khi `up`. Khi đổi subnet phải đổi cả IP A/B, `SITE_B_FDW_HOST`, nguồn HBA và IP gateway API cho tương ứng. Địa chỉ mặc định là cấu hình mô phỏng, không dùng làm IP LAN/VPN giữa hai host khác nhau.

## 3. Schema, dữ liệu và quyền

Schema kế thừa toàn bộ bảng, khóa, function, trigger và migration hiện có; không đổi checksum migration lịch sử. Cài đặt thử nghiệm lưu source hash riêng trong `distributed_installation`.

Phần mở rộng nằm ở [01_site_schema.sql](../database/distributed/01_site_schema.sql):

- `site_config` có đúng dòng cấu hình site được nạp lúc cài đặt; writer không được sửa.
- `seller_site` ánh xạ seller sang A/B, dùng cùng fixture ở hai site.
- `product.site_id` tham chiếu cặp seller–site; trigger chặn site sai máy và đổi ownership.
- ID product/ảnh ở A là số lẻ dương, ở B là số chẵn dương. Sequence tăng 2 và trigger kiểm cả ID truyền tường minh.
- Ảnh tham chiếu product tại site cục bộ nên không thể gắn ảnh A trực tiếp vào product chỉ có ở B.
- Trigger outbox/cleanup được thực thi với quyền owner trên schema không cho PUBLIC tạo object; writer không được ghi trực tiếp bảng vận hành.
- Thu hồi quyền EXECUTE mặc định của các function nghiệp vụ để tài khoản reader không dùng function `SECURITY DEFINER` làm đường ghi vòng.

Fixture giả lập mỗi site có 3 seller, 5 product, 8 ảnh; chung 3 category và một moderator. Có category rỗng, seller rỗng, seller chỉ có product ngoài tháng 11, product chưa duyệt/xóa mềm, product không ảnh và product nhiều ảnh. Các tài khoản giả không có password đăng nhập sử dụng được; wallet bằng 0. URL ảnh là metadata minh họa, không xác nhận có file ảnh thật tại đường dẫn đó.

| Role | Mục đích |
|---|---|
| `site_admin` | Quản trị schema/site; quản trị bằng mật khẩu qua TCP hoặc socket nội bộ container |
| `site_writer` | Đọc/ghi product và ảnh hợp lệ tại site; đọc danh mục tham chiếu |
| `b_reader` | Chỉ đọc đúng bảng danh mục/identity được cho phép; là role kết nối FDW tới B |
| `global_reader` | Chỉ đọc view toàn cục tại A; dùng cho gateway API |

Mật khẩu nằm trong `.env` được Git bỏ qua. Đổi giá trị password trong `.env` không tự thay password role đã tạo; cần quy trình rotate role/mapping rồi cập nhật client. Không xóa `.env` khi muốn tiếp tục dùng volume hiện hữu.

`bootstrap`/`access` tạo HBA chỉ cho các nguồn localhost, gateway của Docker host, nguồn reader đã cấu hình và IP API được phép. Các nguồn còn lại bị từ chối; phép thử quyền kiểm cả trường hợp IP nguồn không được phép. Publish cổng host mặc định chỉ trên `127.0.0.1`.

## 4. Truy vấn và ghi cục bộ

Trên máy chủ có `psql`, kết nối bằng role phù hợp; mật khẩu nhập tương tác từ thông tin trong file cấu hình riêng:

```bash
psql -h 127.0.0.1 -p 56431 -U global_reader -d oldshop_1 -W
```

```sql
SELECT product_id, title, site_id FROM v_product ORDER BY product_id;
SELECT category_id, name FROM v_category ORDER BY category_id;
SELECT site_id FROM v_site_health ORDER BY site_id;
```

View category và seller mapping chỉ lấy bản A, không hợp hai bản nhân bản. View product/ảnh giữ cả dòng xóa mềm để tái tạo; API/query nghiệp vụ có bộ lọc riêng.

Ghi một product B bằng kết nối trực tiếp B:

```bash
psql -h 127.0.0.1 -p 56432 -U site_writer -d oldshop_2 -W
```

```sql
BEGIN;
INSERT INTO product(seller_id, category_id, title, price, quantity)
VALUES (202, 1, 'Sản phẩm mới tại B', 120000, 1)
RETURNING product_id, site_id;
COMMIT;
```

Từ giao dịch đọc mới tại A, product này xuất hiện trong `v_product` mà không copy/import lại dữ liệu B. Nếu đã thêm dữ liệu riêng, bộ kiểm thử đối chiếu fixture sẽ báo khác dữ liệu; đây không phải lỗi FDW. Nên giữ bộ fixture chuẩn để kiểm chứng, hoặc tạo project/site riêng khi thử dữ liệu mới.

`sites.py` không cung cấp thao tác reset/xóa dữ liệu. `stop`/`down` giữ volume. Không chạy lại bộ schema lên database đã cài đặt.

Bộ truy vấn [Q1–Q6](../database/distributed/queries/) dùng `psql` variables; Q1 cần admin tại A để đọc trực tiếp `site_b`. Ví dụ Q5 sau khi kết nối `global_reader` vào A:

```sql
\set from_date '2026-11-01'
\set to_date '2026-12-01'
\i database/distributed/queries/Q5.sql
```

Lệnh `\i` ở ví dụ trên giả định mở `psql` tại repository root. Q3 nhận thêm `product_id`; fixture mặc định dùng ID 4 ở B.

## 5. API danh mục toàn cục

```bash
python3 deploy/scripts/sites.py catalogue
python3 deploy/scripts/sites.py verify-api
```

API docs: [http://127.0.0.1:56480/docs](http://127.0.0.1:56480/docs).

| Endpoint | Hành vi |
|---|---|
| `GET /products` | Product đã duyệt, chưa xóa; category hoạt động; có ảnh và site |
| `GET /products?skip=0&limit=2` | Phân trang sau khi hợp toàn cục, trả cả total |
| `GET /products?search=Site%20B&sort_by=price` | Lọc/tìm/sắp xếp trước phân trang |
| `GET /products?category_id=2` | Lọc theo danh mục |
| `GET /products/4` | Chi tiết product và ảnh ở B |
| `GET /health` | Liveness tiến trình API |
| `GET /ready` | Kiểm tra A và B đều đọc được |

Gateway dùng role `global_reader`, giao dịch chỉ đọc và snapshot lặp lại trong mỗi request. Mọi request dữ liệu kiểm tra cả hai site trước; mất B thì trả `503`, kể cả khi `limit=1` có thể lấy đủ dòng A. Không trả thiếu dữ liệu như thể là kết quả toàn cục đầy đủ.

Đây là module chạy riêng [catalogue_gateway.py](../backend/app/catalogue_gateway.py), dùng dependency sẵn có của backend và [Compose tùy chọn](../deploy/sites/compose.catalog.yml). Không thay router/ORM của ứng dụng cũ. Gateway không tăng view_count, ghi sản phẩm, chạy checkout hoặc merge Mongo metadata. Ảnh giả lập chỉ trả metadata.

Mặc định tái sử dụng image backend có sẵn `oldshop-data-backend:day6`, mount đúng module gateway chỉ đọc. Nếu máy chưa có image, build bằng Dockerfile backend trong repository; đặt `BACKEND_IMAGE` nếu muốn dùng tag khác. Kiểm thử đang chạy trong container đã dùng source module hiện tại, không phải bản module cũ trong image.

## 6. Bộ kiểm chứng và bằng chứng

[test_results.json](evidence/distributed/test_results.json) ghi trạng thái và chi tiết T01–T12:

1. Kết nối TCP A → B bằng `b_reader`, database và IP hai đầu đúng.
2. Commit tại B xuất hiện tại A trong giao dịch mới; giao dịch cũ vẫn giữ snapshot.
3. Reader không ghi/đọc secret/wallet/gọi function nghiệp vụ để ghi; HBA chặn nguồn không được phép.
4. B dừng: A đọc/ghi local được, query global lỗi trong timeout, B bật lại thì đọc được.
5. Chặn khóa trùng, sai FK/site/seller, giá/tồn kho âm và ownership sai.
6. Tái tạo đủ nội dung/khóa và schema tương đương hai site.
7. Bản sao category/mapping giống nhau, view không đếm lặp.
8. Q1–Q6 khớp expected result tính độc lập từ fixture, giữ trường hợp rỗng.
9. Bốn writer đồng thời cấp 40 ID không trùng, đúng quy tắc site; giao dịch được rollback.
10. A dừng: B vẫn đọc/ghi local được và kết nối phục hồi.
11. Bootstrap chạy lại không nạp chồng; dựng cặp site mới hoàn toàn, kiểm schema/fixture và Q1–Q6, rồi gỡ đúng project tạm đó.
12. Đo thời gian local/remote/global và lưu plan thực thi.

T11 dùng một subnet riêng `172.29.83.0/24` và host port ngẫu nhiên; nếu mạng này đã được sử dụng, cần chọn dải trống tương ứng trong bước diễn tập. T12 là phép đo seed nhỏ trên cùng host, không phải benchmark sức chứa hoặc bằng chứng nhanh hơn database tập trung.

Các file bổ sung:

- [Manifest SQL source](evidence/distributed/source_manifest.json).
- [Fixture](../database/distributed/fixture_manifest.json) và [expected results](../database/distributed/expected_results.json).
- [So sánh schema](evidence/distributed/schema_comparison.json).
- [Diễn tập dựng sạch](evidence/distributed/clean_rebuild.json).
- [Plan và thời gian thực thi](evidence/distributed/performance_results.json).
- [Kiểm thử HTTP/API](evidence/distributed/api_results.json).
- [Inventory](evidence/distributed/inventory.json).

Mỗi file kết quả có phạm vi/giới hạn; không dùng evidence một host để khẳng định đã chạy LAN/VPN giữa hai máy. Bộ kiểm chứng dừng sớm nếu FAIL và giữ kết quả lỗi để kiểm tra. Không chạy đồng thời `verify` và `verify-api` vì cả hai đều chủ động dừng/bật site.

## 7. Chuyển sang hai máy qua LAN/VPN

Hướng dẫn từng bước cho cả Windows/Linux: [Kết nối hai site bằng Tailscale](HUONG_DAN_TAILSCALE_WINDOWS_LINUX.md). Tài liệu đó dùng cấu hình/project VPN riêng và có phương án TCP Serve để giữ PostgreSQL chỉ publish ở localhost; các bước dưới đây mô tả phương án publish trực tiếp ra IP LAN/VPN.

Khi có máy B, giữ nguyên schema/fixture và làm theo thứ tự:

1. Checkout cùng phiên bản repository trên hai máy; tạo `.env` riêng bằng `prepare` ở mỗi máy. Không sao chép toàn bộ password quản trị A sang B hoặc ngược lại.
2. Máy A chạy lệnh với `--site A`; máy B chạy với `--site B`. Mỗi nơi chỉ tạo volume PostgreSQL của site mình.
3. Trên B đặt `SITE_B_BIND_IP` bằng IP LAN/VPN của host B, `SITE_B_PORT` bằng cổng công bố; đặt `SITE_B_READER_SOURCE_CIDR` thành IP nguồn A thực tế mà B nhìn thấy, thường là IP host A sau NAT.
4. Cấu hình firewall host B chỉ cho IP A tới cổng PostgreSQL B. Nếu dùng VPN, xác nhận tiến trình/container PostgreSQL A có đường tới IP VPN B.
5. Trên A đặt `SITE_B_FDW_HOST` bằng IP LAN/VPN B, `SITE_B_FDW_PORT` bằng cổng publish của B và `SITE_B_DB_NAME=oldshop_2`. Cung cấp đúng password `b_reader` của B vào `SITE_B_READER_PASSWORD` của file A qua kênh riêng.
6. Khởi tạo B trước, kiểm đăng nhập trực tiếp từ A, rồi chạy `fdw --site A` trên A.
7. Thu lại bằng chứng hai hostname/IP/site, cập nhật/commit, phân quyền, lỗi và phục hồi. `verify` tự động hiện dùng Docker quản lý cả hai site local; không dùng nó để dừng dịch vụ trên host B từ xa. Với hai host, thực hiện từng bước kiểm thử tương ứng trong hướng dẫn hoặc bổ sung điều khiển remote được cho phép.

Ví dụ trên B:

```bash
python3 deploy/scripts/sites.py up --site B
python3 deploy/scripts/sites.py bootstrap --site B
```

Ví dụ trên A sau khi B sẵn sàng:

```bash
python3 deploy/scripts/sites.py up --site A
python3 deploy/scripts/sites.py bootstrap --site A
python3 deploy/scripts/sites.py fdw --site A
python3 deploy/scripts/sites.py catalogue --site A
```

Khi IP/cổng thay đổi: cập nhật publish Compose, firewall, HBA bằng `access` và foreign server bằng `fdw` ở nơi tương ứng. Hostname/IP trong `inet_server_addr()` có thể phản ánh container sau NAT; kèm site identity và thông tin host để xác định đúng B.

## 8. Dừng và khởi động lại

```bash
python3 deploy/scripts/sites.py stop
python3 deploy/scripts/sites.py up
python3 deploy/scripts/sites.py catalogue
```

`down` gỡ container/network của project, giữ volume. `up` tạo lại container dựa trên volume và credential cũ. File `.env` phải được giữ lại.

Schema hiện tại phục vụ triển khai phân mảnh danh mục. Không chuyển connection string của ứng dụng thương mại cũ sang các database này để vận hành tiền/hàng thật trước khi hoàn thành các bước M2 và đối soát/migration đã nêu trong kế hoạch.
