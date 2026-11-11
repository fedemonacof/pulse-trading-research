"""Strategie modulari: ognuna espone generate_signals(data) -> [Signal] e score_series(df) per il backtest.
Lo stesso codice serve al bot dal vivo e al backtest: nessuna logica duplicata."""
from .base import Signal, Strategy
from .meanrev import MeanReversion
from .regime import REGIMES, Regime, detect_regime, regime_series
from .trend import TrendFollowing

__all__ = ["Signal", "Strategy", "TrendFollowing", "MeanReversion", "Regime", "REGIMES", "detect_regime", "regime_series"]
