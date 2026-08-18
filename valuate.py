import json, math, hashlib, os, datetime as dt
RAW = json.load(open("raw.json"))
OV  = json.load(open("overrides.json"))
CUR = dt.date.today().year
NU  = dt.datetime.now(dt.timezone.utc)
VANDAAG = NU.date()

try:
    AGENDA = json.load(open("agenda.json"))["bedrijven"]
except Exception:
    AGENDA = {}

# Wijzigingen in overrides.json zelf detecteren, zodat het tijdstempel klopt
# ongeacht hoe het bestand is bewerkt.
BRON = json.load(open("bronbelasting.json"))

try:
    LOG = json.load(open("override_log.json"))
except Exception:
    LOG = {}

def stempel(tk, ov):
    """Geeft terug wanneer deze override voor het laatst inhoudelijk veranderde."""
    if not ov:
        return None
    h = hashlib.sha256(json.dumps(ov, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    vorig = LOG.get(tk)
    if not vorig or vorig.get("hash") != h:
        LOG[tk] = {"hash": h, "gewijzigd": NU.isoformat(timespec="seconds")}
    return LOG[tk]["gewijzigd"]

def guidance_status(tk, ov):
    """Bepaalt de status live uit de huidige override plus de bewaarde rapportagedata."""
    ag = dict(AGENDA.get(tk, {}))
    laatste, volgende = ag.get("laatste_cijfers"), ag.get("volgende_cijfers")
    gecheckt = ov.get("gecheckt") if ov else None
    if not ov:
        st = "nooit"
    elif not gecheckt:
        st = "verouderd"
    elif laatste and gecheckt < laatste:
        st = "verouderd"
    elif volgende:
        try:
            dagen = (dt.date.fromisoformat(volgende) - VANDAAG).days
            st = "binnenkort" if 0 <= dagen <= 10 else "vers"
        except ValueError:
            st = "vers"
    else:
        st = "vers"
    ag.update({"status": st, "guidance_gecheckt": gecheckt,
               "guidance_bron": ov.get("bron") if ov else None})
    if volgende:
        try:
            ag["dagen_tot"] = (dt.date.fromisoformat(volgende) - VANDAAG).days
        except ValueError:
            pass
    return ag

P = {"rf":0.030,"erp":0.050,"r_min":0.065,"r_max":0.120,"g_cap":0.12,"g_term":0.020,
     "n1":5,"n2":10,"mos_min":0.10,"mos_max":0.40}

# De risicovrije voet komt uit markt.json, dat fetch.py vult met het zesmaands-
# gemiddelde van de tienjaarsrente op AAA-staatsobligaties in de eurozone (ECB).
# Ontbreekt dat bestand, dan blijft de vaste 3,0% hierboven staan.
try:
    MARKT = json.load(open("markt.json"))
    if isinstance(MARKT.get("rf"), (int, float)) and 0.005 <= MARKT["rf"] <= 0.060:
        P["rf"] = float(MARKT["rf"])
except Exception:
    MARKT = {"rf": P["rf"], "bron": "vaste waarde in valuate.py"}

def sector_betas():
    """Mediaan van de zelf berekende beta per sector, als anker voor losse aandelen.

    Damodaran's punt: de meetfout van een beta uit een enkele regressie is groot, die
    van een sectorgemiddelde veel kleiner. Sectoren met minder dan vier fondsen zijn
    te dun om een mediaan op te baseren; die vallen terug op de mediaan van de hele lijst.
    """
    per, alle = {}, []
    for v_ in RAW.values():
        b, r2 = v_.get("beta_regressie"), v_.get("beta_r2")
        if b is None or r2 is None:
            continue
        alle.append(b)
        per.setdefault(v_.get("sector") or "?", []).append(b)
    if not alle:
        return {}, 1.0
    mediaan = lambda w: sorted(w)[len(w)//2] if len(w) % 2 else (sorted(w)[len(w)//2-1]+sorted(w)[len(w)//2])/2
    return {k: mediaan(w) for k, w in per.items() if len(w) >= 4}, mediaan(alle)

SECTOR_BETA, MARKT_BETA = sector_betas()
overgeslagen = []

def gewogen_beta(v):
    """Combineert de eigen beta met die van de sector, en krimpt daarna richting 1.

    Drie stappen, elk met een reden:
    1. Weging op R2. Verklaart de markt maar 2% van de koersbeweging (KPN), dan is een
       lage beta geen bewijs van laag risico maar van weinig samenhang. Pas bij een R2
       van 0,25 of hoger telt de eigen regressie volledig mee.
    2. Krimp richting 1 (Blume): tweederde eigen schatting, eenderde marktgemiddelde.
       Beta's neigen over de tijd naar 1 en extreme uitkomsten zijn meestal meetfout.
    3. Begrenzen op 0,5 tot 2,0.

    Ontbreekt de regressie, dan valt het terug op de sector, en anders op 1,0. Het veld
    van de databron gebruiken we niet meer: dat gaf Shell een negatieve beta.
    """
    b, r2 = v.get("beta_regressie"), v.get("beta_r2")
    anker = SECTOR_BETA.get(v.get("sector") or "?", MARKT_BETA)
    if b is None:
        rauw, herkomst = anker, "sector"
    else:
        w = max(0.0, min((r2 or 0) / 0.25, 1.0))
        rauw = w * b + (1 - w) * anker
        herkomst = "eigen" if w > 0.8 else "gemengd" if w > 0.2 else "sector"
    krimp = 0.67 * rauw + 0.33 * 1.0
    return round(max(0.5, min(krimp, 2.0)), 3), herkomst

def vereist_rendement(beta):
    b = beta if beta and 0.1 < beta < 3 else 1.0
    return min(max(P["rf"] + b*P["erp"], P["r_min"]), P["r_max"])

def beta_van(v):
    return gewogen_beta(v)

def rendement_stabiel():
    """In de stabiele fase convergeert de beta van elk bedrijf naar 1: een volwassen
    onderneming beweegt met de markt mee. Damodaran hanteert dit standaard.
    Dertien van onze aandelen zaten op de ondergrens van 7% en kregen daarmee een
    te lage disconteringsvoet op tweederde van hun waarde."""
    return P["rf"] + P["erp"]

def basisgroei(v):
    g = [x for x in (v.get("g3"), v.get("g5")) if x is not None]
    if not g: return 0.02
    g = sum(g)/len(g)
    return min(max(g, -0.05), P["g_cap"])

def genormaliseerd_d0(v):
    """Filtert incidentele superdividenden eruit: cap op 1.6x mediaan laatste 5 volle jaren."""
    h = {int(k): x for k, x in v.get("div_hist", {}).items()}
    # geen uitkering in de laatste 2 volle jaren -> geen dividendaandeel
    if not any(h.get(y, 0) > 0 for y in (CUR-1, CUR-2)):
        return 0.0, True
    vol = sorted([y for y in h if y < CUR])[-5:]
    if len(vol) < 3: return v["d0"], False
    reeks = sorted(h[y] for y in vol)
    med = reeks[len(reeks)//2]
    d = v["d0"]; sp = False
    if med > 0 and d > 1.6*med:
        d, sp = round(1.6*med, 5), True
    # kapitaaluitkering-check: dividend mag winst/FCF per aandeel niet structureel overtreffen
    sh, fcf, eps = v.get("shares"), v.get("fcf"), v.get("eps")
    draagkracht = max([x for x in [(fcf/sh if fcf and sh and fcf > 0 else None), eps] if x] or [0])
    if draagkracht > 0 and d > 1.5*draagkracht:
        d, sp = round(1.5*draagkracht, 5), True
    return d, sp

def inkoop_rendement(v):
    """Netto inkoop als fractie van de beurswaarde. Negatief bij uitgifte (verwatering)."""
    ink, mc = v.get("netto_inkoop"), v.get("mcap")
    if not ink or not mc: return 0.0
    return round(max(min(ink/mc, 0.10), -0.05), 4)

def houdbare_groei(v, po, b):
    """g = ROE x (1 - uitkeringsratio), waarbij de uitkering ook de inkoop omvat.
    Meet of de groeiaanname gefinancierd kan worden uit wat het bedrijf verdient."""
    roe = v.get("roe")
    if not roe or po is None:
        return None
    winst = (v.get("eps") or 0) * (v.get("shares") or 0)
    ink_deel = (v.get("netto_inkoop") or 0) / winst if winst > 0 else 0
    uitkering = po + max(0.0, min(ink_deel, 1.5))
    return round(roe * (1 - uitkering), 4)

def kwaliteit(v, wpa_ov=None, d0_ref=None, cuts_ov=None):
    """0-100: hoeveel vertrouwen verdient dit dividend?

    Punten worden opgeteld, maar sommige signalen zetten een PLAFOND op de score.
    Dat is het punt: als een bedrijf anderhalf keer zijn winst uitkeert, kan geen
    enkele andere factor dat goedmaken. Zonder plafond streek een schone
    verlagingshistorie zo'n payout gewoon weg - UMG kwam op 89 uit bij 289% payout.
    """
    s, det, plafonds = 50, {}, []

    # payout ratio, op de winstmaatstaf waarop het bedrijf zelf stuurt
    po = v.get("payout")
    if wpa_ov and d0_ref:
        po = d0_ref / wpa_ov
    if po is not None and po < 0:
        # Negatieve winst per aandeel maakt de ratio negatief, en "po < 0,5" is dan
        # WAAR - het dividend kreeg zo +20 punten bonus voor een uitkering zonder
        # enige winstdekking (De Porceleyne Fles: winst -0,06, kreeg +20 in plaats
        # van de zwaarste straf). Behandel dit als de slechtste band, niet de beste.
        s -= 35
        det["payout"] = round(po, 3)
        det["payout_waarschuwing"] = "winst is negatief - dividend wordt niet uit winst betaald"
        plafonds.append(("dividend wordt uit verlies betaald", 30))
    elif po is not None:
        s += 20 if po < 0.5 else 12 if po < 0.7 else 4 if po < 0.9 else -15 if po < 1.0 else -35
        det["payout"] = round(po, 3)
        if po > 1.5:   plafonds.append(("payout boven 150%", 30))
        elif po > 1.2: plafonds.append(("payout boven 120%", 45))
        elif po > 1.0: plafonds.append(("payout boven de winst", 55))

    # dekking uit vrije kasstroom
    fcf, sh, d0 = v.get("fcf"), v.get("shares"), d0_ref or v.get("d0")
    # Banken en verzekeraars kennen geen zinvolle vrije kasstroom: de post schommelt
    # met de beleggingsportefeuille en zegt niets over dividenddekking.
    if (v.get("sector") or "").startswith("Financial"):
        fcf = None
        det["fcf_dekking"] = "n.v.t. (financiele instelling)"
    if fcf and sh and d0:
        dek = (fcf / sh) / d0
        s += 20 if dek > 2 else 12 if dek > 1.3 else 4 if dek > 1 else -15
        det["fcf_dekking"] = round(dek, 2)
        if dek < 0:   plafonds.append(("negatieve vrije kasstroom", 25))
        elif dek < 1: plafonds.append(("kasstroom dekt dividend niet", 50))

    # schuldpositie
    nd, eb = v.get("netdebt"), v.get("ebitda")
    if eb and eb > 0:
        lev = nd / eb
        s += 10 if lev < 1 else 5 if lev < 2.5 else -5 if lev < 4 else -15
        det["netdebt_ebitda"] = round(lev, 2)
        if lev > 5:   plafonds.append(("schuld boven 5x ebitda", 35))
        elif lev > 4: plafonds.append(("schuld boven 4x ebitda", 50))

    # verlagingshistorie
    c = cuts_ov if cuts_ov is not None else v.get("cuts_sinds_2010", 0)
    s += 10 if c == 0 else 0 if c == 1 else -8 if c == 2 else -15
    det["verlagingen"] = c

    # Hoe diep werd er gesneden? Een halvering weegt zwaarder dan het aantal keren.
    # Shell verlaagde in 2020 met tweederde - de eerste keer sinds de oorlog - en
    # kwam zonder deze straf op een score van 100 uit.
    diep = v.get("diepste_verlaging") or 0
    if diep < 0:
        det["diepste_verlaging"] = diep
        if diep <= -0.5:
            s -= 20; plafonds.append(("dividend ooit gehalveerd", 65))
        elif diep <= -0.3:
            s -= 12; plafonds.append(("verlaging van meer dan 30%", 75))
        elif diep <= -0.15:
            s -= 5
    if c >= 4:   plafonds.append(("vier of meer verlagingen", 45))
    elif c == 3: plafonds.append(("drie verlagingen", 55))

    s = max(0, min(100, s))
    if plafonds:
        laagste = min(plafonds, key=lambda x: x[1])
        if laagste[1] < s:
            det["plafond"] = laagste[0]
            det["zonder_plafond"] = s
            s = laagste[1]
    return s, det

def residual_income(bvps, roe, r, payout, n1, n2):
    """Tweede waarderingsmotor, voor banken en verzekeraars.

    Waarom naast het dividendmodel: bij een financiele instelling zegt de vrije kasstroom
    niets - die schommelt met de beleggingsportefeuille - en daarom valt bij negen fondsen
    een van de drie kwaliteitspijlers weg. Het residual income-model heeft die post niet
    nodig. Het waardeert vanuit de boekwaarde, en telt daar alleen de winst BOVEN de
    rendementseis bij op:

        waarde = boekwaarde + som van (ROE - r) x boekwaarde, contant gemaakt

    Verdient een bank precies zijn rendementseis, dan is hij zijn boekwaarde waard en niets
    meer. Dat sluit aan bij hoe deze aandelen in de praktijk worden bekeken (koers/boekwaarde).

    De boekwaarde groeit met de ingehouden winst: wat niet als dividend uitgaat, blijft in
    het eigen vermogen zitten en verdient het jaar daarop mee.

    Aannames, bewust streng:
    - ROE blijft n1 jaar op het huidige niveau en zakt daarna lineair naar r.
    - Na jaar n2 is de overwinst nul, dus er is GEEN eindwaarde. Concurrentie drukt
      overrendement op termijn weg. Dat is conservatief: houdt een bank zijn voorsprong
      vast, dan is de werkelijke waarde hoger dan wat hier uit komt.

    Het grote voordeel zit in die laatste regel: waar het dividendmodel gemiddeld 62% van
    zijn waarde uit de eindwaarde haalt, staat hier het overgrote deel al op dag een op de
    balans. De uitkomst hangt dus veel minder aan aannames over het jaar 2036.
    """
    # Ondergrenzen: bij een boekwaarde van enkele centen (Nedsense) of een negatief
    # rendement op eigen vermogen loopt de aanname vast dat het overrendement naar nul
    # zakt - dan zakt het al onder nul. Beter niets tonen dan een schijngetal.
    if not bvps or bvps < 0.10 or roe is None or not 0 < roe < 0.5:
        return None, None
    retentie = max(0.0, min(1.0 - (payout if payout is not None else 0.5), 1.0))
    b, pv = bvps, 0.0
    for t in range(1, n2 + 1):
        roe_t = roe if t <= n1 else roe + (r - roe) * ((t - n1) / (n2 - n1))
        ri = (roe_t - r) * b
        pv += ri / (1 + r) ** t
        b *= 1 + roe_t * retentie
    return round(bvps + pv, 3), round(pv, 3)

def stabiele_payout(roe, g_term):
    """Damodaran: in de eindfase moet de payout consistent zijn met groei en
    winstgevendheid - payout = 1 - g/ROE. Een bedrijf dat 2% blijft groeien bij een
    ROE van 12% kan 83% uitkeren; bij een ROE van 5% maar 60%. Het model hield de
    payout impliciet constant, wat de eindwaarde vertekent."""
    if not roe or roe <= g_term:
        return None
    return round(1 - g_term / roe, 4)

def dcf(divs_expliciet, d_start, g1, r, n1, n2, g_term, payout_nu=None, payout_st=None):
    """divs_expliciet: dict jaar->DPS. Daarna fade g1->g_term, dan Gordon."""
    pv, jaar_dps, d = 0.0, [], d_start
    t = 0
    for j in sorted(divs_expliciet):
        t += 1; d = divs_expliciet[j]
        pv += d/(1+r)**t; jaar_dps.append((j, round(d,4)))
    while t < n1:
        t += 1; d *= (1+g1)
        pv += d/(1+r)**t; jaar_dps.append((CUR+t-1, round(d,4)))
    fade = n2 - n1
    for i in range(1, fade+1):
        t += 1
        g = g1 + (g_term-g1)*(i/fade)
        d *= (1+g)
        pv += d/(1+r)**t; jaar_dps.append((CUR+t-1, round(d,4)))
    r_st = max(rendement_stabiel(), g_term + 0.01)
    # payout in de eindfase bijstellen naar wat groei en winstgevendheid toelaten
    if payout_nu and payout_st and payout_nu > 0:
        d *= min(max(payout_st / payout_nu, 0.5), 1.5)
    tv = d*(1+g_term)/(r_st-g_term)
    pv_tv = tv/(1+r)**t
    return pv+pv_tv, pv, pv_tv, jaar_dps

res = []
for tk, v in RAW.items():
    if not v.get("koers") or not v.get("d0"): continue
    ov = OV.get(tk, {})
    d0n, special = genormaliseerd_d0(v)
    # Boekjaartotaal uit de bedrijfsbron gaat voor. Het model telt uitkeringen per
    # kalenderjaar, maar bedrijven rapporteren per boekjaar: het slotdividend over
    # jaar X wordt pas in jaar X+1 betaald. Dat scheelt zomaar 10%.
    # d0_fy = 0 betekent expliciet: dit bedrijf keert nu niets uit. Het aandeel valt
    # dan uit de lijst, in plaats van door te rekenen op een dividend uit het verleden.
    if ov.get("d0_fy") is not None:
        d0n, special = float(ov["d0_fy"]), False
    if d0n <= 0: continue
    eps, fcf = v.get("eps"), v.get("fcf")
    if (eps is not None and eps <= 0) and (fcf is not None and fcf <= 0): continue
    beta_g, beta_herkomst = gewogen_beta(v)
    r = vereist_rendement(beta_g)
    g1 = ov.get("g_na", basisgroei(v))
    g1 = min(max(g1, -0.05), P["g_cap"])
    expl = {int(k): float(x) for k, x in ov.get("divs", {}).items() if int(k) >= CUR}
    # Payout-beleid: banken en verzekeraars geven geen bedrag per aandeel maar een
    # percentage van de winst. Dividend = beleid x verwachte winst per aandeel.
    beleid = ov.get("payout_beleid")
    if beleid and not expl and v.get("eps_fwd"):
        expl = {CUR: round(beleid * v["eps_fwd"], 4)}
    # Inkoop verlaagt het aantal aandelen, dus stijgt het dividend PER AANDEEL sneller.
    # Dat is de juiste plek: als je de inkoop ook nog als losse kasstroom optelt,
    # tel je hem twee keer. Alleen toepassen waar g1 uit een override komt --
    # historische groei (g3/g5) bevat het effect van eerdere inkoop al.
    # Dividend boven de winst: dan is doorgroeien geen aanname maar een gok.
    # Groei op nul, geen inkoopopslag, en zichtbaar markeren.
    eps_nu, eps_v = v.get("eps") or 0, v.get("eps_fwd") or 0
    # Verzekeraars sturen op operationeel resultaat, niet op de IFRS-nettowinst.
    # Die laatste schommelt met marktwaarderingen en geeft een vals beeld van de dekking.
    if ov.get("wpa"):
        eps_nu = eps_v = float(ov["wpa"])
    eps_beste = max(eps_nu, eps_v)
    # onhoudbaar: ook de verwachte winst dekt het dividend niet
    onhoudbaar = bool(eps_beste > 0 and d0n > eps_beste)
    # gespannen: alleen houdbaar als het verwachte winstherstel doorzet
    gespannen = bool(not onhoudbaar and eps_nu > 0 and d0n > eps_nu)
    if onhoudbaar and not ov.get("divs"):
        g1 = min(g1, 0.0)
    elif gespannen and not ov.get("divs"):
        g1 = min(g1, 0.02)

    b = inkoop_rendement(v)
    g1_kaal = g1
    # inkoop_negeren: sommige bedrijven kopen alleen in om verwatering te compenseren
    # (keuzedividend, optieplannen). Het aantal aandelen daalt dan niet, dus het
    # dividend per aandeel groeit er ook niet door.
    if ov and b > 0 and not (onhoudbaar or gespannen) and not ov.get("inkoop_negeren"):
        # Fase 1 is eindig, dus g1 mag boven het vereist rendement liggen.
        # Alleen de eeuwige groei in de eindwaarde moet er structureel onder blijven.
        g1 = min((1 + g1) / (1 - b) - 1, 0.18)

    # bronbelasting: wat er van het brutodividend overblijft na inhouding en verrekening
    land = ov.get("land", "NL")
    bb = BRON.get(land, BRON["NL"])
    verlies = max(0.0, bb["tarief"] - bb["verrekenbaar"])

    kw, det = kwaliteit(v, ov.get("wpa"), d0n, ov.get("verlagingen"))

    po_st = stabiele_payout(v.get("roe"), P["g_term"])
    fv, pv_div, pv_tv, pad = dcf(expl, d0n, g1, r, P["n1"], P["n2"], P["g_term"],
                                 det.get("payout"), po_st)
    # tweede motor voor financiele instellingen, als tegenproef op het dividendmodel
    ri_fair = ri_pv = None
    ri_vt = (v.get("sector") or "").startswith("Financial")
    if ri_vt:
        ri_fair, ri_pv = residual_income(v.get("bvps"), v.get("roe"), r,
                                         det.get("payout"), P["n1"], P["n2"])

    sg = houdbare_groei(v, det.get("payout"), b)
    laag = dcf(expl, d0n, max(g1-0.02, -0.05), r, P["n1"], P["n2"], max(P["g_term"]-0.01, 0.005),
               det.get("payout"), po_st)[0]
    hoog = dcf(expl, d0n, g1+0.02, r, P["n1"], P["n2"], P["g_term"]+0.01,
               det.get("payout"), po_st)[0]
    mos = P["mos_max"] - (P["mos_max"]-P["mos_min"])*(kw/100)

    # Bij financiele instellingen telt de LAAGSTE van de twee motoren. Het dividendmodel
    # waardeerde deze groep stelselmatig hoger dan het residual income-model - bij ASR
    # 110 tegen 46, bij Aegon 16 tegen 6 - en dat verschil komt voort uit de zwakte van
    # een dividendmodel bij een bank: een hoge uitkering en een lage rendementseis
    # vermenigvuldigen elkaar, zonder dat de balans meepraat. Wie de hoogste van twee
    # schattingen neemt, kiest per definitie de meest optimistische aanname.
    # Geeft het residual income-model bij een financiele instelling geen uitkomst, dan
    # valt het aandeel uit de lijst. Anders neemt het dividendmodel het over juist waar
    # de balans het meest te zeggen heeft - bij Nedsense leverde dat een koopprijs op
    # boven een boekwaarde van negen cent per aandeel, met een negatieve ROE.
    if ri_vt and not ri_fair:
        overgeslagen.append(tk)
        continue

    fair_ddm = fv
    if ri_vt and ri_fair and ri_fair < fv:
        fv, waardering_bron = ri_fair, "residual income (laagste van twee)"
    elif ri_vt and ri_fair:
        waardering_bron = "dividendmodel (laagste van twee)"
    else:
        waardering_bron = "dividendmodel"
    koop = fv*(1-mos)
    k = v["koers"]
    res.append({**{x: v.get(x) for x in ("ticker","naam","sector","koers","valuta","d0","g3","g5","payout","beta","cuts_sinds_2010","div_hist","mcap","opgehaald")},
        "r": round(r,4), "g1": round(g1,4), "fair": round(fv,3), "pv_div": round(pv_div,3),
        "pv_terminal": round(pv_tv,3), "koopprijs": round(koop,3), "mos": round(mos,3),
        "kwaliteit": kw, "checks": det, "upside": round((fv-k)/k,4),
        "korting_tov_koop": round((koop-k)/k,4),
        "yield_nu": round(d0n/k,4), "yoc_koop": round(d0n/koop,4), "d0_norm": d0n, "special_div": special,
        "vlag": "controleer" if (fv/k > 4 or fv/k < 0.15) else None,
        "handmatig": bool(ov), "pad": pad[:12],
        "guidance_type": ("dps" if ov.get("divs") else "payout" if ov.get("payout_beleid")
                          else "groei" if ov.get("g_na") else None),
        "guidance_bron": ov.get("bron"), "guidance_notitie": ov.get("notitie"),
        "agenda": guidance_status(tk, ov), "override_gewijzigd": stempel(tk, ov),
        "inkoop_rend": b, "netto_inkoop": v.get("netto_inkoop"), "g1_kaal": round(g1_kaal, 4),
        "houdbare_groei": sg, "roe": v.get("roe"),
        "fair_laag": round(laag, 3), "fair_hoog": round(hoog, 3),
        "payout_stabiel": po_st, "land": land, "bron_tarief": bb["tarief"], "bron_verlies": round(verlies, 4),
        "bron_notitie": bb.get("notitie"), "d0_netto": round(d0n * (1 - verlies), 5),
        "model_ongeschikt": bool((det.get("payout") or 1) < 0.35 and (v.get("roe") or 0) > 0.20),
        "groei_boven_houdbaar": bool(sg is not None and g1 > sg + 0.02),
        "r_stabiel": round(rendement_stabiel(), 4),
        "beta_gebruikt": beta_g, "beta_herkomst": beta_herkomst,
        "ri_van_toepassing": ri_vt, "fair_ri": ri_fair, "ri_overwinst": ri_pv,
        "fair_ddm": round(fair_ddm, 3), "waardering_bron": waardering_bron,
        "bvps": v.get("bvps"),
        "ri_afwijking": (round(ri_fair/fv - 1, 3) if (ri_fair and fv) else None),
        "ri_conflict": bool(ri_fair and fv and abs(ri_fair/fv - 1) > 0.25),
        "beta_regressie": v.get("beta_regressie"), "beta_r2": v.get("beta_r2"),
        "op_rendementsvloer": bool(abs(r - P["r_min"]) < 1e-9),
        "onhoudbaar": onhoudbaar, "gespannen": gespannen,
        "eps_nu": eps_nu, "eps_fwd": eps_v, "dekking_wpa": round(eps_beste/d0n, 2) if d0n else None})

res.sort(key=lambda x: -x["korting_tov_koop"])
if overgeslagen:
    print("overgeslagen (financieel, geen residual income):", ", ".join(overgeslagen))
def audit_overrides(o, res_bij_ticker):
    """Controleert of de override-data en het model consistent zijn, en meldt afwijkingen.

    Aanleiding (18-08-2026): De Porceleyne Fles had een expliciet genoteerde negatieve
    winst per aandeel in de notitie, maar de kwaliteitsscore gebruikte de positieve
    databronwaarde omdat "wpa" nooit was ingevuld - en Aperam gebruikte een verouderd
    TTM-winstcijfer terwijl de FY2025-winst er al maanden bij stond. Beide keren was de
    juiste informatie aanwezig, alleen niet op de plek waar de code hem las.

    Dit draait bij elke run mee en print naar de uitvoer, zodat zulke gaten opvallen
    voordat ze maandenlang onopgemerkt blijven.
    """
    meldingen = []
    for t, v in o.items():
        if not isinstance(v, dict):
            continue
        a = res_bij_ticker.get(t)
        if not a:
            continue
        notitie = (v.get("notitie") or "").lower()

        # 1. geen enkel guidance-type: de groei komt dan volledig uit historische data,
        #    ook al staat er een override - dat is verwarrend voor wie het naleest.
        if not any(k in v for k in ("divs", "payout_beleid", "g_na")) and v.get("d0_fy") != 0:
            meldingen.append(f"{t}: geen divs/payout_beleid/g_na - groei komt uit basisgroei(), niet uit de override")

        # 2. d0_fy zonder wpa: de kwaliteitsscore valt terug op de ruwe databronwinst,
        #    ook als de notitie zelf al een ander cijfer noemt (Aperam, Porceleyne Fles).
        if v.get("d0_fy") not in (0, None) and "wpa" not in v and "g_na" in v:
            meldingen.append(f"{t}: d0_fy + g_na maar geen wpa - payout-check gebruikt de ruwe databronwinst")

        # 3. de notitie noemt expliciet een negatieve WINST, maar wpa staat niet op een
        #    negatief getal. Zoekt gericht naar "winst" of "wpa" vlak bij "negatief" om
        #    geen loos alarm te slaan op "negatieve kasstroom" (Holland Colours, NSI).
        import re as _re
        winst_negatief = _re.search(
            r"(winst|wpa|resultaat)[^.]{0,40}negatie|negatie[^.]{0,40}(winst|wpa|resultaat)",
            notitie)
        if winst_negatief and v.get("wpa", 1) >= 0:
            meldingen.append(f"{t}: notitie noemt mogelijk een negatieve winst, maar wpa staat op {v.get('wpa')} - handmatig nalopen")

        # 4. gecheckt-datum ontbreekt of is ouder dan de laatste bekende publicatie.
        if "gecheckt" not in v:
            meldingen.append(f"{t}: geen 'gecheckt' datum")
        if "bron" not in v:
            meldingen.append(f"{t}: geen 'bron' veld")

        # 5. het model gebruikt een ander dividend dan wat de override opgeeft, zonder
        #    dat er een special_div-vlag is - kan wijzen op een vergeten kalenderjaar-
        #    correctie of een override die niet meer aansluit op de nieuwste data.
        if v.get("d0_fy") not in (0, None):
            afwijking = abs((a.get("d0_norm") or 0) - v["d0_fy"])
            if afwijking > 0.01 and not a.get("special_div"):
                meldingen.append(f"{t}: override d0_fy={v['d0_fy']} maar model gebruikt d0_norm={a.get('d0_norm')}")

    return meldingen


meldingen = audit_overrides(OV, {x["ticker"]: x for x in res})
if meldingen:
    print(f"\naudit: {len(meldingen)} aandachtspunten in overrides.json")
    for m in meldingen:
        print(" ", m)
else:
    print("\naudit: geen aandachtspunten gevonden")
json.dump({"gecontroleerd": NU.isoformat(timespec="seconds"), "meldingen": meldingen},
          open("audit_log.json", "w"), indent=1, ensure_ascii=False)

json.dump({"params":P,"markt":MARKT,"bijgewerkt":NU.isoformat(timespec="seconds"),"aandelen":res},
          open("data.json","w"), indent=1)
print(f"{len(res)} aandelen gewaardeerd | koopwaardig: {sum(1 for x in res if x['korting_tov_koop']>0)}")
for x in res[:8]: print(f"  {x['ticker']:11} koers {x['koers']:>8.2f}  fair {x['fair']:>8.2f}  koop {x['koopprijs']:>8.2f}  kw {x['kwaliteit']:>3}")
kpn = next(x for x in res if x["ticker"]=="KPN.AS"); print("\nKPN:", json.dumps({k:kpn[k] for k in ('koers','r','g1','fair','koopprijs','mos','kwaliteit','checks','pad')}, indent=1))
