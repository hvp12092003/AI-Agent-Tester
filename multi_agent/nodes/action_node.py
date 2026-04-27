import asyncio
from multi_agent.state import AgentState
from tools.action_tool import perform_action

async def action_node(state: AgentState) -> AgentState:
    """Node thực thi các hành động vật lý trên trình duyệt."""
    action = state["next_action"]
    
    # Nếu không có hành động nào hoặc AI báo đã hoàn thành thì bỏ qua
    if not action or action["hanh_dong"] == "hoan_thanh":
        return state
        
    print(f"⚡ [Action Node] Thực thi: {action['hanh_dong']} trên {action.get('selector')}")
    
    # Gọi tool thực thi hành động thực tế (Click, Type, Scroll...)
    result = await perform_action(
        action_type=action["hanh_dong"],
        selector=action.get("selector"),
        text=action.get("text")
    )
    
    # Đợi 2 giây để trang web kịp phản hồi/load
    await asyncio.sleep(2)
    
    # Lưu kết quả thực hiện vào lịch sử của State
    state["history"].append(result)
    
    # Xóa hành động hiện tại để chuẩn bị cho bước suy nghĩ tiếp theo
    state["next_action"] = None 
    
    return state
