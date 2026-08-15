import json, pathlib
d = json.load(open("data.json"))
try:
    ag = json.load(open("agenda.json"))["bedrijven"]
except Exception:
    ag = {}
for a in d["aandelen"]:
    a.pop("div_hist", None)          # niet nodig in de UI, scheelt gewicht
    a["pad"] = a["pad"][:2]
    a["agenda"] = ag.get(a["ticker"], {"status": "nooit"})          # alleen de vastgezette guidance-jaren
html = pathlib.Path("template.html").read_text()
out = html.replace("/*__DATA__*/", json.dumps(d, ensure_ascii=False, separators=(",", ":")))
pathlib.Path("index.html").write_text(out)
print("index.html", round(len(out)/1024, 1), "kB |", len(d["aandelen"]), "aandelen")
