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
    "stl": ("Κλεψίματα", (6,)), "blk": ("Κοψίματα", (9,)), "tov": ("Λάθη", (7,)), "pf": ("Προσωπικά φάουλ", (8,)),
    "pra": ("Πόντοι+Ριμπ.+Ασίστ", (2, 3, 4)), "pr": ("Πόντοι+Ριμπάουντ", (2, 3)),
    "pa": ("Πόντοι+Ασίστ", (2, 4)), "ra": ("Ριμπάουντ+Ασίστ", (3, 4)),
}
K_OPP = 10.0      # συρρίκνωση του αντιπάλου (αγώνες)
ROLE_W = 0.35     # πόσο από τη διαφορά "άμυνα ανά ρόλο" κρατάμε (mode "both")
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


PROFILE = ("pts", "reb", "ast", "tpm", "blk")  # ρόλος παίκτη: τι κάνει ανά λεπτό (γκαρντ: ασίστ/τρίποντα, ψηλός: ριμπ./κοψ.)
MIN_BETA, MIN_GAMMA = 0.8, 1.5  # αντικαθίστανται από τον έλεγχο (minutes_research)


class Model:
    def __init__(self, games, box, beta=MIN_BETA, gamma=MIN_GAMMA):
        self.logs, self.allowed = logs(games, box)
        self.by_player = {}
        self._cache, self._lg = {}, {}
        self.beta, self.gamma = beta, gamma
        team_g = {}
        for e in self.logs:
            self.by_player.setdefault((e[1], e[2]), []).append(e)
            team_g.setdefault(e[2], {}).setdefault(e[0], {})[e[1]] = e[4]
        self.team_games = {t: sorted(d.items()) for t, d in team_g.items()}
        self.logs_by_tg = {}
        for e in self.logs:
            self.logs_by_tg.setdefault(e[2], []).append(e)
        self.usage = {}
        self.cap = 0.9 * max((e[4] for e in self.logs), default=40) if self.logs else 40
        # όριο αποβολής: 6 φάουλ στο NBA, 5 στη FIBA (EuroLeague, EuroCup, Basket League)
        self.foul_out = 6 if max((e[5]["pf"] for e in self.logs), default=5) >= 6 else 5
        # τυποποίηση ρόλων (μέσος/τυπική απόκλιση ανά λεπτό σε όλη τη λίγκα)
        rates = [[e[5][k] / e[4] for k in PROFILE] for e in self.logs if e[4] >= 10]
        n = len(rates) or 1
        self._mu = [sum(r[i] for r in rates) / n for i in range(len(PROFILE))]
        self._sd = [max((sum((r[i] - self._mu[i]) ** 2 for r in rates) / n) ** 0.5, 1e-6) for i in range(len(PROFILE))]
        self._plan = {}
        self.opp_mode = "team"  # έλεγχος 11/2026: "role"/"both" όχι καλύτερα από "team" σε NBA, EL, EC, GBL. "team": ό,τι δέχεται η ομάδα συνολικά, "role": ό,τι δέχεται από κάθε ρόλο (G/F/C)
        self._roles()

    ROLE_NAMES = {"G": "Γκαρντ", "F": "Φόργουορντ", "C": "Ψηλοί"}

    def _roles(self):
        """Ρόλος κάθε παίκτη από το τι κάνει ανά λεπτό: δημιουργία (ασίστ, τρίποντα) vs ψηλός (ριμπάουντ, κοψίματα).
        Τα πιο "γκαρντ" 35% των λεπτών = G, τα πιο "ψηλά" 25% = C, τα υπόλοιπα = F."""
        agg = {}
        for e in self.logs:
            a = agg.setdefault((e[1], e[2]), [0.0, 0.0, 0.0, 0.0, 0.0])
            a[0] += e[4]; a[1] += e[5]["ast"]; a[2] += e[5]["tpm"]; a[3] += e[5]["reb"]; a[4] += e[5]["blk"]
        tot = [sum(a[i] for a in agg.values()) for i in range(5)]
        if not tot[0]:
            self.role = {}
            self.role_allowed = {}
            return
        lg = [tot[i] / tot[0] for i in range(1, 5)]
        score = {}
        for key, a in agg.items():
            if a[0] < 30:
                continue
            r = [a[i] / a[0] / (lg[i - 1] or 1) for i in range(1, 5)]
            score[key] = (r[0] + 0.5 * r[1]) / 1.5 - (r[2] + 0.5 * r[3]) / 1.5
        order = sorted(score, key=lambda k: -score[k])
        mins = sum(agg[k][0] for k in order) or 1
        cum, self.role = 0.0, {}
        for k in order:
            cum += agg[k][0]
            self.role[k] = "G" if cum <= 0.35 * mins else "C" if cum > 0.75 * mins else "F"
        # ό,τι δέχεται κάθε ομάδα ανά ρόλο, ανά αγώνα
        per = {}
        for e in self.logs:
            rl = self.role.get((e[1], e[2]))
            if not rl:
                continue
            g = per.setdefault((e[3], e[0], rl), {k: 0.0 for k in STATS})
            for k in STATS:
                g[k] += e[5][k]
        self.role_allowed = {}
        for (opp, date, rl), t in per.items():
            self.role_allowed.setdefault((opp, rl), []).append((date, t))
        self._rcache, self._rlg = {}, {}

    def _role_factor(self, opp, k, role, before):
        key = (opp, role, before[:10])
        if key not in self._rcache:
            d0 = before[:10]
            lk = (role, d0)
            if lk not in self._rlg:
                rows = [t for (o, rl), lst in self.role_allowed.items() if rl == role for d, t in lst if d[:10] < d0]
                self._rlg[lk] = (len(rows), {s: sum(t[s] for t in rows) / (len(rows) or 1) for s in STATS})
            n_lg, lg = self._rlg[lk]
            rows = [t for d, t in self.role_allowed.get((opp, role), []) if d[:10] < d0]
            f = {}
            for s in STATS:
                if len(rows) < 3 or not n_lg or not lg[s]:
                    f[s] = 1.0
                    continue
                raw = (sum(t[s] for t in rows) / len(rows)) / lg[s]
                f[s] = 1 + (raw - 1) * len(rows) / (len(rows) + K_OPP)
            self._rcache[key] = f
        return self._rcache[key][k]

    def defense_view(self, team, before):
        """Πόσο δέχεται η ομάδα από κάθε ρόλο σε σχέση με τον μέσο όρο (πόντοι, ριμπάουντ, ασίστ, τρίποντα)."""
        out = {}
        for rl in ("G", "F", "C"):
            out[rl] = {k: round(self._role_factor(team, k, rl, before) - 1, 3) for k in ("pts", "reb", "ast", "tpm")}
            out[rl]["n"] = len([1 for d, t in self.role_allowed.get((team, rl), []) if d[:10] < before[:10]])
        return out

    def opp_factor(self, player, team, opp, k, before):
        if self.opp_mode == "both":
            # συνολική άμυνα × (διαφορά του ρόλου από τη συνολική, πιο συγκρατημένη)
            rl = self.role.get((player, team))
            tf = self._opp_factor(opp, k, before)
            if not rl:
                return tf
            rf = self._role_factor(opp, k, rl, before)
            return tf * (1 + ROLE_W * (rf - tf))
        if self.opp_mode == "role":
            rl = self.role.get((player, team))
            if rl:
                return self._role_factor(opp, k, rl, before)
        return self._opp_factor(opp, k, before)

    def profile(self, player, team, before):
        h = [e for e in self.by_player.get((player, team), []) if e[0][:10] < before[:10]][-15:]
        m = sum(e[4] for e in h)
        if m < 30:
            return None
        return [(sum(e[5][k] for e in h) / m - self._mu[i]) / self._sd[i] for i, k in enumerate(PROFILE)]

    def exp_minutes(self, player, team, before):
        h = [e for e in self.by_player.get((player, team), []) if e[0][:10] < before[:10]]
        if len(h) < 3:
            return None
        l5, l15 = h[-5:], h[-15:]
        return 0.6 * sum(e[4] for e in l5) / len(l5) + 0.4 * sum(e[4] for e in l15) / len(l15)

    def regulars(self, team, before, n=10):
        """Βασικοί της ροτέισον: έπαιξαν σε >=60% των τελευταίων n αγώνων της ομάδας με >=12 λεπτά."""
        tg = [g for d, g in self.team_games.get(team, []) if d[:10] < before[:10]][-n:]
        if len(tg) < 4:
            return {}, tg
        cnt = {}
        for g in tg:
            for p, mins in g.items():
                c = cnt.setdefault(p, [0, 0.0])
                c[0] += 1; c[1] += mins
        return {p: c[1] / c[0] for p, c in cnt.items() if c[0] >= max(3, 0.6 * len(tg)) and c[1] / c[0] >= 12}, tg

    def usage_plan(self, team, before, absent):
        """Πολλαπλασιαστής παραγωγής ανά λεπτό για τους παρόντες: 1 + u_k × (μερίδιο του απόντα στο στατιστικό k).
        Π.χ. λείπει ο πρώτος σκόρερ (25% των πόντων) -> οι άλλοι παίρνουν περισσότερες επιθέσεις."""
        reg, tg = self.regulars(team, before)
        absent = [a for a in absent if a in reg]
        if not absent or not tg:
            return {}
        share = {k: 0.0 for k in STATS}
        for a in absent:
            h = [e for e in self.by_player.get((a, team), []) if e[0][:10] < before[:10]][-15:]
            dates = {e[0] for e in h}
            games = [(d, g) for d, g in self.team_games.get(team, []) if d in dates]
            if not h:
                continue
            miss15 = sum(1 for g in tg[-15:] if a not in g) / max(len(tg[-15:]), 1)
            for k in STATS:
                own = sum(e[5][k] for e in h)
                tot = sum(x[5][k] for x in self.logs_by_tg.get(team, []) if x[0] in dates)
                if tot > 0:
                    share[k] += (1 - miss15) * own / tot
        return {k: 1 + self.usage.get(k, 0.0) * v for k, v in share.items()}

    def minutes_plan(self, team, before, absent):
        """Επιπλέον λεπτά για κάθε συμπαίκτη όταν λείπουν βασικοί (absent: ονόματα).

        Τα λεπτά του απόντα μοιράζονται στους παρόντες βασικούς ανάλογα με τα λεπτά τους, με περισσότερο βάρος
        σε όσους έχουν παρόμοιο ρόλο (ίδια θέση, π.χ. ψηλός για ψηλό). Αν ο απών έλειπε ήδη στους τελευταίους
        αγώνες, οι συμπαίκτες έχουν ήδη πάρει μέρος από τα λεπτά του (μετράει ήδη στον μέσο όρο τους).
        """
        key = (team, before[:10], tuple(sorted(absent)))
        if key in self._plan:
            return self._plan[key]
        reg, tg = self.regulars(team, before)
        out = {}
        absent = [a for a in absent if a in reg]
        present = [p for p in reg if p not in absent]
        if absent and present:
            base = {p: self.exp_minutes(p, team, before) or reg[p] for p in present}
            prof = {p: self.profile(p, team, before) for p in present}
            for a in absent:
                ma = self.exp_minutes(a, team, before) or reg[a]
                miss5 = sum(1 for g in tg[-5:] if a not in g)
                miss15 = sum(1 for g in tg[-15:] if a not in g)
                eff = ma * max(0.0, 1 - (0.6 * miss5 / max(len(tg[-5:]), 1) + 0.4 * miss15 / max(len(tg[-15:]), 1)))
                if eff <= 0.5:
                    continue
                pa = self.profile(a, team, before)
                w = {}
                for p in present:
                    sim = 0.0
                    if pa and prof[p]:
                        na = sum(x * x for x in pa) ** 0.5
                        nb = sum(x * x for x in prof[p]) ** 0.5
                        sim = sum(x * y for x, y in zip(pa, prof[p])) / (na * nb) if na and nb else 0.0
                    w[p] = base[p] * math.exp(self.gamma * sim)
                tw = sum(w.values()) or 1
                for p in present:
                    out[p] = out.get(p, 0.0) + self.beta * eff * w[p] / tw
            for p in out:
                out[p] = min(out[p], max(self.cap - base[p], 0.0))
        self._plan[key] = out
        return out

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

    def predict(self, player, team, opp, before, extra=0.0, mult=None):
        """{στατ: (μ μοντέλου, μ τελευταίων 10)} ή None αν λίγα δεδομένα. extra: επιπλέον λεπτά (απουσίες)."""
        h = [e for e in self.by_player.get((player, team), []) if e[0][:10] < before[:10]]
        if len(h) < MIN_GAMES:
            return None
        l5, l15, l10 = h[-5:], h[-15:], h[-10:]
        m_exp = 0.6 * sum(e[4] for e in l5) / len(l5) + 0.4 * sum(e[4] for e in l15) / len(l15) + extra
        if m_exp < MIN_MINS:
            return None
        mins15 = sum(e[4] for e in l15) or 1
        out = {}
        for k in STATS:
            rate = sum(e[5][k] for e in l15) / mins15
            mu = rate * m_exp * self.opp_factor(player, team, opp, k, before) * ((mult or {}).get(k, 1.0))
            out[k] = (mu, sum(e[5][k] for e in l10) / len(l10))
        return out, m_exp


