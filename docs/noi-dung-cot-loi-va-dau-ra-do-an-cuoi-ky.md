# TỔNG HỢP KIẾN THỨC CỐT LÕI (LECT 01 - LECT 08) VÀ ĐẦU RA ĐỒ ÁN CUỐI KỲ

> **Môn học:** Cơ sở dữ liệu Nâng cao / CSDL Phân tán & Hiện đại  
> **Tài liệu tham chiếu:** 8 Bài giảng (Lect 01 đến Lect 08)  
> **Mục tiêu tài liệu:** Tổng hợp toàn bộ hệ thống kiến thức lý thuyết & thực hành trong môn học, từ đó quy chiếu và xác định các tiêu chuẩn đầu ra bắt buộc cho Đồ án cuối kỳ.

---

## PHẦN 1: TỔNG HỢP NỘI DUNG CỐT LÕI CỦA 8 BÀI GIẢNG

---

### 1. Lect 01 - Cơ sở Dữ liệu Phân tán (Distributed Database - DDB)

* **Khái niệm & Bản chất**: CSDL phân tán là tập hợp dữ liệu thuộc cùng một hệ thống về mặt logic nhưng được lưu trữ vật lý tại nhiều vị trí (site) khác nhau trên mạng máy tính. Mỗi site có khả năng xử lý tự trị (local autonomy).
* **Động lực & Nguyên tắc**: Kết hợp giữa **Công nghệ CSDL** (tích hợp dữ liệu) và **Mạng máy tính** (phân tán dữ liệu), dựa trên nguyên lý: *Tích hợp không đồng nghĩa với Tập trung (Integration $\neq$ Centralization)*.
* **Hệ Quản trị CSDL Phân tán (D-DBMS)**:
  * **Thành phần chính**: Database (DB), Data Communication (DC), Data Dictionary (DD), Distributed DB (DDB).
  * **Phân loại**: D-DBMS Đồng nhất (Homogeneous) và Không đồng nhất (Heterogeneous - khác nhau về DBMS, OS hoặc mô hình dữ liệu).
* **Kiến trúc Tham khảo (Referential Architecture)**:
  $$\text{Global Schema} \longrightarrow \text{Fragmentation Schema} \longrightarrow \text{Allocation Schema} \longrightarrow \text{Local Mapping Schema}$$
* **4 Mức Trong suốt Phân tán (Distributed Transparency)**:
  1. *Trong suốt phân mảnh (Fragmentation Transparency)*: Người dùng truy vấn trên lược đồ toàn cục, không cần biết dữ liệu bị phân mảnh ra sao.
  2. *Trong suốt vị trí (Location Transparency)*: Người dùng truy vấn trên tên các mảnh, không cần biết mảnh nằm ở site nào.
  3. *Trong suốt nhân bản (Replication Transparency)*: Che khuất sự tồn tại của các bản sao dữ liệu (replica).
  4. *Trong suốt ánh xạ cục bộ (Local Mapping Transparency)*: Người dùng phải chỉ rõ tên mảnh, tên site và các câu lệnh truyền dữ liệu giữa các site.
* **Phân mảnh Dữ liệu (Data Fragmentation)**:
  * **Phân mảnh ngang chính (Primary Horizontal)**: Phân chia các dòng dựa trên vị từ định tính của chính quan hệ đó.
  * **Phân mảnh ngang dẫn xuất (Derived Horizontal)**: Phân chia dòng của quan hệ thành viên dựa trên phân mảnh của quan hệ chủ (thông qua phép $\bowtie$).
  * **Phân mảnh dọc (Vertical)**: Phân chia các cột (thuộc tính), bắt buộc phải giữ lại **Khóa chính (Primary Key)** ở mỗi mảnh để phục vụ tái tạo.
  * **Phân mảnh hỗn hợp (Mixed/Hybrid)**: Kết hợp cả phân mảnh ngang và phân mảnh dọc.
* **Điều kiện phân mảnh hợp lệ**:
  * *Điều kiện tái tạo (Reconstruction)*: Phải có phép toán quan hệ ($\cup$ cho ngang, $\bowtie$ cho dọc) để khôi phục lại quan hệ ban đầu.
  * *Điều kiện tách biệt (Disjointness)*: Dữ liệu ở mảnh này không lặp lại ở mảnh khác (trừ thuộc tính khóa trong phân mảnh dọc).

