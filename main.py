from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime, timedelta
import sqlite3
import json

app = Flask(__name__)
app.secret_key = "baccarat_admin_secret_2026"

DB_PATH = "baccarat_system.db"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07"]
MT_TABLES = ["1","2","3","3A","5","6","7","8","9","10","11","12","13","13A","15"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_expire(value):
    value = (value or "").strip()
    if not value:
        return "2026-12-31 23:59:59"
    if len(value) == 10:
        return value + " 23:59:59"
    return value


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cur, table, col, typ):
    cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        expire TEXT,
        enabled INTEGER DEFAULT 1,
        role TEXT DEFAULT 'member',
        created_at TEXT,
        last_login TEXT,
        last_active TEXT,
        current_platform TEXT,
        current_table TEXT,
        ip TEXT,
        device TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_no TEXT,
        result TEXT,
        cards TEXT,
        player_point INTEGER DEFAULT 0,
        banker_point INTEGER DEFAULT 0,
        player_pair INTEGER DEFAULT 0,
        banker_pair INTEGER DEFAULT 0,
        lucky6 INTEGER DEFAULT 0,
        tie INTEGER DEFAULT 0,
        source TEXT,
        count_bet INTEGER DEFAULT 0,
        ai_learn INTEGER DEFAULT 1,
        ai_suggest_before TEXT,
        ai_hit INTEGER DEFAULT 0,
        hidden INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS shared_ai_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER,
        platform TEXT,
        table_no TEXT,
        result TEXT,
        cards TEXT,
        player_point INTEGER DEFAULT 0,
        banker_point INTEGER DEFAULT 0,
        player_pair INTEGER DEFAULT 0,
        banker_pair INTEGER DEFAULT 0,
        lucky6 INTEGER DEFAULT 0,
        tie INTEGER DEFAULT 0,
        source TEXT,
        username TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS table_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_no TEXT,
        status TEXT DEFAULT 'normal',
        note TEXT,
        updated_at TEXT,
        UNIQUE(platform, table_no)
    )
    """)

    for col, typ in [
        ("expire","TEXT"),
        ("enabled","INTEGER DEFAULT 1"),
        ("role","TEXT DEFAULT 'member'"),
        ("created_at","TEXT"),
        ("last_login","TEXT"),
        ("last_active","TEXT"),
        ("current_platform","TEXT"),
        ("current_table","TEXT"),
        ("ip","TEXT"),
        ("device","TEXT")
    ]:
        ensure_column(cur, "members", col, typ)

    for col, typ in [
        ("platform","TEXT"),
        ("table_no","TEXT"),
        ("cards","TEXT"),
        ("player_point","INTEGER DEFAULT 0"),
        ("banker_point","INTEGER DEFAULT 0"),
        ("player_pair","INTEGER DEFAULT 0"),
        ("banker_pair","INTEGER DEFAULT 0"),
        ("lucky6","INTEGER DEFAULT 0"),
        ("tie","INTEGER DEFAULT 0"),
        ("source","TEXT"),
        ("count_bet","INTEGER DEFAULT 0"),
        ("ai_learn","INTEGER DEFAULT 1"),
        ("ai_suggest_before","TEXT"),
        ("ai_hit","INTEGER DEFAULT 0"),
        ("hidden","INTEGER DEFAULT 0")
    ]:
        ensure_column(cur, "records", col, typ)

    for col, typ in [
        ("record_id","INTEGER"),
        ("platform","TEXT"),
        ("table_no","TEXT"),
        ("result","TEXT"),
        ("cards","TEXT"),
        ("player_point","INTEGER DEFAULT 0"),
        ("banker_point","INTEGER DEFAULT 0"),
        ("player_pair","INTEGER DEFAULT 0"),
        ("banker_pair","INTEGER DEFAULT 0"),
        ("lucky6","INTEGER DEFAULT 0"),
        ("tie","INTEGER DEFAULT 0"),
        ("source","TEXT"),
        ("username","TEXT"),
        ("created_at","TEXT")
    ]:
        ensure_column(cur, "shared_ai_stats", col, typ)

    for col, typ in [
        ("platform","TEXT"),
        ("table_no","TEXT"),
        ("status","TEXT DEFAULT 'normal'"),
        ("note","TEXT"),
        ("updated_at","TEXT")
    ]:
        ensure_column(cur, "table_status", col, typ)

    for platform, tables in [("DG", DG_TABLES), ("MT", MT_TABLES)]:
        for table in tables:
            cur.execute("""
            INSERT OR IGNORE INTO table_status
            (platform, table_no, status, note, updated_at)
            VALUES (?, ?, 'normal', '', ?)
            """, (platform, table, now()))

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members
        (username,password,expire,enabled,role,created_at)
        VALUES (?,?,?,?,?,?)
        """, ("test01","123456","2026-12-31 23:59:59",1,"member",now()))

    conn.commit()
    conn.close()


