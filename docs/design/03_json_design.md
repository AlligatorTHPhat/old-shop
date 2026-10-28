# Thiết kế JSON, MongoDB và MinIO — Ngày 3

Nguồn chuẩn: `backend/app/schemas/documents.py`; validator BSON được sinh bởi `services/mongo_schema.py`. Ví dụ đủ sáu collection: [03_document_examples.json](03_document_examples.json). Validator dùng để khởi tạo: [03_mongo_validators.json](03_mongo_validators.json).

JSON ví dụ biểu diễn ngày giờ ISO 8601; khi ghi Mongo phải dùng `datetime` có múi giờ (BSON Date), không chèn nguyên chuỗi JSON. `_id` là chuỗi ổn định, `schema_version=1`. Không tự gán múi giờ cho timestamp PG cũ khi D7 chưa chốt. Tiền VND là số nguyên không âm trong giới hạn int64; giá nguồn có phần lẻ phải báo lỗi chất lượng dữ liệu, không làm tròn âm thầm. Mã thanh toán giữ `status_code` gốc cho tới D8.

## product_details

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `product_id` | `<class 'int'>` | Có |
| `category_id` | `<class 'int'>` | Có |
| `description` | `str | None` | Không; có mặc định |
| `video_url` | `str | None` | Không; có mặc định |
| `weight_grams` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Ge(ge=0)])]]` | Không; có mặc định |
| `dimensions` | `app.schemas.documents.Dimensions | None` | Không; có mặc định |
| `dimensions_raw` | `str | None` | Không; có mặc định |
| `condition` | `app.schemas.documents.Condition | None` | Không; có mặc định |
| `attributes` | `dict[str, JsonValue]` | Không; có mặc định |
| `tags` | `list[str]` | Không; có mặc định |
| `images` | `list[app.schemas.documents.ProductImageReference]` | Không; có mặc định |
| `updated_at` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `deleted` | `<class 'bool'>` | Không; có mặc định |
| `etl` | `app.schemas.documents.ETLMetadata | None` | Không; có mặc định |

## reviews

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `review_id` | `<class 'int'>` | Có |
| `product_id` | `<class 'int'>` | Có |
| `buyer_id` | `<class 'int'>` | Có |
| `type` | `Literal['review', 'report']` | Có |
| `rating` | `<class 'int'>` | Có |
| `title` | `str | None` | Không; có mặc định |
| `content` | `str | None` | Không; có mặc định |
| `status` | `Optional[Literal['pending', 'approved', 'rejected']]` | Không; có mặc định |
| `moderation` | `app.schemas.documents.Moderation | None` | Không; có mặc định |
| `evidence` | `list[app.schemas.documents.ObjectReference]` | Không; có mặc định |
| `created_at` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `updated_at` | `pydantic.types.AwareDatetime | None` | Không; có mặc định |
| `deleted` | `<class 'bool'>` | Không; có mặc định |
| `etl` | `app.schemas.documents.ETLMetadata | None` | Không; có mặc định |

## order_snapshots

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `order_id` | `<class 'int'>` | Có |
| `buyer` | `<class 'app.schemas.documents.BuyerReference'>` | Có |
| `items` | `list[app.schemas.documents.OrderSnapshotItem]` | Có |
| `payments` | `list[app.schemas.documents.PaymentSnapshot]` | Không; có mặc định |
| `total_amount_vnd` | `<class 'int'>` | Có |
| `shipping_fee_vnd` | `<class 'int'>` | Có |
| `discount_amount_vnd` | `<class 'int'>` | Có |
| `final_amount_vnd` | `<class 'int'>` | Có |
| `voucher_id` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Gt(gt=0), Le(le=9223372036854775807)])]]` | Không; có mặc định |
| `order_status` | `<class 'int'>` | Có |
| `order_date` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `deleted` | `<class 'bool'>` | Không; có mặc định |
| `etl` | `<class 'app.schemas.documents.ETLMetadata'>` | Có |

