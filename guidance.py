"""Leest IR-pagina's uit en stelt dividendguidance voor. Schrijft naar voorstellen.json.
Past overrides.json NIET zelf aan - dat doe jij na controle."""
import json, re, urllib.request, datetime as dt, html as ihtml, sys

BRON = json.load(open("ir_bronnen.json"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
CUR = dt.date.today().year

def tekst(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        h = r.read().decode("utf-8", "ignore")
    h = re.sub(r"(?is)<(script|style|nav|footer)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", ihtml.unescape(h))

# bedragen: € 0.20 / EUR 0,20 / 20 cents / 17.0 cents
BEDRAG = r"(?:€\s*|EUR\s*)?(\d{1,3}[.,]\d{1,3})\s*(?:per\s+(?:ordinary\s+)?share|per\s+aandeel)?|(\d{1,3}(?:[.,]\d)?)\s*(?:euro\s*)?cents?\b"
JAAR = r"\b(20\d{2})\b"

def naar_euro(m):
    if m.group(1): return float(m.group(1).replace(",", "."))
    return float(m.group(2).replace(",", ".")) / 100

def vind(txt):
    """Zinnen met intentie/verwachting + jaar + bedrag."""
    zinnen = re.split(r"(?<=[.!?])\s+", txt)
    uit = []
    for z in zinnen:
        low = z.lower()
        if not re.search(r"\b(dividend|uitkering)\b", low): continue
        if not re.search(r"\b(intend|expect|guidance|target|propose|verwacht|voornemen|beoogt|streeft|policy|outlook)\w*\b", low): continue
        jaren = [int(j) for j in re.findall(JAAR, z) if CUR-1 <= int(j) <= CUR+6]
        if not jaren: continue
        bedragen = []
        for m in re.finditer(BEDRAG, z):
            v = naar_euro(m)
            if 0.01 <= v <= 15: bedragen.append(round(v, 4))
        groei = [round(float(g.replace(",", "."))/100, 4)
                 for g in re.findall(r"(\d{1,2}(?:[.,]\d)?)\s*%", z)]
        # payout-beleid: "40-50% of net income", "50% van de nettowinst", "pay-out ratio of 45%"
        payout = None
        pm = re.search(r"(?:pay[\s-]?out|uitkerings?)[\s\w]{0,24}?(\d{1,3})(?:\s*[-–tot]{1,4}\s*(\d{1,3}))?\s*%"
                       r"|(\d{1,3})(?:\s*[-–tot]{1,4}\s*(\d{1,3}))?\s*%\s*(?:of|van)\s+(?:continuing\s+)?"
                       r"(?:net\s+income|net\s+profit|nettowinst|de\s+winst|resilient\s+net\s+profit)", z, re.I)
        if pm:
            g = [int(x) for x in pm.groups() if x]
            if g and all(5 <= x <= 100 for x in g):
                payout = round(sum(g)/len(g)/100, 4)
        if bedragen or groei or payout:
            uit.append({"zin": z.strip()[:300], "jaren": sorted(set(jaren)),
                        "bedragen": bedragen, "groei_pct": groei, "payout": payout})
    return uit

def koppel(vondsten):
    """Jaar -> bedrag, alleen waar de zin precies één jaar en één plausibel bedrag noemt."""
    voorstel, gr, po = {}, None, None
    for v in vondsten:
        if len(v["jaren"]) == 1 and len(set(v["bedragen"])) == 1:
            j = v["jaren"][0]
            if j >= CUR: voorstel[str(j)] = v["bedragen"][0]
        # g_na alleen uit zinnen die expliciet over de periode DAARNA gaan.
        # Een CAGR over 2025-2027 is geen groeivoet voor 2028+ - die verwarring
        # maakt de waardering stil en systematisch te hoog.
        if re.search(r"\b(thereafter|beyond 20\d\d|from 20\d\d onwards?|daarna|vanaf 20\d\d|nadien)\b", v["zin"], re.I):
            g = [x for x in v["groei_pct"] if 0.01 <= x <= 0.15]
            if g: gr = g[0]
        if v.get("payout") and po is None:
            po = v["payout"]
    return voorstel, gr, po

def alternatieven(tk):
    """Zoekt persberichten wanneer de vaste IR-pagina niet werkt."""
    import urllib.parse, xml.etree.ElementTree as ET
    naam = re.sub(r"\.AS$", "", tk)
    q = urllib.parse.quote(f'{naam} dividend per share intends expects 20{str(CUR)[2:]}')
    try:
        with urllib.request.urlopen(urllib.request.Request(
            f"https://news.google.com/rss/search?q={q}&hl=en&gl=NL&ceid=NL:en", headers=UA), timeout=15) as r:
            root = ET.fromstring(r.read())
        return [it.findtext("link") for it in root.findall(".//item")[:3] if it.findtext("link")]
    except Exception:
        return []

res = {}
args = sys.argv[1:]
if "--verouderd" in args:
    ag = json.load(open("agenda.json"))["bedrijven"]
    only = [t for t, v in ag.items() if v["status"] in ("verouderd", "binnenkort") and t in BRON]
    print(f"nalopen: {only or 'niets'}")
else:
    only = [a for a in args if not a.startswith("--")] or list(BRON)
for tk in only:
    url = BRON.get(tk)
    if not url: continue
    v, gebruikt, fout = [], url, None
    try:
        v = vind(tekst(url))
    except Exception as e:
        fout = str(e)[:70]
    if not v:
        for alt in alternatieven(tk):
            try:
                v = vind(tekst(alt))
                if v: gebruikt, fout = alt, None; break
            except Exception:
                continue
    divs, g, po = koppel(v)
    res[tk] = {"url": gebruikt, "fout": fout, "voorstel": {"divs": divs, "g_na": g} if divs or g else None,
               "bewijs": v[:6], "gecheckt": str(dt.date.today())}
    st = f"{len(divs)} jaren" if divs else f"payout {po}" if po else "niets"
    print(f"{tk:10} {st:14} g_na={g} | {len(v)} kandidaatzinnen")

json.dump(res, open("voorstellen.json", "w"), indent=1, ensure_ascii=False)
