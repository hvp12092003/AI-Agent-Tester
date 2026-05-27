"""
Vision Node — The "Eyes" of the Agent.

Responsibilities:
1. Navigate to URL (first step only)
2. Scan DOM for interactive elements
3. Inject SOM markers
4. Capture screenshot
5. Return observation to Manager
"""
import asyncio
import io
import logging
import base64
from urllib.parse import urlparse
from PIL import Image
from multi_agent.state import AgentState
from tools.vision_tool import capture_screenshot
from tools.dom_tool import get_interactive_elements, inject_som_markers, cleanup_som_markers
from tools.browser_manager import BrowserManager

logger = logging.getLogger(__name__)


async def vision_node(state: AgentState) -> AgentState:
    """Capture the current browser state: screenshot + DOM elements."""
    try:
        page = await BrowserManager.get_page()
        if not page:
            logger.error("❌ [Vision] Could not get browser page.")
            return state

        # === 1. INITIAL NAVIGATION (first step only) ===
        url_to_open = state.get("url")
        if url_to_open:
            logger.info(f"🌐 Navigating to: {url_to_open}")
            try:
                # Use a more generous timeout for initial navigation
                await page.goto(url_to_open, wait_until="load", timeout=30000)
                # Then wait for idle
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                logger.warning(f"⏱️ Navigation stability warning for {url_to_open}: {e}")
            
            state["url"] = None  # Clear so we don't re-navigate

            # Lock base domain
            current_url = page.url
            if current_url != "about:blank":
                parsed = urlparse(current_url)
                state["base_url"] = f"{parsed.scheme}://{parsed.netloc}"
                logger.info(f"🏠 Base domain: {state['base_url']}")

        # === 2. INSTANT SCREENSHOT — Capture notifications/toasts before they disappear ===
        # Take a raw screenshot immediately (no DOM scan, no SOM markers) to catch flash messages
        instant_screenshot = None
        page_was_loading = False
        try:
            # Check if page is still loading
            is_loading = await page.evaluate("document.readyState !== 'complete'")
            page_was_loading = bool(is_loading)

            # Instant capture with 0ms delay — catches toasts, alerts, and flash messages
            raw_bytes = await page.screenshot(full_page=False)
            img = Image.open(io.BytesIO(raw_bytes))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=70, optimize=True)
            instant_screenshot = base64.b64encode(buf.getvalue()).decode("utf-8")
            logger.info(f"📸 Instant snapshot captured (page_loading={page_was_loading})")
        except Exception as e:
            logger.warning(f"⚠️ Instant snapshot failed: {e}")

        # === 3. STABILITY WAIT ===
        # Wait for the page to be stable (DOM not changing much)
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
            # Short buffer for CSS transitions/animations (dropdowns, modals)
            await asyncio.sleep(0.3)
        except Exception:
            # Fallback: brief wait if networkidle not reached
            await asyncio.sleep(1.0)

        # If page was still loading during instant capture, take an additional mid-load screenshot
        mid_screenshot = None
        if page_was_loading:
            try:
                raw_bytes2 = await page.screenshot(full_page=False)
                img2 = Image.open(io.BytesIO(raw_bytes2))
                buf2 = io.BytesIO()
                img2.convert("RGB").save(buf2, format="JPEG", quality=70, optimize=True)
                mid_screenshot = base64.b64encode(buf2.getvalue()).decode("utf-8")
                logger.info("📸 Mid-load snapshot captured (page was loading)")
            except Exception as e:
                logger.warning(f"⚠️ Mid-load snapshot failed: {e}")

        # === 4. SCAN DOM ===
        dom_elements = await get_interactive_elements()
        if not isinstance(dom_elements, list):
            dom_elements = []

        # === 5. INJECT SOM MARKERS ===
        await inject_som_markers(page, dom_elements)

        # === 6. CAPTURE FINAL SCREENSHOT ===
        screenshot = await capture_screenshot(
            cursor_pos=state.get("last_action_location"),
            wait_ms=0  # Already waited above — capture immediately
        )

        # Cleanup SOM markers from DOM
        await cleanup_som_markers(page)

        # Store extra snapshots so manager/validator can access them
        # Priority: instant_screenshot (catches notifications) → mid_screenshot → final screenshot
        extra_screenshots = []
        if instant_screenshot and instant_screenshot != screenshot:
            extra_screenshots.append(instant_screenshot)
        if mid_screenshot and mid_screenshot != screenshot:
            extra_screenshots.append(mid_screenshot)
        state["extra_screenshots"] = extra_screenshots
        if extra_screenshots:
            logger.info(f"📸 Total snapshots this cycle: {1 + len(extra_screenshots)} (instant+mid+final)")

        # === 7. UPDATE STATE ===
        state["screenshot"] = screenshot
        state["dom_elements"] = dom_elements

        # Debug: save instant screenshot (most likely to contain flash notifications)
        try:
            debug_img = instant_screenshot or screenshot
            with open("last_vision.jpg", "wb") as f:
                f.write(base64.b64decode(debug_img))
        except Exception:
            pass

        hist = state.get("history") or []
        hist.append(f"📸 Đã quét trang [{page.url}]: tìm thấy {len(dom_elements)} phần tử tương tác.")
        state["history"] = hist

        return state

    except Exception as e:
        logger.error(f"❌ Vision Node Error: {e}")
        hist = state.get("history") or []
        hist.append(f"❌ Lỗi khi quan sát trang: {e}")
        state["history"] = hist
        return state
