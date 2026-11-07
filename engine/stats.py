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
# Διασπορά (variance = μ + φ·μ²) ανά ομάδα και στο σύνολο. Αντικαθίσταται από τις τιμές της έρευνας.
DEFAULT_DISP = {"co": [0.03, 0.02], "sh": [0.06, 0.03], "st": [0.06, 0.03],
                "fo": [0.03, 0.02], "ca": [0.10, 0.06], "sv": [0.10, 0.06]}
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


def means(home_r, away_r, league, ref=None, disp=None, info=None):
    """Αναμενόμενες τιμές {μετρική: [γηπεδούχος, φιλοξενούμενος, σύνολο]}.

    disp[k] = [φ ομάδας, φ συνόλου, α, αT]: α/αT = πόσο από την απόκλιση από τον μέσο όρο του
    πρωταθλήματος κρατάμε ανά ομάδα / στο σύνολο (μετρήθηκε στην έρευνα σε 2023-25). Ο διαιτητής
    μπαίνει μόνο όπου η έρευνα έδειξε ότι βοηθάει (info[k]["ref_ok"]).
    """
    out = {}
    for k, (ha, aa) in (league.get("sx") or {}).items():
        h = (home_r.get("sx") or {}).get(k, [1.0, 1.0])
        a = (away_r.get("sx") or {}).get(k, [1.0, 1.0])
        d = list((disp or {}).get(k) or [])
        al, alT = (d[2] if len(d) > 2 else 1.0), (d[3] if len(d) > 3 else 1.0)
        rh, ra = ha * h[0] * a[1], aa * a[0] * h[1]
        mh, ma = ha + al * (rh - ha), aa + al * (ra - aa)
        mT = ha + aa + alT * (rh + ra - ha - aa)
        if ref and ((info or {}).get(k) or {}).get("ref_ok"):
            f = ref.get("factor", 1.0) if k == "ca" else (ref.get("ffactor") or 1.0)
            mh, ma, mT = mh * f, ma * f, mT * f
        out[k] = [mh, ma, mT]
    return out


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
        return {**DEFAULT_DISP, **(r.get("stats_disp") or {})}, r.get("stats") or {}
    except (OSError, ValueError):
        return dict(DEFAULT_DISP), {}


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
        pt, pT = disp.get(k, DEFAULT_DISP[k])[:2]
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
        pt, pT = disp.get(k, DEFAULT_DISP[k])[:2]
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
            who = f"{team}: " if team else ""
            out.append({"stat": k, "name": STATS[k], "scope": scope, "key": f"S:{k}:{scope}:{L:g}", "side": side,
                        "label": f"{who}{STATS[k]} {side} {L:g}", "p": round(p, 4), "p_avg": round(q, 4),
                        "exp": round(mu, 1), "avg": round(nmu, 1), "fair": round(1 / p, 2),
                        "min_odds": round(1.03 / p, 2), "hit": ev.get("hit"), "r_model": ev.get("model"),
                        "r_avg": ev.get("avg"), "n": ev.get("n")})
    out.sort(key=lambda e: -(e["p"] - e["p_avg"]))
    return out[:4]
