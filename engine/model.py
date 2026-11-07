"""Μοντέλο: ισχύς ομάδων (xG + γκολ) -> αναμενόμενα γκολ -> πίνακας σκορ (Poisson / Dixon-Coles)."""
import math
from collections import defaultdict
from datetime import datetime, timezone

from . import config, stats as stx

MAX_GOALS = 10
RHO = -0.06  # διόρθωση Dixon-Coles για χαμηλά σκορ (0-0, 1-1 κ.λπ.)


def _w(date_iso, now, season_factor=1.0):
    if not date_iso:
        return 0.0
    age = (now - datetime.fromisoformat(date_iso)).days
    return season_factor * 0.5 ** (max(age, 0) / config.HALF_LIFE_DAYS)


def _blend(goals, xg):
    if xg is None:
        return goals
    return config.XG_WEIGHT * xg + (1 - config.XG_WEIGHT) * goals


def _fit_pair(matches, f_home, f_away, iters=12, prior=None):
    """Γενική επαναληπτική εκτίμηση επίθεσης/άμυνας για μια μετρική (γκολ ή κόρνερ)."""
    tw = sum(m["_w"] for m in matches) or 1.0
    h_avg = sum(m["_w"] * f_home(m) for m in matches) / tw
    a_avg = sum(m["_w"] * f_away(m) for m in matches) / tw
    teams = {m["home"] for m in matches} | {m["away"] for m in matches}
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    P = config.PRIOR_MATCHES if prior is None else prior
    for _ in range(iters):
        na, da = defaultdict(float), defaultdict(float)
        nd, dd = defaultdict(float), defaultdict(float)
        for m in matches:
            w, h, a = m["_w"], m["home"], m["away"]
            na[h] += w * f_home(m); da[h] += w * h_avg * dfn[a]
            na[a] += w * f_away(m); da[a] += w * a_avg * dfn[h]
            nd[h] += w * f_away(m); dd[h] += w * a_avg * att[a]
            nd[a] += w * f_home(m); dd[a] += w * h_avg * att[h]
        att = {t: (na[t] + P) / (da[t] + P) for t in teams}
        dfn = {t: (nd[t] + P) / (dd[t] + P) for t in teams}
        ma = sum(att.values()) / len(att)
        md = sum(dfn.values()) / len(dfn)
        att = {t: v / ma for t, v in att.items()}
        dfn = {t: v / md for t, v in dfn.items()}
    return att, dfn, h_avg, a_avg


def with_proxy_xg(matches):
    """Σεζόν χωρίς xG: εκτίμηση από σουτ στην εστία × (γκολ / σουτ στην εστία της ίδιας σεζόν)."""
    sot = [m for m in matches if m["hst"] is not None and m["ast"] is not None]
    shots = sum(m["hst"] + m["ast"] for m in sot)
    conv = sum(m["hg"] + m["ag"] for m in sot) / shots if shots else 0.3
    out = []
    for m in matches:
        if m["hxg"] is None and m["hst"] is not None and m["ast"] is not None:
            m = {**m, "hxg": m["hst"] * conv, "axg": m["ast"] * conv}
        out.append(m)
    return out


