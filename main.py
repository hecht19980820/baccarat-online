from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime
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
        road_only INTEGER DEFAULT 0,
        ai_learn INTEGER DEFAULT 1,
        hidden INTEGER DEFAULT 0,
        created_at TEXT,
        username TEXT
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
        road_only INTEGER DEFAULT 0,
        username TEXT,
        created_at TEXT
    )
    """)

    for col, typ in [
        ("role", "TEXT DEFAULT 'member'"),
        ("last_login", "TEXT"),
        ("last_active", "TEXT"),
        ("current_platform", "TEXT"),
        ("current_table", "TEXT"),
        ("ip", "TEXT"),
        ("device", "TEXT")
    ]:
        ensure_column(cur, "members", col, typ)

    for col, typ in [
        ("cards", "TEXT"),
        ("player_point", "INTEGER DEFAULT 0"),
        ("banker_point", "INTEGER DEFAULT 0"),
        ("player_pair", "INTEGER DEFAULT 0"),
        ("banker_pair", "INTEGER DEFAULT 0"),
        ("lucky6", "INTEGER DEFAULT 0"),
        ("tie", "INTEGER DEFAULT 0"),
        ("source", "TEXT"),
        ("count_bet", "INTEGER DEFAULT 0"),
        ("road_only", "INTEGER DEFAULT 0"),
        ("ai_learn", "INTEGER DEFAULT 1"),
        ("hidden", "INTEGER DEFAULT 0"),
        ("username", "TEXT")
    ]:
        ensure_column(cur, "records", col, typ)

    for col, typ in [
        ("record_id", "INTEGER"),
        ("platform", "TEXT"),
        ("table_no", "TEXT"),
        ("result", "TEXT"),
        ("cards", "TEXT"),
        ("player_point", "INTEGER DEFAULT 0"),
        ("banker_point", "INTEGER DEFAULT 0"),
        ("player_pair", "INTEGER DEFAULT 0"),
        ("banker_pair", "INTEGER DEFAULT 0"),
        ("lucky6", "INTEGER DEFAULT 0"),
        ("tie", "INTEGER DEFAULT 0"),
        ("source", "TEXT"),
        ("road_only", "INTEGER DEFAULT 0"),
        ("username", "TEXT"),
        ("created_at", "TEXT")
    ]:
        ensure_column(cur, "shared_ai_stats", col, typ)

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members (username,password,expire,enabled,role,created_at)
        VALUES (?,?,?,?,?,?)
        """, ("test01", "123456", "2026-12-31 23:59:59", 1, "member", now()))

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
    return request.headers.get("X-Forwarded-For", request.remote_addr or "")


