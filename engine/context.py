"""Παράγοντες πέρα από τη δύναμη των ομάδων (δωρεάν πηγές, χωρίς κλειδί).

- Αλλαγές προπονητή: πίνακας "Managerial changes" του άρθρου της σεζόν στη Wikipedia.
- Έδρα κάθε ομάδας: πίνακας "Stadiums and locations" (πόλη) -> συντεταγμένες από Open-Meteo geocoding.
- Καιρός: Open-Meteo (ιστορικό archive + πρόγνωση), βροχή / αέρας / θερμοκρασία την ώρα του αγώνα.
"""
import json
import re
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser

from . import names, sources

WIKI = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "value-bets-research/1.0 (personal, non-commercial)"}

# code football-data.co.uk -> τίτλος άρθρου σεζόν στη Wikipedia ("{y}" = π.χ. 2024–25)
WIKI_PAGES = {
    "E0": "{y} Premier League", "E1": "{y} EFL Championship", "E2": "{y} EFL League One",
    "E3": "{y} EFL League Two", "EC": "{y} National League", "SC0": "{y} Scottish Premiership",
    "SC1": "{y} Scottish Championship", "SC2": "{y} Scottish League One", "SC3": "{y} Scottish League Two",
    "SP1": "{y} La Liga", "SP2": "{y} Segunda División", "D1": "{y} Bundesliga", "D2": "{y} 2. Bundesliga",
    "I1": "{y} Serie A", "I2": "{y} Serie B", "F1": "{y} Ligue 1", "F2": "{y} Ligue 2",
    "P1": "{y} Primeira Liga", "N1": "{y} Eredivisie", "B1": "{y} Belgian Pro League",
    "T1": "{y} Süper Lig", "G1": "{y} Super League Greece",
}
COUNTRY = {"E": "GB", "S": "ES", "D": "DE", "I": "IT", "F": "FR", "P": "PT", "N": "NL", "B": "BE", "T": "TR", "G": "GR"}
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"])}


def season_title(season):
    """'2425' -> '2024–25'."""
    return f"20{season[:2]}–{season[2:]}"


# ---------------- Wikipedia: πίνακες ----------------

class _Tables(HTMLParser):
    """Πίνακες wikitable -> λίστα από γραμμές (λίστες κειμένων), με σωστό χειρισμό rowspan/colspan."""

    def __init__(self):
        super().__init__()
        self.tables, self.depth, self.skip = [], 0, 0
        self.row = self.cell = None
        self.span = {}

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "table":
            self.depth += 1
            if self.depth == 1 and "wikitable" in (a.get("class") or ""):
                self.tables.append([])
                self.span = {}
        elif not self.tables or self.depth != 1:
            return
        elif tag in ("sup", "style"):
            self.skip += 1
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"t": "", "rs": int(re.sub(r"\D", "", a.get("rowspan") or "1") or 1),
                         "cs": int(re.sub(r"\D", "", a.get("colspan") or "1") or 1)}
        elif tag == "br" and self.cell is not None:
            self.cell["t"] += " "

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1
        elif not self.tables or self.depth != 1:
            return
        elif tag in ("sup", "style") and self.skip:
            self.skip -= 1
        elif tag in ("td", "th") and self.cell is not None:
            self._fill()
            for _ in range(self.cell["cs"]):
                col = len(self.row)
                if self.cell["rs"] > 1:
                    self.span[col] = [self.cell["rs"] - 1, self.cell["t"].strip()]
                self.row.append(self.cell["t"].strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self._fill()
            if self.row:
                self.tables[-1].append(self.row)
            self.row = None

    def _fill(self):
        while len(self.row) in self.span:
            col = len(self.row)
            n, t = self.span[col]
            self.row.append(t)
            if n <= 1:
                del self.span[col]
            else:
                self.span[col][0] -= 1

    def handle_data(self, d):
        if self.cell is not None and not self.skip:
            self.cell["t"] += d


def wiki_tables(page, section_words):
    """Πίνακες της πρώτης ενότητας του άρθρου που ο τίτλος της περιέχει μία από τις λέξεις."""
    key = "wiki_" + re.sub(r"\W+", "_", page + "_" + section_words[0]).lower()[:90] + ".json"
    hit = sources._cached(key, 24 * 3)
    if hit is not None:
        return hit
    def get(url):
        for i in range(4):
            time.sleep(1.2)
            try:
                return json.loads(sources._get(url, headers=UA)[0])
            except Exception as e:
                if "429" not in str(e) or i == 3:
                    raise
                time.sleep(15 * (i + 1))

    q = lambda **p: f"{WIKI}?{urllib.parse.urlencode({'action': 'parse', 'format': 'json', 'redirects': 1, **p})}"
    try:
        secs = get(q(page=page, prop="sections"))["parse"]["sections"]
        idx = next((s["index"] for s in secs if any(w in s["line"].lower() for w in section_words)), None)
        if idx is None:
            sources._save_cache(key, [])
            return []
        html = get(q(page=page, prop="text", section=idx))["parse"]["text"]["*"]
    except Exception as e:
        print(f"  ! Wikipedia {page}: {e}")
        return sources._cached(key, 0, stale_ok=True) or []
    p = _Tables()
    p.feed(html)
    out = [t for t in p.tables if len(t) > 1]
    sources._save_cache(key, out)
    return out


def _date(s):
    s = (s or "").lower()
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", s)
    if m and m.group(2) in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1) in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return None


