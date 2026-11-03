"""Backtest: python -m engine.backtest

Για κάθε εβδομάδα των παλιών σεζόν, εκπαιδεύει το μοντέλο ΜΟΝΟ με ό,τι είχε παιχτεί πριν,
προβλέπει τους αγώνες της εβδομάδας και τους συγκρίνει με το πραγματικό αποτέλεσμα και τις
πραγματικές αποδόσεις (Pinnacle ως αγορά, Bet365 ως "μαλακή" εταιρεία που θα ποντάραμε).
Γράφει το site/data/backtest.json.
"""
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import config, history, model, sources

SEASONS = [("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
LEAGUE = "E0"
WEIGHTS = [0.0, 0.2, 0.35, 0.5, 1.0]  # βάρος μοντέλου (0 = μόνο αγορά, 1 = μόνο μοντέλο)


def _probs(lh, la):
    M = model.score_matrix(lh, la)
    n = len(M)
    ph = sum(M[i][j] for i in range(n) for j in range(n) if i > j)
    pd = sum(M[i][i] for i in range(n))
    po = sum(M[i][j] for i in range(n) for j in range(n) if i + j > 2.5)
    return [ph, pd, 1 - ph - pd], po


def run():
    rows = []
    for season, prev_season in SEASONS:
        cur_all = sorted(sources.fdcouk_league(LEAGUE, season), key=lambda m: m["date"])
        prev = sources.fdcouk_league(LEAGUE, prev_season)
        start = datetime.fromisoformat(cur_all[0]["date"])
        week = start + timedelta(days=21)  # οι 3 πρώτες εβδομάδες μόνο για "ζέσταμα"
        end = datetime.fromisoformat(cur_all[-1]["date"])
        while week <= end:
            nxt = week + timedelta(days=7)
            past = [m for m in cur_all if datetime.fromisoformat(m["date"]) < week]
            todo = [m for m in cur_all if week <= datetime.fromisoformat(m["date"]) < nxt]
            if todo:
                ratings, lg = model.fit_league(LEAGUE, past, prev, now=week, with_stats=False)
                for m in todo:
                    o = m.get("odds") or {}
                    mk1, mko = o.get("p1x2") or o.get("a1x2"), o.get("pou") or o.get("aou")  # Pinnacle, αλλιώς μέσος όρος
                    if not (mk1 and o.get("b1x2") and mko and o.get("bou")):
                        continue
                    rh, ra = ratings.get(m["home"]), ratings.get(m["away"])
                    if not rh or not ra:
                        continue
                    lh, la, _, _ = model.expected(rh, ra, lg)
                    fair = history._devig(mk1)
                    fou = history._devig(mko)
                    mh, ma = model.implied_lambdas(fair[0], fair[2], fou[0])
                    res = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
                    rows.append({"season": season, "lh": lh, "la": la, "mh": mh, "ma": ma, "res": res,
                                 "over": m["hg"] + m["ag"] > 2.5, "b1x2": o["b1x2"], "bou": o["bou"],
                                 "bc1x2": o.get("bc1x2"), "bcou": o.get("bcou"),
                                 "mk1x2": fair, "mkou": fou[0]})
            week = nxt
        print(f"  {season}: {sum(1 for r in rows if r['season'] == season)} αγώνες")
    return rows


def evaluate(rows):
    out = {"matches": len(rows), "seasons": [s for s, _ in SEASONS], "league": "Premier League", "weights": []}
    for w in WEIGHTS:
        ll1 = llou = 0.0
        bets = defaultdict(lambda: {"n": 0, "won": 0, "profit": 0.0, "clv": []})
        calib = defaultdict(lambda: [0, 0.0, 0])  # bucket -> [πλήθος, άθροισμα p, νίκες]
        for r in rows:
            lh = w * r["lh"] + (1 - w) * r["mh"]
            la = w * r["la"] + (1 - w) * r["ma"]
            p3, po = _probs(lh, la)
            ll1 -= math.log(max(p3[r["res"]], 1e-9))
            llou -= math.log(max(po if r["over"] else 1 - po, 1e-9))
            for i, p in enumerate(p3):
                b = min(int(p * 10), 9)
                calib[b][0] += 1; calib[b][1] += p; calib[b][2] += 1 if r["res"] == i else 0
            cands = [("1X2", p3[i], r["b1x2"][i], r["res"] == i, (r["bc1x2"] or [None] * 3)[i]) for i in range(3)]
            cands += [("OU2.5", po, r["bou"][0], r["over"], (r["bcou"] or [None, None])[0]),
                      ("OU2.5", 1 - po, r["bou"][1], not r["over"], (r["bcou"] or [None, None])[1])]
            for mk, p, odds, won, closing in cands:
                if p * odds - 1 >= config.MIN_EDGE and config.MIN_ODDS <= odds <= config.MAX_ODDS:
                    b = bets[mk]
                    b["n"] += 1; b["won"] += won; b["profit"] += (odds - 1) if won else -1
                    if closing:
                        b["clv"].append(odds / closing - 1)
        n = len(rows) or 1
        out["weights"].append({
            "w": w, "logloss_1x2": round(ll1 / n, 4), "logloss_ou": round(llou / n, 4),
            "bets": {mk: {"n": b["n"], "won": b["won"], "profit": round(b["profit"], 2),
                          "roi": round(b["profit"] / b["n"], 4) if b["n"] else None,
                          "clv": round(sum(b["clv"]) / len(b["clv"]), 4) if b["clv"] else None}
                     for mk, b in bets.items()},
            "calibration": [{"bucket": f"{k * 10}-{k * 10 + 10}%", "n": v[0], "pred": round(v[1] / v[0], 3),
                             "actual": round(v[2] / v[0], 3)} for k, v in sorted(calib.items()) if v[0] >= 20],
        })
    out["current_weight"] = config.MODEL_WEIGHT
    out["created"] = datetime.now(timezone.utc).isoformat()
    return out


def main():
    print("• Backtest Premier League")
    rows = run()
    res = evaluate(rows)
    (config.DATA_OUT / "backtest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for w in res["weights"]:
        b = w["bets"]
        print(f"  w={w['w']}: logloss 1X2 {w['logloss_1x2']}, O/U {w['logloss_ou']} | "
              + " | ".join(f"{k}: {v['n']} στοιχ., ROI {v['roi']}, CLV {v['clv']}" for k, v in b.items()))


if __name__ == "__main__":
    main()
