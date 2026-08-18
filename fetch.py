import yfinance as yf, json, math, datetime as dt, warnings
warnings.filterwarnings("ignore")
import pandas as pd
OK = json.load(open("ok.json"))

def risicovrije_voet():
    """Haalt de tienjaarsrente op AAA-staatsobligaties uit de eurozone bij de ECB.

    Het model rekende hiervoor met een vaste 3,0%. Dat is de voet waar alles aan hangt:
    de ondergrens van het vereist rendement en het stabiele rendement dat op tweederde
    van de waarde drukt. Staat de rente structureel lager, dan zijn alle koopprijzen
    te laag - en andersom.

    We nemen het gemiddelde over circa zes maanden (130 handelsdagen) in plaats van de
    slotstand, zodat de koopprijzen niet meebewegen met dagruis. Lukt het ophalen niet,
    dan blijft de vorige waarde uit markt.json staan; is die er ook niet, dan valt het
    terug op 3,0%.
    """
    import urllib.request, csv, io, statistics
    url = ("https://data-api.ecb.europa.eu/service/data/YC/"
           "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?format=csvdata&lastNObservations=130")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dividend-waardering/1.0"})
        rijen = list(csv.DictReader(io.StringIO(
            urllib.request.urlopen(req, timeout=30).read().decode())))
        w = [float(r["OBS_VALUE"]) for r in rijen if r.get("OBS_VALUE")]
        if len(w) < 30:
            raise ValueError(f"te weinig waarnemingen: {len(w)}")
        gem = statistics.mean(w) / 100
        # veiligheidsband: buiten 0,5%-6,0% is er iets mis met de bron, niet met de markt
        if not 0.005 <= gem <= 0.060:
            raise ValueError(f"onwaarschijnlijke rente: {gem:.4f}")
        return {"rf": round(gem, 5), "rf_laatst": round(w[-1] / 100, 5),
                "waarnemingen": len(w), "van": rijen[0]["TIME_PERIOD"],
                "tot": rijen[-1]["TIME_PERIOD"],
                "bron": "ECB Data Portal, spotrente AAA-staatsobligaties eurozone, 10 jaar",
                "opgehaald": dt.date.today().isoformat()}
    except Exception as e:
        try:
            vorig = json.load(open("markt.json"))
            vorig["waarschuwing"] = f"ophalen mislukt ({str(e)[:80]}), vorige waarde aangehouden"
            return vorig
        except Exception:
            return {"rf": 0.030, "bron": "terugval: vaste 3,0%",
                    "waarschuwing": f"ophalen mislukt ({str(e)[:80]}) en geen markt.json aanwezig",
                    "opgehaald": dt.date.today().isoformat()}

markt = risicovrije_voet()
json.dump(markt, open("markt.json", "w"), indent=1, ensure_ascii=False)
print(f"risicovrije voet: {markt['rf']*100:.2f}%  ({markt.get('bron','')})")
if markt.get("waarschuwing"):
    print("  let op:", markt["waarschuwing"])

def cagr(a, b, n):
    if a and b and a > 0 and b > 0 and n > 0:
        return (b/a)**(1/n) - 1
    return None


def bereken_betas(tickers, index="^AEX"):
    """Berekent de beta zelf uit koershistorie, in plaats van het veld van de databron.

    Aanleiding: die geleverde beta's waren onbruikbaar. Shell stond op -0,218 (een
    aandeel dat tegen de markt in beweegt), Flow Traders op 0,124, Wolters Kluwer op
    0,185. Gevolg: 33 van de 54 aandelen belandden op de ondergrens van 7% en kregen
    dus allemaal dezelfde disconteringsvoet - waarmee het verschil in risico uit het
    model verdween.

    Methode: vijf jaar weekrendementen tegen de AEX. Naast de beta bewaren we R2 en
    het aantal waarnemingen, zodat valuate.py kan wegen hoeveel de uitkomst waard is.
    Bij een R2 van 0,02 (KPN) verklaart de markt vrijwel niets van de koersbeweging en
    is een lage beta geen bewijs van laag risico, maar van weinig samenhang.
    """
    import numpy as np
    try:
        px = yf.download(list(tickers) + [index], period="5y", interval="1wk",
                         auto_adjust=True, progress=False)["Close"]
    except Exception as e:
        print("beta's ophalen mislukt:", str(e)[:100])
        return {}
    r = np.log(px / px.shift(1))
    if index not in r:
        return {}
    m = r[index].dropna()
    uit = {}
    for t in tickers:
        if t not in r:
            continue
        s = r[t].dropna()
        j = s.index.intersection(m.index)
        if len(j) < 60:            # minder dan ruim een jaar: niets zinnigs te zeggen
            continue
        var = np.var(m[j], ddof=1)
        if var <= 0:
            continue
        b = float(np.cov(s[j], m[j])[0, 1] / var)
        corr = float(np.corrcoef(s[j], m[j])[0, 1])
        uit[t] = {"beta_regressie": round(b, 4),
                  "beta_r2": round(corr ** 2, 4),
                  "beta_n": int(len(j))}
    return uit


