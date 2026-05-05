from tools.browser_manager import BrowserManager
from tools.action_tool import perform_action, inject_visual_effects
from tools.file_tool import FileTool
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

# Tool definitions in OpenAI/OpenRouter format
WEB_TESTER_TOOLS = [
    {
        "name": "click_element",
        "description": "Clicks an element on the page using its visual SOM ID (the number in the red badge). Use this for buttons, links, and menu items.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_id": {"type": "integer", "description": "The visual SOM ID from the screenshot."}
            },
            "required": ["element_id"]
        }
    },
    {
        "name": "type_text",
        "description": "Types text into an input field or textarea identified by its SOM ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "element_id": {"type": "integer", "description": "The visual SOM ID of the input field."},
                "text": {"type": "string", "description": "The text to type."},
                "press_enter": {"type": "boolean", "description": "Whether to press Enter after typing.", "default": False}
            },
            "required": ["element_id", "text"]
        }
    },
    {
        "name": "scroll",
        "description": "Scrolls the page up or down to reveal more content.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "description": "The direction to scroll."}
            },
            "required": ["direction"]
        }
    },
    {
        "name": "wait",
        "description": "Pauses execution for a few seconds to wait for animations or page loads.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "Number of seconds to wait."}
            },
            "required": ["seconds"]
        }
    },
    {
        "name": "report_issue",
        "description": "Reports a security vulnerability, UI bug, or functional issue found during testing.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Summary of the issue."},
                "description": {"type": "string", "description": "Detailed description and steps to reproduce."},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]}
            },
            "required": ["title", "description", "severity"]
        }
    },
    {
        "name": "finish_page_test",
        "description": "Ends the testing session on the current page when all goals are met or the page is fully explored.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "A final summary of the findings on this page."}
            },
            "required": ["summary"]
        }
    },
    {
        "name": "list_files",
        "description": "Liệt kê các file có sẵn trong thư mục 'test_assets' để chuẩn bị upload.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "upload_file",
        "description": "Tải một file từ thư mục 'test_assets' lên một phần tử web (thường là nút Upload hoặc input file).",
        "parameters": {
            "type": "object",
            "properties": {
                "element_id": {"type": "integer", "description": "SOM ID của phần tử upload."},
                "filename": {"type": "string", "description": "Tên file muốn upload (ví dụ: 'sample_image.png')."}
            },
            "required": ["element_id", "filename"]
        }
    }
]

async def click_element(element_id: int, plan: list) -> str:
    """
    Clicks an element on the page based on its visual SOM ID.
    
    Args:
        element_id: The number displayed next to the element in the screenshot.
        plan: The current page plan containing element metadata.
        
    Returns:
        A string describing the result (Success or Error).
    """
    target = next((item for item in plan if item.get("som_id") == element_id), None)
    if not target:
        return f"Error: Element ID [{element_id}] not found in current view. It might have shifted or disappeared."
    
    # Resolve coordinates if available, otherwise fallback to selector
    rect = target.get("rect")
    x, y, selector = None, None, None
    
    if rect:
        x = rect["centerX"]
        y = rect["centerY"]
        selector = target.get("best_selector") or target.get("selector")
        logger.info(f"🎯 Clicking at (x: {x}, y: {y}) for Element ID: {element_id}")
    else:
        selector = target.get("best_selector") or target.get("selector")
        logger.info(f"🖱️ Clicking by selector (no coordinates) for Element ID: {element_id}")
    
    page = await BrowserManager.get_page()
    
    # Pillar: Absolute Coordinate Tracking
    is_sidebar = target.get("is_sidebar", False)
    current_scroll_x = await page.evaluate("window.scrollX")
    current_scroll_y = await page.evaluate("window.scrollY")
    
    # Sidebar elements are already viewport-relative (from dom_tool.py logic)
    # Document elements need compensation: final = doc - current_scroll
    final_x, final_y = x, y
    if x is not None and y is not None and not is_sidebar:
        final_x = x - current_scroll_x
        final_y = y - current_scroll_y

    # Priority: ID > Selector. Avoid text= for scroll logic to prevent hangs.
    scroll_selector = target.get("best_selector")
    if scroll_selector and scroll_selector.startswith("text="):
        scroll_selector = target.get("selector")

    if scroll_selector and not is_sidebar:
        try:
            # FAST PATH: Reduce timeout to 3s
            loc = page.locator(scroll_selector).first
            await loc.scroll_into_view_if_needed(timeout=3000)
            # 🚨 300ms Settle Time after scroll
            await asyncio.sleep(0.3)
            
            # Recalculate after scroll if not sidebar
            current_scroll_x = await page.evaluate("window.scrollX")
            current_scroll_y = await page.evaluate("window.scrollY")
            final_x = x - current_scroll_x
            final_y = y - current_scroll_y
        except Exception as e:
            logger.warning(f"⚠️ Could not scroll element {element_id} into view: {e}")

    # Log EXACT pixel coordinates (Viewport-relative for clicking)
    logger.info(f"🎯 Clicking at Viewport (vx: {final_x}, vy: {final_y}) for Element ID: {element_id} (Sidebar: {is_sidebar})")

    result = await perform_action(
        action_type="click",
        selector=target.get("best_selector") or target.get("selector"),
        x=final_x,
        y=final_y,
        is_viewport_coords=True # Tell perform_action not to convert again
    )
    # Pillar 2: Animation-Aware Delay (Reduced for speed)
    await asyncio.sleep(0.8)
    return f"✅ SUCCESS: Clicked element [{element_id}]. Result: {result}. Current URL is: {page.url}"

