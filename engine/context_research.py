"""Έρευνα: στυλ παιχνιδιού, δυσκολία, αλλαγή προπονητή, καιρός. Βοηθούν πέρα από τις αποδόσεις;

python -m engine.context_research

Για κάθε αγώνα 22 πρωταθλημάτων (2022/23-2025/26) υπολογίζουμε ΜΟΝΟ με ό,τι ήταν γνωστό πριν:
- στυλ κάθε ομάδας: ρυθμός (σουτ υπέρ+κατά), κυριαρχία (μερίδιο σουτ ~ κατοχή), σκληρότητα (φάουλ),
- δυσκολία: πόσο φαβορί είναι η μία ομάδα (από τις αποδόσεις),
- νέος προπονητής (Wikipedia): πρώτοι 6 αγώνες μετά από αλλαγή μέσα στη σεζόν / αρχή σεζόν με νέο,
- καιρός την ώρα του αγώνα (Open-Meteo, μόνο Αγγλία/Σκωτία): βροχή, βροχή πριν, αέρας, θερμοκρασία.
Μετά: λογιστική παλινδρόμηση με αφετηρία την πιθανότητα της αγοράς (Pinnacle χωρίς γκανιότα).
Ο παράγοντας μετράει μόνο αν βελτιώνει την πρόβλεψη στο 2025/26, που δεν χρησιμοποιήθηκε στην εκτίμηση.
"""
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta

from . import config, context, sources

SEASONS = [("2223", "2122"), ("2324", "2223"), ("2425", "2324"), ("2526", "2425")]
DISCOVER, TEST = {"2223", "2324", "2425"}, {"2526"}
UK = ["E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3"]
HL = 90
ROWS = "ctx_rows.json"


def _devig(o):
    inv = [1 / x for x in o]
    s = sum(inv)
    return [x / s for x in inv]


def _feats(past, prev, now):
    """Στυλ ομάδων από τους προηγούμενους αγώνες (βάρος: μισό κάθε 90 μέρες, περσινή σεζόν ×0.6)."""
    acc = defaultdict(lambda: defaultdict(float))
    lg = defaultdict(float)
    for ms, sf in ((past, 1.0), (prev, 0.6)):
        for m in ms:
            if m["hs"] is None or m["as"] is None or m["hf"] is None or m["hc"] is None or m["hy"] is None:
                continue
            w = sf * 0.5 ** (max((now - datetime.fromisoformat(m["date"])).days, 0) / HL)
            if w < 0.02:
                continue
            kh = m["hy"] + (m["hr"] or 0)
            ka = m["ay"] + (m["ar"] or 0)
            for t, sh, sa, fo, cf, ca, k in ((m["home"], m["hs"], m["as"], m["hf"], m["hc"], m["ac"], kh),
                                             (m["away"], m["as"], m["hs"], m["af"], m["ac"], m["hc"], ka)):
                a = acc[t]
                a["w"] += w; a["sf"] += w * sh; a["sa"] += w * sa; a["fo"] += w * fo
                a["cf"] += w * cf; a["ca"] += w * ca; a["k"] += w * k
            lg["w"] += 2 * w; lg["sh"] += w * (m["hs"] + m["as"]); lg["fo"] += w * (m["hf"] + m["af"])
            lg["co"] += w * (m["hc"] + m["ac"]); lg["k"] += w * (kh + ka)
    if lg["w"] < 30:
        return None, None
    L = {k: lg[k] / lg["w"] for k in ("sh", "fo", "co", "k")}
    P = 3.0  # σαν 3 αγώνες μέσου όρου (μικρά δείγματα -> προς τον μέσο όρο)
    out = {}
    for t, a in acc.items():
        sf = (a["sf"] + P * L["sh"]) / (a["w"] + P)
        sa = (a["sa"] + P * L["sh"]) / (a["w"] + P)
        out[t] = {"tempo": (sf + sa) / (2 * L["sh"]), "dom": sf / (sf + sa),
                  "agg": (a["fo"] + P * L["fo"]) / (a["w"] + P) / L["fo"],
                  "cf": (a["cf"] + P * L["co"]) / (a["w"] + P), "ca": (a["ca"] + P * L["co"]) / (a["w"] + P),
                  "k": (a["k"] + P * L["k"]) / (a["w"] + P), "n": a["w"]}
    return out, L


