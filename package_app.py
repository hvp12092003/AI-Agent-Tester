import PyInstaller.__main__
import os
import shutil
from pathlib import Path

def build_app():
    # 1. Xác định thư mục hiện tại
    base_dir = Path(__file__).parent.absolute()
    app_name = "AI_Web_Tester"
    
    print(f"📦 Bắt đầu đóng gói ứng dụng: {app_name}")

    # 2. Xóa các thư mục build cũ
    for folder in ["build", "dist"]:
        path = base_dir / folder
        if path.exists():
            shutil.rmtree(path)

    # 3. Danh sách các file và thư mục cần đính kèm (Add Data)
    # Định dạng: 'nguồn:đích' (trên Mac dùng dấu :, trên Win dùng dấu ;)
    separator = ":" if os.name != "nt" else ";"
    
    datas = [
        f"multi_agent{separator}multi_agent",
        f"tools{separator}tools",
        f"agents{separator}agents",
        f"assets{separator}assets",
        f"app.py{separator}.",
        f".env{separator}.",
        f"AGENT_RULES.md{separator}."
    ]

    # 4. Các tham số PyInstaller
    args = [
        'launcher.py',            # File khởi chạy chính
        f'--name={app_name}',      # Tên ứng dụng
        '--onedir',                # Đóng gói vào 1 thư mục (Portable)
        '--noconsole',             # Không hiện cửa sổ console khi chạy
        '--clean',                 # Xóa cache cũ
    ]

    # Thêm dữ liệu vào tham số
    for data in datas:
        args.append(f'--add-data={data}')

    # 5. Chạy PyInstaller
    print("🚀 Đang thực thi PyInstaller (quá trình này có thể mất vài phút)...")
    PyInstaller.__main__.run(args)

    print("\n" + "="*30)
    print(f"✅ ĐÓNG GÓI HOÀN TẤT!")
    print(f"📂 Vị trí App: {base_dir / 'dist' / app_name}")
    print("="*30)
    print("👉 Lưu ý: Lần đầu tiên chạy App, nó sẽ tự động tải trình duyệt Chromium vào thư mục 'dist/AI_Web_Tester/browsers'.")
    print("👉 Sau khi tải xong, bạn có thể copy nguyên thư mục 'dist/AI_Web_Tester' đi gửi cho khách hàng.")

if __name__ == "__main__":
    build_app()
