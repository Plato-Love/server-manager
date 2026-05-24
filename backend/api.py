"""
服务器管家 - API 桥接层
连接 pywebview 前端与后端 Python 模块

注意：pywebview JS API 调用时，所有参数都是位置参数。
例如 JS: pywebview.api.dns_add_record('cf', {domain: '...', ...})
对应 Python: def dns_add_record(self, provider, params)
不能用 **kwargs，因为 pywebview 不会把 dict 展开为关键字参数。
"""
from .storage import (
    get_servers, add_server, update_server, delete_server,
    get_scripts, add_script, update_script, delete_script,
    get_settings, update_settings,
    get_server_groups, add_server_group, rename_server_group, delete_server_group
)
from .autostart import is_enabled as _autostart_is_enabled, set_enabled as _set_autostart_enabled
from .chromium_session import shutdown_shared_chromium_page
from .tools import execute_python_script
from .script_runner import (
    list_recent as _list_script_runs,
    poll as _poll_script_run,
    run_code_async as _run_code_async,
    run_server_script_async as _run_server_script_async,
)
from .dns_manager import (
    get_provider_status, get_domains, get_records_page,
    add_record, delete_record, update_record
)
from .clipboard_util import get_clipboard_image_base64
from .dns_parse_config import (
    get_dns_parse_config_edit,
    get_dns_parse_config_public,
    update_dns_parse_config,
)
from .dns_ai_parse import poll_parse as _poll_dns_ai_parse, start_parse_async as _start_dns_ai_parse
from .dns_detect import detect_provider_for_domain as _detect_provider_for_domain
from .dns_oplog import append_log as _append_oplog, query_logs as _query_oplog
from .dns_import_log import append_import_log as _append_import_log, log_info as _import_log_info
from .logger import get_logger

logger = get_logger('api')


