// ============ 随手记 · 前端 ============
// child_id 从 session 取，切换孩子时走 /api/login 刷新 session
let notesChildId = 1;
let notesTypes = [];
let currentNotes = [];
let notesPage = 1;
let notesTotal = 0;
let selectedType = '';        // '' 表示全部
let notesSearchQuery = '';
let notesDateFilter = '';     // 空 / 'today' / '7' / '30' / 'pinned' / 'due'

// 新建记录中暂存的附件（上传后再提交）
let newNoteAttachments = [];  // [{file, type, tempUrl}]
let newNotePinned = false;
let editingNoteId = null;
let editAttachmentsPendingRemove = [];  // 编辑时要删掉的附件 id

// ============ 初始化 ============
(async function init() {
    // 先从 session 读当前孩子（common.js 也会在 DOMContentLoaded 后渲染顶部按钮组）
    try {
        const u = await fetch('/api/current-user').then(r => r.json());
        if (u && u.child_id) notesChildId = u.child_id;
    } catch (e) {}
    await reloadAll();
    // URL 参数同步：child.html 跳转过来时会带 ?filter=due
    syncFromUrl();
    // 浏览器通知权限申请（首次）
    tryBrowserNotify();
})();

function syncFromUrl() {
    const params = new URLSearchParams(location.search);
    if (params.get('filter')) {
        notesDateFilter = params.get('filter');
        const sel = document.getElementById('notesDateFilter');
        if (sel) sel.value = notesDateFilter;
    }
    if (params.get('type')) {
        selectedType = params.get('type');
    }
    if (params.get('filter') || params.get('type')) {
        renderTypeBar();
        loadNotes();
    }
}

function tryBrowserNotify() {
    if ('Notification' in window && Notification.permission === 'default') {
        // 不强制申请，等用户交互后再问
    }
}
// loadNotesChildren / switchNotesChild 已由 common.js 的 topBarActions + switchGlobalChild 替代

async function reloadAll() {
    document.getElementById('notesLoadMore').style.display = 'none';
    notesPage = 1;
    await loadTypes();            // 先拿数据并赋值 notesTypes
    loadNewNoteTypes();          // 再填充下拉框（用已有的 notesTypes）
    await Promise.all([loadNotes(), loadDueBanner()]);
}

// ============ 类型 ============
async function loadTypes() {
    const res = await fetch(`/api/notes/types`);
    const data = await res.json();
    notesTypes = data.types;
    renderTypeBar();
    const editSel = document.getElementById('editNoteType');
    if (editSel) {
        editSel.innerHTML = notesTypes.map(t =>
            `<option value="${t.id}">${t.icon} ${t.name}</option>`
        ).join('');
    }
}

function loadNewNoteTypes() {
    const sel = document.getElementById('newNoteType');
    if (!sel) return;
    sel.innerHTML = notesTypes.map(t =>
        `<option value="${t.id}" style="color:${t.color};">${t.icon} ${t.name}</option>`
    ).join('');
    previewNewNoteColor();
}

function renderTypeBar() {
    const bar = document.getElementById('noteTypeBar');
    let html = `<button class="note-type-chip ${!selectedType ? 'active' : ''}"
                   onclick="selectNoteType('')" style="border-color:#ccc;">全部</button>`;
    notesTypes.forEach(t => {
        html += `<button class="note-type-chip ${selectedType === t.id ? 'active' : ''}"
                   onclick="selectNoteType('${t.id}')"
                   style="border-color:${t.color};${selectedType === t.id ? 'background:' + t.color + ';color:white;' : ''}">
                   ${t.icon} ${t.name} <span class="count">${t.count || 0}</span>
                </button>`;
    });
    html += `<button class="note-type-chip manage" onclick="openTypeManager()" title="管理类型">⚙️</button>`;
    bar.innerHTML = html;
}

function selectNoteType(tid) {
    selectedType = tid;
    notesPage = 1;
    renderTypeBar();
    loadNotes();
}

