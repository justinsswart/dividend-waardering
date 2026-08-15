# Werkwijze — Dividend Waarderingsmodel

Vastgelegd 15 augustus 2026. Upload dit bestand als projectkennis, dan hoeft het proces
niet elke sessie opnieuw uitgelegd te worden.

---

## Wat dit is

Een waarderingsmodel voor Nederlandse dividendaandelen op basis van de contante waarde
van toekomstige dividenden (DDM). Draait dagelijks via GitHub Actions, publiceert naar
Netlify. Eigendom van Swart Financiële Focus.

- Repo: `github.com/justinsswart/dividend-waardering`
- Lokaal: `C:\Users\justi\dividend-waardering`
- Universum: Euronext Amsterdam — AEX, AMX, AScX en overige lokale noteringen (74 tickers met data, 55 waardeerbaar)

---

## Vaste werkafspraken

**Bestanden komen als één zip.** Claude levert `dividend-waardering.zip` met de complete
projectmap. Nooit losse bestanden — dan raakt er altijd iets zoek.

**Bijwerken gaat via het script:**
```powershell
cd "$HOME\dividend-waardering"
.\update.ps1 -Push
```
Dat pakt de nieuwste zip (ook met `(1)`, `(2)` erachter), laat `.git` en `.venv` met rust,
controleert of alle onderdelen aanwezig zijn, en pusht pas daarna. Vijf groene vinkjes =
goede versie.

**Claude pusht niet zelf.** Elke sessie draait in een schone container; tokens blijven
nergens bewaard. Wil je dat Claude direct pusht, geef dan per sessie een classic token
(`ghp_`-prefix, `repo`-scope) — en trek die daarna in. Fine-grained tokens werken niet.

**Git-identiteit staat op** `justinsswart@gmail.com` / `Justin`.

---

## Dagelijkse automatische run

`.github/workflows/dagelijks.yml`, werkdags 17:30 UTC (19:30 NL zomertijd, 18:30 winter):

```
fetch.py → agenda.py → guidance.py --verouderd → valuate.py → nieuws.py → build.py → commit
```

Netlify deployt op elke commit.

**Twee dingen die stilletjes stukgaan:**
- GitHub schakelt geplande workflows uit na 60 dagen zonder repo-activiteit. Bot-commits
  tellen daarvoor niet altijd mee. Staat er ineens niets meer in Actions → workflow → Enable.
- Workflow-rechten moeten op *Read and write* staan (Settings → Actions → General),
  anders faalt de push van de bot.

---

## Het model

Dividend per aandeel, contant gemaakt. Drie fases:

1. **Expliciet** — bekende dividenden uit `overrides.json`
2. **Groei** — historisch tempo (3- en 5-jaars CAGR), vlakt af richting eeuwige groei
3. **Eindwaarde** — Gordon, standaard 2% eeuwig

Vereist rendement via beta (7–12%). Veiligheidsmarge schaalt met de kwaliteitsscore
(payout ratio, dekking uit vrije kasstroom, nettoschuld/ebitda, dividendverlagingen sinds 2010):
score 100 → 10% marge, score 0 → 40%. **Koopprijs = contante waarde × (1 − marge).**

### Aandeleninkoop

Inkoop verlaagt het aantal aandelen, dus stijgt het dividend *per aandeel* sneller:

    g_effectief = (1 + g) / (1 − inkooprendement) − 1

**Inkoop óók als losse kasstroom optellen is dubbeltellen.** Standaard staat de schakelaar
op "bij guidance": alleen toepassen waar de groei uit een bedrijfsbron komt. Historische
dividendgroei bevat het effect van eerdere inkoop namelijk al.

Fase-1 groei mag boven het vereist rendement liggen (die fase is eindig). Alleen de eeuwige
groei moet er structureel onder blijven.

---

## `overrides.json` — het bestand dat ertoe doet

Zonder override rekent het model met geëxtrapoleerde historie. Dat is de zwakste schakel.
Drie vormen:

