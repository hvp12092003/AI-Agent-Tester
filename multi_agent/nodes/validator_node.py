"""
Validator Node — The "QA Inspector" of the Agent.

Responsibilities (runs after critical actions defined by Scoping):
1. Capture current screenshot + DOM state
2. Compare Actual Result against Expected Result from test_case_data
   (or infer Expected using common sense if test_case_data is None)
3. Classify any mismatch using severity: Critical / Major / Minor / Trivial
4. Apply Visual Tolerance rules to avoid false positives from Mac↔Linux rendering differences
5. Append result to validation_results
6. Set is_bug=True and severity if a failure is found
"""
import json
import re
import base64
import logging
from datetime import datetime
from multi_agent.state import AgentState
from agents.llm_factory import LLMFactory
from tools.dom_tool import format_elements
from tools.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


VALIDATOR_SYSTEM_PROMPT = """You are an expert QA Inspector with deep knowledge of web UI testing.
Your job is to compare the ACTUAL state of the page (screenshot + DOM) against the EXPECTED RESULT.

VISUAL TOLERANCE RULES (Cross-Platform Rendering):
This agent runs on macOS but may be deployed on Linux. Font rendering,
subpixel antialiasing, and border-radius may differ by 1-3px across OSes.

DO NOT flag as a bug:
- Sub-pixel font weight differences (e.g., slightly bolder/lighter text)
- Border-radius differences of 1-3px
- Shadow blur variations of <=5px
- Micro-alignment shifts of <=3px on any element
- Any visual difference that requires zooming in >150% to notice
- Slight color tint variation caused by OS gamma/color profile (within 5% hue)

FORM ERRORS & MISSING DATA RULES:
- Pay close attention to any error messages on the screen (e.g., "Vui lòng tải lên ảnh", "Require", "Trường này là bắt buộc").
- If the test case required uploading a file or filling a field, and the page shows an error about it being missing or invalid, flag it as Major or Critical depending on the impact.
- Do not assume the operation was successful just because the page didn't crash. Check if all required data is actually present and accepted.
- FILE UPLOAD & PREVIEW (CONTEXT-AWARE — READ CAREFULLY):
  * HAPPY PATH test (valid file, expected to succeed): If a thumbnail preview, a loaded image, or a filename is displayed → upload was SUCCESSFUL. Do NOT flag as bug.
  * NEGATIVE test (invalid file type like .exe/.txt, oversized, empty — expected to be REJECTED): If the file appears in a preview area OR no error message is shown → this is a BUG (the system failed to block the invalid file). The CORRECT behavior is an error message blocking the upload. A preview appearing when the file should be rejected IS the bug.
  * To determine which case applies: check the Expected Result and Recent Action History for keywords like "invalid", "không hợp lệ", "định dạng sai", "oversized", "quá lớn", "empty", "rỗng".

DO flag as Minor if ANY of these are true (and only if clearly visible at 100% zoom):
- An element is visually misaligned by MORE than 5px from its expected position
- Text content is incorrect (wrong label, wrong number, wrong language)
- A color is CLEARLY wrong (e.g., a button that should be blue is rendered red)
- An element is partially hidden, clipped, or overlapping another element incorrectly

DO flag as Major if:
- A feature is broken but the page still loads (e.g., button clicks do nothing, form doesn't submit)
- Data shown is incorrect (wrong counts, wrong user info)
- Navigation redirects to wrong page
- A required upload or field was missed or rejected by the system with an error message.

DO flag as Critical ONLY if:
- A core function fails completely (login does not work, save/submit fails with error)
- Content is entirely missing (blank page, empty sections that should have data)
- A destructive error occurs (data lost, HTTP 500, unhandled crash)

DO flag as Trivial if:
- Minor typo in non-critical label
- Slight spacing difference (4-8px) that doesn't affect usability
- Icon slightly different from expected but meaning is clear

SEVERITY DECISION: Choose exactly ONE from: Critical, Major, Minor, Trivial.
If no issues found, set passed=true and severity=null.

LANGUAGE RULE (🚨 MANDATORY):
- ALL text fields in your JSON output MUST be written in VIETNAMESE (Tiếng Việt).
- This applies to: actual_result, expected_result, discrepancy, evidence.
- Do NOT use English in any of these fields.

OUTPUT a single JSON object:
{
  "passed": false,
  "severity": "Critical | Major | Minor | Trivial | null",
  "actual_result": "Những gì bạn quan sát thấy trong ảnh chụp màn hình/DOM",
  "expected_result": "Kết quả mong đợi",
  "discrepancy": "Mô tả rõ ràng sự không khớp (chuỗi rỗng nếu passed=true)",
  "evidence": "Phần tử DOM hoặc khu vực giao diện nào thể hiện vấn đề (chuỗi rỗng nếu passed=true)"
}
"""

VALIDATOR_USER_PROMPT = """--- CURRENT PAGE STATE ---
URL: {current_url}
DOM SUMMARY: {dom_summary}

--- CHECKPOINT BEING VALIDATED ---
Checkpoint: "{checkpoint}"

--- EXPECTED RESULT ---
{expected_result}

--- RECENT ACTION HISTORY ---
{recent_history}

--- INSTRUCTION ---
Look at the screenshot carefully. Apply the Visual Tolerance rules.
Compare what you SEE with the Expected Result above.
Return ONLY valid JSON. No markdown, no explanation.
"""


