"""Dati sintetici e finti per i test: nessuna rete, nessuna chiave."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest


def make_daily(n=320, drift=0.0005, vol=0.006, start=100.0, seed=1, end="2026-11-06") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.bdate_range(end=end, periods=n)
    spread = np.abs(rng.normal(0, vol / 2, n)) * close + close * 0.001
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + spread,
                         "low": np.minimum(open_, close) - spread, "close": close,
                         "volume": rng.integers(1e6, 2e6, n).astype(float)}, index=idx)


class FakeData:
    """MarketData finto: barre giornaliere fisse, prezzi = ultima chiusura (modificabili)."""

    def __init__(self, daily: dict[str, pd.DataFrame]):
        self.daily = daily
        self.overrides: dict[str, float] = {}

    def daily_bars(self, symbols, days=300):
        out = {}
        for s in symbols:
            if s in self.daily:
                df = self.daily[s].tail(days).copy()
                df.attrs["symbol"] = s
                out[s] = df
        return out

    def intraday_bars(self, symbols, minutes=390):
        return {}

    def latest_prices(self, symbols):
        return {s: self.overrides.get(s, float(self.daily[s]["close"].iloc[-1])) for s in symbols if s in self.daily}

    def news(self, symbols, since):
        return []


class FakeStrategy:
    """Strategia con punteggi fissi per titolo: rende deterministici i test del motore."""

    def __init__(self, name, scores: dict[str, float], universe=None):
        self.name, self.scores, self.universe = name, scores, universe

    def applies_to(self, s):
        return self.universe is None or s in self.universe

    def frame(self, df):
        f = pd.DataFrame(index=df.index)
        f["score"] = np.nan
        f.loc[f.index[-1], "score"] = self.scores.get(df.attrs.get("symbol"), 0.0)
        f["spread_pct"] = 1.0
        return f

    def explain(self, row):
        return f"{self.name} finto"


class Clock:
    def __init__(self, t=datetime(2026, 11, 6, 16, 0, tzinfo=timezone.utc)):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()
