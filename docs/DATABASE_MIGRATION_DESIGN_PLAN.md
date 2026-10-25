# OldShop — Database Migration Strategy & Design Plan
## Kế hoạch thiết kế, kiểm thử, áp dụng và khôi phục thay đổi cơ sở dữ liệu

> **Trạng thái:** `DESIGN PLAN — NOT YET APPROVED FOR PRODUCTION`  
> **Phạm vi:** Thiết kế quy trình migration cho PostgreSQL theo nguyên tắc SQL-first; xác định cách phối hợp khi bổ sung MongoDB và MinIO.  
> **Lưu ý:** Đây là kế hoạch cần được hoàn thiện sau Gate B–H. Tài liệu chưa khẳng định đã có migration runner, version table hoặc migration script trong repository.

---

## 1. Mục tiêu

Thiết lập quy trình thay đổi database có kiểm soát để tránh tình trạng code mới chạy trên schema cũ, mất dữ liệu, hoặc các store không đồng bộ.

Kế hoạch phải đáp ứng:

1. SQL trong `database/` tiếp tục là source of truth cho PostgreSQL.
2. Phân biệt bootstrap database mới với migration database đã tồn tại.
3. Mỗi migration có mã định danh/version, mục đích, precondition, thao tác, postcondition và bằng chứng kiểm tra.
4. Có backup/restore và rollback hoặc forward-fix strategy.
5. Migration được thử trên database test có cấu trúc và dữ liệu đại diện trước khi áp dụng môi trường có dữ liệu cần bảo toàn.
6. Thay đổi cross-store không giả định rằng PostgreSQL, MongoDB và MinIO cùng tham gia một transaction ACID.
7. Có thể xác định chính xác migration nào đã được áp dụng.

---

## 2. Baseline hiện tại và giới hạn đã biết

Theo `PROJECT_GUIDE.md` và kết quả Gate A được cung cấp:

- PostgreSQL 16 là database quan hệ hiện tại.
- Schema, function/trigger và seed được quản lý theo SQL-first trong `database/`.
- `backend/scripts/init_db.py` là bootstrap; nếu schema đã tồn tại, script bỏ qua `init.sql`.
- Docker entrypoint gọi bootstrap nhưng không tự cập nhật schema hiện hữu như migration system.
- Backend integration tests dùng PostgreSQL thật với schema/seed.
- MongoDB và MinIO là các thành phần mục tiêu cần thiết kế; chưa được coi là đã tích hợp.

**Hệ quả:** Không sửa `database/01_schema/*.sql` rồi chỉ restart container với giả định database đang tồn tại đã được cập nhật. Không chạy lại toàn bộ `init.sql` trên database có dữ liệu người dùng nếu chưa xác minh tác động.

---

## 3. Phạm vi migration

### 3.1 PostgreSQL — phạm vi chính

Migration có thể bao gồm:

- Tạo/sửa bảng và cột.
- Thay đổi PK, FK, UNIQUE, CHECK, DEFAULT, nullability.
- Tạo/sửa/xóa index.
- Thay đổi function, procedure, trigger.
- Thay đổi enum hoặc bảng danh mục/trạng thái.
- Bổ sung metadata/reference cho object MinIO.
- Bổ sung cột hoặc bảng phục vụ tích hợp MongoDB khi thiết kế chứng minh cần thiết.
- Data migration/backfill, chuyển đổi hoặc chuẩn hóa dữ liệu.
- Cập nhật quyền/schema/config cần thiết.

### 3.2 MongoDB — migration riêng cho document schema

Khi Gate H–I chốt MongoDB, cần quy định cách version hóa document, validator, index và backfill. Không giả định migration PostgreSQL tự áp dụng được lên MongoDB.

### 3.3 MinIO — object/data migration riêng

Khi Gate G chốt MinIO, cần quy định bucket, object key, metadata, kiểm tra checksum, cập nhật PostgreSQL reference, xử lý object thiếu/thừa và cách quay lại nguồn media cũ nếu cần.

### 3.4 Cross-store coordination

