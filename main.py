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
        ("ai_hit", "INTEGER DEFAULT 0"),
        ("hidden", "INTEGER DEFAULT 0")
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
        ("username", "TEXT"),
        ("created_at", "TEXT")
    ]:
        ensure_column(cur, "shared_ai_stats", col, typ)

    for col, typ in [
        ("platform", "TEXT"),
        ("table_no", "TEXT"),
        ("status", "TEXT DEFAULT 'normal'"),
        ("note", "TEXT"),
        ("updated_at", "TEXT")
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
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def get_member(username):
    conn = db()
    row = conn.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def get_table_status_map():
    conn = db()
    rows = conn.execute("SELECT platform, table_no, status, note FROM table_status").fetchall()
    conn.close()
    return {(r["platform"], r["table_no"]): {"status": r["status"] or "normal", "note": r["note"] or ""} for r in rows}


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


def row_to_record(row):
    return {
        "id": row["id"], "platform": row["platform"], "table": row["table_no"],
        "result": row["result"], "cards": json.loads(row["cards"]) if row["cards"] else [],
        "playerPoint": row["player_point"], "bankerPoint": row["banker_point"],
        "playerPair": bool(row["player_pair"]), "bankerPair": bool(row["banker_pair"]),
        "lucky6": bool(row["lucky6"]), "tie": bool(row["tie"]), "source": row["source"],
        "countBet": bool(row["count_bet"]), "aiLearn": bool(row["ai_learn"]),
        "aiSuggestBefore": row["ai_suggest_before"], "aiHit": bool(row["ai_hit"]),
        "hidden": bool(row["hidden"]) if "hidden" in row.keys() else False,
        "createdAt": row["created_at"]
    }


def shared_row_to_record(row):
    return {
        "id": row["id"], "platform": row["platform"], "table": row["table_no"],
        "result": row["result"], "cards": json.loads(row["cards"]) if row["cards"] else [],
        "playerPoint": row["player_point"], "bankerPoint": row["banker_point"],
        "playerPair": bool(row["player_pair"]), "bankerPair": bool(row["banker_pair"]),
        "lucky6": bool(row["lucky6"]), "tie": bool(row["tie"]), "source": row["source"],
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


def get_ai_history(where_sql="", params=(), limit=600):
    conn = db()
    rows = conn.execute(f"""
    SELECT * FROM shared_ai_stats
    {where_sql}
    ORDER BY id DESC
    LIMIT ?
    """, (*params, limit)).fetchall()
    conn.close()
    return [shared_row_to_record(r) for r in reversed(rows)]


def get_mixed_ai_history(platform, table):
    return {
        "table": get_ai_history("WHERE platform=? AND table_no=?", (platform, table), 500),
        "platform": get_ai_history("WHERE platform=? AND table_no<>?", (platform, table), 500),
        "global": get_ai_history("WHERE NOT (platform=? AND table_no=?)", (platform, table), 500)
    }


def calc_pattern_routes(bp):
    results = [x["result"] if isinstance(x, dict) else x for x in bp]
    results = [r for r in results if r in ["B", "P"]]
    if not results:
        return {"cockroachBias": 0, "hollowBias": 0, "routePower": 0}
    switches = sum(1 for i in range(1, len(results)) if results[i] != results[i - 1])
    switch_rate = switches / max(1, len(results) - 1)
    groups = []
    current = results[0]
    count = 1
    for r in results[1:]:
        if r == current:
            count += 1
        else:
            groups.append((current, count))
            current = r
            count = 1
    groups.append((current, count))
    last = results[-1]
    opposite = "P" if last == "B" else "B"
    cockroach_bias = 0
    hollow_bias = 0
    if switch_rate >= 0.58:
        cockroach_bias = 7 if opposite == "B" else -7
    elif groups and groups[-1][1] >= 3:
        cockroach_bias = 6 if last == "B" else -6
    last_groups = groups[-6:]
    same_pair_count = len([g for g in last_groups if g[1] == 2])
    if same_pair_count >= 3:
        hollow_bias = 6 if last == "B" else -6
    elif len(last_groups) >= 4 and last_groups[-1][1] == 1 and last_groups[-2][1] == 1:
        hollow_bias = 5 if opposite == "B" else -5
    return {"cockroachBias": cockroach_bias, "hollowBias": hollow_bias, "routePower": abs(cockroach_bias) + abs(hollow_bias)}


def road_stats(data):
    valid = [x for x in data if x.get("result") in ["B", "P", "T"]]
    bp = [x for x in valid if x.get("result") in ["B", "P"]]
    b = len([x for x in bp if x["result"] == "B"])
    p = len([x for x in bp if x["result"] == "P"])
    t = len([x for x in valid if x["result"] == "T"])
    total = len(bp)
    banker_rate = round((b / total) * 100, 1) if total else 0
    player_rate = round((p / total) * 100, 1) if total else 0
    tie_rate = round((t / len(valid)) * 100, 1) if valid else 0
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
    jump_count = sum(1 for i in range(1, len(bp)) if bp[i]["result"] != bp[i - 1]["result"])
    jump_rate = round((jump_count / (len(bp) - 1)) * 100, 1) if len(bp) > 1 else 0
    route = calc_pattern_routes(bp)
    banker_score = 50 + (banker_rate - 50) * 0.55 + (recent_b - recent_p) * 2.6
    player_score = 50 + (player_rate - 50) * 0.55 + (recent_p - recent_b) * 2.6
    tie_score = max(1, min(18, tie_rate))
    lucky6_score = 3
    if streak_result == "B":
        banker_score += streak_count * 1.8
        if streak_count >= 4:
            player_score += 6
    elif streak_result == "P":
        player_score += streak_count * 1.8
        if streak_count >= 4:
            banker_score += 6
    if jump_rate >= 60:
        if bp and bp[-1]["result"] == "B":
            player_score += 7
        elif bp and bp[-1]["result"] == "P":
            banker_score += 7
    route_bias = route["cockroachBias"] + route["hollowBias"]
    if route_bias > 0:
        banker_score += route_bias
    elif route_bias < 0:
        player_score += abs(route_bias)
    card_rows = [x for x in valid if x.get("cards")]
    recent_cards = card_rows[-30:]
    lucky6_count = len([x for x in recent_cards if x.get("lucky6")])
    banker_point_6 = len([x for x in recent_cards if x.get("result") == "B" and x.get("bankerPoint") == 6])
    pair_count = len([x for x in recent_cards if x.get("playerPair") or x.get("bankerPair")])
    if recent_cards:
        lucky6_score += lucky6_count * 4 + banker_point_6 * 2
        tie_score += len([x for x in recent_cards if x.get("tie")]) * 3
        if pair_count >= 3:
            tie_score += 2
    banker_score = max(0, min(100, round(banker_score, 1)))
    player_score = max(0, min(100, round(player_score, 1)))
    tie_score = max(0, min(35, round(tie_score, 1)))
    lucky6_score = max(0, min(30, round(lucky6_score, 1)))
    suggest = "觀望"
    stable = max(banker_score, player_score)
    if banker_score >= player_score + 6 and banker_score >= 55:
        suggest = "莊"
        stable = banker_score
    elif player_score >= banker_score + 6 and player_score >= 55:
        suggest = "閒"
        stable = player_score
    alerts = []
    if streak_count >= 4: alerts.append("長龍注意，可能續龍或斷龍")
    if jump_rate >= 60: alerts.append("跳路偏高，注意反打")
    if len(bp) < 10: alerts.append("資料量不足，建議觀望")
    if tie_score >= 18: alerts.append("和局機率偏高")
    if lucky6_score >= 15: alerts.append("Lucky 6 機率偏高")
    if banker_score >= 65: alerts.append("莊方勝率偏高")
    if player_score >= 65: alerts.append("閒方勝率偏高")
    if not alerts: alerts.append("共享AI正常分析中")
    return {
        "bankerRate": banker_rate, "playerRate": player_rate, "tieRate": tie_rate,
        "bankerScore": banker_score, "playerScore": player_score,
        "tieScore": tie_score, "lucky6Score": lucky6_score,
        "tieCount": t, "suggest": suggest, "stableRate": stable,
        "betCount": len(valid), "totalAnalysis": len(valid),
        "streakResult": streak_result, "streakCount": streak_count,
        "jumpRate": jump_rate, "routePower": route["routePower"], "alerts": alerts
    }


def weighted_stats_for_table(platform, table, fallback_screen_data=None):
    mixed = get_mixed_ai_history(platform, table)
    table_stats = road_stats(mixed["table"] if mixed["table"] else (fallback_screen_data or []))
    platform_stats = road_stats(mixed["platform"])
    global_stats = road_stats(mixed["global"])
    weights = {"table": 0.70, "platform": 0.20, "global": 0.10}
    if not mixed["platform"]:
        weights["table"] += weights["platform"]
        weights["platform"] = 0
    if not mixed["global"]:
        weights["table"] += weights["global"]
        weights["global"] = 0
    def wavg(key):
        return round(table_stats.get(key, 0) * weights["table"] + platform_stats.get(key, 0) * weights["platform"] + global_stats.get(key, 0) * weights["global"], 1)
    banker_score = wavg("bankerScore")
    player_score = wavg("playerScore")
    tie_score = wavg("tieScore")
    lucky6_score = wavg("lucky6Score")
    stable = max(banker_score, player_score)
    suggest = "觀望"
    if banker_score >= player_score + 5 and banker_score >= 55:
        suggest = "莊"
    elif player_score >= banker_score + 5 and player_score >= 55:
        suggest = "閒"
    alerts = []
    alerts.extend(table_stats.get("alerts", []))
    if tie_score >= 18: alerts.append("和局機率偏高")
    if lucky6_score >= 15: alerts.append("Lucky 6 機率偏高")
    if not alerts: alerts.append("共享AI混合模型分析中")
    return {
        "bankerRate": wavg("bankerRate"), "playerRate": wavg("playerRate"), "tieRate": wavg("tieRate"),
        "bankerScore": banker_score, "playerScore": player_score, "tieScore": tie_score,
        "lucky6Score": lucky6_score, "suggest": suggest, "stableRate": stable,
        "betCount": len(fallback_screen_data or []),
        "totalAnalysis": table_stats.get("totalAnalysis", 0) + platform_stats.get("totalAnalysis", 0) + global_stats.get("totalAnalysis", 0),
        "streakResult": table_stats.get("streakResult"), "streakCount": table_stats.get("streakCount", 0),
        "jumpRate": table_stats.get("jumpRate", 0), "routePower": wavg("routePower"),
        "modelMix": "本桌70%＋同平台20%＋全站10%", "alerts": list(dict.fromkeys(alerts))[:6]
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
    if member["expire"]:
        try:
            expire_time = datetime.strptime(member["expire"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expire_time:
                conn = db()
                conn.execute("UPDATE members SET enabled=0 WHERE username=?", (username,))
                conn.commit()
                conn.close()
                return jsonify({"ok": False, "msg": "會員已到期，已自動停權"})
        except Exception:
            pass
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


@app.route("/api/admin/members")
def api_admin_members():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
    conn = db()
    rows = conn.execute("""
    SELECT id, username, expire, enabled, role, created_at, last_login, last_active,
           current_platform, current_table, ip, device
    FROM members
    ORDER BY id DESC
    """).fetchall()
    conn.close()
    return jsonify({"ok": True, "members": [dict(r) for r in rows]})


@app.route("/api/admin/create-member", methods=["POST"])
def api_admin_create_member():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    expire = normalize_expire(body.get("expire", "2026-12-31 23:59:59"))
    if not username or not password:
        return jsonify({"ok": False, "msg": "帳號密碼必填"})
    conn = db()
    try:
        conn.execute("""
        INSERT INTO members (username,password,expire,enabled,role,created_at)
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
        return jsonify({"ok": False, "msg": "未登入"}), 403
    body = request.json or {}
    username = body.get("username", "").strip()
    conn = db()
    row = conn.execute("SELECT enabled FROM members WHERE username=?", (username,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "msg": "找不到會員"})
    new_status = 0 if row["enabled"] else 1
    conn.execute("UPDATE members SET enabled=? WHERE username=?", (new_status, username))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/add-days", methods=["POST"])
def api_admin_add_days():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
    body = request.json or {}
    username = body.get("username", "").strip()
    days = int(body.get("days", 0))
    if not username or days <= 0:
        return jsonify({"ok": False, "msg": "資料錯誤"})
    member = get_member(username)
    if not member:
        return jsonify({"ok": False, "msg": "找不到會員"})
    try:
        old_expire = datetime.strptime(member["expire"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        old_expire = datetime.now()
    base_time = old_expire if old_expire > datetime.now() else datetime.now()
    new_expire = base_time.replace(microsecond=0) + timedelta(days=days)
    conn = db()
    conn.execute("UPDATE members SET expire=?, enabled=1 WHERE username=?", (new_expire.strftime("%Y-%m-%d %H:%M:%S"), username))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "msg": f"已補 {days} 天"})




@app.route("/api/admin/delete-member", methods=["POST"])
def api_admin_delete_member():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json or {}
    username = body.get("username", "").strip()

    if not username:
        return jsonify({"ok": False, "msg": "會員帳號錯誤"})

    conn = db()
    row = conn.execute("SELECT id FROM members WHERE username=?", (username,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False, "msg": "找不到會員"})

    conn.execute("DELETE FROM members WHERE username=?", (username,))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "msg": "會員已刪除"})


@app.route("/api/admin/update-member", methods=["POST"])
def api_admin_update_member():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json or {}
    old_username = body.get("oldUsername", "").strip()
    new_username = body.get("username", "").strip()
    expire = normalize_expire(body.get("expire", ""))
    enabled = 1 if str(body.get("enabled", "1")) in ["1", "true", "True", "啟用"] else 0

    if not old_username or not new_username:
        return jsonify({"ok": False, "msg": "會員帳號必填"})

    conn = db()

    row = conn.execute("SELECT id FROM members WHERE username=?", (old_username,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "msg": "找不到會員"})

    dup = conn.execute(
        "SELECT id FROM members WHERE username=? AND username<>?",
        (new_username, old_username)
    ).fetchone()

    if dup:
        conn.close()
        return jsonify({"ok": False, "msg": "新帳號已存在"})

    conn.execute("""
    UPDATE members
    SET username=?, expire=?, enabled=?
    WHERE username=?
    """, (new_username, expire, enabled, old_username))

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "msg": "會員資料已更新"})


@app.route("/api/admin/reset-password", methods=["POST"])
def api_admin_reset_password():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    if not username or not password:
        return jsonify({"ok": False, "msg": "帳號與新密碼必填"})

    conn = db()
    row = conn.execute("SELECT id FROM members WHERE username=?", (username,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False, "msg": "找不到會員"})

    conn.execute("UPDATE members SET password=? WHERE username=?", (password, username))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "msg": "密碼已重置"})


@app.route("/api/admin/set-expire", methods=["POST"])
def api_admin_set_expire():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    body = request.json or {}
    username = body.get("username", "").strip()
    expire = normalize_expire(body.get("expire", ""))

    if not username or not expire:
        return jsonify({"ok": False, "msg": "帳號與時間必填"})

    conn = db()
    row = conn.execute("SELECT id FROM members WHERE username=?", (username,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False, "msg": "找不到會員"})

    conn.execute("UPDATE members SET expire=?, enabled=1 WHERE username=?", (expire, username))
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "msg": "會員時間已更新"})

@app.route("/api/admin/set-table-status", methods=["POST"])
def api_admin_set_table_status():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
    body = request.json or {}
    platform = body.get("platform", "").strip()
    table = body.get("table", "").strip()
    status = body.get("status", "normal").strip()
    note = body.get("note", "").strip()
    if platform not in ["DG", "MT"]:
        return jsonify({"ok": False, "msg": "平台錯誤"})
    if status not in ["normal", "maintenance"]:
        return jsonify({"ok": False, "msg": "狀態錯誤"})
    tables = DG_TABLES if platform == "DG" else MT_TABLES
    if table not in tables:
        return jsonify({"ok": False, "msg": "桌號錯誤"})
    conn = db()
    conn.execute("""
    INSERT INTO table_status (platform, table_no, status, note, updated_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(platform, table_no)
    DO UPDATE SET status=excluded.status, note=excluded.note, updated_at=excluded.updated_at
    """, (platform, table, status, note, now()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "msg": "狀態已更新"})


@app.route("/api/admin/tables-monitor")
def api_admin_tables_monitor():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    result = []
    for platform, tables in [("DG", DG_TABLES), ("MT", MT_TABLES)]:
        for table in tables:
            status_row = conn.execute("SELECT status, note FROM table_status WHERE platform=? AND table_no=?", (platform, table)).fetchone()
            status = status_row["status"] if status_row else "normal"
            note = status_row["note"] if status_row else ""
            rows = conn.execute("""
            SELECT result FROM records
            WHERE platform=? AND table_no=? AND hidden=0
            ORDER BY id DESC LIMIT 120
            """, (platform, table)).fetchall()
            road = "".join([r["result"] for r in reversed(rows)])
            ai_stats = weighted_stats_for_table(platform, table)
            result.append({
                "platform": platform, "table": table, "road": road if road else "-",
                "ai": ai_stats["suggest"], "bankerScore": ai_stats["bankerScore"],
                "playerScore": ai_stats["playerScore"], "tieScore": ai_stats["tieScore"],
                "lucky6Score": ai_stats["lucky6Score"], "status": status, "note": note,
                "statusText": "維護中" if status == "maintenance" else "正常"
            })
    conn.close()
    return jsonify({"ok": True, "tables": result})


@app.route("/api/admin/core-stats")
def api_admin_core_stats():
    if not session.get("admin"):
        return jsonify({"ok": False}), 403
    conn = db()
    screen_records = conn.execute("SELECT COUNT(*) c FROM records WHERE hidden=0").fetchone()["c"]
    total_shared = conn.execute("SELECT COUNT(*) c FROM shared_ai_stats").fetchone()["c"]
    total_members = conn.execute("SELECT COUNT(*) c FROM members").fetchone()["c"]
    online_members = conn.execute("""
    SELECT COUNT(*) c FROM members
    WHERE last_active >= datetime('now','-5 minutes')
    """).fetchone()["c"]
    maintenance_tables = conn.execute("SELECT COUNT(*) c FROM table_status WHERE status='maintenance'").fetchone()["c"]
    conn.close()
    return jsonify({
        "ok": True,
        "totalRecords": total_shared,
        "screenRecords": screen_records,
        "totalShared": total_shared,
        "accuracy": 100 if total_shared else 0,
        "totalMembers": total_members,
        "onlineMembers": online_members,
        "maintenanceTables": maintenance_tables
    })


@app.route("/api/tables")
def api_tables():
    platform = request.args.get("platform", "DG")
    full = request.args.get("full", "0")
    tables = MT_TABLES if platform == "MT" else DG_TABLES
    if full != "1":
        return jsonify(tables)
    status_map = get_table_status_map()
    return jsonify([{
        "table": table,
        "status": status_map.get((platform, table), {}).get("status", "normal"),
        "label": f"{table}（維護中）" if status_map.get((platform, table), {}).get("status") == "maintenance" else table
    } for table in tables])


@app.route("/api/data")
def api_data():
    if not session.get("member"):
        return jsonify({"ok": False})
    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")
    status_map = get_table_status_map()
    if status_map.get((platform, table), {}).get("status") == "maintenance":
        return jsonify({"ok": False, "msg": "此桌維護中"})
    update_member_active(platform, table)
    screen_data = get_records(platform, table)
    stats = weighted_stats_for_table(platform, table, screen_data)
    member = get_member(session.get("member"))
    return jsonify({
        "ok": True,
        "records": screen_data,
        "stats": stats,
        "betCount": len(screen_data),
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
    status_map = get_table_status_map()
    if status_map.get((platform, table), {}).get("status") == "maintenance":
        return jsonify({"ok": False, "msg": "此桌維護中，暫停輸入"})
    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False, "msg": "結果錯誤"})
    conn = db()
    cur = conn.execute("""
    INSERT INTO records
    (platform, table_no, result, cards, player_point, banker_point, player_pair, banker_pair,
     lucky6, tie, source, count_bet, ai_learn, ai_suggest_before, ai_hit, hidden, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (platform, table, result, "", 0, 0, 0, 0, 0, 1 if result == "T" else 0, "manual", 0, 1, "", 0, 0, now()))
    record_id = cur.lastrowid
    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, cards, player_point, banker_point,
     player_pair, banker_pair, lucky6, tie, source, username, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (record_id, platform, table, result, "", 0, 0, 0, 0, 0, 1 if result == "T" else 0, "manual", session.get("member", ""), now()))
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
    status_map = get_table_status_map()
    if status_map.get((platform, table), {}).get("status") == "maintenance":
        return jsonify({"ok": False, "msg": "此桌維護中，暫停輸入"})
    calc = calc_cards(cards)
    if calc is None:
        return jsonify({"ok": False, "msg": "牌型錯誤"})
    conn = db()
    cur = conn.execute("""
    INSERT INTO records
    (platform, table_no, result, cards, player_point, banker_point, player_pair, banker_pair,
     lucky6, tie, source, count_bet, ai_learn, ai_suggest_before, ai_hit, hidden, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (platform, table, calc["result"], json.dumps(cards), calc["playerPoint"], calc["bankerPoint"],
          1 if calc["playerPair"] else 0, 1 if calc["bankerPair"] else 0,
          1 if calc["lucky6"] else 0, 1 if calc["tie"] else 0,
          "card_button", 1, 1, "", 0, 0, now()))
    record_id = cur.lastrowid
    conn.execute("""
    INSERT INTO shared_ai_stats
    (record_id, platform, table_no, result, cards, player_point, banker_point,
     player_pair, banker_pair, lucky6, tie, source, username, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (record_id, platform, table, calc["result"], json.dumps(cards), calc["playerPoint"], calc["bankerPoint"],
          1 if calc["playerPair"] else 0, 1 if calc["bankerPair"] else 0,
          1 if calc["lucky6"] else 0, 1 if calc["tie"] else 0,
          "cards", session.get("member", ""), now()))
    conn.commit()
    conn.close()
    update_member_active(platform, table)
    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
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
        conn.execute("UPDATE records SET hidden=1 WHERE id=?", (row["id"],))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def api_clear():
    if not session.get("member"):
        return jsonify({"ok": False, "msg": "未登入"}), 403
    body = request.json or {}
    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")
    conn = db()
    conn.execute("""
    UPDATE records SET hidden=1
    WHERE platform=? AND table_no=? AND hidden=0
    """, (platform, table))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "msg": "已清除此桌畫面，AI學習資料已保留"})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
