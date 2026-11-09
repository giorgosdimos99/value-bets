"""Επιλογές παικτών μπάσκετ (πόντοι, ριμπάουντ, ασίστ, τρίποντα, κλεψίματα, κοψίματα, λάθη, φάουλ, συνδυασμοί).

Ιδέα: η εταιρεία βάζει γραμμή κοντά στον πρόσφατο μέσο όρο του παίκτη. Εμείς προσθέτουμε:
  - αναμενόμενα λεπτά (τελευταίοι 5 και 15 αγώνες),
  - ρυθμό ανά λεπτό (τελευταίοι 15),
  - αντίπαλο: πόσα δίνει αυτή η ομάδα στο συγκεκριμένο στατιστικό σε σχέση με τον μέσο όρο (με συρρίκνωση).
Έλεγχος: κάθε αγώνας της σεζόν προβλέπεται μόνο με τους προηγούμενους. Γραμμή "εταιρείας" = μέσος όρος
τελευταίων 10 αγώνων στρογγυλεμένος σε .5. Κρατάμε μόνο στατιστικά όπου το μοντέλο κερδίζει καθαρά
(ποσοστό επιτυχίας πάνω από το νεκρό σημείο της απόδοσης, με διάστημα εμπιστοσύνης).
"""
import math
from datetime import datetime

STATS = {  # κλειδί: (όνομα, στήλες στη γραμμή boxscore)
    "pts": ("Πόντοι", (2,)), "reb": ("Ριμπάουντ", (3,)), "ast": ("Ασίστ", (4,)), "tpm": ("Τρίποντα", (5,)),
    "stl": ("Κλεψίματα", (6,)), "blk": ("Κοψίματα", (9,)), "tov": ("Λάθη", (7,)), "pf": ("Φάουλ", (8,)),
    "pra": ("Πόντοι+Ριμπ.+Ασίστ", (2, 3, 4)), "pr": ("Πόντοι+Ριμπάουντ", (2, 3)),
    "pa": ("Πόντοι+Ασίστ", (2, 4)), "ra": ("Ριμπάουντ+Ασίστ", (3, 4)),
}
K_OPP = 10.0      # συρρίκνωση του αντιπάλου (αγώνες)
MIN_GAMES = 8
MIN_MINS = 18.0
VIG = 1.035       # γκανιότ ~7% στις αγορές παικτών, μοιρασμένο στις δύο πλευρές
EDGE_MIN = 0.09    # ελάχιστη διαφωνία μοντέλου με τη γραμμή (9 μονάδες πιθανότητας)
BAL = (0.40, 0.60)
PICK_MINS = 24.0   # επιλογές μόνο για βασικούς παίκτες (οι εταιρείες δεν βγάζουν αγορές για τον πάγκο)
MIN_LINE = {"tov": 1.5, "pf": 2.5, "pts": 7.5, "pra": 12.5, "pr": 10.5, "pa": 9.5, "ra": 4.5, "reb": 2.5, "ast": 1.5}  # ισορροπημένη γραμμή (απόδοση εταιρείας ~1.65-2.30)


def _val(row, k):
    return sum(row[i] for i in STATS[k][1])


def logs(games, box):
    """Λίστα εμφανίσεων: (ημερομηνία, παίκτης, ομάδα, αντίπαλος, λεπτά, {στατ: τιμή}) + ό,τι έδωσε κάθε ομάδα."""
    out, allowed = [], {}
    for g in sorted(games, key=lambda g: g["date"]):
        b = box.get(str(g["code"]))
        if not b or "home" not in b or "away" not in b:
            continue
        for side, team, opp in (("home", g["home"], g["away"]), ("away", g["away"], g["home"])):
            tot = {k: 0.0 for k in STATS}
            for r in b[side]:
                v = {k: _val(r, k) for k in STATS}
                for k in STATS:
                    tot[k] += v[k]
                out.append((g["date"], r[0], team, opp, r[1], v))
            allowed.setdefault(opp, []).append((g["date"], tot))  # ό,τι έδωσε ο αντίπαλος σε αυτή την ομάδα
    return out, allowed


def _nb_over(mu, phi, line):
    mu = max(mu, 1e-6)
    k = int(math.floor(line))
    if phi <= 1e-6:
        p, c = math.exp(-mu), 0.0
        for j in range(k + 1):
            c += p
            p *= mu / (j + 1)
        return max(0.0, 1 - c)
    r = 1 / phi
    q = mu / (r + mu)
    p = math.exp(r * math.log(r / (r + mu)))
    c = 0.0
    for j in range(k + 1):
        c += p
        p *= (j + r) / (j + 1) * q
    return max(0.0, 1 - c)


