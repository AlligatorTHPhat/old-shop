# Vận hành migration indexing v2 (007)

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
