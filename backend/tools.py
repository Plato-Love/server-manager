"""
服务器管家 - 脚本引擎模块
支持 Python 脚本执行，实时日志输出
"""
import json
import re
import sys
import io
import threading
import traceback

from .chromium_session import get_automation_tab
from .logger import get_logger

logger = get_logger('tools')


def execute_python_script(code: str, context: dict = None) -> dict:
    """
    执行 Python 脚本（同步，用于简单脚本）
    返回完整输出
    """
    try:
        logger.info('execute_python_script start')
        output_buffer = []
        safe_globals = {
            '__builtins__': __builtins__,
            'json': json,
            're': re,
            'context': context or {},
            'get_automation_browser': get_automation_tab,
        }

        # 捕获 print 输出
        def _print(*args, **kwargs):
            line = ' '.join(str(a) for a in args)
            output_buffer.append(line)
            logger.info('script_print %s', line)

        safe_globals['print'] = _print

        local_vars = {}
        exec(code, safe_globals, local_vars)

        result_value = local_vars.get('result', '')
        if result_value:
            output_buffer.insert(0, str(result_value))

        output = '\n'.join(output_buffer).strip()
        logger.info('execute_python_script success')
        return {'success': True, 'result': output, 'message': '执行完成'}
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception('execute_python_script failed: %s', e)
        return {'success': False, 'result': tb, 'message': str(e)}
