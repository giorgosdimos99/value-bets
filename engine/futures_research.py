"""Έλεγχος των μακροχρόνιων προβλέψεων σε παλιές σεζόν.

Για κάθε πρωτάθλημα/σεζόν «σταματάμε τον χρόνο» στο 20/40/60/80% της σεζόν, προσομοιώνουμε τα υπόλοιπα
και συγκρίνουμε με την τελική βαθμολογία. Δοκιμάζουμε: πηγή δύναμης (αγορά/στατιστικά/μείγμα),
αβεβαιότητα δύναμης (sigma) και χρόνο ημιζωής. Μετρική: log-loss και Brier ανά (ομάδα, αγορά).
python -m engine.futures_research
"""
import json
import math
from collections import defaultdict
from datetime import datetime, timezone

from . import config, futures as F, sources

SEASONS = [("2223", "2122"), ("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
CUTS = [0.2, 0.4, 0.6, 0.8]
VARIANTS = [(src, s, hl) for src in ("market", "model", "blend") for s in (0.0, 0.05, 0.1, 0.15, 0.2) for hl in (90, 180)]


def dt(m):
    d = datetime.fromisoformat(m["date"])
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main():
    agg = defaultdict(lambda: [0.0, 0.0, 0])  # variant -> logloss, brier, n
    by_mk = defaultdict(lambda: [0.0, 0])      # (variant, market kind) -> logloss
    calib = defaultdict(lambda: [0.0, 0.0, 0])  # (variant, bucket) -> sum p, sum y, n
    cases = 0
    for code, mks in F.LEAGUES.items():
        for s, ps in SEASONS:
            cur = [m for m in sources.fdcouk_league(code, s) if m["date"] and m["hg"] is not None]
            prev = [m for m in sources.fdcouk_league(code, ps) if m["date"] and m["hg"] is not None]
            if len(cur) < 100:
                continue
            cur.sort(key=dt)
            teams = sorted({m["home"] for m in cur} | {m["away"] for m in cur})
            n = len(teams)
            if len(cur) < n * (n - 1) * 0.97:  # λείπουν αγώνες: εκτός
                continue
            final = F.table(cur)
            rank = sorted(teams, key=lambda t: (-final[t][0], -final[t][1], -final[t][2]))
            fpos = {t: i for i, t in enumerate(rank)}
            for cut in CUTS:
                k = int(len(cur) * cut)
                played, now = cur[:k], dt(cur[k])
                cache_R = {}
                for v in VARIANTS:
                    src, sig, hl = v
                    if (src, hl) not in cache_R:
                        cache_R[(src, hl)] = F.ratings(played, prev, now, src=src, hl=hl)
                    R = cache_R[(src, hl)]
                    if not R:
                        continue
                    P, _, _, _ = F.simulate(teams, played, R, sigma=sig, nsim=2000, seed=k)
                    for key, _, kind, kk in mks:
                        for t in teams:
                            p = min(max(F.market_p(P[t], kind, kk, n), 0.002), 0.998)
                            y = 1.0 if (fpos[t] < kk if kind == "top" else fpos[t] >= n - kk) else 0.0
                            ll = -(y * math.log(p) + (1 - y) * math.log(1 - p))
                            a = agg[v]; a[0] += ll; a[1] += (p - y) ** 2; a[2] += 1
                            b = by_mk[(v, kind + str(kk))]; b[0] += ll; b[1] += 1
                            c = calib[(v, min(int(p * 10), 9))]; c[0] += p; c[1] += y; c[2] += 1
                cases += 1
            print(f"  {code} {s}: {n} ομάδες ok", flush=True)
    res = sorted(((a[0] / a[2], a[1] / a[2], v) for v, a in agg.items()), key=lambda x: x[0])
    print(f"\n{cases} σημεία ελέγχου")
    for ll, br, v in res[:12]:
        print(f"  {v}: logloss {ll:.4f}  brier {br:.4f}")
    best = res[0][2]
    print("\nΚαλύτερο:", best)
    mk = {k[1]: round(x[0] / x[1], 4) for k, x in by_mk.items() if k[0] == best}
    cal = [{"bucket": f"{b * 10}-{b * 10 + 10}%", "p": round(c[0] / c[2], 3), "hit": round(c[1] / c[2], 3), "n": c[2]}
           for (v, b), c in sorted(calib.items(), key=lambda x: x[0][1]) if v == best]
    for c in cal:
        print("  ", c)
    out = {"cases": cases, "best": list(best), "ranking": [{"v": list(v), "logloss": round(ll, 4), "brier": round(br, 4)} for ll, br, v in res],
           "by_market": mk, "calibration": cal}
    (config.DATA_OUT / "futures_research.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")




def basket_main():
    """EuroLeague 2023/24-2025/26: κανονική περίοδος (θέσεις) + πρωταθλητής."""
    import numpy as np
    from . import basket
    agg = defaultdict(lambda: [0.0, 0])
    for year in (2023, 2024, 2025):
        allg = basket.games("E", year)
        prev = [g for g in basket.games("E", year - 1) if g["played"] and g["phase"] == "RS"]
        rs = sorted([g for g in allg if g["phase"] == "RS" and g["played"]], key=lambda g: g["date"])
        ff = sorted([g for g in allg if g["phase"] == "FF" and g["played"]], key=lambda g: g["date"])
        if len(rs) < 200 or not ff:
            print("  λείπει", year, len(rs), len(ff)); continue
        fin = ff[-1]; champ = fin["home"] if fin["hp"] > fin["ap"] else fin["away"]
        teams = sorted({g["home"] for g in rs} | {g["away"] for g in rs})
        rec = defaultdict(lambda: [0, 0, 0])
        for g in rs:
            w = g["hp"] > g["ap"]
            rec[g["home"]][0 if w else 1] += 1; rec[g["away"]][1 if w else 0] += 1
            rec[g["home"]][2] += g["hp"] - g["ap"]; rec[g["away"]][2] += g["ap"] - g["hp"]
        final = sorted(teams, key=lambda t: (-rec[t][0], -rec[t][2]))
        fpos = {t: i for i, t in enumerate(final)}
        for cut in (0.25, 0.5, 0.75):
            k = int(len(rs) * cut)
            pl, rem = rs[:k], [(g["home"], g["away"]) for g in rs[k:]]
            now = datetime.fromisoformat(rs[k]["date"].replace("Z", "+00:00"))
            # fit με «τώρα» = σημείο ελέγχου
            import engine.basket as B
            R = _bfit(B, pl, prev, now)
            cur = defaultdict(lambda: [0, 0, 0])
            for g in pl:
                w = g["hp"] > g["ap"]
                cur[g["home"]][0 if w else 1] += 1; cur[g["away"]][1 if w else 0] += 1
                cur[g["home"]][2] += g["hp"] - g["ap"]; cur[g["away"]][2] += g["ap"] - g["hp"]
            for sig in (0.0, 1.5, 2.5, 3.5, 5.0):
                S = F.BSim(teams, R, sig, 3000, np.random.default_rng(k))
                W, order = S.season({t: tuple(cur[t]) for t in teams}, rem)
                post = F.el_post(S, order)
                n = len(teams)
                pos = np.empty_like(order); pos[np.arange(S.nsim)[:, None], order] = np.arange(n)[None, :]
                for t in teams:
                    i = S.idx[t]
                    for kk in (1, 4, 6, 10):
                        p = min(max(float((pos[:, i] < kk).mean()), 0.003), 0.997); y = fpos[t] < kk
                        a = agg[(sig, f"t{kk}")]; a[0] += -math.log(p if y else 1 - p); a[1] += 1
                    p = min(max(float((post["champ"] == i).mean()), 0.003), 0.997); y = t == champ
                    a = agg[(sig, "champ")]; a[0] += -math.log(p if y else 1 - p); a[1] += 1
        print(f"  EuroLeague {year}: πρωταθλητής {champ}", flush=True)
    out = {}
    for (sig, mk), a in sorted(agg.items()):
        out.setdefault(str(sig), {})[mk] = round(a[0] / a[1], 4)
    for sig, d in out.items():
        print(f"  sigma {sig}: {d}  μέσο {sum(d.values()) / len(d):.4f}")
    p = config.DATA_OUT / "futures_research.json"
    box = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    box["basket"] = out
    p.write_text(json.dumps(box, ensure_ascii=False, indent=1), encoding="utf-8")


def _bfit(B, played_cur, played_prev, now):
    """basket.fit με δικό μας «τώρα» (για τον έλεγχο)."""
    import engine.basket as bm
    real = bm.datetime

    class _D(real):
        @classmethod
        def now(cls, tz=None):
            return now
    bm.datetime = _D
    try:
        return B.fit(played_cur, played_prev)
    finally:
        bm.datetime = real


if __name__ == "__main__":
    import sys
    basket_main() if "basket" in sys.argv else main()
