"""Κεντρικό script: python -m engine.run

1. Κατεβάζει αποτελέσματα/στατιστικά (football-data.co.uk) και υπολογίζει ισχύ ομάδων.
2. Παίρνει τους επόμενους αγώνες (football-data.org ή fixtures.csv) και αποδόσεις (The Odds API).
3. Υπολογίζει πιθανότητες, δίκαιες αποδόσεις, value και "λογικές επιλογές".
4. Γράφει το site/data/data.json και ενημερώνει το ιστορικό επιλογών.
"""
import json
from datetime import datetime, timedelta, timezone

from . import basket, config, history, markets, model, names, players, predictions, slip, sources
from .settle import outcome


def build_ratings():
    ratings, leagues, results, hist = {}, {}, {}, []
    for code in config.RATING_LEAGUES:
        cur = sources.fdcouk_league(code, config.SEASON)
        prev = sources.fdcouk_league(code, config.PREV_SEASON)
        older = [m for s in config.HISTORY_SEASONS if s != config.PREV_SEASON
                 for m in sources.fdcouk_league(code, s)]
        r, lg = model.fit_league(code, cur, prev)
        if lg:
            ratings.update(r)
            leagues[code] = lg
            results[code] = cur
        hist += older + prev + cur
        print(f"  {code}: {len(cur)} αγώνες φέτος, {len(older) + len(prev)} ιστορικοί, {len(r)} ομάδες")
    return ratings, leagues, results, hist


def _same_match(a, b, hours=36):
    if not a.get("date") or not b.get("date"):
        return False
    da = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
    db = datetime.fromisoformat(b["date"].replace("Z", "+00:00"))
    if abs((da - db).total_seconds()) > hours * 3600:
        return False
    return names.norm(a["home"]) == names.norm(b["home"]) or (
        names.match(a["home"], [b["home"]]) and names.match(a["away"], [b["away"]]))


def fixtures_for(cid, comp, fx_csv):
    now = datetime.now(timezone.utc)
    fx = sources.fdorg_matches(comp["fdorg"], days_back=0) if comp["fdorg"] else None
    if fx is not None:
        return [m for m in fx if m["status"] in ("SCHEDULED", "TIMED")]
    if comp["odds"] and config.ODDS_API_KEY:  # πρόγραμμα από The Odds API (δωρεάν)
        horizon = now + timedelta(days=comp.get("days", config.DAYS_AHEAD))
        evs = [e for e in sources.odds_events(comp["odds"])
               if now < datetime.fromisoformat(e["date"].replace("Z", "+00:00")) < horizon]
        if evs:
            return [{"id": f"{cid}-{e['id']}", "date": e["date"], "home": e["home"], "away": e["away"],
                     "status": "SCHEDULED"} for e in evs]
    # χωρίς κλειδί: μόνο ό,τι υπάρχει στο fixtures.csv
    out = []
    for m in fx_csv:
        if comp["fdcouk"] and m["league"] == comp["fdcouk"] and m["date"]:
            if datetime.fromisoformat(m["date"]) > now - timedelta(hours=2):
                out.append({"id": f"{m['league']}-{m['date'][:10]}-{names.norm(m['home'])}",
                            "date": m["date"], "home": m["home"], "away": m["away"], "status": "SCHEDULED"})
    return out


PATTERN_KEYS = {"1": ("1X2", "1"), "X": ("1X2", "X"), "2": ("1X2", "2"),
                "Over": ("OU2.5", "Over"), "Under": ("OU2.5", "Under")}


def attach_patterns(matches):
    """Σημαδεύει επιλογές που ταιριάζουν σε μοτίβο της έρευνας (κέρδισε σε ανακάλυψη ΚΑΙ έλεγχο)."""
    try:
        pats = json.loads((config.DATA_OUT / "research.json").read_text(encoding="utf-8")).get("patterns", [])
    except (OSError, ValueError):
        return
    code_of = {cid: c["fdcouk"] for cid, c in config.COMPETITIONS.items()}
    for m in matches:
        for pt in pats:
            if code_of.get(m["comp"]) != pt["league"]:
                continue
            key, side = PATTERN_KEYS[pt["side"]]
            s = next((x for x in m["markets"] if x["key"] == key and x["side"] == side), None)
            odds = s and (s.get("best") or s.get("est"))
            if s and odds and pt["odds"][0] <= odds <= pt["odds"][1]:
                s["pattern"] = True
                d, t = pt["disc"], pt["test"]
                m.setdefault("patterns", []).append({
                    "key": key, "side": side, "label": s["label"], "p": s["p"], "odds": odds, "est": s.get("est"),
                    "text": f"{pt['name']}: {s['label']} με απόδοση {pt['odds'][0]}–{pt['odds'][1]} κέρδισε "
                            f"{d['roi'] * 100:+.0f}% σε {d['n']} αγώνες (2023-25) και {t['roi'] * 100:+.0f}% σε {t['n']} (2025/26). "
                            f"Μεγάλη αβεβαιότητα (±{t['ci'] * 100:.0f}%)."})


