"""
DNS 导入 / 解析全量操作日志（持久化 JSONL）

记录解析、校验、导入全流程，便于排查问题。
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from .paths import data_dir

_lock = threading.Lock()
_MAX_DETAIL_TEXT = 4000
_MAX_RECORDS_IN_DETAIL = 200


def log_file_path() -> str:
    d = os.path.join(data_dir(), 'logs')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'dns_import.jsonl')


def new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def _truncate_text(value: Any, limit: int = _MAX_DETAIL_TEXT) -> str:
    s = str(value or '')
    if len(s) <= limit:
        return s
    return s[:limit] + '...(truncated)'


def _sanitize_detail(detail: dict | None) -> dict:
    if not detail:
        return {}
    out: dict[str, Any] = {}
    for k, v in detail.items():
        key = str(k)
        if key in ('image_base64', 'image', 'screenshot'):
            out[key] = '<omitted>'
            continue
        if key == 'text' or key == 'raw_text':
            out[key] = _truncate_text(v)
            continue
        if key == 'records' and isinstance(v, list):
            rows = v[:_MAX_RECORDS_IN_DETAIL]
            out[key] = rows
            if len(v) > len(rows):
                out['records_truncated'] = len(v) - len(rows)
            continue
        if isinstance(v, (dict, list)):
            try:
                encoded = json.dumps(v, ensure_ascii=False)
                if len(encoded) > _MAX_DETAIL_TEXT:
                    out[key] = _truncate_text(encoded)
                else:
                    out[key] = v
            except (TypeError, ValueError):
                out[key] = _truncate_text(v)
            continue
        out[key] = v
    return out


def append_import_log(
    phase: str,
    message: str = '',
    detail: dict | None = None,
    *,
    session_id: str = '',
    source: str = 'web',
    success: bool = True,
) -> dict:
    entry = {
        'time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'session_id': (session_id or '').strip() or 'unknown',
        'phase': (phase or 'info').strip(),
        'message': _truncate_text(message, 2000),
        'detail': _sanitize_detail(detail),
        'source': source,
        'success': bool(success),
    }
    path = log_file_path()
    with _lock:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def query_import_logs(
    session_id: str = '',
    phase: str = '',
    limit: int = 100,
    offset: int = 0,
) -> dict:
    path = log_file_path()
    if not os.path.exists(path):
        return {'logs': [], 'total': 0, 'path': path}

    entries: list[dict] = []
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

    if session_id:
        entries = [e for e in entries if e.get('session_id') == session_id]
    if phase:
        entries = [e for e in entries if e.get('phase') == phase]

    entries.reverse()
    total = len(entries)
    sliced = entries[offset: offset + limit]
    return {'logs': sliced, 'total': total, 'path': path}


def log_info() -> dict:
    path = log_file_path()
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {
        'path': path,
        'relative': os.path.relpath(path, data_dir()).replace('\\', '/'),
        'data_dir': data_dir(),
        'size_bytes': size,
        'exists': os.path.exists(path),
    }
