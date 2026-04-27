from multi_agent.state import AgentState
from tools.vision_tool import capture_screenshot

async def vision_node(state: AgentState) -> AgentState:
    """Node đảm nhận vai trò 'đôi mắt' của hệ thống."""
    print("\n📸 [Vision Node] Đang chụp ảnh màn hình...")
    
    # Lấy URL từ state nếu có (thường chỉ dùng ở bước đầu tiên)
    url = state.get("url")
    
    # Gọi tool chụp ảnh
    screenshot = await capture_screenshot(url)
    
    # Cập nhật State với ảnh vừa chụp được dưới dạng base64
    state["screenshot"] = screenshot
    
    # Sau khi đã điều hướng tới URL ban đầu, chúng ta xóa URL để các bước sau không bị load lại trang
    state["url"] = None 
    
    return state