class Model:
    def __init__(self, games, box):
        self.logs, self.allowed = logs(games, box)
        self.by_player = {}
        self._cache, self._lg = {}, {}
        for e in self.logs:
            self.by_player.setdefault((e[1], e[2]), []).append(e)

    def _opp_factor(self, opp, k, before):
        key = (opp, before[:10])
        if key not in self._cache:
            lgk = before[:10]
            if lgk not in self._lg:
                lg = [t for lst in self.allowed.values() for d, t in lst if d[:10] < lgk]
                self._lg[lgk] = (len(lg), {s: sum(t[s] for t in lg) / (len(lg) or 1) for s in STATS})
            rows = [t for d, t in self.allowed.get(opp, []) if d[:10] < lgk]
            n_lg, lg_avg = self._lg[lgk]
            f = {}
            for s in STATS:
                if len(rows) < 3 or not n_lg:
                    f[s] = 1.0
                    continue
                raw = (sum(t[s] for t in rows) / len(rows)) / (lg_avg[s] or 1)
                f[s] = 1 + (raw - 1) * len(rows) / (len(rows) + K_OPP)
            self._cache[key] = f
        return self._cache[key][k]

    def predict(self, player, team, opp, before):
        """{στατ: (μ μοντέλου, μ τελευταίων 10)} ή None αν λίγα δεδομένα."""
        h = [e for e in self.by_player.get((player, team), []) if e[0][:10] < before[:10]]
        if len(h) < MIN_GAMES:
            return None
        l5, l15, l10 = h[-5:], h[-15:], h[-10:]
        m_exp = 0.6 * sum(e[4] for e in l5) / len(l5) + 0.4 * sum(e[4] for e in l15) / len(l15)
        if m_exp < MIN_MINS:
            return None
        mins15 = sum(e[4] for e in l15) or 1
        out = {}
        for k in STATS:
            rate = sum(e[5][k] for e in l15) / mins15
            mu = rate * m_exp * self._opp_factor(opp, k, before)
            out[k] = (mu, sum(e[5][k] for e in l10) / len(l10))
        return out, m_exp


def half(x):
    return math.floor(x) + 0.5


def research(games, box):
    """Κυλιόμενος έλεγχος: για κάθε στατιστικό, πόσο συχνά βγαίνει η πλευρά που προτιμά το μοντέλο στη γραμμή
    "εταιρείας" (μέσος όρος 10 αγώνων), ανά βαθμό βεβαιότητας. Επιστρέφει και τη διασπορά (phi) ανά στατιστικό."""
    M = Model(games, box)
    # 1) διασπορά από τα σφάλματα (μ.ό. 10) -> phi για Negative Binomial: Var = μ + φμ²
    res = {k: [] for k in STATS}
    for date, player, team, opp, mins, v in M.logs:
        pr = M.predict(player, team, opp, date)
        if not pr:
            continue
        P, _ = pr
        for k in STATS:
            res[k].append((P[k][0], P[k][1], v[k]))
    out = {}
    for k, rows in res.items():
        if len(rows) < 300:
            continue
        num = sum((x - mu) ** 2 - mu for mu, _, x in rows)
        den = sum(mu * mu for mu, _, x in rows)
        phi = max(num / den, 0.0) if den else 0.0
        # 2) μόνο ισορροπημένες γραμμές (όπως τις βγάζουν οι εταιρείες): P(over | μ.ό.10) 40-60%.
        #    Η εταιρεία τιμολογεί ~ με τον μ.ό.10 + γκανιότ. Το μοντέλο αξίζει μόνο αν η πλευρά του βγαίνει
        #    συχνότερα από ό,τι λέει η τιμή της εταιρείας (p_avg × 1.035 = νεκρό σημείο με ~7% γκανιότ).
        buckets = {}
        mae_m = mae_n = 0.0
        for mu, n10, x in rows:
            mae_m += abs(x - mu); mae_n += abs(x - n10)
            L = half(n10)
            pn = _nb_over(n10, phi, L)
            if not (BAL[0] <= pn <= BAL[1]):
                continue
            pm = _nb_over(mu, phi, L)
            side_over = pm >= pn
            edge = (pm - pn) if side_over else (pn - pm)
            p_avg = pn if side_over else 1 - pn
            won = (x > L) if side_over else (x < L)
            b = min(int(edge / 0.03), 4)  # 0-3, 3-6, 6-9, 9-12, 12+ μονάδες
            c = buckets.setdefault(b, [0, 0.0, 0, 0.0])
            c[0] += 1; c[1] += p_avg; c[2] += won; c[3] += p_avg + edge
        bk = []
        for b, (n, spa, w, spm) in sorted(buckets.items()):
            bk.append({"edge": round(b * 0.03, 2), "n": n, "p_avg": round(spa / n, 3), "pred": round(spm / n, 3),
                       "hit": round(w / n, 3)})
        # ελάχιστη απόκλιση από την οποία κερδίζει καθαρά: κάτω όριο διαστήματος > νεκρό σημείο
        # μόνο μεγάλες διαφωνίες (>= EDGE_MIN) ώστε να βγαίνουν λίγες, δυνατές επιλογές
        thr = None
        tail = [x for x in bk if x["edge"] >= EDGE_MIN - 1e-9]
        n = sum(x["n"] for x in tail)
        if n >= 150:
            hit = sum(x["hit"] * x["n"] for x in tail) / n
            be = sum(x["p_avg"] * x["n"] for x in tail) / n * VIG
            if hit - 1.645 * math.sqrt(hit * (1 - hit) / n) > be:
                thr = {"edge_from": EDGE_MIN, "n": n, "hit": round(hit, 3), "breakeven": round(be, 3),
                       "p_avg": round(be / VIG, 3)}
        out[k] = {"name": STATS[k][0], "phi": round(phi, 4), "n": len(rows), "mae_model": round(mae_m / len(rows), 3),
                  "mae_avg10": round(mae_n / len(rows), 3), "buckets": bk, "ok": thr}
    return out


