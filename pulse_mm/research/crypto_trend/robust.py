"""Revisione 4 della pre-registrazione (dopo la rilettura di Grok, prima della firma, senza risultati visti).

- Controllo della leva: fallisce se il peso di una quota supera 1 + 1% in qualunque giorno del periodo.
- Robustezze del drawdown, senza soglie: media dei drawdown massimi su finestre consecutive di 63 giorni, drawdown
  medio, durata media sotto il massimo precedente.
- Robustezza della liquidità: rendimento dei T-bill USA a 3 mesi (FRED, serie DTB3) al posto dello 0%.

Le costanti stanno qui e non in config.py: config.py fa parte dell'impronta del piano del dry-run (criterio 7), che
è già partito e si invaliderebbe a ogni modifica.
"""
from __future__ import annotations

import hashlib
import io
import json
import math

import numpy as np
import pandas as pd

from . import config, data, stats, trials

LEV_TOL = 0.01                          # peso massimo ammesso: 1,01
DD_WINDOW = 63                          # giorni per finestra, finestre consecutive senza sovrapposizione
TBILL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3&cosd={s}&coed={e}"
TB_DIR = config.DATA / "tbill"
TB_MANIFEST = TB_DIR / "manifest.json"
TB_DAYCOUNT = 360                       # DTB3 è un tasso di sconto annuo su base 360


# ------------------------------------------------------------ leva

def leverage_check(res, start, end, tol: float = LEV_TOL) -> dict:
    """Peso massimo di ogni quota nel periodo. Se supera 1 + tol, il calcolo non si riporta."""
    w = res.weights[(res.weights.index >= start) & (res.weights.index <= end)]
    mx = float(w.max().max()) if len(w) else 0.0
    day = w.max(axis=1).idxmax() if len(w) else None
    return {"max_weight": mx, "on": day, "limit": config.MAX_LEV + tol, "ok": mx <= config.MAX_LEV + tol + 1e-12}


# ------------------------------------------------------------ drawdown

def _path(r) -> np.ndarray:
    return np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(r, dtype=float))])


def dd_windows(r, window: int = DD_WINDOW) -> float:
    """Media dei drawdown massimi di finestre consecutive di `window` giorni. L'ultima finestra incompleta si
    scarta. Ogni finestra parte dal suo primo giorno."""
    x = np.asarray(r, dtype=float)
    k = len(x) // window
    if k == 0:
        return float("nan")
    return float(np.mean([stats.max_dd(x[i * window:(i + 1) * window]) for i in range(k)]))


def mean_dd(r) -> float:
    """Drawdown medio: media giornaliera della distanza dal massimo precedente, come numero positivo."""
    p = _path(r)[1:]
    peak = np.maximum.accumulate(np.concatenate([[1.0], p]))[1:]
    return float(np.mean(1.0 - p / peak)) if len(p) else float("nan")


def mean_underwater_days(r) -> float:
    """Durata media, in giorni, dei periodi sotto il massimo precedente. Un periodo non recuperato alla fine
    conta fino all'ultimo giorno."""
    p = _path(r)[1:]
    peak = np.maximum.accumulate(np.concatenate([[1.0], p]))[1:]
    under = p < peak * (1 - 1e-12)
    runs, n = [], 0
    for u in under:
        if u:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    return float(np.mean(runs)) if runs else 0.0


def dd_profile(r: pd.Series) -> dict:
    x = r.to_numpy()
    return {"dd_windows_63": dd_windows(x), "mean_dd": mean_dd(x), "mean_underwater_days": mean_underwater_days(x)}


