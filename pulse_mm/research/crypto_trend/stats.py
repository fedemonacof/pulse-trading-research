"""Statistiche ed esiti di PULSE-CT (sezione 7 della pre-registrazione).

- DD = perdita massima dal picco, numero positivo. ΔDD = DD strategia − DD benchmark: migliore se < 0.
- ΔSharpe = Sharpe strategia − Sharpe benchmark, Sharpe annualizzato con √365.
- IC90 da bootstrap circolare a blocchi, con gli stessi indici per strategia e benchmark.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config


def sharpe(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(config.ANN)) if sd > 0 else 0.0


def max_dd(r: np.ndarray) -> float:
    path = np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(r, dtype=float))])
    peak = np.maximum.accumulate(path)
    return float(1.0 - (path / peak).min())


def cagr(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    growth = float(np.prod(1.0 + r))
    return growth ** (config.ANN / len(r)) - 1.0 if len(r) else 0.0


def summary(r: pd.Series) -> dict:
    x = r.to_numpy()
    return {"sharpe": sharpe(x), "max_dd": max_dd(x), "cagr": cagr(x), "days": len(x)}


def paired_bootstrap(r_s: pd.Series, r_b: pd.Series, block: int = config.BOOT_BLOCK, n: int = config.BOOT_N,
                     seed: int = config.SEED, level: float = config.LEVEL) -> dict:
    s, b = r_s.to_numpy(), r_b.to_numpy()
    if len(s) != len(b):
        raise ValueError("Strategia e benchmark devono avere gli stessi giorni")
    T = len(s)
    rng = np.random.default_rng(seed)
    k = math.ceil(T / block)
    d_sh, d_dd = np.empty(n), np.empty(n)
    for i in range(n):
        starts = rng.integers(0, T, k)
        idx = ((starts[:, None] + np.arange(block)[None, :]) % T).ravel()[:T]
        d_sh[i] = sharpe(s[idx]) - sharpe(b[idx])
        d_dd[i] = max_dd(s[idx]) - max_dd(b[idx])
    q = [(1 - level) / 2 * 100, (1 + level) / 2 * 100]
    lo_sh, hi_sh = np.percentile(d_sh, q)
    lo_dd, hi_dd = np.percentile(d_dd, q)
    return {"block": block, "n": n, "seed": seed,
            "d_sharpe": sharpe(s) - sharpe(b), "d_sharpe_lo": float(lo_sh), "d_sharpe_hi": float(hi_sh),
            "d_dd": max_dd(s) - max_dd(b), "d_dd_lo": float(lo_dd), "d_dd_hi": float(hi_dd)}


def outcome(boot: dict, margin: float = config.SHARPE_MARGIN) -> str:
    """Tabella della sezione 7: passa, fallisce, non concludente."""
    dd_better = boot["d_dd_hi"] < 0
    dd_worse = boot["d_dd_lo"] > 0
    if boot["d_sharpe_hi"] < margin or dd_worse:
        return "fallisce"
    if dd_better and boot["d_sharpe_lo"] > margin:
        return "passa"
    return "non concludente"


def deflated_sharpe(r: pd.Series, n_trials: int = config.N_TRIALS) -> dict:
    """Deflated Sharpe Ratio (Bailey e López de Prado, 2014), con annualizzazione a 365 giorni."""
    x = r.dropna().to_numpy()
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    skew = float(pd.Series(x).skew())
    kurt = float(pd.Series(x).kurt()) + 3.0
    nd, gamma = NormalDist(), 0.5772156649
    sr0 = math.sqrt(1 / T) * ((1 - gamma) * nd.inv_cdf(1 - 1 / n_trials) + gamma * nd.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return {"sharpe_annual": sr * math.sqrt(config.ANN), "sr0_annual": sr0 * math.sqrt(config.ANN),
            "dsr": nd.cdf(z), "n_trials": n_trials}