---

### 2. Lect 02 - Thiết kế CSDL & Chuẩn hóa (Physical Design & Normalization)

* **Thiết kế Vật lý & Chỉ mục (Index)**:
  * Cấu trúc lưu trữ trường, bản ghi vật lý, khối dữ liệu (block/page).
  * **Clustered Index**: Sắp xếp thứ tự vật lý của dữ liệu trên đĩa trùng với thứ tự chỉ mục (mỗi bảng chỉ có 1 Clustered Index).
  * **Non-Clustered Index**: Cấu trúc chỉ mục tách rời, chứa con trỏ trỏ đến vị trí dữ liệu vật lý.
* **Lý thuyết Phụ thuộc Hàm (Functional Dependency - FD)**:
  * Định nghĩa $X \rightarrow Y$: Nếu hai bộ trùng nhau trên $X$ thì bắt buộc phải trùng nhau trên $Y$.
  * **Hệ tiên đề Armstrong**: Tính phản xạ, Tính tăng trưởng, Tính bắc cầu.
  * **Bao đóng của tập thuộc tính ($X^+$)**: Tập tất cả các thuộc tính có thể suy ra từ $X$ dựa vào tập phụ thuộc hàm $F$.
* **Thuật toán Tìm Khóa & Phủ Tối thiểu**:
  * Phân tích các tập thuộc tính: Thuộc tính chỉ xuất hiện ở vế trái ($L$), vế phải ($R$), cả hai vế ($LR$), hoặc không xuất hiện ($N$).
  * Thuật toán tìm tất cả khóa dựa trên $X^+ = U$.
  * **Phủ tối thiểu (Minimal Cover)**: Vế phải chỉ chứa 1 thuộc tính, không chứa thuộc tính dư thừa ở vế trái, không chứa phụ thuộc hàm dư thừa.
* **Các Dạng Chuẩn & Thuật toán Phân rã**:
  * **1NF**: Giá trị thuộc tính phải là nguyên tố (atomic).
  * **2NF**: Đạt 1NF và mọi thuộc tính không khóa phải phụ thuộc đầy đủ vào khóa chính (không phụ thuộc riêng phần).
  * **3NF**: Đạt 2NF và mọi thuộc tính không khóa không phụ thuộc bắc cầu vào khóa chính.
  * **BCNF**: Với mọi $X \rightarrow Y \in F^+$, $X$ bắt buộc phải là siêu khóa (Superkey).
  * **Phép tách bảo toàn thông tin (Lossless Join)**: Dựa trên Định lý Delobel ($R_1 \cap R_2 \rightarrow R_1$ hoặc $R_1 \cap R_2 \rightarrow R_2$).
  * **Phụ thuộc đa trị (Multivalued Dependency - MVD)**: $X \rightarrow\rightarrow Y$ và Hệ tiên đề MVD (Luật bù, Luật tăng trưởng, Luật bắc cầu...).

---

### 3. Lect 03 - NoSQL & CSDL Hướng Tài liệu (MongoDB Overview)

* **Tổng quan NoSQL**:
  * Giải quyết bài toán **Big Data**: Dung lượng lớn (Volume), Tốc độ cao (Velocity), Đa dạng cấu trúc (Variety).
  * **Schema linh hoạt (Dynamic Schema)**: Không bắt buộc định nghĩa trước các cột hay kiểu dữ liệu.
  * **Mở rộng ngang (Horizontal Scalability)**: Dễ dàng thêm node vào cluster.
  * Đánh đổi tính bảo chứng ACID truyền thống lấy hiệu năng và khả năng sẵn sàng cao (BASE model).
* **Kiến trúc dữ liệu trong MongoDB**:
  * **Document**: Đơn vị lưu trữ cơ bản, tổ chức dưới dạng các cặp `key-value` theo định dạng **BSON** (Binary JSON).
  * **Collection**: Tập hợp các Document (tương đương Bảng trong RDBMS).
  * **Database**: Chứa nhiều Collection.
  * **Trường `_id`**: Khóa chính bắt buộc trong mọi Document (mặc định dạng `ObjectId`).
