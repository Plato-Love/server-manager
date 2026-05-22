"""Windows 单实例锁。"""
import ctypes
import ctypes.wintypes

from .logger import get_logger

logger = get_logger('single_instance')

ERROR_ALREADY_EXISTS = 183
_mutex_handle = None


def acquire_single_instance(name: str = 'Global\\ServerManagerPywebviewSingleton') -> bool:
    """获取全局互斥锁；已存在实例则返回 False。"""
    global _mutex_handle
    if _mutex_handle:
        return True
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateMutexW.argtypes = (
        ctypes.wintypes.LPVOID,
        ctypes.wintypes.BOOL,
        ctypes.wintypes.LPCWSTR,
    )
    kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        logger.warning('CreateMutexW failed: %s', ctypes.get_last_error())
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        logger.info('another instance is already running')
        return False
    _mutex_handle = handle
    return True


def release_single_instance():
    global _mutex_handle
    if not _mutex_handle:
        return
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    try:
        kernel32.ReleaseMutex(_mutex_handle)
        kernel32.CloseHandle(_mutex_handle)
    except Exception as exc:
        logger.warning('release mutex failed: %s', exc)
    _mutex_handle = None

