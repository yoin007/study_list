// ========== 全局状态 ==========
let todayData = null;
let timerInterval = null;
let breakCheckInterval = null;
let modalTimerStartPending = false;

// ========== 备份提醒 ==========
async function checkBackupReminder() {
    // 同一个自然日只弹一次提示
    const lastKey = 'backupReminderShown';
    const today = new Date().toISOString().slice(0, 10);
    if (localStorage.getItem(lastKey) === today) return;
    try {
        const res = await fetch('/api/backup/status');
        if (!res.ok) return;
        const d = await res.json();
        if (d.need_warning) {
            const msg = `📦 已 ${d.days_since} 天没做完整备份了（附件 ${d.attachments_size_mb}MB），设置页点「导出完整备份」`;
            showToast(msg, 5000);
            localStorage.setItem(lastKey, today);
        }
    } catch (e) {}
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
    loadCurrentUser();
    loadToday();
    updateDateDisplay();
    setupHomePrompt();
    loadNoteDueCount();
    checkBackupReminder();
});

// ========== 随手记到期提醒 ==========
async function loadNoteDueCount() {
    const card = document.getElementById('noteDueCard');
    if (!card) return;
    try {
        const res = await fetch('/api/notes/due');
        const data = await res.json();
        if (data.count > 0) {
            document.getElementById('noteDueCount').textContent = data.count;
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    } catch (e) { /* 随手记模块尚未就绪时不报错 */ }
}

// 全局：如果有 Notes Due 角标元素，也更新一下
(async function updateNotesBadgeGlobally() {
    const b = document.getElementById('notesDueBadge');
    if (!b) return;
    try {
        const d = await fetch('/api/notes/due').then(r => r.json());
        if (d.count > 0) {
            b.textContent = d.count;
            b.style.display = 'inline-block';
        } else {
            b.style.display = 'none';
        }
    } catch (e) {}
})();

// ========== 加到主屏幕引导 ==========
function isStandalone() {
    return window.navigator.standalone === true ||
        (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
}
function setupHomePrompt() {
    const bar = document.getElementById('homePrompt');
    if (!bar) return;
    if (isStandalone()) return;
    if (localStorage.getItem('homePromptDismissed') === '1') return;
    const ua = navigator.userAgent || '';
    const isIOS = /iP(hone|ad|od)/.test(ua) || (ua.includes('Mac') && 'ontouchend' in document);
    const txt = document.getElementById('homePromptText');
    if (isIOS) {
        txt.textContent = '📲 点底部分享按钮，选"添加到主屏幕"，下次点图标全屏进入';
    } else {
        txt.textContent = '📲 点浏览器菜单，选"添加到主屏幕/安装应用"，下次点图标全屏进入';
    }
    bar.style.display = 'flex';
}
function dismissHomePrompt() {
    const bar = document.getElementById('homePrompt');
    if (bar) bar.style.display = 'none';
    localStorage.setItem('homePromptDismissed', '1');
}

async function loadCurrentUser() {
    const res = await fetch('/api/current_user');
    const data = await res.json();
    // 顶部孩子 pill 已由 common.js 渲染（renderTopBarActions）；
    // 这里只做兜底更新，避免 app.js 里其他地方依赖时出错
    const el = document.getElementById('currentUserName');
    if (el && data.name) el.textContent = data.name;
}

// ========== 深色模式 ==========
function syncDarkIcon() {
    const btn = document.getElementById('darkToggle');
    if (btn) btn.textContent = document.body.classList.contains('dark-mode') ? '☀️' : '🌙';
}
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    const isOn = document.body.classList.contains('dark-mode');
    localStorage.setItem('darkMode', isOn ? '1' : '0');
    syncDarkIcon();
}

// 页面加载时恢复深色模式
if (localStorage.getItem('darkMode') === '1') {
    document.body.classList.add('dark-mode');
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncDarkIcon);
} else {
    syncDarkIcon();
}

function playSound(type) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        
        if (type === 'complete') {
            // 完成音效：上升的do-mi-sol
            osc.type = 'sine';
            osc.frequency.setValueAtTime(523, ctx.currentTime);
            osc.frequency.setValueAtTime(659, ctx.currentTime + 0.15);
            osc.frequency.setValueAtTime(784, ctx.currentTime + 0.3);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.5);
        } else if (type === 'remind') {
            // 提醒音效：两声短促的叮
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.3);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.setValueAtTime(0.3, ctx.currentTime + 0.3);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.6);
        } else if (type === 'tick') {
            // 勾选音效：清脆的滴
            osc.type = 'square';
            osc.frequency.setValueAtTime(1000, ctx.currentTime);
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.1);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.1);
        }
    } catch (e) {
        console.log('音效播放失败:', e);
    }
}

async function logout() {
    await fetch('/api/logout');
    window.location.href = '/';
}

function ensurePinModal() {
    if (document.getElementById('pinModal')) return;
    const div = document.createElement('div');
    div.id = 'pinModal';
    div.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:9999;align-items:center;justify-content:center;';
    div.innerHTML = `
        <div style="background:#fffdf8;border-radius:12px;padding:22px;width:90%;max-width:340px;box-shadow:0 8px 30px rgba(0,0,0,0.2);">
            <h3 style="margin:0 0 14px;font-size:16px;text-align:center;">⚙ 家长后台验证</h3>
            <div style="position:relative;">
                <input type="password" id="pinInput" placeholder="请输入家长PIN码" inputmode="numeric"
                       style="width:100%;padding:10px 38px 10px 12px;border:1px solid #e0e0e0;border-radius:8px;box-sizing:border-box;font-size:15px;">
                <button type="button" onclick="togglePinVisible()" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;font-size:16px;">👁</button>
            </div>
            <div id="pinError" style="color:#c62828;font-size:12px;margin-top:6px;min-height:16px;"></div>
            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px;">
                <button onclick="closePinModal()" style="padding:8px 16px;background:#f0f0f0;border:none;border-radius:8px;cursor:pointer;">取消</button>
                <button onclick="submitPin()" style="padding:8px 16px;background:#4b7791;color:#fff;border:none;border-radius:8px;cursor:pointer;">确定</button>
            </div>
        </div>`;
    document.body.appendChild(div);
    const inp = div.querySelector('#pinInput');
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') submitPin(); });
}
function togglePinVisible() {
    const inp = document.getElementById('pinInput');
    inp.type = inp.type === 'password' ? 'text' : 'password';
}
function closePinModal() {
    const m = document.getElementById('pinModal');
    if (m) m.style.display = 'none';
}
function submitPin() {
    const pin = document.getElementById('pinInput').value.trim();
    if (!pin) { document.getElementById('pinError').textContent = '请输入PIN码'; return; }
    fetch('/api/admin/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pin: pin})
    }).then(r => r.json()).then(data => {
        if (data.success) {
            window.location.href = '/admin';
        } else {
            document.getElementById('pinError').textContent = 'PIN码错误，请重试';
            document.getElementById('pinInput').select();
        }
    });
}
function showAdminLogin() {
    ensurePinModal();
    document.getElementById('pinError').textContent = '';
    const inp = document.getElementById('pinInput');
    inp.value = '';
    inp.type = 'password';
    document.getElementById('pinModal').style.display = 'flex';
    setTimeout(() => inp.focus(), 50);
}

