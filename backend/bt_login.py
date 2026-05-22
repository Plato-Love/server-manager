"""
服务器管家 - 宝塔面板自动登录模块
使用 DrissionPage 4.0，不依赖 WebDriver
禁止使用 time.sleep，全部使用 DrissionPage 智能等待
"""
import threading
import subprocess
import os
import re
import urllib.parse
from .chromium_session import automation_lock, get_shared_chromium_page, get_automation_tab, shutdown_shared_chromium_page
from .logger import get_logger

logger = get_logger('bt_login')


class BtLoginer:
    """宝塔面板自动登录器"""

    def __init__(self, browser_path: str = ''):
        self.browser_path = browser_path  # 兼容旧构造参数；浏览器路径已由 chromium_session 从设置读取
        self.page = None

    def _bring_to_front(self):
        """尽可能将浏览器窗口置前显示"""
        if not self.page:
            return
        try:
            window_ctl = getattr(getattr(self.page, 'set', None), 'window', None)
            if window_ctl:
                for method_name in ('show', 'max', 'activate'):
                    method = getattr(window_ctl, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception:
                            pass
        except Exception:
            pass

    def _open_native_browser(self, panel_url: str) -> bool:
        """使用系统浏览器前台打开（优先与任务栏已有浏览器合并）"""
        try:
            if self.browser_path and os.path.exists(self.browser_path):
                subprocess.Popen([self.browser_path, panel_url], close_fds=True)
                return True
        except Exception as exc:
            logger.warning('native browser open failed by path: %s', exc)

        try:
            import webbrowser
            webbrowser.open(panel_url, new=2)
            return True
        except Exception as exc:
            logger.warning('native browser open failed by webbrowser: %s', exc)
            return False

    @staticmethod
    def _build_redirect_url(panel_url: str, redirect_path: str) -> str:
        path = (redirect_path or '').strip()
        if not path:
            return panel_url
        if path.startswith('http://') or path.startswith('https://'):
            return path
        if not path.startswith('/'):
            path = '/' + path

        try:
            parsed = urllib.parse.urlsplit((panel_url or '').strip())
            if not parsed.scheme or not parsed.netloc:
                return panel_url.rstrip('/') + path

            base_path = (parsed.path or '').rstrip('/')
            last_segment = base_path.split('/')[-1] if base_path else ''
            # 宝塔常见随机安全后缀，如 /d330dcd8，跳转前需要去掉
            if re.fullmatch(r'[A-Za-z0-9]{6,32}', last_segment):
                base_path = ''
            elif base_path.endswith('/login'):
                base_path = base_path[:-len('/login')]

            merged_path = (base_path.rstrip('/') + path) if base_path else path
            return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, merged_path, '', ''))
        except Exception:
            return panel_url.rstrip('/') + path

    def _find_login_inputs(self, page):
        """开发阶段快速查找登录输入框。"""
        t = 0.3
        user_input = (
            page.ele('#username', timeout=t)
            or page.ele('@name=username', timeout=t)
            or page.ele('@placeholder:账号', timeout=t)
            or page.ele('@placeholder:用户名', timeout=t)
            or page.ele('@placeholder:用户', timeout=t)
            or page.ele('tag:input@@type=text', timeout=t)
        )
        pwd_input = (
            page.ele('#password', timeout=t)
            or page.ele('@name=password', timeout=t)
            or page.ele('@name=passwd', timeout=t)
            or page.ele('@placeholder:密码', timeout=t)
            or page.ele('tag:input@@type=password', timeout=t)
        )
        return user_input, pwd_input

    def _looks_like_login_page(self, page, current_url: str = '') -> bool:
        """快速判断当前是否在登录页，避免仅靠 URL 误判。"""
        url = (current_url or '').lower()
        if '/login' in url:
            return True
        try:
            if page.ele('tag:input@@type=password', timeout=0.3):
                return True
            if page.ele('text():安全登录模式', timeout=0.2):
                return True
            if page.ele('tag:button@@text():登录', timeout=0.2):
                return True
        except Exception:
            pass
        return False

    def _find_login_button(self, page):
        """多策略查找登录按钮"""
        btn = page.ele('tag:button@@text():登录', timeout=0.3)
        if btn:
            return btn
        for cls in ['.login-btn', '.btn-login', '.LoginBtn', '#loginBtn']:
            btn = page.ele(cls, timeout=0.3)
            if btn:
                return btn
        btn = page.ele('@type=submit', timeout=0.3)
        if btn:
            return btn
        btn = page.ele('text():登录', timeout=0.3)
        return btn

    def open_and_login(self, panel_url: str, username: str, password: str, redirect_path: str = '',
                       timeout: int = 15, prefer_native: bool = True) -> dict:
        try:
            target_url = self._build_redirect_url(panel_url, redirect_path)
            has_credentials = bool((username or '').strip() and (password or '').strip())
            # 有账号密码时优先自动化登录；仅在无凭据时走原生打开
            if prefer_native and not has_credentials:
                opened = self._open_native_browser(target_url)
                if opened:
                    # 为满足“前台显示并和已有任务栏浏览器合并”的诉求，优先走原生打开
                    return {'success': True, 'message': '已前台打开浏览器（优先合并到现有浏览器窗口）'}

            with automation_lock:
                # 新开标签页，不覆盖当前已有 tab
                browser = get_shared_chromium_page()
                self.page = get_automation_tab(panel_url)
                self._bring_to_front()

                current_url = self.page.url

                # 检测首次安装页
                if '/install' in current_url:
                    return {'success': False, 'message': '检测到首次安装页面，请先完成初始化设置'}

                # 先探测登录页特征，再判已登录，避免 URL 非 /login 但实际仍在登录页的误判。
                if not self._looks_like_login_page(self.page, current_url):
                    if (redirect_path or '').strip():
                        # 跳转也在当前脚本 tab 内进行
                        try:
                            self.page.get(target_url)
                        except Exception:
                            browser.get(target_url)
                        return {'success': True, 'message': '已处于登录状态，已跳转到目标页面'}
                    return {'success': True, 'message': '已处于登录状态'}

                # 检测登录状态
                user_input, pwd_input = self._find_login_inputs(self.page)

                if user_input and pwd_input:
                    # 未登录
                    if not username or not password:
                        return {'success': False, 'message': '未配置宝塔账号密码，请在服务器编辑中填写'}

                    user_input.clear()
                    user_input.input(username)

                    pwd_input.clear()
                    pwd_input.input(password)

                    login_btn = self._find_login_button(self.page)
                    if login_btn:
                        login_btn.click()
                    else:
                        pwd_input.input('\n')

                    check_user, check_pwd = self._find_login_inputs(self.page)
                    if check_user and check_pwd:
                        return {'success': False, 'message': '登录失败，请检查账号密码是否正确'}
                    if (redirect_path or '').strip():
                        try:
                            self.page.get(target_url)
                        except Exception:
                            browser.get(target_url)
                        return {'success': True, 'message': '登录成功，已跳转到目标页面'}
                    return {'success': True, 'message': '登录成功'}

                # 没有登录框
                current_url = self.page.url
                if not self._looks_like_login_page(self.page, current_url):
                    if (redirect_path or '').strip():
                        try:
                            self.page.get(target_url)
                        except Exception:
                            browser.get(target_url)
                        return {'success': True, 'message': '已处于登录状态，已跳转到目标页面'}
                    return {'success': True, 'message': '已处于登录状态'}
                return {'success': False, 'message': '登录页面加载异常，未找到登录表单'}

        except Exception as e:
            logger.exception('open_and_login failed: %s', e)
            return {'success': False, 'message': f'操作异常: {str(e)}'}

    def open_and_login_async(self, panel_url: str, username: str, password: str, redirect_path: str = '',
                             callback=None, prefer_native: bool = True) -> dict:
        """异步执行登录（不阻塞 UI）"""
        def _task():
            result = self.open_and_login(
                panel_url, username, password, redirect_path=redirect_path, prefer_native=prefer_native
            )
            if callback:
                callback(result)

        t = threading.Thread(target=_task, daemon=True)
        t.start()
        return {'success': True, 'message': '已启动浏览器，正在处理...'}

    def close(self):
        """关闭共享自动化浏览器"""
        shutdown_shared_chromium_page()
        self.page = None