def fit_league(code, cur, prev, now=None, with_stats=True):
    """Επιστρέφει dict ομάδα -> ratings + στατιστικά, για ένα πρωτάθλημα."""
    now = now or datetime.now(timezone.utc)
    ms = []
    for m in with_proxy_xg(cur):
        ms.append({**m, "_w": _w(m["date"], now, 1.0)})
    for m in with_proxy_xg(prev):
        ms.append({**m, "_w": _w(m["date"], now, 0.6)})
    ms = [m for m in ms if m["_w"] > 0.01 and m["hg"] is not None]
    if len(ms) < 20:
        return {}, None
    att, dfn, h_avg, a_avg = _fit_pair(ms, lambda m: _blend(m["hg"], m["hxg"]), lambda m: _blend(m["ag"], m["axg"]))
    cms = [m for m in ms if m["hc"] is not None and m["ac"] is not None]
    catt, cdef, hc_avg, ac_avg = _fit_pair(cms, lambda m: m["hc"], lambda m: m["ac"]) if len(cms) > 20 else ({}, {}, 5.5, 4.5)

    # κάρτες: τάση κάθε ομάδας (σύνολο καρτών στα ματς της) σε σχέση με τον μέσο όρο
    def cards(m):
        return (m["hy"] or 0) + (m["ay"] or 0) + (m["hr"] or 0) + (m["ar"] or 0)
    kms = [m for m in ms if m["hy"] is not None]
    tw = sum(m["_w"] for m in kms) or 1
    card_avg = sum(m["_w"] * cards(m) for m in kms) / tw if kms else 4.0
    cn, cd = defaultdict(float), defaultdict(float)
    for m in kms:
        for t in (m["home"], m["away"]):
            cn[t] += m["_w"] * cards(m); cd[t] += m["_w"]
    card_f = {t: ((cn[t] + 3 * card_avg) / (cd[t] + 3)) / card_avg for t in cd}

    # όλα τα υπόλοιπα στατιστικά (σουτ, φάουλ, κάρτες ανά ομάδα, αποκρούσεις...): ίδια μέθοδος
    sfit = {}
    for k in stx.STATS:
        sm = [dict(m, _v=v) for m in ms if (v := stx.values(m, k)) is not None]
        if len(sm) >= 40:
            tw2 = sum(m["_w"] for m in sm) or 1
            avg = sum(m["_w"] * (m["_v"][0] + m["_v"][1]) for m in sm) / tw2 / 2
            sfit[k] = _fit_pair(sm, lambda m: m["_v"][0], lambda m: m["_v"][1], prior=3 * avg)
    hts = [m for m in ms if m.get("hthg") is not None and m.get("htag") is not None]
    g_all = sum(m["_w"] * (m["hg"] + m["ag"]) for m in hts)
    ht_share = (sum(m["_w"] * (m["hthg"] + m["htag"]) for m in hts) + 20) / (g_all + 20 / 0.44) if hts else 0.44

    cur_teams = {m["home"] for m in cur} | {m["away"] for m in cur}
    out = {}
    for t in cur_teams:
        out[t] = {
            "league": code, "att": att.get(t, 0.85), "def": dfn.get(t, 1.15),
            "catt": catt.get(t, 1.0), "cdef": cdef.get(t, 1.0), "cards": card_f.get(t, 1.0),
            "sx": {k: [round(f[0].get(t, 1.0), 3), round(f[1].get(t, 1.0), 3)] for k, f in sfit.items()},
        }
        if with_stats:
            tm = sorted([m for m in cur if t in (m["home"], m["away"])], key=lambda m: m["date"] or "")
            out[t]["stats"] = team_stats(t, tm)
            out[t]["stats_home"] = team_stats(t, [m for m in tm if m["home"] == t])
            out[t]["stats_away"] = team_stats(t, [m for m in tm if m["away"] == t])
    league = {"h_avg": h_avg, "a_avg": a_avg, "hc_avg": hc_avg, "ac_avg": ac_avg, "card_avg": card_avg,
              "sx": {k: [round(f[2], 3), round(f[3], 3)] for k, f in sfit.items()}, "ht_share": round(ht_share, 3)}
    return out, league


