import os
import sys
import subprocess
import time
import socket
import threading
import webbrowser
from pathlib import Path

# Cấu hình đường dẫn gốc
BASE_DIR = Path(__file__).parent.absolute()
BROWSERS_PATH = BASE_DIR / "browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS_PATH)

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def install_browsers():
    """Tải trình duyệt vào thư mục cục bộ nếu chưa có"""
    if not (BROWSERS_PATH / "chromium").exists():
        print("⏳ Đang tải trình duyệt Chromium vào thư mục App (chỉ thực hiện 1 lần)...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Tải trình duyệt hoàn tất.")

def run_streamlit(port):
    """Khởi chạy Streamlit server ở chế độ nền"""
    cmd = [
        sys.executable, "-m", "streamlit", "run", 
        str(BASE_DIR / "app.py"),
        "--server.port", str(port),
        "--server.headless", "true",
        "--global.developmentMode", "false"
    ]
    # Chạy ngầm và ẩn cửa sổ terminal
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    # 1. Đảm bảo trình duyệt đã sẵn sàng trong thư mục App
    install_browsers()

    # 2. Tìm cổng trống để chạy
    port = 8501
    if is_port_in_use(port):
        port = get_free_port()

    print(f"🚀 Đang khởi động AI Web Tester tại cổng {port}...")
    
    # 3. Chạy Streamlit
    process = run_streamlit(port)

    # 4. Đợi server sẵn sàng
    max_retries = 20
    while not is_port_in_use(port) and max_retries > 0:
        time.sleep(1)
        max_retries -= 1

    # 5. Mở giao diện
    url = f"http://localhost:{port}"
    
    try:
        import webview
        print("🖥️ Đang mở cửa sổ ứng dụng Native...")
        webview.create_window("AI Web Tester - Premium Edition", url, width=1280, height=850)
        webview.start()
    except ImportError:
        print("⚠️ Không tìm thấy thư viện 'pywebview'. Mở bằng trình duyệt mặc định...")
        webbrowser.open(url)
        # Giữ script chạy để duy trì server
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        # Dọn dẹp server khi đóng App
        process.terminate()
        print("👋 Đã đóng ứng dụng.")

if __name__ == "__main__":
    main()
