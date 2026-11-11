"""EuroLeague: πρόγραμμα, αποτελέσματα και στατιστικά παικτών από το επίσημο feed της EuroLeague (δωρεάν).

Μοντέλο:
- Επίθεση/άμυνα κάθε ομάδας από τους πόντους (τρέχουσα + προηγούμενη σεζόν, τα πρόσφατα μετράνε περισσότερο).
- Διαφορά και σύνολο πόντων ~ κανονική κατανομή. Η τυπική απόκλιση μετριέται από τα λάθη του μοντέλου
  στους αγώνες που έχουν παιχτεί (όχι υπόθεση).
- Ισοπαλία στην κανονική διάρκεια -> παράταση (~+20 πόντοι στο σύνολο, νικητής 50/50).
- Ανάμειξη με την αγορά (χάντικαπ και σύνολο των εταιρειών) όπως στο ποδόσφαιρο.
"""
import json
import math
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

from . import bcl, esake, config, espn, markets, model, predictions, props, sources

FEED = "https://feeds.incrowdsports.com/provider/euroleague-feeds/v2/competitions/{c}/seasons/{s}/games?limit=400"
BOX = "https://api-live.euroleague.net/v2/competitions/{c}/seasons/{s}/games/{g}/stats"
MODEL_WEIGHT = 0.15  # χωρίς δωρεάν ιστορικές αποδόσεις δεν γίνεται backtest -> συντηρητικά, κοντά στην αγορά
OT_POINTS = 20.0  # παράταση: περίπου 10 πόντοι ανά ομάδα
STOP = {"fc", "kk", "bc", "sk", "jk", "basket", "basketball", "club", "tel", "aviv", "istanbul", "athens", "belgrade",
        "piraeus", "munich", "munchen", "the", "de", "bet", "mozzart", "meridianbet", "aktor", "tarfin", "ibi", "rapyd",
        "kosner", "ldlc", "armani", "segafredo", "nis", "pallacanestro", "basquet", "lyon", "vitoria", "gasteiz", "kaunas"}


