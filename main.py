from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "baccarat_secret_2026"

CORS(app)

DB = "baccarat_system.db"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"


# =========================
# DB
# =========================

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


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
        currentPlatform TEXT DEFAULT '',
        currentTable TEXT DEFAULT '',
        device TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        lastActive TEXT DEFAULT ''
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        result TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# 工具
# =========================

def get_tables(platform):

    if platform == "MT":
        return [
            "MT01","MT02","MT03","MT04","MT05",
            "MT06","MT07","MT08","MT09","MT10"
        ]

    return [
        "RB01","RB02","RB03","RB04","RB05",
        "RB06","RB07","RB08","RB09","RB10"
    ]


def analyze(records):

    banker = len([x for x in records if x["result"] == "B"])
    player = len([x for x in records if x["result"] == "P"])
    tie = len([x for x in records if x["result"] == "T"])

    total = banker + player

    bankerRate = 0
    playerRate = 0

    if total > 0:
        bankerRate = round((banker / total) * 100)
        playerRate = round((player / total) * 100)

    suggest = "觀望"

    if bankerRate >= 58:
        suggest = "莊"

    elif playerRate >= 58:
        suggest = "閒"

    stableRate = max(bankerRate, playerRate)

    streakResult = None
    streakCount = 0

    if len(records) > 0:

        last = records[-1]["result"]

        if last != "T":

            streakResult = last

            for r in reversed(records):

                if r["result"] == last:
                    streakCount += 1
                else:
                    break

    alerts = []

    if streakCount >= 4:
        alerts.append(f"{'莊' if streakResult == 'B' else '閒'} {streakCount} 連")

    return {
        "bankerRate": bankerRate,
        "playerRate": playerRate,
        "tieCount": tie,
        "suggest": suggest,
        "stableRate": stableRate,
        "streakResult": streakResult,
        "streakCount": streakCount,
        "alerts": alerts,
        "totalAnalysis": len(records)
    }


# =========================
# 頁面
# =========================

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
def admin_login():
    return render_template("admin_login.html")


# =========================
# 登入
# =========================

@app.route("/api/login", methods=["POST"])
def login():

    data = request.json

    username = data.get("username")
    password = data.get("password")

    conn = get_db()

    user = conn.execute("""
    SELECT * FROM members
    WHERE username=?
    AND password=?
    AND enabled=1
    """, (username, password)).fetchone()

    conn.close()

    if not user:
        return jsonify({
            "ok": False,
            "msg": "帳號或密碼錯誤"
        })

    session["user"] = username

    return jsonify({"ok": True})


@app.route("/api/admin-login", methods=["POST"])
def admin_login_api():

    data = request.json

    if (
        data.get("username") == ADMIN_USER and
        data.get("password") == ADMIN_PASS
    ):

        session["admin"] = True

        return jsonify({"ok": True})

    return jsonify({
        "ok": False,
        "msg": "帳號密碼錯誤"
    })


# =========================
# tables
# =========================

@app.route("/api/tables")
def api_tables():

    platform = request.args.get("platform", "DG")

    return jsonify(get_tables(platform))


# =========================
# data
# =========================

@app.route("/api/data")
def api_data():

    if "user" not in session:
        return jsonify({
            "ok": False,
            "msg": "未登入"
        })

    platform = request.args.get("platform")
    table = request.args.get("table")

    conn = get_db()

    rows = conn.execute("""
    SELECT * FROM records
    WHERE platform=?
    AND table_name=?
    ORDER BY id ASC
    """, (platform, table)).fetchall()

    records = [dict(x) for x in rows]

    stats = analyze(records)

    user = conn.execute("""
    SELECT * FROM members
    WHERE username=?
    """, (session["user"],)).fetchone()

    conn.execute("""
    UPDATE members
    SET
        currentPlatform=?,
        currentTable=?,
        device=?,
        ip=?,
        lastActive=?
    WHERE username=?
    """, (
        platform,
        table,
        request.user_agent.string[:100],
        request.remote_addr,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        session["user"]
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "records": records,
        "stats": stats,
        "betCount": len(records),
        "memberExpireTime": user["expire"]
    })


# =========================
# 手動加入
# =========================

