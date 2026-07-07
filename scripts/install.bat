@echo off
echo ==========================================
echo   App Adapter — One-Click Install
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
python --version
echo.

:: Install dependencies
echo [1/3] Installing core dependencies...
pip install pyautogui uiautomation -q

:: Optional: Playwright for real browser automation
echo [2/3] Installing Playwright (optional, for browser automation)...
pip install playwright -q
python -m playwright install chromium --quiet 2>nul
echo     If Playwright install failed, browser actions will still work in instruction mode.

:: Optional: Office tools
echo [3/3] Installing optional packages...
pip install openpyxl python-docx python-pptx pdfplumber weasyprint -q

echo.
echo ==========================================
echo   Done! App Adapter is ready.
echo.
echo   Quick test:
echo     python -c "from app_adapter import app_list; print(app_list())"
echo.
echo   Start MCP server:
echo     python server.py --port 8080
echo ==========================================
pause
