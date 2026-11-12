"""Έλεγχος αξιοπιστίας (ποδόσφαιρο): python -m engine.audit_football

Για κάθε αγώνα 2022-26 (22 πρωταθλήματα) με αποδόσεις Pinnacle ΠΡΙΝ τον αγώνα:
 1. Πόσο απέχει η πιθανότητα που βγάζει το μοντέλο Poisson (όπως δουλεύει η εφαρμογή) από την ίδια την αγορά
    (1, Χ, 2, Over 2.5); Αν απέχει, το "value" μπορεί να είναι λάθος του ταιριάσματος και όχι πραγματικό κενό.
 2. Κερδίζουν τα "value" στη Bet365; Χωριστά: όσα βγαίνουν ΚΑΙ με την καθαρή πιθανότητα της αγοράς, και όσα
    βγαίνουν ΜΟΝΟ λόγω του ταιριάσματος Poisson.
 3. Βαθμονόμηση στις παράγωγες αγορές (G/G, διπλή ευκαιρία, Over 1.5/3.5, γκολ ομάδας, χάντικαπ, ημίχρονο):
    όταν λέμε 60%, βγαίνει 60%;
"""
import json
import math
from collections import defaultdict

import numpy as np

from . import config, history, model, sources

SEASONS = ["2223", "2324", "2425", "2526"]
RHO = model.RHO
K = 11


def grid():
    g = np.arange(0.10, 4.51, 0.02)
    LH, LA = np.meshgrid(g, g, indexing="ij")
    return LH.ravel(), LA.ravel(), matrices(LH.ravel(), LA.ravel())


def matrices(lh, la):
    """Πίνακες σκορ (n, 11, 11) με τη διόρθωση Dixon-Coles, όπως το model.score_matrix."""
    k = np.arange(K)
    fact = np.array([math.factorial(i) for i in k], dtype=float)
    ph = np.exp(-lh[:, None]) * lh[:, None] ** k / fact
    pa = np.exp(-la[:, None]) * la[:, None] ** k / fact
    M = ph[:, :, None] * pa[:, None, :]
    M[:, 0, 0] *= 1 - lh * la * RHO
    M[:, 0, 1] *= 1 + lh * RHO
    M[:, 1, 0] *= 1 + la * RHO
    M[:, 1, 1] *= 1 - RHO
    return M / M.sum((1, 2), keepdims=True)


I, J = np.meshgrid(np.arange(K), np.arange(K), indexing="ij")


def probs(M):
    return {"1": (M * (I > J)).sum((1, 2)), "X": (M * (I == J)).sum((1, 2)), "2": (M * (I < J)).sum((1, 2)),
            "O25": (M * (I + J > 2.5)).sum((1, 2))}


