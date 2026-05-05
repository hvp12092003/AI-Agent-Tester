#!/bin/zsh
# Di chuyển vào thư mục dự án
cd "/Users/mrpazou/3DART/AI Agent/AI Agent Tester"

# Kích hoạt môi trường ảo
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ Không tìm thấy thư mục venv. Hãy đảm bảo bạn đã tạo môi trường ảo."
    exit 1
fi

# Chạy dự án
python main.py
