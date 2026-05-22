"""
服务器管家 - 统一脚本运行服务

所有入口（前端脚本页、服务器卡片、系统托盘）都必须走这里，避免行为分叉。
日志只写入 live_logs，前端通过 list/poll 拉取，托盘启动也能被主界面发现。
"""
from __future__ import annotations

import json
import re
import threading
import traceback
from queue import Queue, Empty

from .bt_login import BtLoginer
from .chromium_session import get_automation_tab
from .live_logs import append as append_log
from .live_logs import create_run, fetch as fetch_log, finish as finish_log, list_runs
from .logger import get_logger
from .script_resolver import resolve_script_code_for_server
from .storage import get_scripts, get_servers

logger = get_logger('script_runner')


def _response(run_id: str) -> dict:
    return {
        'success': True,
        'message': '脚本开始执行，日志将实时显示',
        'run_id': run_id,
        'data': {'run_id': run_id},
    }


def _push(run_id: str, text: str) -> None:
    logger.info('script_log run_id=%s %s', run_id, text)
    append_log(run_id, text)


def _finish(run_id: str, success: bool, message: str) -> None:
    label = '执行完成' if success else '执行异常'
    append_log(run_id, '\n--- %s: %s ---\n' % (label, message))
    finish_log(run_id, success, message)


def run_code_async(code: str, context: dict | None = None, meta: dict | None = None) -> dict:
    """运行任意 Python 代码。"""
    context = context or {}
    run_meta = dict(meta or {})
    run_meta.setdefault('source', context.get('source', 'script'))
    run_meta.setdefault('script', context.get('script', {}))
    run_meta.setdefault('server', context.get('server', {}))
    run_id = create_run(run_meta)

    def _run():
        logger.info('run_code_async start run_id=%s meta=%s', run_id, run_meta)
        try:
            _push(run_id, '[INFO] 开始执行脚本...')
            server_ctx = context.get('server') if isinstance(context, dict) else {}
            if not isinstance(server_ctx, dict):
                server_ctx = {}
            safe_globals = {
                '__builtins__': __builtins__,
                'json': json,
                're': re,
                'context': context,
                'server': server_ctx,
                'get_automation_browser': get_automation_tab,
            }
            try:
                import sys as _sys
                if server_ctx:
                    _sys.argv = ['script.py', json.dumps(server_ctx, ensure_ascii=False)]
                else:
                    _sys.argv = ['script.py']
                safe_globals['sys'] = _sys
            except Exception:
                pass

            def _print(*args, **kwargs):
                _push(run_id, ' '.join(str(a) for a in args))

            safe_globals['print'] = _print
            local_vars = {}
            exec(code, safe_globals, local_vars)
            result_value = local_vars.get('result', '')
            if result_value:
                _push(run_id, str(result_value))
            _finish(run_id, True, '执行完成')
            logger.info('run_code_async success run_id=%s', run_id)
        except Exception as exc:
            tb = traceback.format_exc()
            _push(run_id, tb)
            _finish(run_id, False, str(exc))
            logger.exception('run_code_async failed run_id=%s error=%s', run_id, exc)

    threading.Thread(target=_run, daemon=True).start()
    return _response(run_id)


