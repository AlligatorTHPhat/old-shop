# Đo index bằng dữ liệu dự án, gồm seeding

Ngày hướng dẫn: 11/11/2026. Không reset, seed lại, migrate, chạy ETL hoặc đổi index để thực hiện phép đo hiện trạng dưới đây.

## 1. Vì sao lệnh trên host lỗi psycopg2?

`python -m scripts.benchmark_current` sử dụng Python của terminal hiện tại. Python đó chưa có dependency backend, dù container backend đang chạy bình thường. `psycopg2` là tên module import; dependency của dự án là `psycopg2-binary==2.9.13`.

Chạy `python -c 'import sys; print(sys.executable)'` để biết Python đang dùng. Cài bằng `pip` của Python khác không sửa được lỗi này. Không cần thay database để chữa lỗi import.

Đã kiểm tra trong container `oldshop-data-backend-1`: Python 3.13.18, psycopg2 2.9.13, cấu hình PostgreSQL `pg-primary:5432/oldshop`, MongoDB `oldshop`, có source seed ở `/opt/database/03_seeds`. Đây là cấu hình trong lần kiểm tra, không khẳng định số lượng dữ liệu hiện tại bằng seed.

## 2. Chạy bằng backend Docker hiện hữu

Các lệnh sau dùng Bash trên Linux/WSL. Chạy từ root dự án, không chạy từ `backend/`:

```bash
cd /home/phat/Documents/Project/Epic-Ecommerce-FastAPI-main
docker ps --format '{{.Names}} {{.Status}}'
```

Chọn **backend commerce** `oldshop-data-backend-1`. Không chọn `oldshop-fragmentation-catalogue-1`: đó là gateway bộ fixture hai site, không phải toàn bộ dữ liệu ứng dụng/seed bạn muốn đo.

Kiểm thư viện và cấu hình đích; lệnh không in mật khẩu hoặc URI:

```bash
docker exec -e PYTHONPATH=/app oldshop-data-backend-1 python -c 'import sys, psycopg2, pymongo; from app.core.config import settings; print("Python:", sys.version.split()[0]); print("PostgreSQL:", settings.DB_HOST, settings.DB_PORT, settings.DB_NAME); print("Mongo configured:", bool(settings.MONGO_URI)); print("Mongo database:", settings.MONGO_DB)'
```

Nếu sai container/database, dừng tại đây và chọn đúng môi trường. Không sửa `.env` chỉ để lệnh chạy được vào một DB bất kỳ.

Tạo mã lần đo để không ghi đè kết quả cũ:

```bash
bench_stamp=$(TZ=Asia/Ho_Chi_Minh date +%Y%m%d_%H%M%S)
bench_container_dir="/tmp/oldshop-benchmark-${bench_stamp}"
bench_host_dir="docs/benchmark/du-lieu-du-an-${bench_stamp}"
```

Chép đúng script từ working tree vào `/tmp` container; không phải build lại image:

```bash
docker cp backend/scripts/benchmark_current.py oldshop-data-backend-1:/tmp/oldshop-benchmark-current.py
```

Đo 30 lượt sau 3 lượt warm-up:

```bash
docker exec -e PYTHONPATH=/app oldshop-data-backend-1 \
  python /tmp/oldshop-benchmark-current.py \
  --source-root /opt \
  --output "$bench_container_dir" \
  --samples 30 \
  --warmups 3
```

Chỉ tiếp tục nếu lệnh thành công. Output cuối có đường dẫn kết quả và số lượng dữ liệu từng kho. Nếu lỗi Mongo sau khi đã đo PG, thư mục có thể mới chỉ có kết quả một phần; sửa kết nối rồi dùng timestamp mới, không coi đó là lần đo hoàn chỉnh.

Lấy kết quả ra host:

```bash
docker cp "oldshop-data-backend-1:${bench_container_dir}" "$bench_host_dir"
```

Các biến `bench_*` chỉ tồn tại trong terminal hiện tại. Nếu đổi terminal, khai báo lại đúng đường dẫn lần đo. Nếu Docker báo permission denied, dùng quyền Docker theo cấu hình máy; đây không phải lỗi DB.

