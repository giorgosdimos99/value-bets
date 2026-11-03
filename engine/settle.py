"""Εκκαθάριση επιλογών με βάση το τελικό αποτέλεσμα (για το ιστορικό απόδοσης του μοντέλου)."""


def outcome(key, side, r):
    """Επιστρέφει 1 (κέρδος), 0.5 (επιστροφή), 0 (χάθηκε) ή None αν λείπουν δεδομένα."""
    hg, ag = r.get("hg"), r.get("ag")
    if hg is None or ag is None:
        return None
    if key == "1X2":
        res = "1" if hg > ag else "X" if hg == ag else "2"
        return 1 if res == side else 0
    if key == "ML":  # μπάσκετ: δεν υπάρχει ισοπαλία (παράταση)
        return 1 if (hg > ag) == (side == "H") else 0
    if key == "DC":
        res = "1" if hg > ag else "X" if hg == ag else "2"
        return 1 if res in side else 0
    if key == "BTTS":
        yes = hg > 0 and ag > 0
        return 1 if yes == (side == "Yes") else 0
    if key.startswith("AH"):
        d = hg - ag + float(key[2:])
        if side == "A":
            d = -d
        return 1 if d > 0 else 0.5 if d == 0 else 0
    for pre, total in (("HT_OU", hg), ("AT_OU", ag), ("OU", hg + ag),
                       ("CO", _sum(r, "hc", "ac")), ("KO", _cards(r))):
        if key.startswith(pre):
            if total is None:
                return None
            over = total > float(key[len(pre):])
            return 1 if over == (side == "Over") else 0
    return None


def _sum(r, a, b):
    if r.get(a) is None or r.get(b) is None:
        return None
    return r[a] + r[b]


def _cards(r):
    if r.get("hy") is None:
        return None
    return (r.get("hy") or 0) + (r.get("ay") or 0) + (r.get("hr") or 0) + (r.get("ar") or 0)
