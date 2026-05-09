"""
Data Tools — Upload, List Files, Read Text, Get Value.

All tools auto-register via @register_tool decorator.
"""
import asyncio
import logging
from tools.tool_registry import register_tool
from tools.browser_manager import BrowserManager
from tools.utils import inject_visual_effects
import os

logger = logging.getLogger(__name__)

def list_test_assets():
    """Helper to list files in test_assets directory."""
    assets_dir = "test_assets"
    if not os.path.exists(assets_dir):
        return "Error: Directory 'test_assets' does not exist."
    files = [f for f in os.listdir(assets_dir) if os.path.isfile(os.path.join(assets_dir, f))]
    if not files:
        return "Directory 'test_assets' is empty."
    return "Available files: " + ", ".join(files)

async def perform_upload(page, selector, filename):
    """Helper to upload a file using Playwright."""
    filepath = os.path.join("test_assets", filename)
    if not os.path.exists(filepath):
        return f"Error: File '{filename}' not found in 'test_assets'."
    
    try:
        await page.set_input_files(selector, filepath, timeout=5000)
        return f"✅ Uploaded file '{filename}' successfully."
    except Exception as e:
        return f"Error uploading file: {str(e)}"


# ============================================================
# TOOL: list_files
# ============================================================
@register_tool(
    name="list_files",
    description="List available files in the 'test_assets' directory for uploading.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def list_files(**ctx) -> str:
    """List available files in test_assets."""
    return list_test_assets()


# ============================================================
# TOOL: upload_file
# ============================================================
@register_tool(
    name="upload_file",
    description="Upload a file from 'test_assets' to a web element. DO NOT use click for upload buttons, always use this tool.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID of the upload element."},
            "filename": {"type": "string", "description": "Filename (e.g., 'sample_image.png')."}
        },
        "required": ["element_id", "filename"]
    }
)
async def upload_file(element_id: int, filename: str, plan: list = None, **ctx) -> str:
    """Upload a file to a web element."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    filepath = os.path.join("test_assets", filename)
    if not os.path.exists(filepath):
        # List available files to help the AI
        assets = list_test_assets()
        return f"Error: File '{filename}' not found. {assets}"

    # Use visible selector to avoid hidden duplicates
    selector = f'[data-som-id="{element_id}"]:visible'
    
    # Identify target from plan if available
    target_info = ""
    if plan:
        target = next((item for item in plan if item.get("som_id") == element_id), None)
        if target:
            actual_tag = target.get("actualTag", "unknown").lower()
            target_info = f" ({actual_tag})"
            if actual_tag in ['li', 'span', 'p'] and not target.get("text", "").lower().startswith("chọn"):
                logger.warning(f"AI picking suspicious target for upload: {actual_tag}")

    try:
        # 1. Wait for target
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
        except Exception:
            # Check if it exists but is hidden
            hidden_exists = await page.locator(f'[data-som-id="{element_id}"]').count() > 0
            if hidden_exists:
                return f"Error: Element ID [{element_id}]{target_info} is currently hidden or obscured. Try scrolling or opening the containing menu."
            return f"Error: Element ID [{element_id}] not found on the current page."

        # Check for multiple visible matches
        matches = await page.locator(selector).count()
        if matches > 1:
            return f"Error: Found {matches} elements with the same ID [{element_id}]. Run 're_scan' to refresh the ID list."

        # 2. Visual feedback
        try:
            box = await element.bounding_box()
            if box:
                await inject_visual_effects(page)
                await page.evaluate(f"window.showClickEffect({box['x'] + box['width']/2}, {box['y'] + box['height']/2})")
        except: pass

        # 3. Check if this is the file input
        tag_name = await element.evaluate("el => el.tagName")
        type_attr = await element.evaluate("el => el.getAttribute('type')")
        
        file_input = None
        if tag_name == "INPUT" and type_attr == "file":
            file_input = element
        else:
            # 4. If not a file input, look for one inside or near it
            # Many sites use a button that triggers a hidden input
            logger.info(f"Target [{element_id}]{target_info} is not a file input. Searching for hidden input...")
            
            # Try to find input[type=file] inside this element or its parent
            file_input = await element.query_selector("input[type=file]")
            if not file_input:
                # Try sibling or parent's child
                file_input = await page.evaluate_handle(
                    """(el) => {
                        // Look in children
                        let input = el.querySelector('input[type=file]');
                        if (input) return input;
                        // Look in parent's children
                        if (el.parentElement) {
                            return el.parentElement.querySelector('input[type=file]');
                        }
                        return null;
                    }""", element
                )
                file_input = file_input.as_element()

        # 5. Perform upload
        if file_input:
            try:
                await file_input.set_input_files(filepath, timeout=5000)
                await asyncio.sleep(1)
                return f"✅ Uploaded file '{filename}' to [{element_id}]{target_info} successfully."
            except Exception as e:
                logger.warning(f"set_input_files failed: {e}. Trying filechooser fallback...")

        # 6. FileChooser Fallback (Crucial for modern apps like iView/AntD)
        try:
            async with page.expect_file_chooser(timeout=5000) as fc_info:
                await element.click(timeout=3000)
            file_chooser = await fc_info.value
            await file_chooser.set_files(filepath)
            await asyncio.sleep(2)
            return f"✅ Uploaded file '{filename}' to [{element_id}]{target_info} (via FileChooser)."
        except Exception as fe:
            logger.error(f"FileChooser failed: {fe}")
            # Final attempt: try set_input_files on the original element one last time
            try:
                await page.set_input_files(selector, filepath, timeout=2000)
                return f"✅ Uploaded file '{filename}' to [{element_id}] (fallback)."
            except:
                return f"Error uploading file: No suitable file input found for [{element_id}]. Try clicking the upload button directly or find another ID."

    except Exception as e:
        logger.error(f"❌ Error in upload_file: {e}")
        return f"Error upload file: {str(e)}"


# ============================================================
# TOOL: read_page_text
# ============================================================
@register_tool(
    name="read_page_text",
    description="Read all visible text on the current page. Useful for checking content that is not clear in the image.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def read_page_text(**ctx) -> str:
    """Read all visible text on the current page."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    try:
        text = await page.evaluate("document.body.innerText")
        # Truncate if too long
        if len(text) > 3000:
            text = text[:3000] + "\n... (truncated, more content available)"
        return f"📄 Page Content:\n{text}"
    except Exception as e:
        return f"Error reading text: {e}"


# ============================================================
# TOOL: get_element_value
# ============================================================
@register_tool(
    name="get_element_value",
    description="Get the current value of an input/textarea/select element by SOM ID. Useful to verify if a field is filled.",
    parameters={
        "type": "object",
        "properties": {
            "element_id": {"type": "integer", "description": "SOM ID của phần tử cần kiểm tra."}
        },
        "required": ["element_id"]
    }
)
async def get_element_value(element_id: int, plan: list = None, **ctx) -> str:
    """Get the current value of an input element."""
    plan = plan or []
    target = next((item for item in plan if item.get("som_id") == element_id), None)
    if not target:
        return f"Error: Element ID [{element_id}] not found."

    selector = target.get("best_selector") or target.get("selector")
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    try:
        value = await page.eval_on_selector(selector, "el => el.value || el.innerText || ''")
        return f"✅ Value of [{element_id}]: '{value}'"
    except Exception as e:
        return f"Error getting value [{element_id}]: {e}"
