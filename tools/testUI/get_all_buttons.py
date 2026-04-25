from tools.controller import controller
import logging
from browser_use.browser.session import BrowserSession

@controller.action("Lấy danh sách tất cả các nút bấm và link trên trang")
async def get_all_buttons(browser: BrowserSession):
    """
    Quét trang và trả về danh sách các nút bấm và liên kết có thể tương tác.
    """
    try:
        page = await browser.get_current_page()
        
        js_script = """
        () => {
            const elements = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'));
            return elements.map(el => {
                const isLink = el.tagName.toLowerCase() === 'a';
                const text = el.innerText || el.value || el.ariaLabel || 'No Text';
                const type = isLink ? '[LINK]' : '[BUTTON]';
                return `${type}: ${text.trim().substring(0, 50)}`;
            }).filter((v, i, a) => a.indexOf(v) === i).slice(0, 50);
        }
        """
        
        buttons = await page.evaluate(js_script)
        return "Các thành phần tương tác:\n" + "\n".join(buttons) if buttons else "Không tìm thấy nút bấm."
        
    except Exception as e:
        return f"Lỗi: {str(e)}"
