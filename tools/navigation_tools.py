"""
Navigation Tools — Navigate, Go Back, Refresh.

All tools auto-register via @register_tool decorator.
"""
import asyncio
import logging
from tools.tool_registry import register_tool
from tools.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


# ============================================================
# TOOL: navigate_to
# ============================================================
@register_tool(
    name="navigate_to",
    description="Navigate directly to a URL. Use when you know the exact URL or when navigation is stuck.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The full URL to open (e.g., 'https://example.com/admin/post/add')."}
        },
        "required": ["url"]
    }
)
async def navigate_to(url: str, **ctx) -> str:
    """Navigate directly to a URL."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    if url.startswith("/"):
        from urllib.parse import urljoin
        if page.url != "about:blank":
            url = urljoin(page.url, url)
        else:
            return f"Error: Cannot navigate to relative URL '{url}' from 'about:blank'."
    elif not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
    except Exception:
        try:
            await page.goto(url, wait_until="load", timeout=10000)
        except Exception as e:
            return f"Error: Could not open {url}: {e}"

    await asyncio.sleep(0.5)
    return f"✅ Opened {page.url}"


# ============================================================
# TOOL: go_back
# ============================================================
@register_tool(
    name="go_back",
    description="Go back to the previous page (like the browser's Back button).",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def go_back(**ctx) -> str:
    """Go back to the previous page."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    try:
        await page.go_back(wait_until="networkidle", timeout=10000)
    except Exception:
        try:
            await page.go_back(wait_until="load", timeout=5000)
        except Exception as e:
            return f"Error: Could not go back: {e}"

    await asyncio.sleep(0.5)
    return f"✅ Went back. URL: {page.url}"


# ============================================================
# TOOL: refresh_page
# ============================================================
@register_tool(
    name="refresh_page",
    description="Reload the current page.",
    parameters={
        "type": "object",
        "properties": {}
    }
)
async def refresh_page(**ctx) -> str:
    """Refresh the current page."""
    page = await BrowserManager.get_page()
    if not page:
        return "Error: Browser not connected."

    try:
        await page.reload(wait_until="networkidle", timeout=10000)
    except Exception:
        try:
            await page.reload(wait_until="load", timeout=5000)
        except Exception as e:
            return f"Error: Could not refresh page: {e}"

    await asyncio.sleep(0.5)
    return f"✅ Page refreshed. URL: {page.url}"
