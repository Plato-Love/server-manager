"""
服务器管家 - DNS 解析管理模块
支持：阿里云、DNSPod（dnsapi.cn / ID+Token）、腾讯云（云 API / SecretId+SecretKey）
开发阶段：不做历史字段兼容与迁移
"""
import hmac
import hashlib
import base64
import uuid
import json
import urllib.parse
from datetime import datetime, timezone
from .logger import get_logger
from . import tencent_dns

logger = get_logger('dns')

def _select_profile(profiles, active_id):
    profiles = profiles or []
    active_id = (active_id or '').strip()
    if not active_id:
        return {}
    for p in profiles:
        if isinstance(p, dict) and str(p.get('id', '')).strip() == active_id:
            return p
    return {}


def _normalize_line(line: str) -> str:
    v = (line or '').strip()
    if not v or v.lower() == 'default':
        return '默认'
    return v


def _http_request(url, method='GET', headers=None, body=None, timeout=15):
    """通用 HTTP 请求 - 使用 requests 库"""
    try:
        import requests
        
        headers = headers or {}
        if body is not None and isinstance(body, dict):
            body = json.dumps(body)
        
        resp = requests.request(method, url, headers=headers, data=body, timeout=timeout)
        
        if resp.status_code >= 400:
            try:
                return resp.json()
            except Exception:
                raise Exception(f'HTTP {resp.status_code}: {resp.text[:200]}')
        
        return resp.json()
    except ImportError:
        raise Exception('缺少 requests 库，请运行: pip install requests')
    except Exception as e:
        if 'requests' in str(e).lower():
            raise
        raise Exception(f'请求失败: {str(e)}')


# ==================== 阿里云 DNS ====================

def _ali_percent_encode(s):
    """RFC3986 编码（阿里云签名专用）"""
    s = urllib.parse.quote(str(s), safe='')
    s = s.replace('!', '%21').replace("'", '%27').replace('(', '%28')
    s = s.replace(')', '%29').replace('*', '%2A').replace('%7E', '~')
    return s


def _ali_sign(params, ak_secret):
    """阿里云 HMAC-SHA1 签名"""
    sorted_params = sorted(params.items())
    query = '&'.join(f'{_ali_percent_encode(k)}={_ali_percent_encode(v)}' for k, v in sorted_params)
    str_to_sign = f'GET&{_ali_percent_encode("/")}&{_ali_percent_encode(query)}'
    signature = hmac.new((ak_secret + '&').encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha1).digest()
    return base64.b64encode(signature).decode('utf-8')


def _ali_request(action, biz_params, config):
    """阿里云 API 请求"""
    p = _select_profile(config.get('ali_profiles') or [], config.get('ali_active_profile'))
    ak_id = (p.get('access_key_id') or '').strip()
    ak_secret = (p.get('access_key_secret') or '').strip()
    if not ak_id or not ak_secret:
        raise Exception('阿里云密钥未配置，请先添加密钥档案')

    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    params = {
        'Action': action,
        'Version': '2015-01-09',
        'Format': 'JSON',
        'AccessKeyId': ak_id,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureVersion': '1.0',
        'SignatureNonce': str(uuid.uuid4()),
        'Timestamp': ts,
        **biz_params,
    }
    params['Signature'] = _ali_sign(params, ak_secret)
    qs = '&'.join(f'{urllib.parse.quote(k)}={urllib.parse.quote(v)}' for k, v in sorted(params.items()))
    data = _http_request(f'https://alidns.aliyuncs.com/?{qs}')
    if 'Code' in data:
        raise Exception(data.get('Message', f"阿里云错误: {data['Code']}"))
    return data


def ali_get_domains(config):
    data = _ali_request('DescribeDomains', {'PageNumber': '1', 'PageSize': '100'}, config)
    domains = (data.get('Domains') or {}).get('Domain') or []
    return [{'DomainName': d['DomainName'], 'DomainId': d['DomainId']} for d in domains]