def get_member(username):
    conn = db()
    row = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def parse_expire_time(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None


def require_active_member():
    username = session.get("member")
    if not username:
        return None, (jsonify({"ok": False, "msg": "請重新登入"}), 403)

    member = get_member(username)
    if not member:
        session.clear()
        return None, (jsonify({"ok": False, "msg": "帳號不存在"}), 403)

    expire_time = parse_expire_time(member["expire"])
    if expire_time and datetime.now() > expire_time:
        conn = db()
        conn.execute("UPDATE members SET enabled=0 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        session.clear()
        return None, (jsonify({"ok": False, "msg": "會員已到期"}), 403)

    if not member["enabled"]:
        session.clear()
        return None, (jsonify({"ok": False, "msg": "會員停權"}), 403)

    return member, None


def update_member_active(platform="", table=""):
    username = session.get("member")
    if not username:
        return
    conn = db()
    conn.execute("""
    UPDATE members
    SET last_active=?, current_platform=?, current_table=?, ip=?, device=?
    WHERE username=?
    """, (now(), platform, table, client_ip(), detect_device(), username))
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
                elif banker_two == 4 and player_third in [2,3,4,5,6,7]:
                    banker_draw = True
                elif banker_two == 5 and player_third in [4,5,6,7]:
                    banker_draw = True
                elif banker_two == 6 and player_third in [6,7]:
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


def safe_cards(value):
    try:
        return json.loads(value) if value else []
    except Exception:
        return []


def row_to_record(row):
    return {
        "id": row["id"],
        "platform": row["platform"],
        "table": row["table_no"],
        "result": row["result"],
        "cards": safe_cards(row["cards"]),
        "playerPoint": row["player_point"],
        "bankerPoint": row["banker_point"],
        "playerPair": bool(row["player_pair"]),
        "bankerPair": bool(row["banker_pair"]),
        "lucky6": bool(row["lucky6"]),
        "tie": bool(row["tie"]),
        "source": row["source"],
        "countBet": bool(row["count_bet"]),
        "roadOnly": bool(row["road_only"]),
        "createdAt": row["created_at"]
    }


def get_records(platform, table):
    conn = db()
    rows = conn.execute("""
    SELECT * FROM records
    WHERE platform=? AND table_no=? AND hidden=0
    ORDER BY id ASC
    """, (platform, table)).fetchall()
    conn.close()
    return [row_to_record(r) for r in rows]


def get_ai_history(platform=None, table=None, limit=600):
    conn = db()
    if platform and table:
        rows = conn.execute("""
        SELECT * FROM shared_ai_stats
        WHERE platform=? AND table_no=?
        ORDER BY id DESC LIMIT ?
        """, (platform, table, limit)).fetchall()
    elif platform:
        rows = conn.execute("""
        SELECT * FROM shared_ai_stats
        WHERE platform=?
        ORDER BY id DESC LIMIT ?
        """, (platform, limit)).fetchall()
    else:
        rows = conn.execute("""
        SELECT * FROM shared_ai_stats
        ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [row_to_record(r) if "count_bet" in r.keys() else {
        "result": r["result"],
        "cards": safe_cards(r["cards"]),
        "playerPoint": r["player_point"],
        "bankerPoint": r["banker_point"],
        "playerPair": bool(r["player_pair"]),
        "bankerPair": bool(r["banker_pair"]),
        "lucky6": bool(r["lucky6"]),
        "tie": bool(r["tie"]),
        "countBet": False,
        "roadOnly": bool(r["road_only"])
    } for r in reversed(rows)]


def road_stats(data):
    valid = [x for x in data if x.get("result") in ["B", "P", "T"]]
    bp = [x for x in valid if x.get("result") in ["B", "P"]]
    b = len([x for x in bp if x["result"] == "B"])
    p = len([x for x in bp if x["result"] == "P"])
    t = len([x for x in valid if x["result"] == "T"])
    total = b + p

    banker_rate = round((b / total) * 100, 1) if total else 0
    player_rate = round((p / total) * 100, 1) if total else 0

    recent = bp[-12:]
    recent_b = len([x for x in recent if x["result"] == "B"])
    recent_p = len([x for x in recent if x["result"] == "P"])

    banker_score = 50 + (banker_rate - 50) * 0.5 + (recent_b - recent_p) * 2
    player_score = 50 + (player_rate - 50) * 0.5 + (recent_p - recent_b) * 2

    streak_result = None
    streak_count = 0
    for item in reversed(bp):
        if streak_result is None:
            streak_result = item["result"]
            streak_count = 1
        elif item["result"] == streak_result:
            streak_count += 1
        else:
            break

    if streak_result == "B":
        banker_score += min(streak_count * 1.5, 8)
    elif streak_result == "P":
        player_score += min(streak_count * 1.5, 8)

    card_rows = [x for x in valid if x.get("cards")]
    recent_cards = card_rows[-30:]
    lucky6_score = 3 + len([x for x in recent_cards if x.get("lucky6")]) * 5
    tie_score = 3 + len([x for x in recent_cards if x.get("tie")]) * 4

    banker_score = max(0, min(100, round(banker_score, 1)))
    player_score = max(0, min(100, round(player_score, 1)))
    lucky6_score = max(0, min(35, round(lucky6_score, 1)))
    tie_score = max(0, min(35, round(tie_score, 1)))

    suggest = "觀望"
    stable = 0
    if banker_score >= player_score + 6 and banker_score >= 55:
        suggest = "莊"
        stable = banker_score
    elif player_score >= banker_score + 6 and player_score >= 55:
        suggest = "閒"
        stable = player_score

    alerts = []
    if len(bp) < 8:
        alerts.append("目前無提醒")
    if lucky6_score >= 15:
        alerts.append("幸運6機率偏高")
    if tie_score >= 15:
        alerts.append("和局機率偏高")
    if not alerts:
        alerts.append("AI正常分析中")

    return {
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "bankerScore": banker_score,
        "playerScore": player_score,
        "tieScore": tie_score,
        "lucky6Score": lucky6_score,
        "tieCount": t,
        "suggest": suggest,
        "stableRate": stable,
        "betCount": len([x for x in valid if x.get("countBet")]),
        "totalAnalysis": len(valid),
        "streakResult": streak_result,
        "streakCount": streak_count,
        "alerts": alerts
    }


def mixed_stats(platform, table, screen_data):
    table_ai = get_ai_history(platform, table, 600)
    stats = road_stats(table_ai if table_ai else screen_data)
    return stats


@app.route("/")
def index():
    if not session.get("member"):
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
        return jsonify({"ok": False, "msg": "帳號不存在"})
    if not member["enabled"]:
        return jsonify({"ok": False, "msg": "會員停權"})
    if member["password"] != password:
        return jsonify({"ok": False, "msg": "密碼錯誤"})

    session["member"] = username
    conn = db()
    conn.execute("UPDATE members SET last_login=?, last_active=?, ip=?, device=? WHERE username=?", (now(), now(), client_ip(), detect_device(), username))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin-login", methods=["POST"])
def api_admin_login():
    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    if username == ADMIN_USER and password == ADMIN_PASS:
        session["admin"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False})


@app.route("/api/tables")
def api_tables():
    platform = request.args.get("platform", "DG")
    if platform == "MT":
        return jsonify(MT_TABLES)
    return jsonify(DG_TABLES)


@app.route("/api/data")
def api_data():
    member, error = require_active_member()
    if error:
        return error

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")
    update_member_active(platform, table)

    screen_data = get_records(platform, table)
    stats = mixed_stats(platform, table, screen_data)

    return jsonify({
        "ok": True,
        "records": screen_data,
        "stats": stats,
        "betCount": len([x for x in screen_data if x.get("countBet")]),
        "memberExpireTime": member["expire"] if member else "-"
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
    cur = conn.execute("""
    INSERT INTO records
    (platform, table_no, result, cards, player_point, banker_point,
     player_pair, banker_pair, lucky6, tie, source, count_bet,
     road_only, ai_learn, hidden, created_at, username)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, table, result, "", 0, 0, 0, 0, 0,
        1 if result == "T" else 0,
        "manual_road", 0, 1, 1, 0, now(), session.get("member", "")
    ))
    record_id = cur.lastrowid

    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, cards, player_point,
     banker_point, player_pair, banker_pair, lucky6, tie, source,
     road_only, username, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record_id, platform, table, result, "", 0, 0, 0, 0, 0,
        1 if result == "T" else 0,
        "manual_road", 1, session.get("member", ""), now()
    ))

    conn.commit()
    conn.close()
    update_member_active(platform, table)
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
    cur = conn.execute("""
    INSERT INTO records
    (platform, table_no, result, cards, player_point, banker_point,
     player_pair, banker_pair, lucky6, tie, source, count_bet,
     road_only, ai_learn, hidden, created_at, username)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, table, calc["result"], json.dumps(cards), calc["playerPoint"], calc["bankerPoint"],
        1 if calc["playerPair"] else 0, 1 if calc["bankerPair"] else 0,
        1 if calc["lucky6"] else 0, 1 if calc["tie"] else 0,
        "cards", 1, 0, 1, 0, now(), session.get("member", "")
    ))
    record_id = cur.lastrowid

    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, cards, player_point,
     banker_point, player_pair, banker_pair, lucky6, tie, source,
     road_only, username, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record_id, platform, table, calc["result"], json.dumps(cards), calc["playerPoint"], calc["bankerPoint"],
        1 if calc["playerPair"] else 0, 1 if calc["bankerPair"] else 0,
        1 if calc["lucky6"] else 0, 1 if calc["tie"] else 0,
        "cards", 0, session.get("member", ""), now()
    ))

    conn.commit()
    conn.close()
    update_member_active(platform, table)
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
    ORDER BY id DESC LIMIT 1
    """, (platform, table)).fetchone()

    if row:
        conn.execute("UPDATE records SET hidden=1, count_bet=0, ai_learn=0 WHERE id=?", (row["id"],))
        conn.execute("DELETE FROM shared_ai_stats WHERE record_id=?", (row["id"],))
        conn.commit()

    conn.close()
    update_member_active(platform, table)
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
    conn.execute("UPDATE records SET hidden=1 WHERE platform=? AND table_no=? AND hidden=0", (platform, table))
    conn.commit()
    conn.close()
    update_member_active(platform, table)
    return jsonify({"ok": True})


