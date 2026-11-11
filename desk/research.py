"""Test pre-registrato (docs/preregistrazione-2005-2019.md): 5 portafogli, bootstrap a blocchi, Deflated Sharpe.

Il modulo NON fa parte del codice congelato: legge le strategie così come sono e si rifiuta di girare se
l'impronta dei file che decidono i trade non corrisponde a quella scritta nella pre-registrazione.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from statistics import NormalDist

import numpy as np
import pandas as pd

from .backtest import walk_forward
from .config import RiskLimits

FROZEN_FILES = ["desk/config.py", "desk/reflex.py", "desk/risk.py", "desk/backtest.py", "desk/strategies/__init__.py",
                "desk/strategies/base.py", "desk/strategies/meanrev.py", "desk/strategies/regime.py",
                "desk/strategies/trend.py"]
PREREG = "docs/preregistrazione-2005-2019.md"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------- Impronta del codice congelato

def fingerprint(files=FROZEN_FILES) -> str:
    lines = "".join(f"{hashlib.sha256(open(f, 'rb').read()).hexdigest()}  {f}\n" for f in files)
    return hashlib.sha256(lines.encode()).hexdigest()[:16]


def registered_fingerprint(path=PREREG) -> str:
    m = re.search(r"\*\*`([0-9a-f]{16})`\*\*", open(path, encoding="utf-8").read())
    if not m:
        raise SystemExit(f"Impronta non trovata in {path}")
    return m.group(1)


# ---------------------------------------------------------------- Dati storici per intervallo (Yahoo)

def yahoo_between(symbols: list[str], start: str, end: str, fetch=None) -> dict[str, pd.DataFrame]:
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())

    def http(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
            return r.read()

    fetch = fetch or http

    def one(sym):
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}"
               f"&interval=1d&events=split,div")
        raw = json.loads(fetch(url))["chart"]["result"][0]
        if not raw.get("timestamp"):
            return sym, None
        q = raw["indicators"]["quote"][0]
        adj = raw["indicators"].get("adjclose", [{}])[0].get("adjclose")
        df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                          index=pd.to_datetime(raw["timestamp"], unit="s").normalize())
        if adj:
            ratio = pd.Series(adj, index=df.index) / df["close"]
            for k in ("open", "high", "low", "close"):
                df[k] = df[k] * ratio
        df = df.dropna()
        return sym, df[~df.index.duplicated(keep="last")]

    with ThreadPoolExecutor(max_workers=6) as pool:
        return {s: d for s, d in pool.map(one, symbols) if d is not None and len(d)}


# ---------------------------------------------------------------- Portafogli

def curve_from_returns(r: pd.Series, initial: float = 100_000.0) -> pd.Series:
    return (1 + r.fillna(0)).cumprod() * initial


def monthly_mix(r_a: pd.Series, r_b: pd.Series, w_a: float) -> pd.Series:
    """Due componenti ribilanciate al peso w_a all'inizio di ogni mese (i pesi derivano dentro il mese)."""
    out = []
    for _, block in pd.DataFrame({"a": r_a, "b": r_b}).fillna(0).groupby(pd.Grouper(freq="ME")):
        va, vb = w_a, 1 - w_a
        for ra, rb in block.itertuples(index=False):
            before = va + vb
            va, vb = va * (1 + ra), vb * (1 + rb)
            out.append((va + vb) / before - 1)
    return pd.Series(out, index=r_a.fillna(0).index[: len(out)])


def faber_filter(spy_close: pd.Series, index: pd.DatetimeIndex, cost_bps: float = 6.0) -> pd.Series:
    """SPY se a fine mese è sopra la media a 200 giorni, altrimenti liquidità. Segnale del mese scorso: niente look-ahead."""
    sma = spy_close.rolling(200).mean()
    month_end = spy_close.groupby(spy_close.index.to_period("M")).tail(1)
    signal = (month_end > sma.reindex(month_end.index)).astype(float)
    signal.index = signal.index.to_period("M")
    r = spy_close.pct_change()
    w = pd.Series([signal.get(d.to_period("M") - 1, np.nan) for d in r.index], index=r.index).ffill().fillna(1.0)
    switches = w.diff().abs().fillna(0)
    out = w * r - switches * cost_bps / 10_000
    return out.reindex(index)


# ---------------------------------------------------------------- Statistiche e inferenza

def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


def summary(r: pd.Series) -> dict:
    c = curve_from_returns(r)
    years = len(r) / 252
    total = float(c.iloc[-1] / c.iloc[0] - 1) if len(c) else 0.0
    return {"cagr": (c.iloc[-1] / 100_000) ** (1 / years) - 1 if years > 0 else 0.0,
            "vol": float(r.std() * np.sqrt(252)), "sharpe": sharpe(r.to_numpy()),
            "max_drawdown": float((c / c.cummax() - 1).min()), "total": total}


