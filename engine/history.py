"""Ιστορικά δεδομένα: διαιτητές, αναμετρήσεις (H2H) και πραγματικό γκανιότ των στοιχηματικών."""
import re
import unicodedata
from collections import defaultdict
from statistics import median

from . import names


def _cards(m):
    return (m["hy"] or 0) + (m["ay"] or 0) + (m["hr"] or 0) + (m["ar"] or 0)


def ref_key(name):
    """'Michael Oliver' και 'M Oliver' -> 'm oliver'."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    parts = [p for p in re.split(r"[\s.]+", s) if p]
    if not parts:
        return ""
    return f"{parts[0][0]} {parts[-1]}" if len(parts) > 1 else parts[0]


def _season(m):
    d = m.get("date") or ""
    try:
        y, mo = int(d[:4]), int(d[5:7])
    except ValueError:
        return None
    return y if mo >= 7 else y - 1


def _season_avg(ms, f):
    acc = defaultdict(lambda: [0.0, 0])
    for m in ms:
        if m.get("hy") is None:
            continue
        a = acc[(m["league"], _season(m))]
        a[0] += f(m); a[1] += 1
    return {k: v[0] / v[1] for k, v in acc.items() if v[1]}


def _rel(ms, f, savg, prior):
    """Σταθμισμένος λόγος διαιτητή / μέσος όρος σεζόν. Βάρος 0.5^(σεζόν πίσω): φέτος 1, πέρσι 0.5, πρόπερσι 0.25..."""
    seasons = [_season(m) for m in ms]
    last = max((s for s in seasons if s is not None), default=None)
    if last is None:
        return 1.0
    num = den = 0.0
    for m, s in zip(ms, seasons):
        avg = savg.get((m["league"], s))
        if s is None or not avg or m.get("hy") is None:
            continue
        w = 0.5 ** (last - s)
        num += w * f(m) / avg
        den += w
    return round((num + prior) / (den + prior), 3)


def referees(all_matches):
    """Στατιστικά ανά διαιτητή (όλες οι σεζόν που έχουμε, ανά πρωτάθλημα)."""
    by = defaultdict(list)
    for m in all_matches:
        if m.get("ref") and m["hy"] is not None:
            by[(m["league"], ref_key(m["ref"]))].append(m)
    league_avg = defaultdict(list)
    for m in all_matches:
        if m["hy"] is not None:
            league_avg[m["league"]].append(_cards(m))
    lavg = {k: sum(v) / len(v) for k, v in league_avg.items()}
    lf = defaultdict(list)
    for m in all_matches:
        if m.get("hf") is not None and m.get("af") is not None:
            lf[m["league"]].append(m["hf"] + m["af"])
    lfav = {k: sum(v) / len(v) for k, v in lf.items()}
    # μέσοι όροι ανά πρωτάθλημα ΚΑΙ σεζόν (οι κάρτες/φάουλ αλλάζουν από χρονιά σε χρονιά)
    savg, sfav = _season_avg(all_matches, _cards), _season_avg(
        [m for m in all_matches if m.get("hf") is not None and m.get("af") is not None], lambda m: m["hf"] + m["af"])
    out = {}
    for (lg, key), ms in by.items():
        n = len(ms)
        c = [_cards(m) for m in ms]
        fouls = [m["hf"] + m["af"] for m in ms if m.get("hf") is not None and m.get("af") is not None]
        avg = sum(c) / n
        out[(lg, key)] = {
            "name": ms[-1]["ref"], "league": lg, "n": n,
            "cards": round(avg, 2),
            "yellow": round(sum((m["hy"] or 0) + (m["ay"] or 0) for m in ms) / n, 2),
            "reds": round(sum((m["hr"] or 0) + (m["ar"] or 0) for m in ms) / n, 3),
            "home_cards": round(sum((m["hy"] or 0) + (m["hr"] or 0) for m in ms) / n, 2),
            "away_cards": round(sum((m["ay"] or 0) + (m["ar"] or 0) for m in ms) / n, 2),
            "fouls": round(sum(fouls) / len(fouls), 1) if fouls else None,
            "o35": round(sum(1 for x in c if x > 3.5) / n, 3),
            "o45": round(sum(1 for x in c if x > 4.5) / n, 3),
            "home_win": round(sum(1 for m in ms if m["hg"] > m["ag"]) / n, 3),
            "goals": round(sum(m["hg"] + m["ag"] for m in ms) / n, 2),
            "league_cards": round(lavg[lg], 2),
            # συντελεστής με συρρίκνωση (λίγα ματς -> πιο κοντά στο 1). Κάθε αγώνας συγκρίνεται με τον μέσο όρο
            # της ΙΔΙΑΣ σεζόν του πρωταθλήματος, και οι πρόσφατοι αγώνες μετράνε περισσότερο (μισό βάρος ανά σεζόν).
            "factor": _rel(ms, _cards, savg, 8),
            "ffactor": _rel([m for m in ms if m.get("hf") is not None and m.get("af") is not None],
                            lambda m: m["hf"] + m["af"], sfav, 8) if fouls else None,
        }
    return out


def find_referee(name, refs, league=None):
    key = ref_key(name)
    if not key:
        return None
    if league and (league, key) in refs:
        return refs[(league, key)]
    cands = [v for (lg, k), v in refs.items() if k == key]
    return max(cands, key=lambda v: v["n"]) if cands else None


def h2h(home, away, all_matches, limit=6):
    nh, na = names.norm(home), names.norm(away)
    ms = [m for m in all_matches if {names.norm(m["home"]), names.norm(m["away"])} == {nh, na}]
    ms.sort(key=lambda m: m["date"] or "", reverse=True)
    return [{
        "date": m["date"][:10], "home": m["home"], "away": m["away"], "score": f"{int(m['hg'])}-{int(m['ag'])}",
        "corners": (m["hc"] + m["ac"]) if m["hc"] is not None and m["ac"] is not None else None,
        "cards": _cards(m) if m["hy"] is not None else None,
    } for m in ms[:limit]]


# ---------------- γκανιότ στοιχηματικών (από πραγματικές αποδόσεις Bet365 vs Pinnacle) ----------------

BUCKETS = [1.0, 1.5, 2.0, 2.5, 3.5, 5.0, 8.0, 99]


def _bucket(fair):
    for i in range(len(BUCKETS) - 1):
        if BUCKETS[i] <= fair < BUCKETS[i + 1]:
            return i
    return len(BUCKETS) - 2


def _devig(prices):
    """Αφαίρεση γκανιότ με τη μέθοδο "power": p_i = (1/απόδοση_i)^k με Σp = 1.

    Σε 16.450 αγώνες (έρευνα) είχε το μικρότερο σφάλμα βαθμονόμησης (0,39 μονάδες έναντι 0,64 της
    αναλογικής): η αναλογική υποτιμά τα φαβορί και υπερεκτιμά τα αουτσάιντερ.
    """
    inv = [1 / p for p in prices]
    if sum(inv) <= 1:
        s = sum(inv)
        return [x / s for x in inv]
    lo, hi = 1.0, 3.0
    for _ in range(40):
        k = (lo + hi) / 2
        if sum(x ** k for x in inv) > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    out = [x ** k for x in inv]
    s = sum(out)
    return [x / s for x in out]


def margins(all_matches):
    """Πόσο κάτω από τη δίκαιη απόδοση δίνει μια "μαλακή" εταιρεία (Bet365), ανά αγορά και εύρος απόδοσης.

    ratio = (1 / απόδοση Bet365) / δίκαιη πιθανότητα Pinnacle. Π.χ. 1.06 => η απόδοση είναι ~6% χαμηλότερη.
    """
    r = {"1X2": defaultdict(list), "OU": defaultdict(list)}
    over = {"1X2": [], "OU": []}
    for m in all_matches:
        o = m.get("odds") or {}
        if o.get("b1x2") and o.get("p1x2"):
            fair = _devig(o["p1x2"])
            over["1X2"].append(sum(1 / x for x in o["b1x2"]) - 1)
            for b, p in zip(o["b1x2"], fair):
                r["1X2"][_bucket(1 / p)].append((1 / b) / p)
        if o.get("bou") and o.get("pou"):
            fair = _devig(o["pou"])
            over["OU"].append(sum(1 / x for x in o["bou"]) - 1)
            for b, p in zip(o["bou"], fair):
                r["OU"][_bucket(1 / p)].append((1 / b) / p)
    out = {}
    for mk in r:
        out[mk] = {
            "overround": round(median(over[mk]), 4) if over[mk] else None,
            "n": len(over[mk]),
            "ratio": {str(i): round(median(v), 4) for i, v in r[mk].items() if len(v) >= 30},
        }
    return out


def estimate_odds(p, market, margins_tbl):
    """Εκτιμώμενη απόδοση μιας ελληνικής/μαλακής εταιρείας για δίκαιη πιθανότητα p."""
    if not p or p <= 0:
        return None
    fair = 1 / p
    tbl = margins_tbl.get(market) or margins_tbl.get("OU") or {}
    ratio = tbl.get("ratio", {}).get(str(_bucket(fair)))
    if ratio is None:
        ratio = 1 + (tbl.get("overround") or 0.06) / 2
    return max(round(fair / ratio, 2), 1.01)  # καμία εταιρεία δεν δίνει κάτω από 1.01
