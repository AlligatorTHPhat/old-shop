# Kết quả thực hiện indexing v2 — 01/11/2026

Đã hoàn tất mã và kiểm chứng trên stack riêng. **Chưa áp vào DB người dùng** theo lựa chọn
của người dùng. [Hướng dẫn tự áp dụng/tái lập](../README.md),
[migration 007](../../../../database/04_migrations/007_indexing_v2.sql).

## Môi trường và phương pháp

PostgreSQL 16.15 Alpine, MongoDB 8.0.32, Python 3.13.18. Docker có 8 CPU/~7,50 GiB RAM;
PG bị giới hạn 1 CPU/512 MiB, runner 768 MiB theo Compose. Dùng schema thật 001–006,
trigger/constraint thật, không ép enable_seqscan. File [pg/environment.json](pg/environment.json)
ghi version, collation và số dòng ước tính; số dòng trên parent partition bằng 0 trong
pg_class không có nghĩa bảng logic rỗng. [workload.md](workload.md) ghi phạm vi các query.

[inventory_tables.json](inventory_tables.json) xác nhận 28 bảng logic/222 cột.
Tải L: 51.000 product, 202.000 ảnh, 100.030 order, 100.030 detail, 100.000 review,
100.000 log, 50.015 user/role, 20.000 run, 200.000 event và 200.000 cleanup. Event có
190k done và 10k pending/dead; available_at năm 2020/2100 giúp case due/deferred ổn định.
Mongo có 50.000 document synthetic, validator strict, shared/unique/missing image và brand/RAM.
Đây là fixture tải ngoài seed mặc định; không tăng dữ liệu seeding ứng dụng.

Đọc: 1 warmup + 5 EXPLAIN ANALYZE/BUFFERS; bảng ghi **median server execution ms**,
không phải latency HTTP. Có mọi sample/plan JSON và fingerprint kết quả. Ghi: 100 sample
sau warmup, EXPLAIN ANALYZE/BUFFERS/WAL, rollback từng sample. Mongo ghi đo client
wall-clock một writer, 100 lần cập nhật. Cache, CFS quota, page split, trigger/outbox,
sequence và rollback bloat ảnh hưởng số liệu; không suy ra SLA hoặc throughput đa luồng.

## Quyết định đủ 16 ứng viên

Đo riêng từng ứng viên, bỏ sau mỗi trial. Cột bytes là **chỉ index mới và children**;
không lấy chênh tổng dung lượng giữa hai trial vì rollback DML vẫn làm index cũ phình.
[pg/summary.json](pg/summary.json) giữ cả delta tổng với nhãn có trial bloat để đối chiếu.

| Mã | Quyết định | Query đại diện | Trước → sau (ms) | Index mới (bytes) | Lý do |
|---|---|---|---:|---:|---|
| I01 | Hoãn | Q01_category | 0.207 → 0.158 | 1,736,704 | Catalogue theo category đã có index; cần tần suất và thống kê usage trước khi thêm index chồng lặp. |
| I02 | Chọn | Q02_all | 1.086 → 0.213 | 1,343,488 | Tạo thứ tự thời gian toàn bộ category và đúng product_id ASC khi trùng ngày; SQL ORM thực dùng index. |
| I03 | Hoãn | Q02_price | 0.374 → 0.275 | 1,343,488 | Lọc category+giá cải thiện nhưng query đang dưới 1 ms; chưa có bằng chứng tần suất để trả thêm chi phí ghi. |
| I04 | Chọn | Q15_image_missing | 52.626 → 0.069 | 9,953,280 | Tra URL thiếu/duy nhất từ quét 202k ảnh xuống lookup; nonunique để giữ ảnh dùng chung. |
| I05 | Chọn | Q15_avatar_missing | 20.257 → 0.066 | 2,473,984 | Cleanup avatar thiếu/duy nhất tránh quét toàn bộ user_profile; nonunique. |
| I06 | Hoãn | Q05_images | 0.123 → 0.713 | 6,389,760 | Mỗi product chỉ khoảng 4 ảnh, sort nhỏ; index thử nghiệm chậm hơn baseline và tốn hơn 6 MB. |
| I07 | Chọn | Q17_voucher | 29.109 → 10.568 | 770,048 | Voucher fan-out phải gồm cả order xóa mềm; full index trên parent và 4 HASH children. |
| I08 | Chọn | Q14_status | 21.227 → 0.157 | 475,136 | CLI status luôn đọc run mới nhất; tránh sort toàn bộ 20k run. |
| I09 | Chọn | Q14_aggregate | 14.251 → 0.091 | 139,264 | Dashboard lấy aggregate thành công gần nhất, partial predicate đúng query. |
| I10 | Chọn | Q13_retry | 182.075 → 0.112 | 835,584 | Retry tìm entity_key JSONB bằng equality toàn bộ; index B-tree phù hợp, không cần GIN. |
| I11 | Chọn | Q12_poll | 187.461 → 0.476 | 376,832 | Giảm quét event done, khớp ORDER BY event_id; giữ clock_timestamp và index available_at cũ. |
| I12 | Chọn | role_lookup | 9.191 → 0.247 | 1,138,688 | Danh sách thành viên theo role cần role_id đứng đầu; PK user-first giữ nguyên. |
| I13 | Hoãn | token_lookup | 9.988 → 0.076 | 65,536 | Lookup token cải thiện rõ nhưng đường token cũ chưa chứng minh là workload hiện hành; không thêm UNIQUE cho OTP. |
| I14 | Hoãn | Q16_audit | 39.819 → 0.870 | 4,292,608 | Audit resource cải thiện rõ nhưng chưa thấy hot path ứng dụng; cần cân đối dung lượng theo số partition. |
| M01 | Chọn | live images.key missing/unique/shared | 50k/49.999/10 docs → 0/1/1 docs examined | 745,472 | Nonunique multikey, partial deleted=false; cleanup vẫn bảo vệ ảnh dùng chung. |
| M02 | Hoãn | brand+RAM | 7 → 3 ms; 1.000 → 0 docs examined | 671,744 | Có lợi cho mẫu synthetic, nhưng thuộc tính động chưa có tần suất thực tế; update metadata tăng chi phí. |

