# KỊCH BẢN THUYẾT TRÌNH BÁO CÁO ĐỒ ÁN
## ĐỀ TÀI: HỆ THỐNG SÀN THƯƠNG MẠI ĐIỆN TỬ CHỢ CŨ (OLDSHOP)
### MÔN HỌC: CƠ SỞ DỮ LIỆU NÂNG CAO — TRƯỜNG ĐH SƯ PHẠM TP. HỒ CHÍ MINH (HCMUE)

* **Giảng viên hướng dẫn:** TS. Văn Thế Thành  
* **Sinh viên thực hiện:**
  1. **Trần Hoàng Phát** — MSSV: `49.01.104.107`
  2. **Nguyễn Trần Bảo Thái** — MSSV: `49.01.104.133`
  3. **Bùi Minh Tín** — MSSV: `49.01.104.132`

* **Tổng thời lượng dự kiến:** 10 – 12 phút  
* **Phân công trình bày:**
  * **Trần Hoàng Phát:** Slide 1 → Slide 5 (Giới thiệu, bối cảnh bài toán, phạm vi mục tiêu 5 trụ cột công nghệ).
  * **Bùi Minh Tín:** Slide 6 → Slide 8 (Mô hình ERD Polyglot Persistence, Cấu trúc JSON Read Model, Kỹ thuật Indexing).
  * **Nguyễn Trần Bảo Thái:** Slide 9 → Slide 11 (Hệ thống phân tán 2 Site, FDW, mạng VPN Tailscale, định hướng phát triển & kết luận).

---

### 🎙️ SLIDE 1: TRANG TIÊU ĐỀ
* **Người trình bày:** Trần Hoàng Phát  
* **Thời lượng:** ~30 giây  
* **Hành động:** Đứng nghiêm túc, chào giảng viên và hội đồng.

> *"Kính chào thầy TS. Văn Thế Thành và toàn thể các bạn sinh viên.*  
> *Hôm nay, nhóm chúng em gồm ba thành viên: em là **Trần Hoàng Phát**, cùng hai bạn là **Nguyễn Trần Bảo Thái** và **Bùi Minh Tín**, xin phép được đại diện nhóm báo cáo đề tài đồ án môn Cơ sở dữ liệu Nâng cao với chủ đề: **'Nghiên cứu và Triển khai Hệ thống Cơ sở dữ liệu Đa mô hình kết hợp Phân tán cho Sàn thương mại điện tử Chợ Cũ (OldShop)'**.*  
> *Sau đây, em xin phép bắt đầu phần trình bày của nhóm."*

---

### 🎙️ SLIDE 2: BẢNG PHÂN CÔNG NHIỆM VỤ
* **Người trình bày:** Trần Hoàng Phát  
* **Thời lượng:** ~40 giây  
* **Hành động:** Chỉ vào bảng phân công 3 người trên màn hình chiếu.

> *"Để giải quyết khối lượng công việc chuyên sâu của đồ án, nhóm em đã phân định rõ ràng 3 phân hệ độc lập:*  
> * *Em — **Trần Hoàng Phát**, phụ trách phân hệ **Data Tier & NoSQL**: Thiết kế cấu trúc CSDL quan hệ PostgreSQL lõi, áp dụng kỹ thuật phân vùng bảng đơn hàng, phân mảnh dọc bảng người dùng, tối ưu chỉ mục và cấu hình cụm NoSQL MongoDB cùng MinIO Object Storage.*  
> * *Bạn **Nguyễn Trần Bảo Thái**, phụ trách phân hệ **Distributed Systems & VPN**: Thiết kế mô hình phân mảnh ngang 2 Site, cấu hình kết nối PostgreSQL Foreign Data Wrapper (FDW) và thiết lập mạng riêng ảo Tailscale VPN kết nối liên máy giữa Windows và Linux.*  
> * *Bạn **Bùi Minh Tín**, phụ trách phân hệ **Data Pipeline & Testing**: Xây dựng đường ống đồng bộ Transactional Outbox (ETL Worker), phát triển Gateway Catalogue API, thực thi bộ kiểm thử tự động 12 ca test T01–T12 và hồ sơ tài liệu."*

---

### 🎙️ SLIDE 3: NỘI DUNG BÁO CÁO
* **Người trình bày:** Trần Hoàng Phát  
* **Thời lượng:** ~25 giây  
* **Hành động:** Giới thiệu ngắn gọn các mục sẽ trình bày.

