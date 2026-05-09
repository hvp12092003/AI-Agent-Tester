@echo off
echo ===================================================
echo   AI AGENT TESTER - WINDOWS BUILD SCRIPT (FIXED)
echo ===================================================

echo [1/4] Dang kiem tra Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Loi: Chua tim thay Python. Hay cai dat Python va tich chon 'Add to PATH'.
    pause
    exit /b
)

echo [2/4] Dang cai dat thu vien...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller streamlit playwright

echo [3/4] Dang tai trinh duyet Playwright...
python -m playwright install chromium

echo [4/4] Dang tien hanh dong goi EXE...
python -m PyInstaller --noconfirm --onedir --windowed ^
    --additional-hooks-dir=./hooks ^
    --collect-all playwright ^
    --collect-all streamlit ^
    --copy-metadata streamlit ^
    --add-data "app.py;." ^
    --add-data "multi_agent;multi_agent" ^
    --add-data "tools;tools" ^
    --add-data "agents;agents" ^
    --add-data ".env;." ^
    --name "AI_Agent_Tester" ^
    launcher.py

echo ===================================================
echo   BUILD HOAN TAT!
echo   Ung dung cua ban nam trong thu muc: dist\AI_Agent_Tester
echo ===================================================
pause
