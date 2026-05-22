"""
DNS 快速解析 / AI 识图配置

配置文件：data/dns_parse_config.json（每次 AI 识别前实时读取）
"""
from __future__ import annotations

import os

from .paths import data_dir
from .storage import _read_json

DNS_PARSE_CONFIG_FILE = os.path.join(data_dir(), 'dns_parse_config.json')

PARSE_MODE_CLI = 'cli'

DEFAULT_DNS_AI_MODEL = 'composer-2-fast'
ACCOUNT_DEFAULT_MODEL_ALIASES = frozenset({'default', 'account', 'auto'})

_DEFAULTS = {
    'cursor_api_key': '',
    'cursor_agent_path': '',
    'proxy_url': '',
    'cursor_model': '',
    'enabled': True,
}


def _write_dns_parse_config(data: dict) -> dict:
    from .storage import _write_json
    _write_json(DNS_PARSE_CONFIG_FILE, data)
    return data


def get_dns_parse_config() -> dict:
    cfg = dict(_DEFAULTS)
    file_cfg = _read_json(DNS_PARSE_CONFIG_FILE, {}) or {}
    if isinstance(file_cfg, dict):
        for key in _DEFAULTS:
            if key in file_cfg:
                cfg[key] = file_cfg[key]

    cfg['cursor_api_key'] = (cfg.get('cursor_api_key') or '').strip()
    cfg['cursor_agent_path'] = (cfg.get('cursor_agent_path') or '').strip()
    cfg['proxy_url'] = (cfg.get('proxy_url') or '').strip()
    cfg['cursor_model'] = (cfg.get('cursor_model') or '').strip()
    cfg['enabled'] = bool(cfg.get('enabled', True))
    return cfg


def resolve_cursor_model(cfg: dict | None = None) -> tuple[str | None, str]:
    cfg = cfg or get_dns_parse_config()
    raw = (cfg.get('cursor_model') or '').strip()
    if not raw:
        return DEFAULT_DNS_AI_MODEL, 'Composer 2 Fast'
    if raw.lower() in ACCOUNT_DEFAULT_MODEL_ALIASES:
        return None, '账号默认'
    return raw, raw


def apply_proxy_to_env(env: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or get_dns_parse_config()
    out = dict(env)
    proxy = (cfg.get('proxy_url') or '').strip()
    if proxy:
        out['HTTP_PROXY'] = proxy
        out['HTTPS_PROXY'] = proxy
        out['GLOBAL_AGENT_HTTP_PROXY'] = proxy
    return out


def get_dns_parse_config_public() -> dict:
    cfg = get_dns_parse_config()
    key = cfg.get('cursor_api_key') or ''
    masked = ''
    if key:
        if len(key) <= 12:
            masked = key[:4] + '***'
        else:
            masked = key[:8] + '...' + key[-4:]
    proxy = cfg.get('proxy_url') or ''
    cli_model, model_label = resolve_cursor_model(cfg)
    return {
        'config_path': DNS_PARSE_CONFIG_FILE,
        'parse_mode': PARSE_MODE_CLI,
        'parse_mode_label': 'CLI',
        'enabled': cfg.get('enabled', True),
        'has_api_key': bool(key),
        'uses_system_account': not bool(key),
        'auth_mode': 'config_key' if key else 'system_account',
        'api_key_masked': masked,
        'cursor_agent_path': cfg.get('cursor_agent_path') or '',
        'proxy_url': proxy,
        'has_proxy': bool(proxy),
        'cursor_model': cfg.get('cursor_model') or '',
        'effective_model': cli_model or '',
        'effective_model_label': model_label,
        'default_model': DEFAULT_DNS_AI_MODEL,
        'model_note': '',
    }


def get_dns_parse_config_edit() -> dict:
    cfg = get_dns_parse_config()
    pub = get_dns_parse_config_public()
    pub['cursor_api_key'] = cfg.get('cursor_api_key') or ''
    return pub


def update_dns_parse_config(updates: dict) -> dict:
    if not isinstance(updates, dict):
        updates = {}
    cfg = get_dns_parse_config()
    if 'cursor_api_key' in updates:
        cfg['cursor_api_key'] = (updates.get('cursor_api_key') or '').strip()
    if 'cursor_agent_path' in updates:
        cfg['cursor_agent_path'] = (updates.get('cursor_agent_path') or '').strip()
    if 'proxy_url' in updates:
        cfg['proxy_url'] = (updates.get('proxy_url') or '').strip()
    if 'cursor_model' in updates:
        cfg['cursor_model'] = (updates.get('cursor_model') or '').strip()
    if 'enabled' in updates:
        cfg['enabled'] = bool(updates.get('enabled'))
    return _write_dns_parse_config(cfg)
