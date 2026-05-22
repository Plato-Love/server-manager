#!/usr/bin/env python3
"""
服务器管家 - 数据存储层
JSON 文件存储
"""
import json
import os
from datetime import datetime

from .paths import data_dir

# 数据目录（打包后与 exe 同级的 data）
DATA_DIR = data_dir()

# 数据文件路径
SERVERS_FILE = os.path.join(DATA_DIR, 'servers.json')
SCRIPTS_FILE = os.path.join(DATA_DIR, 'scripts.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')


def _read_json(filepath: str, default=None):
    """读取 JSON 文件"""
    if not os.path.exists(filepath):
        return default if default is not None else []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def _write_json(filepath: str, data):
    """写入 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== 服务器管理 ====================

def get_servers() -> list:
    """获取所有服务器"""
    return _read_json(SERVERS_FILE, [])


def add_server(server: dict) -> dict:
    """添加服务器"""
    servers = get_servers()
    server['id'] = datetime.now().strftime('%Y%m%d%H%M%S%f')
    server['created_at'] = datetime.now().isoformat()
    servers.append(server)
    _write_json(SERVERS_FILE, servers)
    return server


def update_server(server_id: str, updates: dict) -> dict:
    """更新服务器"""
    servers = get_servers()
    for s in servers:
        if s.get('id') == server_id:
            s.update(updates)
            s['updated_at'] = datetime.now().isoformat()
            _write_json(SERVERS_FILE, servers)
            return s
    return None


def delete_server(server_id: str) -> bool:
    """删除服务器"""
    servers = get_servers()
    for i, s in enumerate(servers):
        if s.get('id') == server_id:
            servers.pop(i)
            _write_json(SERVERS_FILE, servers)
            return True
    return False


def batch_update_server_group(old_group: str, new_group: str) -> int:
    """批量更新服务器分组名，返回影响数量"""
    old_group = (old_group or '').strip()
    new_group = (new_group or '').strip()
    if not old_group:
        return 0
    servers = get_servers()
    changed = 0
    for s in servers:
        if (s.get('group') or '').strip() == old_group:
            s['group'] = new_group
            s['updated_at'] = datetime.now().isoformat()
            changed += 1
    if changed:
        _write_json(SERVERS_FILE, servers)
    return changed


# ==================== 脚本管理 ====================

def get_scripts() -> list:
    """获取所有脚本，首次使用时自动插入默认宝塔登录脚本"""
    scripts = _read_json(SCRIPTS_FILE, [])
    if not scripts:
        # 首次使用，插入默认脚本
        default_script = {
            'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
            'name': '宝塔自动登录',
            'type': 'python',
            'created_at': datetime.now().isoformat(),
            'code': '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝塔面板自动登录脚本
使用方法：在服务器管理中绑定此脚本，点击运行即可
支持：登录后跳转到指定页面，实时日志输出
禁止使用 time.sleep，全部使用 DrissionPage 智能等待
"""

import json
import sys
import re
import urllib.parse

# 获取服务器信息（context 为本应用注入）
server = {}
if isinstance(context, dict):
    server = context.get('server') or {}
if not server:
    server = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
panel_url = server.get('bt_url', '')
username = server.get('bt_user', '')
password = server.get('bt_pass', '')
redirect_path = server.get('bt_redirect', '')

if not panel_url:
    print('[ERROR] 该服务器未配置宝塔地址')
    sys.exit(1)

print('[INFO] 正在打开宝塔面板: ' + str(panel_url))
page = get_automation_browser()
page.get(panel_url)
# 等待页面加载完成（等待 body 标签出现）
page.wait.eles_loaded('tag:body')

print('[INFO] 页面加载完成，检测登录状态...')

def build_redirect_url(panel_url, redirect_path):
    path = (redirect_path or '').strip()
    if not path:
        return panel_url
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if not path.startswith('/'):
        path = '/' + path
    parsed = urllib.parse.urlsplit((panel_url or '').strip())
    if not parsed.scheme or not parsed.netloc:
        return panel_url.rstrip('/') + path
    base_path = (parsed.path or '').rstrip('/')
    last_segment = base_path.split('/')[-1] if base_path else ''
    if re.fullmatch(r'[A-Za-z0-9]{6,32}', last_segment):
        base_path = ''
    elif base_path.endswith('/login'):
        base_path = base_path[:-len('/login')]
    merged_path = (base_path.rstrip('/') + path) if base_path else path
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, merged_path, '', ''))