def half(x):
    return math.floor(x) + 0.5


def _absent_in(M, team, date):
    """Βασικοί που δεν έπαιξαν σε αυτόν τον αγώνα (στην πράξη: η λίστα τραυματιών πριν τον αγώνα)."""
    g = dict(M.team_games.get(team, [])).get(date)
    if g is None:
        return []
    reg, _ = M.regulars(team, date)
    return [a for a in reg if a not in g]


def minutes_research(M):
    """Έλεγχος: όταν λείπουν βασικοί, πόσο καλύτερα προβλέπουμε τα λεπτά των υπολοίπων;
    Βρίσκει β (πόσο από τα λεπτά του απόντα μοιράζεται) και γ (πόσο μετράει ο ίδιος ρόλος)."""
    cases = []
    for team, tg in M.team_games.items():
        for date, g in tg:
            ab = _absent_in(M, team, date)
            if not ab:
                continue
            for p, mins in g.items():
                b = M.exp_minutes(p, team, date)
                if b is not None and b >= 10 and p in M.regulars(team, date)[0]:
                    cases.append((team, date, tuple(ab), p, b, mins))
    if len(cases) < 200:
        return None
    best = None
    for gamma in (0.0, 1.5, 3.0, 6.0):
        M.gamma, M.beta, M._plan = gamma, 1.0, {}
        xs = [(M.minutes_plan(t, d, list(ab)).get(p, 0.0), b, y) for t, d, ab, p, b, y in cases]
        # y - b = α + β·x  (α: γενική μεροληψία του μέσου όρου λεπτών, ίδια με ή χωρίς απουσίες)
        n = len(xs)
        mx, my = sum(x for x, _, _ in xs) / n, sum(y - b for x, b, y in xs) / n
        sxx = sum((x - mx) ** 2 for x, _, _ in xs) or 1
        beta = max(0.0, min(sum((x - mx) * (y - b - my) for x, b, y in xs) / sxx, 1.2))
        alpha = my - beta * mx
        mae = sum(abs(y - b - alpha - beta * x) for x, b, y in xs) / n
        mae0 = sum(abs(y - b - my) for x, b, y in xs) / n  # χωρίς αναδιανομή (μόνο η μεροληψία)
        if not best or mae < best["mae"]:
            boost = [(x, b, y) for x, b, y in xs if beta * x >= 3]
            best = {"gamma": gamma, "beta": round(beta, 3), "mae": round(mae, 3),
                    "mae_base": round(mae0, 3), "n": len(xs), "alpha": round(alpha, 2),
                    "boost_n": len(boost),
                    "boost_mae": round(sum(abs(y - b - alpha - beta * x) for x, b, y in boost) / len(boost), 3) if boost else None,
                    "boost_mae_base": round(sum(abs(y - b - my) for _, b, y in boost) / len(boost), 3) if boost else None,
                    "boost_gain": round(sum(y - b - alpha for _, b, y in boost) / len(boost), 2) if boost else None,
                    "boost_pred": round(sum(beta * x for x, _, _ in boost) / len(boost), 2) if boost else None}
    M.gamma, M.beta, M._plan = best["gamma"], best["beta"], {}
    # παραγωγή ανά λεπτό: u_k ώστε  πραγματικό ≈ αναμενόμενο_ρυθμού × λεπτά × r0 × (1 + u_k·μερίδιο)
    M.usage = {k: 1.0 for k in STATS}
    num, den, r0n, r0d = {k: 0.0 for k in STATS}, {k: 0.0 for k in STATS}, {k: 0.0 for k in STATS}, {k: 0.0 for k in STATS}
    byk = {(e[0], e[1], e[2]): e for e in M.logs}
    for team, tg in M.team_games.items():
        for date, g in tg:
            ab = _absent_in(M, team, date)
            sh = {k: v - 1 for k, v in M.usage_plan(team, date, ab).items()} if ab else {}
            for p, mins in g.items():
                h = [e for e in M.by_player.get((p, team), []) if e[0][:10] < date[:10]][-15:]
                m = sum(e[4] for e in h)
                if m < 100 or mins < 10:
                    continue
                e = byk[(date, p, team)]
                for k in STATS:
                    ex = sum(x[5][k] for x in h) / m * mins
                    if sh:
                        num[k] += e[5][k]; den[k] += ex; r0d[k] += ex * sh[k]
                    else:
                        r0n[k] += e[5][k]; r0n.setdefault("_" + k, 0); r0n["_" + k] += ex
    usage = {}
    for k in STATS:
        r0 = r0n[k] / r0n["_" + k] if r0n.get("_" + k) else 1.0
        usage[k] = round(max(0.0, min((num[k] / r0 - den[k]) / r0d[k], 2.0)), 3) if r0d[k] > 0 else 0.0
    M.usage = usage
    best["usage"] = usage
    return best


