"""
DNS 解析管理 - 网页版
Flask 后端，复用 backend/ 模块
密钥只在服务端 data/ 目录配置，前端不提供任何密钥管理功能
AI 解析使用 SiliconFlow API（兼容 OpenAI 格式），不依赖本地 Cursor CLI
"""
import copy
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, request, send_from_directory
from backend.storage import get_settings, update_settings
from backend.dns_manager import (
    get_provider_status, get_domains, get_records, get_records_page,
    add_record, delete_record, update_record
)
from backend.dns_detect import detect_provider_for_domain
from backend.dns_ai_parse import start_parse_async, poll_parse
from backend.dns_parse_config import (
    get_dns_parse_config_public,
    update_dns_parse_config,
)
from backend.dns_oplog import append_log, query_logs
from backend.dns_import_log import (
    append_import_log,
    query_import_logs,
    log_info as import_log_info,
    new_session_id,
)
from backend.logger import get_logger

logger = get_logger('web_app')
app = Flask(__name__, static_folder='web_frontend', static_url_path='')

_SECRET_KEYWORDS = ('secret', 'token', 'key', 'password', 'access_key')
_MASK_PLACEHOLDER = '****'


def _get_dns_config():
    return get_settings()


def _mask_value(v):
    if not v or not isinstance(v, str):
        return _MASK_PLACEHOLDER if v else ''
    if len(v) <= 8:
        return v[:2] + '****'
    return v[:4] + '****' + v[-2:]


def _is_secret_key(k):
    kl = k.lower()
    return any(s in kl for s in _SECRET_KEYWORDS)


def _mask_profiles(settings):
    out = copy.deepcopy(settings)
    for profiles_key in ('ali_profiles', 'dnspod_profiles', 'tencent_profiles'):
        profiles = out.get(profiles_key) or []
        for p in profiles:
            for k in list(p.keys()):
                if _is_secret_key(k):
                    p[k] = _mask_value(p[k])
    return out


def _ok(data=None, message=''):
    resp = {'success': True}
    if data is not None:
        resp['data'] = data
    if message:
        resp['message'] = message
    return jsonify(resp)


def _fail(message, code=400):
    return jsonify({'success': False, 'message': str(message)}), code


# ==================== 页面 ====================

@app.route('/')
def index():
    return send_from_directory('web_frontend', 'index.html')


# ==================== DNS API ====================

@app.route('/api/dns/providers', methods=['GET'])
def dns_get_providers():
    config = _get_dns_config()
    status = get_provider_status(config)
    return _ok(status)


@app.route('/api/dns/domains/<provider>', methods=['GET'])
def dns_get_domains(provider):
    try:
        config = _get_dns_config()
        domains = get_domains(provider, config)
        return _ok(domains)
    except Exception as e:
        return _fail(str(e))


