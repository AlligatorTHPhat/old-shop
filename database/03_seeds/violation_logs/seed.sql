-- ===========================================================================
-- FULL SEEDING DATA: VIOLATION LOGS
-- ===========================================================================

-- Xóa sạch dữ liệu cũ và reset ID tự tăng để khớp với bộ init sạch
TRUNCATE TABLE violation_log RESTART IDENTITY;

INSERT INTO violation_log (user_id, reason, action_taken, created_at) VALUES 
-- NGÀY 20/04: Bắt đầu phát hiện các vi phạm nghiêm trọng của Moderator
(2, 'Phê duyệt hàng loạt sản phẩm không rõ nguồn gốc, vi phạm quy trình kiểm duyệt đồ điện tử', 'DEACTIVATE_MODERATOR', '2026-04-20 08:30:00'),
(5, 'Lạm dụng quyền hạn để ưu tiên hiển thị bài đăng của tài khoản người thân', 'DEACTIVATE_MODERATOR', '2026-04-20 14:15:22'),

-- NGÀY 21/04: Phát hiện vi phạm của người dùng (bao gồm cả Buyer 7 và các Seller)
(7, 'Gửi tin nhắn rác quảng cáo hàng loạt cho các chủ shop trong hệ thống', 'DEACTIVATE', '2026-04-21 09:10:05'),
(3, 'Cố tình lách bộ lọc để đăng bán sản phẩm thuộc danh mục hàng cấm (thuốc lá/rượu)', 'DEACTIVATE', '2026-04-21 16:45:30'),
(4, 'Nghi vấn sử dụng nhiều tài khoản phụ để buff đơn ảo tăng uy tín gian hàng', 'DEACTIVATE', '2026-04-21 20:30:12'),

-- NGÀY 22/04: Giai đoạn xem xét giải trình và xử lý thêm
(6, 'Hệ thống bảo mật phát hiện dấu hiệu chiếm đoạt tài khoản từ IP lạ', 'DEACTIVATE_MODERATOR', '2026-04-22 07:55:12'),
(7, 'Đã hoàn thành xác minh danh tính và cam kết không tái phạm hành vi spam', 'ACTIVATE', '2026-04-22 11:20:00'),
(2, 'Hoàn thành khóa đào tạo lại nghiệp vụ kiểm duyệt sau thời gian đình chỉ', 'ACTIVATE_MODERATOR', '2026-04-22 15:45:00'),

-- NGÀY 23/04: Giai đoạn khôi phục cuối cùng (Để dữ liệu dashboard hiện lên là tất cả đã Active trở lại)
(4, 'Chủ shop đã giải trình và cung cấp hóa đơn chứng từ hợp lệ cho các đơn hàng nghi vấn', 'ACTIVATE', '2026-04-23 09:30:00'),
(5, 'Hệ thống xác nhận nhầm lẫn trong quá trình quét tự động, khôi phục quyền hạn Moderator', 'ACTIVATE_MODERATOR', '2026-04-23 13:40:00'),
(6, 'Người dùng đã đổi mật khẩu và kích hoạt bảo mật 2 lớp thành công', 'ACTIVATE_MODERATOR', '2026-04-23 16:20:45');
