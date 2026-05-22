"""
服务器管家 - 主入口
启动 pywebview 桌面应用 + 系统托盘
"""
import os
import sys
import webview

# 确保项目根目录在路径中（源码运行）；frozen 由 PyInstaller 处理
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, 'frozen', False) and BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.api import Api
from backend.paths import frontend_dir, is_frozen
from backend.app_runtime import is_exiting
from backend.logger import get_logger
from backend.single_instance import acquire_single_instance, release_single_instance
from backend.tray import start_tray, notify_frontend_collapse_expanded
from backend.window_theme import APP_BACKGROUND_HEX, apply_window_chrome

logger = get_logger('main')


def main():
    if not acquire_single_instance():
        return
    api = Api()

    # 前端文件目录（打包后在 _MEIPASS/frontend）
    _fe = frontend_dir()
    index_path = os.path.join(_fe, 'index.html')

    # 无边框 + HTML 自定义顶栏，避免系统黑色标题栏与 Python 图标
    window = webview.create_window(
        title='服务器管家',
        url=index_path,
        js_api=api,
        width=1200,
        height=800,
        min_size=(900, 600),
        text_select=True,
        background_color=APP_BACKGROUND_HEX,
        frameless=True,
        easy_drag=False,
    )
    api.set_window(window)

    def _hide_window_to_tray():
        try:
            if hasattr(window, 'hide'):
                window.hide()
            elif hasattr(window, 'minimize'):
                window.minimize()
        except Exception as exc:
            logger.warning('隐藏窗口到托盘失败: %s', exc)

    # 窗口就绪后启动系统托盘
    def on_loaded():
        logger.info('主窗口加载完成')
        apply_window_chrome(window)
        start_tray()

    def on_closing():
        if is_exiting():
            return True
        logger.info('窗口关闭事件：默认隐藏到托盘')
        _hide_window_to_tray()
        return False

    window.events.loaded += on_loaded
    window.events.closing += on_closing

    def on_window_shown():
        notify_frontend_collapse_expanded()

    def on_window_restored():
        notify_frontend_collapse_expanded()

    if hasattr(window.events, 'shown'):
        window.events.shown += on_window_shown
    if hasattr(window.events, 'restored'):
        window.events.restored += on_window_restored

    # 生产 exe 默认关闭 webview 调试；开发或设置 SERVER_MANAGER_DEBUG=1 可开启
    _debug = (not is_frozen()) or (os.environ.get('SERVER_MANAGER_DEBUG', '').strip() == '1')
    logger.info('应用启动 debug=%s frozen=%s', _debug, is_frozen())
    try:
        webview.start(debug=_debug)
    finally:
        release_single_instance()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        logger.exception('应用启动失败: %s', exc)
        raise
