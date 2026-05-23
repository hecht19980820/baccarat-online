from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime
import sqlite3
import json

app = Flask(__name__)
app.secret_key = "baccarat_admin_secret_2026"

DB_PATH = "baccarat_system.db"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07","RB08","RB09","RB10"]
MT_TABLES = ["01","02","03","03A","05","06","07","08","09","10"]


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
        ai_learn INTEGER DEFAULT 1,
        ai_suggest_before TEXT,
        ai_hit INTEGER DEFAULT 0,
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
        source TEXT,
        username TEXT,
        created_at TEXT
    )
    """)

    for col, typ in [
        ("expire", "TEXT"),
        ("enabled", "INTEGER DEFAULT 1"),
        ("role", "TEXT DEFAULT 'member'"),
        ("created_at", "TEXT"),
        ("last_login", "TEXT"),
        ("last_active", "TEXT"),
        ("current_platform", "TEXT"),
        ("current_table", "TEXT"),
        ("ip", "TEXT"),
        ("device", "TEXT")
    ]:
        ensure_column(cur, "members", col, typ)

    for col, typ in [
        ("platform", "TEXT"),
        ("table_no", "TEXT"),
        ("cards", "TEXT"),
        ("player_point", "INTEGER DEFAULT 0"),
        ("banker_point", "INTEGER DEFAULT 0"),
        ("player_pair", "INTEGER DEFAULT 0"),
        ("banker_pair", "INTEGER DEFAULT 0"),
        ("lucky6", "INTEGER DEFAULT 0"),
        ("tie", "INTEGER DEFAULT 0"),
        ("source", "TEXT"),
        ("count_bet", "INTEGER DEFAULT 0"),
        ("ai_learn", "INTEGER DEFAULT 1"),
        ("ai_suggest_before", "TEXT"),
        ("ai_hit", "INTEGER DEFAULT 0")
    ]:
        ensure_column(cur, "records", col, typ)

    for col, typ in [
        ("record_id", "INTEGER"),
        ("platform", "TEXT"),
        ("table_no", "TEXT"),
        ("result", "TEXT"),
        ("source", "TEXT"),
        ("username", "TEXT"),
        ("created_at", "TEXT")
    ]:
        ensure_column(cur, "shared_ai_stats", col, typ)

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")

    if cur.fetchone()["c"] == 0:

        cur.execute("""
        INSERT INTO members
        (
            username,
            password,
            expire,
            enabled,
            role,
            created_at
        )
        VALUES (?,?,?,?,?,?)
        """, (
            "test01",
            "123456",
            "2026-12-31 23:59:59",
            1,
            "member",
            now()
        ))

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
    return request.headers.get(
        "X-Forwarded-For",
        request.remote_addr
    )


def get_member(username):

    conn = db()

    row = conn.execute("""
    SELECT * FROM members
    WHERE username=?
    """, (username,)).fetchone()

    conn.close()

    return row


def update_member_active(platform="", table=""):

    username = session.get("member")

    if not username:
        return

    conn = db()

    conn.execute("""
    UPDATE members
    SET
        last_active=?,
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