@app.route('/api/dns/records/<provider>', methods=['GET'])
def dns_get_records(provider):
    domain = request.args.get('domain', '')
    zone_id = request.args.get('zone_id', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    if not domain:
        return _fail('缺少 domain 参数')
    try:
        config = _get_dns_config()
        page_data = get_records_page(
            provider, domain, config,
            zone_id=zone_id, page=page, page_size=page_size
        )
        records = page_data.get('records') or []
        total = int(page_data.get('total', len(records)) or len(records))
        page_no = int(page_data.get('page', page) or 1)
        page_sz = int(page_data.get('page_size', page_size) or 50)
        return _ok({
            'records': records,
            'pagination': {
                'page': page_no,
                'page_size': page_sz,
                'total': total,
                'total_pages': max(1, (total + page_sz - 1) // page_sz),
            }
        })
    except Exception as e:
        return _fail(str(e))


@app.route('/api/dns/records/<provider>', methods=['POST'])
def dns_add_record(provider):
    params = request.get_json(silent=True) or {}
    required = ['type', 'rr', 'value']
    for key in required:
        if not params.get(key):
            return _fail(f'缺少必要参数: {key}')
    domain = params.get('domain', '')
    try:
        config = _get_dns_config()
        result = add_record(provider, config, **params)
        append_log('add', provider, domain,
                   detail={'type': params.get('type'), 'rr': params.get('rr'), 'value': params.get('value')},
                   source='web', success=True, message='添加记录')
        session_id = (params.get('session_id') or '').strip()
        if session_id:
            append_import_log(
                'import_item',
                '添加记录成功',
                {
                    'provider': provider,
                    'domain': domain,
                    'type': params.get('type'),
                    'rr': params.get('rr'),
                    'value': params.get('value'),
                    'ttl': params.get('ttl'),
                    'result': result,
                },
                session_id=session_id,
                success=True,
            )
        return _ok(result)
    except Exception as e:
        append_log('add', provider, domain,
                   detail={'type': params.get('type'), 'rr': params.get('rr'), 'value': params.get('value')},
                   source='web', success=False, message=str(e))
        session_id = (params.get('session_id') or '').strip()
        if session_id:
            append_import_log(
                'import_item',
                '添加记录失败',
                {
                    'provider': provider,
                    'domain': domain,
                    'type': params.get('type'),
                    'rr': params.get('rr'),
                    'value': params.get('value'),
                    'error': str(e),
                },
                session_id=session_id,
                success=False,
            )
        return _fail(str(e))


@app.route('/api/dns/records/<provider>', methods=['PUT'])
def dns_update_record(provider):
    params = request.get_json(silent=True) or {}
    required = ['type', 'rr', 'value', 'record_id']
    for key in required:
        if not params.get(key):
            return _fail(f'缺少必要参数: {key}')
    domain = params.get('domain', '')
    try:
        config = _get_dns_config()
        result = update_record(provider, config, **params)
        append_log('update', provider, domain,
                   detail={'record_id': params.get('record_id'), 'type': params.get('type'),
                           'rr': params.get('rr'), 'value': params.get('value')},
                   source='web', success=True, message='修改记录')
        return _ok(result)
    except Exception as e:
        append_log('update', provider, domain,
                   detail={'record_id': params.get('record_id'), 'type': params.get('type'),
                           'rr': params.get('rr'), 'value': params.get('value')},
                   source='web', success=False, message=str(e))
        return _fail(str(e))


@app.route('/api/dns/records/<provider>', methods=['DELETE'])
def dns_delete_record(provider):
    params = request.get_json(silent=True) or {}
    if not params.get('record_id'):
        return _fail('缺少必要参数: record_id')
    domain = params.get('domain', '')
    try:
        config = _get_dns_config()
        result = delete_record(provider, config, **params)
        append_log('delete', provider, domain,
                   detail={'record_id': params.get('record_id')},
                   source='web', success=True, message='删除记录')
        return _ok(result)
    except Exception as e:
        append_log('delete', provider, domain,
                   detail={'record_id': params.get('record_id')},
                   source='web', success=False, message=str(e))
        return _fail(str(e))


@app.route('/api/dns/detect', methods=['GET'])
def dns_detect():
    domain = request.args.get('domain', '')
    if not domain:
        return _fail('缺少 domain 参数')
    try:
        config = _get_dns_config()
        data = detect_provider_for_domain(domain, config)
        return _ok(data)
    except Exception as e:
        return _fail(str(e))


def _normalize_rr_for_compare(rr: str, domain: str) -> str:
    rr = (rr or '').strip()
    if not rr or rr == '@':
        return '@'
    domain_lower = (domain or '').strip().lower().rstrip('.')
    if not domain_lower:
        return rr.lower()
    if rr.lower() == domain_lower:
        return '@'
    suffix = '.' + domain_lower
    if rr.lower().endswith(suffix):
        rr = rr[: -len(suffix)].rstrip('.')
    return (rr or '@').lower()


def _normalize_value_for_compare(value: str) -> str:
    v = (value or '').strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        v = v[1:-1]
    return v


@app.route('/api/dns/records-check/<provider>', methods=['POST'])
def dns_records_check(provider):
    body = request.get_json(silent=True) or {}
    records = body.get('records') or []
    domain = body.get('domain', '')
    if not records or not domain:
        return _ok({'results': []})
    try:
        config = _get_dns_config()
        existing = get_records(provider, domain, config)
        results = []
        for rec in records:
            rtype = (rec.get('type') or '').upper()
            rr = _normalize_rr_for_compare(rec.get('rr') or '', domain)
            value = _normalize_value_for_compare(rec.get('value') or '')
            # 冲突检测规则与桌面端一致：type + rr 相同即冲突
            match = None
            conflict = None
            for ex in existing:
                ex_type = ex.get('Type', '').upper()
                ex_rr = _normalize_rr_for_compare(ex.get('RR', ''), domain)
                ex_value = _normalize_value_for_compare(ex.get('Value', ''))
                if ex_type == rtype and ex_rr == rr:
                    conflict = ex
                    if ex_value == value:
                        match = ex
                        break
            if match:
                results.append({'status': 'exists', 'message': '记录已存在', 'existing': match})
            elif conflict:
                results.append({'status': 'conflict', 'message': '冲突：相同类型和主机记录已存在', 'existing': conflict})
            else:
                results.append({'status': 'new', 'message': '新记录，可导入', 'existing': None})
        session_id = (body.get('session_id') or '').strip()
        if session_id:
            append_import_log(
                'check_done',
                '存在性检测完成',
                {
                    'provider': provider,
                    'domain': domain,
                    'records': records,
                    'results': results,
                },
                session_id=session_id,
            )
        return _ok({'results': results})
    except Exception as e:
        session_id = (body.get('session_id') or '').strip()
        if session_id:
            append_import_log(
                'check_fail',
                '存在性检测失败',
                {'provider': provider, 'domain': domain, 'error': str(e)},
                session_id=session_id,
                success=False,
            )
        return _fail(str(e))


# ==================== 设置 API（只读状态，不提供密钥写入） ====================

@app.route('/api/dns/oplog', methods=['GET'])
def dns_get_oplog():
    provider = request.args.get('provider', '')
    domain = request.args.get('domain', '')
    action = request.args.get('action', '')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    try:
        data = query_logs(provider=provider, domain=domain, action=action,
                          limit=min(limit, 500), offset=offset)
        return _ok(data)
    except Exception as e:
        return _fail(str(e))

@app.route('/api/settings/status', methods=['GET'])
def get_settings_status():
    settings = get_settings()
    masked = _mask_profiles(settings)
    for k in ('cursor_api_key', 'cursor_agent_path'):
        if k in masked:
            masked[k] = _mask_value(masked[k])
    return _ok(masked)


# ==================== AI 解析 API ====================

@app.route('/api/dns/import-log', methods=['POST'])
def dns_import_log_append():
    body = request.get_json(silent=True) or {}
    try:
        entry = append_import_log(
            phase=body.get('phase', 'info'),
            message=body.get('message', ''),
            detail=body.get('detail'),
            session_id=body.get('session_id', ''),
            source=body.get('source', 'web'),
            success=bool(body.get('success', True)),
        )
        return _ok(entry)
    except Exception as e:
        logger.exception('dns_import_log_append failed: %s', e)
        return _fail(str(e))


@app.route('/api/dns/import-log', methods=['GET'])
def dns_import_log_query():
    session_id = request.args.get('session_id', '')
    phase = request.args.get('phase', '')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    try:
        data = query_import_logs(
            session_id=session_id,
            phase=phase,
            limit=min(limit, 500),
            offset=offset,
        )
        return _ok(data)
    except Exception as e:
        return _fail(str(e))


@app.route('/api/dns/import-log/info', methods=['GET'])
def dns_import_log_path():
    try:
        return _ok(import_log_info())
    except Exception as e:
        return _fail(str(e))


@app.route('/api/dns/ai/parse', methods=['POST'])
def dns_ai_parse_start():
    body = request.get_json(silent=True) or {}
    text = body.get('text', '')
    image_base64 = body.get('image_base64', '')
    domain_hint = body.get('domain_hint', '')
    session_id = (body.get('session_id') or '').strip() or new_session_id()
    try:
        append_import_log(
            'parse_start',
            '收到解析请求',
            {
                'has_image': bool(image_base64),
                'text_len': len(text or ''),
                'domain_hint': domain_hint or '',
            },
            session_id=session_id,
        )
        result = start_parse_async(
            text=text or '',
            image_base64=image_base64 or '',
            domain_hint=domain_hint or '',
            use_api=True,
            session_id=session_id,
        )
        if result.get('success'):
            payload = dict(result.get('data') or {})
            payload['session_id'] = session_id
            return _ok(payload, message=result.get('message', ''))
        append_import_log(
            'parse_fail',
            result.get('message', '识别失败'),
            {'domain_hint': domain_hint or ''},
            session_id=session_id,
            success=False,
        )
        return _fail(result.get('message', '识别失败'))
    except Exception as e:
        append_import_log(
            'parse_fail',
            str(e),
            {'domain_hint': domain_hint or ''},
            session_id=session_id,
            success=False,
        )
        return _fail(str(e))


@app.route('/api/dns/ai/parse/<run_id>', methods=['GET'])
def dns_ai_parse_poll(run_id):
    since_seq = int(request.args.get('since_seq', 0))
    limit = int(request.args.get('limit', 200))
    try:
        result = poll_parse(run_id, since_seq=since_seq, limit=limit)
        return jsonify(result)
    except Exception as e:
        return _fail(str(e))


@app.route('/api/dns/ai/config', methods=['GET'])
def dns_ai_config_get():
    try:
        data = get_dns_parse_config_public()
        return _ok(data)
    except Exception as e:
        return _fail(str(e))


# ==================== 入口 ====================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='DNS 解析管理 - 网页版')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址 (默认 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='监听端口 (默认 5000)')
    parser.add_argument('--prod', action='store_true', help='生产模式 (关闭 debug)')
    args = parser.parse_args()

    print('DNS 解析管理 - 网页版')
    print('访问 http://%s:%s' % (args.host if args.host != '0.0.0.0' else '127.0.0.1', args.port))

    if args.prod:
        try:
            from werkzeug.serving import run_simple
            run_simple(args.host, args.port, app, use_reloader=False, use_debugger=False)
        except ImportError:
            app.run(host=args.host, port=args.port, debug=False)
    else:
        app.run(host=args.host, port=args.port, debug=True)