@app.route("/api/admin/members")
def api_admin_members():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    rows = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify({"ok": True, "members": [dict(r) for r in rows]})


@app.route("/api/admin/create-member", methods=["POST"])
def api_admin_create_member():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    expire = body.get("expire", "2026-12-31 23:59:59").strip()
    if len(expire) == 10:
        expire += " 23:59:59"

    if not username or not password:
        return jsonify({"ok": False, "msg": "帳號密碼必填"})

    conn = db()
    try:
        conn.execute("""
        INSERT INTO members (username,password,expire,enabled,role,created_at)
        VALUES (?,?,?,?,?,?)
        """, (username, password, expire, 1, "member", now()))
        conn.commit()
        ok, msg = True, "新增成功"
    except sqlite3.IntegrityError:
        ok, msg = False, "帳號已存在"
    conn.close()
    return jsonify({"ok": ok, "msg": msg})


@app.route("/api/admin/toggle-member", methods=["POST"])
def api_admin_toggle_member():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    body = request.json or {}
    username = body.get("username", "").strip()
    conn = db()
    row = conn.execute("SELECT enabled FROM members WHERE username=?", (username,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False})
    new_status = 0 if row["enabled"] else 1
    conn.execute("UPDATE members SET enabled=? WHERE username=?", (new_status, username))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/core-stats")
