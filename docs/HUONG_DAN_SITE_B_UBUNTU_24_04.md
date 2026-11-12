# Dựng site B trên Ubuntu 24.04 từ máy trống

Ngày hướng dẫn: 12/11/2026. Mô hình: máy đang có dự án làm A; Ubuntu 24.04 trong VM làm B. Chỉ dựng catalogue PostgreSQL hai site, không chuyển checkout sang VM. B chưa cần MongoDB, MinIO, frontend, Python backend hoặc psycopg2.

Sử dụng project mới **oldshop-vm-demo**, file env mới **deploy/sites/.env.vm-demo**, port A **56631**, B **56632**, API **56680**. Không dùng/sửa `.env` VPN hiện hữu, không reset database đang dùng. Các lệnh A giả định terminal Linux/Bash của workspace hiện tại; không chạy cả bộ lệnh A trên B.

## 1. Chuẩn bị mạng trước

Ví dụ xuyên suốt:

| Địa chỉ | Vai trò |
| --- | --- |
| `192.168.56.1` | Máy A, IP host-only của host |
| `192.168.56.101` | VM Ubuntu B, IP host-only |
| `10.0.2.xx` | IP NAT có thể đang dùng trên B để ra Internet |
| `172.29.87.11`, `.20` | Container PG A và gateway trên A |
| `172.29.88.12` | Container PG B trong VM |

Hai IP `192.168.56.*` là ví dụ. Thay bằng IP thực tế của bạn ở mọi bước. Không dùng nguyên `10.0.2.xx` vì đây không phải địa chỉ cụ thể; không mặc định host A truy cập được IP NAT của VM.

Phương án Host-only bên dưới giả định A chính là máy host chạy VM. Nếu VM được chạy trên một máy khác với A, dùng Bridged/LAN hoặc VPN để A tới được VM; Host-only chỉ nối VM với host của chính nó. Khi đó thay địa chỉ A/B và SOURCE_CIDR bằng thông số mạng thực tế.

Nếu dùng VirtualBox: tắt VM, giữ Adapter 1 = NAT để cài gói Internet; thêm Adapter 2 = Host-only Adapter cùng network với host. Trong Network Manager kiểm IP host và DHCP. Bật VM, chạy `ip -br address` để xác định IP adapter thứ hai. Nếu dùng VMware, dùng Host-only hoặc Bridged tương ứng. Chế độ Bridged cũng phù hợp: khi đó thay IP ví dụ bằng IP LAN thực tế của A/B.

Nếu Ubuntu Desktop chưa nhận IP host-only, trong Settings → Network chọn đúng adapter thứ hai → IPv4: bật DHCP nếu host-only đã có DHCP; hoặc đặt địa chỉ tĩnh trong đúng subnet. Không đặt gateway mặc định trên adapter host-only; giữ đường ra Internet qua NAT. Ubuntu Server có thể cần cấu hình adapter tương ứng trong Netplan; không ghi đè cấu hình NIC NAT đang hoạt động chỉ để đổi IP demo.

Ví dụ Ubuntu Server: dùng console VM, xác định NIC thứ hai bằng `ip -br link`. Nếu đúng NIC đó là `enp0s8`, tạo `sudo nano /etc/netplan/60-oldshop-demo.yaml` với nội dung sau; thay tên NIC/IP cho đúng máy:

```yaml
network:
  version: 2
  ethernets:
    enp0s8:
      dhcp4: false
      dhcp6: false
      addresses:
        - 192.168.56.101/24
```

Đặt quyền bằng `sudo chmod 600 /etc/netplan/60-oldshop-demo.yaml`, rồi chạy `sudo netplan try`, kiểm và xác nhận cấu hình trong console. Chỉ thêm NIC host-only, không thay file cấu hình NIC NAT. Nếu có nhiều adapter/renderer đặc biệt, kiểm cấu hình Netplan hiện tại trước khi áp ví dụ.

