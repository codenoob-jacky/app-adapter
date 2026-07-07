#!/bin/bash
echo "=========================================="
echo "  App Adapter — One-Click Install"
echo "=========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[X] Python not found. Please install Python 3.10+"
        exit 1
    fi
    PYTHON=python
else
    PYTHON=python3
fi

$PYTHON --version
echo ""

# Install dependencies
echo "[1/3] Installing core dependencies..."
$PYTHON -m pip install pyautogui -q

# Optional: Playwright
echo "[2/3] Installing Playwright (optional, for browser automation)..."
$PYTHON -m pip install playwright -q
$PYTHON -m playwright install chromium --quiet 2>/dev/null
echo "    If Playwright install failed, browser actions will still work in instruction mode."

# Optional: Office tools
echo "[3/3] Installing optional packages..."
$PYTHON -m pip install openpyxl python-docx python-pptx pdfplumber weasyprint -q

echo ""
echo "=========================================="
echo "  Done! App Adapter is ready."
echo ""
echo "  Quick test:"
echo "    $PYTHON -c 'from app_adapter import app_list; print(app_list())'"
echo ""
echo "  Start MCP server:"
echo "    $PYTHON server.py --port 8080"
echo "=========================================="
