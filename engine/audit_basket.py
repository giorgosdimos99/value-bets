"""Έλεγχος αξιοπιστίας (μπάσκετ): python -m engine.audit_basket

Κάθε εβδομάδα κάθε σεζόν προβλέπεται ΜΟΝΟ με ό,τι είχε παιχτεί πριν. Συγκρίνουμε ρυθμίσεις της δύναμης ομάδων:
 - συγκράτηση προς τον μέσο όρο (πόσοι "αγώνες μέσου όρου" προστίθενται σε κάθε ομάδα),
 - ημιζωή (πόσο γρήγορα ξεχνάμε), βάρος προηγούμενης σεζόν.
Μετρικές: σφάλμα διαφοράς/συνόλου πόντων, log-loss νικητή, και αν η τυπική απόκλιση που δηλώνει το μοντέλο
ταιριάζει με τα πραγματικά λάθη (λόγος = 1 σημαίνει σωστές πιθανότητες). Ξεχωριστά οι πρώτες 6 εβδομάδες της σεζόν.
"""
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import basket, config, esake, espn

VARIANTS = [(pg, hl, pw) for pg in (None, 2, 4, 6, 10, 15) for hl in (90, 180) for pw in (0.5, 0.8)]


def _d(g):
    return datetime.fromisoformat(g["date"].replace("Z", "+00:00"))


def datasets():
    out = []
    for feed, name, years in (("E", "EuroLeague", (2023, 2024, 2025)), ("U", "EuroCup", (2024, 2025))):
        for y in years:
            cur = [g for g in basket.games(feed, y) if g["played"]]
            prev = [g for g in basket.games(feed, y - 1) if g["played"]]
            if len(cur) > 100 and prev:
                out.append((f"{name} {y}", cur, prev))
    for y in (2025,):
        cur = [g for g in esake.games(y) if g["played"]]
        prev = [g for g in esake.games(y - 1) if g["played"]]
        if len(cur) > 80 and prev:
            out.append((f"Basket League {y}", cur, prev))
    # NBA 2025/26 (όλη η κανονική περίοδος από την ESPN) με το τέλος της 2024/25 ως "πέρσι"
    conv = lambda gl: [{"code": g["id"], "date": g["date"], "played": g["played"], "home": g["home"], "away": g["away"],
                        "hp": g["hp"], "ap": g["ap"], "ot": g["periods"] > 4} for g in gl if g["played"] and g["hp"] is not None]
    cur = conv(espn.days("basketball/nba", date(2025, 10, 21), date(2026, 4, 12)))
    prev = conv(espn.days("basketball/nba", date(2025, 3, 1), date(2025, 4, 13)))
    if len(cur) > 800:
        out.append(("NBA 2025", cur, prev))
    return out


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def main():
    acc = defaultdict(lambda: defaultdict(float))
    for name, cur, prev in datasets():
        cur = sorted(cur, key=lambda g: g["date"])
        start = _d(cur[0])
        week, end = start + timedelta(days=14), _d(cur[-1])
        n = 0
        while week <= end:
            nxt = week + timedelta(days=7)
            todo = [g for g in cur if week <= _d(g) < nxt]
            if todo:
                past = [g for g in cur if _d(g) < week]
                early = (week - start).days <= 56
                for v in VARIANTS:
                    pg, hl, pw = v
                    R = basket.fit(past, prev, now=week, prior_games=pg, hl=hl, prev_w=pw, sd_factor=1.0)
                    for g in todo:
                        if g["home"] not in R["att"] or g["away"] not in R["att"]:
                            continue
                        mh = R["h_avg"] * R["att"][g["home"]] * R["def"][g["away"]]
                        ma = R["a_avg"] * R["att"][g["away"]] * R["def"][g["home"]]
                        hp, ap = g["hp"], g["ap"]
                        if g.get("ot"):
                            hp, ap = hp - basket.OT_POINTS / 2, ap - basket.OT_POINTS / 2
                        em, et = (hp - ap) - (mh - ma), (hp + ap) - (mh + ma)
                        pw_ = min(max(phi((mh - ma) / R["sd_margin"]), 1e-4), 1 - 1e-4)
                        win = g["hp"] > g["ap"]
                        for tag in ("all", "early" if early else "late", name):
                            a = acc[(v, tag)]
                            a["n"] += 1; a["em2"] += em * em; a["et2"] += et * et
                            a["ll"] += -math.log(pw_ if win else 1 - pw_)
                            a["sdm2"] += R["sd_margin"] ** 2; a["sdt2"] += R["sd_total"] ** 2
                            a["eh2"] += (hp - mh) ** 2 + (ap - ma) ** 2
                n += len(todo)
            week = nxt
        print(f"  {name}: {n} αγώνες", flush=True)

    def row(v, tag):
        a = acc[(v, tag)]
        n = a["n"] or 1
        return {"n": int(a["n"]), "rmse_m": round(math.sqrt(a["em2"] / n), 2), "rmse_t": round(math.sqrt(a["et2"] / n), 2),
                "logloss": round(a["ll"] / n, 4), "sd_ratio_m": round(math.sqrt(a["em2"] / a["sdm2"]), 3) if a["sdm2"] else None,
                "sd_ratio_t": round(math.sqrt(a["et2"] / a["sdt2"]), 3) if a["sdt2"] else None,
                # τυπική απόκλιση πόντων ΜΙΑΣ ομάδας: πραγματική έναντι τύπου sqrt((sd_t²+sd_m²)/4)
                "team_sd": round(math.sqrt(a["eh2"] / (2 * n)), 2),
                "team_sd_formula": round(math.sqrt((a["et2"] + a["em2"]) / n / 4), 2),
                "team_sd_old": round(math.sqrt(a["et2"] / n) / math.sqrt(2) * 1.1, 2)}
    res = {}
    for tag in ("all", "early", "late"):
        rk = sorted(VARIANTS, key=lambda v: row(v, tag)["logloss"])
        print(f"\n== {tag} ==")
        for v in rk[:6] + [(None, 90, 0.5)]:
            print("  ", v, row(v, tag))
        res[tag] = [{"v": list(v), **row(v, tag)} for v in rk]
    names = sorted({t for (_, t) in acc if t not in ("all", "early", "late")})
    print("\nανά διοργάνωση: τωρινό (None,90,0.5) -> υποψήφια")
    for nm in names:
        print("  ", nm, row((None, 90, 0.5), nm)["logloss"], {str(v): row(v, nm)["logloss"] for v in ((4, 90, 0.5), (6, 90, 0.5), (6, 180, 0.5), (10, 180, 0.5), (10, 180, 0.8))})
    res["by_league"] = {nm: [{"v": list(v), **row(v, nm)} for v in sorted(VARIANTS, key=lambda v: row(v, nm)["logloss"])] for nm in names}
    (config.CACHE / "audit_basket.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