def _tokens(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("milano", "milan").replace("munchen", "munich")
    return {t for t in re.split(r"[^a-z]+", s) if len(t) >= 3 and t not in STOP}


def team_match(name, candidates):
    a = _tokens(name)
    best, score = None, 0
    for c in candidates:
        k = len(a & _tokens(c))
        if k > score:
            best, score = c, k
    return best


def _season(now=None):
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def games(c, year):
    s = f"{c}{year}"
    key = f"el_games_{s}.json"
    current = year == _season()
    hit = sources._cached(key, 2 if current else 24 * 60)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get(FEED.format(c=c, s=s))
        data = json.loads(raw)["data"]
    except Exception as e:
        print(f"  ! EuroLeague {s}: {e}")
        return sources._cached(key, 0, stale_ok=True) or []
    out = [{
        "code": g["code"], "date": g["date"], "round": (g.get("round") or {}).get("round"),
        "phase": (g.get("phaseType") or {}).get("code"), "played": g["status"] == "result",
        "home": g["home"]["name"], "away": g["away"]["name"],
        "home_short": g["home"].get("editorialName") or g["home"].get("abbreviatedName"),
        "away_short": g["away"].get("editorialName") or g["away"].get("abbreviatedName"),
        "home_crest": (g["home"].get("imageUrls") or {}).get("crest"),
        "away_crest": (g["away"].get("imageUrls") or {}).get("crest"),
        "hp": g["home"]["score"], "ap": g["away"]["score"],
        "ot": bool((g["home"].get("quarters") or {}).get("ot1")),
    } for g in data]
    sources._save_cache(key, out)
    return out


def boxscores(c, year, played, limit=None):
    """Στατιστικά παικτών ανά αγώνα (μόνο όσα λείπουν από την cache)."""
    s = f"{c}{year}"
    key = f"el_box_{s}.json"
    box = sources._cached(key, 0, stale_ok=True) or {}
    new = 0
    for g in played:
        if str(g["code"]) in box:
            continue
        if limit is not None and new >= limit:
            break
        d = None
        for i in range(3):
            try:
                raw, _ = sources._get(BOX.format(c=c, s=s, g=g["code"]))
                d = json.loads(raw)
                break
            except Exception as e:
                if "429" not in str(e):
                    print(f"  ! boxscore {g['code']}: {e}")
                    break
                time.sleep(30 * (i + 1))  # όριο κλήσεων: περιμένουμε και ξαναδοκιμάζουμε
        if d is None:
            if new and new % 25:
                sources._save_cache(key, box)
            continue
        time.sleep(1.5)  # το feed έχει όριο κλήσεων
        entry = {}
        for side, team in (("local", g["home"]), ("road", g["away"])):
            rows = []
            for p in d[side]["players"]:
                st = p["stats"]
                if not st.get("timePlayed"):
                    continue
                rows.append([p["player"]["person"]["name"], round(st["timePlayed"] / 60, 1), st["points"],
                             st["totalRebounds"], st["assistances"], st["fieldGoalsMade3"], st["steals"],
                             st["turnovers"], st["foulsCommited"], st["blocksFavour"], int(bool(st.get("startFive")))])
            entry["home" if side == "local" else "away"] = rows
        box[str(g["code"])] = entry
        new += 1
        if new % 25 == 0:
            sources._save_cache(key, box)
    if new:
        sources._save_cache(key, box)
    return box


# ---------------- μοντέλο ----------------

def fit(played_cur, played_prev):
    now = datetime.now(timezone.utc)
    ms = []
    for g, f in [(g, 1.0) for g in played_cur] + [(g, 0.5) for g in played_prev]:
        age = (now - datetime.fromisoformat(g["date"].replace("Z", "+00:00"))).days
        # παράταση: αφαιρούμε τους πόντους της παράτασης περίπου, για να μετράμε την κανονική διάρκεια
        hp, ap = g["hp"], g["ap"]
        if g.get("ot"):
            hp, ap = hp - OT_POINTS / 2, ap - OT_POINTS / 2
        ms.append({"home": g["home"], "away": g["away"], "hp": hp, "ap": ap,
                   "_w": f * 0.5 ** (max(age, 0) / config.HALF_LIFE_DAYS)})
    att, dfn, h_avg, a_avg = model._fit_pair(ms, lambda m: m["hp"], lambda m: m["ap"])
    # τυπική απόκλιση από τα λάθη του μοντέλου (σταθμισμένα)
    se_m = se_t = ws = 0.0
    for m in ms:
        ph = h_avg * att[m["home"]] * dfn[m["away"]]
        pa = a_avg * att[m["away"]] * dfn[m["home"]]
        se_m += m["_w"] * ((m["hp"] - m["ap"]) - (ph - pa)) ** 2
        se_t += m["_w"] * ((m["hp"] + m["ap"]) - (ph + pa)) ** 2
        ws += m["_w"]
    # +5%: τα λάθη μέσα στο δείγμα είναι λίγο μικρότερα από τα πραγματικά
    return {"att": att, "def": dfn, "h_avg": h_avg, "a_avg": a_avg,
            "sd_margin": math.sqrt(se_m / ws) * 1.05, "sd_total": math.sqrt(se_t / ws) * 1.05, "n": len(ms)}


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _pmf_int(mu, sd, lo, hi):
    return {k: _phi((k + 0.5 - mu) / sd) - _phi((k - 0.5 - mu) / sd) for k in range(lo, hi + 1)}


def selections(mu_h, mu_a, sd_m, sd_t, lines):
    """Πιθανότητες για νικητή, χάντικαπ, σύνολο, πόντους ομάδας (με παράταση)."""
    margin = _pmf_int(mu_h - mu_a, sd_m, -70, 70)
    p0 = margin.pop(0)
    # παράταση: η ισοπαλία μοιράζεται σε μικρές νίκες (μέση διαφορά παράτασης ~4)
    margin[4] = margin.get(4, 0) + p0 / 2
    margin[-4] = margin.get(-4, 0) + p0 / 2
    out = []
    ph = sum(p for k, p in margin.items() if k > 0)
    out.append(markets._sel("Νικητής (με παράταση)", "ML", "H", "1", ph))
    out.append(markets._sel("Νικητής (με παράταση)", "ML", "A", "2", 1 - ph))
    for L in lines["spread"]:
        wh = sum(p for k, p in margin.items() if k + L > 0)
        pu = sum(p for k, p in margin.items() if k + L == 0)
        key = f"AH{L:+g}"
        out.append(markets._sel("Χάντικαπ", key, "H", f"1 ({L:+g})", wh, pu))
        out.append(markets._sel("Χάντικαπ", key, "A", f"2 ({-L:+g})", 1 - wh - pu, pu))

    def total_over(mu, sd, line):
        reg = 1 - _phi((line - mu) / sd)
        ot = 1 - _phi((line - mu - OT_POINTS) / sd)
        return (1 - p0) * reg + p0 * ot
    for L in lines["total"]:
        po = total_over(mu_h + mu_a, sd_t, L)
        out.append(markets._sel("Σύνολο πόντων", f"OU{L:g}", "Over", f"Over {L:g}", po))
        out.append(markets._sel("Σύνολο πόντων", f"OU{L:g}", "Under", f"Under {L:g}", 1 - po))
    sd_team = sd_t / math.sqrt(2) * 1.1
    for side, mu, lab, key in (("h", mu_h, "Γηπεδούχος", "HT_OU"), ("a", mu_a, "Φιλοξενούμενος", "AT_OU")):
        for L in lines[side]:
            # σε παράταση η κάθε ομάδα βάζει ~10 πόντους επιπλέον
            po = (1 - p0) * (1 - _phi((L - mu) / sd_team)) + p0 * (1 - _phi((L - mu - OT_POINTS / 2) / sd_team))
            grp = f"Πόντοι {lab.lower()}"
            out.append(markets._sel(grp, f"{key}{L:g}", "Over", f"{lab} Over {L:g}", po))
            out.append(markets._sel(grp, f"{key}{L:g}", "Under", f"{lab} Under {L:g}", 1 - po))
    return out


def _market_lines(books):
    spreads, totals = [], []
    for b, mk in books.items():
        if any(x in b for x in markets.NOT_A_BOOK if x != "Pinnacle"):
            continue
        for k, v in mk.items():
            if k.startswith("AH") and "H" in v and "A" in v:
                spreads.append((abs(v["H"] - v["A"]), float(k[2:])))
            if k.startswith("OU") and "Over" in v and "Under" in v:
                totals.append((abs(v["Over"] - v["Under"]), float(k[2:])))
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    # κύρια γραμμή: εκείνη με τις πιο "ίσες" αποδόσεις σε κάθε εταιρεία
    sp = med([x[1] for x in sorted(spreads)[:max(1, len(spreads) // 2)]])
    tt = med([x[1] for x in sorted(totals)[:max(1, len(totals) // 2)]])
    return sp, tt


def _half(x):
    return math.floor(x) + 0.5


def players_for(team, box_games, mu_team, team_avg):
    rows = {}
    for side, plist in box_games:
        for r in plist:
            name, mins, pts, reb, ast, tpm, stl, tov, fouls, blk, start = r
            rows.setdefault(name, []).append((mins, pts, reb, ast, tpm, stl, fouls, start))
    out = []
    k = mu_team / team_avg if team_avg else 1.0
    for name, gl in rows.items():
        if len(gl) < 3:
            continue
        recent = gl[-10:]
        mins = sum(g[0] for g in recent) / len(recent)
        if mins < 12:
            continue
        def stat(i, scale=1.0, counts=False):
            vals = [g[i] for g in recent]
            mean = sum(vals) / len(vals) * scale
            line = _half(mean)
            if counts:  # ριμπάουντ, ασίστ, τρίποντα, φάουλ: Poisson (σωστό και για μικρούς μέσους όρους)
                lam = max(mean, 0.05)
                po = 1 - sum(math.exp(-lam) * lam ** j / math.factorial(j) for j in range(int(line) + 1))
            else:
                var = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
                sd = max(math.sqrt(var), math.sqrt(max(mean, 0.5)))
                po = 1 - _phi((line - mean) / sd)
            return {"avg": round(mean, 1), "line": line, "p_over": round(po, 3),
                    "fair_over": round(1 / po, 2) if po > 0.01 else None,
                    "fair_under": round(1 / (1 - po), 2) if po < 0.99 else None}
        pra = [g[1] + g[2] + g[3] for g in recent]
        pra_mean = sum(pra) / len(pra) * (1 + (k - 1) * 0.6)
        pra_sd = max(math.sqrt(sum((v - pra_mean) ** 2 for v in pra) / max(len(pra) - 1, 1)), math.sqrt(pra_mean))
        pra_line = _half(pra_mean)
        pra_po = 1 - _phi((pra_line - pra_mean) / pra_sd)
        if ", " in name:
            last, _, first = name.partition(", ")
            name = f"{first.title()} {last.title()}".strip()
        out.append({
            "name": name, "games": len(gl), "mins": round(mins, 1),
            "starter": sum(g[7] for g in recent) >= len(recent) / 2,
            "pts": stat(1, k), "reb": stat(2, counts=True), "ast": stat(3, counts=True),
            "tpm": stat(4, counts=True), "fouls": stat(6, counts=True),
            "pra": {"avg": round(pra_mean, 1), "line": pra_line, "p_over": round(pra_po, 3),
                    "fair_over": round(1 / pra_po, 2) if pra_po > 0.01 else None,
                    "fair_under": round(1 / (1 - pra_po), 2) if pra_po < 0.99 else None},
        })
    out.sort(key=lambda r: -r["mins"])
    return out[:10]


def build(cid, comp, margins_tbl):
    year = _season()
    src = comp.get("src")
    if src == "espn":  # NBA
        cur, prev = espn.nba_games(comp.get("days", 3))
    elif src == "esake":  # ελληνική Basket League
        cur, prev = esake.games(year), esake.games(year - 1)
    elif src == "bcl":  # Basketball Champions League (μόνο αποτελέσματα)
        cur, prev = bcl.games(), []
    else:
        cur = games(comp["feed"], year)
        prev = games(comp["feed"], year - 1)
    played_cur = [g for g in cur if g["played"]]
    played_prev = [g for g in prev if g["played"]]
    res = {"name": comp["name"], "sport": "basketball", "matches": [], "standings": None, "teams": [], "recent": []}
    if len(played_cur) + len(played_prev) < comp.get("min_games", 50):
        return res
    R = fit(played_cur, played_prev)
    if src == "espn":
        box = espn.nba_boxscores(played_cur + played_prev)
    elif src == "esake":
        box = esake.boxscores(played_cur + played_prev)
    elif src == "bcl":
        box = {}
    else:
        box = boxscores(comp["feed"], year, played_cur)
        # περσινή σεζόν (για τον έλεγχο των επιλογών παικτών): άλλοι κωδικοί αγώνων -> πρόθεμα "p"
        pbox = boxscores(comp["feed"], year - 1, played_prev, limit=40)
        played_prev = [dict(g, code=f"p{g['code']}") for g in played_prev]
        box = {**{f"p{k}": v for k, v in pbox.items()}, **box}
    # επιλογές παικτών: μοντέλο + εβδομαδιαίος έλεγχος (μόνο στατιστικά που κερδίζουν μένουν)
    PM = props.Model(played_prev + played_cur, box)
    check = sources._cached(f"props_check_{cid}.json", 24 * 7)
    if check is None:
        check = props.research(played_prev + played_cur, box)
        sources._save_cache(f"props_check_{cid}.json", check)
    res["props_check"] = check

    injuries = espn.nba_injuries() if comp.get("src") == "espn" else {}
    OUT = ("Out", "Doubtful")

    def absences(team):
        """Απόντες βασικοί: NBA από τη λίστα τραυματιών, EuroLeague/EuroCup όσοι έλειψαν στον τελευταίο αγώνα."""
        reg, tg = PM.regulars(team, datetime.now(timezone.utc).isoformat())
        out = []
        if comp.get("src") == "espn":
            for name, status, note in injuries.get(team, []):
                if name in reg:
                    out.append({"name": name, "status": status, "note": note, "mins": round(reg[name], 1),
                                "out": status in OUT})
        elif tg:
            for name, mins in reg.items():
                if name not in tg[-1]:
                    miss = 0
                    for x in reversed(tg):
                        if name in x:
                            break
                        miss += 1
                    out.append({"name": name, "status": f"έλειψε {miss} αγ." if miss > 1 else "έλειψε στον τελευταίο",
                                "note": "", "mins": round(mins, 1), "out": True})
        return sorted(out, key=lambda x: -x["mins"])

    def minutes_view(team, ab, before):
        """Αναμενόμενα λεπτά των βασικών με τις απουσίες (και αύξηση παραγωγής όπου ο έλεγχος την επιβεβαίωσε)."""
        mres = check.get("_minutes")
        if not mres or not ab:
            return []
        PM.beta, PM.gamma, PM.usage = mres["beta"], mres["gamma"], mres.get("usage", {})
        names_ab = [x["name"] for x in ab if x["out"]]
        plan = PM.minutes_plan(team, before, names_ab)
        mult = PM.usage_plan(team, before, names_ab)
        out = []
        for p, ex in plan.items():
            base = PM.exp_minutes(p, team, before)
            if base is None:
                continue
            up = {k: round(v - 1, 3) for k, v in mult.items() if k in ("pts", "reb", "ast") and v > 1.01}
            if ex >= 0.5 or up:
                out.append({"name": nice_name(p), "base": round(base, 1), "extra": round(ex, 1), "up": up})
        return sorted(out, key=lambda x: -x["extra"])[:6]

    def roster(team):
        last = sorted((x for x in played_cur if team in (x["home"], x["away"])), key=lambda x: x["date"])[-1:]
        b = box.get(str(last[0]["code"]), {}) if last else {}
        return [r[0] for r in b.get("home" if last and last[0]["home"] == team else "away", [])]

    def nice_name(n):
        if ", " in n:
            last, _, first = n.partition(", ")
            return f"{first.title()} {last.title()}".strip()
        return n

    events, remaining = sources.odds_api(comp["odds"], "h2h,spreads,totals") if comp.get("odds") else (None, None)
    res["credits"] = remaining
    now = datetime.now(timezone.utc)
    upcoming = [g for g in cur if not g["played"]
                and now < datetime.fromisoformat(g["date"].replace("Z", "+00:00")) < now + timedelta(days=comp.get("days", config.DAYS_AHEAD))]
    names_all = sorted({g["home"] for g in cur} | {g["away"] for g in cur})

    def team_games(t):
        return [g for g in played_cur if t in (g["home"], g["away"])]

    cur_t = [t for t in {x["home"] for x in played_cur} | {x["away"] for x in played_cur} if t in R["att"]]
    for g in sorted(upcoming, key=lambda g: g["date"]):
        h, a = g["home"], g["away"]
        if h not in R["att"] or a not in R["att"]:
            continue
        mh = R["h_avg"] * R["att"][h] * R["def"][a]
        ma = R["a_avg"] * R["att"][a] * R["def"][h]
        model_pts = [round(mh, 1), round(ma, 1)]
        books = dict(g.get("books") or {})
        for e in [] if books else events or []:
            if team_match(e["home"], [h]) and team_match(e["away"], [a]) and \
                    abs((datetime.fromisoformat(e["date"].replace("Z", "+00:00")) -
                         datetime.fromisoformat(g["date"].replace("Z", "+00:00"))).total_seconds()) < 36 * 3600:
                books = e["books"]
        sp, tt = _market_lines(books)
        market_pts = None
        if sp is not None and tt is not None:
            mm, mt = -sp, tt  # αγορά: διαφορά = -χάντικαπ γηπεδούχου, σύνολο = γραμμή συνόλου
            market_pts = [round((mt + mm) / 2, 1), round((mt - mm) / 2, 1)]
            w = MODEL_WEIGHT
            mh = w * mh + (1 - w) * market_pts[0]
            ma = w * ma + (1 - w) * market_pts[1]
        base_sp = sp if sp is not None else _half(-(mh - ma))
        base_tt = tt if tt is not None else _half(mh + ma)
        lines = {
            "spread": sorted({base_sp + d for d in (-4, -2, 0, 2, 4)}),
            "total": sorted({base_tt + d for d in (-6, -3, 0, 3, 6)}),
            "h": sorted({_half(mh) + d for d in (-3, 0, 3)}),
            "a": sorted({_half(ma) + d for d in (-3, 0, 3)}),
        }
        sels = selections(mh, ma, R["sd_margin"], R["sd_total"], lines)
        book_view = {}
        if market_pts:
            for s in selections(market_pts[0], market_pts[1], R["sd_margin"], R["sd_total"], lines):
                book_view[(s["key"], s["side"])] = (s["pw"], s["pp"])
        sels = markets.price(sels, books, book_view, margins_tbl)
        hg_, ag_ = team_games(h), team_games(a)
        # χωρίς αποδόσεις αγοράς το μοντέλο δεν ελέγχεται από κάπου -> το πολύ "μέτρια"
        conf = "υψηλή" if len(hg_) >= 5 and len(ag_) >= 5 and books else "μέτρια"

        def tstats(t, gl):
            if not gl:
                return {}
            pf = [x["hp"] if x["home"] == t else x["ap"] for x in gl]
            pa = [x["ap"] if x["home"] == t else x["hp"] for x in gl]
            form = "".join("W" if f > p else "L" for f, p in zip(pf, pa))[-5:]
            return {"p": len(gl), "ppg": round(sum(pf) / len(gl), 1), "oppg": round(sum(pa) / len(gl), 1),
                    "total": round(sum(f + p for f, p in zip(pf, pa)) / len(gl), 1), "form": form}
        hs, as_ = tstats(h, hg_), tstats(a, ag_)
        h_box = [(x["home"] if x2["home"] == h else x["away"]) for x2 in hg_ for x in [box.get(str(x2["code"]), {})] if x]
        a_box = [(x["home"] if x2["home"] == a else x["away"]) for x2 in ag_ for x in [box.get(str(x2["code"]), {})] if x]
        h2h = [{"date": x["date"][:10], "home": x["home_short"], "away": x["away_short"], "score": f"{x['hp']}-{x['ap']}"}
               for x in sorted(played_cur + played_prev, key=lambda x: x["date"], reverse=True)
               if {x["home"], x["away"]} == {h, a}][:6]
        ab_h, ab_a = absences(h), absences(a)
        out_h = [x["name"] for x in ab_h if x["out"]]
        out_a = [x["name"] for x in ab_a if x["out"]]
        # NBA: ενεργοί = όσοι έπαιξαν στον τελευταίο αγώνα + βασικοί που γύρισαν, χωρίς όσους είναι εκτός
        ros = lambda t, outl: [p for p in dict.fromkeys(roster(t) + list(PM.regulars(t, g["date"])[0])) if p not in outl]
        pk = props.picks(PM, check, ros(h, out_h), h, a, g["date"], absent=out_h) +             props.picks(PM, check, ros(a, out_a), a, h, g["date"], absent=out_a)
        for x in pk:
            x["player"] = nice_name(x["player"])
            x["team"] = g["home_short"] if x["team"] == h else g["away_short"]
            x["label"] = f"{x['player']}: {x['name']} {x['side']} {x['line']:g}"
        pk = sorted(pk, key=lambda x: -(x["p"] - x["p_avg"]))[:2]

        def pmodel(team, opp, outl):
            """Πρόβλεψη μοντέλου για κάθε βασικό (για έλεγχο οποιασδήποτε γραμμής στην καρτέλα Δελτίο)."""
            mres = check.get("_minutes") or {}
            PM.beta, PM.gamma, PM.usage = mres.get("beta", 0), mres.get("gamma", 0), mres.get("usage", {})
            plan = PM.minutes_plan(team, g["date"], outl) if outl and mres else {}
            mult = PM.usage_plan(team, g["date"], outl) if outl and mres else None
            out = []
            for p in ros(team, outl):
                pr = PM.predict(p, team, opp, g["date"], plan.get(p, 0.0), mult)
                if not pr:
                    continue
                P, mexp = pr
                out.append({"name": nice_name(p), "mins": round(mexp, 1), "extra": round(plan.get(p, 0.0), 1),
                            "mu": {k: round(v[0], 2) for k, v in P.items()}, "avg10": {k: round(v[1], 1) for k, v in P.items()}})
            return sorted(out, key=lambda x: -x["mins"])
        res["matches"].append({
            "id": f"{cid}-{g['code']}", "comp": cid, "sport": "basketball", "date": g["date"],
            "stage": f"Αγωνιστική {g['round']}" if g.get("round") else None,
            "home": g["home_short"] or h, "away": g["away_short"] or a, "home_full": h, "away_full": a,
            "home_crest": g["home_crest"], "away_crest": g["away_crest"],
            "xg": [round(mh, 1), round(ma, 1)], "model_xg": model_pts, "market_xg": market_pts,
            "home_stats": hs, "away_stats": as_, "h2h": h2h, "confidence": conf,
            "sd": [round(R["sd_margin"], 1), round(R["sd_total"], 1)],
            "markets": sels,
            "values": sorted([s for s in sels if s["value"]], key=lambda s: -s["ev"])[:3],
            "solid": markets.solid(sels), "top": predictions.top(sels), "has_odds": bool(books), "props": pk,
            "coef": {side: {"att": round(R["att"][t], 3), "def": round(R["def"][t], 3),
                            "ratt": 1 + sum(1 for x in cur_t if R["att"][x] > R["att"][t] + 1e-9),
                            "rdef": 1 + sum(1 for x in cur_t if R["def"][x] < R["def"][t] - 1e-9),
                            "of": len(cur_t), "pf": round(R["h_avg" if side == "home" else "a_avg"] * R["att"][t], 1)}
                     for side, t in (("home", h), ("away", a))},
            "dvp": ({"home": PM.defense_view(h, g["date"]), "away": PM.defense_view(a, g["date"])}
                    if PM.role_allowed else None),
            "pmodel": {"phi": {k: v["phi"] for k, v in check.items() if not k.startswith("_")},
                       "ok": [k for k, v in check.items() if not k.startswith("_") and v.get("ok")],
                       "home": pmodel(h, a, out_h), "away": pmodel(a, h, out_a)},
            "absences": {"home": [dict(x, name=nice_name(x["name"])) for x in ab_h],
                         "away": [dict(x, name=nice_name(x["name"])) for x in ab_a],
                         "src": "λίστα τραυματιών NBA (ESPN)" if comp.get("src") == "espn" else "βασικοί που έλειψαν στον τελευταίο αγώνα",
                         "minutes": {"home": minutes_view(h, ab_h, g["date"]), "away": minutes_view(a, ab_a, g["date"])}},
            "players": {"source": comp.get("players_src", "EuroLeague (επίσημα στατιστικά, τελευταίοι 10 αγώνες)"),
                        "home": players_for(h, [(0, x) for x in h_box], mh, hs.get("ppg")),
                        "away": players_for(a, [(0, x) for x in a_box], ma, as_.get("ppg"))},
        })
    # βαθμολογία και στατιστικά ομάδων
    table = {}
    for g in played_cur:
        for t, f, p in ((g["home"], g["hp"], g["ap"]), (g["away"], g["ap"], g["hp"])):
            r = table.setdefault(t, {"team": t, "p": 0, "w": 0, "l": 0, "gf": 0, "ga": 0, "f": ""})
            r["p"] += 1; r["gf"] += f; r["ga"] += p
            r["w" if f > p else "l"] += 1
            r["f"] += "W" if f > p else "L"
    rows = sorted(table.values(), key=lambda r: (-r["w"], -(r["gf"] - r["ga"])))
    for i, r in enumerate(rows, 1):
        r.update({"pos": i, "d": 0, "pts": r["w"], "form": r.pop("f")[-5:]})
    res["standings"] = [{"group": None, "rows": rows}] if rows else None
    res["teams"] = sorted(({"team": t, "att": round(R["att"][t], 3), "def": round(R["def"][t], 3),
                            "ppg": round(table[t]["gf"] / table[t]["p"], 1) if t in table else None,
                            "oppg": round(table[t]["ga"] / table[t]["p"], 1) if t in table else None,
                            "form": table.get(t, {}).get("form")}
                           for t in names_all if t in R["att"]), key=lambda x: -(x["att"] / x["def"]))
    res["model"] = {"sd_margin": round(R["sd_margin"], 1), "sd_total": round(R["sd_total"], 1), "games": R["n"],
                    "home_pts": round(R["h_avg"], 1), "away_pts": round(R["a_avg"], 1)}
    res["recent"] = [{"date": g["date"], "home": g["home"], "away": g["away"], "hg": g["hp"], "ag": g["ap"]}
                     for g in sorted(played_cur, key=lambda g: g["date"])[-40:]]
    return res
