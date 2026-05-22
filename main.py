from flask import Flask, render_template, request, jsonify
from collections import defaultdict

app = Flask(__name__)

records = defaultdict(list)

DG_TABLES = [
    "RB01", "RB02", "RB03", "RB04", "RB05",
    "RB06", "RB07", "RB08", "RB09", "RB10"
]

MT_TABLES = [
    "01", "02", "03", "03A", "05",
    "06", "07", "08", "09", "10"
]


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

    raw_b_rate = round((b_count / total_bp) * 100, 1) if total_bp else 0
    raw_p_rate = round((p_count / total_bp) * 100, 1) if total_bp else 0

    recent = [x["result"] for x in bp][-20:]
    recent10 = recent[-10:]
    recent6 = recent[-6:]

    banker_score = 50
    player_score = 50
    alerts = []

    # 近20局加權，不是單純看莊閒顆數
    for i, r in enumerate(recent):
        weight = i + 1

        if r == "B":
            banker_score += weight * 0.35
        elif r == "P":
            player_score += weight * 0.35

    # 近10局強化
    b10 = recent10.count("B")
    p10 = recent10.count("P")

    banker_score += b10 * 1.8
    player_score += p10 * 1.8

    # 連莊 / 連閒
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
        banker_score += min(streak_count * 3.2, 18)
    elif streak_result == "P":
        player_score += min(streak_count * 3.2, 18)

    # 跳路
    if len(recent6) >= 6:
        if recent6 == ["B", "P", "B", "P", "B", "P"]:
            banker_score += 10
            alerts.append("跳路偏莊")
        elif recent6 == ["P", "B", "P", "B", "P", "B"]:
            player_score += 10
            alerts.append("跳路偏閒")

    # 長龍反打風險
    if streak_count >= 5:
        if streak_result == "B":
            banker_score -= 6
            player_score += 4
            alerts.append("長莊注意斷龍")
        elif streak_result == "P":
            player_score -= 6
            banker_score += 4
            alerts.append("長閒注意斷龍")

    # 牌型後台權重
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

    # 蟑螂路 / 空心路簡化後台分析
    if len(recent) >= 8:
        last8 = recent[-8:]
        changes = sum(
            1 for i in range(1, len(last8))
            if last8[i] != last8[i - 1]
        )

        if changes >= 6:
            alerts.append("蟑螂路跳動偏強")

            if last8[-1] == "B":
                player_score += 5
            else:
                banker_score += 5

        if changes <= 2:
            alerts.append("空心路偏黏")

            if last8[-1] == "B":
                banker_score += 5
            else:
                player_score += 5

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
        "bankerWin": b_count,
        "playerWin": p_count,
        "tieCount": t_count,
        "bankerRate": raw_b_rate,
        "playerRate": raw_p_rate,
        "streakResult": streak_result,
        "streakCount": streak_count,
        "suggest": suggest,
        "stableRate": stable_rate,
        "alerts": alerts[:3],
        "bankerScore": round(banker_score, 1),
        "playerScore": round(player_score, 1)
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
        "aiLearn": True,
        "playerPair": False,
        "bankerPair": False,
        "lucky6": False,
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
        return jsonify({"ok": False, "msg": "cards error"})

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