function openTypeManager() {
    const box = document.getElementById('typeManagerList');
    box.innerHTML = notesTypes.map(t =>
        `<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;padding:8px;border:1px solid #eee;border-radius:6px;">
            <span style="width:12px;height:12px;border-radius:3px;background:${t.color};display:inline-block;"></span>
            <input type="text" value="${t.icon}" maxlength="4" placeholder="emoji" style="width:48px;padding:4px;border:1px solid #e0e0e0;border-radius:4px;" onchange="editType('${t.id}','icon',this.value)">
            <input type="text" value="${t.name}" style="flex:1;padding:4px;border:1px solid #e0e0e0;border-radius:4px;" onchange="editType('${t.id}','name',this.value)">
            <input type="color" value="${t.color}" onchange="editType('${t.id}','color',this.value)">
            <button onclick="deleteType('${t.id}')" style="color:#e74c3c;background:none;border:none;cursor:pointer;">🗑️</button>
        </div>`
    ).join('');
    // 加 emoji 快捷选择
    const picker = document.createElement('div');
    picker.className = 'emoji-picker';
    picker.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px;padding:8px;background:#f7f9fc;border-radius:6px;">
        ${['📝','✅','💭','📚','⭐','🎯','💡','🌀','🎁','❤️','🎨','🏆','📌','🔥','🌱','💬'].map(e =>
            `<button onclick="setQuickEmoji('${e}')" class="emoji-pick-btn">${e}</button>`
        ).join('')}
    </div>`;
    box.parentNode.insertBefore(picker, box);
    box.dataset.pickerInserted = '1';
    document.getElementById('typeManagerModal').style.display = 'flex';
}

function closeTypeManager() {
    document.getElementById('typeManagerModal').style.display = 'none';
}

function setQuickEmoji(e) {
    // 给"添加类型"的新类型默认名里塞 emoji，或者让用户手动点到某行的 icon 输入框
    // 简单做法：把 emoji 填到当前 focused 的输入框
    const sel = document.querySelector('#typeManagerList input[placeholder="emoji"]:focus');
    if (sel) { sel.value = e; sel.onchange(); }
    else {
        // 填到新类型名字里第一个字
        const inp = document.getElementById('newTypeName');
        if (inp) inp.value = e + ' ' + (inp.value || '');
    }
}

async function editType(id, field, val) {
    await fetch(`/api/notes/types/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({[field]: val})
    });
    await loadTypes();
}

async function deleteType(id) {
    if (!(await confirmDialog('删除后该类型下的随手记将变成"未分类"，确定删除吗？', '删除类型'))) return;
    const res = await fetch(`/api/notes/types/${id}`, {method: 'DELETE'});
    const data = await res.json();
    if (data.error) { showToast(data.error); return; }
    if (selectedType === id) selectedType = '';
    await loadTypes();
    loadNotes();
}

async function addType() {
    const name = document.getElementById('newTypeName').value.trim();
    const color = document.getElementById('newTypeColor').value;
    const icon = document.getElementById('newTypeName').dataset.icon || name.slice(0, 2);
    if (!name) return;
    await fetch(`/api/notes/types`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, icon, color})
    });
    document.getElementById('newTypeName').value = '';
    await loadTypes();
    openTypeManager();
    loadNotes();
}

// ============ 列表 & 筛选 ============
function debounceSearch() {
    clearTimeout(window._notesSearchTimer);
    window._notesSearchTimer = setTimeout(() => {
        notesSearchQuery = document.getElementById('notesSearch').value.trim();
        notesPage = 1;
        loadNotes();
    }, 300);
}

function applyFilters() {
    notesDateFilter = document.getElementById('notesDateFilter').value;
    notesPage = 1;
    loadNotes();
}

function buildNotesQuery() {
    const params = new URLSearchParams({page: notesPage});
    if (selectedType) params.set('type_id', selectedType);
    if (notesSearchQuery) params.set('q', notesSearchQuery);
    if (notesDateFilter === 'pinned') {
        params.set('pinned', '1');
    } else if (notesDateFilter === 'today') {
        params.set('from', todayStr());
    } else if (notesDateFilter === '7') {
        const d = new Date(); d.setDate(d.getDate() - 6);
        params.set('from', d.toISOString().slice(0, 10));
    } else if (notesDateFilter === '30') {
        const d = new Date(); d.setDate(d.getDate() - 29);
        params.set('from', d.toISOString().slice(0, 10));
    }
    return params.toString();
}

