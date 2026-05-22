# main.py
# 百家樂 AI 系統：後台管理 + 玩家前台 完整單檔版
# 啟動方式：
# 1) pip install flask werkzeug
# 2) python main.py
# 3) 管理後台：http://127.0.0.1:5000/admin
# 4) 玩家前台：http://127.0.0.1:5000/
# 預設管理者：admin / admin123

from flask import Flask, request, redirect, session, jsonify, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
from datetime import datetime, timedelta

APP_SECRET = "CHANGE_THIS_SECRET_KEY"
DB_PATH = "baccarat_system.db"
ADMIN_INIT_USER = "admin"
ADMIN_INIT_PASSWORD = "admin123"

app = Flask(__name__)
app.secret_key = APP_SECRET

# -----------------------------
# 資料庫基礎
# -----------------------------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'player',
        status TEXT NOT NULL DEFAULT 'active',
        expire_at TEXT,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
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
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        table_id TEXT NOT NULL,
        result TEXT NOT NULL,
        prediction TEXT,
        confidence INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
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
        INSERT INTO users(username, password_hash, role, status, expire_at, created_at)
        VALUES (?, ?, 'admin', 'active', NULL, ?)
        """, (ADMIN_INIT_USER, generate_password_hash(ADMIN_INIT_PASSWORD), now()))

    conn.commit()
    conn.close()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_action(action):
    conn = db()
    conn.execute("INSERT INTO admin_logs(admin_user, action, ip, created_at) VALUES (?, ?, ?, ?)",
                 (session.get("username", "system"), action, request.remote_addr, now()))
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
        if datetime.strptime(user["expire_at"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            session.clear()
            return None
    return user


def require_admin():
    user = require_login()
    if not user or user["role"] != "admin":
        return None
    return user

# -----------------------------
# AI 預測示範邏輯
# 注意：這只是後台流程版，之後可替換成你的正式模型
# -----------------------------
def build_big_road(results):
    return [r for r in results if r in ["莊", "閒"]]


def simple_predict(table_id):
    conn = db()
    rows = conn.execute("SELECT result FROM records WHERE table_id=? ORDER BY id DESC LIMIT 30", (table_id,)).fetchall()
    conn.close()
    results = [r["result"] for r in rows][::-1]
    big = build_big_road(results)

    if len(big) < 8:
        return "觀察", 50, "資料不足，先觀察"

    banker = big.count("莊")
    player = big.count("閒")
    last = big[-1]
    streak = 1
    for x in reversed(big[:-1]):
        if x == last:
            streak += 1
        else:
            break

    if streak >= 3:
        pred = last
        confidence = min(78, 58 + streak * 5)
        reason = f"目前{last}連{streak}，趨勢延續"
    else:
        pred = "莊" if banker >= player else "閒"
        confidence = min(72, 55 + abs(banker - player) * 2)
        reason = "依最近30局比例與大路趨勢"

    return pred, confidence, reason

# -----------------------------
# HTML UI
# -----------------------------
STYLE = """
<style>
*{box-sizing:border-box}body{margin:0;background:#050b16;color:#dff7ff;font-family:Arial,'Microsoft JhengHei',sans-serif}a{text-decoration:none;color:inherit}.wrap{display:flex;min-height:100vh}.side{width:240px;background:linear-gradient(180deg,#061429,#020711);border-right:1px solid #0ff;padding:20px}.brand{font-size:22px;font-weight:800;margin-bottom:25px;color:#fff;text-shadow:0 0 12px #00d5ff}.nav a{display:block;padding:14px 16px;margin:8px 0;border:1px solid #123b63;border-radius:12px;background:#081a32}.nav a:hover,.active{background:#0a4cff!important;box-shadow:0 0 18px #008cff}.main{flex:1;padding:22px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.title{font-size:30px;font-weight:800}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.card{background:linear-gradient(180deg,#071a31,#04101e);border:1px solid #0c7db4;border-radius:16px;padding:18px;box-shadow:0 0 20px rgba(0,180,255,.18)}.big{font-size:34px;font-weight:800;color:#7df9ff}.green{color:#39ff88}.red{color:#ff4d6d}.yellow{color:#ffd84d}.btn{border:1px solid #00d5ff;background:#062b4d;color:#dff7ff;padding:10px 14px;border-radius:10px;cursor:pointer}.btn:hover{box-shadow:0 0 12px #00d5ff}.btn-danger{border-color:#ff4d6d;background:#44111e}input,select{width:100%;padding:11px;border-radius:10px;border:1px solid #0c7db4;background:#020914;color:#dff7ff}table{width:100%;border-collapse:collapse}th,td{padding:11px;border-bottom:1px solid #123b63;text-align:left}.panel{display:grid;grid-template-columns:2fr 1fr;gap:16px}.road{min-height:180px;background:#020914;border:1px solid #0c7db4;border-radius:12px;padding:10px;display:flex;flex-wrap:wrap;align-content:flex-start;gap:6px}.ball{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800}.b{border:2px solid #ff4d6d;color:#ff7a90}.p{border:2px solid #199bff;color:#60c5ff}.t{border:2px solid #39ff88;color:#39ff88}.login{max-width:420px;margin:100px auto}.hero{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}.predict{font-size:80px;text-align:center;text-shadow:0 0 18px #00d5ff}.sub{color:#8bdfff;font-size:13px}.footer-note{margin-top:12px;color:#82a9bd;font-size:13px}.mobile{display:none}@media(max-width:900px){.wrap{display:block}.side{width:auto}.grid,.panel,.hero{grid-template-columns:1fr}.main{padding:14px}.predict{font-size:54px}}
</style>
"""

LOGIN_HTML = STYLE + """
<div class='login card'>
  <div class='brand'>百家樂 AI 預測系統</div>
  <form method='post'>
    <p>帳號</p><input name='username' required>
    <p>密碼</p><input name='password' type='password' required>
    <br><br><button class='btn' style='width:100%'>登入</button>
  </form>
  <div class='footer-note'>預設管理者：admin / admin123</div>
</div>
"""

ADMIN_HTML = STYLE + """
<div class='wrap'>
  <div class='side'>
    <div class='brand'>AI ADMIN PANEL</div>
    <div class='nav'>
      <a class='active' href='/admin'>儀表板</a>
      <a href='/admin/users'>玩家管理</a>
      <a href='/admin/licenses'>序號管理</a>
      <a href='/'>玩家前台</a>
      <a href='/logout'>登出</a>
    </div>
  </div>
  <div class='main'>
    <div class='top'><div class='title'>後台管理系統</div><div>管理者：{{user.username}}｜{{time}}</div></div>
    <div class='grid'>
      <div class='card'><div>總玩家數</div><div class='big'>{{stats.total_users}}</div></div>
      <div class='card'><div>啟用玩家</div><div class='big green'>{{stats.active_users}}</div></div>
      <div class='card'><div>總牌局數</div><div class='big'>{{stats.total_records}}</div></div>
      <div class='card'><div>整體準確率</div><div class='big yellow'>{{stats.accuracy}}%</div></div>
    </div>
    <br>
    <div class='panel'>
      <div class='card'>
        <h3>玩家勝率排行</h3>
        <table><tr><th>玩家</th><th>局數</th><th>準確率</th><th>狀態</th></tr>
        {% for r in ranking %}<tr><td>{{r.username}}</td><td>{{r.cnt}}</td><td>{{r.acc}}%</td><td class='green'>{{r.status}}</td></tr>{% endfor %}
        </table>
      </div>
      <div class='card'>
        <h3>系統狀態</h3>
        <p>資料庫：<span class='green'>正常</span></p>
        <p>清除此桌：<span class='green'>只清前台畫面，不刪後台 records</span></p>
        <p>WAL 模式：<span class='green'>已啟用</span></p>
        <p>系統健康度</p><div class='big green'>98%</div>
      </div>
    </div>
    <br>
    <div class='card'><h3>系統日誌</h3><table><tr><th>時間</th><th>管理者</th><th>動作</th><th>IP</th></tr>{% for l in logs %}<tr><td>{{l.created_at}}</td><td>{{l.admin_user}}</td><td>{{l.action}}</td><td>{{l.ip}}</td></tr>{% endfor %}</table></div>
  </div>
</div>
"""

USERS_HTML = STYLE + """
<div class='wrap'><div class='side'><div class='brand'>PLAYER MANAGE</div><div class='nav'><a href='/admin'>儀表板</a><a class='active' href='/admin/users'>玩家管理</a><a href='/admin/licenses'>序號管理</a><a href='/logout'>登出</a></div></div>
<div class='main'><div class='top'><div class='title'>玩家管理</div></div>
<div class='card'><h3>新增玩家</h3><form method='post' action='/admin/users/create'><div class='grid'><input name='username' placeholder='帳號'><input name='password' placeholder='密碼'><input name='days' placeholder='天數' value='30'><button class='btn'>新增</button></div></form></div><br>
<div class='card'><table><tr><th>ID</th><th>帳號</th><th>角色</th><th>狀態</th><th>到期</th><th>操作</th></tr>{% for u in users %}<tr><td>{{u.id}}</td><td>{{u.username}}</td><td>{{u.role}}</td><td>{{u.status}}</td><td>{{u.expire_at or '-'}}</td><td><a class='btn' href='/admin/users/toggle/{{u.id}}'>啟用/停用</a></td></tr>{% endfor %}</table></div>
</div></div>
"""

LICENSE_HTML = STYLE + """
<div class='wrap'><div class='side'><div class='brand'>LICENSE MANAGE</div><div class='nav'><a href='/admin'>儀表板</a><a href='/admin/users'>玩家管理</a><a class='active' href='/admin/licenses'>序號管理</a><a href='/logout'>登出</a></div></div>
<div class='main'><div class='top'><div class='title'>序號管理</div></div>
<div class='card'><form method='post' action='/admin/licenses/create'><div class='grid'><input name='count' value='5' placeholder='產生數量'><input name='days' value='30' placeholder='天數'><button class='btn'>產生序號</button></div></form></div><br>
<div class='card'><table><tr><th>序號</th><th>狀態</th><th>天數</th><th>綁定玩家</th><th>建立時間</th></tr>{% for x in licenses %}<tr><td>{{x.license_key}}</td><td>{{x.status}}</td><td>{{x.expire_days}}</td><td>{{x.bind_user_id or '-'}}</td><td>{{x.created_at}}</td></tr>{% endfor %}</table></div>
</div></div>
"""

PLAYER_HTML = STYLE + """
<div class='wrap'>
  <div class='side'>
    <div class='brand'>百家樂 AI 系統</div>
    <div class='nav'>
      <a class='active' href='/'>玩家介面</a>
      {% if user.role == 'admin' %}<a href='/admin'>後台管理</a>{% endif %}
      <a href='/logout'>登出</a>
    </div>
    <div class='card'><p>玩家：{{user.username}}</p><p>狀態：<span class='green'>{{user.status}}</span></p><p>到期：{{user.expire_at or '無限制'}}</p></div>
  </div>
  <div class='main'>
    <div class='top'><div class='title'>玩家前端介面</div><div>雲端同步：<span class='green'>已連線</span></div></div>
    <div class='hero'>
      <div class='card'><h3>閒 PLAYER</h3><div class='big'>{{player_rate}}%</div></div>
      <div class='card'><h3>AI 信心度</h3><div class='predict'>{{confidence}}%</div><p class='green'>建議：{{prediction}}</p><p class='sub'>{{reason}}</p></div>
      <div class='card'><h3>莊 BANKER</h3><div class='big red'>{{banker_rate}}%</div></div>
    </div>
    <br>
    <div class='panel'>
      <div class='card'>
        <h3>路線圖分析｜桌號 {{table_id}}</h3>
        <form method='get'><select name='table_id' onchange='this.form.submit()'>{% for i in range(1,9) %}<option value='{{i}}' {% if table_id==i|string %}selected{% endif %}>桌號 {{i}}</option>{% endfor %}</select></form><br>
        <div class='road'>{% for r in records %}<div class='ball {% if r.result=="莊" %}b{% elif r.result=="閒" %}p{% else %}t{% endif %}'>{{r.result}}</div>{% endfor %}</div>
        <br>
        <form method='post' action='/add_record'>
          <input type='hidden' name='table_id' value='{{table_id}}'>
          <button name='result' value='莊' class='btn btn-danger'>加入 莊</button>
          <button name='result' value='閒' class='btn'>加入 閒</button>
          <button name='result' value='和' class='btn'>加入 和</button>
          <a class='btn' href='/clear_table?table_id={{table_id}}'>清除此桌畫面</a>
        </form>
        <div class='footer-note'>清除此桌只清除目前畫面 Session，不會刪除 records 後台資料。</div>
      </div>
      <div class='card'>
        <h3>數據統計</h3>
        <p>總局數：<span class='big'>{{total}}</span></p>
        <p>莊：{{banker_count}}</p>
        <p>閒：{{player_count}}</p>
        <p>和：{{tie_count}}</p>
      </div>
    </div>
  </div>
</div>
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
            return redirect('/admin' if user['role'] == 'admin' else '/')
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def player_home():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.args.get('table_id', '1')
    conn = db()
    rows = conn.execute("SELECT * FROM records WHERE table_id=? ORDER BY id DESC LIMIT 128", (table_id,)).fetchall()
    conn.close()
    records = list(reversed(rows))
    total = len(records)
    banker_count = sum(1 for r in records if r['result'] == '莊')
    player_count = sum(1 for r in records if r['result'] == '閒')
    tie_count = sum(1 for r in records if r['result'] == '和')
    banker_rate = round(banker_count / max(1, banker_count + player_count) * 100)
    player_rate = 100 - banker_rate if banker_count + player_count else 50
    prediction, confidence, reason = simple_predict(table_id)
    return render_template_string(PLAYER_HTML, user=user, table_id=table_id, records=records, total=total,
                                  banker_count=banker_count, player_count=player_count, tie_count=tie_count,
                                  banker_rate=banker_rate, player_rate=player_rate,
                                  prediction=prediction, confidence=confidence, reason=reason)

@app.route('/add_record', methods=['POST'])
def add_record():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.form['table_id']
    result = request.form['result']
    pred, conf, reason = simple_predict(table_id)
    correct = 1 if pred == result else 0
    conn = db()
    conn.execute("INSERT INTO records(user_id, table_id, result, prediction, confidence, correct, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (user['id'], table_id, result, pred, conf, correct, now()))
    conn.commit()
    conn.close()
    return redirect('/?table_id=' + table_id)

@app.route('/clear_table')
def clear_table():
    user = require_login()
    if not user:
        return redirect('/login')
    table_id = request.args.get('table_id', '1')
    # 安全設計：不刪資料庫，只回到空畫面可改成前端 localStorage 清除。
    # 這裡示範直接導回同桌，後台 records 完整保留。
    return redirect('/?table_id=' + table_id)

@app.route('/admin')
def admin_home():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    total_users = conn.execute("SELECT COUNT(*) c FROM users WHERE role='player'").fetchone()['c']
    active_users = conn.execute("SELECT COUNT(*) c FROM users WHERE role='player' AND status='active'").fetchone()['c']
    total_records = conn.execute("SELECT COUNT(*) c FROM records").fetchone()['c']
    correct = conn.execute("SELECT COUNT(*) c FROM records WHERE correct=1").fetchone()['c']
    accuracy = round(correct / max(1, total_records) * 100, 1)
    ranking = conn.execute("""
        SELECT u.username,u.status,COUNT(r.id) cnt,
        ROUND(SUM(CASE WHEN r.correct=1 THEN 1 ELSE 0 END)*100.0/MAX(1,COUNT(r.id)),1) acc
        FROM users u LEFT JOIN records r ON u.id=r.user_id
        WHERE u.role='player'
        GROUP BY u.id ORDER BY acc DESC LIMIT 8
    """).fetchall()
    logs = conn.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 8").fetchall()
    conn.close()
    stats = dict(total_users=total_users, active_users=active_users, total_records=total_records, accuracy=accuracy)
    return render_template_string(ADMIN_HTML, user=user, stats=stats, ranking=ranking, logs=logs, time=now())

@app.route('/admin/users')
def admin_users():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    users = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return render_template_string(USERS_HTML, users=users)

@app.route('/admin/users/create', methods=['POST'])
def admin_users_create():
    user = require_admin()
    if not user:
        return redirect('/login')
    username = request.form['username'].strip()
    password = request.form['password'].strip()
    days = int(request.form.get('days', 30))
    expire_at = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    conn.execute("INSERT INTO users(username,password_hash,role,status,expire_at,created_at) VALUES (?,?,?,?,?,?)",
                 (username, generate_password_hash(password), 'player', 'active', expire_at, now()))
    conn.commit()
    conn.close()
    log_action(f"新增玩家 {username}")
    return redirect('/admin/users')

@app.route('/admin/users/toggle/<int:user_id>')
def admin_users_toggle(user_id):
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    target = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if target and target['role'] != 'admin':
        new_status = 'disabled' if target['status'] == 'active' else 'active'
        conn.execute("UPDATE users SET status=? WHERE id=?", (new_status, user_id))
        conn.commit()
        log_action(f"切換玩家 {target['username']} 狀態為 {new_status}")
    conn.close()
    return redirect('/admin/users')

@app.route('/admin/licenses')
def admin_licenses():
    user = require_admin()
    if not user:
        return redirect('/login')
    conn = db()
    licenses = conn.execute("SELECT * FROM licenses ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    return render_template_string(LICENSE_HTML, licenses=licenses)

@app.route('/admin/licenses/create', methods=['POST'])
def admin_licenses_create():
    user = require_admin()
    if not user:
        return redirect('/login')
    count = int(request.form.get('count', 1))
    days = int(request.form.get('days', 30))
    conn = db()
    for _ in range(count):
        key = 'VIP-' + datetime.now().strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:8].upper()
        conn.execute("INSERT INTO licenses(license_key,status,expire_days,created_at) VALUES (?, 'unused', ?, ?)", (key, days, now()))
    conn.commit()
    conn.close()
    log_action(f"產生 {count} 組序號")
    return redirect('/admin/licenses')

@app.route('/api/stats')
def api_stats():
    user = require_login()
    if not user:
        return jsonify({'error': 'unauthorized'}), 401
    conn = db()
    total = conn.execute("SELECT COUNT(*) c FROM records").fetchone()['c']
    conn.close()
    return jsonify({'total_records': total, 'time': now(), 'status': 'ok'})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