def _coach_flags(code, season, fd_teams, first_date):
    """{ομάδα: [(ημερομηνία αλλαγής, 'mid'|'pre')]}"""
    ch = context.coach_changes(code, season)
    mp = context.team_map({c["team"] for c in ch}, fd_teams)
    out = defaultdict(list)
    for c in ch:
        t = mp.get(c["team"])
        if not t:
            continue
        d = datetime.fromisoformat(c["vacancy"] + "T00:00:00+00:00")
        out[t].append((d, "mid" if d > first_date + timedelta(days=7) else "pre"))
    return out, len(ch), len(mp)


def _weather(code, season, cur):
    """{(ημερομηνία, γηπεδούχος): καιρός} για αγώνες Αγγλίας/Σκωτίας."""
    key = f"ctx_wx_{code}_{season}.json"
    hit = sources._cached(key, 24 * 365)
    if hit is not None:
        return hit
    ven = context.venues(code, season)
    mp = context.team_map(list(ven), sorted({m["home"] for m in cur}))
    city = {fd: ven[w] for w, fd in mp.items()}
    out, by_city = {}, defaultdict(list)
    for m in cur:
        if m["home"] in city:
            by_city[city[m["home"]]].append(m)
    for c, ms in by_city.items():
        ll = context.geocode(c, "GB")
        if not ll:
            print(f"    ? {c}")
            continue
        d0 = min(m["date"] for m in ms)[:10]
        d1 = max(m["date"] for m in ms)[:10]
        try:
            js = context.weather_archive(ll[0], ll[1], d0, d1, tz="Europe/London")
        except Exception as e:
            print(f"    ! καιρός {c}: {e}")
            continue
        for m in ms:
            w = context._wx(js, datetime.fromisoformat(m["date"]))
            if w:
                out[m["date"] + "|" + m["home"]] = w
    print(f"  καιρός {code} {season}: {len(out)}/{len(cur)} αγώνες, {len(city)}/{len({m['home'] for m in cur})} έδρες")
    sources._save_cache(key, out)
    return out


def collect():
    hit = sources._cached(ROWS, 24 * 30)
    if hit:
        return hit
    rows = []
    for code in config.RATING_LEAGUES:
        for season, prev_s in SEASONS:
            cur = sorted([m for m in sources.fdcouk_league(code, season) if m["date"]], key=lambda m: m["date"])
            prev = [m for m in sources.fdcouk_league(code, prev_s) if m["date"]]
            if len(cur) < 100:
                continue
            first = datetime.fromisoformat(cur[0]["date"])
            teams = sorted({m["home"] for m in cur})
            coach, nch, nmap = _coach_flags(code, season, teams, first)
            wx = _weather(code, season, cur) if code in UK else {}
            played = defaultdict(list)  # ομάδα -> ημερομηνίες αγώνων της (για "πόσοι αγώνες μετά την αλλαγή")
            for m in cur:
                played[m["home"]].append(m["date"]); played[m["away"]].append(m["date"])
            week, end = first + timedelta(days=21), datetime.fromisoformat(cur[-1]["date"])
            while week <= end:
                nxt = week + timedelta(days=7)
                todo = [m for m in cur if week <= datetime.fromisoformat(m["date"]) < nxt]
                if todo:
                    F, L = _feats([m for m in cur if datetime.fromisoformat(m["date"]) < week], prev, week)
                    for m in todo:
                        o = m["odds"]
                        f1, fo = o.get("p1x2") or o.get("a1x2"), o.get("pou") or o.get("aou")
                        if not (F and f1 and fo and m["home"] in F and m["away"] in F) or m["hc"] is None or m["hy"] is None:
                            continue
                        fh, fa = F[m["home"]], F[m["away"]]
                        d = datetime.fromisoformat(m["date"])

                        def nc(t):
                            mid = pre = 0
                            for cd, kind in coach.get(t, []):
                                if cd <= d:
                                    k = sum(1 for x in played[t] if cd.isoformat() <= x < m["date"])
                                    if k < 6:
                                        if kind == "mid":
                                            mid = 1
                                        elif k < 8:
                                            pre = 1
                            return mid, pre
                        nh, na = nc(m["home"]), nc(m["away"])
                        hg, ag = m["hg"], m["ag"]
                        rows.append({
                            "lg": code, "s": season, "pk": [round(x, 4) for x in _devig(f1) + _devig(fo)],
                            "y": [int(hg > ag), int(hg == ag), int(hg < ag), int(hg + ag > 2.5)],
                            "g": hg + ag, "co": m["hc"] + m["ac"],
                            "ca": m["hy"] + m["ay"] + (m["hr"] or 0) + (m["ar"] or 0),
                            "base_co": round(fh["cf"] * fa["ca"] / L["co"] * 2 + fa["cf"] * fh["ca"] / L["co"] * 2, 3) / 2,
                            "base_ca": round(fh["k"] + fa["k"], 3),
                            "t": [round(fh["tempo"], 3), round(fa["tempo"], 3)], "dom": [round(fh["dom"], 3), round(fa["dom"], 3)],
                            "agg": [round(fh["agg"], 3), round(fa["agg"], 3)],
                            "nc": [nh[0], na[0]], "ncp": [nh[1], na[1]],
                            "wx": wx.get(m["date"] + "|" + m["home"]),
                        })
                week = nxt
            print(f"  {code} {season}: {len(rows)} αγώνες · αλλαγές προπονητή {nch} (αντιστοιχίστηκαν ομάδες {nmap})")
    sources._save_cache(ROWS, rows)
    return rows