# 多策略查找登录输入框
def find_login_inputs(page):
    user = page.ele('@placeholder:用户', timeout=3)
    if not user:
        user = page.ele('@placeholder:username', timeout=2)
    if not user:
        user = page.ele('@placeholder:账号', timeout=2)
    pwd = page.ele('@placeholder:密码', timeout=3)
    if not pwd:
        pwd = page.ele('@placeholder:password', timeout=2)
    if user and pwd:
        return user, pwd
    user = page.ele('#username', timeout=2)
    if not user:
        user = page.ele('@name=username', timeout=2)
    pwd = page.ele('#password', timeout=2)
    if not pwd:
        pwd = page.ele('@name=password', timeout=2)
    if user and pwd:
        return user, pwd
    return None, None

def find_login_button(page):
    btn = page.ele('tag:button@@text():登录', timeout=3)
    if btn:
        return btn
    for cls in ['.login-btn', '.btn-login', '.LoginBtn', '#loginBtn']:
        btn = page.ele(cls, timeout=1)
        if btn:
            return btn
    btn = page.ele('@type=submit', timeout=1)
    return btn

user_input, pwd_input = find_login_inputs(page)

if user_input and pwd_input:
    print('[INFO] 检测到登录页')
    if not username or not password:
        print('[WARN] 未配置宝塔账号密码，请在服务器编辑中填写')
    else:
        print('[INFO] 正在自动登录...')
        user_input.clear()
        user_input.input(username)
        print(f'[INFO] 已输入用户名: {username}')
        pwd_input.clear()
        pwd_input.input(password)
        print('[INFO] 已输入密码')
        login_btn = find_login_button(page)
        if login_btn:
            print('[INFO] 点击登录按钮')
            login_btn.click()
        elif pwd_input:
            pwd_input.input('\\n')
        # 等待页面跳转（登录成功后 URL 会变化）
        page.wait.url_change(panel_url, timeout=10)
        # 验证登录
        check_user, _ = find_login_inputs(page)
        if check_user:
            print('[ERROR] 登录失败，请检查账号密码')
        else:
            print('[SUCCESS] 登录成功！')
            if redirect_path:
                redirect_url = build_redirect_url(panel_url, redirect_path)
                print(f'[INFO] 正在跳转到: {redirect_url}')
                page.get(redirect_url)
                page.wait.eles_loaded('tag:body')
else:
    current_url = page.url
    if '/login' not in current_url:
        print('[INFO] 已处于登录状态')
        if redirect_path:
            redirect_url = build_redirect_url(panel_url, redirect_path)
            print(f'[INFO] 正在跳转到: {redirect_url}')
            page.get(redirect_url)
            page.wait.eles_loaded('tag:body')
    else:
        print('[WARN] 页面加载异常，未找到登录表单')

