@echo off
setlocal enabledelayedexpansion
title AI Agent Portable Setup - GOLD VERSION
echo ======================================================
echo   HE THONG TU DONG THIET LAP AI AGENT (WINDOWS)
echo ======================================================

:: Tu dong xac dinh thu muc hien tai
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo [*] BUOC 1: TAI PYTHON (10MB)...
if not exist py.zip (
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile 'py.zip'"
)

echo [*] BUOC 2: GIAI NEN MOI TRUONG...
if exist py_env rmdir /s /q py_env
mkdir py_env
powershell -Command "Expand-Archive -Path 'py.zip' -DestinationPath 'py_env' -Force"
del py.zip

echo [*] BUOC 3: CAI DAT PIP...
powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'"
py_env\python.exe get-pip.py --no-warn-script-location
del get-pip.py

:: Kich hoat site-packages
echo import site >> py_env\python311._pth

echo [*] BUOC 4: CAI DAT THU VIEN (MAT 1-2 PHUT)...
py_env\python.exe -m pip install -r requirements.txt

echo [*] BUOC 5: CAI DAT TRINH DUYET AI VAO THU MUC NOI BO...
:: Ep Playwright cai vao thu muc "browsers" ngay tai day
set "PLAYWRIGHT_BROWSERS_PATH=%ROOT_DIR%browsers"
if not exist browsers mkdir browsers
py_env\python.exe -m playwright install chromium

echo [*] BUOC 6: TAO FILE KHOI DONG (KHONG LOI)...
(
echo @echo off
echo set "PLAYWRIGHT_BROWSERS_PATH=%%~dp0browsers"
echo echo Dang khoi dong AI Agent Tester...
echo "%%~dp0py_env\python.exe" -m streamlit run "%%~dp0app.py" --server.headless true
echo pause
) > "CHAY_APP_TAI_DAY.bat"

echo ======================================================
echo CHUC MUNG! Ban Portable da hoan thanh 100%%.
echo Bay gio ban chi can bam file [CHAY_APP_TAI_DAY.bat] de bat dau.
echo ======================================================
pause
