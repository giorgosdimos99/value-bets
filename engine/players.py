"""Αγορές παικτών Premier League από το επίσημο Fantasy Premier League API (δωρεάν, χωρίς κλειδί).

Για κάθε παίκτη: λεπτά, ξεκινήματα, xG, xA, κάρτες, τάκλιν, CBI, ανακτήσεις. Από αυτά:
- Σκοράρει (οποτεδήποτε): xG/90 × αναμενόμενα λεπτά × πόσο καλύτερη/χειρότερη είναι η επίθεση σε αυτό το ματς
- Ασίστ: το ίδιο με xA
- Κάρτα: κάρτες/90 (συρρίκνωση προς τον μέσο όρο της θέσης) × διαιτητής
- Τάκλιν Over 0.5 / 1.5 / 2.5: τάκλιν/90 (Poisson)
Δεν υπάρχουν δωρεάν ιστορικές αποδόσεις για αγορές παικτών, οπότε δίνουμε μόνο πιθανότητα και δίκαιη απόδοση.
"""
import json
import math

from . import names, sources

POS = {1: "ΤΦ", 2: "ΑΜ", 3: "ΜΕ", 4: "ΕΠ"}
PRIOR_MIN = 450  # 5 αγώνες "μέσου" παίκτη της θέσης


def _fpl():
    hit = sources._cached("fpl_bootstrap.json", 6)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get("https://fantasy.premierleague.com/api/bootstrap-static/")
        d = json.loads(raw)
    except Exception as e:
        print(f"  ! FPL: {e}")
        return sources._cached("fpl_bootstrap.json", 0, stale_ok=True)
    keep = ("id", "web_name", "team", "element_type", "minutes", "starts", "goals_scored", "assists",
            "expected_goals", "expected_assists", "yellow_cards", "red_cards", "tackles",
            "clearances_blocks_interceptions", "recoveries", "defensive_contribution", "status",
            "chance_of_playing_next_round", "penalties_order", "news")
    out = {"teams": {t["id"]: t["name"] for t in d["teams"]},
           "gw": max((e["id"] for e in d["events"] if e["finished"]), default=0),
           "players": [{k: p.get(k) for k in keep} for p in d["elements"]]}
    sources._save_cache("fpl_bootstrap.json", out)
    return out


def _f(x):
    try:
        return float(x or 0)
    except ValueError:
        return 0.0


def _p_over(lam, line):
    k = int(math.floor(line))
    return 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def _fair(p):
    return round(1 / p, 2) if p > 0.005 else None


def attach_fpl(matches, ctx):
    data = _fpl()
    if not data:
        return
    teams = {int(k): v for k, v in data["teams"].items()}
    pl = [p for p in data["players"] if p["minutes"] and p["minutes"] > 0]
    gw = max(data["gw"], 1)
    # μέσοι όροι ανά θέση (για συρρίκνωση των μικρών δειγμάτων)
    avg = {}
    for pos in POS:
        ps = [p for p in pl if p["element_type"] == pos]
        mins = sum(p["minutes"] for p in ps) or 1
        avg[pos] = {k: sum(_f(p[k]) for p in ps) / mins * 90 for k in ("yellow_cards", "tackles", "expected_goals", "expected_assists")}
    for m in matches:
        out = {}
        for side, team in (("home", m["home"]), ("away", m["away"])):
            tid = next((i for i, n in teams.items() if names.match(team, [n])), None)
            if tid is None:
                continue
            squad = [p for p in pl if p["team"] == tid]
            team_xg = sum(_f(p["expected_goals"]) for p in squad) / gw or 1.0
            xg_match = m["xg"][0 if side == "home" else 1]
            att_k = xg_match / team_xg  # πόσο πιο "εύκολο" είναι το ματς από τον μέσο όρο της ομάδας
            ref_k = (m.get("ref_stats") or {}).get("factor", 1.0)
            rows = []
            for p in squad:
                if p["status"] not in ("a", "d") or (p["chance_of_playing_next_round"] is not None and p["chance_of_playing_next_round"] < 75):
                    continue
                if not p["starts"] or p["starts"] < max(2, 0.4 * gw):
                    continue
                em = min(90.0, p["minutes"] / max(p["starts"], 1)) * min(1.0, p["starts"] / gw * 1.15)
                pos = p["element_type"]
                w = p["minutes"]

                def rate(k):  # ανά 90', με συρρίκνωση προς τη θέση
                    return (_f(p[k]) + avg[pos][k] * PRIOR_MIN / 90) / (w + PRIOR_MIN) * 90
                lam_g = rate("expected_goals") * em / 90 * att_k
                lam_a = rate("expected_assists") * em / 90 * att_k
                lam_c = rate("yellow_cards") * em / 90 * ref_k
                lam_t = rate("tackles") * em / 90
                pg, pa, pc = 1 - math.exp(-lam_g), 1 - math.exp(-lam_a), 1 - math.exp(-lam_c)
                rows.append({
                    "name": p["web_name"], "pos": POS[pos], "mins": round(em), "starts": p["starts"],
                    "goals": p["goals_scored"], "xg": round(_f(p["expected_goals"]), 2),
                    "assists": p["assists"], "xa": round(_f(p["expected_assists"]), 2),
                    "yc": p["yellow_cards"], "tackles": p["tackles"],
                    "tackles90": round(_f(p["tackles"]) / w * 90, 2), "cbi": p["clearances_blocks_interceptions"],
                    "pen": p["penalties_order"] == 1, "news": p["news"] or None,
                    "p_goal": round(pg, 3), "fair_goal": _fair(pg),
                    "p_assist": round(pa, 3), "fair_assist": _fair(pa),
                    "p_card": round(pc, 3), "fair_card": _fair(pc),
                    "p_tk1": round(_p_over(lam_t, 0.5), 3), "p_tk2": round(_p_over(lam_t, 1.5), 3),
                    "p_tk3": round(_p_over(lam_t, 2.5), 3),
                })
            rows.sort(key=lambda r: -r["mins"])
            out[side] = rows[:14]
        if out:
            m["players"] = {"source": f"Fantasy Premier League (μέχρι την αγωνιστική {gw})", **out}
