"""Στατιστικά αγώνα πέρα από τα γκολ: κόρνερ, σουτ, σουτ στην εστία, φάουλ, κάρτες, αποκρούσεις, ημίχρονο.

Για κάθε μετρική: ισχύς "υπέρ/κατά" κάθε ομάδας (ίδια μέθοδος με τα γκολ) -> αναμενόμενο ανά ομάδα
-> κατανομή Negative Binomial (η διασπορά μετρήθηκε στην έρευνα, οι μετρήσεις έχουν περισσότερη
τυχαιότητα από Poisson) -> πιθανότητες για τις γραμμές που δίνουν οι στοιχηματικές.
"""
import json
import math

from . import config

STATS = {
    "co": "Κόρνερ",
    "sh": "Σουτ",
    "st": "Σουτ στην εστία",
    "fo": "Φάουλ",
    "ca": "Κάρτες",
    "sv": "Αποκρούσεις",
}
# Παράμετροι ανά μετρική (αντικαθίστανται από την έρευνα, engine/stats_research.py):
#  pt/pT: διασπορά (variance = μ + φ·μ²) ανά ομάδα / στο σύνολο
#  a/aT : πόσο από την απόκλιση ομάδας-πρωταθλήματος κρατάμε (επιστροφή στον μέσο όρο)
#  b/bT : "σενάριο αγώνα": πόσο αλλάζει η μετρική με το πόσο φαβορί είναι η ομάδα (sup = P(νίκη) - P(ήττα))
#  ch/ca/cT: μέσες τιμές του sup (κεντράρισμα)
_D = {"a": 1.0, "aT": 1.0, "b": 0.0, "bT": 0.0, "ch": 0.0, "ca": 0.0, "cT": 0.0}
DEFAULT_DISP = {"co": {**_D, "pt": 0.09, "pT": 0.015}, "sh": {**_D, "pt": 0.05, "pT": 0.012},
                "st": {**_D, "pt": 0.035, "pT": 0.014}, "fo": {**_D, "pt": 0.006, "pT": 0.005},
                "ca": {**_D, "pt": 0.0, "pT": 0.03}, "sv": {**_D, "pt": 0.08, "pT": 0.03}}
PROP_RATIO = 1.045  # γκανιότ ~9% στις αγορές στατιστικών (κόρνερ/κάρτες κ.λπ.) -> ~4,5% ανά πλευρά
EDGE_MIN = 0.10     # απόκλιση πιθανότητας από τον "μέσο όρο του πρωταθλήματος" για να σημειωθεί


def values(m, k):
    """(γηπεδούχος, φιλοξενούμενος) για μια μετρική ή None αν λείπει."""
    g = m.get
    if k == "co":
        a, b = g("hc"), g("ac")
    elif k == "sh":
        a, b = g("hs"), g("as")
    elif k == "st":
        a, b = g("hst"), g("ast")
    elif k == "fo":
        a, b = g("hf"), g("af")
    elif k == "ca":
        if g("hy") is None or g("ay") is None:
            return None
        a, b = g("hy") + (g("hr") or 0), g("ay") + (g("ar") or 0)
    elif k == "sv":  # αποκρούσεις τερματοφύλακα = σουτ στην εστία του αντιπάλου - γκολ που δέχτηκε
        if g("hst") is None or g("ast") is None or g("hg") is None:
            return None
        a, b = max(g("ast") - g("ag"), 0), max(g("hst") - g("hg"), 0)
    else:
        return None
    if a is None or b is None:
        return None
    return a, b


def _gs(sup, d):
    """Συντελεστές "σεναρίου αγώνα" (γηπεδούχος, φιλοξενούμενος, σύνολο) από το πόσο φαβορί είναι η κάθε ομάδα."""
    if sup is None:
        return 1.0, 1.0, 1.0
    clamp = lambda x: min(max(x, 0.6), 1.6)
    return (clamp(1 + d["b"] * (sup - d["ch"])), clamp(1 + d["b"] * (-sup - d["ca"])),
            clamp(1 + d["bT"] * (abs(sup) - d["cT"])))


