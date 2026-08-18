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

## Risicovrije voet

`fetch.py` haalt de tienjaarsrente op AAA-staatsobligaties uit de eurozone op bij het
ECB Data Portal en schrijft die naar `markt.json`. `valuate.py` leest dat bestand en
gebruikt het gemiddelde over circa zes maanden als `rf` — niet de slotstand, zodat de
koopprijzen niet meebewegen met dagruis.

Hieraan hangt alles: de ondergrens van het vereist rendement en het stabiele rendement
(rf + erp) dat op tweederde van de waarde drukt. Voorheen stond hier een vaste 3,0%.

Lukt het ophalen niet, dan blijft de vorige waarde in `markt.json` staan; ontbreekt dat
bestand, dan valt het model terug op 3,0%. Waarden buiten 0,5%–6,0% worden geweigerd:
dan is er iets mis met de bron, niet met de markt. De gebruikte voet staat in `data.json`
onder `markt`.

## Regelafsluitingen

`.gitattributes` dwingt LF af voor tekstbestanden. Zonder dat bestand meldde git bij
elke commit "LF will be replaced by CRLF" — onschuldig, maar het maakte de uitvoer
onoverzichtelijk.

## Weekarchief

`update.ps1` bewaart één keer per week een kopie van `data.json` in
`%USERPROFILE%\dividend-historie\`, met de naam `data-JJJJ-Wnn.json`. Die map ligt
buiten de repo, dus de historie lift niet mee naar GitHub en Netlify.

De eerste run van een nieuwe ISO-week maakt het bestand aan; latere runs in dezelfde
week laten het staan. Zo bouw je een reeks op waarmee je achteraf kunt toetsen of de
koopprijzen ergens op sloegen.

## Beta

De beta wordt sinds augustus 2026 zelf berekend in `fetch.py`: vijf jaar weekrendementen
tegen de AEX, waaruit beta, R² en het aantal waarnemingen volgen. Het beta-veld van de
databron gebruiken we niet meer — dat gaf Shell een beta van -0,218, Flow Traders 0,124
en Wolters Kluwer 0,185, waardoor 33 van de 54 aandelen op de rendementsvloer van 7%
belandden en dus allemaal dezelfde disconteringsvoet kregen.

`valuate.py` combineert die regressie in drie stappen tot de beta die het model gebruikt:

1. **Weging op R².** Bij een R² van 0,02 (KPN) verklaart de markt vrijwel niets van de
   koersbeweging; een lage beta is dan geen bewijs van laag risico maar van weinig
   samenhang. Pas vanaf R² 0,25 telt de eigen regressie volledig mee, daaronder schuift
   het gewicht naar de sectormediaan.
2. **Sectormediaan** als anker, berekend over de eigen lijst. Sectoren met minder dan
   vier fondsen zijn te dun en vallen terug op de mediaan van de hele lijst.
3. **Krimp richting 1** (Blume): tweederde eigen schatting, eenderde marktgemiddelde.
   Beta's neigen over de tijd naar 1 en extreme uitkomsten zijn meestal meetfout.
   Daarna begrensd op 0,5 tot 2,0.

In `data.json` staat per aandeel `beta_gebruikt`, `beta_herkomst` (eigen, gemengd of
sector), `beta_regressie`, `beta_r2` en `op_rendementsvloer`.

**Vloer verlaagd naar 6,5% (augustus 2026).** Met de oude vloer van 7% zaten achttien
defensieve namen op dezelfde disconteringsvoet; nu nog zes. Het effect op de waardering
is klein — 3 tot 8% bij de aandelen die er echt onder zaten — omdat de eindwaarde met
`r_stabiel` (rf + erp) rekent en niet met deze voet. De vloer raakt alleen het
terugrekenen van de kasstromen, niet de omvang van de eindwaarde. Lager dan 6,5% is af
te raden: dan vertrouw je beta's met een R² van 0,05 vrijwel volledig.

De vloer wordt vanzelf minder belangrijk nu de risicovrije voet meebeweegt. Stijgt die
naar 4%, dan geeft de formule voor een beta van 0,59 al 6,95% en bindt de vloer bijna
niet meer.

## Residual income: tweede motor voor financiële instellingen

Bij banken en verzekeraars zegt de vrije kasstroom niets — die schommelt met de
beleggingsportefeuille — en daarom zet `kwaliteit()` die pijler daar op "n.v.t.".
Bij negen fondsen valt dus een van de drie kwaliteitstoetsen weg.

Het residual income-model heeft die post niet nodig:

```
waarde = boekwaarde + Σ (ROE − r) × boekwaarde, contant gemaakt
```

Verdient een bank precies zijn rendementseis, dan is hij zijn boekwaarde waard en niets
meer. De boekwaarde groeit met de ingehouden winst.

Aannames, bewust streng: ROE blijft vijf jaar op het huidige niveau en zakt daarna
lineair naar `r`. Na jaar tien is de overwinst nul, dus er is **geen eindwaarde** —
concurrentie drukt overrendement op termijn weg. Waar het dividendmodel gemiddeld 62%
van zijn waarde uit de eindwaarde haalt, staat hier het grootste deel al op dag één op
de balans.

Velden in `data.json`: `fair_ri`, `ri_overwinst`, `ri_afwijking`, `ri_conflict`
(afwijking groter dan 25%), `bvps`. De uitkomst staat als tegenproef in het detailpaneel.

**De koopprijs volgt bij financiële instellingen de LAAGSTE van de twee motoren.**
Wie de hoogste van twee schattingen neemt, kiest per definitie de meest optimistische
aanname. Bij zes van de acht is dat het residual income-model (ABN, Aegon, ASR, ING, NN,
Van Lanschot); bij Flow Traders en HAL blijft het dividendmodel leidend, omdat dat daar
juist de laagste uitkomst geeft.

Bij Flow Traders en HAL is die laagste uitkomst overigens ook de minst betrouwbare: een
variabel dividend dat meebeweegt met handelsvolatiliteit, en een holding die je waardeert
op wat erin zit in plaats van op wat eruit gaat. De regel is bewust mechanisch, maar lees
bij die twee de tegenproef in het detailpaneel mee.

Velden: `fair_ddm` houdt de uitkomst van het dividendmodel apart, `waardering_bron` zegt
welke motor de koopprijs bepaalt. Het aandeel eindwaarde in het detailpaneel rekent met
`fair_ddm`, want de eindwaarde hoort bij het dividendmodel.

Ondergrenzen: geen RI-uitkomst bij een boekwaarde onder 0,10 of een ROE van nul of lager.

**Geen residual income bij een financiële instelling betekent: geen koopprijs.** Het
aandeel valt uit de lijst, met een melding in de uitvoer van `valuate.py`. Zonder die
regel neemt het dividendmodel het over juist waar de balans het meest te zeggen heeft:
Nedsense kreeg zo een koopprijs bij een boekwaarde van negen cent per aandeel en een
negatieve ROE, en stond daarmee als koopkandidaat in de lijst.

## Audit bij elke run

`valuate.py` controleert aan het eind van elke run alle overrides op vijf punten en
print de uitkomst, ook weggeschreven naar `audit_log.json`:

1. Geen enkel guidance-type (`divs`, `payout_beleid`, `g_na`) — de groei komt dan
   uit historische data, ook al staat er een override.
2. Een dividendbedrag zonder eigen winstmaatstaf (`wpa`) — de kwaliteitsscore valt
   dan terug op de ruwe databronwinst, ook als de notitie zelf al een ander cijfer noemt.
3. De notitie vermeldt een negatieve winst, maar `wpa` staat niet op een negatief getal.
4. Geen `gecheckt`-datum.
5. Geen `bron`-veld.
6. Het model gebruikt een ander dividendbedrag dan de override opgeeft, zonder dat
   er een `special_div`-vlag is gezet.

Elke melding is een aanwijzing om zelf na te lopen, geen automatische fout. NSI wordt
bijvoorbeeld altijd gevlagd door punt 3 — de notitie noemt terecht een negatieve
IFRS-winst, maar legt zelf al uit waarom EPRA-winst de juiste maatstaf is. Dat is geen
fout, alleen een punt waarvan de audit niet kan weten dat het al bewust is afgewogen.

Aanleiding (18-08-2026): bij De Porceleyne Fles stond een negatieve winst al in de
notitie, maar de score gebruikte de positieve databronwaarde omdat `wpa` nooit was
ingevuld. Bij Aperam gebruikte de score een verouderd TTM-winstcijfer terwijl de
FY2025-winst er al bij stond. In allebei de gevallen was de juiste informatie aanwezig,
alleen niet op de plek waar de code hem las. Deze audit vangt dat soort gaten voortaan
bij elke run op, in plaats van pas bij een handmatige doorlichting maanden later.
