# 🤖 Dự Án AI-Agent-Tester (Multi-Agent Vision)

Dự án này xây dựng một hệ thống Agent có khả năng "nhìn" (Vision) và "thực thi" (Action) trên trình duyệt web bằng cách sử dụng **Gemini 3 Flash** và **Playwright**.

## 📂 Cấu trúc dự án

### 1. Thư mục gốc
- `main.py`: Điểm bắt đầu. Nơi khởi tạo mục tiêu và chạy luồng công việc (Graph).
- `.env`: Lưu trữ API Key (GOOGLE_API_KEY).
- `AGENT_RULES.md`: Chứa các quy tắc mà Agent phải tuân thủ.
- `requirements.txt`: Danh sách các thư viện cần cài đặt.

### 2. Thư mục `multi_agent/` (Trái tim của hệ thống)
Đây là nơi triển khai kiến trúc **LangGraph**:
- `state.py`: Định nghĩa **Trạng thái (State)**. Đây là "vùng nhớ chung" nơi các Agent lưu trữ ảnh chụp màn hình, lịch sử và quyết định.
- `graph.py`: Định nghĩa **Sơ đồ luồng (Workflow)**. Quy định Agent nào chạy trước, Agent nào chạy sau và điều kiện để kết thúc.

### 3. Thư mục `multi_agent/nodes/` (Các Node Agent)
Mỗi file đại diện cho một Agent chuyên biệt:
- `vision_node.py`: **Agent Thị Giác**. Chụp ảnh màn hình và lưu vào State.
- `manager_node.py`: **Agent Quản Lý**. "Não bộ" nhận ảnh, suy nghĩ và đưa ra lệnh JSON.
- `action_node.py`: **Agent Thực Thi**. Nhận lệnh từ Manager và điều khiển trình duyệt (click, type...).

### 4. Thư mục `tools/` (Các công cụ hỗ trợ)
Các hàm cấp thấp để tương tác với hệ thống:
- `browser_manager.py`: Quản lý việc mở/đóng trình duyệt Playwright (Singleton).
- `vision_tool.py`: Hàm chụp ảnh màn hình thực tế.
- `action_tool.py`: Các hàm thực hiện click, type, scroll.

---

## 🚀 Cách hoạt động
1. `main.py` gửi mục tiêu cho **Vision Node**.
2. **Vision Node** chụp ảnh trang web -> Lưu vào State.
3. **Manager Node** lấy ảnh từ State -> Gửi cho Gemini -> Nhận về hành động tiếp theo.
4. Nếu hành động là "hoàn thành" -> Kết thúc.
5. Nếu không, **Action Node** thực hiện hành động -> Quay lại bước 2 (Vòng lặp).
