# Ngày 4 — Indexing, partitioning và benchmark

Thực hiện 29/10/2026 (ngày dự kiến trong kế hoạch là 30/10). Theo D3/D4/D6;
không tự chốt D7 timezone hoặc D8 mã transaction. **Đã triển khai, kiểm thử và áp vào stack local.**

## Đầu ra

- Bốn migration SQL: 001_indexes, 002_partitioning, 003_vertical_split,
  004_media_metadata trong `database/04_migrations/`.
- Runner `backend/scripts/migrate.py`: baseline fingerprint, session advisory lock,
  transaction/version/checksum; bootstrap và CI cùng chuỗi migration.
- Models/services ghi user_core/profile/secret/wallet, giữ API contract và user_role.
  users_full chỉ đọc; SystemLog dùng PK ghép log_id/created_at.
- Script sinh dữ liệu/benchmark PG và Mongo, bảo trì log tháng, backfill metadata ảnh,
  backup/restore stores và đối soát digest nguồn.
- [Thiết kế + bảng truy vấn/index/chi phí](design/04_indexing.md),
  [ERD sau migration](diagram/04_erd_target.dbml), [benchmark và evidence](benchmark/README.md).
  ERD Ngày 1 vẫn giữ làm mô hình baseline lịch sử.

## Phát hiện, lựa chọn và lỗi đã xử lý

1. Tên ở ví dụ kế hoạch không phải tên schema thật: product.title, order.buyer_id/order_date,
   không có seller_id trên order. Seller phải join qua order_detail/product. Không thêm index
   vào cột không tồn tại hoặc trùng index FK/reference_number đã có.
2. Search ILIKE có OR description: cần cả hai GIN trigram partial, không chỉ title.
3. Query category trước không ORDER BY nên sort_by không có tác dụng. Đã áp sort_by như
   catalogue mặc định, dùng created_at DESC khi không chỉ định; không đổi frontend contract.
4. Thử hai index review mới nhưng planner vẫn dùng idx_review_product/rating. Loại chúng
   khỏi migration cuối thay vì giữ để tăng số lượng index. Kết quả cuối đo lại trên DB mới.
5. LIKE table copy không tự copy FK; order swap phải lưu/chép FK hai chiều, giữ transaction
   ON DELETE CASCADE, sequences, CHECK/NOT NULL và trigger order_detail.
6. User rename giữ OID để FK trỏ core; ba mảnh sao chép và EXCEPT ALL đúng 20 cột.
   ORM association proxy lúc đầu được gán trước khi tạo quan hệ con nên register/moderator
   lỗi constructor; đã sửa tạo ba mảnh trước, kiểm thử atomic rollback và full regression đạt.
7. psql không mở rộng DSN chỉ đặt ở PGDATABASE như dự định ban đầu; sửa bootstrap dùng
   libpq service file tạm 0600, giữ URL query options, không đưa secret vào argv. Có test URL-only,
   password ký tự đặc biệt và baseline drift. Không fallback sang DB_* trỏ sai database.
8. Test CREATE DATABASE không được nằm trong transaction dù dùng context connection;
   sửa admin connection autocommit ngoài transaction. Đây là lỗi test harness, không bỏ test.
9. Benchmark xuất sum(pg_indexes_size) trả Decimal nên JSON ban đầu lỗi; sửa chuyển int,
   chạy lại DB mới. Bằng chứng phát hành là day4_bench_20261029_final, không lấy số đo bản nháp.
10. Log RANGE cần PK ghép và lịch tạo tháng: có DEFAULT tránh mất ghi ngoài lịch,
    script maintain_log_partitions chuyển đúng overflow trước ATTACH, đã kiểm thử chạy lại.
11. MinIO ảnh mới giờ lưu content_type/size_bytes vào product_image cùng commit. Backfill
    chỉ stat key đã tham chiếu, không suy product ID từ tên file và không list bucket để trả API.
12. Mongo giữ 7.0.43 do lỗi kernel với 8.0.32 đã biết; index dùng order_date/order_status/action
    theo schema thực, không lấy created_at/status/type sai từ ví dụ cũ. Chưa chạy ETL Ngày 5.

## Kết quả thực chạy

