"""Έρευνα επιλογών παικτών (13/11/2026): python -m engine.props_research2

Δύο ιδέες του χρήστη, ελεγμένες με δεδομένα (κάθε εμφάνιση προβλέπεται μόνο με τους προηγούμενους αγώνες,
οι ρυθμίσεις βρίσκονται στο πρώτο 60% των ημερομηνιών και ελέγχονται στο τελευταίο 40%):

 Α. Πλαίσιο αγώνα: πόσο "ανοιχτό" (ρυθμός = πόντοι των δύο ομάδων στα ματς τους) και πόσο άνισο (διαφορά δυναμικότητας)
    είναι το παιχνίδι. Εξηγούν κάτι πέρα από όσα ήδη μετράει το μοντέλο (λεπτά, ρυθμός παίκτη, τι δίνει ο αντίπαλος);
 Β. Ακραίοι αγώνες: ένας αγώνας με 7 λάθη δεν πρέπει να "χαλάει" τον μέσο όρο. Δοκιμάζουμε
    - μέσο όρο χωρίς τα άκρα (το μεγαλύτερο και το μικρότερο κόβονται στο αμέσως επόμενο),
    - ανάμειξη με το πόσες φορές πέρασε πραγματικά τη γραμμή στους τελευταίους 20 αγώνες.
    Μετρική: log-loss της πιθανότητας Over σε 3 γραμμές γύρω από τον μέσο όρο 10 αγώνων (μικρότερο = καλύτερο).
"""
import json
import math
from collections import defaultdict

from . import basket, bcl, config, esake, espn, props

STATS = list(props.STATS)
W_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def load(cid):
    comp = config.BASKET[cid]
    year = basket._season()
    src = comp.get("src")
    if src == "espn":
        cur, prev = espn.nba_games(comp.get("days", 3))
    elif src == "esake":
        cur, prev = esake.games(year), esake.games(year - 1)
    else:
        cur, prev = basket.games(comp["feed"], year), basket.games(comp["feed"], year - 1)
    pc, pp = [g for g in cur if g["played"]], [g for g in prev if g["played"]]
    if src == "espn":
        box = espn.nba_boxscores(pc + pp)
    elif src == "esake":
        box = esake.boxscores(pc + pp)
    else:
        box = basket.boxscores(comp["feed"], year, pc)
        pbox = basket.boxscores(comp["feed"], year - 1, pp, limit=0)
        pp = [dict(g, code=f"p{g['code']}") for g in pp]
        box = {**{f"p{k}": v for k, v in pbox.items()}, **box}
    return pp + pc, box


def team_context(M):
    """Ανά ομάδα: [(ημερομηνία, πόντοι υπέρ, πόντοι κατά)] από τα boxscores."""
    pf = defaultdict(dict)
    for d, player, team, opp, mins, v in M.logs:
        pf[(team, d)]["for"] = pf[(team, d)].get("for", 0) + v["pts"]
        pf[(team, d)]["opp"] = opp
    out = defaultdict(list)
    for (team, d), x in pf.items():
        ag = pf.get((x["opp"], d), {}).get("for")
        if ag is not None:
            out[team].append((d, x["for"], ag))
    for t in out:
        out[t].sort()
    return out


def ctx_features(TC, team, opp, date, K=5):
    """(ρυθμός αγώνα σε σχέση με τη λίγκα, απόλυτη διαφορά δυναμικότητας σε πόντους) μόνο από προηγούμενους αγώνες."""
    lg = [f + a for t, rows in TC.items() for d, f, a in rows if d[:10] < date[:10]]
    if len(lg) < 40:
        return None
    lg_avg = sum(lg) / len(lg)

    def tm(t):
        rows = [(f, a) for d, f, a in TC.get(t, []) if d[:10] < date[:10]][-20:]
        n = len(rows)
        if n < 3:
            return None
        pace = (sum(f + a for f, a in rows) + K * lg_avg) / (n + K) / lg_avg
        net = sum(f - a for f, a in rows) / (n + K)
        return pace, net
    a, b = tm(team), tm(opp)
    if not a or not b:
        return None
    return a[0] + b[0] - 1, abs(a[1] - b[1]), a[1] - b[1]


def nb_over(mu, phi, L):
    return props._nb_over(mu, phi, L)