```json
"KPN.AS":  {"divs": {"2026": 0.20, "2027": 0.25}, "g_na": 0.05, "bron": "...", "gecheckt": "2026-08-15"}
"INGA.AS": {"payout_beleid": 0.50, "g_na": 0.04, "bron": "...", "gecheckt": "2026-08-15"}
"SHELL.AS":{"g_na": 0.04, "bron": "...", "gecheckt": "2026-08-15"}
```

- `divs` — bedrag per aandeel (KPN, Wolters Kluwer geven dit)
- `payout_beleid` — percentage × verwachte winst per aandeel (banken, verzekeraars)
- `g_na` — groeibeleid (Shell: ~4%)

**Alleen invullen wat in een bedrijfsbron staat.** Een payout-ratio uit de cijfers aflezen
en als "beleid" invoeren maakt een observatie tot een toezegging — dat is precies de fout
die het model onbetrouwbaar maakt zonder dat je het ziet.

Stand 15-08-2026: 6 ingevuld (KPN, ING, ABN AMRO, Wolters Kluwer, Shell, Ahold Delhaize),
49 op geëxtrapoleerde historie.

---

## Guidance nalopen

`agenda.py` haalt rapportagedata op en vergelijkt met het veld `gecheckt`:

| status | betekenis |
|---|---|
| actueel | nagelopen ná de laatste cijfers |
| verouderd | er zijn cijfers geweest sinds je controle |
| cijfers op komst | rapportage binnen 10 dagen |
| geschat | geen override |

```powershell
python agenda.py                  # wie heeft aandacht nodig
python guidance.py --verouderd    # scant alleen die
python toepassen.py               # toont bewijs, vraagt per bedrijf om goedkeuring
python valuate.py ; python build.py
```

**Nooit automatisch overnemen.** De extractor las ooit "~14% CAGR 2025-2027" en zette dat
als groei ná 2027 — een correcte zin, een correct getal, de verkeerde conclusie. Zonder de
bewijsregels eronder was dat onzichtbaar geweest. Daarom toont `toepassen.py` altijd de
brontekst.

`ir_bronnen.json` bevat de IR-pagina's. Ongeveer één op de zes levert bruikbare tekst;
de rest geeft 404, 403, of zet de guidance in een PDF. Nieuwe bedrijven volgen betekent:
werkende bron opzoeken en toevoegen.

---

## Bestanden

| bestand | rol |
|---|---|
| `tickers.py` | universum per index |
| `probe.py` | eenmalig: welke tickers leveren data → `ok.json` |
| `fetch.py` | koersen, dividendhistorie, fundamentals, inkoop → `raw.json` |
| `agenda.py` | rapportagekalender + guidance-status → `agenda.json` |
| `guidance.py` | leest IR-pagina's → `voorstellen.json` |
| `toepassen.py` | voorstellen goedkeuren → `overrides.json` |
| `valuate.py` | het model; parameters bovenin in `P` → `data.json` |
| `nieuws.py` | nieuwssignalen → `signalen.json` |
| `build.py` | injecteert data in `template.html` → `index.html` |
| `update.ps1` | zip ophalen, uitpakken, controleren, pushen |

---

## Bekende beperkingen

- **13 smallcaps hebben geen rapportagedata** (Acomo, Nedap, Holland Colours, Hydratec e.a.).
  Die blijven op "geschat" zonder dat de agenda ooit signaleert.
- **Eenmalige dividenden vertekenen.** MKB Nedsense, Holland Colours: de koperen stip in de
  tabel markeert uitkomsten die extreem afwijken van de koers. Negeren, niet interpreteren.
- **60–67% van de waarde zit in de eindwaarde.** Normaal voor DDM, maar het betekent dat
  tweederde van elke waardering op een aanname over de verre toekomst rust.
- **Groeibedrijven zonder dividend vallen buiten beeld.** Adyen heeft hier geen waarde —
  dat zegt niets over Adyen, alleen dat dit de verkeerde bril is.
- **Analistenconsensus voor toekomstige dividenden zit achter betaalmuren.** Vandaar het
  handmatige overridebestand.

---

## Volgende stappen

1. Guidance invullen voor de aandelen die daadwerkelijk overwogen worden
2. Werkende IR-bronnen zoeken voor de bedrijven waar de extractor nu faalt
3. Controleren of de geplande run daadwerkelijk draait (Actions, dag na opzet)
