"""Λήψη δεδομένων από τις δωρεάν πηγές."""
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config

UA = {"User-Agent": "value-bets/1.0 (personal use)"}


def _get(url, headers=None, timeout=40):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers)


def _cached(name, max_age_h, stale_ok=False):
    # η ώρα λήψης γράφεται μέσα στο αρχείο (το mtime αλλάζει σε κάθε git checkout)
    p = config.CACHE / name
    if not p.exists():
        return None
    try:
        box = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    if not isinstance(box, dict) or "_at" not in box:
        return None
    if stale_ok or time.time() - box["_at"] < max_age_h * 3600:
        return box["data"]
    return None


def _save_cache(name, obj):
    config.CACHE.mkdir(parents=True, exist_ok=True)
    (config.CACHE / name).write_text(json.dumps({"_at": time.time(), "data": obj}, ensure_ascii=False), encoding="utf-8")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(d, t):
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            # τα ωράρια του football-data.co.uk είναι ώρα Αγγλίας· αρκεί ως προσέγγιση
            return datetime.strptime(f"{d} {t or '15:00'}", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---------------- football-data.co.uk (χωρίς κλειδί) ----------------

def fdcouk_league(code, season):
    """Ολοκληρωμένοι αγώνες ενός πρωταθλήματος με γκολ, xG, σουτ, κόρνερ, κάρτες, αποδόσεις."""
    key = f"fdcouk_{code}_{season}.json"
    hit = _cached(key, 6 if season == config.SEASON else 24 * 30)
    if hit is not None:
        return hit
    url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
    try:
        raw, _ = _get(url)
    except Exception as e:
        print(f"  ! {code} {season}: {e}")
        return []
    rows = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))):
        if not r.get("HomeTeam") or r.get("FTHG") in (None, ""):
            continue
        dt = _parse_date(r.get("Date"), r.get("Time"))
        rows.append({
            "league": code, "date": dt.isoformat() if dt else None,
            "home": r["HomeTeam"].strip(), "away": r["AwayTeam"].strip(),
            "hg": _num(r["FTHG"]), "ag": _num(r["FTAG"]),
            "hxg": _num(r.get("HxG")), "axg": _num(r.get("AxG")),
            "hs": _num(r.get("HS")), "as": _num(r.get("AS")),
            "hst": _num(r.get("HST")), "ast": _num(r.get("AST")),
            "hc": _num(r.get("HC")), "ac": _num(r.get("AC")),
            "hy": _num(r.get("HY")), "ay": _num(r.get("AY")),
            "hr": _num(r.get("HR")), "ar": _num(r.get("AR")),
            "ref": (r.get("Referee") or "").strip(),
            # Pinnacle closing (για μελλοντικό έλεγχο CLV)
            "psch": _num(r.get("PSCH") or r.get("PPCH")), "pscd": _num(r.get("PSCD") or r.get("PPCD")),
            "psca": _num(r.get("PSCA") or r.get("PPCA")),
        })
    _save_cache(key, rows)
    return rows


def fdcouk_fixtures():
    """Επερχόμενοι αγώνες (ανανεώνεται συνήθως Τρίτη & Παρασκευή) με αποδόσεις."""
    hit = _cached("fdcouk_fixtures.json", 3)
    if hit is not None:
        return hit
    try:
        raw, _ = _get("https://www.football-data.co.uk/fixtures.csv")
    except Exception as e:
        print(f"  ! fixtures.csv: {e}")
        return []
    out = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))):
        if not r.get("HomeTeam"):
            continue
        dt = _parse_date(r.get("Date"), r.get("Time"))
        books = {}
        for bk, pre in (("Bet365", "B365"), ("Pinnacle", "PS"), ("Pinnacle", "PP"), ("Betway", "BV"),
                        ("Bwin", "BW"), ("Μέγιστη", "Max"), ("Μέσος όρος", "Avg")):
            h, d, a = _num(r.get(pre + "H")), _num(r.get(pre + "D")), _num(r.get(pre + "A"))
            if h and d and a:
                books.setdefault(bk, {})["1X2"] = {"1": h, "X": d, "2": a}
            o, u = _num(r.get(pre + ">2.5")), _num(r.get(pre + "<2.5"))
            if o and u:
                books.setdefault(bk, {})["OU2.5"] = {"Over": o, "Under": u}
        out.append({"league": r.get("Div"), "date": dt.isoformat() if dt else None,
                    "home": r["HomeTeam"].strip(), "away": r["AwayTeam"].strip(),
                    "ref": (r.get("Referee") or "").strip(), "books": books})
    _save_cache("fdcouk_fixtures.json", out)
    return out


# ---------------- football-data.org (δωρεάν κλειδί) ----------------