function todayStr() { return new Date().toISOString().slice(0, 10); }

async function loadNotes() {
    if (notesDateFilter === 'due') {
        return loadDueOnly();
    }
    const res = await fetch(`/api/notes?${buildNotesQuery()}`);
    const data = await res.json();
    if (notesPage === 1) currentNotes = data.notes;
    else currentNotes = [...currentNotes, ...data.notes];
    notesTotal = data.total;
    renderNotes();
}

async function loadDueOnly() {
    const res = await fetch(`/api/notes/due`);
    const data = await res.json();
    currentNotes = data.items;
    notesTotal = currentNotes.length;
    renderNotes();
}

function renderNotes() {
    const el = document.getElementById('notesList');
    const empty = document.getElementById('notesEmpty');
    if (!currentNotes.length) {
        el.innerHTML = '';
        empty.style.display = 'block';
    } else {
        empty.style.display = 'none';
        el.innerHTML = currentNotes.map(n => renderNoteCard(n)).join('');
    }
    const lm = document.getElementById('notesLoadMore');
    const loaded = notesPage * 30;
    lm.style.display = (notesTotal > loaded && notesDateFilter !== 'due') ? 'block' : 'none';
}

function loadMoreNotes() {
    notesPage++;
    loadNotes();
}

function renderNoteCard(n) {
    const typeColor = n.type_color || '#999';
    const typeIcon = n.type_icon || '📝';
    let html = `<div class="note-card" data-id="${n.id}" style="--type-color:${typeColor};">`;
    html += `<div class="note-card-header">`;
    html += `<span class="note-type-badge" style="background:${typeColor};">${typeIcon} ${escapeHtml(n.type_name || '未知')}</span>`;
    html += `<span class="note-meta">${formatNoteTime(n.created_at)}</span>`;
    html += `</div>`;
    html += `<div class="note-content">${escapeHtml(n.content).replace(/\n/g, '<br>')}</div>`;
    if (n.attachments && n.attachments.length) {
        html += `<div class="note-attachments">`;
        n.attachments.forEach(a => {
            if (a.type === 'image') {
                html += `<img src="/attachments/${a.filename}" class="note-thumb" onclick="previewImg('/attachments/${a.filename}')" />`;
            } else if (a.type === 'audio') {
                html += `<audio controls src="/attachments/${a.filename}" class="note-audio"></audio>`;
            }
        });
        html += `</div>`;
    }
    html += `<div class="note-card-footer">`;
    if (n.pinned) html += `<span class="note-badge pinned" title="置顶">📌 置顶</span>`;
    if (n.remind_at) {
        const overdue = !n.remind_done && n.remind_at <= todayStr();
        html += `<span class="note-badge ${overdue ? 'overdue' : 'remind'}">⏰ ${n.remind_at}</span>`;
    }
    html += `<button class="note-act" onclick="openEdit('${n.id}')">编辑</button>`;
    html += `<button class="note-act danger" onclick="deleteNote('${n.id}')">删除</button>`;
    html += `</div>`;
    html += `</div>`;
    return html;
}

function formatNoteTime(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return '刚刚';
        if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
        if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
        if (d.toISOString().slice(0, 10) === todayStr()) {
            return '今天 ' + d.toTimeString().slice(0, 5);
        }
        return d.toISOString().slice(0, 10);
    } catch { return iso; }
}

function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

