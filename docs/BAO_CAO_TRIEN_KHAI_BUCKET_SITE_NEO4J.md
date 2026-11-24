# Kết quả triển khai bucket/site, seeding và Neo4j

Ngày kiểm chứng: **17/11/2026**. Đã triển khai luồng mới theo opt-in `BUCKET_MODE=true`, chạy trên project Docker **oldshop-buckets** riêng. Không xóa database/volume cũ, không đổi traffic của các stack `oldshop-data`, `oldshop-sites`, `oldshop-fragmentation`, `oldshop-vm-demo`.

Hướng dẫn và lệnh thực tế: [runbook](runbooks/bucket_site_neo4j.md). Thiết kế gốc: [kế hoạch](KE_HOACH_TAI_CAU_TRUC_SEEDING_BUCKET_SITE_NEO4J.md).

## Quyết định đã đóng băng

- Contract `bucket-v2`, 256 bucket, SHA256 của `oldshop:seller:v1:{seller_id}`, lấy 8 byte đầu unsigned big endian rồi modulo 256. Digest `8c9281e20cc6d111d9ca58fde66afd77cfa7526bc01360e1c45754bce6df37be`.
- Mapping ban đầu 0–127 → A, 128–255 → B. Seller không tạo site riêng; registry nhận thêm C và các server khác. Epoch/lease fencing bảo vệ writer trong lúc chuyển bucket.
- Product/image/order/review dùng global integer ID; core cấp range, directory định tuyến product. FK cart/order detail/review tham chiếu directory thay product local ở core.
- SQL giữ image membership và tồn kho; MongoDB giữ caption/description/attributes/tags và metadata revision; Neo4j là projection có thể dựng lại. Không train AI, không dùng embedding hoặc nhận diện pixel.
- Runtime đã chạy: PostgreSQL 16, MongoDB 8.0.32, Neo4j Community **2026.10.2**, Python driver **6.4.0**, Cypher 5. Driver được thêm vào cả requirements và hai hash lockfile.

## Những phần đã thực hiện

| Chặng | Kết quả thực tế |
|---|---|
| P0 | Contract, vectors, authority, ID policy, phiên bản và môi trường đích riêng |
| P1 | Shared allocator, registry/directory, lease/epoch guards, routing API chính và gateway |
| P2 | Bootstrap schema riêng; deterministic generator/validator; plan/apply/resume/manifest/verify; bảo vệ drift và user metadata |
| P3 | Product/image/moderation/cart/order/payment/review, dashboard và báo cáo dùng catalogue phân tán; stock operation ledger, saga phục hồi và fulfillment theo seller |
| P4 | Neo4j schema/index/checksum migration, backfill/reconcile, ACK Mongo/graph riêng, retry/dead letter, Mongo pending revision, rebuild generation |
| P5 | Tìm đúng từng ảnh theo caption/description; AND token, không dấu; SQL/Mongo revalidation; cursor; UI tìm ảnh và sửa metadata; related products bằng Cypher |
| P6 | Import hợp lệ giữ ID/metadata và không sửa nguồn; chuyển bucket sang C/quay lại; backup–restore SQL/Mongo/media; mẫu thời gian HTTP local. Chưa cutover legacy |

Mã chính: [allocation](../backend/app/services/allocation.py), [repositories/API/projection](../backend/app/buckets/), [seeding](../backend/seeding/), [công cụ](../backend/scripts/), [SQL migrations](../database/distributed/bucket/), [graph schema](../database/neo4j/), [compose](../deploy/docker-compose.bucket.yml).

`BUCKET_MODE=false` giữ đường legacy. Các gateway cũ đang chạy không bị đổi cấu hình. `app.catalogue_gateway` chuyển sang adapter bucket khi bật flag; đọc đúng product tại C sau move và tiếp tục chỉ cung cấp API đọc.

## Dataset và evidence

Seed `demo-v2` đã hoàn tất, run ID `96b9accd-2549-402b-aacf-5411b7894078`, dataset hash `317901cdd82e003a99b8e136928f863e5505f67a19166abe1bc2ad91223fecf4`:

| Entity | Số lượng seed |
|---|---:|
| User | 40 |
| Product | 1.000 |
| Image | 2.000 |
| Order | 120 |
| Order detail | 240 |
| Review | 56 |

Manifest seed ghi 294 product ở A, 706 ở B. Đây là kết quả hash của 24 seller, không phải lỗi phân mảnh: 128 bucket mỗi bên không bảo đảm số product bằng nhau. Điều chỉnh tải bằng move bucket sau khi đo. C được đăng ký và dùng cho rehearsal, sau đó bucket được chuyển về A. Các fixture kiểm thử làm tổng product hệ thống lớn hơn 1.000; verifier kiểm riêng các ID seed và toàn bộ reconstruction.

