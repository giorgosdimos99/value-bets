"""Μακροχρόνια: δημιουργία site/data/futures.json για την καρτέλα «Σεζόν»."""
import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from . import config, futures as F

VALUE_EDGE = 1.08  # «συμφέρει από»: δίκαιη απόδοση +8% (μακροχρόνια: περισσότερη αβεβαιότητα + δεσμευμένα χρήματα)
NAMES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A", "D1": "Bundesliga", "F1": "Ligue 1", "P1": "Primeira Liga",
         "N1": "Eredivisie", "T1": "Süper Lig", "E1": "Championship", "E2": "League One", "E3": "League Two",
         "D2": "2. Bundesliga", "I2": "Serie B", "SP2": "Segunda División", "F2": "Ligue 2"}


def _sel(t, p, mkt=None):
    d = {"t": t, "p": round(p, 4), "fair": round(1 / p, 2) if p > 0 else None, "min_odds": round(VALUE_EDGE / p, 2) if p > 0 else None}
    if mkt is not None:
        d["mkt"] = round(mkt, 4)
    return d


def _market(key, label, probs, top=14, note=None, mkt=None):
    sel = sorted(((t, p) for t, p in probs.items() if p >= 0.003), key=lambda x: -x[1])[:top]
    m = {"key": key, "label": label, "sel": [_sel(t, p, (mkt or {}).get(t)) for t, p in sel]}
    if note:
        m["note"] = note
    return m


def _lines(samples, step=5):
    mu = float(samples.mean())
    base = math.floor(mu) + 0.5
    return [[L, round(float((samples > L).mean()), 3)] for L in (base - step, base, base + step) if L > 0]


# ---------------- ποδόσφαιρο ----------------

def football_league(code, name):
    from . import sources
    cur = [m for m in sources.fdcouk_league(code, config.SEASON) if m["date"] and m["hg"] is not None]
    prev = [m for m in sources.fdcouk_league(code, config.PREV_SEASON) if m["date"] and m["hg"] is not None]
    teams = sorted({m["home"] for m in cur} | {m["away"] for m in cur})
    n = len(teams)
    if n < 10 or len(cur) < n * 2:
        return None
    R = F.ratings(cur, prev, datetime.now(timezone.utc))
    if not R:
        return None
    P, xp, T, nrem = F.simulate(teams, cur, R)
    L = F.simulate.last
    pos, pts, idx = L["pos"], L["pts"], L["idx"]
    mks = [_market(key, label, {t: F.market_p(P[t], kind, k, n) for t in teams}) for key, label, kind, k in F.LEAGUES[code]]
    # πρωταθλητής χωρίς το φαβορί: ο καλύτερος από τους υπόλοιπους
    fav = max(teams, key=lambda t: P[t][0])
    fav1 = pos[:, idx[fav]] == 0
    wo = {t: float(((pos[:, idx[t]] == 0) | ((pos[:, idx[t]] == 1) & fav1)).mean()) for t in teams if t != fav}
    mks.insert(1, _market("wo", f"Πρωταθλητής χωρίς {fav}", wo))
    # ποιος τερματίζει ψηλότερα (γειτονικά ζευγάρια της αναμενόμενης κατάταξης)
    order = sorted(teams, key=lambda t: -xp[t])
    h2h = [{"a": a, "b": b, "p": round(float((pos[:, idx[a]] < pos[:, idx[b]]).mean()), 3)} for a, b in zip(order, order[1:])]
    tbl = []
    for t in sorted(teams, key=lambda t: (-T[t][0], -T[t][1], -T[t][2])):
        j = idx[t]
        tbl.append({"t": t, "g": T[t][3], "pts": T[t][0], "gd": T[t][1], "xpts": round(xp[t], 1),
                    "xpos": round(float((P[t] * np.arange(1, n + 1)).sum()), 1), "dist": [round(float(x), 3) for x in P[t]],
                    "lines": _lines(pts[:, j])})
    return {"id": code, "name": name, "sport": "football", "n": n, "progress": round(1 - nrem / (n * (n - 1)), 3), "rem": nrem,
            "markets": mks, "h2h": h2h, "table": tbl, "lines_label": "Βαθμοί στο τέλος"}


# ---------------- Ελλάδα: 26 αγωνιστικές + play-off / play-out ----------------
# 1-4: όλοι με όλους εντός-εκτός με όλους τους βαθμούς, 5-8: με τους μισούς, 9-14: με όλους, υποβιβάζονται οι 2 τελευταίοι.
GREECE_SPLIT = [(0, 4, 1.0), (4, 8, 0.5), (8, 14, 1.0)]
DEDUCT = {"G1": {"Volos NFC": -3}}  # Βόλος -3 (υπόθεση play-out 2024/25)
GREECE_MK = [("win", "Πρωταθλητής", "top", 1), ("t2", "Top 2 (Champions League)", "top", 2),
             ("t4", "Top 4 (play-off τίτλου)", "top", 4), ("t8", "Top 8 (εκτός play-out)", "top", 8),
             ("b2", "Υποβιβασμός (2 τελευταίοι)", "bot", 2), ("last", "Τελευταίος", "bot", 1)]