// ============ 到期提醒横幅 & 浏览器通知 ============
async function loadDueBanner() {
    const res = await fetch(`/api/notes/due`);
    const data = await res.json();
    const banner = document.getElementById('notesDueBanner');
    if (data.count > 0) {
        banner.style.display = 'block';
        banner.innerHTML = `⏰ 今天有 <strong>${data.count}</strong> 条到期提醒 <button onclick="document.getElementById('notesDateFilter').value='due'; applyFilters();" style="margin-left:10px;background:none;border:none;color:#1565c0;cursor:pointer;text-decoration:underline;">查看 →</button>`;
        // 浏览器通知
        if ('Notification' in window) {
            if (Notification.permission === 'granted') {
                new Notification('📝 随手记到期提醒', {
                    body: `今天有 ${data.count} 条随手记提醒到期`,
                    tag: 'notes-due',
                    silent: true
                });
            } else if (Notification.permission === 'default') {
                // 用户交互过了可以申请
                Notification.requestPermission().then(p => {
                    if (p === 'granted') {
                        new Notification('📝 随手记到期提醒', {
                            body: `今天有 ${data.count} 条随手记提醒到期`,
                            tag: 'notes-due', silent: true
                        });
                    }
                });
            }
        }
    } else {
        banner.style.display = 'none';
    }
}

// ============ 新建 ============
function previewNewNoteColor() {
    const sel = document.getElementById('newNoteType');
    if (!sel) return;
    const type = notesTypes.find(t => t.id === sel.value);
    if (type) sel.style.color = type.color;
}

function toggleNewPinned() {
    newNotePinned = !newNotePinned;
    const btn = document.getElementById('newPinBtn');
    btn.style.background = newNotePinned ? '#ffd54f' : 'transparent';
    btn.style.border = newNotePinned ? '1px solid #f5a623' : 'none';
}

async function compressImage(file, maxDim = 1600, quality = 0.8) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            let { width, height } = img;
            if (width > height && width > maxDim) {
                height = Math.round(height * maxDim / width);
                width = maxDim;
            } else if (height > maxDim) {
                width = Math.round(width * maxDim / height);
                height = maxDim;
            }
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);
            canvas.toBlob(b => {
                if (!b) { reject(new Error('压缩失败')); return; }
                resolve(new File([b], file.name, {type: 'image/jpeg', lastModified: file.lastModified}));
            }, 'image/jpeg', quality);
        };
        img.onerror = reject;
        img.src = URL.createObjectURL(file);
    });
}

async function previewNewImage(input) {
    const orig = input.files[0];
    if (!orig) return;
    // 自动压缩
    let file = orig;
    if (orig.size > 200 * 1024 && orig.type.startsWith('image/')) {
        try { file = await compressImage(orig); } catch (e) { /* 压缩失败则用原文件 */ }
    }
    const url = URL.createObjectURL(file);
    newNoteAttachments.push({file, type: 'image', tempUrl: url});
    renderNewAttachments();
    input.value = '';
}

function previewNewAudio(input) {
    const file = input.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    newNoteAttachments.push({file, type: 'audio', tempUrl: url});
    renderNewAttachments();
    input.value = '';
}

function renderNewAttachments() {
    const el = document.getElementById('newNoteAttachPreview');
    if (!el) return;
    el.innerHTML = newNoteAttachments.map((a, i) => {
        if (a.type === 'image') {
            return `<div style="position:relative;"><img src="${a.tempUrl}" style="width:64px;height:64px;object-fit:cover;border-radius:6px;" /><button class="att-close" onclick="removeNewAttachment(${i})" style="position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:#e74c3c;color:white;border:none;font-size:10px;">✕</button></div>`;
        }
        return `<div style="display:flex;align-items:center;gap:4px;font-size:12px;background:#e8f0fe;padding:4px 8px;border-radius:6px;">🎵 音频 <button onclick="removeNewAttachment(${i})" style="background:none;border:none;color:#e74c3c;cursor:pointer;">✕</button></div>`;
    }).join('');
}

function removeNewAttachment(i) {
    const a = newNoteAttachments[i];
    if (a.tempUrl) URL.revokeObjectURL(a.tempUrl);
    newNoteAttachments.splice(i, 1);
    renderNewAttachments();
}

function handleNewNoteKey(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        saveNewNote();
    }
}