function updateDateDisplay() {
    const now = new Date();
    const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    document.getElementById('dateDisplay').textContent =
        `${now.getMonth() + 1}月${now.getDate()}日 ${days[now.getDay()]}`;
}

// ========== 加载今日数据 ==========
async function loadToday() {
    try {
        const res = await fetch('/api/today');
        todayData = await res.json();
        renderTasks();
        renderHabits();
        renderTimer();
        renderFocusChart();
        renderPoints();
        // 显示家长留言
        if (todayData.note) {
            document.getElementById('parentNote').style.display = 'block';
            document.getElementById('parentNoteText').textContent = todayData.note;
        } else {
            document.getElementById('parentNote').style.display = 'none';
        }
        // 护眼/休息提醒轮询（覆盖墙钟手动开启和任务自动开启两种路径）
        startBreakCheck();
    } catch (e) {
        console.error('加载失败', e);
    }
}

// ========== 渲染任务列表 ==========
function renderTasks() {
    const container = document.getElementById('taskList');
    if (!todayData.tasks || todayData.tasks.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:#999;">今天还没有作业任务<br><small>请家长在后台录入</small></div>';
        return;
    }

    // 按科目分组
    const subjects = {};
    todayData.tasks.forEach(t => {
        if (!subjects[t.subject]) subjects[t.subject] = [];
        subjects[t.subject].push(t);
    });

    let html = '';
    for (const [subject, tasks] of Object.entries(subjects)) {
        const doneCount = tasks.filter(t => t.done).length;
        html += `<div class="subject-group">`;
        html += `<div class="subject-title">${subject} <span class="badge">${doneCount}/${tasks.length}</span></div>`;
        tasks.forEach(t => {
            html += renderTaskCard(t);
        });
        html += `</div>`;
    }

    if (todayData.suggested_time) {
        html += `<div style="text-align:center;color:#999;font-size:13px;margin-top:8px;">建议时长：${todayData.suggested_time}</div>`;
    }

    container.innerHTML = html;
}

function renderTaskCard(t) {
    const optional = t.priority === '选做';
    let html = `<div class="task-card ${t.done ? 'done' : ''} ${optional ? 'optional' : ''}">`;
    html += `<div class="task-checkbox ${t.done ? 'checked' : ''}" onclick="toggleTask('${t.id}')"></div>`;
    html += `<div class="task-desc">`;
    // 必做/选做标签
    if (optional) {
        html += `<span style="display:inline-block;background:#fff3e0;color:#e65100;font-size:11px;padding:1px 6px;border-radius:4px;margin-right:6px;">选做</span>`;
    } else {
        html += `<span style="display:inline-block;background:#e3f2fd;color:#1565c0;font-size:11px;padding:1px 6px;border-radius:4px;margin-right:6px;">必做</span>`;
    }
    html += `${t.desc}`;
    // 语音播报按钮
    html += ` <span onclick="speakText('${t.desc.replace(/'/g, "\\'")}')" style="cursor:pointer;font-size:14px;" title="朗读">🔊</span>`;

    // 单任务计时控件（开始/暂停/继续/停止，时间戳由后端结算）
    const baseSec = t.duration_seconds || 0;
    const sessSec = t.session_seconds || 0;
    const shownFmt = formatTaskDur(baseSec + sessSec);
    if (t.timing) {
        // 运行中：暂停 + 停止
        html += ` <span class="task-timer" data-tid="${t.id}" data-base="${baseSec + sessSec}" data-start="${Date.now()}" style="font-size:12px;color:#4b7791;cursor:pointer;">⏱ <span class="tt-val">${shownFmt}</span> `;
        html += `<span onclick="pauseTaskTimer('${t.id}')" style="margin:0 4px;">⏸暂停</span>`;
        html += `<span onclick="stopTaskTimer('${t.id}')">■停</span></span>`;
    } else if (t.paused) {
        // 暂停中：继续
        html += ` <span class="task-timer" style="font-size:12px;color:#f5a623;cursor:pointer;" onclick="startTaskTimer('${t.id}')">⏱ <span class="tt-val">${shownFmt}</span> ▶继续</span>`;
    } else if (!t.done) {
        html += ` <span class="task-timer" style="font-size:12px;color:#999;cursor:pointer;" onclick="startTaskTimer('${t.id}')">⏱ <span class="tt-val">${formatTaskDur(baseSec) || '00:00'}</span> ▶计时</span>`;
    } else if (baseSec > 0) {
        html += ` <span style="font-size:12px;color:#bbb;">⏱ ${shownFmt}</span>`;
    }

    // 附件（多文件明确计数 + 序号）
    if (t.attachments && t.attachments.length > 0) {
        const atts = t.attachments;
        const typeName = {image: '图', video: '视频', audio: '音频', pdf: '文件'};
        const cnt = {};
        atts.forEach(a => { if (a.type) cnt[a.type] = (cnt[a.type] || 0) + 1; });
        const summary = Object.entries(cnt).map(([k, v]) => `${typeName[k] || k}×${v}`).join('，');
        html += `<div class="attachments">`;
        html += `<div class="att-title">📎 附件 ${atts.length} 项<span class="att-summary">（${summary}）</span></div>`;
        html += `<div class="att-chips">`;
        atts.forEach((att, idx) => {
            const icons = {image: '🖼', video: '🎬', audio: '🎵', pdf: '📄'};
            const num = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩'][idx] || (idx + 1) + '.';
            if (att.filename) {
                html += `<span class="att-chip ${att.type}" onclick="showAttachment('${att.filename}', '${att.type}', ${att.id})">${num} ${icons[att.type] || '📎'} ${att.desc}</span>`;
            } else {
                html += `<span class="att-chip ${att.type}" style="opacity:0.5;">${num} ${icons[att.type] || '📎'} ${att.desc}（待上传）</span>`;
            }
        });
        html += `</div></div>`;
    }

    html += `</div></div>`;
    return html;
}