# ---------------- στατιστική ----------------

def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        if abs(M[i][i]) < 1e-12:
            return [0.0] * n
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                M[r] = [a - f * c for a, c in zip(M[r], M[i])]
    return [M[i][n] / M[i][i] for i in range(n)]


def logit_fit(data, ridge=1.0):
    """data: [(offset, [x...], y)] -> (β, SE). Μοντέλο: logit P = offset + α + β·x."""
    k = len(data[0][1]) + 1
    beta = [0.0] * k
    for _ in range(12):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for off, x, y in data:
            z = [1.0] + x
            p = 1 / (1 + math.exp(-(off + sum(b * v for b, v in zip(beta, z)))))
            for i in range(k):
                g[i] += (y - p) * z[i]
                for j in range(k):
                    H[i][j] += p * (1 - p) * z[i] * z[j]
        for i in range(1, k):
            g[i] -= ridge * beta[i]
            H[i][i] += ridge
        step = _solve(H, g)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    inv = [_solve(H, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
    se = [math.sqrt(max(inv[i][i], 0)) for i in range(k)]
    return beta, se


def _ll(data, beta):
    s = 0.0
    for off, x, y in data:
        p = 1 / (1 + math.exp(-(off + sum(b * v for b, v in zip(beta, [1.0] + x)))))
        p = min(max(p, 1e-9), 1 - 1e-9)
        s -= math.log(p if y else 1 - p)
    return s / len(data)


def test(name, rows, off_fn, x_fn, y_fn, labels):
    """Εκτίμηση στις σεζόν ανακάλυψης, έλεγχος στο 2025/26 (σύγκριση με την αγορά μόνη της)."""
    def make(rs):
        out = []
        for r in rs:
            x = x_fn(r)
            if x is None:
                continue
            for xi, yi, oi in zip(x if isinstance(x[0], list) else [x], y_fn(r) if isinstance(x[0], list) else [y_fn(r)],
                                  off_fn(r) if isinstance(x[0], list) else [off_fn(r)]):
                out.append((_logit(oi), xi, yi))
        return out
    D = make([r for r in rows if r["s"] in DISCOVER])
    T = make([r for r in rows if r["s"] in TEST])
    if len(D) < 200 or len(T) < 50:
        return {"name": name, "n": len(D) + len(T), "skip": True}
    b, se = logit_fit(D)
    b0, _ = logit_fit([(o, [], y) for o, _, y in D])
    llm = _ll(T, b0 + [0.0] * (len(b) - 1))  # αγορά (+ σταθερά διόρθωση)
    llf = _ll(T, b)
    ball, seall = logit_fit(D + T)
    return {"name": name, "n_disc": len(D), "n_test": len(T),
            "coef": {lab: [round(ball[i + 1], 3), round(ball[i + 1] / seall[i + 1], 1) if seall[i + 1] else None]
                     for i, lab in enumerate(labels)},
            "test_gain": round((llm - llf) * 1000, 2),  # >0: ο παράγοντας βελτιώνει την πρόβλεψη (×1000)
            "disc_coef": [round(x, 3) for x in b[1:]]}


def linear(name, rows, base_k, y_k, x_fn, labels):
    """Γραμμική: πραγματικό / αναμενόμενο - 1 ~ x. Για κόρνερ/κάρτες (δεν υπάρχουν αποδόσεις στα δεδομένα)."""
    def make(rs):
        return [(r[y_k] / r[base_k] - 1, x_fn(r)) for r in rs if r[base_k] > 0 and x_fn(r) is not None]
    D, T = make([r for r in rows if r["s"] in DISCOVER]), make([r for r in rows if r["s"] in TEST])
    k = len(D[0][1]) + 1
    A = [[sum(([1.0] + x)[i] * ([1.0] + x)[j] for _, x in D) for j in range(k)] for i in range(k)]
    bb = [sum(([1.0] + x)[i] * y for y, x in D) for i in range(k)]
    beta = _solve(A, bb)
    mse = lambda S, bt: sum((y - sum(c * v for c, v in zip(bt, [1.0] + x))) ** 2 for y, x in S) / len(S)
    base = mse(T, [beta[0]] + [0.0] * (k - 1))
    res = mse(D, beta) * len(D) / max(len(D) - k, 1)
    inv = [_solve(A, [1.0 if i == j else 0.0 for i in range(k)]) for j in range(k)]
    return {"name": name, "n_disc": len(D), "n_test": len(T),
            "coef": {lab: [round(beta[i + 1], 3), round(beta[i + 1] / math.sqrt(max(inv[i + 1][i + 1] * res, 1e-12)), 1)]
                     for i, lab in enumerate(labels)},
            "test_gain_pct": round((base - mse(T, beta)) / base * 100, 2)}


def analyse(rows):
    out = {"matches": len(rows), "created": datetime.now().isoformat(timespec="minutes"), "tests": []}
    T = out["tests"]
    ov = lambda r: r["pk"][3]
    yo = lambda r: r["y"][3]
    lt = lambda r: [math.log(r["t"][0]) + math.log(r["t"][1])]
    clash = lambda r: [(r["dom"][0] - 0.5) * (r["dom"][1] - 0.5) * 16]
    # 1. στυλ -> γκολ
    T.append(test("Ρυθμός (ανοιχτό παιχνίδι) -> Over 2.5", rows, ov, lt, yo, ["ρυθμός"]))
    T.append(test("Ίδιο στυλ (κατοχής-κατοχής / άμυνας-άμυνας) -> Over 2.5", rows, ov, clash, yo, ["ίδιο στυλ"]))
    T.append(test("Δύο αμυντικές ομάδες -> Over 2.5", rows, ov,
                  lambda r: [float(r["t"][0] < 0.93 and r["t"][1] < 0.93)], yo, ["2 αμυντικές"]))
    T.append(test("Δύο επιθετικές (γρήγορες) ομάδες -> Over 2.5", rows, ov,
                  lambda r: [float(r["t"][0] > 1.07 and r["t"][1] > 1.07)], yo, ["2 επιθετικές"]))
    T.append(test("Σκληρό παιχνίδι (φάουλ) -> Over 2.5", rows, ov, lambda r: [r["agg"][0] + r["agg"][1] - 2], yo, ["φάουλ"]))
    # 2. στυλ -> ισοπαλία / φαβορί
    T.append(test("Ίδιο στυλ -> Ισοπαλία", rows, lambda r: r["pk"][1], clash, lambda r: r["y"][1], ["ίδιο στυλ"]))
    T.append(test("Φαβορί κατοχής vs αουτσάιντερ που κλείνεται -> νίκη φαβορί", rows,
                  lambda r: max(r["pk"][0], r["pk"][2]),
                  lambda r: [((r["dom"][0] if r["pk"][0] > r["pk"][2] else r["dom"][1]) - 0.5) * 4]
                  if abs(r["pk"][0] - r["pk"][2]) > 0.2 else None,
                  lambda r: r["y"][0] if r["pk"][0] > r["pk"][2] else r["y"][2], ["κυριαρχία φαβορί"]))
    # 3. δυσκολία
    T.append(test("Δυσκολία (μεγάλο φαβορί) -> Over 2.5", rows, ov, lambda r: [abs(r["pk"][0] - r["pk"][2])], yo, ["διαφορά"]))
    T.append(test("Δυσκολία -> νίκη φαβορί", rows, lambda r: max(r["pk"][0], r["pk"][2]),
                  lambda r: [abs(r["pk"][0] - r["pk"][2])], lambda r: r["y"][0] if r["pk"][0] > r["pk"][2] else r["y"][2],
                  ["διαφορά"]))
    # 4. προπονητής (από τη μεριά της ομάδας)
    def team_rows(flag):
        def x(r):
            return [[float(r[flag][0])], [float(r[flag][1])]]
        return x
    T.append(test("Νέος προπονητής μέσα στη σεζόν (6 πρώτοι αγώνες) -> νίκη ομάδας", rows,
                  lambda r: [r["pk"][0], r["pk"][2]], team_rows("nc"), lambda r: [r["y"][0], r["y"][2]], ["νέος προπονητής"]))
    T.append(test("Νέος προπονητής από το καλοκαίρι (8 πρώτοι αγώνες) -> νίκη ομάδας", rows,
                  lambda r: [r["pk"][0], r["pk"][2]], team_rows("ncp"), lambda r: [r["y"][0], r["y"][2]], ["νέος (καλοκαίρι)"]))
    T.append(test("Νέος προπονητής μέσα στη σεζόν -> Over 2.5", rows, ov,
                  lambda r: [float(r["nc"][0] or r["nc"][1])], yo, ["νέος προπονητής"]))
    # 5. καιρός (Αγγλία/Σκωτία)
    wx = [r for r in rows if r.get("wx")]
    out["weather_n"] = len(wx)
    if wx:
        T.append(test("Βροχή στον αγώνα (mm) -> Over 2.5", wx, ov, lambda r: [math.log1p(r["wx"]["rain"])], yo, ["βροχή"]))
        T.append(test("Δυνατή βροχή (≥3 mm) -> Over 2.5", wx, ov, lambda r: [float(r["wx"]["rain"] >= 3)], yo, ["δυνατή βροχή"]))
        T.append(test("Βροχή πριν τον αγώνα (λάσπη) -> Over 2.5", wx, ov,
                      lambda r: [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])], yo, ["βροχή πριν"]))
        T.append(test("Δυνατός αέρας (km/h πάνω από 25) -> Over 2.5", wx, ov,
                      lambda r: [max(r["wx"]["wind"] - 25, 0) / 10], yo, ["αέρας"]))
        T.append(test("Κρύο (<3°C) -> Over 2.5", wx, ov, lambda r: [float(r["wx"]["temp"] < 3)], yo, ["κρύο"]))
        T.append(test("Βροχή/λάσπη -> νίκη φαβορί", wx, lambda r: max(r["pk"][0], r["pk"][2]),
                      lambda r: [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])],
                      lambda r: r["y"][0] if r["pk"][0] > r["pk"][2] else r["y"][2], ["βροχή"]))
        T.append(test("Βροχή/λάσπη -> Ισοπαλία", wx, lambda r: r["pk"][1],
                      lambda r: [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])], lambda r: r["y"][1], ["βροχή"]))
        lower = [r for r in wx if r["lg"] not in ("E0", "SC0")]
        T.append(test("Βροχή/λάσπη -> Over 2.5 (μόνο μικρότερες κατηγορίες)", lower, ov,
                      lambda r: [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])], yo, ["βροχή"]))
        T.append(test("Βροχή/λάσπη -> νίκη φαβορί (μόνο μικρότερες κατηγορίες)", lower, lambda r: max(r["pk"][0], r["pk"][2]),
                      lambda r: [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])],
                      lambda r: r["y"][0] if r["pk"][0] > r["pk"][2] else r["y"][2], ["βροχή"]))
    # 6. κόρνερ / κάρτες (απέναντι στο απλό μοντέλο ομάδα × αντίπαλος)
    L = out["linear"] = []
    L.append(linear("Κόρνερ ~ ρυθμός + ίδιο στυλ", rows, "base_co", "co", lambda r: lt(r) + clash(r), ["ρυθμός", "ίδιο στυλ"]))
    L.append(linear("Κάρτες ~ φάουλ + δυσκολία", rows, "base_ca", "ca",
                    lambda r: [r["agg"][0] + r["agg"][1] - 2, abs(r["pk"][0] - r["pk"][2])], ["φάουλ", "διαφορά"]))
    if wx:
        L.append(linear("Κόρνερ ~ βροχή + αέρας", wx, "base_co", "co",
                        lambda r: [math.log1p(r["wx"]["rain"]), max(r["wx"]["wind"] - 25, 0) / 10], ["βροχή", "αέρας"]))
        L.append(linear("Κάρτες ~ βροχή", wx, "base_ca", "ca", lambda r: [math.log1p(r["wx"]["rain"] + r["wx"]["rain_before"])], ["βροχή"]))
        L.append(linear("Γκολ ~ βροχή + αέρας + κρύο (αναλογία προς τη μέση)", wx, "g_exp", "g",
                        lambda r: [math.log1p(r["wx"]["rain"]), max(r["wx"]["wind"] - 25, 0) / 10, float(r["wx"]["temp"] < 3)],
                        ["βροχή", "αέρας", "κρύο"]) if all("g_exp" in r for r in wx) else {"name": "-", "skip": True})
    return out


