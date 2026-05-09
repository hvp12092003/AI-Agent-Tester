from langgraph.graph import StateGraph, END
from multi_agent.state import AgentState
from multi_agent.nodes.vision_node import vision_node
from multi_agent.nodes.manager_node import manager_node
from multi_agent.nodes.action_node import action_node
from tools.tool_registry import import_all_tools

# Register all tools at import time
import_all_tools()

def should_continue(state: AgentState):
    """Hàm kiểm tra điều kiện để quyết định đi tiếp hay dừng lại."""
    if state.get("is_complete"):
        return "end"
    return "continue"

def create_graph():
    """Khởi tạo và kết nối các Node thành một luồng công việc hoàn chỉnh."""
    workflow = StateGraph(AgentState)

    # Đăng ký các Node (Tác tử) vào sơ đồ
    workflow.add_node("vision", vision_node)
    workflow.add_node("manager", manager_node)
    workflow.add_node("action", action_node)

    # Thiết lập luồng chạy: Bắt đầu từ Vision -> Manager
    workflow.set_entry_point("vision")
    workflow.add_edge("vision", "manager")
    
    # Tại Manager, AI sẽ quyết định rẽ nhánh:
    # Nếu xong -> Kết thúc (END)
    # Nếu chưa -> Chuyển sang Action để thực thi
    workflow.add_conditional_edges(
        "manager",
        should_continue,
        {
            "continue": "action",
            "end": END
        }
    )
    
    # Sau khi Action thực thi xong, kiểm tra xem có cần dừng không, nếu không thì quay lại chụp ảnh (Vision)
    workflow.add_conditional_edges(
        "action",
        should_continue,
        {
            "continue": "vision",
            "end": END
        }
    )
    return workflow.compile()
