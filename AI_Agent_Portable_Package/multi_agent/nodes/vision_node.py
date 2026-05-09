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
import logging
import base64
from urllib.parse import urlparse
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

        # === 2. STABILITY WAIT ===
        # Wait for the page to be stable (DOM not changing much)
        try:
            # Wait for network idle with a longer timeout for stability
            await page.wait_for_load_state("networkidle", timeout=3500)
            # Extra buffer for animations (especially dropdowns)
            await asyncio.sleep(1.0)
        except Exception:
            # Fallback if networkidle takes too long
            await asyncio.sleep(2.0)

        # === 3. SCAN DOM ===
        dom_elements = await get_interactive_elements()
        if not isinstance(dom_elements, list):
            dom_elements = []

        # === 4. CREATE PLAN + INJECT SOM MARKERS ===
        from tools.plan_tool import create_page_plan
        plan = create_page_plan(dom_elements, current_url=page.url)
        plan = await inject_som_markers(page, plan)

        # === 5. CAPTURE SCREENSHOT ===
        screenshot = await capture_screenshot(
            cursor_pos=state.get("last_action_location")
        )

        # Cleanup SOM markers from DOM
        await cleanup_som_markers(page)

        # === 6. UPDATE STATE ===
        state["screenshot"] = screenshot
        state["dom_elements"] = dom_elements
        state["current_page_plan"] = plan

        # Debug: save last screenshot to file
        try:
            with open("last_vision.jpg", "wb") as f:
                f.write(base64.b64decode(screenshot))
        except Exception:
            pass

        hist = state.get("history") or []
        hist.append(f"📸 Scanned page [{page.url}]: {len(plan)} interactive elements.")
        state["history"] = hist

        return state

    except Exception as e:
        logger.error(f"❌ Vision Node Error: {e}")
        hist = state.get("history") or []
        hist.append(f"❌ Error observing page: {e}")
        state["history"] = hist
        return state
