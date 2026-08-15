"""Zet goedgekeurde voorstellen om in overrides.json. Toont eerst wat er verandert."""
import json, sys, datetime as dt
V = json.load(open("voorstellen.json"))
O = json.load(open("overrides.json"))
auto = "--ja" in sys.argv
tickers = [a for a in sys.argv[1:] if not a.startswith("--")] or list(V)

for tk in tickers:
    v = V.get(tk, {}).get("voorstel")
    if not v or not v.get("divs"):
        print(f"{tk}: geen bruikbaar voorstel"); continue
    huidig = O.get(tk, {})
    print(f"\n{tk}\n  nu:      {huidig.get('divs', '-')}  g_na={huidig.get('g_na','-')}")
    print(f"  nieuw:   {v['divs']}  g_na={v.get('g_na') or 'ongewijzigd'}")
    for b in V[tk].get("bewijs", [])[:3]:
        print(f"    | {b['zin'][:150]}")
    if not auto and input("  overnemen? [j/N] ").lower() != "j":
        continue
    O[tk] = {"divs": v["divs"], "g_na": v.get("g_na") or huidig.get("g_na", 0.03),
             "bron": V[tk]["url"], "gecheckt": str(dt.date.today())}
    print("  overgenomen")
json.dump(O, open("overrides.json", "w"), indent=1, ensure_ascii=False)
