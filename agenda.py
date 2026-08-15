"""Houdt per bedrijf bij wanneer er cijfers komen en of de guidance in
overrides.json daarna nog is nagelopen. Schrijft agenda.json.

Statussen:
  nooit      - geen override, model rekent met historische groei
  verouderd  - er zijn cijfers geweest na je laatste controle
  binnenkort - cijfers binnen 10 dagen
  vers       - guidance nagelopen na de laatste rapportage
"""
import json, datetime as dt, warnings, time
warnings.filterwarnings("ignore")
import yfinance as yf

OK = json.load(open("ok.json"))
OV = json.load(open("overrides.json"))
VANDAAG = dt.date.today()
VENSTER = 10  # dagen vooruit waarbinnen we "binnenkort" melden

def soort(d):
    """Nederlandse rapportagekalender: welk type cijfers hoort bij deze maand."""
    m = d.month
    if m in (1, 2, 3):   return "jaarcijfers"
    if m in (4, 5):      return "Q1"
    if m in (6, 7, 8):   return "halfjaarcijfers"
    return "Q3"

def datums(tk):
    laatste = volgende = None
    t = yf.Ticker(tk)
    try:
        ed = t.get_earnings_dates(limit=24)
        if ed is not None and len(ed):
            alle = sorted(d.date() for d in ed.index.to_pydatetime())
            verleden = [d for d in alle if d <= VANDAAG]
            toekomst = [d for d in alle if d > VANDAAG]
            laatste = verleden[-1] if verleden else None
            volgende = toekomst[0] if toekomst else None
    except Exception:
        pass
    if volgende is None:
        try:
            c = t.calendar or {}
            e = c.get("Earnings Date")
            if isinstance(e, list) and e:
                e = e[0]
            if isinstance(e, dt.date) and e > VANDAAG:
                volgende = e
        except Exception:
            pass
    return laatste, volgende

res = {}
for tk in OK:
    laatste, volgende = datums(tk)
    ov = OV.get(tk) if isinstance(OV.get(tk), dict) else None
    gecheckt = None
    if ov and ov.get("gecheckt"):
        try:
            gecheckt = dt.date.fromisoformat(ov["gecheckt"])
        except ValueError:
            pass

    if not ov:
        status = "nooit"
    elif gecheckt is None:
        status = "verouderd"
    elif laatste and gecheckt < laatste:
        status = "verouderd"
    elif volgende and (volgende - VANDAAG).days <= VENSTER:
        status = "binnenkort"
    else:
        status = "vers"

    res[tk] = {
        "laatste_cijfers": str(laatste) if laatste else None,
        "laatste_soort": soort(laatste) if laatste else None,
        "volgende_cijfers": str(volgende) if volgende else None,
        "volgende_soort": soort(volgende) if volgende else None,
        "dagen_tot": (volgende - VANDAAG).days if volgende else None,
        "guidance_gecheckt": str(gecheckt) if gecheckt else None,
        "guidance_bron": ov.get("bron") if ov else None,
        "status": status,
    }
    time.sleep(0.15)

json.dump({"bijgewerkt": str(VANDAAG), "bedrijven": res},
          open("agenda.json", "w"), indent=1, ensure_ascii=False)

tel = {}
for v in res.values():
    tel[v["status"]] = tel.get(v["status"], 0) + 1
print("agenda.json:", tel)

nodig = [t for t, v in res.items() if v["status"] in ("verouderd", "binnenkort")]
if nodig:
    print("\nGuidance nalopen:")
    for t in nodig:
        v = res[t]
        wat = (f"cijfers {v['laatste_cijfers']} ({v['laatste_soort']})" if v["status"] == "verouderd"
               else f"{v['volgende_soort']} over {v['dagen_tot']} dgn")
        print(f"  {t:11} {v['status']:11} {wat}")
    print(f"\n  python guidance.py {' '.join(nodig[:12])}")
