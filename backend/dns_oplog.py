"""
DNS 解析记录操作日志
记录所有增删改操作，支持查询
"""
import json
import os
import threading
from datetime import datetime, timezone

from .paths import data_dir

_lock = threading.Lock()


def _log_file() -> str:
    d = os.path.join(data_dir(), 'logs')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'dns_ops.jsonl')


def _max_lines() -> int:
    return 5000


def append_log(action: str, provider: str, domain: str, detail: dict | None = None,
               source: str = 'web', success: bool = True, message: str = '') -> dict:
    entry = {
        'time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'action': action,
        'provider': provider,
        'domain': domain,
        'detail': detail or {},
        'source': source,
        'success': success,
        'message': message,
    }
    with _lock:
        with open(_log_file(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def query_logs(provider: str = '', domain: str = '', action: str = '',
               limit: int = 100, offset: int = 0) -> dict:
    path = _log_file()
    if not os.path.exists(path):
        return {'logs': [], 'total': 0}

    entries = []
    with _lock:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    if provider:
        entries = [e for e in entries if e.get('provider') == provider]
    if domain:
        entries = [e for e in entries if e.get('domain') == domain]
    if action:
        entries = [e for e in entries if e.get('action') == action]

    entries.reverse()
    total = len(entries)
    sliced = entries[offset:offset + limit]

    return {'logs': sliced, 'total': total}