def detect_device():
    ua = request.headers.get("User-Agent", "")

    if "iPhone" in ua:
        return "iPhone"
    if "Android" in ua:
        return "Android"
    if "Windows" in ua:
        return "Windows"
    if "Macintosh" in ua:
        return "Mac"
    return "Unknown"


def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def get_member(username):
    conn = db()
    row = conn.execute(
        "SELECT * FROM members WHERE username=?",
        (username,)
    ).fetchone()
    conn.close()
    return row


def parse_expire_time(value):
    value = (value or "").strip()

    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except Exception:
            return None


def disable_member(username):
    conn = db()
    conn.execute(
        "UPDATE members SET enabled=0 WHERE username=?",
        (username,)
    )
    conn.commit()
    conn.close()


def require_active_member():
    username = session.get("member")

    if not username:
        return None, (jsonify({"ok": False, "msg": "請重新登入"}), 403)

    member = get_member(username)

    if not member:
        session.clear()
        return None, (jsonify({"ok": False, "msg": "帳號不存在，請重新登入"}), 403)

    expire_time = parse_expire_time(member["expire"])

    if expire_time and datetime.now() > expire_time:
        disable_member(member["username"])
        session.clear()
        return None, (jsonify({"ok": False, "msg": "會員已到期，已自動停權"}), 403)

    if not member["enabled"]:
        session.clear()
        return None, (jsonify({"ok": False, "msg": "會員已停權，請聯絡管理員"}), 403)

    return member, None


def get_table_status_map():
    conn = db()
    rows = conn.execute("""
    SELECT platform, table_no, status, note
    FROM table_status
    """).fetchall()
    conn.close()

    return {
        (r["platform"], r["table_no"]): {
            "status": r["status"] or "normal",
            "note": r["note"] or ""
        }
        for r in rows
    }


def update_member_active(platform="", table=""):
    username = session.get("member")

    if not username:
        return

    conn = db()
    conn.execute("""
    UPDATE members
    SET last_active=?,
        current_platform=?,
        current_table=?,
        ip=?,
        device=?
    WHERE username=?
    """, (
        now(),
        platform,
        table,
        client_ip(),
        detect_device(),
        username
    ))
    conn.commit()
    conn.close()


def calc_cards(cards):
    try:
        nums = [int(x) for x in cards]

        if len(nums) < 4 or len(nums) > 6:
            return None

        player_cards = [nums[0], nums[2]]
        banker_cards = [nums[1], nums[3]]

        player_two = sum(player_cards) % 10
        banker_two = sum(banker_cards) % 10

        if player_two < 8 and banker_two < 8:
            if player_two <= 5:
                if len(nums) >= 5:
                    player_cards.append(nums[4])
                    player_third = nums[4]
                else:
                    player_third = None

                banker_draw = False

                if banker_two <= 2:
                    banker_draw = True
                elif banker_two == 3 and player_third != 8:
                    banker_draw = True
                elif banker_two == 4 and player_third in [2, 3, 4, 5, 6, 7]:
                    banker_draw = True
                elif banker_two == 5 and player_third in [4, 5, 6, 7]:
                    banker_draw = True
                elif banker_two == 6 and player_third in [6, 7]:
                    banker_draw = True

                if banker_draw and len(nums) >= 6:
                    banker_cards.append(nums[5])

            else:
                if banker_two <= 5 and len(nums) >= 5:
                    banker_cards.append(nums[4])

        player_point = sum(player_cards) % 10
        banker_point = sum(banker_cards) % 10

        if player_point > banker_point:
            result = "P"
        elif banker_point > player_point:
            result = "B"
        else:
            result = "T"

        return {
            "result": result,
            "playerPoint": player_point,
            "bankerPoint": banker_point,
            "playerPair": nums[0] == nums[2],
            "bankerPair": nums[1] == nums[3],
            "lucky6": result == "B" and banker_point == 6,
            "tie": result == "T"
        }

    except Exception:
        return None


