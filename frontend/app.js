/**
 * 服务器管家 - 前端主逻辑
 * 使用 pywebview JS API 与 Python 后端通信
 * 纯原生 JavaScript，无外部依赖
 */

// ==================== 通用工具 ====================

/**
 * 显示 Toast 提示消息
 * @param {string} message - 提示文本
 * @param {string} type - 类型: success / error / info
 */
function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    container.appendChild(toast);
    // 触发动画
    requestAnimationFrame(function () {
        toast.classList.add('toast-show');
    });
    // 3秒后自动消失
    setTimeout(function () {
        toast.classList.remove('toast-show');
        toast.classList.add('toast-hide');
        toast.addEventListener('transitionend', function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        });
    }, 3000);
}

/** 模态框与阻塞对话框（见 ui-dialog.js） */
function showModal(id) {
    if (typeof UiDialog !== 'undefined') UiDialog.showModal(id);
    else {
        var modal = document.getElementById(id);
        if (modal) modal.classList.add('modal-active');
    }
}

function hideModal(id) {
    if (typeof UiDialog !== 'undefined') UiDialog.hideModal(id);
    else {
        var modal = document.getElementById(id);
        if (modal) modal.classList.remove('modal-active');
    }
}

function showCustomDialog(options) {
    if (typeof UiDialog !== 'undefined') return UiDialog.open(options);
    return Promise.resolve({ ok: false, value: '' });
}

function uiRunBusy(scope, message, task) {
    if (typeof UiDialog !== 'undefined') {
        return UiDialog.runBusy(scope || document.body, message, task);
    }
    return Promise.resolve().then(task);
}

/**
 * 统一封装 pywebview API 调用
 * @param {string} method - API 方法名
 * @param {...*} args - 传递给 API 的参数
 * @returns {Promise}
 */
function callApi(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    if (typeof pywebview === 'undefined' || !pywebview.api) {
        return Promise.reject(new Error('pywebview API 未就绪'));
    }
    return pywebview.api[method].apply(pywebview.api, args);
}

function waitForApiReady(timeoutMs) {
    timeoutMs = timeoutMs || 10000;
    return new Promise(function (resolve, reject) {
        if (typeof pywebview !== 'undefined' && pywebview.api) {
            resolve();
            return;
        }
        var done = false;
        var timer = setTimeout(function () {
            if (done) return;
            done = true;
            reject(new Error('pywebview API 初始化超时'));
        }, timeoutMs);
        window.addEventListener('pywebviewready', function () {
            if (done) return;
            done = true;
            clearTimeout(timer);
            resolve();
        }, { once: true });
    });
}

function initGlobalLogDrawer() {
    var drawer = document.getElementById('global-log-drawer');
    var header = document.getElementById('global-log-header');
    var btnToggle = document.getElementById('btn-toggle-global-log');
    var btnClear = document.getElementById('btn-clear-global-log');
    var output = document.getElementById('global-log-output');
    if (!drawer || !header || !btnToggle || !btnClear || !output) return;

    var opened = false;
    function renderState() {
        drawer.classList.toggle('open', opened);
        btnToggle.textContent = opened ? '收起' : '展开';
        document.body.classList.toggle('global-log-open', opened);
    }

    function toggle() {
        opened = !opened;
        renderState();
    }

    header.addEventListener('click', function (e) {
        if (e.target && e.target.id === 'btn-clear-global-log') return;
        if (e.target && e.target.id === 'btn-toggle-global-log') return;
        toggle();
    });
    btnToggle.addEventListener('click', function (e) {
        e.stopPropagation();
        toggle();
    });
    btnClear.addEventListener('click', function (e) {
        e.stopPropagation();
        output.value = '';
    });
    renderState();

    window.__setGlobalLogDrawerOpen = function (open) {
        opened = !!open;
        renderState();
    };

    window.__isGlobalLogDrawerOpen = function () {
        return opened;
    };

    window.__openGlobalLogDrawer = function () {
        window.__setGlobalLogDrawerOpen(true);
    };

    window.__appendScriptLogLine = function (line, opts) {
        opts = opts || {};
        if (typeof line !== 'string') line = String(line);
        if (opts.openDrawer === true && !window.__suppressAutoOpenLogDrawer) {
            window.__openGlobalLogDrawer();
        }
        output.value += line;
        output.scrollTop = output.scrollHeight;
        var el = document.getElementById('script-output');
        if (el) {
            el.value += line;
            el.scrollTop = el.scrollHeight;
        }
    };
}

/**
 * 收起所有「展开」态 UI（全局日志抽屉、模态框等）
 */
function collapseExpandedUi() {
    if (typeof window.__setGlobalLogDrawerOpen === 'function') {
        window.__setGlobalLogDrawerOpen(false);
    }
}

function _hasActiveModal() {
    return !!document.querySelector('.modal-overlay.modal-active');
}

var _windowActivateCollapseTimer = null;
/** 窗口刚被托盘/任务栏激活时，禁止日志追加自动展开抽屉 */
window.__suppressAutoOpenLogDrawer = false;
var _lastWindowActivatedAt = 0;

/**
 * 托盘 / 任务栏再次激活主窗口时由后端调用
 */
window.__onWindowActivated = function () {
    if (!window.__uiActivationReady) return;
    if (_hasActiveModal()) return;
    window.__suppressAutoOpenLogDrawer = true;
    collapseExpandedUi();
    if (_windowActivateCollapseTimer) clearTimeout(_windowActivateCollapseTimer);
    _windowActivateCollapseTimer = setTimeout(function () {
        _windowActivateCollapseTimer = null;
        window.__suppressAutoOpenLogDrawer = false;
    }, 2500);
};

function _triggerWindowActivatedFromBrowser() {
    if (!window.__uiActivationReady) return;
    var now = Date.now();
    if (now - _lastWindowActivatedAt < 400) return;
    _lastWindowActivatedAt = now;
    window.__onWindowActivated();
}

function bindWindowActivationCollapse() {
    /* 不在 focus/visibility 时收起 UI，避免打开弹窗或切回窗口时误关模态框 */
}

/**
 * HTML 转义，防止 XSS
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

/**
 * 属性值转义
 * @param {string} str - 原始字符串
 * @returns {string} 转义后的字符串
 */
function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function copyTextToClipboard(text, successMessage) {
    text = (text || '').trim();
    if (!text) { showToast('内容为空', 'error'); return; }
    successMessage = successMessage || '已复制';
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
            showToast(successMessage, 'success');
        }).catch(function () {
            showToast('复制失败', 'error');
        });
        return;
    }
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta);
    showToast(successMessage, 'success');
}

// ==================== 导航切换 ====================

/** 导航 ID 到面板 ID 的映射 */
var navMap = {
    'nav-servers': 'panel-servers',
    'nav-scripts': 'panel-scripts',
    'nav-dns': 'panel-dns',
    'nav-settings': 'panel-settings'
};

/** 当前激活的导航 ID */
var currentNav = 'nav-servers';
var panelLoadedState = {
    'nav-servers': false,
    'nav-scripts': false,
    'nav-dns': false,
    'nav-settings': false
};

var panelLoaders = {
    'nav-servers': loadServers,
    'nav-scripts': loadScripts,
    'nav-dns': loadDnsProviders,
    'nav-settings': loadSettings
};

var settingsCache = null;
var settingsLoadPromise = null;
/** DNS 快速解析配置（data/dns_parse_config.json） */
var dnsParseConfigCache = null;
var dnsParseConfigLoadPromise = null;

function _uuid() {
    return String(Date.now()) + String(Math.floor(Math.random() * 100000));
}

function _getProfiles(provider) {
    if (!settingsCache) return [];
    if (provider === 'ali') return settingsCache.ali_profiles || [];
    if (provider === 'dnspod') return settingsCache.dnspod_profiles || [];
    if (provider === 'tencent') return settingsCache.tencent_profiles || [];
    return [];
}

function _getActiveProfileId(provider) {
    if (!settingsCache) return '';
    if (provider === 'ali') return settingsCache.ali_active_profile || '';
    if (provider === 'dnspod') return settingsCache.dnspod_active_profile || '';
    if (provider === 'tencent') return settingsCache.tencent_active_profile || '';
    return '';
}

function _setActiveProfileId(provider, id) {
    if (!settingsCache) settingsCache = {};
    if (provider === 'ali') settingsCache.ali_active_profile = id;
    if (provider === 'dnspod') settingsCache.dnspod_active_profile = id;
    if (provider === 'tencent') settingsCache.tencent_active_profile = id;
}

function _findProfile(provider, id) {
    var list = _getProfiles(provider);
    for (var i = 0; i < list.length; i++) {
        if (String(list[i].id) === String(id)) return list[i];
    }
    return null;
}

function renderSettingProfileSelect(provider) {
    var selectId = provider === 'ali' ? 'setting-ali-profile' :
        provider === 'dnspod' ? 'setting-dnspod-profile' : 'setting-tencent-profile';
    var select = document.getElementById(selectId);
    if (!select) return;
    var list = _getProfiles(provider);
    var active = _getActiveProfileId(provider);
    var html = '<option value="">请选择档案</option>';
    list.forEach(function (p) {
        html += '<option value="' + escapeAttr(p.id) + '">' + escapeHtml(p.name || p.id) + '</option>';
    });
    select.innerHTML = html;
    select.value = active || '';
}

function applyProfileToInputs(provider) {
    var pid = _getActiveProfileId(provider);
    var p = _findProfile(provider, pid);
    if (!p) {
        if (provider === 'ali') {
            document.getElementById('setting-ali-ak-id').value = '';
            document.getElementById('setting-ali-ak-secret').value = '';
        } else if (provider === 'dnspod') {
            document.getElementById('setting-dnspod-id').value = '';
            document.getElementById('setting-dnspod-token').value = '';
        } else if (provider === 'tencent') {
            document.getElementById('setting-tencent-sid').value = '';
            document.getElementById('setting-tencent-skey').value = '';
        }
        return;
    }

    if (provider === 'ali') {
        document.getElementById('setting-ali-ak-id').value = p.access_key_id || '';
        document.getElementById('setting-ali-ak-secret').value = p.access_key_secret || '';
    } else if (provider === 'dnspod') {
        document.getElementById('setting-dnspod-id').value = p.dnspod_id || '';
        document.getElementById('setting-dnspod-token').value = p.dnspod_token || '';
    } else if (provider === 'tencent') {
        document.getElementById('setting-tencent-sid').value = p.secret_id || '';
        document.getElementById('setting-tencent-skey').value = p.secret_key || '';
    }
}

function syncInputsToActiveProfile(provider) {
    var pid = _getActiveProfileId(provider);
    var p = _findProfile(provider, pid);
    if (!p) return;
    if (provider === 'ali') {
        p.access_key_id = document.getElementById('setting-ali-ak-id').value.trim();
        p.access_key_secret = document.getElementById('setting-ali-ak-secret').value.trim();
    } else if (provider === 'dnspod') {
        p.dnspod_id = document.getElementById('setting-dnspod-id').value.trim();
        p.dnspod_token = document.getElementById('setting-dnspod-token').value.trim();
    } else if (provider === 'tencent') {
        p.secret_id = document.getElementById('setting-tencent-sid').value.trim();
        p.secret_key = document.getElementById('setting-tencent-skey').value.trim();
    }
}

function openProfileModal(provider, profile) {
    var list = _getProfiles(provider);
    document.getElementById('profile-provider').value = provider;
    document.getElementById('profile-id').value = profile ? profile.id : '';
    document.getElementById('profile-name').value = profile ? (profile.name || '') : '';
    var k1Label = document.getElementById('profile-key1-label');
    var k2Label = document.getElementById('profile-key2-label');
    var k1 = document.getElementById('profile-key1');
    var k2 = document.getElementById('profile-key2');
    if (provider === 'ali') {
        document.getElementById('profile-modal-title').textContent = profile ? '编辑阿里云档案' : '新增阿里云档案';
        k1Label.textContent = 'AccessKey ID *';
        k2Label.textContent = 'AccessKey Secret *';
        if (profile) {
            k1.value = profile.access_key_id || '';
            k2.value = profile.access_key_secret || '';
        } else if (!list || list.length === 0) {
            k1.value = (document.getElementById('setting-ali-ak-id').value || '').trim();
            k2.value = (document.getElementById('setting-ali-ak-secret').value || '').trim();
        } else {
            k1.value = '';
            k2.value = '';
        }
        k2.type = 'password';
    } else if (provider === 'dnspod') {
        document.getElementById('profile-modal-title').textContent = profile ? '编辑DNSPod档案' : '新增DNSPod档案';
        k1Label.textContent = 'DNSPod ID *';
        k2Label.textContent = 'DNSPod Token *';
        if (profile) {
            k1.value = profile.dnspod_id || '';
            k2.value = profile.dnspod_token || '';
        } else if (!list || list.length === 0) {
            k1.value = (document.getElementById('setting-dnspod-id').value || '').trim();
            k2.value = (document.getElementById('setting-dnspod-token').value || '').trim();
        } else {
            k1.value = '';
            k2.value = '';
        }
        k2.type = 'password';
    } else {
        document.getElementById('profile-modal-title').textContent = profile ? '编辑腾讯云档案' : '新增腾讯云档案';
        k1Label.textContent = 'SecretId *';
        k2Label.textContent = 'SecretKey *';
        if (profile) {
            k1.value = profile.secret_id || '';
            k2.value = profile.secret_key || '';
        } else if (!list || list.length === 0) {
            k1.value = (document.getElementById('setting-tencent-sid').value || '').trim();
            k2.value = (document.getElementById('setting-tencent-skey').value || '').trim();
        } else {
            k1.value = '';
            k2.value = '';
        }
        k2.type = 'password';
    }
    showModal('profile-modal');
    setTimeout(function () { document.getElementById('profile-name').focus(); }, 0);
}

function saveProfileFromModal() {
    var provider = document.getElementById('profile-provider').value;
    var pid = document.getElementById('profile-id').value;
    var name = document.getElementById('profile-name').value.trim();
    var key1 = document.getElementById('profile-key1').value.trim();
    var key2 = document.getElementById('profile-key2').value.trim();
    if (!name) { showToast('档案名称不能为空', 'error'); return; }
    if (!key1 || !key2) { showToast('密钥不能为空', 'error'); return; }

    if (!settingsCache) settingsCache = {};
    if (!settingsCache.ali_profiles) settingsCache.ali_profiles = [];
    if (!settingsCache.dnspod_profiles) settingsCache.dnspod_profiles = [];
    if (!settingsCache.tencent_profiles) settingsCache.tencent_profiles = [];

    var list = _getProfiles(provider);
    var existing = pid ? _findProfile(provider, pid) : null;
    if (!existing) {
        existing = { id: _uuid() };
        list.push(existing);
    }
    existing.name = name;
    if (provider === 'ali') {
        existing.access_key_id = key1;
        existing.access_key_secret = key2;
    } else if (provider === 'dnspod') {
        existing.dnspod_id = key1;
        existing.dnspod_token = key2;
    } else {
        existing.secret_id = key1;
        existing.secret_key = key2;
    }
    _setActiveProfileId(provider, existing.id);
    hideModal('profile-modal');
    persistSettings().then(function () {
        refreshSettingsProfilesUI();
        showToast('档案已保存', 'success');
    });
}

/**
 * 预加载 settings.json（DNS 档案、分组等依赖此缓存）
 * @param {boolean} force - 是否强制重新拉取
 */
function ensureSettingsLoaded(force) {
    if (!force && settingsCache) {
        return Promise.resolve(settingsCache);
    }
    if (!force && settingsLoadPromise) {
        return settingsLoadPromise;
    }
    settingsLoadPromise = callApi('get_settings').then(function (r) {
        if (r && r.success) {
            settingsCache = r.data || {};
            _applySettingsFormFromCache();
            return settingsCache;
        }
        settingsCache = settingsCache || {};
        return settingsCache;
    }).catch(function () {
        settingsCache = settingsCache || {};
        return settingsCache;
    });
    return settingsLoadPromise;
}

function _applySettingsFormFromCache() {
    if (!settingsCache) return;
    var browserPath = document.getElementById('setting-browser-path');
    if (browserPath) browserPath.value = settingsCache.browser_path || '';
    var autoStartEl = document.getElementById('setting-auto-start');
    if (autoStartEl) autoStartEl.checked = !!settingsCache.auto_start;
    refreshSettingsProfilesUI();
}

/**
 * 加载 DNS 快速解析配置（data/dns_parse_config.json）
 */
