# OldShop — Kết nối hai site bằng Tailscale trên Windows và Linux

Ngày cập nhật: 04/11/2026. Dùng cùng [hướng dẫn CSDL phân tán](HUONG_DAN_CSDL_PHAN_TAN.md).

Tài liệu này hướng dẫn thao tác, chưa phải bằng chứng đã chạy trên hai máy thật. Hiện dự án mới kiểm chứng hai IP Docker trên một host; khi có máy B, cần thu lại kết quả kết nối qua Tailscale.

## 1. Mô hình và thông tin cần chuẩn bị

Máy A chạy PostgreSQL `oldshop_1`; máy B chạy PostgreSQL `oldshop_2`. Hai máy có thể ở hai mạng Internet khác nhau và dùng bất kỳ tổ hợp Windows/Linux nào.

Hướng dẫn chính dùng Tailscale cài **trên hệ điều hành host**, rồi dùng TCP Serve trên B chuyển kết nối tới cổng PostgreSQL đã publish ở localhost. Cách này giữ nguyên `SITE_B_BIND_IP=127.0.0.1` của dự án và dùng được với Docker Desktop. Không cần cài extension Tailscale cho Docker Desktop.

```text
PostgreSQL A trong Docker
       ↓ TCP tới IP Tailscale B:57432
Tailscale host A ← mạng Tailscale → Tailscale host B
                                         ↓ TCP Serve
                                  127.0.0.1:57432 trên B
                                         ↓ Docker publish
                                  PostgreSQL B:5432
```

| Giá trị | Ví dụ trong tài liệu | Thay bằng |
|---|---|---|
| IP Tailscale A | `100.88.10.20` | Kết quả `tailscale ip -4` trên A |
| IP Tailscale B | `100.88.10.25` | Kết quả `tailscale ip -4` trên B |
| Cổng PostgreSQL B trên host/VPN | `57432` | `SITE_B_PORT` và cổng TCP Serve |
| Cổng PostgreSQL bên trong container | `5432` | Giữ theo Compose |
| Database A/B | `oldshop_1` / `oldshop_2` | Giữ theo dự án |
| Project Compose cho hướng dẫn này | `oldshop-vpn` | Dùng nhất quán trên từng host |
| File cấu hình riêng | `deploy/sites/.env.vpn` | Không commit/chia sẻ toàn bộ file |

Mọi IP `100.88.10.*` dưới đây là **ví dụ**, không phải địa chỉ đã được cấp cho bạn. IP Docker `172.29.*` chỉ dùng bên trong host; không lấy IP Docker của B để kết nối từ một host A khác.

Chuẩn bị cả hai máy: cùng phiên bản repository, Docker Engine/Desktop đang chạy, Python 3 và Internet. Nếu muốn dùng `psql` trực tiếp trên host, cài PostgreSQL client; nếu không có client, dùng lệnh chạy `psql` trong container ở mục 8.

Hiện chỉ có một máy thì có thể cài Tailscale và làm quen thao tác đăng nhập. Để kiểm chứng hai máy qua VPN cần thiết bị/VM thứ hai có PostgreSQL B và tham gia tailnet; cài một client trên host không tự tạo thêm một site từ xa.

## 2. Cài và bật Tailscale trên Windows

Thực hiện trên **mỗi máy Windows**, dù máy đó giữ vai A hay B:

1. Tải bộ cài từ [trang Windows chính thức](https://tailscale.com/download/windows), cài đặt và mở Tailscale.
2. Chọn đăng nhập bằng trình duyệt, đưa thiết bị vào tailnet của nhóm.
3. Mở PowerShell mới, kiểm tra:

```powershell
tailscale version
tailscale status
tailscale ip -4
```

Nếu không nhận lệnh `tailscale`, gọi trực tiếp:

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' status
& 'C:\Program Files\Tailscale\tailscale.exe' ip -4
```

Có thể thêm thư mục chứa executable vào PATH hoặc dùng đường dẫn đầy đủ cho các lệnh tiếp theo. Khi cần kết nối lại, mở PowerShell **Run as Administrator**:

```powershell
tailscale up
```

Docker Desktop phải dùng Linux containers và đang hoạt động. Trong thư mục repository, kiểm tra `docker compose version` và `python --version`; nếu máy dùng Python launcher, thay `python` bằng `py -3` trong các lệnh bên dưới.

Nguồn cài đặt: [Tailscale trên Windows](https://tailscale.com/docs/install/windows).

## 3. Cài và bật Tailscale trên Linux

Thực hiện trên **mỗi máy Linux**, dù vai A hay B. Với Ubuntu/Debian và các distro phổ biến được Tailscale hỗ trợ:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/tailscale-install.sh
```

Đọc script nếu cần, rồi cài và bật dịch vụ:

```bash
sh /tmp/tailscale-install.sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Mở URL đăng nhập được hiển thị trong terminal. Sau khi xác thực:

```bash
tailscale version
tailscale status
tailscale ip -4
```

Nếu thiếu `curl` trên Ubuntu/Debian, cài bằng `sudo apt install curl`. Với hệ không dùng systemd hoặc muốn cài bằng package manager thủ công, dùng [hướng dẫn Linux chính thức](https://tailscale.com/docs/install/linux) tương ứng distro.

Trong repository, kiểm tra `docker compose version` và `python3 --version`. Tài khoản chạy script phải truy cập được Docker; không cần chạy cả bộ script bằng `sudo` chỉ để bật Tailscale.

## 4. Cho hai máy vào cùng mạng và kiểm tra VPN

Hai thiết bị phải nằm trong cùng tailnet và được policy cho phép giao tiếp. Một người có thể đăng nhập tài khoản của mình trên hai máy mình sở hữu. Với hai thành viên, chủ tailnet mời người còn lại tham gia và mỗi người dùng tài khoản riêng; không gửi mật khẩu tài khoản cho nhau. Nếu tailnet bật duyệt thiết bị, quản trị viên cần duyệt máy mới.

Trên A kiểm tra tới IP Tailscale thật của B:

```text
tailscale status
tailscale ping 100.88.10.25
```

`direct` hoặc qua relay đều có thể dùng; relay có thể tăng độ trễ. Lệnh này kiểm tra đường Tailscale, **chưa chứng minh PostgreSQL/cổng TCP đã truy cập được**. Xem [CLI Tailscale](https://tailscale.com/docs/reference/tailscale-cli).

Trên B không bật chế độ chặn toàn bộ kết nối vào từ tailnet. Nếu đã bật, thay đổi có chủ đích bằng PowerShell Administrator hoặc bash tương ứng:

```powershell
tailscale set --shields-up=false
```

```bash
sudo tailscale set --shields-up=false
```

Trong trang quản trị Tailscale, kiểm tra policy cho phép A tới B trên TCP `57432`. Ví dụ phần tử thêm vào mảng `grants` của policy hiện hữu:

```json
{
  "src": ["100.88.10.20/32"],
  "dst": ["100.88.10.25/32"],
  "ip": ["tcp:57432"]
}
```

Thay IP thật, kiểm thử bằng policy editor rồi lưu. Không thay toàn bộ policy tổ chức bằng đoạn ví dụ. Quyền được cộng từ mọi grant/ACL phù hợp: thêm rule hẹp không tự thu hẹp một rule rộng đang có. Tham khảo [cú pháp grants](https://tailscale.com/docs/reference/syntax/grants).

Thông thường không cần port-forward PostgreSQL trên router hoặc bật exit node/subnet router cho mô hình host A gọi host B này. Kết nối Tailscale và cổng dịch vụ PostgreSQL là hai lớp kiểm tra khác nhau. Xem [cổng mạng Tailscale](https://tailscale.com/docs/reference/faq/firewall-ports).

## 5. Tạo cấu hình riêng trên cả A và B

Các lệnh từ đây chạy trong repository. Dùng project `oldshop-vpn`, cổng `57431`/`57432`/`57480` và subnet riêng để có thể cùng tồn tại với môi trường mô phỏng `oldshop-sites` đang dùng cổng `56431`/`56432`/`56480`. Hai host khác nhau có thể dùng cùng subnet Docker nội bộ này vì ta không định tuyến subnet đó qua VPN.

**Windows — cả A và B:**

```powershell
python deploy/scripts/sites.py prepare --env deploy/sites/.env.vpn
notepad deploy/sites/.env.vpn
```

**Linux — cả A và B:**

```bash
python3 deploy/scripts/sites.py prepare --env deploy/sites/.env.vpn
nano deploy/sites/.env.vpn
```

`prepare` chỉ chạy lần đầu. File đã có thì mở để sửa, không xóa/tạo lại credential khi volume đã được khởi tạo.

Trên **cả hai máy**, sửa các dòng sau; giữ các password ngẫu nhiên đã sinh:

```dotenv
SITE_A_DB_NAME=oldshop_1
SITE_B_DB_NAME=oldshop_2
SITES_SUBNET=172.29.84.0/24
SITE_A_VIRTUAL_IP=172.29.84.11
SITE_B_VIRTUAL_IP=172.29.84.12
CATALOGUE_VIRTUAL_IP=172.29.84.20
SITE_A_BIND_IP=127.0.0.1
SITE_B_BIND_IP=127.0.0.1
SITE_A_PORT=57431
SITE_B_PORT=57432
CATALOGUE_PORT=57480
SITE_B_FDW_HOST=100.88.10.25
SITE_B_FDW_PORT=57432
SITE_B_READER_SOURCE_CIDR=100.88.10.20/32
```

Thay IP Tailscale A/B bằng giá trị thật. Chọn subnet Docker khác nếu `172.29.84.0/24` đang được dùng. `SITE_B_FDW_PORT` là **cổng VPN/host 57432**, không phải cổng container 5432.

Password dùng cho kết nối A → B là giá trị `SITE_B_READER_PASSWORD` **trong file của B**. Chuyển riêng giá trị này qua kênh riêng tới người A, rồi điền đúng vào `SITE_B_READER_PASSWORD` trong file của A. Không cần đồng nhất password quản trị/writer của hai máy, không gửi cả file `.env.vpn`.

`SITE_A_GLOBAL_PASSWORD` trong file A dùng khi người dùng kết nối `global_reader` vào `oldshop_1`. Nó khác password `b_reader` dùng để A đọc B. Sửa biến môi trường sau bootstrap không tự đổi password role đã lưu trong database.

## 6. Máy B — bật PostgreSQL và chia sẻ cổng trong tailnet

### 6.1. Khởi tạo site B

**B dùng Windows:**

```powershell
python deploy/scripts/sites.py up --site B --project oldshop-vpn --env deploy/sites/.env.vpn
python deploy/scripts/sites.py bootstrap --site B --project oldshop-vpn --env deploy/sites/.env.vpn
```

**B dùng Linux:**

```bash
python3 deploy/scripts/sites.py up --site B --project oldshop-vpn --env deploy/sites/.env.vpn
python3 deploy/scripts/sites.py bootstrap --site B --project oldshop-vpn --env deploy/sites/.env.vpn
```

Chỉ B cần `oldshop_2` của hướng dẫn này. Nếu database đã cài đúng source/site, bootstrap kiểm tra marker thay vì nạp chồng fixture. Nếu script báo khác source, xử lý khác biệt trước, không xóa volume để vượt lỗi.

### 6.2. Bật TCP Serve trên host B

**Windows — PowerShell Administrator trên B:**

```powershell
tailscale serve --bg --tcp=57432 tcp://127.0.0.1:57432
tailscale serve status
```

**Linux — terminal trên B:**

```bash
sudo tailscale serve --bg --tcp=57432 tcp://127.0.0.1:57432
tailscale serve status
```

Mong đợi: TCP `57432` trong tailnet chuyển tới `127.0.0.1:57432` của host B. Nếu CLI yêu cầu quản trị viên cho phép Serve, mở URL nó cung cấp và làm theo policy của tailnet; không bật Funnel/public exposure. Dùng raw TCP, không dùng HTTP proxy hoặc TLS termination cho PostgreSQL ở cấu hình này. Cú pháp tham khảo [TCP Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

**Ảnh hưởng lên HBA:** Serve là proxy; PostgreSQL B thường thấy IP localhost/gateway Docker, không phải IP Tailscale A. Script `access` hiện cho phép gateway Docker đăng nhập bằng password. Vì vậy `SITE_B_READER_SOURCE_CIDR=IP_A/32` không phải rule quyết định khi chạy qua proxy; Tailscale grant kiểm soát máy A, còn PostgreSQL kiểm tra role/password. Không bật PROXY protocol cho PostgreSQL mặc định.

Phần này khác phương án publish trực tiếp ra IP VPN ở mục 11; chỉ dùng một cách cho cùng cổng.

## 7. Máy A — kiểm tra TCP, đăng nhập và khởi tạo FDW

### 7.1. Kiểm tra cổng B từ host A

**A dùng Windows:**

```powershell
Test-NetConnection -ComputerName 100.88.10.25 -Port 57432
```

**A dùng Linux, có netcat:**

```bash
nc -zv -w 5 100.88.10.25 57432
```

Nếu A có `psql`, dùng lệnh chung cho cả hai OS:

```text
psql -h 100.88.10.25 -p 57432 -U b_reader -d oldshop_2 -W
```

Nhập `SITE_B_READER_PASSWORD` của **B**, rồi kiểm tra:

```sql
SELECT current_database(), current_user, inet_client_addr(), inet_server_addr();
SELECT site_id FROM site_identity;
SELECT product_id, title FROM product ORDER BY product_id;
```

Kết quả phải là database `oldshop_2`, role `b_reader`, site `B`. Với Serve/NAT, địa chỉ trả về có thể là gateway/container; đối chiếu thêm hostname hai máy, IP Tailscale và `tailscale serve status` để chứng minh đường đi.

### 7.2. Khởi tạo A và FDW

**A dùng Windows:**

```powershell
python deploy/scripts/sites.py up --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python deploy/scripts/sites.py bootstrap --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python deploy/scripts/sites.py fdw --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python deploy/scripts/sites.py catalogue --site A --project oldshop-vpn --env deploy/sites/.env.vpn
```

**A dùng Linux:**

```bash
python3 deploy/scripts/sites.py up --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python3 deploy/scripts/sites.py bootstrap --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python3 deploy/scripts/sites.py fdw --site A --project oldshop-vpn --env deploy/sites/.env.vpn
python3 deploy/scripts/sites.py catalogue --site A --project oldshop-vpn --env deploy/sites/.env.vpn
```

Nếu cổng API `57480` đang được môi trường local dùng, trước khi chạy gateway đặt `CATALOGUE_PORT=57481` trong `.env.vpn` ở A; truy cập `http://127.0.0.1:57481/docs`. Tương tự, chọn cổng A khác nếu `57431` đã được dùng. Luôn phân biệt project/volume và file env local với VPN.

Script `fdw` chạy kết nối **từ PostgreSQL A trong container** tới IP Tailscale B, đồng thời xác nhận site B. Host A đăng nhập thành công nhưng script này lỗi có thể do đường đi Docker/VM/WSL chưa dùng được VPN host; xem mục 10.

## 8. Kiểm tra không cần cài psql trên host

Chạy trên A, dùng cùng cú pháp cho PowerShell hoặc bash:

```text
docker compose -p oldshop-vpn --env-file deploy/sites/.env.vpn -f deploy/sites/compose.site-a.yml exec pg-a psql -U site_admin -d oldshop_1
```

Trong `psql` tại A:

```sql
SELECT site_id FROM site_b.site_identity;
SELECT product_id, title, site_id FROM v_product ORDER BY product_id;
SELECT category_id, name FROM v_category ORDER BY category_id;
```

Mong đợi fixture chuẩn: 10 product toàn cục, gồm A và B; category chỉ có 3 dòng. View tái tạo giữ cả product xóa mềm/chưa duyệt, còn gateway danh mục chỉ hiển thị những product được phép công bố.

Nếu cần thử TCP trực tiếp **từ container A** trước khi cấu hình FDW:

```text
docker compose -p oldshop-vpn --env-file deploy/sites/.env.vpn -f deploy/sites/compose.site-a.yml exec pg-a psql -h 100.88.10.25 -p 57432 -U b_reader -d oldshop_2 -W
```

Host A thành công nhưng lệnh này thất bại thì chưa đạt điều kiện cấu hình FDW.

## 9. Kiểm chứng cập nhật và mất VPN

1. Trên B, mở `psql` trong container B bằng lệnh tương tự mục 8, đổi file Compose sang `compose.site-b.yml`, service thành `pg-b`, database thành `oldshop_2`.
2. Ghi lại giá trị cũ của `title` tại product ID 2, thay đổi tạm rồi commit:

```sql
BEGIN;
UPDATE product SET title = 'Kiem tra cap nhat qua Tailscale' WHERE product_id = 2;
COMMIT;
```

3. Trên A, kết thúc giao dịch đọc cũ nếu có, rồi đọc lại:

```sql
SELECT product_id, title, site_id FROM v_product WHERE product_id = 2;
```

4. Sau kiểm tra, B khôi phục giá trị title đã ghi lại. Không reset/nạp lại toàn database để dọn một thay đổi thử.
5. Trên B, tạm ngắt Tailscale: Windows chạy `tailscale down`; Linux chạy `sudo tailscale down`. Query local A vẫn chạy; query cần B phải lỗi hoặc timeout. Gateway trả `503` khi thiếu site.
6. B kết nối lại bằng `tailscale up` / `sudo tailscale up`; kiểm `tailscale serve status` và bật lại TCP Serve nếu chưa có. Kết thúc/rollback giao dịch lỗi ở A, rồi truy vấn lại ID 2 để xác nhận phục hồi.

**Không chạy `sites.py verify` hoặc `verify-api` để nghiệm thu hai host theo hướng dẫn này.** Các lệnh đó hiện điều khiển cả A/B trên cùng Docker host. Với VPN, kiểm thủ công từng bước và lưu riêng hostname, IP, câu SQL, kết quả trước/sau và lỗi/phục hồi.

## 10. Xử lý lỗi theo từng tầng

| Hiện tượng | Kiểm tra/cách xử lý |
|---|---|
| `tailscale` không được nhận diện trên Windows | Mở PowerShell mới hoặc gọi executable bằng đường dẫn ở mục 2 |
| Linux báo dịch vụ chưa chạy | `sudo systemctl status tailscaled`; khởi động lại dịch vụ rồi đăng nhập |
| `tailscale status` không thấy máy kia | Kiểm tailnet, lời mời thành viên, duyệt thiết bị và trạng thái đăng nhập |
| `tailscale ping` được nhưng TCP `57432` không được | Kiểm grant/ACL, shields-up, TCP Serve và PostgreSQL B đang chạy |
| Serve báo không kết nối được backend | Trên B thử `psql -h 127.0.0.1 -p 57432 ...`; kiểm port publish và site B |
| Password authentication failed | Dùng đúng password role `b_reader` đã tạo ở B; chỉ sửa `.env` không rotate password DB |
| HBA từ chối | Đọc IP nguồn trong lỗi; kiểm `access` đúng project/env/site. Serve có thể làm nguồn thành gateway |
| Host A đọc được nhưng container A không đọc được | Trên Windows kiểm Docker Desktop/WSL2/VM routing và Tailscale trên đúng host; chạy phép thử container ở mục 8. Trên Linux kiểm forward/filter Docker/Tailscale. Sau thay đổi cấu hình mạng, khởi động lại riêng môi trường liên quan và thử lại |
| Không bind được port | Cổng đang dùng hoặc bind IP không có trên host; chọn cổng khác hoặc dùng phương án Serve với bind localhost |
| Kết quả vẫn lấy B local cũ | Kiểm đúng project `oldshop-vpn`, file `.env.vpn`, foreign server host/port và `site_b.site_identity` |
| A không thấy B vừa sửa | B chưa commit, nhầm database hoặc A đang giữ snapshot cũ; kết thúc giao dịch đọc và thử lại |

Kết nối từ container qua VPN host phụ thuộc môi trường Docker/OS; tài liệu không coi host ping được là bảo đảm container cũng dùng được VPN. Nếu VM/WSL hiện tại không định tuyến được sau khi cấu hình đúng, cần sửa lớp đó hoặc thiết kế Tailscale sidecar trong mạng container; chưa có sidecar trong Compose hiện hữu.

## 11. Phương án khác: publish PostgreSQL trực tiếp trên IP Tailscale B

Chỉ chọn mục này nếu muốn bỏ TCP Serve. Trên B tắt riêng TCP Serve ở cổng này, đặt `SITE_B_BIND_IP` bằng IP Tailscale thật của B trong `.env.vpn`, rồi chạy lại `up --site B` và `access --site B` với đúng project/env. `SITE_B_FDW_HOST`/port ở A vẫn là IP B và cổng `57432`.

**B dùng Windows — PowerShell Administrator**, nếu firewall đang chặn cổng này:

```powershell
New-NetFirewallRule -DisplayName 'OldShop PostgreSQL from Tailscale A' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress 100.88.10.25 -LocalPort 57432 -RemoteAddress 100.88.10.20 -Profile Any
```

**B dùng Linux/UFW**, với dịch vụ chịu điều khiển bởi UFW:

```bash
sudo ufw allow in on tailscale0 from 100.88.10.20 to 100.88.10.25 port 57432 proto tcp
```

Docker trên Linux có quy tắc publish/forward riêng và có thể đi vòng UFW; không xem một rule UFW là bằng chứng đã giới hạn cổng Docker. Kiểm tra chuỗi firewall/backend Docker đang dùng và truy cập thực tế; tham khảo [Docker và firewall](https://docs.docker.com/engine/network/packet-filtering-firewalls/). Không đổi sang bind mọi interface chỉ để vượt lỗi. Nếu bind IP VPN không phù hợp Docker Desktop đang dùng, quay lại phương án Serve ở mục 6.

Với đường trực tiếp, PostgreSQL có thể nhìn thấy IP Tailscale A hoặc IP sau NAT; đặt `SITE_B_READER_SOURCE_CIDR` theo nguồn thực tế và chạy lại `access`. Không đồng thời để Serve và Docker tranh cùng IP/cổng VPN.

## 12. Bật lại, ngắt kết nối và checklist

Sau khi máy B khởi động lại: xác nhận Docker và Tailscale đang chạy, bật site B với đúng project/env, kiểm `tailscale serve status`. Trên A bật site A, kiểm FDW và mở gateway khi cần. `--bg` lưu cấu hình Serve ở chế độ nền; vẫn phải kiểm tra lại dịch vụ sau reboot theo [hướng dẫn Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

Tắt riêng proxy PostgreSQL trên B khi không dùng:

```powershell
tailscale serve --bg --tcp=57432 off
```

```bash
sudo tailscale serve --bg --tcp=57432 off
```

Không dùng `serve reset` nếu máy đang chia sẻ dịch vụ khác. `tailscale down` ngắt Tailscale nhưng không xóa database/volume; lệnh `stop` của dự án dừng container nhưng cũng giữ volume.

- [ ] A/B đã cài Tailscale và có IP/hostname phân biệt.
- [ ] A → B TCP `57432` được policy cho phép.
- [ ] B chạy `oldshop_2`, role `b_reader` chỉ đọc và TCP Serve/publish đúng.
- [ ] Cả host A và container PostgreSQL A truy cập B được.
- [ ] FDW tại `oldshop_1` trỏ tới IP Tailscale B, không trỏ tới IP Docker B local.
- [ ] View có dữ liệu của cả hai site, bản category không đếm lặp.
- [ ] Thử commit tại B, đọc giao dịch mới tại A, mất VPN và phục hồi.
- [ ] Lưu bằng chứng hai host; password và file `.env.vpn` không đưa vào báo cáo/Git.

Nguồn chính thức được liên kết cạnh các bước tương ứng; hướng dẫn này không cài Tailscale hoặc thay đổi cấu hình VPN/firewall của máy người dùng khi chỉ tạo file tài liệu.
