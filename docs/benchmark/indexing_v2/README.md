# Indexing v2 — triển khai và tái lập

Migration [007](../../../database/04_migrations/007_indexing_v2.sql) bổ sung 9 index
PostgreSQL; Mongo schema bổ sung M01 trên `product_details.images.key` khi `deleted=false`.
Giữ các index cũ và mọi PK/UNIQUE. Không đổi seed mặc định, timestamp của worker hay API.

[Báo cáo ngày 01/11/2026](2026-11-01/README.md) chứa quyết định cho đủ I01–I14,
M01/M02 và dữ liệu đo thô. Đây là bằng chứng trên hạ tầng thử nghiệm; DB đang dùng của
người dùng **chưa được áp dụng** trong lần thực hiện này.

## Chạy lại trên môi trường riêng

Chạy từ root repository, cần Docker Compose, Python 3.9+ và các image trong Compose.
Runner dùng `.env.data.example` để sinh credentials tạm; không đọc `backend/.env` hoặc
`deploy/.env.data`. Các cổng host chọn ngẫu nhiên, project/volume riêng. Mongo được pin
8.0.32; PG lấy image cấu hình của Compose nên cần ghi nhận version mỗi lần đo.

```bash
python3 deploy/scripts/test-indexing-v2.py --phase benchmarks \
  --evidence docs/benchmark/indexing_v2/lan-do-moi \
  --state /tmp/oldshop-indexing-v2-lan-do-moi.json --keep
python3 deploy/scripts/test-indexing-v2.py --phase tests \
  --evidence docs/benchmark/indexing_v2/lan-do-moi \
  --state /tmp/oldshop-indexing-v2-lan-do-moi.json --reuse --keep
python3 deploy/scripts/test-indexing-v2.py --cleanup \
  --evidence docs/benchmark/indexing_v2/lan-do-moi \
  --state /tmp/oldshop-indexing-v2-lan-do-moi.json --reuse
```

Dùng evidence/state mới cho mỗi lần đo; script benchmark từ chối output/DB đã tồn tại.
`--phase prepare --keep` chỉ chuẩn bị hạ tầng; dùng tiếp `--reuse` để chạy các phase.
Không chạy các phase đồng thời khi thu số liệu. Bộ ETL/API nạp lại full seed ở nhiều
fixture nên có thể mất vài chục phút với giới hạn PG 1 CPU; log tiến độ nằm trong
`tests_regression.txt`, `tests_etl.txt`, `tests_api.txt` của thư mục evidence. Nếu không có `--keep`, runner dọn stack
riêng cả khi lỗi; `--cleanup` chỉ xóa project được ghi trong state, không tác động project khác.
State/env tạm có quyền 0600, không đưa vào Git. Dev dependencies được cài theo hash lock.
Source backend/database được mount chỉ đọc; evidence là output duy nhất trong repository.

Benchmark L tạo khoảng 51k product, 100k order và 200k event trên DB tên `indexing_v2_*`.
Đây là fixture tải riêng, không thay seed ứng dụng. PG thử từng ứng viên rồi bỏ, so từng
kết quả bằng fingerprint, sau đó áp đúng migration 007 để đo cả gói. Phép approved/ETL write bổ sung dùng clone
riêng và thứ tự A–B–B–A, không đổi lịch sử/DB nguồn; clone được xóa sau đo. Mongo dùng collection
UUID tạm và xóa trong `finally`. Các thao tác ghi EXPLAIN trên PG được rollback; chúng vẫn
có thể sinh WAL, tăng sequence và tạo dead tuples nên không dùng DB thật để chạy benchmark.

## Tự áp vào DB đang dùng

1. Xác nhận đúng host/port/database của backend và bản backup đã thử restore. Chỉ sửa
   `.env` khi đang trỏ sai DB; pgAdmin là client, không quyết định nơi backend kết nối.
2. Với backend chạy trực tiếp, vào `backend/`, kích hoạt virtualenv có dependencies và
   thực hiện trong thời gian bảo trì (dừng backend/worker, các nguồn ghi ngoài ứng dụng):

   ```bash
   python -m scripts.verify_indexing_v2 --preflight
   python -m scripts.verify_day4 --output /duong-dan-rieng/source_before.json
   python -m scripts.migrate
   python -m scripts.init_mongo
   python -m scripts.verify_indexing_v2 --mongo
   python -m scripts.verify_day4 --compare /duong-dan-rieng/source_before.json
   python -m etl.run reconcile
   ```

   `migrate` cần quyền tạo index; `init_mongo` cần quyền collMod/createIndex hiện có.
   `--preflight` chỉ đọc và đòi schema tối thiểu 006, checksum khớp source. Sau migration,
   chạy `ANALYZE product, product_image, user_profile, "order", etl_runs, etl_outbox, user_role;`
   trong Query Tool rồi kiểm tra reconcile trước khi bật dịch vụ. Snapshot chỉ xuất số dòng
   và digest, nhưng vẫn giữ file backup/snapshot riêng.
