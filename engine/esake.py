"""Ελληνική Basket League (Stoiximan GBL) από τις δημόσιες σελίδες της ΕΣΑΚΕ (esake.gr).

- Πρόγραμμα/αποτελέσματα ανά αγωνιστική (EsakeResults).
- Πλήρη στατιστικά παικτών ανά αγώνα (EsakegameView, mode=3).
Ίδια μορφή με τα games()/boxscores() του basket.py. Τα παλιά (τελειωμένα) αποθηκεύονται για πάντα.
"""
import html
import re
import time
from datetime import datetime, timedelta, timezone

from . import sources

BASE = "https://www.esake.gr/el/action"
UA = {"User-Agent": "Mozilla/5.0 (value-bets, personal use)"}
# σεζόν (έτος έναρξης) -> idchampionship της ΕΣΑΚΕ
CHAMP = {2026: "184645B9", 2025: "44B80BEB", 2024: "4820C134", 2023: "C1AF5EF5"}
MONTHS = {"Ιαν": 1, "Φεβ": 2, "Μαρ": 3, "Απρ": 4, "Μαϊ": 5, "Μάι": 5, "Μαι": 5, "Ιουν": 6, "Ιουλ": 7, "Αυγ": 8,
          "Σεπ": 9, "Οκτ": 10, "Νοε": 11, "Δεκ": 12}
NAMES = {"ΟΛΥΜΠΙΑΚΟΣ": "Ολυμπιακός", "ΠΑΝΑΘΗΝΑΪΚΟΣ": "Παναθηναϊκός", "ΑΕΚ": "ΑΕΚ", "ΠΑΟΚ": "ΠΑΟΚ", "ΑΡΗΣ": "Άρης",
         "ΠΕΡΙΣΤΕΡΙ": "Περιστέρι", "ΠΡΟΜΗΘΕΑΣ": "Προμηθέας", "ΗΡΑΚΛΗΣ": "Ηρακλής", "ΚΟΛΟΣΣΟΣ": "Κολοσσός",
         "ΜΑΡΟΥΣΙ": "Μαρούσι", "ΜΥΚΟΝΟΣ": "Μύκονος", "ΚΑΡΔΙΤΣΑ": "Καρδίτσα", "ΔΟΞΑ": "Δόξα Λευκάδας",
         "ΛΑΥΡΙΟ": "Λαύριο", "ΑΠΟΛΛΩΝ": "Απόλλων Πάτρας", "ΙΩΝΙΚΟΣ": "Ιωνικός", "ΣΠΟΡΤΙΝΓΚ": "Σπόρτινγκ",
         "ΚΗΦΙΣΙΑ": "Κηφισιά", "ΠΑΝΙΩΝΙΟΣ": "Πανιώνιος", "ΚΑΡΔΙΤΣΑΣ": "Καρδίτσα", "VIKOS": "Vikos Falcons"}


def _get(url):
    for i in range(3):
        try:
            raw, _ = sources._get(url, headers=UA, timeout=40)
            return raw.decode("utf-8", errors="replace")
        except Exception as e:
            if i == 2:
                raise
            time.sleep(5 * (i + 1))


def _txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _short(raw_name):
    first = _txt(raw_name.split("<br")[0]).upper()
    key = first.split()[0] if first else ""
    return NAMES.get(first) or NAMES.get(key) or first.title()


def _date(txt, season):
    m = re.search(r"(\d{1,2})\s+([Α-Ωα-ωάέήίόύώϊ]+)\s*-\s*(\d{1,2}):(\d{2})", txt)
    if not m:
        return None
    mon = next((v for k, v in MONTHS.items() if m.group(2).startswith(k)), None)
    if not mon:
        return None
    year = season if mon >= 8 else season + 1
    # ώρα Ελλάδας (UTC+2 χειμώνα / UTC+3 καλοκαίρι, κατά προσέγγιση)
    off = 3 if 4 <= mon <= 10 else 2
    d = datetime(year, mon, int(m.group(1)), int(m.group(3)), int(m.group(4)), tzinfo=timezone(timedelta(hours=off)))
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _round_games(season, phase, series):
    s = _get(f"{BASE}/EsakeResults?idchampionship={CHAMP[season]}&idteam=&idseason={phase}&series={series}")
    out = []
    for blk in s.split('<div class="esake-program-game">')[1:]:
        gid = re.search(r"idgame=([0-9A-F]+)", blk)
        when = re.search(r'clock\.svg[^>]*>([^<]+)', blk)
        if "esake-program-game-final-score row" not in blk:
            continue
        fs = blk.split("esake-program-game-final-score row")[1].split("esake-program-game-hidden-row")[0]
        spans = re.findall(r"<span>(.*?)</span>", fs, re.S)
        ids = re.findall(r"/dat/esaketeam/([0-9A-F]+)/", fs)
        crests = re.findall(r'src="(/dat/esaketeam/[^"]+)"', fs)
        if not gid or not when or len(spans) < 3 or len(ids) < 2:
            continue
        score = re.match(r"(\d+)\s*-\s*(\d+)", _txt(spans[1]).replace(" ", " "))
        names = [spans[0], spans[2]]
        rnd = re.search(r"<h5>(\d+)", blk)
        out.append({
            "code": gid.group(1), "date": _date(when.group(1), season), "round": int(rnd.group(1)) if rnd else None,
            "phase": "RS" if phase == "00000001" else "PO", "played": bool(score),
            "hid": ids[0], "aid": ids[1], "home_raw": names[0], "away_raw": names[1],
            "hp": int(score.group(1)) if score else None, "ap": int(score.group(2)) if score else None,
            "home_crest": "https://www.esake.gr" + crests[0], "away_crest": "https://www.esake.gr" + crests[1],
        })
    return out, s