function ensureDnsParseConfigLoaded(force) {
    if (!force && dnsParseConfigCache) {
        return Promise.resolve(dnsParseConfigCache);
    }
    if (!force && dnsParseConfigLoadPromise) {
        return dnsParseConfigLoadPromise;
    }
    dnsParseConfigLoadPromise = callApi('get_dns_parse_config').then(function (r) {
        if (r && r.success) {
            dnsParseConfigCache = r.data || {};
            _renderDnsParseConfigHint();
            return dnsParseConfigCache;
        }
        dnsParseConfigCache = dnsParseConfigCache || {};
        _renderDnsParseConfigHint();
        return dnsParseConfigCache;
    }).catch(function () {
        dnsParseConfigCache = dnsParseConfigCache || {};
        _renderDnsParseConfigHint();
        return dnsParseConfigCache;
    });
    return dnsParseConfigLoadPromise;
}

function _renderDnsParseConfigHint() {
    var el = document.getElementById('dns-import-config-hint');
    if (!el) return;
    var cfg = dnsParseConfigCache || {};
    var mode = cfg.parse_mode_label || 'Cursor Agent 命令行';
    el.style.color = 'var(--text-secondary)';
    var parts = [mode + ' 已就绪'];
    if (cfg.has_api_key && cfg.api_key_masked) {
        parts.push('Key: ' + cfg.api_key_masked);
    } else if (cfg.uses_system_account) {
        parts.push('认证: 本机 Cursor 账号');
    }
    if (cfg.has_proxy && cfg.proxy_url) parts.push('代理: ' + cfg.proxy_url);
    parts.push('模型: ' + (cfg.effective_model_label || cfg.effective_model || 'Composer 2.5 Fast'));
    parts.push('可在「设置」中修改');
    el.textContent = parts.join(' · ');
}

function applyDnsAiSettingsForm(data) {
    data = data || {};
    var keyEl = document.getElementById('setting-dns-ai-api-key');
    var pathEl = document.getElementById('setting-dns-ai-agent-path');
    var proxyEl = document.getElementById('setting-dns-ai-proxy');
    var modelEl = document.getElementById('setting-dns-ai-model');
    var enabledEl = document.getElementById('setting-dns-ai-enabled');
    if (keyEl) keyEl.value = data.cursor_api_key || '';
    if (pathEl) pathEl.value = data.cursor_agent_path || '';
    if (proxyEl) proxyEl.value = data.proxy_url || '';
    if (modelEl) modelEl.value = data.cursor_model || '';
    if (enabledEl) enabledEl.checked = data.enabled !== false;
}

function collectDnsAiSettingsUpdates() {
    var keyEl = document.getElementById('setting-dns-ai-api-key');
    var pathEl = document.getElementById('setting-dns-ai-agent-path');
    var proxyEl = document.getElementById('setting-dns-ai-proxy');
    var modelEl = document.getElementById('setting-dns-ai-model');
    var enabledEl = document.getElementById('setting-dns-ai-enabled');
    return {
        cursor_api_key: keyEl ? keyEl.value.trim() : '',
        cursor_agent_path: pathEl ? pathEl.value.trim() : '',
        proxy_url: proxyEl ? proxyEl.value.trim() : '',
        cursor_model: modelEl ? modelEl.value.trim() : '',
        enabled: enabledEl ? !!enabledEl.checked : true
    };
}

function loadDnsAiSettings() {
    return callApi('get_dns_parse_config', true).then(function (r) {
        if (r && r.success) {
            dnsParseConfigCache = r.data || {};
            applyDnsAiSettingsForm(dnsParseConfigCache);
            _renderDnsParseConfigHint();
        }
        return dnsParseConfigCache;
    }).catch(function () {
        return dnsParseConfigCache || {};
    });
}

function persistSettings() {
    if (!settingsCache) settingsCache = {};
    return callApi('update_settings', settingsCache).then(function (r) {
        if (r && r.success) {
            settingsCache = r.data || settingsCache;
            return true;
        }
        showToast((r && r.message) || '保存失败', 'error');
        return false;
    });
}

function refreshSettingsProfilesUI() {
    ['ali', 'dnspod', 'tencent'].forEach(function (p) {
        renderSettingProfileSelect(p);
        applyProfileToInputs(p);
    });
    renderDnsProfileSelect();
}

function deleteActiveProfile(provider) {
    var pid = _getActiveProfileId(provider);
    if (!pid) { showToast('未选择档案', 'error'); return; }
    showCustomDialog({
        title: '删除档案',
        message: '确定要删除当前档案吗？',
        confirmText: '删除',
        danger: true
    }).then(function (ret) {
        if (!ret.ok) return;
        var list = _getProfiles(provider);
        var next = [];
        list.forEach(function (p) { if (String(p.id) !== String(pid)) next.push(p); });
        if (provider === 'ali') settingsCache.ali_profiles = next;
        if (provider === 'dnspod') settingsCache.dnspod_profiles = next;
        if (provider === 'tencent') settingsCache.tencent_profiles = next;
        _setActiveProfileId(provider, '');
        persistSettings().then(function () {
            refreshSettingsProfilesUI();
            showToast('已删除', 'success');
        });
    });
}

function renderDnsProfileSelect() {
    var sel = document.getElementById('dns-profile-select');
    if (!sel) return;
    if (!dnsCurrentProvider) { sel.style.display = 'none'; return; }
    sel.style.display = '';
    var list = _getProfiles(dnsCurrentProvider);
    var active = _getActiveProfileId(dnsCurrentProvider);
    var html = '<option value="">请选择档案</option>';
    (list || []).forEach(function (p) {
        html += '<option value="' + escapeAttr(p.id) + '">' + escapeHtml(p.name || p.id) + '</option>';
    });
    sel.innerHTML = html;
    sel.value = active || '';
    sel.disabled = !(list && list.length);

    var btnImport = document.getElementById('btn-dns-import');
    if (btnImport) {
        btnImport.disabled = !active;
        btnImport.style.opacity = active ? '1' : '0.6';
        btnImport.style.cursor = active ? 'pointer' : 'not-allowed';
    }
}

function loadPanelData(navId, force) {
    var loader = panelLoaders[navId];
    if (!loader) return;
    if (!force && panelLoadedState[navId]) return;
    panelLoadedState[navId] = true;
    loader();
}

/**
 * 切换面板
 * @param {string} navId - 目标导航 ID
 */
function switchPanel(navId) {
    if (!navMap[navId]) return;
    // 移除旧高亮
    var oldNav = document.getElementById(currentNav);
    if (oldNav) oldNav.classList.remove('active');
    // 隐藏旧面板
    var oldPanel = document.getElementById(navMap[currentNav]);
    if (oldPanel) oldPanel.classList.remove('active');
    // 设置新高亮
    currentNav = navId;
    var newNav = document.getElementById(navId);
    if (newNav) newNav.classList.add('active');
    // 显示新面板
    var newPanel = document.getElementById(navMap[navId]);
    if (newPanel) newPanel.classList.add('active');
    loadPanelData(navId, false);
}

/** 初始化导航事件绑定 */
function initNavigation() {
    Object.keys(navMap).forEach(function (navId) {
        var el = document.getElementById(navId);
        if (el) {
            el.addEventListener('click', function () {
                switchPanel(navId);
            });
        }
    });
}

// ==================== 服务器管理 ====================

/** 服务器列表缓存 */
var serversCache = [];
/** 分组列表缓存 */
var serverGroupsCache = [];

/** 当前选中的分类（空字符串表示全部） */
var currentCategory = '';
/** 主页卡片中每台服务器当前选中的脚本（仅前端态，不自动执行） */
var serverScriptSelections = {};

/**
 * 加载服务器列表
 */
function loadServers() {
    return Promise.all([
        callApi('get_servers'),
        callApi('get_server_groups').catch(function () { return { success: true, data: [] }; })
    ]).then(function (results) {
        var serverResp = results[0];
        var groupResp = results[1];
        if (serverResp && serverResp.success) {
            serversCache = serverResp.data || [];
        }
        if (groupResp && groupResp.success) {
            serverGroupsCache = groupResp.data || [];
        }
        renderCategories();
        renderServers();
        renderGroupSelectOptions('');
    }).catch(function (err) {
        console.error('加载服务器失败:', err);
    });
}

/**
 * 渲染分类筛选栏
 * 从服务器列表中提取所有不重复的 group 值
 */
function renderCategories() {
    var container = document.getElementById('category-list');
    if (!container) return;

    // 提取所有不重复的分组
    var groups = {};
    serversCache.forEach(function (s) {
        var g = (s.group || '').trim();
        if (g) {
            groups[g] = (groups[g] || 0) + 1;
        }
    });

    // 更新"全部"计数
    var allCountEl = document.getElementById('category-all-count');
    if (allCountEl) allCountEl.textContent = serversCache.length;

    // 生成分类项 HTML（保留"全部"项）
    var html = '<div class="category-item' + (currentCategory === '' ? ' active' : '') + '" data-group="" id="category-all">'
        + '<span>全部</span>'
        + '<span class="category-count">' + serversCache.length + '</span>'
        + '</div>';

    var groupNamesMap = {};
    serverGroupsCache.forEach(function (g) {
        var ng = (g || '').trim();
        if (ng) groupNamesMap[ng] = true;
    });
    Object.keys(groups).forEach(function (g) {
        groupNamesMap[g] = true;
    });
    var groupNames = Object.keys(groupNamesMap).sort();
    groupNames.forEach(function (name) {
        var isActive = currentCategory === name;
        var count = groups[name] || 0;
        html += '<div class="category-item' + (isActive ? ' active' : '') + '" data-group="' + escapeAttr(name) + '">'
            + '<span>' + escapeHtml(name) + '</span>'
            + '<span class="category-count">' + count + '</span>'
            + '</div>';
    });

    container.innerHTML = html;

    // 绑定分类点击事件
    container.querySelectorAll('.category-item').forEach(function (item) {
        item.addEventListener('click', function () {
            currentCategory = this.getAttribute('data-group') || '';
            // 更新高亮
            container.querySelectorAll('.category-item').forEach(function (el) {
                el.classList.remove('active');
            });
            this.classList.add('active');
            renderServers();
        });
    });
}

function renderGroupSelectOptions(selectedGroup) {
    var select = document.getElementById('field-group');
    if (!select) return;
    var options = '<option value="">未分组</option>';
    serverGroupsCache.forEach(function (g) {
        var sel = String(g) === String(selectedGroup || '') ? ' selected' : '';
        options += '<option value="' + escapeAttr(g) + '"' + sel + '>' + escapeHtml(g) + '</option>';
    });
    select.innerHTML = options;
}

function addServerGroup() {
    showCustomDialog({
        title: '新增分组',
        message: '请输入新分组名称',
        input: true,
        placeholder: '例如：生产环境'
    }).then(function (ret) {
        if (!ret.ok) return;
        var name = (ret.value || '').trim();
        if (!name) { showToast('分组名称不能为空', 'error'); return; }
        callApi('add_server_group', name).then(function (r) {
            if (r && r.success) {
                serverGroupsCache = r.data || [];
                renderGroupSelectOptions(name);
                renderCategories();
                showToast('分组已新增', 'success');
            } else {
                showToast(r ? r.message : '新增失败', 'error');
            }
        });
    });
}

function renameCurrentServerGroup() {
    var oldName = (currentCategory || '').trim();
    if (!oldName) {
        showToast('“全部”分类不可编辑，请先在左侧选择具体分组', 'error');
        return;
    }
    showCustomDialog({
        title: '编辑分组',
        message: '请输入新的分组名称',
        input: true,
        defaultValue: oldName
    }).then(function (ret) {
        if (!ret.ok) return;
        var newName = (ret.value || '').trim();
        if (!newName) { showToast('分组名称不能为空', 'error'); return; }
        callApi('rename_server_group', oldName, newName).then(function (r) {
            if (r && r.success) {
                serverGroupsCache = r.data || [];
                currentCategory = newName;
                renderGroupSelectOptions(newName);
                loadServers();
                showToast('分组已更新', 'success');
            } else {
                showToast(r ? r.message : '更新失败', 'error');
            }
        });
    });
}

function deleteCurrentServerGroup() {
    var name = (currentCategory || '').trim();
    if (!name) {
        showToast('“全部”分类不可删除，请先在左侧选择具体分组', 'error');
        return;
    }
    showCustomDialog({
        title: '删除分组',
        message: '删除分组后，关联服务器将变为未分组，是否继续？',
        confirmText: '删除',
        danger: true
    }).then(function (ret) {
        if (!ret.ok) return;
        callApi('delete_server_group', name).then(function (r) {
            if (r && r.success) {
                serverGroupsCache = r.data || [];
                currentCategory = '';
                renderGroupSelectOptions('');
                loadServers();
                showToast('分组已删除', 'success');
            } else {
                showToast(r ? r.message : '删除失败', 'error');
            }
        });
    });
}

/**
 * 获取经过搜索和分类过滤后的服务器列表
 * @returns {Array} 过滤后的服务器数组
 */
function getFilteredServers() {
    var searchInput = document.getElementById('server-search');
    var kw = searchInput ? searchInput.value.trim().toLowerCase() : '';

    return serversCache.filter(function (s) {
        // 分类筛选
        if (currentCategory) {
            if ((s.group || '').trim() !== currentCategory) return false;
        }
        // 搜索过滤
        if (kw) {
            var haystack = [(s.name || ''), (s.ip || ''), (s.group || ''), (s.note || '')].join(' ').toLowerCase();
            if (haystack.indexOf(kw) === -1) return false;
        }
        return true;
    });
}

/** 默认「宝塔自动登录」脚本 ID（有宝塔地址但未绑定时使用） */
function getDefaultBtScriptId() {
    for (var i = 0; i < scriptsCache.length; i++) {
        if ((scriptsCache[i].name || '').trim() === '宝塔自动登录') {
            return String(scriptsCache[i].id);
        }
    }
    return scriptsCache.length ? String(scriptsCache[0].id) : '';
}

function resolveServerBindScriptId(server) {
    var bind = String((server && server.bind_script) || '').trim();
    if (bind) {
        var found = scriptsCache.some(function (sc) { return String(sc.id) === bind; });
        return found ? bind : getDefaultBtScriptId();
    }
    if (server && server.bt_url && String(server.bt_url).trim()) {
        return getDefaultBtScriptId();
    }
    return '';
}

/**
 * 渲染服务器卡片列表
 */
function renderServers() {
    var container = document.getElementById('server-list');
    if (!container) return;

    var servers = getFilteredServers();

    if (servers.length === 0) {
        container.innerHTML = '<div class="empty-state">'
            + '<svg viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>'
            + '<div class="text">暂无服务器，点击上方按钮添加</div>'
            + '</div>';
        return;
    }

    var html = '';
    servers.forEach(function (s) {
        var hasBt = s.bt_url && s.bt_url.trim();

        html += '<div class="server-card" data-id="' + s.id + '">'
            // 卡片头部：名称 + 分组标签
            + '<div class="server-card-header">'
            + '<span class="server-name">' + escapeHtml(s.name) + '</span>'
            + (s.group ? '<span class="server-group">' + escapeHtml(s.group) + '</span>' : '')
            + '</div>'
            // meta 行：宝塔地址
            + '<div class="server-meta">'
            + (hasBt
                ? '<span class="server-meta-item"><span class="label">宝塔</span><span class="value">' + escapeHtml(s.bt_url) + '</span>'
                    + '<button class="btn btn-icon" title="复制宝塔地址" onclick="copyTextToClipboard(\'' + escapeAttr(s.bt_url) + '\', \'已复制宝塔地址\')">'
                    + '<svg viewBox="0 0 24 24" width="16" height="16"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
                    + '</button></span>'
                : '')
            + '</div>'
            // 备注
            + (s.note ? '<div class="server-note">' + escapeHtml(s.note) + '</div>' : '')
            // 操作按钮
            + '<div class="server-actions">';

        var effectiveBindScript = resolveServerBindScriptId(s);

        // 宝塔登录按钮（执行绑定脚本，未绑定时默认宝塔自动登录）
        if (hasBt) {
            html += '<button class="btn btn-icon" title="执行绑定脚本" onclick="runServerScript(\'' + s.id + '\', \'' + escapeAttr(effectiveBindScript) + '\')">'
                + '<svg viewBox="0 0 24 24" width="16" height="16"><polygon points="5 3 19 12 5 21 5 3"/></svg>'
                + '</button>';
        }

        // 脚本下拉仅选择，不自动执行；点击执行按钮后才真正运行
        var selectedScriptId = String(serverScriptSelections[s.id] || effectiveBindScript || '');
        html += '<select class="server-script-select" onchange="onServerScriptSelectionChange(\'' + s.id + '\', this.value)" title="选择脚本（不会自动执行）">'
            + '<option value="">选择脚本</option>';
        scriptsCache.forEach(function (sc) {
            var selected = String(sc.id) === selectedScriptId ? ' selected' : '';
            html += '<option value="' + sc.id + '"' + selected + '>' + escapeHtml(sc.name) + '</option>';
        });
        html += '</select>'
            + '<button class="btn btn-icon" title="执行已选脚本" onclick="runSelectedServerScript(\'' + s.id + '\')">'
            + '<svg viewBox="0 0 24 24" width="16" height="16"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>'
            + '</button>';

        // 分隔线
        html += '<span class="action-divider"></span>';

        // 编辑按钮
        html += '<button class="btn btn-icon" title="编辑" onclick="editServer(\'' + s.id + '\')">'
            + '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>'
            + '</button>';

        // 删除按钮
        html += '<button class="btn btn-icon btn-icon-danger" title="删除" onclick="confirmDeleteServer(\'' + s.id + '\')">'
            + '<svg viewBox="0 0 24 24" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'
            + '</button>';

        html += '</div></div>';
    });

    container.innerHTML = html;
}

