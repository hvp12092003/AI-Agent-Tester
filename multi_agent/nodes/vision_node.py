import asyncio
import logging
from urllib.parse import urlparse
from multi_agent.state import AgentState
from tools.vision_tool import capture_screenshot
from tools.dom_tool import get_interactive_elements, inject_som_markers, cleanup_som_markers
from tools.browser_manager import BrowserManager
from tools.crawler_tool import (
    get_domain, normalize_url, add_url, get_next_pending, mark_url_status,
    create_page_plan, is_page_complete, detect_plan_refresh, is_destructive_element
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def vision_node(state: AgentState) -> AgentState:
    """
    Node 'Mắt' của Agent với tích hợp BFS Crawler.
    """
    try:
        print("\n📸 [Vision Node] Capturing screenshot...")
        screenshot = None # Initialize
        
        page = await BrowserManager.get_page()
        if not page:
            logger.error("❌ [Vision Node] Could not get browser page.")
            return state

        queue = state.get("global_url_queue") or []
        plan = state.get("current_page_plan") or []
        blacklist = state.get("clicked_selectors_blacklist") or []
        
        # ===== 1. ĐIỀU HƯỚNG BAN ĐẦU =====
        url_to_open = state.get("url")
        if url_to_open:
            print(f"🌐 Navigating to initial URL: {url_to_open}")
            try:
                await page.goto(url_to_open, wait_until="networkidle", timeout=5000)
            except Exception:
                try:
                    await page.goto(url_to_open, wait_until="load", timeout=5000)
                except Exception as e:
                    print(f"⏱️ TIMEOUT (5s): Initial page load slow: {e}")
            state["url"] = None
            
            current_url = page.url
            
            # Khóa base domain (bao gồm scheme://netloc)
            if current_url != "about:blank":
                parsed = urlparse(current_url)
                state["base_url"] = f"{parsed.scheme}://{parsed.netloc}"
                print(f"🏠 Base domain locked: {state['base_url']}")
                
                # Thêm URL đầu tiên vào queue
                add_url(queue, current_url, state["base_url"])
                mark_url_status(queue, current_url, "testing")
                state["testing_url"] = current_url
                state["already_clicked_buttons"] = [] # Reset on new page
            
            # Quét DOM và tạo page plan
            dom_elements = await get_interactive_elements()
            plan = create_page_plan(dom_elements, current_url=page.url, blacklist=blacklist)
            
            state["global_url_queue"] = queue
            
            # Inject SOM Markers before screenshot
            plan = await inject_som_markers(page, plan)
            
            state["current_page_plan"] = plan
            state["screenshot"] = await capture_screenshot(cursor_pos=state.get("last_action_location"))
            
            # Cleanup after screenshot
            await cleanup_som_markers(page)
            
            state["dom_elements"] = dom_elements
            return state

        # ===== 2. BFS ROUTING (các bước tiếp theo) =====
        current_url = page.url
        base_domain = state.get("base_url", "")
        
        # 2a. URL Guard — Kiểm tra xem Agent có bị trôi ra ngoài không
        testing_url = state.get("testing_url", "")
        current_phase = state.get("phase", "exploration")
        
        # Kiểm tra trang lỗi (chrome-error://) → điều hướng về trang đang test
        if current_url.startswith("chrome-error://") or current_url.startswith("chrome://"):
            print(f"⚠️ Browser error page detected. Navigating back to {testing_url}")
            if testing_url:
                try:
                    await page.goto(testing_url, wait_until="load", timeout=5000)
                except:
                    pass
            await asyncio.sleep(1)
            current_url = page.url
            state["history"] = state.get("history") or []
            state["history"].append(f"⚠️ Browser error page → navigated back to {testing_url}")
        elif (testing_url 
            and normalize_url(current_url) != normalize_url(testing_url) 
            and "exploration" in current_phase
            and current_phase != "login_action"
            and not current_url.startswith(base_domain)): 
            # Only go back if we drift COMPLETELY out of the base domain
            print(f"⚠️ External drift detected: {current_url} (Expected: {testing_url}) → Navigating back...")
            try:
                await page.go_back()
            except:
                if testing_url:
                    try:
                        await page.goto(testing_url, wait_until="load", timeout=5000)
                    except:
                        pass
            await asyncio.sleep(1)
            state["history"] = state.get("history") or []
            state["history"].append(f"⚠️ URL strayed to {current_url} → navigated back to {testing_url}")
        
        # 2b. Khởi tạo queue nếu trống
        if not queue and current_url != "about:blank":
            print(f"📡 Queue is empty. Adding current page to BFS: {current_url}")
            add_url(queue, current_url, base_domain)
            mark_url_status(queue, current_url, "testing")
            state["testing_url"] = current_url
            state["global_url_queue"] = queue
            state["already_clicked_buttons"] = []
            
        # 2c. Reset list nếu URL thay đổi (do redirect hoặc click)
        last_url = state.get("last_vision_url", "")
        if normalize_url(current_url) != normalize_url(last_url):
            print(f"🌐 URL changed to {current_url}. Resetting clicked buttons list.")
            state["already_clicked_buttons"] = []
            state["last_vision_url"] = current_url
        
        # ===== 2. SNAPSHOT & PLAN REFRESH =====
        # 2a. Inject SOM Markers before screenshot (using current plan if exists)
        if plan:
            plan = await inject_som_markers(page, plan)
            
        screenshot = await capture_screenshot()
        
        # 2b. Cleanup after screenshot
        await cleanup_som_markers(page)
        
        dom_elements_raw = await get_interactive_elements()
        
        # Validate dom_elements
        if not isinstance(dom_elements_raw, list):
            logger.warning(f"⚠️ [Vision Node] get_interactive_elements returned {type(dom_elements_raw)}. Defaulting to empty list.")
            dom_elements = []
        else:
            dom_elements = dom_elements_raw
            
        # Refresh hoặc khởi tạo plan
        if not plan:
            plan = create_page_plan(dom_elements, current_url=page.url, blacklist=blacklist)
        else:
            plan = detect_plan_refresh(plan, dom_elements)
        
        # [BFS] Thêm các link mới phát hiện vào queue (Chỉ chạy nếu là mode test_web)
        if state.get("mode") == "test_web":
            for item in plan:
                if not isinstance(item, dict): continue
                link = item.get("href")
                if link and isinstance(link, str):
                    # Chuẩn hóa link relative
                    full_link = link
                    if link.startswith("/"):
                        full_link = f"{base_domain.rstrip('/')}{link}"
                    
                    # Chỉ thêm nếu thuộc base_domain
                    if full_link.startswith(base_domain):
                        add_url(queue, full_link, base_domain)

        # Check if logged in
        is_logged_in = False
        try:
            is_logged_in = any(is_destructive_element(el.get("text"), el.get("href")) for el in dom_elements if isinstance(el, dict))
            if not is_logged_in:
                dashboard_keywords = ["Administrator", "Dashboard", "Trang quản trị", "Thoát", "Đăng xuất", "Log out"]
                is_logged_in = any(isinstance(kw, str) and kw.lower() in str(el.get("text", "")).lower() for el in dom_elements if isinstance(el, dict) for kw in dashboard_keywords)
                # Specific framework detection
                if not is_logged_in:
                    is_logged_in = any("Chủ đầu tư" in str(el.get("text", "")) for el in dom_elements if isinstance(el, dict))
        except Exception as e:
            logger.warning(f"⚠️ Error detecting login state: {e}")

        # Lọc plan
        filtered_plan = []
        for item in plan:
            if not isinstance(item, dict): continue
            if item.get("status") == "unclicked":
                if item.get("base_id") in blacklist:
                    item["status"] = "clicked"
                elif is_destructive_element(item.get("text"), item.get("href")):
                    continue
            filtered_plan.append(item)
        plan = filtered_plan

        # ===== 3. BFS ROUTING (quyết định chuyển trang) =====
        if "exploration" in current_phase and is_page_complete(plan) and testing_url:
            mark_url_status(queue, testing_url, "tested")
            print(f"✅ Page tested: {testing_url}")
            state["history"] = state.get("history") or []
            state["history"].append(f"✅ Completed testing page: {testing_url}")
            
            next_item = get_next_pending(queue)
            if next_item:
                next_url = next_item.get("url")
                if next_url:
                    print(f"🔄 BFS → Next page: {next_url}")
                    mark_url_status(queue, next_url, "testing")
                    state["testing_url"] = next_url
                    state["already_clicked_buttons"] = [] # Reset on navigation
                    
                    try:
                        await page.goto(next_url, wait_until="networkidle", timeout=5000)
                    except:
                        try:
                            await page.goto(next_url, wait_until="load", timeout=5000)
                        except:
                            print(f"⏱️ TIMEOUT: Cannot load {next_url}")
                            mark_url_status(queue, next_url, "tested")
                    
                    await asyncio.sleep(1)
                    # Re-scan cho trang mới
                    # Inject SOM cho trang mới (sau khi scan DOM)
                    dom_elements_raw = await get_interactive_elements()
                    dom_elements = dom_elements_raw if isinstance(dom_elements_raw, list) else []
                    plan = create_page_plan(dom_elements, current_url=page.url, blacklist=blacklist)
                    
                    plan = await inject_som_markers(page, plan)
                    screenshot = await capture_screenshot(cursor_pos=state.get("last_action_location"))
                    await cleanup_som_markers(page)
            else:
                print("🏁 BFS Exploration Complete — All pages tested!")
                plan = []

        elif current_phase == "security":
            current_domain = get_domain(current_url)
            base_domain_netloc = get_domain(base_domain)
            if (base_domain_netloc and current_domain and current_domain != base_domain_netloc and current_url != "about:blank"):
                first_url = queue[0]["url"] if queue and isinstance(queue[0], dict) else ""
                print(f"⚠️ Security phase: External drift → Back to {first_url}")
                if first_url:
                    try:
                        await page.goto(first_url, wait_until="load", timeout=5000)
                    except: pass
                await asyncio.sleep(1)
                # Re-scan sau khi cứu drift
                screenshot = await capture_screenshot(cursor_pos=state.get("last_action_location"))
                dom_elements_raw = await get_interactive_elements()
                dom_elements = dom_elements_raw if isinstance(dom_elements_raw, list) else []
                plan = create_page_plan(dom_elements, current_url=page.url, blacklist=blacklist)

        # ===== 4. CẬP NHẬT TRẠNG THÁI =====
        state["screenshot"] = screenshot
        state["dom_elements"] = dom_elements
        state["global_url_queue"] = queue
        state["current_page_plan"] = plan
        state["logged_in"] = is_logged_in
        
        # Enhanced login form detection
        has_login_form = False
        try:
            has_login_form = any(
                isinstance(el, dict) and (
                    el.get("type") == "password" or 
                    "login" in str(el.get("id", "")).lower() or 
                    "password" in str(el.get("id", "")).lower() or
                    "password" in str(el.get("placeholder", "")).lower()
                ) for el in dom_elements
            )
        except: pass
        state["has_login_form"] = has_login_form
        
        # [DEBUG] Save screenshot to file
        try:
            import base64
            with open("last_vision.jpg", "wb") as f:
                f.write(base64.b64decode(screenshot))
        except: pass
        
        return state
    except Exception as e:
        logger.error(f"❌ Error in vision_node: {e}")
        state["history"] = state.get("history") or []
        state["history"].append(f"❌ Lỗi nghiêm trọng tại Vision Node: {str(e)}")
        return state