def block_bootstrap_delta_sharpe(r_x: pd.Series, r_base: pd.Series, block: int = 21, n: int = 5000,
                                 seed: int = 7, level: float = 0.90) -> dict:
    """Bootstrap circolare a blocchi: gli stessi indici per entrambe le serie, così la correlazione resta."""
    x, b = r_x.to_numpy(), r_base.to_numpy()
    T = len(x)
    rng = np.random.default_rng(seed)
    k = math.ceil(T / block)
    deltas = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, T, k)
        idx = ((starts[:, None] + np.arange(block)[None, :]) % T).ravel()[:T]
        deltas[i] = sharpe(x[idx]) - sharpe(b[idx])
    lo, hi = np.percentile(deltas, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return {"delta": sharpe(x) - sharpe(b), "lo": float(lo), "hi": float(hi)}


def deflated_sharpe(r: pd.Series, n_trials: int) -> dict:
    """Deflated Sharpe Ratio (Bailey e López de Prado, 2014), in unità per periodo (giornaliere).
    La varianza degli Sharpe tra i tentativi, non osservata, è approssimata con quella sotto l'ipotesi nulla (1/T)."""
    x = r.dropna().to_numpy()
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    skew = float(pd.Series(x).skew())
    kurt = float(pd.Series(x).kurt()) + 3.0
    nd, gamma = NormalDist(), 0.5772156649
    sr0 = math.sqrt(1 / T) * ((1 - gamma) * nd.inv_cdf(1 - 1 / n_trials) + gamma * nd.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return {"sharpe_annual": sr * math.sqrt(252), "sr0_annual": sr0 * math.sqrt(252), "dsr": nd.cdf(z),
            "n_trials": n_trials, "skew": skew, "kurtosis": kurt}


# ---------------------------------------------------------------- Il test

def run(daily: dict[str, pd.DataFrame], start: str = "2005-01-03", end: str = "2019-12-31") -> dict:
    data = {s: d[d.index <= end] for s, d in daily.items()}
    n_eval = int((data["SPY"].index >= start).sum())
    years = math.ceil(n_eval / 252)
    limits = RiskLimits()
    c = walk_forward(data, limits, years=years)
    sat = walk_forward(data, replace(limits, core_enabled=False), years=years)

    eq_c = pd.Series({pd.Timestamp(d): v for d, v in c["equity"]})
    eq_s = pd.Series({pd.Timestamp(d): v for d, v in sat["equity"]})
    idx = eq_c.index[eq_c.index >= start]
    spy = data["SPY"]["close"]
    r = {
        "A": spy.pct_change().reindex(idx),
        "C": eq_c.pct_change().reindex(idx),
    }
    r["B"] = monthly_mix(r["A"], pd.Series(0.0, index=idx), 0.75)
    r_sat = eq_s.pct_change().reindex(idx)
    r["D"] = monthly_mix(r["A"], r_sat, 0.75)
    r["E"] = faber_filter(spy, idx)
    r = {k: v.fillna(0) for k, v in r.items()}

    names = {"A": "100% SPY", "B": "75% SPY + 25% liquidità", "C": "Core SPY + satellite PULSE",
             "D": "75% SPY + 25% PULSE (conto separato)", "E": "SPY con filtro a 200 giorni"}
    out = {"period": {"from": str(idx[0].date()), "to": str(idx[-1].date()), "days": len(idx)},
           "portfolios": {k: {"name": names[k], **summary(v)} for k, v in r.items()},
           "vs_A": {k: block_bootstrap_delta_sharpe(r[k], r["A"]) for k in "BCDE"},
           "satellite": {**summary(r_sat.fillna(0)), "corr_spy": float(r_sat.corr(r["A"])),
                         "trades": sat["trades"], "dsr": deflated_sharpe(r_sat, n_trials=8)},
           "core_satellite_trades": c["trades"]}

    p, v = out["portfolios"], out["vs_A"]
    keep_satellite = p["C"]["sharpe"] > p["A"]["sharpe"] and v["C"]["lo"] > 0
    adopt_filter = (p["E"]["max_drawdown"] - p["A"]["max_drawdown"] >= 0.10) and v["E"]["lo"] > -0.10
    out["decisions"] = {
        "R1_keep_satellite": keep_satellite,
        "R2_adopt_200d_filter": adopt_filter,
        "R3_dsr_evidence": out["satellite"]["dsr"]["dsr"] >= 0.95,
    }
    return out


def report(o: dict) -> str:
    def pct(x):
        return f"{x * 100:+.1f}%"

    L = [f"# Risultati del test pre-registrato ({o['period']['from']} → {o['period']['to']}, {o['period']['days']} giorni)", "",
         "| | Portafoglio | CAGR | Vol | Sharpe | Max DD | ΔSharpe vs A [IC 90%] |", "|---|---|---|---|---|---|---|"]
    for k, x in o["portfolios"].items():
        d = o["vs_A"].get(k)
        ci = f"{d['delta']:+.2f} [{d['lo']:+.2f}, {d['hi']:+.2f}]" if d else "—"
        L.append(f"| {k} | {x['name']} | {pct(x['cagr'])} | {x['vol'] * 100:.1f}% | {x['sharpe']:.2f} | "
                 f"{pct(x['max_drawdown'])} | {ci} |")
    s = o["satellite"]
    L += ["", f"**Satellite PULSE da solo:** CAGR {pct(s['cagr'])}, Sharpe {s['sharpe']:.2f}, max DD {pct(s['max_drawdown'])},"
          f" correlazione con SPY {s['corr_spy']:.2f}, {s['trades'].get('count', 0)} trade.",
          f"**Deflated Sharpe Ratio** (N = {s['dsr']['n_trials']}): {s['dsr']['dsr']:.2f} "
          f"(Sharpe {s['dsr']['sharpe_annual']:.2f} contro una soglia attesa per caso di {s['dsr']['sr0_annual']:.2f}).",
          "", "## Decisioni (regole pre-registrate)", ""]
    d = o["decisions"]
    L.append(f"1. Satellite nel core + satellite: **{'RESTA ATTIVO' if d['R1_keep_satellite'] else 'PASSA IN MODALITÀ OMBRA'}**")
    L.append(f"2. Filtro a 200 giorni sul core: **{'ADOTTATO' if d['R2_adopt_200d_filter'] else 'NON ADOTTATO'}**")
    L.append(f"3. Evidenza di abilità (DSR ≥ 0,95): **{'SÌ' if d['R3_dsr_evidence'] else 'NO'}**")
    return "\n".join(L) + "\n"
