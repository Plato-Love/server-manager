"""
腾讯云 DNSPod（云 API 3.0 / TC3-HMAC-SHA256）
Endpoint: dnspod.tencentcloudapi.com
Version: 2021-03-23
"""

import hashlib
import hmac
import json
import time


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()


def _tc3_sign(secret_key: str, date: str, service: str, string_to_sign: str) -> str:
    k_date = _hmac_sha256(('TC3' + secret_key).encode('utf-8'), date)
    k_service = hmac.new(k_date, service.encode('utf-8'), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b'tc3_request', hashlib.sha256).digest()
    sig = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    return sig


def _request(action: str, payload: dict, secret_id: str, secret_key: str, version: str = '2021-03-23', timeout: int = 15):
    try:
        import requests
    except ImportError:
        raise Exception('缺少 requests 库，请运行: pip install requests')

    host = 'dnspod.tencentcloudapi.com'
    service = 'dnspod'
    timestamp = int(time.time())
    date = time.strftime('%Y-%m-%d', time.gmtime(timestamp))

    body = json.dumps(payload or {}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    hashed_payload = _sha256_hex(body)

    content_type = 'application/json; charset=utf-8'
    canonical_headers = f'content-type:{content_type}\nhost:{host}\n'
    signed_headers = 'content-type;host'
    canonical_request = f'POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}'
    hashed_canonical_request = _sha256_hex(canonical_request.encode('utf-8'))
    credential_scope = f'{date}/{service}/tc3_request'
    string_to_sign = f'TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'
    signature = _tc3_sign(secret_key, date, service, string_to_sign)

    authorization = (
        f'TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, '
        f'SignedHeaders={signed_headers}, Signature={signature}'
    )

    headers = {
        'Authorization': authorization,
        'Content-Type': content_type,
        'Host': host,
        'X-TC-Action': action,
        'X-TC-Version': version,
        'X-TC-Timestamp': str(timestamp),
    }

    resp = requests.post(f'https://{host}/', data=body, headers=headers, timeout=timeout)
    try:
        data = resp.json()
    except Exception:
        raise Exception(f'腾讯云返回异常: HTTP {resp.status_code} {resp.text[:200]}')

    r = (data or {}).get('Response') or {}
    if 'Error' in r:
        err = r.get('Error') or {}
        raise Exception(f"腾讯云请求失败: {err.get('Code', '')} {err.get('Message', '')}".strip())
    return r


def get_domains(secret_id: str, secret_key: str):
    r = _request('DescribeDomainList', {'Type': 'ALL', 'Offset': 0, 'Limit': 3000}, secret_id, secret_key)
    items = r.get('DomainList') or []
    result = []
    for d in items:
        result.append({'DomainName': d.get('Name', ''), 'DomainId': str(d.get('DomainId', ''))})
    return result


def get_records(domain: str, secret_id: str, secret_key: str, page: int = 1, page_size: int = 100):
    page = max(1, int(page or 1))
    page_size = max(1, min(500, int(page_size or 100)))
    offset = (page - 1) * page_size
    r = _request(
        'DescribeRecordList',
        {'Domain': domain, 'Offset': offset, 'Limit': page_size, 'ErrorOnEmpty': 'no'},
        secret_id,
        secret_key,
    )
    items = r.get('RecordList') or []
    count_info = r.get('RecordCountInfo') or {}
    total_count = int(count_info.get('TotalCount', len(items)) or len(items))
    result = []
    for rec in items:
        result.append({
            'RecordId': str(rec.get('RecordId', '')),
            'RR': rec.get('Name', ''),
            'Type': rec.get('Type', ''),
            'Value': rec.get('Value', ''),
            'TTL': int(rec.get('TTL', 600) or 600),
            'Line': rec.get('Line', '默认'),
            'DomainName': domain,
            'Status': rec.get('Status', ''),
            'MX': rec.get('MX', 0),
        })
    return {
        'records': result,
        'total': total_count,
        'page': page,
        'page_size': page_size,
    }


def create_record(domain: str, rr: str, rtype: str, value: str, ttl: int, line: str, mx: int | None,
                  secret_id: str, secret_key: str):
    payload = {
        'Domain': domain,
        'SubDomain': rr or '@',
        'RecordType': rtype,
        'RecordLine': line or '默认',
        'Value': value,
        'TTL': int(ttl or 600),
    }
    if mx is not None:
        payload['MX'] = int(mx)
    r = _request('CreateRecord', payload, secret_id, secret_key)
    return {'success': True, 'recordId': str(r.get('RecordId', ''))}


def modify_record(domain: str, record_id: str, rr: str, rtype: str, value: str, ttl: int, line: str, mx: int | None,
                  secret_id: str, secret_key: str):
    payload = {
        'Domain': domain,
        'RecordId': int(record_id),
        'SubDomain': rr or '@',
        'RecordType': rtype,
        'RecordLine': line or '默认',
        'Value': value,
        'TTL': int(ttl or 600),
    }
    if mx is not None:
        payload['MX'] = int(mx)
    _request('ModifyRecord', payload, secret_id, secret_key)
    return {'success': True}


def delete_record(domain: str, record_id: str, secret_id: str, secret_key: str):
    payload = {'Domain': domain, 'RecordId': int(record_id)}
    _request('DeleteRecord', payload, secret_id, secret_key)
    return {'success': True}

