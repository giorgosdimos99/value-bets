"""Μακροχρόνια στοιχήματα: προσομοίωση της υπόλοιπης σεζόν (Monte Carlo).

Ποδόσφαιρο: κάθε πρωτάθλημα «όλοι με όλους, εντός-εκτός». Οι αγώνες που μένουν = όλα τα ζευγάρια που
δεν έχουν παιχτεί ακόμα. Δύναμη ομάδων από τις αποδόσεις κλεισίματος Pinnacle των αγώνων που έχουν
παιχτεί (η αγορά προβλέπει καλύτερα από τα στατιστικά: engine/research.py) + αβεβαιότητα δύναμης ανά
προσομοίωση (χωρίς αυτή οι πιθανότητες βγαίνουν υπερβολικά σίγουρες). Οι ρυθμίσεις βγήκαν από τον
έλεγχο σε 4 παλιές σεζόν (engine/futures_research.py).
"""
import math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from . import config, model

# Πρωταθλήματα όπου όλοι παίζουν με όλους εντός-εκτός (χωρίς play-off/διάσπαση βαθμολογίας).
# (όνομα για την εφαρμογή, αγορές) — αγορά: (κλειδί, ετικέτα, "top"/"bot", k)
TOP = [("win", "Πρωταθλητής", "top", 1), ("t2", "Top 2", "top", 2), ("t4", "Top 4", "top", 4),
       ("t6", "Top 6", "top", 6), ("b3", "Υποβιβασμός (3 τελευταίοι)", "bot", 3), ("last", "Τελευταίος", "bot", 1)]
SECOND = [("win", "Πρωταθλητής", "top", 1), ("t2", "Άνοδος απευθείας (Top 2)", "top", 2),
          ("t6", "Top 6 (play-off ανόδου)", "top", 6), ("b3", "Υποβιβασμός (3 τελευταίοι)", "bot", 3),
          ("last", "Τελευταίος", "bot", 1)]
LEAGUES = {
    "E0": TOP, "SP1": TOP, "I1": TOP,
    "D1": TOP[:4] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), ("b3", "Κάτω 3 (μαζί με μπαράζ)", "bot", 3), TOP[5]],
    "F1": TOP[:4] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), ("b3", "Κάτω 3 (μαζί με μπαράζ)", "bot", 3), TOP[5]],
    "P1": TOP[:4] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), ("b3", "Κάτω 3 (μαζί με μπαράζ)", "bot", 3), TOP[5]],
    "N1": TOP[:4] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), ("b3", "Κάτω 3 (μαζί με μπαράζ)", "bot", 3), TOP[5]],
    "T1": TOP[:4] + [("b4", "Υποβιβασμός (4 τελευταίοι)", "bot", 4), TOP[5]],
    "E1": SECOND, "D2": SECOND[:3] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), SECOND[4]],
    "I2": SECOND, "F2": SECOND[:3] + [("b2", "Υποβιβασμός απευθείας (2 τελευταίοι)", "bot", 2), SECOND[4]],
    "SP2": SECOND[:3] + [("b4", "Υποβιβασμός (4 τελευταίοι)", "bot", 4), SECOND[4]],
    "E2": SECOND[:3] + [("b4", "Υποβιβασμός (4 τελευταίοι)", "bot", 4), SECOND[4]],
    "E3": [SECOND[0], ("t3", "Άνοδος απευθείας (Top 3)", "top", 3), ("t7", "Top 7 (play-off ανόδου)", "top", 7),
           ("b2", "Υποβιβασμός (2 τελευταίοι)", "bot", 2), SECOND[4]],
}

# από τον έλεγχο (futures_research.py): πηγή δύναμης, αβεβαιότητα, χρόνος ημιζωής
SRC = "blend"   # έλεγχος 240 σημείων (2022-26): μείγμα αγοράς+στατιστικών 0.1427, αγορά 0.1434, στατιστικά 0.1481
SIGMA = 0.05
HALF_LIFE = 90
PREV_W = 0.6
NSIM = 10000


# ---------- αγορά -> αναμενόμενα γκολ κάθε αγώνα (γρήγορα, με πίνακα αναζήτησης) ----------
_GRID = None