> *"Bài báo cáo của nhóm sẽ đi qua 7 phần nội dung trọng tâm: từ việc xác định Bối cảnh và vấn đề, Phạm vi mục tiêu giải pháp, cấu trúc dữ liệu trên ERD, mô hình bán cấu trúc JSON, kỹ thuật Indexing tối ưu truy vấn, cho đến phần cốt lõi là Hệ thống CSDL phân tán 2 Site và phần Demo thực nghiệm trực tiếp."*

---

### 🎙️ SLIDE 4: BỐI CẢNH VÀ VẤN ĐỀ
* **Người trình bày:** Trần Hoàng Phát  
* **Thời lượng:** ~1 phút 15 giây  
* **Hành động:** Nhấn mạnh 3 thách thức dữ liệu thực tế của sàn đồ cũ.

> *"Thưa thầy, OldShop là mô hình sàn thương mại điện tử C2C chuyên về hàng đã qua sử dụng. Khác với các hệ thống bán lẻ tiêu chuẩn, dữ liệu của chợ cũ mang 3 đặc thù rất phức tạp:*  
> * * **Thứ nhất, tính chất dữ liệu không đồng nhất:** Giao dịch thanh toán, đơn hàng yêu cầu chuẩn ACID nghiêm ngặt; nhưng thông tin đồ cũ lại có thuộc tính biến thiên liên tục: điện thoại thì cần thông số dung lượng pin, laptop cần RAM/CPU, quần áo thì cần size/màu. Nếu lưu tất cả vào một bảng RDBMS thuần sẽ dẫn đến hiện tượng bảng quá nhiều cột rỗng hoặc phải `ALTER TABLE` liên tục.*  
> * * **Thứ hai, quá tải tệp nhị phân:** Đồ cũ bắt buộc người bán phải chụp từ 4 đến 8 hình ảnh chi tiết góc cạnh và vết trầy xước. Việc lưu trữ trực tiếp ảnh vào database sẽ làm phình to bộ nhớ đệm và suy giảm nghiêm trọng hiệu năng đọc ghi.*  
> * * **Thứ ba, giới hạn mở rộng:** Một máy chủ cơ sở dữ liệu duy nhất sẽ sớm chạm ngưỡng nghẽn I/O và tạo ra điểm chết đơn lẻ (Single Point of Failure).*  
> *Chính vì vậy, nhóm em đã nghiên cứu và ứng dụng giải pháp **Cơ sở dữ liệu Đa mô hình (Polyglot Persistence)** kết hợp kỹ thuật **Phân tán ngang**."*

---

### 🎙️ SLIDE 5: PHẠM VI VÀ MỤC TIÊU (SLIDE TRỌNG TÂM 1)
* **Người trình bày:** Trần Hoàng Phát  
* **Thời lượng:** ~1 phút 30 giây  
* **Hành động:** Nêu bật rõ 5 mục tiêu kỹ thuật cốt lõi có thật trong đồ án.

> *"Nhằm giải quyết triệt để các bài toán trên, đồ án của nhóm đã hiện thực hóa trọn vẹn 5 mục tiêu cốt lõi:*  
> * * **Mục tiêu 1 — Quản lý dữ liệu có cấu trúc:** Ứng dụng **PostgreSQL 16** làm nguồn dữ liệu giao dịch chuẩn, áp dụng Hash Partitioning trên bảng đơn hàng và Vertical Partitioning trên bảng người dùng.*  
> * * **Mục tiêu 2 — Lưu trữ dữ liệu bán cấu trúc:** Triển khai cụm **MongoDB 7.0 Replica Set 3 node**, quản lý các document JSON linh hoạt có validation phục vụ tra cứu chi tiết sản phẩm và nhật ký hệ thống.*  
> * * **Mục tiêu 3 — Lưu trữ dữ liệu phi cấu trúc:** Sử dụng **MinIO Object Storage** chuẩn S3 để lưu trữ toàn bộ ảnh sản phẩm và avatar, tách hoàn toàn lưu lượng media khỏi database.*  
> * * **Mục tiêu 4 — Tối ưu hóa chỉ mục (Indexing):** Thiết kế chỉ mục phức hợp (Compound Index), Partial Index và Text Search, đo lường chi phí truy vấn bằng `EXPLAIN ANALYZE`.*  
> * * **Mục tiêu 5 — Xây dựng CSDL phân tán 2 Site:** Triển khai mô hình phân tán độc lập bằng **PostgreSQL FDW**, định tuyến an toàn qua **Tailscale VPN** và tích hợp Catalogue Gateway API.*  
> *Sau đây, xin mời bạn **Bùi Minh Tín** sẽ tiếp nối phần trình bày về Mô hình ERD, Cấu trúc JSON và Tối ưu Indexing."*

