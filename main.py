from flask import Flask, render_template, request, jsonify, session, redirect
import sqlite3
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "baccarat_secret_2026"

DB = "baccarat_system.db"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07","RB08","RB09","RB10"]
MT_TABLES = ["01","02","03","03A","04","05","06","07","08","09","10"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cur, table, column, col_type):
    cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        expire TEXT,
        enabled INTEGER DEFAULT 1,
        role TEXT DEFAULT 'member',
        currentPlatform TEXT DEFAULT '',
        currentTable TEXT DEFAULT '',
        device TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        lastLogin TEXT DEFAULT '',
        lastActive TEXT DEFAULT '',
        createdAt TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        result TEXT,
        cards TEXT DEFAULT '',
        source TEXT DEFAULT '',
        countBet INTEGER DEFAULT 0,
        aiSuggest TEXT DEFAULT '',
        aiHit INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_learning(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        bankerScore REAL DEFAULT 50,
        playerScore REAL DEFAULT 50,
        totalPredict INTEGER DEFAULT 0,
        totalHit INTEGER DEFAULT 0,
        updatedAt TEXT
    )
    """)

    for col, typ in [
        ("role", "TEXT DEFAULT 'member'"),
        ("currentPlatform", "TEXT DEFAULT ''"),
        ("currentTable", "TEXT DEFAULT ''"),
        ("device", "TEXT DEFAULT ''"),
        ("ip", "TEXT DEFAULT ''"),
        ("lastLogin", "TEXT DEFAULT ''"),
        ("lastActive", "TEXT DEFAULT ''"),
        ("createdAt", "TEXT DEFAULT ''")
    ]:
        ensure_column(cur, "members", col, typ)

    for col, typ in [
        ("cards", "TEXT DEFAULT ''"),
        ("source", "TEXT DEFAULT ''"),
        ("countBet", "INTEGER DEFAULT 0"),
        ("aiSuggest", "TEXT DEFAULT ''"),
        ("aiHit", "INTEGER DEFAULT 0")
    ]:
        ensure_column(cur, "records", col, typ)

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members(username,password,expire,enabled,role,createdAt)
        VALUES(?,?,?,?,?,?)
        """, ("test01","123456","2026-12-31 23:59:59",1,"member",now()))

    conn.commit()
    conn.close()


def get_tables(platform):
    return MT_TABLES if platform == "MT" else DG_TABLES


def get_device():
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


def get_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def update_online(platform="", table=""):
    if "user" not in session:
        return

    conn = get_db()
    conn.execute("""
    UPDATE members
    SET currentPlatform=?, currentTable=?, device=?, ip=?, lastActive=?
    WHERE username=?
    """, (
        platform,
        table,
        get_device(),
        get_ip(),
        now(),
        session["user"]
    ))
    conn.commit()
    conn.close()


def record_to_dict(r):
    return {
        "id": r["id"],
        "platform": r["platform"],
        "table": r["table_name"],
        "result": r["result"],
        "cards": json.loads(r["cards"]) if r["cards"] else [],
        "source": r["source"],
        "countBet": bool(r["countBet"]),
        "aiSuggest": r["aiSuggest"],
        "aiHit": bool(r["aiHit"]),
        "createdAt": r["created_at"]
    }


def get_records(platform, table):
    conn = get_db()
    rows = conn.execute("""
    SELECT * FROM records
    WHERE platform=? AND table_name=?
    ORDER BY id ASC
    """, (platform, table)).fetchall()
    conn.close()
    return [record_to_dict(r) for r in rows]


def calc_cards(cards):
    try:
        nums = [int(x) for x in cards]

        if len(nums) < 4 or len(nums) > 6:
            return None

        player = nums[0] + nums[2]
        banker = nums[1] + nums[3]

        if len(nums) >= 5:
            player += nums[4]

        if len(nums) >= 6:
            banker += nums[5]

        player %= 10
        banker %= 10

        if banker > player:
            result = "B"
        elif player > banker:
            result = "P"
        else:
            result = "T"

        return {
            "result": result,
            "playerPoint": player,
            "bankerPoint": banker
        }

    except Exception:
        return None