def standings_from(results):
    """Βαθμολογία από τα αποτελέσματα (για πρωταθλήματα που δεν έχει το football-data.org)."""
    if not results:
        return None
    t = {}
    for m in sorted(results, key=lambda r: r["date"]):
        for team, gf, ga in ((m["home"], m["hg"], m["ag"]), (m["away"], m["ag"], m["hg"])):
            r = t.setdefault(team, {"team": team, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0, "f": ""})
            r["p"] += 1; r["gf"] += int(gf); r["ga"] += int(ga)
            res = "W" if gf > ga else "D" if gf == ga else "L"
            r["w" if res == "W" else "d" if res == "D" else "l"] += 1
            r["pts"] += 3 if res == "W" else 1 if res == "D" else 0
            r["f"] += res
    rows = sorted(t.values(), key=lambda r: (-r["pts"], -(r["gf"] - r["ga"]), -r["gf"]))
    for i, r in enumerate(rows, 1):
        r["pos"] = i
        r["form"] = r.pop("f")[-5:]
    return [{"group": None, "rows": rows}]


DEFAULT_R = {"league": None, "att": 0.9, "def": 1.1, "catt": 1.0, "cdef": 1.0, "cards": 1.0, "stats": {}}


def _lookup(m, cid, ctx):
    ratings = ctx["ratings"]
    code = config.COMPETITIONS[cid]["fdcouk"]
    pool = {t: r for t, r in ratings.items() if r["league"] == code} if code else ratings
    th = names.match(m["home"], list(pool)) or names.match(m.get("home_full"), list(pool))
    ta = names.match(m["away"], list(pool)) or names.match(m.get("away_full"), list(pool))
    rh, ra = pool.get(th, DEFAULT_R), pool.get(ta, DEFAULT_R)
    lg = ctx["leagues"].get(rh["league"]) or ctx["leagues"].get("E0")
    return th, ta, rh, ra, rh["league"] != ra["league"], lg


def comp_goal_factor(cid, ctx):
    """Πόσο πιο "ανοιχτή" είναι μια διοργάνωση από ό,τι προβλέπει το μοντέλο με βάση τα εγχώρια πρωταθλήματα.

    Συγκρίνει τα πραγματικά γκολ των τελευταίων 3 σεζόν της διοργάνωσης με την πρόβλεψη του μοντέλου
    για τους ίδιους αγώνες (πρόσφατες σεζόν μετράνε περισσότερο, συρρίκνωση προς το 1).
    """
    if cid != "CL":
        return 1.0, None
    now = datetime.now(timezone.utc)
    cur = now.year if now.month >= 7 else now.year - 1
    act = pred = ws = 0.0
    n = 0
    for season, w in ((cur, 1.0), (cur - 1, 0.6), (cur - 2, 0.35)):
        for m in sources.fdorg_season("CL", season):
            th, ta, rh, ra, cross, lg = _lookup(m, cid, ctx)
            if not (th and ta):
                continue
            lh, la, _, _ = model.expected(rh, ra, lg, cross=cross)
            act += w * (m["hg"] + m["ag"]); pred += w * (lh + la); ws += w; n += 1
    if not n:
        return 1.0, None
    P = 40 * pred / ws  # ~40 "μέσοι" αγώνες χωρίς απόκλιση
    k = (act + P) / (pred + P)
    return round(k, 3), {"matches": n, "actual_goals": round(act / ws, 2), "model_goals": round(pred / ws, 2)}


