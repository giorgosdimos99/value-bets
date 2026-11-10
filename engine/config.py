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
    "E3": ("League Two", 0.58),
    "EC": ("National League", 0.50),
    "SC1": ("Σκωτία Championship", 0.56),
    "SC2": ("Σκωτία League One", 0.46),
    "SC3": ("Σκωτία League Two", 0.40),
}
# Πρωταθλήματα με μόνο αποτελέσματα + αποδόσεις κλεισίματος (football-data.co.uk/new/<code>.csv):
# μοντέλο γκολ, χωρίς σουτ/κόρνερ/κάρτες. code -> (όνομα, δύναμη, Country στο new_league_fixtures.csv, The Odds API)
NEW_LEAGUES = {
    "AUT": ("Αυστρία Bundesliga", 0.70, "Austria", "soccer_austria_bundesliga"),
    "SWZ": ("Ελβετία Super League", 0.70, "Switzerland", "soccer_switzerland_superleague"),
    "DNK": ("Δανία Superliga", 0.70, "Denmark", "soccer_denmark_superliga"),
    "NOR": ("Νορβηγία Eliteserien", 0.62, "Norway", "soccer_norway_eliteserien"),
    "SWE": ("Σουηδία Allsvenskan", 0.62, "Sweden", "soccer_sweden_allsvenskan"),
    "POL": ("Πολωνία Ekstraklasa", 0.65, "Poland", "soccer_poland_ekstraklasa"),
    "RUS": ("Ρωσία Premier League", 0.70, "Russia", "soccer_russia_premier_league"),
    "BRA": ("Βραζιλία Serie A", 0.78, "Brazil", "soccer_brazil_campeonato"),
    "ARG": ("Αργεντινή Liga Profesional", 0.72, "Argentina", "soccer_argentina_primera_division"),
    "MEX": ("Μεξικό Liga MX", 0.68, "Mexico", "soccer_mexico_ligamx"),
    "USA": ("ΗΠΑ MLS", 0.68, "USA", "soccer_usa_mls"),
    "JPN": ("Ιαπωνία J1 League", 0.64, "Japan", "soccer_japan_j_league"),
    "CHN": ("Κίνα Super League", 0.55, "China", "soccer_china_superleague"),
    "IRL": ("Ιρλανδία Premier Division", 0.48, "Ireland", "soccer_league_of_ireland"),
    "FIN": ("Φινλανδία Veikkausliiga", 0.48, "Finland", "soccer_finland_veikkausliiga"),
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

def league_strength(code):
    if code in RATING_LEAGUES:
        return RATING_LEAGUES[code][1]
    if code in NEW_LEAGUES:
        return NEW_LEAGUES[code][1]
    return DEFAULT_LEAGUE_STRENGTH


for _cid, _name, _sport, _code in (
        ("L2", "League Two", "soccer_england_league2", "E3"),
        ("NL", "National League", None, "EC"),
        ("SC1", "Σκωτία Championship", None, "SC1"),
        ("SC2", "Σκωτία League One", None, "SC2"),
        ("SC3", "Σκωτία League Two", None, "SC3")):
    COMPETITIONS[_cid] = {"name": _name, "fdorg": None, "odds": _sport, "fdcouk": _code, "paid_odds": False, "days": 7}
# Europa League: ομάδες από όλα τα πρωταθλήματα (όπως το Champions League), πρόγραμμα από The Odds API
COMPETITIONS["UEL"] = {"name": "Europa League", "fdorg": None, "odds": "soccer_uefa_europa_league", "fdcouk": None,
                       "paid_odds": False, "days": 7}
for _code, (_name, _s, _country, _sport) in NEW_LEAGUES.items():
    COMPETITIONS[_code] = {"name": _name, "fdorg": None, "odds": _sport, "fdcouk": _code, "paid_odds": False,
                           "days": 7, "goals_only": True}

# Μπάσκετ (ξεχωριστό μοντέλο: engine/basket.py)
BASKET = {"EL": {"name": "EuroLeague", "feed": "E", "odds": "basketball_euroleague"},
          "EC": {"name": "EuroCup", "feed": "U", "odds": None},
          # NBA: πρόγραμμα, σκορ, παίκτες και αποδόσεις DraftKings από την ESPN (δωρεάν, χωρίς credits)
          "GBL": {"name": "Basket League", "src": "esake", "odds": None, "days": 7,
                  "players_src": "Basket League (επίσημα στατιστικά ΕΣΑΚΕ, τελευταίοι 10 αγώνες)"},
          "BCL": {"name": "Basketball Champions League", "src": "bcl", "odds": None, "days": 7, "min_games": 30},
          "NBA": {"name": "NBA", "src": "espn", "odds": None, "days": 3,
                  "players_src": "NBA (ESPN, τελευταίοι 10 αγώνες)"}}
ODDS_WINDOW_HOURS = 36   # αποδόσεις ζητάμε μόνο αν υπάρχει αγώνας μέσα σε τόσες ώρες (εξοικονόμηση credits)

# Παράγοντες πέρα από τη δύναμη (engine/context_research.py, 26.472 αγώνες 2022-26, έλεγχος στο 2025/26).
# Λογιστικοί συντελεστές πάνω στην πιθανότητα της αγοράς. Ό,τι δεν πέρασε τον έλεγχο ΔΕΝ μπαίνει εδώ
# (σκληρό παιχνίδι, "ίδιο στυλ", αέρας, κρύο, νέος προπονητής από το καλοκαίρι, λάσπη -> ισοπαλία/αουτσάιντερ).
CTX_COEF = {"tempo": 0.509, "diff_ov": 0.139, "mud": 0.095, "diff_fav": 0.186, "coach": -0.079,
            "diff_mean": 0.255, "mud_mean": 0.406}  # μέσες τιμές (κεντράρισμα: ο μέσος αγώνας δεν αλλάζει)
CTX_SHRINK = 0.7          # προσοχή: δοκιμάστηκαν ~20 παράγοντες, κρατάμε το 70% της επίδρασης
WEATHER_LEAGUES = ["E0", "E1", "E2", "E3", "EC"]
DAYS_AHEAD = 10          # πόσες μέρες μπροστά κοιτάμε αγώνες
HALF_LIFE_DAYS = 90      # πόσο γρήγορα "ξεχνάμε" παλιά παιχνίδια
PRIOR_MATCHES = 4        # συρρίκνωση προς τον μέσο όρο (σταθερότητα στην αρχή της σεζόν)
XG_WEIGHT = 0.65         # μείγμα xG / γκολ για την επιθετική/αμυντική ισχύ
# βάρος μοντέλου έναντι της αγοράς (Pinnacle / διάμεσος) στα αναμενόμενα γκολ.
# Έρευνα σε 16.450 αγώνες, 17 πρωταθλήματα (engine/research.py): η ακρίβεια (log-loss) ήταν καλύτερη
# ΧΩΡΙΣ το μοντέλο (0.8323) και χειροτέρευε όσο αυξανόταν το βάρος (0.1: 0.8330, 0.2: 0.8339).
# Οι αποδόσεις περιέχουν ήδη ό,τι ξέρουν τα στατιστικά μας. Το μοντέλο μένει για αγορές/πρωταθλήματα χωρίς αποδόσεις.
MODEL_WEIGHT = 0.0
MIN_EDGE = 0.03          # ελάχιστο +EV για να χαρακτηριστεί value (3%)
MIN_ODDS, MAX_ODDS = 1.30, 4.50
SOLID_MIN_PROB = 0.58   # "λογικές επιλογές" όταν δεν υπάρχει value

# The Odds API: κάθε κλήση κοστίζει (αγορές × περιοχές) credits. Δωρεάν: 500/μήνα.
ODDS_REGIONS = "eu"
ODDS_MARKETS = "h2h,totals,spreads"
ODDS_MIN_REMAINING = 15  # δεν καίμε τα τελευταία credits
ODDS_REFRESH_HOURS = 12 # ανανέωση αποδόσεων το πολύ κάθε τόσες ώρες
