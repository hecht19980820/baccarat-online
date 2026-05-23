from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime, timedelta
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
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        expire TEXT NOT NULL,
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
        platform TEXT NOT NULL,
        table_no TEXT NOT NULL,
        result TEXT NOT NULL,
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
    CREATE TABLE IF NOT EXISTS ai_learning (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_no TEXT,
        banker_score REAL DEFAULT 50,
        player_score REAL DEFAULT 50,
        total_predict INTEGER DEFAULT 0,
        total_hit INTEGER DEFAULT 0,
        updated_at TEXT,
        UNIQUE(platform, table_no)
    )
    """)

    for col, typ in [
        ("role", "TEXT DEFAULT 'member'"),
        ("created_at", "TEXT"),
        ("last_login", "TEXT"),
        ("last_active", "TEXT"),
        ("current_platform", "TEXT"),
        ("current_table", "TEXT"),
        ("ip", "TEXT"),
        ("device", "TEXT"),
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
        ("ai_learn", "INTEGER DEFAULT 1"),
        ("ai_suggest_before", "TEXT"),
        ("ai_hit", "INTEGER DEFAULT 0"),
    ]:
        ensure_column(cur, "records", col, typ)

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members
        (username,password,expire,enabled,role,created_at,last_login,last_active,current_platform,current_table,ip,device)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            "test01",
            "123456",
            "2026-12-31 23:59:59",
            1,
            "member",
            now(),
            "",
            "",
            "",
            "",
            "",
            ""
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
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def get_member(username):
    conn = db()
    row = conn.execute(
        "SELECT * FROM members WHERE username=?",
        (username,)
    ).fetchone()
    conn.close()
    return row


def update_member_active(platform="", table=""):
    username = session.get("member")
    if not username:
        return

    conn = db()
    conn.execute("""
    UPDATE members
    SET last_active=?, current_platform=?, current_table=?, ip=?, device=?
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

        player_cards = []
        banker_cards = []

        for i, n in enumerate(nums):
            if i % 2 == 0:
                player_cards.append(n)
            else:
                banker_cards.append(n)

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
            "playerPair": len(player_cards) >= 2 and player_cards[0] == player_cards[1],
            "bankerPair": len(banker_cards) >= 2 and banker_cards[0] == banker_cards[1],
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

    total = len(bp)

    banker_rate = round((b / total) * 100, 1) if total else 0
    player_rate = round((p / total) * 100, 1) if total else 0

    suggest = "觀望"

    if banker_rate >= 55:
        suggest = "莊"

    if player_rate >= 55:
        suggest = "閒"

    stable = max(banker_rate, player_rate)

    return {
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "suggest": suggest,
        "stableRate": stable,
        "betCount": len(valid)
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


@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.json

    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    member = get_member(username)

    if not member:
        return jsonify({"ok": False})

    if member["password"] != password:
        return jsonify({"ok": False})

    session["member"] = username

    return jsonify({"ok": True})


@app.route("/api/admin-login", methods=["POST"])
def api_admin_login():
    body = request.json

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
    if not session.get("member"):
        return jsonify({"ok": False})

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    update_member_active(platform, table)

    data = get_records(platform, table)
    stats = road_stats(data)

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
        return jsonify({"ok": False})

    body = request.json

    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    conn = db()

    conn.execute("""
    INSERT INTO records
    (platform,table_no,result,created_at)
    VALUES (?,?,?,?)
    """, (
        platform,
        table,
        result,
        now()
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def api_cards():
    if not session.get("member"):
        return jsonify({"ok": False})

    body = request.json

    platform = body.get("platform")
    table = body.get("table")
    cards = body.get("cards", [])

    calc = calc_cards(cards)

    if not calc:
        return jsonify({"ok": False})

    conn = db()

    conn.execute("""
    INSERT INTO records
    (platform,table_no,result,cards,player_point,banker_point,created_at)
    VALUES (?,?,?,?,?,?,?)
    """, (
        platform,
        table,
        calc["result"],
        json.dumps(cards),
        calc["playerPoint"],
        calc["bankerPoint"],
        now()
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