def _grid():
    global _GRID
    if _GRID is None:
        g = np.arange(0.10, 4.51, 0.02)
        LH, LA = np.meshgrid(g, g, indexing="ij")
        k = np.arange(11)
        fact = np.array([math.factorial(i) for i in k], dtype=float)
        ph_k = np.exp(-LH[..., None]) * LH[..., None] ** k / fact  # (n,n,11)
        pa_k = np.exp(-LA[..., None]) * LA[..., None] ** k / fact
        M = ph_k[..., :, None] * pa_k[..., None, :]  # (n,n,11,11)
        i, j = np.meshgrid(k, k, indexing="ij")
        P1 = (M * (i > j)).sum((-1, -2))
        P2 = (M * (i < j)).sum((-1, -2))
        PO = (M * (i + j > 2.5)).sum((-1, -2))
        _GRID = (LH.ravel(), LA.ravel(), P1.ravel(), P2.ravel(), PO.ravel())
    return _GRID


def _devig(o):
    if not o or any(not x or x <= 1 for x in o):
        return None
    inv = [1 / x for x in o]
    s = sum(inv)
    return [x / s for x in inv]


def market_xg(m):
    """Αναμενόμενα γκολ που «έβλεπε» η αγορά πριν τον αγώνα (κλείσιμο Pinnacle, αλλιώς μέσος όρος)."""
    od = m.get("odds") or {}
    t = _devig(od.get("pc1x2") or od.get("p1x2") or od.get("a1x2") or od.get("b1x2"))
    if not t:
        return None
    ou = _devig(od.get("pcou") or od.get("pou") or od.get("aou") or od.get("bou"))
    LH, LA, P1, P2, PO = _grid()
    e = (P1 - t[0]) ** 2 + (P2 - t[2]) ** 2
    if ou:
        e = e + (PO - ou[0]) ** 2
    i = int(np.argmin(e))
    return float(LH[i]), float(LA[i])


def _age_w(date_iso, now, hl):
    if not date_iso:
        return 0.0
    d = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return 0.5 ** (max((now - d).days, 0) / hl)


def ratings(cur, prev, now, src=SRC, hl=HALF_LIFE, prev_w=PREV_W):
    """Επίθεση/άμυνα κάθε ομάδας. src: "market" (αποδόσεις), "model" (γκολ+xG) ή "blend"."""
    out = {}
    if src in ("market", "blend"):
        ms = []
        for m, f in [(m, 1.0) for m in cur] + [(m, prev_w) for m in prev]:
            x = m.get("_mx") if "_mx" in m else market_xg(m)
            m["_mx"] = x
            w = f * _age_w(m["date"], now, hl)
            if x and w > 0.01:
                ms.append({"home": m["home"], "away": m["away"], "lh": x[0], "la": x[1], "_w": w})
        if len(ms) >= 20:
            att, dfn, ha, aa = model._fit_pair(ms, lambda m: m["lh"], lambda m: m["la"], prior=2)
            out["market"] = (att, dfn, ha, aa)
    if src in ("model", "blend"):
        ms = []
        for m, f in [(m, 1.0) for m in model.with_proxy_xg(cur)] + [(m, prev_w) for m in model.with_proxy_xg(prev)]:
            w = f * _age_w(m["date"], now, hl)
            if w > 0.01 and m["hg"] is not None:
                ms.append({**m, "_w": w})
        if len(ms) >= 20:
            att, dfn, ha, aa = model._fit_pair(ms, lambda m: model._blend(m["hg"], m["hxg"]), lambda m: model._blend(m["ag"], m["axg"]))
            out["model"] = (att, dfn, ha, aa)
    if src == "blend" and "market" in out and "model" in out:
        (a1, d1, h1, x1), (a2, d2, h2, x2) = out["market"], out["model"]
        ts = set(a1) | set(a2)
        g = lambda A, B, t: math.sqrt(A.get(t, 1.0) * B.get(t, 1.0))
        return ({t: g(a1, a2, t) for t in ts}, {t: g(d1, d2, t) for t in ts}, math.sqrt(h1 * h2), math.sqrt(x1 * x2))
    return out.get(src) or out.get("market") or out.get("model")