* **So sánh Tương quan SQL vs. MongoDB**:
  * `Table` $\rightarrow$ `Collection`
  * `Row / Tuple` $\rightarrow$ `Document`
  * `Column` $\rightarrow$ `Field`
  * `Primary Key` $\rightarrow$ `_id`
  * `JOIN` $\rightarrow$ Không hỗ trợ trực tiếp (thay bằng Embedded Documents hoặc `$lookup`).
* **2 Mô hình Thiết kế Dữ liệu trong MongoDB**:
  1. **Embedded Data Models (Mô hình Nhúng)**: Đưa tài liệu con vào bên trong tài liệu cha. Tối ưu cho truy vấn đọc nhanh, tránh phải JOIN.
  2. **References Data Models (Mô hình Tham chiếu)**: Lưu `_id` của tài liệu liên quan. Phù hợp cho mối quan hệ $N-N$ hoặc khi dữ liệu con quá lớn (vượt giới hạn 16MB/document).

---

### 4. Lect 04 - Chỉ mục trong MongoDB (MongoDB Indexing)

* **Mục đích của Index**: Giúp MongoDB thực hiện câu truy vấn hiệu quả, tránh việc phải quét toàn bộ tập dữ liệu (**Full Collection Scan**).
* **Chi phí đánh đổi**: Tăng tốc độ đọc (`find`), nhưng tiêu tốn RAM/đĩa cứng và làm chậm tác vụ ghi (`insert`, `update`, `delete`) do phải cập nhật cây chỉ mục.
* **Các loại chỉ mục cơ bản**:
  * **Single Field Index**: Đánh chỉ mục trên 1 trường (ví dụ: `{ name: 1 }` tăng dần, `-1` giảm dần).
  * **Compound Index**: Đánh chỉ mục trên nhiều trường (thứ tự các trường trong chỉ mục rất quan trọng).
  * **Unique Index**: Đảm bảo giá trị trường chỉ mục không bị trùng lặp (ví dụ: `{ email: 1 }, { unique: true }`).
  * **Sparse Index**: Chỉ đánh chỉ mục trên các document có chứa trường đó (tiết kiệm bộ nhớ).
* **Các câu lệnh quản lý chỉ mục**:
  * Tạo chỉ mục: `db.collection.createIndex(keys, options)`
  * Xem danh sách chỉ mục: `db.collection.getIndexes()`
  * Xóa chỉ mục: `db.collection.dropIndex("index_name")`
  * Re-index lại collection: `db.collection.reIndex()`

---

### 5. Lect 05 & Lect 06 - CSDL Đồ thị & Ngôn ngữ Cypher (Neo4j & Graph DB)

* **Khái niệm CSDL Đồ thị (Graph Database)**: Lưu trữ và biểu diễn dữ liệu dưới dạng mạng lưới các thực thể và mối liên kết. Rất mạnh mẽ trong việc xử lý dữ liệu phi cấu trúc có mối quan hệ phức tạp, nhiều cấp (Mạng xã hội, Hệ thống gợi ý, Logistic, Sinh học).
* **Mô hình Labeled Property Graph**:
  * **Node (Nút)**: Biểu diễn đối tượng/thực thể (có thể chứa một hoặc nhiều **Label**).
  * **Relationship (Mối quan hệ)**: Kết nối giữa 2 Node, bắt buộc có hướng và **Type** (tên mối quan hệ).
  * **Property (Thuộc tính)**: Các cặp `key-value` gán trên Node hoặc Relationship.
* **Ngôn ngữ truy vấn Cypher trong Neo4j**:
  * **Tạo dữ liệu**:
    * Tạo Node: `CREATE (p:Person {id: 1, name: 'Jennifer'})`
    * Ràng buộc duy nhất: `CREATE CONSTRAINT ON (p:Person) ASSERT p.id IS UNIQUE`
    * Tạo Relationship: `MATCH (a:Person), (b:Person) WHERE a.name='Andy' AND b.name='Michael' CREATE (a)-[r:KNOWS {since: 2018}]->(b)`
  * **Truy vấn & Lọc dữ liệu**:
    * Tìm kiếm mẫu (Pattern Matching): `MATCH (p:Person)-[:WORKS_FOR]->(c:Company) RETURN p, c`
    * Lọc: `WHERE`, `IN`, `EXISTS()`, `NOT EXISTS()`
    * Phân trang/Sắp xếp: `ORDER BY ... DESC`, `LIMIT 3`, `SKIP`
    * Loại bỏ trùng: `DISTINCT`
    * Chuyển tiếp danh sách: `WITH`, `UNWIND`
  * **Cập nhật & Xóa**:
    * Sửa thuộc tính: `SET p.birthdate = date('1980-01-01')`
    * Xóa thuộc tính: `REMOVE p.surname`
    * Xóa nút/mối quan hệ: `DELETE r`, `DELETE p`
    * Xóa nút kèm tất cả liên kết liên quan: `DETACH DELETE p`

