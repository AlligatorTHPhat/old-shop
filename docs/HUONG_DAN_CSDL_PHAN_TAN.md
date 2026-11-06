# OldShop — Chạy và kiểm chứng hai site PostgreSQL

Ngày cập nhật: 05/11/2026. Thiết kế tham khảo: [đánh giá và kế hoạch](DANH_GIA_VA_KE_HOACH_CSDL_PHAN_TAN_LAB02.md).

**Chọn đúng môi trường trước khi chạy lệnh:**

| Môi trường | Phần cần làm theo |
|---|---|
| Hai PostgreSQL mô phỏng trên cùng máy | Mục 2–6: mặc định A `56431`, B `56432`, FDW tới IP Docker `172.29.82.12:5432`. |
| A Linux và B Windows qua Tailscale | Mục 7: A `56431`, B `57432`, FDW tới **IP Tailscale của Windows**; phải bật TCP Serve và cập nhật mật khẩu reader. |
| Project VPN riêng `oldshop-vpn` / `.env.vpn` | Theo [hướng dẫn Tailscale riêng](HUONG_DAN_TAILSCALE_WINDOWS_LINUX.md); dùng đúng project, file env và cổng của môi trường đó. |

Không trộn các cổng/project/file env giữa ba môi trường. Lệnh terminal chạy trong repository; lệnh SQL và lệnh bắt đầu bằng `\` chạy bên trong `psql`. Dùng `\q` để thoát `psql` trước khi chạy Python, Docker, `nano` hoặc Tailscale.

## 1. Kết quả và phạm vi

Đã triển khai hai PostgreSQL 16 độc lập, phân mảnh ngang `product` theo site quản lý seller, phân mảnh dẫn xuất `product_image`, nhân bản danh mục và FDW chỉ đọc A → B. Mỗi site ghi được dữ liệu của mình. A có các view hợp nhất để truy vấn toàn bộ danh mục.

Các kết quả tự động đang lưu trong repository kiểm thử **hai IP ảo trên cùng một Docker host**. Ngày 05/11, người dùng đã xác nhận kết nối hai máy chạy được sau khi cấu hình FDW, TCP Serve và mật khẩu reader; mục 7 ghi lại đầy đủ quy trình này. Xác nhận đó không tự biến bộ evidence tự động một host thành bộ kiểm chứng chịu lỗi hai host.

| Thành phần | Địa chỉ trên máy chủ | Địa chỉ mạng Docker | Database |
|---|---|---|---|
| Site A | `127.0.0.1:56431` | `172.29.82.11:5432` | `oldshop_1` |
| Site B | `127.0.0.1:56432` | `172.29.82.12:5432` | `oldshop_2` |
| API danh mục chỉ đọc | `http://127.0.0.1:56480` | `172.29.82.20:8000` | Đọc global view tại A |

Tên database không chứa từ khóa bài tham khảo. Database, volume và mạng của hệ thống này tách khỏi ứng dụng OldShop hiện hữu. MongoDB/MinIO và các volume cũ không được chuyển đổi.

Phần triển khai này hoàn thành phạm vi M1 trên IP ảo, đồng thời có gateway thử nghiệm phần đọc của P5. Giao dịch giỏ hàng/thanh toán, đồng bộ Mongo/media nhiều site, chuyển dữ liệu thật và frontend hiện hữu vẫn cần các bước M2 trong kế hoạch.

## 2. Chuẩn bị và khởi động

Yêu cầu: Docker Engine/Desktop, Docker Compose hỗ trợ `--wait`, Python 3.11 trở lên. Host không cần cài psycopg2: script quản trị chạy `psql` bên trong container PostgreSQL. Image database mặc định là `postgres:16-alpine`.

Chạy các lệnh từ thư mục repository. Docker phải truy cập được bằng tài khoản đang dùng. **Chuỗi lệnh dưới dành cho mô phỏng hai site trên cùng host. Nếu A/B là hai máy riêng, dùng mục 7, không chạy mặc định cả hai site trên từng máy.**

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

Ví dụ cổng dưới đây dành cho mô phỏng cùng host. Với B Windows cổng `57432`, dùng lệnh tách theo máy ở mục 7. Các view toàn cục được cấu hình tại **A**; trên **B**, writer/reader dùng bảng local và `site_identity` theo quyền tương ứng.

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

