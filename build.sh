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
PYTHON="$VENV/bin/python"

echo "Installing dependencies..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet pyinstaller yfinance pywebview

echo "Building Columnist..."
"$PYTHON" -m PyInstaller -y "Columnist.spec"

echo ""
if [ "$(uname -s)" = "Darwin" ]; then
    echo "Build complete: dist/Columnist.app"
    echo "To install: cp -r \"dist/Columnist.app\" /Applications/"
else
    echo "Build complete: dist/Columnist/"
fi
