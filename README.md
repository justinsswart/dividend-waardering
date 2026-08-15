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

## Bijwerken vanuit een Claude-sessie

```powershell
.\update.ps1 -Push
```

Zoekt de nieuwste `dividend-waardering*.zip` in Downloads of je homefolder — ook als de
browser er `(1)`, `(2)` van heeft gemaakt — pakt hem uit over de projectmap, laat `.git`
en `.venv` met rust, controleert of de verwachte onderdelen aanwezig zijn, en pusht.

Zonder `-Push` wordt alleen uitgepakt en getoond wat er zou veranderen.
Met `-Draaien` wordt het model daarna lokaal herberekend.

## Boekjaar versus kalenderjaar

Het model telt uitkeringen per kalenderjaar (wanneer ze op je rekening staan), maar
bedrijven rapporteren per boekjaar. Het slotdividend over boekjaar X wordt pas in jaar
X+1 betaald, dus het kalenderjaartotaal is het interim van dit jaar plus het slot van
vorig jaar. Bij NN Group scheelde dat 3,54 tegen 3,88 — negen procent.

Zet het boekjaartotaal daarom vast zodra je het in de bron ziet staan:

```json
"NN.AS": {"d0_fy": 3.88, "g_na": 0.06, "bron": "...", "gecheckt": "..."}
```

`d0_fy` gaat voor op het uit de historie afgeleide bedrag en schakelt de
normalisatie voor eenmalige uitkeringen uit.

## Eigen winstmaatstaf

Verzekeraars sturen op het operationeel resultaat, niet op de IFRS-nettowinst. Die laatste
schommelt met marktwaarderingen van de beleggingsportefeuille en geeft een vals beeld van
de dividenddekking. Bij ASR stond de IFRS-winst op 2,16 tegen een dividend van 3,41 — het
model gaf daardoor onterecht een dekkingswaarschuwing, terwijl de payout op het
operationeel resultaat van 7,93 juist 43% is.

```json
"ASRNL.AS": {"d0_fy": 3.41, "wpa": 7.93, "g_na": 0.07, "bron": "...", "gecheckt": "..."}
```

`wpa` vervangt de winst per aandeel in de dekkingscontrole en de payout ratio. Alleen
gebruiken wanneer het bedrijf zelf op die maatstaf stuurt, met de bron erbij.

## Status en tijdstempel

De guidance-status wordt bij elke `valuate.py`-run opnieuw bepaald: de rapportagedata komen
uit `agenda.json`, het veld `gecheckt` uit `overrides.json`. Pas je een override aan, dan
springt de status meteen om — de trage `agenda.py` hoeft daar niet voor te draaien.

`override_log.json` houdt per aandeel een hash van de override bij. Verandert de inhoud,
dan wordt het tijdstempel `override_gewijzigd` bijgewerkt, ongeacht hoe je het bestand hebt
bewerkt. Dat tijdstempel staat in het detailpaneel onder de notitie.

Twee datums, twee betekenissen:
- **gecheckt** — de dag waarop jij de guidance tegen de bron hebt gecontroleerd (bepaalt de status)
- **override_gewijzigd** — het moment waarop de aanname feitelijk veranderde (automatisch)

## Kwaliteitsscore

Vier onderdelen vanaf een basis van 50 punten: payout ratio, dekking uit vrije kasstroom,
nettoschuld/ebitda en de verlagingshistorie. De score bepaalt de veiligheidsmarge
(100 → 10%, 0 → 40%).

Optellen alleen was niet genoeg. Een schone verlagingshistorie streek een payout van 289%
gewoon weg; UMG kwam zo op 89 uit. Daarom zetten bepaalde signalen een **plafond** op de
totaalscore, ongeacht de rest:

| signaal | plafond |
|---|---|
| payout boven 150% | 30 |
| payout boven 120% | 45 |
| payout boven de winst | 55 |
| negatieve vrije kasstroom | 25 |
| kasstroom dekt dividend niet | 50 |
| schuld boven 5x ebitda | 35 |
| dividend ooit gehalveerd | 65 |
| vier of meer verlagingen | 45 |

Verder gecorrigeerd:

- **Payout op de juiste winstmaatstaf.** Staat `wpa` in de override, dan rekent de score
  daarmee. ASR ging van een schijnbare 150% naar de werkelijke 43%.
- **Geen kasstroomcheck bij financials.** Banken en verzekeraars kennen geen zinvolle vrije
  kasstroom; die post schommelt met de beleggingsportefeuille.
- **Verlagingen tegen het niveau van meerdere jaren.** Een uitkering telt als verlaging bij
  meer dan 15% onder de mediaan van de drie voorgaande jaren, zonder herstel binnen twee
  jaar. Vergelijken met één enkel jaar telde speciale dividenden en verschoven betaaldata
  mee: KPN kwam op -95% uit, ASM op -90%, Heineken en Shell op vier verlagingen.
- **Diepte weegt mee.** Een halvering straft zwaarder dan het aantal keren. Shell scoorde
  zonder deze straf 100, terwijl het in 2020 het dividend met tweederde verlaagde.

Het aantal verlagingen kan handmatig gezet worden met `"verlagingen": n` in de override.

## Modelverbeteringen na literatuuronderzoek

Drie correcties op basis van standaardwerken over dividendwaardering (Damodaran, Stern NYU;
CFA-curriculum over de Gordon-groeimodellen):

**1. Kapitaalkosten in de eindfase.** Het model gebruikte de beta van vandaag voor de hele
horizon. Damodaran laat de beta in de stabiele fase naar 1 convergeren: een volwassen
onderneming beweegt met de markt mee. Dertien van de drieëntwintig aandelen zaten op de
ondergrens van 7% en kregen daarmee een te lage disconteringsvoet op tweederde van hun
waarde. De eindwaarde rekent nu met 8% (risicovrij 3% plus een marktpremie van 5%), wat de
waarderingen met circa 11% verlaagt.

**2. Houdbare groei als controle.** De klassieke formule is g = ROE × (1 − uitkeringsratio),
met de aandeleninkoop meegeteld in de uitkering (Damodaran's "augmented payout"). Groeit een
bedrijf in het model harder dan die formule toelaat, dan moet dat ergens vandaan komen:
hogere winstgevendheid, minder uitkeren, of schuld. Vijftien van de drieëntwintig ingevulde
aandelen overschrijden die grens — vooral waar de inkoopopslag de groei opdrijft.
Het detailpaneel waarschuwt, en er is een filter "Groei houdbaar".

**3. Payout op de juiste winstmaatstaf** — zie de kwaliteitsscore hierboven.

### Wat het model nog steeds niet doet

- **Lage-payout bedrijven worden systematisch ondergewaardeerd.** ASML komt op 145 uit bij
  een koers van 1.580. Dat is geen fout in de berekening maar een grens van de methode: wie
  30% uitkeert en de rest tegen 54% rendement herinvesteert, creëert waarde die een
  dividendmodel per definitie niet ziet. Voor dat type bedrijf is een kasstroommodel (FCFE)
  de juiste bril.
- **Geen dividendbelasting.** Het model rekent bruto. Voor DSM-Firmenich (35% Zwitsers),
  ArcelorMittal (15% Luxemburgs) en RELX (valutarisico) wijkt het netto-rendement af.
- **Geen scenario's.** Eén dividendpad per aandeel, geen kansverdeling.
- **Geen expliciete stabiele payout.** Damodaran leidt de payout in de eindfase af uit
  g en ROE: payout = 1 − g/ROE. Wij houden de payout impliciet constant.

## inkoop_negeren

Standaard telt een inkoopprogramma mee als opslag op de groeivoet: minder aandelen betekent
een hoger dividend per aandeel. Dat klopt alleen als het aantal aandelen daadwerkelijk daalt.
Koopt een bedrijf in om verwatering uit een keuzedividend of optieplan te compenseren, zet dan
`"inkoop_negeren": true` in de override. Voorbeeld: Fugro.

## Geen dividend meer

Zet `"d0_fy": 0` in de override wanneer een bedrijf de uitkering heeft gestaakt. Het aandeel
valt dan uit de lijst in plaats van door te rekenen op een dividend uit het verleden.
Voorbeeld: Cabka, dat over 2024 besloot niets uit te keren terwijl de databron nog 0,15 aanhield.