Không có transaction ACID chung mặc định giữa PostgreSQL, MongoDB và MinIO. Vì vậy quy trình tích hợp phải sử dụng các bước có thể kiểm tra, retry và reconcile; ví dụ: tạo object → xác minh object → ghi/cập nhật reference trong PostgreSQL → xác minh qua API. Chi tiết phải được chốt ở các Gate thiết kế.

---

## 4. Các nguyên tắc bắt buộc

### P-01 — SQL-first

Thay đổi PostgreSQL bắt đầu từ SQL có kiểm soát trong repository. Sau đó đồng bộ ORM, Pydantic schema, CRUD, API, frontend nếu có và test.

### P-02 — Bootstrap không phải migration

`init_db.py` chỉ phục vụ bootstrap theo hành vi đã ghi nhận. Không dùng việc restart container làm cơ chế cập nhật schema.

### P-03 — Migration nhỏ, có mục đích rõ

Mỗi migration nên xử lý một thay đổi logic có thể review độc lập. Tránh một script lớn chứa nhiều thay đổi không liên quan và khó xác định lỗi.

### P-04 — Không sửa lịch sử migration đã áp dụng

Nếu một migration đã được áp dụng ở môi trường dùng chung, không âm thầm chỉnh sửa nội dung migration đó. Tạo migration mới để sửa tiếp, trừ khi quy trình phát triển xác nhận migration chưa được phát hành và chưa được áp dụng ở bất kỳ môi trường nào cần bảo toàn.

### P-05 — Idempotency có chủ đích

Chỉ dùng `IF EXISTS`/`IF NOT EXISTS` hoặc logic idempotent khi hành vi đó an toàn và có kiểm tra trạng thái. Không che giấu schema drift bằng cách bỏ qua mọi lỗi.

### P-06 — Dữ liệu quan trọng phải được bảo toàn

Không drop/rename cột hoặc thay đổi kiểu dữ liệu phá hủy trước khi xác định data mapping, backfill, code compatibility và recovery path.

### P-07 — Verify trước khi đánh dấu thành công

Migration chỉ được đánh dấu thành công sau khi SQL chạy hoàn tất và các postcondition được kiểm tra.

### P-08 — Migration production cần phê duyệt

Không tự động áp dụng migration có nguy cơ khóa bảng lâu, rewrite dữ liệu lớn, thay đổi constraint nghiêm ngặt hoặc xóa dữ liệu nếu chưa có review, backup và kế hoạch khôi phục.

---

## 5. Đề xuất cấu trúc repository

Cấu trúc dưới đây là **đề xuất thiết kế**, chưa phải cấu trúc đã được xác minh tồn tại. Cần đối chiếu với repository sau Gate B trước khi tạo file:

```text
database/
├── init.sql
├── config/
├── 01_schema/
├── 02_functions/
├── 03_seeds/
└── migrations/                 # Đề xuất bổ sung
    ├── README.md
    ├── 0001__migration_metadata.sql
    ├── 0002__example_change.sql
    └── ...
```

Có thể dùng một runner migration hiện có hoặc viết runner nhỏ phù hợp với stack, nhưng phải chốt rõ sau khi kiểm tra dependencies, CI và cách triển khai. Không nên chọn công cụ chỉ vì phổ biến nếu nó làm lệch quy ước SQL-first hoặc không hỗ trợ tốt SQL/PL/pgSQL hiện tại.

### Quy tắc đặt tên

Đề xuất dạng:

```text
NNNN__short_description.sql
```

Ví dụ minh họa, **không phải migration đã được duyệt để chạy**:

```text
0001__create_migration_metadata.sql
0002__add_product_media_reference.sql
0003__add_catalog_query_index.sql
```

Tên và thứ tự thực tế phải được xác lập theo trạng thái schema sau Gate B. Không dùng ví dụ này để kết luận rằng bảng/cột/index tương ứng chắc chắn cần được tạo.

---

## 6. Migration metadata và lịch sử áp dụng

Cần có một nguồn lưu trạng thái migration đã áp dụng. Có thể là bảng metadata trong PostgreSQL, do migration runner quản lý.

### Thông tin tối thiểu đề xuất