async def validator_node(state: AgentState) -> AgentState:
    """Compare Actual vs Expected. Flag bugs with severity. Apply visual tolerance."""
    logger.info("🔬 [Validator] Running post-action validation...")

    try:
        screenshot = state.get("screenshot")
        extra_screenshots = state.get("extra_screenshots") or []

        # Prefer instant_screenshot for validation — it captures flash notifications
        # (toasts, alerts) that appear right after an action and may already be gone
        # by the time the stable final screenshot was taken.
        validation_screenshot = extra_screenshots[0] if extra_screenshots else screenshot

        if not validation_screenshot:
            logger.warning("⚠️ [Validator] No screenshot available. Skipping validation.")
            return state

        model_config = state.get("model_config") or {}
        eval_model = model_config.get("eval_model") or state.get("model_name") or "google/gemini-2.0-flash-001"

        page = await BrowserManager.get_page()
        current_url = page.url if page else "unknown"

        dom_elements = state.get("dom_elements") or []
        dom_summary = format_elements(dom_elements)[:2000]  # Truncate for token budget

        recent_history = "\n".join((state.get("history") or [])[-5:]) or "None"

        # Determine checkpoint and expected result
        test_case_data = state.get("test_case_data") or {}
        test_scope = state.get("test_scope") or {}
        
        if isinstance(test_scope, dict):
            checkpoints = test_scope.get("checkpoints", [])
        else:
            checkpoints = []

        # Find most relevant checkpoint from history
        history_str = " | ".join((state.get("history") or [])[-3:])
        checkpoint = "After the latest action"
        for cp in checkpoints:
            if cp and any(keyword in history_str.lower() for keyword in cp.lower().split()):
                checkpoint = cp
                break

        # Build expected result string
        expected_results = {}
        if isinstance(test_case_data, dict):
            expected_results = test_case_data.get("expected_results", {})
        elif isinstance(test_case_data, list):
            if len(test_case_data) > 0 and isinstance(test_case_data[0], dict):
                expected_results = test_case_data[0].get("expected_results", {})
            else:
                expected_results = "Multiple test cases provided."

        if isinstance(expected_results, dict):
            expected_str = json.dumps(expected_results, ensure_ascii=False, indent=2)
        elif isinstance(expected_results, str):
            expected_str = expected_results
        else:
            expected_str = "No specific expected result provided. Use common sense: the page should function correctly, show appropriate content, and have no visible errors."


        user_prompt = VALIDATOR_USER_PROMPT.format(
            current_url=current_url,
            dom_summary=dom_summary,
            checkpoint=checkpoint,
            expected_result=expected_str,
            recent_history=recent_history,
        )

        # Call eval model with vision
        image_bytes = base64.b64decode(validation_screenshot)
        llm = LLMFactory()

        response_text = await llm.generate_content(
            model_name=eval_model,
            prompt=user_prompt,
            image_data=image_bytes,
            tools=None,
            history=[{"role": "system", "content": VALIDATOR_SYSTEM_PROMPT}],
        )

        # Parse response
        result = {}
        try:
            clean = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", response_text or "", flags=re.DOTALL).strip()
            json_match = re.search(r"\{.*\}", clean, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
        except Exception as parse_err:
            logger.warning(f"⚠️ [Validator] Could not parse JSON response: {parse_err}")
            result = {"passed": True, "severity": None}

        # Build validation record
        passed = result.get("passed", True)
        severity = result.get("severity")
        if severity == "null" or severity == "":
            severity = None

        validation_record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "checkpoint": checkpoint,
            "url": current_url,
            "passed": passed,
            "severity": severity,
            "actual_result": result.get("actual_result", ""),
            "expected_result": result.get("expected_result", expected_str[:200]),
            "discrepancy": result.get("discrepancy", ""),
            "evidence": result.get("evidence", ""),
            "screenshot": validation_screenshot,  # Store instant capture (catches notifications)
        }

        # Append to validation results
        validation_results = state.get("validation_results") or []
        validation_results.append(validation_record)
        state["validation_results"] = validation_results

        # Update bug flags
        if not passed and severity:
            state["is_bug"] = True
            state["severity"] = severity

            # Also add to findings for backwards compat with existing UI/report
            findings = state.get("findings") or []
            
            # Save screenshot to file for report
            import os
            import uuid
            
            os.makedirs("reports", exist_ok=True)
            screenshot_path = f"reports/bug_{uuid.uuid4().hex[:8]}.jpg"
            try:
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(screenshot))
            except Exception as e:
                logger.warning(f"⚠️ Failed to save screenshot: {e}")
                screenshot_path = None

            findings.append({
                "title": f"[{severity}] Kiểm định thất bại tại: {checkpoint}",
                "text": result.get("discrepancy", "Phát hiện sự không khớp"),
                "details": f"Thực tế: {result.get('actual_result', '')}\nKỳ vọng: {result.get('expected_result', '')}",
                "severity": severity.lower(),
                "url": current_url,
                "timestamp": validation_record["timestamp"],
                "screenshot": screenshot_path,
            })
            state["findings"] = findings

            logger.warning(f"🐛 [Validator] BUG FOUND [{severity}] at '{checkpoint}': {result.get('discrepancy', '')[:100]}")
        else:
            state["is_bug"] = False
            state["severity"] = None
            logger.info(f"✅ [Validator] PASSED at '{checkpoint}'")

        # Log to history
        status_icon = "✅" if passed else f"🐛[{severity}]"
        history = state.get("history") or []
        history.append(f"{status_icon} [Kiểm định] '{checkpoint}' → {'ĐẠT' if passed else f'THẤT BẠI ({severity})'}")
        state["history"] = history

        return state

    except Exception as e:
        logger.error(f"❌ [Validator] Unexpected error: {e}")
        state["is_bug"] = False
        state["severity"] = None
        return state