def means(home_r, away_r, league, ref=None, disp=None, info=None, sup=None, explain=False):
    """Αναμενόμενες τιμές {μετρική: [γηπεδούχος, φιλοξενούμενος, σύνολο]}.

    1. ομάδα (υπέρ) × αντίπαλος (κατά) × μέσος όρος πρωταθλήματος,
    2. επιστροφή προς τον μέσο όρο (α ανά ομάδα, αT στο σύνολο, από την έρευνα),
    3. σενάριο αγώνα: φαβορί/αουτσάιντερ από τις αποδόσεις (β, από την έρευνα),
    4. διαιτητής, μόνο όπου η έρευνα έδειξε ότι βοηθάει (κάρτες).
    Με explain=True επιστρέφει και τους επιμέρους συντελεστές για εξήγηση στο site.
    """
    out, why = {}, {}
    for k, (ha, aa) in (league.get("sx") or {}).items():
        h = (home_r.get("sx") or {}).get(k, [1.0, 1.0])
        a = (away_r.get("sx") or {}).get(k, [1.0, 1.0])
        d = param(disp, k)
        rh, ra = ha * h[0] * a[1], aa * a[0] * h[1]
        mh, ma = ha + d["a"] * (rh - ha), aa + d["a"] * (ra - aa)
        mT = ha + aa + d["aT"] * (rh + ra - ha - aa)
        fh, fa, fT = _gs(sup, d)
        mh, ma, mT = mh * fh, ma * fa, mT * fT
        rf = 1.0
        if ref and ((info or {}).get(k) or {}).get("ref_ok"):
            rf = ref.get("factor", 1.0) if k == "ca" else (ref.get("ffactor") or 1.0)
            mh, ma, mT = mh * rf, ma * rf, mT * rf
        out[k] = [mh, ma, mT]
        # [ομάδα υπέρ, αντίπαλος κατά] για γηπεδούχο και φιλοξενούμενο, σενάριο, διαιτητής
        why[k] = {"h": [round(h[0], 2), round(a[1], 2)], "a": [round(a[0], 2), round(h[1], 2)],
                  "gs": [round(fh, 3), round(fa, 3), round(fT, 3)], "ref": round(rf, 3)}
    return (out, why) if explain else out


def param(disp, k):
    d = (disp or {}).get(k)
    if isinstance(d, list):  # παλιά μορφή [pt, pT, a, aT]
        d = {"pt": d[0], "pT": d[1], "a": d[2] if len(d) > 2 else 1.0, "aT": d[3] if len(d) > 3 else 1.0}
    return {**DEFAULT_DISP[k], **(d or {})}


def nb_pmf(mu, phi, kmax=None):
    """Κατανομή Negative Binomial με μέσο μu και variance μ + φ μ² (φ=0 -> Poisson)."""
    mu = max(mu, 1e-6)
    kmax = kmax or int(mu * 3 + 25)
    out = []
    if phi <= 1e-6:
        p = math.exp(-mu)
        for k in range(kmax + 1):
            out.append(p)
            p *= mu / (k + 1)
        return out
    r = 1 / phi
    q = mu / (r + mu)
    p = math.exp(r * math.log(r / (r + mu)))
    for k in range(kmax + 1):
        out.append(p)
        p *= (k + r) / (k + 1) * q
    return out


def p_over(dist, line):
    k = int(math.floor(line))
    return max(0.0, 1 - sum(dist[: k + 1]))


def _lines(mu, n):
    base = math.floor(mu) + 0.5
    return [base + i for i in range(-n, n + 1) if base + i > 0]


def disp_table():
    try:
        r = json.loads((config.DATA_OUT / "research.json").read_text(encoding="utf-8"))
        sd = r.get("stats_disp") or {}
        return {k: param(sd, k) for k in STATS}, r.get("stats") or {}
    except (OSError, ValueError):
        return {k: param({}, k) for k in STATS}, {}


def _s(group, key, side, label, p):
    fair = round(1 / p, 2) if p > 0.001 else None
    est = max(round(fair / PROP_RATIO, 2), 1.01) if fair else None
    return {"group": group, "key": key, "side": side, "label": label, "p": round(p, 4), "fair": fair,
            "est": est, "est_src": "gc", "est_ev": round(p * est - 1, 4) if est else None, "pp": 0}