def picks(M, check, player_rows, team, opp, before, n=3):
    """Επιλογές για τους παίκτες μιας ομάδας, μόνο σε στατιστικά που πέρασαν τον έλεγχο."""
    out = []
    for player in player_rows:
        pr = M.predict(player, team, opp, before)
        if not pr:
            continue
        P, m_exp = pr
        if m_exp < PICK_MINS:
            continue
        for k, (mu, n10) in P.items():
            c = check.get(k) or {}
            if not c.get("ok"):
                continue
            L = half(n10)
            if L < MIN_LINE.get(k, 0.5):
                continue
            pn = _nb_over(n10, c["phi"], L)
            if not (BAL[0] <= pn <= BAL[1]):
                continue
            pm = _nb_over(mu, c["phi"], L)
            side = "Over" if pm >= pn else "Under"
            edge = abs(pm - pn)
            if edge < c["ok"]["edge_from"] - 1e-9:
                continue
            p_avg = pn if side == "Over" else 1 - pn
            # πιθανότητα = ό,τι έγινε στον έλεγχο σε αυτό το επίπεδο απόκλισης (όχι η ωμή του μοντέλου)
            b = next((x for x in reversed(c["buckets"]) if edge >= x["edge"]), None)
            p_real = round(min(p_avg + edge, p_avg + max(b["hit"] - b["p_avg"], 0)) if b else p_avg + edge, 3)
            ladder = []
            for d in (-1, 0, 1):
                LL = L + d
                if LL <= 0:
                    continue
                qm = _nb_over(mu, c["phi"], LL)
                qm = qm if side == "Over" else 1 - qm
                qm -= (p_avg + edge) - p_real  # ίδια διόρθωση
                if 0.45 <= qm <= 0.8 and LL >= MIN_LINE.get(k, 0.5):
                    ladder.append({"line": LL, "p": round(qm, 3), "min_odds": round(1.03 / qm, 2)})
            out.append({"player": player, "team": team, "stat": k, "name": STATS[k][0], "side": side, "line": L,
                        "label": f"{player}: {STATS[k][0]} {side} {L:g}", "p": p_real, "p_avg": round(p_avg, 3),
                        "exp": round(mu, 1), "avg10": round(n10, 1), "mins": round(m_exp, 1),
                        "min_odds": round(1.03 / p_real, 2), "ladder": ladder,
                        "hit": c["ok"]["hit"], "n": c["ok"]["n"]})
    out.sort(key=lambda x: -(x["p"] - x["p_avg"]))
    seen, res = set(), []
    for x in out:  # το πολύ μία επιλογή ανά παίκτη
        if x["player"] in seen:
            continue
        seen.add(x["player"])
        res.append(x)
    return res[:n]
