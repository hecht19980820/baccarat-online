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


def init_db():

    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        expire TEXT,
        enabled INTEGER DEFAULT 1,
        created_at TEXT,
        last_active TEXT,
        current_platform TEXT,
        current_table TEXT,
        device TEXT,
        ip TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_no TEXT,
        result TEXT,
        count_bet INTEGER DEFAULT 1,
        hidden INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS shared_ai_stats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_no TEXT,
        result TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    SELECT COUNT(*) c
    FROM members
    WHERE username='test01'
    """)

    if cur.fetchone()["c"] == 0:

        cur.execute("""
        INSERT INTO members
        (username,password,expire,enabled,created_at)
        VALUES (?,?,?,?,?)
        """, (
            "test01",
            "123456",
            "2026-12-31 23:59:59",
            1,
            now()
        ))

    conn.commit()
    conn.close()


def get_member(username):

    conn = db()

    row = conn.execute("""
    SELECT *
    FROM members
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
    SET last_active=?,
        current_platform=?,
        current_table=?
    WHERE username=?
    """, (
        now(),
        platform,
        table,
        username
    ))

    conn.commit()
    conn.close()


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

    return rows


@app.route("/")
def index():

    if not session.get("member"):
        return redirect("/login")

    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect("/admin-login")

    return render_template("admin.html")


@app.route("/admin-login")
def admin_login():
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/login", methods=["POST"])
def api_login():

    body = request.json or {}

    username = body.get("username", "")
    password = body.get("password", "")

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


@app.route("/api/admin-login", methods=["POST"])
def api_admin_login():

    body = request.json or {}

    username = body.get("username", "")
    password = body.get("password", "")

    if username == ADMIN_USER and password == ADMIN_PASS:

        session["admin"] = True

        return jsonify({
            "ok": True
        })

    return jsonify({
        "ok": False
    })


@app.route("/api/update-active", methods=["POST"])
def api_update_active():

    if not session.get("member"):
        return jsonify({"ok": False})

    body = request.json or {}

    platform = body.get("platform", "DG")
    table = body.get("table", "RB01")

    update_member_active(platform, table)

    return jsonify({
        "ok": True
    })


@app.route("/api/manual", methods=["POST"])
def api_manual():

    if not session.get("member"):
        return jsonify({"ok": False})

    body = request.json or {}

    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    conn = db()

    conn.execute("""
    INSERT INTO records
    (platform,table_no,result,count_bet,created_at)
    VALUES (?,?,?,?,?)
    """, (
        platform,
        table,
        result,
        0,
        now()
    ))

    conn.execute("""
    INSERT INTO shared_ai_stats
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

    return jsonify({
        "ok": True
    })


@app.route("/api/data")
def api_data():

    if not session.get("member"):
        return jsonify({"ok": False})

    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    rows = get_records(platform, table)

    data = []

    for r in rows:

        data.append({
            "result": r["result"]
        })

    return jsonify({
        "ok": True,
        "records": data
    })


@app.route("/api/admin/core-stats")
def api_admin_core_stats():

    if not session.get("admin"):
        return jsonify({"ok": False})

    conn = db()

    total_records = conn.execute("""
    SELECT COUNT(*) c
    FROM records
    """).fetchone()["c"]

    total_shared = conn.execute("""
    SELECT COUNT(*) c
    FROM shared_ai_stats
    """).fetchone()["c"]

    online_members = conn.execute("""
    SELECT COUNT(*) c
    FROM members
    WHERE enabled=1
    """).fetchone()["c"]

    conn.close()

    return jsonify({
        "ok": True,
        "totalRecords": total_records,
        "totalShared": total_shared,
        "onlineMembers": online_members,
        "accuracy": 92
    })


@app.route("/api/admin/members")
def api_admin_members():

    if not session.get("admin"):
        return jsonify({"ok": False})

    conn = db()

    rows = conn.execute("""
    SELECT *
    FROM members
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    members = []

    for r in rows:

        members.append({
            "username": r["username"],
            "enabled": bool(r["enabled"]),
            "expire": r["expire"],
            "current_platform": r["current_platform"],
            "current_table": r["current_table"],
            "last_active": r["last_active"]
        })

    return jsonify({
        "ok": True,
        "members": members
    })


@app.route("/api/admin/create-member", methods=["POST"])
def api_admin_create_member():

    if not session.get("admin"):
        return jsonify({"ok": False})

    body = request.json or {}

    username = body.get("username")
    password = body.get("password")
    expire = body.get("expire")

    conn = db()

    try:

        conn.execute("""
        INSERT INTO members
        (username,password,expire,enabled,created_at)
        VALUES (?,?,?,?,?)
        """, (
            username,
            password,
            expire,
            1,
            now()
        ))

        conn.commit()

    except:

        conn.close()

        return jsonify({
            "ok": False,
            "msg": "帳號已存在"
        })

    conn.close()

    return jsonify({
        "ok": True,
        "msg": "新增成功"
    })


@app.route("/api/admin/toggle-member", methods=["POST"])
def api_admin_toggle_member():

    if not session.get("admin"):
        return jsonify({"ok": False})

    body = request.json or {}

    username = body.get("username")

    conn = db()

    row = conn.execute("""
    SELECT enabled
    FROM members
    WHERE username=?
    """, (username,)).fetchone()

    new_status = 0 if row["enabled"] else 1

    conn.execute("""
    UPDATE members
    SET enabled=?
    WHERE username=?
    """, (
        new_status,
        username
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