print('[INFO] 宝塔面板操作完成')
'''
        }
        scripts = [default_script]
        _write_json(SCRIPTS_FILE, scripts)
    return scripts


def add_script(script: dict) -> dict:
    """添加脚本"""
    scripts = get_scripts()
    script['id'] = datetime.now().strftime('%Y%m%d%H%M%S%f')
    script['created_at'] = datetime.now().isoformat()
    scripts.append(script)
    _write_json(SCRIPTS_FILE, scripts)
    return script


def update_script(script_id: str, updates: dict) -> dict:
    """更新脚本"""
    scripts = get_scripts()
    for s in scripts:
        if s.get('id') == script_id:
            s.update(updates)
            s['updated_at'] = datetime.now().isoformat()
            _write_json(SCRIPTS_FILE, scripts)
            return s
    return None


def delete_script(script_id: str) -> bool:
    """删除脚本"""
    scripts = get_scripts()
    for i, s in enumerate(scripts):
        if s.get('id') == script_id:
            scripts.pop(i)
            _write_json(SCRIPTS_FILE, scripts)
            return True
    return False


# ==================== 设置管理 ====================

def get_settings() -> dict:
    """获取设置"""
    defaults = {
        'browser_path': '',
        'theme': 'light',
        'window_width': 1200,
        'window_height': 800,
        'auto_start': False,
        'server_groups': [],
        # DNS 密钥档案（开发阶段不做兼容迁移）
        'ali_profiles': [],
        'ali_active_profile': '',
        'dnspod_profiles': [],
        'dnspod_active_profile': '',
        'tencent_profiles': [],
        'tencent_active_profile': '',
        'cursor_api_key': '',
        'cursor_agent_path': '',
    }
    settings = _read_json(SETTINGS_FILE, {})

    # ===== 开发阶段：一次性迁移旧字段到档案，并删除旧字段 =====
    migrated = False
    if 'ali_profiles' not in settings:
        settings['ali_profiles'] = []
    if 'dnspod_profiles' not in settings:
        settings['dnspod_profiles'] = []
    if 'tencent_profiles' not in settings:
        settings['tencent_profiles'] = []

    if not settings.get('ali_profiles'):
        akid = (settings.get('ali_access_key_id') or '').strip()
        aksec = (settings.get('ali_access_key_secret') or '').strip()
        if akid and aksec:
            settings['ali_profiles'] = [{
                'id': 'migrated',
                'name': '迁移',
                'access_key_id': akid,
                'access_key_secret': aksec,
            }]
            settings['ali_active_profile'] = 'migrated'
            migrated = True

    if not settings.get('dnspod_profiles'):
        dp_id = (settings.get('dnspod_id') or settings.get('tx_secret_id') or '').strip()
        dp_token = (settings.get('dnspod_token') or settings.get('tx_secret_key') or '').strip()
        if dp_id and dp_token:
            settings['dnspod_profiles'] = [{
                'id': 'migrated',
                'name': '迁移',
                'dnspod_id': dp_id,
                'dnspod_token': dp_token,
            }]
            settings['dnspod_active_profile'] = 'migrated'
            migrated = True

    # 腾讯云旧字段没有明确来源（避免瞎迁移），仅清理 cf/旧字段

    if migrated:
        for k in (
            'ali_access_key_id', 'ali_access_key_secret',
            'dnspod_id', 'dnspod_token',
            'tx_secret_id', 'tx_secret_key',
            'cf_api_token', 'cf_account_id', 'cf_email',
        ):
            if k in settings:
                del settings[k]
        _write_json(SETTINGS_FILE, settings)
    # 合并默认值
    for key, value in defaults.items():
        if key not in settings:
            settings[key] = value
    return settings


def _normalize_group_name(name: str) -> str:
    return (name or '').strip()


def get_server_groups() -> list:
    """获取服务器分组列表"""
    settings = get_settings()
    groups = settings.get('server_groups') or []
    normalized = []
    seen = set()
    for g in groups:
        ng = _normalize_group_name(g)
        if not ng:
            continue
        key = ng.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(ng)
    return sorted(normalized)


def add_server_group(name: str) -> list:
    """新增服务器分组"""
    group = _normalize_group_name(name)
    if not group:
        raise Exception('分组名称不能为空')
    groups = get_server_groups()
    if any(g.lower() == group.lower() for g in groups):
        raise Exception('分组已存在')
    groups.append(group)
    settings = get_settings()
    settings['server_groups'] = sorted(groups)
    _write_json(SETTINGS_FILE, settings)
    return settings['server_groups']


def rename_server_group(old_name: str, new_name: str) -> list:
    """重命名服务器分组并同步更新服务器数据"""
    old_group = _normalize_group_name(old_name)
    new_group = _normalize_group_name(new_name)
    if not old_group or not new_group:
        raise Exception('分组名称不能为空')
    groups = get_server_groups()
    if not any(g.lower() == old_group.lower() for g in groups):
        raise Exception('原分组不存在')
    if any(g.lower() == new_group.lower() for g in groups if g.lower() != old_group.lower()):
        raise Exception('新分组名称已存在')

    updated_groups = []
    for g in groups:
        if g.lower() == old_group.lower():
            updated_groups.append(new_group)
        else:
            updated_groups.append(g)

    settings = get_settings()
    settings['server_groups'] = sorted(updated_groups)
    _write_json(SETTINGS_FILE, settings)
    batch_update_server_group(old_group, new_group)
    return settings['server_groups']


def delete_server_group(name: str) -> list:
    """删除服务器分组并将关联服务器分组清空"""
    group = _normalize_group_name(name)
    if not group:
        raise Exception('分组名称不能为空')
    groups = get_server_groups()
    if not any(g.lower() == group.lower() for g in groups):
        raise Exception('分组不存在')
    updated_groups = [g for g in groups if g.lower() != group.lower()]
    settings = get_settings()
    settings['server_groups'] = sorted(updated_groups)
    _write_json(SETTINGS_FILE, settings)
    batch_update_server_group(group, '')
    return settings['server_groups']


def update_settings(updates: dict) -> dict:
    """更新设置"""
    settings = get_settings()
    settings.update(updates)
    settings['updated_at'] = datetime.now().isoformat()
    _write_json(SETTINGS_FILE, settings)
    return settings
