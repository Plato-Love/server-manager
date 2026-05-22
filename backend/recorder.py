"""
服务器管家 - 脚本录制 & 元素辅助定位模块
使用 DrissionPage 4.0，不依赖 WebDriver
"""
import time
import threading
import json
from DrissionPage import ChromiumPage, ChromiumOptions


class Recorder:
    """浏览器操作录制器"""

    def __init__(self, browser_path: str = ''):
        self.browser_path = browser_path
        self.page = None
        self.recording = False
        self.events = []          # 录制的事件列表
        self._listener_thread = None
        self._stop_event = threading.Event()

    def _create_page(self) -> ChromiumPage:
        co = ChromiumOptions()
        if self.browser_path:
            co.set_browser_path(self.browser_path)
        co.set_argument('--no-first-run')
        co.set_argument('--disable-gpu')
        return ChromiumPage(co)

    def start_recording(self, url: str = '') -> dict:
        """开始录制，打开浏览器"""
        if self.recording:
            return {'success': False, 'message': '正在录制中，请先停止'}
        try:
            self.page = self._create_page()
            self.events = []
            self.recording = True
            self._stop_event.clear()

            if url:
                self.page.get(url)

            # 注入监听脚本，捕获用户操作
            self._inject_listener()

            # 启动事件收集线程
            self._listener_thread = threading.Thread(
                target=self._collect_events, daemon=True
            )
            self._listener_thread.start()

            return {'success': True, 'message': '录制已开始，请在浏览器中操作'}
        except Exception as e:
            self.recording = False
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def _inject_listener(self):
        """注入前端事件监听 JS"""
        js_code = """
        window.__recorderEvents = [];
        window.__recorderActive = true;

        // 获取元素的选择器路径
        function __getSelector(el) {
            if (el.id) return '#' + el.id;
            if (el === document.body) return 'body';
            var path = [];
            while (el && el !== document.body && el.nodeType === 1) {
                var idx = 1;
                var sib = el.previousSibling;
                while (sib) {
                    if (sib.nodeType === 1 && sib.tagName === el.tagName) idx++;
                    sib = sib.previousSibling;
                }
                var selector = el.tagName.toLowerCase();
                if (el.className && typeof el.className === 'string') {
                    var cls = el.className.trim().split(/\\s+/).join('.');
                    if (cls) selector += '.' + cls;
                }
                if (idx > 1) selector += ':nth-of-type(' + idx + ')';
                path.unshift(selector);
                el = el.parentNode;
            }
            return path.join(' > ');
        }

        // 获取元素的关键属性
        function __getElementInfo(el) {
            var info = {
                tag: el.tagName.toLowerCase(),
                selector: __getSelector(el),
                text: (el.innerText || '').substring(0, 100),
                href: el.href || '',
                src: el.src || '',
                type: el.type || '',
                name: el.name || '',
                placeholder: el.placeholder || '',
                value: el.value || ''
            };
            if (el.id) info.id = el.id;
            if (el.className) info.className = el.className;
            return info;
        }

        // 监听点击
        document.addEventListener('click', function(e) {
            if (!window.__recorderActive) return;
            window.__recorderEvents.push({
                type: 'click',
                element: __getElementInfo(e.target),
                timestamp: Date.now()
            });
        }, true);

        // 监听输入
        document.addEventListener('input', function(e) {
            if (!window.__recorderActive) return;
            window.__recorderEvents.push({
                type: 'input',
                element: __getElementInfo(e.target),
                value: e.target.value,
                timestamp: Date.now()
            });
        }, true);

        // 监听键盘
        document.addEventListener('keydown', function(e) {
            if (!window.__recorderActive) return;
            if (e.key === 'Enter' || e.key === 'Tab') {
                window.__recorderEvents.push({
                    type: 'keydown',
                    element: __getElementInfo(e.target),
                    key: e.key,
                    timestamp: Date.now()
                });
            }
        }, true);

        // 监听导航
        window.addEventListener('beforeunload', function() {
            if (!window.__recorderActive) return;
            window.__recorderEvents.push({
                type: 'navigate',
                url: window.location.href,
                timestamp: Date.now()
            });
        });

        console.log('[Recorder] 事件监听已注入');
        """
        try:
            self.page.run_js(js_code)
        except Exception:
            pass

    def _collect_events(self):
        """后台线程：定期从浏览器收集录制事件"""
        while not self._stop_event.is_set() and self.recording:
            try:
                events = self.page.run_js('return JSON.stringify(window.__recorderEvents || [])')
                if events:
                    new_events = json.loads(events)
                    if len(new_events) > len(self.events):
                        self.events = new_events
                time.sleep(1)
            except Exception:
                time.sleep(2)

    def stop_recording(self) -> dict:
        """停止录制，返回录制结果"""
        if not self.recording:
            return {'success': False, 'message': '没有正在进行的录制'}

        self.recording = False
        self._stop_event.set()

        # 停止监听
        try:
            self.page.run_js('window.__recorderActive = false;')
        except Exception:
            pass

        # 生成 Python 脚本
        script = self._generate_script()

        return {
            'success': True,
            'message': f'录制完成，共 {len(self.events)} 个操作',
            'data': {
                'events': self.events,
                'script': script
            }
        }

    def _generate_script(self) -> str:
        """将录制事件转换为可执行的 Python 脚本"""
        if not self.events:
            return '# 没有录制到任何操作'

        lines = [
            '"""',
            '自动录制的脚本 - 由服务器管家生成',
            '"""',
            'from DrissionPage import ChromiumPage, ChromiumOptions',
            '',
            '# 配置浏览器路径（如需指定三方浏览器）',
            '# co = ChromiumOptions()',
            '# co.set_browser_path(r"浏览器可执行文件路径")',
            '# page = ChromiumPage(co)',
            'page = ChromiumPage()',
            '',
        ]

        for i, event in enumerate(self.events):
            lines.append(f'# 操作 {i + 1}: {event.get("type", "unknown")}')
            if event['type'] == 'navigate':
                lines.append(f"page.get('{event['url']}')")
            elif event['type'] == 'click':
                selector = event['element'].get('selector', '')
                text = event['element'].get('text', '')[:30]
                lines.append(f"# 目标元素: {text}")
                lines.append(f"page.ele('{selector}').click()")
            elif event['type'] == 'input':
                selector = event['element'].get('selector', '')
                value = event.get('value', '')
                lines.append(f"page.ele('{selector}').input('{value}')")
            elif event['type'] == 'keydown':
                selector = event['element'].get('selector', '')
                key = event.get('key', '')
                if key == 'Enter':
                    lines.append(f"page.ele('{selector}').input('\\n')")
                elif key == 'Tab':
                    lines.append(f"page.ele('{selector}').input('\\t')")
            lines.append('')

        return '\n'.join(lines)

    def get_recording_status(self) -> dict:
        """获取当前录制状态"""
        return {
            'success': True,
            'data': {
                'recording': self.recording,
                'event_count': len(self.events)
            }
        }

    def close(self):
        """关闭浏览器"""
        self.recording = False
        self._stop_event.set()
        if self.page:
            try:
                self.page.quit()
            except Exception:
                pass
            self.page = None


