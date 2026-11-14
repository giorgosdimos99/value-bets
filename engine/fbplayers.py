"""Στατιστικά παικτών ποδοσφαίρου (σουτ, σουτ στην εστία, φάουλ που κάνει/δέχεται, κάρτες, γκολ, ασίστ).

Πηγή: ESPN (δωρεάν), ανά αγώνα και παίκτη. Κάθε αγώνας κατεβαίνει μία φορά και μένει στην cache (.cache/fbp_<λίγκα>.json).
Μοντέλο (ίδια λογική με το μπάσκετ, engine/props.py):
  αναμενόμενα λεπτά × ρυθμός ανά 90' (μισός κανονικός, μισός χωρίς τα άκρα) × τι δίνει ο αντίπαλος,
  πιθανότητα = 75% κατανομή + 25% πόσες φορές το έκανε στους τελευταίους αγώνες.
Έλεγχος: python -m engine.fbplayers  (κάθε εμφάνιση προβλέπεται μόνο με τους προηγούμενους αγώνες).
"""
import json
import math
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import config, espn, names, sources

LEAGUES = {"PL": "eng.1", "PD": "esp.1", "SA": "ita.1", "BL": "ger.1", "FL1": "fra.1", "GR": "gre.1",
           "CL": "uefa.champions", "UEL": "uefa.europa"}
# θέση στη γραμμή: [όνομα, θέση, λεπτά, σουτ, στην εστία, φάουλ που κάνει, φάουλ που δέχεται, κίτρινες, κόκκινες, γκολ, ασίστ, αποκρούσεις, βασικός]
STATS = {"sh": ("Σουτ", 3), "st": ("Σουτ στην εστία", 4), "fc": ("Φάουλ (που κάνει)", 5), "fs": ("Φάουλ (που δέχεται)", 6),
         "yc": ("Κάρτα", 7), "g": ("Γκολ", 9), "as": ("Ασίστ", 10)}
LINES = {"sh": (0.5, 1.5, 2.5, 3.5), "st": (0.5, 1.5, 2.5), "fc": (0.5, 1.5, 2.5), "fs": (0.5, 1.5, 2.5), "yc": (0.5,), "g": (0.5,), "as": (0.5,)}
K_OPP = 8.0
TRIM_W, FREQ_W, FREQ_N = 0.5, 0.25, 15
MIN_APPS, MIN_MINS = 5, 45.0
NEW_PER_RUN = 80
MAX_P = 1 / (1.40 * 1.06)  # 0,674: πάνω από αυτό η εταιρεία δίνει κάτω από 1,40


def _season_start(now=None):
    now = now or datetime.now(timezone.utc)
    return date(now.year if now.month >= 7 else now.year - 1, 8, 1)


def _clock(s):
    m = re.match(r"(\d+)", s or "")
    return int(m.group(1)) if m else None


def _compact(s):
    comp = s["header"]["competitions"][0]
    tm = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
    out = {"d": comp["date"], "h": tm.get("home"), "a": tm.get("away")}
    for r in s.get("rosters", []):
        rows = []
        for p in r.get("roster") or []:
            st = {x["name"]: x.get("value") or 0 for x in p.get("stats", [])}
            sub_t = next((_clock((pl.get("clock") or {}).get("displayValue")) for pl in p.get("plays", []) if pl.get("substitution")), None)
            if p.get("starter"):
                mins = min(sub_t, 90) if p.get("subbedOut") and sub_t else 90
            elif p.get("subbedIn"):
                mins = max(90 - min(sub_t, 90), 1) if sub_t else 15
            else:
                mins = 0
            v = lambda k: int(st.get(k, 0) or 0)
            rows.append([p["athlete"]["displayName"], (p.get("position") or {}).get("abbreviation", ""), mins, v("totalShots"), v("shotsOnTarget"),
                         v("foulsCommitted"), v("foulsSuffered"), v("yellowCards"), v("redCards"), v("totalGoals"), v("goalAssists"),
                         v("saves"), 1 if p.get("starter") else 0])
        out[r["homeAway"]] = rows
    return out if out.get("home") and out.get("away") else None


