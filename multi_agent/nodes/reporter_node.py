"""
Reporter Node — The "QA Manager" that writes the final report.

Responsibilities (runs at END of workflow or on Critical bug short-circuit):
1. Aggregate history + validation_results + findings
2. Call eval_model to generate a structured Test Summary (Passed/Failed/Untested)
3. Build detailed Defect Logs with severity and visual evidence
4. Call generate_excel_report() with new 3-sheet schema
5. Store final_report dict in AgentState for UI display
"""
import json
import re
import base64
import os
import logging
from datetime import datetime
from multi_agent.state import AgentState
from agents.llm_factory import LLMFactory
from tools.report_tool import generate_excel_report_v3

logger = logging.getLogger(__name__)


REPORTER_SYSTEM_PROMPT = """You are a Senior QA Manager writing the final test execution report.
You will receive:
- The original test goal and URL
- A list of validation results (Actual vs Expected checks)
- A list of bug findings
- The full action history log

Your job is to synthesize this into a structured QA report.

OUTPUT a single JSON object with this exact schema:
{
  "summary": {
    "total_test_cases": 0,
    "passed": 0,
    "failed": 0,
    "untested": 0,
    "overall_status": "PASS | FAIL | PARTIAL"
  },
  "defect_log": [
    {
      "id": "BUG-001",
      "title": "Short bug title",
      "severity": "Critical | Major | Minor | Trivial",
      "checkpoint": "Where it was found",
      "url": "Page URL",
      "actual": "What actually happened",
      "expected": "What should have happened",
      "steps_to_reproduce": "1. Go to... 2. Click..."
    }
  ],
  "recommendations": [
    "Fix the login validation logic on /admin/login",
    "Review the form submission handler"
  ],
  "executive_summary": "One paragraph plain-language summary for non-technical stakeholders"
}

RULES:
- "total_test_cases" = number of checkpoints that were validated.
- "passed" = checkpoints where passed=true.
- "failed" = checkpoints where passed=false.
- "untested" = checkpoints listed in scope that were never reached.
- "overall_status" = "PASS" if all passed, "FAIL" if any Critical/Major found, "PARTIAL" otherwise.
- Format "steps_to_reproduce" as numbered steps based on action history context.
- Keep "executive_summary" under 100 words, non-technical language.
- Tất cả nội dung báo cáo (tiêu đề bug, mô tả, tóm tắt, khuyến nghị) PHẢI được viết bằng TIẾNG VIỆT.
- Return ONLY valid JSON. No markdown fences, no explanation.
"""

REPORTER_USER_PROMPT = """--- TEST SESSION OVERVIEW ---
Goal: {goal}
URL: {base_url}
Executed Steps: {step_count}
Model Used (Brain): {brain_model}
Model Used (Eval): {eval_model}
Test Scope: {test_scope}

--- VALIDATION RESULTS ---
{validation_results_str}

--- FINDINGS (Bug Reports) ---
{findings_str}

--- ACTION HISTORY (last 20 entries) ---
{history_str}

--- INSTRUCTION ---
Generate the final QA report JSON as described in your system instructions.
"""