class Api:
    """暴露给前端的 API 类"""

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def window_minimize(self):
        w = self._window
        if w and hasattr(w, 'minimize'):
            try:
                w.minimize()
            except Exception as exc:
                logger.warning('window_minimize failed: %s', exc)
        return {'success': True}

    def window_hide(self):
        """隐藏主窗口到托盘（与点关闭按钮行为一致）。"""
        w = self._window
        if w:
            try:
                if hasattr(w, 'hide'):
                    w.hide()
                elif hasattr(w, 'minimize'):
                    w.minimize()
            except Exception as exc:
                logger.warning('window_hide failed: %s', exc)
        return {'success': True}

    def window_toggle_maximize(self):
        """最大化 / 还原主窗口。"""
        w = self._window
        if not w:
            return {'success': False, 'message': '窗口未就绪'}
        try:
            if getattr(w, 'maximized', False) and hasattr(w, 'restore'):
                w.restore()
                return {'success': True, 'maximized': False}
            if hasattr(w, 'maximize'):
                w.maximize()
                return {'success': True, 'maximized': True}
        except Exception as exc:
            logger.warning('window_toggle_maximize failed: %s', exc)
            return {'success': False, 'message': str(exc)}
        return {'success': False, 'message': '不支持最大化'}

    def window_restore(self):
        """将主窗口置于前台（打开弹窗时避免被系统压到后台）。"""
        w = self._window
        if not w:
            return {'success': False, 'message': '窗口未就绪'}
        try:
            if hasattr(w, 'restore'):
                w.restore()
        except Exception as exc:
            logger.debug('window_restore.restore: %s', exc)
        try:
            if hasattr(w, 'show'):
                w.show()
        except Exception as exc:
            logger.warning('window_restore.show failed: %s', exc)
            return {'success': False, 'message': str(exc)}
        return {'success': True}

    def _get_dns_config(self):
        return get_settings()

    # ==================== 服务器管理 ====================

    def get_servers(self):
        return {'success': True, 'data': get_servers()}

    def add_server(self, server):
        try:
            result = add_server(server)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def update_server(self, server_id, updates):
        result = update_server(server_id, updates)
        if result:
            return {'success': True, 'data': result}
        return {'success': False, 'message': '服务器不存在'}

    def delete_server(self, server_id):
        if delete_server(server_id):
            return {'success': True, 'message': '已删除'}
        return {'success': False, 'message': '服务器不存在'}

    def get_server_groups(self):
        return {'success': True, 'data': get_server_groups()}

    def add_server_group(self, name):
        try:
            groups = add_server_group(name)
            return {'success': True, 'data': groups}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def rename_server_group(self, old_name, new_name):
        try:
            groups = rename_server_group(old_name, new_name)
            return {'success': True, 'data': groups}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def delete_server_group(self, name):
        try:
            groups = delete_server_group(name)
            return {'success': True, 'data': groups}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    # ==================== 脚本管理 ====================

    def get_scripts(self):
        return {'success': True, 'data': get_scripts()}

    def add_script(self, script):
        try:
            result = add_script(script)
            return {'success': True, 'data': result}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def update_script(self, script_id, updates):
        result = update_script(script_id, updates)
        if result:
            return {'success': True, 'data': result}
        return {'success': False, 'message': '脚本不存在'}

    def delete_script(self, script_id):
        if delete_script(script_id):
            return {'success': True, 'message': '已删除'}
        return {'success': False, 'message': '脚本不存在'}

    # ==================== 设置 ====================

    def get_settings(self):
        settings = get_settings()
        settings['auto_start'] = _autostart_is_enabled()
        return {'success': True, 'data': settings}

    def update_settings(self, updates):
        if isinstance(updates, dict) and 'auto_start' in updates:
            enabled = bool(updates.get('auto_start'))
            if not _set_autostart_enabled(enabled):
                return {'success': False, 'message': '开机自启动设置失败，请检查系统权限'}
        result = update_settings(updates)
        result['auto_start'] = _autostart_is_enabled()
        return {'success': True, 'data': result}

    def close_browser(self):
        shutdown_shared_chromium_page()
        return {'success': True, 'message': '浏览器已关闭'}

    # ==================== DNS 管理 ====================
    # 注意：pywebview JS 调用传 dict 时，Python 端必须用 params 接收
    # JS: pywebview.api.dns_add_record('cf', {type:'A', rr:'www', ...})
    # Python: def dns_add_record(self, provider, params)

    def dns_get_providers(self):
        """获取 DNS 服务商配置状态"""
        config = self._get_dns_config()
        status = get_provider_status(config)
        return {'success': True, 'data': status}

    def dns_get_domains(self, provider):
        """获取域名列表"""
        try:
            config = self._get_dns_config()
            domains = get_domains(provider, config)
            logger.info('dns_get_domains success provider=%s count=%s', provider, len(domains))
            return {'success': True, 'data': domains}
        except Exception as e:
            logger.exception('dns_get_domains failed provider=%s error=%s', provider, e)
            return {'success': False, 'message': str(e)}

    def dns_get_records(self, provider, domain, zone_id='', page=1, page_size=100):
        """获取解析记录"""
        try:
            config = self._get_dns_config()
            page_data = get_records_page(
                provider, domain, config,
                zone_id=zone_id, page=page, page_size=page_size
            )
            records = page_data.get('records') or []
            total = int(page_data.get('total', len(records)) or len(records))
            page_no = int(page_data.get('page', page or 1) or 1)
            page_sz = int(page_data.get('page_size', page_size or 100) or 100)
            logger.info(
                'dns_get_records success provider=%s domain=%s zone_id=%s page=%s page_size=%s count=%s total=%s',
                provider, domain, zone_id, page_no, page_sz, len(records), total
            )
            return {
                'success': True,
                'data': {
                    'records': records,
                    'pagination': {
                        'page': page_no,
                        'page_size': page_sz,
                        'total': total,
                        'total_pages': max(1, (total + page_sz - 1) // page_sz),
                    }
                }
            }
        except Exception as e:
            logger.exception(
                'dns_get_records failed provider=%s domain=%s zone_id=%s page=%s page_size=%s error=%s',
                provider, domain, zone_id, page, page_size, e
            )
            return {'success': False, 'message': str(e)}

    def dns_add_record(self, provider, params):
        """添加解析记录"""
        if not isinstance(params, dict):
            return {'success': False, 'message': '参数格式错误'}
        required = ['type', 'rr', 'value']
        for key in required:
            if not params.get(key):
                return {'success': False, 'message': f'缺少必要参数: {key}'}
        domain = params.get('domain', '')
        try:
            config = self._get_dns_config()
            result = add_record(provider, config, **params)
            logger.info(
                'dns_add_record success provider=%s domain=%s type=%s rr=%s',
                provider, domain, params.get('type', ''), params.get('rr', '')
            )
            _append_oplog('add', provider, domain,
                          detail={'type': params.get('type'), 'rr': params.get('rr'), 'value': params.get('value')},
                          source='desktop', success=True, message='添加记录')
            session_id = (params.get('session_id') or '').strip()
            if session_id:
                _append_import_log(
                    'import_item', '添加记录成功',
                    {'provider': provider, 'domain': domain, 'type': params.get('type'),
                     'rr': params.get('rr'), 'value': params.get('value'), 'result': result},
                    session_id=session_id, source='desktop', success=True,
                )
            return {'success': True, 'data': result}
        except Exception as e:
            logger.exception(
                'dns_add_record failed provider=%s domain=%s type=%s rr=%s error=%s',
                provider, domain, params.get('type', ''), params.get('rr', ''), e
            )
            _append_oplog('add', provider, domain,
                          detail={'type': params.get('type'), 'rr': params.get('rr'), 'value': params.get('value')},
                          source='desktop', success=False, message=str(e))
            session_id = (params.get('session_id') or '').strip()
            if session_id:
                _append_import_log(
                    'import_item', '添加记录失败',
                    {'provider': provider, 'domain': domain, 'type': params.get('type'),
                     'rr': params.get('rr'), 'value': params.get('value'), 'error': str(e)},
                    session_id=session_id, source='desktop', success=False,
                )
            return {'success': False, 'message': str(e)}

    def dns_delete_record(self, provider, params):
        """删除解析记录"""
        if not isinstance(params, dict):
            return {'success': False, 'message': '参数格式错误'}
        if not params.get('record_id'):
            return {'success': False, 'message': '缺少必要参数: record_id'}
        domain = params.get('domain', '')
        try:
            config = self._get_dns_config()
            result = delete_record(provider, config, **params)
            logger.info(
                'dns_delete_record success provider=%s domain=%s record_id=%s',
                provider, domain, params.get('record_id', '')
            )
            _append_oplog('delete', provider, domain,
                          detail={'record_id': params.get('record_id')},
                          source='desktop', success=True, message='删除记录')
            return {'success': True, 'data': result}
        except Exception as e:
            logger.exception(
                'dns_delete_record failed provider=%s domain=%s record_id=%s error=%s',
                provider, domain, params.get('record_id', ''), e
            )
            _append_oplog('delete', provider, domain,
                          detail={'record_id': params.get('record_id')},
                          source='desktop', success=False, message=str(e))
            return {'success': False, 'message': str(e)}

    def dns_update_record(self, provider, params):
        """修改解析记录"""
        if not isinstance(params, dict):
            return {'success': False, 'message': '参数格式错误'}
        required = ['type', 'rr', 'value', 'record_id']
        for key in required:
            if not params.get(key):
                return {'success': False, 'message': f'缺少必要参数: {key}'}
        domain = params.get('domain', '')
        try:
            config = self._get_dns_config()
            result = update_record(provider, config, **params)
            logger.info(
                'dns_update_record success provider=%s domain=%s type=%s rr=%s record_id=%s',
                provider, domain, params.get('type', ''), params.get('rr', ''), params.get('record_id', '')
            )
            _append_oplog('update', provider, domain,
                          detail={'record_id': params.get('record_id'), 'type': params.get('type'),
                                  'rr': params.get('rr'), 'value': params.get('value')},
                          source='desktop', success=True, message='修改记录')
            return {'success': True, 'data': result}
        except Exception as e:
            logger.exception(
                'dns_update_record failed provider=%s domain=%s type=%s rr=%s record_id=%s error=%s',
                provider, domain, params.get('type', ''), params.get('rr', ''), params.get('record_id', ''), e
            )
            _append_oplog('update', provider, domain,
                          detail={'record_id': params.get('record_id'), 'type': params.get('type'),
                                  'rr': params.get('rr'), 'value': params.get('value')},
                          source='desktop', success=False, message=str(e))
            return {'success': False, 'message': str(e)}

    def dns_get_oplog(self, provider='', domain='', action='', limit=100, offset=0):
        """查询 DNS 操作日志"""
        try:
            data = _query_oplog(provider=provider, domain=domain, action=action,
                                limit=min(int(limit), 500), offset=int(offset))
            return {'success': True, 'data': data}
        except Exception as e:
            logger.exception('dns_get_oplog failed: %s', e)
            return {'success': False, 'message': str(e)}

    def dns_get_clipboard_image(self):
        """读取系统剪贴板中的图片（base64 PNG）。"""
        return get_clipboard_image_base64()

    def get_dns_parse_config(self, for_edit=False):
        """获取 DNS 快速解析配置。for_edit=True 时返回完整密钥（仅设置页）。"""
        try:
            data = get_dns_parse_config_edit() if for_edit else get_dns_parse_config_public()
            return {'success': True, 'data': data}
        except Exception as e:
            logger.exception('get_dns_parse_config failed error=%s', e)
            return {'success': False, 'message': str(e)}

    def update_dns_parse_config(self, updates):
        """更新 DNS 快速解析配置文件。"""
        if not isinstance(updates, dict):
            return {'success': False, 'message': '参数格式错误'}
        try:
            data = update_dns_parse_config(updates)
            return {'success': True, 'data': get_dns_parse_config_public(), 'message': '配置已保存'}
        except Exception as e:
            logger.exception('update_dns_parse_config failed error=%s', e)
            return {'success': False, 'message': str(e)}

    def dns_ai_parse_start(self, text='', image_base64='', domain_hint=''):
        """异步启动 DNS AI 识别（Cursor Agent CLI）。"""
        try:
            return _start_dns_ai_parse(
                text=text or '',
                image_base64=image_base64 or '',
                domain_hint=domain_hint or '',
            )
        except Exception as e:
            logger.exception('dns_ai_parse_start failed error=%s', e)
            return {'success': False, 'message': str(e)}

    def dns_detect_provider(self, domain):
        """根据 NS 与域名列表推断已配置的服务商。"""
        try:
            config = self._get_dns_config()
            data = _detect_provider_for_domain(domain or '', config)
            return {'success': True, 'data': data}
        except Exception as e:
            logger.exception('dns_detect_provider failed domain=%s error=%s', domain, e)
            return {'success': False, 'message': str(e)}

    def dns_ai_parse_poll(self, run_id, since_seq=0, limit=200):
        """轮询 DNS AI 识别进度与结果。"""
        try:
            return _poll_dns_ai_parse(run_id, since_seq=since_seq, limit=limit)
        except Exception as e:
            logger.exception('dns_ai_parse_poll failed run_id=%s error=%s', run_id, e)
            return {'success': False, 'message': str(e)}

    # ==================== 脚本执行 ====================

    def run_server_script(self, server_id, script_id=''):
        return _run_server_script_async(server_id, script_id, source='server')

    def execute_python_script(self, code, context=None):
        """同步执行 Python 脚本，返回完整输出"""
        return execute_python_script(code, context)

    def run_python_script_with_log(self, code, context=None):
        return _run_code_async(code, context=context or {})

    def poll_script_log(self, run_id, since_seq=0, limit=200):
        """前端轮询拉取脚本日志（强一致显示）"""
        return _poll_script_run(run_id, since_seq=since_seq, limit=limit)

    def list_script_runs(self, limit=20):
        """获取最近脚本运行任务，前端用来发现托盘启动的任务"""
        return _list_script_runs(limit=limit)

    # ==================== 系统 ====================

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)
        return {'success': True, 'message': '已打开'}

    def get_version(self):
        return {'success': True, 'data': {'version': '1.2.0', 'name': '服务器管家'}}