3. Với stack Compose chính đã ở 006 và ETL đồng bộ (kiểm `etl.run status`: pending/dead bằng 0), có script bảo trì:

   ```bash
   bash deploy/scripts/apply-indexing-v2.sh
   # Nếu đang dùng đầy đủ profile resilience:
   # bash deploy/scripts/apply-indexing-v2.sh --resilience
   ```

   Script build backend mới, kiểm preflight, dừng app/worker, pg_dump, thử pg_restore vào
   DB riêng, đối chiếu nguồn, archive Mongo/media, migrate, ANALYZE, init Mongo, kiểm
   index/reconcile và bật lại.
   Backup PostgreSQL nằm trong `deploy/backups/indexing_v2_<stamp>/` (không vào Git).
   DB restore rehearsal được giữ để kiểm tra rồi tự xóa sau. M01 chỉ thêm index; script
   chạy thêm `archive_day4 backup/verify` vào `stores/` để lưu Mongo và MinIO/local media.
   Migration/M01 chỉ thêm index; bước reconcile có thể đánh dấu projection cũ hoặc thu gom
   media theo cơ chế hiện có, nên script sao lưu cả ba kho trước khi thực hiện.
   Script dùng `deploy/.env.data` và Compose chính; không dùng nó cho backend native,
   stack có override/project name riêng hoặc DB chưa qua 006.
4. Lệnh chỉ đọc sau áp dụng: `python -m scripts.verify_indexing_v2 --mongo` cần PASS,
   đủ 001–007, 9 định nghĩa index đúng, index voucher parent + 4 children hợp lệ, M01
   nonunique/partial đúng. Có thể bỏ `--mongo` nếu chỉ muốn kiểm PostgreSQL. Checker
   `check-data-stack.py` cũng gọi kiểm này khi lịch sử có 007.

`CREATE INDEX` chạy trong transaction theo runner nên cần bảo trì, không sửa thành
`CONCURRENTLY` trong file này. Không paste SQL 007 riêng trong pgAdmin rồi tự chèn lịch sử;
dùng runner để giữ checksum và kiểm thứ tự version. Không sửa 001–006/baseline để vượt lỗi.

## Thu hồi và theo dõi

Nếu 007 lỗi trước commit, runner rollback cả version. Nếu đã commit và cần thu hồi,
tạo version tiếp theo (hiện là 008) chứa `DROP INDEX` cho đúng index mới sau khi kiểm
nghiệp vụ/dependency. Không dùng CASCADE, không xóa schema_migrations, không sửa file 007
đã áp. Index parent voucher tự quản lý children; kiểm catalog trước thao tác. M01 thu hồi
bằng `dropIndex('idx_live_product_image_key')` trên đúng DB và bỏ khai báo tương ứng ở
source trong cùng phiên bản ứng dụng; không cần sửa document.

DDL tham khảo cho migration bù (chỉ tạo khi đã quyết định thu hồi; không đặt sẵn vào
`04_migrations/` vì runner sẽ tự áp tất cả version):

```sql
DROP INDEX public.idx_user_role_role_user;
DROP INDEX public.idx_etl_outbox_pending_event;
DROP INDEX public.idx_etl_outbox_entity_pending;
DROP INDEX public.idx_etl_runs_aggregate_success;
DROP INDEX public.idx_etl_runs_started;
DROP INDEX public.idx_order_voucher_lookup;
DROP INDEX public.idx_user_profile_avatar_url;
DROP INDEX public.idx_product_image_url;
DROP INDEX public.idx_product_visible_date_id;
```

Theo dõi latency/p95 đọc và ghi, WAL/disk, HOT/vacuum, queue pending/dead/oldest event,
reconcile mismatch và shared-image cleanup trong đủ chu kỳ nghiệp vụ. Những index cũ
chồng lặp chỉ được xem xét bỏ ở version sau khi có pg_stat_user_indexes và dependency.
