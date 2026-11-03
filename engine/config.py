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
}
DEFAULT_LEAGUE_STRENGTH = 0.68  # ομάδες από πρωταθλήματα που δεν παρακολουθούμε
CROSS_EXP = 2.0                 # πόσο έντονα μετράει η διαφορά δύναμης πρωταθλημάτων

# Διοργανώσεις που εμφανίζονται στην εφαρμογή
COMPETITIONS = {
    "PL": {"name": "Premier League", "fdorg": "PL", "odds": "soccer_epl", "fdcouk": "E0"},
    "CL": {"name": "Champions League", "fdorg": "CL", "odds": "soccer_uefa_champs_league", "fdcouk": None},
    # football-data.org δεν έχει Super League στο δωρεάν πακέτο: πρόγραμμα από The Odds API (δωρεάν "events")
    "GR": {"name": "Super League", "fdorg": None, "odds": "soccer_greece_super_league", "fdcouk": "G1",
           "odds_markets": "h2h,totals"},
}
# Μπάσκετ (ξεχωριστό μοντέλο: engine/basket.py)
BASKET = {"EL": {"name": "EuroLeague", "feed": "E", "odds": "basketball_euroleague"}}
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
