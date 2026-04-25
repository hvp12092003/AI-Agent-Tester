# tools/__init__.py
from .controller import controller
from .testUI import get_all_buttons, get_all_links, register_click_button_tool

# Tự động đăng ký các tool vào controller
register_click_button_tool(controller)

# Export để sử dụng ở ngoài nếu cần
__all__ = ["controller", "get_all_buttons", "get_all_links"]