| Trường | Mục đích |
|---|---|
| `version` | Mã migration duy nhất |
| `name` | Tên ngắn mô tả thay đổi |
| `checksum` | Phát hiện nội dung migration đã bị sửa sau khi áp dụng |
| `applied_at` | Thời điểm áp dụng |
| `applied_by` | Tác nhân hoặc pipeline áp dụng |
| `execution_ms` | Thời gian chạy, nếu runner hỗ trợ |
| `status` | Trạng thái theo thiết kế runner; không ghi nhận thành công trước verify |

Đây là đề xuất logic, không phải schema SQL cuối cùng. Cần quyết định loại dữ liệu, quyền truy cập, cách ghi nhận thất bại và xử lý khi process bị dừng giữa chừng.

### Quy tắc runner

1. Đọc danh sách migration theo thứ tự xác định.
2. Đọc trạng thái đã áp dụng.
3. Kiểm tra checksum của migration đã áp dụng.
4. Dừng nếu phát hiện migration cũ bị thay đổi hoặc lịch sử không nhất quán.
5. Áp dụng migration chưa chạy theo thứ tự.
6. Ghi nhận thành công chỉ sau khi migration và các kiểm tra bắt buộc hoàn tất.
7. In ra version bắt đầu/kết thúc và lỗi đủ rõ để vận hành.
8. Không tự động tiếp tục khi trạng thái sau lỗi không rõ ràng; yêu cầu kiểm tra và recovery có chủ đích.

---

## 7. Quy trình migration chuẩn

```text
Audit & design
    ↓
Viết SQL migration + pre/postconditions
    ↓
Review SQL, data impact, lock/runtime risk
    ↓
Tạo backup/snapshot phù hợp với môi trường
    ↓
Chạy trên clean test database
    ↓
Chạy trên database test có dữ liệu đại diện
    ↓
Chạy migration + verify + regression tests
    ↓
Diễn tập rollback/restore hoặc forward-fix
    ↓
Phê duyệt triển khai
    ↓
Backup/restore point trước thay đổi
    ↓
Áp dụng theo runbook
    ↓
Post-deployment verification
    ↓
Theo dõi và ghi audit evidence
```

### Giai đoạn A — Thiết kế

Mỗi migration cần ghi:

- Mục tiêu và finding/requirement liên quan.
- Những object database bị ảnh hưởng.
- Các điều kiện tiên quyết.
- Tác động lên dữ liệu hiện có.
- Ước lượng thời gian và khả năng khóa bảng.
- Tương thích với phiên bản backend cũ/mới.
- Postcondition cần kiểm tra.
- Rollback, restore hoặc forward-fix strategy.
- Test và bằng chứng chấp nhận.

### Giai đoạn B — Kiểm thử

Bắt buộc thử tối thiểu trên:

1. **Clean database:** bootstrap theo quy trình chuẩn, sau đó chạy toàn bộ migration.
2. **Database đại diện dữ liệu cũ:** áp dụng migration từ schema/version trước đó.
3. **Regression tests:** kiểm tra API và business rules bị ảnh hưởng.
4. **Failure test:** xác định trạng thái khi migration thất bại ở giữa; xác minh có thể phát hiện và khôi phục.
5. **Repeat/status test:** chạy runner lần nữa để xác nhận migration đã áp dụng được nhận diện đúng, không bị chạy lại ngoài ý muốn.

### Giai đoạn C — Triển khai

- Chốt đúng target database và environment.
- Dừng hoặc giới hạn các hoạt động có thể xung đột nếu runbook yêu cầu.
- Tạo backup/restore point và kiểm tra khả năng truy cập backup.
- Ghi nhận version hiện tại.
- Áp dụng migration bằng runner/command được phê duyệt.
- Chạy postcondition checks và health/regression checks.
- Ghi nhận version cuối, thời gian, log và kết quả.
- Chỉ chuyển traffic/hoàn tất release khi tiêu chí chấp nhận đạt.

---

## 8. Chiến lược tương thích ứng dụng: Expand → Migrate → Contract

Với thay đổi có thể phá tương thích, ưu tiên triển khai theo nhiều bước thay vì đổi schema và code cùng lúc.

