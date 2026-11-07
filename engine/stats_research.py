"""Έρευνα στα στατιστικά αγώνα: κόρνερ, σουτ, σουτ στην εστία, φάουλ, κάρτες, αποκρούσεις, ημίχρονο.

python -m engine.stats_research

Για 17 πρωταθλήματα × 3 σεζόν, εβδομάδα-εβδομάδα, το μοντέλο προβλέπει κάθε μετρική ΜΟΝΟ με ό,τι
είχε παιχτεί πριν. Συγκρίνουμε με τον "αφελή" τρόπο (μέσος όρος του πρωταθλήματος), δηλαδή αυτό
που κάνει όποιος βάζει γραμμές χωρίς να κοιτάει τις ομάδες. Παράμετροι (διασπορά) από 2023-25,
έλεγχος στο 2025/26 που δεν "είδε" το μοντέλο.
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta

from . import config, history, model, sources, stats

SEASONS = [("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
DISCOVER = {"2324", "2425"}
TEST = {"2526"}
CACHE = "research_stats.json"


def _ref_factors(past, lavg_c, lavg_f):
    """Συντελεστές διαιτητή (κάρτες, φάουλ) μόνο από αγώνες ΠΡΙΝ την εβδομάδα."""
    by = defaultdict(lambda: [0, 0.0, 0, 0.0])
    for m in past:
        if not m.get("ref") or m.get("hy") is None:
            continue
        b = by[history.ref_key(m["ref"])]
        b[0] += 1; b[1] += history._cards(m)
        if m.get("hf") is not None and m.get("af") is not None:
            b[2] += 1; b[3] += m["hf"] + m["af"]
    out = {}
    for k, (n, c, nf, f) in by.items():
        out[k] = (((c + 8 * lavg_c) / (n + 8)) / lavg_c if lavg_c else 1.0,
                  ((f + 8 * lavg_f) / (nf + 8)) / lavg_f if lavg_f and nf else 1.0)
    return out


def collect():
    cached = sources._cached(CACHE, 24 * 30)
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
                    pool = prev + past
                    cs = [history._cards(m) for m in pool if m.get("hy") is not None]
                    fs = [m["hf"] + m["af"] for m in pool if m.get("hf") is not None and m.get("af") is not None]
                    refs = _ref_factors(pool, sum(cs) / len(cs) if cs else 0, sum(fs) / len(fs) if fs else 0)
                    for m in todo:
                        rh, ra = ratings.get(m["home"]), ratings.get(m["away"])
                        if not (rh and ra and lg):
                            continue
                        mx = stats.means(rh, ra, lg)
                        x = {}
                        for k, (ph, pa) in mx.items():
                            v = stats.values(m, k)
                            if v is None:
                                continue
                            nh, na = lg["sx"][k]
                            x[k] = [round(ph, 2), round(pa, 2), round(nh, 2), round(na, 2), v[0], v[1]]
                        lh, la, _, _ = model.expected(rh, ra, lg)
                        row = {"lg": code, "s": season, "x": x,
                               "rf": [round(f, 3) for f in refs.get(history.ref_key(m.get("ref")), (1.0, 1.0))]
                               if m.get("ref") else None}
                        if m.get("hthg") is not None:
                            row["ht"] = [round(lh * lg["ht_share"], 3), round(la * lg["ht_share"], 3),
                                         int(m["hthg"]), int(m["htag"])]
                        rows.append(row)
                week = nxt
            print(f"  {code} {season}: {len(rows)} αγώνες συνολικά")
    sources._save_cache(CACHE, rows)
    return rows


def _ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if y else 1 - p)


def _disp(pairs):
    """Διασπορά φ (variance = μ + φμ²) με μέθοδο ροπών από (μ, x)."""
    num = sum((x - mu) ** 2 - mu for mu, x in pairs)
    den = sum(mu * mu for mu, _ in pairs)
    return max(round(num / den, 4), 0.0) if den else 0.0


def analyse(rows):
    out, disp = {}, {}
    for k, name in stats.STATS.items():
        R = [(r, r["x"][k]) for r in rows if k in r["x"]]
        D = [x for r, x in R if r["s"] in DISCOVER]
        T = [(r, x) for r, x in R if r["s"] in TEST]
        if len(D) < 500 or len(T) < 200:
            continue
        # "επιστροφή στον μέσο όρο" (από 2023-25): πόσο από την απόκλιση ομάδας-πρωταθλήματος επιβεβαιώνεται,
        # χωριστά ανά ομάδα (α) και στο σύνολο του αγώνα (αT, π.χ. στα κόρνερ οι αποκλίσεις αλληλοαναιρούνται)
        def reg(pairs):
            num = sum(dy * dx for dx, dy in pairs)
            den = sum(dx * dx for dx, _ in pairs)
            return round(min(max(num / den, 0.0), 1.0), 3) if den else 0.0
        alpha = reg([(x[i] - x[2 + i], x[4 + i] - x[2 + i]) for x in D for i in (0, 1)])
        alphaT = reg([(x[0] + x[1] - x[2] - x[3], x[4] + x[5] - x[2] - x[3]) for x in D])

        def shrink(x):
            nT = x[2] + x[3]
            return [x[2] + alpha * (x[0] - x[2]), x[3] + alpha * (x[1] - x[3])] + x[2:6] + [nT + alphaT * (x[0] + x[1] - nT)]
        D = [shrink(x) for x in D]
        T = [(r, shrink(x)) for r, x in T]
        pt = _disp([(x[0], x[4]) for x in D] + [(x[1], x[5]) for x in D])
        pT = _disp([(x[6], x[4] + x[5]) for x in D])
        disp[k] = [pt, pT, alpha, alphaT]

        def ref_f(r):
            if not r.get("rf"):
                return 1.0
            return r["rf"][0] if k == "ca" else r["rf"][1] if k == "fo" else 1.0

        sse_m = sse_n = 0.0
        ll_m = ll_n = ll_r = 0.0
        cal = defaultdict(lambda: [0, 0.0, 0])
        edge, tedge = [], []  # (πιθανότητα μοντέλου, πιθανότητα μέσου όρου, κέρδισε) για την πλευρά του μοντέλου
        team_ll_m = team_ll_n = 0.0
        for r, x in T:
            mu, nmu, act = x[6], x[2] + x[3], x[4] + x[5]
            sse_m += (act - mu) ** 2; sse_n += (act - nmu) ** 2
            L = math.floor(nmu) + 0.5
            y = act > L
            pm = stats.p_over(stats.nb_pmf(mu, pT), L)
            pn = stats.p_over(stats.nb_pmf(nmu, pT), L)
            pr = stats.p_over(stats.nb_pmf(mu * ref_f(r), pT), L)
            ll_m += _ll(pm, y); ll_n += _ll(pn, y); ll_r += _ll(pr, y)
            b = min(int(pm * 5), 4)
            cal[b][0] += 1; cal[b][1] += pm; cal[b][2] += y
            if abs(pm - pn) >= stats.EDGE_MIN:
                edge.append((pm, pn, y) if pm > pn else (1 - pm, 1 - pn, not y))
            for i in (0, 1):  # ανά ομάδα, στη "συνηθισμένη" γραμμή της
                Lt = math.floor(x[2 + i]) + 0.5
                yt = x[4 + i] > Lt
                qm = stats.p_over(stats.nb_pmf(x[i], pt), Lt)
                qn = stats.p_over(stats.nb_pmf(x[2 + i], pt), Lt)
                team_ll_m += _ll(qm, yt); team_ll_n += _ll(qn, yt)
                if abs(qm - qn) >= stats.EDGE_MIN:
                    tedge.append((qm, qn, yt) if qm > qn else (1 - qm, 1 - qn, not yt))

        def summ(E, better):
            n_ = len(E)
            if not n_:
                return {"n": 0, "model": None, "avg": None, "hit": None, "ok": False}
            pm_, pn_, h_ = (sum(e[j] for e in E) / n_ for j in range(3))
            return {"n": n_, "model": round(pm_, 4), "avg": round(pn_, 4), "hit": round(h_, 4),
                    "ok": bool(n_ >= 100 and better and abs(h_ - pm_) < abs(h_ - pn_))}
        n = len(T)
        et = summ(edge, ll_m < ll_n)
        eteam = summ(tedge, team_ll_m < team_ll_n)
        out[k] = {
            "name": name, "n": n, "avg": round(sum(x[4] + x[5] for _, x in T) / n, 2),
            "sd": round(math.sqrt(sse_m / n), 2),
            "disp": [pt, pT], "alpha": alpha, "alphaT": alphaT,
            "explained": round(1 - sse_m / sse_n, 4),   # πόσο της διακύμανσης εξηγούν οι ομάδες πέρα από τον μ.ό.
            "logloss": [round(ll_m / n, 4), round(ll_n / n, 4)],
            "gain": round((ll_n - ll_m) / ll_n * 100, 2),
            "team_gain": round((team_ll_n - team_ll_m) / team_ll_n * 100, 2),
            "ref_gain": round((ll_m - ll_r) / ll_m * 100, 2) if k in ("ca", "fo") else None,
            "ref_ok": bool(k in ("ca", "fo") and ll_r < ll_m),
            "calibration": [{"bucket": f"{b * 20}-{b * 20 + 20}%", "n": v[0], "pred": round(v[1] / v[0], 4),
                             "actual": round(v[2] / v[0], 4)} for b, v in sorted(cal.items()) if v[0] >= 30],
            "edge_total": et, "edge_team": eteam,
            "validated": et["ok"] or eteam["ok"],
        }
    # ημίχρονο: γκολ Α' ημιχρόνου (Poisson με το ποσοστό γκολ του πρωταθλήματος)
    H = [r["ht"] for r in rows if r.get("ht") and r["s"] in TEST]
    if H:
        res = {"n": len(H), "share": None, "lines": []}
        for L in (0.5, 1.5):
            pm_s = y_s = ll = 0.0
            for lh, la, hg, ag in H:
                p = stats.p_over(stats.nb_pmf(lh + la, 0, 15), L)
                y = hg + ag > L
                pm_s += p; y_s += y; ll += _ll(p, y)
            res["lines"].append({"line": L, "pred": round(pm_s / len(H), 4), "actual": round(y_s / len(H), 4),
                                 "logloss": round(ll / len(H), 4)})
        out["ht"] = res
    return out, disp


def main():
    print("• Έρευνα στατιστικών: συλλογή")
    rows = collect()
    res, disp = analyse(rows)
    for k, v in res.items():
        if k == "ht":
            print(f"  Ημίχρονο: {v['lines']}")
            continue
        print(f"  {v['name']:<16} μ.ό. {v['avg']:>5}  εξηγεί {v['explained'] * 100:5.1f}%  κέρδος log-loss {v['gain']:5.2f}%"
              f"  ομάδα {v['team_gain']:5.2f}%  διαιτ. {v['ref_gain']}  "
              f"σύνολο {v['edge_total']}  ομάδα {v['edge_team']}  α={v['alpha']} αT={v['alphaT']}")
    return res, disp


if __name__ == "__main__":
    main()