def row_to_record(row):
    return {
        "id": row["id"],
        "platform": row["platform"],
        "table": row["table_no"],
        "result": row["result"],
        "cards": json.loads(row["cards"]) if row["cards"] else [],
        "playerPoint": row["player_point"],
        "bankerPoint": row["banker_point"],
        "playerPair": bool(row["player_pair"]),
        "bankerPair": bool(row["banker_pair"]),
        "lucky6": bool(row["lucky6"]),
        "tie": bool(row["tie"]),
        "source": row["source"],
        "countBet": bool(row["count_bet"]),
        "aiLearn": bool(row["ai_learn"]),
        "aiSuggestBefore": row["ai_suggest_before"],
        "aiHit": bool(row["ai_hit"]),
        "hidden": bool(row["hidden"]),
        "createdAt": row["created_at"]
    }


def shared_row_to_record(row):
    return {
        "id": row["id"],
        "platform": row["platform"],
        "table": row["table_no"],
        "result": row["result"],
        "cards": json.loads(row["cards"]) if row["cards"] else [],
        "playerPoint": row["player_point"],
        "bankerPoint": row["banker_point"],
        "playerPair": bool(row["player_pair"]),
        "bankerPair": bool(row["banker_pair"]),
        "lucky6": bool(row["lucky6"]),
        "tie": bool(row["tie"]),
        "source": row["source"],
        "createdAt": row["created_at"]
    }


def get_records(platform, table):
    conn = db()

    rows = conn.execute("""
    SELECT *
    FROM records
    WHERE platform=? AND table_no=? AND hidden=0
    ORDER BY id ASC
    """, (
        platform,
        table
    )).fetchall()

    conn.close()

    return [row_to_record(r) for r in rows]


def get_ai_history(where_sql="", params=(), limit=600):
    conn = db()

    rows = conn.execute(f"""
    SELECT *
    FROM shared_ai_stats
    {where_sql}
    ORDER BY id DESC
    LIMIT ?
    """, (*params, limit)).fetchall()

    conn.close()

    return [shared_row_to_record(r) for r in reversed(rows)]


def get_mixed_ai_history(platform, table):
    return {
        "table": get_ai_history(
            "WHERE platform=? AND table_no=?",
            (platform, table),
            500
        ),

        "platform": get_ai_history(
            "WHERE platform=? AND table_no<>?",
            (platform, table),
            500
        ),

        "global": get_ai_history(
            "WHERE NOT (platform=? AND table_no=?)",
            (platform, table),
            500
        )
    }


def make_hidden_route(results, gap):
    bp = [r for r in results if r in ["B", "P"]]

    route = []

    for i in range(gap, len(bp)):
        route.append(
            "R" if bp[i] == bp[i - gap] else "L"
        )

    return route