def analyze(records):
    banker = len([r for r in records if r["result"] == "B"])
    player = len([r for r in records if r["result"] == "P"])
    tie = len([r for r in records if r["result"] == "T"])

    total = banker + player

    bankerRate = round((banker / total) * 100, 1) if total else 0
    playerRate = round((player / total) * 100, 1) if total else 0

    recent = [r["result"] for r in records if r["result"] in ["B","P"]][-20:]

    bankerScore = 50
    playerScore = 50

    for i, r in enumerate(recent):
        weight = i + 1
        if r == "B":
            bankerScore += weight * 0.45
        elif r == "P":
            playerScore += weight * 0.45

    streakResult = None
    streakCount = 0

    for r in reversed(records):
        if r["result"] == "T":
            continue

        if streakResult is None:
            streakResult = r["result"]
            streakCount = 1
        elif r["result"] == streakResult:
            streakCount += 1
        else:
            break

    if streakResult == "B":
        bankerScore += streakCount * 2
    elif streakResult == "P":
        playerScore += streakCount * 2

    diff = abs(bankerScore - playerScore)

    if total < 6:
        suggest = "觀望"
        stableRate = 0
    elif diff < 6:
        suggest = "觀望"
        stableRate = round(50 + diff, 1)
    elif bankerScore > playerScore:
        suggest = "莊"
        stableRate = round(min(96, 50 + diff), 1)
    else:
        suggest = "閒"
        stableRate = round(min(96, 50 + diff), 1)

    alerts = []

    if total < 6:
        alerts.append("資料不足")

    if streakCount >= 4:
        alerts.append(("莊" if streakResult == "B" else "閒") + f" {streakCount} 連")

    return {
        "bankerRate": bankerRate,
        "playerRate": playerRate,
        "tieCount": tie,
        "suggest": suggest,
        "stableRate": stableRate,
        "streakResult": streakResult,
        "streakCount": streakCount,
        "alerts": alerts[:3],
        "totalAnalysis": total,
        "bankerScore": round(bankerScore, 1),
        "playerScore": round(playerScore, 1),
        "betCount": len([r for r in records if r.get("countBet")])
    }


def update_learning(platform, table, result, suggest):
    suggestCode = "B" if suggest == "莊" else "P" if suggest == "閒" else ""
    aiHit = 1 if suggestCode == result else 0
    predict = 1 if suggestCode in ["B", "P"] else 0

    conn = get_db()

    row = conn.execute("""
    SELECT * FROM ai_learning
    WHERE platform=? AND table_name=?
    """, (platform, table)).fetchone()

    if not row:
        conn.execute("""
        INSERT INTO ai_learning(platform,table_name,bankerScore,playerScore,totalPredict,totalHit,updatedAt)
        VALUES(?,?,?,?,?,?,?)
        """, (platform, table, 50, 50, predict, aiHit, now()))
    else:
        bankerScore = row["bankerScore"]
        playerScore = row["playerScore"]

        if result == "B":
            bankerScore += 1.5
            playerScore -= 0.5
        elif result == "P":
            playerScore += 1.5
            bankerScore -= 0.5

        bankerScore = max(1, bankerScore)
        playerScore = max(1, playerScore)

        conn.execute("""
        UPDATE ai_learning
        SET bankerScore=?, playerScore=?, totalPredict=?, totalHit=?, updatedAt=?
        WHERE id=?
        """, (
            bankerScore,
            playerScore,
            row["totalPredict"] + predict,
            row["totalHit"] + aiHit,
            now(),
            row["id"]
        ))

    conn.commit()
    conn.close()

    return suggestCode, aiHit


def ai_accuracy():
    conn = get_db()

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    def calc(where, params):
        rows = conn.execute(f"""
        SELECT aiHit FROM records
        WHERE aiSuggest IN ('B','P')
        AND countBet=1
        {where}
        """, params).fetchall()

        if not rows:
            return 0

        hit = len([x for x in rows if x["aiHit"]])
        return round((hit / len(rows)) * 100, 1)

    result = {
        "today": calc("AND DATE(created_at)=?", (today,)),
        "yesterday": calc("AND DATE(created_at)=?", (yesterday,)),
        "week": calc("AND DATE(created_at)>=?", (week,))
    }

    conn.close()
    return result


