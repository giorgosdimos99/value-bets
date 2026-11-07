"""Έρευνα: πού κάνουν λάθος οι στοιχηματικές και ποιοι κανόνες "πιθανότητα + απόδοση" κερδίζουν.

python -m engine.research

1. Για 22 πρωταθλήματα × 5 σεζόν (2021/22-2025/26), εβδομάδα-εβδομάδα: το μοντέλο εκπαιδεύεται ΜΟΝΟ
   με ό,τι είχε παιχτεί πριν και προβλέπει 1/X/2 και Over/Under 2.5.
2. Συγκρίνουμε με τις πραγματικές αποδόσεις Bet365 πριν τον αγώνα (μαλακή εταιρεία, σαν Stoiximan),
   τη "δίκαιη" αγορά (Pinnacle χωρίς γκανιότα, αλλιώς μέσος όρος) και το αποτέλεσμα.
3. Ψάχνουμε κανόνες σε 2021/22-2024/25 (ανακάλυψη) και τους ελέγχουμε στο 2025/26 (που δεν "είδαμε").
Γράφει το site/data/research.json.
"""
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import config, model, sources

SEASONS = [("2122", "2021"), ("2223", "2122"), ("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
DISCOVER = {"2122", "2223", "2324", "2425"}
TEST = {"2526"}
ROWS_CACHE = "research_rows2.json"
SIDES = ("1", "X", "2", "Over", "Under")


def _devig(prices):
    inv = [1 / p for p in prices]
    s = sum(inv)
    return [x / s for x in inv]


def collect():
    cached = sources._cached(ROWS_CACHE, 24 * 30)
    if cached:
        return cached
    rows = []
    for code in config.RATING_LEAGUES:
        for season, prev_s in SEASONS:
            cur = sorted(sources.fdcouk_league(code, season), key=lambda m: m["date"] or "")
            prev = sources.fdcouk_league(code, prev_s)
            if len(cur) < 100:
                continue
            start = datetime.fromisoformat(cur[0]["date"])
            week, end = start + timedelta(days=28), datetime.fromisoformat(cur[-1]["date"])
            while week <= end:
                nxt = week + timedelta(days=7)
                todo = [m for m in cur if week <= datetime.fromisoformat(m["date"]) < nxt]
                if todo:
                    past = [m for m in cur if datetime.fromisoformat(m["date"]) < week]
                    ratings, lg = model.fit_league(code, past, prev, now=week, with_stats=False)
                    for m in todo:
                        o = m["odds"]
                        fair1 = o.get("p1x2") or o.get("a1x2")
                        fairou = o.get("pou") or o.get("aou")
                        if not (o.get("b1x2") and o.get("bou") and fair1 and fairou and lg):
                            continue
                        rh, ra = ratings.get(m["home"]), ratings.get(m["away"])
                        if not rh or not ra:
                            continue
                        lh, la, _, _ = model.expected(rh, ra, lg)
                        M = model.score_matrix(lh, la)
                        n = len(M)
                        ph = sum(M[i][j] for i in range(n) for j in range(n) if i > j)
                        pd = sum(M[i][i] for i in range(n))
                        po = sum(M[i][j] for i in range(n) for j in range(n) if i + j > 2.5)
                        mk = _devig(fair1) + _devig(fairou)
                        close1 = o.get("pc1x2") or o.get("bc1x2")
                        closeou = o.get("pcou") or o.get("bcou")
                        close = (_devig(close1) if close1 else [None] * 3) + (_devig(closeou) if closeou else [None] * 2)
                        hg, ag = m["hg"], m["ag"]
                        res = [hg > ag, hg == ag, hg < ag, hg + ag > 2.5, hg + ag < 2.5]
                        rows.append({
                            "lg": code, "s": season,
                            "pm": [round(x, 4) for x in (ph, pd, 1 - ph - pd, po, 1 - po)],
                            "pk": [round(x, 4) for x in mk],
                            "b": o["b1x2"] + o["bou"],
                            "c": [round(x, 4) if x else None for x in close],
                            "w": [int(x) for x in res],
                        })
                week = nxt
            print(f"  {code} {season}: {len(rows)} αγώνες συνολικά")
    sources._save_cache(ROWS_CACHE, rows)
    return rows


def _stats(bets):
    """bets: λίστα (απόδοση, κέρδισε, fair_closing ή None)."""
    n = len(bets)
    if not n:
        return {"n": 0}
    profit = [(o - 1) if w else -1 for o, w, _ in bets]
    roi = sum(profit) / n
    sd = math.sqrt(sum((x - roi) ** 2 for x in profit) / max(n - 1, 1))
    clv = [o * c - 1 for o, _, c in bets if c]  # απόδοση × δίκαιη πιθανότητα κλεισίματος - 1
    return {"n": n, "hit": round(sum(w for _, w, _ in bets) / n, 4), "odds": round(sum(o for o, _, _ in bets) / n, 2),
            "roi": round(roi, 4), "ci": round(1.96 * sd / math.sqrt(n), 4),
            "clv": round(sum(clv) / len(clv), 4) if clv else None}


BUCKETS = [(1.0, 1.4), (1.4, 1.7), (1.7, 2.1), (2.1, 2.6), (2.6, 3.5), (3.5, 5.0), (5.0, 99)]


def analyse(rows):
    out = {"matches": len(rows), "leagues": sorted({r["lg"] for r in rows}),
           "created": datetime.now(timezone.utc).isoformat()}

    # Α. Λάθη της αγοράς: όλα τα στοιχήματα στη Bet365 ανά εύρος απόδοσης (χωρίς μοντέλο)
    bias = []
    for lo, hi in BUCKETS:
        for grp, idx in (("1X2", (0, 1, 2)), ("O/U 2.5", (3, 4))):
            bets = [(r["b"][i], r["w"][i], r["c"][i]) for r in rows for i in idx if lo <= r["b"][i] < hi]
            st = _stats(bets)
            if st["n"]:
                st["implied"] = round(sum(1 / o for o, _, _ in bets) / st["n"], 4)
                bias.append({"market": grp, "range": f"{lo:.2f}-{hi:.2f}" if hi < 99 else f"{lo:.1f}+", **st})
    out["bias"] = bias

    # Β. Ακρίβεια ανά βάρος μοντέλου (log-loss, μικρότερο = καλύτερο)
    weights = []
    for w in (0.0, 0.1, 0.2, 0.35, 1.0):
        ll = n = 0
        for r in rows:
            for i in range(5):
                if r["w"][i]:
                    ll -= math.log(max(w * r["pm"][i] + (1 - w) * r["pk"][i], 1e-9)); n += 1
        weights.append({"w": w, "logloss": round(ll / n, 4)})
    out["weights"] = weights

    # Γ. Μέθοδοι αφαίρεσης γκανιότ στις αποδόσεις Bet365: πόσο σωστές πιθανότητες δίνουν
    from .history import _devig as power_devig
    def prop(o):
        inv = [1 / x for x in o]; t = sum(inv); return [x / t for x in inv]
    devig = []
    for name, f in (("Αναλογική", prop), ("Power (χρησιμοποιείται)", power_devig)):
        cal = defaultdict(lambda: [0, 0.0, 0])
        for r in rows:
            for idx in ((0, 1, 2), (3, 4)):
                ps = f([r["b"][i] for i in idx])
                for j, i in enumerate(idx):
                    b = min(int(ps[j] * 10), 9)
                    cal[b][0] += 1; cal[b][1] += ps[j]; cal[b][2] += r["w"][i]
        tot = sum(v[0] for v in cal.values())
        err = sum(abs(v[1] - v[2]) for v in cal.values()) / tot
        devig.append({"method": name, "error": round(err * 100, 2),
                      "calibration": [{"bucket": f"{k * 10}-{k * 10 + 10}%", "n": v[0], "pred": round(v[1] / v[0], 4),
                                       "actual": round(v[2] / v[0], 4)} for k, v in sorted(cal.items()) if v[0] >= 50]})
    out["devig"] = devig

    # Δ. "Κενά": η Bet365 δίνει πάνω από τη δίκαιη τιμή της αγοράς (Pinnacle/μ.ό.)
    gap = []
    for ev in (0.02, 0.03):
        res = {}
        for part, seasons in (("disc", DISCOVER), ("test", TEST)):
            bets = [(r["b"][i], r["w"][i], r["c"][i]) for r in rows if r["s"] in seasons for i in range(5)
                    if r["pk"][i] * r["b"][i] - 1 >= ev and 1.15 <= r["b"][i] <= 4.5]
            res[part] = _stats(bets)
        gap.append({"evmin": ev, **res})
    out["gap"] = gap

    # Ε. Μοτίβα: πρωτάθλημα × πλευρά που κέρδισαν ΚΑΙ στην ανακάλυψη ΚΑΙ στον έλεγχο
    patterns = []
    for lg in out["leagues"]:
        for i, side in enumerate(SIDES):
            res = {}
            for part, seasons in (("disc", DISCOVER), ("test", TEST)):
                bets = [(r["b"][i], r["w"][i], r["c"][i]) for r in rows
                        if r["lg"] == lg and r["s"] in seasons and 1.25 <= r["b"][i] <= 3.0]
                res[part] = _stats(bets)
            d, t = res["disc"], res["test"]
            if d["n"] >= 80 and t["n"] >= 30 and d["roi"] > 0.02 and t["roi"] > 0.02:
                patterns.append({"league": lg, "name": config.RATING_LEAGUES[lg][0], "side": side,
                                 "odds": [1.25, 3.0], **res})
    out["patterns"] = patterns
    return out


def main():
    print("• Έρευνα: συλλογή προβλέψεων")
    rows = collect()
    res = analyse(rows)
    from . import stats_research  # κόρνερ, σουτ, φάουλ, κάρτες, αποκρούσεις, ημίχρονο
    res["stats"], res["stats_disp"] = stats_research.main()
    (config.DATA_OUT / "research.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ {res['matches']} αγώνες, μοτίβα: {[(p['league'], p['side']) for p in res['patterns']]}")
    return res


if __name__ == "__main__":
    main()