def hidden_route_bias(results):
    bp = [r for r in results if r in ["B", "P"]]

    if len(bp) < 8:
        return {
            "bigEye": [],
            "small": [],
            "cockroach": [],
            "hollow": [],
            "bankerBias": 0,
            "playerBias": 0,
            "routePower": 0
        }

    routes = {
        "bigEye": make_hidden_route(bp, 2),
        "small": make_hidden_route(bp, 3),
        "cockroach": make_hidden_route(bp, 4),
        "hollow": make_hidden_route(bp, 5)
    }

    weights = {
        "bigEye": 2.5,
        "small": 3.5,
        "cockroach": 5.0,
        "hollow": 4.0
    }

    banker_bias = 0
    player_bias = 0

    last = bp[-1]

    opposite = "P" if last == "B" else "B"

    for name, arr in routes.items():

        recent = arr[-8:]

        if len(recent) < 4:
            continue

        red_count = recent.count("R")
        blue_count = recent.count("L")

        weight = weights[name]

        if red_count >= blue_count + 2:
            target = last
            power = weight

        elif blue_count >= red_count + 2:
            target = opposite
            power = weight

        else:
            continue

        if target == "B":
            banker_bias += power
        else:
            player_bias += power
    return {
        "bigEye": routes["bigEye"],
        "small": routes["small"],
        "cockroach": routes["cockroach"],
        "hollow": routes["hollow"],
        "bankerBias": banker_bias,
        "playerBias": player_bias,
        "routePower": round(
            banker_bias + player_bias,
            1
        )
    }


@app.route("/")
def index():
    member, error = require_active_member()

    if error:
        session.clear()
        return redirect("/login")

    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/admin-login")
def admin_login_page():
    return render_template("admin_login.html")


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect("/admin-login")

    return render_template("admin.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.json or {}

    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    member = get_member(username)

    if not member:
        return jsonify({
            "ok": False,
            "msg": "帳號不存在"
        })

    if not member["enabled"]:
        return jsonify({
            "ok": False,
            "msg": "會員停權"
        })

    if member["password"] != password:
        return jsonify({
            "ok": False,
            "msg": "密碼錯誤"
        })

    session["member"] = username

    return jsonify({
        "ok": True
    })


@app.route("/api/tables")
def api_tables():
    platform = request.args.get("platform", "DG")
    tables = MT_TABLES if platform == "MT" else DG_TABLES
    return jsonify(tables)


@app.route("/api/data")
def api_data():
    member, error = require_active_member()
    if error:
        return error

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    update_member_active(platform, table)

    records = get_records(platform, table)

    b = len([r for r in records if r["result"] == "B"])
    p = len([r for r in records if r["result"] == "P"])
    t = len([r for r in records if r["result"] == "T"])
    total = b + p

    banker_rate = round((b / total) * 100, 1) if total else 0
    player_rate = round((p / total) * 100, 1) if total else 0

    suggest = "觀望"
    stable = 0

    if total >= 3:
        if banker_rate > player_rate:
            suggest = "莊"
            stable = banker_rate
        elif player_rate > banker_rate:
            suggest = "閒"
            stable = player_rate

    stats = {
        "suggest": suggest,
        "stableRate": stable,
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "tieCount": t,
        "totalAnalysis": len(records),
        "streakResult": records[-1]["result"] if records else "",
        "streakCount": 1 if records else 0,
        "alerts": ["目前無提醒"]
    }

    return jsonify({
        "ok": True,
        "records": records,
        "stats": stats,
        "betCount": len(records),
        "memberExpireTime": member["expire"]
    })


@app.route("/api/manual", methods=["POST"])
def api_manual():
    member, error = require_active_member()
    if error:
        return error

    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")
    result = body.get("result")

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False, "msg": "結果錯誤"})

    conn = db()
    conn.execute("""
    INSERT INTO records
    (platform, table_no, result, cards, source, count_bet, ai_learn, hidden, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        platform,
        table,
        result,
        "",
        "manual",
        0,
        1,
        0,
        now()
    ))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def api_cards():
    member, error = require_active_member()
    if error:
        return error

    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")
    cards = body.get("cards", [])

    calc = calc_cards(cards)

    if calc is None:
        return jsonify({"ok": False, "msg": "牌型錯誤"})

    conn = db()
    conn.execute("""
    INSERT INTO records
    (
        platform, table_no, result, cards,
        player_point, banker_point,
        player_pair, banker_pair,
        lucky6, tie,
        source, count_bet, ai_learn, hidden, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        platform,
        table,
        calc["result"],
        json.dumps(cards),
        calc["playerPoint"],
        calc["bankerPoint"],
        1 if calc["playerPair"] else 0,
        1 if calc["bankerPair"] else 0,
        1 if calc["lucky6"] else 0,
        1 if calc["tie"] else 0,
        "cards",
        1,
        1,
        0,
        now()
    ))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    member, error = require_active_member()
    if error:
        return error

    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")

    conn = db()
    row = conn.execute("""
    SELECT id FROM records
    WHERE platform=? AND table_no=? AND hidden=0
    ORDER BY id DESC
    LIMIT 1
    """, (platform, table)).fetchone()

    if row:
        conn.execute("""
        UPDATE records
        SET hidden=1
        WHERE id=?
        """, (row["id"],))
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    member, error = require_active_member()
    if error:
        return error

    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")

    conn = db()
    conn.execute("""
    UPDATE records
    SET hidden=1
    WHERE platform=? AND table_no=? AND hidden=0
    """, (platform, table))
    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "msg": "已清除此桌畫面"
    })


