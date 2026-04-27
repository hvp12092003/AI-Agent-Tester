import os
import json
import re
import base64
from dotenv import load_dotenv
from agents.llm_factory import LLMFactory
from multi_agent.state import AgentState

load_dotenv()
llm_factory = LLMFactory()

async def manager_node(state: AgentState) -> AgentState:
    """Node xử lý logic suy nghĩ của AI."""
    # Sử dụng model do người dùng chọn từ menu
    model_name = state.get("model_name", "google/gemini-2.0-flash-001")
    
    goal = state["goal"]
    screenshot = state["screenshot"]
    
    # Prompt hướng dẫn AI cách phân tích ảnh và trả về định dạng JSON chuẩn
    prompt = f"""
    Bạn là một Manager điều phối tự động hóa web. Mục tiêu: '{goal}'
    
    Hãy phân tích ảnh và quyết định bước tiếp theo.
    
    **LƯU Ý VỀ HÀNH ĐỘNG**:
    - Ưu tiên dùng text chính xác: `text="Nội dung nút"`
    - **Tương tác với ảnh**: Nếu bạn nghi ngờ một hình ảnh (img) có thể nhấn được, hãy thử `click` hoặc `hover` vào nó.
    - Nếu cần xem hiệu ứng khi di chuột qua, hãy dùng `hover`.
    - Nếu không thấy phần tử mục tiêu trên ảnh, hãy trả về hành động `scroll` để tìm tiếp bên dưới.
    - Chỉ 'hoan_thanh' khi đã thực hiện xong mục tiêu.
    
    Trả về JSON (chỉ JSON):
    {{
        "suy_nghi": "Mô tả những gì bạn thấy và tại sao chọn phần tử đó",
        "hanh_dong": "click" | "type" | "scroll" | "hover" | "hoan_thanh",
        "selector": "Playwright selector chuẩn (ví dụ: img[alt='logo'] hoặc button)",
        "text": "Nội dung cần nhập (nếu có)"
    }}
    """
    
    # Gửi ảnh và prompt lên AI (thông qua Factory)
    image_data = base64.b64decode(screenshot)
    content = await llm_factory.generate_content(
        model_name=model_name,
        prompt=prompt,
        image_data=image_data
    )
    
    # Kiểm tra nếu có lỗi API trả về từ Factory
    if "[[API_ERROR]]" in content:
        print(f"⚠️ Lỗi từ AI Provider: {content}")
        state["is_complete"] = True
        return state

    # Trích xuất JSON từ kết quả trả về của AI
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            print(f"🤖 AI: {result['suy_nghi']}")
            
            # Cập nhật hành động tiếp theo vào State
            state["next_action"] = result
            
            # Nếu AI báo đã xong việc thì đánh dấu để dừng Graph
            if result["hanh_dong"] == "hoan_thanh":
                state["is_complete"] = True
        except json.JSONDecodeError:
            print(f"❌ Lỗi định dạng JSON trong phản hồi: {content}")
            state["is_complete"] = True
    else:
        print(f"❌ AI không trả lời đúng định dạng JSON. Phản hồi: {content}")
        state["is_complete"] = True
        
    return state
