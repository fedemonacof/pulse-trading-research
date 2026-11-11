"""Riconoscitore di regime su SPY: trending / mean_reverting / high_vol / crisis.

Usa SPY contro la media a 200 giorni, la volatilità realizzata, l'ATR e l'efficiency ratio
(quanto il prezzo si è mosso in linea retta). Il regime sceglie quanto pesa ogni strategia.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import atr

# Pesi delle strategie e dimensione delle posizioni per regime. Sono costanti nel codice:
# la revisione notturna li moltiplica per pesi propri limitati, ma non li riscrive.
REGIMES = {
    "trending":       {"trend": 1.00, "meanrev": 0.25, "size": 1.0, "longs": True},
    "mean_reverting": {"trend": 0.35, "meanrev": 1.00, "size": 1.0, "longs": True},
    "high_vol":       {"trend": 0.50, "meanrev": 0.70, "size": 0.5, "longs": True},
    "crisis":         {"trend": 0.60, "meanrev": 0.30, "size": 0.5, "longs": False},  # niente nuovi long
    "warming_up":     {"trend": 0.00, "meanrev": 0.00, "size": 0.0, "longs": False},  # storico insufficiente
}
LABELS = {"trending": "Trend", "mean_reverting": "Laterale", "high_vol": "Alta volatilità",
          "crisis": "Crisi", "warming_up": "In avvio"}


@dataclass
class Regime:
    name: str
    vol20: float | None
    atr_pct: float | None
    dist_sma200: float | None
    efficiency: float | None
    reason: str

    @property
    def label(self) -> str:
        return LABELS[self.name]


def regime_frame(spy: pd.DataFrame) -> pd.DataFrame:
    c = spy["close"]
    f = pd.DataFrame(index=spy.index)
    f["sma200"] = c.rolling(200).mean()
    f["dist_sma200"] = c / f["sma200"] - 1
    f["vol20"] = c.pct_change().rolling(20).std() * np.sqrt(252)
    f["atr_pct"] = atr(spy) / c
    f["dd_252"] = c / c.rolling(252, min_periods=60).max() - 1
    move = (c - c.shift(20)).abs()
    path = c.diff().abs().rolling(20).sum()
    f["efficiency"] = move / path.replace(0, np.nan)
    crisis = (f["dist_sma200"] < 0) & ((f["vol20"] > 0.30) | (f["dd_252"] < -0.20))
    high_vol = (f["vol20"] > 0.22) | (f["atr_pct"] > 0.02)
    trending = (f["efficiency"] > 0.30) & (f["dist_sma200"].abs() > 0.02)
    f["regime"] = np.select([f["sma200"].isna(), crisis, high_vol, trending],
                            ["warming_up", "crisis", "high_vol", "trending"], default="mean_reverting")
    return f


def regime_series(spy: pd.DataFrame) -> pd.Series:
    return regime_frame(spy)["regime"]


def detect_regime(spy: pd.DataFrame) -> Regime:
    r = regime_frame(spy).iloc[-1]
    name = str(r["regime"])

    def v(x):
        return None if pd.isna(x) else float(x)

    if name == "warming_up":
        reason = "meno di 200 giorni di storico su SPY"
    else:
        reason = (f"SPY {'sopra' if r['dist_sma200'] > 0 else 'sotto'} la media a 200 giorni di "
                  f"{abs(r['dist_sma200']) * 100:.1f}%, volatilità {r['vol20'] * 100:.0f}% annua, "
                  f"efficienza del movimento {r['efficiency']:.2f}")
    return Regime(name, v(r["vol20"]), v(r["atr_pct"]), v(r["dist_sma200"]), v(r["efficiency"]), reason)
