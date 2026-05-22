from flask import Flask, render_template, request, jsonify
from collections import defaultdict

app = Flask(__name__)

records = defaultdict(list)

DG_TABLES = ["RB01", "RB02", "RB03", "RB04", "RB05", "RB06", "RB07", "RB08"]
MT_TABLES = ["01", "02", "03", "03A", "05", "06", "07", "08", "09", "10"]

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
    total_analysis = len([x for x in data if x["result"] in ["B", "P"]])
    b_count = len([x for x in data if x["result"] == "B"])
    p_count = len([x for x in data if x["result"] == "P"])

    b_rate = round((b_count / total_analysis) * 100, 1) if total_analysis else 0
    p_rate = round((p_count / total_analysis) * 100, 1) if total_analysis else 0

    streak_result = None
    streak_count = 0

    for item in reversed(data):
        if item["result"] == "T":
            continue
        if streak_result is None:
            streak_result = item["result"]
            streak_count = 1
        elif item["result"] == streak_result:
            streak_count += 1
        else:
            break

    recent = [x["result"] for x in data if x["result"] in ["B", "P"]][-12:]

    banker_score = b_rate
    player_score = p_rate

    if len(recent) >= 4:
        if recent[-1] == "B":
            banker_score += 4
        if recent[-1] == "P":
            player_score += 4

        if len(set(recent[-3:])) == 1:
            if recent[-1] == "B":
                banker_score += 8
            else:
                player_score += 8

        if len(recent) >= 6:
            pattern = recent[-6:]
            if pattern == ["B", "P", "B", "P", "B", "P"]:
                banker_score += 6
            if pattern == ["P", "B", "P", "B", "P", "B"]:
                player_score += 6

    if banker_score > player_score:
        suggest = "莊"
        stable_rate = round(banker_score, 1)
    elif player_score > banker_score:
        suggest = "閒"
        stable_rate = round(player_score, 1)
    else:
        suggest = "觀望"
        stable_rate = 0

    return {
        "totalAnalysis": total_analysis,
        "bankerWin": b_count,
        "playerWin": p_count,
        "bankerRate": b_rate,
        "playerRate": p_rate,
        "streakResult": streak_result,
        "streakCount": streak_count,
        "suggest": suggest,
        "stableRate": stable_rate,
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/tables")
def tables():
    platform = request.args.get("platform", "DG")
    if platform == "MT":
        return jsonify(MT_TABLES)
    return jsonify(DG_TABLES)

@app.route("/api/data")
def get_data():
    platform = request.args.get("platform", "DG")
    table = request.args.get("table", "RB01")
    key = table_key(platform, table)
    data = records[key]

    bet_count = len([x for x in data if x.get("countBet")])

    return jsonify({
        "records": data,
        "betCount": bet_count,
        "stats": road_stats(data)
    })

@app.route("/api/manual", methods=["POST"])
def manual_add():
    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    result = body.get("result")

    if result not in ["B", "P", "T"]:
        return jsonify({"ok": False, "msg": "invalid result"})

    key = table_key(platform, table)

    records[key].append({
        "result": result,
        "source": "manual_road",
        "countBet": False,
        "aiLearn": True
    })

    return jsonify({"ok": True})

@app.route("/api/cards", methods=["POST"])
def cards_add():
    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    cards = body.get("cards", [])

    result = calc_cards(cards)

    if result is None:
        return jsonify({"ok": False, "msg": "cards error"})

    key = table_key(platform, table)

    records[key].append({
        "result": result,
        "cards": cards,
        "source": "card_button",
        "countBet": True,
        "aiLearn": True
    })

    return jsonify({"ok": True, "result": result})

@app.route("/api/undo", methods=["POST"])
def undo():
    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    key = table_key(platform, table)

    if records[key]:
        records[key].pop()

    return jsonify({"ok": True})

@app.route("/api/clear", methods=["POST"])
def clear():
    body = request.json
    platform = body.get("platform")
    table = body.get("table")
    key = table_key(platform, table)
    records[key] = []
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
