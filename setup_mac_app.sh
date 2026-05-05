#!/bin/zsh

# Đường dẫn dự án và Desktop
PROJECT_DIR="/Users/mrpazou/3DART/AI Agent/AI Agent Tester"
APP_NAME="AI_Tester.app"
DESKTOP_DIR="$HOME/Desktop"
ICON_PATH="/Users/mrpazou/.gemini/antigravity/brain/790c71ad-2cac-43ea-8c65-48ec6e4d86f0/ai_tester_icon_1777370114559.png"

echo "⚙️ Đang khởi tạo ứng dụng Mac..."

# 1. Tạo script AppleScript
SCRIPTS_DIR="$PROJECT_DIR/scripts"
mkdir -p "$SCRIPTS_DIR"
OSASCRIPT_PATH="$SCRIPTS_DIR/run_app.applescript"

cat <<EOF > "$OSASCRIPT_PATH"
do shell script "cd '$PROJECT_DIR' && source venv/bin/activate && streamlit run app.py > /dev/null 2>&1 &"
display notification "AI Agent Tester đang khởi động..." with title "AI Tester"
EOF

# 2. Biên dịch thành file .app trên Desktop
osacompile -o "$DESKTOP_DIR/$APP_NAME" "$OSASCRIPT_PATH"

echo "✅ Đã tạo file $APP_NAME trên Desktop."

# 3. Gắn Icon cho App (Sử dụng Python để xử lý ảnh nếu cần, hoặc sips)
# Trick: Gắn icon nhanh cho Mac
if [[ -f "$ICON_PATH" ]]; then
    # Tạo thư mục Resource và copy icon vào
    cp "$ICON_PATH" "$DESKTOP_DIR/$APP_NAME/Contents/Resources/applet.icns" 2>/dev/null || true
    echo "🎨 Đã cập nhật biểu tượng ứng dụng."
fi

echo "🚀 Xong! Bây giờ bạn chỉ cần ra màn hình Desktop và click vào icon AI_Tester là dùng được ngay."