---

### 🎙️ SLIDE 6: MÔ HÌNH ERD & CHIẾN LƯỢC POLYGLOT PERSISTENCE (SLIDE TRỌNG TÂM 2)
* **Người trình bày:** Bùi Minh Tín  
* **Thời lượng:** ~2 phút  
* **Hành động:** Chỉ vào 3 vùng màu trên sơ đồ ERD để làm nổi bật kiến trúc đa mô hình.

> *"Kính thưa thầy, trên slide số 6 là sơ đồ ERD quan niệm của OldShop. Điểm nâng cao trong thiết kế của nhóm là áp dụng chiến lược **Polyglot Persistence — chọn đúng công nghệ cho từng loại dữ liệu**, thể hiện qua 3 cụm màu rõ rệt:*  
> * * **Vùng màu xanh dương (PostgreSQL - Dữ liệu có cấu trúc):** Đóng vai trò là 'Nguồn chân lý' (Source of Truth) bảo đảm chuẩn ACID cho các thực thể tài chính: `users`, `orders`, `order_details`, `transactions`, `vouchers`. Tại đây, nhóm đã áp dụng 2 kỹ thuật nâng cao:*  
>   * * **Phân mảnh ngang nội bộ (Hash Partitioning):** Bảng `orders` được chia thành 4 phân vùng vật lý theo thuật toán băm `order_id` để tăng tốc độ ghi đơn hàng đồng thời. Bảng `system_logs` được chia theo dải thời gian (Range Partitioning).*  
>   * * **Phân mảnh dọc (Vertical Partitioning):** Nhóm tách bảng `users` thành 4 bảng độc lập: `user_core` (danh tính), `user_profile` (thông tin cá nhân), `user_secret` (mật khẩu) và `user_wallet` (số dư ví) nhằm tăng cường bảo mật và giảm tải I/O khi đọc.*  
> * * **Vùng màu xanh lá (MongoDB - Dữ liệu bán cấu trúc):** Lưu trữ các collection `product_details`, `reviews`, `system_logs` và `order_snapshots`. Dữ liệu được đồng bộ từ PostgreSQL sang MongoDB hoàn toàn tự động thông qua **Python ETL Worker** theo mô hình **Transactional Outbox**, bảo đảm tính nhất quán cuối cùng mà không làm nghẽn luồng xử lý chính.*  
> * * **Vùng màu vàng (MinIO - Dữ liệu phi cấu trúc):** Quản lý toàn bộ tệp nhị phân hình ảnh, tách rời đường truyền media ra khỏi máy chủ cơ sở dữ liệu."*

---

### 🎙️ SLIDE 7: CẤU TRÚC TÀI LIỆU JSON (READ MODEL) (SLIDE TRỌNG TÂM 3)
* **Người trình bày:** Bùi Minh Tín  
* **Thời lượng:** ~1 phút 40 giây  
* **Hành động:** Nhìn vào đoạn code JSON trên slide và giải thích cấu trúc nhúng.

> *"Tại slide 7, đây là cấu trúc document JSON thực tế được lưu trữ trong MongoDB collection `product_details`.*  
> *Trong hệ thống của nhóm, tài liệu JSON này đóng vai trò là **Read Model (Bản đọc phi chuẩn hóa)** theo mô hình CQRS:*  
> * *Khi người mua xem chi tiết một món hàng cũ, họ cần thấy đồng thời: tên hàng, danh mục, giá bán, tình trạng độ mới, bảo hành, cùng danh sách tất cả các ảnh chụp.*  
> * *Nếu truy vấn hoàn toàn trên PostgreSQL, hệ thống bắt buộc phải thực hiện các phép nối `JOIN` phức tạp qua các bảng `product`, `category`, `product_image`, `seller`... Điều này tiêu tốn nhiều chi phí bộ nhớ khi có hàng nghìn lượt xem cùng lúc.*  
> * *Với tài liệu JSON này, toàn bộ mảng `product_images` và các thuộc tính chi tiết đã được nhúng sẵn vào một document duy nhất. Frontend chỉ cần thực hiện đúng một lệnh đọc theo `product_id` là có đầy đủ thông tin để hiển thị giao diện, đạt độ phản hồi cực nhanh dưới 2 mili-giây mà không cần `JOIN` bất kỳ bảng nào trên RDBMS."*

---

### 🎙️ SLIDE 8: INDEXING & TỐI ƯU HÓA KẾ HOẠCH TRUY VẤN (SLIDE TRỌNG TÂM 4)
* **Người trình bày:** Bùi Minh Tín  
* **Thời lượng:** ~2 phút  
* **Hành động:** Phân tích trực tiếp các thông số trên ảnh `explain("executionStats")` ở slide.

