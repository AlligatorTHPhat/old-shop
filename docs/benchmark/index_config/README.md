# Kiểm chứng index đọc từ JSON

Ngày chạy: 03/11/2026. MongoDB 8.0.32, DB kiểm thử riêng, 10.000 document mỗi
collection tạm. Chạy `scripts.benchmark_mongo_day4`; `mongo_schema.INDEXES` của script
được nạp từ `database/indexing/catalog.json`. Script xóa đúng các collection UUID do
nó tạo sau khi đo. EXPLAIN dùng lựa chọn tự nhiên của optimizer, không hint.

| Truy vấn | Docs examined trước → sau | Returned trước/sau |
|---|---:|---:|
| Product theo category và attributes.brand, limit 20 | 192 → 20 | 20 |
| Review theo product, sort created_at | 10.000 → 10 | 10 |
| Order snapshot theo buyer, sort order_date | 10.000 → 10 | 10 |

Xem [`mongo/summary.json`](mongo/summary.json) và các file EXPLAIN trước/sau đi kèm.
Baseline của các collection đo chỉ có `_id_`; pha sau tạo index qua adapter JSON.
Đây là một lần explain mỗi pha, không phải thống kê latency nhiều lần; truy vấn product
có LIMIT nên baseline không phải quét đủ 10.000 document. Một số thời gian nhỏ sau khi
thêm index cao hơn trước; không suy ra cải thiện latency ổn định từ mẫu đo này.

Việc giữ nguyên định nghĩa index khi chuyển Python/SQL sang JSON không tự đổi hiệu năng.
Kết quả này chứng minh đường tạo index và sử dụng index từ cấu hình mới. Chưa đề xuất
thêm index vật lý mới vào cấu hình ứng dụng để tối ưu hiệu năng.

Đối soát toàn hệ và kết quả test:
[`../../evidence/index_config_validation.json`](../../evidence/index_config_validation.json).
