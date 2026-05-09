"""
Web Interaction Tools — Click, Type, Hover, Scroll, Press Key, Click at Coordinates.

All tools auto-register via @register_tool decorator.
"""
import asyncio
import logging
from tools.tool_registry import register_tool
from tools.browser_manager import BrowserManager
from tools.utils import inject_visual_effects

logger = logging.getLogger(__name__)


# ============================================================
# HELPER: Resolve SOM ID → element metadata from plan
# ============================================================
def _resolve_element(element_id: int, plan: list) -> dict | None:
    """Find element in plan by SOM ID."""
    return next((item for item in plan if item.get("som_id") == element_id), None)


# ============================================================
# TOOL: click_element
# ============================================================
@register_tool(
    name="click_element",
    description="Click a web element by its SOM ID (red numbers on the image). Use for buttons, links, menus.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID of the element to click."}
        },
        "required": ["element_id"]
    }
)
async def click_element(element_id: int, plan: list = None, **ctx) -> str:
    """Click an element by its SOM ID."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    # Use visible selector to avoid targeting hidden duplicates from dropdowns/modals
    selector = f'[data-som-id="{element_id}"]:visible'
    
    try:
        # 1. Wait for element to exist and be visible
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
        except Exception:
            # Fallback check: does it exist but is hidden?
            exists = await page.locator(f'[data-som-id="{element_id}"]').count() > 0
            if exists:
                return f"Error: Element ID [{element_id}] is currently hidden or obscured. Try scrolling or opening the containing menu."
            return f"Error: Element ID [{element_id}] not found."

        # 2. Ensure visible and centered
        await element.scroll_into_view_if_needed()

        # 3. Get coordinates for visual effect
        try:
            box = await element.bounding_box()
            if box:
                await inject_visual_effects(page)
                vx, vy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
                await page.evaluate(f"window.showClickEffect({vx}, {vy})")
        except Exception: pass

        # 4. Perform the click using the element handle
        await element.click(timeout=5000)
        await asyncio.sleep(0.8)
        return f"✅ Clicked [{element_id}]. URL: {page.url}"

    except Exception as e:
        logger.warning(f"Click failed for [{element_id}]: {e}")
        # Final fallback: Coordinate-based click if selector fails
        plan = plan or []
        target = _resolve_element(element_id, plan)
        if target and target.get("rect"):
            try:
                rect = target["rect"]
                await page.mouse.click(rect["centerX"], rect["centerY"])
                return f"✅ Clicked [{element_id}] (fallback coordinates). URL: {page.url}"
            except: pass
        return f"Error clicking [{element_id}]: {e}"


@register_tool(
    name="type_text",
    description="Type text into an input/textarea by SOM ID. Automatically clears old content before typing.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID of the input field."},
            "text": {"type": "string", "description": "The text to type."},
            "press_enter": {"type": "boolean", "description": "Press Enter after typing.", "default": False}
        },
        "required": ["element_id", "text"]
    }
)
async def type_text(element_id: int, text: str, press_enter: bool = False, plan: list = None, **ctx) -> str:
    """Type text into an input field by SOM ID."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    # Use visible selector
    selector = f'[data-som-id="{element_id}"]:visible'
    
    try:
        # 1. Wait and find
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
        except Exception:
            return f"Error: Element ID [{element_id}] not found or is hidden."

        # 2. Ensure visible
        await element.scroll_into_view_if_needed()
        
        # 3. Fill text
        try:
            await element.fill(text)
        except Exception as fill_err:
            logger.warning(f"Standard fill failed for [{element_id}], trying keyboard fallback: {fill_err}")
            # Fallback: keyboard simulation for non-input elements (divs, spans)
            plan = plan or []
            target = _resolve_element(element_id, plan)
            if target and target.get("rect"):
                rect = target["rect"]
                await page.mouse.click(rect["centerX"], rect["centerY"])
                await asyncio.sleep(0.2)
                # Clear content
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(text)
                if press_enter: 
                    await page.keyboard.press("Enter")
                await asyncio.sleep(0.5)
                return f"✅ Typed '{text}' into [{element_id}] (keyboard fallback). URL: {page.url}"
            else:
                raise fill_err # Re-raise if no coordinates available
        
        if press_enter:
            await page.keyboard.press("Enter")
        
        await asyncio.sleep(0.5)
        return f"✅ Typed '{text}' into [{element_id}]. URL: {page.url}"

    except Exception as e:
        logger.warning(f"All typing methods failed for [{element_id}]: {e}")
        return f"Error typing text [{element_id}]: {e}. Suggestion: If this is a dropdown, use click_element first, then select the option."