def load(cid, limit=NEW_PER_RUN):
    """{id αγώνα: συμπιεσμένα στατιστικά} για όλη τη σεζόν. Κατεβάζει μόνο ό,τι λείπει (το πολύ `limit` ανά τρέξιμο)."""
    slug = LEAGUES[cid]
    key = f"fbp_{slug}.json"
    box = sources._cached(key, 0, stale_ok=True) or {}
    today = datetime.now(timezone.utc).date()
    evs = [g for g in espn.days(f"soccer/{slug}", _season_start(), today, draw=True) if g["played"]]
    new = 0
    for g in evs:
        if str(g["id"]) in box or new >= limit:
            continue
        try:
            raw, _ = sources._get(f"{espn.BASE}/soccer/{slug}/summary?event={g['id']}", headers={"User-Agent": "Mozilla/5.0"})
            c = _compact(json.loads(raw))
        except Exception as e:
            print(f"  ! παίκτες {slug} {g['id']}: {str(e)[:80]}")
            continue
        box[str(g["id"])] = c or {"d": g["date"], "skip": 1}  # χωρίς συνθέσεις: δεν ξαναζητιέται
        new += 1
        time.sleep(0.25)
        if new % 40 == 0:
            sources._save_cache(key, box)
    if new:
        sources._save_cache(key, box)
    return box


class Model:
    def __init__(self, box):
        self.games = sorted((g for g in box.values() if not g.get("skip")), key=lambda g: g["d"])
        self.by_player = defaultdict(list)   # (παίκτης, ομάδα) -> [(ημ/νία, εντός, γραμμή, αντίπαλος)]
        self.allowed = defaultdict(list)     # ομάδα -> [(ημ/νία, {στατ: σύνολο που δέχτηκε})]
        self.team_dates = defaultdict(list)
        for g in self.games:
            for side, team, opp in (("home", g["h"], g["a"]), ("away", g["a"], g["h"])):
                tot = {k: 0 for k in STATS}
                for r in g[side]:
                    self.by_player[(r[0], team)].append((g["d"], 1 if side == "home" else 0, r, opp))
                    for k, (_, i) in STATS.items():
                        tot[k] += r[i]
                self.allowed[opp].append((g["d"], tot))
                self.team_dates[team].append(g["d"])
        self._lg = {}

    def opp_factor(self, opp, k, before):
        d0 = before[:10]
        if d0 not in self._lg:
            rows = [t for lst in self.allowed.values() for d, t in lst if d[:10] < d0]
            self._lg[d0] = {s: (sum(t[s] for t in rows) / len(rows) if rows else 0) for s in STATS}
        rows = [t for d, t in self.allowed.get(opp, []) if d[:10] < d0]
        lg = self._lg[d0][k]
        if len(rows) < 3 or not lg:
            return 1.0
        raw = (sum(t[k] for t in rows) / len(rows)) / lg
        return 1 + (raw - 1) * len(rows) / (len(rows) + K_OPP)

    def predict(self, player, team, opp, before, min_apps=MIN_APPS, min_mins=MIN_MINS):
        """({στατ: (μ, μ.ό. ανά αγώνα στους τελευταίους 10, τιμές τελευταίων αγώνων)}, αναμενόμενα λεπτά, εντός/εκτός των αγώνων) ή None."""
        h = [e for e in self.by_player.get((player, team), []) if e[0][:10] < before[:10]]
        played = [e for e in h if e[2][2] > 0]
        if len(played) < min_apps:
            return None
        l5, l10 = h[-5:], h[-10:]   # μαζί με αγώνες που έμεινε στον πάγκο (0 λεπτά): μετράνε στα αναμενόμενα λεπτά
        m_exp = 0.6 * sum(e[2][2] for e in l5) / len(l5) + 0.4 * sum(e[2][2] for e in l10) / len(l10)
        if m_exp < min_mins:
            return None
        p12 = played[-12:]
        mins = sum(e[2][2] for e in p12) or 1
        ok = [e for e in p12 if e[2][2] >= 20]
        lastn = played[-FREQ_N:]
        out = {}
        for k, (_, i) in STATS.items():
            mu = sum(e[2][i] for e in p12) / mins * m_exp
            if len(ok) >= 6:
                sc = sorted(e[2][i] / e[2][2] * m_exp for e in ok)
                w = [sc[1]] + sc[1:-1] + [sc[-2]]
                mu = (1 - TRIM_W) * mu + TRIM_W * sum(w) / len(w)
            mu *= self.opp_factor(opp, k, before)
            out[k] = (mu, sum(e[2][i] for e in played[-10:]) / len(played[-10:]), [e[2][i] for e in lastn])
        return out, m_exp, [e[1] for e in lastn]


