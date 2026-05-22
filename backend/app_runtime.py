"""应用运行态标记。"""

_exiting = False


def request_exit():
    global _exiting
    _exiting = True


def is_exiting() -> bool:
    return _exiting