// ========== 单任务计时 ==========
function formatTaskDur(sec) {
    sec = Math.floor(sec || 0);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

async function startTaskTimer(taskId) {
    // 墙钟首次启动时弹注意事项（墙钟 auto start/resume 都算首次）
    await showFirstTimeWallNotice();
    const res = await fetch(`/api/task/${taskId}/timer/start`, {method:'POST'});
    const data = await res.json();
    if (data && data.success === false) { showToast(data.error || '操作失败'); return; }
    // 墙钟自动 start/resume 也触发注意事项（后端 wall_action 返回 auto_start/auto_resume）
    if (data.wall_action === 'auto_start') markWallStartedToday();
    await loadToday();
}

async function pauseTaskTimer(taskId) {
    await fetch(`/api/task/${taskId}/timer/pause`, {method:'POST'});
    await loadToday();
}

async function stopTaskTimer(taskId) {
    await fetch(`/api/task/${taskId}/timer/stop`, {method:'POST'});
    await loadToday();
}

// 计时中卡片实时跳动
setInterval(() => {
    document.querySelectorAll('.task-timer[data-start]').forEach(el => {
        const base = parseInt(el.dataset.base || 0, 10);
        const extra = Math.floor((Date.now() - parseInt(el.dataset.start,10)) / 1000);
        const val = el.querySelector('.tt-val');
        if (val) val.textContent = formatTaskDur(base + extra);
    });
    if (typeof renderFocusChart === 'function') renderFocusChart();
    // 习惯倒计时本地跳动 + 到点检测
    document.querySelectorAll('.habit-countdown[data-start]').forEach(el => {
        const target = parseInt(el.dataset.target, 10);
        const base = parseInt(el.dataset.base || '0', 10);
        if (parseInt(el.dataset.paused || '0', 10)) {
            el.textContent = formatHabitDur(target - base);
            return;
        }
        const start = new Date(el.dataset.start);
        const elapsed = base + Math.floor((Date.now() - start) / 1000);
        const rem = Math.max(0, target - elapsed);
        el.textContent = formatHabitDur(rem);
        if (rem <= 0) finishHabit(el.id.replace('countdown_', ''));
    });
}, 1000);

// 语音播报
function speakText(text) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        utter.lang = 'zh-CN';
        utter.rate = (todayData && typeof todayData.speech_rate === 'number') ? todayData.speech_rate : 0.9;
        window.speechSynthesis.speak(utter);
    }
}

// ========== 任务勾选 ==========
async function toggleTask(taskId) {
    playSound('tick');
    const res = await fetch(`/api/task/${taskId}/toggle`, {method: 'POST'});
    const data = await res.json();
    await loadToday();
    if (!data || !data.success) return;
    const doneTask = (todayData.tasks || []).find(t => String(t.id) === String(taskId));
    if (data.started_next) {
        const next = (todayData.tasks || []).find(t => String(t.id) === String(data.started_next));
        showToast(`✅ ${doneTask ? doneTask.desc : '任务'}完成 · 已开始「${next ? next.desc : '下一个任务'}」`);
    }
    if (data.celebration === 'all_done') {
        showCelebrate();
    } else if (data.celebration === 'required_done') {
        showRequiredDone(data.optional_remaining);
    }
}

// 完成庆祝弹窗（必做+选做全部完成）
function showCelebrate() {
    playSound('complete');
    const timer = todayData.timer;
    let elapsed = 0;
    if (timer.start_time) {
        const start = new Date(timer.start_time);
        const end = timer.pause_start ? new Date(timer.pause_start) : new Date();
        elapsed = Math.max(0, Math.floor((end - start) / 1000) - Math.floor(timer.total_paused || 0));
    }
    const tu = document.getElementById('timeUsed');
    if (tu) tu.textContent = '总用时 ' + formatTime(elapsed);
    const optDone = (todayData.tasks || []).filter(t => t.done && t.priority === '选做').length;
    const cp = document.getElementById('celebratePoints');
    if (cp) cp.textContent = 30 + optDone * 10;
    document.getElementById('celebrateModal').classList.add('show');
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        new Notification('🎉 太棒了！', {body: '今天的作业全部完成啦！'});
    }
}

function closeCelebrate() {
    document.getElementById('celebrateModal').classList.remove('show');
}

// 必做全完成但还有选做：弹窗询问继续还是结束
function showRequiredDone(optRemaining) {
    playSound('complete');
    const cnt = document.getElementById('optionalRemainCount');
    if (cnt) cnt.textContent = optRemaining;
    document.getElementById('requiredDoneModal').classList.add('show');
}
function closeRequiredDone() {
    document.getElementById('requiredDoneModal').classList.remove('show');
}
async function continueOptional() {
    closeRequiredDone();
    const next = (todayData.tasks || []).find(t => !t.done && t.priority === '选做');
    if (next) {
        await startTaskTimer(next.id);
    } else {
        await loadToday();
    }
}
async function finishToday() {
    closeRequiredDone();
    await fetch('/api/timer/suspend', {method: 'POST'});
    await loadToday();
    showToast('👍 今天的作业完成，休息一下吧！');
}

// 轻提示（自动消失，不打断操作）
function showToast(msg, dur = 2600) {
    const box = document.getElementById('toastBox');
    if (!box) return;
    const el = document.createElement('div');
    el.className = 'toast-item';
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => {
        el.classList.add('hide');
        setTimeout(() => el.remove(), 350);
    }, dur);
}

// ========== 习惯任务 ==========
let habitTimers = {}; // {habitId: {interval, remaining, paused}}

// 互斥：返回当前仍在计时的其他习惯 id（排除自身）
function activeHabitId(excludeId) {
    return Object.keys(habitTimers).find(k =>
        String(k) !== String(excludeId) && habitTimers[k] && habitTimers[k].remaining > 0);
}
function habitName(id) {
    const h = (todayData.habits || []).find(x => String(x.id) === String(id));
    return h ? h.name : '其他习惯';
}

// 按习惯名称关键词匹配图标
function habitIconFor(name) {
    const n = name || '';
    if (/读|书|课外|朗读|背诵/.test(n)) return '📖';
    if (/练字|书写|抄写|写字|描红/.test(n)) return '✍️';
    if (/口算|算术|计算|数学/.test(n)) return '🧮';
    if (/运动|跳绳|跑步|做操|锻炼|眼保/.test(n)) return '🏃';
    if (/坐姿|姿势|整理|书包|物品/.test(n)) return '🧹';
    if (/听|英语|跟读|听力/.test(n)) return '🎧';
    return '⭐';
}