Cú pháp `addresses` theo [Netplan static address](https://netplan.readthedocs.io/en/stable/examples/#how-to-configure-a-static-ip-address-on-an-interface).

Host-only cho phép host và VM giao tiếp; NAT thông thường cần forwarding nếu host chủ động kết nối vào guest. Tham khảo [VirtualBox Networking](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/networkingdetails.html). Kiểm trên B:

```bash
ip -br address
ip route
hostname
```

Chưa xác định được IP B có thể truy cập từ A thì chưa dựng FDW. Không cần xóa mạng Docker đang phục vụ ứng dụng. Nếu subnet 172.29.87/88 đã có trên máy tương ứng, chọn subnet Docker trống khác và sửa đồng bộ IP gateway/container trong env.

## 2. Trên B: cài công cụ cơ bản và SSH

Mở terminal ngay trong Ubuntu VM:

```bash
sudo apt update
sudo apt install -y ca-certificates curl python3 openssh-server nano
sudo systemctl enable --now ssh
python3 --version
ip -br address
```

Python 3.12 mặc định Ubuntu 24.04 đủ cho `deploy/scripts/sites.py` vì script dùng thư viện chuẩn. Không cần cài dependencies backend vào B. Nếu UFW đang active và cần SSH từ A, cho phép đúng nguồn A:

```bash
sudo ufw status
# Chỉ chạy nếu cần mở SSH từ A; thay bằng IP A thực tế.
sudo ufw allow from 192.168.56.1 to any port 22 proto tcp
```

Trên A thử `ssh TEN_USER_B@192.168.56.101`, thay TEN_USER_B bằng username Ubuntu B. Đây là kiểm tra mạng và SSH, chưa chứng minh PostgreSQL hoạt động.

## 3. Trên B: cài Docker Engine và Compose plugin

Lệnh dành cho Ubuntu 24.04 mới, chưa cài Docker. Nếu đã có Docker, kiểm `docker version`/`docker compose version` trước thay vì cài chồng. Thiết lập kho gói chính thức:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
```

Đây là phương pháp apt repository của [Docker Engine Ubuntu](https://docs.docker.com/engine/install/ubuntu/), dùng codename `noble` cho Ubuntu 24.04.

Cho tài khoản hiện tại dùng Docker để script Python gọi được Docker:

```bash
sudo usermod -aG docker "$USER"
```

Đăng xuất rồi đăng nhập lại Ubuntu/SSH, sau đó:

```bash
docker version
docker compose version
docker ps
```

Nếu vẫn permission denied, session chưa nhận group mới; không chữa bằng chmod 777 socket. Quyền group Docker tương đương quyền quản trị host; dùng tài khoản demo bạn kiểm soát. Xem [Docker post-install](https://docs.docker.com/engine/install/linux-postinstall/).

## 4. Trên A: chuyển source hiện tại sang B

Mã thay đổi đang nằm trong working tree; chỉ git clone remote có thể thiếu router/migration mới chưa push. B chỉ cần các source SQL và công cụ site. Gói tối thiểu dưới đây không lấy `.env`, backup hoặc dữ liệu runtime:

```bash
cd /home/phat/Documents/Project/Epic-Ecommerce-FastAPI-main
tar -czf /tmp/oldshop-vm-source.tgz \
  database \
  deploy/scripts/sites.py \
  deploy/sites/compose.site-b.yml \
  deploy/sites/env.example
scp /tmp/oldshop-vm-source.tgz TEN_USER_B@192.168.56.101:~/
```

Trên B:

```bash
mkdir -p ~/oldshop-demo
tar -xzf ~/oldshop-vm-source.tgz -C ~/oldshop-demo
cd ~/oldshop-demo
ls database/distributed/fragmentation.json
ls database/distributed/migrations/001_fragment_contract.sql
ls database/04_migrations/008_fragmentation_seller_index.sql
```

Ba file phải tồn tại. Giữ nguyên cấu trúc thư mục; `sites.py` tìm database tương đối từ root dự án.

## 5. Trên B: tạo env và cấu hình PostgreSQL

Chỉ tạo env một lần trên project mới:

```bash
cd ~/oldshop-demo
python3 deploy/scripts/sites.py prepare --env deploy/sites/.env.vm-demo
nano deploy/sites/.env.vm-demo
```

Sửa các dòng sau, giữ toàn bộ password đã sinh tự động:

```ini
SITE_B_DB_NAME=oldshop_2
SITE_B_BIND_IP=192.168.56.101
SITE_B_PORT=56632
SITES_SUBNET=172.29.88.0/24
SITE_A_VIRTUAL_IP=172.29.88.11
SITE_B_VIRTUAL_IP=172.29.88.12
CATALOGUE_VIRTUAL_IP=172.29.88.20
SITE_B_READER_SOURCE_CIDR=192.168.56.1/32
SITE_B_CATALOG_SOURCE_CIDR=192.168.56.1/32
```

`SITE_B_CATALOG_SOURCE_CIDR` là tùy chọn mới cho gateway A đọc trực tiếp B; cần dùng bản sites.py trong gói source này. `b_reader` phục vụ FDW, `global_reader` phục vụ gateway; hai role cần HBA riêng. Hai dòng SOURCE dùng IP nguồn **B nhìn thấy**, thường là IP host A sau Docker masquerade, không phải IP container A 172.29.87.11. Nếu NAT/proxy khác, kiểm log B để xác định nguồn thật, không mở HBA cho mọi IP.

Port Docker được bind vào IP host-only của B. Nếu UFW active, có thể thêm rule cho đúng nguồn A:

```bash
sudo ufw allow from 192.168.56.1 to 192.168.56.101 port 56632 proto tcp
```

Không dựa riêng vào UFW để giới hạn port Docker; Docker có tương tác riêng với firewall. HBA vẫn chỉ cho đúng role/nguồn và yêu cầu mật khẩu.

## 6. Trên B: tạo database và fixture

```bash
python3 deploy/scripts/sites.py up --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
python3 deploy/scripts/sites.py bootstrap --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'
```

Mong đợi container `oldshop-vm-demo-pg-b-1` healthy, publish `192.168.56.101:56632->5432/tcp`. Bootstrap tạo schema, migrations, role, quy tắc site, contract và fixture 5 product/8 ảnh ở B; không phải bộ 1.000 product của commerce. Không chạy `database/init.sql` hoặc seed commerce bổ sung vào DB này.

Kiểm bằng tài khoản admin qua socket trong container, không cần nhập password:

```bash
docker exec -it oldshop-vm-demo-pg-b-1 psql -U site_admin -d oldshop_2
```

Trong psql:

```sql
SELECT current_database(), site_id FROM site_identity;
SELECT product_id, seller_id, site_id, title FROM product ORDER BY product_id;
SELECT * FROM v_fragment_identity;
```

Kết quả: oldshop_2/site B, product ID chẵn, `rules_valid=true`. Gõ `\q` để thoát. Giữ env/password và volume để lần sau `up` tiếp tục dùng dữ liệu cũ; không prepare lại hay xóa volume khi gặp lỗi kết nối.

## 7. Trên A: tạo site A riêng cho demo VM

Quay lại terminal A, root dự án. A hiện đã có Docker; không cài lại Docker trên A.

```bash
python3 deploy/scripts/sites.py prepare --env deploy/sites/.env.vm-demo
nano deploy/sites/.env.vm-demo
```

Sửa các dòng:

```ini
SITE_A_DB_NAME=oldshop_1
SITE_A_BIND_IP=127.0.0.1
SITE_A_PORT=56631
SITES_SUBNET=172.29.87.0/24
SITE_A_VIRTUAL_IP=172.29.87.11
SITE_B_VIRTUAL_IP=172.29.87.12
CATALOGUE_VIRTUAL_IP=172.29.87.20
CATALOGUE_PORT=56680
SITE_B_FDW_HOST=192.168.56.101
SITE_B_FDW_PORT=56632
SITE_B_CATALOG_HOST=192.168.56.101
SITE_B_CATALOG_PORT=56632
DISTRIBUTED_CATALOG_ROUTING=1
BACKEND_IMAGE=oldshop-vm-demo-backend:latest
```

Chép riêng giá trị của **SITE_B_READER_PASSWORD và SITE_B_GLOBAL_PASSWORD** từ env B vào đúng hai key trong env A, qua kênh riêng. Không cần password admin/writer của B giống A; không đăng env lên chat/Git. Sửa env sau bootstrap không tự đổi password role trong PostgreSQL.

```bash
python3 deploy/scripts/sites.py up --site A --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
python3 deploy/scripts/sites.py bootstrap --site A --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

Luôn có `--site A`: không dựng pg-b local trên A rồi nhầm đó là VM. Các DB `oldshop_1`/`oldshop_2` có thể cùng tên với project khác vì nằm trong container/volume project khác.

## 8. Trên A: kiểm đường mạng từ container tới VM

Kiểm FDW credentials từ đúng nơi sẽ mở kết nối:

```bash
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -h 192.168.56.101 -p 56632 -U b_reader -d oldshop_2 -W
```

Nhập SITE_B_READER_PASSWORD trong env B. Trong psql:

```sql
SELECT current_database(), current_user, site_id FROM site_identity;
SELECT inet_client_addr(), inet_server_addr();
\q
```

Mong đợi oldshop_2/b_reader/B. Kiểm tiếp gateway credentials:

```bash
docker exec -it oldshop-vm-demo-pg-a-1 \
  psql -h 192.168.56.101 -p 56632 -U global_reader -d oldshop_2 -W
```

Nhập SITE_B_GLOBAL_PASSWORD, rồi `SELECT * FROM v_fragment_identity;` phải có `rules_valid=true`. Thoát bằng `\q`. Chỉ ping thành công chưa đủ; hai phép đăng nhập này mới kiểm TCP, authentication và HBA.

Nếu bị từ chối HBA, trên B xem `docker logs --tail 50 oldshop-vm-demo-pg-b-1`, sửa đúng SOURCE_CIDR trong env B rồi áp lại:

```bash
python3 deploy/scripts/sites.py access --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

Lệnh `access` sinh lại HBA từ env; sửa tay pg_hba.conf có thể bị ghi đè ở lần này. Timeout/refused cần kiểm IP/bind/port/mạng trước, không đổi password ngẫu nhiên hoặc reset DB.

## 9. Trên A: tạo FDW và view toàn cục

```bash
python3 deploy/scripts/sites.py fdw --site A --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
docker exec -it oldshop-vm-demo-pg-a-1 psql -U site_admin -d oldshop_1
```

Trong psql tại A:

```sql
SELECT srvname, srvoptions FROM pg_foreign_server;
SELECT product_id, site_id, title FROM product ORDER BY product_id;
SELECT product_id, site_id, title FROM site_b.product ORDER BY product_id;
SELECT product_id, site_id, title FROM v_product ORDER BY product_id;
\q
```

srvoptions phải trỏ IP VM/cổng 56632, không phải container B cũ của project local. Bảng local A có ID lẻ; site_b.product đọc các ID chẵn trong VM; v_product ban đầu có 10 hàng (bao gồm cả pending/deleted). Giao diện API lọc visibility nên ban đầu trả 6 product, không phải 10.

## 10. Trên A: build và chạy gateway

Build image riêng trên A, không cần build backend trong VM B:

```bash
docker compose -p oldshop-vm-demo --env-file deploy/sites/.env.vm-demo \
  -f deploy/sites/compose.site-a.yml -f deploy/sites/compose.catalog.yml \
  build catalogue
python3 deploy/scripts/sites.py catalogue --site A --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

Mở `http://127.0.0.1:56680/docs` trên A. Kiểm:

```bash
curl -i http://127.0.0.1:56680/ready
curl -i http://127.0.0.1:56680/products/1
curl -i http://127.0.0.1:56680/products/2
curl -i 'http://127.0.0.1:56680/products?limit=100'
```

Phải có ready 200; product 1 ở A, product 2 ở B; danh sách có cả A/B. Nếu curl chạy ở VM thì 127.0.0.1 là VM, không phải A: các lệnh trên chạy tại A.

## 11. Demo bản ghi mới thực sự được ghi ở VM

Trên B, đăng nhập bằng role writer qua localhost bên trong container:

```bash
docker exec -it oldshop-vm-demo-pg-b-1 psql -h 127.0.0.1 -U site_writer -d oldshop_2 -W
```

Nhập SITE_B_WRITER_PASSWORD. Trong psql:

```sql
BEGIN;
INSERT INTO product(seller_id,category_id,title,price,quantity,status)
VALUES(202,1,'DEMO-VM-B-20261112',120000,1,1)
RETURNING product_id,site_id;
COMMIT;
\q
```

Ghi lại product_id trả về; không tự đoán ID. Trên A, mở psql admin rồi chạy:

```sql
SELECT product_id,site_id,title
FROM v_product
WHERE title='DEMO-VM-B-20261112';
```

Hoặc gọi detail với ID vừa nhận. Product mới phải có site B/ID chẵn và xuất hiện từ A mà không nạp lại dữ liệu. Đối chiếu hostname/IP B và endpoint FDW để chứng minh đúng VM, không chỉ dựa vào nhãn site_id.

## 12. Demo sự cố và phục hồi

Trên B, chỉ dừng PostgreSQL của project demo:

```bash
python3 deploy/scripts/sites.py stop --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

Trên A:

```bash
curl -i http://127.0.0.1:56680/products/1
curl -i http://127.0.0.1:56680/products/2
curl -i http://127.0.0.1:56680/products
curl -i http://127.0.0.1:56680/ready
```

Mong đợi lần lượt 200, 503, 503, 503. B không hoạt động thì không trả danh sách thiếu dữ liệu như thành công. Có thể thử tắt VM sau khi đã thành công với dừng service; khi tắt VM, IP phải giữ ổn định khi bật lại.

Trên B phục hồi:

```bash
python3 deploy/scripts/sites.py up --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

Lặp curl trên A: ready/global/detail B trở lại 200, product demo vẫn còn. Không bootstrap/reset để phục hồi dữ liệu. Dừng A và thử detail B chỉ hợp lý khi gateway A vẫn còn chạy; tắt cả VM/host chứa gateway thì client không thể gọi gateway đó.

Không chạy `verify`/`verify-api` của bộ demo cùng host để điều khiển mô hình hai máy: chúng không quản lý B từ xa và dựa fixture chuẩn. Kiểm thủ công đúng project/host như trên, lưu kết quả riêng.

## 13. Lưu bằng chứng và kết thúc

Lưu hostname/IP A/B, danh sách container mỗi máy, SELECT site_identity, srvoptions tại A, INSERT/COMMIT tại B, SELECT cùng ID từ A, HTTP trước/trong/sau sự cố. Không chụp env, password hoặc user mapping chứa credentials.

Demo này chứng minh catalogue phân mảnh và truy vấn giữa hai môi trường OS, chưa chứng minh checkout đa site, Mongo sharding hay chịu mất host vật lý khi VM vẫn nằm trên chính host A. Muốn demo toàn bộ dữ liệu seed commerce cần bước phân phối dataset riêng; không copy nguyên 1.000 product giống nhau vào cả A/B rồi gọi là phân mảnh.

Khi xong, dừng project tương ứng trên từng máy:

```bash
# Chạy tại A:
python3 deploy/scripts/sites.py stop --site A --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
# Chạy tại B:
python3 deploy/scripts/sites.py stop --site B --project oldshop-vm-demo --env deploy/sites/.env.vm-demo
```

`stop` giữ dữ liệu; không dùng `down -v`/volume prune để xử lý lỗi. File hướng dẫn và tùy chọn HBA đã được kiểm tra trên source; việc cài Ubuntu/Docker và kết nối VM thật cần được thực hiện trên máy B của bạn.