def p_over(mu, line, raw=None):
    """P(τιμή > γραμμή) με Poisson + συχνότητα στους τελευταίους αγώνες."""
    k = int(math.floor(line))
    mu = max(mu, 1e-6)
    p = 1 - sum(math.exp(-mu) * mu ** j / math.factorial(j) for j in range(k + 1))
    if raw and len(raw) >= 6:
        p = (1 - FREQ_W) * p + FREQ_W * (sum(1 for x in raw if x > line) + 1) / (len(raw) + 2)
    return p


def research(M):
    """Βαθμονόμηση: όταν το μοντέλο λέει 60%, βγαίνει 60%; Μόνο εμφανίσεις όπου ο παίκτης ξεκίνησε βασικός
    (τότε ισχύει το στοίχημα). Επιστρέφει ανά στατιστικό: πλήθος, πίνακα πρόβλεψη/πραγματικό, κλίση διόρθωσης."""
    acc = {k: defaultdict(lambda: [0, 0.0, 0]) for k in STATS}
    slope = {k: [0.0, 0.0] for k in STATS}
    base = {k: defaultdict(lambda: [0, 0]) for k in STATS}
    rows = []
    for g in M.games:
        for side, team, opp in (("home", g["h"], g["a"]), ("away", g["a"], g["h"])):
            for r in g[side]:
                if not r[12]:
                    continue
                pr = M.predict(r[0], team, opp, g["d"])
                if pr:
                    rows.append((pr[0], r))
    for P, r in rows:
        for k, (_, i) in STATS.items():
            for L in LINES[k]:
                b = base[k][L]; b[0] += 1; b[1] += r[i] > L
    for P, r in rows:
        for k, (_, i) in STATS.items():
            mu, _, raw = P[k]
            for L in LINES[k]:
                p = p_over(mu, L, raw)
                y = r[i] > L
                c = acc[k][min(int(p * 5), 4)]
                c[0] += 1; c[1] += p; c[2] += y
                b = base[k][L]; p0 = b[1] / b[0]
                slope[k][0] += (y - p0) * (p - p0); slope[k][1] += (p - p0) ** 2
    out = {}
    for k in STATS:
        n = sum(c[0] for c in acc[k].values())
        if n < 300:
            continue
        cal = min(max(slope[k][0] / slope[k][1], 0.0), 1.0) if slope[k][1] else 1.0
        out[k] = {"name": STATS[k][0], "n": n, "cal": round(cal, 3),
                  "base": {str(L): round(b[1] / b[0], 4) for L, b in base[k].items() if b[0]},
                  "buckets": [{"p": f"{b * 20}-{b * 20 + 20}%", "n": c[0], "pred": round(c[1] / c[0], 3), "hit": round(c[2] / c[0], 3)}
                              for b, c in sorted(acc[k].items()) if c[0] >= 30]}
    return out


def calibrated(p, k, L, check):
    """Φέρνει την πιθανότητα προς τη μέση συχνότητα της λίγκας όσο λέει ο έλεγχος (cal<1 = το μοντέλο ήταν πιο σίγουρο απ' ό,τι έπρεπε)."""
    c = check.get(k)
    if not c:
        return p
    p0 = c["base"].get(str(L), p)
    return p0 + c["cal"] * (p - p0)


def _split(raw, flags, L, side):
    ok = [(x > L) == (side == "Over") for x in raw]
    hm = [o for o, f in zip(ok, flags) if f]
    aw = [o for o, f in zip(ok, flags) if not f]
    return {"home": [sum(hm), len(hm)], "away": [sum(aw), len(aw)], "last5": [sum(ok[-5:]), len(ok[-5:])]}


