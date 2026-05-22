"""
DNS 记录 AI 识别（Cursor Agent CLI）

支持文本 + 截图，异步执行，结果通过 poll 返回。
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from typing import Any

from .live_logs import append as append_log
from .live_logs import create_run, fetch as fetch_log, finish as finish_log
from .logger import get_logger
from .dns_parse_config import apply_proxy_to_env, get_dns_parse_config, resolve_cursor_model
from .paths import data_dir
from .dns_detect import (
    enrich_records_with_domain_hints,
    normalize_console_table_record,
)

logger = get_logger('dns_ai_parse')

_PARSE_RESULTS: dict[str, dict] = {}
_LOCK = threading.RLock()

_DNS_TYPES = frozenset({'A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'})
_HEADER_MARKERS = ('校验域名', '主机记录', '记录类型', '记录值', 'txt记录值', 'a记录值')


def _resolve_agent_executable(settings: dict | None) -> str:
    settings = settings or {}
    custom = (settings.get('cursor_agent_path') or '').strip()
    if custom:
        if os.path.isfile(custom):
            return custom
        raise FileNotFoundError('未找到配置的 Cursor Agent 路径: %s' % custom)

    found = shutil.which('agent')
    if found:
        return found

    local = os.environ.get('LOCALAPPDATA') or ''
    home = os.environ.get('USERPROFILE') or os.path.expanduser('~')
    candidates = [
        os.path.join(local, 'cursor-agent', 'agent.exe'),
        os.path.join(local, 'cursor-agent', 'agent.ps1'),
        os.path.join(local, 'cursor-agent', 'agent.cmd'),
        os.path.join(home, '.cursor', 'bin', 'agent.exe'),
        os.path.join(home, '.cursor', 'bin', 'agent.ps1'),
        os.path.join(home, '.cursor', 'bin', 'agent.cmd'),
        os.path.join(home, 'AppData', 'Local', 'cursor-agent', 'agent.exe'),
        os.path.join(home, 'AppData', 'Local', 'cursor-agent', 'agent.ps1'),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path

    raise FileNotFoundError(
        '未找到 Cursor Agent CLI。请在设置中填写 agent 路径，'
        '或在 PowerShell 执行: irm https://cursor.com/install?win32=true | iex'
    )


def _normalize_record_type(raw: str) -> str:
    s = re.sub(r'\s+', '', str(raw or '').upper())
    if not s:
        return ''
    for token, rtype in (
        ('TXT', 'TXT'),
        ('AAAA', 'AAAA'),
        ('CNAME', 'CNAME'),
        ('MX', 'MX'),
        ('NS', 'NS'),
        ('SRV', 'SRV'),
        ('CAA', 'CAA'),
    ):
        if token in s:
            return rtype
    if s == 'A' or 'A记录' in s or s.startswith('A'):
        return 'A'
    return s if s in _DNS_TYPES else ''


def parse_console_table_text(text: str) -> list[dict]:
    """解析控制台复制的表格行。"""
    out: list[dict] = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if any(m in line for m in _HEADER_MARKERS) and ('记录' in line or '域名' in line):
            continue

        line = re.sub(r'\s*复制\s*', ' ', line)
        line = re.sub(r'\s+', ' ', line).strip()

        domain = ''
        rr = ''
        rtype_raw = ''
        value = ''

        row_m = re.match(
            r'^([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})\s+(\S+)\s+(.+?)\s+([A-Za-z0-9][\w.+:/=-]{8,})\s*$',
            line,
        )
        if row_m:
            domain, rr, rtype_raw, value = row_m.group(1), row_m.group(2), row_m.group(3), row_m.group(4)
        else:
            cols = [c for c in re.split(r'\t+|\s{2,}', line) if c and c != '复制']
            if len(cols) < 3:
                cols = [c for c in line.split() if c != '复制']
            if len(cols) < 3:
                continue
            if re.match(r'^[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,}$', cols[0]):
                domain = cols[0]
                rr = cols[1]
                rtype_raw = cols[2]
                value = cols[-1]
            else:
                rr = cols[0]
                rtype_raw = cols[1]
                value = cols[-1]

        rtype = _normalize_record_type(rtype_raw)
        if not rtype or not value:
            continue
        rec = {
            'type': rtype,
            'rr': (rr or '@').strip().rstrip('.'),
            'value': value.strip(),
            'ttl': 600,
            'domain': domain.rstrip('.') if domain else '',
        }
        out.append(normalize_console_table_record(rec))
    return enrich_records_with_domain_hints(out, text)


def _save_image_temp(image_base64: str) -> str:
    raw = (image_base64 or '').strip()
    if not raw:
        return ''
    if ',' in raw and raw.startswith('data:'):
        raw = raw.split(',', 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception as exc:
        raise ValueError('图片 base64 无效: %s' % exc) from exc
    fd, path = tempfile.mkstemp(suffix='.png', prefix='dns_ai_', dir=data_dir())
    os.close(fd)
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def _build_prompt(text: str, image_path: str, domain_hint: str) -> str:
    hint = (domain_hint or '').strip()
    lines = [
        '你是 DNS 解析助手。从文本或截图中提取 DNS 解析记录。',
        '只输出 JSON 数组，不要 markdown 代码块，不要解释。',
        '每项字段：type(A/AAAA/CNAME/MX/TXT/NS/SRV/CAA)、rr、value、ttl(默认600)、domain(根域)。',
        '控制台「校验域名」列若是完整主机名，请写入 domain 并在 rr 填相对记录名。',
    ]
    if hint:
        lines.append('优先根域：%s' % hint)
    if text:
        lines.append('文本：\n' + text)
    if image_path:
        lines.append('截图文件：%s' % image_path)
    return '\n'.join(lines)


def _extract_json_array(text: str) -> list[dict]:
    text = (text or '').strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ('records', 'data', 'list', 'items', 'result'):
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
    except Exception:
        pass
    start = text.find('[')
    end = text.rfind(']')
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except Exception:
            pass
    return []


def _normalize_records(items: list[dict], text: str = '') -> list[dict]:
    out: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        rtype = _normalize_record_type(
            item.get('type') or item.get('Type') or item.get('record_type') or ''
        )
        value = str(item.get('value') or item.get('Value') or '').strip()
        if not rtype or not value:
            continue
        rec = {
            'type': rtype,
            'rr': str(item.get('rr') or item.get('RR') or item.get('name') or item.get('Name') or '@').strip() or '@',
            'value': value,
            'ttl': int(item.get('ttl') or item.get('TTL') or 600) or 600,
            'domain': str(item.get('domain') or item.get('Domain') or '').strip().rstrip('.'),
        }
        out.append(normalize_console_table_record(rec))
    return enrich_records_with_domain_hints(out, text)


def _subprocess_hidden_kwargs() -> dict:
    if sys.platform != 'win32':
        return {}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return {'creationflags': flags} if flags else {}


def _version_dir_sort_key(name: str) -> int:
    m = re.match(r'^(\d{4})\.(\d{1,2})\.(\d{1,2})-', name)
    if not m:
        return -1
    return int(m.group(1) + m.group(2).zfill(2) + m.group(3).zfill(2))


def _resolve_direct_node_cmd(agent_path: str, agent_args: list[str]) -> list[str] | None:
    low = agent_path.lower()
    if not low.endswith(('.ps1', '.cmd')):
        return None
    script_dir = os.path.dirname(os.path.abspath(agent_path))
    node_exe = os.path.join(script_dir, 'node.exe')
    index_js = os.path.join(script_dir, 'index.js')
    if os.path.isfile(node_exe) and os.path.isfile(index_js):
        return [node_exe, index_js] + agent_args

    versions_root = os.path.join(script_dir, 'versions')
    if not os.path.isdir(versions_root):
        return None
    version_dirs = []
    for name in os.listdir(versions_root):
        full = os.path.join(versions_root, name)
        if os.path.isdir(full) and _version_dir_sort_key(name) >= 0:
            version_dirs.append((_version_dir_sort_key(name), full))
    if not version_dirs:
        return None
    version_dirs.sort(key=lambda item: item[0], reverse=True)
    best_dir = version_dirs[0][1]
    node_exe = os.path.join(best_dir, 'node.exe')
    index_js = os.path.join(best_dir, 'index.js')
    if os.path.isfile(node_exe) and os.path.isfile(index_js):
        return [node_exe, index_js] + agent_args
    return None


def _run_agent(
    agent_path: str,
    prompt: str,
    api_key: str,
    parse_cfg: dict | None = None,
    timeout_sec: int = 180,
) -> str:
    parse_cfg = parse_cfg or get_dns_parse_config()
    env = os.environ.copy()
    env.pop('CURSOR_API_KEY', None)
    if api_key:
        env['CURSOR_API_KEY'] = api_key
    env = apply_proxy_to_env(env, parse_cfg)

    cli_model, model_label = resolve_cursor_model(parse_cfg)
    agent_args = ['-p', '--trust', '-f', '--output-format', 'text']
    if cli_model:
        agent_args.extend(['--model', cli_model])
    agent_args.append(prompt)

    direct = _resolve_direct_node_cmd(agent_path, agent_args)
    if direct:
        cmd = direct
    else:
        low = agent_path.lower()
        sibling_exe = os.path.join(os.path.dirname(agent_path), 'agent.exe')
        if os.path.isfile(sibling_exe):
            cmd = [sibling_exe] + agent_args
        elif low.endswith('.ps1'):
            cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', agent_path] + agent_args
        elif low.endswith('.cmd'):
            cmd = ['cmd', '/c', agent_path] + agent_args
        else:
            cmd = [agent_path] + agent_args

    auth = 'config_key' if api_key else 'system_account'
    logger.info(
        'run agent: %s auth=%s model=%s trust=on',
        agent_path,
        auth,
        cli_model or model_label,
    )
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env,
        timeout=timeout_sec,
        cwd=data_dir(),
        **_subprocess_hidden_kwargs(),
    )
    stdout = (proc.stdout or '').strip()
    stderr = (proc.stderr or '').strip()
    if proc.returncode != 0:
        detail = stderr or stdout or ('exit code %s' % proc.returncode)
        raise RuntimeError('Cursor Agent 执行失败: %s' % detail[:500])
    if not stdout:
        raise RuntimeError('Cursor Agent 未返回内容')
    return stdout


def _store_result(run_id: str, payload: dict) -> None:
    with _LOCK:
        _PARSE_RESULTS[run_id] = payload


def get_parse_result(run_id: str) -> dict | None:
    with _LOCK:
        return _PARSE_RESULTS.get(run_id)


def start_parse_async(
    text: str = '',
    image_base64: str = '',
    domain_hint: str = '',
    settings: dict | None = None,
) -> dict:
    parse_cfg = get_dns_parse_config()
    if not parse_cfg.get('enabled', True):
        return {'success': False, 'message': 'DNS AI 识别已在配置文件中禁用'}

    text = (text or '').strip()
    image_base64 = (image_base64 or '').strip()
    if not text and not image_base64:
        return {'success': False, 'message': '请粘贴文本或图片后再识别'}

    run_id = create_run({
        'kind': 'dns_ai_parse',
        'domain_hint': domain_hint or '',
        'has_image': bool(image_base64),
    })

    with _LOCK:
        if getattr(start_parse_async, '_busy', False):
            return {'success': False, 'message': '已有识别任务进行中，请稍候'}
        start_parse_async._busy = True

    def _worker():
        image_path = ''
        try:
            live_cfg = get_dns_parse_config()
            live_key = (live_cfg.get('cursor_api_key') or '').strip()
            _, model_label = resolve_cursor_model(live_cfg)

            append_log(run_id, '[INFO] 状态：识别中\n')
            if live_key:
                append_log(run_id, '[INFO] 认证：API Key\n')
            else:
                append_log(run_id, '[INFO] 认证：本机\n')
            append_log(run_id, '[INFO] 模型：%s\n' % model_label)
            agent_path = _resolve_agent_executable(live_cfg)
            append_log(run_id, '[INFO] Agent：%s\n' % agent_path)

            if image_base64:
                append_log(run_id, '[INFO] 图片：处理中\n')
                image_path = _save_image_temp(image_base64)

            records: list[dict] = []
            if text:
                records = parse_console_table_text(text)
                if records:
                    append_log(run_id, '[INFO] 表格：%d 条\n' % len(records))
                    append_log(run_id, '[INFO] %s\n' % json.dumps(records, ensure_ascii=False))
                    _store_result(run_id, {'records': records, 'source': 'console_table'})
                    finish_log(run_id, True, '本地表格解析成功')
                    logger.info('dns_ai_parse local_table run_id=%s count=%d', run_id, len(records))
                    return

            append_log(run_id, '[INFO] Agent：执行中\n')
            prompt = _build_prompt(text, image_path, domain_hint)
            output = _run_agent(agent_path, prompt, live_key, parse_cfg=live_cfg)
            append_log(run_id, '[INFO] 输出：\n%s\n' % (output[:2000] + ('...' if len(output) > 2000 else '')))

            items = _extract_json_array(output)
            records = _normalize_records(items, text)
            if not records and text:
                records = parse_console_table_text(text)
            append_log(run_id, '[INFO] 记录：%d 条\n' % len(records))
            if records:
                append_log(run_id, '[INFO] %s\n' % json.dumps(records, ensure_ascii=False))

            if not records:
                finish_log(run_id, False, '未能从 Agent 输出解析出 DNS 记录')
                _store_result(run_id, {'records': [], 'message': '未能解析出 DNS 记录'})
                logger.info('dns_ai_parse empty run_id=%s', run_id)
                return

            _store_result(run_id, {'records': records, 'source': 'ai'})
            finish_log(run_id, True, '识别成功')
            append_log(run_id, '[SUCCESS] 记录：%d 条\n' % len(records))
            logger.info('dns_ai_parse success run_id=%s count=%d', run_id, len(records))
        except Exception as exc:
            tb = traceback.format_exc()
            logger.exception('dns_ai_parse failed run_id=%s error=%s', run_id, exc)
            append_log(run_id, '[ERROR] %s\n' % exc)
            append_log(run_id, tb)
            finish_log(run_id, False, str(exc))
            _store_result(run_id, {'records': [], 'message': str(exc)})
        finally:
            if image_path and os.path.isfile(image_path):
                try:
                    os.remove(image_path)
                except OSError:
                    pass
            with _LOCK:
                start_parse_async._busy = False

    threading.Thread(target=_worker, daemon=True).start()
    return {'success': True, 'run_id': run_id, 'data': {'run_id': run_id}}


def poll_parse(run_id: str, since_seq: int = 0, limit: int = 200) -> dict:
    resp = fetch_log(run_id, since_seq=since_seq, limit=limit)
    if not resp.get('success'):
        return resp
    data = resp.get('data') or {}
    if data.get('done'):
        with _LOCK:
            payload = _PARSE_RESULTS.get(run_id) or {}
        records = payload.get('records')
        if records is not None:
            data['records'] = records
        if payload.get('message') and not data.get('message'):
            data['message'] = payload['message']
    return resp
