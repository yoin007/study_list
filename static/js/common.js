// ========== 公共导航 / 状态 / 跨页交互 ==========
// 所有孩子页（child / rewards / history / notes）和 admin 页共用。
// 引入顺序：<script src="/static/js/common.js"></script> 必须在页面内联 <script> 之前。

const API = '/api';

// 读取当前登录孩子
async function getCurrentChild() {
    try {
        const r = await fetch(`${API}/current_user`);
        return (await r.json()).child;
    } catch { return null; }
}

// 读取所有孩子（用于 select 渲染）
async function loadChildren() {
    try {
        const r = await fetch(`${API}/children`);
        return (await r.json()).children || [];
    } catch { return []; }
}

// ========== 统一顶部按钮组 ==========
// 在 top-bar 内放一个占位 <div id="topBarActions"></div>，由本函数填充按钮。
// child.html / rewards / history / notes 各页自己写页面标题 + 左侧日期，右侧按钮统一由这里渲染。
async function renderTopBarActions(opts = {}) {
    const box = document.getElementById('topBarActions');
    if (!box) return;
    const children = await loadChildren();
    const me = await getCurrentChild();

    let html = '';

    // 多孩子：显示下拉切换；单孩子：只显示名字 pill
    if (children.length > 1) {
        html += `<select id="globalChildSelect" onchange="switchGlobalChild()" style="background:rgba(255,255,255,0.2);color:white;border:1px solid rgba(255,255,255,0.3);border-radius:12px;padding:4px 10px;font-size:13px;appearance:none;cursor:pointer;">`;
        children.forEach(c => {
            const sel = (me && String(c.id) === String(me.id)) ? ' selected' : '';
            html += `<option value="${c.id}"${sel} style="color:#333;background:white;">${c.name}</option>`;
        });
        html += `</select>`;
    } else if (me) {
        html += `<span style="color:white;font-size:13px;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:12px;">👶 ${me.name}</span>`;
    }

    html += `<button class="admin-entry" id="darkToggle" onclick="toggleDarkMode()" title="深色模式">🌙</button>`;
    // admin 页不要 ⚙️（已经在后台了）
    if (!opts.isAdmin) {
        html += `<button class="admin-entry" onclick="showAdminLogin()" title="家长后台">⚙️</button>`;
    }
    html += `<button class="admin-entry" onclick="logout()" title="退出登录">🔒</button>`;

    box.innerHTML = html;
    // 深色模式：根据 localStorage 给按钮打状态 + 给 body 加 class
    initDarkMode();
}

// 切孩子：POST /api/login + 刷新当前页
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

// ========== 深色模式 ==========
function initDarkMode() {
    const on = localStorage.getItem('darkMode') === '1';
    document.body.classList.toggle('dark-mode', on);
}
function toggleDarkMode() {
    const on = document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', on ? '1' : '0');
}

// ========== 退出登录 ==========
async function logout() {
    if (!confirm('确定退出吗？')) return;
    await fetch(`${API}/logout`, {method: 'POST'});
    location.href = '/login';
}

// ========== 家长后台 PIN 弹窗 ==========
function showAdminLogin() {
    // 复用 child.html 的 adminModal（如果存在），否则简单 prompt
    const modal = document.getElementById('adminModal');
    if (modal) {
        modal.classList.add('show');
        document.getElementById('adminPin').value = '';
        setTimeout(() => document.getElementById('adminPin').focus(), 50);
    } else {
        const pin = prompt('请输入家长 PIN 码');
        if (!pin) return;
        fetch(`${API}/admin/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pin})
        }).then(r => r.json()).then(d => {
            if (d.success) location.href = '/admin';
            else alert('PIN 码错误');
        });
    }
}

// 页面初始化时自动渲染顶部按钮（DOMContentLoaded 之后）
document.addEventListener('DOMContentLoaded', () => {
    const isAdmin = !!document.getElementById('adminMain');
    renderTopBarActions({isAdmin});
});
