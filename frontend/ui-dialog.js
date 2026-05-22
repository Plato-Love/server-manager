/**
 * 通用对话框与局部阻塞层（不冻结整个应用，仅遮住指定弹窗/区域）
 */
var UiDialog = (function () {
    var busyLayers = Object.create(null);

    function getScopeEl(scope) {
        if (!scope) return document.body;
        if (typeof scope === 'string') {
            var el = document.getElementById(scope);
            if (el) {
                if (el.classList.contains('modal-overlay')) {
                    return el.querySelector('.modal') || el;
                }
                return el;
            }
            return document.body;
        }
        return scope;
    }

    function ensureBusyLayer(scopeEl) {
        var isBody = scopeEl === document.body;
        var id = scopeEl.id || ('ui-busy-' + Math.random().toString(36).slice(2, 8));
        if (!scopeEl.id) scopeEl.id = id;
        if (busyLayers[id]) return busyLayers[id];

        if (!isBody && window.getComputedStyle(scopeEl).position === 'static') {
            scopeEl.classList.add('ui-busy-scope');
        }

        var layer = document.createElement('div');
        layer.className = 'ui-busy-overlay';
        if (isBody) {
            layer.classList.add('ui-busy-overlay-app');
        }
        layer.innerHTML =
            '<div class="ui-busy-panel">'
            + '<div class="ui-busy-spinner" aria-hidden="true"></div>'
            + '<div class="ui-busy-text">处理中，请稍候…</div>'
            + '</div>';
        scopeEl.appendChild(layer);
        busyLayers[id] = layer;
        return layer;
    }

    function showBusy(scope, message) {
        var scopeEl = getScopeEl(scope);
        var layer = ensureBusyLayer(scopeEl);
        var textEl = layer.querySelector('.ui-busy-text');
        if (textEl) textEl.textContent = message || '处理中，请稍候…';
        layer.classList.add('is-active');
        scopeEl.setAttribute('aria-busy', 'true');
    }

    function hideBusy(scope) {
        var scopeEl = getScopeEl(scope);
        var layer = busyLayers[scopeEl.id];
        if (!layer) {
            layer = scopeEl.querySelector(':scope > .ui-busy-overlay');
        }
        if (layer) layer.classList.remove('is-active');
        scopeEl.removeAttribute('aria-busy');
    }

    function runBusy(scope, message, task) {
        showBusy(scope, message);
        return Promise.resolve()
            .then(task)
            .finally(function () {
                hideBusy(scope);
            });
    }

    function showModal(id) {
        var modal = document.getElementById(id);
        if (modal) modal.classList.add('modal-active');
        if (window.pywebview && window.pywebview.api && window.pywebview.api.window_restore) {
            try {
                window.pywebview.api.window_restore();
            } catch (e) { /* ignore */ }
        }
    }

    function hideModal(id) {
        var modal = document.getElementById(id);
        if (modal) modal.classList.remove('modal-active');
    }

    function open(options) {
        options = options || {};
        return new Promise(function (resolve) {
            var modal = document.getElementById('dialog-modal');
            var titleEl = document.getElementById('dialog-title');
            var messageEl = document.getElementById('dialog-message');
            var inputGroup = document.getElementById('dialog-input-group');
            var inputEl = document.getElementById('dialog-input');
            var btnCancel = document.getElementById('btn-dialog-cancel');
            var btnConfirm = document.getElementById('btn-dialog-confirm');
            var btnClose = document.getElementById('btn-close-dialog-modal');
            if (!modal || !titleEl || !messageEl || !inputGroup || !inputEl || !btnCancel || !btnConfirm || !btnClose) {
                resolve({ ok: false, value: '' });
                return;
            }

            var needInput = !!options.input;
            titleEl.textContent = options.title || '提示';
            messageEl.textContent = options.message || '';
            inputGroup.style.display = needInput ? 'block' : 'none';
            inputEl.placeholder = options.placeholder || '';
            inputEl.value = options.defaultValue || '';
            btnCancel.textContent = options.cancelText || '取消';
            btnConfirm.textContent = options.confirmText || '确定';
            btnConfirm.className = options.danger ? 'btn btn-danger' : 'btn btn-primary';
            btnCancel.style.display = options.hideCancel ? 'none' : '';

            var settled = false;
            function cleanup() {
                btnCancel.removeEventListener('click', onCancel);
                btnClose.removeEventListener('click', onCancel);
                btnConfirm.removeEventListener('click', onConfirm);
                modal.removeEventListener('click', onOverlayClick);
                inputEl.removeEventListener('keydown', onInputKeydown);
                document.removeEventListener('keydown', onEscKeydown);
                hideModal('dialog-modal');
            }
            function done(ok) {
                if (settled) return;
                settled = true;
                var value = needInput ? (inputEl.value || '') : '';
                cleanup();
                resolve({ ok: !!ok, value: value });
            }
            function onCancel() { done(false); }
            function onConfirm() { done(true); }
            function onOverlayClick(e) {
                if (options.closeOnOverlay === false) return;
                if (e.target === modal) done(false);
            }
            function onInputKeydown(e) {
                if (e.key === 'Enter') done(true);
            }
            function onEscKeydown(e) {
                if (e.key === 'Escape') done(false);
            }

            btnCancel.addEventListener('click', onCancel);
            btnClose.addEventListener('click', onCancel);
            btnConfirm.addEventListener('click', onConfirm);
            modal.addEventListener('click', onOverlayClick);
            inputEl.addEventListener('keydown', onInputKeydown);
            document.addEventListener('keydown', onEscKeydown);
            showModal('dialog-modal');
            if (needInput) {
                setTimeout(function () {
                    inputEl.focus();
                    inputEl.select();
                }, 0);
            }
        });
    }

    function alert(message, title) {
        return open({
            title: title || '提示',
            message: message || '',
            hideCancel: true,
            confirmText: '知道了',
            closeOnOverlay: true
        }).then(function (r) { return !!r.ok; });
    }

    function confirm(message, options) {
        options = options || {};
        return open({
            title: options.title || '请确认',
            message: message || '',
            confirmText: options.confirmText || '确定',
            cancelText: options.cancelText || '取消',
            danger: !!options.danger,
            closeOnOverlay: options.closeOnOverlay !== false
        }).then(function (r) { return !!r.ok; });
    }

    function prompt(message, options) {
        options = options || {};
        return open({
            title: options.title || '请输入',
            message: message || '',
            input: true,
            placeholder: options.placeholder || '',
            defaultValue: options.defaultValue || '',
            confirmText: options.confirmText || '确定',
            cancelText: options.cancelText || '取消'
        });
    }

    return {
        showModal: showModal,
        hideModal: hideModal,
        open: open,
        alert: alert,
        confirm: confirm,
        prompt: prompt,
        showBusy: showBusy,
        hideBusy: hideBusy,
        runBusy: runBusy
    };
})();
