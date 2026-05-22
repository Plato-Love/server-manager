"""
服务器管家 - 脚本解析/选择（托盘/快捷启动共用）
"""
from __future__ import annotations

from .storage import get_scripts


def resolve_script_code_for_server(server: dict) -> tuple[str, dict]:
    """
    根据服务器绑定脚本优先选择脚本代码；若未绑定，则回退到默认“宝塔自动登录”脚本。
    返回 (code, script_meta)
    """
    scripts = get_scripts() or []
    bind_script = (server or {}).get('bind_script', '') or ''

    if bind_script:
        for sc in scripts:
            if str(sc.get('id', '')) == str(bind_script):
                return (sc.get('code', '') or ''), {'id': sc.get('id', ''), 'name': sc.get('name', '')}

    for sc in scripts:
        if (sc.get('name') or '').strip() == '宝塔自动登录':
            return (sc.get('code', '') or ''), {'id': sc.get('id', ''), 'name': sc.get('name', '')}

    return '', {'id': '', 'name': ''}