### Ví dụ khái niệm: đổi tên hoặc thay thế một cột

1. **Expand:** thêm cột mới theo cách tương thích, giữ cột cũ.
2. **Dual compatibility/backfill:** code có thể đọc/ghi phù hợp trong giai đoạn chuyển đổi; backfill dữ liệu cũ theo batch nếu cần.
3. **Verify:** so sánh số lượng, nulls, giá trị và business invariants giữa cột cũ/mới.
4. **Switch reads:** chuyển code đọc sang cột mới sau khi dữ liệu đạt điều kiện.
5. **Stop old writes:** ngừng ghi cột cũ sau khi mọi phiên bản ứng dụng liên quan đã được nâng cấp.
6. **Contract:** chỉ xóa cột cũ trong một migration riêng sau thời gian xác nhận và khi rollback không còn phụ thuộc cột đó.

Đây là mẫu quy trình, không phải đề nghị đổi tên cột cụ thể trước Gate B.

---

## 9. Backup, rollback và recovery

### 9.1 Backup

Trước migration có rủi ro hoặc áp dụng lên dữ liệu cần bảo toàn:

- Chọn phương pháp backup phù hợp với quy mô và yêu cầu recovery.
- Ghi thời điểm, target database, schema/version và vị trí lưu backup.
- Bảo vệ backup vì có thể chứa dữ liệu cá nhân/secrets.
- Kiểm tra exit code và log; không coi file backup tồn tại là bằng chứng đủ.
- Xác minh khả năng restore trên môi trường cô lập theo lịch kiểm thử.
- Ghi nhận RPO/RTO mục tiêu sau khi nhóm dự án thống nhất.

### 9.2 Rollback SQL

Rollback bằng SQL chỉ phù hợp khi thay đổi có thể đảo ngược an toàn. Ví dụ, một index mới có thể có lệnh drop tương ứng, nhưng phải xác nhận index đó không còn được yêu cầu và lệnh phù hợp với cách tạo index ban đầu.

Các thay đổi thường **không dễ đảo ngược**:

- Xóa dữ liệu hoặc cột.
- Gộp/chuẩn hóa dữ liệu làm mất biểu diễn ban đầu.
- Thay đổi kiểu dữ liệu gây mất độ chính xác.
- Ghi dữ liệu mới theo semantics không tương thích.
- Chuyển object giữa filesystem và MinIO khi chưa giữ bản nguồn.

Với các trường hợp này, kế hoạch phải dựa trên backup/restore hoặc forward-fix có kiểm soát; không hứa rằng mọi migration đều có thể rollback bằng một file SQL đơn giản.

### 9.3 Recovery decision

| Tình huống | Hành động dự kiến |
|---|---|
| Migration thất bại trước khi thay đổi dữ liệu đáng kể | Dừng, kiểm tra trạng thái transaction/log, sửa nguyên nhân rồi chạy theo quy trình đã duyệt |
| Migration thất bại nhưng trạng thái schema chưa rõ | Không chạy lặp lại mù quáng; kiểm tra catalog, metadata và log trước |
| Migration thành công nhưng application regression | Đánh giá tương thích; rollback nếu đã thiết kế và an toàn, nếu không thì forward-fix hoặc restore theo runbook |
| Dữ liệu bị mất/sai | Ngừng các thao tác có thể làm nặng thêm, giữ evidence, đánh giá restore point và quy trình phục hồi |
| PostgreSQL tốt nhưng MongoDB/MinIO không đồng bộ | Chạy reconciliation/retry theo quy trình cross-store; không giả định có distributed transaction |
| Restore được chọn | Restore vào môi trường đích theo runbook, kiểm tra integrity và API trước khi mở lại traffic |

### 9.4 Không dùng rollback như lời hứa mặc định

Mỗi migration phải phân loại trước:

- `REVERSIBLE`: có rollback SQL được review và test.
- `RESTORE_REQUIRED`: cần khôi phục backup/snapshot nếu muốn quay lại.
- `FORWARD_FIX`: dữ liệu hoặc external side effects khiến rollback không an toàn; phương án là sửa tiến về trạng thái đúng.
- Có thể kết hợp các chiến lược theo từng bước, nhưng phải ghi rõ trong migration manifest/review.