def greece():
    from . import sources
    cur = sorted([m for m in sources.fdcouk_league("G1", config.SEASON) if m["date"] and m["hg"] is not None], key=lambda m: m["date"])
    prev = [m for m in sources.fdcouk_league("G1", config.PREV_SEASON) if m["date"] and m["hg"] is not None]
    teams = sorted({m["home"] for m in cur} | {m["away"] for m in cur})
    n = len(teams)
    if n != 14 or len(cur) < 20:
        return None
    seen, rs, ph2 = set(), [], []
    for m in cur:  # 1η φορά κάθε ζευγαριού = κανονική περίοδος, ό,τι ξαναπαίζεται = 2η φάση
        k = (m["home"], m["away"])
        (ph2 if k in seen else rs).append(m)
        seen.add(k)
    R = F.ratings(cur, prev, datetime.now(timezone.utc))
    P, xp, T, nrem = F.simulate(teams, rs, R, deduct=DEDUCT["G1"], split=GREECE_SPLIT, played2=ph2)
    L = F.simulate.last
    pos, pts, idx = L["pos"], L["pts"], L["idx"]
    mks = [_market(key, label, {t: F.market_p(P[t], kind, k, n) for t in teams}) for key, label, kind, k in GREECE_MK]
    fav = max(teams, key=lambda t: P[t][0])
    fav1 = pos[:, idx[fav]] == 0
    wo = {t: float(((pos[:, idx[t]] == 0) | ((pos[:, idx[t]] == 1) & fav1)).mean()) for t in teams if t != fav}
    mks.insert(1, _market("wo", f"Πρωταθλητής χωρίς {fav}", wo))
    order = sorted(teams, key=lambda t: -float((P[t] * np.arange(n)).sum()) * -1)
    h2h = [{"a": a, "b": b, "p": round(float((pos[:, idx[a]] < pos[:, idx[b]]).mean()), 3)} for a, b in zip(order, order[1:])]
    T2 = F.table(rs + ph2)
    for t, d in DEDUCT["G1"].items():
        T2[t][0] += d
    tbl = []
    for t in sorted(teams, key=lambda t: (-T2[t][0], -T2[t][1], -T2[t][2])):
        j = idx[t]
        tbl.append({"t": t, "g": T2[t][3], "pts": T2[t][0], "gd": T2[t][1], "xpts": round(xp[t], 1),
                    "xpos": round(float((P[t] * np.arange(1, n + 1)).sum()), 1), "dist": [round(float(x), 3) for x in P[t]],
                    "lines": _lines(pts[:, j])})
    total = n * (n - 1) + 12 + 12 + 30
    return {"id": "G1", "name": "Super League", "sport": "football", "n": n, "progress": round(len(cur) / total, 3),
            "rem": total - len(cur), "markets": mks, "h2h": h2h, "table": tbl, "lines_label": "Βαθμοί στο τέλος (μετά τα play-off/out)",
            "note": "Σύστημα: 26 αγωνιστικές, μετά play-off 1-4 (όλοι οι βαθμοί), 5-8 (μισοί βαθμοί), play-out 9-14 (όλοι οι βαθμοί, πέφτουν οι 2 τελευταίοι). "
                    "Ο Βόλος ξεκίνησε με -3."}


# ---------------- μπάσκετ ----------------

def _rec(played):
    rec = defaultdict(lambda: [0, 0, 0])
    for g in played:
        w = g["hp"] > g["ap"]
        rec[g["home"]][0 if w else 1] += 1; rec[g["away"]][1 if w else 0] += 1
        rec[g["home"]][2] += g["hp"] - g["ap"]; rec[g["away"]][2] += g["ap"] - g["hp"]
    return rec


