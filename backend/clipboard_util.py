"""读取系统剪贴板中的图片（Windows 优先）。"""
from __future__ import annotations

import base64
import io
import sys

from .logger import get_logger

logger = get_logger('clipboard')


def get_clipboard_image_base64() -> dict:
    """
    返回 {success, data: {base64, mime, width, height}} 或失败信息。
    """
    if sys.platform != 'win32':
        return {'success': False, 'message': '当前仅支持在 Windows 上读取剪贴板图片'}

    try:
        from PIL import ImageGrab
    except ImportError:
        return {'success': False, 'message': '缺少 Pillow，无法读取剪贴板图片'}

    try:
        img = ImageGrab.grabclipboard()
    except Exception as exc:
        logger.exception('grabclipboard failed: %s', exc)
        return {'success': False, 'message': '读取剪贴板失败: %s' % exc}

    if img is None:
        return {'success': False, 'message': '剪贴板中没有图片，请先复制或截图后重试'}

    if not hasattr(img, 'save'):
        return {'success': False, 'message': '剪贴板内容不是图片格式'}

    try:
        buf = io.BytesIO()
        # 统一转 PNG，避免 RGBA/P 模式兼容问题
        if getattr(img, 'mode', '') not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        img.save(buf, format='PNG')
        raw = buf.getvalue()
        if not raw:
            return {'success': False, 'message': '剪贴板图片为空'}
        b64 = base64.b64encode(raw).decode('ascii')
        return {
            'success': True,
            'data': {
                'base64': b64,
                'mime': 'image/png',
                'width': getattr(img, 'width', 0) or 0,
                'height': getattr(img, 'height', 0) or 0,
            },
        }
    except Exception as exc:
        logger.exception('encode clipboard image failed: %s', exc)
        return {'success': False, 'message': '处理剪贴板图片失败: %s' % exc}