---

### 6. Lect 07 - Lập trình Kết nối CSDL Đa Nền tảng (C# & Java Drivers)

* **Mục tiêu**: Xây dựng phần mềm ứng dụng thực tế kết nối và tương tác CRUD với CSDL NoSQL (MongoDB) và Graph DB (Neo4j).
* **Kết nối MongoDB trong C# (Windows Forms)**:
  * Bộ thư viện: `MongoDB.Driver`
  * Khởi tạo kết nối:
    ```csharp
    var client = new MongoClient("mongodb://localhost:27017");
    var db = client.GetDatabase("QLNhanVien");
    var collection = db.GetCollection<BsonDocument>("NhanVien");
    ```
  * Lập trình CRUD:
    * Duyệt: `collection.FindAll()`
    * Thêm: `collection.Insert(bsonDoc)`
    * Sửa: `collection.Update(query, update)`
    * Xóa: `collection.Remove(query)`
* **Kết nối MongoDB trong Java (SWT / Swing)**:
  * Thư viện: `mongo-java-driver-x.x.x.jar`, `json-simple-x.x.x.jar`
  * Đối tượng chính: `MongoClient`, `MongoDatabase`, `MongoCollection<Document>`
  * Câu lệnh: `collection.find()`, `collection.insertOne()`, `collection.updateOne(eq("MANV", id), new Document("$set", ...))`, `collection.deleteOne(eq("MANV", id))`
* **Kết nối Neo4j trong Java**:
  * Thư viện: `neo4j-java-driver`
  * Đối tượng kết nối: `Driver driver = GraphDatabase.driver("bolt://localhost:7687", AuthTokens.basic("neo4j", "password"))`
  * Quản lý Session & Transaction: `try (Session session = driver.session()) { ... }`
  * Thực thi Cypher kèm tham số:
    ```java
    Map<String, Object> params = new HashMap<>();
    params.put("name", "Lan");
    Result result = session.run("MATCH (p:Person {name: $name})-[r:IS_FRIENDS_WITH]->(q) RETURN q.name AS name", params);
    while(result.hasNext()) {
        Record record = result.next();
        System.out.println(record.get("name").asString());
    }
    ```

---

### 7. Lect 08 - CSDL Không gian - Thời gian & Mô hình Đối tượng (ODL/OQL & Spatial/Temporal DB)

* **Ngôn ngữ Mô tả Đối tượng ODL (Object Definition Language - ODMG)**:
  * Dùng xác định mô hình logic cho CSDL Hướng đối tượng (OODBMS).
  * Khai báo lớp: `class Person (extent persons key ssn) { attribute string name; relationship Person spouse inverse Person::spouse; };`
  * Kế thừa: `class Student extends Person`
  * Lớp trừu tượng: `abstract class Student`
* **Ngôn ngữ Truy vấn Đối tượng OQL (Object Query Language)**:
  * Cú pháp `SELECT - FROM - WHERE` tương tự SQL nhưng làm việc trên các Đối tượng (Objects) và Tập hợp (Collections).
  * **Không sử dụng JOIN truyền thống**: Truy xuất trực tiếp thuộc tính và mối quan hệ bằng dấu chấm (Con trỏ/Reference):
    ```sql
    SELECT c.crse_title, c.credit_hrs 
    FROM courses c 
    WHERE c.crse_code = "ADB"
    ```
  * Hỗ trợ cấu trúc trả về phức tạp: `SELECT DISTINCT struct(name: s.name, gpa: s.gpa) FROM students s`
  * Hàm gom nhóm và nhóm dữ liệu: `COUNT`, `AVG`, `SUM`, `GROUP BY`.
