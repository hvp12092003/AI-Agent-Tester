from langgraph.graph import StateGraph, END
from .state import AgentState
from .agents import supervisor_node, ui_tester_node

def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("ui_tester", ui_tester_node)

    # LUỒNG CHẠY TỐI GIẢN: Manager -> UItester1 -> Hết
    workflow.set_entry_point("supervisor")
    workflow.add_edge("supervisor", "ui_tester")
    workflow.add_edge("ui_tester", END)

    return workflow.compile()
