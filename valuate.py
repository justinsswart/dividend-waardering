import json, math, datetime as dt
RAW = json.load(open("raw.json"))
OV  = json.load(open("overrides.json"))
CUR = dt.date.today().year

P = {"rf":0.030,"erp":0.050,"r_min":0.070,"r_max":0.120,"g_cap":0.12,"g_term":0.020,
     "n1":5,"n2":10,"mos_min":0.10,"mos_max":0.40}

def vereist_rendement(beta):
    b = beta if beta and 0.1 < beta < 3 else 1.0
    return min(max(P["rf"] + b*P["erp"], P["r_min"]), P["r_max"])

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

def kwaliteit(v):
    """0-100. Bepaalt hoeveel veiligheidsmarge nodig is."""
    s, det = 50, {}
    # payout ratio
    po = v.get("payout")
    if po is not None:
        pt = 20 if po < 0.5 else 12 if po < 0.7 else 4 if po < 0.9 else -10 if po < 1.1 else -20
        s += pt; det["payout"] = pt
    # FCF-dekking
    fcf, sh, d0 = v.get("fcf"), v.get("shares"), v.get("d0")
    if fcf and sh and d0:
        dek = (fcf/sh)/d0
        ft = 20 if dek > 2 else 12 if dek > 1.3 else 4 if dek > 1 else -15
        s += ft; det["fcf_dekking"] = round(dek,2)
    # schuld
    nd, eb = v.get("netdebt"), v.get("ebitda")
    if eb and eb > 0:
        lev = nd/eb
        lt = 10 if lev < 1 else 5 if lev < 2.5 else -5 if lev < 4 else -15
        s += lt; det["netdebt_ebitda"] = round(lev,2)
    # verlagingen
    c = v.get("cuts_sinds_2010", 0)
    ct = 10 if c == 0 else 0 if c == 1 else -8 if c == 2 else -15
    s += ct; det["verlagingen"] = c
    return max(0, min(100, s)), det

def dcf(divs_expliciet, d_start, g1, r, n1, n2, g_term):
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
    tv = d*(1+g_term)/(r-g_term)
    pv_tv = tv/(1+r)**t
    return pv+pv_tv, pv, pv_tv, jaar_dps

res = []
for tk, v in RAW.items():
    if not v.get("koers") or not v.get("d0"): continue
    ov = OV.get(tk, {})
    d0n, special = genormaliseerd_d0(v)
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
    b = inkoop_rendement(v)
    g1_kaal = g1
    if ov and b > 0:
        # Fase 1 is eindig, dus g1 mag boven het vereist rendement liggen.
        # Alleen de eeuwige groei in de eindwaarde moet er structureel onder blijven.
        g1 = min((1 + g1) / (1 - b) - 1, 0.18)

    fv, pv_div, pv_tv, pad = dcf(expl, d0n, g1, r, P["n1"], P["n2"], P["g_term"])
    kw, det = kwaliteit(v)
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
        "inkoop_rend": b, "netto_inkoop": v.get("netto_inkoop"), "g1_kaal": round(g1_kaal, 4)})

res.sort(key=lambda x: -x["korting_tov_koop"])
json.dump({"params":P,"bijgewerkt":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")+"Z","aandelen":res},
          open("data.json","w"), indent=1)
print(f"{len(res)} aandelen gewaardeerd | koopwaardig: {sum(1 for x in res if x['korting_tov_koop']>0)}")
for x in res[:8]: print(f"  {x['ticker']:11} koers {x['koers']:>8.2f}  fair {x['fair']:>8.2f}  koop {x['koopprijs']:>8.2f}  kw {x['kwaliteit']:>3}")
kpn = next(x for x in res if x["ticker"]=="KPN.AS"); print("\nKPN:", json.dumps({k:kpn[k] for k in ('koers','r','g1','fair','koopprijs','mos','kwaliteit','checks','pad')}, indent=1))
