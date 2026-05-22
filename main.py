from flask import Flask, render_template, request, jsonify, redirect, session
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)
app.secret_key = "baccarat_admin_secret_2026"

records = defaultdict(list)

DG_TABLES = [
    "RB01","RB02","RB03","RB04","RB05",
    "RB06","RB07","RB08","RB09","RB10"
]

MT_TABLES = [
    "01","02","03","03A","05",
    "06","07","08","09","10"
]

MEMBER_EXPIRE_TIME = "2026-12-31 23:59:59"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"

# 測試會員
members = {
    "test01": {
        "password": "123456",
        "expire": "2026-12-31 23:59:59",
        "enabled": True
    }
}


def table_key(platform, table):
    return f"{platform}_{table}"


# 固定順序：
# 閒1 莊1 閒2 莊2 閒3 莊3
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

        player_pair = (
            len(player_cards) >= 2 and
            player_cards[0] == player_cards[1]
        )

        banker_pair = (
            len(banker_cards) >= 2 and
            banker_cards[0] == banker_cards[1]
        )

        lucky6 = (
            result == "B" and
            banker_point == 6
        )

        return {
            "result": result,
            "playerPoint": player_point,
            "bankerPoint": banker_point,
            "playerPair": player_pair,
            "bankerPair": banker_pair,
            "lucky6": lucky6,
            "tie": result == "T"
        }

    except:
        return None


def road_stats(data):

    valid = [
        x for x in data
        if x.get("result") in ["B","P","T"]
    ]

    bp = [
        x for x in valid
        if x.get("result") in ["B","P"]
    ]

    bet_count = len([
        x for x in data
        if x.get("countBet")
    ])

    b_count = len([
        x for x in bp
        if x["result"] == "B"
    ])

    p_count = len([
        x for x in bp
        if x["result"] == "P"
    ])

    t_count = len([
        x for x in valid
        if x["result"] == "T"
    ])

    total_bp = len(bp)

    banker_rate = round(
        (b_count / total_bp) * 100,
        1
    ) if total_bp else 0

    player_rate = round(
        (p_count / total_bp) * 100,
        1
    ) if total_bp else 0

    recent = [x["result"] for x in bp][-20:]

    banker_score = 50
    player_score = 50

    alerts = []

    for i, r in enumerate(recent):

        weight = i + 1

        if r == "B":
            banker_score += weight * .35

        elif r == "P":
            player_score += weight * .35

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

    recent_cards = valid[-20:]

    banker_pair_count = len([
        x for x in recent_cards
        if x.get("bankerPair")
    ])

    player_pair_count = len([
        x for x in recent_cards
        if x.get("playerPair")
    ])

    lucky6_count = len([
        x for x in recent_cards
        if x.get("lucky6")
    ])

    tie_count = len([
        x for x in recent_cards
        if x.get("tie")
    ])

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
        stable_rate = round(50 + diff,1)

        alerts.append("莊閒不明顯")

    elif banker_score > player_score:

        suggest = "莊"
        stable_rate = round(min(92,50+diff),1)

    else:

        suggest = "閒"
        stable_rate = round(min(92,50+diff),1)

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
        "bankerScore": round(banker_score,1),
        "playerScore": round(player_score,1)
    }


# =====================
# 會員登入
# =====================