async function saveNewNote() {
    const content = document.getElementById('newNoteContent').value.trim();
    const type_id = document.getElementById('newNoteType').value;
    const remind_at = document.getElementById('newNoteRemind').value;
    if (!content) { showToast('内容不能为空'); return; }

    const res = await fetch('/api/notes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content, type_id, remind_at, pinned: newNotePinned})
    });
    const data = await res.json();
    if (!data.success) { showToast(data.error || '保存失败'); return; }

    // 附件上传
    for (const a of newNoteAttachments) {
        const fd = new FormData();
        fd.append('note_id', data.id);
        fd.append('file', a.file);
        await fetch('/api/note/upload', {method: 'POST', body: fd});
    }

    // 清空
    document.getElementById('newNoteContent').value = '';
    document.getElementById('newNoteRemind').value = '';
    newNoteAttachments = [];
    newNotePinned = false;
    const pb = document.getElementById('newPinBtn');
    if (pb) { pb.style.background = 'transparent'; pb.style.border = 'none'; }
    renderNewAttachments();
    loadTypes();
    loadNotes();
    loadDueBanner();
}

// ============ 编辑 ============
async function openEdit(id) {
    editingNoteId = id;
    editAttachmentsPendingRemove = [];
    const res = await fetch(`/api/notes/${id}`);
    const n = await res.json();
    if (!n.id) return;
    const editTypeSel = document.getElementById('editNoteType');
    if (editTypeSel) editTypeSel.value = n.type_id;
    document.getElementById('editNoteRemind').value = n.remind_at || '';
    document.getElementById('editNoteContent').value = n.content;
    document.getElementById('editNotePinned').checked = n.pinned;
    const attEl = document.getElementById('editNoteAttachments');
    if (attEl) {
        attEl.innerHTML = n.attachments.map(a => {
            if (a.type === 'image') {
                return `<div style="display:inline-block;margin:4px;"><img src="/attachments/${a.filename}" style="width:64px;height:64px;object-fit:cover;border-radius:6px;" />
                    <button class="att-close" onclick="removeEditAttachment(${a.id})" style="position:relative;top:-30px;left:20px;width:20px;height:20px;border-radius:50%;background:#e74c3c;color:white;border:none;font-size:10px;">✕</button></div>`;
            }
            return `<div style="display:flex;align-items:center;gap:4px;margin:4px;font-size:12px;background:#e8f0fe;padding:4px 8px;border-radius:6px;">🎵 音频
                    <button onclick="removeEditAttachment(${a.id})" style="background:none;border:none;color:#e74c3c;cursor:pointer;margin-left:4px;">✕</button></div>`;
        }).join('');
    }
    document.getElementById('editModal').style.display = 'flex';
}

function removeEditAttachment(aid) {
    editAttachmentsPendingRemove.push(aid);
    const el = event.target.closest('div');
    if (el) el.remove();
}

function closeEditModal() {
    document.getElementById('editModal').style.display = 'none';
    editingNoteId = null;
    editAttachmentsPendingRemove = [];
}

async function saveEdit() {
    const content = document.getElementById('editNoteContent').value.trim();
    if (!content) { showToast('内容不能为空'); return; }
    const pinned = document.getElementById('editNotePinned').checked;
    const body = {
        content,
        type_id: document.getElementById('editNoteType').value,
        remind_at: document.getElementById('editNoteRemind').value,
        pinned
    };
    await fetch(`/api/notes/${editingNoteId}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    });
    for (const aid of editAttachmentsPendingRemove) {
        await fetch(`/api/note/attachment/${aid}`, {method: 'DELETE'});
    }
    closeEditModal();
    loadNotes();
    loadDueBanner();
}

async function deleteNote(id) {
    if (!(await confirmDialog('确定删除这条随手记吗？', '删除随手记'))) return;
    const res = await fetch(`/api/notes/${id}`, {method: 'DELETE'});
    const data = await res.json();
    if (data.error) { showToast(data.error); return; }
    loadTypes();
    loadNotes();
    loadDueBanner();
}

// ============ 图片预览 ============
function previewImg(src) {
    document.getElementById('imgModalContent').src = src;
    document.getElementById('imgModal').style.display = 'flex';
}

// ============ 今日页用：到期提醒 ============
async function loadDueReminderForToday() {
    // 由 child.html 按需调用
}
