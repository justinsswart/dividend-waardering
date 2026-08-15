"""Scant per aandeel op nieuws dat het dividendpad kan raken en zet een signaal
in signalen.json. Verandert de aannames NIET zelf - dat blijft jouw beslissing."""
import json, urllib.request, urllib.parse, xml.etree.ElementTree as ET, datetime as dt, re, time

RAW = json.load(open("raw.json"))
TRIGGERS = {
 "dividend": 3, "slotdividend": 3, "interim": 2, "uitkering": 2, "payout": 2,
 "guidance": 3, "outlook": 3, "vooruitzicht": 3, "verwachting": 2,
 "winstwaarschuwing": 4, "profit warning": 4, "verlaagt": 3, "verhoogt": 2, "schrapt": 4,
 "inkoop eigen aandelen": 2, "buyback": 2, "overname": 3, "bod op": 4, "emissie": 3,
 "kwartaalcijfers": 2, "jaarcijfers": 2, "halfjaarcijfers": 2, "capital markets day": 3,
}
UA = {"User-Agent": "Mozilla/5.0 (dividend-monitor)"}

def zoek(naam, dagen=7):
    q = urllib.parse.quote(f'"{naam}" (dividend OR cijfers OR outlook OR guidance) when:{dagen}d')
    url = f"https://news.google.com/rss/search?q={q}&hl=nl&gl=NL&ceid=NL:nl"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        return []
    uit = []
    for it in root.findall(".//item")[:12]:
        t = (it.findtext("title") or "").strip()
        uit.append({"titel": t, "link": it.findtext("link"), "datum": it.findtext("pubDate"),
                    "bron": (it.findtext("source") or "")})
    return uit

sig = {}
for tk, v in RAW.items():
    naam = re.sub(r"\s+(N\.?V\.?|KON|Group|Holding|Groep)$", "", v.get("naam", tk)).strip()
    if len(naam) < 3: continue
    items = zoek(naam)
    score, hits = 0, []
    for it in items:
        low = it["titel"].lower()
        w = sum(p for k, p in TRIGGERS.items() if k in low)
        if w >= 3:
            score += w; hits.append({**it, "gewicht": w})
    if hits:
        sig[tk] = {"naam": v.get("naam"), "score": score,
                   "niveau": "hoog" if score >= 8 else "midden" if score >= 5 else "laag",
                   "items": sorted(hits, key=lambda x: -x["gewicht"])[:5]}
    time.sleep(0.8)

json.dump({"gescand": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "signalen": sig}, open("signalen.json", "w"), indent=1, ensure_ascii=False)
hoog = [k for k, x in sig.items() if x["niveau"] == "hoog"]
print(f"{len(sig)} aandelen met signaal | herzie met voorrang: {hoog}")
