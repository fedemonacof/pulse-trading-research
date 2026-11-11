"""Riscarica i dati dei test di ricerca (non sono nel repository: i prezzi Yahoo non vanno ridistribuiti).

    python scripts/fetch_data.py

Scrive:
- data/sp500/components.csv          composizione storica dell'S&P 500 (github.com/fja05680/sp500)
- data/sp500/yahoo_2003_2020.pkl     prezzi giornalieri dei membri 2005-2019 + i 15 titoli di default (giu 2003 - gen 2020)
- data/pulse_st/etf_1999_2019.pkl    ETF settoriali SPDR + SPY fino al 31/12/2019 (il test di PULSE-ST resta chiuso)

Ci vogliono 15-20 minuti: Yahoo limita le richieste, quindi si va piano e si riprova. I titoli senza storico
(400/404, di solito delistati) si saltano subito. Yahoo corregge e cambia i dati nel tempo: i numeri dei test
possono differire leggermente da quelli nei documenti.
"""
from __future__ import annotations

import pickle
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from desk.research import yahoo_between  # noqa: E402
from desk.universe import FIXED_15  # noqa: E402

COMPONENTS = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
              "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")
SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "SPY"]


def fetch(url: str) -> bytes:
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):                      # nessun dato per quel titolo
                return b'{"chart":{"result":[{}]}}'
            time.sleep(6 * (attempt + 1))                  # 429: troppe richieste
        except Exception:
            time.sleep(6 * (attempt + 1))
    print("non riuscito:", url, flush=True)
    return b'{"chart":{"result":[{}]}}'


def main() -> None:
    (ROOT / "data" / "sp500").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "pulse_st").mkdir(parents=True, exist_ok=True)

    comp_path = ROOT / "data" / "sp500" / "components.csv"
    comp_path.write_bytes(fetch(COMPONENTS))
    comp = pd.read_csv(comp_path)
    comp = comp[(comp.date >= "2004-12-01") & (comp.date <= "2019-12-31")]
    tickers = sorted({s.replace(".", "-") for t in comp.tickers for s in t.split(",")} | set(FIXED_15))
    print(f"composizione: {len(tickers)} ticker da scaricare", flush=True)

    prices = {}
    for i, t in enumerate(tickers):
        prices.update(yahoo_between([t], "2003-06-01", "2020-01-31", fetch=fetch))
        time.sleep(0.4)
        if i % 50 == 0:
            print(f"{i}/{len(tickers)} · {len(prices)} con dati", flush=True)
    with open(ROOT / "data" / "sp500" / "yahoo_2003_2020.pkl", "wb") as f:
        pickle.dump(prices, f)

    etf = yahoo_between(SECTOR_ETFS, "1998-12-01", "2020-01-01", fetch=fetch)
    etf = {s: d[d.index < "2020-01-01"] for s, d in etf.items()}
    with open(ROOT / "data" / "pulse_st" / "etf_1999_2019.pkl", "wb") as f:
        pickle.dump(etf, f)
    print(f"fatto: {len(prices)} serie di azioni, {len(etf)} ETF")


if __name__ == "__main__":
    main()
