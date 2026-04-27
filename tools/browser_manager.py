import asyncio
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
            cls._playwright = await async_playwright().start()
            # Khởi chạy trình duyệt với tham số mở rộng toàn màn hình
            cls._browser = await cls._playwright.chromium.launch(
                headless=False,
                args=[
                    "--window-size=1920,1080", # Ép kích thước Full HD
                    "--window-position=-1920,0" # Vị trí màn hình bên TRÁI
                ] 
            )
            # Thiết lập context không giới hạn viewport để nó tự nhận theo kích thước cửa sổ
            cls._context = await cls._browser.new_context(no_viewport=True)
            cls._page = await cls._context.new_page()
        return cls._page

    @classmethod
    async def close(cls):
        if cls._browser:
            await cls._browser.close()
        if cls._playwright:
            await cls._playwright.stop()
        cls._page = None
        cls._context = None
        cls._browser = None
        cls._playwright = None
