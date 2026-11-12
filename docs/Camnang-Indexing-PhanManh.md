Cẩm Nang Áp Dụng Chỉ Mục (Index) và Phân Mảnh Dữ Liệu Trong Thiết Kế Hệ Thống CSDL

Trong các hệ thống phần mềm quy mô lớn, việc tối ưu hóa hiệu năng truy vấn và mở rộng khả năng lưu trữ là đòi hỏi tiên quyết. Hai kỹ thuật nền tảng được áp dụng phổ biến nhất hiện nay là Phân mảnh dữ liệu (Data Fragmentation) trong kiến trúc Cơ sở dữ liệu phân tán và Đánh chỉ mục (Indexing) trong các cơ sở dữ liệu lưu trữ tài liệu như MongoDB. Cẩm nang kỹ thuật này được tổng hợp và hệ thống hóa dựa trên hai bài giảng chuyên sâu ("Lect 01 - Distributed DB" và "Lect 04 - Chỉ mục trong MongoDB"), mang lại khung hướng dẫn thực hành chuẩn xác cho các kiến trúc sư và kỹ sư cơ sở dữ liệu.

1. Chiến Lược Phân Mảnh Dữ Liệu Trong Cơ Sở Dữ Liệu Phân Tán

Theo định nghĩa trong tài liệu về Cơ sở dữ liệu phân tán, một CSDL phân tán (Distributed Database - DDB) là tập hợp dữ liệu về mặt luận lý thuộc cùng một hệ thống nhưng được đặt tại nhiều trạm (site) khác nhau trên một mạng máy tính. Mỗi trạm có khả năng xử lý tự trị để thực hiện các ứng dụng cục bộ (chỉ sử dụng dữ liệu tại trạm đó) và đồng thời tham gia thực hiện ít nhất một ứng dụng toàn cục (sử dụng dữ liệu từ hai trạm trở lên).

Phân mảnh dữ liệu là quá trình chia quan hệ toàn cục R thành các quan hệ con R_1, R_2, \dots, R_n (gọi là các mảnh). Mục tiêu của phân mảnh là đặt dữ liệu gần nơi có tần suất truy cập cao nhất, nhằm tăng tính tự trị cục bộ, giảm thiểu chi phí truyền thông trên mạng và tăng khả năng xử lý song song.

1.1 Cấu Trúc Hệ Quản Trị CSDL Phân Tán (D-DBMS)

Một Hệ quản trị CSDL phân tán (D-DBMS) bao gồm bốn thành phần chức năng cơ bản được phân bố tại mỗi trạm:

* Quản trị CSDL (DB - Database Management): Phụ trách quản lý dữ liệu cục bộ và thực hiện các yêu cầu truy xuất từ ứng dụng.
* Truyền thông dữ liệu (DC - Data Communication): Nhận yêu cầu truy xuất dữ liệu từ các thiết bị đầu cuối và truyền nhận dữ liệu/kết quả giữa các trạm.
* Từ điển dữ liệu (DD - Data Dictionary): Lưu trữ thông tin meta-data về các đối tượng CSDL và vị trí phân tán của dữ liệu trên toàn hệ thống.
* CSDL phân tán (DDB - Distributed Database): Thực hiện quản lý sự liên lạc và tương tác dữ liệu giữa các nơi.

Về mặt kiến trúc, D-DBMS được chia thành D-DBMS đồng nhất (Homogeneous) khi các DBMS cục bộ tại tất cả các trạm hoàn toàn giống nhau, và D-DBMS không đồng nhất (Heterogeneous) khi có ít nhất hai DBMS cục bộ khác nhau đòi hỏi tầng chuyển đổi mô hình dữ liệu trung gian.

1.2 Phân Loại Các Hình Thức Phân Mảnh Dữ Liệu

Tài liệu thiết lập bốn hình thức phân mảnh cơ bản dựa trên các phép toán đại số quan hệ:

1. Phân mảnh ngang chính (Primary Horizontal Fragmentation): Phân chia các bộ (tuples) của quan hệ toàn cục thành các tập hợp con dựa vào các vị từ định tính (điều kiện chọn) trên chính thuộc tính của quan hệ đó. Phép toán sử dụng là phép chọn \sigma. Ví dụ với quan hệ supplier(snum, name, city):
  * \text{supplier}_1 = \sigma_{\text{city} = \text{'SF'}} \text{supplier} (vị từ q_1: \text{city} = \text{'SF'})
  * \text{supplier}_2 = \sigma_{\text{city} = \text{'LA'}} \text{supplier} (vị từ q_2: \text{city} = \text{'LA'})
2. Phân mảnh ngang dẫn xuất (Derived Horizontal Fragmentation): Phân chia các bộ của một quan hệ toàn cục (quan hệ thành viên) dựa vào phân mảnh ngang của một quan hệ khác (quan hệ chủ). Vị từ định tính bao gồm điều kiện kết (\bowtie) và vị từ của mảnh chủ. Ví dụ quan hệ supply(snum, pnum, deptnum, quan) phân mảnh theo supplier:
  * \text{supply}_1 = \text{supply} \bowtie_{\text{snum = snum}} \text{supplier}_1
  * \text{supply}_2 = \text{supply} \bowtie_{\text{snum = snum}} \text{supplier}_2
3. Phân mảnh dọc (Vertical Fragmentation): Phân chia tập thuộc tính của quan hệ toàn cục thành các tập thuộc tính con bằng phép chiếu \Pi.
  * Phân mảnh dọc không dư thừa: Thuộc tính khóa chính được lặp lại ở tất cả các mảnh để phục vụ liên kết, các thuộc tính còn lại phân tách hoàn toàn. Ví dụ: \text{emp}_1 = \Pi_{\text{empnum, name, mgrnum, deptnum}} \text{emp} và \text{emp}_2 = \Pi_{\text{empnum, sal, tax}} \text{emp}.
  * Phân mảnh dọc dư thừa: Lặp lại một số thuộc tính không phải khóa giữa các mảnh nhằm tối ưu truy vấn chỉ đọc tại chỗ.
4. Phân mảnh hỗn hợp (Mixed/Hybrid Fragmentation): Kết hợp áp dụng phân mảnh dọc trên một mảnh ngang hoặc phân mảnh ngang trên một mảnh dọc, tạo thành cấu trúc cây phân mảnh nhiều cấp.

1.3 Ba Điều Kiện Đúng Đắn Của Phân Mảnh

Để đảm bảo quá trình phân rã không làm thất thoát thông tin hoặc biến đổi ngữ nghĩa dữ liệu, quy trình thiết kế phân mảnh bắt buộc phải đáp ứng ba điều kiện nghiêm ngặt:

Điều kiện kiểm tra	Yêu cầu kỹ thuật & Công thức	Áp dụng cho Phân mảnh Ngang	Áp dụng cho Phân mảnh Dọc
Tính đầy đủ (Completeness)	Mọi mục dữ liệu trong quan hệ toàn cục R phải có mặt trong ít nhất một mảnh con R_i.	Mọi bộ dữ liệu đều phải thỏa mãn ít nhất một vị từ định tính của phép chọn.	Mọi thuộc tính của R phải xuất hiện trong ít nhất một tập thuộc tính được chiếu.
Tính tái tạo (Reconstruction)	Tồn tại phép toán quan hệ \nabla để tái tạo chính xác R từ các mảnh R_i.	Phép Hợp quan hệ (\cup): R = R_1 \cup R_2 \cup \dots \cup R_n.	Phép Kết tự nhiên (\bowtie) theo thuộc tính khóa chính: R = R_1 \bowtie R_2 \bowtie \dots \bowtie R_n.
Tính tách biệt (Disjointness)	Nếu mục dữ liệu có trong R_i thì không được xuất hiện trong R_k (k \neq i).	Tuân thủ tuyệt đối: các bộ dữ liệu giữa các mảnh ngang không trùng lặp.	Thường bị vi phạm vì bắt buộc phải lặp lại thuộc tính khóa chính ở các mảnh.