> *"Tại slide số 8, nhóm xin chứng minh tính hiệu quả của chiến lược Indexing thông qua kết quả đo lường thực tế từ lệnh `explain('executionStats')` trên cụm MongoDB:*  
> * *Nếu không đánh chỉ mục, hệ thống sẽ rơi vào trạng thái `COLLSCAN` (Collection Scan) — tức là phải quét toàn bộ bảng $O(N)$, đọc toàn bộ dữ liệu từ đĩa vào RAM.*  
> * *Nhóm đã thiết lập chỉ mục B-tree trên trường `product_id`. Nhìn vào bức ảnh trích xuất kế hoạch thực thi ở bên phải slide, thầy và các bạn có thể thấy 3 chỉ số tối ưu lý tưởng:*  
>   * * **Thứ nhất, giai đoạn thực thi (`stage`):** Đạt trạng thái **`EXPRESS_IXSCAN`** trên chỉ mục `product_id_1`, nghĩa là hệ thống chỉ duyệt qua cây chỉ mục B-tree với độ phức tạp $O(\log N)$.*  
>   * * **Thứ hai, thời gian thực thi (`executionTimeMillis`):** Chỉ mất đúng **2 mili-giây**.*  
>   * * **Thứ ba, tỷ lệ tài liệu kiểm tra:** Thông số `totalDocsExamined` là **1**, khớp tuyệt đối 100% với số lượng tài liệu trả về `nReturned: 1`. Điều này chứng minh hệ thống không phải đọc dư thừa bất kỳ một document nào.*  
> * *Bên cạnh đó, trên PostgreSQL, nhóm cũng tạo các chỉ mục **GIN Trigram** trên trường tiêu đề sản phẩm để hỗ trợ tìm kiếm mờ (Fuzzy Search), cùng **Partial Index** chỉ đánh dấu các sản phẩm đang hiển thị (`status = 'approved' AND is_deleted = false`), giúp tiết kiệm 40% dung lượng cây chỉ mục.*  
> *Tiếp theo, bạn **Nguyễn Trần Bảo Thái** sẽ trình bày về Kiến trúc Phân tán 2 Site và mạng VPN."*

---

### 🎙️ SLIDE 9: HỆ THỐNG CƠ SỞ DỮ LIỆU PHÂN TÁN (SLIDE TRỌNG TÂM 5)
* **Người trình bày:** Nguyễn Trần Bảo Thái  
* **Thời lượng:** ~2 phút 30 giây  
* **Hành động:** Chỉ vào các khối Site A, Site B, FDW và Gateway trên sơ đồ.

> *"Kính thưa thầy, slide số 9 thể hiện kiến trúc CSDL Phân tán — phần cốt lõi của đề tài theo tiêu chuẩn Lab02:*  
> * **1. Mô hình Phân mảnh ngang (Horizontal Fragmentation):**  
>   * *Nhóm triển khai 2 site PostgreSQL hoàn toàn độc lập: **Site A (`oldshop_1`)** đặt trên máy Windows và **Site B (`oldshop_2`)** đặt trên máy Linux.*  
>   * *Phân mảnh theo chủ sở hữu (Seller-based Fragmentation): **Site A chỉ quản lý các seller mang ID lẻ và sinh `product_id` số lẻ (1, 3, 5...)**; **Site B chỉ quản lý các seller mang ID chẵn và sinh `product_id` số chẵn (2, 4, 6...)**.*  
>   * *Phân mảnh dẫn xuất: Bảng ảnh `product_image` đi liền với sản phẩm cục bộ tại site đó. Riêng bảng danh mục `category` được nhân bản toàn phần trên cả hai máy.*  
> * **2. Cơ chế liên kết phân tán bằng Foreign Data Wrapper (FDW):**  
>   * *Trên Site A, nhóm kích hoạt extension `postgres_fdw`, khai báo Foreign Server trỏ sang Site B với tài khoản bảo mật giới hạn chỉ đọc `b_reader`.*  
>   * *Tạo view toàn cục `v_product` bằng phép `UNION ALL` giữa bảng cục bộ tại A và foreign table `site_b.product`. Người dùng tại Site A truy vấn qua view hoàn toàn trong suốt như đang làm việc trên một CSDL duy nhất.*  
> * **3. Hạ tầng mạng riêng ảo liên máy (Tailscale VPN):**  
>   * *Hai máy kết nối xuyên qua mạng riêng ảo Tailscale VPN (Máy Windows: `100.95.171.37` ↔ Máy Linux: `100.81.147.43`).*  
>   * *Sử dụng cơ chế `tailscale serve` chuyển tiếp cổng TCP `57432`, đảm bảo kết nối ổn định với độ trễ trực tiếp chỉ 11ms.*  
>   * *Đứng trước hệ thống là **Catalogue API Gateway** (cổng `57480`), cung cấp REST API đọc danh mục hợp nhất và tích hợp cơ chế bảo vệ **Fail-Closed** (tự động cô lập lỗi khi đứt mạng).*  
> *Toàn bộ kiến trúc này đã vượt qua **12/12 ca kiểm thử tích hợp tự động (T01–T12)** được ghi nhận đầy đủ trong file bằng chứng `test_results.json`."*

