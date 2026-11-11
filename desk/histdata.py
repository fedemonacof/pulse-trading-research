"""Storico giornaliero per il backtest.

    YahooHistory   gratuito, senza chiavi (endpoint pubblico non ufficiale: dati indicativi)
    AlpacaHistory  barre storiche Alpaca, quando le chiavi sono nel .env

Entrambi restituiscono {simbolo: DataFrame con open, high, low, close, volume} indicizzato per data.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd

log = logging.getLogger("desk.histdata")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class YahooHistory:
    def __init__(self, timeout: float = 20.0, fetch=None):
        self.timeout = timeout
        self._fetch = fetch or self._http

    def _http(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read()

    def one(self, symbol: str, years: int) -> pd.DataFrame:
        rng = "5y" if years > 2 else "2y"
        if years > 5:
            rng = "10y"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d&events=split,div"
        raw = json.loads(self._fetch(url))["chart"]["result"][0]
        q = raw["indicators"]["quote"][0]
        adj = raw["indicators"].get("adjclose", [{}])[0].get("adjclose")
        df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                          index=pd.to_datetime(raw["timestamp"], unit="s").normalize())
        if adj:  # prezzi rettificati per dividendi e split: confronto onesto col buy & hold
            ratio = pd.Series(adj, index=df.index) / df["close"]
            for k in ("open", "high", "low", "close"):
                df[k] = df[k] * ratio
        df = df.dropna()
        df = df[~df.index.duplicated(keep="last")]
        cutoff = df.index.max() - pd.Timedelta(days=int(365.25 * years) + 5)
        return df[df.index >= cutoff]

    def daily(self, symbols: list[str], years: int = 3) -> dict[str, pd.DataFrame]:
        def get(s):
            try:
                return s, self.one(s, years)
            except Exception as e:
                log.warning("Storico non disponibile per %s: %s", s, e)
                return s, None

        with ThreadPoolExecutor(max_workers=6) as pool:
            return {s: df for s, df in pool.map(get, symbols) if df is not None and len(df)}


class AlpacaHistory:
    def __init__(self, key: str, secret: str):
        from alpaca.data.historical import StockHistoricalDataClient

        self.client = StockHistoricalDataClient(key, secret)

    def daily(self, symbols: list[str], years: int = 3) -> dict[str, pd.DataFrame]:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = datetime.now(timezone.utc) - timedelta(days=int(365.25 * years) + 5)
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start,
                               adjustment=Adjustment.ALL, feed=DataFeed.IEX)
        df = self.client.get_stock_bars(req).df
        out = {}
        for s in symbols:
            try:
                d = df.xs(s, level="symbol")[["open", "high", "low", "close", "volume"]].copy()
            except KeyError:
                continue
            d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
            out[s] = d
        return out