def main():
    LH, LA, GM = grid()
    GP = probs(GM)
    rows = []
    for code in config.RATING_LEAGUES:
        for s in SEASONS:
            for m in sources.fdcouk_league(code, s):
                o = m.get("odds") or {}
                if not (o.get("p1x2") and o.get("pou") and o.get("b1x2") and o.get("bou")) or m["hg"] is None:
                    continue
                rows.append(m)
    print(len(rows), "αγώνες με Pinnacle + Bet365")
    f1 = np.array([history._devig(m["odds"]["p1x2"]) for m in rows])
    fo = np.array([history._devig(m["odds"]["pou"])[0] for m in rows])
    # ταίριασμα όπως η εφαρμογή (ελάχιστα τετράγωνα σε 1, 2, Over 2.5)
    idx = np.empty(len(rows), int)
    for a in range(0, len(rows), 500):
        sl = slice(a, a + 500)
        e = (GP["1"][None, :] - f1[sl, 0:1]) ** 2 + (GP["2"][None, :] - f1[sl, 2:3]) ** 2 + (GP["O25"][None, :] - fo[sl, None]) ** 2
        idx[sl] = e.argmin(1)
    lh, la = LH[idx], LA[idx]
    M = GM[idx]
    P = probs(M)
    hg = np.array([int(m["hg"]) for m in rows]); ag = np.array([int(m["ag"]) for m in rows])
    res = {"1": hg > ag, "X": hg == ag, "2": hg < ag, "O25": hg + ag > 2.5, "U25": hg + ag < 2.5}
    fair = {"1": f1[:, 0], "X": f1[:, 1], "2": f1[:, 2], "O25": fo, "U25": 1 - fo}
    fit = {"1": P["1"], "X": P["X"], "2": P["2"], "O25": P["O25"], "U25": 1 - P["O25"]}
    b = {"1": np.array([m["odds"]["b1x2"][0] for m in rows]), "X": np.array([m["odds"]["b1x2"][1] for m in rows]),
         "2": np.array([m["odds"]["b1x2"][2] for m in rows]), "O25": np.array([m["odds"]["bou"][0] for m in rows]),
         "U25": np.array([m["odds"]["bou"][1] for m in rows])}
    out = {"matches": len(rows), "fit_gap": {}, "value": {}, "derived": {}}
    print("\n1) Απόκλιση ταιριάσματος Poisson από την αγορά (μονάδες πιθανότητας)")
    for k in fair:
        d = fit[k] - fair[k]
        out["fit_gap"][k] = {"mean": round(float(d.mean()) * 100, 2), "abs": round(float(np.abs(d).mean()) * 100, 2),
                             "p95": round(float(np.percentile(np.abs(d), 95)) * 100, 2)}
        print(f"   {k:4s} μέση {d.mean() * 100:+.2f}  μέση απόλυτη {np.abs(d).mean() * 100:.2f}  95%: {np.percentile(np.abs(d), 95) * 100:.2f}")

    def roi(mask, k):
        n = int(mask.sum())
        if not n:
            return {"n": 0}
        pr = np.where(res[k][mask], b[k][mask] - 1, -1.0)
        return {"n": n, "roi": round(float(pr.mean()), 4), "se": round(float(pr.std() / math.sqrt(n)), 4),
                "hit": round(float(res[k][mask].mean()), 4), "p_fit": round(float(fit[k][mask].mean()), 4),
                "p_mkt": round(float(fair[k][mask].mean()), 4)}

    print("\n2) 'Value' στη Bet365 (EV >= 3%, απόδοση 1.30-4.50)")
    tot = defaultdict(lambda: [0, 0.0])
    for k in fair:
        ok = (b[k] >= config.MIN_ODDS) & (b[k] <= config.MAX_ODDS)
        v_fit = ok & (fit[k] * b[k] - 1 >= config.MIN_EDGE)
        v_mkt = ok & (fair[k] * b[k] - 1 >= config.MIN_EDGE)
        r = {"app": roi(v_fit, k), "market": roi(v_mkt, k), "both": roi(v_fit & v_mkt, k), "fit_only": roi(v_fit & ~v_mkt, k),
             "market_only": roi(v_mkt & ~v_fit, k)}
        out["value"][k] = r
        for name, x in r.items():
            if x["n"]:
                tot[name][0] += x["n"]; tot[name][1] += x["roi"] * x["n"]
        print(f"   {k:4s} " + " | ".join(f"{n}: {x['n']} ROI {x.get('roi', 0) * 100:+.1f}%" for n, x in r.items()))
    out["value"]["_total"] = {n: {"n": v[0], "roi": round(v[1] / v[0], 4) if v[0] else None} for n, v in tot.items()}
    print("   ΣΥΝΟΛΟ " + " | ".join(f"{n}: {v[0]} ROI {v[1] / max(v[0], 1) * 100:+.1f}%" for n, v in tot.items()))

    print("\n3) Βαθμονόμηση παράγωγων αγορών (πρόβλεψη -> πραγματικό)")
    hth = np.array([m["hthg"] if m.get("hthg") is not None else -1 for m in rows])
    hta = np.array([m["htag"] if m.get("htag") is not None else -1 for m in rows])
    der = {
        "G/G": ((M * ((I > 0) & (J > 0))).sum((1, 2)), (hg > 0) & (ag > 0)),
        "1X": (P["1"] + P["X"], hg >= ag), "X2": (P["2"] + P["X"], hg <= ag), "12": (P["1"] + P["2"], hg != ag),
        "Over 1.5": ((M * (I + J > 1.5)).sum((1, 2)), hg + ag > 1.5), "Over 3.5": ((M * (I + J > 3.5)).sum((1, 2)), hg + ag > 3.5),
        "Γηπ. Over 0.5": ((M * (I > 0.5)).sum((1, 2)), hg > 0.5), "Γηπ. Over 1.5": ((M * (I > 1.5)).sum((1, 2)), hg > 1.5),
        "Φιλ. Over 0.5": ((M * (J > 0.5)).sum((1, 2)), ag > 0.5), "Φιλ. Over 1.5": ((M * (J > 1.5)).sum((1, 2)), ag > 1.5),
        "1 (-1.5)": ((M * (I - J > 1.5)).sum((1, 2)), hg - ag > 1.5), "2 (+1.5)": ((M * (I - J < 1.5)).sum((1, 2)), hg - ag < 1.5),
        "1 (+1.5)": ((M * (I - J > -1.5)).sum((1, 2)), hg - ag > -1.5), "2 (-1.5)": ((M * (J - I > 1.5)).sum((1, 2)), ag - hg > 1.5),
        "X (ισοπαλία)": (P["X"], hg == ag),
    }
    for name, (p, y) in der.items():
        bk = []
        for lo in np.arange(0, 1, 0.1):
            msk = (p >= lo) & (p < lo + 0.1)
            if msk.sum() >= 200:
                bk.append({"bucket": f"{int(lo * 100)}-{int(lo * 100) + 10}%", "n": int(msk.sum()), "pred": round(float(p[msk].mean()), 4),
                           "actual": round(float(y[msk].mean()), 4)})
        err = sum(abs(x["pred"] - x["actual"]) * x["n"] for x in bk) / max(sum(x["n"] for x in bk), 1)
        bias = float(p.mean() - y.mean())
        out["derived"][name] = {"bias": round(bias * 100, 2), "cal_err": round(err * 100, 2), "buckets": bk}
        print(f"   {name:14s} μέση πρόβλεψη {p.mean():.3f} πραγματικό {y.mean():.3f} (διαφορά {bias * 100:+.2f}) · σφάλμα βαθμονόμησης {err * 100:.2f}")
    (config.CACHE / "audit_football.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
