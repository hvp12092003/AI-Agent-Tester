import os
import asyncio
from playwright.async_api import Page

class FileTool:
    def __init__(self, assets_dir="test_assets"):
        self.assets_dir = assets_dir
        if not os.path.exists(self.assets_dir):
            os.makedirs(self.assets_dir)

    def list_test_files(self):
        """Liệt kê danh sách các file trong thư mục test_assets."""
        try:
            files = os.listdir(self.assets_dir)
            if not files:
                return "Thư mục test_assets đang trống. Hãy bỏ ảnh vào đó."
            return f"Danh sách file có sẵn: {', '.join(files)}"
        except Exception as e:
            return f"Lỗi khi đọc thư mục: {str(e)}"

    async def upload_file_to_element(self, page: Page, selector: str, filename: str):
        """Tải một file lên phần tử web cụ thể, hỗ trợ tìm input ẩn."""
        file_path = os.path.abspath(os.path.join(self.assets_dir, filename))
        if not os.path.exists(file_path):
            return f"Lỗi: File '{filename}' không tồn tại trong thư mục {self.assets_dir}."
        
        try:
            # 1. Thử set trực tiếp (nếu selector là input)
            try:
                await page.set_input_files(selector, file_path, timeout=2000)
                return f"✅ Đã tải file '{filename}' lên thành công (Direct)."
            except:
                pass

            # 2. Thử tìm input file bên trong phần tử đó
            try:
                inner_input = f"{selector} input[type='file']"
                await page.set_input_files(inner_input, file_path, timeout=2000)
                return f"✅ Đã tải file '{filename}' lên thành công (Inner input)."
            except:
                pass

            # 3. Sử dụng File Chooser (Click vào phần tử và đợi hội thoại chọn file)
            try:
                async with page.expect_file_chooser(timeout=3000) as fc_info:
                    await page.click(selector)
                file_chooser = await fc_info.value
                await file_chooser.set_files(file_path)
                return f"✅ Đã tải file '{filename}' lên thành công (File Chooser)."
            except Exception as e:
                return f"❌ Lỗi: Không tìm thấy input file và không mở được hội thoại chọn file. Chi tiết: {str(e)}"

        except Exception as e:
            return f"❌ Lỗi khi tải file: {str(e)}"