async def reporter_node(state: AgentState) -> AgentState:
    """Aggregate all results → generate structured Test Summary + Defect Log → export Excel."""
    logger.info("📋 [Reporter] Generating final QA report...")

    try:
        model_config = state.get("model_config") or {}
        eval_model = model_config.get("eval_model") or state.get("model_name") or "google/gemini-2.0-flash-001"
        brain_model = model_config.get("brain_model") or state.get("model_name") or "unknown"

        validation_results = state.get("validation_results") or []
        findings = state.get("findings") or []
        history = state.get("history") or []
        test_scope = state.get("test_scope") or {}

        # ── Build validation_results from task_plan when validator didn't run ──
        # This ensures the "Kịch bản kiểm thử" Excel sheet is always populated
        task_plan = state.get("task_plan") or []
        if not validation_results and task_plan:
            logger.info(f"📋 [Reporter] No validation_results found. Building from task_plan ({len(task_plan)} steps).")
            base_url = state.get("base_url", "")
            for step_item in task_plan:
                step_text = step_item.get("step", "")
                status = step_item.get("status", "todo")

                if status == "done":
                    passed = True
                    status_label = "done"
                    severity = None
                    discrepancy = ""
                elif status == "failed":
                    passed = False
                    status_label = "failed"
                    severity = "Minor"
                    discrepancy = "Bước thực hiện không thành công."
                elif status == "skipped":
                    passed = True   # treat skipped as neutral/pass for summary calc
                    status_label = "skipped"
                    severity = None
                    discrepancy = "Bước được bỏ qua theo yêu cầu."
                else:
                    # todo / doing → untested
                    passed = False
                    status_label = "untested"
                    severity = None
                    discrepancy = "Bước chưa được thực hiện (agent dừng sớm hoặc chưa tới bước này)."

                validation_results.append({
                    "checkpoint": step_text,
                    "url": base_url,
                    "passed": passed,
                    "severity": severity,
                    "discrepancy": discrepancy,
                    "evidence": "",
                    "_plan_status": status_label,   # internal flag for Excel coloring
                })

        # Serialize for prompt (strip screenshots and internal flags to save tokens)
        def strip_screenshot(record):
            r = dict(record)
            r.pop("screenshot", None)
            r.pop("_plan_status", None)   # internal flag, not useful for AI
            return r

        validation_str = json.dumps([strip_screenshot(v) for v in validation_results], indent=2, ensure_ascii=False)
        findings_str = json.dumps([strip_screenshot(f) for f in findings], indent=2, ensure_ascii=False)
        history_str = "\n".join(history[-20:]) or "None"
        scope_str = json.dumps({k: v for k, v in test_scope.items() if not k.startswith("_")}, ensure_ascii=False)

        user_prompt = REPORTER_USER_PROMPT.format(
            goal=state.get("goal", ""),
            base_url=state.get("base_url", "Unknown"),
            step_count=state.get("current_step_count", 0),
            brain_model=brain_model,
            eval_model=eval_model,
            test_scope=scope_str,
            validation_results_str=validation_str[:3000],
            findings_str=findings_str[:2000],
            history_str=history_str,
        )

        # Call eval model (no image needed for reporting)
        llm = LLMFactory()
        response_text = await llm.generate_content(
            model_name=eval_model,
            prompt=user_prompt,
            image_data=None,
            tools=None,
            history=[{"role": "system", "content": REPORTER_SYSTEM_PROMPT}],
        )

        # Parse report JSON
        report_data = {}
        try:
            clean = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", response_text or "", flags=re.DOTALL).strip()
            json_match = re.search(r"\{.*\}", clean, re.DOTALL)
            if json_match:
                report_data = json.loads(json_match.group(0))
        except Exception as parse_err:
            logger.warning(f"⚠️ [Reporter] Could not parse JSON: {parse_err}. Building fallback report.")

        # Fallback report if AI parsing fails
        if not report_data:
            # When validation_results were built from task_plan, use _plan_status for accurate counts
            n_pass = sum(1 for v in validation_results if v.get("_plan_status") == "done" or (not v.get("_plan_status") and v.get("passed")))
            n_fail = sum(1 for v in validation_results if v.get("_plan_status") == "failed" or (not v.get("_plan_status") and not v.get("passed")))
            n_skipped = sum(1 for v in validation_results if v.get("_plan_status") == "skipped")
            n_untested = sum(1 for v in validation_results if v.get("_plan_status") == "untested")
            # Correct for old-style: if no _plan_status at all, use checkpoints count
            if not any(v.get("_plan_status") for v in validation_results):
                checkpoints = test_scope.get("checkpoints", [])
                n_untested = max(0, len(checkpoints) - len(validation_results))
                n_skipped = 0
            total_executed = n_pass + n_fail
            report_data = {
                "summary": {
                    "total_test_cases": total_executed,
                    "passed": n_pass,
                    "failed": n_fail,
                    "untested": n_untested + n_skipped,
                    "overall_status": "FAIL" if n_fail > 0 else ("PARTIAL" if n_untested > 0 else "PASS"),
                },
                "defect_log": [
                    {
                        "id": f"BUG-{i+1:03d}",
                        "title": f.get("title", "Unknown issue"),
                        "severity": f.get("severity", "minor"),
                        "checkpoint": f.get("title", ""),
                        "url": f.get("url", ""),
                        "actual": f.get("text", ""),
                        "expected": "",
                        "steps_to_reproduce": "",
                    }
                    for i, f in enumerate(findings)
                ],
                "recommendations": ["Xem xét các kịch bản kiểm thử thất bại và sửa các lỗi đã xác định."],
                "executive_summary": f"Kiểm thử tự động hoàn thành. {n_pass} kịch bản đạt ✅, {n_fail} kịch bản lỗi ❌, {n_skipped} bước bỏ qua ⏭️, {n_untested} chưa kiểm tra ⬜.",
            }

        # Attach metadata
        report_data["meta"] = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "goal": state.get("goal", ""),
            "base_url": state.get("base_url", ""),
            "brain_model": brain_model,
            "eval_model": eval_model,
            "early_stop": state.get("severity") == "Critical" and not state.get("is_complete"),
        }

        state["final_report"] = report_data

        # Export Excel with new 3-sheet format
        try:
            excel_path = generate_excel_report_v3(
                summary=report_data.get("summary", {}),
                defect_log=report_data.get("defect_log", []),
                validation_results=validation_results,
                history=history,
                meta=report_data.get("meta", {}),
                executive_summary=report_data.get("executive_summary", ""),
                recommendations=report_data.get("recommendations", []),
            )
            if excel_path:
                state["final_report"]["excel_path"] = excel_path
                logger.info(f"📊 [Reporter] Excel report saved: {excel_path}")
        except Exception as excel_err:
            logger.warning(f"⚠️ [Reporter] Excel export failed: {excel_err}")

        # Mark as complete
        state["is_complete"] = True

        # Log to history
        summary = report_data.get("summary", {})
        history_entry = (
            f"📋 [Reporter] Đã tạo báo cáo kết quả → "
            f"Đạt: {summary.get('passed', 0)}, "
            f"Thất bại: {summary.get('failed', 0)}, "
            f"Chưa kiểm thử: {summary.get('untested', 0)} | "
            f"Trạng thái chung: {summary.get('overall_status', 'N/A')}"
        )
        history.append(history_entry)
        state["history"] = history
        state["last_thought"] = history_entry

        logger.info(f"✅ [Reporter] Done. {history_entry}")
        return state

    except Exception as e:
        logger.error(f"❌ [Reporter] Unexpected error: {e}")
        state["is_complete"] = True
        return state