def table(played):
    T = defaultdict(lambda: [0, 0, 0, 0])  # βαθμοί, διαφορά, γκολ υπέρ, αγώνες
    for m in played:
        if m["hg"] is None:
            continue
        h, a, hg, ag = m["home"], m["away"], int(m["hg"]), int(m["ag"])
        T[h][1] += hg - ag; T[a][1] += ag - hg; T[h][2] += hg; T[a][2] += ag; T[h][3] += 1; T[a][3] += 1
        if hg > ag: T[h][0] += 3
        elif hg < ag: T[a][0] += 3
        else: T[h][0] += 1; T[a][0] += 1
    return T


def _phase2(rng, pts, gd, gf, A, D, ha, aa, eA, eD, groups, real):
    """Δεύτερη φάση (π.χ. Ελλάδα): ομάδες θέσεων, όλοι με όλους εντός-εκτός, μεταφορά βαθμών.
    groups: [(από, έως, συντελεστής βαθμών)]. real: {(γηπ, φιλ): (γκολ, γκολ)} αγώνες 2ης φάσης που έχουν γίνει."""
    nsim, nT = pts.shape
    key = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random((nsim, nT)) * 0.5
    order = np.argsort(-key, axis=1)
    r = np.arange(nsim)
    final = np.empty_like(order)
    for a0, a1, carry in groups:
        slots = order[:, a0:a1]
        gp = np.ceil(pts[r[:, None], slots] * carry) if carry != 1 else pts[r[:, None], slots].copy()
        ggd = gd[r[:, None], slots].copy(); ggf = gf[r[:, None], slots].copy()
        k = a1 - a0
        for i in range(k):
            for j in range(k):
                if i == j:
                    continue
                ti, tj = slots[:, i], slots[:, j]
                lh = ha * A[ti] * D[tj] * np.exp(eA[r, ti] + eD[r, tj])
                la = aa * A[tj] * D[ti] * np.exp(eA[r, tj] + eD[r, ti])
                hg = rng.poisson(lh); ag = rng.poisson(la)
                for (h, a), (x, y) in real.items():  # ό,τι έχει ήδη παιχτεί
                    msk = (ti == h) & (tj == a)
                    hg[msk] = x; ag[msk] = y
                gp[:, i] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0)); gp[:, j] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
                ggd[:, i] += hg - ag; ggd[:, j] += ag - hg; ggf[:, i] += hg; ggf[:, j] += ag
        kk = gp * 1e6 + (ggd + 500) * 1e3 + ggf + rng.random(gp.shape) * 0.5
        o = np.argsort(-kk, axis=1)
        final[:, a0:a1] = slots[r[:, None], o]
        pts[r[:, None], slots] = gp  # για τους «αναμενόμενους βαθμούς»
    return final


