"""
服务器管家 - 系统托盘模块
右键菜单快速打开面板/服务器
"""
import threading
import os
from .app_runtime import request_exit
from .chromium_session import shutdown_shared_chromium_page
from .logger import get_logger

logger = get_logger('tray')


def _create_icon_image():
    """生成托盘图标 PIL Image"""
    try:
        from PIL import Image, ImageDraw
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([12, 48, 52, 58], radius=3, fill=(137, 180, 250, 255))
        draw.rounded_rectangle([14, 8, 50, 46], radius=4, fill=(137, 180, 250, 255))
        draw.ellipse([20, 16, 28, 24], fill=(166, 227, 161, 255))
        draw.ellipse([32, 16, 40, 24], fill=(166, 227, 161, 255))
        draw.rectangle([20, 30, 44, 32], fill=(30, 30, 46, 200))
        draw.rectangle([20, 36, 44, 38], fill=(30, 30, 46, 200))
        return img
    except Exception as e:
        logger.exception('图标生成失败: %s', e)
        return None


def _build_menu():
    """构建托盘右键菜单"""
    import pystray
    from pystray import Menu, MenuItem

    items = [
        MenuItem('显示主窗口', _on_show_window, default=True),
        Menu.SEPARATOR,
    ]

    try:
        from .storage import get_servers
        servers = get_servers()
        if servers:
            server_items = []
            for s in servers[:10]:
                name = s.get('name', s.get('ip', ''))
                server_id = s.get('id', '')
                bt_url = s.get('bt_url', '')

                def make_run_callback(sid, fallback_name):
                    def _cb(icon, item):
                        try:
                            # 统一走 Api.run_server_script：实时读取最新服务器配置（避免托盘缓存导致 bt_redirect 失效）
                            from .script_runner import run_server_script_async
                            resp = run_server_script_async(str(sid or ''), '', source='tray')
                            if not resp or not resp.get('success'):
                                logger.warning(
                                    'tray quick start failed sid=%s name=%s msg=%s',
                                    sid, fallback_name, (resp or {}).get('message', '')
                                )
                        except Exception as e:
                            logger.exception('tray quick start failed: %s', e)
                    return _cb

                if bt_url:
                    server_items.append(MenuItem(f'快速启动 {name}', make_run_callback(server_id, name)))

            if server_items:
                # pystray 子菜单必须使用 MenuItem + Menu(*items)，直接传字符串会在 win32 后端崩溃
                items.append(MenuItem('服务器', Menu(*server_items)))
                items.append(Menu.SEPARATOR)
    except Exception as e:
        logger.exception('加载服务器列表失败: %s', e)

    items.append(MenuItem('退出', _on_quit))
    return Menu(*items)


_tray_instance = None
_tray_started = False


def _notify_frontend_collapse_expanded():
    """主窗口被托盘/任务栏再次激活时，通知前端收起日志抽屉（不关用户打开的弹窗）。"""
    import webview
    if not webview.windows:
        return
    w = webview.windows[0]
    try:
        if hasattr(w, 'evaluate_js'):
            w.evaluate_js(
                '(function(){'
                'if(typeof window.__onWindowActivated==="function"){window.__onWindowActivated();}'
                '})();'
            )
    except Exception as exc:
        logger.debug('notify collapse expanded ui: %s', exc)


def _show_main_window():
    import webview
    windows = webview.windows
    if not windows:
        return
    w = windows[0]
    try:
        w.restore()
    except Exception:
        pass
    try:
        w.show()
    except Exception:
        pass
    _notify_frontend_collapse_expanded()


def _on_show_window(icon, item):
    """显示主窗口"""
    try:
        _show_main_window()
    except Exception as e:
        logger.exception('显示窗口失败: %s', e)


def _on_quit(icon, item):
    """退出应用"""
    global _tray_instance
    request_exit()
    shutdown_shared_chromium_page()
    if _tray_instance:
        try:
            _tray_instance.stop()
        except Exception:
            pass
    try:
        import webview
        webview.destroy()
    except Exception:
        pass
    os._exit(0)


def run_tray():
    """在后台线程中运行系统托盘"""
    global _tray_instance
    try:
        import pystray
        from PIL import Image

        img = _create_icon_image()
        if img is None:
            logger.warning('图标生成失败，跳过托盘启动')
            return

        menu = _build_menu()

        # Windows 上需要用 .ico 格式或直接传 Image
        # pystray 4.x 接受 PIL Image
        _tray_instance = pystray.Icon(
            name='server_manager',
            icon=img,
            title='服务器管家',
            menu=menu
        )
        _tray_instance.run()
        logger.info('托盘线程已退出')
    except ImportError:
        logger.error('缺少依赖，请运行: pip install pystray Pillow')
    except Exception as e:
        logger.exception('托盘启动失败: %s', e)


def notify_frontend_collapse_expanded():
    """供 main 窗口事件与托盘显示主窗口时调用。"""
    _notify_frontend_collapse_expanded()


def start_tray():
    """启动托盘（非阻塞）"""
    global _tray_started
    if _tray_started:
        return
    _tray_started = True
    t = threading.Thread(target=run_tray, daemon=True)
    t.start()
    logger.info('托盘线程启动')
