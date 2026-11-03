"""Προτεινόμενα δελτία ανά ημέρα, μόνο με αγώνες της ίδιας ημέρας (ώρα Ελλάδας).

- Απλό: συνολική απόδοση ≥ 5, χωρίς ανώτατο όριο, 2-4 επιλογές, υψηλή πιθανότητα ανά επιλογή.
- Ακραίο: συνολική απόδοση ≥ 20, χωρίς ανώτατο όριο, 3-6 επιλογές.
Σε κάθε περίπτωση διαλέγεται ο συνδυασμός με το καλύτερο αναμενόμενο αποτέλεσμα (EV).
"""
from datetime import datetime, timedelta, timezone
from itertools import combinations

ATHENS = timezone(timedelta(hours=2))  # χειμερινή ώρα (αρκεί για ομαδοποίηση ανά ημέρα)
MAX_DISAGREE = 0.08   # το μοντέλο δεν απέχει πάνω από 8 μονάδες από την αγορά (αλλιώς μάλλον λάθος του)
MIN_LEG_EV = -0.03    # το πολύ 3% κάτω από τη δίκαιη (περίπου το μισό γκανιότ των εταιρειών)

KINDS = {
    "simple": {"min_total": 5.0, "legs": (2, 4), "leg_p": 0.45, "leg_odds": (1.30, 3.0), "min_p": 0.10, "pool": 22},
    "extreme": {"min_total": 20.0, "legs": (3, 6), "leg_p": 0.30, "leg_odds": (1.50, 4.5), "min_p": 0.02, "pool": 18},
}


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ATHENS).strftime("%Y-%m-%d")


def _legs(matches, rule):
    now = datetime.now(timezone.utc)
    legs = []
    for m in matches:
        start = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
        if start <= now or m["confidence"] == "χαμηλή":
            continue
        lo, hi = rule["leg_odds"]
        cand = [s for s in m["markets"]
                if s["p"] >= rule["leg_p"] and s.get("est") and lo <= s["est"] <= hi
                and s["pp"] == 0 and s.get("est_ev") is not None and s["est_ev"] >= MIN_LEG_EV
                and s.get("p_book") is not None and abs(s["p"] - s["p_book"]) <= MAX_DISAGREE
                and s["group"] != "Διπλή ευκαιρία"]
        cand.sort(key=lambda s: (-s["est_ev"], -s["p"]))
        for s in cand[:2]:
            legs.append({"match": m, "s": s})
    legs.sort(key=lambda x: (-x["s"]["est_ev"], -x["s"]["p"]))
    return legs[:rule["pool"]]


def _best(legs, rule):
    best = None
    kmin, kmax = rule["legs"]
    for k in range(kmin, kmax + 1):
        for combo in combinations(legs, k):
            if len({x["match"]["id"] for x in combo}) < k:
                continue
            odds = p = 1.0
            for x in combo:
                odds *= x["s"]["est"]
                p *= x["s"]["p"]
            if odds < rule["min_total"] or p < rule["min_p"]:
                continue
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


def build_daily(matches):
    by_day = {}
    for m in matches:
        by_day.setdefault(_day(m["date"]), []).append(m)
    out = []
    for day in sorted(by_day):
        entry = {"day": day, "matches": len(by_day[day])}
        for kind, rule in KINDS.items():
            entry[kind] = _best(_legs(by_day[day], rule), rule)
        if entry["simple"] or entry["extreme"]:
            out.append(entry)
    return out