function onServerScriptSelectionChange(serverId, scriptId) {
    serverScriptSelections[String(serverId || '')] = String(scriptId || '');
}

function runSelectedServerScript(serverId) {
    var sid = String(serverId || '');
    var selectedScriptId = String(serverScriptSelections[sid] || '');
    if (!selectedScriptId) {
        showToast('请先选择脚本', 'info');
        return;
    }
    runServerScript(sid, selectedScriptId);
}

/**
 * 打开添加服务器模态框
 */
function openAddServerModal() {
    var editIdField = document.getElementById('edit-server-id');
    if (editIdField) editIdField.value = '';
    // 清空表单
    ['field-name', 'field-bt-url', 'field-bt-user', 'field-bt-pass', 'field-group', 'field-note', 'field-bt-redirect'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    var title = document.getElementById('server-modal-title');
    if (title) title.textContent = '添加服务器';
    renderGroupSelectOptions('');
    // 加载脚本列表到绑定脚本下拉框
    loadBindScriptOptions('');
    showModal('server-modal');
}

/**
 * 编辑服务器
 * @param {string} id - 服务器 ID
 */
function editServer(id) {
    var server = null;
    for (var i = 0; i < serversCache.length; i++) {
        if (String(serversCache[i].id) === String(id)) { server = serversCache[i]; break; }
    }
    if (!server) { showToast('未找到服务器', 'error'); return; }
    document.getElementById('edit-server-id').value = server.id;
    document.getElementById('field-name').value = server.name || '';
    document.getElementById('field-bt-url').value = server.bt_url || '';
    document.getElementById('field-bt-user').value = server.bt_user || '';
    document.getElementById('field-bt-pass').value = server.bt_pass || '';
    renderGroupSelectOptions(server.group || '');
    document.getElementById('field-note').value = server.note || '';
    document.getElementById('field-bt-redirect').value = server.bt_redirect || '';
    var title = document.getElementById('server-modal-title');
    if (title) title.textContent = '编辑服务器';
    // 加载脚本列表并选中已绑定的脚本
    loadBindScriptOptions(server.bind_script || '');
    showModal('server-modal');
}

/**
 * 加载绑定脚本下拉选项
 * @param {string} selectedId - 当前选中的脚本 ID
 */
function loadBindScriptOptions(selectedId) {
    var select = document.getElementById('field-bind-script');
    if (!select) return;
    // 先用缓存填充，如果缓存为空则从 API 获取
    var html = '<option value="">不绑定脚本</option>';
    scriptsCache.forEach(function (s) {
        var sel = String(s.id) === String(selectedId) ? ' selected' : '';
        html += '<option value="' + s.id + '"' + sel + '>' + escapeHtml(s.name) + '</option>';
    });
    select.innerHTML = html;

    // 如果缓存为空，尝试从 API 加载
    if (scriptsCache.length === 0) {
        callApi('get_scripts').then(function (response) {
            if (response && response.success) {
                scriptsCache = response.data || [];
                var html2 = '<option value="">不绑定脚本</option>';
                scriptsCache.forEach(function (s) {
                    var sel = String(s.id) === String(selectedId) ? ' selected' : '';
                    html2 += '<option value="' + s.id + '"' + sel + '>' + escapeHtml(s.name) + '</option>';
                });
                select.innerHTML = html2;
            }
        }).catch(function () {});
    }
}

/**
 * 从 URL 中提取 IP 地址
 * @param {string} url - URL 字符串
 * @returns {string} IP 地址
 */
function extractIpFromUrl(url) {
    if (!url) return '';
    try {
        // 去掉协议
        var clean = url.replace(/^https?:\/\//, '');
        // 取 host:port 部分
        var hostPart = clean.split('/')[0];
        // 去掉端口
        var host = hostPart.split(':')[0];
        return host;
    } catch (e) {
        return '';
    }
}

/**
 * 提交服务器表单（添加或编辑）
 */
function submitServerForm() {
    var name = document.getElementById('field-name').value.trim();
    var btUrl = document.getElementById('field-bt-url').value.trim();
    if (!name) { showToast('请输入服务器名称', 'error'); return; }

    var ip = extractIpFromUrl(btUrl);

    var bindScript = document.getElementById('field-bind-script').value || '';
    if (!bindScript && btUrl) {
        bindScript = getDefaultBtScriptId();
    }

    var data = {
        name: name,
        ip: ip,
        port: '22',
        bt_url: btUrl,
        bt_user: document.getElementById('field-bt-user').value.trim(),
        bt_pass: document.getElementById('field-bt-pass').value.trim(),
        group: document.getElementById('field-group').value.trim(),
        bind_script: bindScript,
        bt_redirect: document.getElementById('field-bt-redirect').value.trim(),
        note: document.getElementById('field-note').value.trim()
    };

    var editId = document.getElementById('edit-server-id').value;
    if (editId) {
        callApi('update_server', editId, data).then(function (r) {
            if (r && r.success) { showToast('更新成功', 'success'); hideModal('server-modal'); loadServers(); }
            else showToast('更新失败', 'error');
        });
    } else {
        callApi('add_server', data).then(function (r) {
            if (r && r.success) { showToast('添加成功', 'success'); hideModal('server-modal'); loadServers(); }
            else showToast('添加失败', 'error');
        });
    }
}

/**
 * 确认并删除服务器
 * @param {string} id - 服务器 ID
 */
function confirmDeleteServer(id) {
    showCustomDialog({
        title: '删除服务器',
        message: '确定要删除该服务器吗？',
        confirmText: '删除',
        danger: true
    }).then(function (ret) {
        if (!ret.ok) return;
        callApi('delete_server', id).then(function (r) {
            if (r && r.success) { showToast('已删除', 'success'); loadServers(); }
        });
    });
}

/**
 * 运行服务器绑定的脚本
 * @param {string} serverId - 服务器 ID
 * @param {string} scriptId - 脚本 ID
 */
function runServerScript(serverId, scriptId) {
    var server = null;
    for (var si = 0; si < serversCache.length; si++) {
        if (String(serversCache[si].id) === String(serverId)) { server = serversCache[si]; break; }
    }

    showToast('开始执行，实时日志在底部“运行日志（全局）”查看', 'info');
    callApi('run_server_script', String(serverId || ''), String(scriptId || '')).then(function (r) {
        if (r && r.success) {
            var runId = extractRunId(r);
            if (runId) startPollingScriptLog(runId, { openDrawer: false });
            else {
                showToast('未获取到 run_id，正在自动发现运行任务', 'info');
                discoverScriptRuns();
            }
        } else {
            showToast('执行失败: ' + (r ? r.message : '未知错误'), 'error');
        }
    }).catch(function (err) {
        showToast('执行出错: ' + err.message, 'error');
    });
}

/** 初始化服务器搜索功能 */
function initServerSearch() {
    var searchInput = document.getElementById('server-search');
    if (!searchInput) return;
    searchInput.addEventListener('input', function () {
        renderServers();
    });
}

/** 初始化服务器管理模块 */
function initServerModule() {
    document.getElementById('btn-add-server').addEventListener('click', openAddServerModal);
    document.getElementById('btn-save-server').addEventListener('click', submitServerForm);
    document.getElementById('btn-cancel-server').addEventListener('click', function () { hideModal('server-modal'); });
    document.getElementById('btn-close-server-modal').addEventListener('click', function () { hideModal('server-modal'); });
    document.getElementById('btn-add-group').addEventListener('click', addServerGroup);
    document.getElementById('btn-rename-group').addEventListener('click', renameCurrentServerGroup);
    document.getElementById('btn-delete-group').addEventListener('click', deleteCurrentServerGroup);
    initServerSearch();
}

// ==================== 脚本工具 ====================

/** 脚本列表缓存 */
var scriptsCache = [];

/** 当前正在编辑的脚本 ID（空字符串表示新建） */
var editingScriptId = '';

/**
 * 加载脚本列表
 */
function loadScripts() {
    return callApi('get_scripts').then(function (response) {
        if (response && response.success) {
            scriptsCache = response.data || [];
            renderScripts();
            if (currentNav === 'nav-servers') {
                renderServers();
            }
        }
    }).catch(function (err) {
        console.error('加载脚本失败:', err);
    });
}

/**
 * 渲染脚本标签列表
 */
function renderScripts() {
    var container = document.getElementById('script-list');
    if (!container) return;
    if (scriptsCache.length === 0) {
        container.innerHTML = '<span style="font-size:12px;color:var(--text-muted)">暂无保存的脚本</span>';
        return;
    }
    var html = '';
    scriptsCache.forEach(function (s) {
        var isActive = editingScriptId && String(editingScriptId) === String(s.id);
        html += '<div class="script-tag' + (isActive ? ' active' : '') + '" data-id="' + s.id + '" onclick="editScript(\'' + s.id + '\')">'
            + '<span class="script-tag-type">Py</span>'
            + escapeHtml(s.name)
            + '<button class="script-tag-delete" onclick="event.stopPropagation();confirmDeleteScript(\'' + s.id + '\')" title="删除">'
            + '<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
            + '</button>'
            + '</div>';
    });
    container.innerHTML = html;
}

/**
 * 新建脚本（清空编辑区）
 */
function newScript() {
    editingScriptId = '';
    document.getElementById('script-name').value = '';
    document.getElementById('script-code').value = '';
    document.getElementById('script-output').value = '';
    // 取消所有标签高亮
    document.querySelectorAll('.script-tag').forEach(function (tag) {
        tag.classList.remove('active');
    });
    // 聚焦到名称输入框
    document.getElementById('script-name').focus();
}

/**
 * 编辑已有脚本
 * @param {string} id - 脚本 ID
 */
function editScript(id) {
    var script = null;
    for (var i = 0; i < scriptsCache.length; i++) {
        if (String(scriptsCache[i].id) === String(id)) { script = scriptsCache[i]; break; }
    }
    if (!script) return;
    editingScriptId = String(id);
    document.getElementById('script-name').value = script.name || '';
    document.getElementById('script-code').value = script.code || '';
    document.getElementById('script-output').value = '';
    // 高亮当前标签
    document.querySelectorAll('.script-tag').forEach(function (tag) {
        tag.classList.toggle('active', tag.getAttribute('data-id') === String(id));
    });
}

/**
 * 确认删除脚本
 * @param {string} id - 脚本 ID
 */
function confirmDeleteScript(id) {
    showCustomDialog({
        title: '删除脚本',
        message: '确定要删除该脚本吗？',
        confirmText: '删除',
        danger: true
    }).then(function (ret) {
        if (!ret.ok) return;
        callApi('delete_script', id).then(function (r) {
            if (r && r.success) {
                showToast('已删除', 'success');
                if (editingScriptId === String(id)) {
                    editingScriptId = '';
                    document.getElementById('script-code').value = '';
                    document.getElementById('script-name').value = '';
                }
                loadScripts();
            }
        });
    });
}

/**
 * 保存当前脚本
 */
function saveScript() {
    var name = document.getElementById('script-name').value.trim();
    var code = document.getElementById('script-code').value;
    if (!name) { showToast('请输入脚本名称', 'error'); return; }
    if (!code.trim()) { showToast('请输入脚本代码', 'error'); return; }

    var data = { name: name, type: 'python', code: code };

    if (editingScriptId) {
        callApi('update_script', editingScriptId, data).then(function (r) {
            if (r && r.success) { showToast('保存成功', 'success'); loadScripts(); }
            else showToast('保存失败', 'error');
        });
    } else {
        callApi('add_script', data).then(function (r) {
            if (r && r.success) {
                showToast('保存成功', 'success');
                if (r.data && r.data.id) editingScriptId = String(r.data.id);
                loadScripts();
            } else {
                showToast('保存失败', 'error');
            }
        });
    }
}

/**
 * 执行当前 Python 脚本
 */
function runScript() {
    var codeEl = document.getElementById('script-code');
    var outputEl = document.getElementById('script-output');
    if (!codeEl || !outputEl) return;
    var code = codeEl.value;
    if (!code.trim()) { showToast('请输入脚本代码', 'error'); return; }

    // 清空输出区
    outputEl.value = '';
    showToast('脚本开始执行...', 'info');

    // 使用实时日志 API（后端缓存 + 轮询确保显示）
    callApi('run_python_script_with_log', code).then(function (r) {
        if (r && r.success) {
            var runId = extractRunId(r);
            if (runId) startPollingScriptLog(runId, { openDrawer: false });
            else {
                showToast('未获取到 run_id，正在自动发现运行任务', 'info');
                discoverScriptRuns();
            }
        } else {
            outputEl.value += '\n[错误] ' + (r ? r.message : '未知错误') + '\n';
            showToast('执行失败', 'error');
        }
    }).catch(function (err) {
        outputEl.value += '\n[错误] ' + (err.message || '未知错误') + '\n';
        showToast('执行出错', 'error');
    });
}

// ==================== 脚本日志轮询（强一致显示） ====================
var __scriptLogPollingTimer = null;
var __scriptRunDiscoveryTimer = null;
var __scriptLogRunId = '';
var __scriptLogSeq = 0;
var __scriptLogPollFailedOnce = false;
var __seenScriptRuns = {};

function extractRunId(resp) {
    if (!resp) return '';
    if (typeof resp === 'string') {
        try {
            var parsedResp = JSON.parse(resp);
            return extractRunId(parsedResp);
        } catch (e0) {}
    }
    if (resp.run_id) return String(resp.run_id);
    if (resp.data && typeof resp.data === 'object' && resp.data.run_id) return String(resp.data.run_id);
    if (resp.data && typeof resp.data === 'string') {
        try {
            var obj = JSON.parse(resp.data);
            if (obj && obj.run_id) return String(obj.run_id);
        } catch (e) {}
    }
    return '';
}

function startPollingScriptLog(runId, options) {
    options = options || {};
    __scriptLogRunId = String(runId || '');
    if (!__scriptLogRunId) return;
    __seenScriptRuns[__scriptLogRunId] = true;
    __scriptLogSeq = 0;
    __scriptLogPollFailedOnce = false;
    if (__scriptLogPollingTimer) {
        clearInterval(__scriptLogPollingTimer);
        __scriptLogPollingTimer = null;
    }
    var openDrawer = options.openDrawer === true;
    if (window.__appendScriptLogLine) {
        window.__appendScriptLogLine(
            '[INFO] 日志轮询已启动 run_id=' + __scriptLogRunId + '\n',
            { openDrawer: openDrawer }
        );
    }
    // 立即拉一次
    pollScriptLogOnce();
    __scriptLogPollingTimer = setInterval(pollScriptLogOnce, 350);
}

function initScriptRunDiscovery() {
    if (__scriptRunDiscoveryTimer) return;
    discoverScriptRuns();
    __scriptRunDiscoveryTimer = setInterval(discoverScriptRuns, 1200);
}

function discoverScriptRuns() {
    callApi('list_script_runs', 10).then(function (r) {
        if (typeof r === 'string') {
            try { r = JSON.parse(r); } catch (eJson) {}
        }
        if (!r || !r.success || !Array.isArray(r.data)) return;
        if (!r.data.length) return;
        var latest = null;
        for (var i = 0; i < r.data.length; i++) {
            var item = r.data[i] || {};
            var meta = item.meta || {};
            if ((meta.kind || '') === 'dns_ai_parse') continue;
            latest = item;
            break;
        }
        if (!latest) return;
        var rid = latest.run_id ? String(latest.run_id) : '';
        if (!rid) return;
        if (!__seenScriptRuns[rid]) {
            __seenScriptRuns[rid] = true;
            var meta2 = latest.meta || {};
            var source = meta2.source || '';
            if (rid !== __scriptLogRunId && rid !== dnsImportAiHandledRunId && rid !== dnsImportAiActiveRunId) {
                startPollingScriptLog(rid, { openDrawer: false });
            }
        }
    }).catch(function () {});
}

function pollScriptLogOnce() {
    if (!__scriptLogRunId) return;
    callApi('poll_script_log', __scriptLogRunId, __scriptLogSeq, 400).then(function (r) {
        if (typeof r === 'string') {
            try { r = JSON.parse(r); } catch (eJson) {}
        }
        if (!r || !r.success || !r.data) {
            if (!__scriptLogPollFailedOnce) {
                __scriptLogPollFailedOnce = true;
                showToast('日志同步失败（轮询无响应），请重启应用后再试', 'error');
            }
            return;
        }
        var lines = r.data.lines || [];
        for (var i = 0; i < lines.length; i++) {
            if (window.__appendScriptLogLine) window.__appendScriptLogLine(lines[i]);
        }
        __scriptLogSeq = r.data.next_seq || __scriptLogSeq;
        if (r.data.done) {
            clearInterval(__scriptLogPollingTimer);
            __scriptLogPollingTimer = null;
            __scriptLogRunId = '';
        }
    }).catch(function (e) {
        if (!__scriptLogPollFailedOnce) {
            __scriptLogPollFailedOnce = true;
            showToast('日志同步异常：' + (e && e.message ? e.message : '未知错误'), 'error');
        }
    });
}

/** 初始化脚本工具模块 */
function initScriptsModule() {
    // 新建脚本
    document.getElementById('btn-add-script').addEventListener('click', newScript);
    // 保存脚本
    document.getElementById('btn-save-script').addEventListener('click', saveScript);
    // 执行脚本
    document.getElementById('btn-run-script').addEventListener('click', runScript);
    // 清空输出
    document.getElementById('btn-clear-output').addEventListener('click', function () {
        document.getElementById('script-output').value = '';
    });
    initScriptRunDiscovery();
}

// ==================== DNS 管理 ====================

var dnsCurrentProvider = '';
var dnsCurrentDomain = '';
var dnsCurrentZoneId = '';
var dnsDomainsCache = [];
var dnsRecordsPage = 1;
var dnsRecordsPageSize = 50;
var dnsRecordsTotal = 0;
/** @type {Object.<string, Array<{type:string,rr:string,value:string}>>} */
var dnsExistingRecordsCache = {};

function initDnsModule() {
    // 服务商卡片点击
    document.querySelectorAll('.dns-provider-card').forEach(function (card) {
        card.addEventListener('click', function () {
            var provider = this.getAttribute('data-provider');
            selectDnsProvider(provider);
        });
    });
    // 刷新域名
    document.getElementById('btn-dns-refresh-domains').addEventListener('click', function () {
        if (dnsCurrentProvider) loadDnsDomains(dnsCurrentProvider);
    });
    // 刷新记录
    document.getElementById('btn-dns-refresh-records').addEventListener('click', function () {
        if (dnsCurrentProvider && dnsCurrentDomain) loadDnsRecords();
    });
    // 分页
    document.getElementById('btn-dns-prev-page').addEventListener('click', function () {
        if (dnsRecordsPage <= 1) return;
        dnsRecordsPage -= 1;
        loadDnsRecords();
    });
    document.getElementById('btn-dns-next-page').addEventListener('click', function () {
        var totalPages = Math.max(1, Math.ceil(dnsRecordsTotal / dnsRecordsPageSize));
        if (dnsRecordsPage >= totalPages) return;
        dnsRecordsPage += 1;
        loadDnsRecords();
    });
    document.getElementById('dns-records-page-size').addEventListener('change', function () {
        var nextSize = parseInt(this.value, 10) || 50;
        dnsRecordsPageSize = nextSize;
        dnsRecordsPage = 1;
        if (dnsCurrentProvider && dnsCurrentDomain) loadDnsRecords();
    });
    // 添加记录
    document.getElementById('btn-dns-add-record').addEventListener('click', openDnsAddModal);
    // 保存记录
    document.getElementById('btn-save-dns').addEventListener('click', submitDnsRecord);
    // 取消/关闭
    document.getElementById('btn-cancel-dns').addEventListener('click', function () { hideModal('dns-record-modal'); });
    document.getElementById('btn-close-dns-modal').addEventListener('click', function () { hideModal('dns-record-modal'); });
    // 记录类型切换 → 动态显示/隐藏字段
    document.getElementById('dns-field-type').addEventListener('change', onDnsTypeChange);
    // 快速导入
    document.getElementById('btn-dns-import').addEventListener('click', openDnsImportModal);
    document.getElementById('btn-close-dns-import-modal').addEventListener('click', closeDnsImportModal);
    document.getElementById('btn-dns-paste-clipboard-image').addEventListener('click', loadDnsImportClipboardImage);
    document.getElementById('btn-dns-import-pick-image').addEventListener('click', function () {
        var fileInput = document.getElementById('dns-import-file-input');
        if (fileInput) fileInput.click();
    });
    document.getElementById('dns-import-file-input').addEventListener('change', function (e) {
        var files = e.target && e.target.files;
        if (files && files.length) _readDnsImportImageFile(files[0], '本地图片');
        e.target.value = '';
    });
    document.getElementById('btn-dns-import-clear-image').addEventListener('click', clearDnsImportImage);
    document.getElementById('btn-dns-import-parse').addEventListener('click', runDnsImportParse);
    document.getElementById('btn-dns-import-back').addEventListener('click', backToDnsImportStep1);
    document.getElementById('btn-dns-import-confirm').addEventListener('click', confirmDnsImport);
    var dnsImportText = document.getElementById('dns-import-text');
    if (dnsImportText) {
        dnsImportText.addEventListener('paste', onDnsImportPaste);
    }
    initDnsImportDragDrop();
    _flushPendingDnsImportCallbacks();
}

function loadDnsProviders() {
    ensureSettingsLoaded(false).then(function () {
    callApi('dns_get_providers').then(function (r) {
        if (!r || !r.success) return;
        var data = r.data;
        ['ali', 'dnspod', 'tencent'].forEach(function (p) {
            var statusEl = document.getElementById('dns-status-' + p);
            if (statusEl) {
                if (data[p]) {
                    statusEl.textContent = '已配置';
                    statusEl.classList.add('configured');
                } else {
                    statusEl.textContent = '未配置';
                    statusEl.classList.remove('configured');
                }
            }
        });
    });
    });
}

function selectDnsProvider(provider) {
    selectDnsProviderAsync(provider, { silentProfileError: false });
}

function selectDnsProviderAsync(provider, options) {
    options = options || {};
    dnsCurrentProvider = provider;
    if (!options.keepDomain) {
        dnsCurrentDomain = '';
        dnsCurrentZoneId = '';
    }
    document.querySelectorAll('.dns-provider-card').forEach(function (c) {
        c.classList.toggle('active', c.getAttribute('data-provider') === provider);
    });
    document.getElementById('dns-domain-section').style.display = 'block';
    if (!options.keepDomain) {
        document.getElementById('dns-records-section').style.display = 'none';
    }
    return ensureSettingsLoaded(false).then(function () {
        renderDnsProfileSelect();
        if (!_getActiveProfileId(provider)) {
            if (!options.silentProfileError) {
                showToast('请先选择该服务商的密钥档案', 'error');
            }
            document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--text-muted)">请先选择密钥档案</span>';
            return false;
        }
        return loadDnsDomainsAsync(provider);
    });
}

function loadDnsDomainsAsync(provider) {
    document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--text-muted)">加载中...</span>';
    return callApi('dns_get_domains', provider).then(function (r) {
        if (!r || !r.success) {
            document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--accent-red)">加载失败: ' + (r ? r.message : '') + '</span>';
            return false;
        }
        dnsDomainsCache = r.data || [];
        if (dnsDomainsCache.length === 0) {
            document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--text-muted)">暂无域名</span>';
            return true;
        }
        var html = '';
        dnsDomainsCache.forEach(function (d) {
            html += '<div class="dns-domain-tag" data-domain="' + escapeAttr(d.DomainName) + '" data-zone-id="' + escapeAttr(d.DomainId || '') + '" onclick="selectDnsDomain(this)">'
                + escapeHtml(d.DomainName) + '</div>';
        });
        document.getElementById('dns-domain-list').innerHTML = html;
        return true;
    }).catch(function () {
        document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--accent-red)">请求失败</span>';
        return false;
    });
}

