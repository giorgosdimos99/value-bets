"""Κεντρικό script: python -m engine.run

1. Κατεβάζει αποτελέσματα/στατιστικά (football-data.co.uk) και υπολογίζει ισχύ ομάδων.
2. Παίρνει τους επόμενους αγώνες (football-data.org ή fixtures.csv) και αποδόσεις (The Odds API).
3. Υπολογίζει πιθανότητες, δίκαιες αποδόσεις, value και "λογικές επιλογές".
4. Γράφει το site/data/data.json και ενημερώνει το ιστορικό επιλογών.
"""
import json
from datetime import datetime, timedelta, timezone

from . import config, history, markets, model, names, slip, sources
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
    fx = sources.fdorg_matches(comp["fdorg"], days_back=0)
    if fx is not None:
        return [m for m in fx if m["status"] in ("SCHEDULED", "TIMED")]
    # χωρίς κλειδί: μόνο ό,τι υπάρχει στο fixtures.csv
    out = []
    for m in fx_csv:
        if comp["fdcouk"] and m["league"] == comp["fdcouk"] and m["date"]:
            if datetime.fromisoformat(m["date"]) > now - timedelta(hours=2):
                out.append({"id": f"{m['league']}-{m['date'][:10]}-{names.norm(m['home'])}",
                            "date": m["date"], "home": m["home"], "away": m["away"], "status": "SCHEDULED"})
    return out


def analyse(m, cid, ctx, books):
    ratings, leagues, fx_csv = ctx["ratings"], ctx["leagues"], ctx["fx_csv"]
    pool = ratings if cid == "CL" else {t: r for t, r in ratings.items() if r["league"] == "E0"}
    th = names.match(m["home"], list(pool)) or names.match(m.get("home_full"), list(pool))
    ta = names.match(m["away"], list(pool)) or names.match(m.get("away_full"), list(pool))
    default = {"league": None, "att": 0.9, "def": 1.1, "catt": 1.0, "cdef": 1.0, "cards": 1.0, "stats": {}}
    rh, ra = pool.get(th, default), pool.get(ta, default)
    cross = rh["league"] != ra["league"]
    lg = leagues.get(rh["league"]) or leagues.get("E0")
    lh, la, lc, lk = model.expected(rh, ra, lg, cross=cross)
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
    ref = history.find_referee(ref_name, ctx["refs"], "E0" if cid == "PL" else None)
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
        "has_odds": bool(books),
    }


def update_history(matches, results, slip_now=None, extra_results=()):
    path = config.DATA_OUT / "history.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"picks": []}
    hist.setdefault("slips", [])
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
    # δελτίο: κρατάμε την τελευταία πρόταση πριν ξεκινήσει ο πρώτος αγώνας του
    if slip_now:
        sig = [(l["match_id"], l["key"], l["side"]) for l in slip_now["legs"]]
        open_slips = [s for s in hist["slips"] if s.get("result") is None
                      and min(l["date"] for l in s["legs"]) > datetime.now(timezone.utc).isoformat()]
        if not any([(l["match_id"], l["key"], l["side"]) for l in s["legs"]] == sig for s in hist["slips"]):
            for s in open_slips:  # αντικαθίσταται από νεότερη πρόταση
                hist["slips"].remove(s)
            hist["slips"].append({**slip_now, "created": datetime.now(timezone.utc).isoformat(), "result": None})

    # εκκαθάριση με αποτελέσματα από όλα τα πρωταθλήματα (+ Champions League από football-data.org)
    allres = [r for rs in results.values() for r in rs] + [r for r in extra_results if r.get("hg") is not None]

    def settle(item):
        r = next((r for r in allres if _same_match(r, item, hours=30)), None)
        if r:
            item["score"] = f"{int(r['hg'])}-{int(r['ag'])}"
            return outcome(item["key"], item["side"], r)
        return None

    for p in hist["picks"]:
        if p["result"] is None:
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
           "margins": margins_tbl, "hist": hist_matches}
    cur_refs = {history.ref_key(m["ref"]) for m in results.get("E0", []) if m.get("ref")}
    out = {"updated": datetime.now(timezone.utc).isoformat(), "competitions": {}, "credits": None,
           "sources": {"fixtures": "football-data.org" if config.FOOTBALL_DATA_ORG_KEY else "football-data.co.uk",
                       "odds": bool(config.ODDS_API_KEY), "history_matches": len(hist_matches)},
           "margins": margins_tbl,
           "referees": sorted((v for (lg, k), v in refs.items() if lg == "E0" and k in cur_refs),
                              key=lambda v: -v["cards"])}
    all_matches = []
    for cid, comp in config.COMPETITIONS.items():
        fixtures = fixtures_for(cid, comp, fx_csv)
        events, remaining = sources.odds_api(comp["odds"])
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
        standings = sources.fdorg_standings(comp["fdorg"])
        teams = []
        if comp["fdcouk"]:
            teams = sorted(({"team": t, **r["stats"], "att": round(r["att"], 2), "def": round(r["def"], 2)}
                            for t, r in ratings.items() if r["league"] == comp["fdcouk"]),
                           key=lambda x: -(x["att"] / x["def"]))
        recent = sources.fdorg_matches(comp["fdorg"], days_back=10, days_ahead=0) or []
        out["competitions"][cid] = {
            "name": comp["name"], "matches": matches, "standings": standings, "teams": teams,
            "recent": [r for r in recent if r["status"] == "FINISHED"][-15:],
        }
        all_matches += matches
        print(f"  {cid}: {len(matches)} αγώνες, {sum(len(m['values']) for m in matches)} value")
    out["slip"] = slip.build(all_matches)
    fd_results = [r for c in out["competitions"].values() for r in c["recent"]]
    hist = update_history(all_matches, results, out["slip"], fd_results)
    settled = [p for p in hist["picks"] if p["result"] is not None]
    out["track"] = {
        "picks": len(settled),
        "profit": round(sum((p["odds"] - 1) if p["result"] == 1 else 0 if p["result"] == 0.5 else -1
                            for p in settled), 2),
    }
    (config.DATA_OUT / "data.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    bt = config.DATA_OUT / "backtest.json"
    try:
        stale = (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(bt.read_text(encoding="utf-8"))["created"])).days >= 7
    except (OSError, ValueError, KeyError):
        stale = True
    if stale:  # μία φορά την εβδομάδα
        from . import backtest
        backtest.main()
    print(f"✓ Έτοιμο: {config.DATA_OUT / 'data.json'}")


if __name__ == "__main__":
    main()