---

### 🎙️ SLIDE 10: ĐỊNH HƯỚNG PHÁT TRIỂN
* **Người trình bày:** Nguyễn Trần Bảo Thái  
* **Thời lượng:** ~1 phút  
* **Hành động:** Nêu 3 định hướng công nghệ tiếp theo.

> *"Từ những kết quả đã được chứng minh ở giai đoạn M1, định hướng hoàn thiện hệ thống trong giai đoạn M2 bao gồm 3 mục tiêu lớn:*  
> * * **Thứ nhất — Mở rộng giao dịch ghi phân tán (M2 Scope):** Áp dụng giao thức Two-Phase Commit (2PC) hoặc Saga Pattern để xử lý các giao dịch giỏ hàng, trừ tồn kho và thanh toán xuyên suốt giữa 2 site mà vẫn bảo đảm tính nhất quán dữ liệu.*  
> * * **Thứ hai — Triển khai Sharding cho MongoDB:** Khi dữ liệu log và review tăng trưởng lên hàng triệu bản ghi, cấu hình MongoDB Sharded Cluster theo vùng địa lý để phân bổ tải đọc ghi.*  
> * * **Thứ ba — Tích hợp CDC (Change Data Capture) thời gian thực:** Chuyển đổi cơ chế Polling ETL Worker hiện tại sang mô hình CDC liên tục bằng công nghệ Debezium và Apache Kafka."*

---

### 🎙️ SLIDE 11: KẾT LUẬN & CHUYỂN TIẾP SANG DEMO
* **Người trình bày:** Nguyễn Trần Bảo Thái  
* **Thời lượng:** ~45 giây  
* **Hành động:** Cảm ơn thầy, mở terminal chuẩn bị demo trực tiếp.

> *"Tóm lại, đề tài của nhóm đã hiện thực hóa thành công một hệ thống cơ sở dữ liệu hoàn chỉnh: vừa kết hợp đa mô hình lưu trữ Polyglot (PostgreSQL + MongoDB + MinIO), vừa phân tán dữ liệu thực tế trên 2 máy vật lý thông qua Tailscale VPN và PostgreSQL FDW, đáp ứng tính nhất quán, bảo mật và khả năng chịu lỗi cao.*  
> *Nhóm em xin chân thành cảm ơn thầy Văn Thế Thành và các bạn đã chú ý lắng nghe!*  
> *Sau đây, nhóm xin phép chuyển sang **Phần Demo trực tiếp trên hệ thống** để kính mời thầy kiểm chứng việc phân mảnh và FDW đọc dữ liệu thời gian thực giữa hai site!"*

---

### 💡 HƯỚNG DẪN THAO TÁC KHI BẮT ĐẦU DEMO CHO GIẢNG VIÊN XEM:
1. **Thao tác 1 (Ghi tại Site B):** Mở terminal Site B gõ lệnh thêm 1 sản phẩm:
   ```sql
   INSERT INTO product(seller_id, category_id, title, price, quantity)
   VALUES (202, 1, 'San pham Demo Site B', 120000, 1) RETURNING product_id, site_id;
   ```
   *(Chỉ vào màn hình cho thầy thấy: Sản phẩm sinh ra mang ID chẵn và `site_id = B`)*.
2. **Thao tác 2 (Đọc tại Site A):** Mở terminal Site A gõ:
   ```sql
   SELECT product_id, title, price, site_id FROM v_product WHERE product_id = [ID_vừa_tạo];
   ```
   *(Cho thầy thấy: Dữ liệu Site B lập tức xuất hiện tại Site A qua FDW)*.
3. **Thao tác 3 (Trình chiếu API):** Mở trình duyệt `http://127.0.0.1:57480/docs` thực hiện `GET /products` xem kết quả hợp nhất.