class ElementLocator:
    """元素辅助定位器 - 悬停高亮 + 点击获取选择器"""

    def __init__(self, browser_path: str = ''):
        self.browser_path = browser_path
        self.page = None
        self.locating = False
        self._collect_thread = None
        self._stop_event = threading.Event()
        self.highlighted_elements = []

    def _create_page(self) -> ChromiumPage:
        co = ChromiumOptions()
        if self.browser_path:
            co.set_browser_path(self.browser_path)
        co.set_argument('--no-first-run')
        co.set_argument('--disable-gpu')
        return ChromiumPage(co)

    def start_locating(self, url: str = '') -> dict:
        """开始定位模式"""
        if self.locating:
            return {'success': False, 'message': '定位模式已开启'}
        try:
            self.page = self._create_page()
            self.locating = True
            self._stop_event.clear()
            self.highlighted_elements = []

            if url:
                self.page.get(url)

            # 注入高亮和选择脚本
            self._inject_locator()

            return {'success': True, 'message': '定位模式已开启，悬停元素查看信息，点击获取选择器'}
        except Exception as e:
            self.locating = False
            return {'success': False, 'message': f'启动失败: {str(e)}'}

    def _inject_locator(self):
        """注入元素定位辅助脚本"""
        js_code = """
        window.__locatorActive = true;
        window.__locatorSelected = null;

        // 创建悬浮信息框
        var tooltip = document.createElement('div');
        tooltip.id = '__locator_tooltip';
        tooltip.style.cssText = 'position:fixed;z-index:999999;padding:6px 12px;'
            + 'background:#1e1e2e;color:#89b4fa;font-size:12px;font-family:monospace;'
            + 'border:1px solid #45475a;border-radius:6px;pointer-events:none;'
            + 'display:none;max-width:400px;word-break:break-all;';
        document.body.appendChild(tooltip);

        // 创建高亮覆盖层
        var overlay = document.createElement('div');
        overlay.id = '__locator_overlay';
        overlay.style.cssText = 'position:fixed;z-index:999998;pointer-events:none;'
            + 'border:2px solid #89b4fa;background:rgba(137,180,250,0.1);'
            + 'display:none;transition:all 0.1s ease;';
        document.body.appendChild(overlay);

        function __getSelector(el) {
            if (el.id) return '#' + el.id;
            if (el === document.body) return 'body';
            var path = [];
            while (el && el !== document.body && el.nodeType === 1) {
                var idx = 1;
                var sib = el.previousSibling;
                while (sib) {
                    if (sib.nodeType === 1 && sib.tagName === el.tagName) idx++;
                    sib = sib.previousSibling;
                }
                var selector = el.tagName.toLowerCase();
                if (el.className && typeof el.className === 'string') {
                    var cls = el.className.trim().split(/\\s+/).join('.');
                    if (cls) selector += '.' + cls;
                }
                if (idx > 1) selector += ':nth-of-type(' + idx + ')';
                path.unshift(selector);
                el = el.parentNode;
            }
            return path.join(' > ');
        }

        document.addEventListener('mousemove', function(e) {
            if (!window.__locatorActive) return;
            var el = document.elementFromPoint(e.clientX, e.clientY);
            if (!el || el.id === '__locator_tooltip' || el.id === '__locator_overlay') return;

            var rect = el.getBoundingClientRect();
            overlay.style.display = 'block';
            overlay.style.left = rect.left + 'px';
            overlay.style.top = rect.top + 'px';
            overlay.style.width = rect.width + 'px';
            overlay.style.height = rect.height + 'px';

            var selector = __getSelector(el);
            var info = el.tagName.toLowerCase();
            if (el.id) info += '#' + el.id;
            if (el.className && typeof el.className === 'string') {
                var cls = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
                if (cls) info += '.' + cls;
            }
            if (el.name) info += ' [name=' + el.name + ']';
            if (el.type) info += ' [type=' + el.type + ']';

            tooltip.textContent = info + '  →  ' + selector;
            tooltip.style.display = 'block';
            tooltip.style.left = (e.clientX + 15) + 'px';
            tooltip.style.top = (e.clientY + 15) + 'px';
        }, true);

        document.addEventListener('click', function(e) {
            if (!window.__locatorActive) return;
            e.preventDefault();
            e.stopPropagation();

            var el = document.elementFromPoint(e.clientX, e.clientY);
            if (!el || el.id === '__locator_tooltip' || el.id === '__locator_overlay') return;

            var selector = __getSelector(el);
            window.__locatorSelected = {
                selector: selector,
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                className: (el.className || '').toString(),
                name: el.name || '',
                type: el.type || '',
                href: el.href || '',
                text: (el.innerText || '').substring(0, 100),
                placeholder: el.placeholder || '',
                attributes: {}
            };

            // 收集其他有用属性
            var attrs = el.attributes;
            for (var i = 0; i < attrs.length; i++) {
                window.__locatorSelected.attributes[attrs[i].name] = attrs[i].value;
            }

            // 闪烁效果
            overlay.style.borderColor = '#a6e3a1';
            overlay.style.background = 'rgba(166,227,161,0.2)';
            setTimeout(function() {
                overlay.style.borderColor = '#89b4fa';
                overlay.style.background = 'rgba(137,180,250,0.1)';
            }, 300);
        }, true);

        console.log('[Locator] 元素定位辅助已注入');
        """
        try:
            self.page.run_js(js_code)
        except Exception:
            pass

    def get_selected_element(self) -> dict:
        """获取最近点击选中的元素信息"""
        if not self.page or not self.locating:
            return {'success': False, 'message': '定位模式未开启'}
        try:
            result = self.page.run_js('return JSON.stringify(window.__locatorSelected)')
            if result:
                element = json.loads(result)
                if element:
                    self.highlighted_elements.append(element)
                    return {
                        'success': True,
                        'data': element,
                        'message': f'已选择: {element.get("selector", "")}'
                    }
            return {'success': False, 'message': '尚未选中任何元素，请在浏览器中点击'}
        except Exception as e:
            return {'success': False, 'message': f'获取失败: {str(e)}'}

    def stop_locating(self) -> dict:
        """停止定位模式"""
        if not self.locating:
            return {'success': False, 'message': '定位模式未开启'}
        self.locating = False
        self._stop_event.set()
        try:
            self.page.run_js(
                'window.__locatorActive = false;'
                'var t = document.getElementById("__locator_tooltip");'
                'if(t) t.remove();'
                'var o = document.getElementById("__locator_overlay");'
                'if(o) o.remove();'
            )
        except Exception:
            pass
        return {
            'success': True,
            'message': '定位模式已关闭',
            'data': {'elements': self.highlighted_elements}
        }

    def close(self):
        """关闭浏览器"""
        self.locating = False
        self._stop_event.set()
        if self.page:
            try:
                self.page.quit()
            except Exception:
                pass
            self.page = None