function loadDnsDomains(provider) {
    loadDnsDomainsAsync(provider);
}

function _activateDnsDomainTag(domain) {
    if (!domain) return false;
    var tags = document.querySelectorAll('.dns-domain-tag');
    var found = false;
    tags.forEach(function (el) {
        var match = String(el.getAttribute('data-domain') || '').toLowerCase() === String(domain).toLowerCase();
        el.classList.toggle('active', match);
        if (match) {
            found = true;
            dnsCurrentDomain = el.getAttribute('data-domain');
            dnsCurrentZoneId = el.getAttribute('data-zone-id') || '';
            document.getElementById('dns-records-section').style.display = 'block';
            document.getElementById('dns-current-domain').textContent = dnsCurrentDomain;
        }
    });
    return found;
}

function autoApplyDnsProviderForDomain(domain) {
    domain = String(domain || '').trim();
    if (!domain) return Promise.resolve(false);
    return callApi('dns_detect_provider', domain).then(function (r) {
        if (!r || !r.success) {
            showToast((r && r.message) || '识别服务商失败', 'error');
            return false;
        }
        var data = r.data || {};
        var provider = data.provider || '';
        if (!provider) {
            showToast(data.message || '未能自动识别服务商，请手动选择', 'info');
            if (data.ns_servers && data.ns_servers.length) {
                _appendGlobalLog('[DNS导入] NS: ' + data.ns_servers.join(', ') + '\n');
            }
            return false;
        }
        var label = provider === 'ali' ? '阿里云' : provider === 'dnspod' ? 'DNSPod' : '腾讯云';
        var via = data.matched_by === 'domain_list' ? '域名列表' : (data.matched_by === 'ns_guess' ? 'NS 推测' : '');
        _appendGlobalLog('[DNS导入] 自动识别服务商: ' + label + (via ? ('（' + via + '）') : '') + ' → ' + domain + '\n');
        return selectDnsProviderAsync(provider, { silentProfileError: true, keepDomain: true }).then(function (ok) {
            if (!ok) {
                showToast('已识别为 ' + label + '，请先配置并选择密钥档案', 'info');
                return false;
            }
            if (!_activateDnsDomainTag(domain)) {
                showToast('服务商 ' + label + ' 下未找到域名 ' + domain + '，请确认档案或手动选择', 'info');
            } else {
                showToast('已识别服务商 ' + label + '，域名 ' + domain, 'success');
            }
            return true;
        });
    });
}

function ensureDnsProviderForImportRecords(records) {
    var domain = '';
    (records || []).some(function (rec) {
        var d = String(rec.domain || '').trim();
        if (d) {
            domain = d;
            return true;
        }
        return false;
    });
    if (!domain) return Promise.resolve();
    if (dnsCurrentProvider && dnsCurrentDomain && dnsCurrentDomain.toLowerCase() === domain.toLowerCase()) {
        return Promise.resolve();
    }
    if (dnsCurrentProvider && !dnsCurrentDomain) {
        return autoApplyDnsProviderForDomain(domain);
    }
    if (!dnsCurrentProvider) {
        return autoApplyDnsProviderForDomain(domain);
    }
    if (dnsCurrentDomain && dnsCurrentDomain.toLowerCase() !== domain.toLowerCase()) {
        return autoApplyDnsProviderForDomain(domain);
    }
    return Promise.resolve();
}

function loadDnsDomains(provider) {
    document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--text-muted)">加载中...</span>';
    callApi('dns_get_domains', provider).then(function (r) {
        if (!r || !r.success) {
            document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--accent-red)">加载失败: ' + (r ? r.message : '') + '</span>';
            return;
        }
        dnsDomainsCache = r.data || [];
        if (dnsDomainsCache.length === 0) {
            document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--text-muted)">暂无域名</span>';
            return;
        }
        var html = '';
        dnsDomainsCache.forEach(function (d) {
            html += '<div class="dns-domain-tag" data-domain="' + escapeAttr(d.DomainName) + '" data-zone-id="' + escapeAttr(d.DomainId || '') + '" onclick="selectDnsDomain(this)">'
                + escapeHtml(d.DomainName) + '</div>';
        });
        document.getElementById('dns-domain-list').innerHTML = html;
    }).catch(function () {
        document.getElementById('dns-domain-list').innerHTML = '<span style="font-size:12px;color:var(--accent-red)">请求失败</span>';
    });
}

function selectDnsDomain(el) {
    dnsCurrentDomain = el.getAttribute('data-domain');
    dnsCurrentZoneId = el.getAttribute('data-zone-id');
    dnsRecordsPage = 1;
    dnsRecordsTotal = 0;
    document.querySelectorAll('.dns-domain-tag').forEach(function (t) { t.classList.remove('active'); });
    el.classList.add('active');
    // 显示记录区
    document.getElementById('dns-records-section').style.display = 'block';
    document.getElementById('dns-current-domain').textContent = dnsCurrentDomain;
    loadDnsRecords();
}

function _normalizeDnsRrForCompare(rr) {
    var r = String(rr || '').trim().toLowerCase();
    return r === '' ? '@' : r;
}

function _normalizeDnsValueForCompare(value) {
    var v = String(value || '').trim();
    if (v.length >= 2 && ((v[0] === '"' && v[v.length - 1] === '"') || (v[0] === "'" && v[v.length - 1] === "'"))) {
        v = v.slice(1, -1);
    }
    return v;
}

function _dnsRecordCompareKey(domain, type, rr, value) {
    return [
        String(domain || '').trim().toLowerCase(),
        String(type || '').trim().toUpperCase(),
        _normalizeDnsRrForCompare(rr),
        _normalizeDnsValueForCompare(value)
    ].join('|');
}

function _zoneIdForDomain(domain) {
    if (dnsCurrentDomain && domain === dnsCurrentDomain && dnsCurrentZoneId) {
        return dnsCurrentZoneId;
    }
    var found = null;
    (dnsDomainsCache || []).forEach(function (d) {
        if (!found && d && String(d.DomainName).toLowerCase() === String(domain || '').toLowerCase()) {
            found = d;
        }
    });
    return (found && found.DomainId) || '';
}

function fetchAllDnsRecordsForDomain(domain, zoneId) {
    if (!dnsCurrentProvider || !domain) {
        return Promise.resolve([]);
    }
    var page = 1;
    var pageSize = 500;
    var all = [];

    function fetchPage() {
        return callApi('dns_get_records', dnsCurrentProvider, domain, zoneId || '', page, pageSize).then(function (r) {
            if (!r || !r.success) {
                return Promise.reject(new Error((r && r.message) || '加载现有记录失败'));
            }
            var payload = r.data || {};
            var records = payload.records || [];
            var pg = payload.pagination || {};
            records.forEach(function (rec) {
                all.push({
                    type: String(rec.Type || '').toUpperCase(),
                    rr: _normalizeDnsRrForCompare(rec.RR),
                    value: String(rec.Value || '').trim()
                });
            });
            var total = parseInt(pg.total, 10) || all.length;
            var totalPages = Math.max(1, Math.ceil(total / pageSize));
            if (page < totalPages) {
                page += 1;
                return fetchPage();
            }
            return all;
        });
    }

    return fetchPage();
}

function ensureDnsExistingRecordsForImport(records) {
    var domains = {};
    (records || []).forEach(function (rec) {
        var d = String(rec.domain || '').trim();
        if (!d && dnsCurrentDomain) d = dnsCurrentDomain;
        if (d) domains[d.toLowerCase()] = d;
    });
    if (!Object.keys(domains).length && dnsCurrentDomain) {
        domains[dnsCurrentDomain.toLowerCase()] = dnsCurrentDomain;
    }
    var list = Object.keys(domains).map(function (k) { return domains[k]; });
    if (!list.length) {
        return Promise.resolve({});
    }
    return Promise.all(list.map(function (domain) {
        var cacheKey = domain.toLowerCase();
        if (dnsExistingRecordsCache[cacheKey]) {
            return Promise.resolve({ domain: domain, records: dnsExistingRecordsCache[cacheKey] });
        }
        return fetchAllDnsRecordsForDomain(domain, _zoneIdForDomain(domain)).then(function (rows) {
            dnsExistingRecordsCache[cacheKey] = rows;
            return { domain: domain, records: rows };
        });
    })).then(function (pairs) {
        var keySetByDomain = {};
        pairs.forEach(function (p) {
            var set = {};
            (p.records || []).forEach(function (row) {
                set[_dnsRecordCompareKey(p.domain, row.type, row.rr, row.value)] = true;
            });
            keySetByDomain[p.domain.toLowerCase()] = set;
        });
        return keySetByDomain;
    });
}

function isDnsImportRecordDuplicate(rec, existingKeySetByDomain) {
    var domain = String(rec.domain || dnsCurrentDomain || '').trim();
    if (!domain) return false;
    var set = existingKeySetByDomain[domain.toLowerCase()];
    if (!set) return false;
    return !!set[_dnsRecordCompareKey(domain, rec.type, rec.rr, rec.value)];
}