M02 trả cùng 323 IDs, sau index là covered scan 323 keys. Không chọn mặc định một cặp
brand/RAM cho mọi ngành hàng. M01 missing/unique trước 128/125 ms, sau 0 ms ở độ phân
giải nguyên millisecond của Mongo; **0 ms không nghĩa không tốn thời gian**.
Xem [mongo/summary.json](mongo/summary.json) và raw executionStats.

[Đối chiếu inventory trước/sau](selected/index_retention.json) xác nhận giữ nguyên toàn bộ 174 index relation cũ, chỉ thêm 13 relation của 007.
Không bỏ index cũ: chưa có chu kỳ pg_stat_user_indexes của hệ thống người dùng. Giữ các
GIN trigram/title, UNIQUE/PK, buyer/date, cart và report_date PK. MinIO không thêm cấu
trúc index riêng, URL/object key và bytes ảnh giữ nguyên. Nhánh tự lập trình Hash/B+ tree
ở mục 14 của kế hoạch là tùy chọn học tập, chưa triển khai trong backend giao dịch.

## Kết quả khi áp cả gói 007

Lần đo cả gói dùng cùng DB fixture, VACUUM ANALYZE trước/sau, gồm cả query không nhận
index mới. [selected/summary.json](selected/summary.json) có 36 kết quả bằng fingerprint,
100 product IDs từ ORM giống nhau, source digest không đổi, replay migration là no-op.

| Query | Trước → sau (ms) | Shared hit blocks trước → sau |
|---|---:|---:|
| Q02_all | 1.100 → 0.202 | 152 → 38 |
| Q15_image_missing | 48.072 → 0.090 | 2720 → 3 |
| Q15_avatar_missing | 13.294 → 0.100 | 518 → 3 |
| Q17_voucher | 23.828 → 10.358 | 1044 → 1054 |
| Q17_voucher_missing | 17.245 → 0.156 | 1044 → 8 |
| Q14_status | 16.342 → 0.090 | 326 → 3 |
| Q14_aggregate | 14.086 → 0.152 | 326 → 3 |
| Q13_retry | 180.022 → 0.086 | 4366 → 2 |
| Q12_poll | 141.257 → 0.561 | 4601 → 216 |
| role_lookup | 8.165 → 0.358 | 222 → 5 |

Catalogue qua CRUDProduct.catalogue (SQL ORM thật, joinedload ảnh): 3.482 → 2.820 ms tổng EXPLAIN của các SELECT được capture; đây là một plan mỗi phía, không phải median/p95 HTTP. Index I02 được dùng.

Postflight xác nhận 9 index logical, gồm 13 relation index (voucher parent + 4 children), tổng physical size 17,530,880 bytes (~16.72 MiB). Đây là ảnh chụp sau trial; kích thước khác từng candidate do ghi/rollback và page split.