def ali_get_records(domain, config, page=1, page_size=100):
    page = max(1, int(page or 1))
    page_size = max(1, min(500, int(page_size or 100)))
    data = _ali_request(
        'DescribeDomainRecords',
        {'DomainName': domain, 'PageNumber': str(page), 'PageSize': str(page_size)},
        config
    )
    records = (data.get('DomainRecords') or {}).get('Record') or []
    result = [{
        'RecordId': r['RecordId'],
        'RR': r['RR'],
        'Type': r['Type'],
        'Value': r['Value'],
        'TTL': r.get('TTL', 600),
        'Line': r.get('Line', 'default'),
        'DomainName': domain,
        'Status': r.get('Status', ''),
    } for r in records]
    total = int(data.get('TotalCount', len(result)) or len(result))
    return {
        'records': result,
        'total': total,
        'page': page,
        'page_size': page_size,
    }


def ali_add_record(domain, rr, rtype, value, ttl=600, line='default', config=None, **kwargs):
    params = {
        'DomainName': domain, 'RR': rr, 'Type': rtype,
        'Value': value, 'TTL': str(ttl), 'Line': line
    }
    # MX 优先级
    if rtype == 'MX' and 'mx_priority' in kwargs:
        params['Priority'] = str(kwargs['mx_priority'])
    # SRV: value 格式为 "优先级 权重 端口 目标"
    if rtype == 'SRV':
        srv = f"{kwargs.get('srv_priority', 10)} {kwargs.get('srv_weight', 5)} {kwargs.get('srv_port', 443)} {value}"
        params['Value'] = srv
    # CAA: value 格式为 "flags tag value"
    if rtype == 'CAA':
        params['Value'] = f"{kwargs.get('caa_flags', 0)} {kwargs.get('caa_tag', 'issue')} {value}"
    data = _ali_request('AddDomainRecord', params, config)
    return {'success': True, 'recordId': data.get('RecordId')}


def ali_delete_record(record_id, config):
    _ali_request('DeleteDomainRecord', {'RecordId': str(record_id)}, config)
    return {'success': True}


def ali_update_record(record_id, rr, rtype, value, ttl=600, line='default', config=None, **kwargs):
    params = {
        'RecordId': str(record_id), 'RR': rr, 'Type': rtype,
        'Value': value, 'TTL': str(ttl), 'Line': line
    }
    if rtype == 'MX' and 'mx_priority' in kwargs:
        params['Priority'] = str(kwargs['mx_priority'])
    if rtype == 'SRV':
        srv = f"{kwargs.get('srv_priority', 10)} {kwargs.get('srv_weight', 5)} {kwargs.get('srv_port', 443)} {value}"
        params['Value'] = srv
    if rtype == 'CAA':
        params['Value'] = f"{kwargs.get('caa_flags', 0)} {kwargs.get('caa_tag', 'issue')} {value}"
    _ali_request('UpdateDomainRecord', params, config)
    return {'success': True}


# ==================== DNSPod（ID + Token） ====================

def _tx_get_credentials(config):
    """获取 DNSPod 凭据（兼容旧字段）"""
    p = _select_profile(config.get('dnspod_profiles') or [], config.get('dnspod_active_profile'))
    sid = (p.get('dnspod_id') or '').strip()
    stoken = (p.get('dnspod_token') or '').strip()
    if not sid or not stoken:
        raise Exception('DNSPod 凭据未配置，请先添加密钥档案')
    return sid, stoken


def _tx_request(action, params, config):
    """DNSPod API 请求（https://dnsapi.cn）"""
    sid, stoken = _tx_get_credentials(config)
    payload = {
        'login_token': f'{sid},{stoken}',
        'format': 'json',
        'lang': 'cn',
    }
    payload.update(params or {})

    try:
        import requests
    except ImportError:
        raise Exception('缺少 requests 库，请运行: pip install requests')

    resp = requests.post(
        f'https://dnsapi.cn/{action}',
        data=payload,
        headers={'User-Agent': 'server-manager/1.0'},
        timeout=15
    )
    try:
        data = resp.json()
    except Exception:
        raise Exception(f'DNSPod 返回异常: HTTP {resp.status_code} {resp.text[:200]}')

    status = data.get('status') or {}
    code = str(status.get('code', ''))
    if code != '1':
        raise Exception(status.get('message', f'DNSPod 请求失败: {action}'))
    return data


def tx_get_domains(config):
    data = _tx_request('Domain.List', {'type': 'all', 'offset': 0, 'length': 3000}, config)
    domains = data.get('domains') or []
    return [{'DomainName': d.get('name', ''), 'DomainId': str(d.get('id', ''))} for d in domains]