function invalidateDnsExistingRecordsCache(domain) {
    if (domain) {
        delete dnsExistingRecordsCache[String(domain).toLowerCase()];
        return;
    }
    dnsExistingRecordsCache = {};
}

function loadDnsRecords() {
    var tbody = document.getElementById('dns-records-body');
    var pageBar = document.getElementById('dns-records-pagination');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px">加载中...</td></tr>';
    if (pageBar) pageBar.style.display = 'none';
    callApi('dns_get_records', dnsCurrentProvider, dnsCurrentDomain, dnsCurrentZoneId, dnsRecordsPage, dnsRecordsPageSize).then(function (r) {
        if (!r || !r.success) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--accent-red)">' + (r ? r.message : '加载失败') + '</td></tr>';
            renderDnsRecordsPagination(0, dnsRecordsPage, dnsRecordsPageSize);
            return;
        }
        var payload = r.data || {};
        var records = payload.records || [];
        var pg = payload.pagination || {};
        dnsRecordsPage = parseInt(pg.page, 10) || dnsRecordsPage;
        dnsRecordsPageSize = parseInt(pg.page_size, 10) || dnsRecordsPageSize;
        dnsRecordsTotal = parseInt(pg.total, 10) || records.length;

        // 删除等场景下可能出现“超出最后一页”，自动回退一页重载。
        if (records.length === 0 && dnsRecordsTotal > 0 && dnsRecordsPage > 1) {
            dnsRecordsPage -= 1;
            loadDnsRecords();
            return;
        }
        if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px">暂无解析记录</td></tr>';
            renderDnsRecordsPagination(dnsRecordsTotal, dnsRecordsPage, dnsRecordsPageSize);
            return;
        }
        var html = '';
        records.forEach(function (rec) {
            html += '<tr>'
                + '<td><span class="dns-type-badge">' + escapeHtml(rec.Type) + '</span></td>'
                + '<td>' + escapeHtml(rec.RR) + '</td>'
                + '<td title="' + escapeAttr(rec.Value) + '">' + escapeHtml(rec.Value) + '</td>'
                + '<td>' + rec.TTL + '</td>'
                + '<td>' + escapeHtml(rec.Line || '-') + '</td>'
                + '<td class="dns-actions">'
                + '<button class="btn btn-sm btn-ghost" onclick="editDnsRecord(' + JSON.stringify(rec).replace(/"/g, '&quot;') + ')">编辑</button>'
                + '<button class="btn btn-sm btn-danger" onclick="deleteDnsRecord(\'' + escapeAttr(rec.RecordId) + '\')">删除</button>'
                + '</td></tr>';
        });
        tbody.innerHTML = html;
        renderDnsRecordsPagination(dnsRecordsTotal, dnsRecordsPage, dnsRecordsPageSize);
    }).catch(function () {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--accent-red)">请求失败</td></tr>';
        renderDnsRecordsPagination(0, dnsRecordsPage, dnsRecordsPageSize);
    });
}

function renderDnsRecordsPagination(total, page, pageSize) {
    var bar = document.getElementById('dns-records-pagination');
    var info = document.getElementById('dns-records-page-info');
    var btnPrev = document.getElementById('btn-dns-prev-page');
    var btnNext = document.getElementById('btn-dns-next-page');
    var sizeSel = document.getElementById('dns-records-page-size');
    if (!bar || !info || !btnPrev || !btnNext || !sizeSel) return;

    var totalNum = Math.max(0, parseInt(total, 10) || 0);
    var pageNum = Math.max(1, parseInt(page, 10) || 1);
    var sizeNum = Math.max(1, parseInt(pageSize, 10) || 50);
    var totalPages = Math.max(1, Math.ceil(totalNum / sizeNum));

    if (pageNum > totalPages) pageNum = totalPages;
    dnsRecordsPage = pageNum;
    dnsRecordsPageSize = sizeNum;
    dnsRecordsTotal = totalNum;

    info.textContent = '第 ' + pageNum + ' / ' + totalPages + ' 页，共 ' + totalNum + ' 条';
    btnPrev.disabled = pageNum <= 1;
    btnNext.disabled = pageNum >= totalPages;
    sizeSel.value = String(sizeNum);
    bar.style.display = 'flex';
}

// 根据记录类型动态切换表单字段
function onDnsTypeChange() {
    var rtype = document.getElementById('dns-field-type').value;
    var mxGroup = document.getElementById('dns-mx-priority-group');
    var srvFields = document.getElementById('dns-srv-fields');
    var caaFields = document.getElementById('dns-caa-fields');
    var rrGroup = document.getElementById('dns-rr-group');
    var valueGroup = document.getElementById('dns-value-group');
    var rrLabel = document.getElementById('dns-rr-label');
    var valueLabel = document.getElementById('dns-value-label');

    // 隐藏所有额外字段
    mxGroup.style.display = 'none';
    srvFields.style.display = 'none';
    caaFields.style.display = 'none';
    rrGroup.style.display = 'block';
    valueGroup.style.display = 'block';

    if (rtype === 'MX') {
        mxGroup.style.display = 'block';
        rrLabel.textContent = '主机记录 *';
        valueLabel.textContent = '邮件服务器 *';
    } else if (rtype === 'SRV') {
        srvFields.style.display = 'block';
        rrLabel.textContent = '服务名 *（如 _sip._tcp）';
        valueLabel.textContent = '目标主机 *';
    } else if (rtype === 'CAA') {
        caaFields.style.display = 'block';
        rrGroup.style.display = 'none';
        valueLabel.textContent = 'CA 域名 *（如 letsencrypt.org）';
    } else {
        rrLabel.textContent = '主机记录 *';
        valueLabel.textContent = '记录值 *';
    }
}

function openDnsAddModal() {
    document.getElementById('dns-modal-title').textContent = '添加记录';
    document.getElementById('dns-edit-record-id').value = '';
    document.getElementById('dns-edit-zone-id').value = dnsCurrentZoneId;
    document.getElementById('dns-field-type').value = 'A';
    document.getElementById('dns-field-rr').value = '';
    document.getElementById('dns-field-value').value = '';
    document.getElementById('dns-field-ttl').value = '600';
    document.getElementById('dns-field-line').value = 'default';
    document.getElementById('dns-field-proxied').checked = false;
    document.getElementById('dns-field-mx-priority').value = '10';
    document.getElementById('dns-field-srv-priority').value = '10';
    document.getElementById('dns-field-srv-weight').value = '5';
    document.getElementById('dns-field-srv-port').value = '443';
    document.getElementById('dns-field-caa-flags').value = '0';
    document.getElementById('dns-field-caa-tag').value = 'issue';
    document.getElementById('dns-field-proxied-group').style.display = 'none';
    document.getElementById('dns-field-line-group').style.display = 'block';
    onDnsTypeChange();
    showModal('dns-record-modal');
}

function editDnsRecord(rec) {
    document.getElementById('dns-modal-title').textContent = '编辑记录';
    document.getElementById('dns-edit-record-id').value = rec.RecordId;
    document.getElementById('dns-edit-zone-id').value = dnsCurrentZoneId;
    document.getElementById('dns-field-type').value = rec.Type;
    document.getElementById('dns-field-rr').value = rec.RR;
    document.getElementById('dns-field-value').value = rec.Value;
    document.getElementById('dns-field-ttl').value = String(rec.TTL);
    document.getElementById('dns-field-line').value = rec.Line === 'proxied' || rec.Line === 'dns_only' ? 'default' : (rec.Line || 'default');
    document.getElementById('dns-field-proxied').checked = !!rec.Proxied;
    // 恢复特殊字段
    document.getElementById('dns-field-mx-priority').value = rec.MXPriority || '10';
    document.getElementById('dns-field-srv-priority').value = rec.SrvPriority || '10';
    document.getElementById('dns-field-srv-weight').value = rec.SrvWeight || '5';
    document.getElementById('dns-field-srv-port').value = rec.SrvPort || '443';
    document.getElementById('dns-field-caa-flags').value = rec.CaaFlags || '0';
    document.getElementById('dns-field-caa-tag').value = rec.CaaTag || 'issue';
    document.getElementById('dns-field-proxied-group').style.display = 'none';
    document.getElementById('dns-field-line-group').style.display = 'block';
    onDnsTypeChange();
    showModal('dns-record-modal');
}

function submitDnsRecord() {
    var rtype = document.getElementById('dns-field-type').value;
    var rr = document.getElementById('dns-field-rr').value.trim();
    var value = document.getElementById('dns-field-value').value.trim();
    var ttl = parseInt(document.getElementById('dns-field-ttl').value);
    var line = document.getElementById('dns-field-line').value;
    var proxied = document.getElementById('dns-field-proxied').checked;
    var editId = document.getElementById('dns-edit-record-id').value;
    var zoneId = document.getElementById('dns-edit-zone-id').value;

    // 前端校验：RR 不能包含空格
    if (/\s/.test(rr)) { showToast('主机记录不能包含空格', 'error'); return; }

    // 前端校验：Value 不能为空
    if (!value) { showToast('记录值不能为空', 'error'); return; }

    // 前端校验：TTL 必须是正整数
    if (isNaN(ttl) || ttl <= 0) { showToast('TTL 必须是正整数', 'error'); return; }

    // 前端校验：A 记录 value 必须是有效 IP
    if (rtype === 'A') {
        if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(value)) {
            showToast('A 记录的值必须是有效的 IPv4 地址', 'error'); return;
        }
        // 进一步验证每个段在 0-255
        var octets = value.split('.');
        var validIp = true;
        for (var i = 0; i < octets.length; i++) {
            if (parseInt(octets[i]) > 255) { validIp = false; break; }
        }
        if (!validIp) { showToast('A 记录的值必须是有效的 IPv4 地址', 'error'); return; }
    }

    // 前端校验：AAAA 记录 value 必须是有效 IPv6
    if (rtype === 'AAAA') {
        var ipv6Pattern = /^([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$/;
        if (!ipv6Pattern.test(value) && !/^[0-9a-fA-F]{1,4}(:[0-9a-fA-F]{1,4}){7}$/.test(value)) {
            showToast('AAAA 记录的值必须是有效的 IPv6 地址', 'error'); return;
        }
    }

    // 前端校验：CNAME / MX 的 value 必须是域名格式
    if (rtype === 'CNAME' || rtype === 'MX') {
        if (!/^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.?$/.test(value)) {
            showToast(rtype + ' 记录的值必须是有效的域名', 'error'); return;
        }
    }

    // CAA 特殊校验
    if (rtype === 'CAA') {
        if (!value) { showToast('请填写 CA 域名', 'error'); return; }
    } else {
        if (!rr) { showToast('请填写主机记录', 'error'); return; }
    }

    // 前端重复检查：检查当前表格中是否已存在相同 (type, rr) 的记录（编辑时排除自身）
    var rows = document.querySelectorAll('#dns-records-body tr');
    for (var i = 0; i < rows.length; i++) {
        var cells = rows[i].querySelectorAll('td');
        if (cells.length < 2) continue;
        var existingType = cells[0].textContent.trim().toUpperCase();
        var existingRR = cells[1].textContent.trim();
        if (existingType === rtype.toUpperCase() && existingRR === rr) {
            // 编辑模式：找到的行如果是当前编辑的记录，跳过
            var editBtn = rows[i].querySelector('.btn-ghost');
            if (editId && editBtn) {
                var onclickAttr = editBtn.getAttribute('onclick') || '';
                if (onclickAttr.indexOf(editId) !== -1) continue;
            }
            // 新增模式或匹配到其他记录
            if (!editId) {
                showToast('记录已存在：' + rtype + ' ' + rr, 'error'); return;
            }
        }
    }

    var params = {
        domain: dnsCurrentDomain,
        zone_id: zoneId,
        type: rtype,
        rr: rr,
        value: value,
        ttl: ttl,
        line: line,
        proxied: proxied,
    };

    // MX 优先级
    if (rtype === 'MX') {
        params.mx_priority = parseInt(document.getElementById('dns-field-mx-priority').value) || 10;
    }
    // SRV 字段
    if (rtype === 'SRV') {
        params.srv_priority = parseInt(document.getElementById('dns-field-srv-priority').value) || 10;
        params.srv_weight = parseInt(document.getElementById('dns-field-srv-weight').value) || 5;
        params.srv_port = parseInt(document.getElementById('dns-field-srv-port').value) || 443;
    }
    // CAA 字段
    if (rtype === 'CAA') {
        params.caa_flags = parseInt(document.getElementById('dns-field-caa-flags').value) || 0;
        params.caa_tag = document.getElementById('dns-field-caa-tag').value;
    }

    if (editId) {
        params.record_id = editId;
        callApi('dns_update_record', dnsCurrentProvider, params).then(function (r) {
            if (r && r.success) {
                showToast('修改成功', 'success');
                hideModal('dns-record-modal');
                loadDnsRecords();
            } else {
                showToast(r ? r.message : '修改失败', 'error');
            }
        });
    } else {
        callApi('dns_add_record', dnsCurrentProvider, params).then(function (r) {
            if (r && r.success) {
                showToast('添加成功', 'success');
                hideModal('dns-record-modal');
                loadDnsRecords();
            } else {
                showToast(r ? r.message : '添加失败', 'error');
            }
        });
    }
}

function deleteDnsRecord(recordId) {
    showCustomDialog({
        title: '删除解析记录',
        message: '确定要删除这条解析记录吗？',
        confirmText: '删除',
        danger: true
    }).then(function (ret) {
        if (!ret.ok) return;
        callApi('dns_delete_record', dnsCurrentProvider, {
            domain: dnsCurrentDomain,
            zone_id: dnsCurrentZoneId,
            record_id: recordId
        }).then(function (r) {
            if (r && r.success) { showToast('已删除', 'success'); loadDnsRecords(); }
            else showToast(r ? r.message : '删除失败', 'error');
        });
    });
}

// ==================== DNS 快速导入 ====================

/** 导入预览中的记录缓存 */
var dnsImportRecords = [];
/** 待识别图片 base64（不含 data: 前缀） */
var dnsImportImageBase64 = '';
/** AI 识别轮询定时器 */
var dnsImportAiPollTimer = null;
var dnsImportAiPollInFlight = false;
var dnsImportAiHandledRunId = '';
var dnsImportAiActiveRunId = '';
var dnsImportParseStarting = false;
var dnsImportFormCheckTimer = null;
var dnsImportPreviewWatchBound = false;
/** 解析完成回调：{ onParsed, onError, onProgress } */
var dnsImportCallbacks = { onParsed: null, onError: null, onProgress: null };
var _pendingDnsImportCallbacks = null;
var _dnsImportHooksReady = false;

/**
 * 注册快速导入回调：
 * - onParsed({ records, source, runId? })
 * - onError({ message, runId? })
 * - onProgress({ text })
 * - onImportComplete({ successCount, failCount, total, results: [{ domain, rr, type, value, success, message }] })
 * 可在应用初始化前调用，会排队到模块就绪后自动挂载。
 */
function setDnsImportCallbacks(callbacks) {
    callbacks = callbacks || {};
    if (!_dnsImportHooksReady) {
        _pendingDnsImportCallbacks = callbacks;
        return;
    }
    dnsImportCallbacks.onParsed = typeof callbacks.onParsed === 'function' ? callbacks.onParsed : null;
    dnsImportCallbacks.onError = typeof callbacks.onError === 'function' ? callbacks.onError : null;
    dnsImportCallbacks.onProgress = typeof callbacks.onProgress === 'function' ? callbacks.onProgress : null;
    dnsImportCallbacks.onImportComplete = typeof callbacks.onImportComplete === 'function' ? callbacks.onImportComplete : null;
}

function _appendGlobalLog(line, openDrawer) {
    if (window.__appendScriptLogLine) {
        var expand = openDrawer !== false;
        window.__appendScriptLogLine(
            typeof line === 'string' ? line : String(line),
            { openDrawer: expand }
        );
    }
}
window.setDnsImportCallbacks = setDnsImportCallbacks;

function _flushPendingDnsImportCallbacks() {
    _dnsImportHooksReady = true;
    if (_pendingDnsImportCallbacks) {
        setDnsImportCallbacks(_pendingDnsImportCallbacks);
        _pendingDnsImportCallbacks = null;
    }
}

function _invokeDnsImportCallback(name, payload) {
    var fn = dnsImportCallbacks[name];
    if (fn) {
        try { fn(payload); } catch (e) { console.warn('dns import callback error:', e); }
    }
}

function _setDnsImportAiStatus(text) {
    _invokeDnsImportCallback('onProgress', { text: text || '' });
}

function _stopDnsImportAiPoll() {
    if (dnsImportAiPollTimer) {
        clearInterval(dnsImportAiPollTimer);
        dnsImportAiPollTimer = null;
    }
    dnsImportAiPollInFlight = false;
    dnsImportAiHandledRunId = '';
    dnsImportAiActiveRunId = '';
}

function _renderDnsImportImagePreview() {
    var img = document.getElementById('dns-import-image-preview');
    var placeholder = document.getElementById('dns-import-image-placeholder');
    var zone = document.getElementById('dns-import-dropzone');
    if (!img) return;
    if (dnsImportImageBase64) {
        img.src = 'data:image/png;base64,' + dnsImportImageBase64;
        if (placeholder) placeholder.style.display = 'none';
        if (zone) {
            zone.classList.add('has-image');
        }
    } else {
        img.removeAttribute('src');
        if (placeholder) placeholder.style.display = '';
        if (zone) {
            zone.classList.remove('has-image');
        }
    }
}

function clearDnsImportImage() {
    dnsImportImageBase64 = '';
    _renderDnsImportImagePreview();
}

function _readDnsImportImageFile(file, sourceLabel) {
    if (!file || !file.type || file.type.indexOf('image') !== 0) {
        showToast('请使用图片文件（PNG/JPG/WEBP/GIF）', 'error');
        return;
    }
    var reader = new FileReader();
    reader.onload = function (ev) {
        var dataUrl = ev.target && ev.target.result;
        if (!dataUrl || typeof dataUrl !== 'string') return;
        var comma = dataUrl.indexOf(',');
        var b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
        _applyDnsImportImageBase64(b64, sourceLabel || '图片');
    };
    reader.readAsDataURL(file);
}

function _handleDnsImportDroppedFiles(fileList) {
    if (!fileList || !fileList.length) return;
    for (var i = 0; i < fileList.length; i++) {
        if (fileList[i].type && fileList[i].type.indexOf('image') === 0) {
            _readDnsImportImageFile(fileList[i], '拖拽的图片');
            return;
        }
    }
    showToast('未检测到图片，请拖拽 PNG/JPG 等图片文件', 'error');
}

function initDnsImportDragDrop() {
    var zone = document.getElementById('dns-import-dropzone');
    var modal = document.getElementById('dns-import-modal');
    if (!zone) return;

    function preventDrag(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    zone.addEventListener('dragenter', function (e) {
        preventDrag(e);
        zone.classList.add('is-dragover');
    });
    zone.addEventListener('dragover', function (e) {
        preventDrag(e);
        zone.classList.add('is-dragover');
    });
    zone.addEventListener('dragleave', function (e) {
        preventDrag(e);
        zone.classList.remove('is-dragover');
    });
    zone.addEventListener('drop', function (e) {
        preventDrag(e);
        zone.classList.remove('is-dragover');
        if (e.dataTransfer && e.dataTransfer.files) {
            _handleDnsImportDroppedFiles(e.dataTransfer.files);
        }
    });

    if (modal) {
        modal.addEventListener('dragover', preventDrag);
        modal.addEventListener('drop', function (e) {
            preventDrag(e);
            if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
                _handleDnsImportDroppedFiles(e.dataTransfer.files);
            }
        });
    }
}

function _applyDnsImportImageBase64(b64, sourceLabel) {
    if (!b64) return false;
    var normalized = String(b64).trim();
    var comma = normalized.indexOf(',');
    if (normalized.startsWith('data:image') && comma >= 0) {
        normalized = normalized.slice(comma + 1);
    }
    dnsImportImageBase64 = normalized;
    _renderDnsImportImagePreview();
    showToast((sourceLabel || '图片') + '已就绪，可点击 AI 识别', 'success');
    return true;
}

function onDnsImportPaste(e) {
    var items = (e.clipboardData && e.clipboardData.items) ? e.clipboardData.items : [];
    for (var i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf('image') === 0) {
            e.preventDefault();
            var file = items[i].getAsFile();
            if (!file) continue;
            var reader = new FileReader();
            reader.onload = function (ev) {
                var dataUrl = ev.target && ev.target.result;
                if (!dataUrl || typeof dataUrl !== 'string') return;
                var comma = dataUrl.indexOf(',');
                var b64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
                _applyDnsImportImageBase64(b64, '粘贴的图片');
            };
            reader.readAsDataURL(file);
            return;
        }
    }
}

