"""Προτεινόμενο δελτίο: 2-4 επιλογές από διαφορετικούς αγώνες, συνολική απόδοση κάτω από 10."""
from datetime import datetime, timedelta, timezone
from itertools import combinations

MAX_TOTAL = 10.0
MIN_TOTAL = 4.0
MIN_LEG_P = 0.50
LEG_ODDS = (1.30, 2.60)
MAX_DISAGREE = 0.08   # το μοντέλο δεν απέχει πάνω από 8 μονάδες από την αγορά (αλλιώς μάλλον λάθος του)
MIN_LEG_EV = -0.03    # το πολύ 3% κάτω από τη δίκαιη (περίπου το μισό γκανιότ των εταιρειών)
MIN_SLIP_P = 0.18     # τουλάχιστον 18% πιθανότητα να βγει
WINDOW_DAYS = 5


def _legs(matches):
    now = datetime.now(timezone.utc)
    legs = []
    for m in matches:
        start = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
        if not (now < start < now + timedelta(days=WINDOW_DAYS)) or m["confidence"] == "χαμηλή":
            continue
        cand = [s for s in m["markets"]
                if s["p"] >= MIN_LEG_P and s["est"] and LEG_ODDS[0] <= s["est"] <= LEG_ODDS[1]
                and s["pp"] == 0 and s["est_ev"] is not None and s["est_ev"] >= MIN_LEG_EV
                and s.get("p_book") is not None and abs(s["p"] - s["p_book"]) <= MAX_DISAGREE
                and s["group"] != "Διπλή ευκαιρία"]
        cand.sort(key=lambda s: (-s["p"], -s["est_ev"]))
        for s in cand[:2]:
            legs.append({"match": m, "s": s})
    legs.sort(key=lambda x: -x["s"]["p"])
    return legs[:26]  # αρκετές για αναζήτηση, χωρίς να εκτοξεύεται ο χρόνος


def build(matches):
    legs = _legs(matches)
    best = None
    for k in (2, 3, 4):
        for combo in combinations(legs, k):
            if len({id(x["match"]) for x in combo}) < k:
                continue
            odds = p = 1.0
            for x in combo:
                odds *= x["s"]["est"]
                p *= x["s"]["p"]
            if not (MIN_TOTAL <= odds < MAX_TOTAL) or p < MIN_SLIP_P:
                continue
            # το δελτίο με το καλύτερο αναμενόμενο αποτέλεσμα· ισοπαλία -> πιθανότερο
            key = (round(p * odds - 1, 3), p)
            if best is None or key > best[0]:
                best = (key, combo, odds, p)
    if not best:
        return None
    _, combo, odds, p = best
    return {
        "legs": [{
            "match_id": x["match"]["id"], "comp": x["match"]["comp"], "date": x["match"]["date"],
            "home": x["match"]["home"], "away": x["match"]["away"],
            "key": x["s"]["key"], "side": x["s"]["side"],
            "label": x["s"]["label"], "group": x["s"]["group"], "p": x["s"]["p"],
            "fair": x["s"]["fair"], "est": x["s"]["est"], "est_src": x["s"]["est_src"],
            "best": x["s"]["best"], "book": x["s"]["book"],
        } for x in sorted(combo, key=lambda x: x["match"]["date"])],
        "odds": round(odds, 2), "p": round(p, 4), "ev": round(p * odds - 1, 4),
    }
