from tools.controller import controller
import logging
# Import chuẩn xác BrowserSession cho phiên bản 0.12.6
from browser_use.browser.session import BrowserSession

@controller.action("Lấy tất cả liên kết nội bộ từ trang hiện tại")
async def get_all_links(browser: BrowserSession):
    """
    Tự động quét trang web hiện tại và trả về danh sách tối đa 30 URL nội bộ.
    """
    try:
        # Trong phiên bản này, ta lấy page trực tiếp từ session
        page = await browser.get_current_page()
        
        js_script = """
        () => {
            const currentHostname = window.location.hostname;
            const links = Array.from(document.querySelectorAll('a'));
            
            const internalLinks = links
                .map(a => {
                    try {
                        const url = new URL(a.href);
                        if (url.hostname === currentHostname || url.hostname === '') {
                            if (a.href.includes('#') || a.href.startsWith('javascript:') || 
                                a.href.startsWith('mailto:') || a.href.startsWith('tel:')) {
                                return null;
                            }
                            return a.href;
                        }
                    } catch(e) {
                        if (a.getAttribute('href') && !a.getAttribute('href').startsWith('http')) {
                             return window.location.origin + a.getAttribute('href');
                        }
                    }
                    return null;
                })
                .filter((val, index, self) => val !== null && val !== '' && self.indexOf(val) === index)
                .slice(0, 30);
            
            return internalLinks;
        }
        """
        
        links = await page.evaluate(js_script)
        
        if not links:
            return "Không tìm thấy liên kết nội bộ nào."
            
        return "Danh sách URL nội bộ:\n" + "\n".join(links)
        
    except Exception as e:
        return f"Lỗi thực thi tool: {str(e)}"
