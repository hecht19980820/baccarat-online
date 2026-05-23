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
MT_TABLES = ["01","02","03","03A","05","06","07","08","09","10"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cur, table, col, typ):
    cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


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
        agent_id INTEGER DEFAULT 0,
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
        player_point INTEGER DEFAULT 0,
        banker_point INTEGER DEFAULT 0,
        player_pair INTEGER DEFAULT 0,
        banker_pair INTEGER DEFAULT 0,
        lucky6 INTEGER DEFAULT 0,
        tie INTEGER DEFAULT 0,
        source TEXT DEFAULT '',
        count_bet INTEGER DEFAULT 0,
        ai_learn INTEGER DEFAULT 1,
        ai_suggest_before TEXT DEFAULT '',
        ai_hit INTEGER DEFAULT 0,
        member TEXT DEFAULT '',
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_models(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        banker_weight REAL DEFAULT 50,
        player_weight REAL DEFAULT 50,
        total_rounds INTEGER DEFAULT 0,
        total_hit INTEGER DEFAULT 0,
        total_predict INTEGER DEFAULT 0,
        updated_at TEXT,
        UNIQUE(platform, table_name)
    )
    """)

    for col, typ in [
        ("role", "TEXT DEFAULT 'member'"),
        ("agent_id", "INTEGER DEFAULT 0"),
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
        ("player_point", "INTEGER DEFAULT 0"),
        ("banker_point", "INTEGER DEFAULT 0"),
        ("player_pair", "INTEGER DEFAULT 0"),
        ("banker_pair", "INTEGER DEFAULT 0"),
        ("lucky6", "INTEGER DEFAULT 0"),
        ("tie", "INTEGER DEFAULT 0"),
        ("source", "TEXT DEFAULT ''"),
        ("count_bet", "INTEGER DEFAULT 0"),
        ("ai_learn", "INTEGER DEFAULT 1"),
        ("ai_suggest_before", "TEXT DEFAULT ''"),
        ("ai_hit", "INTEGER DEFAULT 0"),
        ("member", "TEXT DEFAULT ''")
    ]:
        ensure_column(cur, "records", col, typ)

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members(username,password,expire,enabled,role,agent_id,createdAt)
        VALUES(?,?,?,?,?,?,?)
        """, ("test01", "123456", "2026-12-31 23:59:59", 1, "member", 0, now()))

    conn.commit()
    conn.close()


def get_tables(platform):
    return MT_TABLES if platform == "MT" else DG_TABLES


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


