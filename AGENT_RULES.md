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

## 4. 🚨 An Toàn Dữ Liệu Kiểm Thử (DATA SAFETY — QUY TẮc BẢT BUỘC)
**Áp dụng cho AI Testing Agent khi chạy kiểm thử tự động:**

- **🚫 TUYỆT ĐỐI CẤM**: Không được sửa, xóa, hay thay đổi bất kỳ dữ liệu, tài khoản, mật khẩu, hay cấu hình nào mà người dùng đã cung cấp hoặc đang tồn tại sẵn trên hệ thống.
- **🚫 TÀI KHOẢN ADMIN**: Tài khoản admin được cung cấp là **CHỈ ĐỌC (READ-ONLY)**. Agent chỉ dùng để đăng nhập và quan sát — tuyệt đối không thay đổi thông tin (email, mật khẩu, vai trò, quyền).
- **🔑 TEST CHỨC NĂNG CHỈNH SỬa**: Nếu cần test tính năng sửa/xóa thông tin, Agent phải:
  1. Đăng xuất khỏi tài khoản được cung cấp.
  2. Tự đăng ký 1 tài khoản mới (email chứa `_AI_AGENT_TEST`).
  3. Thực hiện test chức năng sửa/xóa trên tài khoản mới đó.
- **🏷️ QUY TẮc HẬU TỐ**: Mọi dữ liệu mà Agent tự tạo ra (bản ghi, tài khoản, tài liệu) ĐỀU PHẢI có hậu tố **`_AI_AGENT_TEST`**.
- **✅ CHỈ ĐƯỢC TƯƠNG TÁC**: Agent chỉ được sửa/xóa dữ liệu do chính nó tạo ra trong phiên kiểm thử đang chạy.
- **🚫 CẤM DÙNG ID CỨNG**: Khi test case có thao tác DELETE / PUT / PATCH, Agent **TUYỆT ĐỐI KHÔNG** được gọi thẳng vào ID cố định (ví dụ `/api/users/1`, `/api/users/3`). ID đó có thể là admin hoặc người dùng thật. Thay vào đó Agent **BẮT BUỘC** phải:
  1. Gọi POST để tự **tạo mới** một bản ghi với tên/email chứa `_AI_AGENT_TEST`.
  2. **Lấy `id`** từ response của bước tạo mới đó.
  3. Chỉ thực hiện DELETE/PUT/PATCH trên **`id` vừa lấy được** — không bao giờ dùng ID cứng.

---
*Ghi chú: Bản quy tắc này có thể được cập nhật bởi người dùng bất cứ lúc nào.*
- Agent luôn sử dụng Playwright để nhìn vào màn hình.
- **🚫 NGHIÊM CẤM**: Agent không bao giờ được đọc, tải về, hoặc gửi toàn bộ mã nguồn (source code) của website lên bất kỳ dịch vụ AI Cloud nào. Agent chỉ được phép tương tác với website thông qua giao diện trực quan (screenshot) và DOM elements — không được trích xuất hay truyền tải nội dung HTML/CSS/JS nguyên bản của trang web ra bên ngoài.
- Luôn có hiệu ứng chuột trên màn hình để người dùng dễ dàng biết Agent đang làm gì.
- Khi sửa 1 chức năng luôn phải xem luồng tổng thể của dự án xem có ảnh hưởng tới các chức năng khác không. Nếu có thì phải update lại luồng đó.    
- Khi cập nhật thì cũng sửa luông file LUONG_HOAT_DONG_CHI_TIET.md để sau này khi bắt đầu 1 quá trình làm việc, agent có thể đọc lại các file luồng và nắm được quy trình làm việc của dự án.




- Khi được giao nhiệm vụ sửa 1 file cụ thể hoặc 1 module cụ thể, thì phải đọc lại toàn bộ dự án để nắm được 