def tx_get_records(domain, config, page=1, page_size=100):
    page = max(1, int(page or 1))
    page_size = max(1, min(3000, int(page_size or 100)))
    offset = (page - 1) * page_size
    data = _tx_request('Record.List', {'domain': domain, 'offset': offset, 'length': page_size}, config)
    records = data.get('records') or []
    result = [{
        'RecordId': str(r.get('id', '')),
        'RR': r.get('name', ''),
        'Type': r.get('type', ''),
        'Value': r.get('value', ''),
        'TTL': int(r.get('ttl', 600)),
        'Line': r.get('line', '默认'),
        'DomainName': domain,
        'Status': r.get('enabled', '1'),
    } for r in records]
    info = data.get('info') or {}
    try:
        total = int(info.get('record_total', len(result)) or len(result))
    except Exception:
        total = len(result)
    return {
        'records': result,
        'total': total,
        'page': page,
        'page_size': page_size,
    }


def tx_add_record(domain, sub_domain, record_type, value, ttl=600, record_line='默认', config=None, **kwargs):
    record_line = _normalize_line(record_line)
    final_value = value
    if record_type == 'SRV':
        final_value = f"{kwargs.get('srv_priority', 10)} {kwargs.get('srv_weight', 5)} {kwargs.get('srv_port', 443)} {value}"
    if record_type == 'CAA':
        final_value = f"{kwargs.get('caa_flags', 0)} {kwargs.get('caa_tag', 'issue')} {value}"

    params = {
        'domain': domain,
        'sub_domain': sub_domain,
        'record_type': record_type,
        'record_line': record_line or '默认',
        'value': final_value,
        'ttl': int(ttl),
    }
    if record_type == 'MX' and 'mx_priority' in kwargs:
        params['mx'] = int(kwargs['mx_priority'])

    data = _tx_request('Record.Create', params, config)
    return {'success': True, 'recordId': str((data.get('record') or {}).get('id', ''))}


def tx_delete_record(domain, record_id, config):
    _tx_request('Record.Remove', {'domain': domain, 'record_id': str(record_id)}, config)
    return {'success': True}


def tx_update_record(domain, record_id, sub_domain, record_type, value, ttl=600, record_line='默认', config=None, **kwargs):
    record_line = _normalize_line(record_line)
    final_value = value
    if record_type == 'SRV':
        final_value = f"{kwargs.get('srv_priority', 10)} {kwargs.get('srv_weight', 5)} {kwargs.get('srv_port', 443)} {value}"
    if record_type == 'CAA':
        final_value = f"{kwargs.get('caa_flags', 0)} {kwargs.get('caa_tag', 'issue')} {value}"

    params = {
        'domain': domain,
        'record_id': str(record_id),
        'sub_domain': sub_domain,
        'record_type': record_type,
        'record_line': record_line or '默认',
        'value': final_value,
        'ttl': int(ttl),
    }
    if record_type == 'MX' and 'mx_priority' in kwargs:
        params['mx'] = int(kwargs['mx_priority'])

    _tx_request('Record.Modify', params, config)
    return {'success': True}


# ==================== Cloudflare ====================

