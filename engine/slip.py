"""Προτεινόμενα δελτία ανά ημέρα, μόνο με αγώνες της ίδιας ημέρας (ώρα Ελλάδας).

- Απλό: συνολική απόδοση ≥ 5, χωρίς ανώτατο όριο, 2-5 επιλογές.
- Ακραίο: συνολική απόδοση ≥ 20, χωρίς ανώτατο όριο, 3-7 επιλογές.
Κριτήριο: ο ΠΙΘΑΝΟΤΕΡΟΣ συνδυασμός (με βάση τα στατιστικά) που φτάνει την ελάχιστη απόδοση.
Αποκλείονται επιλογές με πολύ κακή τιμή (εκτιμώμενη απόδοση πάνω από 7% κάτω από τη δίκαιη).
"""
from datetime import datetime, timedelta, timezone
from itertools import combinations

ATHENS = timezone(timedelta(hours=2))  # χειμερινή ώρα (αρκεί για ομαδοποίηση ανά ημέρα)
MAX_DISAGREE = 0.08   # το μοντέλο δεν απέχει πάνω από 8 μονάδες από την αγορά (αλλιώς μάλλον λάθος του)
MIN_LEG_EV = -0.07    # όχι επιλογές με πολύ κακή τιμή (γκανιότ ~5-7% είναι το συνηθισμένο)

KINDS = {
    "simple": {"min_total": 5.0, "legs": (2, 5), "leg_p": 0.50, "leg_odds": (1.25, 2.60), "pool": 20},
    "extreme": {"min_total": 20.0, "legs": (3, 7), "leg_p": 0.40, "leg_odds": (1.35, 3.50), "pool": 17},
}


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ATHENS).strftime("%Y-%m-%d")


def _legs(matches, rule):
    now = datetime.now(timezone.utc)
    legs = []
    for m in matches:
        start = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
        if start <= now or m["confidence"] == "χαμηλή" or (not m.get("has_odds") and m["confidence"] != "υψηλή"):
            continue
        lo, hi = rule["leg_odds"]
        cand = [s for s in m["markets"]
                if s["p"] >= rule["leg_p"] and s.get("est") and lo <= s["est"] <= hi
                and s["pp"] == 0 and s.get("est_ev") is not None and s["est_ev"] >= MIN_LEG_EV
                and (s.get("p_book") is None or abs(s["p"] - s["p_book"]) <= MAX_DISAGREE)
                and s["key"][:2] not in ("CO", "KO")]  # κόρνερ/κάρτες: χωρίς δεδομένα αγοράς
        # ανά αγώνα: η πιθανότερη επιλογή και η πιθανότερη με απόδοση ≥ 1.6 (για να "ανεβαίνει" το δελτίο)
        cand.sort(key=lambda s: -s["p"])
        pick = cand[:1] + [s for s in cand if s["est"] >= 1.6][:1]
        for s in {id(x): x for x in pick}.values():
            legs.append({"match": m, "s": s})
    # οι πιο "δυνατές" επιλογές: πιθανότητα σε σχέση με την απόδοση που προσφέρει
    legs.sort(key=lambda x: -(x["s"]["p"] * x["s"]["est"]))
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
            if odds < rule["min_total"]:
                continue
            key = (round(p, 4), p * odds - 1)  # πιθανότερο· ισοπαλία -> καλύτερο EV
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
