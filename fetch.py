import yfinance as yf, json, math, datetime as dt, warnings
warnings.filterwarnings("ignore")
import pandas as pd
OK = json.load(open("ok.json"))

def cagr(a, b, n):
    if a and b and a > 0 and b > 0 and n > 0:
        return (b/a)**(1/n) - 1
    return None

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
        cuts = sum(1 for i in range(1, len(full)) if by_year[full[i]] < by_year[full[i-1]] * 0.98)
        out[t] = {
            "ticker": t,
            "naam": info.get("longName") or info.get("shortName") or t,
            "sector": info.get("sector"),
            "koers": round(float(price), 4) if price else None,
            "valuta": info.get("currency"),
            "mcap": info.get("marketCap"),
            "div_hist": by_year,
            "d0": round(float(d0), 5) if d0 else 0,
            "g3": round(g3, 4) if g3 is not None else None,
            "g5": round(g5, 4) if g5 is not None else None,
            "cuts_sinds_2010": cuts,
            "eps": info.get("trailingEps"),
            "eps_fwd": info.get("forwardEps"),
            "payout": info.get("payoutRatio"),
            "fcf": info.get("freeCashflow"),
            "shares": info.get("sharesOutstanding"),
            "netdebt": (info.get("totalDebt") or 0) - (info.get("totalCash") or 0),
            "ebitda": info.get("ebitda"),
            "yield_ttm": info.get("dividendYield"),
            "beta": info.get("beta"),
            "opgehaald": dt.datetime.utcnow().isoformat(timespec="seconds")+"Z",
        }
    except Exception as e:
        out[t] = {"ticker": t, "fout": str(e)[:120]}
json.dump(out, open("raw.json","w"), indent=1)
print("klaar:", len(out), "| met koers:", sum(1 for v in out.values() if v.get("koers")))
