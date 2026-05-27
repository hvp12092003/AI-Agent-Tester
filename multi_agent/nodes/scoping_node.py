"""
Scoping Node — The "Architect" of the QA Session.

Responsibilities (runs ONCE at the start of the workflow):
1. Parse goal + test_case_data (if provided)
2. Determine test scope: UI, Functional, Security
3. Determine viewport: pc or mobile
4. Identify key checkpoints (critical actions that require Validator)
5. Set test_scope in AgentState — does NOT interact with browser
"""
import json
import re
import logging
from multi_agent.state import AgentState
from agents.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

SCOPING_PROMPT_TEMPLATE = """You are a Senior QA Architect. Analyze the test goal and optional test case below.
Your job is to define the testing strategy for an autonomous AI browser agent.

GOAL: {goal}
URL: {url}

TEST CASE DATA (may be empty):
{test_case_data}

OUTPUT a single JSON object with this exact schema:
{{
  "scope": {{
    "ui": true,
    "functional": true,
    "security": false
  }},
  "viewport": "pc",
  "checkpoints": [
    "After clicking Login button",
    "After submitting a form",
    "After deleting an item"
  ],{task_plan_schema}
  "precondition_summary": "Brief summary of prerequisites for the test",
  "risk_level": "low | medium | high",
  "PROVIDED_CREDENTIALS": {{
    "username": "...",
    "password": "..."
  }}
}}

RULES:
- "ui": true if the goal involves checking visual layout, fonts, colors, or responsive design.
- "functional": true if the goal involves testing features (login, CRUD, navigation flow).
- "security": true ONLY if the goal explicitly mentions security, XSS, SQLi, auth bypass.
- "viewport": "mobile" only if the goal mentions mobile, phone, or responsive testing.
- "checkpoints": list of 3-5 critical moments AFTER which the Validator Node must compare Actual vs Expected.
  Examples: "After login", "After form submit", "After page navigation", "After delete action".{task_plan_rule}
- "risk_level": "high" if any security tests are included, "medium" for functional, "low" for UI-only.
- "PROVIDED_CREDENTIALS": Extract any credentials (username, password) provided in the TEST CASE DATA or GOAL. If none are provided, leave values as empty strings.

Return ONLY the JSON. No markdown fences, no explanation.
"""

async def scoping_node(state: AgentState) -> AgentState:
    """Parse goal + test case → set test_scope. Runs once, no browser interaction."""
    logger.info("🔭 [Scoping] Analyzing test goal and defining QA scope...")

    # Skip if already scoped (guard against re-entry)
    if state.get("test_scope") and state["test_scope"].get("_scoped"):
        logger.info("🔭 [Scoping] Already scoped. Skipping.")
        return state

    try:
        model_config = state.get("model_config") or {}
        eval_model = model_config.get("eval_model") or state.get("model_name") or "google/gemini-2.0-flash-001"

        test_case_data = state.get("test_case_data")
        test_case_str = json.dumps(test_case_data, indent=2, ensure_ascii=False) if test_case_data else "Not provided."

        # If task_plan is already populated by app.py (from JSON test case file), we don't need Scoping Node to rebuild it
        has_task_plan = bool(state.get("task_plan"))
        task_plan_schema = "" if has_task_plan else """
  "task_plan": [
    {"step": "[Login] Nhập thông tin tài khoản", "status": "todo"},
    {"step": "[Login] Bấm đăng nhập", "status": "todo"}
  ],"""
        task_plan_rule = "" if has_task_plan else '\n- "task_plan": Break down the user\'s goal into a sequential list of high-level steps. If TEST CASE DATA is provided, summarize it into max 10 steps. Each step MUST have "status": "todo".'

        prompt = SCOPING_PROMPT_TEMPLATE.format(
            goal=state.get("goal", ""),
            url=state.get("url") or state.get("base_url") or "Unknown",
            test_case_data=test_case_str,
            task_plan_schema=task_plan_schema,
            task_plan_rule=task_plan_rule
        )

        llm = LLMFactory()
        response_text = await llm.generate_content(
            model_name=eval_model,
            prompt=prompt,
            image_data=None,
            tools=None,
            history=None,
        )

        # Parse JSON
        scope_data = {}
        try:
            clean = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", response_text or "", flags=re.DOTALL).strip()
            json_match = re.search(r"\{.*\}", clean, re.DOTALL)
            if json_match:
                scope_data = json.loads(json_match.group(0))
        except Exception as parse_err:
            logger.warning(f"⚠️ [Scoping] Could not parse JSON: {parse_err}. Using defaults.")

        # Merge defaults + mark as scoped
        test_scope = {
            "ui": scope_data.get("ui", True) if "scope" not in scope_data else scope_data["scope"].get("ui", True),
            "functional": scope_data.get("functional", True) if "scope" not in scope_data else scope_data["scope"].get("functional", True),
            "security": scope_data.get("security", False) if "scope" not in scope_data else scope_data["scope"].get("security", False),
            "viewport": scope_data.get("viewport", "pc"),
            "checkpoints": scope_data.get("checkpoints", ["After login", "After form submit", "After navigation"]),
            "precondition_summary": scope_data.get("precondition_summary", ""),
            "risk_level": scope_data.get("risk_level", "medium"),
            "_scoped": True,  # Guard flag
        }

        # Handle nested "scope" key from AI
        if "scope" in scope_data:
            s = scope_data["scope"]
            test_scope["ui"] = s.get("ui", True)
            test_scope["functional"] = s.get("functional", True)
            test_scope["security"] = s.get("security", False)
            test_scope["viewport"] = scope_data.get("viewport", "pc")
            test_scope["checkpoints"] = scope_data.get("checkpoints", test_scope["checkpoints"])
            test_scope["precondition_summary"] = scope_data.get("precondition_summary", "")
            test_scope["risk_level"] = scope_data.get("risk_level", "medium")

        state["test_scope"] = test_scope
        
        # Extract provided credentials if any
        state["PROVIDED_CREDENTIALS"] = scope_data.get("PROVIDED_CREDENTIALS", {})
        
        if not state.get("task_plan") and "task_plan" in scope_data:
            state["task_plan"] = scope_data.get("task_plan", [])

        # Log to history
        scope_flags = f"Giao diện={test_scope['ui']}, Chức năng={test_scope['functional']}, Bảo mật={test_scope['security']}"
        history = state.get("history") or []
        history.append(
            f"🔭 [Scoping] Xác định phạm vi → {scope_flags} | Viewport: {test_scope['viewport'].upper()} | "
            f"Mức rủi ro: {test_scope['risk_level']} | Checkpoints: {len(test_scope['checkpoints'])}"
        )
        if state.get("task_plan"):
            history.append(f"🔭 [Scoping] Đã tạo kế hoạch công việc với {len(state['task_plan'])} bước.")
        state["history"] = history

        logger.info(f"✅ [Scoping] Done. {scope_flags}")
        return state

    except Exception as e:
        logger.error(f"❌ [Scoping] Error: {e}")
        # Fallback scope — don't block the workflow
        state["test_scope"] = {
            "ui": True, "functional": True, "security": False,
            "viewport": "pc", "checkpoints": ["After any major action"],
            "precondition_summary": "", "risk_level": "medium", "_scoped": True,
        }
        return state