* **CSDL Không gian & Thời gian (Spatial & Temporal Databases)**:
  * **CSDL Thời gian (Temporal DB)**: Lưu trữ lịch sử biến đổi của dữ liệu theo trục thời gian (Valid Time, Transaction Time, Bi-temporal).
  * **CSDL Không gian (Spatial DB)**: Lưu trữ dữ liệu hình học (Point, Line, Polygon, Raster, Vector). Xử lý các bài toán tìm kiếm vị trí (Nearest Neighbor - ví dụ: Tìm cây ATM gần nhất).
  * **CSDL Không - Thời gian (Spatio-Temporal DB)**: Quản lý đối tượng di chuyển theo thời gian (Tracking, GPS logistics).

---

## PHẦN 2: CHUẨN ĐẦU RA VÀ YÊU CẦU BẮT BUỘC ĐỐI VỚI ĐỒ ÁN CUỐI KỲ

---

### 1. Yêu cầu Đầu ra Tối thượng: Hợp nhất CSDL Đa Mô hình (Multi-model Database Integration)

Mục tiêu cốt lõi của môn học là sinh viên không chỉ sử dụng thành thạo từng hệ quản trị CSDL riêng lẻ, mà phải có năng lực **Tích hợp và Hợp nhất 3 dạng dữ liệu khác nhau** trong cùng một Hệ thống / Đồ án thực tế:

```
                      +------------------------------------------+
                      |         HỆ THỐNG ỨNG DỤNG THỰC TẾ        |
                      |    (C# WinForms / Java SWT / Web App)    |
                      +--------------------+---------------------+
                                           |
            +------------------------------+------------------------------+
            |                              |                              |
            v                              v                              v
+-----------------------+      +-----------------------+      +-----------------------+
| DỮ LIỆU CÓ CẤU TRÚC  |      | DỮ LIỆU BÁN CẤU TRÚC  |      | DỮ LIỆU PHI CẤU TRÚC  |
|  (Structured Data)    |      |  (Semi-structured)    |      |    (Unstructured)     |
|                       |      |                       |      |                       |
|   SQL Server / RDBMS  |      |   MongoDB / Document  |      |   Neo4j / Graph DB    |
| - Nghiệp vụ lõi       |      | - Thuộc tính linh hoạt|      | - Mạng lưới liên kết  |
| - Tài khoản, Hóa đơn  |      | - Log, Review, Giỏ hàng|      | - Gợi ý, Bạn bè       |
+-----------------------+      +-----------------------+      +-----------------------+
```

---

### 2. Yêu cầu Kiến trúc & Phân bổ Dữ liệu trong Đồ án

Đồ án cuối kỳ bắt buộc phải xây dựng trên một **Miền bài toán thực tế** (Ví dụ: Hệ thống Thương mại Điện tử, Quản lý Bệnh viện & Hồ sơ Bệnh án, Mạng xã hội & Khóa học Trực tuyến, Quản lý Logistics & Chuỗi Cung ứng). Trong đó, dữ liệu phải được phân quặng và lưu trữ đúng mô hình:

#### A. Khối Dữ liệu Có cấu trúc (RDBMS - SQL Server)
* **Nhiệm vụ**: Lưu trữ dữ liệu quan trọng yêu cầu tính toàn vẹn cao, ràng buộc chặt chẽ và tuân thủ ACID.
* **Yêu cầu thực hiện trong Đồ án**:
  * Thiết kế sơ đồ ERD/Lược đồ quan hệ đạt chuẩn **3NF** hoặc **BCNF**.
  * Thiết kế các **Clustered Index** và **Non-Clustered Index** để tối ưu hóa truy vấn.
  * *(Mở rộng/Điểm thưởng)*: Áp dụng kỹ thuật **Phân mảnh CSDL Phân tán** (Phân mảnh ngang hoặc phân mảnh dọc) trên ít nhất 2 Site và viết truy vấn minh họa tính **Trong suốt phân tán**.