Voucher phổ biến vẫn phải đọc nhiều heap page (hits tăng 1.044 → 1.054 dù thời gian giảm),
không hứa tiết kiệm IO cho mọi độ chọn lọc. Missing voucher cho thấy bỏ quét 100k order.

## Chi phí ghi và đánh đổi

| Ghi | Median trước → sau (ms) | p95 trước → sau (ms) | WAL bytes median trước → sau |
|---|---:|---:|---:|
| view_count | 2.625 → 2.433 | 4.465 → 3.550 | 1066 → 1066 |
| reserve | 3.181 → 2.726 | 6.533 → 4.140 | 1074 → 1074 |
| moderate | 2.692 → 2.455 | 3.589 → 3.621 | 1082 → 1082 |
| description | 2.444 → 2.426 | 3.531 → 3.534 | 1074 → 1074 |
| image_insert | 0.730 → 0.802 | 1.526 → 1.286 | 247 → 335 |
| avatar | 0.351 → 0.240 | 0.486 → 0.447 | 246 → 334 |
| run_insert | 0.220 → 0.182 | 0.427 → 0.435 | 5017 → 272 |
| event_ack | 0.296 → 0.269 | 0.463 → 0.455 | 324 → 150 |
| order_insert | 1.573 → 1.496 | 2.411 → 2.440 | 434 → 498 |
| role_insert | 0.198 → 0.183 | 0.371 → 0.368 | 127 → 191 |

Image insert tăng median khoảng 9,8% (+0,072 ms), WAL 247 → 335 bytes, đổi lấy lookup
URL thiếu 48 ms → 0,09 ms. Role insert/order insert/avatar có thêm WAL cho index mới.
Các giảm thời gian/WAL ở run/event không chứng minh index làm ghi rẻ hơn: page state,
full-page images và rollback trial khác nhau. Các dòng view_count/reserve/description ở bảng trên dùng product pending; riêng moderate
dùng product approved. Bảng bổ sung dưới đây đo chi phí trên approved và lifecycle ETL.
Chưa đo throughput ghi đồng thời; không tuyên bố đạt ngân sách 10%
cho mọi tải thực. Các case >10% ở từng trial cần xem cả bảng riêng và nhiễu môi trường;
quyết định cuối dựa phép đo cả gói, lợi ích đường đọc và theo dõi sau rollout.

### Bổ sung: sản phẩm approved và lifecycle ETL

[approved_writes/summary.json](approved_writes/summary.json) đo trên clone riêng của DB L
sau 007, bỏ/tạo lại đúng 9 index **chỉ trong clone**, không sửa lịch sử migration hoặc DB
nguồn. Đo thứ tự A–B–B–A (trước–sau–sau–trước), 100 mẫu/stage, gộp 200 mẫu/cấu hình.
Clone được xóa sau phép đo; digest các dòng thử và lịch sử không đổi. Product 1000043 có
status=1, is_deleted=false để mô tả đi qua GIN và partial index. Run finish đi từ partial
sang success+aggregate; event retry cập nhật available_at và attempts.

| Ghi bổ sung | Median trước → sau (ms) | p95 trước → sau (ms) | WAL bytes median trước → sau |
|---|---:|---:|---:|
| view_count_approved | 2.321 → 2.250 | 3.626 → 4.023 | 2688 → 2758 |
| reserve_approved | 2.433 → 2.387 | 4.047 → 4.230 | 2696 → 2768 |
| description_approved | 2.301 → 2.148 | 3.493 → 3.786 | 2840 → 2912 |
| run_finish | 0.140 → 0.167 | 0.262 → 0.276 | 329 → 457 |
| event_retry | 0.246 → 0.334 | 0.461 → 0.538 | 231 → 572 |

Có đánh đổi vượt ngưỡng rà soát 10%: p95 view_count tăng ~11% (+0,397 ms), median run
finish tăng ~19% (+0,027 ms), event retry tăng ~36% (+0,088 ms), WAL retry 231 → 572 bytes.
Giữ gói 007 vì catalogue/đọc run/claim queue giảm chi phí rõ, nhưng cần theo
dõi counter update và retry ở tải thật. Đây là **chấp nhận đánh đổi có ghi nhận**, không
phải bằng chứng mọi phép ghi đạt ngân sách 10%. Giữ index available_at cũ đến khi có usage.