def games(season):
    """Όλοι οι αγώνες μιας σεζόν (κανονική περίοδος + play-offs), με ονόματα ομάδων ανά idteam."""
    if season not in CHAMP:
        return []
    now = datetime.now(timezone.utc)
    current = season == (now.year if now.month >= 8 else now.year - 1)
    key = f"esake_games_{season}.json"
    hit = sources._cached(key, 2 if current else 24 * 90)
    if hit is not None:
        return hit
    old = {g["code"]: g for g in (sources._cached(key, 0, stale_ok=True) or [])}
    out = []
    try:
        for phase in ("00000001", "00000002"):
            first, page = _round_games(season, phase, "01")
            rounds = sorted(set(re.findall(r"#series'\)\.append\(new Option\('[^']*', '(\d+)'\)\)", page)))
            if not rounds:
                out += first
                continue
            for r in rounds:
                # τελειωμένες αγωνιστικές περασμένων σεζόν: από την cache
                cached = [g for g in old.values() if g.get("series") == f"{phase}:{r}" and g["played"]]
                if cached and not current:
                    out += cached
                    continue
                gl = first if r == "01" else _round_games(season, phase, r)[0]
                for g in gl:
                    g["series"] = f"{phase}:{r}"
                out += gl
                time.sleep(0.8)
    except Exception as e:
        print(f"  ! ΕΣΑΚΕ {season}: {e}")
        return list(old.values())
    seen, res = set(), []
    for g in out:
        if g["code"] not in seen and g["date"]:
            seen.add(g["code"])
            res.append(g)
    # όνομα ομάδας = το τελευταίο όνομα (χορηγοί αλλάζουν, το idteam μένει ίδιο)
    names = {}
    for g in sorted(res, key=lambda g: g["date"]):
        names[g["hid"]] = g["home_raw"]
        names[g["aid"]] = g["away_raw"]
    for g in res:
        g["home"], g["away"] = _short(names[g["hid"]]), _short(names[g["aid"]])
        g["home_short"], g["away_short"] = g["home"], g["away"]
        g["ot"] = False
    res.sort(key=lambda g: g["date"])
    sources._save_cache(key, res)
    return res


COLS = ["P", "REBS", "AST", "BLK", "FOULS F", "STL", "TO", "TIM.PL.", "3PM-A"]


def _box_table(tb):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)
    head = None
    out = []
    for r in rows:
        raw = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)
        cells = [_txt(c) for c in raw]
        if "ΠΑΙΚΤΗΣ" in cells and "P" in cells:
            head = cells
            continue
        if not head or not cells or not cells[0].startswith("#"):
            continue
        off = len(cells) - len(head)
        ix = {h: i + off for i, h in enumerate(head) if i >= head.index("P")}
        # "#2 <SPAN>WILLIS</SPAN> PAYTON" -> "WILLIS, PAYTON" (επίθετο, όνομα, όπως στη EuroLeague)
        nm = re.search(r"<span>(.*?)</span>(.*?)</a>", raw[0], re.S | re.I)
        name = f"{_txt(nm.group(1))}, {_txt(nm.group(2))}".strip(", ") if nm else re.sub(r"^#\d+\s*", "", cells[0])
        mm = re.match(r"(\d+):(\d+):(\d+)", cells[ix["TIM.PL."]])
        mins = int(mm.group(1)) * 60 + int(mm.group(2)) + int(mm.group(3)) / 60 if mm else 0
        if mins <= 0:
            continue
        n = lambda c: float(re.split(r"\s*-\s*", cells[ix[c]])[0] or 0)
        out.append([name, round(mins, 1), n("P"), n("REBS"), n("AST"), n("3PM-A"), n("STL"), n("TO"), n("FOULS M"), n("BLK"), 0])  # FOULS M = φάουλ που κάνει (F = που δέχεται)
    return out


def boxscores(played, limit=60):
    """Στατιστικά παικτών (ίδια μορφή με basket.boxscores). Μόνο όσα λείπουν, το πολύ `limit` κάθε φορά."""
    key = "esake_box.json"
    box = sources._cached(key, 0, stale_ok=True) or {}
    new = 0
    for g in sorted(played, key=lambda g: g["date"], reverse=True):
        if g["code"] in box:
            continue
        if new >= limit:
            break
        try:
            s = _get(f"{BASE}/EsakegameView?idgame={g['code']}&mode=3")
        except Exception as e:
            print(f"  ! ΕΣΑΚΕ boxscore {g['code']}: {e}")
            continue
        tabs = [t for t in re.findall(r"<table.*?</table>", s, re.S) if "ΠΑΙΚΤΗΣ" in t]
        if len(tabs) >= 2:
            h, a = _box_table(tabs[0]), _box_table(tabs[1])
            if h and a:
                box[g["code"]] = {"home": h, "away": a}
                new += 1
        time.sleep(1.0)
        if new and new % 20 == 0:
            sources._save_cache(key, box)
    if new:
        sources._save_cache(key, box)
        print(f"  ΕΣΑΚΕ: +{new} boxscores ({len(box)} σύνολο)")
    return box
