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
        plan = state.get("current_page_plan") or []
        history = state.get("history") or []
        page = await BrowserManager.get_page()

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
                    result = await handler(**tool_args, plan=plan, page=page)
                except TypeError:
                    try:
                        result = await handler(**tool_args, plan=plan)
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

            # === APPEND RESULT TO MESSAGES ===
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": result,
            })

            # Human-readable log
            log_entry = f"{'✅' if '✅' in result else '❌'} {tool_name}"
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
            if eid and plan:
                target = next((item for item in plan if item.get("som_id") == eid), None)
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
                
            # 2. Wait for stabilization
            await asyncio.sleep(0.5)

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