async def type_text(element_id: int, text: str, plan: list, press_enter: bool = False) -> str:
    """
    Types text into an input field.
    """
    target = next((item for item in plan if item.get("som_id") == element_id), None)
    if not target:
        return f"Error: Element ID [{element_id}] not found."
    
    rect = target.get("rect")
    x, y = None, None
    if rect:
        x = rect["centerX"]
        y = rect["centerY"]
    
    selector = target.get("best_selector") or target.get("selector")
    
    page = await BrowserManager.get_page()
    
    # FAST PATH: Click coordinates first, then type directly
    if x is not None and y is not None:
        try:
            is_sidebar = target.get("is_sidebar", False)
            scroll_y = await page.evaluate("window.scrollY")
            scroll_x = await page.evaluate("window.scrollX")
            
            # Sidebar Rule: No compensation if sidebar
            vx = x if is_sidebar else x - scroll_x
            vy = y if is_sidebar else y - scroll_y
            
            # Scroll if needed (Fast) - only for non-sidebar
            if not is_sidebar and (vy < 0 or vy > 600):
                await page.evaluate(f"window.scrollTo({{top: {y - 200}, behavior: 'instant'}})")
                # 🚨 Settle Time
                await asyncio.sleep(0.3)
                scroll_y = await page.evaluate("window.scrollY")
                vx, vy = x - scroll_x, y - scroll_y

            # Clean-Slate: Clear field before typing
            js_handle = await page.evaluate_handle(
                "(coords) => document.elementFromPoint(coords.x, coords.y)",
                {"x": vx, "y": vy}
            )
            element = js_handle.as_element()
            if element:
                # Use Playwright's native clear if possible
                try:
                    await element.fill("")
                except:
                    # Fallback to keyboard clear
                    await page.mouse.click(vx, vy)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
            else:
                # Direct keyboard clear fallback
                await page.mouse.click(vx, vy)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")

            await asyncio.sleep(0.1)
            await page.keyboard.type(text, delay=30)
            if press_enter:
                await page.keyboard.press("Enter")
            
            # Pillar 2: Animation-Aware Delay (Reduced)
            await asyncio.sleep(0.5)
            return f"✅ SUCCESS: Typed '{text}' into element [{element_id}] after clearing field. Current URL is: {page.url}"
        except Exception as e:
            logger.warning(f"⚠️ Coordinate typing failed, falling back to selector: {e}")

    # Fallback to selector
    result = await perform_action(
        action_type="type",
        selector=selector,
        text=text,
        x=x,
        y=y,
        is_viewport_coords=False # Fallback uses doc coords
    )
    return f"✅ SUCCESS: Typed '{text}' into element [{element_id}]. Result: {result}. Current URL is: {page.url}"

async def scroll(direction: str) -> str:
    """
    Scrolls the page.
    """
    page = await BrowserManager.get_page()
    if direction.lower() == "down":
        await page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
    else:
        await page.evaluate("window.scrollBy(0, -window.innerHeight / 2)")
    
    # Pillar 2: Animation-Aware Delay
    await asyncio.sleep(1.2)
    return f"✅ SUCCESS: Scrolled {direction}. Content shifted. Current URL is: {page.url}"

async def wait(seconds: float) -> str:
    """
    Wait for a specified number of seconds.
    """
    await asyncio.sleep(seconds)
    return f"Action: Waited {seconds}s."

async def report_issue(title: str, description: str, severity: str) -> str:
    """
    Reports a discovered security vulnerability or bug.
    """
    logger.info(f"🚨 ISSUE REPORTED: [{severity.upper()}] {title}")
    return f"Reported {severity} issue: {title}. Recorded in findings."

async def finish_page_test(summary: str) -> str:
    """
    Marks the current page testing as complete.
    """
    await asyncio.sleep(1.0)
    return "PAGE_TEST_COMPLETE: " + summary

async def list_files() -> str:
    """Liệt kê danh sách file có sẵn trong test_assets."""
    ft = FileTool()
    return ft.list_test_files()

async def upload_file(element_id: int, filename: str, plan: list) -> str:
    """Tải một file lên phần tử web được chỉ định."""
    target = next((item for item in plan if item.get("som_id") == element_id), None)
    if not target:
        return f"Error: Element ID [{element_id}] not found."
    
    selector = target.get("selector")
    if not selector:
        return f"Error: Element [{element_id}] has no valid selector."

    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser page not available."

    # Visual feedback
    await inject_visual_effects(page)
    if "rect" in target:
        x = target["rect"]["x"] + target["rect"]["width"] / 2
        y = target["rect"]["y"] + target["rect"]["height"] / 2
        await page.evaluate(f"window.showClickEffect({x}, {y})")
    
    ft = FileTool()
    result = await ft.upload_file_to_element(page, selector, filename)
    
    # Wait a bit for upload to process
    await asyncio.sleep(1)
    return result
