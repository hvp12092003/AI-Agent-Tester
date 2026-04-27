from typing import TypedDict, List, Optional

class AgentState(TypedDict):
    # Tên model AI được chọn để chạy (ví dụ: gemini-2.5-pro)
    model_name: str
    
    # Mục tiêu cuối cùng của người dùng (ví dụ: "Đăng nhập vào Facebook")
    goal: str
    
    # URL cần truy cập (chỉ dùng ở bước đầu tiên)
    url: Optional[str]
    
    # Ảnh chụp màn hình hiện tại (định dạng base64) để gửi cho AI
    screenshot: Optional[str]
    
    # Hành động tiếp theo do Manager quyết định (hành động, selector, text...)
    next_action: Optional[dict]
    
    # Lịch sử các bước đã thực hiện thành công
    history: List[str]
    
    # Cờ đánh dấu khi mục tiêu đã đạt được
    is_complete: bool