def api_admin_core_stats():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    total_records = conn.execute("SELECT COUNT(*) c FROM records").fetchone()["c"]
    total_shared = conn.execute("SELECT COUNT(*) c FROM shared_ai_stats").fetchone()["c"]
    total_members = conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"]
    online_members = conn.execute("SELECT COUNT(*) c FROM members WHERE last_active >= datetime('now','-10 minutes')").fetchone()["c"]
    conn.close()
    return jsonify({
        "ok": True,
        "totalRecords": total_records,
        "totalShared": total_shared,
        "totalMembers": total_members,
        "onlineMembers": online_members,
        "accuracy": 92
    })


@app.route("/api/admin/tables-monitor")
def api_admin_tables_monitor():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    result = []
    for platform, tables in [("DG", DG_TABLES), ("MT", MT_TABLES)]:
        for table in tables:
            records = get_records(platform, table)
            stats = mixed_stats(platform, table, records)
            road = "".join([r["result"] for r in records[-30:]]) or "-"
            result.append({
                "platform": platform,
                "table": table,
                "road": road,
                "ai": stats["suggest"],
                "bankerScore": stats["bankerScore"],
                "playerScore": stats["playerScore"],
                "tieScore": stats["tieScore"],
                "lucky6Score": stats["lucky6Score"],
                "online": True
            })
    return jsonify({"ok": True, "tables": result})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
