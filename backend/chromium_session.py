"""
共享 DrissionPage 浏览器实例：脚本运行与宝塔自动登录共用同一 Chromium，避免重复打开。
使用独立锁序列化自动化操作（导航、点击），防止多脚本并发争抢同一页面。
"""
import threading

from DrissionPage import ChromiumPage, ChromiumOptions

from .logger import get_logger
from .storage import get_settings

logger = get_logger('chromium_session')

# 串行执行脚本 / 宝塔登录等对共享页的互斥访问
automation_lock = threading.RLock()

_page = None
_page_lock = threading.Lock()


def _build_chromium_options() -> ChromiumOptions:
    co = ChromiumOptions()
    s = get_settings()
    path = (s.get('browser_path') or '').strip()
    if path:
        co.set_browser_path(path)
    co.set_argument('--no-first-run')
    co.set_argument('--disable-gpu')
    # 默认静默启动：任务栏可见，但不抢焦点
    co.set_argument('--start-minimized')
    co.set_argument('--disable-backgrounding-occluded-windows')
    co.set_argument('--disable-renderer-backgrounding')
    # 宝塔自签/HSTS 环境问题：按需求忽略证书校验
    co.set_argument('--ignore-certificate-errors')
    co.set_argument('--ignore-ssl-errors')
    co.set_argument('--allow-insecure-localhost')
    return co


def get_shared_chromium_page() -> ChromiumPage:
    """获取全局共享的 ChromiumPage，已存在则复用。"""
    global _page
    with _page_lock:
        if _page is not None:
            try:
                _ = _page.url
                return _page
            except Exception:
                try:
                    _page.quit()
                except Exception:
                    pass
                _page = None
        logger.info('create shared chromium')
        co = _build_chromium_options()
        _page = ChromiumPage(co)
        return _page


def get_automation_tab(url: str = ''):
    """
    获取一个新的标签页（在共享 Chromium 中打开），用于脚本运行。
    这样每次脚本启用都会新开 tab，不覆盖已有页面。
    """
    browser = get_shared_chromium_page()
    u = (url or '').strip() or 'about:blank'
    try:
        tab = browser.new_tab(u)
        return tab
    except Exception as exc:
        logger.warning('new_tab failed: %s, fallback to get()', exc)
        browser.get(u)
        return browser


def shutdown_shared_chromium_page():
    """关闭共享浏览器（用户主动关闭面板时调用）。"""
    global _page
    with _page_lock:
        if _page:
            try:
                _page.quit()
            except Exception:
                pass
            _page = None