BETAS = bereken_betas(OK)
print(f"beta's berekend: {len(BETAS)} van {len(OK)}")

out = {}
for t in OK:
    try:
        tk = yf.Ticker(t)
        info = tk.info or {}
        div = tk.dividends
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            h = tk.history(period="5d")
            price = float(h["Close"].iloc[-1]) if len(h) else None
        # dividend per kalenderjaar
        by_year = {}
        if div is not None and len(div):
            s = div.copy(); s.index = pd.to_datetime(s.index).tz_localize(None)
            by_year = s.groupby(s.index.year).sum().to_dict()
            by_year = {int(k): round(float(v), 5) for k, v in by_year.items()}
        yrs = sorted([y for y in by_year if y >= 2010])
        cur = dt.date.today().year
        full = [y for y in yrs if y < cur]
        d0 = by_year.get(cur - 1) or (by_year.get(full[-1]) if full else 0)
        g5 = cagr(by_year.get(cur-6), by_year.get(cur-1), 5) if len(full) >= 6 else None
        g3 = cagr(by_year.get(cur-4), by_year.get(cur-1), 3) if len(full) >= 4 else None
        # Een verlaging telt alleen als de uitkering fors onder het NIVEAU van de
        # voorgaande jaren zakt en daar ook niet snel van herstelt. Vergelijken met
        # een enkel voorgaand jaar telt speciale dividenden en verschoven betaaldata
        # mee als verlaging: KPN kwam zo op -95% uit, ASM op -90%.
        cuts, diepste = 0, 0.0
        for i in range(3, len(full)):
            eerder = sorted(by_year[full[j]] for j in range(i - 3, i))
            basis = eerder[1]                       # mediaan van de drie jaar ervoor
            nu = by_year[full[i]]
            if basis <= 0 or nu >= basis * 0.85:
                continue
            hersteld = any(by_year[full[k]] >= basis * 0.95
                           for k in range(i + 1, min(i + 3, len(full))))
            if not hersteld:
                cuts += 1
                diepste = min(diepste, nu / basis - 1)

        # aandelenaantal en beurswaarde: aanvullen als info ze niet levert
        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        mcap = info.get("marketCap")
        if not shares or not mcap:
            try:
                fi = tk.fast_info
                shares = shares or getattr(fi, "shares", None)
                mcap = mcap or getattr(fi, "market_cap", None)
            except Exception:
                pass
        if not mcap and shares and price:
            mcap = shares * price
        if not shares and mcap and price:
            shares = mcap / price

        # netto aandeleninkoop, gemiddeld over de beschikbare jaren
        inkoop = None
        try:
            cf = tk.cashflow
            rij = None
            for kand in ("Net Common Stock Issuance", "Repurchase Of Capital Stock"):
                tr = [i for i in cf.index if str(i) == kand]
                if tr: rij = tr[0]; break
            if rij is not None:
                w = [float(x) for x in cf.loc[rij].values[:3] if str(x) != "nan"]
                if w: inkoop = round(-sum(w)/len(w))
        except Exception:
            pass

        out[t] = {
            "netto_inkoop": inkoop,
            "ticker": t,
            "naam": info.get("longName") or info.get("shortName") or t,
            "sector": info.get("sector"),
            "koers": round(float(price), 4) if price else None,
            "valuta": info.get("currency"),
            "mcap": mcap,
            "div_hist": by_year,
            "d0": round(float(d0), 5) if d0 else 0,
            "g3": round(g3, 4) if g3 is not None else None,
            "g5": round(g5, 4) if g5 is not None else None,
            "cuts_sinds_2010": cuts,
            "diepste_verlaging": round(diepste, 3),
            "eps": info.get("trailingEps"),
            "eps_fwd": info.get("forwardEps"),
            "payout": info.get("payoutRatio"),
            "fcf": info.get("freeCashflow"),
            "shares": shares,
            "netdebt": (info.get("totalDebt") or 0) - (info.get("totalCash") or 0),
            "ebitda": info.get("ebitda"),
            "yield_ttm": info.get("dividendYield"),
            "beta": info.get("beta"),
            "roe": info.get("returnOnEquity"),
            "opgehaald": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
    except Exception as e:
        # netto aandeleninkoop, gemiddeld over de beschikbare jaren
        inkoop = None
        try:
            cf = tk.cashflow
            rij = None
            for kand in ("Net Common Stock Issuance", "Repurchase Of Capital Stock"):
                tr = [i for i in cf.index if str(i) == kand]
                if tr: rij = tr[0]; break
            if rij is not None:
                w = [float(x) for x in cf.loc[rij].values[:3] if str(x) != "nan"]
                if w: inkoop = round(-sum(w)/len(w))
        except Exception:
            pass

        out[t] = {"ticker": t, "fout": str(e)[:120]}
for t, b in BETAS.items():
    if t in out:
        out[t].update(b)
json.dump(out, open("raw.json","w"), indent=1)
print("klaar:", len(out), "| met koers:", sum(1 for v in out.values() if v.get("koers")))
