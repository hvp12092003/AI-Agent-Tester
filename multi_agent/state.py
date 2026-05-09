from typing import TypedDict, List, Optional


class AgentState(TypedDict):
    """Clean state for the autonomous AI agent."""
    
    # === Core ===
    model_name: str                    # AI model name
    goal: str                          # User's goal / task description
    url: Optional[str]                 # Initial URL to open (cleared after first use)
    base_url: Optional[str]            # Domain root (for safety guard)
    
    # === Perception ===
    screenshot: Optional[str]          # Current screenshot (base64 JPEG)
    dom_elements: Optional[list]       # Raw DOM elements from dom_tool
    current_page_plan: list            # SOM-annotated plan [{som_id, selector, text, rect, ...}]
    
    # === Decision ===
    next_action: Optional[dict]        # Tool calls from AI: {"tool_calls": [...]}
    messages: List[dict]               # ReAct conversation history (JSON messages)
    
    # === Output ===
    history: List[str]                 # Human-readable action log (for UI)
    findings: List[dict]               # Bug reports [{title, description, severity, url}]
    last_thought: Optional[str]        # Latest AI thought (for UI display)
    task_plan: List[dict]              # Dynamic steps: [{"step": "...", "status": "todo|done|failed"}]
    
    # === Control ===
    is_complete: bool                  # Whether the task is done
    last_action_location: Optional[dict]  # Cursor position for screenshot overlay
    
    # === Auth ===
    login_user: Optional[str]          # Login username (if provided)
    login_pass: Optional[str]          # Login password (if provided)
    
    # === Internal Counters (giữ giữa các vòng lặp graph) ===
    _api_error_count: int              # Đếm lỗi API liên tiếp (dừng khi >= 2)
    _empty_count: int                  # Đếm response rỗng liên tiếp
    _last_actions: List[str]           # Danh sách action gần nhất (chống loop)

