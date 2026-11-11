"""Δεύτερος έλεγχος μακροχρόνιων: βαθμονόμηση ΜΟΝΟ στις δύσκολες αγορές (πρωταθλητής, top 4, υποβιβασμός)
ανά σημείο της σεζόν και για διάφορα sigma. python -m engine.futures_check"""
import math
from collections import defaultdict

from . import futures as F, sources
from .futures_research import SEASONS, dt

SIGMAS = (0.05, 0.10, 0.15, 0.20)
CUTS = (0.15, 0.25, 0.4, 0.6)


def main():
    ll = defaultdict(lambda: [0.0, 0])
    cal = defaultdict(lambda: [0.0, 0.0, 0])
    for code, mks in F.LEAGUES.items():
        for s, ps in SEASONS:
            cur = sorted([m for m in sources.fdcouk_league(code, s) if m["date"] and m["hg"] is not None], key=dt)
            prev = [m for m in sources.fdcouk_league(code, ps) if m["date"] and m["hg"] is not None]
            teams = sorted({m["home"] for m in cur} | {m["away"] for m in cur})
            n = len(teams)
            if len(cur) < n * (n - 1) * 0.97:
                continue
            fin = F.table(cur)
            rank = sorted(teams, key=lambda t: (-fin[t][0], -fin[t][1], -fin[t][2]))
            fpos = {t: i for i, t in enumerate(rank)}
            for cut in CUTS:
                k = int(len(cur) * cut)
                R = F.ratings(cur[:k], prev, dt(cur[k]), src="blend", hl=90)
                for sig in SIGMAS:
                    P, _, _, _ = F.simulate(teams, cur[:k], R, sigma=sig, nsim=2000, seed=k)
                    for key, _, kind, kk in mks:
                        if kk not in (1, 4, 3) and key not in ("win",):
                            continue
                        for t in teams:
                            p = min(max(F.market_p(P[t], kind, kk, n), 0.002), 0.998)
                            y = fpos[t] < kk if kind == "top" else fpos[t] >= n - kk
                            g = ll[(sig, cut, kind + str(kk))]; g[0] += -math.log(p if y else 1 - p); g[1] += 1
                            if p >= 0.5:
                                c = cal[(sig, cut, min(int(p * 10), 9))]; c[0] += p; c[1] += y; c[2] += 1
        print(" ", code, flush=True)
    for cut in CUTS:
        print(f"\n== σημείο {cut:.0%} ==")
        for sig in SIGMAS:
            row = {m: round(v[0] / v[1], 4) for (s, c, m), v in sorted(ll.items()) if s == sig and c == cut}
            print(f"  sigma {sig}: {row}  σύνολο {sum(row.values()):.4f}")
            print("     ", [(f"{b * 10}%", round(v[0] / v[2], 3), round(v[1] / v[2], 3), v[2]) for (s, c, b), v in sorted(cal.items()) if s == sig and c == cut])


if __name__ == "__main__":
    main()