@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/admin")
def admin_page():
    if not session.get("admin"):
        return redirect("/admin-login")
    return render_template("admin.html")


@app.route("/admin-login")
def admin_login_page():
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    conn = get_db()
    user = conn.execute("""
    SELECT * FROM members
    WHERE username=? AND password=? AND enabled=1
    """, (username, password)).fetchone()

    if not user:
        conn.close()
        return jsonify({"ok": False, "msg": "帳號或密碼錯誤"})

    try:
        expire = datetime.strptime(user["expire"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expire:
            conn.close()
            return jsonify({"ok": False, "msg": "會員已到期"})
    except Exception:
        pass

    conn.execute("""
    UPDATE members
    SET lastLogin=?, lastActive=?, device=?, ip=?
    WHERE username=?
    """, (now(), now(), get_device(), get_ip(), username))

    conn.commit()
    conn.close()

    session["user"] = username
    return jsonify({"ok": True})


@app.route("/api/admin-login", methods=["POST"])
def api_admin_login():
    data = request.json or {}

    if data.get("username") == ADMIN_USER and data.get("password") == ADMIN_PASS:
        session["admin"] = True
        return jsonify({"ok": True})

    return jsonify({"ok": False, "msg": "帳號密碼錯誤"})


@app.route("/api/tables")
def api_tables():
    platform = request.args.get("platform", "DG")
    return jsonify(get_tables(platform))


@app.route("/api/data")
def api_data():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", get_tables(platform)[0])

    update_online(platform, table)

    records = get_records(platform, table)
    stats = analyze(records)

    conn = get_db()
    user = conn.execute("SELECT * FROM members WHERE username=?", (session["user"],)).fetchone()
    conn.close()

    return jsonify({
        "ok": True,
        "records": records,
        "stats": stats,
        "betCount": stats["betCount"],
        "memberExpireTime": user["expire"] if user else "-"
    })


@app.route("/api/manual", methods=["POST"])
def api_manual():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    data = request.json or {}

    platform = data.get("platform")
    table = data.get("table")
    result = data.get("result")

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False, "msg": "結果錯誤"})

    update_online(platform, table)

    before = get_records(platform, table)
    suggest = analyze(before)["suggest"]
    suggestCode, aiHit = update_learning(platform, table, result, suggest)

    conn = get_db()
    conn.execute("""
    INSERT INTO records(platform,table_name,result,cards,source,countBet,aiSuggest,aiHit,created_at)
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (
        platform,
        table,
        result,
        "",
        "manual",
        0,
        suggestCode,
        aiHit,
        now()
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def api_cards():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    data = request.json or {}

    platform = data.get("platform")
    table = data.get("table")
    cards = data.get("cards", [])

    calc = calc_cards(cards)

    if not calc:
        return jsonify({"ok": False, "msg": "牌型錯誤"})

    update_online(platform, table)

    result = calc["result"]

    before = get_records(platform, table)
    suggest = analyze(before)["suggest"]
    suggestCode, aiHit = update_learning(platform, table, result, suggest)

    conn = get_db()
    conn.execute("""
    INSERT INTO records(platform,table_name,result,cards,source,countBet,aiSuggest,aiHit,created_at)
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (
        platform,
        table,
        result,
        json.dumps(cards),
        "cards",
        1,
        suggestCode,
        aiHit,
        now()
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "result": result})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    data = request.json or {}

    platform = data.get("platform")
    table = data.get("table")

    conn = get_db()
    row = conn.execute("""
    SELECT id FROM records
    WHERE platform=? AND table_name=?
    ORDER BY id DESC
    LIMIT 1
    """, (platform, table)).fetchone()

    if row:
        conn.execute("DELETE FROM records WHERE id=?", (row["id"],))
        conn.commit()

    conn.close()

    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    data = request.json or {}

    conn = get_db()
    conn.execute("""
    DELETE FROM records
    WHERE platform=? AND table_name=?
    """, (data.get("platform"), data.get("table")))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin-data")
