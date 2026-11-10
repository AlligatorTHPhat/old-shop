# DFD mức 1 — OldShop

Sơ đồ khái quát các luồng dữ liệu chính. Các số trên mũi tên là mã luồng dữ liệu, không phải thứ tự thực thi. Hình chữ nhật là External Entity, hình bo tròn là tiến trình, hình trụ biểu diễn kho dữ liệu logic.

```mermaid
flowchart LR
    BUY["Người mua / Khách truy cập"]
    SELL["Người bán"]
    MOD["Kiểm duyệt viên"]
    ADMIN["Quản trị viên"]
    EMAIL["Email Service"]
    PAYPAL["PayPal Service"]
    HELP["Google Apps Script\nHelpdesk Service"]

    subgraph SYS["HỆ THỐNG OLDSHOP"]
        P1(["1.0 Quản lý tài khoản"])
        P2(["2.0 Quản lý và kiểm duyệt sản phẩm"])
        P3(["3.0 Xử lý mua hàng và thanh toán"])
        P4(["4.0 Quản trị và tiếp nhận phản hồi"])

        D1[("D1. Tài khoản")]
        D2[("D2. Sản phẩm và đánh giá")]
        D3[("D3. Giỏ hàng, đơn hàng và giao dịch")]
        D4[("D4. Voucher và phản hồi")]
    end

    BUY -->|"01. Thông tin đăng ký, đăng nhập, khôi phục"| P1
    P1 -->|"02. Kết quả xác thực / tài khoản"| BUY
    P1 -->|"03. Dữ liệu tài khoản cập nhật"| D1
    D1 -->|"04. Hồ sơ và dữ liệu xác thực"| P1
    P1 -->|"05. Email nhận và nội dung OTP"| EMAIL

    BUY -->|"06. Tiêu chí tìm kiếm / đánh giá"| P2
    P2 -->|"07. Danh sách / chi tiết sản phẩm"| BUY
    SELL -->|"08. Thông tin đăng bán / cập nhật"| P2
    P2 -->|"09. Kết quả đăng bán / trạng thái duyệt"| SELL
    MOD -->|"10. Kết quả duyệt / xử lý vi phạm"| P2
    P2 -->|"11. Sản phẩm chờ duyệt / báo cáo vi phạm"| MOD
    P2 -->|"12. Sản phẩm, đánh giá và trạng thái duyệt"| D2
    D2 -->|"13. Dữ liệu sản phẩm và đánh giá"| P2

    BUY -->|"14. Giỏ hàng / thông tin đặt hàng, thanh toán"| P3
    P3 -->|"15. Đơn hàng / kết quả thanh toán"| BUY
    SELL -->|"16. Trạng thái xử lý đơn"| P3
    P3 -->|"17. Đơn hàng của người bán"| SELL
    D2 -->|"18. Sản phẩm, giá và tồn kho"| P3
    P3 -->|"19. Tồn kho sau giữ / hoàn hàng"| D2
    P3 -->|"20. Giỏ hàng, đơn hàng và giao dịch cập nhật"| D3
    D3 -->|"21. Dữ liệu giỏ hàng, đơn hàng và giao dịch"| P3
    P3 -->|"22. Thông tin tạo / xác nhận thanh toán"| PAYPAL
    PAYPAL -->|"23. Mã giao dịch / kết quả thanh toán"| P3
    D4 -->|"24. Thông tin voucher"| P3

    ADMIN -->|"25. Dữ liệu quản trị / yêu cầu thống kê"| P4
    P4 -->|"26. Kết quả quản trị / báo cáo"| ADMIN
    BUY -->|"27. Nội dung liên hệ / phản hồi"| P4
    P4 -->|"28. Kết quả tiếp nhận"| BUY
    P4 -->|"29. Voucher / phản hồi cập nhật"| D4
    D4 -->|"30. Voucher / phản hồi đã lưu"| P4
    P4 -->|"31. Nội dung liên hệ chuyển tiếp"| HELP
    D1 -->|"32. Thông tin người dùng / nhân sự"| P4
    P4 -->|"33. Thông tin nhân sự cập nhật"| D1
    D3 -->|"34. Dữ liệu đơn hàng phục vụ thống kê"| P4
```

Để giữ sơ đồ khái quát, luồng tài khoản dùng chung cho các Actor chỉ được minh họa qua Người mua / Khách truy cập. Người bán, Kiểm duyệt viên và Quản trị viên cũng sử dụng tiến trình 1.0. Kho dữ liệu được nhóm theo nghiệp vụ, không theo công nghệ lưu trữ. Các luồng phụ, như quản lý địa chỉ và khóa tài khoản, được lược bỏ.