- Image `oldshop-data-backend:day4` build thành công.
- **96 passed in 13.69s**, không skip: toàn bộ regression cũ + integration Mongo/MinIO +
  15 test Ngày 4. DB riêng `day4_test_20261029183655_31302` được giữ lại.
- Kiểm thử checksum bị sửa → từ chối; DDL lỗi → rollback cả bảng/history; baseline lệch →
  từ chối; rerun → no-op; PK/FK/self-buy/cart uniqueness; OTP/profile/wallet/đăng ký/role;
  monthly overflow di chuyển; MinIO upload/API/metadata/ảnh legacy.
- Benchmark: 100.030 orders, 50.016 products, 100.000 logs, 100.000 review; 9 truy vấn PG.
  Search 316,562 → 0,372 ms; seller orders 44,052 → 17,521 ms; không phải mọi truy vấn nhanh hơn.
  Full migration đo 11,47 giây, chưa tính backup/startup.
- Hash order PK chỉ đọc order_h3; log tháng chỉ đọc system_log_202603. Lịch sử buyer vẫn
  merge cả bốn hash partition. Index tăng 35.225.600 → 58.736.640 bytes.
- Mongo explain ba query: documents examined 192→20, 10.000→10 và 10.000→10.

## Áp dụng local có bảo trì

Đã chạy `bash deploy/scripts/apply-day4.sh --resilience` sau khi test image đạt.
Dừng backend/frontend để chặn cả API ghi; chưa có ETL worker. Backup PostgreSQL và restore
vào DB mới; so sánh đủ digest/cột/dòng của **18 bảng nguồn**. Backup sáu collection Mongo
(hiện chưa có document ứng dụng vì ETL chưa chạy) và **95 object MinIO**; restore thử tên/prefix
UUID, xác minh BSON/bytes rồi dọn đúng dữ liệu thử. Đây không phải dữ liệu giả ghi vào PG thật.

Sau đó migrate versions **001–004**, backfill metadata **32 ảnh**, không ảnh unavailable;
đối soát lại 18 bảng giữ nguyên digest/count nguồn: 15 user, 30 order, 30 transaction,
16 product, 32 product_image và các bảng khác. Nâng backend, restart Nginx để cập nhật DNS.
Readiness **database=up, mongo=up, minio=up**; giữ profile PG replica/Mongo ba member.
Kiểm tra cuối [stack](benchmark/day4_stack.json) PASS, replica streaming/async đã replay WAL
và có đủ 30 đơn. [Chạy lại](benchmark/day4_repeat.txt): applied=[], metadata updated=0.

Backup private: `deploy/backups/day4_20261029_183835/` (ignored).
DB restore giữ lại: `day4_restore_20261029_183835`.
[Log áp dụng](benchmark/day4_apply.txt), [log test](benchmark/day4_tests.txt).
Không reset/reseed/drop database ứng dụng. Không chạm lab03-mongo hoặc minio-local.

## Giới hạn còn lại

- Backup diễn tập cùng máy, chưa có bản ngoài máy hoặc khả năng chịu mất host.
- Nhiều migration đã commit không rollback cả chuỗi khi version sau lỗi; script giữ
  maintenance, cần khôi phục có quy trình hoặc forward migration. Không tự sửa checksum.
- Tách bảng không tự tạo phân quyền DB theo principal; app owner vẫn đọc được secret/wallet.
  View chỉ đọc và serializer không xuất bí mật, nhưng chưa có RLS hay tài khoản theo module.
- Giữ timestamp nguồn, D7 chưa quyết định. D8 raw status không remap; hàm voucher DB cũ
  không được backend dùng vẫn có lỗi đã biết ở D11, chưa sửa ngoài scope ngày này.
- Nhiễu thời gian benchmark; PK/cart/log tháng có lượt chậm hơn dù plan/pruning đúng.
  Chưa đo write throughput, chưa claim mọi index tăng tốc hoặc SLA.
- GC ảnh, FK invariant core có đủ con khi DBA ghi trực tiếp, theo dõi DEFAULT log và
  lịch bảo trì tháng là trách nhiệm vận hành được ghi rõ trong tài liệu thiết kế.