def for_match(M, check, home, away, when, n=6):
    """Επιλογές παικτών + πρόβλεψη κάθε παίκτη (για το Δελτίο) για έναν αγώνα. home/away: ονόματα όπως στην ESPN."""
    picks, pm = [], {"home": [], "away": []}
    for side, team, opp in (("home", home, away), ("away", away, home)):
        last = sorted(M.team_dates.get(team, []))[-3:]
        squad = [p for (p, t), h in M.by_player.items() if t == team and any(e[0] in last for e in h)]
        for p in squad:
            pr = M.predict(p, team, opp, when, min_apps=3, min_mins=10)
            if not pr:
                continue
            P, m_exp, flags = pr
            apps = sum(1 for e in M.by_player[(p, team)] if e[2][2] > 0)
            few = apps < MIN_APPS or m_exp < MIN_MINS
            pm[side].append({"name": p, "mins": round(m_exp), "g": apps, "few": few,
                             "mu": {k: round(v[0], 2) for k, v in P.items()}, "avg10": {k: round(v[1], 2) for k, v in P.items()},
                             "h": "|".join(".".join([str(P[k][2][i]) for k in STATS] + [str(flags[i])]) for i in range(len(flags)))})
            if few or m_exp < 60:
                continue
            best = None
            for k in STATS:
                if k not in check:
                    continue
                mu, a10, raw = P[k]
                for L in LINES[k]:
                    po = calibrated(p_over(mu, L, raw), k, L, check)
                    for sd, pp in (("Over", po), ("Under", 1 - po)):
                        if sd == "Under":
                            continue  # οι εταιρείες δίνουν στους παίκτες μόνο «Over» (1+ σουτ, 2+ φάουλ...), όχι Under
                        # απόδοση εταιρείας ~ 1 / (πιθανότητα × 1,06). Κάτω από 1,40 δεν έχει νόημα να προταθεί (π.χ. «1+ σουτ» στο 1,15)
                        if 0.55 <= pp <= MAX_P and (best is None or pp > best["p"]):
                            lab = {"yc": "Να πάρει κάρτα", "g": "Να σκοράρει", "as": "Να δώσει ασίστ"}.get(k, f"{STATS[k][0]} {sd} {L:g}")
                            best = {"player": p, "team": team, "stat": k, "side": sd, "line": L, "label": f"{p}: {lab}", "p": round(pp, 3),
                                    "exp": round(mu, 2), "avg10": round(a10, 2), "mins": round(m_exp), "min_odds": round(1.03 / pp, 2),
                                    "freq": [sum(1 for x in raw if (x > L) == (sd == "Over")), len(raw)],
                                    "split": _split(raw, flags, L, sd), "at_home": side == "home"}
            if best:
                picks.append(best)
        pm[side].sort(key=lambda x: -x["mins"])
    picks.sort(key=lambda x: -x["p"])
    return picks[:n], pm


def attach(matches, cid):
    """Προσθέτει σε κάθε αγώνα της διοργάνωσης: fptop (επιλογές παικτών) και pmodel (για το Δελτίο)."""
    if cid not in LEAGUES or not matches:
        return None
    box = load(cid)
    M = Model(box)
    if len(M.games) < 30:
        return None
    check = sources._cached(f"fbp_check_{cid}.json", 24 * 7)
    if check is None:
        check = research(M)
        sources._save_cache(f"fbp_check_{cid}.json", check)
    teams = sorted(M.team_dates)
    n = 0
    for m in matches:
        h = names.match(m.get("home_full") or m["home"], teams) or names.match(m["home"], teams)
        a = names.match(m.get("away_full") or m["away"], teams) or names.match(m["away"], teams)
        if not h or not a or h == a:
            continue
        picks, pm = for_match(M, check, h, a, m["date"])
        for x in picks:
            x["team"] = m["home"] if x["team"] == h else m["away"]
        m["fptop"] = picks
        m["pmodel"] = {"sport": "fb", "base": list(STATS), "names": {k: v[0] for k, v in STATS.items()}, "phi": {k: 0 for k in STATS},
                       "ok": list(check), "cal": 1.0, "home": pm["home"], "away": pm["away"],
                       # βαθμονόμηση ανά στατιστικό (κλίση) και μέση συχνότητα της λίγκας ανά γραμμή, για το Δελτίο
                       "calk": {k: v["cal"] for k, v in check.items()}, "basek": {k: v["base"] for k, v in check.items()}}
        n += bool(picks)
    return {"matches": n, "games": len(M.games), "check": check}


if __name__ == "__main__":
    import sys
    for cid in (sys.argv[1:] or list(LEAGUES)):
        box = load(cid, limit=10 ** 6)
        M = Model(box)
        res = research(M)
        print(f"{cid}: {len(M.games)} αγώνες")
        for k, v in res.items():
            print(f"   {v['name']:22s} n={v['n']:6d} κλίση {v['cal']}  " + " ".join(f"[{b['p']} {b['pred']:.2f}->{b['hit']:.2f} ({b['n']})]" for b in v["buckets"]))
