/**
 * 通用工具函数
 */

/** debounce - 防抖函数，延迟执行直到停止调用后 wait 毫秒 */
function debounce(fn, wait = 200) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), wait);
    };
}

/** escapeHtml - 统一 HTML 转义，防止 XSS */
function escapeHtml(str) {
    if (!str && str !== 0) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 暴露到全局
window.debounce = debounce;
window.escapeHtml = escapeHtml;

/**
 * withBtnLoading - 异步操作期间禁用按钮并显示 loading 文字，防重复点击
 * @param {HTMLElement} btn  - 触发按钮
 * @param {Function}    fn   - 要执行的 async 函数
 * @param {string}      [loadingText='处理中...'] - loading 时显示的文字
 */
async function withBtnLoading(btn, fn, loadingText = '处理中...') {
    if (!btn || btn.disabled) return;
    const originalText = btn.textContent;
    const originalDisabled = btn.disabled;
    btn.disabled = true;
    btn.textContent = loadingText;
    try {
        await fn();
    } finally {
        btn.disabled = originalDisabled;
        btn.textContent = originalText;
    }
}

window.withBtnLoading = withBtnLoading;

// ==================== Toast 通知 ====================

function showToast(message, type = 'error', duration = 3000) {
    // 创建容器（如果不存在）
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    // 图标映射
    const icons = {
        error: '✕',
        warning: '⚠',
        success: '✓',
        info: 'ℹ'
    };

    // 创建toast元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <span class="toast-close" onclick="this.parentElement.classList.add('toast-exit');setTimeout(()=>this.parentElement.remove(),300)">×</span>
    `;

    // 点击toast本身也可以关闭
    toast.addEventListener('click', function(e) {
        if (e.target.classList.contains('toast-close')) return;
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 300);
    });

    // 添加到容器
    container.appendChild(toast);

    // 自动消失
    if (duration > 0) {
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('toast-exit');
                setTimeout(() => {
                    if (toast.parentElement) toast.remove();
                }, 300);
            }
        }, duration);
    }

    return toast;
}

// 快捷方法
window.showError = (msg) => showToast(msg, 'error');
window.showWarning = (msg) => showToast(msg, 'warning');
window.showSuccess = (msg) => showToast(msg, 'success');
window.showInfo = (msg) => showToast(msg, 'info');
