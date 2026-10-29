# Benchmark Ngày 4 — 29/10/2026

Đo thực trên PostgreSQL 16.15, Docker một máy, schema baseline v0 rồi migrate trên **cùng
một DB riêng** `day4_bench_20261029_final`. Có warmup trước mỗi truy vấn, trung vị ba lượt
EXPLAIN ANALYZE BUFFERS FORMAT JSON; một lượt text bổ sung để đọc plan. Không ép planner,
không xóa index cũ, ANALYZE cả trước/sau. Giới hạn backend/PG theo Compose và các container
khác chạy cùng máy nên thời gian có nhiễu/cache/scheduling; không suy ra SLA hoặc tải production.

Dữ liệu tổng: **50.016 products, 100.030 orders, 100.000 system_log**, 100.000 review,
50.000 cart item; trong đó sinh mới 50.000 products/100.000 orders/1.000 users.
Buyer và seller giả thuộc hai nhóm tách biệt để trigger self-buy không bị bỏ qua;
phân bố 500 seller, 500 buyer, dữ liệu ngày cố định trong năm 2026, không có dữ liệu cá nhân thật.
Migration và copy đối soát ở quy mô này mất **11,47 giây**; đây không phải toàn thời gian bảo trì,
vì backup/restore/startup còn tốn thêm thời gian.

## PostgreSQL: trung vị Execution Time (ms)

| Truy vấn | Trước | Sau | Plan / đánh giá |
|---|---:|---:|---|
| Catalogue category + mới nhất | 0,261 | 0,166 | idx_product_catalogue, lấy 20 dòng |
| ILIKE title OR description | 316,562 | 0,372 | Seq Scan → BitmapOr hai GIN trigram |
| Lịch sử buyer | 0,730 | 0,436 | Merge Append bốn B-tree buyer/date, không hash-prune theo buyer |
| Đơn seller | 44,052 | 17,521 | Index Only Scan idx_order_detail_product_order |
| Review theo product | 0,085 | 0,158 | Vẫn dùng index baseline; không có bằng chứng cần composite mới |
| Report rating=0 | 0,145 | 0,327 | Vẫn dùng idx_review_rating; loại đề xuất partial mới |
| Lookup cart/product | 0,048 | 0,114 | uq_cart_product; lý do chính là tính duy nhất, không chứng minh nhanh hơn |
| Order theo PK | 0,050 | 0,088 | Chỉ order_h3, prune ba phần còn lại; chưa có lợi ích thời gian ở workload nhỏ |
| Log tháng 03/2026 | 4,410 | 4,582 | Chỉ system_log_202603; Seq Scan hợp lý khi đọc cả tháng, chưa nhanh hơn |

Tổng dung lượng index vật lý: **35.225.600 → 58.736.640 byte**. GIN/B-tree bổ sung và
partition có chi phí dung lượng, WAL/ghi; chưa đo throughput ghi dưới tải đồng thời.
Không chỉ báo các truy vấn nhanh hơn. Index review mới được thử ở bản nháp, rồi bỏ vì planner
chọn index baseline; các file trước/sau ở đây đều từ **bản migration cuối**.

[summary.json](pg/summary.json) giữ số đo máy đọc. Mỗi truy vấn có `before_*.txt`,
`after_*.txt` và JSON đủ ba lượt, gồm Buffers, Planning Time, Execution Time.
Ví dụ: [search trước](pg/before_search.txt), [search sau](pg/after_search.txt),
[order prune](pg/after_order_pk_pruning.txt), [log prune](pg/after_log_month_pruning.txt).

## MongoDB: executionStats

Mongo **7.0.43** theo ngoại lệ kernel đã thống nhất từ Ngày 2. Mỗi collection tạm có
10.000 document, validator cùng hợp đồng Ngày 3; trước chỉ _id, sau thêm index ứng dụng.
Một lượt explain mỗi pha, không hint; milliseconds chỉ tham khảo, docs examined là bằng chứng chính.

| Query | Docs examined trước → sau | Keys sau | Returned | Milliseconds trước → sau |
|---|---:|---:|---:|---:|
| product_details category/brand, limit 20 | 192 → 20 | 20 | 20 | 4 → 2 |
| reviews product/date | 10.000 → 10 | 10 | 10 | 83 → 2 |
| order_snapshots buyer/order_date | 10.000 → 10 | 10 | 10 | 20 → 1 |

[Mongo summary](mongo/summary.json), sáu file explain trong `mongo/`. Collection tạm
được xóa sau đo; không seed dữ liệu giả vào collection thật. Không tuyên bố kết quả Mongo 8.

## Lặp lại

Chạy từ root sau khi build image day4 và stack dữ liệu đã healthy:

```bash
bash deploy/scripts/test-day4.sh
# Đổi DB_NAME sang tên mới mỗi lượt; script từ chối DB đã tồn tại.
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --user "$(id -u):$(id -g)" -e DB_NAME=day4_bench_new_run -v "$PWD/docs/benchmark:/evidence" --entrypoint python backend -m scripts.benchmark_day4 --output /evidence/pg_new_run
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --user "$(id -u):$(id -g)" -v "$PWD/docs/benchmark:/evidence" --entrypoint python backend -m scripts.benchmark_mongo_day4 --output /evidence/mongo_new_run
```

DB benchmark/test được giữ cho việc xem xét, không tự reset. Script chỉ tạo DB có prefix
`day4_bench_`; các bảng thật không bị truncate. Không chạy nhiều benchmark/maintenance cùng lúc.

## Bằng chứng kiểm thử và áp dụng

- [96/96 tests PASS](day4_tests.txt), gồm 24 test Ngày 3 và 15 test Ngày 4; không skip.
- [Maintenance, backup/restore và migrate](day4_apply.txt).
- [Trạng thái stack và replication](day4_stack.json).
- Snapshot so sánh 18 bảng nguồn bằng count + digest mọi cột v0; user khôi phục qua users_full.
  Backup chứa dữ liệu nhạy cảm ở deploy/backups, không chép vào thư mục evidence.