def team_stats(team, ms):
    n = len(ms)
    if not n:
        return {}
    s = defaultdict(float)
    form = []
    for m in ms:
        home = m["home"] == team
        gf, ga = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
        s["gf"] += gf; s["ga"] += ga
        s["xgf"] += (m["hxg"] if home else m["axg"]) or 0
        s["xga"] += (m["axg"] if home else m["hxg"]) or 0
        s["sot"] += (m["hst"] if home else m["ast"]) or 0
        s["cf"] += (m["hc"] if home else m["ac"]) or 0
        s["ca"] += (m["ac"] if home else m["hc"]) or 0
        s["cards"] += ((m["hy"] or 0) + (m["hr"] or 0)) if home else ((m["ay"] or 0) + (m["ar"] or 0))
        s["cards_a"] += ((m["ay"] or 0) + (m["ar"] or 0)) if home else ((m["hy"] or 0) + (m["hr"] or 0))
        s["sh"] += (m.get("hs") if home else m.get("as")) or 0
        s["sh_a"] += (m.get("as") if home else m.get("hs")) or 0
        s["sot_a"] += (m["ast"] if home else m["hst"]) or 0
        s["fo"] += (m.get("hf") if home else m.get("af")) or 0
        s["fo_a"] += (m.get("af") if home else m.get("hf")) or 0
        s["sv"] += max(((m["ast"] if home else m["hst"]) or 0) - ga, 0)
        s["btts"] += 1 if gf > 0 and ga > 0 else 0
        s["o25"] += 1 if gf + ga > 2.5 else 0
        s["cs"] += 1 if ga == 0 else 0
        form.append("W" if gf > ga else "D" if gf == ga else "L")
    r = lambda x: round(x, 2)
    return {
        "p": n, "gf": r(s["gf"] / n), "ga": r(s["ga"] / n), "xgf": r(s["xgf"] / n), "xga": r(s["xga"] / n),
        "sot": r(s["sot"] / n), "cf": r(s["cf"] / n), "ca": r(s["ca"] / n), "cards": r(s["cards"] / n),
        "cards_a": r(s["cards_a"] / n), "sh": r(s["sh"] / n), "sh_a": r(s["sh_a"] / n), "sot_a": r(s["sot_a"] / n),
        "fo": r(s["fo"] / n), "fo_a": r(s["fo_a"] / n), "sv": r(s["sv"] / n),
        "btts": r(s["btts"] / n), "o25": r(s["o25"] / n), "cs": r(s["cs"] / n), "form": "".join(form[-5:]),
    }


def expected(home_r, away_r, league, cross=False):
    """Αναμενόμενα γκολ/κόρνερ/κάρτες για έναν αγώνα."""
    lh = league["h_avg"] * home_r["att"] * away_r["def"]
    la = league["a_avg"] * away_r["att"] * home_r["def"]
    if cross:
        sh = config.RATING_LEAGUES.get(home_r["league"], (None, config.DEFAULT_LEAGUE_STRENGTH))[1]
        sa = config.RATING_LEAGUES.get(away_r["league"], (None, config.DEFAULT_LEAGUE_STRENGTH))[1]
        k = config.CROSS_EXP
        lh *= (sh / sa) ** k
        la *= (sa / sh) ** k
    lc = league["hc_avg"] * home_r["catt"] * away_r["cdef"] + league["ac_avg"] * away_r["catt"] * home_r["cdef"]
    lk = league["card_avg"] * (home_r["cards"] + away_r["cards"]) / 2
    return lh, la, lc, lk


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(lh, la):
    M = [[_pois(i, lh) * _pois(j, la) for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
    M[0][0] *= 1 - lh * la * RHO
    M[0][1] *= 1 + lh * RHO
    M[1][0] *= 1 + la * RHO
    M[1][1] *= 1 - RHO
    s = sum(map(sum, M))
    return [[v / s for v in row] for row in M]


def _market_probs(lh, la):
    M = score_matrix(lh, la)
    n = len(M)
    ph = sum(M[i][j] for i in range(n) for j in range(n) if i > j)
    pa = sum(M[i][j] for i in range(n) for j in range(n) if i < j)
    po = sum(M[i][j] for i in range(n) for j in range(n) if i + j > 2.5)
    return ph, pa, po


def implied_lambdas(p1, p2, pover=None):
    """Βρίσκει τα αναμενόμενα γκολ που "βλέπει" η αγορά (από 1X2 και Over/Under 2.5 χωρίς γκανιότα)."""
    def err(lh, la):
        ph, pa, po = _market_probs(lh, la)
        e = (ph - p1) ** 2 + (pa - p2) ** 2
        if pover is not None:
            e += (po - pover) ** 2
        return e
    best = min(((err(h / 10, a / 10), h / 10, a / 10) for h in range(2, 46, 2) for a in range(2, 46, 2)))
    _, bh, ba = best
    for step in (0.05, 0.01):
        cand = [(err(bh + i * step, ba + j * step), bh + i * step, ba + j * step)
                for i in range(-4, 5) for j in range(-4, 5) if bh + i * step > 0.05 and ba + j * step > 0.05]
        _, bh, ba = min(cand)
    return bh, ba


def pois_over(lam, line):
    """P(X > line) για Poisson (line με .5)."""
    k = int(math.floor(line))
    return 1 - sum(_pois(i, lam) for i in range(k + 1))
