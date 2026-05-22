"""Windows 窗口主题：标题栏/边框与前端主题色一致。"""
from __future__ import annotations

import sys

from .logger import get_logger

logger = get_logger('window_theme')

# 与 frontend :root 变量一致
APP_BACKGROUND_HEX = '#1e1e2e'
APP_SURFACE_HEX = '#181825'
APP_TEXT_HEX = '#cdd6f4'


def _hex_to_bgr(hex_color: str) -> int:
    h = (hex_color or '').lstrip('#')
    if len(h) != 6:
        return 0x002e1e1e
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_window_chrome(window) -> None:
    """标题栏、边框颜色与 Catppuccin 深色主题一致。"""
    if sys.platform != 'win32':
        return
    try:
        native = getattr(window, 'native', None)
        if not native:
            return
        hwnd = _get_hwnd(native)
        if not hwnd:
            return
        _apply_theme_chrome(hwnd)
        logger.info('已应用窗口主题色 hwnd=%s', hwnd)
    except Exception as exc:
        logger.warning('应用窗口主题失败: %s', exc)


def _get_hwnd(native) -> int | None:
    if hasattr(native, 'Handle'):
        try:
            return int(native.Handle.ToInt32())
        except Exception:
            pass
    return None


def _dwm_set(hwnd: int, attr: int, value: int) -> None:
    import ctypes
    val = ctypes.c_int(value)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)
    )


def _apply_theme_chrome(hwnd: int) -> None:
    caption_bgr = _hex_to_bgr(APP_BACKGROUND_HEX)
    border_bgr = _hex_to_bgr(APP_SURFACE_HEX)
    text_bgr = _hex_to_bgr(APP_TEXT_HEX)

    # 深色模式
    _dwm_set(hwnd, 20, 1)   # DWMWA_USE_IMMERSIVE_DARK_MODE
    try:
        _dwm_set(hwnd, 38, 2)  # immersive dark mode policy (Win11)
    except Exception:
        pass

    # Win11 自定义标题栏/边框（BGR）
    for attr, color in (
        (35, caption_bgr),  # CAPTION_COLOR
        (34, border_bgr),   # BORDER_COLOR
        (36, text_bgr),     # TEXT_COLOR
    ):
        try:
            _dwm_set(hwnd, attr, color)
        except Exception:
            pass
