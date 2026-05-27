"""
Action Node — Tool Executor with Auto-Dispatch.

Uses the Tool Registry to dynamically find and execute tools.
No more if-elif chains. Adding a new tool = just add @register_tool in its file.
"""
import asyncio
import logging
import traceback
from multi_agent.state import AgentState
from tools.browser_manager import BrowserManager
from tools.dom_tool import get_interactive_elements
from tools.plan_tool import create_page_plan
from tools.tool_registry import get_handler

logger = logging.getLogger(__name__)


async def action_node(state: AgentState) -> AgentState:
    """Execute tool calls from Manager using auto-dispatch."""
    try:
        next_action = state.get("next_action")
        if not next_action or "tool_calls" not in next_action:
            return state

        tool_calls = next_action["tool_calls"]
        messages = state.get("messages") or []
        dom_elements = state.get("dom_elements") or []
        history = state.get("history") or []
        page = await BrowserManager.get_page()

        # Find current step index
        current_plan = state.get("task_plan") or []
        current_idx = 0
        for idx, step in enumerate(current_plan):
            if step.get("status") not in ["done", "failed", "skipped"]:
                current_idx = idx
                break

        for i, tc in enumerate(tool_calls):
            tool_name = tc["name"]
            tool_args = tc.get("arguments") or {}
            tool_id = tc.get("id", "no_id")

            logger.info(f"🛠️ Executing: {tool_name}({tool_args})")
            
            # Record URL before action to detect navigation
            url_before = page.url if page else ""

            # === AUTO-DISPATCH ===
            handler = get_handler(tool_name)
            result = ""

            if handler:
                try:
                    # Inject context that tools might need
                    result = await handler(**tool_args, plan=dom_elements, page=page)
                except TypeError:
                    try:
                        result = await handler(**tool_args, plan=dom_elements)
                    except TypeError:
                        try:
                            result = await handler(**tool_args)
                        except Exception as e:
                            result = f"Error: {tool_name}: {e}"
                except Exception as e:
                    result = f"Error: {tool_name}: {e}"
                    logger.error(f"❌ Tool Error: {e}")
            else:
                result = f"Error: Tool '{tool_name}' không tồn tại."

            # Check for error messages in DOM if the action was a click or upload or type
            if not "Error" in result and tool_name in ["click_element", "upload_file", "type_text", "select_option"]:
                try:
                    error_detected = await page.evaluate("""() => {
                        const errorSelectors = ['.error-message', '.text-danger', '.ivu-form-item-error-tip', '.ant-form-item-explain-error'];
                        for (const sel of errorSelectors) {
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) {
                                return el.innerText;
                            }
                        }
                        const bodyText = document.body.innerText;
                        if (bodyText.includes('Vui lòng tải lên ảnh') || bodyText.includes('Require')) {
                            return 'Phát hiện thông báo lỗi trên màn hình.';
                        }
                        return null;
                    }""")
                    if error_detected:
                        logger.warning(f"⚠️ Error detected in DOM after {tool_name}: {error_detected}")
                        result = f"Error: Phát hiện lỗi trên giao diện sau khi thực hiện {tool_name}: {error_detected}"
                except Exception as e:
                    logger.warning(f"⚠️ Failed to check DOM errors: {e}")

            # === APPEND RESULT TO MESSAGES ===
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": result,
            })

            # Human-readable log in Vietnamese
            vietnamese_tool_names = {
                "click_element": "Click phần tử",
                "click_at_coordinates": "Click tọa độ",
                "type_text": "Nhập văn bản",
                "hover_element": "Rê chuột vào",
                "scroll": "Cuộn trang",
                "navigate_to": "Truy cập URL",
                "select_option": "Chọn tùy chọn",
                "upload_file": "Tải tệp lên",
                "generate_test_file": "Tạo tệp kiểm thử",
                "cleanup_test_assets": "Dọn dẹp tệp tạm",
                "report_issue": "Báo cáo lỗi",
                "finish_task": "Hoàn thành nhiệm vụ",
                "wait": "Chờ đợi",
            }
            vn_name = vietnamese_tool_names.get(tool_name, tool_name)
            log_entry = f"{'✅' if '✅' in result else '❌'} {vn_name}"
            eid = tool_args.get("element_id")
            if eid:
                log_entry += f" [ID:{eid}]"
            if tool_args.get("text"):
                log_entry += f" → '{tool_args['text'][:30]}'"
            history.append(log_entry)

            # === HANDLE SPECIAL TOOLS ===
            if tool_name == "report_issue" and "✅" in result:
                findings = state.get("findings") or []
                findings.append({
                    "title": tool_args.get("title", ""),
                    "text": tool_args.get("description", ""),
                    "severity": tool_args.get("severity", "medium"),
                    "url": page.url if page else "",
                })
                state["findings"] = findings

            if tool_name == "finish_task":
                state["is_complete"] = True

            # Track cursor position for screenshot
            if eid and dom_elements:
                target = next((item for item in dom_elements if item.get("som_id") == eid), None)
                if target and "rect" in target:
                    try:
                        sx = await page.evaluate("window.scrollX")
                        sy = await page.evaluate("window.scrollY")
                        state["last_action_location"] = {
                            "x": target["rect"]["centerX"] - sx,
                            "y": target["rect"]["centerY"] - sy,
                        }
                    except Exception: pass

            # === STABILIZATION & STOP CONDITIONS ===
            # 1. Stop if error or navigation
            url_after = page.url if page else ""
            navigation_happened = (url_after != url_before)
            
            should_break = False
            break_reason = ""

            if "Error" in result:
                should_break = True
                break_reason = f"Cancelled: Previous tool '{tool_name}' failed."
                logger.warning(f"⚠️ Stopping tool sequence due to error in {tool_name}")
                
                # Increment fail count
                step_retry_count = state.get("step_retry_count", 0) + 1
                state["step_retry_count"] = step_retry_count
                
                logger.warning(f"⚠️ Tool failed. Step retry count: {step_retry_count}")
                
                if step_retry_count >= 3:
                    if current_idx < len(current_plan):
                        current_plan[current_idx]["status"] = "failed"
                        logger.warning(f"⚠️ Step {current_idx} failed 3 times. Skipping.")
                        history.append(f"⚠️ Bước [{current_idx}] thất bại 3 lần. Đánh dấu lỗi và bỏ qua.")
                        
                    state["step_retry_count"] = 0 # Reset
                    state["task_plan"] = current_plan # Save plan update
            
            elif navigation_happened and i < len(tool_calls) - 1:
                should_break = True
                break_reason = "Cancelled: Navigation detected, state needs refresh."
                logger.info(f"🌐 Navigation detected ({url_after}). Stopping remaining tool calls.")

            if should_break:
                # IMPORTANT: Must provide a result for EVERY tool_call to avoid API 400 errors
                for j in range(i + 1, len(tool_calls)):
                    tc_rem = tool_calls[j]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_rem.get("id", "no_id"),
                        "name": tc_rem["name"],
                        "content": break_reason,
                    })
                break
                
            # 2. Minimal stabilization — vision_node instant capture handles the rest
            await asyncio.sleep(0.1)

        state["messages"] = messages
        state["history"] = history
        state["next_action"] = None
        return state

    except Exception as e:
        logger.error(f"❌ Action Node Error: {e}\n{traceback.format_exc()}")
        hist = state.get("history") or []
        hist.append(f"❌ Lỗi khi thực hiện hành động: {e}")
        state["history"] = hist
        return state
