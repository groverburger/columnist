# PnF Viewer

Interactive Point-and-Figure chart viewer. Runs as a native macOS window or in the browser.

## Features

- **170+ tickers** in a clickable sidebar organized by category (ETFs, sectors, futures, crypto, stocks)
- **Pan, zoom, and keyboard navigation** on a canvas-rendered PnF chart
- **Per-box date hover** — hover over any X or O to see when it was added, with same-day boxes highlighted
- **Per-ticker box size** — each ticker remembers its last-used box size across sessions
- **Configurable parameters** — box size (0.25%–5%), reversal count (1–5), and date range presets
- **Standalone macOS app** — builds to a self-contained `.app` via PyInstaller

## Running from source

Requires Python 3.10+.

```bash
pip install yfinance pywebview
python pnf_viewer.py             # native window (pywebview)
python pnf_viewer.py --browser   # opens in default browser
```

`pywebview` is optional — if not installed, the app falls back to the browser automatically.

## Building the standalone app

```bash
chmod +x build.sh
./build.sh
```

This creates a virtual environment, installs build dependencies, and produces `dist/PnF Viewer.app` (~68 MB). To install:

```bash
cp -r "dist/PnF Viewer.app" /Applications/
```

### Build requirements

- macOS (uses `pywebview` with WebKit and `iconutil` for the app icon)
- Python 3.10+
- No global package installs needed — the build script creates its own venv

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `R` | Reset / fit view |
| Arrow keys | Pan |
| `+` / `-` | Zoom in / out |
| `Home` / `End` | Jump to first / last column |
| Double-click | Fit view |
| Scroll wheel | Zoom at cursor |

## Project structure

```
pnf_viewer.py       Single-file app (Python server + embedded HTML/JS)
icon.icns           macOS app icon
build.sh            Build script for standalone .app
PnF Viewer.spec     PyInstaller spec (auto-generated)
```