---

## 10. MongoDB và MinIO: kế hoạch điều phối riêng

### 10.1 MongoDB

Sau khi Gate H–I chốt collection và ownership:

- Version hóa thay đổi document/validator/index.
- Xác định script backfill và điều kiện hoàn tất.
- Đặt PostgreSQL business key/reference rõ ràng khi cần liên kết.
- Kiểm tra document orphan hoặc reference hỏng.
- Có test khi MongoDB unavailable và khi retry.
- Không chuyển order/payment/inventory critical sang MongoDB chỉ để có thêm một loại database.

### 10.2 MinIO/media

Sau Gate G:

1. Inventory media path/reference hiện tại trong PostgreSQL, seed và filesystem volume.
2. Xác định bucket, object key, metadata, access policy và naming rules.
3. Copy object sang MinIO theo batch.
4. Kiểm tra object tồn tại, kích thước và checksum khi khả thi.
5. Chỉ cập nhật reference/URL theo từng batch sau khi object đã được xác minh.
6. Chạy kiểm tra media qua backend/API và frontend.
7. Theo dõi missing object, duplicate object và reference sai.
8. Giữ nguồn cũ trong giai đoạn xác nhận; chỉ xóa sau khi backup/retention và phê duyệt đã đáp ứng.

Không cập nhật hàng loạt reference trước khi chứng minh object đích tồn tại. Không xóa filesystem media ngay sau lần copy đầu tiên.

### 10.3 Cross-store reconciliation

Cần có báo cáo hoặc script kiểm tra:

- PostgreSQL reference không có object/document tương ứng.
- Object/document không còn reference.
- Batch migration chưa hoàn tất.
- Lỗi retry hoặc trạng thái không xác định.

Thiết kế chi tiết sẽ phụ thuộc data ownership và luồng được chốt ở Gate G–I.

---

## 11. Kiểm thử và tiêu chí chấp nhận

### 11.1 Migration test matrix

| ID | Kiểm tra | Kết quả mong đợi |
|---|---|---|
| MIG-T01 | Bootstrap clean database | Schema ban đầu được tạo đúng |
| MIG-T02 | Áp dụng toàn bộ migrations từ đầu | Tới version cuối, không lỗi |
| MIG-T03 | Upgrade từ schema/version trước | Dữ liệu và constraint được bảo toàn theo thiết kế |
| MIG-T04 | Migration có data backfill | Số lượng và invariant trước/sau khớp tiêu chí |
| MIG-T05 | Chạy runner lần hai | Migration đã áp dụng không bị chạy lại ngoài ý muốn |
| MIG-T06 | Checksum mismatch | Runner dừng và báo rõ |
| MIG-T07 | Cố ý tạo lỗi migration trên test DB | Lỗi được phát hiện; trạng thái sau lỗi có thể xác định |
| MIG-T08 | Rollback/restore rehearsal | Khôi phục theo runbook và xác minh được |
| MIG-T09 | API regression | Các luồng nghiệp vụ liên quan vẫn hoạt động |
| MIG-T10 | Constraint/FK/index/function/trigger | Hành vi database sau migration đúng yêu cầu |
| MIG-T11 | Cross-store reference | Reference được xác minh; lỗi/thiếu dữ liệu được phát hiện |
| MIG-T12 | Deployment/restart | Restart không bị nhầm là migration và không gây thay đổi schema ngoài ý muốn |

### 11.2 Evidence cần lưu

- Migration version và checksum.
- Log command/pipeline cùng exit code.
- Kết quả precondition/postcondition.
- Test report.
- Backup metadata và kết quả restore rehearsal.
- Trước/sau về số dòng, null, duplicate, orphan hoặc business invariant có liên quan.
- `EXPLAIN ANALYZE` trước/sau nếu migration tác động index hoặc query performance.
- Quyết định phê duyệt và các giới hạn đã biết.

### 11.3 Definition of Done

Một migration chỉ được xem là hoàn tất khi:

- [ ] SQL đã được review.
- [ ] Precondition và postcondition được ghi rõ.
- [ ] Đã chạy trên clean test database.
- [ ] Đã thử upgrade từ trạng thái cũ đại diện.
- [ ] Test regression liên quan đã đạt.
- [ ] Có chiến lược rollback/restore/forward-fix được duyệt.
- [ ] Có evidence lưu lại.
- [ ] ORM/schema/API/frontend được đồng bộ nếu liên quan.
- [ ] Hướng dẫn vận hành và thứ tự triển khai được cập nhật.
- [ ] Không còn schema drift chưa giải thích.

---

## 12. Tích hợp vào Docker và CI/CD

### Local development

- `docker compose up` có thể tiếp tục dùng để khởi động service.
- Bootstrap database mới phải được tách biệt về ý nghĩa với nâng cấp database đang tồn tại.
- Không để mọi lần backend restart tự động chạy migration có rủi ro mà không có kiểm soát.
- Cấu hình connection/credentials qua environment hoặc secret mechanism; không commit secrets.

### CI

Pipeline nên có các bước:

1. Khởi động PostgreSQL test service.
2. Tạo clean test database.
3. Bootstrap schema baseline theo quy ước repository.
4. Áp dụng migration sequence.
5. Kiểm tra migration history/checksum.
6. Chạy backend integration tests và các regression tests.
7. Nếu có MongoDB/MinIO trong scope của change, khởi động service test và chạy integration/reconciliation tests tương ứng.
8. Lưu logs/test report làm evidence.

### Deployment

- Migration phải là bước có chủ đích trong deployment runbook/pipeline, không phụ thuộc ngầm vào việc container khởi động.
- Xác định thứ tự deploy migration và application dựa trên compatibility; dùng expand-contract khi cần.
- Có health check và post-deployment verification.
- Không cho nhiều backend replica đồng thời chạy cùng migration nếu runner chưa bảo đảm locking/serialization.
- Cần quyết định migration chạy từ CI job, one-off container hay operator command sau khi audit deployment thực tế.

---

## 13. Kế hoạch triển khai theo giai đoạn

### Phase 0 — Gate B–F: Audit và xác định tác động

- [ ] Inventory schema, constraints, indexes, functions/triggers.
- [ ] Audit CRUD/API queries và transaction boundaries.
- [ ] Xác định data ownership và các bảng/reference sẽ thay đổi.
- [ ] Xác định data volume, lock risk và yêu cầu tương thích.
- [ ] Không viết migration production cụ thể trước khi có bằng chứng.

**Deliverable:** impact analysis và danh sách migration candidate.

### Phase 1 — Thiết kế migration mechanism

- [ ] Chọn/thiết kế runner.
- [ ] Chốt migration naming/version/checksum.
- [ ] Chốt metadata/history schema.
- [ ] Chốt error handling, locking và concurrency.
- [ ] Chốt phân loại reversible/restore-required/forward-fix.
- [ ] Viết runbook cho clean DB và upgrade DB hiện hữu.

**Deliverable:** migration design được review.

### Phase 2 — Proof of concept trên test DB

- [ ] Tạo một migration không phá hủy, có phạm vi nhỏ sau khi audit xác định nhu cầu thật.
- [ ] Chạy trên clean DB.
- [ ] Chạy trên database test có dữ liệu.
- [ ] Thử lỗi có kiểm soát.
- [ ] Thử runner chạy lại.
- [ ] Diễn tập rollback/restore phù hợp.
- [ ] Tích hợp vào CI.

**Deliverable:** migration mechanism proof + test evidence.

### Phase 3 — Migrations nghiệp vụ

- [ ] Tạo từng migration từ các finding đã duyệt.
- [ ] Với data migration, dùng batch khi cần và đo thời gian.
- [ ] Kiểm tra constraints, functions/triggers và business invariants.
- [ ] Đánh giá query plans nếu index/query thay đổi.
- [ ] Cập nhật ORM/API/tests cùng change.

**Deliverable:** migrations có version và test.

### Phase 4 — Cross-store migration

