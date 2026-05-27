"""
Data Tools — Upload, List Files, Read Text, Get Value, Generate Test File, Cleanup.

All tools auto-register via @register_tool decorator.
"""
import asyncio
import logging
import io
import struct
from tools.tool_registry import register_tool
from tools.browser_manager import BrowserManager
from tools.utils import inject_visual_effects
import os

logger = logging.getLogger(__name__)

# Files that are part of the permanent test_assets and must NOT be deleted by cleanup
_PERMANENT_ASSETS = {"sample_image.png"}
# Registry of files generated dynamically during the current test session
_GENERATED_FILES: set = set()

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

    # Strip '@' prefix if present (common when users tag files in prompt)
    if filename.startswith("@"):
        filename = filename[1:]
        
    # If filename is an absolute path, use it directly
    if os.path.isabs(filename):
        filepath = filename
    else:
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
                        // Search up the parent chain up to 4 levels to find the upload container
                        let curr = el;
                        for (let i = 0; i < 4; i++) {
                            if (!curr) break;
                            let input = curr.querySelector('input[type=file]');
                            if (input) return input;
                            curr = curr.parentElement;
                        }
                        return null;
                    }""", element
                )
                file_input = file_input.as_element()
            
            # If still not found, search the entire page for any file input
            if not file_input:
                logger.info("Searching entire page for any input[type=file]...")
                all_file_inputs = await page.query_selector_all("input[type=file]")
                if all_file_inputs:
                    file_input = all_file_inputs[0]
                    logger.info(f"Found {len(all_file_inputs)} file input(s) on page, using first one.")

        # 5. Perform upload
        if file_input:
            try:
                await file_input.set_input_files(filepath, timeout=5000)
                # Dispatch events to trigger reactivity in Vue/React/Angular
                try:
                    await file_input.evaluate("""(el) => {
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }""")
                except Exception as ev_err:
                    logger.warning(f"Failed to dispatch change/input events: {ev_err}")
                await asyncio.sleep(1.5)
                return f"✅ Uploaded file '{filename}' to [{element_id}]{target_info} successfully."
            except Exception as e:
                logger.warning(f"set_input_files failed: {e}. Trying filechooser fallback...")

        # 6. DataTransfer Injection Fallback — NO Finder dialog opened
        # Try to inject the file directly via JavaScript DataTransfer API
        logger.info(f"Attempting DataTransfer injection for [{element_id}]{target_info}...")
        try:
            # Read file bytes and encode as base64 to pass into JS
            import base64
            import mimetypes
            mime_type, _ = mimetypes.guess_type(filepath)
            mime_type = mime_type or "application/octet-stream"
            with open(filepath, "rb") as f:
                file_bytes = f.read()
            file_b64 = base64.b64encode(file_bytes).decode("utf-8")
            file_name = os.path.basename(filepath)
            
            # Find any file input on the page to inject into
            injected = await page.evaluate(
                """
                ([b64, fname, mtype]) => {
                    const byteChars = atob(b64);
                    const byteNums = new Array(byteChars.length);
                    for (let i = 0; i < byteChars.length; i++) byteNums[i] = byteChars.charCodeAt(i);
                    const arr = new Uint8Array(byteNums);
                    const file = new File([arr], fname, { type: mtype });
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    // Find a file input: hidden or visible
                    const inputs = document.querySelectorAll('input[type=file]');
                    if (!inputs.length) return false;
                    for (const inp of inputs) {
                        inp.files = dt.files;
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        inp.dispatchEvent(new Event('input',  { bubbles: true }));
                    }
                    return inputs.length;
                }
                """,
                [file_b64, file_name, mime_type]
            )
            if injected:
                await asyncio.sleep(1.5)
                return f"✅ Uploaded file '{filename}' to [{element_id}]{target_info} (via DataTransfer injection, {injected} input(s))."
        except Exception as dt_err:
            logger.warning(f"DataTransfer injection failed: {dt_err}")
        
        # 7. Last resort: set_input_files directly on the element selector
        try:
            await page.set_input_files(selector, filepath, timeout=2000)
            return f"✅ Uploaded file '{filename}' to [{element_id}] (last-resort set_input_files)."
        except Exception as last_err:
            logger.error(f"All upload methods failed: {last_err}")
            return f"Error uploading file: No suitable file input found for [{element_id}]. The file input may be inside a shadow DOM or iframe. Try a different element ID."

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


# ============================================================
# TOOL: generate_test_file
# ============================================================
@register_tool(
    name="generate_test_file",
    description=(
        "Generate a file in the 'test_assets' directory for upload testing. "
        "Use this tool to create: (1) a valid image file for happy-path tests, "
        "(2) an invalid file type (e.g. .exe, .txt) for type-rejection tests, "
        "(3) a 0-byte empty file for empty-upload tests, "
        "(4) a large binary file to test size-limit rejection. "
        "The tool returns the ABSOLUTE file path — you MUST pass this exact path "
        "as the 'filename' argument of upload_file. "
        "DO NOT guess or construct the path yourself."
    ),
    parameters={
        "type": "object",
        "properties": {
            "file_type": {
                "type": "string",
                "enum": ["image", "text", "binary", "empty"],
                "description": (
                    "Category of file to generate: "
                    "'image' = a real PNG/JPG/WEBP/etc. image (valid for upload); "
                    "'text' = a plain-text file (use for invalid-type tests); "
                    "'binary' = a raw binary blob of specified size (use for size-limit tests); "
                    "'empty' = a 0-byte file (use for empty-file tests)."
                )
            },
            "extension": {
                "type": "string",
                "description": (
                    "File extension WITHOUT the leading dot, e.g. 'png', 'jpg', 'txt', 'exe', 'pdf'. "
                    "For 'image' type, supported extensions are: png, jpg, jpeg, bmp, gif, webp. "
                    "Defaults: image→'png', text→'txt', binary→'bin', empty→'tmp'."
                )
            },
            "size_mb": {
                "type": "number",
                "description": (
                    "Target file size in megabytes. Only effective for 'binary' and 'text' types. "
                    "For 'image', a minimal real image is created (size is not controllable). "
                    "For 'empty', this is ignored (always 0 bytes). "
                    "Max allowed: 150 MB. Default: 1 MB."
                )
            },
            "filename_prefix": {
                "type": "string",
                "description": (
                    "Optional prefix for the generated filename, e.g. 'invalid_type', 'oversized', 'empty'. "
                    "Defaults to the file_type value."
                )
            }
        },
        "required": ["file_type"]
    }
)
async def generate_test_file(
    file_type: str,
    extension: str = "",
    size_mb: float = 1.0,
    filename_prefix: str = "",
    **ctx
) -> str:
    """
    Dynamically generate a test file in 'test_assets' and return its absolute path.
    The caller (upload_file tool) must use this exact absolute path.
    """
    assets_dir = os.path.abspath("test_assets")
    os.makedirs(assets_dir, exist_ok=True)

    # --- Resolve defaults ---
    file_type = file_type.lower().strip()
    if file_type not in ("image", "text", "binary", "empty"):
        return f"Error: Invalid file_type '{file_type}'. Must be one of: image, text, binary, empty."

    default_ext = {"image": "png", "text": "txt", "binary": "bin", "empty": "tmp"}
    ext = (extension or default_ext[file_type]).lower().strip().lstrip(".")
    prefix = (filename_prefix or file_type).strip()

    # --- Validate size ---
    MAX_MB = 150
    if size_mb > MAX_MB:
        return f"Error: size_mb ({size_mb}) exceeds maximum allowed ({MAX_MB} MB)."

    # --- Build unique filename (avoid collisions between test cases) ---
    import time
    ts = int(time.time() * 1000) % 100000  # 5-digit ms suffix
    filename = f"{prefix}_{ts}.{ext}"
    filepath = os.path.join(assets_dir, filename)

    try:
        if file_type == "empty":
            # 0-byte file
            open(filepath, "wb").close()
            size_info = "0 bytes"

        elif file_type == "image":
            # Use PIL to create a minimal real image so it passes browser MIME detection
            try:
                from PIL import Image
                img = Image.new("RGB", (100, 100), color=(200, 100, 50))
                # Map extension to PIL format
                fmt_map = {
                    "jpg": "JPEG", "jpeg": "JPEG",
                    "png": "PNG", "bmp": "BMP",
                    "gif": "GIF", "webp": "WEBP",
                }
                pil_fmt = fmt_map.get(ext, "PNG")
                img.save(filepath, format=pil_fmt)
                size_info = f"{os.path.getsize(filepath)} bytes"
            except ImportError:
                # Fallback: write a minimal valid PNG header manually (1x1 white pixel)
                _write_minimal_png(filepath)
                size_info = f"{os.path.getsize(filepath)} bytes"

        elif file_type == "text":
            target_bytes = max(1, int(size_mb * 1024 * 1024))
            line = "AI_AGENT_TEST_DATA — This file was generated for QA testing purposes.\n"
            with open(filepath, "w", encoding="utf-8") as f:
                written = 0
                while written < target_bytes:
                    f.write(line)
                    written += len(line.encode("utf-8"))
            size_info = f"{os.path.getsize(filepath) / (1024*1024):.2f} MB"

        elif file_type == "binary":
            target_bytes = max(1, int(size_mb * 1024 * 1024))
            chunk = b"\x00" * min(target_bytes, 4 * 1024 * 1024)  # write in 4 MB chunks max
            with open(filepath, "wb") as f:
                written = 0
                while written < target_bytes:
                    to_write = min(len(chunk), target_bytes - written)
                    f.write(chunk[:to_write])
                    written += to_write
            size_info = f"{os.path.getsize(filepath) / (1024*1024):.2f} MB"

        # Register so cleanup can remove it
        _GENERATED_FILES.add(filepath)
        logger.info(f"📁 Generated test file: {filepath} ({size_info})")
        return (
            f"✅ Generated '{filename}' ({size_info}). "
            f"ABSOLUTE PATH: {filepath}  "
            f"⚠️ You MUST pass this exact absolute path to upload_file's 'filename' argument. "
            f"Do NOT modify or guess the path."
        )

    except Exception as e:
        logger.error(f"❌ generate_test_file error: {e}")
        return f"Error generating test file: {str(e)}"


def _write_minimal_png(filepath: str) -> None:
    """Write a minimal 1x1 white-pixel PNG file without PIL."""
    import zlib
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    raw_row = b"\x00\xFF\xFF\xFF"  # filter byte + 1 RGB pixel
    compressed = zlib.compress(raw_row)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    with open(filepath, "wb") as f:
        f.write(png)


# ============================================================
# TOOL: cleanup_test_assets
# ============================================================
@register_tool(
    name="cleanup_test_assets",
    description=(
        "Delete all dynamically generated test files from the 'test_assets' directory. "
        "Permanent files like 'sample_image.png' are NEVER deleted. "
        "Call this tool at the END of a test session to keep the directory clean. "
        "Returns a summary of deleted files."
    ),
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def cleanup_test_assets(**ctx) -> str:
    """Remove all session-generated test files from test_assets, keeping permanent assets."""
    return _do_cleanup_test_assets()


def _do_cleanup_test_assets() -> str:
    """
    Synchronous cleanup helper — also called by app.py at session start.
    Deletes any file in test_assets that:
      1. Is tracked in _GENERATED_FILES, OR
      2. Is NOT in _PERMANENT_ASSETS (safety net for files left by a previous crash).
    Returns a human-readable summary.
    """
    assets_dir = os.path.abspath("test_assets")
    if not os.path.exists(assets_dir):
        return "test_assets directory does not exist — nothing to clean."

    deleted = []
    errors = []
    for fname in os.listdir(assets_dir):
        if fname in _PERMANENT_ASSETS:
            continue  # Never delete permanent files
        fpath = os.path.join(assets_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            os.remove(fpath)
            deleted.append(fname)
            _GENERATED_FILES.discard(fpath)
            logger.info(f"🗑️ Cleaned up test file: {fpath}")
        except Exception as e:
            errors.append(f"{fname}: {e}")
            logger.warning(f"⚠️ Could not delete {fpath}: {e}")

    summary_parts = []
    if deleted:
        summary_parts.append(f"✅ Deleted {len(deleted)} file(s): {', '.join(deleted)}")
    else:
        summary_parts.append("✅ No generated files to clean.")
    if errors:
        summary_parts.append(f"⚠️ Failed to delete {len(errors)} file(s): {'; '.join(errors)}")
    return " | ".join(summary_parts)