def analyse(m, cid, ctx, books):
    fx_csv = ctx["fx_csv"]
    th, ta, rh, ra, cross, lg = _lookup(m, cid, ctx)
    lh, la, lc, lk = model.expected(rh, ra, lg, cross=cross)
    k = ctx["goal_factor"].get(cid, 1.0)
    lh, la = lh * k, la * k
    model_xg = [round(lh, 2), round(la, 2)]
    market_xg = None
    x12, ou = markets.market_view(books)
    if x12:
        mh, ma = model.implied_lambdas(x12["1"], x12["2"], ou["Over"] if ou else None)
        market_xg = [round(mh, 2), round(ma, 2)]
        # λιγότερο βάρος στο μοντέλο όταν δεν ξέρουμε καλά τις ομάδες
        w = config.MODEL_WEIGHT * (1.0 if th and ta and not cross else 0.6 if th and ta else 0.2)
        lh = w * lh + (1 - w) * mh
        la = w * la + (1 - w) * ma

    # διαιτητής: football-data.org ή fixtures.csv -> ιστορικό καρτών του
    ref_name = m.get("referee") or next((f.get("ref") for f in fx_csv if f.get("ref") and _same_match(f, m)), None)
    ref = history.find_referee(ref_name, ctx["refs"], config.COMPETITIONS[cid]["fdcouk"])
    if ref:
        lk *= ref["factor"]

    # πώς "βλέπει" ο στοιχηματικός τον αγώνα (για εκτίμηση αποδόσεων σε αγορές χωρίς τιμές)
    book_view = {}
    if market_xg:
        for s in markets.selections(model.score_matrix(*market_xg), lc, lk):
            book_view[(s["key"], s["side"])] = (s["pw"], s["pp"])

    M = model.score_matrix(lh, la)
    sels = markets.price(markets.selections(M, lc, lk), books, book_view, ctx["margins"])
    scores = sorted(((i, j, M[i][j]) for i in range(6) for j in range(6)), key=lambda x: -x[2])[:6]
    confidence = "υψηλή" if th and ta and not cross else "μέτρια" if th and ta else "χαμηλή"
    return {
        "id": m["id"], "comp": cid, "date": m["date"], "stage": m.get("stage"),
        "home": m["home"], "away": m["away"],
        "home_crest": m.get("home_crest"), "away_crest": m.get("away_crest"),
        "home_stats": rh.get("stats"), "away_stats": ra.get("stats"),
        "home_split": rh.get("stats_home"), "away_split": ra.get("stats_away"),
        "h2h": history.h2h(th or m["home"], ta or m["away"], ctx["hist"]),
        "xg": [round(lh, 2), round(la, 2)], "model_xg": model_xg, "market_xg": market_xg, "corners": round(lc, 1), "cards": round(lk, 1),
        "referee": ref_name, "ref_stats": ref, "confidence": confidence,
        "ratings": {"home": [round(rh["att"], 2), round(rh["def"], 2)], "away": [round(ra["att"], 2), round(ra["def"], 2)]},
        "scores": [{"s": f"{i}-{j}", "p": round(p, 3)} for i, j, p in scores],
        "markets": sels,
        "values": sorted([s for s in sels if s["value"]], key=lambda s: -s["ev"])[:3],
        "solid": markets.solid(sels),
        "top": predictions.top(sels),
        "has_odds": bool(books),
    }