def simulate(teams, played, R, sigma=SIGMA, nsim=NSIM, seed=7, deduct=None, split=None, played2=()):
    """Επιστρέφει (θέσεις: dict ομάδα -> πίνακας πιθανοτήτων θέσης, αναμενόμενοι βαθμοί, τρέχων πίνακας).
    deduct: {ομάδα: βαθμοί} (αφαίρεση βαθμών). split: ομάδες 2ης φάσης (βλ. _phase2)."""
    rng = np.random.default_rng(seed)
    att, dfn, ha, aa = R
    idx = {t: i for i, t in enumerate(teams)}
    nT = len(teams)
    done = {(m["home"], m["away"]) for m in played}
    rem = [(h, a) for h in teams for a in teams if h != a and (h, a) not in done]
    T = table(played)
    for t, d in (deduct or {}).items():
        if t in T:
            T[t][0] += d
    base = np.array([[T[t][0], T[t][1], T[t][2]] for t in teams], dtype=float)
    pts = np.repeat(base[None, :, 0], nsim, 0)
    gd = np.repeat(base[None, :, 1], nsim, 0)
    gf = np.repeat(base[None, :, 2], nsim, 0)
    A = np.array([att.get(t, 0.85) for t in teams]); D = np.array([dfn.get(t, 1.15) for t in teams])
    eA = rng.normal(0, sigma, (nsim, nT)); eD = rng.normal(0, sigma, (nsim, nT))
    if rem:
        hi = np.array([idx[h] for h, _ in rem]); ai = np.array([idx[a] for _, a in rem])
        lh = ha * A[hi] * D[ai] * np.exp(eA[:, hi] + eD[:, ai])
        la = aa * A[ai] * D[hi] * np.exp(eA[:, ai] + eD[:, hi])
        hg = rng.poisson(lh); ag = rng.poisson(la)
        hp = np.where(hg > ag, 3, np.where(hg == ag, 1, 0)); ap = np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
        H = np.zeros((len(rem), nT)); H[np.arange(len(rem)), hi] = 1
        Aw = np.zeros((len(rem), nT)); Aw[np.arange(len(rem)), ai] = 1
        pts += hp @ H + ap @ Aw
        gd += (hg - ag) @ H + (ag - hg) @ Aw
        gf += hg @ H + ag @ Aw
    if split:
        real = {(idx[m["home"]], idx[m["away"]]): (int(m["hg"]), int(m["ag"])) for m in played2 if m["home"] in idx and m["away"] in idx}
        order = _phase2(rng, pts, gd, gf, A, D, ha, aa, eA, eD, split, real)
    else:
        key = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random((nsim, nT)) * 0.5
        order = np.argsort(-key, axis=1)
    pos = np.empty_like(order)
    pos[np.arange(nsim)[:, None], order] = np.arange(nT)[None, :]
    P = np.zeros((nT, nT))
    for j in range(nT):
        P[j] = np.bincount(pos[:, j], minlength=nT) / nsim
    simulate.last = {"pos": pos, "pts": pts, "idx": idx}
    return {t: P[idx[t]] for t in teams}, {t: float(pts[:, idx[t]].mean()) for t in teams}, T, len(rem)


def market_p(posP, kind, k, n):
    return float(posP[:k].sum()) if kind == "top" else float(posP[n - k:].sum())


# ======================= ΜΠΑΣΚΕΤ =======================
# Δύναμη: engine/basket.fit (πόντοι επίθεσης/άμυνας). Αβεβαιότητα: τυχαία μετατόπιση πόντων ανά ομάδα/προσομοίωση.
B_SIGMA = 2.0  # επανέλεγχος EuroLeague 2023-26 με τη νέα δύναμη ομάδων: 0-2 ισοδύναμα (0,2335), πάνω από 3 χειρότερα
B_NSIM = 6000


def _phi_np(x):
    from math import sqrt
    return 0.5 * (1 + np.vectorize(math.erf)(x / sqrt(2))) if np.ndim(x) else 0.5 * (1 + math.erf(x / math.sqrt(2)))