Script đo dữ liệu đang được lưu, gồm seed đã nạp và dữ liệu phát sinh. Nó không đọc SQL seed rồi tạo một dataset mới. `--source-root /opt` ghi hash seed của image trong manifest; nếu seed trên host đã sửa nhưng image chưa build lại thì hash này mô tả seed trong image, không phải seed mới trên host.

## 3. Đọc kết quả

```text
du-lieu-du-an-<timestamp>/
  manifest.json
  pg/
    summary.json
    indexes.json
    catalogue.json / catalogue.txt
    catalogue_category.json / catalogue_category.txt
    ...
  mongo/
    summary.json
    indexes.json
    product_details.json
    ...
```

| File/thông tin | Cần xem |
| --- | --- |
| `pg/summary.json` | Đúng database/version, số hàng, migration hiện có; query measured hay skipped |
| `pg/indexes.json` | Index nào thật sự tồn tại, không chỉ có trong source |
| `pg/<query>.json` | SQL, tham số thực tế, execution/planning time, plan, buffers, filter và sort |
| `mongo/summary.json` | Đúng database; docs/keys examined, số kết quả và collection bị bỏ qua |
| `mongo/<query>.json` | Filter, projection, sort và executionStats đầy đủ |
| `manifest.json` | Nguồn seed, thời điểm, dữ liệu và giới hạn của lần đo |

Kiểm `Index Scan`, `Index Only Scan`, `Bitmap Index Scan` hoặc `Seq Scan` trong plan. Xem index được dùng, lượng dữ liệu đọc và SORT; không chỉ nhìn số mili giây. Tập nhỏ hoặc điều kiện ít chọn lọc có thể hợp lý khi dùng Seq Scan. Mongo có `0 ms` không nghĩa không tốn công việc vì số đo server có độ phân giải millisecond.

Script hiện báo **median server execution time**, không báo p95 HTTP hoặc throughput. `--samples 30` không tự biến báo cáo thành p95. Nó giữ nguyên các index hiện có, không tự đo một phiên bản "trước tối ưu".

## 4. Đo riêng index seller mới

`benchmark_current` có ca seller orders nhưng chưa có ca độc lập đúng query liệt kê product theo seller của gateway mới. Để xem plan của index mới, chạy SQL đọc dưới đây trong pgAdmin/psql trên đúng DB có bảng product.

Chọn seller thực sự có hàng đang hiển thị:

```sql
SELECT seller_id, count(*) AS visible_products
FROM product
WHERE status = 1 AND NOT is_deleted
GROUP BY seller_id
ORDER BY count(*) DESC, seller_id
LIMIT 5;
```

Ví dụ seller 3 còn dữ liệu; thay 3 bằng ID lấy từ kết quả trên:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT product_id, title, price, created_at
FROM product
WHERE seller_id = 3 AND status = 1 AND NOT is_deleted
ORDER BY created_at DESC, product_id ASC
LIMIT 20;
```

Index đích là `idx_product_visible_seller_date_id`. Nếu commerce chưa áp migration 008, index này có thể chưa tồn tại; đó là trạng thái cần ghi nhận, không tự tạo index trên DB đang dùng chỉ để có một plan đẹp. Với bộ fixture catalogue riêng, seller là 101/202; không lấy các ID fixture này làm tham số cho dữ liệu commerce một cách máy móc.

## 5. Nếu muốn chạy trực tiếp trên host

Chỉ dùng nhánh này khi muốn quản lý Python và cấu hình host riêng. Nếu chỉ cần đo, nhánh Docker ở trên đã đủ.

```bash
cd /home/phat/Documents/Project/Epic-Ecommerce-FastAPI-main/backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --only-binary=:all: --require-hashes -r requirements.lock
python -m pip check
python -c 'import sys, psycopg2, pymongo; print(sys.executable); print(psycopg2.__version__)'
```

Nếu chưa có Python 3.13 thì dùng Docker, không cần cài thêm Python chỉ để đo. Nếu đã có venv backend đúng phiên bản/dependencies thì activate venv đó, không tạo chồng lên môi trường đang sử dụng.

Kiểm `backend/.env`: PostgreSQL/Mongo phải truy cập được **từ host**. Các hostname nội bộ `pg-primary`, `mongo1` trong Docker không mặc nhiên truy cập được từ host. `DATABASE_URL` có ưu tiên hơn các `DB_*`; Mongo cần URI hợp lệ, không để trống. Không chép đè `.env` đang dùng. Xem [hướng dẫn môi trường host](HUONG_DAN_CAU_HINH_VA_CHAY_HE_THONG.md).

Sau khi import và kết nối đúng:

```bash
python -m scripts.benchmark_current \
  --output ../docs/benchmark/du-lieu-du-an-lan-moi \
  --samples 30 \
  --warmups 3