def _cf_request(path, method='GET', body=None, config=None):
    """Cloudflare API 请求"""
    token = (config.get('cf_api_token', '') or '').strip()
    if not token:
        raise Exception('Cloudflare Token 未配置，请在设置中填写')
    token = token.strip('"').strip("'")
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    # 容忍误粘贴的换行/空白字符
    token = ''.join(token.split())
    # 去除常见不可见字符（零宽空格、BOM）
    token = token.replace('\ufeff', '').replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
    cf_account_id = (config.get('cf_account_id', '') or '').strip()
    # 兼容“把邮箱填在 ID 字段”的情况（部分面板将 Email 显示为 ID）
    cf_email = cf_account_id if ('@' in cf_account_id) else ''

    base_headers = {
        'Authorization': f'Bearer {token}',
    }
    legacy_headers = None
    if cf_email:
        legacy_headers = {
            'X-Auth-Email': cf_email,
            'X-Auth-Key': token,
        }

    headers = dict(base_headers)
    # Cloudflare 对 GET 请求附带 Content-Type 较敏感，可能返回 Invalid request headers
    if method.upper() != 'GET':
        headers['Content-Type'] = 'application/json'

    def _do_request(req_headers):
        return _http_request(
            f'https://api.cloudflare.com/client/v4{path}',
            method=method,
            headers=req_headers,
            body=body
        )

    data = _do_request(headers)
    if data.get('success') or not data.get('errors'):
        return data

    msg = data['errors'][0].get('message', 'Cloudflare API 错误')
    err_code = str(data['errors'][0].get('code', ''))
    # Bearer 失败且提供了邮箱时，自动回退 Global Key 模式
    should_fallback = legacy_headers is not None
    if should_fallback:
        logger.warning('cloudflare auth fallback to X-Auth-Key mode: %s (code=%s)', msg, err_code)
        fallback_headers = dict(legacy_headers)
        if method.upper() != 'GET':
            fallback_headers['Content-Type'] = 'application/json'
        data2 = _do_request(fallback_headers)
        if data2.get('success') or not data2.get('errors'):
            return data2
        msg2 = data2['errors'][0].get('message', 'Cloudflare API 错误')
        code2 = data2['errors'][0].get('code', '')
        raise Exception(f'Cloudflare 鉴权失败（Bearer 与 Global Key 均失败）: [{code2}] {msg2}')

    if 'Invalid request headers' in msg:
        raise Exception('Cloudflare 鉴权头无效，请检查 ID/Token 是否正确，Token 建议使用 API Token（Zone.DNS.Edit + Zone.Zone.Read）')
    raise Exception(f'[{err_code}] {msg}')


def _cf_record_name(rr, domain):
    rr = (rr or '').strip()
    domain = (domain or '').strip()
    if not domain:
        return rr
    if rr in ('', '@'):
        return domain
    if rr == domain or rr.endswith('.' + domain):
        return rr
    return f'{rr}.{domain}'


def cf_get_domains(config):
    account_id = (config.get('cf_account_id', '') or '').strip()
    # 如果 ID 字段实际是邮箱，不作为 account.id 过滤参数
    if account_id and '@' in account_id:
        account_id = ''
    query = '/zones?per_page=50'
    if account_id:
        query += '&account.id=' + urllib.parse.quote(account_id, safe='')
    try:
        data = _cf_request(query, config=config)
    except Exception as exc:
        # 部分账号配置的 account_id 非 zone 过滤所需格式，自动回退为不带过滤查询
        if account_id:
            logger.warning('cf_get_domains fallback without account filter: %s', exc)
            data = _cf_request('/zones?per_page=50', config=config)
        else:
            raise
    zones = data.get('result') or []
    return [{'DomainName': z['name'], 'DomainId': z['id']} for z in zones]


def cf_get_records(zone_id, config):
    if not zone_id:
        raise Exception('Cloudflare zone_id 不能为空')
    data = _cf_request(f'/zones/{zone_id}/dns_records?per_page=100', config=config)
    records = data.get('result') or []
    result = []
    for r in records:
        # 从完整域名中提取子域名
        full_name = r.get('name', '')
        zone_name = r.get('zone_name', '')
        rr = full_name
        if zone_name and full_name.endswith('.' + zone_name):
            rr = full_name[:-(len(zone_name) + 1)]
        elif zone_name and full_name == zone_name:
            rr = '@'
        result.append({
            'RecordId': r['id'],
            'RR': rr,
            'Type': r['type'],
            'Value': r['content'],
            'TTL': r.get('ttl', 1),
            'Line': 'proxied' if r.get('proxied') else 'dns_only',
            'DomainName': zone_name,
            'Proxied': r.get('proxied', False),
        })
    return result


def cf_add_record(zone_id, domain, rtype, name, content, ttl=1, proxied=False, config=None):
    if not zone_id:
        raise Exception('Cloudflare zone_id 不能为空')
    normalized_name = _cf_record_name(name, domain)
    data = _cf_request(f'/zones/{zone_id}/dns_records', method='POST',
                       body={'type': rtype, 'name': normalized_name, 'content': content, 'ttl': ttl, 'proxied': proxied},
                       config=config)
    if not data.get('success'):
        errors = data.get('errors', [])
        raise Exception(errors[0].get('message', 'Cloudflare 添加失败') if errors else 'Cloudflare 添加失败')
    return {'success': True, 'recordId': data.get('result', {}).get('id')}


