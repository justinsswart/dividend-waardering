# Contante Waarde — dividendwaardering Euronext Amsterdam

Waardeert Nederlandse aandelen op de contante waarde van hun toekomstige dividenden (DDM).

## Draaien
```
pip install yfinance pandas
python probe.py     # eenmalig: welke tickers leveren data
python fetch.py     # koersen, dividendhistorie, fundamentals
python valuate.py   # waardering + kwaliteitsscore + koopprijs
python nieuws.py    # signalen die je aannames kunnen raken (optioneel)
python build.py     # index.html
```

## Bestanden
| bestand | rol |
|---|---|
| `tickers.py` | universum: AEX, AMX, AScX, overige lokale noteringen |
| `overrides.json` | **jouw** handmatige dividendguidance per aandeel — dit is het bestand dat ertoe doet |
| `valuate.py` | het model: parameters bovenin in `P` |
| `signalen.json` | nieuws dat om herziening van een override vraagt |

## Een override toevoegen
```json
"KPN.AS": {"divs": {"2026": 0.189, "2027": 0.20}, "g_na": 0.05, "bron": "KPN CMD guidance"}
```
`divs` overschrijft het dividendpad voor die jaren, `g_na` is de groei daarna.
Zonder override schat het model de groei uit de historie (3- en 5-jaars CAGR).

## Automatisch
`.github/workflows/dagelijks.yml` draait elke werkdag om 19:30 NL en commit de nieuwe `index.html`.
Netlify publiceert die vanzelf.