def selections(mx, disp, ht=None, home="Γηπεδούχος", away="Φιλοξενούμενος"):
    """Επιλογές για όλες τις αγορές στατιστικών. mx: {μετρική: [μ_γηπ, μ_φιλ]}."""
    out = []
    for k, (mh, ma, mT) in mx.items():
        name = STATS[k]
        d = param(disp, k)
        pt, pT = d["pt"], d["pT"]
        tot = nb_pmf(mT, pT)
        for L in _lines(mT, 2):
            po = p_over(tot, L)
            out.append(_s(name, f"S:{k}:T:{L:g}", "Over", f"{name} Over {L:g}", po))
            out.append(_s(name, f"S:{k}:T:{L:g}", "Under", f"{name} Under {L:g}", 1 - po))
        dh, da = nb_pmf(mh, pt), nb_pmf(ma, pt)
        for side, mu, d, who in (("H", mh, dh, home), ("A", ma, da, away)):
            for L in _lines(mu, 1):
                po = p_over(d, L)
                g = f"{name} {'γηπεδούχου' if side == 'H' else 'φιλοξενούμενου'}"
                out.append(_s(g, f"S:{k}:{side}:{L:g}", "Over", f"{who}: {name.lower()} Over {L:g}", po))
                out.append(_s(g, f"S:{k}:{side}:{L:g}", "Under", f"{who}: {name.lower()} Under {L:g}", 1 - po))
        p1 = sum(dh[i] * sum(da[:min(i, len(da))]) for i in range(len(dh)))
        px = sum(dh[i] * da[i] for i in range(min(len(dh), len(da))))
        g = f"Περισσότερα: {name.lower()}"
        out.append(_s(g, f"S:{k}:1X2", "1", f"Περισσότερα {name.lower()}: {home}", p1))
        out.append(_s(g, f"S:{k}:1X2", "X", f"Ίδια {name.lower()}: X", px))
        out.append(_s(g, f"S:{k}:1X2", "2", f"Περισσότερα {name.lower()}: {away}", max(1 - p1 - px, 0)))
    if ht:
        hh, ha = ht
        dh, da = nb_pmf(hh, 0, 12), nb_pmf(ha, 0, 12)
        tot = nb_pmf(hh + ha, 0, 15)
        for L in (0.5, 1.5, 2.5):
            po = p_over(tot, L)
            out.append(_s("Α' ημίχρονο: γκολ", f"H1:OU{L:g}", "Over", f"Α' ημίχρονο Over {L:g}", po))
            out.append(_s("Α' ημίχρονο: γκολ", f"H1:OU{L:g}", "Under", f"Α' ημίχρονο Under {L:g}", 1 - po))
        p1 = sum(dh[i] * sum(da[:i]) for i in range(len(dh)))
        px = sum(dh[i] * da[i] for i in range(len(dh)))
        for side, p in (("1", p1), ("X", px), ("2", 1 - p1 - px)):
            out.append(_s("Α' ημίχρονο: αποτέλεσμα", "H1:1X2", side, f"Ημίχρονο {side}", p))
    return [s for s in out if s["fair"]]