@app.route("/api/manual", methods=["POST"])
def api_manual():

    if "user" not in session:
        return jsonify({"ok": False})

    data = request.json

    conn = get_db()

    conn.execute("""
    INSERT INTO records(
        platform,
        table_name,
        result,
        created_at
    )
    VALUES(?,?,?,?)
    """, (
        data["platform"],
        data["table"],
        data["result"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# 牌型輸入
# =========================

@app.route("/api/cards", methods=["POST"])
def api_cards():

    if "user" not in session:
        return jsonify({"ok": False})

    data = request.json

    cards = data.get("cards", [])

    if len(cards) < 4:
        return jsonify({
            "ok": False,
            "msg": "牌數不足"
        })

    player = cards[0] + cards[2]
    banker = cards[1] + cards[3]

    if len(cards) >= 5:
        player += cards[4]

    if len(cards) >= 6:
        banker += cards[5]

    player %= 10
    banker %= 10

    result = "T"

    if banker > player:
        result = "B"

    elif player > banker:
        result = "P"

    conn = get_db()

    conn.execute("""
    INSERT INTO records(
        platform,
        table_name,
        result,
        created_at
    )
    VALUES(?,?,?,?)
    """, (
        data["platform"],
        data["table"],
        result,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "result": result
    })


# =========================
# undo
# =========================

@app.route("/api/undo", methods=["POST"])
def api_undo():

    data = request.json

    conn = get_db()

    row = conn.execute("""
    SELECT * FROM records
    WHERE platform=?
    AND table_name=?
    ORDER BY id DESC
    LIMIT 1
    """, (
        data["platform"],
        data["table"]
    )).fetchone()

    if row:
        conn.execute("""
        DELETE FROM records
        WHERE id=?
        """, (row["id"],))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# clear
# =========================

@app.route("/api/clear", methods=["POST"])
def api_clear():

    data = request.json

    conn = get_db()

    conn.execute("""
    DELETE FROM records
    WHERE platform=?
    AND table_name=?
    """, (
        data["platform"],
        data["table"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# admin data
# =========================

@app.route("/api/admin-data")
def admin_data():

    if not session.get("admin"):
        return jsonify({"ok": False})

    conn = get_db()

    members = conn.execute("""
    SELECT * FROM members
    ORDER BY id DESC
    """).fetchall()

    members = [dict(x) for x in members]

    tables = []

    totalRounds = 0

    for platform in ["DG", "MT"]:

        for table in get_tables(platform):

            rows = conn.execute("""
            SELECT * FROM records
            WHERE platform=?
            AND table_name=?
            ORDER BY id ASC
            """, (platform, table)).fetchall()

            records = [dict(x) for x in rows]

            stats = analyze(records)

            totalRounds += len(records)

            tables.append({
                "platform": platform,
                "table": table,
                "records": records[-30:],
                **stats
            })

    conn.close()

    return jsonify({
        "ok": True,
        "members": members,
        "tables": tables,
        "onlineCount": len([
            x for x in members
            if x["lastActive"]
        ]),
        "totalTables": len(tables),
        "totalRounds": totalRounds,
        "aiAccuracy": {
            "today": 72
        }
    })


# =========================
# member add
# =========================

@app.route("/api/admin/member/add", methods=["POST"])
def add_member():

    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

    try:

        conn = get_db()

        conn.execute("""
        INSERT INTO members(
            username,
            password,
            expire
        )
        VALUES(?,?,?)
        """, (
            data["username"],
            data["password"],
            data["expire"]
        ))

        conn.commit()
        conn.close()

        return jsonify({"ok": True})

    except Exception as e:

        return jsonify({
            "ok": False,
            "msg": str(e)
        })


# =========================
# update member
# =========================

@app.route("/api/admin/member/update", methods=["POST"])
def update_member():

    if not session.get("admin"):
        return jsonify({"ok": False})

    data = request.json

    conn = get_db()

    conn.execute("""
    UPDATE members
    SET
        password=?,
        expire=?
    WHERE id=?
    """, (
        data["password"],
        data["expire"],
        data["id"]
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# toggle
# =========================

@app.route("/api/admin/member/toggle", methods=["POST"])
def toggle_member():

    data = request.json

    conn = get_db()

    row = conn.execute("""
    SELECT enabled
    FROM members
    WHERE id=?
    """, (data["id"],)).fetchone()

    newVal = 0 if row["enabled"] else 1

    conn.execute("""
    UPDATE members
    SET enabled=?
    WHERE id=?
    """, (newVal, data["id"]))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# delete
# =========================

@app.route("/api/admin/member/delete", methods=["POST"])
def delete_member():

    data = request.json

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({
            "ok": False,
            "msg": "管理員密碼錯誤"
        })

    conn = get_db()

    conn.execute("""
    DELETE FROM members
    WHERE id=?
    """, (data["id"],))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================
# clear all
# =========================

@app.route("/api/admin/clear-all", methods=["POST"])
def clear_all():

    data = request.json

    if data.get("adminPassword") != ADMIN_PASS:
        return jsonify({
            "ok": False,
            "msg": "管理員密碼錯誤"
        })

    conn = get_db()

    conn.execute("DELETE FROM records")

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================

if __name__ == "__main__":
    app.run(debug=True)