def fdorg_matches(comp, days_back=0, days_ahead=config.DAYS_AHEAD):
    if not config.FOOTBALL_DATA_ORG_KEY:
        return None
    now = datetime.now(timezone.utc)
    q = urllib.parse.urlencode({
        "dateFrom": (now - timedelta(days=days_back)).strftime("%Y-%m-%d"),
        "dateTo": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d"),
    })
    key = f"fdorg_{comp}_{days_back}_{days_ahead}.json"
    hit = _cached(key, 2)
    if hit is not None:
        return hit
    try:
        raw, _ = _get(f"https://api.football-data.org/v4/competitions/{comp}/matches?{q}",
                      {"X-Auth-Token": config.FOOTBALL_DATA_ORG_KEY})
        data = json.loads(raw)
    except Exception as e:
        print(f"  ! football-data.org {comp}: {e}")
        return None
    out = []
    for m in data.get("matches", []):
        ft = (m.get("score") or {}).get("fullTime") or {}
        out.append({
            "id": m["id"], "date": m["utcDate"], "status": m["status"],
            "stage": m.get("stage"), "matchday": m.get("matchday"),
            "home": m["homeTeam"].get("shortName") or m["homeTeam"].get("name"),
            "away": m["awayTeam"].get("shortName") or m["awayTeam"].get("name"),
            "home_full": m["homeTeam"].get("name"), "away_full": m["awayTeam"].get("name"),
            "home_crest": m["homeTeam"].get("crest"), "away_crest": m["awayTeam"].get("crest"),
            "hg": ft.get("home"), "ag": ft.get("away"),
        })
    _save_cache(key, out)
    time.sleep(6.5)  # όριο 10 κλήσεις/λεπτό
    return out


def fdorg_standings(comp):
    if not config.FOOTBALL_DATA_ORG_KEY:
        return None
    hit = _cached(f"fdorg_st_{comp}.json", 6)
    if hit is not None:
        return hit
    try:
        raw, _ = _get(f"https://api.football-data.org/v4/competitions/{comp}/standings",
                      {"X-Auth-Token": config.FOOTBALL_DATA_ORG_KEY})
        data = json.loads(raw)
    except Exception as e:
        print(f"  ! standings {comp}: {e}")
        return None
    tables = []
    for st in data.get("standings", []):
        if st.get("type") != "TOTAL":
            continue
        tables.append({"group": st.get("group"), "rows": [{
            "pos": r["position"], "team": r["team"].get("shortName") or r["team"]["name"],
            "crest": r["team"].get("crest"), "p": r["playedGames"], "w": r["won"], "d": r["draw"],
            "l": r["lost"], "gf": r["goalsFor"], "ga": r["goalsAgainst"], "pts": r["points"],
            "form": r.get("form"),
        } for r in st.get("table", [])]})
    _save_cache(f"fdorg_st_{comp}.json", tables)
    time.sleep(6.5)
    return tables


# ---------------- The Odds API (δωρεάν κλειδί, 500 credits/μήνα) ----------------

def odds_api(sport):
    """Επιστρέφει (events, remaining). Χρησιμοποιεί cache για να μη ξοδεύει credits."""
    if not config.ODDS_API_KEY:
        return None, None
    key = f"odds_{sport}.json"
    hit = _cached(key, config.ODDS_REFRESH_HOURS)
    if hit is not None:
        return hit["events"], hit.get("remaining")
    meta = _cached("odds_meta.json", 24) or {}  # μια φορά τη μέρα ξαναδοκιμάζει (τα credits μηδενίζονται κάθε μήνα)
    if meta.get("remaining") is not None and meta["remaining"] < config.ODDS_MIN_REMAINING:
        print("  ! Odds API: λίγα credits, παράλειψη")
        old = _cached(key, 0, stale_ok=True)
        return (old["events"] if old else None), meta["remaining"]
    q = urllib.parse.urlencode({"apiKey": config.ODDS_API_KEY, "regions": config.ODDS_REGIONS,
                                "markets": config.ODDS_MARKETS, "oddsFormat": "decimal"})
    try:
        raw, hdr = _get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds?{q}")
    except Exception as e:
        print(f"  ! Odds API {sport}: {e}")
        old = _cached(key, 0, stale_ok=True)
        return (old["events"] if old else None), meta.get("remaining")
    remaining = _num(hdr.get("x-requests-remaining") or hdr.get("X-Requests-Remaining"))
    events = []
    for ev in json.loads(raw):
        books = {}
        for b in ev.get("bookmakers", []):
            mk = {}
            for m in b.get("markets", []):
                if m["key"] == "h2h":
                    o = {x["name"]: x["price"] for x in m["outcomes"]}
                    if ev["home_team"] in o and ev["away_team"] in o and "Draw" in o:
                        mk["1X2"] = {"1": o[ev["home_team"]], "X": o["Draw"], "2": o[ev["away_team"]]}
                elif m["key"] == "totals":
                    for x in m["outcomes"]:
                        mk.setdefault(f"OU{x.get('point')}", {})[x["name"]] = x["price"]
                elif m["key"] == "spreads":
                    for x in m["outcomes"]:
                        side = "H" if x["name"] == ev["home_team"] else "A"
                        pt = x.get("point")
                        line = pt if side == "H" else -pt
                        mk.setdefault(f"AH{line:+g}", {})[side] = x["price"]
            if mk:
                books[b["title"]] = mk
        events.append({"date": ev["commence_time"], "home": ev["home_team"],
                       "away": ev["away_team"], "books": books})
    _save_cache(key, {"events": events, "remaining": remaining})
    _save_cache("odds_meta.json", {"remaining": remaining, "at": datetime.now(timezone.utc).isoformat()})
    return events, remaining