Ảnh được dùng lại từ asset repository với checksum và mô tả trung tính có căn cứ. Query `alphaonly` chỉ xuất hiện trong description một ảnh; API trả đúng image ID `100008`, không trả toàn bộ ảnh của product. Metadata mới do người dùng sửa được bảo vệ khi SQL ETL và seed chạy lại.

Evidence được lưu tại [runtime.json](evidence/bucket_site_neo4j/runtime.json), [backup-restore.json](evidence/bucket_site_neo4j/backup-restore.json), [validation.json](evidence/bucket_site_neo4j/validation.json). Bản dump/BSON/binary media nằm trong `deploy/backups/buckets/` bị git ignore, không đưa dữ liệu nguồn vào git. Các JSON evidence chỉ chứa count/hash/ID vận hành và thời gian tổng hợp, không chứa credential hay nội dung user secret.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Bucket integration trên SQL A/B/C + Mongo + Neo4j | **18 passed**, lần cuối 51,61 giây |
| Legacy regression trên database mới, flag tắt | **218 passed**, **78 skipped** do profile/điều kiện không bật |
| Frontend | **33 passed**, 15 test files |
| Build production frontend và Docker images | Thành công; initial bundle 714,02 kB, còn warning budget 500 kB |
| Ruff phần code thêm/sửa liên quan | Đạt |
| Seed từ database trống → lỗi projection → resume → replay | Đạt; giữ ID/count và caption người dùng |
| Lost ACK stock, lỗi site thứ hai, compensation, retry | Đạt; không trừ tồn hai lần, không bán vượt tồn |
| PayPal | Fake provider hoàn toàn; retry cùng request key, chặn sai buyer/sai amount, hủy khi capture chưa đối soát bị chặn |
| Mongo revision cũ/mới, xóa ảnh, graph generation khác | Đạt; không ACK nhầm revision, không trả ảnh đã xóa hoặc product chưa công khai |
| Move A → C → A | Đạt; giữ ID/API, operation replay không giữ hàng hai lần, ghi mới sau cutover được mang về, epoch cũ bị từ chối |
| Import legacy hợp lệ | Đạt; giữ product/image ID và caption/description, chạy lại không nhân đôi, hash nguồn giữ nguyên |
| Restore core/A/B/C, Mongo validator/index/BSON và media | Đạt; hash/count SQL/Mongo và checksum media khớp |
| Graph rebuild generation 2 | Đạt; namespace cũ được giữ, generation 2 active |
| `benchmark-v2 --scale 2` | Generator/validator đạt với 2.000 product, 4.000 image, 240 order; chưa nạp để đo tải production |

Runtime evidence đo 10 request tuần tự mỗi endpoint trên máy local. Kết quả có ảnh hưởng của cache, worker và các stack khác cùng máy; không suy ra throughput hoặc SLA production từ các mẫu này.

## Giới hạn và việc cần làm trước cutover

1. Nguồn cũ được đọc kiểm tra có 1.001 product, **30 contact–buyer mismatch**, **5 transaction status ngoài 0–3**, không có self-buy line. Importer từ chối các vi phạm; chưa tự sửa, xóa hoặc nhập nguồn này vào target demo. Cần quyết định nghiệp vụ cho từng dòng trước migration thực.
2. Đơn lịch sử không có reservation đáng tin cậy cần reconciliation tồn kho trước khi cho hủy. Các đơn do seeder mới sinh có reservation trạng thái tương ứng và không bị trừ tồn lần hai.
3. Đây là topology lab trên một máy, chưa HA/control-plane replication hoặc tự động cân bằng/move bucket. Runtime database credential trong compose là tài khoản quản trị lab; deployment production cần tách quyền migration và quyền ứng dụng.
4. Backfill hiện đọc theo entity trong một process, chưa có chunk checkpoint cho hàng triệu dòng. Gateway exact count giới hạn 100.000; cần thu hẹp filter khi vượt. Chưa chạy benchmark tải đồng thời hoặc tối ưu mọi truy vấn.
5. Graph có eventual consistency: kết quả mới có thể trễ, cursor không phải snapshot giao dịch. Graph outage trả 503 cho tính năng graph, không dùng bản chiếu để quyết định tồn kho. Chưa có job dọn generation/retained shadow tự động.
6. Dataset demo là baseline đã đóng băng. Các scenario bổ sung như voucher/report và seller lệch tải lớn hơn cần dataset version riêng hoặc fixture kiểm thử riêng; không sửa âm thầm content hash của dataset đã nạp.
7. Các test/database restore được giữ riêng để điều tra, có prefix `bucket_*`; runbook không chứa thao tác tự xóa chúng. Chưa thay endpoint/frontend đang dùng của môi trường cũ.

Ứng dụng local mới: **http://localhost:57600**, Swagger: **http://localhost:57680/api/docs**. Tài khoản demo và cách khởi động lại nằm trong runbook.
