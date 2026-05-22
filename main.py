from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime, timedelta
import sqlite3
import json

app = Flask(__name__)
app.secret_key = "baccarat_admin_secret_2026"

DB_PATH = "baccarat_system.db"

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07","RB08","RB09","RB10"]
MT_TABLES = ["01","02","03","03A","05","06","07","08","09","10"]

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        player_point INTEGER,
        banker_point INTEGER,
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

    cur.execute("SELECT COUNT(*) AS c FROM members WHERE username='test01'")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
        INSERT INTO members
        (username,password,expire,enabled,created_at,last_login,last_active,current_platform,current_table,ip,device)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            "test01",
            "123456",
            "2026-12-31 23:59:59",
            1,
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


def table_key(platform, table):
    return f"{platform}_{table}"


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


def update_member_active(platform=None, table=None):
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
        platform or "",
        table or "",
        request.headers.get("X-Forwarded-For", request.remote_addr),
        detect_device(),
        username
    ))
    conn.commit()
    conn.close()


def get_member(username):
    conn = db()
    row = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def member_expire_time(username):
    row = get_member(username)
    return row["expire"] if row else "-"


def calc_cards(cards):
    try:
        nums = [int(x) for x in cards]

        if len(nums) < 4 or len(nums) > 6:
            return None

        player_cards = []
        banker_cards = []

        # 固定：閒1 莊1 閒2 莊2 閒3 莊3
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
    valid = [x for x in data if x.get("result") in ["B", "P", "T"]]
    bp = [x for x in valid if x.get("result") in ["B", "P"]]

    bet_count = len([x for x in data if x.get("countBet")])
    b_count = len([x for x in bp if x["result"] == "B"])
    p_count = len([x for x in bp if x["result"] == "P"])
    t_count = len([x for x in valid if x["result"] == "T"])

    total_bp = len(bp)

    banker_rate = round((b_count / total_bp) * 100, 1) if total_bp else 0
    player_rate = round((p_count / total_bp) * 100, 1) if total_bp else 0

    recent = [x["result"] for x in bp][-20:]
    recent10 = recent[-10:]
    recent6 = recent[-6:]

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

    for item in reversed(bp):
        r = item["result"]
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

    if len(recent6) == 6:
        if recent6 == ["B","P","B","P","B","P"]:
            banker_score += 8
            alerts.append("跳路偏莊")
        elif recent6 == ["P","B","P","B","P","B"]:
            player_score += 8
            alerts.append("跳路偏閒")

    recent_cards = valid[-20:]

    banker_pair_count = len([x for x in recent_cards if x.get("bankerPair")])
    player_pair_count = len([x for x in recent_cards if x.get("playerPair")])
    lucky6_count = len([x for x in recent_cards if x.get("lucky6")])
    tie_count = len([x for x in recent_cards if x.get("tie")])

    if banker_pair_count >= 3:
        banker_score += 3
        alerts.append("莊對偏熱")

    if player_pair_count >= 3:
        player_score += 3
        alerts.append("閒對偏熱")

    if lucky6_count >= 2:
        banker_score += 4
        alerts.append("幸運6偏熱")

    if tie_count >= 2:
        alerts.append("和局偏熱")

    diff = abs(banker_score - player_score)

    if total_bp < 6:
        suggest = "觀望"
        stable_rate = 0
        alerts.append("資料不足")
    elif diff < 6:
        suggest = "觀望"
        stable_rate = round(50 + diff, 1)
        alerts.append("莊閒不明顯")
    elif banker_score > player_score:
        suggest = "莊"
        stable_rate = round(min(92, 50 + diff), 1)
    else:
        suggest = "閒"
        stable_rate = round(min(92, 50 + diff), 1)

    return {
        "totalAnalysis": total_bp,
        "betCount": bet_count,
        "bankerRate": banker_rate,
        "playerRate": player_rate,
        "tieCount": t_count,
        "streakResult": streak_result,
        "streakCount": streak_count,
        "suggest": suggest,
        "stableRate": stable_rate,
        "alerts": alerts[:3],
        "bankerScore": round(banker_score, 1),
        "playerScore": round(player_score, 1)
    }