```

## 6. Có nên reset DB hoặc đổi seed/ID không?

**Không reset DB đang dùng chỉ để đo index hoặc làm product_id liên tục.** Lỗi psycopg2 không liên quan dữ liệu. `product_id` có khoảng trống không có nghĩa index bị lỗi. Khi muốn xem ID có thứ tự, dùng `ORDER BY product_id`.

Seed hiện giữ 16 sản phẩm gốc để đơn hàng mẫu tham chiếu đúng, rồi bổ sung 984 sản phẩm thành 1.000. Mã SP-00017…SP-01000 hiện nằm trong title/description, không phải cột SKU riêng. Ảnh seed dùng công thức liên kết theo product_id. Không đổi/reseed riêng product mà bỏ qua ảnh, order_detail, cart, review, outbox, Mongo và media.

| Mục đích | Cách làm |
| --- | --- |
| Đo dataset đang dùng, gồm seed và dữ liệu phát sinh | Giữ nguyên DB, chạy benchmark hiện trạng |
| Chỉ muốn bảng hiện ID tăng dần | Thêm ORDER BY khi xem/truy vấn |
| Cần mã hiển thị dễ đọc | Thiết kế thêm product_code/SKU độc lập; không đổi PK để phục vụ index |
| Muốn seed sạch có thể lặp lại | Tạo DB/stack thử nghiệm mới, dùng cùng seed revision; không reset DB chính |
| Muốn chứng minh index nhanh hơn | Restore cùng snapshot vào môi trường thử nghiệm, so sánh bộ index cũ/mới trên dataset giữ nguyên |

Nếu cải tiến seed sau này, ưu tiên giữ đúng FK, phân bố seller/category/status/price/time có tính đại diện, ngày mốc cố định và seed revision. Seed hiện không dùng random cho phần product bổ sung, nhưng thời gian dựa CURRENT_TIMESTAMP nên không giống tuyệt đối giữa hai lần khởi tạo khác ngày. Đổi seed giữa hai lần đo làm thay đổi dataset và không còn cô lập được tác động của index.

DB mới là lựa chọn phù hợp nếu bạn muốn một bộ seed sạch để trình diễn. Việc này cần cấu hình đủ PG/Mongo/media/ETL tương ứng khi demo luồng tích hợp, không chỉ reset một bảng product. Không chạy lại `database/init.sql` trên database đang có dữ liệu.

## 7. So sánh trước/sau đúng cách

1. Backup dataset dự án, restore vào môi trường đo riêng; nếu chỉ muốn seed sạch thì khởi tạo một dataset mới và giữ nguyên nó cho cả hai phương án.
2. Ghi lại revision, số hàng/document, query, tham số, bộ index và thống kê. Cố định trạng thái nguồn ghi/ETL để dataset không đổi giữa hai phương án.
3. Đo bộ index cũ; thêm index ứng viên trên bản thử nghiệm; đo lại cùng query/tham số/cache/workload. Với PostgreSQL, duy trì thống kê ANALYZE phù hợp và cùng phương pháp ở hai phương án.
4. Đối chiếu kết quả trả về, plan/buffers/docs/keys, nhiều lượt thời gian và dung lượng index. Chi phí ghi cần workload ghi riêng trên DB thử nghiệm, có tính commit/fsync nếu muốn kết luận về thực tế.
5. Không bỏ PK/UNIQUE hoặc index bảo vệ constraint. `SET enable_seqscan=off` không tương đương dataset "không có index" và không dùng để công bố mức tăng tốc thực tế.

Benchmark hiện trạng không tự thực hiện các bước thay index trên bản sao. Các số liệu giả lập ở [benchmark fragmentation](benchmark/fragmentation_indexing/README.md) cũng không thay cho phép đo trước/sau trên dataset dự án của bạn.
