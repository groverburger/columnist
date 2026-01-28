#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV=".build-venv"

# Create virtual environment if needed
if [ ! -d "$VENV" ]; then
    echo "Creating build virtual environment..."
    python3 -m venv "$VENV"
fi

source "$VENV/bin/activate"

echo "Installing dependencies..."
pip install --quiet pyinstaller yfinance pywebview

echo "Building PnF Viewer.app..."
pyinstaller -y --windowed \
    --name "PnF Viewer" \
    --icon icon.icns \
    --hidden-import=webview \
    --hidden-import=yfinance \
    --hidden-import=pandas \
    --hidden-import=requests \
    --hidden-import=certifi \
    pnf_viewer.py

echo ""
echo "Build complete: dist/PnF Viewer.app"
echo "To install: cp -r \"dist/PnF Viewer.app\" /Applications/"