#### B. Khối Dữ liệu Bán cấu trúc (NoSQL - MongoDB)
* **Nhiệm vụ**: Lưu trữ dữ liệu có cấu trúc biến đổi, schema động, chứa nhiều thuộc tính con nhúng nhiều cấp.
* **Yêu cầu thực hiện trong Đồ án**:
  * Thiết kế các **Collection** áp dụng linh hoạt **Embedded Data Model** (Nhúng comment, chi tiết cấu hình sản phẩm...) và **Reference Data Model**.
  * Đánh chỉ mục nâng cao (**Compound Index**, **Unique Index**, **Sparse Index**) để tối ưu tốc độ đọc.
  * Thực hiện các truy vấn phức tạp, lọc mảng và sử dụng Aggregation Pipeline.

#### C. Khối Dữ liệu Phi cấu trúc / Mạng lưới Liên kết (Graph DB - Neo4j)
* **Nhiệm vụ**: Lưu trữ các mối quan hệ đa chiều, mạng lưới tương tác phức tạp mà CSDL quan hệ khó xử lý hiệu quả.
* **Yêu cầu thực hiện trong Đồ án**:
  * Xây dựng mô hình **Labeled Property Graph**: Định nghĩa các **Node**, **Label**, **Relationship**, **Property**.
  * Viết các câu lệnh **Cypher** nâng cao: Viết các thuật toán tìm kiếm đường đi, gợi ý sản phẩm/bạn bè (Recommender System) sử dụng `MATCH`, `WITH`, `UNWIND`, `EXISTS`, `LIMIT`.
  * Thiết lập ràng buộc duy nhất (`ASSERT ... IS UNIQUE`).

---

### 3. Yêu cầu Lập trình Ứng dụng & Giao diện (Software Application Requirement)

* **Công nghệ phát triển**: C# (Windows Forms / WPF / ASP.NET) hoặc Java (SWT / Swing / Spring Boot).
* **Tích hợp Thư viện Driver**:
  * Sử dụng thư viện chính thức: `MongoDB.Driver` (C#) / `mongo-java-driver` (Java) và `Neo4j.Driver`.
* **Chức năng Giao diện**:
  * Xây dựng màn hình quản lý cho phép thực hiện đầy đủ các thao tác **CRUD** (Create, Read, Update, Delete) trên cả 3 CSDL.
  * **Tích hợp dữ liệu đa nguồn**: Một chức năng nghiệp vụ trên giao diện có thể kéo dữ liệu từ SQL Server, kết hợp với thông tin chi tiết từ MongoDB và hiển thị danh sách gợi ý liên quan từ Neo4j.
  * Bắt lỗi ngoại lệ, quản lý luồng kết nối (Connection/Session/Transaction) an toàn và tối ưu.

---

### 4. Bảng Tiêu chí Đánh giá Đồ án Cuối kỳ (Checklist Chấm điểm)

| STT | Hạng mục Đánh giá | Trọng số | Yêu cầu Kỹ thuật Cụ thể |
| :-: | :--- | :-: | :--- |
| **1** | **Thiết kế CSDL Quan hệ (SQL Server)** | 20% | Chuẩn hóa 3NF/BCNF, tạo Index tối ưu, (Bonus: Demo Phân mảnh & Truy vấn phân tán). |
| **2** | **Thiết kế CSDL MongoDB** | 20% | Thiết kế Document/Collection hợp lý (Embedded/Reference), đánh chỉ mục Compound/Sparse Index. |
| **3** | **Thiết kế CSDL Neo4j** | 20% | Biểu diễn mô hình Đồ thị Node/Relationship, viết truy vấn Cypher phức tạp (Gợi ý/Mạng lưới). |
| **4** | **Lập trình Kết nối & Hợp nhất Dữ liệu** | 25% | Dùng Driver C#/Java chính thức, đồng bộ CRUD đa CSDL, hiển thị dữ liệu hợp nhất trên giao diện. |
| **5** | **Báo cáo & Demo** | 15% | Báo cáo Markdown/PDF chi tiết, slide thuyết trình và demo chạy chương trình mượt mà. |

---

### 5. Kết luận

Để hoàn tất xuất sắc môn học này, đồ án cuối kỳ không chỉ đơn thuần là một bài tập làm phần mềm CRUD thông thường, mà là một **sản phẩm tích hợp công nghệ CSDL hiện đại**. Việc nắm vững cả 8 bài giảng sẽ cung cấp đầy đủ nền tảng từ lý thuyết phân mảnh, thiết kế chuẩn hóa, đến kỹ năng thực hành thao tác trên MongoDB, Neo4j và lập trình ứng dụng kết nối.
