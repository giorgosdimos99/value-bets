"""Πιθανότητες για τις συνηθισμένες αγορές των στοιχηματικών + σύγκριση με αποδόσεις (value)."""
from . import config, history
from .model import pois_over

GOAL_LINES = [0.5, 1.5, 2.5, 3.5, 4.5]
# Χωρίς ±0.5: το "1 (-0.5)" είναι η νίκη του 1 και το "1 (+0.5)" είναι η διπλή ευκαιρία 1Χ (ίδιο στοίχημα με άλλο όνομα).
AH_LINES = [-2.5, -2, -1.5, -1, 0, 1, 1.5, 2, 2.5]
CORNER_LINES = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
CARD_LINES = [2.5, 3.5, 4.5, 5.5, 6.5]
SHARP = ("Pinnacle",)
VALIDATED = {"1X2", "OU2.5"}
DERIVED_RATIO = 1.045  # ελάχιστο γκανιότ ανά πλευρά στις παράγωγες αγορές όταν δεν υπάρχουν πραγματικές τιμές
# Δεν μετράνε ως "καλύτερη απόδοση": exchanges (έχουν προμήθεια) και offshore εταιρείες
NOT_A_BOOK = ("Μέγιστη", "Μέσος όρος", "Betfair", "Matchbook", "Smarkets", "Betdaq", "BetOnline",
              "GTbets", "BetAnything", "Everygame", "Suprabets", "Bovada", "MyBookie", "LowVig", "1xBet",
              "Pinnacle")  # η Pinnacle χρησιμοποιείται ως σημείο αναφοράς, δεν είναι διαθέσιμη στην Ελλάδα