def get_shared_records(platform, table):

    conn = db()

    rows = conn.execute("""
    SELECT *
    FROM shared_ai_stats
    WHERE platform=? AND table_no=?
    ORDER BY id ASC
    """, (
        platform,
        table
    )).fetchall()

    conn.close()

        return [
        {
            "result": r["result"],
            "source": r["source"],
            "username": r["username"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


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

    except:
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
        "createdAt": row["created_at"]
    }


def get_records(platform, table):
    conn = db()
    rows = conn.execute("""
    SELECT * FROM records
    WHERE platform=? AND table_no=?
    ORDER BY id ASC
    """, (platform, table)).fetchall()
    conn.close()
    return [row_to_record(r) for r in rows]


def road_stats(data):
    valid = [x for x in data if x.get("result") in ["B","P","T"]]
    bp = [x for x in valid if x.get("result") in ["B","P"]]

    b = len([x for x in bp if x["result"] == "B"])
    p = len([x for x in bp if x["result"] == "P"])
    t = len([x for x in valid if x["result"] == "T"])
    total = len(bp)

    banker_rate = round((b / total) * 100, 1) if total else 0
    player_rate = round((p / total) * 100, 1) if total else 0

    recent = bp[-12:]
    recent_b = len([x for x in recent if x["result"] == "B"])
    recent_p = len([x for x in recent if x["result"] == "P"])

    streak_result = None
    streak_count = 0

    for item in reversed(bp):
        r = item["result"]
        if streak_result is None:
            streak_result = r
            streak_count = 1
        elif r == streak_result:
            streak_count += 1
        else:
            break

    jump_count = 0
    for i in range(1, len(bp)):
        if bp[i]["result"] != bp[i-1]["result"]:
            jump_count += 1

    jump_rate = round((jump_count / (len(bp)-1)) * 100, 1) if len(bp) > 1 else 0

    banker_score = 50
    player_score = 50

    banker_score += (banker_rate - 50) * 0.6
    player_score += (player_rate - 50) * 0.6

    banker_score += (recent_b - recent_p) * 3
    player_score += (recent_p - recent_b) * 3

    if streak_result == "B":
        banker_score += streak_count * 2
        if streak_count >= 4:
            player_score += 8
    elif streak_result == "P":
        player_score += streak_count * 2
        if streak_count >= 4:
            banker_score += 8

    if jump_rate >= 60:
        if bp and bp[-1]["result"] == "B":
            player_score += 8
        elif bp and bp[-1]["result"] == "P":
            banker_score += 8

    banker_score = max(0, min(100, round(banker_score, 1)))
    player_score = max(0, min(100, round(player_score, 1)))

    suggest = "觀望"
    stable = max(banker_score, player_score)

    if banker_score >= player_score + 6 and banker_score >= 55:
        suggest = "莊"
        stable = banker_score
    elif player_score >= banker_score + 6 and player_score >= 55:
        suggest = "閒"
        stable = player_score

    alerts = []

    if streak_count >= 4:
        alerts.append("長龍注意，可能續龍或斷龍")

    if jump_rate >= 60:
        alerts.append("跳路偏高，注意反打")

    if len(bp) < 10:
        alerts.append("資料量不足，建議觀望")

    if not alerts:
        alerts.append("共享AI正常分析中")

    return {
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "bankerScore": banker_score,
        "playerScore": player_score,
        "tieCount": t,
        "suggest": suggest,
        "stableRate": stable,
        "betCount": len(valid),
        "totalAnalysis": len(valid),
        "streakResult": streak_result,
        "streakCount": streak_count,
        "jumpRate": jump_rate,
        "alerts": alerts
    }


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
    update_member_active()

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
    return jsonify(MT_TABLES if platform == "MT" else DG_TABLES)


@app.route("/api/data")
def api_data():
    if not session.get("member"):
        return jsonify({"ok": False})

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    update_member_active(platform, table)

    data = get_records(platform, table)
    shared_data = get_shared_records(platform, table)
    stats = road_stats(shared_data if shared_data else data)

    member = get_member(session.get("member"))

    return jsonify({
        "ok": True,
        "records": data,
        "stats": stats,
        "betCount": stats.get("betCount", 0),
        "memberExpireTime": member["expire"] if member else "-"
    })


@app.route("/api/manual", methods=["POST"])
def api_manual():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")
    result = body.get("result")

    if result not in ["B","P","T"]:
        return jsonify({"ok": False, "msg": "結果錯誤"})

    conn = db()

    cur = conn.execute("""
    INSERT INTO records
    (
        platform, table_no, result, cards,
        player_point, banker_point,
        player_pair, banker_pair,
        lucky6, tie, source, count_bet,
        ai_learn, ai_suggest_before, ai_hit, created_at
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, table, result, "",
        0, 0,
        0, 0,
        0, 1 if result == "T" else 0,
        "manual", 0,
        1, "", 0, now()
    ))

    record_id = cur.lastrowid

    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, source, username, created_at)
    VALUES (?,?,?,?,?,?,?)
    """, (
        record_id,
        platform,
        table,
        result,
        "manual",
        session.get("member", ""),
        now()
    ))

    conn.commit()
    conn.close()

    update_member_active(platform, table)

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def api_cards():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

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
    (
        platform, table_no, result, cards,
        player_point, banker_point,
        player_pair, banker_pair,
        lucky6, tie, source, count_bet,
        ai_learn, ai_suggest_before, ai_hit, created_at
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        "card_button",
        1,
        1,
        "",
        0,
        now()
    ))

    record_id = cur.lastrowid

    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, source, username, created_at)
    VALUES (?,?,?,?,?,?,?)
    """, (
        record_id,
        platform,
        table,
        calc["result"],
        "cards",
        session.get("member", ""),
        now()
    ))

    conn.commit()
    conn.close()

    update_member_active(platform, table)

    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")

    conn = db()

    row = conn.execute("""
    SELECT id FROM records
    WHERE platform=? AND table_no=?
    ORDER BY id DESC
    LIMIT 1
    """, (platform, table)).fetchone()

    if row:
        conn.execute("DELETE FROM shared_ai_stats WHERE record_id=?", (row["id"],))
        conn.execute("DELETE FROM records WHERE id=?", (row["id"],))
        conn.commit()

    conn.close()

    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")

    conn = db()

    rows = conn.execute("""
    SELECT id FROM records
    WHERE platform=? AND table_no=?
    """, (platform, table)).fetchall()

    ids = [r["id"] for r in rows]

    if ids:
        conn.executemany(
            "DELETE FROM shared_ai_stats WHERE record_id=?",
            [(i,) for i in ids]
        )

    conn.execute("""
    DELETE FROM records
    WHERE platform=? AND table_no=?
    """, (platform, table))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