class BSim:
    """Πίνακες περιθωρίου (γηπεδούχος - φιλοξενούμενος) και προσομοίωση αγώνων/σειρών."""

    def __init__(self, teams, R, sigma, nsim, rng, shift=None):
        self.teams, self.idx, self.n = teams, {t: i for i, t in enumerate(teams)}, len(teams)
        A = np.array([R["att"].get(t, 1.0) for t in teams]); D = np.array([R["def"].get(t, 1.0) for t in teams])
        ha, aa = R["h_avg"], R["a_avg"]
        self.M = ha * A[:, None] * D[None, :] - aa * A[None, :] * D[:, None]         # έδρα: γραμμή = γηπεδούχος
        nu = (ha + aa) / 2
        self.N = nu * A[:, None] * D[None, :] - nu * A[None, :] * D[:, None]        # ουδέτερο γήπεδο
        self.sd, self.rng, self.nsim = R["sd_margin"], rng, nsim
        self.off = rng.normal(0, sigma, (nsim, self.n)) + (0 if shift is None else np.asarray(shift)[None, :])

    def game(self, h, a, neutral=False):
        """h, a: πίνακες δεικτών (nsim,). Επιστρέφει True όπου κερδίζει ο h."""
        base = (self.N if neutral else self.M)[h, a]
        r = np.arange(self.nsim)
        m = base + self.off[r, h] - self.off[r, a]
        return m + self.rng.normal(0, self.sd, self.nsim) > 0

    def series(self, hi, lo, best_of):
        """hi: καλύτερη έδρα. Μοτίβο έδρας 2-2-1 (best of 5) ή 2-2-1-1-1 (best of 7)."""
        need = best_of // 2 + 1
        home_hi = [1, 1, 0, 0, 1] if best_of == 5 else [1, 1, 0, 0, 1, 0, 1]
        wh = np.zeros(self.nsim, int); wl = np.zeros(self.nsim, int)
        for g in range(best_of):
            live = (wh < need) & (wl < need)
            w = np.where(home_hi[g], self.game(hi, lo), ~self.game(lo, hi))
            wh += live & w; wl += live & ~w
        return np.where(wh >= need, hi, lo)

    def season(self, played, remaining):
        """Νίκες/ήττες: τρέχουσες + προσομοίωση. played: {ομάδα: (νίκες, ήττες, διαφορά)}."""
        W = np.repeat(np.array([[played.get(t, (0, 0, 0))[0] for t in self.teams]], float), self.nsim, 0)
        PD = np.repeat(np.array([[played.get(t, (0, 0, 0))[2] for t in self.teams]], float), self.nsim, 0)
        for h, a in remaining:
            if h not in self.idx or a not in self.idx:
                continue
            i, j = self.idx[h], self.idx[a]
            w = self.game(np.full(self.nsim, i), np.full(self.nsim, j))
            W[:, i] += w; W[:, j] += ~w
        key = W * 1e4 + PD * 1e-3 + self.rng.random(W.shape) * 1e-4
        order = np.argsort(-key, axis=1)  # order[:, k] = δείκτης ομάδας στη θέση k
        return W, order


def _playin(S, order, base):
    """Play-in 7-10 (θέσεις base+6..base+9): επιστρέφει (7ος, 8ος)."""
    s7, s8, s9, s10 = (order[:, base + k] for k in (6, 7, 8, 9))
    w78 = S.game(s7, s8); seed7 = np.where(w78, s7, s8); l78 = np.where(w78, s8, s7)
    w910 = np.where(S.game(s9, s10), s9, s10)
    seed8 = np.where(S.game(l78, w910), l78, w910)
    return seed7, seed8


def _quarters(S, seeds, best_of):
    return [S.series(seeds[0], seeds[7], best_of), S.series(seeds[3], seeds[4], best_of),
            S.series(seeds[1], seeds[6], best_of), S.series(seeds[2], seeds[5], best_of)]


def el_post(S, order):
    """EuroLeague: 1-6 απευθείας, 7-10 play-in, playoffs best of 5, Final Four ουδέτερο."""
    s7, s8 = _playin(S, order, 0)
    seeds = [order[:, k] for k in range(6)] + [s7, s8]
    q = _quarters(S, seeds, 5)
    f1 = np.where(S.game(q[0], q[1], neutral=True), q[0], q[1])
    f2 = np.where(S.game(q[2], q[3], neutral=True), q[2], q[3])
    champ = np.where(S.game(f1, f2, neutral=True), f1, f2)
    return {"champ": champ, "final": (f1, f2), "ff": q}


def nba_post(S, orders, W):
    """NBA: ανά περιφέρεια play-in 7-10, 3 γύροι best of 7, τελικοί (έδρα: περισσότερες νίκες)."""
    r = np.arange(S.nsim)

    def better(a, b):
        hb = W[r, a] >= W[r, b]
        return np.where(hb, a, b), np.where(hb, b, a)
    conf = []
    for order in orders:
        s7, s8 = _playin(S, order, 0)
        seeds = [order[:, k] for k in range(6)] + [s7, s8]
        q = _quarters(S, seeds, 7)
        a = S.series(*better(q[0], q[1]), 7); b = S.series(*better(q[2], q[3]), 7)
        conf.append(S.series(*better(a, b), 7))
    champ = S.series(*better(conf[0], conf[1]), 7)
    return {"champ": champ, "conf": conf}
