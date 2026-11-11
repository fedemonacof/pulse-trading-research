"""Dati di mercato e notizie (Alpaca) + un fornitore simulato per i test."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import numpy as np
import pandas as pd


@dataclass
class NewsItem:
    created_at: datetime
    headline: str
    summary: str
    source: str
    symbols: list[str]


class MarketData(Protocol):
    def daily_bars(self, symbols: list[str], days: int = 300) -> dict[str, pd.DataFrame]: ...
    def intraday_bars(self, symbols: list[str], minutes: int = 390) -> dict[str, pd.DataFrame]: ...
    def latest_prices(self, symbols: list[str]) -> dict[str, float]: ...
    def news(self, symbols: list[str], since: datetime) -> list[NewsItem]: ...


def _split_by_symbol(df: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    if df is None or df.empty:
        return out
    for s in symbols:
        try:
            out[s] = df.xs(s, level="symbol")[["open", "high", "low", "close", "volume"]].copy()
        except KeyError:
            continue
    return out


class AlpacaData:
    def __init__(self, key: str, secret: str):
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.historical.news import NewsClient

        self.stocks = StockHistoricalDataClient(key, secret)
        self.news_client = NewsClient(key, secret)
        # IEX è gratuito; con abbonamento dati usa DATA_FEED=sip
        self.feed = DataFeed(os.getenv("DATA_FEED", "iex"))

    def _bars(self, symbols, timeframe, start) -> dict[str, pd.DataFrame]:
        from alpaca.data.requests import StockBarsRequest

        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=timeframe, start=start, feed=self.feed)
        return _split_by_symbol(self.stocks.get_stock_bars(req).df, symbols)

    def daily_bars(self, symbols, days=300):
        from alpaca.data.timeframe import TimeFrame

        return self._bars(symbols, TimeFrame.Day, datetime.now(timezone.utc) - timedelta(days=int(days * 1.5)))

    def intraday_bars(self, symbols, minutes=390):
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        start = datetime.now(timezone.utc) - timedelta(minutes=minutes * 3)
        return self._bars(symbols, TimeFrame(5, TimeFrameUnit.Minute), start)

    def latest_prices(self, symbols):
        from alpaca.data.requests import StockLatestTradeRequest

        trades = self.stocks.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbols, feed=self.feed)
        )
        return {s: float(t.price) for s, t in trades.items()}

    def news(self, symbols, since):
        from alpaca.data.requests import NewsRequest

        res = self.news_client.get_news(
            NewsRequest(symbols=",".join(symbols), start=since, limit=50, exclude_contentless=True)
        )
        raw = res.data.get("news", []) if hasattr(res, "data") else res.get("news", [])
        items = []
        for n in raw:
            items.append(
                NewsItem(
                    created_at=n.created_at,
                    headline=n.headline,
                    summary=(n.summary or "")[:500],
                    source=n.source,
                    symbols=list(n.symbols or []),
                )
            )
        return items


class SimData:
    """Prezzi sintetici (random walk deterministico) per test e demo senza chiavi."""

    def __init__(self, symbols: list[str], seed: int = 7, news: list[NewsItem] | None = None, days: int = 300):
        rng = np.random.default_rng(seed)
        self._daily = {}
        self._intraday = {}
        for i, s in enumerate(symbols):
            drift = 0.0006 * (1 if i % 2 == 0 else -1)
            close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, days)))
            self._daily[s] = self._ohlc(close, pd.date_range(end="2026-11-10", periods=days, freq="B"), rng)
            intr = close[-1] * np.exp(np.cumsum(rng.normal(0, 0.002, 78)))
            self._intraday[s] = self._ohlc(intr, pd.date_range(end="2026-11-10 16:00", periods=78, freq="5min"), rng)
        self._news = news or []
        self.overrides: dict[str, float] = {}

    @staticmethod
    def _ohlc(close, idx, rng):
        spread = np.abs(rng.normal(0, 0.006, len(close))) * close
        return pd.DataFrame(
            {"open": close, "high": close + spread, "low": close - spread, "close": close,
             "volume": rng.integers(1e5, 1e6, len(close))},
            index=idx,
        )

    def daily_bars(self, symbols, days=300):
        return {s: self._daily[s].tail(days) for s in symbols if s in self._daily}
    def intraday_bars(self, symbols, minutes=390):
        return {s: self._intraday[s] for s in symbols if s in self._intraday}

    def latest_prices(self, symbols):
        return {s: self.overrides.get(s, float(self._intraday[s]["close"].iloc[-1])) for s in symbols if s in self._intraday}

    def news(self, symbols, since):
        return [n for n in self._news if set(n.symbols) & set(symbols)]