### 7.1. Thông số và tài khoản của quy trình A Linux / B Windows

Quy trình dưới giữ **project `oldshop-sites` và file `deploy/sites/.env` riêng trên mỗi máy**, phù hợp trường hợp A đang chạy cổng `56431`, B Windows cổng `57432`. Không tạo project/volume mới chỉ để đổi đích FDW của A. Nếu đã dùng project/file khác, thay chúng **nhất quán trong mọi lệnh**, kể cả Docker Compose và cập nhật password.

| Thông số | Máy A Linux | Máy B Windows |
|---|---|---|
| Database sử dụng | `oldshop_1` | `oldshop_2` |
| Service sử dụng | `pg-a` | `pg-b` |
| PostgreSQL trên host | `127.0.0.1:56431` | `127.0.0.1:57432` |
| PostgreSQL trong container | `5432` | `5432` |
| Vai trò trong kiểm chứng | `global_reader` đọc view tại A | `site_writer` ghi product local B |
| Vai trò kết nối liên site | User mapping của `site_admin` trên A | Đăng nhập từ xa bằng `b_reader` trên B |

Trong các ví dụ, **`100.88.10.25` là IP Tailscale minh họa của B**: thay bằng kết quả `tailscale ip -4` trên Windows. Không gõ nguyên `100.xx.xxx.xx`; đây không phải địa chỉ hợp lệ. Hai máy cần cùng tailnet hoặc được chia sẻ/quyền truy cập phù hợp, policy cho phép A tới B TCP `57432`. Cài đặt/đăng nhập Tailscale theo [hướng dẫn chi tiết](HUONG_DAN_TAILSCALE_WINDOWS_LINUX.md).

Ba mật khẩu khác nhau cần phân biệt:

| Đăng nhập | Mật khẩu phải lấy ở đâu? |
|---|---|
| `global_reader` tại A | `SITE_A_GLOBAL_PASSWORD` trong file của A. |
| `site_writer` tại B | `SITE_B_WRITER_PASSWORD` trong file của B. |
| A đọc B bằng `b_reader` | Password **đang lưu trong PostgreSQL B**; bình thường là `SITE_B_READER_PASSWORD` đã dùng khi bootstrap B. File A phải chứa cùng giá trị này để tạo user mapping. |

Không cần đồng nhất password admin/writer/global của hai máy; chỉ chuyển riêng password `b_reader` qua kênh riêng. Không đăng `.env` hoặc mật khẩu lên chat. Sửa `.env` không tự đổi password role trong database, và sửa biến FDW cũng không tự đổi `server_b` đang tồn tại: phải chạy bước 7.5.

### 7.2. Máy B Windows — cấu hình và kiểm tra PostgreSQL local

Mở PowerShell tại repository trên B, ví dụ `C:\Study\old-shop`. Kiểm Docker và Tailscale:

```powershell
docker compose version
tailscale status
tailscale ip -4
```

**Chỉ nếu chưa có `deploy/sites/.env`**, tạo một lần:

```powershell
python deploy/scripts/sites.py prepare --env deploy/sites/.env
```

Máy đã có DB/volume phải giữ file và password cũ, không chạy prepare để tạo lại. Mở file trên B:

```powershell
notepad deploy/sites/.env
```

Đặt/kiểm tra các dòng sau, giữ nguyên các password đã sinh:

```dotenv
SITE_B_DB_NAME=oldshop_2
SITE_B_BIND_IP=127.0.0.1
SITE_B_PORT=57432
```

Khởi động đúng site B, dùng lại volume của project:

```powershell
python deploy/scripts/sites.py up --site B --project oldshop-sites --env deploy/sites/.env
```

**Chỉ với database mới chưa bootstrap**, chạy tiếp:

```powershell
python deploy/scripts/sites.py bootstrap --site B --project oldshop-sites --env deploy/sites/.env
```

Nếu DB đã cài đúng thì không cần bootstrap lại. Marker/source khác phải được kiểm tra, không xóa volume để vượt lỗi. Nếu trước đây đã dựng cả pg-a lẫn pg-b trên Windows, không cần xóa chúng để sửa FDW: quy trình này chọn đúng `pg-b`, còn A Linux phải trỏ IP Windows.

