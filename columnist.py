#!/usr/bin/env python3
"""
Columnist - Interactive Point-and-Figure Chart Explorer

Usage:
    python columnist.py             # opens in native window (pywebview)
    python columnist.py --browser   # opens in default browser instead

Requirements:
    pip install yfinance pywebview
"""

import argparse
import json
import os
import socket
import threading
import webbrowser
import signal
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("Error: yfinance is required. Install with: pip install yfinance")
    sys.exit(1)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def get_settings_path():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / 'Columnist' / 'settings.json'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Columnist' / 'settings.json'
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'columnist' / 'settings.json'


def get_legacy_settings_path():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / 'PnF Viewer' / 'settings.json'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'PnF Viewer' / 'settings.json'
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'pnf-viewer' / 'settings.json'


def get_static_dir():
    here = Path(__file__).resolve().parent
    candidates = [Path(getattr(sys, '_MEIPASS', here))]
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / '_internal',
            exe_dir.parent / 'Resources',
        ])
    candidates.append(here)

    for candidate in candidates:
        if (candidate / 'index.html').exists():
            return candidate
    return candidates[0]


STATIC_DIR = get_static_dir()


DEFAULT_SETTINGS = {
    'version': 1,
    'watchlists': [
        {
            'id': 'default',
            'name': 'Default',
            'symbols': ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'GLD', 'TLT', 'USO', 'BTC-USD'],
            'readonly': True,
        },
    ],
    'tickerSettings': {},
}


def read_settings():
    path = get_settings_path()
    legacy_path = get_legacy_settings_path()
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    source_path = path if path.exists() else legacy_path
    if source_path.exists():
        try:
            saved = json.loads(source_path.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                if isinstance(saved.get('watchlists'), list):
                    settings['watchlists'] = saved['watchlists']
                if isinstance(saved.get('tickerSettings'), dict):
                    settings['tickerSettings'] = saved['tickerSettings']
        except (OSError, json.JSONDecodeError):
            pass
    if not any(w.get('id') == 'default' for w in settings.get('watchlists', [])):
        settings.setdefault('watchlists', []).insert(0, DEFAULT_SETTINGS['watchlists'][0])
    settings['settingsPath'] = str(path)
    return settings


def write_settings(settings):
    path = get_settings_path()
    clean = {
        'version': 1,
        'watchlists': settings.get('watchlists', DEFAULT_SETTINGS['watchlists']),
        'tickerSettings': settings.get('tickerSettings', {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding='utf-8')
    clean['settingsPath'] = str(path)
    return clean


def fetch_ohlc(ticker, start=None, end=None, period=None):
    kwargs = {}
    if period:
        kwargs['period'] = period
    else:
        if start:
            kwargs['start'] = start
        if end:
            kwargs['end'] = end
        if not start and not end:
            kwargs['period'] = '2y'

    df = yf.download(ticker, **kwargs, progress=False, auto_adjust=True)

    if df.empty:
        return {'error': f'No data found for {ticker}'}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    needed = ['Open', 'High', 'Low', 'Close']
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return {'error': f'Missing columns: {missing}'}

    df = df[needed].dropna()
    result = []
    for idx, row in df.iterrows():
        result.append({
            'date': idx.strftime('%Y-%m-%d'),
            'open': round(float(row['Open']), 6),
            'high': round(float(row['High']), 6),
            'low': round(float(row['Low']), 6),
            'close': round(float(row['Close']), 6),
        })
    return {'data': result, 'ticker': ticker.upper()}


class ColumnistHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/ohlc':
            params = parse_qs(parsed.query)
            ticker = params.get('ticker', ['SPY'])[0].strip()
            start = params.get('start', [None])[0]
            end = params.get('end', [None])[0]
            period = params.get('period', [None])[0]
            try:
                result = fetch_ohlc(ticker, start=start, end=end, period=period)
            except Exception as e:
                result = {'error': str(e)}
            self.send_json(result)
        elif parsed.path == '/api/settings':
            self.send_json(read_settings())
        elif parsed.path.startswith('/api/'):
            self.send_json({'error': 'Not found'}, status=404)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/settings':
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            raw = self.rfile.read(length).decode('utf-8') if length else '{}'
            payload = json.loads(raw)
            self.send_json(write_settings(payload))
        except Exception as e:
            self.send_json({'error': str(e)}, status=400)


def main():
    parser = argparse.ArgumentParser(description='Columnist - Interactive Point-and-Figure Chart Explorer')
    parser.add_argument('--browser', action='store_true',
                        help='Open in default browser instead of native window')
    args = parser.parse_args()

    port = find_free_port()
    server = HTTPServer(('127.0.0.1', port), ColumnistHandler)
    url = f'http://127.0.0.1:{port}'

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f'Columnist running at {url}')

    if args.browser:
        webbrowser.open(url)
        try:
            signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
            server.serve_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
    else:
        try:
            import webview
            webview.create_window('Columnist', url, width=1400, height=900)
            webview.start()
        except ImportError:
            print('pywebview not found, falling back to browser (pip install pywebview)')
            webbrowser.open(url)
            try:
                signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
                server.serve_forever()
            except (KeyboardInterrupt, SystemExit):
                pass

    server.shutdown()


if __name__ == '__main__':
    main()