@app.route("/login", methods=["GET","POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        member = members.get(username)

        if not member:

            return render_template(
                "login.html",
                error="帳號不存在"
            )

        if not member["enabled"]:

            return render_template(
                "login.html",
                error="會員已停權"
            )

        if member["password"] != password:

            return render_template(
                "login.html",
                error="密碼錯誤"
            )

        expire_time = datetime.strptime(
            member["expire"],
            "%Y-%m-%d %H:%M:%S"
        )

        if datetime.now() > expire_time:

            return render_template(
                "login.html",
                error="會員已到期"
            )

        session["member"] = username

        return redirect("/")

    return render_template("login.html")


# =====================
# 會員首頁
# =====================

@app.route("/")
def index():

    if not session.get("member"):
        return redirect("/login")

    return render_template("index.html")


# =====================
# 管理員登入
# =====================

@app.route("/admin-login", methods=["GET","POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if (
            username == ADMIN_USER and
            password == ADMIN_PASS
        ):

            session["admin"] = True

            return redirect("/admin")

        return render_template(
            "admin_login.html",
            error="帳號或密碼錯誤"
        )

    return render_template("admin_login.html")


# =====================
# 管理員後台
# =====================

@app.route("/admin")
def admin():

    if not session.get("admin"):
        return redirect("/admin-login")

    return render_template("admin.html")


# =====================
# 登出
# =====================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# =====================
# 桌號
# =====================

@app.route("/api/tables")
def tables():

    platform = request.args.get("platform","DG")

    if platform == "MT":
        return jsonify(MT_TABLES)

    return jsonify(DG_TABLES)


# =====================
# 前台資料
# =====================

@app.route("/api/data")
def get_data():

    platform = request.args.get("platform","DG")
    table = request.args.get("table","RB01")

    key = table_key(platform, table)

    data = records[key]

    return jsonify({
        "records": data,
        "betCount": len([
            x for x in data
            if x.get("countBet")
        ]),
        "memberExpireTime": MEMBER_EXPIRE_TIME,
        "stats": road_stats(data)
    })


# =====================
# 後台資料
# =====================

@app.route("/api/admin-data")
def admin_data():

    if not session.get("admin"):
        return jsonify({"ok":False}),403

    all_tables = []

    total_rounds = 0
    total_bets = 0

    for platform, tables in {

        "DG":DG_TABLES,
        "MT":MT_TABLES

    }.items():

        for table in tables:

            key = table_key(platform, table)

            data = records[key]

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

    return jsonify({

        "ok": True,

        "memberExpireTime": MEMBER_EXPIRE_TIME,

        "totalRounds": total_rounds,

        "totalBets": total_bets,

        "totalTables": len(all_tables),

        "tables": all_tables
    })


# =====================
# 手動新增
# =====================

@app.route("/api/manual", methods=["POST"])
def manual_add():

    body = request.json

    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    if result not in ["B","P","T"]:
        return jsonify({"ok":False})

    key = table_key(platform, table)

    records[key].append({

        "result": result,

        "source": "manual",

        "countBet": False,

        "aiLearn": True,

        "playerPair": False,

        "bankerPair": False,

        "lucky6": False,

        "tie": result == "T"
    })

    return jsonify({"ok":True})


# =====================
# 牌型輸入
# =====================

@app.route("/api/cards", methods=["POST"])
def cards_add():

    body = request.json

    platform = body.get("platform")
    table = body.get("table")

    cards = body.get("cards", [])

    calc = calc_cards(cards)

    if calc is None:
        return jsonify({"ok":False})

    key = table_key(platform, table)

    records[key].append({

        "result": calc["result"],

        "cards": cards,

        "playerPoint": calc["playerPoint"],

        "bankerPoint": calc["bankerPoint"],

        "playerPair": calc["playerPair"],

        "bankerPair": calc["bankerPair"],

        "lucky6": calc["lucky6"],

        "tie": calc["tie"],

        "source": "card_button",

        "countBet": True,

        "aiLearn": True
    })

    return jsonify({
        "ok":True,
        **calc
    })


# =====================
# 撤回
# =====================

@app.route("/api/undo", methods=["POST"])
def undo():

    body = request.json

    key = table_key(
        body.get("platform"),
        body.get("table")
    )

    if records[key]:
        records[key].pop()

    return jsonify({"ok":True})


# =====================
# 清空桌號
# =====================

@app.route("/api/clear", methods=["POST"])
def clear():

    body = request.json

    key = table_key(
        body.get("platform"),
        body.get("table")
    )

    records[key] = []

    return jsonify({"ok":True})


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
