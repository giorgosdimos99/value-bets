"""Basketball Champions League: πρόγραμμα και αποτελέσματα από τη δημόσια σελίδα αγώνων
(championsleague.basketball/en/games, τα δεδομένα είναι μέσα στη σελίδα· το robots.txt επιτρέπει την πρόσβαση).
Δεν υπάρχουν δωρεάν στατιστικά παικτών -> μόνο νικητής / χάντικαπ / σύνολο πόντων.
"""
import json
import re

from . import sources

URL = "https://www.championsleague.basketball/en/games"
UA = {"User-Agent": "Mozilla/5.0 (value-bets, personal use)"}


def games():
    key = "bcl_games.json"
    hit = sources._cached(key, 2)
    if hit is not None:
        return hit
    try:
        raw, _ = sources._get(URL, headers=UA, timeout=60)
        s = raw.decode("utf-8", errors="replace").replace('\\"', '"')
    except Exception as e:
        print(f"  ! BCL: {e}")
        return sources._cached(key, 0, stale_ok=True) or []
    out, seen = [], set()
    dec = json.JSONDecoder()
    for m in re.finditer(r'\{"gameId":(\d+),', s):
        try:
            g, _ = dec.raw_decode(s, m.start())
        except ValueError:
            continue
        gid = g.get("gameId")
        comp = (g.get("competition") or {}).get("competitionCode")
        if gid in seen or comp != "BCL" or not g.get("teamA") or not g.get("teamB"):
            continue
        seen.add(gid)
        if g.get("isPostponed") or (g.get("gameDateTimeUTC") or "").startswith("0001"):
            continue
        a, b = g["teamA"], g["teamB"]
        played = g.get("teamAScore") is not None and g.get("teamBScore") is not None and not g.get("isLive") \
            and g.get("currentPeriodStatus") == "E"
        rnd = g.get("round") or {}
        out.append({
            "code": gid, "date": g["gameDateTimeUTC"][:19] + "Z", "round": rnd.get("roundNumber"),
            "phase": rnd.get("roundCode"), "played": bool(played),
            "home": a.get("shortName") or a.get("officialName"), "away": b.get("shortName") or b.get("officialName"),
            "home_short": a.get("shortName"), "away_short": b.get("shortName"),
            "home_crest": None, "away_crest": None,
            "hp": g.get("teamAScore") if played else None, "ap": g.get("teamBScore") if played else None, "ot": False,
        })
    out.sort(key=lambda g: g["date"])
    if out:
        sources._save_cache(key, out)
    return out