# ============================================================
# TOOL: select_option
# ============================================================
@register_tool(
    name="select_option",
    description="Select a value in a dropdown/select box by SOM ID.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID of the dropdown."},
            "value": {"type": "string", "description": "The value to select (visible text or value)."}
        },
        "required": ["element_id", "value"]
    }
)
async def select_option(element_id: int, value: str, plan: list = None, **ctx) -> str:
    """Select an option in a dropdown."""
    plan = plan or []
    target = _resolve_element(element_id, plan)
    if not target:
        return f"Error: Element ID [{element_id}] không tìm thấy."

    selector = target.get("best_selector") or target.get("selector")
    page = await BrowserManager.get_page()

    try:
        # Try by visible text first, then by value
        try:
            await page.select_option(selector, label=value, timeout=3000)
        except Exception:
            await page.select_option(selector, value=value, timeout=3000)
        await asyncio.sleep(0.5)
        return f"✅ Selected '{value}' in [{element_id}]. URL: {page.url}"
    except Exception as e:
        return f"Error selecting option [{element_id}]: {e}"


# ============================================================
# TOOL: hover_element
# ============================================================
@register_tool(
    name="hover_element",
    description="Hover over a web element to open submenus or view tooltips.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID of the element to hover."}
        },
        "required": ["element_id"]
    }
)
async def hover_element(element_id: int, plan: list = None, **ctx) -> str:
    """Hover over an element by SOM ID."""
    plan = plan or []
    target = _resolve_element(element_id, plan)
    if not target:
        return f"Error: Element ID [{element_id}] không tìm thấy."

    selector = target.get("best_selector") or target.get("selector")
    page = await BrowserManager.get_page()

    try:
        await page.hover(selector, timeout=3000)
        await asyncio.sleep(0.5)
        return f"✅ Hovered [{element_id}]. URL: {page.url}"
    except Exception as e:
        return f"Error hovering [{element_id}]: {e}"


# ============================================================
# TOOL: scroll
# ============================================================
@register_tool(
    name="scroll",
    description="Scroll the page up or down. Use only when all elements in the current view have been processed.",
    parameters={
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction."}
        },
        "required": ["direction"]
    }
)
async def scroll(direction: str, **ctx) -> str:
    """Scroll the page."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    if direction.lower() == "down":
        await page.evaluate("window.scrollBy(0, window.innerHeight / 1.5)")
    else:
        await page.evaluate("window.scrollBy(0, -window.innerHeight / 1.5)")

    await asyncio.sleep(1.0)
    pos = await page.evaluate("window.scrollY")
    return f"✅ Scrolled {direction}. Position: {pos}. URL: {page.url}"


# ============================================================
# TOOL: press_key
# ============================================================
@register_tool(
    name="press_key",
    description="Press a keyboard key (Escape, Enter, Tab, etc.). Use Escape to close popups/dialogs.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Key name to press."}
        },
        "required": ["key"]
    }
)
async def press_key(key: str, **ctx) -> str:
    """Press a keyboard key."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."
    await page.keyboard.press(key)
    await asyncio.sleep(0.5)
    return f"✅ Pressed key '{key}'."


# ============================================================
# TOOL: click_at_coordinates
# ============================================================
@register_tool(
    name="click_at_coordinates",
    description="Click at pixel coordinates (x, y) on the screenshot. Use only when the element has no SOM ID.",
    parameters={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X coordinate (0-1024)."},
            "y": {"type": "integer", "description": "Y coordinate."}
        },
        "required": ["x", "y"]
    }
)
async def click_at_coordinates(x: int, y: int, **ctx) -> str:
    """Click at pixel coordinates on the screenshot."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    viewport = page.viewport_size
    actual_width = viewport["width"] if viewport else 1440
    scale = actual_width / 1024  # AI sees 1024px wide image

    real_x = x * scale
    real_y = y * scale

    await inject_visual_effects(page)
    await page.evaluate(f"window.showClickEffect({real_x}, {real_y})")
    await page.mouse.click(real_x, real_y)
    await asyncio.sleep(1.0)

    return f"✅ Clicked coordinates ({x}, {y}) [actual: {real_x:.0f}, {real_y:.0f}]. URL: {page.url}"


# ============================================================
# TOOL: list_tabs
# ============================================================
@register_tool(
    name="list_tabs",
    description="List all open tabs (windows). Use when a click opens a new tab.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def list_tabs(**ctx) -> str:
    """List all open tabs."""
    pages = await BrowserManager.get_pages()
    if not pages:
        return "No tabs open."
    
    tabs = []
    for i, p in enumerate(pages):
        try:
            title = await p.title()
            url = p.url
            tabs.append(f"[{i}] {title} ({url})")
        except:
            tabs.append(f"[{i}] (Tab inaccessible)")
    
    return "Open tabs:\n" + "\n".join(tabs)


# ============================================================
# TOOL: switch_tab
# ============================================================
@register_tool(
    name="switch_tab",
    description="Switch focus to another tab by index (from list_tabs).",
    parameters={
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "Index of the tab to switch to (0, 1, 2...)."}
        },
        "required": ["index"]
    }
)
async def switch_tab(index: int, **ctx) -> str:
    """Switch focus to a specific tab."""
    success = await BrowserManager.switch_to_page(index)
    if success:
        page = await BrowserManager.get_page()
        return f"✅ Switched to tab [{index}]. Current URL: {page.url}"
    else:
        return f"Error: Tab with index [{index}] not found."
