"""ESPN (δωρεάν, χωρίς κλειδί): NBA και εθνικές ομάδες.

- Πρόγραμμα/αποτελέσματα ανά ημέρα (scoreboard).
- Στατιστικά παικτών NBA ανά αγώνα (summary/boxscore).
- Αποδόσεις DraftKings όπου υπάρχουν (νικητής, χάντικαπ, σύνολο) -> χωρίς κόστος credits.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone

from . import sources

BASE = "https://site.api.espn.com/apis/site/v2/sports"
DONE = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_ABANDONED", "STATUS_FORFEIT")


def _dec(american):
    """Αμερικάνικη απόδοση (+150 / -120) -> δεκαδική."""
    try:
        a = float(str(american).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return round(1 + (a / 100 if a > 0 else 100 / -a), 3)


def _line(s):
    try:
        return float(str(s).lstrip("ou"))
    except (TypeError, ValueError):
        return None


def _books(odds_list, draw):
    """Αποδόσεις ESPN -> {"DraftKings": {"1X2"|"ML": ..., "OU<γραμμή>": ..., "AH<γραμμή>": ...}}."""
    o = next((x for x in odds_list or [] if isinstance(x, dict)), None)
    if not o:
        return {}
    name = (o.get("provider") or {}).get("name") or "DraftKings"
    close = lambda d, k: ((d or {}).get(k) or {}).get("close") or ((d or {}).get(k) or {}).get("open") or {}
    mk = {}
    ml = o.get("moneyline") or {}
    h, a = _dec(close(ml, "home").get("odds")), _dec(close(ml, "away").get("odds"))
    if h and a:
        if draw:
            d = _dec(close(ml, "draw").get("odds"))
            if d:
                mk["1X2"] = {"1": h, "X": d, "2": a}
        else:
            mk["ML"] = {"H": h, "A": a}
    tot = o.get("total") or {}
    ov, un = close(tot, "over"), close(tot, "under")
    L = _line(ov.get("line"))
    if L is not None and _dec(ov.get("odds")) and _dec(un.get("odds")):
        mk[f"OU{L:g}"] = {"Over": _dec(ov.get("odds")), "Under": _dec(un.get("odds"))}
    ps = o.get("pointSpread") or {}
    ph, pa = close(ps, "home"), close(ps, "away")
    L = _line(ph.get("line"))
    if L is not None and _dec(ph.get("odds")) and _dec(pa.get("odds")):
        mk[f"AH{L:+g}"] = {"H": _dec(ph.get("odds")), "A": _dec(pa.get("odds"))}
    return {name: mk} if mk else {}


def day(path, d, draw=False):
    """Αγώνες μιας ημέρας. Οι παλιές μέρες με όλα τελειωμένα μένουν στην cache για πάντα."""
    key = f"espn_{path.replace('/', '_')}_{d:%Y%m%d}.json"
    past = d < datetime.now(timezone.utc).date() - timedelta(days=1)
    hit = sources._cached(key, 24 * 365 if past else 2)
    if hit is not None and (not past or all(g["played"] or g["state"] in DONE for g in hit)):
        return hit
    try:
        raw, _ = sources._get(f"{BASE}/{path}/scoreboard?dates={d:%Y%m%d}", headers={"User-Agent": "Mozilla/5.0"})
        evs = json.loads(raw).get("events", [])
    except Exception as e:
        print(f"  ! ESPN {path} {d}: {e}")
        return sources._cached(key, 0, stale_ok=True) or []
    out = []
    for e in evs:
        c = e["competitions"][0]
        t = {x["homeAway"]: x for x in c["competitors"]}
        if "home" not in t or "away" not in t:
            continue
        st = e["status"]["type"]
        sc = lambda x: int(float(x["score"])) if x.get("score") not in (None, "") else None
        out.append({
            "id": e["id"], "date": e["date"], "played": bool(st.get("completed")), "state": st.get("name"),
            "home": t["home"]["team"]["displayName"], "away": t["away"]["team"]["displayName"],
            "home_abbr": t["home"]["team"].get("abbreviation"), "away_abbr": t["away"]["team"].get("abbreviation"),
            "home_crest": t["home"]["team"].get("logo"), "away_crest": t["away"]["team"].get("logo"),
            "hp": sc(t["home"]), "ap": sc(t["away"]),
            "periods": len(t["home"].get("linescores") or []),
            "neutral": bool(c.get("neutralSite")),
            "books": _books(c.get("odds"), draw),
        })
    sources._save_cache(key, out)
    return out


def days(path, start, end, draw=False):
    out, d = [], start
    while d <= end:
        out += day(path, d, draw)
        d += timedelta(days=1)
    return out


# ---------------- NBA ----------------

def nba_season_year(now=None):
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 8 else now.year - 1


def nba_games(days_ahead=3):
    """(τρέχουσα σεζόν, τέλος προηγούμενης) σε μορφή ίδια με το basket.games()."""
    today = datetime.now(timezone.utc).date()
    y = nba_season_year()
    cur = days("basketball/nba", date(y, 10, 15), min(today + timedelta(days=days_ahead), date(y + 1, 6, 30)))
    prev = days("basketball/nba", date(y, 3, 1), date(y, 4, 15))  # τελευταίοι ~45 μέρες της περσινής κανονικής περιόδου
    conv = lambda gl: [{
        "code": g["id"], "date": g["date"], "round": None, "phase": None, "played": g["played"],
        "home": g["home"], "away": g["away"], "home_short": g["home"], "away_short": g["away"],
        "home_crest": g["home_crest"], "away_crest": g["away_crest"],
        "hp": g["hp"], "ap": g["ap"], "ot": g["periods"] > 4, "books": g["books"],
    } for g in gl if g["played"] or g["state"] == "STATUS_SCHEDULED"]
    return conv(cur), conv(prev)


NBA_COLS = ["MIN", "PTS", "REB", "AST", "3PT", "STL", "TO", "PF", "BLK"]


def nba_boxscores(played, limit=120):
    """Στατιστικά παικτών ανά αγώνα (μόνο όσα λείπουν από την cache, το πολύ `limit` κάθε φορά)."""
    key = "espn_nba_box.json"
    box = sources._cached(key, 0, stale_ok=True) or {}
    new = 0
    for g in sorted(played, key=lambda g: g["date"], reverse=True):
        if str(g["code"]) in box:
            continue
        if new >= limit:
            break
        try:
            raw, _ = sources._get(f"{BASE}/basketball/nba/summary?event={g['code']}", headers={"User-Agent": "Mozilla/5.0"})
            d = json.loads(raw)
        except Exception as e:
            print(f"  ! NBA boxscore {g['code']}: {e}")
            continue
        entry = {}
        for tp in (d.get("boxscore") or {}).get("players", []):
            side = "home" if tp["team"]["displayName"] == g["home"] else "away"
            st = tp["statistics"][0]
            names = st.get("names") or st.get("labels") or []
            ix = {n: i for i, n in enumerate(names)}
            if not all(c in ix for c in NBA_COLS):
                continue
            rows = []
            for a in st.get("athletes", []):
                v = a.get("stats") or []
                if a.get("didNotPlay") or len(v) < len(names):
                    continue
                num = lambda c: float(str(v[ix[c]]).split("-")[0] or 0) if v[ix[c]] not in ("", "--") else 0.0
                try:
                    mins = num("MIN")
                except ValueError:
                    continue
                if not mins:
                    continue
                rows.append([a["athlete"]["displayName"], mins, num("PTS"), num("REB"), num("AST"), num("3PT"),
                             num("STL"), num("TO"), num("PF"), num("BLK"), int(bool(a.get("starter")))])
            entry[side] = rows
        if entry:
            box[str(g["code"])] = entry
            new += 1
    if new:
        sources._save_cache(key, box)
        print(f"  NBA: +{new} boxscores ({len(box)} σύνολο)")
    return box


def nba_injuries():
    """Λίστα τραυματιών NBA: {ομάδα: [(παίκτης, κατάσταση, σχόλιο)]} (κατάσταση: Out / Doubtful / Questionable / Day-To-Day)."""
    key = "espn_nba_injuries.json"
    hit = sources._cached(key, 2)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get(f"{BASE}/basketball/nba/injuries", headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(raw)
    except Exception as e:
        print(f"  ! NBA τραυματίες: {e}")
        return sources._cached(key, 0, stale_ok=True) or {}
    out = {}
    for t in d.get("injuries", []):
        out[t.get("displayName")] = [[i["athlete"]["displayName"], i.get("status"), i.get("shortComment") or ""]
                                     for i in t.get("injuries", []) if i.get("athlete")]
    sources._save_cache(key, out)
    return out


def nba_standings():
    """{ομάδα: {"conf": "East"/"West", "w", "l", "id"}} από τη βαθμολογία της ESPN."""
    key = "espn_nba_standings.json"
    hit = sources._cached(key, 3)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings", headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(raw)
    except Exception as e:
        print(f"  ! ESPN standings: {e}")
        return sources._cached(key, 0, stale_ok=True) or {}
    out = {}
    for c in d.get("children", []):
        conf = "East" if "East" in c["name"] else "West"
        for e in c["standings"]["entries"]:
            st = {x["name"]: x.get("value") for x in e["stats"]}
            out[e["team"]["displayName"]] = {"conf": conf, "id": e["team"]["id"], "w": int(st.get("wins") or 0),
                                             "l": int(st.get("losses") or 0), "pd": float(st.get("differential") or 0)}
    sources._save_cache(key, out)
    return out


def nba_remaining():
    """Αγώνες κανονικής περιόδου που μένουν: [(γηπεδούχος, φιλοξενούμενος)] από το πρόγραμμα κάθε ομάδας."""
    key = "espn_nba_remaining.json"
    hit = sources._cached(key, 12)
    if hit is not None:
        return hit
    seen, out = set(), []
    for team, x in nba_standings().items():
        try:
            raw, _ = sources._get(f"{BASE}/basketball/nba/teams/{x['id']}/schedule", headers={"User-Agent": "Mozilla/5.0"})
            evs = json.loads(raw).get("events", [])
        except Exception as e:
            print(f"  ! ESPN schedule {team}: {e}")
            return sources._cached(key, 0, stale_ok=True) or []
        for e in evs:
            c = e["competitions"][0]
            if e["id"] in seen or (e.get("seasonType") or {}).get("type") != 2 or c["status"]["type"].get("completed"):
                continue
            t = {y["homeAway"]: y["team"]["displayName"] for y in c["competitors"]}
            if "home" in t and "away" in t:
                seen.add(e["id"]); out.append([t["home"], t["away"]])
        time.sleep(0.3)
    sources._save_cache(key, out)
    return out
