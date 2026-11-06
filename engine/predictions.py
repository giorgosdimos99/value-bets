"""Πιθανότερες προβλέψεις ανά αγώνα, με βάση τα στατιστικά (όχι μόνο value).

Από τις αγορές που δίνουν οι στοιχηματικές διαλέγουμε τις επιλογές με τη μεγαλύτερη πιθανότητα,
με εκτιμώμενη απόδοση τουλάχιστον 1.30 (για να έχει νόημα το στοίχημα), μία ανά είδος αγοράς.
"""

GROUPS = {"Τελικό αποτέλεσμα", "Διπλή ευκαιρία", "Γκολ Over/Under", "Γκολ-Γκολ", "Ισοπαλία όχι στοίχημα",
          "Ασιατικό χάντικαπ", "Γκολ γηπεδούχου", "Γκολ φιλοξενούμενου",
          "Νικητής (με παράταση)", "Χάντικαπ", "Σύνολο πόντων"}
MIN_ODDS = 1.30


def top(sels, n=3):
    cand = [s for s in sels if s["group"] in GROUPS and s.get("est") and s["est"] >= MIN_ODDS
            and (s["pp"] == 0 or s["key"] == "AH+0")]
    cand.sort(key=lambda s: -s["p"])
    out, seen = [], set()
    for s in cand:
        if s["group"] in seen:
            continue
        seen.add(s["group"])
        out.append({k: s[k] for k in ("group", "key", "side", "label", "p", "fair", "est", "est_ev", "best", "book")})
        if len(out) == n:
            break
    return out


def level(p):
    return "πολύ πιθανό" if p >= 0.70 else "πιθανό" if p >= 0.60 else "μέτριο"


def _pc(x):
    return f"{round((x or 0) * 100)}%"


def reason(t, m):
    """Σύντομη εξήγηση από τα πραγματικά στατιστικά των ομάδων."""
    hs, as_ = m.get("home_stats") or {}, m.get("away_stats") or {}
    H, A = m["home"], m["away"]
    k = t["key"]
    if m.get("sport") == "basketball":
        if k.startswith("OU"):
            return (f"Μέσο σύνολο στα ματς τους: {H} {hs.get('total', '—')}, {A} {as_.get('total', '—')}. "
                    f"Αναμενόμενο: {m['xg'][0] + m['xg'][1]:.1f}")
        return (f"{H}: {hs.get('ppg', '—')} υπέρ / {hs.get('oppg', '—')} κατά, φόρμα {hs.get('form', '—')}. "
                f"{A}: {as_.get('ppg', '—')} / {as_.get('oppg', '—')}, φόρμα {as_.get('form', '—')}")
    if not hs or not as_:
        return f"Αναμενόμενα γκολ {m['xg'][0]:.2f}–{m['xg'][1]:.2f}"
    if k.startswith("OU"):
        line = float(k[2:])
        stat = "o25" if line == 2.5 else None
        extra = f" · Over 2.5 φέτος: {H} {_pc(hs.get('o25'))}, {A} {_pc(as_.get('o25'))}" if stat else ""
        return f"Αναμενόμενα γκολ {m['xg'][0] + m['xg'][1]:.2f} (γκολ/αγώνα: {H} {hs['gf'] + hs['ga']:.1f}, {A} {as_['gf'] + as_['ga']:.1f}){extra}"
    if k == "BTTS":
        return f"G/G φέτος: {H} {_pc(hs.get('btts'))}, {A} {_pc(as_.get('btts'))} · ανέπαφη εστία: {H} {_pc(hs.get('cs'))}, {A} {_pc(as_.get('cs'))}"
    if k.startswith("HT_OU") or k.startswith("AT_OU"):
        s, team = (hs, H) if k.startswith("HT") else (as_, A)
        return f"{team}: {s.get('gf')} γκολ και {s.get('xgf')} xG ανά αγώνα · αναμενόμενα σε αυτό το ματς {m['xg'][0 if k.startswith('HT') else 1]:.2f}"
    return (f"xG υπέρ/κατά: {H} {hs.get('xgf')}/{hs.get('xga')}, {A} {as_.get('xgf')}/{as_.get('xga')} · "
            f"φόρμα {H} {hs.get('form', '—')}, {A} {as_.get('form', '—')}")


def annotate(matches):
    for m in matches:
        for t in m.get("top", []):
            t["level"] = level(t["p"])
            t["why"] = reason(t, m)