def euroleague():
    from . import basket
    year = basket._season()
    rs = [g for g in basket.games("E", year) if g["phase"] == "RS"]
    prev = [g for g in basket.games("E", year - 1) if g["played"]]
    played = [g for g in rs if g["played"]]
    if len(played) < 20:
        return None
    teams = sorted({g["home"] for g in rs} | {g["away"] for g in rs})
    rem = [(g["home"], g["away"]) for g in rs if not g["played"]]
    S = F.BSim(teams, basket.fit(played, prev), F.B_SIGMA, F.B_NSIM, np.random.default_rng(11))
    rec = _rec(played)
    W, order = S.season({t: tuple(rec[t]) for t in teams}, rem)
    post = F.el_post(S, order)
    n = len(teams)
    pos = np.empty_like(order); pos[np.arange(S.nsim)[:, None], order] = np.arange(n)[None, :]
    ff, fin = np.stack(post["ff"], 1), np.stack(post["final"], 1)
    pr = lambda f: {t: float(f(S.idx[t])) for t in teams}
    mks = [_market("champ", "Πρωταθλήτρια EuroLeague", pr(lambda i: (post["champ"] == i).mean())),
           _market("fin", "Στον τελικό", pr(lambda i: (fin == i).any(1).mean())),
           _market("ff", "Στο Final Four", pr(lambda i: (ff == i).any(1).mean())),
           _market("t1", "1η στην κανονική περίοδο", pr(lambda i: (pos[:, i] == 0).mean())),
           _market("t4", "Top 4 (έδρα στα playoffs)", pr(lambda i: (pos[:, i] < 4).mean())),
           _market("t6", "Top 6 (απευθείας playoffs)", pr(lambda i: (pos[:, i] < 6).mean()), top=16),
           _market("t10", "Top 10 (τουλάχιστον play-in)", pr(lambda i: (pos[:, i] < 10).mean()), top=18),
           _market("out", "Εκτός 10άδας", pr(lambda i: (pos[:, i] >= 10).mean()), top=18)]
    tbl = []
    for t in sorted(teams, key=lambda t: (-rec[t][0], -rec[t][2])):
        i = S.idx[t]
        tbl.append({"t": t, "w": rec[t][0], "l": rec[t][1], "pd": rec[t][2], "xw": round(float(W[:, i].mean()), 1),
                    "lines": _lines(W[:, i], step=3), "champ": round(float((post["champ"] == i).mean()), 3),
                    "ff": round(float((ff == i).any(1).mean()), 3), "t6": round(float((pos[:, i] < 6).mean()), 3),
                    "t10": round(float((pos[:, i] < 10).mean()), 3)})
    return {"id": "EL", "name": "EuroLeague", "sport": "basketball", "n": n, "progress": round(len(played) / len(rs), 3),
            "rem": len(rem), "markets": mks, "table": tbl, "lines_label": "Νίκες κανονικής περιόδου",
            "cols": [["champ", "Πρωτ."], ["ff", "F4"], ["t6", "Top 6"], ["t10", "Top 10"]]}


def nba(outright=None):
    from . import basket, espn
    st = espn.nba_standings()
    if len(st) < 30:
        return None
    cur, prev = espn.nba_games(1)
    R = basket.fit([g for g in cur if g["played"]], [g for g in prev if g["played"]], **config.BASKET["NBA"].get("fit", {}))
    teams = sorted(st)
    rem = [tuple(x) for x in espn.nba_remaining()]
    rec = {t: (st[t]["w"], st[t]["l"], st[t]["pd"] * (st[t]["w"] + st[t]["l"])) for t in teams}
    mk = None
    if outright:
        tot = sum(1 / o for o in outright.values())
        mk = {t: (1 / o) / tot for t, o in outright.items()}
    shift, blended = _nba_calibrate(teams, R, rec, rem, st, mk) if mk else (None, False)
    S = F.BSim(teams, R, F.B_SIGMA, F.B_NSIM, np.random.default_rng(12), shift=shift)
    W, _ = S.season(rec, rem)
    rng, r = S.rng, np.arange(S.nsim)
    orders = []
    for conf in ("East", "West"):
        ci = np.array([S.idx[t] for t in teams if st[t]["conf"] == conf])
        key = W[:, ci] + rng.random((S.nsim, len(ci))) * 0.01
        orders.append(ci[np.argsort(-key, axis=1)])
    post = F.nba_post(S, orders, W)
    seed = np.full((S.nsim, len(teams)), 99)
    for o in orders:
        seed[r[:, None], o] = np.arange(o.shape[1])[None, :]
    best = np.argmax(W + rng.random(W.shape) * 0.01, axis=1)
    pr = lambda f, sub=None: {t: float(f(S.idx[t])) for t in teams if sub is None or st[t]["conf"] == sub}
    mks = [_market("champ", "Πρωταθλήτρια NBA", pr(lambda i: (post["champ"] == i).mean()), mkt=mk,
                   note=("Η δύναμη των ομάδων είναι μείγμα 50/50 στατιστικών και αγοράς (όπως βγήκε καλύτερο στον έλεγχο). "
                         "«Αγορά» = πιθανότητα από τις αποδόσεις των εταιρειών, χωρίς το γκανιότ.") if blended else None),
           _market("east", "Νικήτρια Ανατολής", pr(lambda i: (post["conf"][0] == i).mean(), "East")),
           _market("west", "Νικήτρια Δύσης", pr(lambda i: (post["conf"][1] == i).mean(), "West")),
           _market("best", "Καλύτερο ρεκόρ κανονικής περιόδου", pr(lambda i: (best == i).mean())),
           _market("t1e", "1η Ανατολής (κανονική περίοδος)", pr(lambda i: (seed[:, i] == 0).mean(), "East")),
           _market("t1w", "1η Δύσης (κανονική περίοδος)", pr(lambda i: (seed[:, i] == 0).mean(), "West")),
           _market("t6", "Top 6 περιφέρειας (απευθείας playoffs)", pr(lambda i: (seed[:, i] < 6).mean()), top=20),
           _market("t10", "Top 10 περιφέρειας (τουλάχιστον play-in)", pr(lambda i: (seed[:, i] < 10).mean()), top=24),
           _market("out", "Εκτός play-in (θέση 11-15)", pr(lambda i: (seed[:, i] >= 10).mean()), top=20)]
    tbl = []
    for ci, conf in enumerate(("East", "West")):
        for t in sorted([t for t in teams if st[t]["conf"] == conf], key=lambda t: (-st[t]["w"], st[t]["l"])):
            i = S.idx[t]
            tbl.append({"t": t, "conf": conf, "w": st[t]["w"], "l": st[t]["l"], "pd": round(st[t]["pd"], 1),
                        "xw": round(float(W[:, i].mean()), 1), "lines": _lines(W[:, i], step=3),
                        "champ": round(float((post["champ"] == i).mean()), 3), "conf_w": round(float((post["conf"][ci] == i).mean()), 3),
                        "t6": round(float((seed[:, i] < 6).mean()), 3), "t10": round(float((seed[:, i] < 10).mean()), 3)})
    gp = sum(st[t]["w"] + st[t]["l"] for t in teams) / 2
    return {"id": "NBA", "name": "NBA", "sport": "basketball", "n": 30, "progress": round(gp / (gp + len(rem)), 3), "rem": len(rem),
            "markets": mks, "table": tbl, "lines_label": "Νίκες κανονικής περιόδου",
            "cols": [["champ", "Πρωτ."], ["conf_w", "Περιφ."], ["t6", "Top 6"], ["t10", "Top 10"]]}


