"""Ρυθμίσεις της μηχανής."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_OUT = ROOT / "site" / "data"
CACHE = ROOT / ".cache"


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

FOOTBALL_DATA_ORG_KEY = os.environ.get("FOOTBALL_DATA_ORG_KEY", "")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")

# Σεζόν για football-data.co.uk (π.χ. 2627 = 2026/27)
SEASON = os.environ.get("SEASON", "2627")
PREV_SEASON = os.environ.get("PREV_SEASON", "2526")
# Παλαιότερες σεζόν: διαιτητές, H2H, γκανιότα στοιχηματικών και backtest
HISTORY_SEASONS = ["2223", "2324", "2425", "2526"]

# Πρωταθλήματα για τις βαθμολογίες ομάδων (code στο football-data.co.uk -> (όνομα, δύναμη πρωταθλήματος))
# Η "δύναμη" χρησιμοποιείται μόνο σε αγώνες μεταξύ ομάδων από διαφορετικά πρωταθλήματα (Champions League).
RATING_LEAGUES = {
    "E0": ("Premier League", 1.00),
    "SP1": ("La Liga", 0.94),
    "D1": ("Bundesliga", 0.91),
    "I1": ("Serie A", 0.91),
    "F1": ("Ligue 1", 0.86),
    "P1": ("Primeira Liga", 0.80),
    "N1": ("Eredivisie", 0.78),
    "B1": ("Pro League", 0.76),
    "T1": ("Süper Lig", 0.74),
    "G1": ("Super League", 0.70),
    "SC0": ("Premiership", 0.70),
    "E1": ("Championship", 0.80),
    "E2": ("League One", 0.66),
    "D2": ("2. Bundesliga", 0.74),
    "I2": ("Serie B", 0.70),
    "SP2": ("Segunda División", 0.72),
    "F2": ("Ligue 2", 0.68),
}
DEFAULT_LEAGUE_STRENGTH = 0.68  # ομάδες από πρωταθλήματα που δεν παρακολουθούμε
CROSS_EXP = 2.0                 # πόσο έντονα μετράει η διαφορά δύναμης πρωταθλημάτων

# Διοργανώσεις που εμφανίζονται στην εφαρμογή
COMPETITIONS = {
    "PL": {"name": "Premier League", "fdorg": "PL", "odds": "soccer_epl", "fdcouk": "E0", "paid_odds": True},
    "CL": {"name": "Champions League", "fdorg": "CL", "odds": "soccer_uefa_champs_league", "fdcouk": None, "paid_odds": True},
    # football-data.org δεν έχει Super League στο δωρεάν πακέτο: πρόγραμμα από The Odds API (δωρεάν "events")
    "GR": {"name": "Super League", "fdorg": None, "odds": "soccer_greece_super_league", "fdcouk": "G1",
           "odds_markets": "h2h,totals", "paid_odds": True},
}
# Υπόλοιπα πρωταθλήματα: πρόγραμμα από The Odds API "events" (0 credits), αποδόσεις από το δωρεάν
# fixtures.csv του football-data.co.uk (Bet365, Pinnacle, μέσος όρος). Δεν ξοδεύουν credits.
for _cid, _name, _sport, _code in (
        ("PD", "La Liga", "soccer_spain_la_liga", "SP1"),
        ("SA", "Serie A", "soccer_italy_serie_a", "I1"),
        ("BL", "Bundesliga", "soccer_germany_bundesliga", "D1"),
        ("FL1", "Ligue 1", "soccer_france_ligue_one", "F1"),
        ("ELC", "Championship", "soccer_efl_champ", "E1"),
        ("DED", "Eredivisie", "soccer_netherlands_eredivisie", "N1"),
        ("PPL", "Primeira Liga", "soccer_portugal_primeira_liga", "P1"),
        ("BEL", "Βέλγιο Pro League", "soccer_belgium_first_div", "B1"),
        ("TUR", "Τουρκία Süper Lig", "soccer_turkey_super_league", "T1"),
        ("SCO", "Σκωτία Premiership", "soccer_spl", "SC0"),
        ("L1", "League One", "soccer_england_league1", "E2"),
        ("BL2", "2. Bundesliga", "soccer_germany_bundesliga2", "D2"),
        ("SB", "Serie B", "soccer_italy_serie_b", "I2"),
        ("SD", "Segunda División", "soccer_spain_segunda_division", "SP2"),
        ("FL2", "Ligue 2", "soccer_france_ligue_two", "F2")):
    COMPETITIONS[_cid] = {"name": _name, "fdorg": None, "odds": _sport, "fdcouk": _code, "paid_odds": False, "days": 7}

# Μπάσκετ (ξεχωριστό μοντέλο: engine/basket.py)
BASKET = {"EL": {"name": "EuroLeague", "feed": "E", "odds": "basketball_euroleague"},
          "EC": {"name": "EuroCup", "feed": "U", "odds": None}}
ODDS_WINDOW_HOURS = 36   # αποδόσεις ζητάμε μόνο αν υπάρχει αγώνας μέσα σε τόσες ώρες (εξοικονόμηση credits)

DAYS_AHEAD = 10          # πόσες μέρες μπροστά κοιτάμε αγώνες
HALF_LIFE_DAYS = 90      # πόσο γρήγορα "ξεχνάμε" παλιά παιχνίδια
PRIOR_MATCHES = 4        # συρρίκνωση προς τον μέσο όρο (σταθερότητα στην αρχή της σεζόν)
XG_WEIGHT = 0.65         # μείγμα xG / γκολ για την επιθετική/αμυντική ισχύ
# βάρος μοντέλου έναντι της αγοράς (Pinnacle / διάμεσος) στα αναμενόμενα γκολ.
# Από backtest Premier League 2023-26 (1.051 αγώνες): 0.2 έδωσε το καλύτερο CLV και θετικό ROI.
MODEL_WEIGHT = 0.20
MIN_EDGE = 0.03          # ελάχιστο +EV για να χαρακτηριστεί value (3%)
MIN_ODDS, MAX_ODDS = 1.30, 4.50
SOLID_MIN_PROB = 0.58   # "λογικές επιλογές" όταν δεν υπάρχει value

# The Odds API: κάθε κλήση κοστίζει (αγορές × περιοχές) credits. Δωρεάν: 500/μήνα.
ODDS_REGIONS = "eu"
ODDS_MARKETS = "h2h,totals,spreads"
ODDS_MIN_REMAINING = 15  # δεν καίμε τα τελευταία credits
ODDS_REFRESH_HOURS = 12 # ανανέωση αποδόσεων το πολύ κάθε τόσες ώρες