def research(games, box, usage_scale=None, opp_mode=None):
    """Κυλιόμενος έλεγχος: για κάθε στατιστικό, πόσο συχνά βγαίνει η πλευρά που προτιμά το μοντέλο στη γραμμή
    "εταιρείας" (μέσος όρος 10 αγώνων), ανά βαθμό βεβαιότητας. Επιστρέφει και τη διασπορά (phi) ανά στατιστικό.
    Με τις απουσίες του κάθε αγώνα (βασικοί που δεν έπαιξαν) -> επιπλέον λεπτά στους συμπαίκτες."""
    M = Model(games, box)
    if opp_mode:
        M.opp_mode = opp_mode
    mres = minutes_research(M)
    if mres and usage_scale is not None:
        mres["usage"] = {k: round(v * usage_scale, 3) for k, v in mres["usage"].items()}
        M.usage = mres["usage"]
    boost_rows = {k: [] for k in STATS}
    # 1) διασπορά από τα σφάλματα (μ.ό. 10) -> phi για Negative Binomial: Var = μ + φμ²
    res = {k: [] for k in STATS}
    for date, player, team, opp, mins, v in M.logs:
        ab = _absent_in(M, team, date) if mres else []
        extra = M.minutes_plan(team, date, ab).get(player, 0.0) if ab else 0.0
        mult = M.usage_plan(team, date, ab) if ab else None
        pr = M.predict(player, team, opp, date, extra, mult)
        if not pr:
            continue
        P, _ = pr
        for k in STATS:
            res[k].append((P[k][0], P[k][1], v[k]))
            if extra >= 2 or (mult or {}).get(k, 1) >= 1.05:
                boost_rows[k].append((P[k][0], P[k][1], v[k]))
    out = {}
    cal_num = cal_den = 0.0  # βαθμονόμηση: πόσο από τη διαφωνία μοντέλου-γραμμής επιβεβαιώνεται στην πράξη
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
            cal_num += (won - p_avg) * edge; cal_den += edge * edge
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
        # παίκτες με >=3 επιπλέον λεπτά λόγω απουσιών: πόσο συχνά βγαίνει το Over της γραμμής μ.ό. 10
        br = boost_rows[k]
        if len(br) >= 40:
            wins = [x > half(n10) for mu, n10, x in br if mu > n10]
            pavg = [_nb_over(n10, phi, half(n10)) for mu, n10, x in br if mu > n10]
            if wins:
                out[k]["boost"] = {"n": len(wins), "hit": round(sum(wins) / len(wins), 3),
                                   "p_avg": round(sum(pavg) / len(pavg), 3)}
    if mres:
        # η αύξηση παραγωγής από απουσίες μένει μόνο όπου οι "ενισχυμένοι" παίκτες πέτυχαν καθαρά πιο συχνά
        # το Over της γραμμής από ό,τι λέει η γραμμή (>= 5 μονάδες, >= 150 περιπτώσεις)
        mres["usage"] = {k: (v if (out.get(k) or {}).get("boost") and out[k]["boost"]["n"] >= 150
                             and out[k]["boost"]["hit"] - out[k]["boost"]["p_avg"] >= 0.05 else 0.0)
                         for k, v in mres["usage"].items()}
        out["_minutes"] = mres
    # κλίση 1 = η πιθανότητα του μοντέλου βγαίνει όπως τη λέει. <1 = το μοντέλο είναι πιο σίγουρο απ' ό,τι πρέπει:
    # η εφαρμογή φέρνει την πρόβλεψη τόσο πιο κοντά στον μέσο όρο των 10 αγώνων (καρτέλα Δελτίο, οποιαδήποτε γραμμή).
    out["_cal"] = round(min(max(cal_num / cal_den, 0.0), 1.0), 3) if cal_den > 0 else 1.0
    return out


