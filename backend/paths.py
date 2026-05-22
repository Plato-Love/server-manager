"""应用路径：开发与 PyInstaller 打包后一致读写。"""
import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def bundle_dir() -> str:
    """只读资源目录（源码项目根目录 或 frozen 解压目录 `_MEIPASS`）。"""
    if is_frozen():
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def app_root_dir() -> str:
    """可写数据根目录（与可执行文件同级；开发时为项目根）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    d = os.path.join(app_root_dir(), 'data')
    os.makedirs(d, exist_ok=True)
    return d


def frontend_dir() -> str:
    return os.path.join(bundle_dir(), 'frontend')
