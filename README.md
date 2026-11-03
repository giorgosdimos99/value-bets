# Value Bets

**Online:** https://giorgosdimos99.github.io/value-bets

Προσωπική εφαρμογή για Premier League και Champions League. Δείχνει στατιστικά, πιθανότητες, δίκαιες αποδόσεις και value επιλογές, και κρατάει τα στοιχήματά σου.

## Πώς δουλεύει
- `engine/`: Python, χωρίς εξωτερικές βιβλιοθήκες.
  - `sources.py`: λήψη δεδομένων από football-data.co.uk (xG, σουτ, κόρνερ, κάρτες, αποδόσεις, χωρίς κλειδί), football-data.org (πρόγραμμα, βαθμολογίες) και The Odds API (ζωντανές αποδόσεις).
  - `model.py`: ισχύς επίθεσης/άμυνας ανά ομάδα (xG + γκολ, πιο πρόσφατα ματς μετράνε περισσότερο), υπολογισμός σκορ με Poisson / Dixon-Coles.
  - `markets.py`: 1X2, Διπλή ευκαιρία, Over/Under, G/G, Ασιατικό χάντικαπ / DNB, γκολ ομάδας, κόρνερ, κάρτες. Υπολογίζει value = πιθανότητα × απόδοση − 1.
  - `run.py`: τα ενώνει όλα και γράφει το `site/data/data.json` και το ιστορικό `history.json`.
- `site/`: το web app (στατικό, σκούρο θέμα, ελληνικά). Ανοίγει και σαν εφαρμογή στο iPhone.
- `.github/workflows/update.yml`: τρέχει αυτόματα κάθε 3 ώρες και ανεβάζει το site στο GitHub Pages.

## Τοπικά
```
python -m engine.run
python -m http.server 8765 --directory site
```
Τα κλειδιά μπαίνουν στο αρχείο `.env` (δες το `.env.example`).

## Ρυθμίσεις
Όλες είναι στο `engine/config.py`: όριο value (`MIN_EDGE`), εύρος αποδόσεων, βάρος μοντέλου/αγοράς, μέρες μπροστά κ.λπ.