function loadDnsImportClipboardImage() {
    callApi('dns_get_clipboard_image').then(function (r) {
        if (r && r.success && r.data && r.data.base64) {
            _applyDnsImportImageBase64(r.data.base64, '剪贴板图片');
        } else {
            showToast((r && r.message) || '剪贴板中没有图片', 'error');
        }
    }).catch(function (err) {
        showToast('读取剪贴板失败: ' + (err.message || err), 'error');
    });
}

/**
 * 从文本中提取 JSON 数组（兼容 AI 返回的 markdown 包裹）
 */
function extractJsonArrayFromText(text) {
    var raw = (text || '').trim();
    if (!raw) return null;

    var fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence) raw = fence[1].trim();

    try {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed;
        if (parsed && typeof parsed === 'object') {
            var keys = ['records', 'data', 'list', 'items', 'result'];
            for (var i = 0; i < keys.length; i++) {
                if (Array.isArray(parsed[keys[i]])) return parsed[keys[i]];
            }
        }
    } catch (e1) { /* continue */ }

    var start = raw.indexOf('[');
    var end = raw.lastIndexOf(']');
    if (start >= 0 && end > start) {
        try {
            return JSON.parse(raw.slice(start, end + 1));
        } catch (e2) { /* ignore */ }
    }
    return null;
}

/**
 * 判断是否已是可本地解析的 JSON 数组
 */
function _isJsonDnsRecordsText(text) {
    var arr = extractJsonArrayFromText(text);
    return !!(arr && arr.length);
}

/**
 * 一键解析：文本/图片均走内置 AI；仅当已是 JSON 时本地直解析
 */
function _setDnsImportParseLoading(loading) {
    var btn = document.getElementById('btn-dns-import-parse');
    if (!btn) return;
    btn.disabled = !!loading;
}

function _afterDnsImportParsed(records, source, ok, extra) {
    if (!ok) return;
    showToast(
        source === 'json' ? ('已解析 JSON，共 ' + records.length + ' 条')
            : source === 'console_table' ? ('已识别控制台表格，共 ' + records.length + ' 条')
                : ('AI 解析完成，共 ' + records.length + ' 条，可确认导入'),
        'success'
    );
    var payload = { records: records, source: source };
    if (extra) {
        Object.keys(extra).forEach(function (k) { payload[k] = extra[k]; });
    }
    _invokeDnsImportCallback('onParsed', payload);
}

function runDnsImportParse() {
    if (dnsImportParseStarting) {
        showToast('解析任务进行中，请勿重复点击', 'info');
        return;
    }
    var text = document.getElementById('dns-import-text').value.trim();
    if (!text && !dnsImportImageBase64) {
        showToast('请先粘贴控制台文字、JSON 或截图', 'error');
        return;
    }

    if (text && _isJsonDnsRecordsText(text)) {
        var jsonRecords = normalizeDnsImportItems(extractJsonArrayFromText(text));
        enrichDnsImportRecordsDomains(jsonRecords, text);
        _appendGlobalLog('[DNS导入] JSON 解析，共 ' + jsonRecords.length + ' 条\n');
        uiRunBusy('dns-import-modal', '正在解析并比对记录…', function () {
            return showDnsImportPreview(jsonRecords).then(function (ok) {
                _afterDnsImportParsed(jsonRecords, 'json', ok);
            });
        });
        return;
    }

    if (text) {
        var localRows = parseConsoleTableDnsText(text);
        enrichDnsImportRecordsDomains(localRows, text);
        if (localRows.length) {
            var localRecords = normalizeDnsImportItems(localRows);
            _appendGlobalLog('[DNS导入] 本地表格解析成功，共 ' + localRecords.length + ' 条\n');
            _appendGlobalLog(JSON.stringify(localRecords, null, 2) + '\n');
            uiRunBusy('dns-import-modal', '正在解析并比对记录…', function () {
                return showDnsImportPreview(localRecords).then(function (ok) {
                    _afterDnsImportParsed(localRecords, 'console_table', ok);
                });
            });
            return;
        }
    }

    _appendGlobalLog('[DNS导入] 启动 AI 识别...\n');
    _setDnsImportParseLoading(true);
    startDnsAiRecognize();
}

/**
 * 打开快速导入模态框
 */
function openDnsImportModal() {
    Promise.all([
        ensureSettingsLoaded(false),
        ensureDnsParseConfigLoaded(true)
    ]).then(function () {
        if (dnsCurrentProvider && !_getActiveProfileId(dnsCurrentProvider)) {
            showToast('当前服务商未选择密钥档案，解析后将尝试按域名自动识别服务商', 'info');
        }
        _stopDnsImportAiPoll();
        document.getElementById('dns-import-text').value = '';
        clearDnsImportImage();
        var fileInput = document.getElementById('dns-import-file-input');
        if (fileInput) fileInput.value = '';
        _setDnsImportAiStatus('');
        document.getElementById('dns-import-step1').style.display = 'block';
        document.getElementById('dns-import-step2').style.display = 'none';
        document.getElementById('btn-dns-import-back').style.display = 'none';
        document.getElementById('btn-dns-import-confirm').style.display = 'none';
        dnsImportRecords = [];
        invalidateDnsExistingRecordsCache(dnsCurrentDomain || '');
        showModal('dns-import-modal');
        if (dnsCurrentDomain && dnsCurrentProvider) {
            fetchAllDnsRecordsForDomain(dnsCurrentDomain, dnsCurrentZoneId).then(function (rows) {
                dnsExistingRecordsCache[dnsCurrentDomain.toLowerCase()] = rows;
            }).catch(function () {});
        }
    });
}

/**
 * 关闭快速导入模态框
 */
function closeDnsImportModal() {
    _stopDnsImportAiPoll();
    dnsImportParseStarting = false;
    hideModal('dns-import-modal');
}

/**
 * 从 FQDN 中提取主机记录和域名（使用已加载的域名列表匹配）
 * @param {string} fqdn - 完整域名
 * @returns {Object} {rr, domain}
 */
function extractRRAndDomain(fqdn) {
    var rr = '';
    var domain = '';
    var parts = fqdn.split('.');

    // 使用已加载的域名列表进行匹配
    if (dnsDomainsCache && dnsDomainsCache.length > 0) {
        // 按域名长度降序排列（优先匹配更长的域名，如 sub.example.com 优先于 example.com）
        var sortedDomains = dnsDomainsCache.slice().sort(function (a, b) {
            return (b.DomainName || '').length - (a.DomainName || '').length;
        });

        for (var i = 0; i < sortedDomains.length; i++) {
            var d = sortedDomains[i].DomainName || '';
            if (!d) continue;
            var dLower = d.toLowerCase();
            var fqdnLower = fqdn.toLowerCase();

            // 完全匹配
            if (fqdnLower === dLower) {
                domain = d;
                rr = '@';
                return { rr: rr, domain: domain };
            }
            // 子域名匹配（如 www.example.com 匹配 example.com）
            if (fqdnLower.endsWith('.' + dLower)) {
                domain = d;
                var prefix = fqdn.substring(0, fqdn.length - d.length - 1);
                rr = prefix || '@';
                return { rr: rr, domain: domain };
            }
        }
    }

    // 回退逻辑：取最后两部分作为主域名（适用于简单域名如 example.com）
    if (parts.length >= 2) {
        domain = parts.slice(-2).join('.');
        if (parts.length > 2) {
            rr = parts.slice(0, -2).join('.');
        } else {
            rr = '@';
        }
    }

    return { rr: rr, domain: domain };
}

function normalizeDnsRecordType(raw) {
    var s = String(raw || '').toUpperCase().replace(/\s+/g, '');
    if (!s) return '';
    var types = ['TXT', 'AAAA', 'CNAME', 'MX', 'NS', 'SRV', 'CAA'];
    for (var i = 0; i < types.length; i++) {
        if (s.indexOf(types[i]) !== -1) return types[i];
    }
    if (s === 'A' || s.indexOf('A记录') !== -1) return 'A';
    return ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'].indexOf(s) !== -1 ? s : '';
}

/**
 * 解析控制台复制的表格（校验域名 / 主机记录 / 记录类型 / TXT 记录值）
 */
