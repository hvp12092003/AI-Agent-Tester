"""
Manager Node — The "Brain" of the Agent.

Responsibilities:
1. Build observation context (URL, DOM, history)
2. Send screenshot + context + tools to AI
3. Parse JSON response
4. Simple loop detection
5. Return tool_calls for Action Node
"""
import json
import re
import uuid
import base64
import logging
from multi_agent.state import AgentState
from agents.llm_factory import LLMFactory
from tools.dom_tool import format_elements
from tools.browser_manager import BrowserManager
from tools.tool_registry import get_all_tool_definitions

logger = logging.getLogger(__name__)
SYSTEM_PROMPT_TEMPLATE = """YOU ARE AN ELITE, PROFESSIONAL WEB AUTOMATION QA & SECURITY TESTER.
You approach testing with a structured, methodical, and detail-oriented mindset. You do not click randomly; you analyze the state of the application and execute precise interactions.

GOAL: {goal}
DOMAIN: {base_url}
LOGIN INFO: {login_info}
PROVIDED CREDENTIALS: {provided_credentials}
TEST CASE SCENARIO:
{test_case_data}

FIXED RULES:
1. RESPONSE MUST BE A SINGLE VALID JSON OBJECT. DO NOT use code expressions, functions, or string multiplication (like `"a".repeat(256)` or `"a" * 256`) in JSON values. All strings MUST be literal.
2. DO NOT HALLUCINATE TOOL OUTPUTS.
3. VISION FIRST: The screenshot is the primary source of truth. Trust your EYES.
   - If you see a button/input in the image but it has NO red SOM ID, YOU MUST use `click_at_coordinates(x, y)`.
   - Calculate (x, y) by looking at the 1024px-wide screenshot.
4. ANTI-LOOPING: If an action repeats, STOP. Check if the menu is already open or the field is already filled.
5. NAVIGATION LOOP PREVENTION: DO NOT click a link if you are already at that URL.
6. HIGH-SPEED BATCH MODE (EFFICIENCY):
   - If you see multiple input fields or buttons in the screenshot, DO NOT process them one-by-one.
   - Group 3-5 fields into a SINGLE `tool_calls` list (e.g., Fill Name -> Fill Phone -> Click Submit).
   - CRITICAL: Actions that change the page (scroll, navigate, refresh) MUST be the LAST tool in your batch.
7. MISSING ELEMENTS & PAGINATION:
   - If you cannot find a field visually, use `scroll(direction="down")`.
   - If you are searching for data you created in a list and it is not on the current page, you MUST navigate through all available pages (pagination) to find it before assuming it does not exist.
8. FILE UPLOADS 🚨 CRITICAL — MANDATORY 2-STEP PATTERN:
   - For HAPPY PATH upload tests (valid file, correct format): use `sample_image.png` from `test_assets` directly.
   - For ALL other upload test cases (invalid type, oversized, empty file), you MUST follow this EXACT 2-step sequence:
     STEP A: Call `generate_test_file` with the correct `file_type`, `extension`, `size_mb`, and `filename_prefix`.
     STEP B: Read the `ABSOLUTE PATH` field from the tool's response output. Pass that exact absolute path as `filename` to `upload_file`.
   🚫 ABSOLUTELY FORBIDDEN — VIOLATION CAUSES TEST FAILURE:
     - DO NOT guess, construct, or hallucinate any file path. The path MUST come verbatim from `generate_test_file` output.
     - DO NOT use paths like 'test_assets/empty.tmp' or '/some/guessed/path.txt'. These are hallucinated paths that will cause File Not Found errors.
     - DO NOT skip Step A and call `upload_file` directly with a non-existent filename for negative test cases.
   💡 EXAMPLE — Correct pattern for empty-file test:
     1. Call: generate_test_file(file_type='empty', filename_prefix='empty_test')
     2. Response: '... ABSOLUTE PATH: /Users/.../test_assets/empty_test_12345.tmp ...'
     3. Call: upload_file(element_id=42, filename='/Users/.../test_assets/empty_test_12345.tmp')
9. MENUS & HOVERS: If clicking fails, try `hover_element`.
10. STABILITY: Use `wait(seconds=1)` for animations/popups. The web responds fast — do NOT wait more than 1 second after a form submit or notification appears.
11. SEQUENTIAL & COMPLETE EXECUTION: Process fields and buttons in a strict **top-to-bottom** order. You MUST identify and fill every single visible input, dropdown, checkbox, and file upload field. Skipping even one field may cause a validation error or incomplete test.
12. DATA SAFETY & ISOLATION (🚨 CRITICAL — ABSOLUTE RULE — NO EXCEPTIONS):
    - 🚫 ABSOLUTELY FORBIDDEN: DO NOT modify, edit, delete, or change ANY data, account, password, profile, or settings that were PROVIDED by the user or that existed BEFORE you started testing.
    - This includes: account credentials (username, email, password), admin accounts, existing records, existing documents, pre-existing configurations.
    - You are ONLY allowed to EDIT or DELETE items/data that YOU have created during this test session, specifically those ending with the suffix **_AI_AGENT_TEST**.
    - 🔑 IF YOU NEED TO TEST A MODIFICATION FEATURE (e.g., change password, edit profile, update record): You MUST create a brand-new record or account first (with suffix _AI_AGENT_TEST), then test the modification on THAT new item ONLY.
    - When CREATING new data (e.g., naming a project, registering a new account), you MUST append **_AI_AGENT_TEST** to names/usernames (Example: "New Project _AI_AGENT_TEST", email: "test_ai_agent_test@example.com").
    - If no self-created data exists yet and the test requires editing/deleting, CREATE the test data FIRST, then perform the edit/delete on it.
    - 🚫 HARDCODED ID STRICTLY FORBIDDEN: NEVER call DELETE, PUT, or PATCH on a hardcoded numeric ID (e.g., `/api/users/1`, `/api/users/3`, `/api/posts/5`). These IDs belong to real users or admins. For any destructive or mutating operation, you MUST:
        1. First call POST to CREATE a new record with name/email containing `_AI_AGENT_TEST`.
        2. Extract the `id` field from the API response of the creation step.
        3. Use ONLY that dynamically obtained `id` for the subsequent DELETE/PUT/PATCH call.
13. CONTEXT-AWARE SECURITY TESTING: When performing security tests, analyze the website's category (e.g., Admin Panel, CMS, E-commerce) and prioritize relevant vulnerabilities:
    - Admin/Dashboard: Focus on Access Control, Privilege Escalation, and SQL Injection.
    - Forms/CMS: Focus on XSS, File Upload safety, and Input Validation.
    - E-commerce: Focus on Logic Errors (price, quantity) and IDOR.
    Adapt your test payloads based on the application's specific purpose.
14. MAXIMUM FORM ATTENTION: Look extremely closely at the screenshot. Identify all labels and their corresponding input fields and upload zones.
    - DROPDOWNS: If a field is a Select/Dropdown (often a `div` with "Chọn"), you MUST: 1) `click_element` to open it, 2) wait for the list, 3) click the correct option ID. DO NOT try to `type_text` into a non-input dropdown.
    - NEVER leave a field empty unless explicitly instructed.
    - UPLOADS: If you see an upload zone or button:
      * HAPPY PATH testcase → use `upload_file` with `sample_image.png` directly.
      * NEGATIVE testcases (invalid type / oversized / empty) → MANDATORY: call `generate_test_file` FIRST, then use the ABSOLUTE PATH from its response in `upload_file`. See Rule 8 for the exact pattern.
15. LOGIN & AUTHENTICATION (🚨 CRITICAL — PROTECT PROVIDED CREDENTIALS):
    - If you are at a login page (`/login`), use the credentials provided in "PROVIDED CREDENTIALS", "LOGIN INFO" or the "TEST CASE SCENARIO".
    - `type_text` the username/email, `type_text` the password, then `click_element` the Login button.
    - After login, verify you are on the Dashboard before proceeding.
    - 🚫 ABSOLUTELY FORBIDDEN: DO NOT change the password, email, username, or ANY information of the account listed in PROVIDED_CREDENTIALS. This is the user's real account — treat it as READ-ONLY.
    - 🚫 DO NOT navigate to account settings/profile of the provided account with intent to modify anything.
    - ACCOUNT MODIFICATION RULE: If the test requires modifying account information (profile, password, role, permissions, etc.):
        1. LOG OUT of the provided account first.
        2. REGISTER a completely new test account (username/email must contain '_AI_AGENT_TEST').
        3. LOG IN with the new test account.
        4. Perform ALL modification tests on the new test account ONLY.
        5. When done, you may log back into the provided account if needed for further testing.
    - DO NOT use default passwords (like admin@123) if the Test Case has provided a specific password.
16. MULTIPLE TEST CASES: If "TEST CASE SCENARIO" is a list/array of multiple test cases, you MUST execute ALL scenarios sequentially. Do not call `finish_task` until all scenarios have been tested.
17. TASK PLAN TRACKING: To save tokens, DO NOT rewrite the entire task plan. Instead, provide a `task_updates` array containing ONLY the steps whose status has changed. Use the step's index from the observation. To update the plan status, always use the index contained in square brackets [ ] at the beginning of each task line.
    - CRITICAL: Khi bắt đầu làm một bước mới (bước đang ở trạng thái 'todo'), bạn BẮT BUỘC phải xuất ra mảng `task_updates` chứa index của bước đó với status: 'doing'.
    - 'todo': Not yet started.
    - 'doing': Currently executing.
    - 'done': Successfully completed and verified.
    - 'failed': Attempted but failed (e.g. element missing, error occurred).
18. BE CONCISE & VIETNAMESE: Keep the 'thought' field short (1-3 sentences) in VIETNAMESE and focused on the immediate next action. Do not repeat the full history or plan. This prevents response truncation. (BẮT BUỘC ghi trường 'thought' bằng TIẾNG VIỆT).
19. STRICT JSON: Do not add any conversational filler or explanation outside the JSON object. Your entire response must be parseable as JSON.
20. NO DIRECT URL NAVIGATION: Do not use `navigate_to` to move between pages or to return to a page after logout. You MUST use UI interactions (clicking buttons, links) to navigate within the application. Using `navigate_to` is only allowed for the initial page load or if the test case explicitly specifies a direct URL.
21. FORM VALIDATION ERROR RECOVERY: If a form submission/save action fails due to a validation error (e.g., missing field warning like "Vui lòng chọn danh mục", "Vui lòng nhập...", or invalid format error):
    - DO NOT cancel the dialog, click cancel ("Hủy"), close the form/modal, or restart the test case.
    - Identify the specific field(s) causing the validation error from the UI or error message.
    - Fill or correct only those specific fields.
    - Click the submit/save/add button (e.g., "Lưu", "Thêm mới") again to complete the form.
    - Retain the form state and continue the submission process in place.
22. TEST SESSION CLEANUP 🧹 (MANDATORY — LAST ACTION OF SESSION):
    - When ALL test cases have been completed (or `finish_task` is about to be called), you MUST call `cleanup_test_assets` as the very last tool call before finishing.
    - This removes all dynamically generated files (created by `generate_test_file`) from the `test_assets` directory.
    - Permanent files like `sample_image.png` are NEVER deleted by this tool.
    - DO NOT skip this step. Skipping will pollute the disk over repeated CI/CD runs.

RESPONSE FORMAT (JSON):

{{
  "thought": "Phân tích giao diện: Tôi thấy có 3 trường nhập liệu. Tôi sẽ điền tất cả các trường này trong cùng một lượt để tối ưu hóa hiệu năng.",
  "task_updates": [
    {{"index": 0, "status": "done"}},
    {{"index": 1, "status": "doing"}}
  ],
  "tool_calls": [
    {{"name": "type_text", "arguments": {{"element_id": 1, "text": "value1"}}}},
    {{"name": "click_element", "arguments": {{"element_id": 3}}}}
  ]
}}
"""