def verdict(key, side, why, home="", away=""):
    """Βολεύει ο αντίπαλος και το σενάριο του αγώνα την επιλογή; Επιστρέφει (βαθμός, κείμενο)."""
    parts = key.split(":")
    if parts[0] != "S" or parts[1] not in why:
        return None
    w, k = why[parts[1]], parts[1]
    name = STATS[k].lower()
    scope = parts[2]
    notes, f = [], 1.0
    sides = {"H": [("h", 0, home, away)], "A": [("a", 1, away, home)]}.get(scope, [("h", 0, home, away), ("a", 1, away, home)])
    for tag, i, team, opp in sides:
        own, opp_f = w[tag]
        gs = w["gs"][i] if scope != "T" else w["gs"][2] ** 0.5
        f *= opp_f * gs
        if scope == "1X2":
            continue
        verb = {"fo": "προκαλεί", "ca": "προκαλεί", "sv": "αναγκάζει σε"}.get(k, "επιτρέπει")
        txt = f"{opp} {verb} {_pc(opp_f)} {name} από τον μ.ό."
        if abs(gs - 1) >= 0.02:
            txt += f", σενάριο αγώνα {_pc(gs)} ({team} {'φαβορί' if gs > 1 and k in ('co', 'sh', 'st') else 'αουτσάιντερ' if k in ('co', 'sh', 'st') else 'πιο πιεσμένη' if gs > 1 else 'λιγότερο πιεσμένη'})"
        notes.append(txt)
    if scope == "1X2":
        (oh, fh), (oa, fa) = w["h"], w["a"]
        sh, sa = oh * fh * w["gs"][0], oa * fa * w["gs"][1]
        better = side == ("1" if sh > sa else "2")
        return (1 if better else -1, f"{home} {_pc(sh)} vs {away} {_pc(sa)} (ομάδα × αντίπαλος × σενάριο)")
    if scope == "T":
        f = f ** 0.5
    want_up = side == "Over"
    score = 1 if (f > 1.03 and want_up) or (f < 0.97 and not want_up) else -1 if (f > 1.03 or f < 0.97) else 0
    return score, " · ".join(notes)


def _pc(x):
    return f"{(x - 1) * 100:+.0f}%"


def edges(mx, naive, disp, info, home="", away=""):
    """Αγορές όπου η πρόβλεψη για τον αγώνα απέχει πολύ από τον μέσο όρο του πρωταθλήματος.

    Μια στοιχηματική που "αγκυρώνεται" στον μέσο όρο κάνει λάθος εκεί. Δείχνονται μόνο μετρικές/αγορές
    (σύνολο ή ανά ομάδα) όπου η έρευνα, σε σεζόν που δεν είδε το μοντέλο, επιβεβαίωσε ότι σε τέτοιες
    αποκλίσεις το αποτέλεσμα ήταν πιο κοντά στο μοντέλο.
    """
    out = []
    for k, (mh, ma, mT) in mx.items():
        st = info.get(k) or {}
        if k not in naive:
            continue
        d = param(disp, k)
        pt, pT = d["pt"], d["pT"]
        nh, na = naive[k]
        cands = []
        if (st.get("edge_total") or {}).get("ok"):
            cands.append(("T", "", mT, nh + na, pT, st["edge_total"]))
        if (st.get("edge_team") or {}).get("ok"):
            cands += [("H", home, mh, nh, pt, st["edge_team"]), ("A", away, ma, na, pt, st["edge_team"])]
        for scope, team, mu, nmu, ph, ev in cands:
            L = math.floor(nmu) + 0.5  # η "συνηθισμένη" γραμμή του πρωταθλήματος
            pm = p_over(nb_pmf(mu, ph), L)
            pn = p_over(nb_pmf(nmu, ph), L)
            if abs(pm - pn) < EDGE_MIN:
                continue
            side, p, q = ("Over", pm, pn) if pm > pn else ("Under", 1 - pm, 1 - pn)
            # βαθμονόμηση από την έρευνα: σε τέτοιες αποκλίσεις το μοντέλο ήταν λίγο πιο σίγουρο απ' ό,τι έπρεπε
            if ev.get("model") and ev.get("avg") is not None and ev["model"] - ev["avg"] > 0.02:
                kc = min(max((ev["hit"] - ev["avg"]) / (ev["model"] - ev["avg"]), 0.0), 1.0)
                p = q + kc * (p - q)
            who = f"{team}: " if team else ""
            out.append({"stat": k, "name": STATS[k], "scope": scope, "key": f"S:{k}:{scope}:{L:g}", "side": side,
                        "label": f"{who}{STATS[k]} {side} {L:g}", "p": round(p, 4), "p_avg": round(q, 4),
                        "exp": round(mu, 1), "avg": round(nmu, 1), "fair": round(1 / p, 2),
                        "min_odds": round(1.03 / p, 2), "hit": ev.get("hit"), "r_model": ev.get("model"),
                        "r_avg": ev.get("avg"), "n": ev.get("n")})
    out.sort(key=lambda e: -(e["p"] - e["p_avg"]))
    return out[:4]