def paired_bootstrap_metric(r_s: pd.Series, r_b: pd.Series, fn, block: int = config.BOOT_BLOCK,
                            n: int = config.BOOT_N, seed: int = config.SEED, level: float = config.LEVEL) -> dict:
    """IC della differenza fn(strategia) − fn(benchmark) con lo stesso bootstrap a blocchi della sezione 7."""
    s, b = r_s.to_numpy(), r_b.to_numpy()
    T = len(s)
    rng = np.random.default_rng(seed)
    k = math.ceil(T / block)
    d = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, T, k)
        idx = ((starts[:, None] + np.arange(block)[None, :]) % T).ravel()[:T]
        d[i] = fn(s[idx]) - fn(b[idx])
    lo, hi = np.percentile(d, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return {"point": fn(s) - fn(b), "lo": float(lo), "hi": float(hi), "block": block, "n": n, "seed": seed}


# ------------------------------------------------------------ T-bill a 3 mesi (FRED DTB3)

def fred_get(url: str) -> bytes:
    """FRED risponde solo allo user agent standard di Python (con quello di PULSE la richiesta resta appesa)."""
    import time
    import urllib.error
    import urllib.request
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download non riuscito: {url}")


def tbill_download(start: str, end: str, get=fred_get, st: str | None = None) -> bytes:
    data._check_limit(pd.Timestamp(end), st or trials.stage())
    return get(TBILL.format(s=start, e=end))


def tbill_save(start: str, end: str, blob: bytes) -> str:
    TB_DIR.mkdir(parents=True, exist_ok=True)
    name = f"DTB3-FRED_{start}_{end}.csv"
    (TB_DIR / name).write_bytes(blob)
    man = tbill_manifest()
    man[name] = hashlib.sha256(blob).hexdigest()
    TB_MANIFEST.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    return man[name]


def tbill_manifest() -> dict:
    return json.loads(TB_MANIFEST.read_text()) if TB_MANIFEST.exists() else {}


def tbill_parse(blob: bytes) -> pd.Series:
    df = pd.read_csv(io.BytesIO(blob))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")       # i festivi arrivano come "." o vuoti
    s.index = pd.to_datetime(df.iloc[:, 0])
    s = s.dropna()
    return s[~s.index.duplicated(keep="last")].sort_index().rename("dtb3_pct")


def tbill_load(st: str | None = None) -> pd.Series:
    st = st or trials.stage()
    parts = []
    for name, digest in sorted(tbill_manifest().items()):
        blob = (TB_DIR / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise PermissionError(f"Impronta di {name} diversa dal manifest: file modificato")
        parts.append(tbill_parse(blob))
    if not parts:
        raise FileNotFoundError("T-bill non scaricati (python -m pulse_mm.research.crypto_trend fetch)")
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    data._check_limit(s.index.max(), st)
    return s


def daily_cash_rate(dtb3_pct: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """Tasso semplice per giorno di calendario. Il giorno d usa l'ultimo valore pubblicato prima di d (niente
    lookahead): DTB3 / 100 / 360."""
    shifted = dtb3_pct.copy()
    shifted.index = shifted.index + pd.Timedelta(days=1)       # il valore del giorno d vale dal giorno d+1
    r = shifted.reindex(shifted.index.union(days)).ffill().reindex(days)
    if r.isna().any():
        raise ValueError(f"Manca il tasso T-bill prima del {r[r.isna()].index.max().date()}")
    return r / 100.0 / TB_DAYCOUNT


def tbill_gaps(dtb3_pct: pd.Series, start, end, max_gap: int = 5) -> dict:
    t = dtb3_pct[(dtb3_pct.index >= pd.Timestamp(start) - pd.Timedelta(days=max_gap)) & (dtb3_pct.index <= end)]
    steps = t.index.to_series().diff().dt.days.dropna()
    longest = int(steps.max()) if len(steps) else None
    return {"rates": len(t), "first": t.index.min(), "last": t.index.max(), "longest_gap_days": longest,
            "ok": bool(len(t) and t.index.min() <= pd.Timestamp(start) and longest is not None
                       and longest <= max_gap)}


# ------------------------------------------------------------ benchmark a esposizione uguale (revisione 5)

def exposure_ratio(res_s, res_b, start, end) -> dict:
    """k = esposizione media della strategia / esposizione media del benchmark, sullo stesso periodo valutato."""
    from . import strategy
    e_s, e_b = strategy.avg_exposure(res_s, start, end), strategy.avg_exposure(res_b, start, end)
    return {"exposure_strategy": e_s, "exposure_benchmark": e_b, "k": e_s / e_b if e_b > 0 else float("nan")}


def scaled_benchmark(r_b: pd.Series, k: float) -> pd.Series:
    """Benchmark con una quota fissa k, ribilanciata ogni giorno, e il resto in liquidità allo 0%."""
    return r_b * k
