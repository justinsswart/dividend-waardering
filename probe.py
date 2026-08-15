import yfinance as yf, json, sys
from tickers import ALL
ok, bad = [], []
d = yf.download(ALL, period="5d", progress=False, auto_adjust=False)
try:
    close = d["Close"]
    for t in ALL:
        if t in close and close[t].dropna().shape[0] > 0: ok.append(t)
        else: bad.append(t)
except Exception as e:
    print("ERR", e)
print("OK", len(ok)); print("BAD", bad)
json.dump(ok, open("ok.json","w"))
