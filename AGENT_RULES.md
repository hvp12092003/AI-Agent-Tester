# AGENT RULES - BẢN QUY TẮC CHO AGENT

Bạn là một AI Coding Assistant cao cấp. Đây là các quy tắc bạn **PHẢI** đọc và tuân thủ trước khi bắt đầu bất kỳ công việc nào trong dự án này.

## 1. Nguyên Tắc Chung
- **Ngôn ngữ**: Luôn giao tiếp với người dùng bằng tiếng Việt.
- **Tính cẩn trọng**: Trước khi thực hiện các hành động mang tính phá hủy (như xóa file, ghi đè lượng lớn code), phải tạo Implementation Plan và chờ xác nhận.
- **Tổ chức file**: Giữ cho cấu trúc thư mục gọn gàng. Các script nháp nên để trong thư mục `scratch/`.

## 2. Quy Trình Làm Việc
1. **Lập kế hoạch**: Với các task phức tạp, luôn tạo `implementation_plan.md`.
2. **Theo dõi**: Sử dụng `task.md` để theo dõi tiến độ công việc hiện tại.
3. **Báo cáo**: Sau khi hoàn thành, cập nhật `walkthrough.md` để tóm tắt các thay đổi và kết quả kiểm tra.

## 3. Quy Định Kỹ Thuật
- **Quản lý Key**: Tuyệt đối không hardcode API Key vào mã nguồn. Luôn sử dụng file `.env` và thư viện `python-dotenv`.
- **Thử nghiệm**: Khi tạo các tính năng liên quan đến Browser (Playwright, Selenium), hãy chạy thử trong môi trường không đầu (headless) trước trừ khi có yêu cầu khác.
- **Log**: Thêm log rõ ràng trong code để dễ dàng debug.

## 4. Đặc Thù Dự Án (AI-Agent-Tester)
- Dự án tập trung vào việc xây dựng hệ thống Multi-Agent để tự động hóa việc test UI/UX và Security.
- Ưu tiên sử dụng các framework hiện đại như LangChain, LangGraph.

---
*Ghi chú: Bản quy tắc này có thể được cập nhật bởi người dùng bất cứ lúc nào.*
