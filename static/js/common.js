// ========== 公共导航 / 状态 / 跨页交互 ==========
// 所有孩子页（child / rewards / history / notes）和 admin 页共用。
// 引入顺序：<script src="/static/js/common.js"></script> 必须在页面内联 <script> 之前。

const API = '/api';

// ---------- 轻提示 toast（自动消失，不打断操作） ----------
function showToast(msg, dur = 2600) {
    let box = document.getElementById('toastBox');
    if (!box) {
        box = document.createElement('div');
        box.id = 'toastBox';
        box.style.cssText = 'position:fixed;top:60px;right:16px;z-index:2000;display:flex;flex-direction:column;gap:8px;pointer-events:none;';
        document.body.appendChild(box);
    }
    const item = document.createElement('div');
    item.style.cssText = 'background:rgba(30,30,30,0.92);color:white;padding:10px 16px;border-radius:10px;font-size:14px;box-shadow:0 4px 16px rgba(0,0,0,0.2);pointer-events:auto;max-width:80vw;animation:toastIn 0.2s ease-out;';
    item.textContent = msg;
    box.appendChild(item);
    setTimeout(() => {
        item.style.opacity = '0';
        item.style.transition = 'opacity 0.3s';
        setTimeout(() => item.remove(), 300);
    }, dur);
}

// ---------- 通用确认模态框（替代 window.confirm） ----------
// 返回 Promise<boolean>：true=确认, false=取消
function confirmDialog(message, title = '确认操作', confirmText = '确定', cancelText = '取消') {
    return new Promise((resolve) => {
        let modal = document.getElementById('commonConfirmModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'commonConfirmModal';
            modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:2000;display:flex;justify-content:center;align-items:center;padding:20px;';
            modal.innerHTML = `
                <div style="background:white;border-radius:16px;padding:24px;max-width:320px;width:100%;text-align:center;">
                    <h3 id="confirmTitle" style="margin:0 0 12px;font-size:17px;color:#333;"></h3>
                    <p id="confirmMsg" style="margin:0 0 20px;font-size:14px;color:#666;line-height:1.6;"></p>
                    <div style="display:flex;gap:10px;">
                        <button id="confirmCancel" style="flex:1;padding:10px;border:1px solid #ddd;background:white;border-radius:10px;font-size:14px;cursor:pointer;color:#666;">取消</button>
                        <button id="confirmOk" style="flex:1;padding:10px;border:none;background:#e74c3c;color:white;border-radius:10px;font-size:14px;cursor:pointer;">确定</button>
                    </div>
                </div>`;
            document.body.appendChild(modal);
        }
        // 深色模式适配
        if (document.body.classList.contains('dark-mode')) {
            modal.querySelector('div').style.background = '#1f1f1f';
            modal.querySelector('#confirmTitle').style.color = '#eee';
            modal.querySelector('#confirmMsg').style.color = '#bbb';
        }
        modal.querySelector('#confirmTitle').textContent = title;
        modal.querySelector('#confirmMsg').textContent = message;
        modal.querySelector('#confirmOk').textContent = confirmText;
        modal.querySelector('#confirmCancel').textContent = cancelText;
        modal.style.display = 'flex';

        const cleanup = (result) => {
            modal.style.display = 'none';
            modal.querySelector('#confirmOk').onclick = null;
            modal.querySelector('#confirmCancel').onclick = null;
            resolve(result);
        };
        modal.querySelector('#confirmOk').onclick = () => cleanup(true);
        modal.querySelector('#confirmCancel').onclick = () => cleanup(false);
    });
}

// ---------- 通用 PIN 输入模态框 ----------
function pinDialog(title = '请输入家长 PIN 码') {
    return new Promise((resolve) => {
        let modal = document.getElementById('commonPinModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'commonPinModal';
            modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:2000;display:flex;justify-content:center;align-items:center;padding:20px;';
            modal.innerHTML = `
                <div style="background:white;border-radius:16px;padding:24px;max-width:320px;width:100%;text-align:center;">
                    <h3 id="pinTitle" style="margin:0 0 16px;font-size:17px;color:#333;"></h3>
                    <input id="pinInput" type="password" inputmode="numeric" placeholder="PIN 码"
                           style="width:100%;padding:12px;border:1px solid #ddd;border-radius:10px;font-size:18px;text-align:center;letter-spacing:8px;box-sizing:;">
                    <div style="display:flex;gap:10px;margin-top:18px;">
                        <button id="pinCancel" style="flex:1;padding:10px;border:1px solid #ddd;background:white;border-radius:10px;font-size:14px;cursor:pointer;color:#666;">取消</button>
                        <button id="pinOk" style="flex:1;padding:10px;border:none;background:#4b7791;color:white;border-radius:10px;font-size:14px;cursor:pointer;">确定</button>
                    </div>
                    <p id="pinError" style="color:#e74c3c;font-size:12px;margin:10px 0 0;display:none;"></p>
                </div>`;
            document.body.appendChild(modal);
        }
        // 深色模式适配
        if (document.body.classList.contains('dark-mode')) {
            modal.querySelector('div').style.background = '#1f1f1f';
            modal.querySelector('#pinTitle').style.color = '#eee';
        }
        modal.querySelector('#pinTitle').textContent = title;
        modal.querySelector('#pinInput').value = '';
        modal.querySelector('#pinError').style.display = 'none';
        modal.style.display = 'flex';
        setTimeout(() => modal.querySelector('#pinInput').focus(), 50);

        const cleanup = (result) => {
            modal.style.display = 'none';
            modal.querySelector('#pinOk').onclick = null;
            modal.querySelector('#pinCancel').onclick = null;
            modal.querySelector('#pinInput').onkeydown = null;
            resolve(result);
        };
        const doOk = () => {
            const v = modal.querySelector('#pinInput').value.trim();
            if (!v) { cleanup(null); return; }
            cleanup(v);
        };
        modal.querySelector('#pinOk').onclick = doOk;
        modal.querySelector('#pinCancel').onclick = () => cleanup(null);
        modal.querySelector('#pinInput').onkeydown = (e) => {
            if (e.key === 'Enter') doOk();
            else if (e.key === 'Escape') cleanup(null);
        };
    });
}

