"""Εθνικές ομάδες ποδοσφαίρου.

- Ισχύς: όλα τα επίσημα αποτελέσματα εθνικών (github.com/martj42/international_results, δωρεάν),
  μοντέλο Poisson επίθεση/άμυνα με πλεονέκτημα έδρας μόνο όταν δεν είναι ουδέτερο γήπεδο.
  Τα πρόσφατα μετράνε περισσότερο, τα φιλικά λιγότερο.
- Πρόγραμμα + αποδόσεις DraftKings: ESPN (Nations League, προκριματικά Μουντιάλ/Euro). Χωρίς φιλικά.
- Έλεγχος: το μοντέλο ξαναπροβλέπει τους αγώνες των τελευταίων 12 μηνών μόνο με ό,τι ήξερε πριν.
"""
import csv
import io
import math
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

from . import config, espn, markets, model, predictions, sources

RESULTS = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
LEAGUES = {  # ESPN slug -> όνομα. Μόνο επίσημες ευρωπαϊκές διοργανώσεις (όχι φιλικά)
    "uefa.nations": "Nations League",
    "fifa.worldq.uefa": "Προκριματικά Μουντιάλ (Ευρώπη)",
    "uefa.euroq": "Προκριματικά Euro",
}
# ρυθμίσεις από έλεγχο σε 1.022 αγώνες (τελευταίοι 12 μήνες, μόνο με παλαιότερα δεδομένα):
# log-loss 0.881 (σταθερές συχνότητες: 1.051), σωστό φαβορί 60%
HALF_LIFE = 900      # μέρες
FRIENDLY_W = 1.0     # τα φιλικά μετράνε το ίδιο (καλύτερο αποτέλεσμα στον έλεγχο)
PRIOR = 0.5          # "εικονικοί" αγώνες προς τον μέσο όρο
YEARS = 5
ALIAS = {"usa": "united states", "czechia": "czech republic", "turkiye": "turkey", "korea republic": "south korea",
         "korea dpr": "north korea", "ir iran": "iran", "cote d'ivoire": "ivory coast", "cabo verde": "cape verde",
         "bosnia-herzegovina": "bosnia and herzegovina", "chinese taipei": "taiwan", "kyrgyz republic": "kyrgyzstan",
         "republic of ireland": "republic of ireland", "ireland": "republic of ireland", "curacao": "curacao",
         "st. lucia": "saint lucia", "st. kitts and nevis": "saint kitts and nevis",
         "st. vincent and the grenadines": "saint vincent and the grenadines", "sint maarten": "sint maarten",
         "us virgin islands": "united states virgin islands", "trinidad & tobago": "trinidad and tobago",
         "antigua & barbuda": "antigua and barbuda", "dr congo": "dr congo", "congo dr": "dr congo",
         "macedonia": "north macedonia", "the gambia": "gambia", "eswatini": "eswatini", "swaziland": "eswatini"}


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"\s+", " ", s)
    return ALIAS.get(s, s)


def results():
    hit = sources._cached("intl_results.json", 24)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get(RESULTS)
    except Exception as e:
        print(f"  ! αποτελέσματα εθνικών: {e}")
        return sources._cached("intl_results.json", 0, stale_ok=True) or []
    start = (date.today() - timedelta(days=365 * (YEARS + 1))).isoformat()
    out = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        if r["date"] < start or r["home_score"] in ("", "NA"):
            continue
        out.append([r["date"], r["home_team"], r["away_team"], int(r["home_score"]), int(r["away_score"]),
                    r["tournament"], r["neutral"] == "TRUE"])
    sources._save_cache("intl_results.json", out)
    return out


