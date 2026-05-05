from typing import TypedDict, List, Optional

class AgentState(TypedDict):
    # AI model name (e.g., gemini-2.5-pro)
    model_name: str
    
    # User's final goal
    goal: str
    
    # Agent mode: "test_web" or "custom"
    mode: str
    
    # URL to navigate (only used on first step)
    url: Optional[str]
    
    # Original website domain (used for URL Guard)
    base_url: Optional[str]
    
    # Current screenshot (base64) to send to AI
    screenshot: Optional[str]
    
    # List of interactive elements found on page (raw string from dom_tool)
    dom_elements: Optional[str]
    
    # Next action decided by Manager
    next_action: Optional[dict]
    
    # History of completed steps
    history: List[str]
    
    # Latest AI thought for Dashboard display
    last_thought: Optional[str]

    # Security/UI findings list: [{"text": str, "url": str, "screenshot": str, "timestamp": str}]
    findings: List[dict]

    # Flag khi gặp lỗi trình duyệt
    browser_error: bool
    
    # Tọa độ hành động cuối cùng để vẽ con trỏ chuột: {"x": float, "y": float}
    last_action_location: Optional[dict]

    # Flag when goal is achieved
    is_complete: bool

    # ===== BFS Crawler State =====
    
    # URL queue: [{url: str, status: "pending"|"testing"|"tested", title: str}]
    global_url_queue: List[dict]
    
    # Page plan: [{selector: str, text: str, tag: str, url: str, status: "unclicked"|"clicked"|"skipped"}]
    current_page_plan: List[dict]
    
    # Blacklist selector đã click để chống lặp vòng (Infinite Toggle Loop)
    clicked_selectors_blacklist: List[str]
    
    # URL đang được kiểm thử hiện tại
    testing_url: Optional[str]
    
    # Pha hiện tại: "exploration" (BFS click) → "security" (inject payload) → done
    phase: str
    security_steps: int
    
    # Lựa chọn kiểm tra của người dùng
    test_ui: bool
    test_security: bool

    # Authentication
    login_user: Optional[str]
    login_pass: Optional[str]
    logged_in: bool
    # Master Plan: [{id: int, task: str, status: "pending"|"completed"}]
    master_plan: List[dict]
    
    # Login tracking
    login_steps: int
    login_attempts: int
    
    # Path tracking (Dành cho Path A/B/C)
    path_steps: List[str]
    current_step_index: int
    
    # Security Memory (Chống lặp bước test bảo mật)
    # [{url: str, selector: str, payload_type: str}]
    security_memory: List[dict]
    # Global Memory (Theo dõi toàn bộ hành động để chống lặp vòng)
    # [{url: str, action: str, selector: str, value: str}]
    global_memory: List[dict]
    
    # Danh sách các nút (canonical selector) đã được click thành công trên trang hiện tại
    already_clicked_buttons: List[str]

    # ReAct Message History
    # [{role: "user"|"assistant"|"tool", content: str, tool_calls: list, tool_call_id: str}]
    messages: List[dict]
    
    # Counter for actions on the current page to prevent loops
    page_step_count: int

    # Anti-Loop Guard: List of recently interacted element IDs
    last_actions: List[int]
    
    # Universal Loop Tracking
    last_clicked_id: Optional[int]
    last_url: Optional[str]