@app.route("/api/admin/core-stats")
def api_admin_core_stats():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    conn = db()

    total_records = conn.execute("""
    SELECT COUNT(*) c FROM records
    """).fetchone()["c"]

    total_members = conn.execute("""
    SELECT COUNT(*) c FROM members
    """).fetchone()["c"]

    online_members = conn.execute("""
    SELECT COUNT(*) c FROM members
    WHERE last_active >= datetime('now','-5 minutes')
    """).fetchone()["c"]

    conn.close()

    return jsonify({
        "ok": True,
        "totalRecords": total_records,
        "totalShared": total_records,
        "accuracy": 100 if total_records else 0,
        "totalMembers": total_members,
        "onlineMembers": online_members
    })


@app.route("/api/admin/members")
def api_admin_members():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    conn = db()
    rows = conn.execute("""
    SELECT *
    FROM members
    ORDER BY id DESC
    """).fetchall()
    conn.close()

    return jsonify({
        "ok": True,
        "members": [dict(r) for r in rows]
    })


@app.route("/api/admin/create-member", methods=["POST"])
def api_admin_create_member():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    expire = normalize_expire(body.get("expire", "2026-12-31"))

    if not username or not password:
        return jsonify({"ok": False, "msg": "帳號密碼必填"})

    conn = db()

    try:
        conn.execute("""
        INSERT INTO members
        (username,password,expire,enabled,role,created_at)
        VALUES (?, ?, ?, 1, 'member', ?)
        """, (username, password, expire, now()))
        conn.commit()
        ok = True
        msg = "新增成功"
    except sqlite3.IntegrityError:
        ok = False
        msg = "帳號已存在"

    conn.close()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/admin/toggle-member", methods=["POST"])
def api_admin_toggle_member():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json or {}
    username = body.get("username", "").strip()

    conn = db()
    row = conn.execute("""
    SELECT enabled FROM members
    WHERE username=?
    """, (username,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False})

    new_status = 0 if row["enabled"] else 1

    conn.execute("""
    UPDATE members
    SET enabled=?
    WHERE username=?
    """, (new_status, username))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/tables-monitor")
def api_admin_tables_monitor():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    tables = []

    for platform, list_tables in [("DG", DG_TABLES), ("MT", MT_TABLES)]:
        for table in list_tables:
            records = get_records(platform, table)
            road = "".join([r["result"] for r in records[-20:]])

            tables.append({
                "platform": platform,
                "table": table,
                "road": road if road else "-",
                "ai": "觀望",
                "online": True
            })

    return jsonify({
        "ok": True,
        "tables": tables
    })


@app.route("/api/admin-login", methods=["POST"])
def api_admin_login():
    body = request.json or {}

    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    if username == ADMIN_USER and password == ADMIN_PASS:
        session["admin"] = True
        return jsonify({"ok": True})

    return jsonify({"ok": False})

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
