"""Επίσημη αναφορά τραυματισμών EuroLeague / EuroCup (όπως τη δημοσιεύει η διοργάνωση πριν από κάθε αγωνιστική).

Πηγή: τα άρθρα «Injury report» της Euroleague Basketball, από το ίδιο επίσημο feed (Incrowd) που δίνει και το
πρόγραμμα. Το κείμενο είναι ελεύθερο («X and Y are ruled out, while Z is a game-day decision»), οπότε:
κάθε πρόταση -> ποιοι παίκτες της λίγκας αναφέρονται -> κατάσταση από λέξεις-κλειδιά (εκτός / αμφίβολος / διαθέσιμος).
Ό,τι δεν αναγνωρίζεται καθαρά αγνοείται (τότε ισχύει ο παλιός κανόνας: «έλειψε στον τελευταίο αγώνα»).
"""
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from . import sources

API = "https://article-cms-api.incrowdsports.com/v2/articles"
OUT = ("ruled out", "will miss", "is out", "are out", "remains out", "remain out", "still out", "out for", "out until", "out with",
       "out at least", "be out", "sidelined", "will not play", "won't play", "not play", "unavailable", "not available",
       "did not travel", "not travel", "will not be available", "not been registered", "season-ending", "underwent surgery",
       "has not played since", "all out", "also out", "both out", "is expected to miss", "expected to miss", "misses")
DOUBT = ("game-day decision", "game day decision", "game-time decision", "game-time call", "game-day call", "game time", "questionable", "doubtful", "uncertain", "day-to-day",
         "will be evaluated", "to be evaluated", "in doubt", "probable")
BACK = ("is back", "are back", "back in", "returns", "return to", "returned", "available", "cleared", "is ready", "are ready",
        "will play", "expected to play", "has recovered", "have recovered", "could debut", "registered")
NEG_BACK = ("not available", "unavailable", "not been registered", "will not be available")


def _n(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9' -]+", " ", s)


def latest(kind):
    """Το πιο πρόσφατο άρθρο αναφοράς τραυματισμών. kind: "EL" ή "EC". Επιστρέφει (ημερομηνία δημοσίευσης, κείμενο) ή None."""
    key = f"injury_report_{kind}.json"
    hit = sources._cached(key, 2)
    if hit is not None:
        return hit or None
    try:
        raw, _ = sources._get(f"{API}?clientId=EUROLEAGUE&size=100", headers={"User-Agent": "Mozilla/5.0"})
        arts = json.loads(raw)["data"]["articles"]
        cand = []
        for a in arts:
            slug = a.get("slug", "")
            title = ((a.get("heroMedia") or {}).get("title") or "").lower()
            if "injury-report" not in slug and "injury report" not in title:
                continue
            is_ec = bool(re.search(r"ec\d{4}|eurocup", slug))
            if is_ec == (kind == "EC"):
                cand.append(a)
        if not cand:
            sources._save_cache(key, [])
            return None
        a = max(cand, key=lambda a: a["publishDate"])
        raw, _ = sources._get(f"{API}/slug/{a['slug']}?clientId=EUROLEAGUE", headers={"User-Agent": "Mozilla/5.0"})
        art = json.loads(raw)["data"]["article"]
        text = "\n".join(b["content"] for b in art.get("content", []) if b.get("contentType") == "TEXT" and b.get("content"))
        out = [a["publishDate"], text, a["slug"]]
    except Exception as e:
        print(f"  ! αναφορά τραυματισμών {kind}: {e}")
        return sources._cached(key, 0, stale_ok=True) or None
    sources._save_cache(key, out)
    return out


def _sentences(text, only_injuries):
    """Κομμάτια κειμένου με ένα «νόημα» το καθένα. EuroCup: μόνο οι παράγραφοι **Injuries:** (το υπόλοιπο είναι δηλώσεις)."""
    if only_injuries:
        parts = re.findall(r"\*\*Injuries:?\*\*:?(.*?)(?=\n#|\n\*\*|\Z)", text, flags=re.S | re.I)
        text = "\n".join(parts)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)      # σύνδεσμοι markdown -> κείμενο
    text = re.sub(r"^#+ .*$", "\n", text, flags=re.M)          # επικεφαλίδες
    out = []
    for line in re.split(r"\n+|(?<=[.!?])\s+(?=[A-Z-])", text):
        # «οι Α και Β λείπουν, ενώ ο Γ είναι αμφίβολος» -> δύο κομμάτια
        for piece in re.split(r",?\s+while\s+|;\s+|,\s+but\s+|\s+but\s+", line):
            piece = piece.strip(" -*\t")
            if len(piece) > 8:
                out.append(piece)
    return out


