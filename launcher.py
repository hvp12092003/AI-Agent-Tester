import os
import sys
import subprocess
import streamlit.web.cli as stcli
import logging
import multiprocessing

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Launcher")


def resolve_path(path):
    """Resolve paths relative to the executable or script."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, path)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), path))


if __name__ == "__main__":
    # Rất quan trọng cho Windows EXE
    multiprocessing.freeze_support()

    # Kiểm tra xem có phải Streamlit đang gọi chính nó không
    # Nếu trong args đã có 'run' hoặc các lệnh của streamlit thì bỏ qua bước init
    is_streamlit_child = len(sys.argv) > 1 and sys.argv[1] in ["run", "shell"]

    if not is_streamlit_child:
        # Bước này chỉ chạy 1 lần duy nhất khi người dùng click icon
        logger.info("Initializing AI Agent Tester...")
        try:
            # Chỉ cài trình duyệt nếu chưa có
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"], check=False
            )
        except:
            pass

        # Thiết lập đối số cho Streamlit lần đầu
        app_path = resolve_path("app.py")
        sys.argv = [
            "streamlit",
            "run",
            app_path,
            "--global.developmentMode=false",
            "--server.headless=true",
        ]

    # Chạy Streamlit CLI
    sys.exit(stcli.main())
