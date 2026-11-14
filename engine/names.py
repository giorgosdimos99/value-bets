"""Αντιστοίχιση ονομάτων ομάδων ανάμεσα στις πηγές."""
import difflib
import re
import unicodedata

# κανονικοποιημένο όνομα -> κοινό κλειδί
ALIASES = {
    "man united": "manchester united", "man utd": "manchester united", "manchester utd": "manchester united",
    "man city": "manchester city", "nottm forest": "nottingham forest", "nott'm forest": "nottingham forest",
    "nottingham": "nottingham forest", "wolves": "wolverhampton", "wolverhampton wanderers": "wolverhampton",
    "spurs": "tottenham", "tottenham hotspur": "tottenham", "newcastle united": "newcastle",
    "west ham united": "west ham", "brighton hove": "brighton", "brighton and hove albion": "brighton",
    "brighton hove albion": "brighton", "leeds united": "leeds", "leicester city": "leicester",
    "ipswich town": "ipswich", "luton town": "luton", "sheffield united": "sheffield utd",
    "sheffield united fc": "sheffield utd", "coventry city": "coventry", "hull city": "hull",
    "norwich city": "norwich", "stoke city": "stoke", "swansea city": "swansea", "cardiff city": "cardiff",
    "afc bournemouth": "bournemouth", "west bromwich albion": "west brom",
    "paris saint germain": "paris sg", "psg": "paris sg", "paris": "paris sg",
    "1 koln": "cologne", "koln": "cologne", "fc koln": "cologne",
    "bayern munich": "bayern munchen", "bayern": "bayern munchen", "fc bayern munchen": "bayern munchen",
    "borussia dortmund": "dortmund", "bvb": "dortmund", "bayer leverkusen": "leverkusen",
    "bayer 04 leverkusen": "leverkusen", "rb leipzig": "rb leipzig", "leipzig": "rb leipzig",
    "eintracht frankfurt": "ein frankfurt", "frankfurt": "ein frankfurt", "vfb stuttgart": "stuttgart",
    "borussia monchengladbach": "m'gladbach", "monchengladbach": "m'gladbach",
    "inter milan": "inter", "internazionale": "inter", "fc internazionale milano": "inter",
    "ac milan": "milan", "juventus": "juventus", "ssc napoli": "napoli", "as roma": "roma",
    "atalanta bc": "atalanta", "ss lazio": "lazio",
    "atletico madrid": "ath madrid", "atletico de madrid": "ath madrid", "atleti": "ath madrid",
    "club atletico de madrid": "ath madrid", "athletic bilbao": "ath bilbao", "athletic club": "ath bilbao",
    "real sociedad": "sociedad", "fc barcelona": "barcelona", "barca": "barcelona",
    "real madrid cf": "real madrid", "villarreal cf": "villarreal", "real betis": "betis",
    "sevilla fc": "sevilla", "girona fc": "girona",
    "sporting cp": "sp lisbon", "sporting lisbon": "sp lisbon", "sporting": "sp lisbon",
    "sl benfica": "benfica", "fc porto": "porto", "sporting braga": "sp braga", "braga": "sp braga",
    "psv eindhoven": "psv", "psv": "psv", "afc ajax": "ajax", "feyenoord rotterdam": "feyenoord",
    "olympique marseille": "marseille", "olympique de marseille": "marseille",
    "olympique lyonnais": "lyon", "as monaco": "monaco", "losc lille": "lille", "stade brestois": "brest",
    "stade brestois 29": "brest", "club brugge": "club brugge", "club brugge kv": "club brugge",
    "galatasaray sk": "galatasaray", "fenerbahce sk": "fenerbahce",
    "olympiacos": "olympiakos", "olympiacos piraeus": "olympiakos", "olympiakos piraeus": "olympiakos",
    "panathinaikos fc": "panathinaikos", "paok fc": "paok", "paok thessaloniki": "paok",
    "aek athens": "aek", "pae aek": "aek", "shaktar": "shakhtar donetsk", "shakhtar": "shakhtar donetsk",
    "slavia praha": "slavia prague", "sl bratislava": "slovan bratislava", "bodo/glimt": "bodo glimt",
    "fk bodo/glimt": "bodo glimt", "como 1907": "como", "rc lens": "lens", "celtic fc": "celtic", "rangers fc": "rangers",
}

_STRIP = re.compile(r"\b(fc|afc|cf|sc|ac|sk|fk|bc|cfc|kv|ssc|calcio|club)\b")


def norm(name):
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " ").replace("-", " ").replace(".", "")
    s = re.sub(r"\s+", " ", s).strip()
    if s in ALIASES:
        return ALIASES[s]
    s2 = re.sub(r"\s+", " ", _STRIP.sub(" ", s)).strip()
    return ALIASES.get(s2, s2)


def match(name, candidates, cutoff=0.72):
    """Βρίσκει το καλύτερο ταίριασμα από λίστα ονομάτων (επιστρέφει το αρχικό όνομα ή None)."""
    n = norm(name)
    table = {norm(c): c for c in candidates}
    if n in table:
        return table[n]
    for k, v in table.items():  # π.χ. "brentford" μέσα σε "brentford fc"
        if n and k and (n in k.split() or k in n.split() or n.startswith(k) or k.startswith(n)):
            return v
    best = difflib.get_close_matches(n, list(table), n=1, cutoff=cutoff)
    return table[best[0]] if best else None
