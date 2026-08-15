# Analysewerkwijze per bedrijf

Vaste volgorde bij het invullen van een override. Elke stap levert iets dat in
`overrides.json` terechtkomt, met bron en datum.

---

## 1. Wat is de vorm van het beleid?

Nederlandse bedrijven doen dit op vijf manieren. De vorm bepaalt welk veld je invult.

| vorm | herkenbaar aan | veld | voorbeeld |
|---|---|---|---|
| bedrag per aandeel | "we betalen 0,20 in 2026" | `divs` | KPN, Wolters Kluwer |
| percentage van de winst | "50% van de nettowinst" | `payout_beleid` | ING, ABN AMRO |
| progressief | "stijgend dividend", geen bedrag | `g_na` | NN Group, ASR, Signify |
| bodembedrag | "minimaal X per aandeel" | `d0_fy` + `g_na: 0` | Randstad |
| geen beleid | alleen "houdbaar dividend" | `g_na` (eigen aanname) | Aegon |

Alleen de eerste twee zijn echte guidance. Bij de rest kies jij de groeivoet, en dat
hoort expliciet in de notitie te staan.

## 2. Boekjaartotaal ophalen, niet het kalenderjaar

Zoek in het persbericht bij de jaarcijfers: interim plus slotdividend over hetzelfde
boekjaar. Het slotdividend over jaar X wordt in jaar X+1 betaald, dus wat het model uit
de koershistorie afleidt is een mengsel van twee boekjaren.

Vul in als `d0_fy`. Bij NN scheelde dat 3,54 tegen 3,88.

## 3. Op welke winstmaatstaf stuurt het bedrijf?

Verzekeraars sturen op operationeel resultaat, niet op IFRS-nettowinst. Uitzenders en
industriële bedrijven vaak op winst gecorrigeerd voor afschrijving van overnames.

Staat de payout in de bron ver af van wat het model berekent, dan gebruikt het bedrijf een
andere noemer. Vul die in als `wpa`. Bij ASR: IFRS 2,16 tegen operationeel 7,93 — het
verschil tussen een dekkingswaarschuwing en een payout van 43%.

## 4. Incidenteel scheiden van structureel

Speciale dividenden, kapitaalteruggaven en uitkeringen na een verkoop horen niet in de
groeivoet. Ze verschijnen in de historie als een piek, en het jaar erna als een daling —
waarop het model een negatieve groei afleidt.

Randstad: het model las -31% groei, terwijl het reguliere dividend al acht jaar exact
1,62 is. Alleen het speciale dividend viel weg.

Kijk of het bedrijf regulier en speciaal apart benoemt. Vul alleen het reguliere deel in.

## 5. Voorwaarden en inkoop noteren

Veel beleid is voorwaardelijk: ASR keert niets uit onder 140% solvabiliteit, Randstad doet
alleen extra uitkeringen onder een leverage van 1,0. Dat hoort in de notitie — het zegt
wanneer de aanname breekt.

Aandeleninkoop rekent het model als groeiopslag. Noteer het lopende programma in de
notitie zodat je later kunt controleren of het nog loopt.

## 6. Vastleggen

```json
"TICKER.AS": {
  "d0_fy": 0.00,
  "g_na": 0.00,
  "wpa": 0.00,
  "bron": "url of documentnaam",
  "gecheckt": "JJJJ-MM-DD",
  "notitie": "vorm van het beleid, boekjaarcijfers, voorwaarden, en welk deel een eigen aanname is"
}
```

De notitie is geen bijzaak. Over een half jaar is dat het enige wat vertelt waarom er
6% staat en niet 12%.

---

## Wat een goede bron is

1. Persbericht bij de jaarcijfers — bevat interim, slot en de winstmaatstaf
2. De dividendpagina op de IR-site — bevat het beleid
3. Capital Markets Day-presentatie — bevat meerjarige guidance indien aanwezig
4. Jaarverslag — bevat de voorwaarden

Niet gebruiken als enige bron: zoeksnippets. Bij Signify leverde dat een payout-ratio van
40-50% op die al jaren niet meer gold — oud beleid uit de Philips Lighting-tijd. De
eigen pagina zei iets anders. Altijd de bron zelf openen.

Aggregatorsites (dividendinfo, stocksguide, marketscreener) zijn bruikbaar om
boekjaarbedragen te reconstrueren wanneer de IR-site blokkeert, maar noteer dat dan in
de bron.

## Wat je niet moet doen

- Een waargenomen payout-ratio invoeren als `payout_beleid`. Dat maakt van een observatie
  een toezegging.
- Historische groei overnemen als `g_na` zonder te controleren of het bedrijf dat tempo
  ergens heeft toegezegd.
- Een override laten staan zonder notitie. Dan weet je later niet wat aanname was en wat feit.
