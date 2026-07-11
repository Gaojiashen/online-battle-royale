// ui.js — 公共 UI 工具（错误提示、按钮状态、Toast）
const UI = {
  setLoading(btn, text) {
    btn._origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = text;
  },

  clearLoading(btn) {
    btn.disabled = false;
    if (btn._origText) btn.textContent = btn._origText;
  },

  showError(msg) {
    const el = document.getElementById('error-bar');
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 6000);
  },

  showToast(msg, duration = 3000) {
    let el = document.getElementById('toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast';
      el.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#333;color:#e0d8c0;padding:10px 24px;border-radius:8px;font-size:14px;z-index:999;transition:opacity .3s;';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.opacity = '1';
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.style.opacity = '0'; }, duration);
  }
};

// 全局包装函数（保持 HTML onclick 兼容）
function setBtnLoading(btn, text) { UI.setLoading(btn, text); }
function resetBtn(btn) { UI.clearLoading(btn); }
function showError(msg) { UI.showError(msg); }
function now() { return new Date().toLocaleTimeString(); }
