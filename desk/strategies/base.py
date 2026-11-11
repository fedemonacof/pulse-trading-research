"""Interfaccia comune delle strategie."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass
class Signal:
    symbol: str
    side: str            # "buy" | "sell" | "hold"
    confidence: float    # 0-100
    reason: str          # spiegazione in italiano semplice
    strategy: str
    score: float = 0.0   # -100..+100: positivo = rialzista, negativo = ribassista

    @classmethod
    def from_score(cls, symbol: str, score: float, reason: str, strategy: str, enter: float = 55.0) -> "Signal":
        side = "buy" if score >= enter else "sell" if score <= -enter else "hold"
        return cls(symbol, side, round(abs(score), 1), reason, strategy, round(score, 1))


class Strategy(Protocol):
    name: str

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Indicatori + colonna 'score' per ogni barra, calcolati solo con i dati fino a quella barra."""

    def explain(self, row: pd.Series) -> str:
        """Motivo leggibile per l'ultima barra."""

    def applies_to(self, symbol: str) -> bool: ...


def generate_signals(strategy: Strategy, data: dict[str, pd.DataFrame]) -> list[Signal]:
    """data: barre giornaliere OHLCV per simbolo. Restituisce un segnale per simbolo (anche 'hold')."""
    out = []
    for symbol, df in data.items():
        if not strategy.applies_to(symbol):
            continue
        if df is None or len(df) < 60:
            out.append(Signal(symbol, "hold", 0.0, "storico insufficiente", strategy.name))
            continue
        row = strategy.frame(df).iloc[-1]
        score = 0.0 if pd.isna(row["score"]) else float(row["score"])
        out.append(Signal.from_score(symbol, score, strategy.explain(row), strategy.name))
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()
