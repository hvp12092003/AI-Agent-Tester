import json
import asyncio
import logging
import traceback
from multi_agent.state import AgentState
from tools.browser_manager import BrowserManager
from tools.dom_tool import get_interactive_elements
from tools.crawler_tool import create_page_plan
from tools.agent_tools import (
    click_element, type_text, scroll, wait, 
    report_issue, finish_page_test,
    list_files, upload_file
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def action_node(state: AgentState) -> AgentState:
    """
    Autonomous Action Node:
    - Executes native tool calls from state["next_action"].
    - Updates conversation history with tool results.
    - Re-scans the DOM after actions to keep SOM IDs fresh.
    """
    try:
        # Increment step count
        step_count = state.get("page_step_count", 0) + 1
        state["page_step_count"] = step_count
        
        if step_count > 20:
            logger.warning(f"⚠️ Page step limit reached ({step_count}). Forcing page transition.")
            state["history"] = state.get("history") or []
            state["history"].append("⚠️ Reached max steps (20) on this page. Stopping further actions here.")
            state["page_step_count"] = 0
            state["next_action"] = None
            return state

        next_action = state.get("next_action")
        if not next_action or "tool_calls" not in next_action:
            return state

        tool_calls = next_action["tool_calls"]
        messages = state.get("messages") or []
        plan = state.get("current_page_plan") or []
        history = state.get("history") or []
        
        page = await BrowserManager.get_page()
        if not page:
            return state

        step_logs = []
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("arguments") or tool_call.get("args") or {}
            tool_id = tool_call.get("id", "no_id")
            
            logger.info(f"🛠️ Executing Tool [{tool_id}]: {tool_name}({tool_args})")
            
            # Tracking for Environment Feedback (Objective Feedback)
            url_before = page.url
            elements_before = len(state.get("dom_elements") or [])
            
            result = ""
            try:
                # Helper to update last_action_location
                def update_cursor(eid, plan):
                    target = next((item for item in plan if item.get("som_id") == eid), None)
                    if target and "rect" in target:
                        state["last_action_location"] = {
                            "x": target["rect"]["x"] + target["rect"]["width"] / 2,
                            "y": target["rect"]["y"] + target["rect"]["height"] / 2
                        }
                    else:
                        state["last_action_location"] = None

                if tool_name == "click_element":
                    eid = tool_args.get("element_id")
                    update_cursor(eid, plan)
                    result = await click_element(eid, plan)
                elif tool_name == "type_text":
                    eid = tool_args.get("element_id")
                    update_cursor(eid, plan)
                    result = await type_text(
                        eid, 
                        tool_args.get("text"), 
                        plan, 
                        tool_args.get("press_enter", False)
                    )
                elif tool_name == "scroll":
                    state["last_action_location"] = None # Clear cursor on scroll
                    result = await scroll(tool_args.get("direction"))
                elif tool_name == "wait":
                    state["last_action_location"] = None
                    result = await wait(tool_args.get("seconds"))
                elif tool_name == "report_issue":
                    state["last_action_location"] = None
                    result = await report_issue(
                        tool_args.get("title"), 
                        tool_args.get("description"), 
                        tool_args.get("severity")
                    )
                    # Sync findings
                    findings = state.get("findings") or []
                    findings.append({
                        "title": tool_args.get("title"),
                        "text": tool_args.get("description"),
                        "severity": tool_args.get("severity"),
                        "url": page.url,
                        "timestamp": str(asyncio.get_event_loop().time())
                    })
                    state["findings"] = findings
                elif tool_name == "finish_page_test":
                    state["last_action_location"] = None
                    result = await finish_page_test(tool_args.get("summary"))
                    state["page_step_count"] = 0
                elif tool_name == "list_files":
                    result = await list_files()
                elif tool_name == "upload_file":
                    eid = tool_args.get("element_id")
                    update_cursor(eid, plan)
                    result = await upload_file(
                        eid,
                        tool_args.get("filename"),
                        plan
                    )
                else:
                    result = f"Error: Tool '{tool_name}' not found."
            except Exception as e:
                result = f"Error executing {tool_name}: {str(e)}"
                logger.error(f"❌ Tool Execution Failure: {str(e)}")

            # Update messages for the LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": result
            })

            # Sequential Re-scan and Environment Feedback Capture
            elements_after = elements_before
            url_after = url_before
            
            if tool_name in ["click_element", "type_text", "scroll"]:
                await asyncio.sleep(1.5)
                new_dom = await get_interactive_elements()
                if new_dom and "❌" not in new_dom:
                    state["dom_elements"] = new_dom
                    elements_after = len(new_dom)
                    url_after = page.url
                    
                    plan = create_page_plan(new_dom, current_url=page.url)
                    state["current_page_plan"] = plan
                    state["testing_url"] = page.url

            # Construct Detailed Step Log
            step_log = f"[Step {step_count}] Tool: {tool_name}({tool_args}) | Result: {result} | URL Shift: {url_before} -> {url_after} | DOM Shift: {elements_before} -> {elements_after}"
            
            if url_before == url_after and elements_before == elements_after:
                step_log += " | NOTE: The environment did not change. The action might be ineffective, opened a hidden dropdown, or triggered an error."
            
            step_logs.append(step_log)

        state["messages"] = messages
        if step_logs:
            history.extend(step_logs)
        state["next_action"] = None
        return state

    except Exception as e:
        logger.error(f"❌ Critical Error in action_node: {e}\n{traceback.format_exc()}")
        state["history"] = state.get("history") or []
        state["history"].append(f"❌ Critical Error in Action Node: {str(e)}")
        return state