def picks(M, check, player_rows, team, opp, before, n=3, absent=(), edge_min=None, by="edge"):
    """Επιλογές για τους παίκτες μιας ομάδας, μόνο σε στατιστικά που πέρασαν τον έλεγχο.
    by="edge": οι μεγαλύτερες διαφωνίες με τη γραμμή (value). by="p": οι πιθανότερες (edge_min μικρότερο).
    absent: απόντες βασικοί -> επιπλέον λεπτά στους συμπαίκτες (αν ο έλεγχος λεπτών υπάρχει)."""
    out = []
    mres = check.get("_minutes")
    if mres:
        M.beta, M.gamma, M.usage = mres["beta"], mres["gamma"], mres.get("usage", {})
    plan = M.minutes_plan(team, before, list(absent)) if absent and mres else {}
    mult = M.usage_plan(team, before, list(absent)) if absent and mres else None
    for player in player_rows:
        if player in absent:
            continue
        extra = plan.get(player, 0.0)
        pr = M.predict(player, team, opp, before, extra, mult)
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
            if L < MIN_LINE.get(k, 0.5) or (k == "pf" and L >= M.foul_out - 1):
                continue
            pn = _nb_over(n10, c["phi"], L)
            if not (BAL[0] <= pn <= BAL[1]):
                continue
            pm = _nb_over(mu, c["phi"], L)
            side = "Over" if pm >= pn else "Under"
            edge = abs(pm - pn)
            if edge < (c["ok"]["edge_from"] if edge_min is None else edge_min) - 1e-9:
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
                        "min_odds": round(1.03 / p_real, 2), "ladder": ladder, "extra": round(extra, 1),
                        "hit": c["ok"]["hit"], "n": c["ok"]["n"]})
    out.sort(key=(lambda x: -x["p"]) if by == "p" else (lambda x: -(x["p"] - x["p_avg"])))
    seen, res = set(), []
    for x in out:  # το πολύ μία επιλογή ανά παίκτη
        if x["player"] in seen:
            continue
        seen.add(x["player"])
        res.append(x)
    return res[:n]
