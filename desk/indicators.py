"""Indicatori tecnici calcolati in modo deterministico: i numeri li fa il codice, non l'LLM."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).fillna(100).iloc[-1])


def atr(df: pd.DataFrame, n: int = 14) -> float:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def macd_hist(close: pd.Series) -> float:
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return float((macd - macd.ewm(span=9, adjust=False).mean()).iloc[-1])


def quant_scores(close: pd.Series) -> pd.Series:
    """Segnale trend + momentum in [-1, 1], calcolato per ogni giorno (usato anche dal backtest).

    Componenti classiche di trend following: prezzo vs SMA50 e SMA200, momentum a 3 e 12 mesi
    (escluso l'ultimo mese, per evitare l'inversione di breve). Ogni componente vale +1 o -1.
    """
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    mom3 = close.shift(21) / close.shift(63) - 1
    mom12 = close.shift(21) / close.shift(252) - 1
    parts = [np.sign(close - sma50), np.sign(close - sma200), np.sign(mom3), np.sign(mom12)]
    return (sum(parts) / len(parts)).where(sma200.notna())


def snapshot(daily: pd.DataFrame, intraday: pd.DataFrame | None = None) -> dict:
    c = daily["close"]
    last = float(intraday["close"].iloc[-1]) if intraday is not None and len(intraday) else float(c.iloc[-1])
    rets = c.pct_change().dropna()

    def sma(n):
        return round(float(c.tail(n).mean()), 2) if len(c) >= n else None

    def chg(n):
        return round(last / float(c.iloc[-n - 1]) - 1, 4) if len(c) > n else None

    snap = {
        "price": round(last, 2),
        "chg_1d": chg(1), "chg_5d": chg(5), "chg_21d": chg(21), "chg_63d": chg(63), "chg_252d": chg(252),
        "sma20": sma(20), "sma50": sma(50), "sma200": sma(200),
        "rsi14": round(rsi(c), 1),
        "macd_hist": round(macd_hist(c), 3),
        "atr14": round(atr(daily), 2),
        "vol_20d_annual": round(float(rets.tail(20).std() * np.sqrt(252)), 3),
        "drawdown_from_52w_high": round(last / float(c.tail(252).max()) - 1, 4),
        "volume_vs_20d_avg": round(float(daily["volume"].iloc[-1] / daily["volume"].tail(20).mean()), 2),
    }
    qs = quant_scores(c).iloc[-1]
    snap["quant_score"] = None if pd.isna(qs) else round(float(qs), 2)
    if intraday is not None and len(intraday) > 1:
        ic = intraday["close"]
        vwap = float((ic * intraday["volume"]).sum() / intraday["volume"].sum())
        snap.update({
            "intraday_chg": round(last / float(intraday["open"].iloc[0]) - 1, 4),
            "intraday_vs_vwap": round(last / vwap - 1, 4),
            "intraday_rsi": round(rsi(ic), 1),
        })
    return snap
