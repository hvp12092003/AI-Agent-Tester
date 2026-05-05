import asyncio
import os
from playwright.async_api import async_playwright


class BrowserManager:
    _instance = None
    _playwright = None
    _browser = None
    _context = None
    _page = None

    @classmethod
    async def get_page(cls):
        if cls._page is None:
            # Thiết lập đường dẫn trình duyệt cục bộ
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            browsers_path = os.path.join(base_dir, "browsers")
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
            
            # Đảm bảo thư mục tồn tại
            if not os.path.exists(browsers_path):
                os.makedirs(browsers_path, exist_ok=True)

            # Tự động xóa lock nếu trình duyệt trước đó bị treo
            lock_path = os.path.join(base_dir, ".browser_data", "SingletonLock")
            if os.path.exists(lock_path):
                try: os.remove(lock_path)
                except: pass

            cls._playwright = await async_playwright().start()
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            
            # Kiểm tra xem trình duyệt đã tồn tại chưa, nếu chưa có thể cần cài đặt (sẽ xử lý ở launcher)
            cls._browser = await cls._playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled", # Ẩn cờ automation
                    "--window-position=0,0",
                    "--window-size=1440,900",
                ],
            )
            
            cls._context = await cls._browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1440, "height": 900},
            )
            cls._page = cls._context.pages[0] if cls._context.pages else await cls._context.new_page()
        return cls._page

    @classmethod
    async def close(cls):
        try:
            if cls._context:
                await cls._context.close()
            if cls._browser:
                await cls._browser.close()
        except Exception:
            pass
        finally:
            cls._page = None
            cls._context = None
            cls._browser = None
            if cls._playwright:
                try:
                    await cls._playwright.stop()
                except:
                    pass
                cls._playwright = None