- [ ] Hoàn thành thiết kế MongoDB và MinIO.
- [ ] Viết migration/backfill scripts riêng cho từng store.
- [ ] Thiết kế thứ tự phối hợp và reconciliation.
- [ ] Thử missing object/document, retry và service outage.
- [ ] Giữ nguồn cũ cho tới khi verification và retention criteria đạt.

**Deliverable:** cross-store migration runbook và integration evidence.

### Phase 5 — Production readiness

- [ ] Backup và restore rehearsal đạt.
- [ ] Runbook đã review.
- [ ] Có thời gian chạy/lock risk được đánh giá.
- [ ] Có rollback/recovery decision.
- [ ] Có người chịu trách nhiệm và phê duyệt.
- [ ] Có post-deployment verification.
- [ ] Chỉ triển khai khi các điều kiện bắt buộc đạt.

**Deliverable:** approved release plan.

---

## 14. Open questions cần chốt sau audit

| ID | Câu hỏi | Vì sao chưa chốt |
|---|---|---|
| MQ-01 | Chọn migration runner/tool nào? | Cần xem dependencies, CI, deployment và khả năng quản lý SQL/PL/pgSQL |
| MQ-02 | Migration metadata nằm ở schema nào và ai có quyền ghi? | Cần chốt quyền DB và operational model |
| MQ-03 | Có cần advisory lock/serialization trong runner không? | Phụ thuộc cách chạy deploy và số replica |
| MQ-04 | Backup PostgreSQL dùng phương pháp nào, RPO/RTO bao nhiêu? | Cần biết môi trường triển khai và yêu cầu recovery |
| MQ-05 | Những migration nào cần expand-contract? | Chỉ xác định sau schema/API impact audit |
| MQ-06 | Data backfill xử lý batch/retry ra sao? | Phụ thuộc bảng, volume, lock và tính chất dữ liệu |
| MQ-07 | MongoDB document versioning/validator migration thế nào? | Chờ Gate H–I |
| MQ-08 | MinIO object key và media cutover/rollback ra sao? | Chờ Gate G |
| MQ-09 | Migration chạy từ CI, one-off container hay operator command? | Chờ audit deployment |
| MQ-10 | Ai phê duyệt migration có phá tương thích? | Cần thống nhất quy trình nhóm |

---

## 15. Quyết định đề xuất

| ID | Quyết định | Trạng thái |
|---|---|---|
| D-MIG-001 | Giữ SQL-first cho PostgreSQL | CONFIRMED BY PROJECT GUIDE |
| D-MIG-002 | Không coi bootstrap/entrypoint là migration | CONFIRMED BY GATE A |
| D-MIG-003 | Mỗi migration phải có version/history và verification | PROPOSED — cần phê duyệt |
| D-MIG-004 | Migration đã áp dụng không bị sửa âm thầm | PROPOSED — cần phê duyệt |
| D-MIG-005 | Có backup/recovery strategy và rehearsal trước thay đổi rủi ro | REQUIRED |
| D-MIG-006 | MongoDB và MinIO có quy trình migration riêng | REQUIRED BY MULTI-STORE DESIGN |
| D-MIG-007 | Không giả định transaction ACID xuyên PostgreSQL/MongoDB/MinIO | REQUIRED |
| D-MIG-008 | Chỉ triển khai production sau test, evidence và approval | REQUIRED |

---

## 16. Kết luận

Kế hoạch migration phải được xem là một phần của kiến trúc, không phải một lệnh chạy kèm lúc khởi động container. Baseline hiện tại dùng SQL-first, nhưng `init_db.py` chỉ là bootstrap; vì vậy cần thiết kế và kiểm chứng migration mechanism riêng trước khi có thay đổi schema cần áp dụng lên database đã tồn tại.

**Trình tự được khuyến nghị:**

`Gate B–F audit → impact analysis → migration mechanism design → test DB proof of concept → migration + regression tests → backup/restore rehearsal → approval → controlled deployment → verification`

Các migration cụ thể, tên bảng/cột/index, runner và lệnh triển khai vẫn là quyết định mở cho đến khi các Gate liên quan cung cấp đủ bằng chứng.
