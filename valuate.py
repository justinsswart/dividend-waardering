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

P = {"rf":0.030,"erp":0.050,"r_min":0.070,"r_max":0.120,"g_cap":0.12,"g_term":0.020,
     "n1":5,"n2":10,"mos_min":0.10,"mos_max":0.40}

def vereist_rendement(beta):
    b = beta if beta and 0.1 < beta < 3 else 1.0
    return min(max(P["rf"] + b*P["erp"], P["r_min"]), P["r_max"])

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
    if po is not None:
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
    if ov.get("d0_fy"):
        d0n, special = float(ov["d0_fy"]), False
    if d0n <= 0: continue
    eps, fcf = v.get("eps"), v.get("fcf")
    if (eps is not None and eps <= 0) and (fcf is not None and fcf <= 0): continue
    r = vereist_rendement(v.get("beta"))
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
    if ov and b > 0 and not (onhoudbaar or gespannen):
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
    sg = houdbare_groei(v, det.get("payout"), b)
    laag = dcf(expl, d0n, max(g1-0.02, -0.05), r, P["n1"], P["n2"], max(P["g_term"]-0.01, 0.005),
               det.get("payout"), po_st)[0]
    hoog = dcf(expl, d0n, g1+0.02, r, P["n1"], P["n2"], P["g_term"]+0.01,
               det.get("payout"), po_st)[0]
    mos = P["mos_max"] - (P["mos_max"]-P["mos_min"])*(kw/100)
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
        "onhoudbaar": onhoudbaar, "gespannen": gespannen,
        "eps_nu": eps_nu, "eps_fwd": eps_v, "dekking_wpa": round(eps_beste/d0n, 2) if d0n else None})

res.sort(key=lambda x: -x["korting_tov_koop"])
json.dump(LOG, open("override_log.json","w"), indent=1)
json.dump({"params":P,"bijgewerkt":NU.isoformat(timespec="seconds"),"aandelen":res},
          open("data.json","w"), indent=1)
print(f"{len(res)} aandelen gewaardeerd | koopwaardig: {sum(1 for x in res if x['korting_tov_koop']>0)}")
for x in res[:8]: print(f"  {x['ticker']:11} koers {x['koers']:>8.2f}  fair {x['fair']:>8.2f}  koop {x['koopprijs']:>8.2f}  kw {x['kwaliteit']:>3}")
kpn = next(x for x in res if x["ticker"]=="KPN.AS"); print("\nKPN:", json.dumps({k:kpn[k] for k in ('koers','r','g1','fair','koopprijs','mos','kwaliteit','checks','pad')}, indent=1))