// 验证 PIN 并决定是否重试（用于 showAdminLogin）
async function verifyPin() {
    for (let attempt = 0; attempt < 3; attempt++) {
        const pin = await pinDialog('请输入家长 PIN 码');
        if (pin === null) return null;  // 取消
        const r = await fetch(`${API}/admin/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pin})
        });
        const d = await r.json();
        if (d.success) return pin;
        // 错了：显示错误信息并让用户重试
        const modal = document.getElementById('commonPinModal');
        const err = modal?.querySelector('#pinError');
        if (err) {
            err.textContent = 'PIN 码错误，再试一次';
            err.style.display = 'block';
        }
        const input = modal?.querySelector('#pinInput');
        if (input) { input.value = ''; input.focus(); }
        // 等待用户再点确定/取消——不跳出循环
        await new Promise((r) => {
            const okBtn = modal.querySelector('#pinOk');
            const cancelBtn = modal.querySelector('#pinCancel');
            const onOk = () => { okBtn.removeEventListener('click', onOk); cancelBtn.removeEventListener('click', onCancel); r(); };
            const onCancel = () => { okBtn.removeEventListener('click', onOk); cancelBtn.removeEventListener('click', onCancel); r(); };
            okBtn.addEventListener('click', onOk);
            cancelBtn.addEventListener('click', onCancel);
        });
    }
    return null;  // 超过 3 次
}

// ---------- 读取当前登录孩子 ----------
async function getCurrentChild() {
    try {
        const r = await fetch(`${API}/current_user`);
        return (await r.json()).child;
    } catch { return null; }
}

// ---------- 读取所有孩子（用于 select 渲染） ----------
async function loadChildren() {
    try {
        const r = await fetch(`${API}/children`);
        return (await r.json()).children || [];
    } catch { return []; }
}

// ---------- 统一顶部按钮组 ----------
async function renderTopBarActions(opts = {}) {
    const box = document.getElementById('topBarActions');
    if (!box) return;
    const children = await loadChildren();
    const me = await getCurrentChild();

    let html = '';
    if (children.length > 1) {
        html += `<select id="globalChildSelect" onchange="switchGlobalChild()" style="background:#faf6ee;color:#4f4a41;border:1px solid #d9d0bd;border-radius:12px;padding:4px 10px;font-size:13px;appearance:none;cursor:pointer;">`;
        children.forEach(c => {
            const sel = (me && String(c.id) === String(me.id)) ? ' selected' : '';
            html += `<option value="${c.id}"${sel} style="color:#333;background:white;">${c.name}</option>`;
        });
        html += `</select>`;
    } else if (me) {
        html += `<span style="color:#4f4a41;font-size:13px;background:#faf6ee;padding:4px 12px;border-radius:12px;">👶 ${me.name}</span>`;
    }
    html += `<button class="admin-entry" id="darkToggle" onclick="toggleDarkMode()" title="深色模式">🌙</button>`;
    if (!opts.isAdmin) {
        html += `<button class="admin-entry" onclick="showAdminLogin()" title="家长后台">⚙️</button>`;
    }
    html += `<button class="admin-entry" onclick="logout()" title="退出登录">🔒</button>`;
    box.innerHTML = html;
    initDarkMode();
}

async function switchGlobalChild() {
    const sel = document.getElementById('globalChildSelect');
    if (!sel) return;
    await fetch(`${API}/login`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({child_id: parseInt(sel.value)})
    });
    location.reload();
}

// ---------- 深色模式 ----------
function initDarkMode() {
    const on = localStorage.getItem('darkMode') === '1';
    document.body.classList.toggle('dark-mode', on);
}
function toggleDarkMode() {
    const on = document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', on ? '1' : '0');
}

// ---------- 退出登录 ----------
async function logout() {
    const ok = await confirmDialog('确定退出当前孩子的账号吗？', '退出登录', '退出', '取消');
    if (!ok) return;
    await fetch(`${API}/logout`, {method: 'POST'});
    location.href = '/login';
}

// ---------- 家长后台 PIN 弹窗 ----------
async function showAdminLogin() {
    const pin = await verifyPin();
    if (pin === null) return;
    location.href = '/admin';
}

// ---------- 页面初始化 ----------
document.addEventListener('DOMContentLoaded', () => {
    const isAdmin = !!document.getElementById('adminMain');
    renderTopBarActions({isAdmin});
});
