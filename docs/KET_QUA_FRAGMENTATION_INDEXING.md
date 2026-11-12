# Kết quả triển khai fragmentation và indexing

Ngày: 10/11/2026. Nguồn yêu cầu: [kế hoạch](KE_HOACH_SUA_FRAGMENTATION_INDEXING.md), [CookBook](CookBook.md).

## Phần đã triển khai

- Contract `fragmentation-v1` có validator, digest và kiểm đầy đủ hai mảnh A/B; `seller_site` là nguồn owner, parity ID là cơ chế cấp ID/định tuyến product.
- Gateway định tuyến detail và ảnh theo site; thêm lọc seller, tra mapping ở A, kiểm health theo phạm vi. Global query giữ contract đầy đủ dữ liệu; không có seller mapping trả 404; drift hoặc thiếu site bắt buộc trả 503.
- Đọc B trực tiếp bằng DSN riêng hoặc dùng view FDW riêng ở A khi chưa cấu hình DSN B. Query client không cần biết tên DB/site. Count/filter/sort/page được giữ trong SQL, thứ tự ổn định theo product_id.
- Migration site 001 bổ sung identity, fingerprint constraint/trigger/function/sequence và checksum reference đã duyệt. Giữ nguyên chính sách chặn đổi owner và FK ảnh local. Không thêm endpoint ghi vào gateway.
- Index release `index-v2-fragmentation`: snapshot bất biến, binding checksum và migration bổ sung 008 cho seller visible `(seller_id, created_at DESC, product_id ASC)`. Snapshot/release cũ và SQL 001–007 không bị sửa.
- Planner kiểm duplicate trước unique build PostgreSQL/MongoDB. Mongo xét missing/null/sparse/partial; multikey cần review tường minh. Planner không tự sửa dữ liệu hoặc drop/rebuild index.
- Có plan/verify index riêng commerce/site-a/site-b; audit ba tính chất phân mảnh; benchmark database UUID riêng; runner nâng cấp có backup/restore rehearsal, checksum, source manifest và rollback router.

File chính: [gateway](../backend/app/catalogue_gateway.py), [router/contract validator](../backend/app/services/fragment_router.py), [audit](../backend/scripts/verify_fragmentation.py), [scoped index planner](../backend/scripts/plan_scoped_indexes.py), [migration 008](../database/04_migrations/008_fragmentation_seller_index.sql), [runner nâng cấp](../deploy/scripts/apply-fragmentation.py).

## Bằng chứng kiểm thử

Lượt regression trên PostgreSQL 16 tách biệt, seed mới: **215 passed, 47 skipped**. Các test bỏ qua cần profile MinIO/ETL tích hợp riêng; không được tính là đã đạt. Có chạy integration PostgreSQL/Mongo cho index, migration, generation/snapshot/rollback và các test fragmentation mới.

Sau cùng chạy lại riêng fragmentation: **13 passed**. Cả **12/12 kiểm tra hai site** và rehearsal rollback router/phục hồi đều đạt trên stack local riêng. Ruff lint và format check toàn backend đạt; có chuẩn hóa import/format ở các file hiện hữu để vượt kiểm tra này, không đổi logic tương ứng.

- [Log regression](evidence/fragmentation_indexing/backend_tests.txt).
- [Log fragmentation riêng](evidence/fragmentation_indexing/fragmentation_tests.txt).
- [Integrity cấu trúc/tái tạo](evidence/fragmentation_indexing/integrity.json).
- [Scoped indexes](evidence/fragmentation_indexing/scoped_indexes.json).
- [HTTP và outage](evidence/fragmentation_indexing/api_results.json).
- [Kiểm chứng hai site và dựng mới](evidence/fragmentation_indexing/test_results.json).
- [Backup, restore và rollout local](evidence/fragmentation_indexing/rollout.json).
- [Rollback router và bật lại](evidence/fragmentation_indexing/router_rollback.json).

Audit live không có snapshot nguồn trước phân chia nên ghi `independent_reference_checked=false`. Lab có kiểm full-row với reference trong bộ nhớ, kiểm mất hàng/thiếu mảnh, nhưng không thay bằng chứng nguồn gốc của một dataset production. Kiểm schema, ghi sai site, orphan, ID đồng thời, rollback, user vertical split và partition pruning được kiểm riêng.

## Kết quả hiệu năng và quyết định index

Trong [benchmark giả lập](benchmark/fragmentation_indexing/README.md), index seller giảm p95 query mẫu từ **2,453 ms xuống 0,838 ms**, khoảng **65,8%**. Index category/price/image không đạt đầy đủ tiêu chí trong lần thử nên không phát hành. Mongo brand index chỉ giữ làm ứng viên dù có covered query hiệu quả, vì chưa chứng minh được workload và write cost thực tế.

Đây là thử nghiệm một máy, cache ấm, một client. Các update PostgreSQL được rollback và chưa đo commit/fsync; write overhead âm phản ánh nhiễu, không chứng minh ghi nhanh hơn. Chưa nghiệm thu ngưỡng hiệu năng production hoặc throughput đồng thời. Remote SQL xác nhận filter/projection được đẩy xuống B; sort vẫn có thể ở A.

## Phạm vi rollout thực tế

Đã dựng stack độc lập **`oldshop-fragmentation`**: PostgreSQL A/B tại port 56531/56532, gateway port **56580**, network `172.29.83.0/24`. Stack này được dùng để thử HTTP/outage, bootstrap lặp lại và clean rebuild, không dùng để chứng minh hai máy vật lý. Env riêng ở `deploy/backups/fragmentation_local_test.env`, chứa thông tin xác thực, không đưa vào Git.

Hai container local hiện hữu thuộc `oldshop-sites` đã nhận migration 008 và contract site 001; backup đã được phục hồi thử. Tuy nhiên FDW A đang trỏ **VPN `100.95.171.37:57432`** từ trước đợt này và endpoint đó không phản hồi trong quá trình kiểm tra. Cấu hình VPN được giữ nguyên; gateway hiện hữu chưa được recreate với router mới. Không coi container B local là bằng chứng remote B qua VPN đã nâng cấp. Chi tiết trong [trạng thái môi trường hiện hữu](evidence/fragmentation_indexing/existing_stack_status.json).

Commerce hiện hữu chưa áp migration 008; mã nguồn và migration đã sẵn sàng cho runner commerce trong cửa sổ bảo trì có backup/restore. Mongo ứng dụng không được thêm index brand hoặc đổi write concern. Các thay đổi planner áp dụng khi dùng bộ công cụ mã nguồn mới.

## Phần còn cần thực hiện ở môi trường đích

1. Khôi phục kết nối VPN, xác định đúng DB B từ xa, backup và nâng cấp tại đúng host B; kiểm contract/reference ở cả hai bên trước khi recreate gateway hiện hữu. Đặt DSN B/VPN/HBA theo [runbook](runbooks/fragmentation_indexing.md).
2. Áp migration 008 cho commerce theo runner hiện hữu nếu đưa release này vào commerce; kiểm desired/applied catalog riêng từng engine.
3. Thu workload, tỷ lệ đọc/ghi và concurrency thực tế; đo latency có commit/fsync và throughput, rồi chốt ngưỡng production.
4. Endpoint ghi tập trung tự định tuyến và chuyển owner xuyên site chưa được bổ sung. Ghi local vẫn được bảo vệ bằng FK/trigger; chuyển owner cần thiết kế điều phối/phục hồi riêng.

Các bước còn lại được giữ chưa đánh dấu trong kế hoạch. Không suy ra toàn bộ kế hoạch đã nghiệm thu chỉ từ test local đạt.
