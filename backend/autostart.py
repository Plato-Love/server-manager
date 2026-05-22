"""Windows 开机自启动管理。"""
import os
import sys
import winreg

from .logger import get_logger

logger = get_logger('autostart')

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
APP_NAME = 'ServerManager'


def _main_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')


def _python_executable() -> str:
    exe = sys.executable
    if exe.lower().endswith('python.exe'):
        pythonw = os.path.join(os.path.dirname(exe), 'pythonw.exe')
        if os.path.exists(pythonw):
            return pythonw
    return exe


def startup_command() -> str:
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    return f'"{_python_executable()}" "{_main_path()}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
        return value.strip() == startup_command()
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.warning('check autostart failed: %s', exc)
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        logger.info('autostart set enabled=%s command=%s', enabled, startup_command())
        return True
    except Exception as exc:
        logger.exception('set autostart failed: %s', exc)
        return False