def fit(rows, upto):
    """Poisson: λ_γηπ = μ·att_h·def_a·(H αν όχι ουδέτερο), λ_φιλ = μ·att_a·def_h."""
    t0 = datetime.fromisoformat(upto)
    ms = []
    for d, h, a, hg, ag, tour, neutral in rows:
        if d >= upto:
            continue
        age = (t0 - datetime.fromisoformat(d)).days
        if age > 365 * YEARS:
            continue
        w = 0.5 ** (age / HALF_LIFE) * (FRIENDLY_W if tour == "Friendly" else 1.0)
        ms.append((norm(h), norm(a), hg, ag, neutral, w))
    teams = {t for m in ms for t in m[:2]}
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    W = sum(m[5] for m in ms)
    mu = sum(m[5] * (m[2] + m[3]) for m in ms) / (2 * W)
    H = 1.3
    for _ in range(40):
        num = {t: PRIOR * mu for t in teams}
        den = {t: PRIOR * mu for t in teams}
        for h, a, hg, ag, neu, w in ms:
            hf = 1.0 if neu else H
            num[h] += w * hg; den[h] += w * mu * dfn[a] * hf
            num[a] += w * ag; den[a] += w * mu * dfn[h]
        att = {t: num[t] / den[t] for t in teams}
        num = {t: PRIOR * mu for t in teams}
        den = {t: PRIOR * mu for t in teams}
        for h, a, hg, ag, neu, w in ms:
            hf = 1.0 if neu else H
            num[a] += w * hg; den[a] += w * mu * att[h] * hf
            num[h] += w * ag; den[h] += w * mu * att[a]
        dfn = {t: num[t] / den[t] for t in teams}
        hn = sum(w * hg for h, a, hg, ag, neu, w in ms if not neu)
        hd = sum(w * mu * att[h] * dfn[a] for h, a, hg, ag, neu, w in ms if not neu)
        H = hn / hd if hd else 1.0
        g = math.exp(sum(math.log(v) for v in att.values()) / len(att))
        att = {t: v / g for t, v in att.items()}
        mu *= g
    n = {}
    for m in ms:
        n[m[0]] = n.get(m[0], 0) + 1
        n[m[1]] = n.get(m[1], 0) + 1
    return {"att": att, "def": dfn, "mu": mu, "H": H, "n": n}


def lambdas(R, h, a, neutral):
    lh = R["mu"] * R["att"][h] * R["def"][a] * (1.0 if neutral else R["H"])
    la = R["mu"] * R["att"][a] * R["def"][h]
    return lh, la


def _probs(lh, la):
    M = model.score_matrix(lh, la)
    n = len(M)
    p1 = sum(M[i][j] for i in range(n) for j in range(n) if i > j)
    p2 = sum(M[i][j] for i in range(n) for j in range(n) if i < j)
    return M, p1, 1 - p1 - p2, p2


def validate(rows):
    """Αγώνες των τελευταίων 12 μηνών, πρόβλεψη μόνο με τα προηγούμενα (ανανέωση ισχύος κάθε 3 μήνες)."""
    today = date.today()
    ll = ll0 = 0.0
    n = hit = 0
    cal = {}
    for q in range(4, 0, -1):
        a = (today - timedelta(days=91 * q)).isoformat()
        b = (today - timedelta(days=91 * (q - 1))).isoformat()
        R = fit(rows, a)
        for d, h, aw, hg, ag, tour, neu in rows:
            if not (a <= d < b):
                continue
            h, aw = norm(h), norm(aw)
            if R["n"].get(h, 0) < 8 or R["n"].get(aw, 0) < 8:
                continue
            _, p1, px, p2 = _probs(*lambdas(R, h, aw, neu))
            res = 0 if hg > ag else 1 if hg == ag else 2
            p = (p1, px, p2)
            ll -= math.log(max(p[res], 1e-9))
            ll0 -= math.log((0.47, 0.23, 0.30)[res])  # σταθερές συχνότητες (γηπ./ισοπ./φιλοξ.)
            n += 1
            best = max(range(3), key=lambda i: p[i])
            hit += best == res
            bk = min(int(p[best] * 10), 9)
            c = cal.setdefault(bk, [0, 0.0, 0])
            c[0] += 1; c[1] += p[best]; c[2] += best == res
    if not n:
        return None
    return {"matches": n, "logloss": round(ll / n, 4), "logloss_base": round(ll0 / n, 4), "hit": round(hit / n, 3),
            "calibration": [{"bucket": f"{k * 10}-{k * 10 + 10}%", "n": v[0], "pred": round(v[1] / v[0], 3),
                             "actual": round(v[2] / v[0], 3)} for k, v in sorted(cal.items()) if v[0] >= 20]}