1.4 Các Mức Trong Suốt Phân Tán

Tính trong suốt là khả năng che giấu sự phức tạp của hạ tầng phân tán đối với người dùng và lập trình viên ứng dụng. Hệ thống hỗ trợ ba mức trong suốt:

* Mức 1 - Trong suốt phân mảnh (Fragmentation Transparency): Mức cao nhất. Người dùng truy vấn trực tiếp trên lược đồ toàn cục R. DDBMS tự động ánh xạ truy vấn xuống các mảnh và vị trí tương ứng.
* Mức 2 - Trong suốt vị trí (Location Transparency): Người dùng phải sử dụng tên các mảnh dữ liệu trong câu lệnh (ví dụ: supplier1, supplier2), nhưng không cần biết các mảnh đó được đặt tại trạm vật lý nào.
* Mức 3 - Trong suốt ánh xạ cục bộ (Local Mapping Transparency): Mức thấp nhất. Câu lệnh phải chỉ rõ tên mảnh và địa chỉ trạm vật lý (ví dụ: SUPPLIER1 at site 1, SUPPLIER2 at site 3).

1.5 Quy Trình Xử Lý Truy Vấn Đọc Và Cập Nhật Dữ Liệu Phân Tán

Đối với các ứng dụng giao tác trên CSDL phân tán, tài liệu chỉ rõ hai chiến lược xử lý:

* Ứng dụng chỉ đọc (Read-only): Khi thông tin đầu vào trùng với vị từ định tính của mảnh, DDBMS sẽ điều hướng câu lệnh truy vấn đến đúng trạm chứa mảnh đó, loại bỏ việc quét dữ liệu trên toàn bộ các trạm còn lại.
* Ứng dụng cập nhật (Update): Việc thêm, xóa, sửa phải bảo đảm toàn vẹn dữ liệu. Với hệ thống có bản nhân (replica), quy tắc Read-one Write-all được áp dụng (đọc trên 1 trạm bất kỳ, nhưng cập nhật phải ghi lên tất cả trạm chứa bản nhân).
* Cập nhật làm thay đổi vị từ định tính: Khi câu lệnh UPDATE làm thay đổi giá trị thuộc tính định tính (ví dụ sửa deptnum từ 3 sang 15), dữ liệu không thể sửa trực tiếp tại chỗ. DDBMS phải thực thi chuỗi tác vụ bao gồm: đọc dữ liệu cũ, thực hiện DELETE bộ dữ liệu tại mảnh thuộc phòng 3, và thực hiện INSERT bộ dữ liệu mới vào mảnh thuộc phòng 15.

2. Kỹ Thuật Đánh Chỉ Mục (Index) Tối Ưu Hóa Truy Xuất Trong MongoDB

Ở cấp độ lưu trữ tại từng trạm hoặc từng nút CSDL, chỉ mục (Index) là cấu trúc dữ liệu lưu trữ trên ổ cứng tương ứng với một collection nhằm mục đích gia tăng tốc độ truy xuất. Đánh chỉ mục là việc tạo ra cấu trúc chứa giá trị của field và con trỏ trỏ trực tiếp tới document liên quan.

2.1 Cấu Trúc B-Tree Và Tốc Độ Truy Xuất

MongoDB xây dựng chỉ mục dựa trên cấu trúc cây B-Tree. Sự khác biệt về độ phức tạp thuật toán được tài liệu mô tả rõ:

* Quét toàn bộ collection (COLLSCAN): Xảy ra khi không có chỉ mục. MongoDB phải kiểm tra lần lượt từng document. Độ phức tạp thời gian là O(n).
* Quét qua chỉ mục (IXSCAN): MongoDB duyệt trên cây B-Tree. Độ phức tạp thời gian giảm xuống O(\log_2 n). Với collection chứa 1.000.000 tài liệu, việc duyệt B-Tree chỉ mất tối đa khoảng 19 phép so sánh để định vị chính xác dữ liệu.

2.2 Các Loại Chỉ Mục Trong MongoDB

Tài liệu bài giảng MongoDB phân loại các dạng chỉ mục kỹ thuật như sau:

* Chỉ mục đơn (Single Field Index): Tạo trên 1 trường dữ liệu. Chỉ mục mặc định của MongoDB luôn là trường _id (chỉ mục duy nhất và không thể bị xóa). Chỉ mục đơn cũng có thể đánh trên các khóa bên trong văn bản nhúng (Embedded document keys), như Diachi.Quan hoặc Diachi.TP.
* Chỉ mục hỗn hợp (Compound Index): Đánh trên nhiều trường dữ liệu (ví dụ {state: 1, city: 1, pop: -1}). Thứ tự các trường quyết định khả năng hỗ trợ lọc và hỗ trợ phép sắp xếp (sort).
* Chỉ mục thưa thớt (Sparse Index): Chỉ chứa các đầu mục trỏ đến các document thực sự có chứa trường được đánh index. Những document bị thiếu trường này sẽ không được đưa vào chỉ mục, giúp tiết kiệm dung lượng bộ nhớ.
* Chỉ mục duy nhất (Unique Index): Đảm bảo không có hai document nào có giá trị khóa trùng lặp ({unique: true}).

2.3 Cú Pháp Lệnh Quản Trị Chỉ Mục

Các thao tác vận hành chỉ mục trên MongoDB được thực hiện thông qua bộ lệnh chuẩn sau:

// Khởi tạo chỉ mục đơn (1: tăng dần, -1: giảm dần)
db.user.createIndex({ name: 1 })

// Khởi tạo chỉ mục hỗn hợp trên trường thường và trường nhúng
db.user.createIndex({ name: 1, "address.city": -1 })

// Khởi tạo chỉ mục duy nhất
db.user.createIndex({ name: 1 }, { unique: true })

// Kiểm tra danh sách chỉ mục hiện có trên collection
db.user.getIndexes()

// Xóa chỉ mục theo tên chỉ mục
db.user.dropIndex("Diachi_1")

// Xóa và tạo lại tất cả chỉ mục (Lưu ý: Rất tốn chi phí, cần tránh sử dụng trên collection lớn)
db.collection.reIndex()


2.4 So Sánh Hiệu Suất Truy Vấn Qua Các Giai Đoạn Thực Thi (Execution Stages)

Thông qua câu lệnh phân tích .explain("executionStats"), tài liệu trình bày kết quả thử nghiệm thực nghiệm trên dữ liệu tài liệu zips.json với câu truy vấn: db.zips.find({state:'NY', city:'NEW YORK', pop:{'$gt':100000}}).sort({pop:-1}). Kết quả giữa 4 phương án đánh chỉ mục được tổng hợp chi tiết dưới đây:

Phương án thiết kế Index	Giai đoạn thực thi (Execution Stages)	Số tài liệu đã quét (totalDocsExamined)	Số khóa index kiểm tra (totalKeysExamined)	Xử lý Sắp xếp (SORT)	Thời gian thực thi (executionTimeMillis)
Cách 1: Chưa có Index	COLLSCAN \rightarrow SORT	29,353	0	Sắp xếp trong bộ nhớ (In-Memory Sort)	15 ms
Cách 2: Index đơn {state:1}	IXSCAN \rightarrow FETCH \rightarrow SORT	1,595	1,595	Sắp xếp trong bộ nhớ (In-Memory Sort)	6 ms
Cách 3: Index hỗn hợp {state:1, city:1}	IXSCAN \rightarrow FETCH \rightarrow SORT	40	40	Sắp xếp trong bộ nhớ (In-Memory Sort)	4 ms
Cách 4: Index phủ 3 trường {state:1, city:1, pop:1}	IXSCAN \rightarrow FETCH	2	2	Loại bỏ Stage SORT (Dùng thứ tự Index)	2 ms

3. Khung Nguyên Tắc & Ma Trận Ra Quyết Định Áp Dụng Cho Hệ Thống

Để áp dụng hiệu quả cả hai kỹ thuật Phân mảnh và Đánh chỉ mục vào một hệ thống cơ sở dữ liệu thực tế, nhà thiết kế hệ thống cần nắm vững ma trận nguyên tắc đánh đổi giữa tốc độ đọc, chi phí ghi và không gian lưu trữ.

