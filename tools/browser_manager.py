import asyncio
import os
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class BrowserManager:
    _instance = None
    _playwright = None
    _browser = None
    _context = None
    _page = None

    @classmethod
    async def get_page(cls):
        """Returns the currently active page. Initializes if necessary."""
        # Check if current page is still alive
        if cls._page is not None:
            try:
                await cls._page.evaluate("1 + 1")
                return cls._page
            except Exception:
                logger.warning("⚠️ Current page died. Attempting to recover...")
                cls._page = None

        # If we have a context but no page, try to get the last one
        if cls._context:
            pages = cls._context.pages
            if pages:
                cls._page = pages[-1] # Default to last opened page
                return cls._page

        # Initialize new browser if totally empty
        await cls._init_browser()
        return cls._page

    @classmethod
    async def _init_browser(cls):
        """Internal helper to launch browser."""
        current_file_path = os.path.abspath(__file__)
        base_dir = os.path.dirname(os.path.dirname(current_file_path))
        # Chỉ dùng thư mục browsers riêng trên Windows (bản portable)
        if os.name == 'nt':
            browsers_path = os.path.join(base_dir, "browsers")
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
            os.makedirs(browsers_path, exist_ok=True)
        
        lock_path = os.path.join(base_dir, ".browser_data", "SingletonLock")
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except: pass

        cls._playwright = await async_playwright().start()
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        # Chạy ẩn (headless) khi ở trên Streamlit Cloud hoặc server Linux không có display
        is_cloud = (
            os.environ.get("STREAMLIT_SHARING") is not None
            or os.environ.get("STREAMLIT_SERVER_HEADLESS") == "true"
            or os.path.exists("/home/appuser")  # Đặc trưng Streamlit Cloud
            or not os.environ.get("DISPLAY")  # Linux không có GUI
        )
        
        cls._browser = await cls._playwright.chromium.launch(
            headless=is_cloud,  # Chạy ẩn (headless) nếu ở trên cloud/không có display
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",  # Mở toàn màn hình ngay khi khởi động
            ],
        )
        
        cls._context = await cls._browser.new_context(
            user_agent=user_agent,
            no_viewport=True,  # Không cố định viewport → browser tự dùng kích thước cửa sổ thực
        )
        
        # === AUTO-SWITCH TO NEW TABS ===
        async def handle_new_page(new_page):
            logger.info(f"🆕 New tab detected: {new_page.url}")
            cls._page = new_page
            await new_page.bring_to_front()
            # Also handle if the new page closes
            new_page.on("close", lambda p: cls._handle_page_closed(p))

        cls._context.on("page", handle_new_page)
        cls._page = await cls._context.new_page()

    @classmethod
    def _handle_page_closed(cls, closed_page):
        """Reset cls._page if the current active page is closed."""
        if cls._page == closed_page:
            logger.info("📄 Active page closed. Switching back to the last available page...")
            if cls._context and cls._context.pages:
                cls._page = cls._context.pages[-1]
            else:
                cls._page = None

    @classmethod
    async def get_pages(cls):
        """Returns all open pages."""
        if not cls._context:
            return []
        return cls._context.pages

    @classmethod
    async def switch_to_page(cls, index: int):
        """Switches focus to a specific tab."""
        if not cls._context:
            return False
        pages = cls._context.pages
        if 0 <= index < len(pages):
            cls._page = pages[index]
            await cls._page.bring_to_front()
            return True
        return False

    @classmethod
    async def close(cls):
        """Closes the browser and releases resources."""
        print("🔒 BrowserManager: Đang đóng trình duyệt...")
        try:
            if cls._context:
                await cls._context.close()
        except Exception: pass
        try:
            if cls._browser:
                await cls._browser.close()
        except Exception: pass
        finally:
            cls._page = None
            cls._context = None
            cls._browser = None
            if cls._playwright:
                try: await cls._playwright.stop()
                except Exception: pass
                cls._playwright = None
        print("✅ BrowserManager: Trình duyệt đã đóng hoàn toàn.")

    @classmethod
    def force_reset(cls):
        """Force reset references."""
        cls._page = None
        cls._context = None
        cls._browser = None
        cls._playwright = None
        print("🔄 BrowserManager: Force reset hoàn tất.")
