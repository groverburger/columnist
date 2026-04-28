# Point and Figure Viewer

An interactive Point-and-Figure (PnF) chart viewer for stocks, ETFs, futures, and crypto. Runs as a native macOS window via WebKit or in any browser.

## Features

- **170+ tickers** organized in a sidebar by category (ETFs, sectors, futures, crypto, stocks)
- **Pan, zoom, and keyboard navigation** on a canvas-rendered PnF chart
- **Per-box date hover** — hover over any X or O to see when it was added, with same-day boxes highlighted
- **Per-ticker box size** — each ticker remembers its last-used box size across sessions
- **Configurable parameters** — box size (0.25%–5%), reversal count (1–5), and date range presets
- **Standalone macOS app** — builds to a self-contained `.app` bundle via PyInstaller

## Running from source

Requires Python 3.10+.

```bash
pip install yfinance pywebview
python pnf_viewer.py             # native window (pywebview)
python pnf_viewer.py --browser   # opens in default browser
```

`pywebview` is optional — if not installed, the app automatically falls back to the browser.

## Building the standalone app

```bash
chmod +x build.sh
./build.sh
```

Creates a virtual environment, installs build dependencies, and produces `dist/PnF Viewer.app` (~68 MB).

```bash
cp -r "dist/PnF Viewer.app" /Applications/
```

**Build requirements:**
- macOS (uses `pywebview` with WebKit and `iconutil` for the app icon)
- Python 3.10+

No global package installs needed — the build script manages its own venv.

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
PnF Viewer.spec     PyInstaller spec file
tools/              Support utilities outside the packaged viewer runtime
```

## License

MIT — see [LICENSE](LICENSE).