function extractDomainsFromDnsProse(text) {
    var found = [];
    var seen = {};
    function addDomain(raw) {
        var d = String(raw || '').trim().replace(/\.$/, '').toLowerCase();
        if (!d || seen[d]) return;
        if (!/^[a-z0-9][\w.-]*\.[a-z]{2,}$/i.test(d)) return;
        seen[d] = true;
        found.push(d);
    }
    var patterns = [
        /请前往域名\s*[「"'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})/gi,
        /域名为?\s*[「"'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})/gi,
        /域名\s*[「"'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})/gi,
        /为域名\s*[「"'\s]*([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})/gi
    ];
    patterns.forEach(function (re) {
        var m;
        while ((m = re.exec(text)) !== null) {
            addDomain(m[1]);
        }
    });
    var fqdnRe = /(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}/g;
    var fm;
    while ((fm = fqdnRe.exec(text)) !== null) {
        addDomain(fm[0]);
    }
    found.sort(function (a, b) { return b.length - a.length; });
    return found;
}

function enrichDnsImportRecordsDomains(records, text) {
    var hints = extractDomainsFromDnsProse(text);
    if (!hints.length) return records;
    var lowText = String(text || '').toLowerCase();
    var defaultDomain = hints[0];
    (records || []).forEach(function (rec) {
        if (String(rec.domain || '').trim()) return;
        var rr = String(rec.rr || '').trim();
        var matched = '';
        for (var i = 0; i < hints.length; i++) {
            var d = hints[i];
            var candidates = [];
            if (rr && rr !== '@') {
                candidates.push(rr + '.' + d);
                if (rr.indexOf('_dnsauth.') === 0) {
                    candidates.push(rr + '.' + d);
                    var sub = rr.split('.').slice(1).join('.');
                    if (sub) candidates.push(sub + '.' + d);
                }
            }
            for (var c = 0; c < candidates.length; c++) {
                if (lowText.indexOf(candidates[c].toLowerCase()) !== -1) {
                    matched = d;
                    break;
                }
            }
            if (matched) break;
        }
        rec.domain = matched || defaultDomain;
    });
    return records;
}

/**
 * 「校验域名」常为完整主机名；DNS API 需要根域 + 主机记录两列。
 */
function guessDnsZoneFromFqdn(fqdn) {
    fqdn = String(fqdn || '').trim().toLowerCase().replace(/\.$/, '');
    var parts = fqdn.split('.').filter(Boolean);
    if (parts.length < 2) return '';
    return parts.slice(-2).join('.');
}

function normalizeVerifyDomainColumn(rec) {
    if (!rec || typeof rec !== 'object') return rec;
    var raw = String(rec.domain || '').trim().replace(/\.$/, '');
    var rr = String(rec.rr || '').trim() || '@';
    if (!raw) return rec;
    var parts = raw.split('.').filter(Boolean);
    if (parts.length >= 3) {
        rec.verifyHost = raw;
        rec.domain = parts.slice(-2).join('.');
    } else if (parts.length === 2) {
        rec.domain = raw;
    }
    return rec;
}

function parseConsoleTableDnsText(text) {
    var records = [];
    var headerMarks = ['校验域名', '主机记录', '记录类型', '记录值'];
    var lines = String(text || '').split('\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line || line.indexOf('#') === 0) continue;
        var isHeader = false;
        for (var h = 0; h < headerMarks.length; h++) {
            if (line.indexOf(headerMarks[h]) !== -1 && (line.indexOf('记录') !== -1 || line.indexOf('域名') !== -1)) {
                isHeader = true;
                break;
            }
        }
        if (isHeader) continue;

        line = line.replace(/\s*复制\s*/g, ' ').replace(/\s+/g, ' ').trim();
        var domain = '';
        var rr = '';
        var rtypeRaw = '';
        var value = '';
        var rowM = line.match(/^([a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,})\s+(\S+)\s+(.+?)\s+([A-Za-z0-9][\w.+:/=-]{8,})\s*$/);
        if (rowM) {
            domain = rowM[1].replace(/\.$/, '');
            rr = rowM[2];
            rtypeRaw = rowM[3];
            value = rowM[4];
        } else {
            var cols = line.split(/\t+|\s{2,}/).filter(function (c) { return c && c !== '复制'; });
            if (cols.length < 3) cols = line.split(/\s+/).filter(function (c) { return c !== '复制'; });
            if (cols.length < 3) continue;
            if (/^[a-zA-Z0-9][\w.-]*\.[a-zA-Z]{2,}$/.test(cols[0])) {
                domain = cols[0].replace(/\.$/, '');
                rr = cols[1];
                rtypeRaw = cols[2];
                value = cols[cols.length - 1];
            } else {
                rr = cols[0];
                rtypeRaw = cols[1];
                value = cols[cols.length - 1];
            }
        }
        var rtype = normalizeDnsRecordType(rtypeRaw);
        if (!rtype || !value) continue;
        records.push(normalizeVerifyDomainColumn({
            type: rtype,
            rr: rr || '@',
            value: value,
            ttl: 600,
            domain: domain
        }));
    }
    enrichDnsImportRecordsDomains(records, text);
    return records;
}

function resolveImportDomainName(raw, domainMap) {
    var low = String(raw || '').trim().toLowerCase();
    if (!low) return '';
    if (domainMap[low]) return domainMap[low];
    var best = '';
    var bestLen = 0;
    Object.keys(domainMap).forEach(function (k) {
        if (low === k || (low.length > k.length + 1 && low.slice(-(k.length + 1)) === '.' + k)) {
            if (k.length > bestLen) {
                bestLen = k.length;
                best = domainMap[k];
            }
        }
    });
    return best;
}

/**
 * 解析粘贴的纯文本格式（BIND 格式和表格格式）
 * @param {string} text - 粘贴的文本内容
 * @returns {Array} 解析后的记录数组
 */
function parseDnsTextRecords(text) {
    var records = [];
    var lines = text.split('\n');
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line || line.startsWith('#') || line.startsWith(';')) continue;

        // BIND：www.example.com. 300 IN A 1.2.3.4
        var bindMatch = line.match(/^(\S+)\s+(\d+)\s+IN\s+(A|AAAA|CNAME|MX|TXT|NS|SRV|CAA)\s+(.+)$/i);
        if (bindMatch) {
            var fqdn = bindMatch[1].replace(/\.$/, '');
            var extracted = extractRRAndDomain(fqdn);
            records.push({
                type: bindMatch[3].toUpperCase(),
                rr: extracted.rr,
                value: bindMatch[4].trim(),
                ttl: parseInt(bindMatch[2]) || 600,
                domain: extracted.domain
            });
            continue;
        }

        // BIND 简写：www.example.com. IN A 1.2.3.4 或 www.example.com. A 1.2.3.4
        var bindShort = line.match(/^(\S+)\s+(?:IN\s+)?(A|AAAA|CNAME|MX|TXT|NS|SRV|CAA)\s+(.+)$/i);
        if (bindShort) {
            var fqdn2 = bindShort[1].replace(/\.$/, '');
            var extracted2 = extractRRAndDomain(fqdn2);
            records.push({
                type: bindShort[2].toUpperCase(),
                rr: extracted2.rr,
                value: bindShort[3].trim(),
                ttl: 600,
                domain: extracted2.domain
            });
            continue;
        }

        // 表格格式：www  A  1.2.3.4  600（空格或 Tab 分隔）
        var cols = line.split(/[\t\s]+/);
        if (cols.length >= 3) {
            var rr2 = cols[0];
            var type2 = cols[1].toUpperCase();
            var val2 = cols[2];
            var ttl2 = cols.length >= 4 ? parseInt(cols[3]) : 600;
            // 验证类型是否合法
            if (['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'].indexOf(type2) !== -1) {
                records.push({ type: type2, rr: rr2, value: val2, ttl: ttl2 || 600, domain: '' });
                continue;
            }
        }
    }
    return records;
}

/**
 * 将原始项规范为导入记录
 */
function normalizeDnsImportItems(items) {
    var records = [];
    (items || []).forEach(function (item) {
        if (!item || typeof item !== 'object') return;
        var rtype = normalizeDnsRecordType(item.type || item.Type || item.record_type || 'A');
        if (!rtype) return;
        var value = String(item.value || item.Value || '').trim();
        if (!value) return;
        records.push({
            type: rtype,
            rr: String(item.rr || item.RR || item.name || item.Name || '@').trim() || '@',
            value: value,
            ttl: parseInt(item.ttl || item.TTL, 10) || 600,
            domain: String(item.domain || item.Domain || '').trim()
        });
    });
    return records;
}

/**
 * 从文本或 AI 结果解析记录列表
 */
function parseDnsRecordsFromInput(text) {
    text = (text || '').trim();
    if (!text) return [];

    var jsonArr = extractJsonArrayFromText(text);
    if (jsonArr && jsonArr.length) {
        return normalizeDnsImportItems(jsonArr);
    }
    var consoleRows = parseConsoleTableDnsText(text);
    if (consoleRows.length) {
        return normalizeDnsImportItems(consoleRows);
    }
    return parseDnsTextRecords(text);
}

function _prepareDnsImportRecords(records) {
    records = records || [];
    var hasDomain = !!dnsCurrentDomain;
    var domainMap = {};
    var unresolvedDomainCount = 0;
    var invalidDomainCount = 0;

    dnsDomainsCache.forEach(function (d) {
        if (d && d.DomainName) domainMap[String(d.DomainName).toLowerCase()] = d.DomainName;
    });

    if (!hasDomain) {
        records.forEach(function (rec) {
            normalizeVerifyDomainColumn(rec);
            var raw = String(rec.domain || '').trim();
            var verifyHost = String(rec.verifyHost || '').trim();
            var resolved = resolveImportDomainName(raw, domainMap);
            if (!resolved && verifyHost) {
                resolved = resolveImportDomainName(verifyHost, domainMap);
            }
            if (resolved) {
                rec.domain = resolved;
                return;
            }
            if (!raw) {
                rec.domain = '';
                unresolvedDomainCount++;
                return;
            }
            var apex = guessDnsZoneFromFqdn(raw) || guessDnsZoneFromFqdn(verifyHost);
            if (apex) {
                rec.domain = apex;
                return;
            }
            rec.domain = '';
            invalidDomainCount++;
        });
    } else {
        records.forEach(function (rec) {
            if (!String(rec.domain || '').trim()) {
                rec.domain = dnsCurrentDomain;
            }
        });
    }

    return {
        hasDomain: hasDomain,
        showDomainPicker: true,
        unresolvedDomainCount: unresolvedDomainCount,
        invalidDomainCount: invalidDomainCount
    };
}

function _buildDnsImportPreviewHtml(records, existingKeySetByDomain, meta) {
    meta = meta || {};
    var showDomainPicker = meta.showDomainPicker !== false;
    var html = '';
    var duplicateCount = 0;
    var newCount = 0;
    var checking = !existingKeySetByDomain;

    records.forEach(function (rec, idx) {
        var isDup = !checking && isDnsImportRecordDuplicate(rec, existingKeySetByDomain);
        if (isDup) duplicateCount++;
        else newCount++;

        html += '<div class="dns-import-card' + (isDup ? ' is-duplicate' : '') + '" data-idx="' + idx + '" data-duplicate="' + (isDup ? '1' : '0') + '">';
        html += '<div class="dns-import-row">';
        if (showDomainPicker) {
            var domainVal = rec.domain || dnsCurrentDomain || '';
            var domainOptions = '<option value="">请选择域名</option>';
            if (domainVal && !dnsDomainsCache.some(function (d) {
                return String(d.DomainName || '').toLowerCase() === String(domainVal).toLowerCase();
            })) {
                domainOptions += '<option value="' + escapeAttr(domainVal) + '" selected>' + escapeHtml(domainVal) + '（解析）</option>';
            }
            dnsDomainsCache.forEach(function (d) {
                var dn = d.DomainName || '';
                domainOptions += '<option value="' + escapeAttr(dn) + '"' + (dn === domainVal ? ' selected' : '') + '>' + escapeHtml(dn) + '</option>';
            });
            html += '<div class="dns-import-field"><label>目标域名</label><select class="form-input dns-import-domain">' + domainOptions + '</select></div>';
        }
        html += '<div class="dns-import-field"><label>主机记录</label><input type="text" class="form-input dns-import-rr" value="' + escapeAttr(rec.rr) + '"></div>';
        html += '<div class="dns-import-field"><label>类型';
        if (isDup) html += '<span class="dns-import-dup-badge">已存在</span>';
        else if (checking) html += '<span class="dns-import-dup-badge" style="color:var(--text-muted);background:transparent">比对中</span>';
        html += '</label><select class="form-input dns-import-type">';
        ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'].forEach(function (t) {
            html += '<option value="' + t + '"' + (rec.type === t ? ' selected' : '') + '>' + t + '</option>';
        });
        html += '</select></div></div>';
        html += '<div class="dns-import-row dns-import-row-2">';
        html += '<div class="dns-import-field"><label>记录值</label><input type="text" class="form-input dns-import-value" value="' + escapeAttr(rec.value) + '"></div>';
        html += '<div class="dns-import-field"><label>TTL</label><input type="number" class="form-input dns-import-ttl" value="' + rec.ttl + '"></div>';
        html += '<div class="dns-import-field dns-import-field-action"><button type="button" class="btn btn-sm btn-icon-danger" onclick="removeDnsImportRow(' + idx + ')" title="移除">'
            + '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
            + '</button></div></div></div>';
    });

    return { html: html, duplicateCount: duplicateCount, newCount: newCount, checking: checking };
}

function _paintDnsImportPreviewList(records, existingKeySetByDomain, meta) {
    return new Promise(function (resolve) {
        requestAnimationFrame(function () {
            var built = _buildDnsImportPreviewHtml(records, existingKeySetByDomain, meta);
            var listEl = document.getElementById('dns-import-preview-list');
            if (listEl) listEl.innerHTML = built.html;
            document.getElementById('dns-import-count').textContent = records.length;
            resolve(built);
        });
    });
}

/**
 * 显示导入预览：先渲染列表，再异步比对重复（避免长时间白屏卡顿）
 */
function _collectDnsImportDraftFromForm() {
    var rows = document.querySelectorAll('#dns-import-preview-list .dns-import-card');
    var draft = [];
    rows.forEach(function (row) {
        var domainSel = row.querySelector('.dns-import-domain');
        var domain = domainSel ? (domainSel.value || '') : (dnsCurrentDomain || '');
        draft.push({
            domain: domain,
            type: (row.querySelector('.dns-import-type') || {}).value || 'A',
            rr: ((row.querySelector('.dns-import-rr') || {}).value || '').trim(),
            value: ((row.querySelector('.dns-import-value') || {}).value || '').trim(),
            ttl: parseInt((row.querySelector('.dns-import-ttl') || {}).value, 10) || 600
        });
    });
    return draft;
}

function initDnsImportPreviewFormWatch() {
    var listEl = document.getElementById('dns-import-preview-list');
    if (!listEl || dnsImportPreviewWatchBound) return;
    dnsImportPreviewWatchBound = true;
    function schedule() {
        clearTimeout(dnsImportFormCheckTimer);
        dnsImportFormCheckTimer = setTimeout(refreshDnsImportDuplicateMarks, 400);
    }
    listEl.addEventListener('input', schedule);
    listEl.addEventListener('change', schedule);
}

function refreshDnsImportDuplicateMarks() {
    var draft = _collectDnsImportDraftFromForm();
    if (!draft.length) return Promise.resolve();
    dnsImportRecords = draft;
    var meta = { hasDomain: !!dnsCurrentDomain, showDomainPicker: true };
    return ensureDnsProviderForImportRecords(draft).then(function () {
        return ensureDnsExistingRecordsForImport(draft);
    }).then(function (existingKeySetByDomain) {
        return _paintDnsImportPreviewList(draft, existingKeySetByDomain, meta);
    }).catch(function () {});
}

function showDnsImportPreview(records) {
    records = records || [];
    if (!records.length) {
        showToast('未能解析到有效的 DNS 记录', 'error');
        return Promise.resolve(false);
    }

    dnsImportRecords = records;
    document.getElementById('dns-import-step1').style.display = 'none';
    document.getElementById('dns-import-step2').style.display = 'block';
    document.getElementById('btn-dns-import-back').style.display = '';
    document.getElementById('btn-dns-import-confirm').style.display = '';
    initDnsImportPreviewFormWatch();

    var loadDomainsP = Promise.resolve();
    if (dnsCurrentProvider && (!dnsDomainsCache || !dnsDomainsCache.length)) {
        loadDomainsP = loadDnsDomainsAsync(dnsCurrentProvider);
    }

    return loadDomainsP.then(function () {
        return ensureDnsProviderForImportRecords(records);
    }).then(function () {
        var meta = _prepareDnsImportRecords(records);
        return _paintDnsImportPreviewList(records, null, meta).then(function () {
            return ensureDnsExistingRecordsForImport(records).then(function (existingKeySetByDomain) {
                return _paintDnsImportPreviewList(records, existingKeySetByDomain, meta).then(function (built) {
                if (meta.unresolvedDomainCount > 0) {
                    showToast(
                        '部分记录缺少域名：' + meta.unresolvedDomainCount + ' 条，请在下拉框选择',
                        'error'
                    );
                } else if (meta.invalidDomainCount > 0) {
                    showToast(
                        '部分域名无法识别：无效 ' + meta.invalidDomainCount + ' 条，请手动选择域名',
                        'error'
                    );
                    } else if (built.duplicateCount > 0) {
                        _appendGlobalLog('[DNS导入] 重复记录 ' + built.duplicateCount + ' 条，可导入 ' + built.newCount + ' 条\n');
                        showToast('发现 ' + built.duplicateCount + ' 条与现有记录相同，确认导入时将自动跳过', 'info');
                    }
                    return true;
                });
            }).catch(function (err) {
                showToast('加载现有记录失败: ' + (err.message || err), 'error');
                return false;
            });
        });
    }).catch(function (err) {
        showToast('准备预览失败: ' + (err.message || err), 'error');
        return false;
    });
}

/**
 * 内置 AI 识别（文本 + 可选图片，自动返回 JSON 并进入预览）
 */
function startDnsAiRecognize() {
    var text = document.getElementById('dns-import-text').value.trim();
    if (!text && !dnsImportImageBase64) {
        showToast('请先粘贴文本或图片', 'error');
        return;
    }
    if (dnsImportParseStarting) {
        showToast('识别任务进行中，请勿重复点击', 'info');
        return;
    }

    Promise.all([
        ensureSettingsLoaded(false),
        ensureDnsParseConfigLoaded(true)
    ]).then(function () {
        _runDnsAiRecognize(text);
    });
}

function _runDnsAiRecognize(text) {
    _stopDnsImportAiPoll();
    dnsImportParseStarting = true;
    _setDnsImportParseLoading(true);
    showToast('AI 正在解析，完成后自动进入预览…', 'info');

    var domainHint = dnsCurrentDomain || '';
    var hints = extractDomainsFromDnsProse(text);
    if (!domainHint && hints.length) domainHint = hints[0];

    callApi('dns_ai_parse_start', text, dnsImportImageBase64, domainHint).then(function (r) {
        if (!r || !r.success) {
            dnsImportParseStarting = false;
            _setDnsImportParseLoading(false);
            var msg = (r && r.message) || '启动识别失败';
            _setDnsImportAiStatus('');
            showToast(msg, 'error');
            _invokeDnsImportCallback('onError', { message: msg });
            return;
        }
        var runId = (r.data && r.data.run_id) || r.run_id || '';
        if (!runId) {
            dnsImportParseStarting = false;
            _setDnsImportParseLoading(false);
            showToast('未获取到任务 ID', 'error');
            return;
        }
        dnsImportAiActiveRunId = runId;
        var sinceSeq = 0;

        function pollOnce() {
            if (dnsImportAiPollInFlight) return;
            dnsImportAiPollInFlight = true;
            callApi('dns_ai_parse_poll', runId, sinceSeq, 200).then(function (pr) {
                if (!pr || !pr.success) return;
                var data = pr.data || {};
                var lines = data.lines || [];
                for (var li = 0; li < lines.length; li++) {
                    _appendGlobalLog(lines[li]);
                }
                sinceSeq = data.next_seq || sinceSeq;

                if (!data.done) return;

                if (dnsImportAiHandledRunId === runId) return;
                dnsImportAiHandledRunId = runId;
                dnsImportAiActiveRunId = '';
                _stopDnsImportAiPoll();
                dnsImportParseStarting = false;
                _setDnsImportParseLoading(false);

                if (data.success_flag && data.records && data.records.length) {
                    var records = normalizeDnsImportItems(data.records);
                    enrichDnsImportRecordsDomains(records, text);
                    _appendGlobalLog('[DNS导入] AI 解析完成，共 ' + records.length + ' 条\n');
                    _appendGlobalLog(JSON.stringify(records, null, 2) + '\n');
                    document.getElementById('dns-import-text').value = JSON.stringify(records, null, 2);
                    uiRunBusy('dns-import-modal', '比对中…', function () {
                        return showDnsImportPreview(records).then(function (ok) {
                            _afterDnsImportParsed(records, 'ai', ok, { runId: runId });
                        });
                    });
                } else {
                    var errMsg = data.message || 'AI 识别失败';
                    _appendGlobalLog('[DNS导入] 失败: ' + errMsg + '\n');
                    showToast(errMsg, 'error');
                    _invokeDnsImportCallback('onError', { message: errMsg, runId: runId });
                }
            }).catch(function (err) {
                _stopDnsImportAiPoll();
                dnsImportParseStarting = false;
                _setDnsImportParseLoading(false);
                var em = err.message || String(err);
                showToast('识别轮询失败: ' + em, 'error');
                _invokeDnsImportCallback('onError', { message: em });
            }).finally(function () {
                dnsImportAiPollInFlight = false;
            });
        }

        dnsImportAiPollTimer = setInterval(pollOnce, 800);
        pollOnce();
    }).catch(function (err) {
        dnsImportParseStarting = false;
        _setDnsImportParseLoading(false);
        showToast('启动识别失败: ' + (err.message || err), 'error');
        _invokeDnsImportCallback('onError', { message: err.message || String(err) });
    });
}

