"""
根据域名 NS 记录与已配置服务商的域名列表，推断 DNS 托管厂商。
"""
from __future__ import annotations

import re
import subprocess

from .dns_manager import get_domains, get_provider_status
from .logger import get_logger

logger = get_logger('dns_detect')

_NS_HINTS = (
    ('ali', ('hichina', 'alidns', 'aliyuncs.com', 'alibaba')),
    ('dnspod', ('dnspod', 'dnsv1.com', 'dnsv2.com')),
    ('tencent', ('tencent', 'tencentyun', 'dnspod.net')),
)

_DOMAIN_IN_TEXT = re.compile(
    r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}'
)


def extract_domains_from_prose(text: str) -> list[str]:
    """从说明文字、表格上下文提取候选主域名（长域名优先）。"""
    text = text or ''
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        d = (raw or '').strip().rstrip('.').lower()
        if not d or d in seen:
            return
        if not _DOMAIN_IN_TEXT.fullmatch(d):
            return
        seen.add(d)
        found.append(d)

    for pat in (
        r'请前往域名\s*[「"\'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})',
        r'域名为?\s*[「"\'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})',
        r'域名\s*[「"\'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})',
        r'为域名\s*[「"\'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})',
    ):
        for m in re.finditer(pat, text, re.IGNORECASE):
            _add(m.group(1))

    for m in _DOMAIN_IN_TEXT.finditer(text):
        _add(m.group(0))

    found.sort(key=len, reverse=True)
    return found


def guess_zone_domain_from_fqdn(fqdn: str) -> str:
    """从 FQDN 推断 DNS 托管根域（如 tongxinxuetang.dingdong.work → dingdong.work）。"""
    fqdn = (fqdn or '').strip().rstrip('.').lower()
    parts = [p for p in fqdn.split('.') if p]
    if len(parts) < 2:
        return ''
    return '.'.join(parts[-2:])


def normalize_console_table_record(rec: dict) -> dict:
    """
    「校验域名」列常为待验证的完整主机名，「主机记录」为相对根域的 RR。
    例：校验域名 tongxinxuetang.dingdong.work + RR _dnsauth.tongxinxuetang → 域 dingdong.work
    """
    raw = (rec.get('domain') or '').strip().rstrip('.')
    rr = (rec.get('rr') or '').strip() or '@'
    if not raw:
        return rec
    parts = [p for p in raw.split('.') if p]
    if len(parts) >= 3:
        rec['verify_host'] = raw
        rec['domain'] = '.'.join(parts[-2:])
        if not rr or rr == '@':
            rec['rr'] = '.'.join(parts[:-2]) or '@'
    elif len(parts) == 2:
        rec['domain'] = raw
    return rec


def enrich_records_with_domain_hints(records: list[dict], text: str) -> list[dict]:
    """为缺少 domain 的记录补全主域名（控制台说明 + 子域提及）。"""
    hints = extract_domains_from_prose(text)
    if not hints:
        return records
    low_text = (text or '').lower()
    default = hints[0]
    for rec in records:
        if (rec.get('domain') or '').strip():
            continue
        rr = str(rec.get('rr') or '').strip()
        matched = ''
        for d in hints:
            candidates = []
            if rr and rr != '@':
                candidates.append('%s.%s' % (rr, d))
                if rr.startswith('_dnsauth.'):
                    candidates.append('%s.%s' % (rr, d))
                    sub = rr.split('.', 1)[-1]
                    if sub:
                        candidates.append('%s.%s' % (sub, d))
            for c in candidates:
                if c.lower() in low_text:
                    matched = d
                    break
            if matched:
                break
        rec['domain'] = matched or default
    return records


def lookup_ns_servers(domain: str) -> list[str]:
    domain = (domain or '').strip().rstrip('.')
    if not domain:
        return []
    servers: list[str] = []
    try:
        proc = subprocess.run(
            ['nslookup', '-type=NS', domain],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=12,
        )
        blob = ((proc.stdout or '') + '\n' + (proc.stderr or '')).lower()
        for line in blob.splitlines():
            line = line.strip()
            if not line or line.startswith('server:') or line.startswith('address:'):
                continue
            if 'nameserver' in line or 'name:' in line:
                parts = line.split()
                host = parts[-1].rstrip('.').lower()
                if '.' in host and host not in servers:
                    servers.append(host)
            elif re.match(r'^[a-z0-9][\w.-]+\.[a-z]{2,}$', line):
                if line not in servers:
                    servers.append(line)
    except Exception as exc:
        logger.warning('lookup_ns_servers failed domain=%s error=%s', domain, exc)
    return servers


def guess_provider_from_ns(ns_servers: list[str]) -> str:
    joined = ' '.join(ns_servers).lower()
    for provider, hints in _NS_HINTS:
        if any(h in joined for h in hints):
            return provider
    return ''


def detect_provider_for_domain(domain: str, config: dict) -> dict:
    """推断域名对应的已配置服务商。"""
    domain = (domain or '').strip().rstrip('.')
    if not domain:
        return {
            'domain': '',
            'provider': '',
            'ns_servers': [],
            'ns_guess': '',
            'matched_by': '',
            'candidates': [],
            'message': '域名为空',
        }

    status = get_provider_status(config) or {}
    ns_servers = lookup_ns_servers(domain)
    ns_guess = guess_provider_from_ns(ns_servers)

    order = ['ali', 'dnspod', 'tencent']
    if ns_guess in order:
        order = [ns_guess] + [p for p in order if p != ns_guess]

    candidates: list[dict] = []
    for provider in order:
        if not status.get(provider):
            continue
        try:
            names = {
                str(d.get('DomainName') or '').strip().lower()
                for d in (get_domains(provider, config) or [])
                if d.get('DomainName')
            }
            if domain.lower() in names:
                candidates.append({'provider': provider, 'matched_by': 'domain_list'})
        except Exception as exc:
            logger.info('detect skip provider=%s domain=%s error=%s', provider, domain, exc)

    provider = ''
    matched_by = ''
    if candidates:
        provider = candidates[0]['provider']
        matched_by = candidates[0]['matched_by']
    elif ns_guess and status.get(ns_guess):
        provider = ns_guess
        matched_by = 'ns_guess'

    message = ''
    if not provider:
        message = '未在已配置服务商中找到该域名，请检查密钥档案或手动选择服务商'

    return {
        'domain': domain,
        'provider': provider,
        'ns_servers': ns_servers,
        'ns_guess': ns_guess,
        'matched_by': matched_by,
        'candidates': candidates,
        'message': message,
    }