def _col(head, *words):
    return next((i for i, h in enumerate(head) if any(w in h.lower() for w in words)), None)


def coach_changes(code, season):
    """[{team, out, in, vacancy, appointed}] από τη Wikipedia (ημερομηνίες ως 'YYYY-MM-DD')."""
    page = WIKI_PAGES.get(code)
    if not page:
        return []
    out = []
    for t in wiki_tables(page.format(y=season_title(season)), ["managerial change", "coaching change", "head coach change", "manager change"]):
        head = t[0]
        ct, cv, ca = _col(head, "team", "club"), _col(head, "vacancy"), _col(head, "appointment")
        co, ci = _col(head, "outgoing"), _col(head, "incoming", "replaced")
        if ct is None or cv is None:
            continue
        for r in t[1:]:
            if len(r) < len(head):
                continue
            v = _date(r[cv])
            ap = _date(r[ca]) if ca is not None else None
            if not v and not ap:
                continue
            out.append({"team": r[ct], "out": r[co] if co is not None else "", "in": r[ci] if ci is not None else "",
                        "vacancy": (v or ap).isoformat(), "appointed": (ap or v).isoformat()})
    return out


def venues(code, season):
    """{ομάδα (όνομα Wikipedia): πόλη}."""
    page = WIKI_PAGES.get(code)
    if not page:
        return {}
    out = {}
    for t in wiki_tables(page.format(y=season_title(season)), ["stadia", "stadium", "venues", "teams"]):
        head = t[0]
        ct, cl = _col(head, "team", "club"), _col(head, "location", "city", "town")
        if ct is None or cl is None:
            continue
        for r in t[1:]:
            if len(r) > max(ct, cl) and r[ct] and r[cl]:
                out[r[ct]] = re.sub(r"\(.*?\)|\[.*?\]", "", r[cl]).split(",")[0].strip()
    return out


def team_map(wiki_names, fd_names):
    """Όνομα Wikipedia -> όνομα football-data.co.uk."""
    out = {}
    for w in wiki_names:
        f = names.match(w, fd_names, cutoff=0.6)
        if not f:
            short = re.sub(r"\b(City|Town|United|Rovers|Athletic|Wanderers|County|Albion|Hotspur|Borough)\b", "", w).strip()
            f = names.match(short, fd_names, cutoff=0.6) if short else None
        if f:
            out[w] = f
    return out


# ---------------- Open-Meteo ----------------

def geocode(place, country):
    key = "geo_" + re.sub(r"\W+", "_", f"{place}_{country}").lower() + ".json"
    hit = sources._cached(key, 24 * 365)
    if hit is not None:
        return hit
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": place, "count": 5, "language": "en"})
    try:
        res = json.loads(sources._get(url)[0]).get("results") or []
    except Exception as e:
        print(f"  ! geocode {place}: {e}")
        return None
    best = next((r for r in res if r.get("country_code") == country), None)
    out = [round(best["latitude"], 3), round(best["longitude"], 3)] if best else []
    sources._save_cache(key, out)
    return out


def _wx(js, when):
    """Καιρός γύρω από την ώρα του αγώνα (έναρξη έως +2 ώρες) από ωριαία δεδομένα Open-Meteo."""
    h = js.get("hourly") or {}
    times = h.get("time") or []
    t0 = when.strftime("%Y-%m-%dT%H:00")
    try:
        i = times.index(t0)
    except ValueError:
        return None
    seg = lambda k: [x for x in (h.get(k) or [])[i:i + 3] if x is not None]
    pr, wd, tp = seg("precipitation"), seg("wind_speed_10m"), seg("temperature_2m")
    pre = [x for x in (h.get("precipitation") or [])[max(i - 6, 0):i] if x is not None]
    if not pr or not wd or not tp:
        return None
    return {"rain": round(sum(pr), 1), "rain_before": round(sum(pre), 1), "wind": round(max(wd), 1),
            "temp": round(sum(tp) / len(tp), 1)}


def weather_archive(lat, lon, start, end, tz="UTC"):
    """Ωριαίος καιρός (τοπική ώρα Λονδίνου) για ιστορικό. Επιστρέφει το raw json (δεν αποθηκεύεται)."""
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "hourly": "precipitation,wind_speed_10m,temperature_2m", "timezone": tz})
    return json.loads(sources._get(url, timeout=90)[0])


def forecast(lat, lon, when):
    """Πρόγνωση για αγώνα στις επόμενες 16 ημέρες (ώρα UTC)."""
    key = f"wx_{lat}_{lon}.json"
    js = sources._cached(key, 3)
    if js is None:
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "hourly": "precipitation,wind_speed_10m,temperature_2m",
            "timezone": "UTC", "past_days": 1, "forecast_days": 16})
        try:
            js = json.loads(sources._get(url)[0])
        except Exception as e:
            print(f"  ! καιρός {lat},{lon}: {e}")
            return None
        sources._save_cache(key, {"hourly": js.get("hourly")})
    return _wx(js, when)