def main():
    rows = collect()
    res = analyse(rows)
    (config.DATA_OUT / "context_research.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in res["tests"] + res["linear"]:
        print(t)
    return res


if __name__ == "__main__":
    main()


def joint(rows):
    """Τελικοί συντελεστές (όλα τα δεδομένα), μόνο για τους παράγοντες που πέρασαν τον έλεγχο του 2025/26."""
    ov = lambda r: _logit(r["pk"][3])
    fx = lambda r: [math.log(r["t"][0]) + math.log(r["t"][1]), abs(r["pk"][0] - r["pk"][2])]
    b_ov, se_ov = logit_fit([(ov(r), fx(r), r["y"][3]) for r in rows])
    wx = [r for r in rows if r.get("wx")]
    b_rain, se_rain = logit_fit([(ov(r) + sum(b * x for b, x in zip(b_ov[1:], fx(r))),
                                  [math.log1p(r["wx"]["rain_before"] + r["wx"]["rain"])], r["y"][3]) for r in wx])
    fav = []
    for r in rows:
        hf = r["pk"][0] > r["pk"][2]
        d = abs(r["pk"][0] - r["pk"][2])
        dom = ((r["dom"][0] if hf else r["dom"][1]) - 0.5) * 4 if d > 0.2 else 0.0
        fav.append((_logit(max(r["pk"][0], r["pk"][2])), [d, dom], r["y"][0] if hf else r["y"][2]))
    b_fav, se_fav = logit_fit(fav)
    team = [(_logit(r["pk"][i]), [float(r["nc"][j])], r["y"][i]) for r in rows for i, j in ((0, 0), (2, 1))]
    b_nc, se_nc = logit_fit(team)
    z = lambda b, s: [round(x / y, 1) if y else None for x, y in zip(b[1:], s[1:])]
    return {"over": {"tempo": round(b_ov[1], 3), "diff": round(b_ov[2], 3), "z": z(b_ov, se_ov)},
            "rain": {"mud": round(b_rain[1], 3), "z": z(b_rain, se_rain), "n": len(wx)},
            "fav": {"diff": round(b_fav[1], 3), "dom": round(b_fav[2], 3), "z": z(b_fav, se_fav)},
            "coach": {"nc": round(b_nc[1], 3), "z": z(b_nc, se_nc)}}
