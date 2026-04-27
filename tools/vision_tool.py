import base64
from tools.browser_manager import BrowserManager

async def capture_screenshot(url: str = None):
    """
    Chụp ảnh màn hình trang web. Nếu có URL, sẽ điều hướng đến đó trước.
    Trả về ảnh dưới dạng base64 string.
    """
    page = await BrowserManager.get_page()
    if url:
        await page.goto(url, wait_until="networkidle")
    
    # Chụp ảnh và chuyển sang base64
    screenshot_bytes = await page.screenshot(full_page=False)
    base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
    return base64_image
