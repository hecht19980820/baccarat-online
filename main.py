from flask import Flask, render_template, request, jsonify, redirect, session
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "baccarat_admin_secret_2026"

records = defaultdict(list)

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07","RB08","RB09","RB10"]
MT_TABLES = ["01","02","03","03A","05","06","07","08","09","10"]

MEMBER_EXPIRE_TIME = "2025-06-30 23:59:59"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"


def table_key(platform, table):
    return f"{platform}_{table}"


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

        player_pair = len(player_cards) >= 2 and player_cards[0] == player_cards[1]
        banker_pair = len(banker_cards) >= 2 and banker_cards[0] == banker_cards[1]
        lucky6 = result == "B" and banker_point == 6

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

    banker_score = 50
    player_score = 50
    alerts = []

    for i, r in enumerate(recent):
        weight = i + 1

        if r == "B":
            banker_score += weight * 0.35
        elif r == "P":
            player_score += weight * 0.35

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
        "alerts": alerts,
        "bankerScore": round(banker_score, 1),
        "playerScore": round(player_score, 1)
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

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
    return redirect("/admin-login")


@app.route("/api/tables")
def tables():
    platform = request.args.get("platform", "DG")
    return jsonify(MT_TABLES if platform == "MT" else DG_TABLES)


@app.route("/api/data")
def get_data():
    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")

    key = table_key(platform, table)
    data = records[key]

    return jsonify({
        "records": data,
        "betCount": len([x for x in data if x.get("countBet")]),
        "memberExpireTime": MEMBER_EXPIRE_TIME,
        "stats": road_stats(data)
    })


@app.route("/api/admin-data")
def admin_data():
    if not session.get("admin"):
        return jsonify({"ok": False, "msg": "未登入"}), 403

    all_tables = []

    total_rounds = 0
    total_bets = 0
    total_banker = 0
    total_player = 0
    total_tie = 0

    platforms = {
        "DG": DG_TABLES,
        "MT": MT_TABLES
    }

    for platform, tables in platforms.items():
        for table in tables:
            key = table_key(platform, table)
            data = records[key]
            stats = road_stats(data)

            total_rounds += len(data)
            total_bets += stats["betCount"]
            total_banker += stats["bankerRate"]
            total_player += stats["playerRate"]
            total_tie += stats["tieCount"]

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
                "records": data[-30:]
            })

    return jsonify({
        "ok": True,
        "memberExpireTime": MEMBER_EXPIRE_TIME,
        "totalRounds": total_rounds,
        "totalBets": total_bets,
        "tables": all_tables
    })


@app.route("/api/manual", methods=["POST"])
def manual_add():
    body = request.json

    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False})

    key = table_key(platform, table)

    records[key].append({
        "result": result,
        "source": "manual",
        "countBet": False,
        "aiLearn": True,
        "tie": result == "T"
    })

    return jsonify({"ok": True})


@app.route("/api/cards", methods=["POST"])
def cards_add():
    body = request.json

    platform = body.get("platform")
    table = body.get("table")
    cards = body.get("cards", [])

    calc = calc_cards(cards)

    if calc is None:
        return jsonify({"ok": False})

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

    return jsonify({"ok": True, **calc})


@app.route("/api/undo", methods=["POST"])
def undo():
    body = request.json
    key = table_key(body.get("platform"), body.get("table"))

    if records[key]:
        records[key].pop()

    return jsonify({"ok": True})


@app.route("/api/clear", methods=["POST"])
def clear():
    body = request.json
    key = table_key(body.get("platform"), body.get("table"))

    records[key] = []

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