def clean_json_response(raw_text):
    # 1. Thử tìm trong code block ```json ... ```
    match = re.search(r'```json\s*(.*?)\s*```', raw_text, re.DOTALL)
    if match:
        text = match.group(1)
        # Thử tìm { ... } trong đó
        inner_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if inner_match:
            return inner_match.group(1)
        return text
        
    # 2. Nếu không có code block, tìm nội dung giữa { và } lớn nhất
    match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
    if match:
        return match.group(1)
        
    return raw_text


async def manager_node(state: AgentState) -> AgentState:
    """AI Brain: Observe → Think → Decide tools to call."""
    try:
        llm_factory = LLMFactory()

        # === 1. BUILD MESSAGES ===
        messages = state.get("messages") or []
        
        if not messages:
            login_info = f"{state.get('login_user')} / {state.get('login_pass')}" if state.get("login_user") else "None"
            test_case_data = state.get("test_case_data")
            test_case_str = json.dumps(test_case_data, indent=2, ensure_ascii=False) if test_case_data else "No explicit test case provided. Act autonomously based on GOAL."
            
            provided_creds = json.dumps(state.get("PROVIDED_CREDENTIALS", {}), indent=2, ensure_ascii=False)
            
            system_msg = SYSTEM_PROMPT_TEMPLATE.format(
                goal=state.get("goal", ""),
                base_url=state.get("base_url", ""),
                login_info=login_info,
                provided_credentials=provided_creds,
                test_case_data=test_case_str,
            )
            messages.append({"role": "system", "content": system_msg})

        # Context window management
        if len(messages) > 22:
            system_msgs = [m for m in messages if m.get("role") == "system"]
            non_system = [m for m in messages if m.get("role") != "system"]
            messages = system_msgs + non_system[-18:]

        # === 2. BUILD OBSERVATION ===
        page = await BrowserManager.get_page()
        current_url = page.url
        pages = await BrowserManager.get_pages()
        tab_count = len(pages)
        
        dom_elements = state.get("dom_elements") or []
        dom_summary = format_elements(dom_elements)
        history = state.get("history") or []
        recent_history = "\n".join(history[-8:]) if history else "None."

        # Include current task plan in observation with indices
        current_plan = state.get("task_plan") or []
        # Kiểm tra mảng rỗng
        if not current_plan:
            plan_str = "Không có kế hoạch công việc nào."
        else:
            # Tìm bước hiện tại (bỏ qua cả "done", "failed", "skipped")
            current_idx = 0
            found_active = False
            for i, step in enumerate(current_plan):
                if step.get("status") not in ["done", "failed", "skipped"]:
                    current_idx = i
                    found_active = True
                    break
            
            if not found_active:
                # Nếu tất cả đều done/failed/skipped, trỏ về step cuối cùng
                current_idx = len(current_plan) - 1 if current_plan else 0

            # Đếm số bước đã bỏ qua
            skipped_count = sum(1 for s in current_plan if s.get("status") == "skipped")

            # Xác định khoảng hiển thị
            window_before = 10
            window_after = 20
            start_idx = max(0, current_idx - window_before)
            end_idx = min(len(current_plan), current_idx + window_after + 1)

            plan_str = ""
            if skipped_count > 0 and start_idx == 0:
                plan_str += f"⏭️ [{skipped_count} bước đã bỏ qua theo yêu cầu - SKIPPED, không cần thực hiện]\n"
            elif start_idx > 0:
                plan_str += f"... [Đã ẩn {start_idx} bước đầu tiên đã hoàn thành] ...\n"

            for i in range(start_idx, end_idx):
                step = current_plan[i]
                status = step.get("status", "todo")
                if status == "skipped":
                    # Hiển thị bước đã skip nhưng chỉ khi trong cửả start_idx-current_idx
                    if i >= start_idx and i < current_idx:
                        plan_str += f"    [{i}] ⏭️ {step.get('step')} (Status: SKIPPED - bỏ qua, không thực hiện)\n"
                else:
                    # Đánh dấu trực quan bước hiện tại cho AI dễ nhận biết
                    marker = "--> " if i == current_idx else "    "
                    plan_str += f"{marker}[{i}] {step.get('step')} (Status: {status})\n"

            if end_idx < len(current_plan):
                plan_str += f"... [Đã ẩn {len(current_plan) - end_idx} bước tiếp theo] ...\n"


        tools = get_all_tool_definitions()
        
        observation = f"""--- CURRENT OBSERVATION ---
URL: {current_url}
OPEN TABS: {tab_count} (Use `list_tabs` if > 1)
--- CURRENT TASK PLAN ---
{plan_str}
--- ACTION HISTORY ---
{recent_history}
--- PAGE ELEMENTS (SOM ID) ---
{dom_summary}
--- AVAILABLE TOOLS ---
{json.dumps(tools, indent=2)}
--- REQUEST ---
Update the 'task_updates' array to mark progress (if any) and decide the next tool call. RETURN VALID JSON."""

        # === 3. CALL AI ===
        # Priority: brain_model from model_config > legacy model_name > default
        model_config = state.get("model_config") or {}
        model_name = (
            model_config.get("brain_model")
            or state.get("model_name")
            or "google/gemini-2.0-flash-001"
        )
        screenshot = state.get("screenshot")
        extra_screenshots = state.get("extra_screenshots") or []

        if not screenshot:
            logger.error("❌ No screenshot available.")
            state["next_action"] = {"action": "wait"}
            return state

        # Use instant_screenshot (first extra) if available — it captures flash notifications
        # that disappear before the final stable screenshot is taken
        active_screenshot = extra_screenshots[0] if extra_screenshots else screenshot
        if extra_screenshots:
            logger.info(f"📸 [Manager] Using instant snapshot for AI vision ({len(extra_screenshots)} extras available)")

        image_bytes = base64.b64decode(active_screenshot)

        # Append note to observation if multiple snapshots captured this cycle
        if extra_screenshots:
            observation += f"\n--- MULTI-SNAPSHOT NOTE ---\nThis cycle captured {1 + len(extra_screenshots)} snapshots (instant + stable). The image shown is the INSTANT capture taken immediately after the last action — it may contain transient notifications, toasts, or loading states. The stable DOM state is reflected in the PAGE ELEMENTS above."

        response_text = await llm_factory.generate_content(
            model_name=model_name,
            prompt=observation,
            image_data=image_bytes,
            tools=None, # Force JSON text response instead of native tool calls
            history=messages,
        )

        # === 4. HANDLE EMPTY/INVALID RESPONSE ===
        if not response_text or len(response_text.strip()) < 5:
            empty_count = state.get("_empty_count", 0) + 1
            state["_empty_count"] = empty_count
            logger.warning(f"⚠️ Low-quality response #{empty_count}: {response_text}")

            if empty_count >= 4:
                state["is_complete"] = True
                return state
            
            messages.append({"role": "user", "content": "Error: Response is empty or too short. Please perform an action and return valid JSON."})
            state["messages"] = messages
            state["next_action"] = {"action": "wait"}
            return state

        state["_empty_count"] = 0
        logger.info(f"🔍 AI Response:\n{response_text[:300]}...")

        # === 4.5. DETECT API AUTH ERRORS (401/403) ===
        if "[[API_ERROR]]" in response_text:
            api_fail_count = state.get("_api_error_count", 0) + 1
            state["_api_error_count"] = api_fail_count
            logger.error(f"🚨 API Error #{api_fail_count}: {response_text[:200]}")
            
            if api_fail_count >= 2:
                # Dừng hẳn sau 2 lần lỗi API liên tiếp
                error_msg = response_text.replace("[[API_ERROR]]: ", "")
                state["last_thought"] = f"❌ LỖI API: {error_msg[:150]}. Agent đã dừng. Vui lòng kiểm tra API Key."
                state["is_complete"] = True
                hist = state.get("history") or []
                hist.append(f"❌ Agent dừng do lỗi API liên tiếp: {error_msg[:100]}")
                state["history"] = hist
                return state
            
            state["next_action"] = {"action": "wait"}
            return state
        
        # Reset API error counter on success
        state["_api_error_count"] = 0

        # === 5. PARSE JSON ===
        try:
            # Detect hallucinated tool outputs
            if "tool_outputs" in response_text or "click_element_response" in response_text:
                raise ValueError("Hallucination detected: Do not write tool outputs or results. You are the AI, not the system.")

            # Clean and extract JSON
            clean_text = response_text.replace("\\'", "'")
            json_str = clean_json_response(clean_text)
            
            parsed = json.loads(json_str, strict=False)

        except Exception as e:
            logger.error(f"❌ Response/JSON Error: {e}")
            logger.error(f"🔍 Raw JSON string that failed:\n{json_str}")
            fail_count = state.get("_empty_count", 0) + 1
            state["_empty_count"] = fail_count
            
            err_msg = f"ERROR: {e}. Please return ONLY valid JSON with 'thought' and 'tool_calls'. DO NOT hallucinate results."
            messages.append({"role": "user", "content": err_msg})
            state["messages"] = messages
            state["next_action"] = {"action": "wait"}
            return state

        # === 6. EXTRACT FIELDS ===
        thought = parsed.get("thought", "")
        tool_calls = parsed.get("tool_calls", [])
        task_updates = parsed.get("task_updates", [])
        
        state["last_thought"] = thought

        if task_updates and isinstance(task_updates, list):
            current_plan = state.get("task_plan") or []
            for update in task_updates:
                idx = update.get("index")
                new_status = update.get("status")
                
                # Đảm bảo index là số nguyên
                try:
                    if idx is not None:
                        idx = int(idx)
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Invalid index in task_updates: {idx}")
                    continue
                    
                if isinstance(idx, int) and 0 <= idx < len(current_plan) and new_status:
                    current_plan[idx]["status"] = new_status
                    # Reset step_retry_count and loop detection if step is marked done
                    if new_status == "done":
                        state["step_retry_count"] = 0
                        state["_last_actions"] = []
                        logger.info(f"🔄 Step {idx} marked done. Reset step_retry_count and loop detection.")
            state["task_plan"] = current_plan

        # Extract findings if any
        ai_findings = parsed.get("findings", [])
        if ai_findings:
            current_findings = state.get("findings") or []
            for f in ai_findings:
                if isinstance(f, dict):
                    current_findings.append(f)
            state["findings"] = current_findings

        # === 7. SANITIZE TOOL CALLS ===
        sanitized = []
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                name = tc.get("name") or tc.get("tool_name")
                if not name:
                    continue
                # Fix hallucinated "functions." prefix
                if name.startswith("functions."):
                    name = name.replace("functions.", "")
                sanitized.append({
                    "id": tc.get("id") or str(uuid.uuid4())[:8],
                    "name": name,
                    "arguments": tc.get("arguments") or tc.get("args") or {},
                })


        # === 8. LOOP DETECTION ===
        if sanitized:
            last_actions = state.get("_last_actions") or []
            for tc in sanitized:
                eid = tc.get("arguments", {}).get("element_id")
                if eid and last_actions.count(eid) >= 2:
                    logger.warning(f"🚨 LOOP: ID {eid} đã tương tác 2+ lần. Blocking.")
                    loop_msg = (
                        f"LOOP DETECTED: Bạn đã thử ID {eid} nhiều lần. "
                        f"Hãy thử: 1) navigate_to URL khác, 2) hover_element, 3) scroll để tìm phần tử khác."
                    )
                    messages.append({"role": "user", "content": loop_msg})
                    state["messages"] = messages
                    state["next_action"] = {"action": "wait"}
                    return state
                
                if eid:
                    last_actions.append(eid)
                    if len(last_actions) > 5:
                        last_actions.pop(0)
            
            state["_last_actions"] = last_actions

        # === 9. RETURN DECISION ===
        if sanitized:
            state["next_action"] = {"tool_calls": sanitized}
            messages.append({
                "role": "assistant",
                "content": thought,
                "tool_calls": sanitized,
            })
        else:
            # No tools = AI is thinking or waiting
            state["next_action"] = {"action": "wait"}
            if thought:
                messages.append({"role": "assistant", "content": thought})

        state["messages"] = messages

        if thought:
            hist = state.get("history") or []
            hist.append(f"🧠 {thought}")
            state["history"] = hist

        return state

    except Exception as e:
        logger.error(f"❌ Manager Error: {e}")
        state["next_action"] = {"action": "wait"}
        return state