def row_record(r):
    return {
        "id": r["id"],
        "platform": r["platform"],
        "table": r["table_name"],
        "result": r["result"],
        "cards": json.loads(r["cards"]) if r["cards"] else [],
        "playerPoint": r["player_point"],
        "bankerPoint": r["banker_point"],
        "playerPair": bool(r["player_pair"]),
        "bankerPair": bool(r["banker_pair"]),
        "lucky6": bool(r["lucky6"]),
        "tie": bool(r["tie"]),
        "source": r["source"],
        "countBet": bool(r["count_bet"]),
        "aiLearn": bool(r["ai_learn"]),
        "aiSuggestBefore": r["ai_suggest_before"],
        "aiHit": bool(r["ai_hit"]),
        "member": r["member"],
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
    return [row_record(r) for r in rows]


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

        if banker_point > player_point:
            result = "B"
        elif player_point > banker_point:
            result = "P"
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


def analyze(records):
    bp = [x for x in records if x["result"] in ["B", "P"]]
    valid = [x for x in records if x["result"] in ["B", "P", "T"]]

    banker = len([x for x in bp if x["result"] == "B"])
    player = len([x for x in bp if x["result"] == "P"])
    tie = len([x for x in valid if x["result"] == "T"])
    total = len(bp)

    banker_rate = round((banker / total) * 100, 1) if total else 0
    player_rate = round((player / total) * 100, 1) if total else 0

    recent = [x["result"] for x in bp][-20:]
    recent10 = recent[-10:]

    banker_score = 50
    player_score = 50
    alerts = []

    for i, r in enumerate(recent):
        weight = i + 1

        if r == "B":
            banker_score += weight * 0.35
        elif r == "P":
            player_score += weight * 0.35

    banker_score += recent10.count("B") * 1.8
    player_score += recent10.count("P") * 1.8

    streak_result = None
    streak_count = 0

    for x in reversed(bp):
        r = x["result"]

        if streak_result is None:
            streak_result = r
            streak_count = 1
        elif r == streak_result:
            streak_count += 1
        else:
            break

    if streak_result == "B":
        banker_score += min(streak_count * 3, 18)
    elif streak_result == "P":
        player_score += min(streak_count * 3, 18)

    if streak_count >= 4:
        alerts.append(("莊" if streak_result == "B" else "閒") + f" {streak_count} 連")

    recent_cards = valid[-20:]

    if len([x for x in recent_cards if x.get("bankerPair")]) >= 3:
        banker_score += 3
        alerts.append("莊對偏熱")

    if len([x for x in recent_cards if x.get("playerPair")]) >= 3:
        player_score += 3
        alerts.append("閒對偏熱")

    if len([x for x in recent_cards if x.get("lucky6")]) >= 2:
        banker_score += 4
        alerts.append("幸運6偏熱")

    diff = abs(banker_score - player_score)

    if total < 6:
        suggest = "觀望"
        stable_rate = 0
        alerts.append("資料不足")
    elif diff < 6:
        suggest = "觀望"
        stable_rate = round(50 + diff, 1)
    elif banker_score > player_score:
        suggest = "莊"
        stable_rate = round(min(96, 50 + diff), 1)
    else:
        suggest = "閒"
        stable_rate = round(min(96, 50 + diff), 1)

    return {
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "tieCount": tie,
        "suggest": suggest,
        "stableRate": stable_rate,
        "streakResult": streak_result,
        "streakCount": streak_count,
        "alerts": alerts[:3],
        "totalAnalysis": total,
        "bankerScore": round(banker_score, 1),
        "playerScore": round(player_score, 1),
        "betCount": len([x for x in records if x.get("countBet")])
    }


def update_ai_model(platform, table, suggest_code, result):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO ai_models(
        platform,table_name,banker_weight,player_weight,
        total_rounds,total_hit,total_predict,updated_at
    )
    VALUES(?,?,?,?,?,?,?,?)
    """, (platform, table, 50, 50, 0, 0, 0, now()))

    hit = 1 if suggest_code in ["B", "P"] and suggest_code == result else 0
    predict = 1 if suggest_code in ["B", "P"] else 0

    if result == "B":
        cur.execute("""
        UPDATE ai_models
        SET banker_weight=banker_weight+0.8,
            player_weight=player_weight-0.2,
            total_rounds=total_rounds+1,
            total_hit=total_hit+?,
            total_predict=total_predict+?,
            updated_at=?
        WHERE platform=? AND table_name=?
        """, (hit, predict, now(), platform, table))

    elif result == "P":
        cur.execute("""
        UPDATE ai_models
        SET player_weight=player_weight+0.8,
            banker_weight=banker_weight-0.2,
            total_rounds=total_rounds+1,
            total_hit=total_hit+?,
            total_predict=total_predict+?,
            updated_at=?
        WHERE platform=? AND table_name=?
        """, (hit, predict, now(), platform, table))

    else:
        cur.execute("""
        UPDATE ai_models
        SET total_rounds=total_rounds+1,
            total_hit=total_hit+?,
            total_predict=total_predict+?,
            updated_at=?
        WHERE platform=? AND table_name=?
        """, (hit, predict, now(), platform, table))

    conn.commit()
    conn.close()


def ai_accuracy():
    conn = get_db()

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    def calc(where, params):
        rows = conn.execute(f"""
            SELECT ai_hit FROM records
            WHERE ai_suggest_before IN ('B','P')
            AND count_bet=1
            {where}
        """, params).fetchall()

        if not rows:
            return 0

        hit = len([x for x in rows if x["ai_hit"]])
        return round((hit / len(rows)) * 100, 1)

    data = {
        "today": calc("AND DATE(created_at)=?", (today,)),
        "yesterday": calc("AND DATE(created_at)=?", (yesterday,)),
        "week": calc("AND DATE(created_at)>=?", (week,))
    }

    conn.close()
    return data


def update_member_online(platform="", table=""):
    username = session.get("user")

    if not username:
        return

    conn = get_db()
    conn.execute("""
    UPDATE members
    SET currentPlatform=?,
        currentTable=?,
        device=?,
        ip=?,
        lastActive=?
    WHERE username=?
    """, (
        platform,
        table,
        detect_device(),
        client_ip(),
        now(),
        username
    ))
    conn.commit()
    conn.close()


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
def login():
    data = request.json
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
        exp = datetime.strptime(user["expire"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > exp:
            conn.close()
            return jsonify({"ok": False, "msg": "會員已到期"})
    except:
        pass

    conn.execute("""
    UPDATE members
    SET lastLogin=?, lastActive=?, device=?, ip=?
    WHERE username=?
    """, (now(), now(), detect_device(), client_ip(), username))

    conn.commit()
    conn.close()

    session["user"] = username

    return jsonify({"ok": True})


@app.route("/api/admin-login", methods=["POST"])
def admin_login_api():
    data = request.json

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

    update_member_online(platform, table)

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

    data = request.json

    platform = data.get("platform")
    table = data.get("table")
    result = data.get("result")

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False, "msg": "結果錯誤"})

    update_member_online(platform, table)

    before = get_records(platform, table)
    suggest = analyze(before)["suggest"]

    suggest_code = "B" if suggest == "莊" else "P" if suggest == "閒" else ""
    ai_hit = 1 if suggest_code == result else 0

    conn = get_db()
    conn.execute("""
    INSERT INTO records(
        platform,table_name,result,cards,source,count_bet,ai_learn,
        ai_suggest_before,ai_hit,member,created_at
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, table, result, "", "manual", 0, 1,
        suggest_code, ai_hit, session["user"], now()
    ))
    conn.commit()
    conn.close()

    update_ai_model(platform, table, suggest_code, result)

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def api_cards():
    if "user" not in session:
        return jsonify({"ok": False, "msg": "未登入"})

    data = request.json

    platform = data.get("platform")
    table = data.get("table")
    cards = data.get("cards", [])

    calc = calc_cards(cards)

    if calc is None:
        return jsonify({"ok": False, "msg": "牌數錯誤"})

    update_member_online(platform, table)

    before = get_records(platform, table)
    suggest = analyze(before)["suggest"]

    suggest_code = "B" if suggest == "莊" else "P" if suggest == "閒" else ""
    ai_hit = 1 if suggest_code == calc["result"] else 0

    conn = get_db()
    conn.execute("""
    INSERT INTO records(
        platform,table_name,result,cards,player_point,banker_point,
        player_pair,banker_pair,lucky6,tie,source,count_bet,ai_learn,
        ai_suggest_before,ai_hit,member,created_at
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        suggest_code,
        ai_hit,
        session["user"],
        now()
    ))
    conn.commit()
    conn.close()

    update_ai_model(platform, table, suggest_code, calc["result"])

    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    if "user" not in session:
        return jsonify({"ok": False})

    data = request.json

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
        return jsonify({"ok": False})

    data = request.json

    conn = get_db()
    conn.execute("""
    DELETE FROM records
    WHERE platform=? AND table_name=?
    """, (data.get("platform"), data.get("table")))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin-data")
def admin_data():
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
                t = datetime.strptime(m["lastActive"], "%Y-%m-%d %H:%M:%S")
                online = (now_dt - t).total_seconds() <= 300
            except:
                online = False

        members.append({
            "id": m["id"],
            "username": m["username"],
            "password": m["password"],
            "expire": m["expire"],
            "enabled": bool(m["enabled"]),
            "role": m["role"],
            "agentId": m["agent_id"],
            "currentPlatform": m["currentPlatform"],
            "currentTable": m["currentTable"],
            "device": m["device"],
            "ip": m["ip"],
            "lastLogin": m["lastLogin"],
            "lastActive": m["lastActive"],
            "online": online
        })

    tables = []
    total_rounds = 0
    total_bets = 0

    for platform in ["DG", "MT"]:
        for table in get_tables(platform):
            records = get_records(platform, table)
            stats = analyze(records)

            model = conn.execute("""
            SELECT * FROM ai_models
            WHERE platform=? AND table_name=?
            """, (platform, table)).fetchone()

            ai_hit_rate = 0

            if model and model["total_predict"]:
                ai_hit_rate = round((model["total_hit"] / model["total_predict"]) * 100, 1)

            total_rounds += len(records)
            total_bets += stats["betCount"]

            tables.append({
                "platform": platform,
                "table": table,
                "records": records[-36:],
                **stats,
                "aiHitRate": ai_hit_rate,
                "modelRounds": model["total_rounds"] if model else 0,
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
        "onlineCount": len([x for x in members if x["online"]]),
        "totalTables": len(tables),
        "totalRounds": total_rounds,
        "totalBets": total_bets,
        "aiAccuracy": ai_accuracy()
    })


@app.route("/api/admin/member/add", methods=["POST"])
def add_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    expire = data.get("expire", "").strip()
    role = data.get("role", "member")
    agent_id = data.get("agentId", 0)

    if not username or not password or not expire:
        return jsonify({"ok": False, "msg": "資料不完整"})

    conn = get_db()

    try:
        conn.execute("""
        INSERT INTO members(username,password,expire,enabled,role,agent_id,createdAt)
        VALUES(?,?,?,?,?,?,?)
        """, (username, password, expire, 1, role, agent_id, now()))
        conn.commit()

    except Exception as e:
        conn.close()
        return jsonify({"ok": False, "msg": str(e)})

    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/member/update", methods=["POST"])
def update_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

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
def toggle_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

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
def delete_member():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({"ok": False, "msg": "管理員密碼錯誤"})

    conn = get_db()
    conn.execute("DELETE FROM members WHERE id=?", (data.get("id"),))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/clear-table", methods=["POST"])
def admin_clear_table():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

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
def clear_all():
    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({"ok": False, "msg": "管理員密碼錯誤"})

    conn = get_db()
    conn.execute("DELETE FROM records")
    conn.execute("DELETE FROM ai_models")
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/manual", methods=["POST"])
def api_manual():

    if "user" not in session:
        return jsonify({"ok":False})

    data = request.json

    platform = data.get("platform")
    table = data.get("table")
    result = data.get("result")

    if result not in ["B","P","T"]:
        return jsonify({"ok":False,"msg":"錯誤結果"})

    conn = get_db()

    conn.execute("""
    INSERT INTO records(
        platform,
        table_name,
        result,
        source,
        created_at
    )
    VALUES(?,?,?,?,?)
    """,(
        platform,
        table,
        result,
        "manual",
        now()
    ))

    conn.commit()
    conn.close()

    update_online(platform, table)

    return jsonify({"ok":True})


@app.route("/api/cards", methods=["POST"])
def api_cards():

    if "user" not in session:
        return jsonify({"ok":False})

    data = request.json

    platform = data.get("platform")
    table = data.get("table")
    cards = data.get("cards", [])

    resultData = calc_cards(cards)

    if not resultData:
        return jsonify({
            "ok":False,
            "msg":"牌型錯誤"
        })

    result = resultData["result"]

    conn = get_db()

    rows = conn.execute("""
    SELECT result
    FROM records
    WHERE platform=? AND table_name=?
    ORDER BY id DESC
    LIMIT 20
    """,(platform,table)).fetchall()

    recent = [r["result"] for r in rows]

    suggest = "觀望"

    if recent:
        banker = recent.count("B")
        player = recent.count("P")

        if banker > player:
            suggest = "莊"
        elif player > banker:
            suggest = "閒"

    aiHit = 0

    if (
        (suggest == "莊" and result == "B") or
        (suggest == "閒" and result == "P")
    ):
        aiHit = 1

    conn.execute("""
    INSERT INTO records(
        platform,
        table_name,
        result,
        cards,
        source,
        countBet,
        aiSuggest,
        aiHit,
        created_at
    )
    VALUES(?,?,?,?,?,?,?,?,?)
    """,(
        platform,
        table,
        result,
        json.dumps(cards),
        "cards",
        1,
        suggest,
        aiHit,
        now()
    ))

    learn = conn.execute("""
    SELECT *
    FROM ai_learning
    WHERE platform=? AND table_name=?
    """,(platform,table)).fetchone()

    if learn:

        totalPredict = learn["totalPredict"] + 1
        totalHit = learn["totalHit"] + aiHit

        bankerScore = learn["bankerScore"]
        playerScore = learn["playerScore"]

        if result == "B":
            bankerScore += 1.5
            playerScore -= .8

        elif result == "P":
            playerScore += 1.5
            bankerScore -= .8

        bankerScore = max(1, bankerScore)
        playerScore = max(1, playerScore)

        conn.execute("""
        UPDATE ai_learning
        SET
            bankerScore=?,
            playerScore=?,
            totalPredict=?,
            totalHit=?,
            updatedAt=?
        WHERE id=?
        """,(
            bankerScore,
            playerScore,
            totalPredict,
            totalHit,
            now(),
            learn["id"]
        ))

    else:

        conn.execute("""
        INSERT INTO ai_learning(
            platform,
            table_name,
            bankerScore,
            playerScore,
            totalPredict,
            totalHit,
            updatedAt
        )
        VALUES(?,?,?,?,?,?,?)
        """,(
            platform,
            table,
            50,
            50,
            1,
            aiHit,
            now()
        ))

    conn.commit()
    conn.close()

    update_online(platform, table)

    return jsonify({
        "ok":True,
        "result":result
    })


@app.route("/api/undo", methods=["POST"])
def api_undo():

    if "user" not in session:
        return jsonify({"ok":False})

    data = request.json

    platform = data.get("platform")
    table = data.get("table")

    conn = get_db()

    row = conn.execute("""
    SELECT id
    FROM records
    WHERE platform=? AND table_name=?
    ORDER BY id DESC
    LIMIT 1
    """,(platform,table)).fetchone()

    if row:

        conn.execute("""
        DELETE FROM records
        WHERE id=?
        """,(row["id"],))

        conn.commit()

    conn.close()

    return jsonify({"ok":True})


@app.route("/api/clear", methods=["POST"])
def api_clear():

    if "user" not in session:
        return jsonify({"ok":False})

    data = request.json

    platform = data.get("platform")
    table = data.get("table")

    conn = get_db()

    conn.execute("""
    DELETE FROM records
    WHERE platform=? AND table_name=?
    """,(platform,table))

    conn.commit()
    conn.close()

    return jsonify({"ok":True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
