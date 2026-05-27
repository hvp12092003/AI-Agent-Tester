"""
LangGraph Workflow — EVN QA 5-Node Architecture.

Flow:
  START
    → scoping_node   (once: parse test case, define scope)
    → vision_node    (loop: capture screenshot + DOM)
    → manager_node   (loop: brain model decides next action)
    → [route_after_manager]
         "end"           → reporter_node → END
         "critical_bug"  → reporter_node → END  (short-circuit)
         "validate"      → validator_node → action_node → [route_after_action]
         "action"        → action_node → [route_after_action]
    → [route_after_action]
         "end"           → reporter_node → END
         "max_steps"     → reporter_node → END  (safety cap)
         "validate"      → validator_node → vision_node
         "continue"      → vision_node

Router Decision Table:
  ┌──────────────────────────────────────────────────────────────┐
  │ Condition                        │ Route         │ Priority  │
  ├──────────────────────────────────┼───────────────┼───────────┤
  │ is_complete = True               │ reporter      │ 1 (High)  │
  │ is_bug AND severity = Critical   │ reporter      │ 2         │
  │ step_count >= max_steps          │ reporter      │ 3         │
  │ last action is "critical action" │ validator     │ 4         │
  │ default                          │ continue loop │ 5 (Low)   │
  └──────────────────────────────────┴───────────────┴───────────┘
"""
from langgraph.graph import StateGraph, END
from multi_agent.state import AgentState
from multi_agent.nodes.vision_node import vision_node
from multi_agent.nodes.manager_node import manager_node
from multi_agent.nodes.action_node import action_node
from multi_agent.nodes.scoping_node import scoping_node
from multi_agent.nodes.validator_node import validator_node
from multi_agent.nodes.reporter_node import reporter_node
from tools.tool_registry import import_all_tools

# Register all tools at import time
import_all_tools()

# ─────────────────────────────────────────────
# Keyword lists for detecting "critical actions"
# that should trigger Validator after execution
# ─────────────────────────────────────────────
_CRITICAL_ACTION_KEYWORDS = [
    "login", "logout", "sign in", "sign out",
    "submit", "save", "confirm", "create", "publish",
    "delete", "remove", "reset", "upload", "payment",
    "register", "update", "change password",
]


def _is_critical_action(state: AgentState) -> bool:
    """Check if the latest history entry indicates a critical action was taken."""
    history = state.get("history") or []
    if not history:
        return False
    last_entry = history[-1].lower()
    return any(kw in last_entry for kw in _CRITICAL_ACTION_KEYWORDS)


# ─────────────────────────────────────────────
# Router: After Manager Node
# ─────────────────────────────────────────────
def route_after_manager(state: AgentState) -> str:
    """Decide next step after Manager (brain) has made a decision."""
    # Priority 1: Task marked complete (explicit finish or all steps processed)
    if state.get("is_complete"):
        return "reporter"

    current_plan = state.get("task_plan") or []
    is_finished = all(step.get("status") in ["done", "failed", "skipped"] for step in current_plan)
    if is_finished and current_plan:
        return "reporter"

    # Priority 2: Critical bug detected by previous Validator cycle
    if state.get("is_bug") and state.get("severity") == "Critical":
        return "reporter"

    # Priority 3: Max steps reached
    step_count = state.get("current_step_count", 0)
    max_steps = state.get("max_steps", 50)
    if step_count >= max_steps:
        return "reporter"

    # Priority 4: No tool calls (wait/think) — skip to next vision cycle
    next_action = state.get("next_action") or {}
    if not next_action.get("tool_calls"):
        return "reporter" if state.get("is_complete") else "action"

    return "action"


# ─────────────────────────────────────────────
# Router: After Action Node
# ─────────────────────────────────────────────
def route_after_action(state: AgentState) -> str:
    """Decide next step after Action Node has executed tool calls."""
    # Increment step counter
    state["current_step_count"] = state.get("current_step_count", 0) + 1

    # Priority 1: Task marked complete by finish_task tool or all steps processed
    if state.get("is_complete"):
        return "reporter"

    current_plan = state.get("task_plan") or []
    is_finished = all(step.get("status") in ["done", "failed", "skipped"] for step in current_plan)
    if is_finished and current_plan:
        return "reporter"

    # Priority 2: Critical bug detected
    if state.get("is_bug") and state.get("severity") == "Critical":
        return "reporter"

    # Priority 3: Max steps safety cap
    step_count = state.get("current_step_count", 0)
    max_steps = state.get("max_steps", 50)
    if step_count >= max_steps:
        return "reporter"

    # Priority 4: Critical action detected → Validate before continuing
    test_scope = state.get("test_scope") or {}
    if test_scope.get("functional", True) and _is_critical_action(state):
        return "validator"

    # Default: Continue loop
    return "vision"


# ─────────────────────────────────────────────
# Router: After Validator Node
# ─────────────────────────────────────────────
def route_after_validator(state: AgentState) -> str:
    """Decide next step after Validator has inspected the result."""
    # Short-circuit on Critical bug
    if state.get("is_bug") and state.get("severity") == "Critical":
        return "reporter"

    # Otherwise continue the loop
    return "vision"


# ─────────────────────────────────────────────
# Graph Construction
# ─────────────────────────────────────────────
def create_graph():
    """Build and compile the EVN QA 5-node LangGraph workflow."""
    workflow = StateGraph(AgentState)

    # Register all nodes
    workflow.add_node("scoping", scoping_node)
    workflow.add_node("vision", vision_node)
    workflow.add_node("manager", manager_node)
    workflow.add_node("action", action_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("reporter", reporter_node)

    # Entry point: always start with Scoping
    workflow.set_entry_point("scoping")

    # Scoping → Vision (always, runs once then guard prevents re-scoping)
    workflow.add_edge("scoping", "vision")

    # Vision → Manager (always)
    workflow.add_edge("vision", "manager")

    # Manager → [route_after_manager] → action | reporter
    workflow.add_conditional_edges(
        "manager",
        route_after_manager,
        {
            "action": "action",
            "reporter": "reporter",
        }
    )

    # Action → [route_after_action] → vision | validator | reporter
    workflow.add_conditional_edges(
        "action",
        route_after_action,
        {
            "vision": "vision",
            "validator": "validator",
            "reporter": "reporter",
        }
    )

    # Validator → [route_after_validator] → vision | reporter
    workflow.add_conditional_edges(
        "validator",
        route_after_validator,
        {
            "vision": "vision",
            "reporter": "reporter",
        }
    )

    # Reporter → END (always)
    workflow.add_edge("reporter", END)

    return workflow.compile()