## system_logs

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `log_id` | `<class 'int'>` | Có |
| `actor_id` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Gt(gt=0), Le(le=9223372036854775807)])]]` | Không; có mặc định |
| `action` | `<class 'str'>` | Có |
| `resource_type` | `str | None` | Không; có mặc định |
| `resource_id` | `int | None` | Không; có mặc định |
| `message` | `str | None` | Không; có mặc định |
| `payload` | `app.schemas.documents.LogPayload | None` | Không; có mặc định |
| `ip_hash` | `str | None` | Không; có mặc định |
| `created_at` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `etl` | `app.schemas.documents.ETLMetadata | None` | Không; có mặc định |

## violation_logs

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `log_id` | `<class 'int'>` | Có |
| `target_user_id` | `<class 'int'>` | Có |
| `actor_id` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Gt(gt=0), Le(le=9223372036854775807)])]]` | Không; có mặc định |
| `reason` | `<class 'str'>` | Có |
| `action_taken` | `<class 'str'>` | Có |
| `created_at` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `payload` | `app.schemas.documents.LogPayload | None` | Không; có mặc định |
| `etl` | `app.schemas.documents.ETLMetadata | None` | Không; có mặc định |

## contact_messages

| Field | Kiểu Pydantic | Bắt buộc khi tạo |
|---|---|---|
| `_id` | `<class 'str'>` | Có |
| `schema_version` | `Literal[1]` | Không; có mặc định |
| `feedback_id` | `<class 'int'>` | Có |
| `user_id` | `Optional[Annotated[int, FieldInfo(annotation=NoneType, required=True, metadata=[Gt(gt=0), Le(le=9223372036854775807)])]]` | Không; có mặc định |
| `subject` | `<class 'str'>` | Có |
| `content` | `<class 'str'>` | Có |
| `status` | `<class 'int'>` | Có |
| `attachments` | `list[app.schemas.documents.ObjectReference]` | Không; có mặc định |
| `created_at` | `<class 'pydantic.types.AwareDatetime'>` | Có |
| `etl` | `app.schemas.documents.ETLMetadata | None` | Không; có mặc định |

## Nhúng và tham chiếu

- `product_details`: nhúng attributes/tags/condition/dimensions/images để đọc cùng sản phẩm; product_id/category_id tham chiếu PG. Mongo sở hữu thuộc tính mới; ETL chỉ `$set` trường do PG sở hữu, giữ attributes/tags.
- `reviews`: tham chiếu product_id/buyer_id, nhúng moderation và evidence; rating=0 chỉ dành cho report, review=1..5. Không nhúng user PII.
- `order_snapshots`: nhúng buyer chỉ ID/vùng chuẩn hóa, items và payments để đọc một đơn không join. Giá mua là lịch sử; title/category/seller có hậu tố `_current` nếu nguồn không có snapshot lịch sử. Không nhận là giao dịch hay ràng buộc FK Mongo.
- `system_logs`: payload giới hạn event/reason_code/changed_fields; unique (log_id,created_at) tương thích partition tương lai. TTL 90 ngày chỉ áp dụng bản sao log Mongo, không xóa log PG.
- `violation_logs`: tham chiếu target_user_id, không suy diễn actor_id mà PG không lưu; giữ bằng chứng kiểm duyệt, không TTL.
- `contact_messages`: tham chiếu feedback_id từ system_feedback, không phải contact_info/address book; nhúng attachment reference, không sao chép guest_email.

ObjectReference gồm bucket/key (bắt buộc), content_type/size (tùy chọn). ProductImageReference thêm image_id/is_primary/display_order. Các cấu trúc nhúng khác được định nghĩa chặt trong Pydantic và validator JSON đính kèm. `additionalProperties=false` chặn field ngoài hợp đồng, riêng attributes cho phép JSON linh hoạt. Không thể dùng schema để bảo đảm nội dung text/attributes không chứa PII: ETL Ngày 5 phải lọc rõ ràng; không ghi mật khẩu, token, địa chỉ, email vào Mongo.