def market_view(books):
    """Πιθανότητες της αγοράς χωρίς γκανιότα: Pinnacle αν υπάρχει, αλλιώς διάμεσος όλων."""
    def consensus(key, sides):
        if key in (books.get("Pinnacle") or {}) and all(s in books["Pinnacle"][key] for s in sides):
            return _devig({s: books["Pinnacle"][key][s] for s in sides})
        rows = [_devig({s: mk[key][s] for s in sides}) for b, mk in books.items()
                if key in mk and all(s in mk[key] for s in sides) and not any(x in b for x in ("Μέγιστη", "Μέσος"))]
        if not rows:
            return None
        return {s: sorted(r[s] for r in rows)[len(rows) // 2] for s in sides}
    x12 = consensus("1X2", ("1", "X", "2"))
    ou = consensus("OU2.5", ("Over", "Under"))
    return x12, ou


def _sel(group, key, side, label, pw, pp=0.0):
    return {"group": group, "key": key, "side": side, "label": label, "pw": pw, "pp": pp}


def selections(M, lc, lk):
    n = len(M)
    cells = [(i, j, M[i][j]) for i in range(n) for j in range(n)]
    ph = sum(p for i, j, p in cells if i > j)
    pd = sum(p for i, j, p in cells if i == j)
    pa = 1 - ph - pd
    out = [
        _sel("Τελικό αποτέλεσμα", "1X2", "1", "1", ph),
        _sel("Τελικό αποτέλεσμα", "1X2", "X", "X", pd),
        _sel("Τελικό αποτέλεσμα", "1X2", "2", "2", pa),
        _sel("Διπλή ευκαιρία", "DC", "1X", "1X", ph + pd),
        _sel("Διπλή ευκαιρία", "DC", "X2", "X2", pa + pd),
        _sel("Διπλή ευκαιρία", "DC", "12", "12", ph + pa),
    ]
    for L in GOAL_LINES:
        po = sum(p for i, j, p in cells if i + j > L)
        out.append(_sel("Γκολ Over/Under", f"OU{L:g}", "Over", f"Over {L:g}", po))
        out.append(_sel("Γκολ Over/Under", f"OU{L:g}", "Under", f"Under {L:g}", 1 - po))
    pb = sum(p for i, j, p in cells if i > 0 and j > 0)
    out.append(_sel("Γκολ-Γκολ", "BTTS", "Yes", "G/G", pb))
    out.append(_sel("Γκολ-Γκολ", "BTTS", "No", "N/G", 1 - pb))
    for L in AH_LINES:
        wh = sum(p for i, j, p in cells if i - j + L > 0)
        pu = sum(p for i, j, p in cells if i - j + L == 0)
        wa = 1 - wh - pu
        key = f"AH{L:+g}"
        name = "Ισοπαλία όχι στοίχημα" if L == 0 else "Ασιατικό χάντικαπ"
        lh = "1 (DNB)" if L == 0 else f"1 ({L:+g})"
        la = "2 (DNB)" if L == 0 else f"2 ({-L:+g})"
        out.append(_sel(name, key, "H", lh, wh, pu))
        out.append(_sel(name, key, "A", la, wa, pu))
    for L in (0.5, 1.5, 2.5):
        h = sum(p for i, j, p in cells if i > L)
        a = sum(p for i, j, p in cells if j > L)
        out.append(_sel("Γκολ γηπεδούχου", f"HT_OU{L:g}", "Over", f"Γηπεδούχος Over {L:g}", h))
        out.append(_sel("Γκολ γηπεδούχου", f"HT_OU{L:g}", "Under", f"Γηπεδούχος Under {L:g}", 1 - h))
        out.append(_sel("Γκολ φιλοξενούμενου", f"AT_OU{L:g}", "Over", f"Φιλοξενούμενος Over {L:g}", a))
        out.append(_sel("Γκολ φιλοξενούμενου", f"AT_OU{L:g}", "Under", f"Φιλοξενούμενος Under {L:g}", 1 - a))
    if lc is None:  # κόρνερ/κάρτες πλέον στο engine/stats.py (με διασπορά από την έρευνα)
        return out
    for L in CORNER_LINES:
        po = pois_over(lc, L)
        out.append(_sel("Κόρνερ", f"CO{L:g}", "Over", f"Κόρνερ Over {L:g}", po))
        out.append(_sel("Κόρνερ", f"CO{L:g}", "Under", f"Κόρνερ Under {L:g}", 1 - po))
    for L in CARD_LINES:
        po = pois_over(lk, L)
        out.append(_sel("Κάρτες", f"KO{L:g}", "Over", f"Κάρτες Over {L:g}", po))
        out.append(_sel("Κάρτες", f"KO{L:g}", "Under", f"Κάρτες Under {L:g}", 1 - po))
    return out


def _devig(prices):
    """Δίκαιες πιθανότητες (μέθοδος power, βλ. history._devig)."""
    keys = [k for k, v in prices.items() if v]
    if not keys:
        return {}
    return dict(zip(keys, history._devig([prices[k] for k in keys])))


def _est(s, book_view, mains, margins_tbl):
    """Εκτιμώμενη απόδοση Stoiximan/Superbet.

    1) Αν υπάρχουν αποδόσεις από κανονικές εταιρείες: ο διάμεσός τους.
    2) Αλλιώς: η πιθανότητα όπως τη "βλέπει" η αγορά, μείον το πραγματικό γκανιότ (Bet365 vs Pinnacle, 4 σεζόν).
    """
    pb, pp = book_view.get((s["key"], s["side"]), (None, s["pp"]))
    s["p_book"] = round(pb, 4) if pb is not None else None
    if len(mains) >= 2:
        v = sorted(mains)
        return round(v[len(v) // 2], 2), f"m{len(v)}"  # διάμεσος n εταιρειών
    if pb is None:
        pb = s["pw"]
    p_eff = pb / (1 - pp) if pp < 1 else pb  # ακέραια χάντικαπ: δίκαιη απόδοση = (1 - επιστροφή) / νίκη
    mk = "1X2" if s["key"] in ("1X2", "DC") else "OU"
    o = history.estimate_odds(p_eff, mk, margins_tbl)
    # Παράγωγες αγορές (γκολ ομάδας, G/G, χάντικαπ, άλλες γραμμές γκολ): οι εταιρείες κρατούν μεγαλύτερο γκανιότ από
    # ό,τι στο 1Χ2 των φαβορί. Ο πίνακας (Bet365 vs Pinnacle στο 1Χ2/O-U 2.5) έβγαζε μόλις ~2-3% στις χαμηλές αποδόσεις
    # και η εκτίμηση ήταν πιο ψηλή από αυτό που δίνουν στην πράξη. Τουλάχιστον ~4,5% ανά πλευρά.
    if o and p_eff and s["key"] not in ("1X2", "OU2.5"):
        o = max(min(o, round(1 / p_eff / DERIVED_RATIO, 2)), 1.01)
    # g = από γκανιότ, gc = από γκανιότ χωρίς καθόλου δεδομένα αγοράς (κόρνερ/κάρτες)
    return o, "gc" if s["key"][:2] in ("CO", "KO") else "g"


def price(sels, books, book_view=None, margins_tbl=None):
    """Προσθέτει σε κάθε επιλογή: τελική πιθανότητα, δίκαιη απόδοση, καλύτερη/εκτιμώμενη απόδοση, EV."""
    book_view = book_view or {}
    margins_tbl = margins_tbl or {}
    for s in sels:
        pw, pp = s["pw"], s["pp"]
        s["p"] = round(pw, 4)
        s["fair"] = round((1 - pp) / pw, 2) if pw > 0.001 else None
        best, best_book, all_odds = None, None, {}
        for b, mks in books.items():
            o = (mks.get(s["key"]) or {}).get(s["side"])
            if not o:
                continue
            all_odds[b] = o
            if any(x in b for x in NOT_A_BOOK):
                continue
            if best is None or o > best:
                best, best_book = o, b
        s["odds"] = all_odds
        s["best"], s["book"] = best, best_book
        s["ev"] = round(pw * best + pp - 1, 4) if best else None
        mains = [o for b, o in all_odds.items() if not any(x in b for x in NOT_A_BOOK)]
        s["est"], s["est_src"] = _est(s, book_view, mains, margins_tbl)
        s["est_ev"] = round(pw * s["est"] + pp - 1, 4) if s["est"] else None
        # ακέραια χάντικαπ (+1, -2...) δίνονται από κάποιες εταιρείες ως ευρωπαϊκά (χωρίς επιστροφή): όχι value
        # "κενό αγοράς" μόνο όπου το επιβεβαίωσε η έρευνα (16.450 αγώνες): 1X2 και Over/Under 2.5.
        # Σε άλλες αγορές η πιθανότητα βγαίνει από υπολογισμό (Poisson), όχι από τιμή της ίδιας αγοράς.
        # Η ισοπαλία εξαιρείται: σε 26.070 αγώνες (engine/audit_football.py) τα "value" στο Χ έχασαν -11% (211 στοιχήματα),
        # ενώ στα 1 / 2 / Over / Under πήγαν +10,6% (182). Μικρά δείγματα και τα δύο, αλλά δεν σημαδεύουμε ό,τι έχανε.
        reliable = s["key"] in VALIDATED and not (s["key"] == "1X2" and s["side"] == "X")
        s["value"] = bool(best and reliable and s["ev"] >= config.MIN_EDGE and config.MIN_ODDS <= best <= config.MAX_ODDS)
        s["pw"], s["pp"] = round(s["pw"], 4), round(s["pp"], 4)
    # Διπλή ευκαιρία χωρίς πραγματικές τιμές: οι εταιρείες τη βγάζουν από τις δύο αποδόσεις του 1Χ2 (με όλο το γκανιότ
    # και των δύο). Παλιά εκτιμούσαμε με ~2% γκανιότ και το "Όχι ισοπαλία" φαινόταν 1,40 ενώ στην πράξη δίνουν ~1,30.
    x = {s["side"]: s for s in sels if s["key"] == "1X2"}
    for s in sels:
        if s["key"] != "DC" or (s.get("est_src") or "")[:1] == "m":
            continue
        a, b = (x.get(c) for c in {"1X": "1X", "X2": "X2", "12": "12"}[s["side"]])
        ea = (a or {}).get("est")
        eb = (b or {}).get("est")
        if ea and eb:
            s["est"] = max(round(1 / (1 / ea + 1 / eb), 2), 1.01)
            s["est_ev"] = round(s["pw"] * s["est"] + s["pp"] - 1, 4)
    return sels


def solid(sels):
    """Όταν δεν υπάρχει value: οι πιο λογικές επιλογές (υψηλή πιθανότητα, απόδοση που αξίζει)."""
    c = [s for s in sels if s["p"] >= config.SOLID_MIN_PROB and s["fair"] and s["fair"] >= 1.40
         and s["group"] not in ("Διπλή ευκαιρία",)]
    c.sort(key=lambda s: -s["p"])
    return c[:4]