def cf_delete_record(zone_id, record_id, config):
    data = _cf_request(f'/zones/{zone_id}/dns_records/{record_id}', method='DELETE', config=config)
    if not data.get('success'):
        errors = data.get('errors', [])
        raise Exception(errors[0].get('message', 'Cloudflare 删除失败') if errors else 'Cloudflare 删除失败')
    return {'success': True}


def cf_update_record(zone_id, record_id, domain, rtype, name, content, ttl=1, proxied=False, config=None):
    if not zone_id:
        raise Exception('Cloudflare zone_id 不能为空')
    normalized_name = _cf_record_name(name, domain)
    data = _cf_request(f'/zones/{zone_id}/dns_records/{record_id}', method='PUT',
                body={'type': rtype, 'name': normalized_name, 'content': content, 'ttl': ttl, 'proxied': proxied},
                config=config)
    if not data.get('success'):
        errors = data.get('errors', [])
        raise Exception(errors[0].get('message', 'Cloudflare 修改失败') if errors else 'Cloudflare 修改失败')
    return {'success': True}


# ==================== 统一接口 ====================

def get_provider_status(config):
    """获取各厂商配置状态"""
    ali_ok = bool(_select_profile(config.get('ali_profiles') or [], config.get('ali_active_profile')))
    dnspod_ok = bool(_select_profile(config.get('dnspod_profiles') or [], config.get('dnspod_active_profile')))
    tencent_ok = bool(_select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile')))
    return {
        'ali': ali_ok,
        'dnspod': dnspod_ok,
        'tencent': tencent_ok,
    }


def get_domains(provider, config):
    """获取域名列表（统一接口）"""
    if provider == 'ali':
        return ali_get_domains(config)
    elif provider == 'dnspod':
        return tx_get_domains(config)
    elif provider == 'tencent':
        p = _select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile'))
        sid = (p.get('secret_id') or '').strip()
        skey = (p.get('secret_key') or '').strip()
        if not sid or not skey:
            raise Exception('腾讯云密钥未配置，请先添加密钥档案')
        return tencent_dns.get_domains(sid, skey)
    raise Exception(f'不支持的厂商: {provider}')


def get_records(provider, domain, config, zone_id=None):
    """获取解析记录（统一接口）"""
    page_result = get_records_page(provider, domain, config, zone_id=zone_id, page=1, page_size=3000)
    return page_result.get('records') or []


def get_records_page(provider, domain, config, zone_id=None, page=1, page_size=100):
    """获取解析记录分页（统一接口）"""
    if provider == 'ali':
        return ali_get_records(domain, config, page=page, page_size=page_size)
    elif provider == 'dnspod':
        return tx_get_records(domain, config, page=page, page_size=page_size)
    elif provider == 'tencent':
        p = _select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile'))
        sid = (p.get('secret_id') or '').strip()
        skey = (p.get('secret_key') or '').strip()
        if not sid or not skey:
            raise Exception('腾讯云密钥未配置，请先添加密钥档案')
        return tencent_dns.get_records(domain, sid, skey, page=page, page_size=page_size)
    raise Exception(f'不支持的厂商: {provider}')


def add_record(provider, config, **kwargs):
    """添加记录（统一接口），带重复检查"""
    extra = {}
    for key in ('mx_priority', 'srv_priority', 'srv_weight', 'srv_port', 'caa_flags', 'caa_tag'):
        if key in kwargs:
            extra[key] = kwargs[key]

    # 参数验证
    rr = kwargs.get('rr', '')
    rtype = kwargs.get('type', '')
    value = kwargs.get('value', '')
    if not rr or not value or not rtype:
        raise Exception('主机记录、记录值和类型不能为空')

    # 重复检查
    domain = kwargs.get('domain', '')
    zone_id = kwargs.get('zone_id', '')
    existing = get_records(provider, domain, config, zone_id=zone_id)
    for rec in existing:
        if rec.get('Type', '').upper() == rtype.upper() and rec.get('RR', '') == rr:
            raise Exception(f'记录已存在：{rtype} {rr} -> {rec.get("Value", "")}')

    # 调用厂商 API
    if provider == 'ali':
        return ali_add_record(
            kwargs['domain'], kwargs['rr'], kwargs['type'], kwargs['value'],
            kwargs.get('ttl', 600), kwargs.get('line', 'default'), config, **extra
        )
    elif provider == 'dnspod':
        return tx_add_record(
            kwargs['domain'], kwargs['rr'], kwargs['type'], kwargs['value'],
            kwargs.get('ttl', 600), _normalize_line(kwargs.get('line', '默认')), config, **extra
        )
    elif provider == 'tencent':
        p = _select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile'))
        sid = (p.get('secret_id') or '').strip()
        skey = (p.get('secret_key') or '').strip()
        if not sid or not skey:
            raise Exception('腾讯云密钥未配置，请先添加密钥档案')
        mx = extra.get('mx_priority') if kwargs.get('type') == 'MX' else None
        val = kwargs['value']
        if kwargs.get('type') == 'SRV':
            val = f"{extra.get('srv_priority', 10)} {extra.get('srv_weight', 5)} {extra.get('srv_port', 443)} {val}"
        if kwargs.get('type') == 'CAA':
            val = f"{extra.get('caa_flags', 0)} {extra.get('caa_tag', 'issue')} {val}"
        return tencent_dns.create_record(
            kwargs['domain'], kwargs['rr'], kwargs['type'], val,
            kwargs.get('ttl', 600), _normalize_line(kwargs.get('line', '默认')), mx,
            sid, skey
        )
    raise Exception(f'不支持的厂商: {provider}')


def delete_record(provider, config, **kwargs):
    """删除记录（统一接口）"""
    if provider == 'ali':
        return ali_delete_record(kwargs['record_id'], config)
    elif provider == 'dnspod':
        return tx_delete_record(kwargs['domain'], kwargs['record_id'], config)
    elif provider == 'tencent':
        p = _select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile'))
        sid = (p.get('secret_id') or '').strip()
        skey = (p.get('secret_key') or '').strip()
        if not sid or not skey:
            raise Exception('腾讯云密钥未配置，请先添加密钥档案')
        return tencent_dns.delete_record(kwargs['domain'], kwargs['record_id'], sid, skey)
    raise Exception(f'不支持的厂商: {provider}')


def update_record(provider, config, **kwargs):
    """修改记录（统一接口）"""
    extra = {}
    for key in ('mx_priority', 'srv_priority', 'srv_weight', 'srv_port', 'caa_flags', 'caa_tag'):
        if key in kwargs:
            extra[key] = kwargs[key]

    if provider == 'ali':
        return ali_update_record(
            kwargs['record_id'], kwargs['rr'], kwargs['type'], kwargs['value'],
            kwargs.get('ttl', 600), kwargs.get('line', 'default'), config, **extra
        )
    elif provider == 'dnspod':
        return tx_update_record(
            kwargs['domain'], kwargs['record_id'], kwargs['rr'], kwargs['type'], kwargs['value'],
            kwargs.get('ttl', 600), _normalize_line(kwargs.get('line', '默认')), config, **extra
        )
    elif provider == 'tencent':
        p = _select_profile(config.get('tencent_profiles') or [], config.get('tencent_active_profile'))
        sid = (p.get('secret_id') or '').strip()
        skey = (p.get('secret_key') or '').strip()
        if not sid or not skey:
            raise Exception('腾讯云密钥未配置，请先添加密钥档案')
        mx = extra.get('mx_priority') if kwargs.get('type') == 'MX' else None
        val = kwargs['value']
        if kwargs.get('type') == 'SRV':
            val = f"{extra.get('srv_priority', 10)} {extra.get('srv_weight', 5)} {extra.get('srv_port', 443)} {val}"
        if kwargs.get('type') == 'CAA':
            val = f"{extra.get('caa_flags', 0)} {extra.get('caa_tag', 'issue')} {val}"
        return tencent_dns.modify_record(
            kwargs['domain'], kwargs['record_id'], kwargs['rr'], kwargs['type'], val,
            kwargs.get('ttl', 600), _normalize_line(kwargs.get('line', '默认')), mx,
            sid, skey
        )
    raise Exception(f'不支持的厂商: {provider}')
