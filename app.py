#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小学生作业任务清单系统 - Flask后端 (SQLite版)
支持多孩子、局域网访问、数据持久化
"""

import os
import json
import re
import uuid
import socket
import threading
import sqlite3
import time
import zipfile
import tempfile
import shutil
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, g, session, Response, redirect, url_for, make_response

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 上传限制50MB

# ============ 路径配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ATTACH_DIR = os.path.join(BASE_DIR, 'attachments')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
DB_PATH = os.path.join(DATA_DIR, 'app.db')

for d in [DATA_DIR, ATTACH_DIR, BACKUP_DIR]:
    os.makedirs(d, exist_ok=True)


def load_secret_key():
    """session 密钥：优先环境变量，其次本地随机生成后落盘（不进 git）"""
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    key_file = os.path.join(DATA_DIR, '.secret_key')
    try:
        with open(key_file, 'r', encoding='utf-8') as f:
            saved = f.read().strip()
        if saved:
            return saved
    except OSError:
        pass
    new_key = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        with open(key_file, 'w', encoding='utf-8') as f:
            f.write(new_key)
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return new_key


app.secret_key = load_secret_key()  # session加密


# ============ 数据库初始化 ============
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            avatar TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            child_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            original_date TEXT NOT NULL,
            subject TEXT NOT NULL,
            desc TEXT NOT NULL,
            priority TEXT DEFAULT '必做',
            done INTEGER DEFAULT 0,
            done_time TEXT,
            quality INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            FOREIGN KEY (child_id) REFERENCES children(id)
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            type TEXT NOT NULL,
            desc TEXT DEFAULT '',
            filename TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS habits (
            id TEXT PRIMARY KEY,
            child_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            minutes INTEGER DEFAULT 0,
            days TEXT DEFAULT 'all',
            enabled INTEGER DEFAULT 1,
            FOREIGN KEY (child_id) REFERENCES children(id)
        );

        CREATE TABLE IF NOT EXISTS habit_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            habit_id TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            done_time TEXT,
            UNIQUE(child_id, date, habit_id)
        );

        CREATE TABLE IF NOT EXISTS daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            elapsed_seconds INTEGER DEFAULT 0,
            pause_count INTEGER DEFAULT 0,
            habit_pause_count INTEGER DEFAULT 0,
            star INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            mood TEXT DEFAULT '',
            suggested_time TEXT DEFAULT '',
            UNIQUE(child_id, date)
        );

        CREATE TABLE IF NOT EXISTS points_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pdf_annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attachment_id INTEGER NOT NULL,
            page_num INTEGER NOT NULL,
            strokes TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(attachment_id, page_num)
        );

        CREATE TABLE IF NOT EXISTS mistakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            subject TEXT DEFAULT '',
            content TEXT NOT NULL,
            mtype TEXT DEFAULT '',
            note TEXT DEFAULT '',
            mastered INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            next_review TEXT DEFAULT '',
            image TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS note_types (
            id TEXT PRIMARY KEY,
            child_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📝',
            color TEXT DEFAULT '#4a90d9',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (child_id) REFERENCES children(id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            child_id INTEGER NOT NULL,
            type_id TEXT NOT NULL,
            content TEXT NOT NULL,
            pinned INTEGER DEFAULT 0,
            remind_at TEXT DEFAULT '',
            remind_done INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (child_id) REFERENCES children(id),
            FOREIGN KEY (type_id) REFERENCES note_types(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS note_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id TEXT NOT NULL,
            type TEXT NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE
        );

        -- 小应用（单网页应用）数据同步：按 孩子 + 应用 + 键 存 JSON 字符串
        CREATE TABLE IF NOT EXISTS app_data (
            child_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            data_key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (child_id, slug, data_key)
        );
    ''')
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_notes_child_time ON notes(child_id, created_at DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_notes_type ON notes(child_id, type_id)")
        db.commit()
    except Exception:
        pass

    # 增量迁移：为旧库补列
    cols = [r[1] for r in db.execute("PRAGMA table_info(tasks)").fetchall()]
    if 'duration_seconds' not in cols:
        db.execute("ALTER TABLE tasks ADD COLUMN duration_seconds INTEGER DEFAULT 0")
    # 单任务计时窗口（时间戳结算，支持暂停，重启不丢）
    for tc, ttype in [('tt_start','TEXT'), ('tt_pause_start','TEXT'),
                      ('tt_accum','INTEGER DEFAULT 0'), ('tt_pause_count','INTEGER DEFAULT 0')]:
        if tc not in cols:
            db.execute(f"ALTER TABLE tasks ADD COLUMN {tc} {ttype}")
    # mistakes 表补复习/图片列
    mcols = [r[1] for r in db.execute("PRAGMA table_info(mistakes)").fetchall()]
    for mc, mtype in [('retry_count','INTEGER DEFAULT 0'), ('next_review','TEXT DEFAULT \'\''), ('image','TEXT DEFAULT \'\'')]:
        if mcols and mc not in mcols:
            db.execute(f"ALTER TABLE mistakes ADD COLUMN {mc} {mtype}")
    # 习惯倒计时窗口（时间戳结算，支持暂停，重启不丢）
    hcols = [r[1] for r in db.execute("PRAGMA table_info(habit_records)").fetchall()]
    for hc, htype in [('hb_start','TEXT'), ('hb_pause_start','TEXT'),
                      ('hb_elapsed','INTEGER DEFAULT 0'), ('hb_paused','INTEGER DEFAULT 0'),
                      ('hb_pause_count','INTEGER DEFAULT 0')]:
        if hcols and hc not in hcols:
            db.execute(f"ALTER TABLE habit_records ADD COLUMN {hc} {htype}")
    # 今日完成时刻（首次必做全完成的时间；取消勾选必做时清空）
    dcols = [r[1] for r in db.execute("PRAGMA table_info(daily_records)").fetchall()]
    if dcols and 'completed_at' not in dcols:
        db.execute("ALTER TABLE daily_records ADD COLUMN completed_at TEXT")
    # 积分记录：明细快照 + 类型（daily 每日结算 / redeem 兑换 / manual 手动 / streak 连续奖励）
    pcols = [r[1] for r in db.execute("PRAGMA table_info(points_records)").fetchall()]
    if pcols and 'detail' not in pcols:
        db.execute("ALTER TABLE points_records ADD COLUMN detail TEXT DEFAULT ''")
    if pcols and 'type' not in pcols:
        db.execute("ALTER TABLE points_records ADD COLUMN type TEXT DEFAULT 'daily'")
        # 旧记录分类：负分为兑换，其余为每日结算
        db.execute("UPDATE points_records SET type='redeem' WHERE points<0")
    db.commit()

    # 默认设置
    defaults = {
        'pin': '1234',
        'port': '8000',
        'base_points': '30',
        'star3_bonus': '20',
        'star2_bonus': '10',
        'habit_points': '5',
        'habit_all_bonus': '5',
        'optional_bonus': '10',
        'streak7_bonus': '50',
        'streak30_bonus': '200',
        'eye_break_interval': '20',
        'speech_rate': '0.9',
    }
    for k, v in defaults.items():
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # 默认兑换奖励
    rewards = [
        ('r1', '30分钟动画片/游戏时间', '100'),
        ('r2', '周末公园/游乐场一次', '200'),
        ('r3', '自选一本书', '300'),
        ('r4', '小玩具（50元内）', '500'),
    ]
    for rid, name, pts in rewards:
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                   (f'reward_{rid}', json.dumps({'id': rid, 'name': name, 'points': int(pts)}, ensure_ascii=False)))

    # 默认孩子
    cur = db.execute("SELECT COUNT(*) FROM children")
    if cur.fetchone()[0] == 0:
        db.execute("INSERT INTO children (name) VALUES (?)", ('宝贝',))

    # 默认习惯任务（始终确保存在，INSERT OR IGNORE 不重复）
    default_habits = [
        ('h1', '阅读', 10, 'all'),
        ('h2', '练字', 15, 'all'),
        ('h3', '坐姿端正', 0, 'all'),
        ('h4', '写字工整', 0, 'all'),
        ('h5', '物品整理', 0, 'all'),
    ]
    for hid, name, mins, days in default_habits:
        db.execute("INSERT OR IGNORE INTO habits (id, child_id, name, minutes, days, enabled) VALUES (?, ?, ?, ?, ?, 1)",
                   (hid, 1, name, mins, days))

    db.commit()

    # 迁移：给旧表加avatar字段
    try:
        db.execute("ALTER TABLE children ADD COLUMN avatar TEXT")
        db.commit()
    except:
        pass  # 字段已存在

    db.close()


# ============ 设置工具 ============
def get_setting(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()


def get_all_settings():
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    s = {}
    for r in rows:
        if r['key'].startswith('reward_'):
            continue
        try:
            s[r['key']] = int(r['value'])
        except:
            s[r['key']] = r['value']
    # 兑换奖励
    reward_rows = db.execute("SELECT value FROM settings WHERE key LIKE 'reward_%'").fetchall()
    s['rewards'] = [json.loads(r['value']) for r in reward_rows]
    return s


# ============ 多孩子工具 ============
def get_children():
    db = get_db()
    rows = db.execute("SELECT * FROM children ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_child_id():
    """获取当前请求的孩子 ID，安全隔离：
    - 家长后台（admin_authed session）：优先从 query/form 参数 child_id 获取
    - 孩子端：从 session['child_id'] 获取，禁止 query 参数绕过
    - 都没有则返回 None（禁止默认回退到 1）"""
    is_admin = session.get('admin_authed')
    # 家长后台：允许从 query/form 参数拿 child_id（前端切换孩子时拼在 URL 上）
    if is_admin:
        cid = request.args.get('child_id', request.form.get('child_id'))
        if cid:
            try:
                return int(cid)
            except:
                pass
    # 孩子端或 admin 没传参数时：从 session 取（admin 也允许 session 回退，
    # 比如 admin 页面没显式传 child_id 但 session 里还有之前孩子端的登录态）
    cid = session.get('child_id')
    if cid is not None:
        return int(cid)
    return None


def require_child_id():
    """路由入口守卫：
    - admin 会话：允许，child_id 由 get_child_id() 提供（信任前端传的 child_id 参数）
    - 非 admin 会话：必须 session['child_id'] 存在，否则 401
    """
    cid = get_child_id()
    if cid is None:
        return None, jsonify({'error': '请先登录'}), 401
    # 非 admin 时，额外确认没被 query 参数绕过
    if not session.get('admin_authed'):
        # 再次确认 query 参数没有生效（防御性校验）
        q_cid = request.args.get('child_id', request.form.get('child_id'))
        if q_cid is not None:
            # query 参数被忽略是 get_child_id() 的设计，这里不需要额外处理
            pass
    return cid, None, None


def _api_err(msg, code=400):
    return jsonify({'error': msg}), code


# ============ 积分计算 ============
def compute_points(child_id, day_str, settings=None):
    """纯计算指定日期的积分，不写库。返回 (points, details)。"""
    db = get_db()
    if settings is None:
        settings = get_all_settings()

    # 必做任务是否全部完成（只算当天原本就有的任务，不算延后过来的）
    req_total = db.execute("SELECT COUNT(*) as c FROM tasks WHERE child_id=? AND original_date=? AND priority='必做'",
                           (child_id, day_str)).fetchone()['c']
    req_done = db.execute("SELECT COUNT(*) as c FROM tasks WHERE child_id=? AND original_date=? AND priority='必做' AND done=1",
                          (child_id, day_str)).fetchone()['c']

    points = 0
    details = []

    if req_total > 0 and req_done == req_total:
        points += settings['base_points']
        details.append({'reason': '必做任务全部完成', 'points': settings['base_points']})

    # 选做题完成（只算当天原本就有的）
    opt = db.execute("SELECT COUNT(*) as c FROM tasks WHERE child_id=? AND original_date=? AND priority='选做' AND done=1",
                     (child_id, day_str)).fetchone()['c']
    if opt > 0:
        points += settings['optional_bonus']
        details.append({'reason': f'完成{opt}个选做题', 'points': settings['optional_bonus']})

    # 习惯任务
    habits = db.execute("SELECT * FROM habits WHERE child_id=? AND enabled=1", (child_id,)).fetchall()
    habit_done = db.execute("SELECT COUNT(*) as c FROM habit_records WHERE child_id=? AND date=? AND done=1",
                            (child_id, day_str)).fetchone()['c']
    habit_total = len(habits)
    if habit_done > 0:
        p = habit_done * settings['habit_points']
        points += p
        details.append({'reason': f'完成{habit_done}个习惯任务', 'points': p})
        if habit_total > 0 and habit_done == habit_total:
            points += settings['habit_all_bonus']
            details.append({'reason': '全部习惯任务完成', 'points': settings['habit_all_bonus']})

    # 家长星级评价
    dr = db.execute("SELECT star FROM daily_records WHERE child_id=? AND date=?", (child_id, day_str)).fetchone()
    star = dr['star'] if dr else 0
    if star == 3:
        points += settings['star3_bonus']
        details.append({'reason': '家长评价3星', 'points': settings['star3_bonus']})
    elif star == 2:
        points += settings['star2_bonus']
        details.append({'reason': '家长评价2星', 'points': settings['star2_bonus']})

    return points, details


def compute_streak(child_id, day_str):
    """从 day_str 往前统计连续「必做全部完成」的天数，返回 (streak, start_date)。"""
    db = get_db()
    cur = datetime.strptime(day_str, '%Y-%m-%d').date()
    streak = 0
    while True:
        rows = db.execute("SELECT done FROM tasks WHERE child_id=? AND date=? AND priority='必做'",
                          (child_id, cur.isoformat())).fetchall()
        if rows and all(r['done'] for r in rows):
            streak += 1
            cur -= timedelta(days=1)
        else:
            break
    start = (cur + timedelta(days=1)).isoformat() if streak > 0 else None
    return streak, start


def award_streak_bonus(child_id, day_str, settings=None):
    """连续打卡奖励：达到 7 / 30 天各发一次，同一轮里程碑只发一次。

    记录落在里程碑当天（start + days - 1），用日期 + 原因去重，
    因此中途断签重来后起点变化，会重新计算，不会漏发也不会重复发。
    """
    if settings is None:
        settings = get_all_settings()
    streak, start = compute_streak(child_id, day_str)
    if streak == 0:
        # 今天还没完成时，昨天可能已达成里程碑，回溯一天避免漏发
        prev = (datetime.strptime(day_str, '%Y-%m-%d').date() - timedelta(days=1)).isoformat()
        streak, start = compute_streak(child_id, prev)
    if streak <= 0 or not start:
        return []
    db = get_db()
    awarded = []
    start_date = datetime.strptime(start, '%Y-%m-%d').date()
    for days, key in ((7, 'streak7_bonus'), (30, 'streak30_bonus')):
        if streak < days:
            continue
        bonus = int(settings.get(key, 0) or 0)
        if bonus <= 0:
            continue
        milestone = (start_date + timedelta(days=days - 1)).isoformat()
        reason = f'连续打卡{days}天奖励'
        exists = db.execute(
            "SELECT 1 FROM points_records WHERE child_id=? AND type='streak' AND date=? AND reason=?",
            (child_id, milestone, reason)).fetchone()
        if exists:
            continue
        detail = json.dumps([{'reason': f'连续打卡{days}天', 'points': bonus}], ensure_ascii=False)
        db.execute("INSERT INTO points_records (child_id, date, points, reason, detail, type) VALUES (?, ?, ?, ?, ?, 'streak')",
                   (child_id, milestone, bonus, reason, detail))
        db.commit()
        awarded.append({'days': days, 'points': bonus, 'date': milestone})
    return awarded


def settle_day(child_id, day_str, settings=None):
    """结算当天积分：每天一条 type='daily' 记录，分数随完成度更新（upsert）。

    历史日期不自动改写，避免浏览历史时污染账本。
    """
    today = date.today().isoformat()
    if day_str < today:
        return compute_points(child_id, day_str, settings)

    points, details = compute_points(child_id, day_str, settings)
    db = get_db()
    row = db.execute("SELECT id, points, reason, detail FROM points_records WHERE child_id=? AND date=? AND type='daily'",
                     (child_id, day_str)).fetchone()
    if points > 0:
        detail_json = json.dumps(details, ensure_ascii=False)
        reason = f'每日结算（{len(details)}项）'
        if row:
            # 值没变就不写，避免每次刷新页面都产生写盘
            if row['points'] != points or row['reason'] != reason or (row['detail'] or '') != detail_json:
                db.execute("UPDATE points_records SET points=?, reason=?, detail=? WHERE id=?",
                           (points, reason, detail_json, row['id']))
                db.commit()
        else:
            db.execute("INSERT INTO points_records (child_id, date, points, reason, detail, type) VALUES (?, ?, ?, ?, ?, 'daily')",
                       (child_id, day_str, points, reason, detail_json))
            db.commit()
    elif row:
        # 全部取消完成，清零当天记录
        db.execute("DELETE FROM points_records WHERE id=?", (row['id'],))
        db.commit()

    # 连续打卡奖励（达到 7 / 30 天时自动发放）
    award_streak_bonus(child_id, day_str, settings)
    return points, details


# ============ 自动备份 ============
def _export_data_dict(db):
    """从连接好的 db 导出完整数据字典（auto_backup 和手动导出共用）"""
    return {
        'children': [dict(r) for r in db.execute("SELECT * FROM children").fetchall()],
        'tasks': [dict(r) for r in db.execute("SELECT * FROM tasks").fetchall()],
        'mistakes': [dict(r) for r in db.execute("SELECT * FROM mistakes").fetchall()],
        'note_types': [dict(r) for r in db.execute("SELECT * FROM note_types").fetchall()],
        'notes': [dict(r) for r in db.execute("SELECT * FROM notes").fetchall()],
        'note_attachments': [dict(r) for r in db.execute("SELECT * FROM note_attachments").fetchall()],
        'app_data': [dict(r) for r in db.execute("SELECT * FROM app_data").fetchall()],
        'daily_records': [dict(r) for r in db.execute("SELECT * FROM daily_records").fetchall()],
        'habits': [dict(r) for r in db.execute("SELECT * FROM habits").fetchall()],
        'habit_records': [dict(r) for r in db.execute("SELECT * FROM habit_records").fetchall()],
        'points_records': [dict(r) for r in db.execute("SELECT * FROM points_records").fetchall()],
        'attachments': [dict(r) for r in db.execute("SELECT * FROM attachments").fetchall()],
        'settings': dict(db.execute("SELECT key, value FROM settings").fetchall()),
        'backup_time': datetime.now().isoformat()
    }


def _cleanup_old_backups(keep_days=30):
    """清理超过 keep_days 天的旧备份文件"""
    try:
        cutoff = date.today() - timedelta(days=keep_days)
        removed = 0
        for fname in os.listdir(BACKUP_DIR):
            if not (fname.endswith('.json') or fname.endswith('.zip')):
                continue
            try:
                datestr = fname.split('_', 1)[1].rsplit('.', 1)[0]
                fdate = date.fromisoformat(datestr)
            except Exception:
                continue
            if fdate < cutoff:
                try:
                    os.remove(os.path.join(BACKUP_DIR, fname))
                    removed += 1
                except Exception:
                    pass
        if removed:
            print(f"清理 {removed} 个超过 {keep_days} 天的旧备份")
    except Exception:
        pass


def auto_backup():
    today_str = date.today().isoformat()
    backup_file = os.path.join(BACKUP_DIR, f"auto_{today_str}.json")
    if os.path.exists(backup_file):
        return
    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        data = _export_data_dict(db)
        db.close()
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _cleanup_old_backups(30)
    except Exception as e:
        print(f"自动备份失败: {e}")


# ============ 任务文本解析 ============
def parse_task_text(text):
    tasks = []
    current_subject = None
    suggested_time = None

    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('【日期】'):
            continue
        if line.startswith('【建议时长】'):
            suggested_time = line.replace('【建议时长】', '').strip()
            continue
        m = re.match(r'^【(.+?)】$', line)
        if m:
            current_subject = m.group(1)
            continue
        # 更宽容的匹配：支持 - · * 等开头，任意空白
        m = re.match(r'^[-·*•]\s*[\[\【]\s*(必做|选做)\s*[\]\】]\s*(.+)', line)
        if m:
            priority = m.group(1)
            desc = m.group(2).strip()
            attachments = []
            att_matches = re.findall(r'（(附图|附视频|附音频|附文件)：([^）]+)）', desc)
            for att_type, att_desc in att_matches:
                type_map = {'附图': 'image', '附视频': 'video', '附音频': 'audio', '附文件': 'pdf'}
                attachments.append({'type': type_map.get(att_type, 'image'), 'desc': att_desc.strip(), 'filename': None})
            desc_clean = re.sub(r'（(附图|附视频|附音频|附文件)：[^）]+）', '', desc).strip()
            tasks.append({
                'subject': current_subject or '其他',
                'desc': desc_clean,
                'priority': priority,
                'attachments': attachments
            })
    return tasks, suggested_time


# ============ 页面路由 ============
@app.route('/favicon.ico')
def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _current_port():
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute("SELECT value FROM settings WHERE key='port'").fetchone()
        db.close()
        return int(row[0]) if row else 8000
    except Exception:
        return 8000


@app.route('/api/server/info')
def api_server_info():
    ip = get_lan_ip()
    port = _current_port()
    return jsonify({
        'ip': ip,
        'port': port,
        'lan_url': f'http://{ip}:{port}' if ip else None,
        'local_url': f'http://127.0.0.1:{port}'
    })


@app.route('/api/server/stop', methods=['POST'])
def api_server_stop():
    if not session.get('admin_authed'):
        return jsonify({'error': '需要家长权限'}), 403
    def _halt():
        time.sleep(0.6)
        os._exit(0)
    threading.Thread(target=_halt, daemon=True).start()
    return jsonify({'success': True, 'message': '服务即将关闭'})


def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="80" font-size="80">📚</text></svg>'
    return Response(svg, mimetype='image/svg+xml')

@app.route('/')
def index():
    if 'child_id' in session:
        return render_template('child.html')
    return render_template('login.html')


@app.route('/admin')
def admin():
    if not session.get('admin_authed'):
        return redirect('/')
    resp = make_response(render_template('admin.html'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/history')
def history():
    return render_template('history.html')


@app.route('/rewards')
def rewards():
    return render_template('rewards.html')


@app.route('/notes')
def notes_view():
    return render_template('notes.html')


@app.route('/guide')
def guide():
    return render_template('guide.html')


# ============ 小应用（单网页应用）============
# 约定：把任意单网页应用放到 static/apps/<slug>/ 下，并提供一个 app.json：
#   { "name": "汉字随机认读", "icon": "字", "desc": "...", "entry": "index.html",
#     "color": "#d9603f", "order": 10,
#     "sync": true, "syncKeys": ["key1"], "syncPrefixes": ["prefix."] }
# 放进去即自动出现在「应用中心」，无需改 Python 代码。
APPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'apps')


def scan_apps():
    """扫描 static/apps/*/app.json，返回应用清单（按 order 排序）。"""
    apps = []
    if not os.path.isdir(APPS_DIR):
        return apps
    for slug in sorted(os.listdir(APPS_DIR)):
        meta_path = os.path.join(APPS_DIR, slug, 'app.json')
        if not os.path.isfile(meta_path):
            continue
        try:
            with open(meta_path, encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            continue
        meta.setdefault('slug', slug)
        meta['slug'] = slug
        meta.setdefault('name', slug)
        meta.setdefault('icon', '🧩')
        meta.setdefault('desc', '')
        meta.setdefault('entry', 'index.html')
        meta.setdefault('color', '#4a90d9')
        meta.setdefault('order', 100)
        meta.setdefault('sync', False)
        meta.setdefault('syncKeys', [])
        meta.setdefault('syncPrefixes', [])
        meta['url'] = f"/static/apps/{slug}/{meta['entry']}"
        meta['page'] = f"/apps/{slug}"
        apps.append(meta)
    apps.sort(key=lambda a: (a.get('order', 100), a['slug']))
    return apps


@app.route('/apps')
def apps_hub():
    if not session.get('child_id'):
        return redirect('/login')
    return render_template('apps.html', apps=scan_apps())


@app.route('/apps/<slug>')
def app_shell(slug):
    cid = session.get('child_id')
    if not cid:
        return redirect('/login')
    app = next((a for a in scan_apps() if a['slug'] == slug), None)
    if not app:
        return render_template('apps.html', apps=scan_apps()), 404
    return render_template('app_shell.html', app=app, child_id=cid)


@app.route('/api/apps')
def api_apps():
    return jsonify({'apps': scan_apps()})


def _valid_app_slug(slug):
    return any(a['slug'] == slug for a in scan_apps())


@app.route('/api/apps/<slug>/data', methods=['GET'])
def api_app_data_get(slug):
    child_id, err = _require_notes_auth()
    if err:
        return err
    if not _valid_app_slug(slug):
        return jsonify({'error': '应用不存在'}), 404
    db = get_db()
    rows = db.execute(
        "SELECT data_key, value, updated_at FROM app_data WHERE child_id=? AND slug=?",
        (child_id, slug)).fetchall()
    keys = {}
    latest = ''
    for r in rows:
        try:
            keys[r['data_key']] = json.loads(r['value'])
        except Exception:
            keys[r['data_key']] = r['value']
        if r['updated_at'] > latest:
            latest = r['updated_at']
    return jsonify({'slug': slug, 'keys': keys, 'updated_at': latest})


@app.route('/api/apps/<slug>/data', methods=['PUT', 'POST'])
def api_app_data_put(slug):
    child_id, err = _require_notes_auth()
    if err:
        return err
    if not _valid_app_slug(slug):
        return jsonify({'error': '应用不存在'}), 404
    payload = request.json or {}
    keys = payload.get('keys') or {}
    if not isinstance(keys, dict):
        return jsonify({'error': 'keys 必须是对象'}), 400
    db = get_db()
    now = datetime.now().isoformat()
    for k, v in keys.items():
        db.execute(
            "INSERT INTO app_data (child_id, slug, data_key, value, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(child_id, slug, data_key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (child_id, slug, str(k), json.dumps(v, ensure_ascii=False), now))
    db.commit()
    return jsonify({'success': True, 'updated_at': now, 'count': len(keys)})


# ============ API: 孩子管理 ============
@app.route('/api/children')
def api_children():
    return jsonify({'children': get_children()})


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    child_id = data.get('child_id')
    child = next((c for c in get_children() if c['id'] == child_id), None)
    if not child:
        return jsonify({'error': '孩子不存在'}), 404
    session['child_id'] = child_id
    session['child_name'] = child['name']
    return jsonify({'success': True, 'child_id': child_id, 'name': child['name']})


@app.route('/api/logout')
def api_logout():
    session.pop('child_id', None)
    session.pop('child_name', None)
    return jsonify({'success': True})


@app.route('/api/current_user')
def api_current_user():
    return jsonify({
        'child_id': session.get('child_id'),
        'name': session.get('child_name')
    })


@app.route('/api/children/add', methods=['POST'])
def api_add_child():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '名字不能为空'}), 400
    db = get_db()
    cur = db.execute("INSERT INTO children (name) VALUES (?)", (name,))
    db.commit()
    # 给新孩子创建默认习惯
    default_habits = [
        ('阅读', 10, 'all'),
        ('练字', 15, 'all'),
        ('坐姿端正', 0, 'all'),
        ('写字工整', 0, 'all'),
        ('物品整理', 0, 'all'),
    ]
    for name, mins, days in default_habits:
        hid = uuid.uuid4().hex[:8]
        db.execute("INSERT INTO habits (id, child_id, name, minutes, days, enabled) VALUES (?, ?, ?, ?, ?, 1)",
                   (hid, cur.lastrowid, name, mins, days))
    db.commit()
    return jsonify({'success': True, 'id': cur.lastrowid})


@app.route('/api/children/<int:child_id>', methods=['DELETE'])
def api_delete_child(child_id):
    db = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM children").fetchone()['c']
    if count <= 1:
        return jsonify({'error': '至少保留一个孩子'}), 400
    db.execute("DELETE FROM tasks WHERE child_id=?", (child_id,))
    db.execute("DELETE FROM habits WHERE child_id=?", (child_id,))
    db.execute("DELETE FROM habit_records WHERE child_id=?", (child_id,))
    db.execute("DELETE FROM daily_records WHERE child_id=?", (child_id,))
    db.execute("DELETE FROM points_records WHERE child_id=?", (child_id,))
    db.execute("DELETE FROM children WHERE id=?", (child_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/children/<int:child_id>/rename', methods=['POST'])
def api_rename_child(child_id):
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '名字不能为空'}), 400
    db = get_db()
    db.execute("UPDATE children SET name=? WHERE id=?", (name, child_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/children/<int:child_id>/avatar', methods=['POST'])
def api_upload_avatar(child_id):
    file = request.files.get('avatar')
    if not file:
        return jsonify({'error': '没有文件'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif']:
        return jsonify({'error': '只支持jpg/png/gif'}), 400
    safe_name = f"avatar_{child_id}{ext}"
    safe_name = os.path.basename(safe_name)
    filepath = os.path.join(ATTACH_DIR, safe_name)
    file.save(filepath)
    db = get_db()
    db.execute("UPDATE children SET avatar=? WHERE id=?", (safe_name, child_id))
    db.commit()
    return jsonify({'success': True, 'avatar': safe_name})


@app.route('/api/children/<int:child_id>/sticker', methods=['POST'])
def api_set_sticker(child_id):
    emoji = (request.get_json(silent=True) or {}).get('emoji', '')
    # 只允许单字符emoji，防止注入；sticker: 前缀区分于图片文件名
    emoji = emoji.strip()[:8]
    if not emoji:
        return jsonify({'error': '请选择贴纸'}), 400
    db = get_db()
    db.execute("UPDATE children SET avatar=? WHERE id=?", ('sticker:' + emoji, child_id))
    db.commit()
    return jsonify({'success': True, 'avatar': 'sticker:' + emoji})


# ============ API: 手动添加任务 ============
@app.route('/api/task/add', methods=['POST'])
def api_add_task():
    child_id, err, code = require_child_id()
    if err: return err, code
    data = request.json
    db = get_db()
    target_date = data.get('date') or date.today().isoformat()
    tid = uuid.uuid4().hex[:8]
    db.execute("""INSERT INTO tasks (id, child_id, date, original_date, subject, desc, priority, sort_order)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
               (tid, child_id, target_date, target_date, data.get('subject', '其他'),
                data.get('desc', ''), data.get('priority', '必做'), 0))
    db.commit()
    return jsonify({'success': True, 'id': tid})


# ============ 计时器状态（内存+持久化） ============
timer_state = {}

def get_timer_state(child_id):
    today = date.today().isoformat()
    if child_id not in timer_state:
        # 从数据库恢复
        db = get_db()
        dr = db.execute("SELECT * FROM daily_records WHERE child_id=? AND date=?", (child_id, today)).fetchone()
        if dr and dr['start_time'] and not dr['end_time']:
            timer_state[child_id] = {
                'status': 'running',
                'start_time': dr['start_time'],
                'pause_start': None,
                'total_paused': 0,
                'pause_count': dr['pause_count'],
                'date': today
            }
        else:
            timer_state[child_id] = {
                'status': 'idle', 'start_time': None, 'pause_start': None,
                'total_paused': 0, 'pause_count': 0, 'date': today
            }
    if timer_state[child_id]['date'] != today:
        timer_state[child_id] = {
            'status': 'idle', 'start_time': None, 'pause_start': None,
            'total_paused': 0, 'pause_count': 0, 'date': today
        }
    return timer_state[child_id]

def _calc_elapsed(ts):
    """根据计时状态计算已用秒数（扣除暂停）"""
    if not ts['start_time']:
        return 0
    start = datetime.fromisoformat(ts['start_time'])
    if ts['status'] == 'paused' and ts.get('pause_start'):
        end = datetime.fromisoformat(ts['pause_start'])
    else:
        end = datetime.now()
    return max(0, int((end - start).total_seconds() - ts.get('total_paused', 0)))


def save_timer_state(child_id):
    ts = get_timer_state(child_id)
    db = get_db()
    today = ts['date']
    # 先确保行存在（INSERT OR IGNORE 不覆盖已有评价/用时）
    db.execute("""
        INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)
    """, (child_id, today))
    # 只更新计时相关字段，保留 star/note/mood/elapsed_seconds
    elapsed = _calc_elapsed(ts)
    db.execute("""
        UPDATE daily_records
        SET start_time=?, end_time=?, pause_count=?, elapsed_seconds=?
        WHERE child_id=? AND date=?
    """, (ts['start_time'],
          datetime.now().isoformat() if ts['status'] == 'done' else None,
          ts['pause_count'], elapsed, child_id, today))
    db.commit()


# ============ API: 今日数据 ============
@app.route('/api/today')
def api_today():
    auto_backup()
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()

    tasks = db.execute("SELECT * FROM tasks WHERE child_id=? AND date=? ORDER BY sort_order, rowid",
                       (child_id, today)).fetchall()
    task_list = []
    focus_sec = 0
    for t in tasks:
        attachments = db.execute("SELECT * FROM attachments WHERE task_id=?", (t['id'],)).fetchall()
        sess = _task_session_seconds(t)
        focus_sec += (t['duration_seconds'] or 0) + sess
        task_list.append({
            'id': t['id'], 'subject': t['subject'], 'desc': t['desc'],
            'priority': t['priority'], 'done': bool(t['done']),
            'done_time': t['done_time'], 'quality': t['quality'],
            'errors': t['errors'],
            'duration_seconds': t['duration_seconds'] or 0,
            'session_seconds': sess,
            'timing': bool(t['tt_start']) and not t['tt_pause_start'],
            'paused': bool(t['tt_start'] and t['tt_pause_start']),
            'attachments': [dict(a) for a in attachments]
        })

    habits = db.execute("SELECT * FROM habits WHERE child_id=? AND enabled=1", (child_id,)).fetchall()
    habit_records = db.execute("SELECT * FROM habit_records WHERE child_id=? AND date=?", (child_id, today)).fetchall()
    habits_status = {}
    for r in habit_records:
        habits_status[r['habit_id']] = {
            'done': bool(r['done']),
            'done_time': r['done_time'],
            'hb_start': r['hb_start'] if 'hb_start' in r.keys() else None,
            'hb_paused': bool(r['hb_paused']) if 'hb_paused' in r.keys() else False,
            'hb_elapsed': (r['hb_elapsed'] or 0) if 'hb_elapsed' in r.keys() else 0,
        }

    dr = db.execute("SELECT * FROM daily_records WHERE child_id=? AND date=?", (child_id, today)).fetchone()
    ts = get_timer_state(child_id)

    # 计算实时已用时间
    elapsed = 0
    if ts['status'] == 'running' and ts['start_time']:
        elapsed = int((datetime.now() - datetime.fromisoformat(ts['start_time'])).total_seconds() - ts['total_paused'])
    elif ts['status'] == 'paused' and ts['start_time']:
        elapsed = int((datetime.fromisoformat(ts['pause_start']) - datetime.fromisoformat(ts['start_time'])).total_seconds() - ts['total_paused'])
    elif ts['status'] == 'done':
        elapsed = dr['elapsed_seconds'] if dr else 0

    # running/paused 时把实时用时增量落库，避免忘记点结束导致历史为0
    if ts['status'] in ('running', 'paused') and elapsed > 0:
        db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)",
                   (child_id, today))
        db.execute("UPDATE daily_records SET elapsed_seconds=? WHERE child_id=? AND date=?",
                   (elapsed, child_id, today))
        db.commit()

    timer = {
        'status': ts['status'],
        'start_time': ts['start_time'],
        'elapsed_seconds': elapsed,
        'focus_seconds': focus_sec,
        'pause_count': ts['pause_count'],
        'total_paused': ts['total_paused'],
        'pause_start': ts['pause_start'],
        'habit_pause_count': dr['habit_pause_count'] if dr else 0
    }

    points, details = settle_day(child_id, today)

    return jsonify({
        'date': today,
        'tasks': task_list,
        'focus_seconds': focus_sec,
        'suggested_time': dr['suggested_time'] if dr else '',
        'timer': timer,
        'habits': [dict(h) for h in habits],
        'habits_status': habits_status,
        'star': dr['star'] if dr else 0,
        'note': dr['note'] if dr else '',
        'mood': dr['mood'] if dr else '',
        'habit_pause_count': dr['habit_pause_count'] if dr else 0,
        'speech_rate': float(get_setting('speech_rate', '0.9') or 0.9),
        'points_earned': points,
        'point_details': details
    })


# ============ API: 周计划（本周一~周日） ============
@app.route('/api/week')
def api_week():
    child_id, err, code = require_child_id()
    if err: return err, code
    ref = request.args.get('date')
    try:
        base = datetime.strptime(ref, '%Y-%m-%d').date() if ref else date.today()
    except ValueError:
        base = date.today()
    monday = base - timedelta(days=base.weekday())
    db = get_db()
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        ds = d.isoformat()
        rows = db.execute(
            "SELECT id, subject, desc, priority, done, done_time FROM tasks WHERE child_id=? AND date=? ORDER BY sort_order",
            (child_id, ds)).fetchall()
        task_list = [dict(r) for r in rows]
        done_n = sum(1 for r in rows if r['done'])
        days.append({
            'date': ds,
            'weekday': weekdays[i],
            'is_today': ds == date.today().isoformat(),
            'tasks': task_list,
            'done_count': done_n,
            'total': len(rows)
        })
    return jsonify({'monday': monday.isoformat(), 'days': days})


# ============ API: 任务导入 ============
@app.route('/api/tasks/import', methods=['POST'])
def api_import():
    child_id, err, code = require_child_id()
    if err: return err, code
    data = request.json
    text = data.get('text', '')
    target_date = data.get('date', date.today().isoformat())

    tasks, suggested_time = parse_task_text(text)
    if not tasks:
        return jsonify({'error': '没有解析到任务'}), 400

    db = get_db()
    for i, t in enumerate(tasks):
        tid = uuid.uuid4().hex[:8]
        db.execute("INSERT INTO tasks (id, child_id, date, original_date, subject, desc, priority, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (tid, child_id, target_date, target_date, t['subject'], t['desc'], t['priority'], i))
        for att in t['attachments']:
            db.execute("INSERT INTO attachments (task_id, type, desc, filename) VALUES (?, ?, ?, ?)",
                       (tid, att['type'], att['desc'], None))

    if suggested_time:
        db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)",
                   (child_id, target_date))
        db.execute("UPDATE daily_records SET suggested_time=? WHERE child_id=? AND date=?",
                   (suggested_time, child_id, target_date))

    db.commit()
    return jsonify({'success': True, 'imported': len(tasks)})


# ============ API: 任务勾选 ============
@app.route('/api/task/<task_id>/toggle', methods=['POST'])
def api_toggle_task(task_id):
    db = get_db()
    t = db.execute("SELECT done, child_id, date, priority, tt_start, tt_pause_start, tt_accum FROM tasks WHERE id=?",
                   (task_id,)).fetchone()
    if not t:
        return jsonify({'error': '任务不存在'}), 404
    new_done = 0 if t['done'] else 1
    child_id = t['child_id']
    today = t['date']
    now_iso = datetime.now().isoformat()
    started_next = None
    celebration = None
    optional_remaining = 0
    # 勾选时该任务是否正在计时（决定是否自动接力）
    was_running = bool(t['tt_start']) and not t['tt_pause_start']

    # 勾选完成时，自动结算该任务正在进行的计时（时间戳）
    if new_done and t['tt_start']:
        elapsed = _task_session_seconds(t)
        db.execute("UPDATE tasks SET duration_seconds=COALESCE(duration_seconds,0)+?, tt_start=NULL, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                   (elapsed, task_id))
    db.execute("UPDATE tasks SET done=?, done_time=? WHERE id=?",
               (new_done, now_iso if new_done else None, task_id))

    if new_done:
        rem_req = db.execute("SELECT COUNT(*) FROM tasks WHERE child_id=? AND date=? AND done=0 AND priority='必做'",
                             (child_id, today)).fetchone()[0]
        rem_opt = db.execute("SELECT COUNT(*) FROM tasks WHERE child_id=? AND date=? AND done=0 AND priority='选做'",
                             (child_id, today)).fetchone()[0]
        optional_remaining = rem_opt
        db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)", (child_id, today))

        if rem_req == 0:
            # 必做全完成：记录完成时刻（只记第一次）
            old_completed = db.execute("SELECT completed_at FROM daily_records WHERE child_id=? AND date=?",
                                       (child_id, today)).fetchone()
            first_required_done = old_completed and old_completed['completed_at'] is None
            db.execute("UPDATE daily_records SET completed_at=COALESCE(completed_at, ?) WHERE child_id=? AND date=?",
                       (now_iso, child_id, today))
            if rem_opt == 0:
                celebration = 'all_done'   # 必做+选做全部完成
            elif first_required_done:
                celebration = 'required_done'  # 首次必做全完成，弹窗询问是否继续选做
            # 挂起墙钟（不记休息次数）：作业结束是检查点，不是休息
            _suspend_wall_if_no_task_running(db, child_id, today, now_iso)
        elif was_running:
            # 还有必做且完成的是正在计时的任务 → 自动接力下一个必做
            nxt = db.execute(
                "SELECT id FROM tasks WHERE child_id=? AND date=? AND done=0 AND priority='必做' "
                "ORDER BY sort_order, rowid LIMIT 1",
                (child_id, today)).fetchone()
            if nxt:
                wall_action, _ = _ensure_wall_running_if_idle(child_id, now_iso)
                if wall_action != 'habit_running':
                    db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                               (now_iso, nxt['id']))
                    started_next = nxt['id']
    else:
        # 取消勾选必做 → 清空完成时刻，重新全完成时再记录
        if t['priority'] == '必做':
            db.execute("UPDATE daily_records SET completed_at=NULL WHERE child_id=? AND date=? AND completed_at IS NOT NULL",
                       (child_id, today))
    db.commit()
    return jsonify({'success': True, 'started_next': started_next,
                    'celebration': celebration, 'optional_remaining': optional_remaining})


# 单任务计时：时间戳落库结算，支持暂停，重启不丢
def _task_session_seconds(row):
    """当前会话已走秒数（含暂停前累计）。"""
    if not row['tt_start']:
        return 0
    acc = row['tt_accum'] or 0
    if row['tt_pause_start']:
        return acc
    try:
        acc += int((datetime.now() - datetime.fromisoformat(row['tt_start'])).total_seconds())
    except Exception:
        pass
    return acc


# ============ 墙钟 ↔ 任务专注计时 联动 ============

def _ensure_wall_running_if_idle(child_id, when_iso):
    """任务启动时：若墙钟是 idle → 自动 start；若 paused → 自动 resume。
    返回: ('started', reason)  reason='auto_start' | 'auto_resume' | 'already' | 'habit_running'"""
    ts = get_timer_state(child_id)
    today = date.today().isoformat()
    db = get_db()

    # 墙钟已 running：无需动作
    if ts['status'] == 'running':
        return ('already', None)

    # 墙钟 paused → resume（把墙钟 pause_start 记入 total_paused，清掉 pause_start）
    if ts['status'] == 'paused':
        paused_dur = 0
        if ts['pause_start']:
            paused_dur = int((datetime.now() - datetime.fromisoformat(ts['pause_start'])).total_seconds())
        ts['total_paused'] = (ts.get('total_paused') or 0) + paused_dur
        ts['pause_start'] = None
        ts['status'] = 'running'
        db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)", (child_id, today))
        db.execute("UPDATE daily_records SET pause_count=? WHERE child_id=? AND date=?",
                   (ts['pause_count'], child_id, today))
        return ('auto_resume', None)

    # wall_status == 'idle' → 检查习惯倒计时是否在跑（互斥）
    habit_running = db.execute(
        "SELECT 1 FROM habit_records hr JOIN habits h ON hr.habit_id=h.id "
        "WHERE h.child_id=? AND hr.date=? AND hr.hb_start IS NOT NULL AND hr.hb_paused=0 LIMIT 1",
        (child_id, today)).fetchone()
    if habit_running:
        return ('habit_running', None)

    # 墙钟 idle → 自动 start
    ts['status'] = 'running'
    ts['start_time'] = when_iso
    ts['pause_start'] = None
    ts['total_paused'] = 0
    ts['pause_count'] = 0
    db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)", (child_id, today))
    db.execute("UPDATE daily_records SET start_time=?, pause_count=? WHERE child_id=? AND date=?",
               (ts['start_time'], 0, child_id, today))
    return ('auto_start', None)


def _maybe_auto_pause_wall(child_id, when_iso):
    """任务被 pause/stop 后：若没有任何任务在 running → 自动把墙钟置为 paused（暂停次数 +1）。
    返回: True 表示墙钟被自动 pause 了。"""
    ts = get_timer_state(child_id)
    if ts['status'] != 'running':
        return False
    db = get_db()
    today = date.today().isoformat()
    still_running = db.execute(
        "SELECT 1 FROM tasks WHERE child_id=? AND date=? AND tt_start IS NOT NULL AND tt_pause_start IS NULL LIMIT 1",
        (child_id, today)).fetchone()
    if still_running:
        return False
    # 自动 pause 墙钟
    ts['status'] = 'paused'
    ts['pause_start'] = when_iso
    ts['pause_count'] += 1
    db.execute("UPDATE daily_records SET pause_count=? WHERE child_id=? AND date=?",
               (ts['pause_count'], child_id, today))
    return True


def _suspend_wall_if_no_task_running(db, child_id, today, when_iso):
    """必做全完成时挂起墙钟：running → paused，但【不】增加休息次数。
    作业结束是检查点，不是休息；之后若做选做/新任务，墙钟自动恢复。"""
    ts = get_timer_state(child_id)
    if ts['status'] != 'running':
        return False
    still_running = db.execute(
        "SELECT 1 FROM tasks WHERE child_id=? AND date=? AND tt_start IS NOT NULL AND tt_pause_start IS NULL LIMIT 1",
        (child_id, today)).fetchone()
    if still_running:
        return False
    ts['status'] = 'paused'
    ts['pause_start'] = when_iso
    return True


def _link_auto_start_task(db, child_id, today, when_iso):
    """墙钟开始：若没有任何任务在计时，自动开启第一个未完成任务。"""
    running = db.execute(
        "SELECT 1 FROM tasks WHERE child_id=? AND date=? AND done=0 AND tt_start IS NOT NULL AND tt_pause_start IS NULL LIMIT 1",
        (child_id, today)).fetchone()
    if running:
        return
    nxt = db.execute(
        "SELECT id FROM tasks WHERE child_id=? AND date=? AND done=0 AND tt_start IS NULL "
        "ORDER BY sort_order, rowid LIMIT 1", (child_id, today)).fetchone()
    if nxt:
        db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                   (when_iso, nxt['id']))


def _link_pause_running_task(db, child_id, today, when_iso):
    """墙钟暂停：把正在运行的任务专注计时一起暂停。"""
    row = db.execute(
        "SELECT id, tt_start, tt_accum FROM tasks WHERE child_id=? AND date=? "
        "AND tt_start IS NOT NULL AND tt_pause_start IS NULL LIMIT 1",
        (child_id, today)).fetchone()
    if row:
        sess = int((datetime.now() - datetime.fromisoformat(row['tt_start'])).total_seconds())
        new_accum = (row['tt_accum'] or 0) + sess
        db.execute("UPDATE tasks SET tt_accum=?, tt_pause_start=?, tt_pause_count=COALESCE(tt_pause_count,0)+1 WHERE id=?",
                   (new_accum, when_iso, row['id']))
        db.execute("UPDATE daily_records SET pause_count=COALESCE(pause_count,0)+1 WHERE child_id=? AND date=?",
                   (child_id, today))


def _link_resume_paused_task(db, child_id, today, when_iso):
    """墙钟继续：恢复被墙钟暂停的任务。"""
    row = db.execute(
        "SELECT id FROM tasks WHERE child_id=? AND date=? AND tt_pause_start IS NOT NULL LIMIT 1",
        (child_id, today)).fetchone()
    if row:
        db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL WHERE id=?", (when_iso, row['id']))


def _link_settle_running_tasks(db, child_id, today):
    """墙钟结束：结算所有运行中任务的专注时长并清空窗口。"""
    rows = db.execute(
        "SELECT id, tt_start, tt_pause_start, tt_accum FROM tasks WHERE child_id=? AND date=? AND tt_start IS NOT NULL",
        (child_id, today)).fetchall()
    for r in rows:
        elapsed = _task_session_seconds(r)
        db.execute("UPDATE tasks SET duration_seconds=COALESCE(duration_seconds,0)+?, tt_start=NULL, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                   (elapsed, r['id']))


@app.route('/api/task/<task_id>/timer/start', methods=['POST'])
def api_task_timer_start(task_id):
    db = get_db()
    row = db.execute("SELECT tt_start, tt_pause_start, tt_accum, child_id, date FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        return jsonify({'error': '任务不存在'}), 404
    now = datetime.now().isoformat()
    child_id = row['child_id']
    today = row['date']

    # ① 互斥：若有其他任务正在 running → 自动暂停它（不再 409 拒绝）
    if not row['tt_start'] or row['tt_pause_start']:
        other = db.execute(
            "SELECT id, tt_start, tt_accum FROM tasks WHERE child_id=? AND date=? AND done=0 "
            "AND tt_start IS NOT NULL AND tt_pause_start IS NULL AND id!=? LIMIT 1",
            (child_id, today, task_id)).fetchone()
        if other:
            sess = int((datetime.now() - datetime.fromisoformat(other['tt_start'])).total_seconds())
            new_accum = (other['tt_accum'] or 0) + sess
            db.execute("UPDATE tasks SET tt_accum=?, tt_pause_start=?, tt_pause_count=COALESCE(tt_pause_count,0)+1 WHERE id=?",
                       (new_accum, now, other['id']))

    # ② 启动/恢复当前任务
    if row['tt_pause_start']:
        db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL WHERE id=?", (now, task_id))
    elif not row['tt_start']:
        db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                   (now, task_id))
    # 已在 running → 不动

    # ③ 墙钟联动：idle→auto start；paused→auto resume；若习惯倒计时在跑则拒绝
    wall_action, _ = _ensure_wall_running_if_idle(child_id, now)
    if wall_action == 'habit_running':
        # 回滚：把刚才启动的任务撤掉
        db.execute("UPDATE tasks SET tt_start=NULL, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?", (task_id,))
        # 刚才被我们自动 pause 的其他任务也要恢复
        db.execute("UPDATE tasks SET tt_start=?, tt_pause_start=NULL WHERE child_id=? AND date=? AND id!=? AND tt_pause_start=?",
                   (now, child_id, today, task_id, now))
        db.commit()
        return jsonify({'success': False, 'error': '习惯任务正在倒计时，请先暂停习惯再开始作业'}), 409

    db.commit()
    return jsonify({'success': True, 'running': True, 'paused': False, 'wall_action': wall_action})


@app.route('/api/task/<task_id>/timer/pause', methods=['POST'])
def api_task_timer_pause(task_id):
    db = get_db()
    row = db.execute("SELECT tt_start, tt_pause_start, tt_accum, child_id FROM tasks WHERE id=?",
                     (task_id,)).fetchone()
    if not row:
        return jsonify({'error': '任务不存在'}), 404
    paused = False
    wall_action = None
    if row['tt_start'] and not row['tt_pause_start']:
        now = datetime.now().isoformat()
        sess = int((datetime.now() - datetime.fromisoformat(row['tt_start'])).total_seconds())
        new_accum = (row['tt_accum'] or 0) + sess
        db.execute("UPDATE tasks SET tt_accum=?, tt_pause_start=?, tt_pause_count=COALESCE(tt_pause_count,0)+1 WHERE id=?",
                   (new_accum, now, task_id))
        # 注意：不再直接改 daily_records.pause_count，统一由 _maybe_auto_pause_wall 管
        paused = True
        # 墙钟联动：若没有任何任务在 running → 自动 pause 墙钟
        if _maybe_auto_pause_wall(row['child_id'], now):
            wall_action = 'auto_pause'
        db.commit()
    return jsonify({'success': True, 'paused': paused, 'wall_action': wall_action})


@app.route('/api/task/<task_id>/timer/stop', methods=['POST'])
def api_task_timer_stop(task_id):
    db = get_db()
    row = db.execute("SELECT tt_start, tt_pause_start, tt_accum, duration_seconds, child_id FROM tasks WHERE id=?",
                     (task_id,)).fetchone()
    if not row:
        return jsonify({'error': '任务不存在'}), 404
    elapsed = _task_session_seconds(row)
    wall_action = None
    if row['tt_start']:
        now = datetime.now().isoformat()
        db.execute("UPDATE tasks SET duration_seconds=COALESCE(duration_seconds,0)+?, tt_start=NULL, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
                   (elapsed, task_id))
        # 墙钟联动
        if _maybe_auto_pause_wall(row['child_id'], now):
            wall_action = 'auto_pause'
        db.commit()
    row2 = db.execute("SELECT duration_seconds FROM tasks WHERE id=?", (task_id,)).fetchone()
    return jsonify({'success': True, 'added': elapsed, 'total': row2['duration_seconds'] if row2 else 0, 'wall_action': wall_action})


@app.route('/api/task/<task_id>/timer/reset', methods=['POST'])
def api_task_timer_reset(task_id):
    db = get_db()
    db.execute("UPDATE tasks SET duration_seconds=0, tt_start=NULL, tt_pause_start=NULL, tt_accum=0, tt_pause_count=0 WHERE id=?",
               (task_id,))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/task/<task_id>', methods=['PUT'])
def api_update_task(task_id):
    data = request.json
    db = get_db()
    fields = []
    values = []
    if 'subject' in data:
        fields.append('subject=?')
        values.append(data['subject'])
    if 'desc' in data:
        fields.append('desc=?')
        values.append(data['desc'])
    if 'priority' in data:
        fields.append('priority=?')
        values.append(data['priority'])
    if fields:
        values.append(task_id)
        db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", values)
        db.commit()
    return jsonify({'success': True})


@app.route('/api/task/<task_id>/defer', methods=['POST'])
def api_defer_task(task_id):
    data = request.json
    days = data.get('days', 1)  # 延后几天
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t:
        return jsonify({'error': '任务不存在'}), 404
    # 计算新日期
    from datetime import timedelta
    current_date = datetime.strptime(t['date'], '%Y-%m-%d').date()
    new_date = current_date + timedelta(days=days)
    db.execute("UPDATE tasks SET date=? WHERE id=?", (new_date.isoformat(), task_id))
    db.commit()
    return jsonify({'success': True, 'new_date': new_date.isoformat()})


@app.route('/api/task/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM attachments WHERE task_id=?", (task_id,))
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    db.commit()
    return jsonify({'success': True})


# ============ API: 计时器 ============
@app.route('/api/timer/start', methods=['POST'])
def api_timer_start():
    child_id, err, code = require_child_id()
    if err: return err, code
    ts = get_timer_state(child_id)
    ts['status'] = 'running'
    ts['start_time'] = datetime.now().isoformat()
    ts['pause_start'] = None
    ts['total_paused'] = 0
    ts['pause_count'] = 0

    today = date.today().isoformat()
    db = get_db()
    db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)",
               (child_id, today))
    db.execute("UPDATE daily_records SET start_time=? WHERE child_id=? AND date=?",
               (ts['start_time'], child_id, today))
    # 联动：自动开启第一个未完成任务的专注计时
    _link_auto_start_task(db, child_id, today, ts['start_time'])
    db.commit()
    return jsonify({'success': True, 'timer': ts})


@app.route('/api/timer/pause', methods=['POST'])
def api_timer_pause():
    child_id, err, code = require_child_id()
    if err: return err, code
    ts = get_timer_state(child_id)
    today = date.today().isoformat()
    db = get_db()
    now_iso = datetime.now().isoformat()
    if ts['status'] == 'running':
        ts['status'] = 'paused'
        ts['pause_start'] = now_iso
        ts['pause_count'] += 1
        # 联动：暂停正在运行的任务专注计时
        _link_pause_running_task(db, child_id, today, now_iso)
    elif ts['status'] == 'paused':
        ts['status'] = 'running'
        if ts['pause_start']:
            paused_dur = (datetime.now() - datetime.fromisoformat(ts['pause_start'])).total_seconds()
            ts['total_paused'] += paused_dur
            ts['pause_start'] = None
        # 联动：恢复任务专注计时
        _link_resume_paused_task(db, child_id, today, now_iso)
    db.commit()
    return jsonify({'success': True, 'timer': ts})


@app.route('/api/timer/suspend', methods=['POST'])
def api_timer_suspend():
    """作业结束挂起墙钟：暂停但不增加休息次数（区别于手动暂停）。"""
    child_id, err, code = require_child_id()
    if err: return err, code
    ts = get_timer_state(child_id)
    now_iso = datetime.now().isoformat()
    if ts['status'] == 'running':
        ts['status'] = 'paused'
        ts['pause_start'] = now_iso
    return jsonify({'success': True, 'timer': ts})


@app.route('/api/timer/stop', methods=['POST'])
def api_timer_stop():
    child_id, err, code = require_child_id()
    if err: return err, code
    ts = get_timer_state(child_id)
    today = date.today().isoformat()

    elapsed = 0
    if ts['start_time']:
        if ts['pause_start']:
            # 暂停中停止，算到暂停开始时
            elapsed = int((datetime.fromisoformat(ts['pause_start']) - datetime.fromisoformat(ts['start_time'])).total_seconds() - ts['total_paused'])
        else:
            elapsed = int((datetime.now() - datetime.fromisoformat(ts['start_time'])).total_seconds() - ts['total_paused'])

    ts['status'] = 'done'
    db = get_db()
    # 联动：结束时结算所有运行中任务的专注时长
    _link_settle_running_tasks(db, child_id, today)
    db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)",
               (child_id, today))
    db.execute("""UPDATE daily_records
                  SET start_time=?, end_time=?, elapsed_seconds=?, pause_count=?
                  WHERE child_id=? AND date=?""",
               (ts['start_time'], datetime.now().isoformat(), elapsed,
                ts['pause_count'], child_id, today))
    db.commit()
    return jsonify({'success': True, 'elapsed': elapsed})


@app.route('/api/timer/reset', methods=['POST'])
def api_timer_reset():
    child_id, err, code = require_child_id()
    if err: return err, code
    timer_state[child_id] = {
        'status': 'idle', 'start_time': None, 'pause_start': None,
        'total_paused': 0, 'pause_count': 0, 'date': date.today().isoformat()
    }
    return jsonify({'success': True})


@app.route('/api/admin/reset-timer', methods=['POST'])
def api_admin_reset_timer():
    """家长按日重置计时。默认保留完成打勾/评价/积分；
    reset_done=true 时一并恢复所有任务为未完成（适用于"今天重新来过"场景）。"""
    if not session.get('admin_authed'):
        return jsonify({'error': '需要家长权限'}), 403
    data = request.json or {}
    child_id = data.get('child_id') or session.get('child_id')
    target = data.get('date') or date.today().isoformat()
    reset_done = data.get('reset_done', False)
    db = get_db()
    # 作业任务专注计时清零
    db.execute("""UPDATE tasks SET duration_seconds=0, tt_start=NULL, tt_pause_start=NULL,
                  tt_accum=0, tt_pause_count=0 WHERE child_id=? AND date=?""", (child_id, target))
    # 习惯倒计时窗口清零（保留 done/done_time）
    db.execute("""UPDATE habit_records SET hb_start=NULL, hb_pause_start=NULL, hb_paused=0,
                  hb_elapsed=0, hb_pause_count=0 WHERE child_id=? AND date=?""", (child_id, target))
    # 墙钟当日记录清零（保留 star/note/mood）；暂停次数 + 习惯暂停次数一并清
    db.execute("""UPDATE daily_records SET start_time=NULL, end_time=NULL,
                  elapsed_seconds=0, pause_count=0, habit_pause_count=0,
                  completed_at=NULL
                  WHERE child_id=? AND date=?""", (child_id, target))
    # 恢复未完成（可选）
    if reset_done:
        db.execute("UPDATE tasks SET done=0, done_time=NULL WHERE child_id=? AND date=?", (child_id, target))
    db.commit()
    # 内存墙钟复位
    timer_state[child_id] = {
        'status': 'idle', 'start_time': None, 'pause_start': None,
        'total_paused': 0, 'pause_count': 0, 'date': date.today().isoformat()
    }
    return jsonify({'success': True, 'date': target, 'child_id': child_id, 'reset_done': reset_done})


# ============ API: 习惯任务 ============
@app.route('/api/habit/<habit_id>/toggle', methods=['POST'])
def api_toggle_habit(habit_id):
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()
    existing = db.execute("SELECT done FROM habit_records WHERE child_id=? AND date=? AND habit_id=?",
                          (child_id, today, habit_id)).fetchone()
    if existing:
        new_done = 0 if existing['done'] else 1
        db.execute("""UPDATE habit_records SET done=?, done_time=?,
                      hb_start=NULL, hb_pause_start=NULL, hb_paused=0, hb_elapsed=0, hb_pause_count=0
                      WHERE child_id=? AND date=? AND habit_id=?""",
                   (new_done, datetime.now().isoformat() if new_done else None, child_id, today, habit_id))
    else:
        db.execute("INSERT INTO habit_records (child_id, date, habit_id, done, done_time) VALUES (?, ?, ?, 1, ?)",
                   (child_id, today, habit_id, datetime.now().isoformat()))
    db.commit()
    return jsonify({'success': True})


def _habit_live_elapsed(row):
    """习惯本轮已走秒（含暂停前累计）。"""
    base = row['hb_elapsed'] or 0
    if not row['hb_start'] or row['hb_paused']:
        return base
    try:
        return base + int((datetime.now() - datetime.fromisoformat(row['hb_start'])).total_seconds())
    except Exception:
        return base


@app.route('/api/habit/<habit_id>/timer/start', methods=['POST'])
def api_habit_timer_start(habit_id):
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()
    h = db.execute("SELECT minutes FROM habits WHERE id=? AND child_id=?", (habit_id, child_id)).fetchone()
    if not h or not h['minutes']:
        return jsonify({'success': False, 'error': '该习惯无需倒计时'}), 400
    rec = db.execute("SELECT done FROM habit_records WHERE child_id=? AND date=? AND habit_id=?",
                     (child_id, today, habit_id)).fetchone()
    if rec and rec['done']:
        return jsonify({'success': False, 'error': '今天已完成，无需重复开始'}), 400
    # 互斥：作业墙钟进行中
    ts = get_timer_state(child_id)
    if ts['status'] == 'running':
        return jsonify({'success': False, 'error': '作业计时进行中，请先暂停作业'}), 409
    # 互斥：其他习惯在计时（running 或已暂停都算占用）
    other = db.execute(
        "SELECT 1 FROM habit_records WHERE child_id=? AND date=? AND habit_id!=? "
        "AND hb_start IS NOT NULL AND done=0 LIMIT 1", (child_id, today, habit_id)).fetchone()
    if other:
        return jsonify({'success': False, 'error': '已有其他习惯在计时，请先暂停或完成'}), 409

    now = datetime.now().isoformat()
    db.execute("INSERT OR IGNORE INTO habit_records (child_id, date, habit_id, done) VALUES (?, ?, ?, 0)",
               (child_id, today, habit_id))
    row = db.execute("SELECT hb_paused FROM habit_records WHERE child_id=? AND date=? AND habit_id=?",
                     (child_id, today, habit_id)).fetchone()
    if row and row['hb_paused']:
        # 暂停态 → 恢复，保留已走秒
        db.execute("UPDATE habit_records SET hb_start=?, hb_paused=0, hb_pause_start=NULL "
                   "WHERE child_id=? AND date=? AND habit_id=?", (now, child_id, today, habit_id))
    else:
        db.execute("""UPDATE habit_records SET hb_start=?, hb_paused=0, hb_pause_start=NULL,
                      hb_elapsed=0, hb_pause_count=0 WHERE child_id=? AND date=? AND habit_id=?""",
                   (now, child_id, today, habit_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/habit/<habit_id>/timer/pause', methods=['POST'])
def api_habit_timer_pause(habit_id):
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()
    row = db.execute("SELECT hb_start, hb_paused, hb_elapsed FROM habit_records "
                     "WHERE child_id=? AND date=? AND habit_id=?", (child_id, today, habit_id)).fetchone()
    if not row or not row['hb_start']:
        return jsonify({'success': False, 'error': '未在计时'}), 400
    now = datetime.now()
    if not row['hb_paused']:
        sess = int((now - datetime.fromisoformat(row['hb_start'])).total_seconds())
        new_el = (row['hb_elapsed'] or 0) + sess
        db.execute("""UPDATE habit_records SET hb_elapsed=?, hb_paused=1, hb_pause_start=?,
                      hb_pause_count=COALESCE(hb_pause_count,0)+1 WHERE child_id=? AND date=? AND habit_id=?""",
                   (new_el, now.isoformat(), child_id, today, habit_id))
        db.execute("UPDATE daily_records SET habit_pause_count=habit_pause_count+1 WHERE child_id=? AND date=?",
                   (child_id, today))
    else:
        db.execute("UPDATE habit_records SET hb_start=?, hb_paused=0, hb_pause_start=NULL "
                   "WHERE child_id=? AND date=? AND habit_id=?", (now.isoformat(), child_id, today, habit_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/habit/<habit_id>/timer/stop', methods=['POST'])
def api_habit_timer_stop(habit_id):
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()
    db.execute("""UPDATE habit_records SET hb_start=NULL, hb_pause_start=NULL, hb_paused=0,
                  hb_elapsed=0, hb_pause_count=0 WHERE child_id=? AND date=? AND habit_id=?""",
               (child_id, today, habit_id))
    db.commit()
    return jsonify({'success': True})


@app.route('/api/habit/pause', methods=['POST'])
def api_habit_pause():
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today().isoformat()
    db = get_db()
    db.execute("UPDATE daily_records SET habit_pause_count = habit_pause_count + 1 WHERE child_id=? AND date=?",
               (child_id, today))
    db.commit()
    return jsonify({'success': True})


# ============ API: 家长评价 ============
@app.route('/api/admin/rate', methods=['POST'])
def api_admin_rate():
    child_id, err, code = require_child_id()
    if err: return err, code
    data = request.json
    today = date.today().isoformat()
    db = get_db()
    db.execute("INSERT OR IGNORE INTO daily_records (child_id, date) VALUES (?, ?)",
               (child_id, today))
    db.execute("""UPDATE daily_records SET star=?, note=?, mood=?
                  WHERE child_id=? AND date=?""",
               (data.get('star', 0), data.get('note', ''), data.get('mood', ''),
                child_id, today))
    # 更新每个任务评价
    for tid, rating in data.get('task_ratings', {}).items():
        db.execute("UPDATE tasks SET quality=?, errors=? WHERE id=?",
                   (rating.get('quality', 0), rating.get('errors', 0), tid))
    db.commit()
    return jsonify({'success': True})


# ============ API: 家长PIN码 ============
@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json
    if data.get('pin') == get_setting('pin'):
        session['admin_authed'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'PIN码错误'}), 401


# ============ API: 附件上传 ============
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@app.route('/api/attachment/upload', methods=['POST'])
def api_upload():
    task_id = request.form.get('task_id')
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': '没有文件'}), 400

    # 安全校验：task_id必须存在
    db = get_db()
    t = db.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t:
        return jsonify({'error': '任务不存在'}), 404

    type_map = {'.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.gif': 'image',
                '.mp4': 'video', '.webm': 'video',
                '.mp3': 'audio', '.wav': 'audio',
                '.pdf': 'pdf'}
    uploaded = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in type_map:
            continue  # 只允许已知类型

        # 文件大小限制
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > MAX_FILE_SIZE:
            return jsonify({'error': f'文件{file.filename}超过50MB限制'}), 400
        safe_name = f"{task_id}_{uuid.uuid4().hex[:8]}{ext}"
        # 防止路径遍历
        safe_name = os.path.basename(safe_name)
        filepath = os.path.join(ATTACH_DIR, safe_name)
        file.save(filepath)
        att_type = type_map[ext]
        # 填充空槽位或新增
        empty = db.execute("SELECT id FROM attachments WHERE task_id=? AND filename IS NULL LIMIT 1", (task_id,)).fetchone()
        if empty:
            db.execute("UPDATE attachments SET filename=?, type=? WHERE id=?", (safe_name, att_type, empty['id']))
        else:
            db.execute("INSERT INTO attachments (task_id, type, desc, filename) VALUES (?, ?, ?, ?)",
                       (task_id, att_type, file.filename, safe_name))
        uploaded.append(safe_name)
    db.commit()
    return jsonify({'success': True, 'uploaded': uploaded})


@app.route('/api/attachment/<filename>', methods=['DELETE'])
def api_delete_attachment(filename):
    filename = os.path.basename(filename)  # 防路径遍历
    db = get_db()
    db.execute("DELETE FROM attachments WHERE filename=?", (filename,))
    db.commit()
    filepath = os.path.join(ATTACH_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return jsonify({'success': True})


@app.route('/attachments/<path:filename>')
def serve_attachment(filename):
    # 安全：只从ATTACH_DIR提供文件
    return send_from_directory(ATTACH_DIR, os.path.basename(filename))


# ============ API: PDF批注 ============
@app.route('/api/pdf/annotations/<int:attachment_id>', methods=['GET'])
def api_get_annotations(attachment_id):
    db = get_db()
    rows = db.execute("SELECT page_num, strokes FROM pdf_annotations WHERE attachment_id=?", (attachment_id,)).fetchall()
    result = {}
    for r in rows:
        result[r['page_num']] = json.loads(r['strokes'])
    return jsonify({'annotations': result})


@app.route('/api/pdf/annotations/<int:attachment_id>', methods=['POST'])
def api_save_annotations(attachment_id):
    data = request.json
    page_num = data.get('page_num')
    strokes = data.get('strokes')
    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO pdf_annotations (attachment_id, page_num, strokes, updated_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
    """, (attachment_id, page_num, json.dumps(strokes)))
    db.commit()
    return jsonify({'success': True})


# ============ API: 历史记录 ============
@app.route('/api/history/<target_date>')
def api_history_day(target_date):
    child_id, err, code = require_child_id()
    if err: return err, code
    db = get_db()
    tasks = db.execute("SELECT * FROM tasks WHERE child_id=? AND date=? ORDER BY sort_order, rowid",
                       (child_id, target_date)).fetchall()
    task_list = []
    for t in tasks:
        attachments = db.execute("SELECT * FROM attachments WHERE task_id=?", (t['id'],)).fetchall()
        task_list.append({
            'id': t['id'], 'subject': t['subject'], 'desc': t['desc'],
            'priority': t['priority'], 'done': bool(t['done']),
            'quality': t['quality'], 'errors': t['errors'],
            'duration_seconds': t['duration_seconds'] or 0,
            'attachments': [dict(a) for a in attachments]
        })
    dr = db.execute("SELECT * FROM daily_records WHERE child_id=? AND date=?", (child_id, target_date)).fetchone()
    points, details = compute_points(child_id, target_date)
    # 优先展示账本里已结算的分数，未结算的日期才用实时计算值
    acc = db.execute("SELECT points FROM points_records WHERE child_id=? AND date=? AND type='daily'",
                     (child_id, target_date)).fetchone()
    return jsonify({
        'date': target_date,
        'tasks': task_list,
        'star': dr['star'] if dr else 0,
        'note': dr['note'] if dr else '',
        'mood': dr['mood'] if dr else '',
        'elapsed_seconds': dr['elapsed_seconds'] if dr else 0,
        'points': acc['points'] if acc else points,
        'live_points': points,
        'point_details': details,
        'suggested_time': dr['suggested_time'] if dr else ''
    })


@app.route('/api/history/calendar')
def api_history_calendar():
    child_id, err, code = require_child_id()
    if err: return err, code
    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)
    import calendar as cal_module
    cal = cal_module.monthcalendar(int(year), int(month))
    db = get_db()
    result = []
    for week in cal:
        for day in week:
            if day == 0:
                result.append(None)
                continue
            day_str = f"{year}-{int(month):02d}-{day:02d}"
            tasks = db.execute("SELECT * FROM tasks WHERE child_id=? AND date=?", (child_id, day_str)).fetchall()
            required = [t for t in tasks if t['priority'] == '必做']
            required_done = all(t['done'] for t in required) if required else False
            if not tasks:
                status = 'empty'
            elif required_done:
                status = 'complete'
            elif any(t['done'] for t in tasks):
                status = 'partial'
            else:
                status = 'pending'
            dr = db.execute("SELECT elapsed_seconds FROM daily_records WHERE child_id=? AND date=?",
                            (child_id, day_str)).fetchone()
            elapsed = dr['elapsed_seconds'] if dr else 0
            result.append({
                'day': day, 'date': day_str, 'status': status,
                'task_count': len(tasks), 'done_count': sum(1 for t in tasks if t['done']),
                'elapsed_seconds': elapsed
            })
    return jsonify({'days': result, 'year': year, 'month': month})


# ============ API: 积分 ============
@app.route('/api/points')
def api_points():
    child_id, err, code = require_child_id()
    if err: return err, code
    db = get_db()
    rows = db.execute("SELECT * FROM points_records WHERE child_id=? ORDER BY date DESC, id DESC LIMIT 200",
                      (child_id,)).fetchall()
    earned = db.execute("SELECT COALESCE(SUM(points),0) as s FROM points_records WHERE child_id=? AND points>0",
                        (child_id,)).fetchone()['s']
    spent = db.execute("SELECT COALESCE(-SUM(points),0) as s FROM points_records WHERE child_id=? AND points<0",
                       (child_id,)).fetchone()['s']
    return jsonify({
        'total': earned - spent,   # 当前可用余额
        'earned': earned,          # 累计获得
        'spent': spent,            # 累计已兑换
        'records': [dict(r) for r in rows]
    })


@app.route('/api/points/summary')
def api_points_summary():
    """按月份聚合积分，供历史页使用（避免逐日重算）"""
    child_id, err, code = require_child_id()
    if err: return err, code
    db = get_db()
    year = request.args.get('year')
    month = request.args.get('month')
    if year and month:
        prefix = f"{int(year):04d}-{int(month):02d}%"
        s = db.execute("SELECT COALESCE(SUM(points),0) as s FROM points_records WHERE child_id=? AND date LIKE ?",
                       (child_id, prefix)).fetchone()['s']
    else:
        s = db.execute("SELECT COALESCE(SUM(points),0) as s FROM points_records WHERE child_id=?",
                       (child_id,)).fetchone()['s']
    return jsonify({'total': s})


@app.route('/api/points/redeem', methods=['POST'])
def api_redeem():
    child_id, err, code = require_child_id()
    if err: return err, code
    data = request.json
    reward_id = data.get('reward_id')
    settings = get_all_settings()
    reward = next((r for r in settings['rewards'] if r['id'] == reward_id), None)
    if not reward:
        return jsonify({'error': '奖励不存在'}), 400
    db = get_db()
    total = db.execute("SELECT COALESCE(SUM(points),0) as s FROM points_records WHERE child_id=?", (child_id,)).fetchone()['s']
    if total < reward['points']:
        return jsonify({'error': f'积分不足，需要{reward["points"]}分'}), 400
    db.execute("INSERT INTO points_records (child_id, date, points, reason, detail, type) VALUES (?, ?, ?, ?, '', 'redeem')",
               (child_id, date.today().isoformat(), -reward['points'], f"兑换：{reward['name']}"))
    db.commit()
    new_total = db.execute("SELECT COALESCE(SUM(points),0) as s FROM points_records WHERE child_id=?", (child_id,)).fetchone()['s']
    return jsonify({'success': True, 'total': new_total})


# ============ API: 连续打卡 ============
@app.route('/api/streak')
def api_streak():
    child_id, err, code = require_child_id()
    if err: return err, code
    today = date.today()
    streak, _ = compute_streak(child_id, today.isoformat())
    # 今天还没完成时，不把连续天数清零，改为从昨天往回数
    if streak == 0:
        streak, _ = compute_streak(child_id, (today - timedelta(days=1)).isoformat())
    return jsonify({'streak': streak, 'next7': max(0, 7 - streak), 'next30': max(0, 30 - streak)})


# ============ API: 设置 ============
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify(get_all_settings())
    else:
        data = request.json
        db = get_db()
        for k, v in data.items():
            if k == 'rewards':
                continue
            set_setting(k, v)
        # 保存兑换奖励
        if 'rewards' in data:
            # 删除旧奖励
            db.execute("DELETE FROM settings WHERE key LIKE 'reward_%'")
            for r in data['rewards']:
                set_setting(f"reward_{r['id']}", json.dumps(r, ensure_ascii=False))
        db.commit()
        return jsonify({'success': True})


# ============ API: 习惯任务管理 ============
@app.route('/api/habits', methods=['GET', 'POST'])
def api_habits_manage():
    child_id, err, code = require_child_id()
    if err: return err, code
    db = get_db()
    if request.method == 'GET':
        rows = db.execute("SELECT * FROM habits WHERE child_id=?", (child_id,)).fetchall()
        return jsonify({'habits': [dict(r) for r in rows]})
    else:
        data = request.json
        # 简化：全量替换
        db.execute("DELETE FROM habits WHERE child_id=?", (child_id,))
        for h in data.get('habits', []):
            db.execute("INSERT INTO habits (id, child_id, name, minutes, days, enabled) VALUES (?, ?, ?, ?, ?, ?)",
                       (h.get('id', uuid.uuid4().hex[:8]), child_id, h['name'], h.get('minutes', 0),
                        h.get('days', 'all'), 1))
        db.commit()
        return jsonify({'success': True})


# ============ API: 错题库 ============
@app.route('/api/mistakes', methods=['GET', 'POST'])
def api_mistakes():
    child_id, err, code = require_child_id()
    if err: return err, code
    db = get_db()
    if request.method == 'GET':
        subject = request.args.get('subject', '')
        q = "SELECT * FROM mistakes WHERE child_id=?"
        args = [child_id]
        if subject:
            q += " AND subject=?"; args.append(subject)
        q += " ORDER BY mastered ASC, date DESC, id DESC"
        rows = db.execute(q, args).fetchall()
        today_str = date.today().isoformat()
        all_rows = db.execute("SELECT * FROM mistakes WHERE child_id=?", (child_id,)).fetchall()
        stats = {
            'total': len(all_rows),
            'mastered': sum(1 for r in all_rows if r['mastered']),
            'open': sum(1 for r in all_rows if not r['mastered']),
            'due': sum(1 for r in all_rows if not r['mastered'] and r['next_review'] and r['next_review'] <= today_str),
        }
        # 汇总所有科目用于筛选下拉
        subs = [r['subject'] for r in db.execute(
            "SELECT DISTINCT subject FROM mistakes WHERE child_id=? AND subject!=''", (child_id,)).fetchall()]
        return jsonify({'mistakes': [dict(r) for r in rows], 'subjects': subs, 'stats': stats})
    else:
        data = request.json
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        db.execute("""INSERT INTO mistakes (child_id, date, subject, content, mtype, note, image, retry_count, next_review)
                      VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                   (child_id,
                    data.get('date') or date.today().isoformat(),
                    data.get('subject', ''), data.get('content', '').strip(),
                    data.get('mtype', ''), data.get('note', ''),
                    data.get('image', ''), tomorrow))
        db.commit()
        return jsonify({'success': True})

@app.route('/api/mistakes/<int:mid>', methods=['PUT', 'DELETE'])
def api_mistake_edit(mid):
    db = get_db()
    if request.method == 'DELETE':
        db.execute("DELETE FROM mistakes WHERE id=?", (mid,))
        db.commit()
        return jsonify({'success': True})
    data = request.json
    fields, vals = [], []
    for k in ('subject', 'content', 'mtype', 'note', 'mastered', 'retry_count', 'next_review', 'image'):
        if k in data:
            fields.append(f"{k}=?"); vals.append(data[k])
    if fields:
        vals.append(mid)
        db.execute(f"UPDATE mistakes SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({'success': True})


@app.route('/api/mistake/upload', methods=['POST'])
def api_mistake_upload():
    file = request.files.get('image')
    if not file:
        return jsonify({'error': '没有文件'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.gif'):
        return jsonify({'error': '只支持 jpg/png/gif 图片'}), 400
    file.seek(0, 2); size = file.tell(); file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': '超过50MB限制'}), 400
    safe_name = f"mk_{uuid.uuid4().hex[:8]}{ext}"
    safe_name = os.path.basename(safe_name)
    file.save(os.path.join(ATTACH_DIR, safe_name))
    return jsonify({'success': True, 'image': safe_name})


# ============ 随手记：默认类型初始化 ============
_DEFAULT_NOTE_TYPES = [
    ('📝 灵感', '#4a90d9'),
    ('✅ 待办', '#4caf50'),
    ('💭 心情', '#e91e63'),
    ('📚 学习', '#ff9800'),
    ('⭐ 其他', '#9c27b0'),
]

def _ensure_default_note_types(child_id):
    db = get_db()
    cur = db.execute("SELECT COUNT(*) FROM note_types WHERE child_id=?", (child_id,)).fetchone()[0]
    if cur > 0:
        return
    for i, (name, color) in enumerate(_DEFAULT_NOTE_TYPES):
        tid = uuid.uuid4().hex[:8]
        db.execute("INSERT INTO note_types (id, child_id, name, icon, color, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                   (tid, child_id, name, name[:2], color, i))
    db.commit()


def _notes_child_id():
    """随手记专用：严格从 session 取 child_id，不允许 query 参数绕过"""
    cid = session.get('child_id')
    if not cid:
        return None
    return cid


def _require_notes_auth():
    """随手记守卫：未登录返回 (response, 401)"""
    cid = _notes_child_id()
    if cid is None:
        return cid, (jsonify({'error': '请先登录'}), 401)
    return cid, None


# ============ API: 随手记类型 ============
@app.route('/api/notes/types', methods=['GET', 'POST'])
def api_note_types():
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    _ensure_default_note_types(child_id)
    if request.method == 'POST':
        data = request.json
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': '类型名不能为空'}), 400
        tid = uuid.uuid4().hex[:8]
        db.execute("INSERT INTO note_types (id, child_id, name, icon, color, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
                   (tid, child_id, name, data.get('icon', '📝'),
                    data.get('color', '#4a90d9'),
                    data.get('sort_order', 99)))
        db.commit()
        return jsonify({'success': True, 'id': tid})
    # GET
    rows = db.execute("SELECT * FROM note_types WHERE child_id=? ORDER BY sort_order, id",
                      (child_id,)).fetchall()
    types = []
    for r in rows:
        cnt = db.execute("SELECT COUNT(*) as c FROM notes WHERE child_id=? AND type_id=?",
                         (child_id, r['id'])).fetchone()['c']
        types.append({'id': r['id'], 'name': r['name'], 'icon': r['icon'],
                      'color': r['color'], 'sort_order': r['sort_order'], 'count': cnt})
    return jsonify({'types': types})


@app.route('/api/notes/types/<tid>', methods=['PUT', 'DELETE'])
def api_note_type_edit(tid):
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    t = db.execute("SELECT * FROM note_types WHERE id=? AND child_id=?", (tid, child_id)).fetchone()
    if not t:
        return jsonify({'error': '类型不存在'}), 404
    if request.method == 'DELETE':
        cnt = db.execute("SELECT COUNT(*) FROM notes WHERE type_id=? AND child_id=?",
                         (tid, child_id)).fetchone()[0]
        if cnt > 0:
            return jsonify({'error': f'该类型下还有 {cnt} 条记录，请先移动或删除'}), 409
        db.execute("DELETE FROM note_types WHERE id=?", (tid,))
        db.commit()
        return jsonify({'success': True})
    # PUT
    data = request.json or {}
    fields, vals = [], []
    for k in ('name', 'icon', 'color', 'sort_order'):
        if k in data:
            fields.append(f"{k}=?"); vals.append(data[k])
    if fields:
        vals.append(tid)
        db.execute(f"UPDATE note_types SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({'success': True})


# ============ API: 随手记记录 ============
def _serialize_note(db, row):
    attachments = db.execute("SELECT * FROM note_attachments WHERE note_id=?", (row['id'],)).fetchall()
    return {
        'id': row['id'], 'child_id': row['child_id'],
        'type_id': row['type_id'], 'content': row['content'],
        'pinned': bool(row['pinned']), 'remind_at': row['remind_at'] or '',
        'remind_done': bool(row['remind_done']),
        'created_at': row['created_at'], 'updated_at': row['updated_at'],
        'attachments': [dict(a) for a in attachments],
    }


@app.route('/api/notes', methods=['GET', 'POST'])
def api_notes():
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    _ensure_default_note_types(child_id)
    if request.method == 'POST':
        data = request.json
        content = (data.get('content') or '').strip()
        type_id = data.get('type_id')
        if not content:
            return jsonify({'error': '内容不能为空'}), 400
        t = db.execute("SELECT id FROM note_types WHERE id=? AND child_id=?", (type_id, child_id)).fetchone()
        if not t:
            return jsonify({'error': '类型不存在'}), 400
        nid = uuid.uuid4().hex[:8]
        db.execute("""INSERT INTO notes (id, child_id, type_id, content, pinned, remind_at)
                      VALUES (?, ?, ?, ?, ?, ?)""",
                   (nid, child_id, type_id, content, int(bool(data.get('pinned'))),
                    (data.get('remind_at') or '')[:10]))
        db.commit()
        return jsonify({'success': True, 'id': nid})
    # GET
    type_id = request.args.get('type_id', '')
    q = (request.args.get('q') or '').strip()
    from_d = request.args.get('from', '')
    to_d = request.args.get('to', '')
    pinned_only = request.args.get('pinned') == '1'
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, max(1, int(request.args.get('per_page', 30))))

    args = [child_id]
    qs = ["n.child_id=?"]
    if type_id:
        qs.append("n.type_id=?"); args.append(type_id)
    if q:
        qs.append("n.content LIKE ?"); args.append(f"%{q}%")
    if from_d:
        qs.append("n.created_at >= ?"); args.append(from_d + "T00:00:00")
    if to_d:
        qs.append("n.created_at < ?"); args.append((to_d + "T23:59:59")[:32])
    if pinned_only:
        qs.append("n.pinned=1")

    where = " AND ".join(qs)
    # COUNT 走原表不 JOIN 更高效
    base_where = where.replace("n.", "")
    total = db.execute(f"SELECT COUNT(*) as c FROM notes WHERE {base_where}", args).fetchone()['c']
    rows = db.execute(f"""SELECT n.*, nt.name AS type_name, nt.icon AS type_icon, nt.color AS type_color
                          FROM notes n LEFT JOIN note_types nt ON nt.id = n.type_id
                          WHERE {where}
                          ORDER BY n.pinned DESC, n.created_at DESC
                          LIMIT ? OFFSET ?""", args + [per_page, (page - 1) * per_page]).fetchall()

    result = []
    for r in rows:
        note = _serialize_note(db, r)
        note['type_name'] = r['type_name'] or '未知'
        note['type_icon'] = r['type_icon'] or '📝'
        note['type_color'] = r['type_color'] or '#999'
        result.append(note)
    return jsonify({'notes': result, 'total': total, 'page': page, 'per_page': per_page})


@app.route('/api/notes/<nid>', methods=['GET', 'PUT', 'DELETE'])
def api_note_edit(nid):
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM notes WHERE id=? AND child_id=?", (nid, child_id)).fetchone()
    if not row:
        return jsonify({'error': '记录不存在'}), 404
    if request.method == 'DELETE':
        # 附件文件
        atts = db.execute("SELECT filename FROM note_attachments WHERE note_id=?", (nid,)).fetchall()
        db.execute("DELETE FROM note_attachments WHERE note_id=?", (nid,))
        db.execute("DELETE FROM notes WHERE id=?", (nid,))
        db.commit()
        for a in atts:
            try:
                os.remove(os.path.join(ATTACH_DIR, a['filename']))
            except Exception:
                pass
        return jsonify({'success': True})
    if request.method == 'GET':
        return jsonify(_serialize_note(db, row))
    # PUT
    data = request.json or {}
    fields, vals = [], []
    for k in ('content', 'type_id', 'remind_at', 'remind_done'):
        if k in data:
            fields.append(f"{k}=?"); vals.append(data[k])
    if 'pinned' in data:
        fields.append("pinned=?"); vals.append(int(bool(data['pinned'])))
    if fields:
        fields.append("updated_at=?"); vals.append(datetime.now().isoformat())
        vals.append(nid)
        db.execute(f"UPDATE notes SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({'success': True})


# ============ API: 随手记附件 ============
@app.route('/api/note/upload', methods=['POST'])
def api_note_upload():
    nid = request.form.get('note_id')
    if not nid:
        return jsonify({'error': '缺少 note_id'}), 400
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    n = db.execute("SELECT * FROM notes WHERE id=? AND child_id=?", (nid, child_id)).fetchone()
    if not n:
        return jsonify({'error': '记录不存在'}), 404
    file = request.files.get('file')
    if not file:
        return jsonify({'error': '没有文件'}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
    audio_exts = ('.webm', '.m4a', '.mp3', '.wav', '.ogg')
    if ext not in image_exts + audio_exts:
        return jsonify({'error': '仅支持图片(jpg/png/gif/webp)或音频(webm/m4a/mp3/wav/ogg)'}), 400
    file.seek(0, 2); size = file.tell(); file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': '超过50MB限制'}), 400
    safe_name = os.path.basename(f"note_{nid}_{uuid.uuid4().hex[:8]}{ext}")
    file.save(os.path.join(ATTACH_DIR, safe_name))
    atype = 'image' if ext in image_exts else 'audio'
    cur = db.execute("INSERT INTO note_attachments (note_id, type, filename) VALUES (?, ?, ?)",
                     (nid, atype, safe_name))
    db.commit()
    return jsonify({'success': True, 'attachment_id': cur.lastrowid, 'type': atype, 'filename': safe_name})


@app.route('/api/note/attachment/<int:aid>', methods=['DELETE'])
def api_note_att_del(aid):
    child_id, err = _require_notes_auth()
    if err: return err
    db = get_db()
    att = db.execute("SELECT na.*, n.child_id FROM note_attachments na "
                     "JOIN notes n ON n.id=na.note_id WHERE na.id=?", (aid,)).fetchone()
    if not att or att['child_id'] != child_id:
        return jsonify({'error': '附件不存在'}), 404
    db.execute("DELETE FROM note_attachments WHERE id=?", (aid,))
    db.commit()
    try:
        os.remove(os.path.join(ATTACH_DIR, att['filename']))
    except Exception:
        pass
    return jsonify({'success': True})


# ============ API: 随手记到期提醒 ============
@app.route('/api/notes/due')
def api_notes_due():
    child_id, err = _require_notes_auth()
    if err: return err
    today = date.today().isoformat()
    db = get_db()
    rows = db.execute("""SELECT n.*, nt.name AS type_name, nt.icon AS type_icon, nt.color AS type_color
                          FROM notes n LEFT JOIN note_types nt ON nt.id = n.type_id
                          WHERE n.child_id=? AND n.remind_at!=''
                          AND n.remind_at<=? AND n.remind_done=0
                          ORDER BY n.remind_at ASC, n.created_at DESC""",
                       (child_id, today)).fetchall()
    result = []
    for r in rows:
        n = _serialize_note(db, r)
        n['type_name'] = r['type_name'] or '未知'
        n['type_icon'] = r['type_icon'] or '📝'
        n['type_color'] = r['type_color'] or '#999'
        result.append(n)
    return jsonify({'items': result, 'count': len(result)})


# ============ API: 备份导出 ============
@app.route('/api/backup/export')
def api_backup_export():
    """手动导出：打包成 zip（data.json + attachments/）。
    with_attachments=0 可以只导 JSON；默认带附件并更新 last_full_backup 时间。
    每天保留一个，超过 30 天自动清理。"""
    with_attachments = request.args.get('with_attachments', '1') == '1'

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    data = _export_data_dict(db)
    db.close()

    tmp_dir = tempfile.mkdtemp(prefix='backup_')
    try:
        json_path = os.path.join(tmp_dir, 'data.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        today_str = date.today().isoformat()
        if with_attachments and os.path.isdir(ATTACH_DIR) and any(os.scandir(ATTACH_DIR)):
            # 带附件 → zip
            backup_file = os.path.join(BACKUP_DIR, f"backup_{today_str}.zip")
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(json_path, 'data.json')
                for root, dirs, files in os.walk(ATTACH_DIR):
                    for fname in files:
                        full = os.path.join(root, fname)
                        arc = os.path.relpath(full, ATTACH_DIR)
                        zf.write(full, os.path.join('attachments', arc))
            # 记录时间戳
            _update_full_backup_time()
            filename = f"作业任务清单_backup_full_{today_str}.zip"
        else:
            # 不带附件 → 纯 JSON
            backup_file = os.path.join(BACKUP_DIR, f"backup_{today_str}.json")
            with open(json_path, encoding='utf-8') as sf, open(backup_file, 'w', encoding='utf-8') as df:
                df.write(sf.read())
            filename = f"作业任务清单_backup_{today_str}.json"

        _cleanup_old_backups(30)
        return send_file(backup_file, as_attachment=True, download_name=filename)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _update_full_backup_time():
    """写入最近一次带附件的完整备份时间戳"""
    try:
        db = sqlite3.connect(DB_PATH)
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_full_backup', ?)",
                   (datetime.now().isoformat(),))
        db.commit()
        db.close()
    except Exception as e:
        print(f"写入 last_full_backup 失败: {e}")


@app.route('/api/backup/status')
def api_backup_status():
    """返回备份状态：上次完整带附件导出时间、距今天数、附件目录体积。"""
    last_iso = None
    days_since = None
    try:
        db = sqlite3.connect(DB_PATH)
        row = db.execute("SELECT value FROM settings WHERE key='last_full_backup'").fetchone()
        db.close()
        if row and row[0]:
            last_iso = row[0]
            try:
                last_dt = datetime.fromisoformat(last_iso)
                days_since = (datetime.now() - last_dt).days
            except Exception:
                days_since = None
    except Exception:
        pass

    attach_size_mb = 0
    try:
        if os.path.isdir(ATTACH_DIR):
            total = 0
            for root, _, files in os.walk(ATTACH_DIR):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            attach_size_mb = round(total / 1024 / 1024, 1)
    except Exception:
        pass

    return jsonify({
        'last_full_backup': last_iso,
        'days_since': days_since,
        'attachments_size_mb': attach_size_mb,
        'need_warning': days_since is not None and days_since >= 10
    })


# ============ API: 备份恢复 ============
@app.route('/api/backup/restore', methods=['POST'])
def api_backup_restore():
    """从上传的 JSON 或 zip 恢复。恢复前自动备份当前数据；zip 里有附件就一并写回。"""
    # admin 守卫
    if not session.get('is_admin'):
        return jsonify({'error': '需要管理员权限'}), 403

    file = request.files.get('file')
    if not file:
        return jsonify({'error': '未上传文件'}), 400

    tmp_dir = tempfile.mkdtemp(prefix='restore_')
    try:
        # 保存上传的文件
        upload_path = os.path.join(tmp_dir, file.filename or 'backup')
        file.save(upload_path)

        # 解析数据
        data = None
        attach_src = None
        if zipfile.is_zipfile(upload_path):
            with zipfile.ZipFile(upload_path) as zf:
                # 找 data.json
                json_members = [m for m in zf.namelist() if m.endswith('data.json')]
                if not json_members:
                    return jsonify({'error': 'zip 中未找到 data.json'}), 400
                data = json.loads(zf.read(json_members[0]))
                # 附件解压（zip 里 attachments/ 开头的文件）
                attach_members = [m for m in zf.namelist()
                                  if m.startswith('attachments/') and not m.endswith('/')]
                if attach_members:
                    attach_src = os.path.join(tmp_dir, 'attachments')
                    for m in attach_members:
                        target = os.path.join(tmp_dir, m)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(m) as sf, open(target, 'wb') as df:
                            shutil.copyfileobj(sf, df)
        else:
            # 纯 JSON
            try:
                with open(upload_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                return jsonify({'error': f'无法解析 JSON: {e}'}), 400

        if not isinstance(data, dict) or 'children' not in data:
            return jsonify({'error': '备份文件格式不合法'}), 400

        # 恢复前自动备份
        auto_backup()

        # 先确保 schema 完整（万一 DB 文件刚被重建）
        with app.app_context():
            init_db()

        # 事务写回所有表
        db = sqlite3.connect(DB_PATH)
        db.execute('PRAGMA foreign_keys = OFF')  # 恢复场景临时关外键
        try:
            db.execute('BEGIN')
            # 清库（清完再调 init_db 补默认习惯等种子数据）
            tables = ('attachments', 'app_data', 'daily_records', 'habit_records',
                      'note_attachments', 'notes', 'note_types', 'mistakes',
                      'points_records', 'tasks', 'habits', 'children', 'settings')
            for table in tables:
                db.execute(f'DELETE FROM {table}')

            def _insert(table, rows):
                for r in rows:
                    cols = ', '.join(r.keys())
                    qs = ', '.join(['?'] * len(r))
                    db.execute(f'INSERT INTO {table} ({cols}) VALUES ({qs})', list(r.values()))

            for table, key in (
                ('children', 'children'),
                ('tasks', 'tasks'),
                ('mistakes', 'mistakes'),
                ('note_types', 'note_types'),
                ('notes', 'notes'),
                ('note_attachments', 'note_attachments'),
                ('app_data', 'app_data'),
                ('daily_records', 'daily_records'),
                ('habits', 'habits'),
                ('habit_records', 'habit_records'),
                ('points_records', 'points_records'),
                ('attachments', 'attachments'),
            ):
                _insert(table, data.get(key, []))

            settings = data.get('settings', {})
            if isinstance(settings, dict):
                for k, v in settings.items():
                    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (k, v))

            # 旧备份没有 type 列，恢复后按正负分补齐分类
            db.execute("UPDATE points_records SET type='redeem' WHERE points<0 AND (type IS NULL OR type='daily')")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # 清库后补默认习惯等种子数据（备份里可能没有 habits）
        with app.app_context():
            init_db()

        # 写回附件（zip 里有的）
        if attach_src and os.path.isdir(attach_src):
            os.makedirs(ATTACH_DIR, exist_ok=True)
            for fname in os.listdir(attach_src):
                shutil.copy2(os.path.join(attach_src, fname), os.path.join(ATTACH_DIR, fname))

        _cleanup_old_backups(30)
        return jsonify({
            'success': True,
            'children': len(data.get('children', [])),
            'tasks': len(data.get('tasks', [])),
            'notes': len(data.get('notes', [])),
            'app_data': len(data.get('app_data', [])),
            'daily_records': len(data.get('daily_records', []))
        })
    except Exception as e:
        return jsonify({'error': f'恢复失败: {e}'}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============ 启动 ============
if __name__ == '__main__':
    import sys
    init_db()
    db = sqlite3.connect(DB_PATH)
    port_row = db.execute("SELECT value FROM settings WHERE key='port'").fetchone()
    port = int(port_row[0]) if port_row else 8000
    # 命令行临时指定端口：仅本次进程生效，不写 settings
    if '--port' in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index('--port') + 1])
        except (ValueError, IndexError):
            pass
    db.close()

    local_ip = get_lan_ip()
    print("=" * 50)
    print("  作业任务清单系统 (SQLite版)")
    print("=" * 50)
    print(f"  本机访问:   http://127.0.0.1:{port}")
    if local_ip:
        print(f"  局域网访问: http://{local_ip}:{port}")
        print("  其他手机/平板连同一Wi-Fi，扫码或输入上面地址即可")
    else:
        print("  未检测到局域网地址（仅本机可访问）")
    print("  按 Ctrl+C 关闭服务；数据已保存在本机，关闭不丢失")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)