Lần [pilot 100 mẫu/cấu hình](approved_writes_pilot/summary.json) từng cho description
approved tăng median 1,897 → 2,805 ms (~48%). Lần đo đảo thứ tự cho 2,301 → 2,148 ms,
p95 3,493 → 3,786 ms. Sự khác nhau cho thấy nhiễu/thứ tự/cache ảnh hưởng mạnh; không lấy
median giảm để kết luận index làm ghi nhanh hơn. Chi phí WAL tăng khoảng 70–72 bytes ở
các cập nhật product approved là dấu hiệu ổn định hơn giữa các lần. Cần phép tải đồng
thời dài hơn trên môi trường vận hành trước khi đặt SLA.

Mongo M01 image update: median 4,098 → 4,191 ms, p95 5,247 → 5,805 ms (~10,6% p95,
+0,558 ms); chấp nhận đánh đổi cho cleanup khỏi quét 50k docs, cần theo dõi thực tế.
M02 attribute update: median 4,178 → 5,718 ms, p95 5,368 → 8,073 ms; đây là thêm lý do
hoãn ngoài việc thiếu workload thuộc tính thực. Không so trực tiếp ms Mongo với ms PG.

## Hàng đợi và giới hạn

Matrix mixed/old_deferred/all_deferred thử cả clock_timestamp và statement_timestamp,
5 mẫu mỗi case, index cũ so với I11. Với clock_timestamp, median mixed 150,823 → 0,515 ms;
old_deferred 138,034 → 5,958 ms; all_deferred 148,630 → 5,842 ms. Index event_id giảm
quét done nhưng vẫn có thể phải kiểm mọi pending chưa due. Đổi sang statement_timestamp
cho thấy lợi ích trong thử nghiệm, nhưng thay ý nghĩa thời gian trong một statement;
**không đổi code worker** chỉ để đạt plan đẹp. Giữ index available_at cũ.

Kiểm SKIP LOCKED bằng hai connection, loại done/future, chỉ claim pending/dead đã due.
Không khẳng định end-to-end ETL dưới 5 phút cho mọi backlog từ phép đo SELECT này;
regression ETL/API dùng PG/Mongo/MinIO thật xác nhận đúng luồng, còn SLA cần tải vận hành.
Cleanup media_deletions cũng được đo clock/stable; không thêm index pending thứ hai khi
chưa có bằng chứng đánh đổi tốt hơn trên workload thực.

## Kiểm chứng chức năng và hồ sơ

**147 kiểm thử đạt:** 97 regression, 28 ETL, 22 API tích hợp; không có ca bị skip.
Test upgrade được chạy lại riêng và đạt thêm một lần sau khi hoàn thiện verifier.

- [tests_summary.json](tests_summary.json): tổng hợp 147 kiểm thử đạt.
- [tests_regression.txt](tests_regression.txt): API/CRUD/schema/partition/rollback và upgrade 006 → 007.
- [tests_etl.txt](tests_etl.txt): incremental/full/aggregate/retry/reconcile, PG → Mongo/MinIO thật.
- [tests_api.txt](tests_api.txt): hybrid product/search/report/shared-image cleanup thật.
- [postflight.json](postflight.json): checksum/definition/key order/predicate/validity/partition/M01.
- [restore_rehearsal.json](restore_rehearsal.json): backup custom-format, restore riêng, source digest và index đúng.
- [cleanup.json](cleanup.json): stack riêng đã được dọn; Mongo/MinIO đang dùng giữ nguyên.
- [manifest.json](manifest.json): hash nguồn/001–007, kiểm lịch sử 001–006 giữ nguyên so HEAD.
- [lint.txt](lint.txt), [lint_deploy.txt](lint_deploy.txt): Ruff và bash -n.
- [tests_upgrade_final.txt](tests_upgrade_final.txt): chạy lại upgrade với verifier đã hoàn thiện.

Upgrade test so toàn bộ dòng/cột của bảng nguồn và constraints (không chỉ v0 projection),
ảnh dùng chung, OTP trùng hợp lệ, replay no-op và queue concurrency. Những thay đổi test cũ
chỉ sửa tháng log hardcode và giả định danh sách pending nằm hết trang đầu. Dữ liệu trong
file plan là fixture synthetic, không trích xuất dữ liệu người dùng.

Script bảo trì mới được kiểm cú pháp và các thao tác dump/restore trên stack riêng;
chưa chạy trọn rollout trên DB người dùng. Backup Mongo/media dùng cơ chế archive hiện
có, được script gọi trước reconcile vì reconcile có thể sweep/cleanup theo nghiệp vụ.

Sau khi tự áp, chạy postflight/reconcile theo [runbook](../README.md), quan sát thực tế
trước khi xem xét DROP index cũ hoặc bổ sung các ứng viên đã hoãn.
