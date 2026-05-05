from multi_agent.state import AgentState
from agents.llm_factory import LLMFactory
from tools.dom_tool import format_elements
from tools.agent_tools import WEB_TESTER_TOOLS
from tools.crawler_tool import (
    get_queue_summary,
    get_plan_summary,
    get_next_unclicked,
    is_page_complete,
)
import json
import re
import uuid
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def manager_node(state: AgentState) -> AgentState:
    """Autonomous coordinator using Native Tool Calling."""
    llm_factory = LLMFactory()

    # 1. CONTEXT ASSEMBLY
    dom_elements = state.get("dom_elements") or []
    dom_summary = format_elements(dom_elements)

    # Message history for ReAct
    messages = state.get("messages") or []
    if not messages:
        # Initialize conversation with goals
        mode = state.get("mode", "test_web")
        is_web_test = (mode == "test_web")
        
        system_msg = f"""YOU ARE AN AUTONOMOUS EXPERT AI AGENT.
Current Mode: {'WEB AUDIT & TESTING' if is_web_test else 'GENERAL TASK EXECUTION'}
Your goal: {state.get("goal")}

MISSION CONTEXT:
- Target domain: {state.get("base_url")}
- Credentials: {state.get("login_user")} / {state.get("login_pass")}

🚨 SAFETY & DATA PROTECTION RULES (CRITICAL):
1. NO MODIFICATION OF EXISTING DATA: Never edit or delete information that was already present before you started.
2. CREATE NEW DATA ONLY: If the task requires editing/deleting, you must first CREATE a new entry and then you may modify THAT entry.
3. IDENTIFICATION TAG: All data created by you MUST include the suffix '_AI_TEST' (e.g., 'New User _AI_TEST').
4. SELF-CONTROL: You are ONLY allowed to edit or delete entries that contain the '_AI_TEST' tag.

🚨 STRATEGIC GUIDELINES:
1. {'Perform a systematic BFS audit of the site, checking UI and Security.' if is_web_test else 'Focus purely on completing the specific task provided by the user. Do not wander.'}
2. EVALUATE HISTORY: Read "--- ACTION HISTORY ---". If URL & DOM Shifts are 0, the last action failed. Do NOT repeat the same ID.
3. FILE UPLOAD: To upload files, first use `list_files` to see what is available in 'test_assets'. Then use `upload_file` with the correct SOM ID and filename. Do NOT wait for OS popups; the tool handles it directly.
4. MASTER PLAN: Maintain a 5-step plan. For General Tasks, focus on reaching the target ASAP.
5. STAY ON TRACK: If you drift to an irrelevant page, go back immediately.
6. COORDINATE CHECK: If coordinates are (0,0) or ID is missing, scroll or wait.

FINAL DECISION STRUCTURE:
- Your "thought" must follow this structure EXACTLY: 
  "Current Page: [Name] | Plan Status: [Step X of Y] | Observation: [What changed?] | Next Step: [Why this ID?]"

REQUIRED JSON FORMAT:
{{
  "thought": "Current Page: ... | Plan Status: ... | Observation: ... | Next Step: ...",
  "master_plan": [
    {{ "task": "Bước 1: ...", "status": "completed/pending" }},
    {{ "task": "Bước 2: ...", "status": "completed/pending" }},
    {{ "task": "Bước 3: ...", "status": "completed/pending" }},
    {{ "task": "Bước 4: ...", "status": "completed/pending" }},
    {{ "task": "Bước 5: ...", "status": "completed/pending" }}
  ],
  "tool_calls": [
    {{ "name": "click_element", "arguments": {{ "element_id": 1 }} }}
  ],
  "findings": [
    {{ "url": "...", "text": "Phát hiện lỗi X tại đây", "type": "ui/security/info" }}
  ]
}}
- findings: Must be in Vietnamese.
- ONLY interact with visible elements in the screenshot.
"""
        messages.append({"role": "system", "content": system_msg})

    # Add current observation
    queue_summary = get_queue_summary(state.get("global_url_queue") or [])
    step_count = state.get("page_step_count", 0)
    history = state.get("history") or []
    recent_history = "\n".join(history[-7:]) if history else "No history yet."

    observation = f"""--- CURRENT OBSERVATION ---
URL: {state.get("testing_url")}
Logged In: {state.get("logged_in")}
Step Count: {step_count}/20
--- ACTION HISTORY ---
{recent_history}
---------------------------
SOM ID Reference: 
{dom_summary}
---------------------------"""

    # 2. GENERATE RESPONSE
    try:
        model_name = state.get("model_name") or "google/gemini-2.0-flash-001"
        screenshot = state.get("screenshot")
        
        if not screenshot:
            logger.error("❌ No screenshot available in state. Possible browser failure.")
            state["error"] = "Không thể chụp ảnh màn hình. Vui lòng kiểm tra trình duyệt."
            state["next_action"] = {"action": "wait"}
            return state

        image_bytes = base64.b64decode(screenshot)

        response_text = await llm_factory.generate_content(
            model_name=model_name,
            prompt=observation,
            image_data=image_bytes,
            tools=WEB_TESTER_TOOLS,
            history=messages,
        )

        if not response_text:
            logger.error("❌ Empty response from LLM")
            return state

        logger.info(f"🔍 RAW AI Response:\n{response_text}")

        # Pillar 4: Aggressive Response Sanitization
        # Remove any hallucinated tool outputs or success blocks that break JSON parsing
        response_text = re.sub(
            r"```tool_outputs.*?```", "", response_text, flags=re.DOTALL
        )
        response_text = re.sub(
            r"```tool_result.*?```", "", response_text, flags=re.DOTALL
        )
        response_text = re.sub(
            r"tool_outputs:.*", "", response_text, flags=re.IGNORECASE | re.DOTALL
        )

        if "```tool_outputs" in response_text:
            response_text = response_text.split("```tool_outputs")[0]

        # [HALLUCINATION KILLER] If AI writes "SUCCESS:" it's almost always a hallucination
        if "SUCCESS:" in response_text.upper() and "tool_calls" not in response_text:
            logger.warning("⚠️ Hallucinated SUCCESS detected. Forcing re-observation.")
            error_msg = "Error: Your response contained 'SUCCESS:' but no tool calls. Do NOT hallucinate success. Provide tool_calls to verify."
            messages.append({"role": "user", "content": error_msg})
            state["messages"] = messages
            state["next_action"] = {"action": "wait"}
            return state

        # Clean common invalid escape characters in AI JSON
        response_text = response_text.replace("\\'", "'")

        logger.info(f"🔍 SANITIZED Response:\n{response_text}")

        # 3. RESPONSE PROCESSING (Robust Regex Parsing)
        try:
            # Step 1: Find the JSON block (either inside code block or first/last braces)
            json_str = ""

            # Pattern 1: Content between ```tool_calls and ```
            tc_match = re.search(
                r"```(?:json|tool_calls)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if tc_match:
                json_str = tc_match.group(1)
            else:
                # Pattern 2: First { and last } - handle cases where multiple blocks might exist after cleaning
                brace_match = re.search(
                    r"(\{.*\})", response_text.replace("\n", " "), re.DOTALL
                )
                if brace_match:
                    json_str = brace_match.group(1)

            if not json_str:
                raise ValueError(
                    "No valid tool_calls block found in the required JSON format."
                )

            # Step 2: Parse JSON with strict=False to handle common escape errors
            next_action = json.loads(json_str, strict=False)

            thought = next_action.get("thought", "")
            tool_calls = next_action.get("tool_calls", [])
            state["last_thought"] = thought
            
            # Cập nhật Master Plan từ AI (nếu có)
            if "master_plan" in next_action:
                state["master_plan"] = next_action["master_plan"]
            
            # Cập nhật Findings từ AI (nếu có)
            ai_findings = next_action.get("findings", [])
            if ai_findings:
                current_findings = state.get("findings", [])
                # Tránh trùng lặp nội dung
                for af in ai_findings:
                    if af["text"] not in [cf["text"] for cf in current_findings if isinstance(cf, dict)]:
                        current_findings.append(af)
                state["findings"] = current_findings

            # Step 3: Sanitize and Map Tool Calls
            sanitized_calls = []
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    # Map 'tool_name' -> 'name'
                    name = tc.get("name") or tc.get("tool_name")
                    if not name:
                        continue

                    # Ensure ID exists
                    call_id = tc.get("id") or str(uuid.uuid4())[:8]

                    sanitized_calls.append(
                        {
                            "id": call_id,
                            "name": name,
                            "arguments": tc.get("arguments") or tc.get("args") or {},
                        }
                    )

            if sanitized_calls:
                # Loop Detection & Tracking
                current_last_actions = state.get("last_actions") or []
                for tc in sanitized_calls:
                    eid = tc.get("arguments", {}).get("element_id")
                    if eid:
                        if eid in current_last_actions:
                            logger.warning(
                                f"⚠️ LOOP WARNING: Element {eid} targeted again (Recent: {current_last_actions})"
                            )

                        # Add to tracking (maintain last 5)
                        current_last_actions.append(eid)
                        if len(current_last_actions) > 5:
                            current_last_actions.pop(0)

                state["last_actions"] = current_last_actions
                state["next_action"] = {"tool_calls": sanitized_calls}
                messages.append(
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": sanitized_calls,
                    }
                )
            else:
                logger.warning("⚠️ No valid tool calls found.")
                error_msg = "Error: No valid tool_calls block found. Please provide your action in the required JSON format."
                messages.append({"role": "user", "content": error_msg})
                state["messages"] = messages
                state["next_action"] = {"action": "wait"}
                return state

        except Exception as e:
            logger.error(f"❌ Parsing Error: {e}")
            error_msg = f"Error: {str(e)}. Please use the 'name' field for tools and provide valid JSON."
            messages.append({"role": "user", "content": error_msg})
            state["messages"] = messages
            state["next_action"] = {"action": "wait"}
            return state

        state["messages"] = messages
        return state

    except Exception as e:
        logger.error(f"❌ Manager Node Error: {e}")
        state["next_action"] = {"action": "complete"}
        return state

    state["messages"] = messages
    return state