def _form(rows, team):
    t = norm(team)
    out = []
    for d, h, a, hg, ag, tour, neu in sorted(rows):
        if norm(h) == t:
            out.append("W" if hg > ag else "D" if hg == ag else "L")
        elif norm(a) == t:
            out.append("W" if ag > hg else "D" if hg == ag else "L")
    return "".join(out[-5:])


def build(margins_tbl):
    """Επιστρέφει {cid: διοργάνωση} για όσες διοργανώσεις εθνικών έχουν αγώνες τις επόμενες μέρες."""
    rows = results()
    if len(rows) < 1000:
        return {}, None
    R = fit(rows, (date.today() + timedelta(days=1)).isoformat())
    check = sources._cached("intl_check.json", 24 * 7)
    if check is None:
        check = validate(rows)
        sources._save_cache("intl_check.json", check)
    ranked = sorted(R["att"], key=lambda t: -(R["att"][t] / R["def"][t]))
    rank = {t: i + 1 for i, t in enumerate(t for t in ranked if R["n"].get(t, 0) >= 8)}
    now = datetime.now(timezone.utc)
    today = now.date()
    out, all_results = {}, {}
    for slug, cname in LEAGUES.items():
        gl = espn.days(f"soccer/{slug}", today, today + timedelta(days=config.DAYS_AHEAD), draw=True)
        past = espn.days(f"soccer/{slug}", today - timedelta(days=10), today, draw=True)
        cid = "N-" + slug.split(".")[-1].upper() if slug != "uefa.nations" else "UNL"
        cid = {"fifa.friendly": "FRI", "concacaf.nations.league": "CNL"}.get(slug, cid)
        # αποτελέσματα για την εκκαθάριση, ακόμα κι αν η διοργάνωση δεν έχει άλλους αγώνες τις επόμενες μέρες
        all_results[cid] = [{"id": f"{cid}-{g['id']}", "date": g["date"], "home": g["home"], "away": g["away"],
                             "hg": g["hp"], "ag": g["ap"]} for g in past if g["played"] and g["hp"] is not None]
        matches = []
        for g in sorted(gl, key=lambda g: g["date"]):
            if g["played"] or g["state"] != "STATUS_SCHEDULED":
                continue
            if datetime.fromisoformat(g["date"].replace("Z", "+00:00")) < now:
                continue
            h, a = norm(g["home"]), norm(g["away"])
            known = R["n"].get(h, 0) >= 8 and R["n"].get(a, 0) >= 8
            books = g["books"]
            if not known and not books:
                continue
            m = analyse(g, cid, R, h, a, known, books, margins_tbl, rows, rank)
            if m:
                matches.append(m)
        if not matches:
            continue
        recent = [{"id": f"{cid}-{g['id']}", "date": g["date"], "home": g["home"], "away": g["away"], "hg": g["hp"], "ag": g["ap"]}
                  for g in sorted(past, key=lambda g: g["date"]) if g["played"] and g["hp"] is not None]
        out[cid] = {"name": cname, "sport": "football", "national": True, "matches": matches, "standings": None,
                    "teams": [], "recent": recent[-40:]}
    info = {"teams": len(rank), "matches_used": len(rows), "home_adv": round(R["H"], 3), "goals": round(R["mu"], 3),
            "check": check, "_results": all_results}
    return out, info


