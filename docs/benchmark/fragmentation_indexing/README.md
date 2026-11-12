# Benchmark fragmentation/indexing — 10/11/2026

Dữ liệu giả lập xác định trước: 20.000 product ở A, 10.000 ở B, seller/category lệch 9:1, thời gian/giá có nhiều giá trị trùng; thêm 1.000 ảnh/site. PostgreSQL 16.15 và MongoDB 8.0.32. Mỗi query warm-up 3 lượt, đo latency 30 lượt, lưu 3 explain PostgreSQL. Cache ấm, concurrency 1, cùng một máy. Không dùng dữ liệu production để thay đổi index thử nghiệm.

| Ứng viên PostgreSQL | p95 trước → sau (ms) | Cải thiện đọc | Chênh lệch p95 ghi | Quyết định |
| --- | --- | --- | --- | --- |
| category + date + ID | 1,079 → 0,944 | 12,5% | −6,5% | Chưa thêm; mức cải thiện đọc thấp |
| seller + date + ID | 2,453 → 0,838 | 65,8% | −35,6% | Chọn bổ sung cho đường đọc theo seller, migration 008 |
| price + ID | 1,590 → 0,718 | 54,9% | +51,4% | Chưa thêm; chi phí ghi tăng vượt ngưỡng |
| product + display order + image ID | 4,707 → 12,829 | −172,6% | +3,9% | Chưa thêm; không có lợi trong lần thử |

Index seller chiếm 827.392 byte trên tập A. Số ghi âm là biến động của phép đo, không phải bằng chứng thêm index giúp ghi nhanh hơn. Các update được rollback, chưa tính commit/fsync; đây chỉ là chỉ báo ban đầu về write cost. Cần đo lại trên phân bố dữ liệu, số client, tỷ lệ đọc/ghi thực tế trước khi coi ngưỡng p95 đọc giảm 20%/ghi tăng tối đa 10% là đã nghiệm thu production.

Mongo thử đúng dạng attribute search của service: `{deleted:false, attributes.brand:'minor'}`, projection `{product_id:1,_id:0}`, limit 5001. Compound partial index thử nghiệm giảm p95 52,117 → 5,129 ms; docs examined 20.000 → 0, keys examined 0 → 200, trả 200 document. Không phát hành index brand vì chưa có tần suất brand thực tế và phép đo ghi tương ứng. Không ép chuyển field giá/title sang Mongo để đạt IXSCAN.

Explain FDW xác nhận filter seller/status/deleted và projection được đẩy xuống B; Remote SQL trong lần đo này không có ORDER BY, nên không tuyên bố sort đã được đẩy xuống. Có explain pruning cho order_id và khoảng log nửa mở. Kiểm thử nghiệp vụ riêng kiểm biên tháng/default partition và rollback mảnh user.

- [results.json](results.json): đầy đủ latency, explain, số đo ghi và thống kê Mongo.
- [postgresql.json](postgresql.json): checkpoint kết quả PostgreSQL trước phần Mongo.
- [Bộ chạy](../../../backend/scripts/benchmark_fragmentation.py): tạo database/role UUID và dọn sau thử nghiệm.

Mỗi index được thử độc lập; chỉ một index được chọn nên chưa có phép đo nhiều index bổ sung cộng dồn. Kết quả không đại diện throughput đồng thời hoặc latency HTTP. Commit được ghi trong JSON là HEAD nền; mã triển khai đang ở working tree, không phải commit đã publish.