3.1 Ma Trận Đánh Giá Khuyên Dùng Khi Tạo Index

Tài liệu bài giảng nhấn mạnh các quy tắc cốt lõi khi quyết định tạo chỉ mục:

Yếu tố hệ thống / Dữ liệu	Trường hợp Khuyên Dùng (NÊN)	Trường hợp Không Khuyên Dùng (KHÔNG NÊN)	Bản chất lý thuyết kỹ thuật
Tần suất Đọc / Ghi	Cơ sở dữ liệu cần Đọc nhiều - Ghi ít (Read-heavy, Write-light).	Bảng / Collection có các thao tác INSERT, UPDATE, DELETE xảy ra thường xuyên với tần suất lớn.	Khi dữ liệu thay đổi, MongoDB bắt buộc phải cập nhật và đánh lại toàn bộ cây B-Tree của chỉ mục, làm suy giảm tốc độ ghi.
Dung lượng Collection	Collection có kích thước lớn, lưu trữ hàng trăm nghìn bản ghi trở lên.	Các bảng nhỏ, số lượng bản ghi ít.	Chi phí duyệt cây chỉ mục B-Tree và giải mã con trỏ tài liệu không chênh lệch đáng kể so với việc quét trực tiếp toàn bộ bảng nhỏ.
Đặc tính dữ liệu NULL	Các trường dữ liệu có giá trị xác định rõ ràng (hoặc dùng Sparse Index).	Các cột / trường chứa một số lượng lớn giá trị NULL.	Đánh chỉ mục trên trường chứa quá nhiều NULL gây lãng phí dung lượng RAM/Disk cho bảng chỉ mục mà hiệu quả phân lọc kém.
Cấu trúc Chỉ mục hỗn hợp	Sắp xếp trường theo thứ tự: Trường lọc bằng trước \rightarrow Trường lọc khoảng \rightarrow Trường dùng để sort.	Đánh quá nhiều chỉ mục dư thừa trên cùng một collection.	Tiêu tốn thêm bộ nhớ đĩa cứng để chứa các bảng Index và kéo tụt hiệu năng chung của hệ thống.

3.2 Quy Trình 5 Bước Phối Hợp Phân Mảnh Vấn Đánh Chỉ Mục Cho Kiến Trúc Hệ Thống

1. Phân tích mô hình truy vấn: Xác định tỷ lệ giao tác đọc/ghi và phạm vi ứng dụng (cục bộ hay toàn cục).
2. Xác định phương án phân mảnh:
  * Sử dụng Phân mảnh ngang khi truy vấn gắn liền với thuộc tính địa lý, chi nhánh hoặc khoảng giá trị định tính.
  * Sử dụng Phân mảnh dọc khi các truy vấn thường chỉ truy cập một tập thuộc tính con nhất định (tách trường hành chính và trường tài chính).
3. Thẩm định 3 điều kiện đúng đắn: Đảm bảo mô hình phân mảnh thỏa mãn tính Đầy đủ, Tái tạo (xác định phép hợp \cup cho mảnh ngang hoặc phép kết \bowtie cho mảnh dọc) và tính Tách biệt.
4. Thiết lập chỉ mục cục bộ (Local B-Tree Indexing): Tại từng trạm lưu trữ mảnh dữ liệu, tiến hành đánh chỉ mục hỗn hợp phủ (Covered Index) hỗ trợ cả điều kiện tìm kiếm và điều kiện sắp xếp nhằm triệt tiêu giai đoạn SORT trong RAM.
5. Cấu hình tính trong suốt & Xử lý giao tác: Đảm bảo hệ thống đạt mức Trong suốt phân mảnh (Mức 1), áp dụng quy tắc Read-one Write-all cho bản nhân và xây dựng giải thuật xử lý tự trị chuỗi lệnh DELETE-INSERT khi câu lệnh UPDATE làm thay đổi vị từ định tính của mảnh.
