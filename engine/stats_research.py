"""Έρευνα στα στατιστικά αγώνα: κόρνερ, σουτ, σουτ στην εστία, φάουλ, κάρτες, αποκρούσεις, ημίχρονο.

python -m engine.stats_research

Για 22 πρωταθλήματα × 5 σεζόν (2021/22-2025/26), εβδομάδα-εβδομάδα, το μοντέλο προβλέπει κάθε μετρική
ΜΟΝΟ με ό,τι είχε παιχτεί πριν. Συγκρίνουμε με τον "αφελή" τρόπο (μέσος όρος του πρωταθλήματος).

Έλεγχος "κυλιόμενος": για κάθε σεζόν ελέγχου (2023/24, 2024/25, 2025/26) οι παράμετροι (διασπορά,
επιστροφή στον μέσο όρο, σενάριο αγώνα) υπολογίζονται ΜΟΝΟ από τις προηγούμενες σεζόν. Ένα εύρημα
θεωρείται επιβεβαιωμένο μόνο αν ισχύει και στους 3 ελέγχους.
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta

from . import config, history, model, sources, stats

SEASONS = [("2122", "2021"), ("2223", "2122"), ("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
TESTS = ["2324", "2425", "2526"]
CACHE = "research_stats2.json"


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


def _sup(m, lh, la):
    """Πόσο φαβορί είναι ο γηπεδούχος: P(1) - P(2) από τις αποδόσεις (Pinnacle/μ.ό.), αλλιώς από το μοντέλο."""
    o = m.get("odds") or {}
    fair = o.get("p1x2") or o.get("a1x2") or o.get("b1x2")
    if fair:
        p = history._devig(fair)
        return round(p[0] - p[2], 3)
    M = model.score_matrix(lh, la)
    n = len(M)
    return round(sum(M[i][j] * ((i > j) - (i < j)) for i in range(n) for j in range(n)), 3)


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
                        x = {}
                        for k in stats.STATS:
                            v = stats.values(m, k)
                            if v is None or k not in (lg.get("sx") or {}):
                                continue
                            nh, na = lg["sx"][k]
                            h, a = rh["sx"][k], ra["sx"][k]
                            # [μ.ό. γηπ., μ.ό. φιλ., υπέρ γηπ., κατά φιλ., υπέρ φιλ., κατά γηπ., πραγμ. γηπ., πραγμ. φιλ.]
                            x[k] = [round(nh, 2), round(na, 2), h[0], a[1], a[0], h[1], v[0], v[1]]
                        lh, la, _, _ = model.expected(rh, ra, lg)
                        row = {"lg": code, "s": season, "x": x, "sup": _sup(m, lh, la),
                               "rf": [round(f, 3) for f in refs.get(history.ref_key(m.get("ref")), (1.0, 1.0))]
                               if m.get("ref") else None}
                        if m.get("hthg") is not None:
                            row["ht"] = [round(lh * lg["ht_share"], 3), round(la * lg["ht_share"], 3),
                                         int(m["hthg"]), int(m["htag"])]
                        rows.append(row)
                week = nxt
            print(f"  {code} {season}: {len(rows)} αγώνες συνολικά", flush=True)
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


def _reg(pairs):
    """Κλίση χωρίς σταθερό όρο: y ≈ β·x."""
    num = sum(x * y for x, y in pairs)
    den = sum(x * x for x, _ in pairs)
    return num / den if den else 0.0


def _raw(x, own_only=False):
    """Πρόβλεψη πριν τις διορθώσεις: μ.ό. × υπέρ ομάδας × κατά αντιπάλου (ή μόνο ομάδα)."""
    if own_only:
        return x[0] * x[2], x[1] * x[4]
    return x[0] * x[2] * x[3], x[1] * x[4] * x[5]


def _means(x, sup, d, gs=True, own_only=False):
    rh, ra = _raw(x, own_only)
    mh, ma = x[0] + d["a"] * (rh - x[0]), x[1] + d["a"] * (ra - x[1])
    mT = x[0] + x[1] + d["aT"] * (rh + ra - x[0] - x[1])
    if gs:
        fh, fa, fT = stats._gs(sup, d)
        mh, ma, mT = mh * fh, ma * fa, mT * fT
    return mh, ma, mT


def fit_params(rows, k):
    """Παράμετροι μιας μετρικής από ένα σύνολο αγώνων (χωρίς να κοιτάμε τον έλεγχο)."""
    X = [(r, r["x"][k]) for r in rows if k in r["x"]]
    if len(X) < 300:
        return None
    a = min(max(_reg([(_raw(x)[i] - x[i], x[6 + i] - x[i]) for _, x in X for i in (0, 1)]), 0.0), 1.0)
    aT = min(max(_reg([(sum(_raw(x)) - x[0] - x[1], x[6] + x[7] - x[0] - x[1]) for _, x in X]), 0.0), 1.0)
    ch = sum(r["sup"] for r, _ in X) / len(X)
    cT = sum(abs(r["sup"]) for r, _ in X) / len(X)
    d = {"a": round(a, 3), "aT": round(aT, 3), "b": 0.0, "bT": 0.0,
         "ch": round(ch, 4), "ca": round(-ch, 4), "cT": round(cT, 4)}
    mu = [_means(x, r["sup"], d, gs=False) for r, x in X]
    # σενάριο αγώνα: (πραγμ. - μ) ≈ β · μ · (sup - c)
    b = _reg([(m[0] * (r["sup"] - d["ch"]), x[6] - m[0]) for (r, x), m in zip(X, mu)] +
             [(m[1] * (-r["sup"] - d["ca"]), x[7] - m[1]) for (r, x), m in zip(X, mu)])
    bT = _reg([(m[2] * (abs(r["sup"]) - d["cT"]), x[6] + x[7] - m[2]) for (r, x), m in zip(X, mu)])
    d.update(b=round(b, 4), bT=round(bT, 4))
    mu = [_means(x, r["sup"], d) for r, x in X]
    d["pt"] = _disp([(m[0], x[6]) for (r, x), m in zip(X, mu)] + [(m[1], x[7]) for (r, x), m in zip(X, mu)])
    d["pT"] = _disp([(m[2], x[6] + x[7]) for (r, x), m in zip(X, mu)])
    return d


def _ci(p, n):
    return round(1.96 * math.sqrt(max(p * (1 - p), 1e-9) / n), 4) if n else None


def evaluate(rows, k, d):
    """Αποτελέσματα μιας μετρικής σε αγώνες ελέγχου με παραμέτρους d."""
    X = [(r, r["x"][k]) for r in rows if k in r["x"]]
    n = len(X)
    if not n:
        return None
    acc = defaultdict(float)
    edge, tedge, by_lg = [], [], defaultdict(list)
    cal = defaultdict(lambda: [0, 0.0, 0])
    for r, x in X:
        nT, act = x[0] + x[1], x[6] + x[7]
        full = _means(x, r["sup"], d)
        nogs = _means(x, r["sup"], d, gs=False)
        own = _means(x, r["sup"], d, own_only=True)
        rf = (r["rf"][0] if k == "ca" else r["rf"][1] if k == "fo" else 1.0) if r.get("rf") else 1.0
        L = math.floor(nT) + 0.5
        y = act > L

        def P(mu):
            return stats.p_over(stats.nb_pmf(mu, d["pT"]), L)
        pm, pn = P(full[2]), P(nT)
        acc["ll_m"] += _ll(pm, y); acc["ll_n"] += _ll(pn, y)
        acc["ll_gs0"] += _ll(P(nogs[2]), y)
        acc["ll_ref"] += _ll(P(full[2] * rf), y)
        acc["sse_m"] += (act - full[2]) ** 2; acc["sse_n"] += (act - nT) ** 2
        b = min(int(pm * 5), 4)
        cal[b][0] += 1; cal[b][1] += pm; cal[b][2] += y
        if abs(pm - pn) >= stats.EDGE_MIN:
            edge.append((pm, pn, y) if pm > pn else (1 - pm, 1 - pn, not y))
        for i in (0, 1):
            Lt = math.floor(x[i]) + 0.5
            yt = x[6 + i] > Lt

            def Q(mu):
                return stats.p_over(stats.nb_pmf(mu, d["pt"]), Lt)
            qm, qn = Q(full[i]), Q(x[i])
            acc["tl_m"] += _ll(qm, yt); acc["tl_n"] += _ll(qn, yt)
            acc["tl_gs0"] += _ll(Q(nogs[i]), yt); acc["tl_own"] += _ll(Q(own[i]), yt)
            if abs(qm - qn) >= stats.EDGE_MIN:
                e = (qm, qn, yt) if qm > qn else (1 - qm, 1 - qn, not yt)
                tedge.append(e); by_lg[r["lg"]].append(e)

    def summ(E, better):
        m = len(E)
        if not m:
            return {"n": 0, "model": None, "avg": None, "hit": None, "ci": None, "ok": False}
        pm_, pn_, h_ = (sum(e[j] for e in E) / m for j in range(3))
        return {"n": m, "model": round(pm_, 4), "avg": round(pn_, 4), "hit": round(h_, 4), "ci": _ci(h_, m),
                "ok": bool(m >= 100 and better and abs(h_ - pm_) < abs(h_ - pn_))}

    def g(a, b_):
        return round((acc[b_] - acc[a]) / acc[b_] * 100, 2) if acc[b_] else None
    return {
        "n": n, "avg": round(sum(x[6] + x[7] for _, x in X) / n, 2), "sd": round(math.sqrt(acc["sse_m"] / n), 2),
        "explained": round(1 - acc["sse_m"] / acc["sse_n"], 4) if acc["sse_n"] else None,
        "gain": g("ll_m", "ll_n"), "team_gain": g("tl_m", "tl_n"),
        # πόσο βοηθάει ο αντίπαλος / το σενάριο αγώνα (σε σχέση με το μοντέλο χωρίς αυτά)
        "opp_gain": g("tl_m", "tl_own"), "gs_gain": g("tl_m", "tl_gs0"), "gs_gain_total": g("ll_m", "ll_gs0"),
        "ref_gain": g("ll_ref", "ll_m") if k in ("ca", "fo") else None,
        "ref_better": bool(acc["ll_ref"] < acc["ll_m"]),
        "calibration": [{"bucket": f"{b * 20}-{b * 20 + 20}%", "n": v[0], "pred": round(v[1] / v[0], 4),
                         "actual": round(v[2] / v[0], 4)} for b, v in sorted(cal.items()) if v[0] >= 30],
        "edge_total": summ(edge, acc["ll_m"] < acc["ll_n"]),
        "edge_team": summ(tedge, acc["tl_m"] < acc["tl_n"]),
        "by_league": {lg: summ(E, True) for lg, E in by_lg.items() if len(E) >= 40},
    }


def analyse(rows):
    out, disp = {}, {}
    for k, name in stats.STATS.items():
        per = {}
        for t in TESTS:
            d = fit_params([r for r in rows if r["s"] < t], k)
            if d:
                per[t] = evaluate([r for r in rows if r["s"] == t], k, d)
        final = fit_params(rows, k)  # για τη ζωντανή εφαρμογή: όλες οι σεζόν
        if len(per) < len(TESTS) or not final:
            continue
        disp[k] = final
        pooled = evaluate([r for r in rows if r["s"] in TESTS], k, final)
        ok_t = all(p["edge_total"]["ok"] for p in per.values())
        ok_team = all(p["edge_team"]["ok"] for p in per.values())
        pooled["edge_total"]["ok"] = ok_t
        pooled["edge_team"]["ok"] = ok_team
        out[k] = {"name": name, **pooled, "params": final, "validated": ok_t or ok_team,
                  "ref_ok": bool(k in ("ca", "fo") and all(p["ref_better"] for p in per.values())),
                  "tests": {t: {"n": p["n"], "gain": p["gain"], "team_gain": p["team_gain"],
                                "edge_total": p["edge_total"], "edge_team": p["edge_team"]} for t, p in per.items()}}
    H = [r["ht"] for r in rows if r.get("ht") and r["s"] in TESTS]
    if H:
        res = {"n": len(H), "lines": []}
        for L in (0.5, 1.5):
            pm_s = y_s = 0.0
            for lh, la, hg, ag in H:
                pm_s += stats.p_over(stats.nb_pmf(lh + la, 0, 15), L); y_s += hg + ag > L
            res["lines"].append({"line": L, "pred": round(pm_s / len(H), 4), "actual": round(y_s / len(H), 4)})
        out["ht"] = res
    out["_meta"] = {"matches": len(rows), "seasons": [s for s, _ in SEASONS], "tests": TESTS,
                    "leagues": sorted({r["lg"] for r in rows})}
    return out, disp


def main():
    print("• Έρευνα στατιστικών: συλλογή")
    rows = collect()
    res, disp = analyse(rows)
    for k, v in res.items():
        if k.startswith("_") or k == "ht":
            continue
        print(f"  {v['name']:<16} κέρδος σύνολο {v['gain']}% ομάδα {v['team_gain']}% · αντίπαλος {v['opp_gain']}% · "
              f"σενάριο {v['gs_gain']}%/{v['gs_gain_total']}% · διαιτ. {v['ref_gain']} ({v['ref_ok']})")
        for t, p in v["tests"].items():
            et, eT = p["edge_team"], p["edge_total"]
            print(f"      {t}: ομάδα {et['model']}/{et['avg']}/{et['hit']} ({et['n']}) ok={et['ok']}"
                  f" · σύνολο {eT['model']}/{eT['avg']}/{eT['hit']} ({eT['n']}) ok={eT['ok']}")
        print(f"      παράμετροι {v['params']}")
    print(f"  {res['_meta']['matches']} αγώνες")
    return res, disp


if __name__ == "__main__":
    main()