def ai_accuracy():
    conn = db()

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    seven_days = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    def calc(where, params):
        rows = conn.execute(f"""
            SELECT ai_hit FROM records
            WHERE ai_suggest_before IN ('B','P')
            AND count_bet=1
            {where}
        """, params).fetchall()

        if not rows:
            return 0

        hit = len([r for r in rows if r["ai_hit"]])
        return round((hit / len(rows)) * 100, 1)

    today_acc = calc("AND DATE(created_at)=?", (today,))
    yesterday_acc = calc("AND DATE(created_at)=?", (yesterday,))
    week_acc = calc("AND DATE(created_at)>=?", (seven_days,))

    conn.close()

    return {
        "today": today_acc,
        "yesterday": yesterday_acc,
        "week": week_acc
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        member = get_member(username)

        if not member:
            return render_template("login.html", error="帳號不存在")

        if not member["enabled"]:
            return render_template("login.html", error="會員已停權")

        if member["password"] != password:
            return render_template("login.html", error="密碼錯誤")

        expire_time = datetime.strptime(member["expire"], "%Y-%m-%d %H:%M:%S")

        if datetime.now() > expire_time:
            return render_template("login.html", error="會員已到期")

        conn = db()
        conn.execute("""
        UPDATE members
        SET last_login=?, last_active=?, ip=?, device=?
        WHERE username=?
        """, (
            now(),
            now(),
            request.headers.get("X-Forwarded-For", request.remote_addr),
            detect_device(),
            username
        ))
        conn.commit()
        conn.close()

        session["member"] = username
        return redirect("/")

    return render_template("login.html")


@app.route("/")
def index():
    if not session.get("member"):
        return redirect("/login")
    return render_template("index.html")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin"] = True
            return redirect("/admin")

        return render_template("admin_login.html", error="帳號或密碼錯誤")

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


@app.route("/api/tables")
def tables():
    platform = request.args.get("platform", "DG")
    return jsonify(MT_TABLES if platform == "MT" else DG_TABLES)


@app.route("/api/data")
def get_data():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    update_member_active(platform, table)

    data = get_records(platform, table)

    return jsonify({
        "ok": True,
        "records": data,
        "betCount": len([x for x in data if x.get("countBet")]),
        "memberExpireTime": member_expire_time(session.get("member")),
        "stats": road_stats(data)
    })


@app.route("/api/admin-data")
def admin_data():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    all_tables = []
    total_rounds = 0
    total_bets = 0

    for platform, tables in {"DG": DG_TABLES, "MT": MT_TABLES}.items():
        for table in tables:
            data = get_records(platform, table)
            stats = road_stats(data)

            total_rounds += len(data)
            total_bets += stats["betCount"]

            all_tables.append({
                "platform": platform,
                "table": table,
                "rounds": len(data),
                "betCount": stats["betCount"],
                "suggest": stats["suggest"],
                "stableRate": stats["stableRate"],
                "bankerRate": stats["bankerRate"],
                "playerRate": stats["playerRate"],
                "tieCount": stats["tieCount"],
                "streakResult": stats["streakResult"],
                "streakCount": stats["streakCount"],
                "bankerScore": stats["bankerScore"],
                "playerScore": stats["playerScore"],
                "alerts": stats["alerts"],
                "records": data[-36:]
            })

    conn = db()
    members_rows = conn.execute("SELECT * FROM members ORDER BY id DESC").fetchall()
    conn.close()

    now_dt = datetime.now()
    member_list = []

    for m in members_rows:
        online = False

        if m["last_active"]:
            try:
                active_time = datetime.strptime(m["last_active"], "%Y-%m-%d %H:%M:%S")
                online = (now_dt - active_time).total_seconds() <= 300
            except:
                online = False

        member_list.append({
            "id": m["id"],
            "username": m["username"],
            "password": m["password"],
            "expire": m["expire"],
            "enabled": bool(m["enabled"]),
            "createdAt": m["created_at"],
            "lastLogin": m["last_login"],
            "lastActive": m["last_active"],
            "currentPlatform": m["current_platform"],
            "currentTable": m["current_table"],
            "ip": m["ip"],
            "device": m["device"],
            "online": online
        })

    acc = ai_accuracy()

    return jsonify({
        "ok": True,
        "totalRounds": total_rounds,
        "totalBets": total_bets,
        "totalTables": len(all_tables),
        "tables": all_tables,
        "members": member_list,
        "onlineCount": len([m for m in member_list if m["online"]]),
        "aiAccuracy": acc
    })


@app.route("/api/admin/member/add", methods=["POST"])
def admin_member_add():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    expire = body.get("expire", "").strip()

    if not username or not password or not expire:
        return jsonify({"ok": False, "msg": "資料不完整"})

    conn = db()
    try:
        conn.execute("""
        INSERT INTO members
        (username,password,expire,enabled,created_at,last_login,last_active,current_platform,current_table,ip,device)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (username, password, expire, 1, now(), "", "", "", "", "", ""))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "msg": "帳號已存在"})

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/member/update", methods=["POST"])
def admin_member_update():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json
    member_id = body.get("id")
    password = body.get("password", "").strip()
    expire = body.get("expire", "").strip()

    if not member_id or not password or not expire:
        return jsonify({"ok": False, "msg": "資料不完整"})

    conn = db()
    conn.execute("UPDATE members SET password=?, expire=? WHERE id=?", (password, expire, member_id))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/member/toggle", methods=["POST"])
def admin_member_toggle():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json
    member_id = body.get("id")

    conn = db()
    m = conn.execute("SELECT enabled FROM members WHERE id=?", (member_id,)).fetchone()

    if not m:
        conn.close()
        return jsonify({"ok": False})

    new_status = 0 if m["enabled"] else 1

    conn.execute("UPDATE members SET enabled=? WHERE id=?", (new_status, member_id))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/member/delete", methods=["POST"])
def admin_member_delete():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json
    member_id = body.get("id")

    conn = db()
    conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/clear-table", methods=["POST"])
def admin_clear_table():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    body = request.json
    platform = body.get("platform")
    table = body.get("table")

    conn = db()
    conn.execute("DELETE FROM records WHERE platform=? AND table_no=?", (platform, table))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/admin/clear-all", methods=["POST"])
def admin_clear_all():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403

    conn = db()
    conn.execute("DELETE FROM records")
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/manual", methods=["POST"])
def manual_add():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    update_member_active(platform, table)

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False})

    data_before = get_records(platform, table)
    suggest_before = road_stats(data_before)["suggest"]
    suggest_code = "B" if suggest_before == "莊" else "P" if suggest_before == "閒" else ""

    ai_hit = 1 if suggest_code == result else 0

    conn = db()
    conn.execute("""
    INSERT INTO records
    (platform,table_no,result,cards,player_point,banker_point,
     player_pair,banker_pair,lucky6,tie,source,count_bet,ai_learn,
     ai_suggest_before,ai_hit,created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        platform, table, result, "",
        None, None,
        0, 0, 0, 1 if result == "T" else 0,
        "manual", 0, 1,
        suggest_code, ai_hit, now()
    ))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def cards_add():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    cards = body.get("cards", [])

    update_member_active(platform, table)

    calc = calc_cards(cards)

    if calc is None:
        return jsonify({"ok": False})

    data_before = get_records(platform, table)
    suggest_before = road_stats(data_before)["suggest"]
    suggest_code = "B" if suggest_before == "莊" else "P" if suggest_before == "閒" else ""

    ai_hit = 1 if suggest_code == calc["result"] else 0

    conn = db()
    conn.execute("""
    INSERT INTO records
    (platform,table_no,result,cards,player_point,banker_point,
     player_pair,banker_pair,lucky6,tie,source,count_bet,ai_learn,
     ai_suggest_before,ai_hit,created_at)
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
        suggest_code,
        ai_hit,
        now()
    ))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def undo():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json
    platform = body.get("platform")
    table = body.get("table")

    update_member_active(platform, table)

    conn = db()
    row = conn.execute("""
        SELECT id FROM records
        WHERE platform=? AND table_no=?
        ORDER BY id DESC
        LIMIT 1
    """, (platform, table)).fetchone()

    if row:
        conn.execute("DELETE FROM records WHERE id=?", (row["id"],))
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def clear():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json
    platform = body.get("platform")
    table = body.get("table")

    update_member_active(platform, table)

    conn = db()
    conn.execute("DELETE FROM records WHERE platform=? AND table_no=?", (platform, table))
    conn.commit()
    conn.close()

    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