Kiểm cổng local và container:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 57432
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Mong đợi `TcpTestSucceeded: True` và `pg-b` healthy, port mapping `127.0.0.1:57432->5432/tcp`. Kết quả này **chỉ chứng minh Windows local vào được PG B**, chưa chứng minh IP Tailscale B nhận kết nối. Nếu False, sửa trạng thái/cổng PostgreSQL trước bước tiếp theo.

### 7.3. Máy B Windows — bật TCP Serve bắt buộc cho cổng chỉ bind localhost

Mở **PowerShell bằng Run as Administrator** trên B:

```powershell
tailscale serve --bg --tcp=57432 tcp://127.0.0.1:57432
tailscale serve status
```

Mong đợi cấu hình TCP port `57432` trong tailnet chuyển tới `127.0.0.1:57432` trên B. **`No serve config` nghĩa là bước này chưa được cấu hình**, dù Test-NetConnection local đã True. Nếu CLI yêu cầu bật quyền Serve, làm theo URL nó cung cấp rồi chạy lại. Dùng raw TCP; không dùng HTTP proxy, TLS termination hoặc Funnel/public exposure. Cú pháp và ý nghĩa `--tcp`, `--bg`, `status` theo [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

Luồng kết nối là **PostgreSQL A trong container → IP Tailscale Windows:57432 → Serve → 127.0.0.1:57432 → pg-b:5432**. Serve là proxy; PostgreSQL B có thể thấy nguồn localhost/gateway Docker thay vì IP Tailscale A. HBA do bootstrap/access tạo đã có rule password cho gateway Docker; tailnet policy kiểm soát máy A. Không thay HBA thành tin cậy mọi nguồn để vượt lỗi.

### 7.4. Kiểm mật khẩu b_reader trước khi cấu hình FDW

Nếu B có `psql`, kiểm ngay trên **Windows B**:

```powershell
psql -h 127.0.0.1 -p 57432 -U b_reader -d oldshop_2 -W
```

Nhập password reader của B. Trong psql:

```sql
SELECT current_database(), current_user;
SELECT site_id FROM site_identity;
SELECT product_id, title, site_id FROM product ORDER BY product_id;
\q
```

Mong đợi `oldshop_2`, `b_reader`, site `B`. Reader này được đọc bảng danh mục, không dùng view toàn cục ở A hoặc tài khoản global_reader để thay cho kiểm password B.

Nếu không biết password hiện tại hoặc file B đã bị sửa sau bootstrap, đặt lại **riêng `b_reader` trên B**, không bootstrap/xóa DB. Mở psql admin bên trong đúng container, không cần cài psql trên host:

```powershell
docker compose -p oldshop-sites --env-file deploy/sites/.env -f deploy/sites/compose.site-b.yml exec pg-b psql -U site_admin -d oldshop_2
```

Trong psql admin B:

```text
\password b_reader
\q
```

Nhập password mới hai lần, ít nhất 16 ký tự để phù hợp kiểm tra của script. `\password` nhập tương tác thay vì ghi password rõ trong câu SQL/history; xem [psql PostgreSQL 16](https://www.postgresql.org/docs/16/app-psql.html). Sau đó cập nhật cùng giá trị vào `SITE_B_READER_PASSWORD` **ở file B và file A**. Không tự thêm dấu nháy bao password vào file: parser `sites.py` đọc giá trị sau `=` và không loại dấu nháy.

Trên **terminal Linux A**, kiểm kết nối tới B thật. Thay IP ví dụ trước khi chạy:

```bash
tailscale status
psql -h 100.88.10.25 -p 57432 -U b_reader -d oldshop_2 -W
```

Trong phiên kết nối này:

```sql
SELECT current_database(), current_user, inet_client_addr(), inet_server_addr();
SELECT site_id FROM site_identity;
\q
```

Mong đợi `oldshop_2`, role `b_reader`, site `B`. IP do PostgreSQL báo có thể là gateway/container sau proxy; cần đối chiếu thêm hostname/IP Tailscale của Windows. Nếu host A vào được nhưng FDW vẫn lỗi, kiểm riêng từ container A tại mục 9.

### 7.5. Máy A Linux — cập nhật đúng file môi trường và chạy fdw bằng quyền admin

Thoát psql bằng `\q` trước khi chạy lệnh terminal. Kiểm Docker và chỉ tạo file nếu A hoàn toàn mới:

```bash
docker compose version
```

**Chỉ nếu chưa có file env trên A:**

```bash
python3 deploy/scripts/sites.py prepare --env deploy/sites/.env
```

Mở file A:

```bash
nano deploy/sites/.env
```

Kiểm/sửa các dòng sau; thay IP ví dụ bằng IP Windows thật, điền password reader đã kiểm ở bước 7.4 và giữ password admin/global của A:

```dotenv
SITE_A_DB_NAME=oldshop_1
SITE_A_BIND_IP=127.0.0.1
SITE_A_PORT=56431
SITE_B_DB_NAME=oldshop_2
SITE_B_FDW_HOST=100.88.10.25
SITE_B_FDW_PORT=57432
SITE_B_READER_PASSWORD=MAT_KHAU_B_READER_DANG_DUNG_TREN_B
```

Giá trị password ở trên chỉ là nhãn minh họa, không để nguyên. Nano lưu bằng Ctrl+O, Enter, thoát Ctrl+X. Kiểm riêng các biến không chứa password bằng `grep` có sẵn, không yêu cầu cài `rg`:

```bash
grep -E '^SITE_(A_PORT|B_DB_NAME|B_FDW_HOST|B_FDW_PORT)=' deploy/sites/.env
```

FDW phải dùng IP Tailscale Windows và port `57432`, **không dùng `172.29.82.12:5432` của B mô phỏng trên Linux**. Không cần sửa SITE_B_PORT trên file A để đổi FDW: script đọc SITE_B_FDW_HOST/PORT; SITE_B_PORT dùng publish pg-b khi chạy site B.

Nếu cần khởi động A:

```bash
python3 deploy/scripts/sites.py up --site A --project oldshop-sites --env deploy/sites/.env
```

**Chỉ nếu DB A mới chưa bootstrap:**

```bash
python3 deploy/scripts/sites.py bootstrap --site A --project oldshop-sites --env deploy/sites/.env
```

Với A đã có dữ liệu, chuyển thẳng tới lệnh cấu hình dưới. Đây là bước phải chạy sau khi sửa IP/cổng/password reader:

```bash
python3 deploy/scripts/sites.py fdw --site A --project oldshop-sites --env deploy/sites/.env
```

Mong đợi thông báo `FDW A → B configured and remote site identity checked`. Script dùng **site_admin**, cập nhật host/port/dbname của `server_b`, password user mapping của site_admin tới `b_reader` B, các view và kiểm site identity. Không chạy `ALTER SERVER` trong phiên global_reader. Chỉ sửa `.env` hoặc đăng nhập lại psql không tự áp thay đổi.

Nếu script lỗi, đọc lỗi cụ thể: timeout/refused thuộc đường TCP; password authentication failed thuộc password reader; admin authentication failed có thể do chọn sai env/project hoặc password admin A. Script có thể đã commit cấu hình trước khi kiểm remote; lỗi cuối không có nghĩa mọi thay đổi đều được rollback. Không in toàn bộ `.env` để chẩn đoán.

### 7.6. Máy A — kiểm đích FDW và quyền reader

Trên terminal A:

```bash
psql -h 127.0.0.1 -p 56431 -U global_reader -d oldshop_1 -W
```

Nhập SITE_A_GLOBAL_PASSWORD của A. Trong psql:

```sql
SELECT current_database(), current_user;
SELECT srvname, srvoptions FROM pg_foreign_server;
SELECT site_id FROM v_site_health ORDER BY site_id;
SELECT product_id, title, site_id
FROM v_product WHERE site_id = 'B' ORDER BY product_id DESC LIMIT 10;
```

Mong đợi DB `oldshop_1`, user `global_reader`; srvoptions có host IP Windows, port57432, dbname oldshop_2; health có A/B. Health A/B **không tự chứng minh hai máy**: B mô phỏng cũ cũng trả site B. Phải kiểm đúng host và bản ghi mới ở7.7.

`global_reader` chỉ đọc các view được cấp quyền: `v_product`, `v_product_image`, `v_category`, `v_seller_site`, `v_site_health` và `site_identity`. Lệnh `FROM product` local hoặc `FROM site_b.product` trực tiếp sẽ bị từ chối theo thiết kế. Không cấp thêm quyền cho reader để vượt lỗi này. Nếu cần chẩn đoán foreign table bằng admin, từ terminal A mở phiên riêng:

```bash
docker compose -p oldshop-sites --env-file deploy/sites/.env -f deploy/sites/compose.site-a.yml exec pg-a psql -U site_admin -d oldshop_1
```

Trong phiên admin A mới được chạy:

```sql
SELECT site_id FROM site_b.site_identity;
SELECT product_id, title, site_id FROM site_b.product ORDER BY product_id DESC LIMIT 10;
\q
```

### 7.7. Kiểm chứng B ghi → A thấy bản ghi mới

**Windows B, PowerShell:**

```powershell
psql -h 127.0.0.1 -p 57432 -U site_writer -d oldshop_2 -W
```

Nhập SITE_B_WRITER_PASSWORD của B. Trong psql B:

```sql
SELECT current_database(), current_user;
SELECT site_id FROM site_identity;
BEGIN;
INSERT INTO product(seller_id, category_id, title, price, quantity)
VALUES (202, 1, 'Kiem chung B Windows qua Tailscale', 120000, 1)
RETURNING product_id, seller_id, title, site_id;
COMMIT;
```

Ghi lại **ID thực tế** được RETURNING trả về; không mặc định luôn là58/60 vì sequence đã tăng sau các lần thử. Nếu không chạy BEGIN và psql dùng autocommit mặc định thì INSERT tự commit; COMMIT sau đó có warning “no transaction in progress” không có nghĩa INSERT thất bại.

**Linux A, psql global_reader:** nếu đang giữ giao dịch đọc cũ, kết thúc nó trước. Ví dụ sản phẩm B vừa trả ID60:

```sql
ROLLBACK;
\set b_product_id 60
SELECT product_id, seller_id, title, site_id
FROM v_product WHERE product_id = :b_product_id;
```

Thay60 bằng ID thực nhận trên B. Warning “no transaction in progress” của ROLLBACK chỉ có nghĩa không có transaction đang mở; không xóa dữ liệu đã commit. Nếu đang có giao dịch ghi chủ đích thì không rollback tùy tiện; ví dụ này dành cho reader.

Mong đợi cùng ID, seller202, đúng title và site B. Nếu chỉ thấy fixture ID2/4/6/8/10 và không thấy ID mới, kiểm lại server_b, project/env, đúng database B và COMMIT; không kết luận ngay là lỗi đồng bộ. View đọc lại B qua FDW, **không phải replication hoặc lịch ETL A–B**. Product mới có thể chưa duyệt nên chưa xuất hiện ở API public, trong khi v_product vẫn tái tạo đủ dòng.

Bộ bằng chứng nên lưu: hostname/IP Tailscale hai máy; srvoptions A trỏ IP Windows; kết quả INSERT/COMMIT trên B; SELECT cùng ID trên A. Không chụp user mapping/password hoặc `.env`. Lượt này chứng minh truy vấn liên site của danh mục, chưa chứng minh checkout đa site/HA hoặc chịu mất host.

### 7.8. API tùy chọn và giới hạn bộ kiểm thử tự động

Khi FDW đã đọc đúng B, nếu muốn mở gateway trên A:

```bash
python3 deploy/scripts/sites.py catalogue --site A --project oldshop-sites --env deploy/sites/.env
```

Cổng dùng CATALOGUE_PORT trong file A, mặc định56480; không nhầm với gateway cổng57480 có thể đang chạy trên Windows. Nếu thiếu backend image, xem mục5.

**Không chạy `verify`/`verify-api` mặc định để nghiệm thu hai host đang dùng.** Hiện các runner điều khiển cả A/B trên cùng Docker host và đối chiếu fixture chuẩn; chúng không điều khiển B Windows từ A và có thể dừng B local cũ. Sau khi thêm product thử, fixture cũng đã khác expected. Kiểm thủ công đúng hai máy và lưu evidence riêng. Chỉ thử mất mạng/khôi phục trong môi trường demo khi không có thao tác khác đang sử dụng.

### 7.9. Phương án LAN/VPN publish trực tiếp, không dùng Serve

Chỉ chọn phương án này nếu chủ động publish PostgreSQL B trực tiếp ra IP LAN/VPN. Trong file B đặt SITE_B_BIND_IP bằng IP host B, SITE_B_PORT bằng cổng công bố, SITE_B_READER_SOURCE_CIDR bằng IP nguồn A thực tế mà PostgreSQL B nhìn thấy; firewall chỉ cho A tới cổng đó. Áp publish/HBA trên Windows B:

```powershell
python deploy/scripts/sites.py up --site B --project oldshop-sites --env deploy/sites/.env
python deploy/scripts/sites.py access --site B --project oldshop-sites --env deploy/sites/.env
```

Trên A đặt SITE_B_FDW_HOST/PORT bằng IP/cổng trực tiếp của B và chạy lại fdw như7.5. Không đồng thời để Serve và Docker tranh cùng IP/cổng. Nếu muốn chuyển từ Serve sang publish trực tiếp, tắt riêng forward57432 trên B sau khi đã sắp xếp thời điểm chuyển:

```powershell
tailscale serve --bg --tcp=57432 off
```

Không dùng `tailscale serve reset` vì có thể xóa dịch vụ khác. Không chuyển phương án nếu Serve đang chạy đúng và không có nhu cầu đổi.

## 8. Dừng và khởi động lại

Với mô phỏng hai site cùng host:

```bash
python3 deploy/scripts/sites.py stop
python3 deploy/scripts/sites.py up
python3 deploy/scripts/sites.py catalogue
```

Với **A Linux/B Windows qua Tailscale**, thao tác riêng đúng máy và giữ project/env đang dùng. Trên A:

```bash
python3 deploy/scripts/sites.py stop --site A --project oldshop-sites --env deploy/sites/.env
python3 deploy/scripts/sites.py up --site A --project oldshop-sites --env deploy/sites/.env
```

Trên B Windows:

```powershell
python deploy/scripts/sites.py stop --site B --project oldshop-sites --env deploy/sites/.env
python deploy/scripts/sites.py up --site B --project oldshop-sites --env deploy/sites/.env
tailscale status
tailscale serve status
```

Hai lệnh stop/up là thao tác dừng rồi bật lại khi cần, không chạy trong lúc kiểm chứng ghi dữ liệu. Serve có `--bg` duy trì cấu hình nền; sau reboot vẫn kiểm Docker/Tailscale/Serve và query lại A. Nếu thiếu forward, bật lại bằng mục 7.3; không prepare/bootstrap lại database chỉ để restart. `stop --site A` chọn cả profile catalogue để dừng gateway nếu có; `up --site A` không tự bật profile này. Nếu dùng gateway trên A, chạy lại lệnh đầy đủ ở mục 7.8 sau khi FDW đọc được B.

`down` gỡ container/network của project, giữ volume. `up` tạo lại container dựa trên volume và credential cũ. File `.env` phải được giữ lại.

Schema hiện tại phục vụ triển khai phân mảnh danh mục. Không chuyển connection string của ứng dụng thương mại cũ sang các database này để vận hành tiền/hàng thật trước khi hoàn thành các bước M2 và đối soát/migration đã nêu trong kế hoạch.

## 9. Chẩn đoán lỗi A Linux / B Windows theo từng tầng

Làm theo thứ tự **DB B local → TCP Serve/VPN → password b_reader B → FDW A → SELECT qua view**. Mỗi lần sửa, kiểm đúng tầng rồi mới làm tiếp; không sửa quyền/password để chữa lỗi connection refused.

| Hiện tượng | Ý nghĩa | Lệnh/bước xử lý |
|---|---|---|
| `rg: command not found` | Thiếu công cụ tìm chuỗi, không phải lỗi PostgreSQL. | Dùng lệnh grep ở mục 7.5 trên Linux; không cần cài rg. |
| srvoptions vẫn có `172.29.82.12:5432` | A còn trỏ B Docker local. | Sửa đúng env của A, dùng IP Windows/cổng57432, chạy lệnh fdw7.5 rồi kiểm lại srvoptions. |
| `.env` đã sửa nhưng srvoptions không đổi | Chưa áp FDW hoặc chạy nhầm project/file. | Chạy fdw với đầy đủ --site/--project/--env, đọc output; không chỉ đăng nhập lại global_reader. |
| `Connection refused` tới B:57432 | TCP bị từ chối trước khi xác thực. | B chạy Test-NetConnection local, docker ps, tailscale serve status; `No serve config` thì bật7.3. |
| Timeout/không tới được IP Tailscale | Chưa đủ đường mạng từ tiến trình PG A tới B. | Kiểm IP thật, Tailscale status/policy, cổng và đường đi container; dùng lệnh kiểm container phía dưới. |
| `password authentication failed for user "b_reader"` | Đã tới PostgreSQL đích nhưng password không được chấp nhận. | Kiểm đúng B/database, thử reader local B; cần thì admin B `\password b_reader`, cập nhật env B/A rồi fdw7.5. Không dùng password global_reader của A. |
| `no pg_hba.conf entry` hoặc HBA reject | Nguồn TCP tới B chưa được phép. | Xem nguồn thực trong lỗi; với Serve thường là gateway. Dùng access đúng site B/env để áp lại rule của dự án nếu phù hợp, không mở trust toàn mạng. |
| `permission denied for schema site_b` | Global_reader không được đọc foreign table trực tiếp. | Reader dùng v_product/v_site_health; admin session riêng7.6 mới đọc site_b.product. |
| `permission denied for table product` | Global_reader không được đọc bảng local trực tiếp. | Trên A dùng v_product; trên B dùng b_reader/site_writer khi cần bảng local. |
| `must be owner of foreign server server_b` | Đang ALTER SERVER bằng tài khoản reader. | Thoát psql, dùng script fdw chạy site_admin, không cấp ownership cho global_reader. |
| `syntax error` ở `SET host 100...` | Giá trị host SQL thiếu dấu nháy. | Nếu thao tác SQL admin phải là `SET host 'IP_THAT'`; ưu tiên script fdw để cập nhật cả mapping. |
| `WARNING: there is no transaction in progress` | COMMIT/ROLLBACK khi không có transaction mở. | Không phải lỗi kết nối; INSERT autocommit đã xong nếu trước đó không BEGIN và autocommit bật. |
| Psql hiện dấu nhắc tiếp dòng do câu gõ dở | Buffer SQL chưa kết thúc; có thể ghép nhầm câu sau. | Trong psql chạy `\r` để xóa buffer rồi nhập lại câu SQL đầy đủ. |
| `v_site_health` có A/B nhưng không thấy ID mới | Site label không xác nhận đúng máy B, hoặc ID/transaction/database chưa đúng. | So IP/cổng/dbname srvoptions; ID thực từ RETURNING; COMMIT B; kết thúc snapshot đọc cũ ở A rồi SELECT lại. |
| CLI admin password failed hoặc không tìm thấy service | Có thể chọn nhầm env/project/volume hoặc password admin đã thay. | Đối chiếu `docker ps`, tên project và file đã dùng tạo A/B; không chạy prepare/xóa volume để sửa. |

Nếu host A đăng nhập B được nhưng FDW không được, từ **terminal Linux A** kiểm TCP/password bằng chính network container A:

```bash
docker compose -p oldshop-sites --env-file deploy/sites/.env -f deploy/sites/compose.site-a.yml exec pg-a psql -h 100.88.10.25 -p 57432 -U b_reader -d oldshop_2 -W
```

Thay IP bằng IP Windows thật. Đây là **role b_reader kết nối remote B**, khác với `exec pg-a psql -U site_admin ...` mở admin local A. Vào được thì chạy `SELECT current_database(), current_user; SELECT site_id FROM site_identity;`, rồi `\q` và chạy lại fdw. Không vào được thì giữ lỗi nguyên văn để kiểm VPN/proxy/auth; host A thành công chưa chứng minh container A có cùng đường mạng.

Khi cần hỗ trợ, gửi hostname máy đang chạy lệnh, project/env được chọn, srvoptions, trạng thái cổng/Serve và lỗi; không gửi password, toàn bộ `.env`, user mapping options hoặc dữ liệu nhạy cảm.