def analyse(g, cid, R, h, a, known, books, margins_tbl, rows, rank):
    model_xg = None
    if known:
        lh, la = lambdas(R, h, a, g["neutral"])
        model_xg = [round(lh, 2), round(la, 2)]
    market_xg = None
    x12, ou = markets.market_view(books)
    if x12:
        mh, ma = model.implied_lambdas(x12["1"], x12["2"], ou["Over"] if ou else None)
        market_xg = [round(mh, 2), round(ma, 2)]
        if known:  # ίδιος κανόνας με τα πρωταθλήματα: η αγορά κυριαρχεί
            w = config.MODEL_WEIGHT
            lh, la = w * lh + (1 - w) * mh, w * la + (1 - w) * ma
        else:
            lh, la = mh, ma
    elif not known:
        return None
    M, p1, px, p2 = _probs(lh, la)
    book_view = {}
    if market_xg:
        for s in markets.selections(model.score_matrix(*market_xg), None, None):
            book_view[(s["key"], s["side"])] = (s["pw"], s["pp"])
    raw = markets.selections(M, None, None)
    if x12 and (config.MODEL_WEIGHT == 0 or not known):  # 1/Χ/2 και O/U 2.5 = η αγορά χωρίς γκανιότ (όχι προσέγγιση Poisson)
        anchor = {("1X2", "1"): x12["1"], ("1X2", "X"): x12["X"], ("1X2", "2"): x12["2"],
                  ("DC", "1X"): x12["1"] + x12["X"], ("DC", "X2"): x12["X"] + x12["2"], ("DC", "12"): x12["1"] + x12["2"]}
        if ou:
            anchor.update({("OU2.5", "Over"): ou["Over"], ("OU2.5", "Under"): ou["Under"]})
        for s_ in raw:
            if (s_["key"], s_["side"]) in anchor:
                s_["pw"] = anchor[(s_["key"], s_["side"])]
        p1, px, p2 = x12["1"], x12["X"], x12["2"]
    sels = markets.price(raw, books, book_view, margins_tbl)
    scores = sorted(((i, j, M[i][j]) for i in range(6) for j in range(6)), key=lambda x: -x[2])[:6]

    def lvl(pw, pl):
        return ("πολύ εύκολο" if pw >= 0.65 else "εύκολο" if pw >= 0.5 else "ισορροπημένο" if pw >= pl - 0.08
                else "δύσκολο" if pw >= 0.2 else "πολύ δύσκολο")
    form_h, form_a = _form(rows, g["home"]), _form(rows, g["away"])
    diff = {"p": [round(p1, 3), round(px, 3), round(p2, 3)],
            "home": {"level": lvl(p1, p2), "rank": rank.get(h), "of": len(rank), "league": "εθνικές", "form": form_h},
            "away": {"level": lvl(p2, p1), "rank": rank.get(a), "of": len(rank), "league": "εθνικές", "form": form_a}}
    h2h = [{"date": d, "home": hh, "away": aa, "score": f"{hg}-{ag}"}
           for d, hh, aa, hg, ag, tour, neu in sorted(rows, reverse=True) if {norm(hh), norm(aa)} == {h, a}][:6]
    return {
        "id": f"{cid}-{g['id']}", "comp": cid, "date": g["date"], "national": True,
        "stage": "ουδέτερο γήπεδο" if g["neutral"] else None,
        "home": g["home"], "away": g["away"], "home_crest": g["home_crest"], "away_crest": g["away_crest"],
        "home_stats": {"form": form_h}, "away_stats": {"form": form_a},
        "h2h": h2h, "xg": [round(lh, 2), round(la, 2)], "model_xg": model_xg, "market_xg": market_xg,
        "confidence": "υψηλή" if known and books else "μέτρια" if known or books else "χαμηλή",
        "scores": [{"s": f"{i}-{j}", "p": round(p, 3)} for i, j, p in scores],
        "markets": sels,
        "values": sorted([s for s in sels if s["value"]], key=lambda s: -s["ev"])[:3],
        "solid": markets.solid(sels), "top": predictions.top(sels),
        "stat_top": [], "stat_edges": [], "difficulty": diff, "has_odds": bool(books),
    }
