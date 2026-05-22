# -*- mode: python ; coding: utf-8 -*-
# PyInstaller — 服务器管家（Windows onedir）
# SPEC 由 PyInstaller 注入，指向本 .spec 的绝对路径

from pathlib import Path

ROOT = Path(SPEC).resolve().parent

block_cipher = None

_datas = [(str(ROOT / 'frontend'), 'frontend')]
_binaries = []
_extra_hidden = []

try:
    from PyInstaller.utils.hooks import collect_all
    for pkg in ('DrissionPage', 'webview'):
        d, b, h = collect_all(pkg)
        _datas += d
        _binaries += b
        _extra_hidden += h
except Exception:
    pass

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        'webview',
        'pystray._win32',
        'PIL._tkinter_finder',
        'backend.api',
        'backend.paths',
        'backend.storage',
        'backend.logger',
        'backend.bt_login',
        'backend.chromium_session',
        'backend.script_runner',
        'backend.script_resolver',
        'backend.live_logs',
        'backend.dns_manager',
        'backend.tencent_dns',
        'backend.autostart',
        'backend.single_instance',
        'backend.app_runtime',
        'backend.tools',
        'backend.recorder',
        'backend.tray',
    ]
    + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ServerManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ServerManager',
)
