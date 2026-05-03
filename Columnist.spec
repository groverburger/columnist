# -*- mode: python ; coding: utf-8 -*-

import sys

app_name = 'Columnist'
icon = 'icon.icns' if sys.platform == 'darwin' else None


a = Analysis(
    ['pnf_viewer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['webview', 'yfinance', 'pandas', 'requests', 'certifi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Columnist.app',
        icon='icon.icns',
        bundle_identifier='com.econlabs.columnist',
    )