def update_history(matches, results, slip_now=None, extra_results=()):
    path = config.DATA_OUT / "history.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"picks": []}
    hist.setdefault("slips", [])
    hist.setdefault("preds", [])
    # κύρια πρόβλεψη κάθε αγώνα: ενημερώνεται μέχρι να ξεκινήσει ο αγώνας, μετά "κλειδώνει"
    now_iso0 = datetime.now(timezone.utc).isoformat()
    by_id = {p["match_id"]: p for p in hist["preds"]}
    for m in matches:
        if not m.get("top") or m["date"].replace("Z", "+00:00") <= now_iso0:
            continue
        t = m["top"][0]
        old = by_id.get(m["id"])
        if old and old.get("result") is not None:
            continue
        row = {"match_id": m["id"], "comp": m["comp"], "date": m["date"], "home": m["home"], "away": m["away"],
               "key": t["key"], "side": t["side"], "label": t["label"], "group": t["group"],
               "p": t["p"], "est": t["est"], "result": None}
        if old:
            old.update(row)
        else:
            hist["preds"].append(row)
    known = {(p["match_id"], p["key"], p["side"]) for p in hist["picks"]}
    for m in matches:
        for s in m["values"]:
            k = (m["id"], s["key"], s["side"])
            if k not in known:
                hist["picks"].append({
                    "match_id": m["id"], "comp": m["comp"], "date": m["date"], "home": m["home"], "away": m["away"],
                    "key": s["key"], "side": s["side"], "label": s["label"], "group": s["group"],
                    "p": s["p"], "odds": s["best"], "book": s["book"], "ev": s["ev"], "result": None,
                })
            else:  # ενημέρωση απόδοσης μέχρι την έναρξη (κρατάμε την τελευταία πριν το ματς)
                for p in hist["picks"]:
                    if (p["match_id"], p["key"], p["side"]) == k and p["result"] is None:
                        p["closing"] = s["best"]
    # δελτία ανά ημέρα: κρατάμε την τελευταία πρόταση (ανά ημέρα και είδος) πριν ξεκινήσει ο πρώτος αγώνας
    now_iso = datetime.now(timezone.utc).isoformat()
    for day in slip_now or []:
        for kind in ("simple", "extreme"):
            s_new = day.get(kind)
            if not s_new:
                continue
            sig = [(l["match_id"], l["key"], l["side"]) for l in s_new["legs"]]
            if any(s.get("day") == day["day"] and s.get("kind", "simple") == kind
                   and [(l["match_id"], l["key"], l["side"]) for l in s["legs"]] == sig for s in hist["slips"]):
                continue
            for s in [s for s in hist["slips"] if s.get("day") == day["day"] and s.get("kind", "simple") == kind
                      and s.get("result") is None and min(l["date"] for l in s["legs"]) > now_iso]:
                hist["slips"].remove(s)  # αντικαθίσταται από νεότερη πρόταση
            if min(l["date"] for l in s_new["legs"]) > now_iso:
                hist["slips"].append({**s_new, "day": day["day"], "kind": kind, "created": now_iso, "result": None})

    # εκκαθάριση με αποτελέσματα από όλα τα πρωταθλήματα (+ Champions League από football-data.org)
    allres = [r for rs in results.values() for r in rs] + [r for r in extra_results if r.get("hg") is not None]

    def settle(item):
        r = next((r for r in allres if _same_match(r, item, hours=30)), None)
        if r:
            item["score"] = f"{int(r['hg'])}-{int(r['ag'])}"
            return outcome(item["key"], item["side"], r)
        return None

    for p in hist["picks"] + hist["preds"]:
        if p["result"] is None and p["date"].replace("Z", "+00:00") < now_iso0:
            p["result"] = settle(p)
    for s in hist["slips"]:
        if s["result"] is not None:
            continue
        for l in s["legs"]:
            if l.get("result") is None:
                l["result"] = settle(l)
        res = [l.get("result") for l in s["legs"]]
        if 0 in res:
            s["result"] = 0
        elif all(x is not None for x in res):
            s["result"] = 1
    path.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    return hist


