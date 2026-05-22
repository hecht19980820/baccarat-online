# main.py
# 百家樂 AI 系統：後台科技版 + 玩家簡易版
# 新增：代理、刪除玩家、週/月統計、清除此桌只清畫面、撤回、大路盤左上往下、DG/MT分開、手動牌型輸入

from flask import Flask, request, redirect, session, jsonify, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uuid
from datetime import datetime, timedelta

DB_PATH = "baccarat_system.db"
APP_SECRET = "CHANGE_THIS_TO_RANDOM_SECRET"
ADMIN_INIT_USER = "admin"
ADMIN_INIT_PASSWORD = "admin123"

app = Flask(__name__)
app.secret_key = APP_SECRET

# -----------------------------
# DB
# -----------------------------
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def safe_add_column(cur, table, column_sql):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
    except Exception:
        pass


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player',
        status TEXT NOT NULL DEFAULT 'active',
        expire_at TEXT,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        player_limit INTEGER DEFAULT 0
    )
    """)
    safe_add_column(cur, "users", "created_by INTEGER")
    safe_add_column(cur, "users", "player_limit INTEGER DEFAULT 0")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        table_id TEXT NOT NULL,
        result TEXT NOT NULL,
        prediction TEXT,
        confidence INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        is_bet INTEGER DEFAULT 0,
        player_cards TEXT,
        banker_cards TEXT,
        created_at TEXT NOT NULL
    )
    """)
    safe_add_column(cur, "records", "is_bet INTEGER DEFAULT 0")
    safe_add_column(cur, "records", "player_cards TEXT")
    safe_add_column(cur, "records", "banker_cards TEXT")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS table_clears(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        table_id TEXT NOT NULL,
        last_record_id INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT 'unused',
        bind_user_id INTEGER,
        expire_days INTEGER NOT NULL DEFAULT 30,
        created_at TEXT NOT NULL,
        used_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_user TEXT,
        action TEXT,
        ip TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("SELECT id FROM users WHERE username=?", (ADMIN_INIT_USER,))
    if not cur.fetchone():
        cur.execute("""
        INSERT INTO users(username,password_hash,role,status,expire_at,created_at,created_by,player_limit)
        VALUES(?,?,?,?,?,?,?,?)
        """, (ADMIN_INIT_USER, generate_password_hash(ADMIN_INIT_PASSWORD), "admin", "active", None, now(), None, 0))

    conn.commit()
    conn.close()


def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user


def require_login():
    user = current_user()
    if not user:
        return None
    if user["status"] != "active":
        session.clear()
        return None
    if user["role"] == "player" and user["expire_at"]:
        try:
            if datetime.strptime(user["expire_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
                session.clear()
                return None
        except Exception:
            pass
    return user


def require_admin():
    user = require_login()
    if not user or user["role"] != "admin":
        return None
    return user


def log_action(action):
    conn = db()
    conn.execute("INSERT INTO admin_logs(admin_user,action,ip,created_at) VALUES(?,?,?,?)",
                 (session.get("username", "system"), action, request.remote_addr, now()))
    conn.commit()
    conn.close()

# -----------------------------
# Baccarat helpers
# -----------------------------
def card_value(x):
    x = str(x).strip().upper()
    if x in ["J", "Q", "K", "10"]:
        return 0
    try:
        return int(x) % 10
    except Exception:
        return 0


def parse_cards(text):
    # 支援：0.2.8.0 / 0,2,8,0 / 0 2 8 0
    text = (text or "").replace("，", ".").replace(",", ".").replace(" ", ".")
    return [x for x in text.split(".") if x != ""]


def baccarat_point(text):
    cards = parse_cards(text)
    return sum(card_value(x) for x in cards) % 10


def result_from_cards(player_cards, banker_cards):
    p = baccarat_point(player_cards)
    b = baccarat_point(banker_cards)
    if p > b:
        return "閒"
    if b > p:
        return "莊"
    return "和"


def latest_clear_id(user_id, table_id):
    conn = db()
    row = conn.execute("""
        SELECT last_record_id FROM table_clears
        WHERE user_id=? AND table_id=?
        ORDER BY id DESC LIMIT 1
    """, (user_id, str(table_id))).fetchone()
    conn.close()
    return row["last_record_id"] if row else 0


def visible_records(user_id, table_id, limit=128):
    clear_id = latest_clear_id(user_id, table_id)
    conn = db()
    rows = conn.execute("""
        SELECT * FROM records
        WHERE table_id=? AND id>?
        ORDER BY id DESC LIMIT ?
    """, (str(table_id), clear_id, limit)).fetchall()
    conn.close()
    return list(reversed(rows))


def build_big_road_columns(records, max_rows=6):
    # 左上開始，往下排；換路往右
    cols = []
    current_col = []
    last = None
    for r in records:
        res = r["result"] if isinstance(r, sqlite3.Row) else r.get("result")
        if res == "和":
            # 和局放同欄，不改路；沒有欄位則開一欄
            if not current_col:
                current_col = [res]
            else:
                current_col.append(res)
            continue
        if last is None:
            current_col = [res]
            last = res
        elif res == last and len(current_col) < max_rows:
            current_col.append(res)
        else:
            cols.append(current_col)
            current_col = [res]
            last = res
    if current_col:
        cols.append(current_col)
    return cols


def period_condition(period):
    if period == "today":
        return "date(created_at)=date('now','localtime')"
    if period == "week":
        return "strftime('%Y-%W', created_at)=strftime('%Y-%W','now','localtime')"
    if period == "month":
        return "strftime('%Y-%m', created_at)=strftime('%Y-%m','now','localtime')"
    return "1=1"


def calc_stats(user_id=None, table_id=None, period="all"):
    # 統計只算 is_bet=1；手動大路盤不算下注次數、不算勝率
    wheres = [period_condition(period), "is_bet=1"]
    params = []
    if user_id:
        wheres.append("user_id=?")
        params.append(user_id)
    if table_id:
        wheres.append("table_id=?")
        params.append(str(table_id))
    where_sql = " AND ".join(wheres)
    conn = db()
    row = conn.execute(f"""
        SELECT COUNT(*) total,
               SUM(CASE WHEN correct=1 THEN 1 ELSE 0 END) correct_count,
               SUM(CASE WHEN result='莊' THEN 1 ELSE 0 END) banker_count,
               SUM(CASE WHEN result='閒' THEN 1 ELSE 0 END) player_count,
               SUM(CASE WHEN result='和' THEN 1 ELSE 0 END) tie_count
        FROM records WHERE {where_sql}
    """, params).fetchone()
    conn.close()
    total = row["total"] or 0
    correct = row["correct_count"] or 0
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "banker": row["banker_count"] or 0,
        "player": row["player_count"] or 0,
        "tie": row["tie_count"] or 0,
    }


def table_road_counts(table_id):
    conn = db()
    row = conn.execute("""
        SELECT SUM(CASE WHEN result='莊' THEN 1 ELSE 0 END) banker_count,
               SUM(CASE WHEN result='閒' THEN 1 ELSE 0 END) player_count,
               SUM(CASE WHEN result='和' THEN 1 ELSE 0 END) tie_count
        FROM records WHERE table_id=?
    """, (str(table_id),)).fetchone()
    conn.close()
    return {"banker": row["banker_count"] or 0, "player": row["player_count"] or 0, "tie": row["tie_count"] or 0}


def simple_predict(table_id):
    conn = db()
    rows = conn.execute("SELECT result FROM records WHERE table_id=? ORDER BY id DESC LIMIT 40", (str(table_id),)).fetchall()
    conn.close()
    road = [r["result"] for r in rows][::-1]
    road = [x for x in road if x in ["莊", "閒"]]
    if len(road) < 8:
        return "觀察", 50, "資料不足，建議先觀察"
    banker = road.count("莊")
    player = road.count("閒")
    last = road[-1]
    streak = 1
    for x in reversed(road[:-1]):
        if x == last:
            streak += 1
        else:
            break
    if streak >= 3:
        return last, min(80, 58 + streak * 5), f"目前 {last} 連 {streak}"
    pred = "莊" if banker >= player else "閒"
    return pred, min(72, 55 + abs(banker - player) * 2), "依大路與近期比例"

# -----------------------------
# UI
# -----------------------------
STYLE = """
<style>
*{box-sizing:border-box}body{margin:0;background:#050b16;color:#e8fbff;font-family:Arial,'Microsoft JhengHei',sans-serif}a{text-decoration:none;color:inherit}.wrap{display:flex;min-height:100vh}.side{width:245px;background:linear-gradient(180deg,#07152d,#020713);border-right:1px solid #0b9ccc;padding:20px}.brand{font-size:22px;font-weight:900;margin-bottom:25px;color:#fff;text-shadow:0 0 14px #00d9ff}.nav a{display:block;padding:14px 16px;margin:9px 0;border:1px solid #12446b;border-radius:14px;background:#071a32}.nav a:hover,.active{background:#073e70!important;box-shadow:0 0 16px rgba(0,225,255,.45)}.main{flex:1;padding:22px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.title{font-size:30px;font-weight:900}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.panel{display:grid;grid-template-columns:2fr 1fr;gap:16px}.card{background:linear-gradient(180deg,#071a32,#030d1d);border:1px solid #0e89c2;border-radius:18px;padding:18px;box-shadow:0 0 22px rgba(0,180,255,.14)}.big{font-size:34px;font-weight:900;color:#83fbff}.green{color:#34ff98}.red{color:#ff4d73}.yellow{color:#ffd84d}.sub{color:#8bcfe5;font-size:13px}.btn{display:inline-block;border:1px solid #00d8ff;background:#062b4d;color:#e8fbff;padding:10px 14px;border-radius:12px;cursor:pointer;margin:3px}.btn:hover{box-shadow:0 0 14px #00d8ff}.btn-danger{border-color:#ff4d73;background:#45101f}input,select{width:100%;padding:11px;border-radius:12px;border:1px solid #0e89c2;background:#020914;color:#e8fbff}table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid #123b63;text-align:left;font-size:14px}.ball{width:31px;height:31px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900}.b{border:2px solid #ff4d73;color:#ff7f99}.p{border:2px solid #1ba0ff;color:#62c6ff}.t{border:2px solid #34ff98;color:#34ff98}.login{max-width:430px;margin:100px auto}.footer-note{margin-top:12px;color:#82a9bd;font-size:13px}@media(max-width:900px){.wrap{display:block}.side{width:auto}.grid,.grid3,.panel{grid-template-columns:1fr}.main{padding:14px}.title{font-size:24px}.card{padding:15px}table{font-size:12px}}
</style>
"""

LOGIN_HTML = STYLE + """
<div class='login card'>
  <div class='brand'>百家樂 AI 系統</div>
  <form method='post'>
    <p>帳號</p><input name='username' required>
    <p>密碼</p><input name='password' type='password' required>
    <br><br><button class='btn' style='width:100%'>登入系統</button>
  </form>
  <div class='footer-note'>系統登入驗證</div>
</div>
"""

PLAYER_HTML = STYLE + """
<style>
.player-simple{max-width:980px;margin:0 auto;padding:18px}.simple-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.simple-title{font-size:24px;font-weight:800}.simple-box{background:#071a32;border:1px solid #0e89c2;border-radius:14px;padding:14px;margin-bottom:12px}.simple-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.simple-big{font-size:34px;font-weight:900}.road-board{min-height:230px;background:#020914;border:1px solid #0e89c2;border-radius:12px;padding:10px;display:flex;align-items:flex-start;gap:6px;overflow-x:auto}.road-col{display:flex;flex-direction:column;gap:6px}.simple-actions{display:flex;gap:8px;flex-wrap:wrap}.simple-actions .btn{min-width:80px}.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.three{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.small-note{color:#8bcfe5;font-size:13px}@media(max-width:800px){.simple-grid,.two,.three{grid-template-columns:1fr}.simple-top{display:block}.player-simple{padding:12px}.simple-big{font-size:28px}}
</style>
<div class='player-simple'>
  <div class='simple-top'>
    <div class='simple-title'>百家樂玩家頁面</div>
    <div>玩家：{{user.username}} <a class='btn' href='/logout'>登出</a>{% if user.role == 'admin' %}<a class='btn' href='/admin'>後台</a>{% endif %}{% if user.role == 'agent' %}<a class='btn' href='/agent'>代理中心</a>{% endif %}</div>
  </div>

  <div class='simple-grid'>
    <div class='simple-box'><div>本週下注</div><div class='simple-big'>{{week.total}}</div><div class='sub'>勝率 {{week.accuracy}}%</div></div>
    <div class='simple-box'><div>本月下注</div><div class='simple-big'>{{month.total}}</div><div class='sub'>勝率 {{month.accuracy}}%</div></div>
    <div class='simple-box'><div>AI 建議</div><div class='simple-big green'>{{prediction}}</div><div class='sub'>信心度 {{confidence}}%｜{{reason}}</div></div>
  </div>

  <div class='simple-box'>
    <h3>桌台選擇</h3>
    <form method='get' class='three'>
      <select name='platform' onchange='this.form.submit()'>
        <option value='DG' {% if platform=='DG' %}selected{% endif %}>DG</option>
        <option value='MT' {% if platform=='MT' %}selected{% endif %}>MT</option>
      </select>
      <select name='table_no' onchange='this.form.submit()'>
        {% for i in range(1,21) %}<option value='{{i}}' {% if table_no==i|string %}selected{% endif %}>桌號 {{i}}</option>{% endfor %}
      </select>
      <div class='small-note'>目前：{{table_id}}</div>
    </form>
  </div>

  <div class='simple-box'>
    <h3>大路盤</h3>
    <div class='road-board'>
      {% for col in road_cols %}
        <div class='road-col'>
          {% for r in col %}<div class='ball {% if r=='莊' %}b{% elif r=='閒' %}p{% else %}t{% endif %}'>{{r}}</div>{% endfor %}
        </div>
      {% endfor %}
    </div>
    <br>
    <form class='simple-actions' method='post' action='/add_record'>
      <input type='hidden' name='table_id' value='{{table_id}}'>
      <input type='hidden' name='is_bet' value='0'>
      <button name='result' value='莊' class='btn btn-danger'>加入莊</button>
      <button name='result' value='閒' class='btn'>加入閒</button>
      <button name='result' value='和' class='btn'>加入和</button>
      <a class='btn' href='/undo_record?table_id={{table_id}}'>撤回</a>
      <a class='btn' href='/clear_table?table_id={{table_id}}'>清除此桌</a>
    </form>
  </div>

  <div class='simple-box'>
    <h3>手動輸入牌型</h3>
    <form method='post' action='/add_cards'>
      <input type='hidden' name='table_id' value='{{table_id}}'>
      <div class='two'>
        <div><p>閒牌，例如：0.8</p><input name='player_cards' placeholder='0.8'></div>
        <div><p>莊牌，例如：2.0</p><input name='banker_cards' placeholder='2.0'></div>
      </div>
      <br>
      <button class='btn'>依牌型加入大路盤</button>
      <span class='small-note'>例如閒 0.8、莊 2.0，結果會自動判斷為閒。可輸入 0.2.8.0 這種格式。</span>
    </form>
  </div>

  <div class='simple-box'>
    <h3>本桌統計</h3>
    <p>今日下注：{{today.total}} 次｜勝率 {{today.accuracy}}%</p>
    <p>本週下注：{{week_table.total}} 次｜勝率 {{week_table.accuracy}}%</p>
    <p>本月下注：{{month_table.total}} 次｜勝率 {{month_table.accuracy}}%</p>
    <p>大路莊：{{table_road.banker}}　大路閒：{{table_road.player}}　和：{{table_road.tie}}</p>
  </div>
</div>
"""

ADMIN_HTML = STYLE + """
<div class='wrap'>
  <div class='side'><div class='brand'>AI ADMIN</div><div class='nav'><a class='active' href='/admin'>儀表板</a><a href='/admin/users'>玩家/代理管理</a><a href='/admin/licenses'>序號管理</a><a href='/'>玩家頁面</a><a href='/logout'>登出</a></div></div>
  <div class='main'>
    <div class='top'><div class='title'>後台數據中心</div><div>{{time}}</div></div>
    <div class='grid'>
      <div class='card'><div>今日下注</div><div class='big'>{{today.total}}</div><div class='sub'>勝率 {{today.accuracy}}%</div></div>
      <div class='card'><div>本週下注</div><div class='big'>{{week.total}}</div><div class='sub'>勝率 {{week.accuracy}}%</div></div>
      <div class='card'><div>本月下注</div><div class='big'>{{month.total}}</div><div class='sub'>勝率 {{month.accuracy}}%</div></div>
      <div class='card'><div>總下注</div><div class='big yellow'>{{alltime.total}}</div><div class='sub'>總勝率 {{alltime.accuracy}}%</div></div>
    </div><br>
    <div class='grid'><div class='card'><div>總玩家</div><div class='big'>{{sys.total_users}}</div></div><div class='card'><div>啟用玩家</div><div class='big green'>{{sys.active_users}}</div></div><div class='card'><div>資料庫</div><div class='big green'>OK</div></div><div class='card'><div>清除保護</div><div class='big green'>ON</div></div></div><br>
    <div class='card'><h3>玩家週/月勝率排行</h3><table><tr><th>玩家</th><th>週次數</th><th>週勝率</th><th>月次數</th><th>月勝率</th><th>狀態</th></tr>{% for r in ranking %}<tr><td>{{r.username}}</td><td>{{r.week_total}}</td><td>{{r.week_acc}}%</td><td>{{r.month_total}}</td><td>{{r.month_acc}}%</td><td>{{r.status}}</td></tr>{% endfor %}</table></div><br>
    <div class='card'><h3>後台日誌</h3><table><tr><th>時間</th><th>管理者</th><th>動作</th><th>IP</th></tr>{% for l in logs %}<tr><td>{{l.created_at}}</td><td>{{l.admin_user}}</td><td>{{l.action}}</td><td>{{l.ip}}</td></tr>{% endfor %}</table></div>
  </div>
</div>
"""

USERS_HTML = STYLE + """
<div class='wrap'><div class='side'><div class='brand'>PLAYERS</div><div class='nav'><a href='/admin'>儀表板</a><a class='active' href='/admin/users'>玩家/代理管理</a><a href='/admin/licenses'>序號管理</a><a href='/logout'>登出</a></div></div>
<div class='main'><div class='top'><div class='title'>玩家/代理管理</div></div>
<div class='card'><h3>新增玩家 / 代理</h3><form method='post' action='/admin/users/create'><div class='grid'><input name='username' placeholder='帳號' required><input name='password' placeholder='密碼' required><input name='days' placeholder='天數' value='30'><select name='role'><option value='player'>玩家</option><option value='agent'>代理</option></select></div><br><div class='grid'><input name='player_limit' placeholder='代理可開玩家數，玩家填0' value='0'><button class='btn'>新增帳號</button></div></form></div><br>
<div class='card'><table><tr><th>ID</th><th>帳號</th><th>角色</th><th>狀態</th><th>到期</th><th>代理上限</th><th>已開玩家</th><th>週下注</th><th>週勝率</th><th>月下注</th><th>月勝率</th><th>操作</th></tr>{% for u in users %}<tr><td>{{u.id}}</td><td>{{u.username}}</td><td>{{u.role}}</td><td>{{u.status}}</td><td>{{u.expire_at or '-'}}</td><td>{{u.player_limit}}</td><td>{{u.created_count}}</td><td>{{u.week_total}}</td><td>{{u.week_acc}}%</td><td>{{u.month_total}}</td><td>{{u.month_acc}}%</td><td>{% if u.role!='admin' %}<a class='btn' href='/admin/users/toggle/{{u.id}}'>啟用/停用</a><a class='btn btn-danger' onclick="return confirm('確定刪除這個會員？')" href='/admin/users/delete/{{u.id}}'>刪除</a>{% endif %}</td></tr>{% endfor %}</table></div>
</div></div>
"""

AGENT_HTML = STYLE + """
<div class='wrap'><div class='side'><div class='brand'>AGENT</div><div class='nav'><a href='/'>玩家頁面</a><a class='active' href='/agent'>代理中心</a><a href='/logout'>登出</a></div></div>
<div class='main'><div class='top'><div class='title'>代理中心</div><div>代理：{{user.username}}</div></div>
<div class='grid3'><div class='card'><div>可開玩家上限</div><div class='big'>{{limit}}</div></div><div class='card'><div>已開玩家</div><div class='big yellow'>{{used}}</div></div><div class='card'><div>剩餘名額</div><div class='big green'>{{remain}}</div></div></div><br>
<div class='card'><h3>新增線下玩家</h3><form method='post' action='/agent/users/create'><div class='grid'><input name='username' placeholder='玩家帳號' required><input name='password' placeholder='玩家密碼' required><input name='days' placeholder='天數' value='30'><button class='btn'>新增玩家</button></div></form></div><br>
<div class='card'><h3>我的玩家</h3><table><tr><th>ID</th><th>帳號</th><th>狀態</th><th>到期</th><th>週下注</th><th>週勝率</th><th>月下注</th><th>月勝率</th><th>操作</th></tr>{% for u in users %}<tr><td>{{u.id}}</td><td>{{u.username}}</td><td>{{u.status}}</td><td>{{u.expire_at or '-'}}</td><td>{{u.week_total}}</td><td>{{u.week_acc}}%</td><td>{{u.month_total}}</td><td>{{u.month_acc}}%</td><td><a class='btn' href='/agent/users/toggle/{{u.id}}'>啟用/停用</a></td></tr>{% endfor %}</table></div>
</div></div>
"""

LICENSE_HTML = STYLE + """
<div class='wrap'><div class='side'><div class='brand'>LICENSE</div><div class='nav'><a href='/admin'>儀表板</a><a href='/admin/users'>玩家/代理管理</a><a class='active' href='/admin/licenses'>序號管理</a><a href='/logout'>登出</a></div></div>
<div class='main'><div class='top'><div class='title'>序號管理</div></div>
<div class='card'><form method='post' action='/admin/licenses/create'><div class='grid'><input name='count' value='5' placeholder='產生數量'><input name='days' value='30' placeholder='天數'><button class='btn'>產生序號</button></div></form></div><br>
<div class='card'><table><tr><th>序號</th><th>狀態</th><th>天數</th><th>綁定玩家</th><th>建立時間</th></tr>{% for x in licenses %}<tr><td>{{x.license_key}}</td><td>{{x.status}}</td><td>{{x.expire_days}}</td><td>{{x.bind_user_id or '-'}}</td><td>{{x.created_at}}</td></tr>{% endfor %}</table></div>
</div></div>
"""

# -----------------------------
# Routes
# -----------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password) and user['status'] == 'active':
            session['user_id'] = user['id']
            session['username'] = user['username']
            if user['role'] == 'admin':
                return redirect('/admin')
            if user['role'] == 'agent':
                return redirect('/agent')
            return redirect('/')
    return render_template_string(LOGIN_HTML)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


def split_table_id(table_id):
    if '-' in str(table_id):
        a, b = str(table_id).split('-', 1)
        return a, b
    return 'DG', str(table_id)


@app.route('/')
def player_home():
    user = require_login()
    if not user:
        return redirect('/login')
    platform = request.args.get('platform')
    table_no = request.args.get('table_no')
    table_id = request.args.get('table_id')
    if not table_id:
        platform = platform or 'DG'
        table_no = table_no or '1'
        table_id = f"{platform}-{table_no}"
    else:
        platform, table_no = split_table_id(table_id)

    records = visible_records(user['id'], table_id, 128)
    road_cols = build_big_road_columns(records)
    table_road = table_road_counts(table_id)
    today = calc_stats(user_id=user['id'], table_id=table_id, period='today')
    week = calc_stats(user_id=user['id'], period='week')
    month = calc_stats(user_id=user['id'], period='month')
    week_table = calc_stats(user_id=user['id'], table_id=table_id, period='week')
    month_table = calc_stats(user_id=user['id'], table_id=table_id, period='month')
    prediction, confidence, reason = simple_predict(table_id)

    return render_template_string(PLAYER_HTML, user=user, table_id=table_id, platform=platform, table_no=table_no,
        records=records, road_cols=road_cols, table_road=table_road,
        today=today, week=week, month=month, week_table=week_table, month_table=month_table,
        prediction=prediction, confidence=confidence, reason=reason)


@app.route('/add_record', methods=['POST'])
def add_record():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.form['table_id']
    result = request.form['result']
    is_bet = int(request.form.get('is_bet', 0))
    pred, conf, _ = simple_predict(table_id)
    correct = 1 if is_bet == 1 and pred == result else 0
    conn = db()
    conn.execute("""
        INSERT INTO records(user_id,table_id,result,prediction,confidence,correct,is_bet,created_at)
        VALUES(?,?,?,?,?,?,?,?)
    """, (user['id'], table_id, result, pred, conf, correct, is_bet, now()))
    conn.commit()
    conn.close()
    return redirect('/?table_id=' + str(table_id))


@app.route('/add_cards', methods=['POST'])
def add_cards():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.form['table_id']
    player_cards = request.form.get('player_cards', '')
    banker_cards = request.form.get('banker_cards', '')
    result = result_from_cards(player_cards, banker_cards)
    pred, conf, _ = simple_predict(table_id)
    conn = db()
    conn.execute("""
        INSERT INTO records(user_id,table_id,result,prediction,confidence,correct,is_bet,player_cards,banker_cards,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (user['id'], table_id, result, pred, conf, 0, 0, player_cards, banker_cards, now()))
    conn.commit()
    conn.close()
    return redirect('/?table_id=' + str(table_id))


@app.route('/clear_table')
def clear_table():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.args.get('table_id', 'DG-1')
    conn = db()
    last = conn.execute("SELECT MAX(id) m FROM records WHERE table_id=?", (str(table_id),)).fetchone()['m'] or 0
    conn.execute("INSERT INTO table_clears(user_id,table_id,last_record_id,created_at) VALUES(?,?,?,?)",
                 (user['id'], str(table_id), last, now()))
    conn.commit()
    conn.close()
    return redirect('/?table_id=' + str(table_id))


@app.route('/undo_record')
def undo_record():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.args.get('table_id', 'DG-1')
    clear_id = latest_clear_id(user['id'], table_id)
    conn = db()
    last = conn.execute("SELECT id FROM records WHERE table_id=? AND id>? ORDER BY id DESC LIMIT 1", (str(table_id), clear_id)).fetchone()
    if last:
        conn.execute("DELETE FROM records WHERE id=?", (last['id'],))
        conn.commit()
    conn.close()
    return redirect('/?table_id=' + str(table_id))


@app.route('/admin')
def admin_home():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) c FROM users WHERE role='player'").fetchone()['c']
    active_users = conn.execute("SELECT COUNT(*) c FROM users WHERE role='player' AND status='active'").fetchone()['c']
    logs = conn.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 10").fetchall()
    ranking = conn.execute("""
        SELECT u.id,u.username,u.status,
        COUNT(CASE WHEN r.is_bet=1 AND strftime('%Y-%W', r.created_at)=strftime('%Y-%W','now','localtime') THEN r.id END) week_total,
        ROUND(SUM(CASE WHEN r.is_bet=1 AND strftime('%Y-%W', r.created_at)=strftime('%Y-%W','now','localtime') AND r.correct=1 THEN 1 ELSE 0 END)*100.0/
            MAX(1,COUNT(CASE WHEN r.is_bet=1 AND strftime('%Y-%W', r.created_at)=strftime('%Y-%W','now','localtime') THEN r.id END)),1) week_acc,
        COUNT(CASE WHEN r.is_bet=1 AND strftime('%Y-%m', r.created_at)=strftime('%Y-%m','now','localtime') THEN r.id END) month_total,
        ROUND(SUM(CASE WHEN r.is_bet=1 AND strftime('%Y-%m', r.created_at)=strftime('%Y-%m','now','localtime') AND r.correct=1 THEN 1 ELSE 0 END)*100.0/
            MAX(1,COUNT(CASE WHEN r.is_bet=1 AND strftime('%Y-%m', r.created_at)=strftime('%Y-%m','now','localtime') THEN r.id END)),1) month_acc
        FROM users u LEFT JOIN records r ON u.id=r.user_id
        WHERE u.role='player'
        GROUP BY u.id ORDER BY month_acc DESC, month_total DESC LIMIT 12
    """).fetchall()
    conn.close()
    sys = {"total_users": total_users, "active_users": active_users}
    return render_template_string(ADMIN_HTML, user=user, time=now(), sys=sys,
        today=calc_stats(period='today'), week=calc_stats(period='week'), month=calc_stats(period='month'), alltime=calc_stats(),
        ranking=ranking, logs=logs)


@app.route('/admin/users')
def admin_users():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    rows = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    conn.close()
    users = []
    for u in rows:
        week = calc_stats(user_id=u['id'], period='week')
        month = calc_stats(user_id=u['id'], period='month')
        d = dict(u)
        conn2 = db()
        d['created_count'] = conn2.execute("SELECT COUNT(*) c FROM users WHERE created_by=? AND role='player'", (u['id'],)).fetchone()['c']
        conn2.close()
        d['week_total'] = week['total']; d['week_acc'] = week['accuracy']; d['month_total'] = month['total']; d['month_acc'] = month['accuracy']
        users.append(d)
    return render_template_string(USERS_HTML, users=users)


@app.route('/admin/users/create', methods=['POST'])
def admin_users_create():
    user = require_admin()
    if not user:
        return redirect('/login')
    username = request.form['username'].strip(); password = request.form['password'].strip()
    days = int(request.form.get('days', 30)); role = request.form.get('role', 'player')
    if role not in ['player', 'agent']:
        role = 'player'
    player_limit = int(request.form.get('player_limit', 0)) if role == 'agent' else 0
    expire_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    try:
        conn.execute("INSERT INTO users(username,password_hash,role,status,expire_at,created_at,created_by,player_limit) VALUES(?,?,?,?,?,?,?,?)",
            (username, generate_password_hash(password), role, 'active', expire_at, now(), user['id'], player_limit))
        conn.commit(); log_action(f"新增{role} {username} 上限 {player_limit}")
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect('/admin/users')


@app.route('/admin/users/toggle/<int:user_id>')
def admin_users_toggle(user_id):
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db(); target = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if target and target['role'] != 'admin':
        new_status = 'disabled' if target['status'] == 'active' else 'active'
        conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, user_id)); conn.commit(); log_action(f"切換帳號 {target['username']} 狀態為 {new_status}")
    conn.close(); return redirect('/admin/users')


@app.route('/admin/users/delete/<int:user_id>')
def admin_users_delete(user_id):
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db(); target = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if target and target['role'] != 'admin':
        conn.execute("DELETE FROM users WHERE id=?", (user_id,)); conn.commit(); log_action(f"刪除帳號 {target['username']}")
    conn.close(); return redirect('/admin/users')


@app.route('/agent')
def agent_home():
    user = require_login()
    if not user or user['role'] != 'agent':
        return redirect('/login')
    conn = db()
    rows = conn.execute("SELECT * FROM users WHERE created_by=? AND role='player' ORDER BY id DESC", (user['id'],)).fetchall()
    used = conn.execute("SELECT COUNT(*) c FROM users WHERE created_by=? AND role='player'", (user['id'],)).fetchone()['c']
    conn.close()
    users = []
    for u in rows:
        week = calc_stats(user_id=u['id'], period='week'); month = calc_stats(user_id=u['id'], period='month')
        d = dict(u); d['week_total'] = week['total']; d['week_acc'] = week['accuracy']; d['month_total'] = month['total']; d['month_acc'] = month['accuracy']; users.append(d)
    limit = user['player_limit'] or 0
    return render_template_string(AGENT_HTML, user=user, users=users, limit=limit, used=used, remain=max(0, limit-used))


@app.route('/agent/users/create', methods=['POST'])
def agent_users_create():
    user = require_login()
    if not user or user['role'] != 'agent':
        return redirect('/login')
    conn = db(); used = conn.execute("SELECT COUNT(*) c FROM users WHERE created_by=? AND role='player'", (user['id'],)).fetchone()['c']; limit = user['player_limit'] or 0
    if used >= limit:
        conn.close(); return redirect('/agent')
    username = request.form['username'].strip(); password = request.form['password'].strip(); days = int(request.form.get('days', 30))
    expire_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute("INSERT INTO users(username,password_hash,role,status,expire_at,created_at,created_by,player_limit) VALUES(?,?,?,?,?,?,?,?)",
            (username, generate_password_hash(password), 'player', 'active', expire_at, now(), user['id'], 0))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close(); return redirect('/agent')


@app.route('/agent/users/toggle/<int:user_id>')
def agent_users_toggle(user_id):
    user = require_login()
    if not user or user['role'] != 'agent':
        return redirect('/login')
    conn = db(); target = conn.execute("SELECT * FROM users WHERE id=? AND created_by=? AND role='player'", (user_id, user['id'])).fetchone()
    if target:
        new_status = 'disabled' if target['status'] == 'active' else 'active'
        conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, user_id)); conn.commit()
    conn.close(); return redirect('/agent')


@app.route('/admin/licenses')
def admin_licenses():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db(); licenses = conn.execute("SELECT * FROM licenses ORDER BY id DESC LIMIT 100").fetchall(); conn.close()
    return render_template_string(LICENSE_HTML, licenses=licenses)


@app.route('/admin/licenses/create', methods=['POST'])
def admin_licenses_create():
    user = require_admin()
    if not user:
        return redirect('/login')
    count = int(request.form.get('count', 1)); days = int(request.form.get('days', 30)); conn = db()
    for _ in range(count):
        key = 'VIP-' + datetime.now().strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:8].upper()
        conn.execute("INSERT INTO licenses(license_key,status,expire_days,created_at) VALUES(?,?,?,?)", (key, 'unused', days, now()))
    conn.commit(); conn.close(); log_action(f"產生 {count} 組序號")
    return redirect('/admin/licenses')


@app.route('/api/stats')
def api_stats():
    user = require_login()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify({'today': calc_stats(period='today'), 'week': calc_stats(period='week'), 'month': calc_stats(period='month'), 'all': calc_stats(), 'time': now(), 'status': 'ok'})


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