def _status(sentence):
    s = " " + _n(sentence) + " "
    if any(k in s for k in OUT):
        return "out"
    if any(k in s for k in DOUBT):
        return "doubt"
    if any(k in s for k in BACK) and not any(k in s for k in NEG_BACK):
        return "ok"
    return None


def report(kind, players):
    """{όνομα παίκτη (όπως στα boxscores): {"status": out/doubt/ok, "note": πρόταση}} + ημερομηνία αναφοράς.
    players: όλα τα ονόματα της λίγκας από τα boxscores ("LAST, FIRST")."""
    got = latest(kind)
    if not got:
        return {}, None
    published, text = got[0], got[1]
    idx = []
    lasts = {}
    for p in players:
        last, _, first = p.partition(", ")
        ln, fn = _n(last).strip(), _n(first).strip()
        if len(ln) < 3:
            continue
        lasts[ln] = lasts.get(ln, 0) + 1
        idx.append((p, ln, fn))
    out = {}
    pieces = []
    for sent in _sentences(text, kind == "EC"):
        n = " " + _n(sent) + " "
        kinds = sum(1 for ks in (OUT, DOUBT) if any(k in n for k in ks))
        # «ο Α είναι εκτός και ο Β αμφίβολος» στην ίδια πρόταση -> χωριστά κομμάτια
        pieces += [(c, sent) for c in re.split(r"\s+and\s+", sent)] if kinds > 1 else [(sent, sent)]
    for piece, sent in pieces:
        st = _status(piece)
        if not st:
            continue
        s = " " + _n(piece) + " "
        found = []
        for p, ln, fn in idx:  # πρώτα ονοματεπώνυμα («Bryant Dunston»), και βγαίνουν από το κείμενο
            f0 = fn.split()[0] if fn else ""
            if f0 and re.search(rf"(?<![a-z]){re.escape(f0)}\s+{re.escape(ln)}(?![a-z])", s):
                found.append(p)
                s = re.sub(rf"(?<![a-z]){re.escape(f0)}\s+{re.escape(ln)}(?![a-z])", " # ", s)
        for p, ln, fn in idx:  # μετά σκέτα επώνυμα, μόνο αν είναι μοναδικά στη λίγκα και όχι πολύ μικρά
            if p not in found and lasts[ln] == 1 and len(ln) >= 5 and re.search(rf"(?<![a-z]){re.escape(ln)}(?![a-z])", s):
                found.append(p)
        for p in found:
            # η πρώτη αναφορά είναι η δήλωση της ομάδας για αυτόν τον αγώνα· οι επόμενες είναι παλιότερο ιστορικό
            out.setdefault(p, {"status": st, "note": sent[:160]})
    return out, published


def applies(published, game_date):
    """Η αναφορά αφορά αγώνες από 1 μέρα πριν έως 4 μέρες μετά τη δημοσίευσή της."""
    if not published:
        return False
    p = datetime.fromisoformat(published.replace("Z", "+00:00"))
    g = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
    if g.tzinfo is None:
        g = g.replace(tzinfo=timezone.utc)
    return p - timedelta(days=1) <= g <= p + timedelta(days=4)