function renderHabits() {
    const section = document.getElementById('habitSection');
    const list = document.getElementById('habitList');
    if (!todayData.habits || todayData.habits.length === 0) {
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';

    let html = '';
    todayData.habits.forEach(h => {
        const status = todayData.habits_status[h.id] || {};
        const habitIcon = habitIconFor(h.name);
        html += `<div class="habit-item">`;
        html += `<div class="habit-info">`;
        html += `<div><div class="habit-name">${habitIcon} ${h.name}</div><div class="habit-time">${h.minutes ? '每日' + h.minutes + '分钟' : '每日检查'}</div></div>`;
        html += `</div>`;
        if (status.done) {
            html += `<span style="color:#4caf50;font-size:14px;">✅ 已完成</span>`;
        } else if (h.minutes) {
            // 有倒计时的任务（后端落库）
            const target = h.minutes * 60;
            let elapsed = status.hb_elapsed || 0;
            if (status.hb_start && !status.hb_paused) {
                elapsed += Math.floor((Date.now() - new Date(status.hb_start)) / 1000);
            }
            const remaining = Math.max(0, target - elapsed);
            const running = status.hb_start && !status.hb_paused;
            const paused = !!status.hb_paused;
            const btnText = running ? '暂停' : (paused ? '继续' : '开始');
            const btnBg = running ? '#f5a623' : '#4b7791';
            html += `<button class="habit-btn" id="habitBtn_${h.id}" onclick="toggleHabitTimer('${h.id}', ${h.minutes})" style="background:${btnBg};color:white;border:none;padding:8px 16px;border-radius:16px;cursor:pointer;font-size:13px;">${btnText}</button>`;
            html += `<span class="habit-countdown" id="countdown_${h.id}"
                data-target="${target}" data-base="${status.hb_elapsed||0}"
                data-start="${status.hb_start||''}" data-paused="${paused?1:0}"
                style="font-size:18px;font-weight:700;color:#4b7791;font-variant-numeric:tabular-nums;${(running||paused)?'':'display:none;'}">${formatHabitDur(remaining)}</span>`;
            html += `<button onclick="manualCompleteHabit('${h.id}')" title="提前完成" style="background:#f0f0f0;color:#666;border:none;padding:8px 16px;border-radius:16px;cursor:pointer;font-size:13px;margin-left:6px;">完成打勾</button>`;
        } else {
            // 无倒计时的检查项
            html += `<button onclick="toggleHabit('${h.id}')" style="background:#f0f0f0;color:#666;border:none;padding:8px 16px;border-radius:16px;cursor:pointer;font-size:13px;">完成打勾</button>`;
        }
        html += `</div>`;
    });
    list.innerHTML = html;
}

// 习惯倒计时：后端落库，前端只负责本地跳动与到点检测
async function toggleHabitTimer(habitId, minutes) {
    const status = (todayData.habits_status || {})[habitId] || {};
    const running = status.hb_start && !status.hb_paused;
    // running → pause；未开始/已暂停 → start（恢复保留已走秒）
    const action = running ? 'pause' : 'start';
    const res = await fetch(`/api/habit/${habitId}/timer/${action}`, {method:'POST'});
    const data = await res.json();
    if (data && data.success === false) { showToast(data.error || '操作失败'); return; }
    await loadToday();
}

function formatHabitDur(sec) {
    sec = Math.max(0, Math.floor(sec));
    const m = Math.floor(sec / 60), s = sec % 60;
    return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

// 到点自动完成（带防重复标记）
async function finishHabit(habitId) {
    if (habitTimers[habitId] === 'done') return;
    habitTimers[habitId] = 'done';
    await fetch(`/api/habit/${habitId}/toggle`, {method:'POST'});
    await loadToday();
    const name = todayData.habits.find(h => String(h.id) === String(habitId))?.name || '任务';
    showToast(`🎉 ${name}完成 · +5 积分`);
}

async function toggleHabit(habitId) {
    delete habitTimers[habitId];
    await fetch(`/api/habit/${habitId}/toggle`, {method: 'POST'});
    await loadToday();
}

// 手动完成有倒计时的习惯任务（提前做完了）
async function manualCompleteHabit(habitId) {
    const name = todayData.habits.find(h => String(h.id) === String(habitId))?.name || '任务';
    if (!confirm(`确定提前完成"${name}"吗？`)) return;
    // 先把前端计时标记完成，防止到点重复触发
    habitTimers[habitId] = 'done';
    delete habitTimers[habitId];
    await fetch(`/api/habit/${habitId}/toggle`, {method: 'POST'});
    await loadToday();
    showToast(`🎉 ${name}完成 · +5 积分`);
}

// ========== 今日积分 ==========
// ========== 当天时间分配（专注条形） ==========
const SUBJECT_COLORS = {'语文':'#4b7791','数学':'#f5a623','英语':'#7e57c2'};
function subjectColor(s){ return SUBJECT_COLORS[s] || '#8aa0b8'; }
function renderFocusChart() {
    const card = document.getElementById('focusChartCard');
    if (!card || !todayData || !todayData.tasks) return;
    let focus = 0;
    const rows = [];
    todayData.tasks.forEach(t => {
        const el = document.querySelector(`.task-timer[data-tid="${t.id}"]`);
        let sec = (t.duration_seconds || 0) + (t.session_seconds || 0);
        const live = el && el.dataset.start;
        if (live) {
            sec = parseInt(el.dataset.base || 0, 10) + Math.floor((Date.now() - parseInt(el.dataset.start,10))/1000);
        }
        focus += sec;
        if (sec > 0) rows.push({desc: t.desc || t.subject, subject: t.subject, sec, live});
    });
    // 简化口径：墙钟=净运行（实际在写的时间）；暂停=在场总−墙钟（没在写的全归暂停）
    const focusEl = document.getElementById('focusSummary');
    if (focusEl) {
        const wall = todayData.timer.elapsed_seconds || 0;      // 墙钟：净运行时间
        const present = todayData.timer.present_seconds || 0;   // 在场总时长
        const paused = Math.max(0, present - wall);             // 暂停累计（没在写的时间）
        const pauseCnt = todayData.timer.pause_count || 0;      // 暂停次数
        let html = `📊 在场总 <strong>${formatTime(present)}</strong>`;
        if (present > 0 || wall > 0) {
            html += ` ＝ ✍️ 墙钟 <strong>${formatTime(wall)}</strong>`;
            if (paused > 0) html += ` ＋ ⏸ 暂停 <strong>${formatTime(paused)}</strong>${pauseCnt>0?`（${pauseCnt}次）`:''}`;
        }
        focusEl.innerHTML = html;
    }
    if (rows.length === 0) { card.style.display = 'none'; return; }
    card.style.display = 'block';
    const max = Math.max(...rows.map(r => r.sec), 1);
    rows.sort((a,b)=>b.sec-a.sec);
    document.getElementById('focusChart').innerHTML = rows.map(r => {
        const pct = Math.round(r.sec/max*100);
        const label = r.desc.length > 14 ? r.desc.slice(0,14)+'…' : r.desc;
        return `<div style="margin:8px 0;">
            <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px;">
                <span>${r.subject} · ${label}${r.live?' <span style="color:#4b7791;">●</span>':''}</span>
                <span style="font-variant-numeric:tabular-nums;color:#555;">${formatTime(r.sec)}</span>
            </div>
            <div style="background:#f0f2f5;border-radius:6px;height:10px;overflow:hidden;">
                <div style="height:100%;width:${pct}%;background:${subjectColor(r.subject)};border-radius:6px;"></div>
            </div>
        </div>`;
    }).join('');
}

function renderPoints() {
    const card = document.getElementById('pointsCard');
    if (!card) return;
    const earned = todayData.points_earned || 0;
    if (earned > 0) {
        card.style.display = 'block';
        document.getElementById('todayPoints').textContent = earned;
    } else {
        card.style.display = 'none';
    }
}

// ========== 计时器 ==========
function renderTimer() {
    const timer = todayData.timer;
    const btn = document.getElementById('timerBtn');
    const display = document.getElementById('timerDisplay');
    const status = document.getElementById('timerStatus');
    const pauseEl = document.getElementById('pauseCount');

    // 暂停次数：统一口径 = 墙钟的 pause_count（墙钟 running→paused 次数，包含手动暂停 + 最后一个任务被 pause/stop 自动触发）
    const totalPause = (timer.pause_count || 0);
    if (totalPause > 0) {
        pauseEl.textContent = `⏸ 今日暂停 ${totalPause} 次`;
    } else {
        pauseEl.textContent = '';
    }

    if (timer.status === 'idle') {
        btn.textContent = '开始写作业';
        btn.className = 'timer-btn';
        display.textContent = '00:00';
        status.textContent = '';
    } else if (timer.status === 'running') {
        btn.textContent = '暂停';
        btn.className = 'timer-btn pause';
        status.textContent = '正在写作业中...';
        startTimerDisplay();
    } else if (timer.status === 'paused') {
        btn.textContent = '继续';
        btn.className = 'timer-btn';
        display.textContent = formatTime(timer.elapsed_seconds);
        status.textContent = '已暂停';
        startTimerDisplay();
    } else if (timer.status === 'done') {
        btn.textContent = '重新开始';
        btn.className = 'timer-btn stop';
        display.textContent = formatTime(timer.elapsed_seconds);
        status.textContent = '今天的作业已完成！';
    }

    // 常驻悬浮计时条：仅在 进行中/暂停 时显示
    const sc = document.getElementById('stickyClock');
    const scBtn = document.getElementById('stickyClockBtn');
    const mainContent = document.querySelector('.main-content');
    if (sc) {
        if (timer.status === 'running' || timer.status === 'paused') {
            sc.style.display = 'flex';
            scBtn.textContent = timer.status === 'running' ? '暂停' : '继续';
            const scTime = document.getElementById('stickyClockTime');
            if (scTime && timer.status === 'paused') scTime.textContent = formatTime(timer.elapsed_seconds);
            // 动态避让：量 top-bar 实际高度，sticky-clock 紧跟其下，main-content 给两者让路
            const topBar = document.querySelector('.top-bar');
            const barH = topBar ? topBar.offsetHeight : 56;
            sc.style.top = barH + 'px';
            // 下一帧取准确高度（刚显示时可能还没 layout）
            requestAnimationFrame(() => {
                const scH = sc.offsetHeight;
                sc.style.top = barH + 'px';
                if (mainContent) mainContent.style.paddingTop = (barH + scH + 8) + 'px';
            });
        } else {
            sc.style.display = 'none';
            if (mainContent) mainContent.style.paddingTop = '';
        }
    }
}

function handleTimer() {
    const status = todayData.timer.status;
    if (status === 'idle') {
        // 显示护眼小贴士
        document.getElementById('eyeCareModal').classList.add('show');
        modalTimerStartPending = true;
    } else if (status === 'running') {
        timerAction('pause');
    } else if (status === 'paused') {
        timerAction('pause'); // 继续
    } else if (status === 'done') {
        timerAction('reset');
    }
}

function startTimerFromModal() {
    document.getElementById('eyeCareModal').classList.remove('show');
    if (modalTimerStartPending) {
        modalTimerStartPending = false;
        timerAction('start');
    }
}

async function timerAction(action) {
    if (action === 'start') {
        // 墙钟和习惯的互斥在后端 api_timer_start 做了
        await showFirstTimeWallNotice();
        markWallStartedToday();
    }
    const res = await fetch(`/api/timer/${action}`, {method: 'POST'});
    const data = await res.json();
    if (data && data.success === false) { showToast(data.error || '操作失败'); return; }
    await loadToday();
    if (action === 'start') {
        startBreakCheck();
    }
}

// ============ 墙钟首次启动注意事项 ============
// 一天只弹一次：不管是手动点墙钟 start 还是点任务 ▶ 触发 wall auto start
function markWallStartedToday() {
    try { localStorage.setItem('wallStarted', new Date().toISOString().slice(0,10)); } catch {}
}
async function showFirstTimeWallNotice() {
    let last = '';
    try { last = localStorage.getItem('wallStarted') || ''; } catch {}
    const today = new Date().toISOString().slice(0,10);
    if (last === today) return;  // 今天已经弹过
    document.getElementById('wallNoticeModal')?.classList.add('show');
}

function closeWallNotice() {
    document.getElementById('wallNoticeModal')?.classList.remove('show');
    markWallStartedToday();
}

function startTimerDisplay() {
    if (timerInterval) clearInterval(timerInterval);
    timerInterval = setInterval(() => {
        const timer = todayData.timer;
        if (timer.status !== 'running' && timer.status !== 'paused') {
            clearInterval(timerInterval);
            return;
        }
        const start = new Date(timer.start_time);
        const now = new Date();
        let elapsed = Math.floor((now - start) / 1000);
        elapsed -= Math.floor(timer.total_paused || 0);
        if (timer.status === 'paused' && timer.pause_start) {
            const pauseStart = new Date(timer.pause_start);
            elapsed -= Math.floor((now - pauseStart) / 1000);
        }
        document.getElementById('timerDisplay').textContent = formatTime(elapsed);
        const scTime = document.getElementById('stickyClockTime');
        if (scTime) scTime.textContent = formatTime(elapsed);
    }, 1000);
}

function formatTime(seconds) {
    seconds = Math.floor(seconds);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ========== 休息提醒 ==========
function startBreakCheck() {
    if (breakCheckInterval) clearInterval(breakCheckInterval);
    let lastBreak20 = 0;   // 上次 20 分钟远眺提醒的基准（循环提醒）
    let break45Shown = false;
    let break60Shown = false;

    breakCheckInterval = setInterval(() => {
        const timer = todayData.timer;
        if (timer.status !== 'running') return;

        const start = new Date(timer.start_time);
        const now = new Date();
        let elapsed = Math.floor((now - start) / 1000) - Math.floor(timer.total_paused || 0);

        // 每满 20 分钟连续作业提醒远眺（每 20 分钟循环一次）
        if (elapsed - lastBreak20 >= 1200) {
            lastBreak20 = Math.floor(elapsed / 1200) * 1200;
            showBreakModal('☕ 休息一下', `已经连续写了 ${Math.floor(elapsed / 60)} 分钟啦，抬头看看远处 20 秒，让眼睛休息一下！`);
        }
        // 45分钟提醒活动身体
        if (!break45Shown && elapsed >= 2700) {
            break45Shown = true;
            showBreakModal('🤸 站起来活动一下', '写作业已经45分钟了，站起来伸伸腰、走动走动，喝口水！');
        }
        // 60分钟强制休息
        if (!break60Shown && elapsed >= 3600) {
            break60Shown = true;
            showBreakModal('😴 该休息啦', '连续写作业1小时了！休息10分钟再继续吧，眼睛和身体都需要放松。');
        }
    }, 5000);
}

function showBreakModal(title, text) {
    playSound('remind');
    document.querySelector('#breakModal h2').textContent = title;
    document.querySelector('#breakModal p').textContent = text;
    document.getElementById('breakModal').classList.add('show');
}

function closeBreakModal() {
    document.getElementById('breakModal').classList.remove('show');
}

// ========== 附件预览 ==========
function closeAttModal() {
    document.getElementById('attModal').classList.remove('show');
    // 不清除pageDrawings，下次打开同一个PDF时恢复笔迹
    currentStroke = null;
    drawing = false;
}

let currentPdfUrl = null; // 记录当前打开的PDF

let currentPdfAttachmentId = null;

function showAttachment(filename, type, attachmentId) {
    const modal = document.getElementById('attModal');
    const content = document.getElementById('attModalContent');
    const url = `/attachments/${filename}`;
    currentPdfAttachmentId = attachmentId || null;

    if (type === 'image') {
        content.innerHTML = `<img src="${url}" alt="附件">`;
    } else if (type === 'video') {
        content.innerHTML = `<video src="${url}" controls autoplay style="max-width:100%;"></video>`;
    } else if (type === 'audio') {
        content.innerHTML = `<audio src="${url}" controls autoplay></audio>`;
    } else if (type === 'pdf') {
        content.innerHTML = `
            <div style="margin-bottom:10px;display:flex;gap:6px;justify-content:center;flex-wrap:wrap;align-items:center;">
                <button onclick="prevPage()" class="pdf-nav-btn">◀ 上一页</button>
                <span id="pageInfo" style="font-size:14px;color:#666;min-width:60px;text-align:center;">1 / 1</span>
                <button onclick="nextPage()" class="pdf-nav-btn">下一页 ▶</button>
                <span style="width:1px;height:20px;background:#ddd;margin:0 4px;"></span>
                <button onclick="zoomOut()" class="pdf-nav-btn" style="font-size:16px;">−</button>
                <span id="zoomInfo" style="font-size:13px;color:#666;min-width:50px;text-align:center;">100%</span>
                <button onclick="zoomIn()" class="pdf-nav-btn" style="font-size:16px;">+</button>
                <span style="width:1px;height:20px;background:#ddd;margin:0 4px;"></span>
                <button id="toolPen" onclick="setTool('pen')" class="pdf-tool-btn active">✏️ 笔记</button>
                <button id="toolPan" onclick="setTool('pan')" class="pdf-tool-btn">🖐 平移</button>
                <button id="toolEraser" onclick="setTool('eraser')" class="pdf-tool-btn">🧹 橡皮</button>
                <span style="width:1px;height:20px;background:#ddd;margin:0 4px;"></span>
                <div id="penOptions" style="display:flex;gap:6px;align-items:center;">
                    <input type="color" id="penColor" value="#e74c3c" onchange="penColor=this.value" style="width:30px;height:30px;border:none;cursor:pointer;">
                    <label style="font-size:12px;color:#666;">笔粗</label>
                    <input type="range" id="penSizeRange" min="1" max="20" value="4" onchange="penSize=parseInt(this.value);document.getElementById('penSizeVal').textContent=this.value+'px'">
                    <span id="penSizeVal" style="font-size:12px;color:#666;min-width:32px;">4px</span>
                </div>
                <div id="eraserOptions" style="display:none;gap:6px;align-items:center;">
                    <label style="font-size:12px;color:#666;">橡皮粗</label>
                    <input type="range" id="eraserSizeRange" min="5" max="50" value="20" onchange="eraserSize=parseInt(this.value);document.getElementById('eraserSizeVal').textContent=this.value+'px'">
                    <span id="eraserSizeVal" style="font-size:12px;color:#666;min-width:36px;">20px</span>
                </div>
                <span style="width:1px;height:20px;background:#ddd;margin:0 4px;"></span>
                <button onclick="clearCanvas()" style="background:#ffebee;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;color:#c62828;">清空</button>
                <button onclick="exportPDF()" style="background:#4b7791;color:white;border:none;padding:6px 12px;border-radius:6px;cursor:pointer;">导出</button>
            </div>
            <div style="width:100%;overflow:auto;max-height:80vh;border:1px solid #eee;border-radius:8px;" id="pdfContainer">
                <div style="position:relative;width:max-content;margin:0 auto;">
                    <canvas id="pdfCanvas" style="border:1px solid #ccc;background:white;display:block;"></canvas>
                    <canvas id="drawCanvas" style="position:absolute;top:0;left:0;display:block;"></canvas>
                </div>
            </div>
            <div style="font-size:12px;color:#999;margin-top:4px;">💡 选择工具后操作：✏️笔记书写 / 🖐拖拽平移 / 🧹擦除 | Ctrl+滚轮缩放</div>
        `;
        loadPDF(url);
    }
    modal.classList.add('show');
}

let pdfPage = null;
let drawCtx = null;
let drawing = false;
let lastX = 0, lastY = 0;


// ============ PDF编辑器（WPS风格） ============
let pdfDoc = null;
let currentPage = 1;
let penColor = '#e74c3c';
let penSize = 4;
let eraserMode = false;
let eraserSize = 20;
let toolMode = 'pen'; // pen | pan | eraser
let pdfZoom = 1;
let pageDrawings = {};
let currentStroke = null;
let isPanning = false;
let panStartX = 0, panStartY = 0;
let containerScrollLeft = 0, containerScrollTop = 0;

// 切换工具
function setTool(mode) {
    toolMode = mode;
    eraserMode = (mode === 'eraser');
    // 更新按钮选中状态
    ['pen', 'pan', 'eraser'].forEach(m => {
        const btn = document.getElementById('tool' + m.charAt(0).toUpperCase() + m.slice(1));
        if (btn) btn.classList.toggle('active', m === mode);
    });
    // 显示对应参数
    const penOpt = document.getElementById('penOptions');
    const eraOpt = document.getElementById('eraserOptions');
    if (penOpt) penOpt.style.display = (mode === 'pen') ? 'flex' : 'none';
    if (eraOpt) eraOpt.style.display = (mode === 'eraser') ? 'flex' : 'none';
    // 光标
    const canvas = document.getElementById('drawCanvas');
    if (canvas) {
        canvas.style.cursor = mode === 'pan' ? 'grab' : (mode === 'eraser' ? 'cell' : 'crosshair');
    }
}

function zoomIn() {
    pdfZoom = Math.min(pdfZoom + 0.25, 4);
    document.getElementById('zoomInfo').textContent = Math.round(pdfZoom * 100) + '%';
    renderCurrentPage();
}

function zoomOut() {
    pdfZoom = Math.max(pdfZoom - 0.25, 0.5);
    document.getElementById('zoomInfo').textContent = Math.round(pdfZoom * 100) + '%';
    renderCurrentPage();
}

async function loadPDF(url) {
    try {
        setTool('pen'); // 每次打开默认笔记工具
        if (currentPdfUrl !== url) {
            pageDrawings = {};
            currentPdfUrl = url;
        }
        const loadingTask = pdfjsLib.getDocument(url);
        pdfDoc = await loadingTask.promise;
        currentPage = 1;
        // 从数据库加载批注
        if (currentPdfAttachmentId) {
            const res = await fetch(`/api/pdf/annotations/${currentPdfAttachmentId}`);
            const data = await res.json();
            if (data.annotations) {
                Object.keys(data.annotations).forEach(pageNum => {
                    pageDrawings[pageNum] = data.annotations[pageNum];
                });
            }
        }
        await renderCurrentPage();
    } catch (e) {
        console.error('PDF加载失败:', e);
        showToast('PDF加载失败: ' + e.message);
    }
}

async function renderCurrentPage() {
    if (!pdfDoc) return;
    const page = await pdfDoc.getPage(currentPage);
    const viewport = page.getViewport({scale: 1.5 * pdfZoom});

    const pdfCanvas = document.getElementById('pdfCanvas');
    const drawCanvas = document.getElementById('drawCanvas');
    pdfCanvas.width = viewport.width;
    pdfCanvas.height = viewport.height;
    drawCanvas.width = viewport.width;
    drawCanvas.height = viewport.height;

    const ctx = pdfCanvas.getContext('2d');
    await page.render({canvasContext: ctx, viewport: viewport}).promise;

    drawCtx = drawCanvas.getContext('2d');
    drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    renderStrokes(drawCtx);

    document.getElementById('pageInfo').textContent = currentPage + ' / ' + pdfDoc.numPages;

    drawCanvas.oncontextmenu = function(e) { e.preventDefault(); };
    drawCanvas.style.touchAction = 'none';

    // 核心：按下（鼠标/触控笔/单指共用）
    const handleDown = (e, isMouse) => {
        e.preventDefault();
        const rect = e.target.getBoundingClientRect();
        const scale = e.target.width / rect.width;
        const button = e.button;
        if (toolMode === 'pan' || button === 1 || button === 2) {
            // 平移模式 / 右键中键拖拽
            isPanning = true;
            panStartX = e.clientX;
            panStartY = e.clientY;
            const container = document.getElementById('pdfContainer');
            containerScrollLeft = container.scrollLeft;
            containerScrollTop = container.scrollTop;
            if (button === 0) drawCanvas.style.cursor = 'grabbing';
            return;
        }
        // 书写（pen 或 eraser）
        drawing = true;
        const x = (e.clientX - rect.left) * scale / (1.5 * pdfZoom);
        const y = (e.clientY - rect.top) * scale / (1.5 * pdfZoom);
        currentStroke = {color: penColor, size: penSize, eraser: eraserMode, points: [{x, y}]};
    };
    const handleMove = (e) => {
        if (isPanning) {
            e.preventDefault();
            const container = document.getElementById('pdfContainer');
            // 自然拖拽：抓住内容，拖哪跟哪（与滚动条方向相反）
            container.scrollLeft = containerScrollLeft + (panStartX - e.clientX);
            container.scrollTop = containerScrollTop + (panStartY - e.clientY);
            return;
        }
        if (!drawing || !currentStroke) return;
        e.preventDefault();
        const rect = e.target.getBoundingClientRect();
        const scale = e.target.width / rect.width;
        const x = (e.clientX - rect.left) * scale / (1.5 * pdfZoom);
        const y = (e.clientY - rect.top) * scale / (1.5 * pdfZoom);
        currentStroke.points.push({x, y});
        drawCtx.strokeStyle = eraserMode ? '#000' : penColor;
        drawCtx.lineWidth = (eraserMode ? eraserSize : penSize) * 1.5 * pdfZoom;
        drawCtx.lineCap = 'round';
        drawCtx.globalCompositeOperation = eraserMode ? 'destination-out' : 'source-over';
        drawCtx.beginPath();
        const pts = currentStroke.points;
        const px = pts[pts.length-2].x * 1.5 * pdfZoom;
        const py = pts[pts.length-2].y * 1.5 * pdfZoom;
        drawCtx.moveTo(px, py);
        drawCtx.lineTo(x * 1.5 * pdfZoom, y * 1.5 * pdfZoom);
        drawCtx.stroke();
    };
    const handleUp = () => {
        if (isPanning) {
            isPanning = false;
            drawCanvas.style.cursor = toolMode === 'pan' ? 'grab' : 'crosshair';
        }
        endDraw();
    };

    // Pointer Events：只处理触控笔/触摸（鼠标交给mouse事件，避免双触发）
    drawCanvas.onpointerdown = function(e) {
        if (e.pointerType === 'mouse') return;
        if (e.pointerType === 'touch' && e.isPrimary === false) return;
        try { drawCanvas.setPointerCapture(e.pointerId); } catch(err) {}
        handleDown(e, false);
    };
    drawCanvas.onpointermove = function(e) {
        if (e.pointerType === 'mouse') return;
        handleMove(e);
    };
    drawCanvas.onpointerup = handleUp;
    drawCanvas.onpointercancel = handleUp;

    // 鼠标事件（桌面鼠标兜底）
    drawCanvas.onmousedown = function(e) { handleDown(e, true); };
    drawCanvas.onmousemove = function(e) { handleMove(e); };
    drawCanvas.onmouseup = handleUp;
    drawCanvas.onmouseleave = handleUp;

    // 双指缩放 + 平移（touch事件）
    drawCanvas.ontouchstart = handleTouchStart;
    drawCanvas.ontouchmove = handleTouchMove;
    drawCanvas.ontouchend = endDraw;
    drawCanvas.onwheel = handleWheel;
    drawCanvas.oncontextmenu = function(e) { e.preventDefault(); };
}

function renderStrokes(ctx) {
    const strokes = pageDrawings[currentPage] || [];
    const scale = 1.5 * pdfZoom;
    strokes.forEach(stroke => {
        ctx.strokeStyle = stroke.eraser ? '#000' : stroke.color;
        ctx.lineWidth = stroke.size * scale;
        ctx.lineCap = 'round';
        ctx.globalCompositeOperation = stroke.eraser ? 'destination-out' : 'source-over';
        ctx.beginPath();
        stroke.points.forEach((p, i) => {
            const x = p.x * scale;
            const y = p.y * scale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
    });
    ctx.globalCompositeOperation = 'source-over';
}

function endDraw() {
    if (currentStroke && currentStroke.points.length > 0) {
        if (!pageDrawings[currentPage]) pageDrawings[currentPage] = [];
        pageDrawings[currentPage].push(currentStroke);
        // 自动保存到数据库
        saveAnnotationsToDb();
    }
    currentStroke = null;
    drawing = false;
    isPanning = false;
}

// 保存批注到数据库
async function saveAnnotationsToDb() {
    if (!currentPdfAttachmentId) return;
    try {
        await fetch(`/api/pdf/annotations/${currentPdfAttachmentId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                page_num: currentPage,
                strokes: pageDrawings[currentPage] || []
            })
        });
    } catch (e) {
        console.error('保存批注失败:', e);
    }
}

function handleWheel(e) {
    if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        if (e.deltaY < 0) zoomIn();
        else zoomOut();
    }
}

let lastTouchDist = 0;
let lastTouchMidX = 0;
let lastTouchMidY = 0;

function handleTouchStart(e) {
    e.preventDefault();
    if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        lastTouchDist = Math.sqrt(dx*dx + dy*dy);
        lastTouchMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        lastTouchMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
    } else if (e.touches.length === 1) {
        const t = e.touches[0];
        if (toolMode === 'pan') {
            // 平移模式：单指拖动
            isPanning = true;
            panStartX = t.clientX;
            panStartY = t.clientY;
            const container = document.getElementById('pdfContainer');
            containerScrollLeft = container.scrollLeft;
            containerScrollTop = container.scrollTop;
            return;
        }
        // 书写模式
        drawing = true;
        const rect = e.target.getBoundingClientRect();
        const scale = e.target.width / rect.width;
        const x = (t.clientX - rect.left) * scale / (1.5 * pdfZoom);
        const y = (t.clientY - rect.top) * scale / (1.5 * pdfZoom);
        currentStroke = {color: penColor, size: penSize, eraser: eraserMode, points: [{x, y}]};
    }
}

function handleTouchMove(e) {
    e.preventDefault();
    if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.sqrt(dx*dx + dy*dy);
        // 中点位置
        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;

        // 缩放
        if (lastTouchDist > 0 && Math.abs(dist - lastTouchDist) > 5) {
            pdfZoom = Math.max(0.5, Math.min(4, pdfZoom * dist / lastTouchDist));
            document.getElementById('zoomInfo').textContent = Math.round(pdfZoom * 100) + '%';
            renderCurrentPage();
        }
        // 平移
        if (lastTouchMidX > 0) {
            const container = document.getElementById('pdfContainer');
            container.scrollLeft -= (midX - lastTouchMidX);
            container.scrollTop -= (midY - lastTouchMidY);
        }
        lastTouchDist = dist;
        lastTouchMidX = midX;
        lastTouchMidY = midY;
    } else if (e.touches.length === 1 && isPanning) {
        // 平移模式单指拖动
        const container = document.getElementById('pdfContainer');
        const t = e.touches[0];
        // 自然拖拽：抓住内容拖，拖哪跟哪
        container.scrollLeft = containerScrollLeft + (panStartX - t.clientX);
        container.scrollTop = containerScrollTop + (panStartY - t.clientY);
    } else if (e.touches.length === 1 && drawing && currentStroke) {
        const rect = e.target.getBoundingClientRect();
        const t = e.touches[0];
        const scale = e.target.width / rect.width;
        const x = (t.clientX - rect.left) * scale / (1.5 * pdfZoom);
        const y = (t.clientY - rect.top) * scale / (1.5 * pdfZoom);
        currentStroke.points.push({x, y});
        drawCtx.strokeStyle = eraserMode ? '#000' : penColor;
        drawCtx.lineWidth = (eraserMode ? eraserSize : penSize) * 1.5 * pdfZoom;
        drawCtx.lineCap = 'round';
        drawCtx.globalCompositeOperation = eraserMode ? 'destination-out' : 'source-over';
        drawCtx.beginPath();
        const pts = currentStroke.points;
        const px = pts[pts.length-2].x * 1.5 * pdfZoom;
        const py = pts[pts.length-2].y * 1.5 * pdfZoom;
        drawCtx.moveTo(px, py);
        drawCtx.lineTo(x * 1.5 * pdfZoom, y * 1.5 * pdfZoom);
        drawCtx.stroke();
    }
}

async function prevPage() {
    if (currentPage > 1) { currentPage--; await renderCurrentPage(); }
}

async function nextPage() {
    if (pdfDoc && currentPage < pdfDoc.numPages) { currentPage++; await renderCurrentPage(); }
}

function clearCanvas() {
    pageDrawings[currentPage] = [];
    renderCurrentPage();
}

async function exportPDF() {
    if (!pdfDoc) return;
    const newPdf = await PDFLib.PDFDocument.create();
    for (let i = 1; i <= pdfDoc.numPages; i++) {
        const page = await pdfDoc.getPage(i);
        const viewport = page.getViewport({scale: 1.5});
        const tmpCanvas = document.createElement('canvas');
        tmpCanvas.width = viewport.width;
        tmpCanvas.height = viewport.height;
        const tmpCtx = tmpCanvas.getContext('2d');
        await page.render({canvasContext: tmpCtx, viewport: viewport}).promise;
        const strokes = pageDrawings[i] || [];
        strokes.forEach(stroke => {
            tmpCtx.strokeStyle = stroke.eraser ? '#000' : stroke.color;
            tmpCtx.lineWidth = stroke.size * 1.5;
            tmpCtx.lineCap = 'round';
            tmpCtx.globalCompositeOperation = stroke.eraser ? 'destination-out' : 'source-over';
            tmpCtx.beginPath();
            stroke.points.forEach((p, j) => {
                const x = p.x * 1.5;
                const y = p.y * 1.5;
                if (j === 0) tmpCtx.moveTo(x, y);
                else tmpCtx.lineTo(x, y);
            });
            tmpCtx.stroke();
        });
        const imgData = tmpCanvas.toDataURL('image/png');
        const pngBytes = dataURLtoBytes(imgData);
        const pngImage = await newPdf.embedPng(pngBytes);
        const newPage = newPdf.addPage([viewport.width, viewport.height]);
        newPage.drawImage(pngImage, {x: 0, y: 0, width: viewport.width, height: viewport.height});
    }
    const bytes = await newPdf.save();
    const blob = new Blob([bytes], {type: 'application/pdf'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '作业批注_' + new Date().toISOString().slice(0,10) + '.pdf';
    a.click();
    URL.revokeObjectURL(url);
}

function dataURLtoBytes(dataURL) {
    const base64 = dataURL.split(',')[1];
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
}