def run_bt_panel_async(server: dict, script_meta: dict | None = None, source: str = 'server') -> dict:
    """运行内置宝塔登录逻辑。默认脚本不再 exec data/scripts.json，避免两套逻辑。"""
    script_meta = script_meta or {'name': '宝塔自动登录'}
    run_id = create_run({
        'source': source,
        'server': _server_meta(server),
        'script': script_meta,
        'kind': 'bt_login',
    })

    def _run():
        panel_url = (server or {}).get('bt_url', '')
        username = (server or {}).get('bt_user', '')
        password = (server or {}).get('bt_pass', '')
        redirect_path = (server or {}).get('bt_redirect', '')
        logger.info(
            'run_bt_panel start run_id=%s server_id=%s redirect=%s',
            run_id, (server or {}).get('id', ''), redirect_path
        )
        try:
            _push(run_id, '[INFO] 开始执行脚本...')
            _push(run_id, '[INFO] 正在打开宝塔面板: %s' % panel_url)
            if redirect_path:
                _push(run_id, '[INFO] 登录后跳转路径: %s' % redirect_path)
            result = _call_with_timeout(
                lambda: BtLoginer().open_and_login(
                    panel_url,
                    username,
                    password,
                    redirect_path=redirect_path,
                    prefer_native=False,
                    timeout=25,
                ),
                timeout_seconds=35,
            )
            msg = (result or {}).get('message', '')
            if (result or {}).get('success'):
                _push(run_id, '[SUCCESS] %s' % (msg or '宝塔面板操作完成'))
                _finish(run_id, True, msg or '执行完成')
            else:
                _push(run_id, '[ERROR] %s' % (msg or '执行失败'))
                _finish(run_id, False, msg or '执行失败')
        except Exception as exc:
            _push(run_id, traceback.format_exc())
            _finish(run_id, False, str(exc))
            logger.exception('run_bt_panel failed run_id=%s error=%s', run_id, exc)

    threading.Thread(target=_run, daemon=True).start()
    return _response(run_id)


def _call_with_timeout(func, timeout_seconds: int = 35):
    q: Queue = Queue(maxsize=1)

    def _target():
        try:
            q.put((True, func()))
        except Exception as exc:
            q.put((False, exc))

    threading.Thread(target=_target, daemon=True).start()
    try:
        ok, payload = q.get(timeout=timeout_seconds)
    except Empty:
        return {'success': False, 'message': '浏览器自动化超时，请检查面板是否可访问'}
    if ok:
        return payload
    raise payload


def run_server_script_async(server_id: str, script_id: str = '', source: str = 'server') -> dict:
    """按 server_id 运行服务器脚本，托盘和面板共用。"""
    sid = str(server_id or '')
    if not sid:
        return {'success': False, 'message': '缺少 server_id'}

    server = _get_server_by_id(sid)
    if not server:
        return {'success': False, 'message': '服务器不存在'}

    code = ''
    script_meta = {'id': '', 'name': ''}
    selected_script_id = str(script_id or '').strip()
    if selected_script_id:
        scripts = get_scripts() or []
        for sc in scripts:
            if str(sc.get('id', '')) == selected_script_id:
                code = sc.get('code', '') or ''
                script_meta = {'id': sc.get('id', ''), 'name': sc.get('name', '')}
                break
    else:
        code, script_meta = resolve_script_code_for_server(server)

    if not code:
        return {'success': False, 'message': '未找到可执行脚本'}

    logger.info(
        'run_server_script server_id=%s script_id=%s script_name=%s redirect=%s source=%s',
        sid, script_meta.get('id', ''), script_meta.get('name', ''), server.get('bt_redirect', ''), source
    )

    # 内置默认脚本统一走后端宝塔登录器，保证托盘/面板完全一致。
    if (script_meta.get('name') or '').strip() == '宝塔自动登录':
        return run_bt_panel_async(server, script_meta=script_meta, source=source)

    return run_code_async(code, context={
        'source': source,
        'server': server,
        'script': script_meta,
    }, meta={
        'source': source,
        'server': _server_meta(server),
        'script': script_meta,
        'kind': 'python',
    })


def poll(run_id: str, since_seq=0, limit=200) -> dict:
    logger.info('poll_script_log run_id=%s since_seq=%s limit=%s', run_id, since_seq, limit)
    return fetch_log(run_id, since_seq=since_seq, limit=limit)


def list_recent(limit=20) -> dict:
    return list_runs(limit=limit)


def _get_server_by_id(server_id: str) -> dict | None:
    for server in get_servers() or []:
        if str(server.get('id', '')) == str(server_id):
            return server
    return None


def _server_meta(server: dict | None) -> dict:
    server = server or {}
    return {
        'id': server.get('id', ''),
        'name': server.get('name', ''),
        'ip': server.get('ip', ''),
        'bt_url': server.get('bt_url', ''),
        'bt_redirect': server.get('bt_redirect', ''),
    }