## Index và khởi tạo

Index cụ thể nằm trong `INDEXES` của `services/mongo_schema.py`: unique ID nguồn, compound theo truy vấn sản phẩm/đơn/người mua/trạng thái, text description/tags, partial report pending, TTL system_logs. Unique index có thể từ chối dữ liệu cũ trùng lặp; script dừng báo lỗi, không xóa dữ liệu để ép chạy.

`python -m scripts.init_mongo` dùng tài khoản quản trị trong job `mongo-schema-init`, chạy lại bằng create/collMod + create_index, không drop/seed. Backend chỉ dùng tài khoản readWrite của database. Ngày 3 tạo hợp đồng và collection rỗng; đồng bộ PG → Mongo thuộc Ngày 5, ghép dữ liệu API thuộc Ngày 6.

## MinIO và đường dẫn ảnh

Ba bucket private: product-images, user-avatars, attachments. Tài khoản ứng dụng có quyền object chỉ trong ba bucket; root chỉ cấp cho job khởi tạo. Route `/media/products/...` và `/media/users/...` của FastAPI đọc S3 rồi stream; Nginx giữ proxy `/media/` hiện tại, frontend không đổi. Không mở bucket anonymous, không đưa secret/presigned credential tới trình duyệt. Attachments không đi qua route media công khai; API kiểm quyền cho file đính kèm chưa thuộc Ngày 3.

Ảnh mới: `products/{product_id}/{uuid}.ext`, avatar `users/{user_id}/avatar-{uuid}.ext`. Avatar dùng key bất biến thay vì ghi đè avatar.ext để rollback giao dịch không làm mất ảnh cũ và tránh cache trả ảnh cũ. Seed có thêm alias `users/{id}/avatar.ext`. Giữ các key legacy để URL PG không phải migration. MIME image/*, đuôi jpg/jpeg/png/webp/gif và tối đa 2 MiB; đây là kiểm tra khai báo/đuôi/kích thước, chưa giải mã hoặc quét nội dung ảnh.

`LocalStorage` giữ hỗ trợ chế độ đĩa; `MinioStorage` chọn qua STORAGE_BACKEND. Upload trước commit PG, lỗi commit dọn object mới; avatar cũ giữ lại để tránh mất dữ liệu, cần GC riêng sau này. Không tự xóa object chưa tham chiếu. Streaming đóng kết nối cả khi lỗi/HEAD; đường dẫn traversal và symlink thoát root bị từ chối.

## Chạy lại và kiểm thử

Tại thư mục gốc:

```bash
python3 deploy/scripts/prepare-media-env.py
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml up -d minio-init mongo-schema-init
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml run --rm --no-deps --entrypoint python backend -m scripts.seed_media
python3 deploy/scripts/prepare-media-env.py --enable-minio
docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml --profile resilience up -d --wait
```

Seed chỉ thêm object chưa tồn tại, không sửa PG hay ghi đè upload. Đọc cả seed lẫn volume media; avatar fallback chỉ cho URL đã biết trong seed SQL. Trước chuyển backend cần bảo trì/chặn upload để không có ghi mới giữa lượt copy cuối và restart. Muốn quay về local, phải copy ảnh phát sinh trên MinIO về volume trước; chỉ đổi biến sẽ làm mất khả năng đọc các ảnh đó.

Readiness `/health/ready` kiểm tra PG, Mongo khi cấu hình URI, MinIO khi dùng backend minio; lỗi trả 503. `/health` là liveness. Các test trong `backend/tests/test_day3_data.py`; integration bật DAY3_INTEGRATION=1 trên stack riêng hoặc test DB, không chạy regression ghi lên DB ứng dụng. Swagger dùng cho API upload/GET, Mongo validator/index kiểm bằng test/driver.