def api_admin_data():
    if not session.get("admin"):
        return jsonify({"ok": False})

    conn = get_db()

    members_rows = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    members = []

    now_dt = datetime.now()

    for m in members_rows:
        online = False

        if m["lastActive"]:
            try:
                last = datetime.strptime(m["lastActive"], "%Y-%m-%d %H:%M:%S")
                online = (now_dt - last).total_seconds() <= 300
            except Exception:
                online = False

        members.append({
            "id": m["id"],
            "username": m["username"],
            "password": m["password"],
            "expire": m["expire"],
            "enabled": bool(m["enabled"]),
            "role": m["role"],
            "currentPlatform": m["currentPlatform"],
            "currentTable": m["currentTable"],
            "device": m["device"],
            "ip": m["ip"],
            "lastLogin": m["lastLogin"],
            "lastActive": m["lastActive"],
            "online": online
        })

    tables = []
    totalRounds = 0
    totalBets = 0

    for platform in ["DG", "MT"]:
        for table in get_tables(platform):
            records = get_records(platform, table)
            stats = analyze(records)

            model = conn.execute("""
            SELECT * FROM ai_learning
            WHERE platform=? AND table_name=?
            """, (platform, table)).fetchone()

            aiHitRate = 0
            modelRounds = 0

            if model:
                modelRounds = model["totalPredict"]
                if model["totalPredict"]:
                    aiHitRate = round((model["totalHit"] / model["totalPredict"]) * 100, 1)

            totalRounds += len(records)
            totalBets += stats["betCount"]

            tables.append({
                "platform": platform,
                "table": table,
                "records": records[-36:],
                **stats,
                "aiHitRate": aiHitRate,
                "modelRounds": modelRounds,
                "rounds": len(records),
                "hot": len(records) >= 10,
                "cold": len(records) == 0
            })

    conn.close()

    ranking = sorted(tables, key=lambda x: x["aiHitRate"], reverse=True)

    return jsonify({
        "ok": True,
        "members": members,
        "tables": tables,
        "ranking": ranking[:10],
        "onlineCount": len([m for m in members if m["online"]]),
        "totalTables": len(tables),
        "totalRounds": totalRounds,
        "totalBets": totalBets,
        "aiAccuracy": ai_accuracy()
    })


@app.route("/api/admin/member/add", methods=["POST"])
def api_add_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    expire = data.get("expire", "").strip()
    role = data.get("role", "member")

    if not username or not password or not expire:
        return jsonify({"ok": False, "msg": "資料不完整"})

    conn = get_db()

    try:
        conn.execute("""
        INSERT INTO members(username,password,expire,enabled,role,createdAt)
        VALUES(?,?,?,?,?,?)
        """, (username, password, expire, 1, role, now()))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({"ok": False, "msg": str(e)})

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/member/update", methods=["POST"])
def api_update_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    conn = get_db()
    conn.execute("""
    UPDATE members
    SET password=?, expire=?, role=?
    WHERE id=?
    """, (
        data.get("password"),
        data.get("expire"),
        data.get("role", "member"),
        data.get("id")
    ))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/member/toggle", methods=["POST"])
def api_toggle_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    conn = get_db()
    row = conn.execute("SELECT enabled FROM members WHERE id=?", (data.get("id"),)).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False})

    new_val = 0 if row["enabled"] else 1

    conn.execute("UPDATE members SET enabled=? WHERE id=?", (new_val, data.get("id")))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/member/delete", methods=["POST"])
def api_delete_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({"ok": False, "msg": "管理員密碼錯誤"})

    conn = get_db()
    conn.execute("DELETE FROM members WHERE id=?", (data.get("id"),))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/clear-table", methods=["POST"])
def api_admin_clear_table():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({"ok": False, "msg": "管理員密碼錯誤"})

    conn = get_db()
    conn.execute("""
    DELETE FROM records
    WHERE platform=? AND table_name=?
    """, (data.get("platform"), data.get("table")))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/clear-all", methods=["POST"])
def api_admin_clear_all():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json or {}

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({"ok": False, "msg": "管理員密碼錯誤"})

    conn = get_db()
    conn.execute("DELETE FROM records")
    conn.execute("DELETE FROM ai_learning")
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
