"""Έρευνα 3 (παίκτες): έδρα και φόρμα.  python -m engine.props_research3

Για κάθε εμφάνιση (πρόβλεψη μόνο με προηγούμενους αγώνες):
 - έδρα: πόσο καλύτερα/χειρότερα (ανά λεπτό) πάει ο παίκτης σε αγώνες σαν τον σημερινό (εντός ή εκτός) σε σχέση με όλους,
 - φόρμα: ρυθμός στους 5 τελευταίους αγώνες σε σχέση με τους 15.
Ερώτημα: εξηγούν κάτι από το λάθος της τωρινής πρόβλεψης; (συντελεστής στο πρώτο 60% των ημερομηνιών, έλεγχος στο τελευταίο 40%)
Θετικός συντελεστής = «συνεχίζει έτσι», αρνητικός = «γυρίζει στον μέσο όρο του».
"""
import json

from . import config, props
from .props_research2 import STATS, load, ols, split


def collect(cid):
    games, box = load(cid)
    home_of = {(g["home"], g["date"]): 1 for g in games}
    M = props.Model(games, box)
    rows = []
    for date, player, team, opp, mins, v in M.logs:
        pr = M.predict(player, team, opp, date)
        if not pr:
            continue
        P, m_exp = pr
        h = [e for e in M.by_player.get((player, team), []) if e[0][:10] < date[:10]][-20:]
        is_home = home_of.get((team, date), 0)
        same = [e for e in h if home_of.get((team, e[0]), 0) == is_home]
        other = [e for e in h if home_of.get((team, e[0]), 0) != is_home]
        l5, l15 = h[-5:], h[-15:]
        r = {"d": date[:10], "home": is_home, "s": {}}
        for k in STATS:
            def rate(L):
                m = sum(e[4] for e in L)
                return sum(e[5][k] for e in L) / m if m > 0 else None
            ra, rs, ro, r5, r15 = rate(h), rate(same), rate(other), rate(l5), rate(l15)
            if not ra or rs is None or ro is None or len(same) < 4 or len(other) < 4 or not r15 or r5 is None:
                continue
            n = len(same)
            venue = (rs - ro) / ra * n / (n + 6)          # συρρίκνωση: λίγοι αγώνες -> προς το 0
            form = (r5 - r15) / r15
            r["s"][k] = {"mu": P[k][0], "x": v[k], "venue": max(min(venue, 1.5), -1.5), "form": max(min(form, 1.5), -1.5)}
        rows.append(r)
    return rows


def main():
    out = {}
    for cid in ("EL", "NBA", "EC", "GBL"):
        rows = collect(cid)
        tr, te = split(rows)
        out[cid] = {}
        print(f"{cid}: {len(rows)} εμφανίσεις")
        for k in STATS:
            A = [r["s"][k] for r in tr if k in r["s"] and r["s"][k]["mu"] > 0.3]
            B = [r["s"][k] for r in te if k in r["s"] and r["s"][k]["mu"] > 0.3]
            if len(A) < 300 or len(B) < 200:
                continue
            beta, z = ols([[s["venue"], s["form"]] for s in A], [s["x"] / s["mu"] - 1 for s in A])
            f = lambda s, b=beta: max(1 + b[1] * s["venue"] + b[2] * s["form"], 0.5)
            mae0 = sum(abs(s["x"] - s["mu"]) for s in B) / len(B)
            mae1 = sum(abs(s["x"] - s["mu"] * f(s)) for s in B) / len(B)
            # γενικό πλεονέκτημα έδρας (όλοι οι παίκτες): πραγματικό/πρόβλεψη εντός έναντι εκτός
            out[cid][k] = {"venue": [round(beta[1], 3), round(z[1], 1)], "form": [round(beta[2], 3), round(z[2], 1)],
                           "mae": [round(mae0, 4), round(mae1, 4)], "n": [len(A), len(B)]}
            print(f"   {k:4s} έδρα {out[cid][k]['venue']}  φόρμα {out[cid][k]['form']}  MAE ελέγχου {mae0:.4f} -> {mae1:.4f}")
        H = [(r["home"], s["x"], s["mu"]) for r in rows for k, s in r["s"].items() if k == "pts"]
        for hv in (1, 0):
            xs = [(x, mu) for h_, x, mu in H if h_ == hv]
            if xs:
                print(f"   πόντοι {'εντός' if hv else 'εκτός'}: πραγματικό/πρόβλεψη = {sum(x for x, _ in xs) / sum(m for _, m in xs):.3f} ({len(xs)})")
        out[cid]["_home_pts"] = {str(hv): round(sum(x for h_, x, mu in H if h_ == hv) / max(sum(mu for h_, x, mu in H if h_ == hv), 1e-9), 4) for hv in (1, 0)}
    (config.DATA_OUT / "props_research3.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
