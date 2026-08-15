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

## Rapportagekalender

`agenda.py` haalt per bedrijf de laatste en volgende rapportagedatum op en vergelijkt die
met het veld `gecheckt` in je override. Vier statussen:

| status | betekenis |
|---|---|
| actueel | guidance nagelopen ná de laatste cijfers |
| verouderd | er zijn cijfers geweest sinds je laatste controle |
| cijfers op komst | rapportage binnen 10 dagen |
| geschat | geen override — dividendpad komt uit historische groei |

Dagelijkse volgorde: `fetch → agenda → guidance --verouderd → valuate → nieuws → build`.
`guidance.py --verouderd` scant alleen bedrijven die aandacht nodig hebben, niet alle 55.

Nalopen wat er klaarstaat:
```
python agenda.py            # toont de lijst
python guidance.py --verouderd
python toepassen.py         # bewijs bekijken, per bedrijf goedkeuren
python valuate.py ; python build.py
```
Bij goedkeuring zet `toepassen.py` de datum van vandaag in `gecheckt`, waarmee de status
weer op actueel springt tot de volgende rapportage.

## Aandeleninkoop

Inkoop zet geen geld op je rekening, maar verlaagt het aantal uitstaande aandelen.
Hetzelfde dividendbedrag wordt over minder stukken verdeeld, dus groeit het dividend
**per aandeel** sneller. Daarom zit inkoop in dit model als opslag op de groeivoet:

    g_effectief = (1 + g) / (1 - inkooprendement) - 1

Inkoop *ook* als losse kasstroom optellen is dubbeltellen — dan zit hij zowel in de
teller als in de groei.

Drie standen in het dashboard:

| stand | gedrag |
|---|---|
| bij guidance | alleen waar de groei uit een override komt (standaard) |
| niet meerekenen | inkoop genegeerd |
| overal | ook bovenop historische groei — let op: die bevat eerdere inkoop al |

`netto_inkoop` komt uit het kasstroomoverzicht (Net Common Stock Issuance, anders
Repurchase Of Capital Stock), gemiddeld over drie jaar, gedeeld door de beurswaarde.
Gecapt tussen -5% (verwatering) en +10%. 57 van de 74 bedrijven hebben deze data.

De effectieve groei in fase 1 mag boven het vereist rendement liggen — die fase is
eindig. Alleen de eeuwige groei in de eindwaarde moet er structureel onder blijven.
Boven 12% samengestelde groei toont het detailpaneel een waarschuwing: zo'n tempo
volhouden bij een stijgende koers kost elk jaar meer euro's.