def collect(cid):
    games, box = load(cid)
    M = props.Model(games, box)
    mres = props.minutes_research(M)
    TC = team_context(M)
    rows = []
    for date, player, team, opp, mins, v in M.logs:
        ab = props._absent_in(M, team, date) if mres else []
        extra = M.minutes_plan(team, date, ab).get(player, 0.0) if ab else 0.0
        pr = M.predict(player, team, opp, date, extra, M.usage_plan(team, date, ab) if ab else None)
        if not pr:
            continue
        P, m_exp = pr
        h = [e for e in M.by_player.get((player, team), []) if e[0][:10] < date[:10]]
        l15, l20 = h[-15:], h[-20:]
        cx = ctx_features(TC, team, opp, date)
        r = {"d": date[:10], "cx": cx, "s": {}}
        for k in STATS:
            # τιμές ανά αγώνα "ανηγμένες" στα αναμενόμενα λεπτά (ώστε να συγκρίνονται)
            sc = sorted(e[5][k] / e[4] * m_exp for e in l15 if e[4] >= 5)
            if len(sc) >= 6:
                w = [sc[1]] + sc[1:-1] + [sc[-2]]  # κόβουμε το μικρότερο και το μεγαλύτερο στο αμέσως επόμενο
                trim = sum(w) / len(w)
                med = sc[len(sc) // 2] if len(sc) % 2 else (sc[len(sc) // 2 - 1] + sc[len(sc) // 2]) / 2
            else:
                trim = med = None
            of = M.opp_factor(player, team, opp, k, date)
            r["s"][k] = {"mu": P[k][0], "n10": P[k][1], "x": v[k], "of": of,
                         "trim": trim * of if trim is not None else None, "med": med * of if med is not None else None,
                         "raw20": [e[5][k] for e in l20]}
        rows.append(r)
    return rows


def split(rows):
    ds = sorted({r["d"] for r in rows})
    cut = ds[int(len(ds) * 0.6)]
    return [r for r in rows if r["d"] < cut], [r for r in rows if r["d"] >= cut]


def phi_of(pairs):
    num = sum((x - mu) ** 2 - mu for mu, x in pairs)
    den = sum(mu * mu for mu, _ in pairs)
    return max(num / den, 0.0) if den else 0.0


def ll(p, y):
    p = min(max(p, 0.01), 0.99)
    return -math.log(p if y else 1 - p)


def ols(X, y):
    """y ~ a + b·x (πολλαπλή). Επιστρέφει συντελεστές και z."""
    n, k = len(y), len(X[0]) + 1
    Z = [[1.0] + list(x) for x in X]
    A = [[sum(z[i] * z[j] for z in Z) for j in range(k)] for i in range(k)]
    b = [sum(z[i] * yy for z, yy in zip(Z, y)) for i in range(k)]
    from .context_research import _solve
    beta = _solve(A, b)
    res = sum((yy - sum(c * v for c, v in zip(beta, z))) ** 2 for z, yy in zip(Z, y)) / max(n - k, 1)
    inv = [_solve(A, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
    se = [math.sqrt(max(inv[i][i] * res, 1e-18)) for i in range(k)]
    return beta, [c / s for c, s in zip(beta, se)]


def analyse(cid, rows):
    tr, te = split(rows)
    out = {"n": len(rows), "A": {}, "B": {}}
    for k in STATS:
        get = lambda R: [r["s"][k] for r in R]
        # ---------- Α. πλαίσιο αγώνα ----------
        Atr = [(r["cx"], r["s"][k]) for r in tr if r["cx"] and r["s"][k]["mu"] > 0.3]
        Ate = [(r["cx"], r["s"][k]) for r in te if r["cx"] and r["s"][k]["mu"] > 0.3]
        if len(Atr) > 300 and len(Ate) > 200:
            X = [[c[0] - 1, c[1] / 10] for c, s in Atr]
            y = [s["x"] / s["mu"] - 1 for c, s in Atr]
            beta, z = ols(X, y)
            base = sum(((s["x"] / s["mu"] - 1) - beta[0]) ** 2 for c, s in Ate) / len(Ate)
            full = sum(((s["x"] / s["mu"] - 1) - (beta[0] + beta[1] * (c[0] - 1) + beta[2] * c[1] / 10)) ** 2 for c, s in Ate) / len(Ate)
            # MAE στην πράξη: μ × (1 + διόρθωση)
            mae0 = sum(abs(s["x"] - s["mu"]) for c, s in Ate) / len(Ate)
            mae1 = sum(abs(s["x"] - s["mu"] * max(1 + beta[1] * (c[0] - 1) + beta[2] * c[1] / 10, 0.5)) for c, s in Ate) / len(Ate)
            out["A"][k] = {"pace": [round(beta[1], 3), round(z[1], 1)], "mismatch": [round(beta[2], 3), round(z[2], 1)],
                           "test_gain_pct": round((base - full) / base * 100, 3), "mae": [round(mae0, 4), round(mae1, 4)],
                           "n": [len(Atr), len(Ate)]}
        # ---------- Β. ακραίοι αγώνες / συχνότητα ----------
        Btr = [s for s in get(tr) if s["trim"] is not None]
        Bte = [s for s in get(te) if s["trim"] is not None]
        if len(Btr) < 300 or len(Bte) < 200:
            continue
        phi = {m: phi_of([(s[m], s["x"]) for s in Btr]) for m in ("mu", "trim", "med")}

        def lines(s):
            L0 = props.half(s["n10"])
            return [L for L in (L0 - 1, L0, L0 + 1) if L > 0]

        def freq(s, L):
            v = s["raw20"]
            return (sum(1 for x in v if x > L) + 1) / (len(v) + 2)

        def score(S, fn):
            t = n = 0
            for s in S:
                for L in lines(s):
                    t += ll(fn(s, L), s["x"] > L); n += 1
            return t / max(n, 1)
        res = {"n": [len(Btr), len(Bte)], "phi": {m: round(v, 4) for m, v in phi.items()},
               "mae": {m: round(sum(abs(s["x"] - s[m]) for s in Bte) / len(Bte), 4) for m in ("mu", "trim", "med", "n10")}}
        # καλύτερο βάρος ανάμειξης (στο train) για κάθε βάση
        best = {}
        for m in ("mu", "trim"):
            for a_ in (0.0, 0.5, 1.0):  # ανάμειξη μέσου: a_·μοντέλο + (1-a_)·χωρίς άκρα  (μόνο για m == "mu")
                if m == "trim" and a_ != 1.0:
                    continue
                def mean_of(s, a_=a_, m=m):
                    return s["mu"] if m == "mu" and a_ == 1.0 else s["trim"] if m == "trim" else a_ * s["mu"] + (1 - a_) * s["trim"]
                ph = phi["mu"] if m == "mu" and a_ == 1.0 else phi["trim"]
                for w in W_GRID:
                    fn = lambda s, L, w=w, mean_of=mean_of, ph=ph: w * nb_over(mean_of(s), ph, L) + (1 - w) * freq(s, L)
                    name = f"{m}{'' if a_ == 1.0 else a_}|w{w}"
                    best[name] = (score(Btr, fn), score(Bte, fn))
        res["variants"] = {n_: [round(a, 4), round(b, 4)] for n_, (a, b) in sorted(best.items(), key=lambda x: x[1][0])}
        res["current_test"] = round(best["mu|w1.0"][1], 4)
        pick = min(best, key=lambda n_: best[n_][0])  # επιλογή ΜΟΝΟ από το train
        res["picked"] = pick
        res["picked_test"] = round(best[pick][1], 4)
        out["B"][k] = res
    return out


def main():
    allres = {}
    for cid in ("EL", "NBA", "EC", "GBL"):
        rows = collect(cid)
        print(f"{cid}: {len(rows)} εμφανίσεις", flush=True)
        allres[cid] = analyse(cid, rows)
        print("  Α. πλαίσιο αγώνα (συντελεστής [τιμή, z] · κέρδος στον έλεγχο %)")
        for k, a in allres[cid]["A"].items():
            print(f"    {k:4s} ρυθμός {a['pace']}  ανισότητα {a['mismatch']}  κέρδος {a['test_gain_pct']}%  MAE {a['mae']}")
        print("  Β. ακραίοι αγώνες (log-loss ελέγχου: τωρινό -> επιλεγμένο από train)")
        for k, b in allres[cid]["B"].items():
            print(f"    {k:4s} τωρινό {b['current_test']} -> {b['picked']} {b['picked_test']} | MAE {b['mae']}")
    (config.DATA_OUT / "props_research2.json").write_text(json.dumps(allres, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