function buildDnsZoneMap() {
    var map = {};
    (dnsDomainsCache || []).forEach(function (d) {
        if (d && d.DomainName) map[d.DomainName] = d.DomainId || '';
    });
    return map;
}

/**
 * 移除导入预览中的某一行
 * @param {number} idx - 行索引
 */
function removeDnsImportRow(idx) {
    var row = document.querySelector('#dns-import-preview-list .dns-import-card[data-idx="' + idx + '"]');
    if (row) row.remove();
    var remaining = document.querySelectorAll('#dns-import-preview-list .dns-import-card').length;
    document.getElementById('dns-import-count').textContent = remaining;
    if (remaining === 0) {
        showToast('所有记录已移除', 'info');
    }
}

/**
 * 返回修改步骤
 */
function backToDnsImportStep1() {
    _stopDnsImportAiPoll();
    dnsImportParseStarting = false;
    _setDnsImportParseLoading(false);
    document.getElementById('dns-import-step1').style.display = 'block';
    document.getElementById('dns-import-step2').style.display = 'none';
    document.getElementById('btn-dns-import-back').style.display = 'none';
    document.getElementById('btn-dns-import-confirm').style.display = 'none';
}

/**
 * 确认导入：逐条调用 API 添加记录
 */
function confirmDnsImport() {
    if (!dnsCurrentProvider) {
        showToast('尚未识别服务商，请等待自动识别完成或手动选择服务商', 'error');
        return;
    }
    if (!_getActiveProfileId(dnsCurrentProvider)) {
        showToast('请先为当前服务商选择密钥档案', 'error');
        return;
    }
    var rows = document.querySelectorAll('#dns-import-preview-list .dns-import-card');
    if (rows.length === 0) {
        showToast('没有可导入的记录', 'error');
        return;
    }

    var draftRecords = [];
    var failCount = 0;
    var missingDomainCount = 0;

    rows.forEach(function (row) {
        var domainSel = row.querySelector('.dns-import-domain');
        var domain = domainSel ? (domainSel.value || '') : (dnsCurrentDomain || '');
        var type = (row.querySelector('.dns-import-type') || {}).value || 'A';
        var rr = ((row.querySelector('.dns-import-rr') || {}).value || '').trim();
        var value = ((row.querySelector('.dns-import-value') || {}).value || '').trim();
        var ttl = parseInt((row.querySelector('.dns-import-ttl') || {}).value, 10) || 600;

        if (!rr || !value) {
            failCount++;
            return;
        }
        if (!domain) {
            missingDomainCount++;
            return;
        }

        if (/\s/.test(rr)) {
            failCount++;
            return;
        }
        if (isNaN(ttl) || ttl <= 0) {
            failCount++;
            return;
        }
        if (type === 'A' && !/^(\d{1,3}\.){3}\d{1,3}$/.test(value)) {
            failCount++;
            return;
        }
        if ((type === 'CNAME' || type === 'MX') &&
            !/^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.?$/.test(value)) {
            failCount++;
            return;
        }

        draftRecords.push({ domain: domain, type: type, rr: rr, value: value, ttl: ttl });
    });

    if (draftRecords.length === 0) {
        if (missingDomainCount > 0) {
            showToast('有 ' + missingDomainCount + ' 条记录未选择目标域名', 'error');
            return;
        }
        if (failCount > 0) {
            showToast('所有 ' + failCount + ' 条记录校验失败，请检查格式', 'error');
        } else {
            showToast('没有有效的记录可导入', 'error');
        }
        return;
    }

    uiRunBusy('dns-import-modal', '正在校验并导入…', function () {
        return ensureDnsExistingRecordsForImport(draftRecords).then(function (existingKeySetByDomain) {
            var tasks = [];
            var skipDupCount = 0;
            draftRecords.forEach(function (rec) {
                if (isDnsImportRecordDuplicate(rec, existingKeySetByDomain)) {
                    skipDupCount++;
                    _appendGlobalLog('[DNS导入] 跳过重复: ' + rec.type + ' ' + rec.rr + '.' + rec.domain + ' -> ' + rec.value + '\n');
                    return;
                }
                tasks.push(rec);
            });

            if (tasks.length === 0) {
                if (skipDupCount > 0) {
                    showToast('全部为重复记录，无需导入（共 ' + skipDupCount + ' 条）', 'info');
                } else {
                    showToast('没有可导入的记录', 'error');
                }
                return;
            }
            if (skipDupCount > 0) {
                showToast('将导入 ' + tasks.length + ' 条，跳过重复 ' + skipDupCount + ' 条', 'info');
            }

            return doDnsImportTasks(tasks, false, failCount, skipDupCount);
        });
    }).catch(function (err) {
        showToast('校验重复记录失败: ' + (err.message || err), 'error');
    });
}

function doDnsImportTasks(tasks, hasDomain, failCount, skipDupCount) {
    return new Promise(function (resolve, reject) {
    var doImport = function (zoneMap) {
        showToast('开始导入 ' + tasks.length + ' 条记录...', 'info');
        _appendGlobalLog('[DNS导入] 开始导入 ' + tasks.length + ' 条记录...\n');
        var successCount = 0;
        var importFailCount = failCount;
        var idx = 0;
        var importResults = [];

        function importNext() {
            if (idx >= tasks.length) {
                var summary = {
                    successCount: successCount,
                    failCount: importFailCount,
                    skippedDuplicate: skipDupCount || 0,
                    total: tasks.length,
                    results: importResults
                };
                _appendGlobalLog(
                    '[DNS导入] 完成：成功 ' + successCount + '，失败 ' + importFailCount
                    + '，跳过重复 ' + (skipDupCount || 0) + '，待导入 ' + tasks.length + '\n'
                );
                _invokeDnsImportCallback('onImportComplete', summary);

                if (importFailCount === 0 && successCount > 0) {
                    showToast('已成功导入 ' + successCount + ' 条记录', 'success');
                    hideModal('dns-import-modal');
                } else if (successCount > 0) {
                    showToast('导入完成：成功 ' + successCount + ' 条，失败 ' + importFailCount + ' 条', 'error');
                } else {
                    showToast('导入失败：' + importFailCount + ' 条均未成功', 'error');
                }
                if (successCount > 0) {
                    invalidateDnsExistingRecordsCache();
                    if (dnsCurrentProvider && dnsCurrentDomain) loadDnsRecords();
                }
                resolve(summary);
                return;
            }

            var task = tasks[idx];
            var zoneId = hasDomain ? dnsCurrentZoneId : (zoneMap && zoneMap[task.domain] || '');
            var params = {
                domain: task.domain,
                zone_id: zoneId,
                type: task.type,
                rr: task.rr,
                value: task.value,
                ttl: task.ttl,
                line: 'default',
                proxied: false
            };

            callApi('dns_add_record', dnsCurrentProvider, params).then(function (r) {
                var ok = !!(r && r.success);
                var msg = (r && r.message) || (ok ? 'ok' : 'unknown');
                if (ok) {
                    successCount++;
                    _appendGlobalLog('[DNS导入] ✓ ' + task.type + ' ' + task.rr + '.' + task.domain + ' -> ' + task.value + '\n');
                } else {
                    importFailCount++;
                    _appendGlobalLog('[DNS导入] ✗ ' + task.type + ' ' + task.rr + '.' + task.domain + ' : ' + msg + '\n');
                }
                importResults.push({
                    domain: task.domain,
                    type: task.type,
                    rr: task.rr,
                    value: task.value,
                    ttl: task.ttl,
                    success: ok,
                    message: msg
                });
                idx++;
                importNext();
            }).catch(function (err) {
                importFailCount++;
                var em = err.message || String(err);
                _appendGlobalLog('[DNS导入] ✗ ' + task.type + ' ' + task.rr + '.' + task.domain + ' : ' + em + '\n');
                importResults.push({
                    domain: task.domain,
                    type: task.type,
                    rr: task.rr,
                    value: task.value,
                    ttl: task.ttl,
                    success: false,
                    message: em
                });
                idx++;
                importNext();
            });
        }

        importNext();
    };

    try {
        doImport(buildDnsZoneMap());
    } catch (err) {
        reject(err);
    }
    });
}

function _setWindowMaximizeIcon(maximized) {
    var btn = document.getElementById('btn-window-maximize');
    if (!btn) return;
    btn.title = maximized ? '还原' : '最大化';
    btn.setAttribute('aria-label', maximized ? '还原' : '最大化');
    btn.innerHTML = maximized
        ? '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="10" height="10" rx="1"/><path d="M6 6h12v12"/></svg>'
        : '<svg viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="1"/></svg>';
}

// ==================== 设置 ====================

/**
 * 加载设置
 */
function loadSettings() {
    ensureSettingsLoaded(true).then(function () {
        _applySettingsFormFromCache();
        return loadDnsAiSettings();
    }).catch(function () {});
}

/**
 * 保存设置
 */
function saveSettings() {
    if (!settingsCache) settingsCache = {};
    settingsCache.browser_path = document.getElementById('setting-browser-path').value.trim();
    var autoStartEl = document.getElementById('setting-auto-start');
    if (autoStartEl) settingsCache.auto_start = !!autoStartEl.checked;
    ['ali', 'dnspod', 'tencent'].forEach(function (p) { syncInputsToActiveProfile(p); });
    var dnsAiUpdates = collectDnsAiSettingsUpdates();
    Promise.all([
        persistSettings(),
        callApi('update_dns_parse_config', dnsAiUpdates)
    ]).then(function (results) {
        var okSettings = results[0];
        var dnsRes = results[1];
        if (dnsRes && dnsRes.success) {
            dnsParseConfigCache = dnsRes.data || dnsParseConfigCache;
            _renderDnsParseConfigHint();
        }
        if (okSettings && dnsRes && dnsRes.success) {
            showToast('设置已保存', 'success');
        } else if (okSettings) {
            showToast('部分保存失败: ' + ((dnsRes && dnsRes.message) || 'AI 配置'), 'error');
        } else {
            showToast((dnsRes && dnsRes.message) || '保存失败', 'error');
        }
    }).catch(function (err) {
        showToast('保存失败: ' + (err.message || err), 'error');
    });
}

/** 初始化设置模块 */
function initSettingsModule() {
    document.getElementById('btn-save-settings').addEventListener('click', saveSettings);

    document.getElementById('setting-ali-profile').addEventListener('change', function () {
        _setActiveProfileId('ali', this.value);
        applyProfileToInputs('ali');
        persistSettings();
    });
    document.getElementById('setting-dnspod-profile').addEventListener('change', function () {
        _setActiveProfileId('dnspod', this.value);
        applyProfileToInputs('dnspod');
        persistSettings();
    });
    document.getElementById('setting-tencent-profile').addEventListener('change', function () {
        _setActiveProfileId('tencent', this.value);
        applyProfileToInputs('tencent');
        persistSettings();
    });

    document.getElementById('btn-ali-profile-add').addEventListener('click', function () { openProfileModal('ali', null); });
    document.getElementById('btn-ali-profile-edit').addEventListener('click', function () {
        var pid = _getActiveProfileId('ali');
        if (!pid) { showToast('请先选择档案再编辑', 'error'); return; }
        openProfileModal('ali', _findProfile('ali', pid));
    });
    document.getElementById('btn-ali-profile-del').addEventListener('click', function () { deleteActiveProfile('ali'); });

    document.getElementById('btn-dnspod-profile-add').addEventListener('click', function () { openProfileModal('dnspod', null); });
    document.getElementById('btn-dnspod-profile-edit').addEventListener('click', function () {
        var pid = _getActiveProfileId('dnspod');
        if (!pid) { showToast('请先选择档案再编辑', 'error'); return; }
        openProfileModal('dnspod', _findProfile('dnspod', pid));
    });
    document.getElementById('btn-dnspod-profile-del').addEventListener('click', function () { deleteActiveProfile('dnspod'); });

    document.getElementById('btn-tencent-profile-add').addEventListener('click', function () { openProfileModal('tencent', null); });
    document.getElementById('btn-tencent-profile-edit').addEventListener('click', function () {
        var pid = _getActiveProfileId('tencent');
        if (!pid) { showToast('请先选择档案再编辑', 'error'); return; }
        openProfileModal('tencent', _findProfile('tencent', pid));
    });
    document.getElementById('btn-tencent-profile-del').addEventListener('click', function () { deleteActiveProfile('tencent'); });

    document.getElementById('btn-save-profile').addEventListener('click', saveProfileFromModal);
    document.getElementById('btn-cancel-profile').addEventListener('click', function () { hideModal('profile-modal'); });
    document.getElementById('btn-close-profile-modal').addEventListener('click', function () { hideModal('profile-modal'); });

    var dnsProfileSelect = document.getElementById('dns-profile-select');
    if (dnsProfileSelect) {
        dnsProfileSelect.addEventListener('change', function () {
            if (!dnsCurrentProvider) return;
            _setActiveProfileId(dnsCurrentProvider, this.value);
            persistSettings().then(function () {
                loadDnsDomains(dnsCurrentProvider);
            });
        });
    }
}

// ==================== 初始化 ====================

/**
 * 应用初始化入口
 */
function initWindowChrome() {
    var btnMin = document.getElementById('btn-window-minimize');
    var btnMax = document.getElementById('btn-window-maximize');
    var btnClose = document.getElementById('btn-window-close');
    if (btnMin) {
        btnMin.addEventListener('click', function () {
            waitForApiReady().then(function () {
                return callApi('window_minimize');
            }).catch(function () {});
        });
    }
    if (btnMax) {
        btnMax.addEventListener('click', function () {
            waitForApiReady().then(function () {
                return callApi('window_toggle_maximize');
            }).then(function (r) {
                if (r && r.success) _setWindowMaximizeIcon(!!r.maximized);
            }).catch(function () {});
        });
    }
    _setWindowMaximizeIcon(false);
    if (btnClose) {
        btnClose.addEventListener('click', function () {
            waitForApiReady().then(function () {
                return callApi('window_hide');
            }).catch(function () {});
        });
    }
}

/** 模态框标题栏拖动 */
function initModalDrag() {
    document.querySelectorAll('.modal-overlay .modal-header').forEach(function (header) {
        var modal = header.closest('.modal');
        if (!modal || header._dragBound) return;
        header._dragBound = true;
        var dragging = false;
        var startX = 0;
        var startY = 0;
        var origLeft = 0;
        var origTop = 0;

        header.addEventListener('mousedown', function (e) {
            if (e.button !== 0 || e.target.closest('button')) return;
            dragging = true;
            modal.classList.add('modal-dragging');
            var rect = modal.getBoundingClientRect();
            modal.style.position = 'fixed';
            modal.style.margin = '0';
            modal.style.left = rect.left + 'px';
            modal.style.top = rect.top + 'px';
            modal.style.transform = 'none';
            startX = e.clientX;
            startY = e.clientY;
            origLeft = rect.left;
            origTop = rect.top;
            e.preventDefault();
        });

        document.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            modal.style.left = (origLeft + e.clientX - startX) + 'px';
            modal.style.top = (origTop + e.clientY - startY) + 'px';
        });

        document.addEventListener('mouseup', function () {
            if (!dragging) return;
            dragging = false;
            modal.classList.remove('modal-dragging');
        });
    });
}

function initApp() {
    bindWindowActivationCollapse();
    initWindowChrome();
    initModalDrag();
    initNavigation();
    initServerModule();
    initScriptsModule();
    initDnsModule();
    initSettingsModule();
    initGlobalLogDrawer();
    initScriptRunDiscovery();
    waitForApiReady().then(function () {
        return Promise.all([
            ensureSettingsLoaded(true),
            ensureDnsParseConfigLoaded(true)
        ]);
    }).then(function () {
        return loadScripts();
    }).then(function () {
        loadPanelData('nav-servers', true);
    }).catch(function (err) {
        console.error('初始化失败:', err);
        showToast('应用初始化失败：' + (err.message || '未知错误'), 'error');
    }).finally(function () {
        window.__uiActivationReady = true;
    });
}

document.addEventListener('DOMContentLoaded', initApp);
