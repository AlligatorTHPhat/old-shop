# Vận hành fragmentation-v1 và index-v2-fragmentation

Release ngày 10/11/2026. Chi tiết kết quả: [báo cáo triển khai](../KET_QUA_FRAGMENTATION_INDEXING.md).

## Hành vi mới

`GET /products/{id}` đọc sản phẩm và ảnh ở site sở hữu: ID lẻ ở A, chẵn ở B. Quy tắc cấp ID được kiểm với contract và database trước khi đọc. `GET /products?seller_id=...` tra `seller_site` tại A rồi đọc mảnh sở hữu; seller không có mapping trả 404. Danh sách toàn cục và `/ready` vẫn cần cả hai site; thiếu site, lệch contract hoặc reference trả 503. Filter thực hiện trước count/phân trang, sort có khóa phụ product_id.

`DISTRIBUTED_CATALOG_B_URL` cho phép detail B hoạt động khi A lỗi. Nếu bỏ biến này, gateway đọc B qua view FDW riêng ở A và vẫn phụ thuộc A. Truy vấn theo seller luôn cần A vì A là nguồn mapping có thẩm quyền. Hai DB độc lập không cung cấp snapshot nguyên tử toàn cục.

Contract `database/distributed/fragmentation.json` chỉ chứa metadata. `seller_site` quyết định owner; parity của ID không thay thế mapping seller. Gateway chỉ đọc; `site_writer` ghi local qua FK/constraint/trigger hiện có. Tiếp tục chặn đổi owner, ID và site; chưa hỗ trợ chuyển owner xuyên site.

Migration site `001_fragment_contract.sql` kiểm dữ liệu cũ, trigger, FK và sequence, rồi tạo các projection chỉ đọc và `v_fragment_identity`. View kiểm fingerprint constraint/trigger/function và checksum reference đã duyệt khi cài đặt. Sửa category/mapping hoặc tắt trigger sẽ làm site đó trả 503. Reference đang đóng băng theo release: muốn cập nhật phải có migration bảo trì mới cho cả hai bản, đối chiếu và duyệt lại checksum; không tự sửa bảng state để che drift.

## Nâng cấp hai site

Dừng các nguồn ghi vào A/B trước khi chạy; công cụ không dừng các client ngoài hệ thống. Chỉ tác động hai site catalogue, không tác động database commerce.

Runner này yêu cầu hai site local có địa chỉ riêng và FDW hiện tại hoạt động; từ chối cấu hình VPN. Nâng cấp nhiều máy cần backup và chạy `sites.py upgrade --site A`/`--site B` tại đúng máy tương ứng, rồi cập nhật view FDW sau khi cả hai bên đạt version yêu cầu. Không thay endpoint để vượt bước kiểm tra kết nối.

```bash
python deploy/scripts/sites.py plan-upgrade
python deploy/scripts/apply-fragmentation.py apply
python deploy/scripts/sites.py plan-upgrade
```

`apply-fragmentation.py` backup mỗi DB, thử restore vào DB tạm, đối chiếu count/digest tám bảng nguồn, áp migration, cập nhật manifest, cấu hình view FDW và recreate riêng catalogue. Chọn stack bằng `--env`/`--project`. Backup riêng tư ở `deploy/backups/fragmentation_<timestamp>/`, không đưa vào Git. Không bootstrap/reseed dữ liệu hiện có.

Mỗi site commit riêng. Nếu A thành công rồi B lỗi, giữ bảo trì, xem plan và chạy lại để hoàn tất B. Không sửa/xóa lịch sử migration. Các migration index mới phải có snapshot/header hợp lệ; nguồn cài đặt và checksum cũ phải khớp trước khi nâng cấp.

Migration 008 thêm index seller visible `(seller_id, created_at DESC, product_id ASC)`. Commerce dùng runner riêng `cd backend && python -m scripts.migrate`, sau backup/restore theo [runbook index](indexing_v2.md). Công cụ site không nâng cấp commerce.

Hai máy vật lý: cấu hình `SITE_B_CATALOG_HOST` bằng IP VPN B, `SITE_B_CATALOG_PORT` bằng cổng publish B, cho phép IP gateway trong HBA B. Không dùng hostname Docker `pg-b` giữa hai network độc lập.

## Kiểm tra và benchmark

Trong `backend/`, đặt `FRAGMENT_SITE_A_DSN`, `FRAGMENT_SITE_B_DSN` bằng biến môi trường rồi chạy:

```bash
python -m scripts.plan_scoped_indexes --scope site-a --scope site-b --verify
python -m scripts.verify_fragmentation --output ../docs/evidence/fragmentation_indexing/integrity.json
```

Scope commerce dùng `--scope commerce` và `FRAGMENT_COMMERCE_DSN`. Plan/verify chỉ đọc, báo kết quả riêng từng scope; DDL vẫn qua runner. Audit cần quyền đọc bảng nguồn/user fragments; không cấp quyền này cho gateway. Báo cáo chỉ xuất kết quả/digest, không xuất secret.

`verify_fragmentation --reference source.json` đối chiếu JSON dạng `{"product": [...], "product_image": [...]}` với đầy đủ hàng/cột từ nguồn trước khi chia. Không có reference độc lập thì chỉ chứng minh integrity cấu trúc và tái tạo từ mảnh, chưa chứng minh dữ liệu ban đầu không bị mất. Chạy đối soát trong cửa sổ ngừng ghi.

Planner kiểm duplicate trước unique build; Mongo phân biệt missing/null/sparse/partial, multikey chưa hỗ trợ preflight phải review tường minh. Không tự sửa/xóa dữ liệu. Unique build vẫn là lớp bảo đảm cuối cùng khi có ghi đồng thời sau preflight.

```bash
# PostgreSQL lab riêng, trust auth và quyền tạo DB/role; Mongo lab riêng.
# DSN lab được đặt qua FRAGMENT_TEST_PG_DSN / FRAGMENT_TEST_MONGO_URI.
cd backend
pytest --noconftest -o addopts='' tests/test_fragmentation.py tests/test_index_config.py
python -m scripts.benchmark_fragmentation --output /tmp/fragment-benchmark-new --samples 30 --rows 20000
```

Lab tạo DB/role UUID và dọn khi kết thúc; DSN chỉ dùng để tạo DB mới, không dùng làm nơi chạy thử DDL. Khi kill cứng có thể còn DB tạm: kiểm đúng prefix/ID trước khi dọn. Xem [giới hạn benchmark](../benchmark/fragmentation_indexing/README.md).

## Rollback

```bash
python deploy/scripts/apply-fragmentation.py rollback-routing
```

Lệnh recreate gateway với `DISTRIBUTED_CATALOG_ROUTING=0`, quay về global view và kiểm cả hai site như trước. Muốn giữ chế độ này qua lần recreate sau, đặt 0 trong env của stack; đặt lại 1 để bật router. Các view bổ sung có thể giữ nguyên.

Nếu cần bỏ index seller, tạo migration bù phiên bản tiếp theo cùng catalog/snapshot/release, kiểm dependency trước `DROP INDEX public.idx_product_visible_seller_date_id`. Không đặt sẵn migration bù trong thư mục tự áp. Rollback application image không tự rollback schema; restore backup chỉ khi cần phục hồi dữ liệu và đã dừng nguồn ghi.