def _nba_conf_sim(S, teams, st, rec, rem):
    W, _ = S.season(rec, rem)
    orders = []
    for conf in ("East", "West"):
        ci = np.array([S.idx[t] for t in teams if st[t]["conf"] == conf])
        key = W[:, ci] + S.rng.random((S.nsim, len(ci))) * 0.01
        orders.append(ci[np.argsort(-key, axis=1)])
    return F.nba_post(S, orders, W)


def _nba_calibrate(teams, R, rec, rem, st, mk, w_model=0.5, iters=5):
    """Μετατοπίζει τη δύναμη κάθε ομάδας (πόντοι) ώστε η πιθανότητα τίτλου να ταιριάζει με το μείγμα
    μοντέλου/αγοράς (γεωμετρικός μέσος). Έτσι όλες οι αγορές (περιφέρεια, ρεκόρ...) μένουν συνεπείς."""
    if sum(1 for t in teams if t in mk) < 25:
        return None, False
    lg = lambda p: math.log(max(p, 0.002) / (1 - max(p, 0.002)))
    shift = np.zeros(len(teams))
    target = None
    for it in range(iters + 1):
        S = F.BSim(teams, R, F.B_SIGMA, 3000, np.random.default_rng(100 + it), shift=shift)
        post = _nba_conf_sim(S, teams, st, rec, rem)
        p = np.array([(post["champ"] == i).mean() for i in range(len(teams))])
        if target is None:  # στόχος: μείγμα της αρχικής πρόβλεψης του μοντέλου με την αγορά
            q = np.array([max(p[i], 0.001) ** w_model * max(mk.get(t, 0.001), 0.001) ** (1 - w_model) for i, t in enumerate(teams)])
            target = q / q.sum()
        if it == iters:
            break
        shift = np.clip(shift + 2.0 * np.array([lg(target[i]) - lg(p[i]) for i in range(len(teams))]) * (target > 0.004), -8, 8)
    return shift, True


def build():
    from . import sources
    out = []
    try:
        r = greece()
        if r:
            out.append(r)
    except Exception as e:
        print(f"  ! μακροχρόνια Ελλάδα: {e}")
    for code in F.LEAGUES:
        try:
            r = football_league(code, NAMES[code])
            if r:
                out.append(r)
        except Exception as e:
            print(f"  ! μακροχρόνια {code}: {e}")
    for name, fn in (("EuroLeague", euroleague), ("NBA", lambda: nba(sources.odds_outright("basketball_nba_championship_winner")))):
        try:
            r = fn()
            if r:
                out.append(r)
        except Exception as e:
            print(f"  ! μακροχρόνια {name}: {e}")
    return {"updated": datetime.now(timezone.utc).isoformat(), "nsim": F.NSIM, "leagues": out}