def main():
    config.DATA_OUT.mkdir(parents=True, exist_ok=True)
    print("• Ισχύς ομάδων")
    ratings, leagues, results, hist_matches = build_ratings()
    if not results.get("E0") or not any(r["league"] == "E0" for r in ratings.values()):
        raise SystemExit("✗ Δεν κατέβηκαν τα δεδομένα της Premier League. Δεν ενημερώνω τίποτα.")
    print("• Διαιτητές & γκανιότ στοιχηματικών")
    refs = history.referees(hist_matches)
    margins_tbl = history.margins(hist_matches)
    print(f"  {len(refs)} διαιτητές, γκανιότ 1X2 {margins_tbl['1X2']['overround']} ({margins_tbl['1X2']['n']} αγώνες)")
    print("• Επόμενοι αγώνες & αποδόσεις")
    fx_csv = sources.fdcouk_fixtures()
    ctx = {"ratings": ratings, "leagues": leagues, "fx_csv": fx_csv, "refs": refs,
           "margins": margins_tbl, "hist": hist_matches, "goal_factor": {}}
    goal_info = {}
    for cid in config.COMPETITIONS:
        ctx["goal_factor"][cid], goal_info[cid] = comp_goal_factor(cid, ctx)
    if goal_info.get("CL"):
        gi = goal_info["CL"]
        print(f"  Champions League: πραγματικά {gi['actual_goals']} γκολ/αγώνα vs μοντέλο {gi['model_goals']}"
              f" ({gi['matches']} αγώνες) -> διόρθωση ×{ctx['goal_factor']['CL']}")
    cur_refs = {history.ref_key(m["ref"]) for m in results.get("E0", []) if m.get("ref")}
    out = {"updated": datetime.now(timezone.utc).isoformat(), "competitions": {}, "credits": None,
           "sources": {"fixtures": "football-data.org" if config.FOOTBALL_DATA_ORG_KEY else "football-data.co.uk",
                       "odds": bool(config.ODDS_API_KEY), "history_matches": len(hist_matches)},
           "margins": margins_tbl,
           "goal_factor": {c: {"factor": ctx["goal_factor"][c], **(goal_info[c] or {})} for c in goal_info},
           "referees": sorted((v for (lg, k), v in refs.items() if lg == "E0" and k in cur_refs),
                              key=lambda v: -v["cards"])}
    all_matches = []
    for cid, comp in config.COMPETITIONS.items():
        fixtures = fixtures_for(cid, comp, fx_csv)
        # πληρωμένες αποδόσεις (credits) μόνο για τις βασικές διοργανώσεις
        events, remaining = (sources.odds_api(comp["odds"], comp.get("odds_markets"))
                             if comp.get("paid_odds") else (None, None))
        if remaining is not None:
            out["credits"] = remaining
        matches = []
        for m in sorted(fixtures, key=lambda x: x["date"])[:30]:
            books = {}
            for f in fx_csv:
                if _same_match(f, m):
                    books.update(f["books"])
            for e in events or []:
                if _same_match(e, m):
                    for b, mk in e["books"].items():
                        books.setdefault(b, {}).update(mk)
            matches.append(analyse(m, cid, ctx, books))
        if cid == "PL":
            players.attach_fpl(matches, ctx)
        standings = sources.fdorg_standings(comp["fdorg"]) if comp["fdorg"] else standings_from(results.get(comp["fdcouk"], []))
        teams = []
        if comp["fdcouk"]:
            teams = sorted(({"team": t, **r["stats"], "att": round(r["att"], 2), "def": round(r["def"], 2)}
                            for t, r in ratings.items() if r["league"] == comp["fdcouk"]),
                           key=lambda x: -(x["att"] / x["def"]))
        if comp["fdorg"]:
            recent = [r for r in sources.fdorg_matches(comp["fdorg"], days_back=10, days_ahead=0) or []
                      if r["status"] == "FINISHED"]
        else:
            recent = sorted(results.get(comp["fdcouk"], []), key=lambda r: r["date"])
        out["competitions"][cid] = {
            "name": comp["name"], "sport": "football", "matches": matches, "standings": standings, "teams": teams,
            "recent": recent[-15:],
        }
        all_matches += matches
        print(f"  {cid}: {len(matches)} αγώνες, {sum(len(m['values']) for m in matches)} value")

    print("• Μπάσκετ")
    for cid, comp in config.BASKET.items():
        bres = basket.build(cid, comp, ctx["margins"])
        if remaining_b := bres.pop("credits", None):
            out["credits"] = remaining_b
        out["competitions"][cid] = bres
        all_matches += bres["matches"]
        print(f"  {cid}: {len(bres['matches'])} αγώνες, {sum(len(m['values']) for m in bres['matches'])} value")

    predictions.annotate(all_matches)
    attach_patterns(all_matches)
    out["slips"] = slip.build_daily(all_matches)
    out["slip"] = (out["slips"][0]["simple"] if out["slips"] else None)
    fd_results = [r for c in out["competitions"].values() for r in c["recent"]]
    hist = update_history(all_matches, results, out["slips"], fd_results)
    settled = [p for p in hist["picks"] if p["result"] is not None]
    out["track"] = {
        "picks": len(settled),
        "profit": round(sum((p["odds"] - 1) if p["result"] == 1 else 0 if p["result"] == 0.5 else -1
                            for p in settled), 2),
    }
    # μικρότερο αρχείο για το κινητό: χωρίς τις αποδόσεις κάθε εταιρείας και χωρίς ακραίες επιλογές
    for c in out["competitions"].values():
        for m in c["matches"]:
            m["markets"] = [{k: v for k, v in s.items() if k not in ("odds", "pw") and v is not None and v is not False}
                            for s in m["markets"] if 0.02 <= s["p"] <= 0.98 or s["value"]]
            m["solid"] = m["solid"][:2]
            for s in m["values"] + m["solid"]:
                s.pop("odds", None)
    (config.DATA_OUT / "data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    bt = config.DATA_OUT / "backtest.json"
    try:
        stale = (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(bt.read_text(encoding="utf-8"))["created"])).days >= 7
    except (OSError, ValueError, KeyError):
        stale = True
    if stale:  # μία φορά την εβδομάδα
        from . import backtest
        backtest.main()
    rs = config.DATA_OUT / "research.json"
    try:
        stale_r = (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(rs.read_text(encoding="utf-8"))["created"])).days >= 7
    except (OSError, ValueError, KeyError):
        stale_r = True
    if stale_r:  # η έρευνα ξανατρέχει κάθε εβδομάδα (οι προβλέψεις των παλιών αγώνων μένουν στην cache)
        from . import research
        research.main()
    print(f"✓ Έτοιμο: {config.DATA_OUT / 'data.json'}")


if __name__ == "__main__":
    main()
