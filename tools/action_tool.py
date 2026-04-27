from tools.browser_manager import BrowserManager

async def perform_action(action_type: str, selector: str = None, text: str = None, x: int = None, y: int = None):
    """
    Thực hiện các hành động trên trình duyệt: click, type, scroll.
    Đã thêm cơ chế đợi phần tử (wait_for_selector).
    """
    page = await BrowserManager.get_page()
    
    try:
        if action_type == "click":
            if selector:
                # Đợi tối đa 10 giây để phần tử xuất hiện
                # Nếu là text selector, ưu tiên dùng ':has-text' để chính xác hơn
                if selector.startswith("text="):
                    inner_text = selector.split("text=")[1].strip("'\"")
                    selector = f"text='{inner_text}'"
                
                await page.wait_for_selector(selector, timeout=10000, state="visible")
                # Highlight phần tử trước khi click để dễ debug (nếu cần xem video)
                await page.evaluate(f"s => document.querySelector(\"{selector}\")?.style?.setProperty('outline', '3px solid red')", selector)
                
                await page.click(selector)
                # Đợi trang web ổn định sau khi click
                await page.wait_for_load_state("networkidle", timeout=5000)
                return f"✅ Đã click thành công vào: {selector}"
            elif x is not None and y is not None:
                await page.mouse.click(x, y)
                return f"✅ Đã click thành công vào tọa độ: {x}, {y}"
        
        elif action_type == "type":
            if selector and text:
                await page.wait_for_selector(selector, timeout=10000)
                await page.fill(selector, text)
                return f"✅ Đã nhập '{text}' vào: {selector}"
        
        elif action_type == "hover":
            if selector:
                await page.wait_for_selector(selector, timeout=10000)
                await page.hover(selector)
                return f"✅ Đã di chuột (hover) vào: {selector}"
            elif x is not None and y is not None:
                await page.mouse.move(x, y)
                return f"✅ Đã di chuột vào tọa độ: {x}, {y}"
        
        elif action_type == "scroll":
            await page.mouse.wheel(0, 500)
            return "✅ Đã cuộn trang xuống"
            
    except Exception as e:
        return f"❌ Lỗi khi thực hiện {action_type}: {str(e)}"
    
    return "⚠️ Hành động không hợp lệ"
