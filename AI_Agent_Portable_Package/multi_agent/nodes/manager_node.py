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

FIXED RULES:
1. RESPONSE MUST BE A SINGLE VALID JSON OBJECT.
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
7. MISSING ELEMENTS: If you cannot find a field visually, use `scroll(direction="down")`.
8. FILE UPLOADS: ALWAYS use `upload_file`. If the upload zone has no SOM ID, use `click_at_coordinates` to trigger the dialog, then use `upload_file`.
9. MENUS & HOVERS: If clicking fails, try `hover_element`.
10. STABILITY: Use `wait(seconds=2)` for slow animations/popups.
11. SEQUENTIAL & COMPLETE EXECUTION: Process fields and buttons in a strict **top-to-bottom** order. You MUST identify and fill every single visible input, dropdown, and checkbox. Skipping even one field may cause a validation error.
12. DATA SAFETY & ISOLATION:
    - You are ONLY allowed to EDIT or DELETE items/data that end with the suffix **_AI_AGENT_TEST**.
    - When CREATING new data (e.g., naming a project), you MUST append **_AI_AGENT_TEST** to the end of the string (Example: "New Project _AI_AGENT_TEST").
    - DO NOT interact with any other real data to avoid accidental deletion.
13. CONTEXT-AWARE SECURITY TESTING: When performing security tests, analyze the website's category (e.g., Admin Panel, CMS, E-commerce) and prioritize relevant vulnerabilities:
    - Admin/Dashboard: Focus on Access Control, Privilege Escalation, and SQL Injection.
    - Forms/CMS: Focus on XSS, File Upload safety, and Input Validation.
    - E-commerce: Focus on Logic Errors (price, quantity) and IDOR.
    Adapt your test payloads based on the application's specific purpose.
14. MAXIMUM FORM ATTENTION: Look extremely closely at the screenshot. Identify all labels and their corresponding input fields.
    - DROPDOWNS: If a field is a Select/Dropdown (often a `div` with "Chọn"), you MUST: 1) `click_element` to open it, 2) wait for the list, 3) click the correct option ID. DO NOT try to `type_text` into a non-input dropdown.
    - NEVER leave a field empty unless explicitly instructed.
15. LOGIN & AUTHENTICATION: If you are at a login page (`/login`) and credentials are provided in "LOGIN INFO", use them immediately.
    - `type_text` the username/email, `type_text` the password, then `click_element` the Login button.
    - After login, verify you are on the Dashboard before proceeding.

RESPONSE FORMAT (JSON):
{{
  "thought": "Deep analysis of the UI. I see 3 visible fields. I will fill them all in this batch for maximum efficiency.",
  "tool_calls": [
    {{"name": "type_text", "arguments": {{"element_id": 1, "text": "value1"}}}},
    {{"name": "type_text", "arguments": {{"element_id": 2, "text": "value2"}}}},
    {{"name": "click_element", "arguments": {{"element_id": 3}}}}
  ]
}}
"""


async def manager_node(state: AgentState) -> AgentState:
    """AI Brain: Observe → Think → Decide tools to call."""
    try:
        llm_factory = LLMFactory()

        # === 1. BUILD MESSAGES ===
        messages = state.get("messages") or []
        
        if not messages:
            login_info = f"{state.get('login_user')} / {state.get('login_pass')}" if state.get("login_user") else "None"
            system_msg = SYSTEM_PROMPT_TEMPLATE.format(
                goal=state.get("goal", ""),
                base_url=state.get("base_url", ""),
                login_info=login_info,
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

        # Include current task plan in observation
        current_plan = state.get("task_plan") or []
        plan_str = json.dumps(current_plan, indent=2) if current_plan else "Not initialized yet."

        observation = f"""--- CURRENT OBSERVATION ---
URL: {current_url}
OPEN TABS: {tab_count} (Use `list_tabs` if > 1)
--- CURRENT TASK PLAN ---
{plan_str}
--- ACTION HISTORY ---
{recent_history}
--- PAGE ELEMENTS (SOM ID) ---
{dom_summary}
--- REQUEST ---
Update the 'task_plan' (mark current step as done/failed, add new steps if needed) and decide the next tool call. RETURN VALID JSON."""

        # === 3. CALL AI ===
        model_name = state.get("model_name") or "google/gemini-2.0-flash-001"
        screenshot = state.get("screenshot")

        if not screenshot:
            logger.error("❌ No screenshot available.")
            state["next_action"] = {"action": "wait"}
            return state

        image_bytes = base64.b64decode(screenshot)
        tools = get_all_tool_definitions()

        response_text = await llm_factory.generate_content(
            model_name=model_name,
            prompt=observation,
            image_data=image_bytes,
            tools=tools,
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

        # === 5. PARSE JSON ===
        try:
            # Detect hallucinated tool outputs
            if "tool_outputs" in response_text or "click_element_response" in response_text:
                raise ValueError("Hallucination detected: Do not write tool outputs or results. You are the AI, not the system.")

            # Clean common artifacts
            clean_text = response_text.replace("\\'", "'")
            clean_text = re.sub(r"```(?:json|tool_outputs)?\s*(.*?)\s*```", r"\1", clean_text, flags=re.DOTALL)
            
            # Robust JSON extraction
            json_match = re.search(r"\{.*\}", clean_text, re.DOTALL)
            if not json_match:
                raise ValueError("JSON object not found in response.")
            
            json_str = json_match.group(0)
            parsed = json.loads(json_str, strict=False)

        except Exception as e:
            logger.error(f"❌ Response/JSON Error: {e}")
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
        
        state["last_thought"] = thought

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
