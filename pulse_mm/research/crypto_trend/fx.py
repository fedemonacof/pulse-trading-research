"""Cambio EUR/USD di riferimento BCE per la robustezza in EUR (sezioni 2 e 5 della pre-registrazione).

- Fonte: BCE, serie EXR.D.USD.EUR.SP00.A (dollari per un euro, fissato alle 14:15 CET nei giorni lavorativi).
- Il file grezzo è la risposta CSV così come arriva, con l'impronta SHA-256 in un manifest separato da quello
  delle candele.
- Stesso blocco delle date delle candele: il limite dipende dallo stato della pre-registrazione, non da un
  parametro.
- La conversione usa per ogni giorno l'ultimo cambio pubblicato fino a quel giorno incluso: il cambio delle
  14:15 CET è noto prima della chiusura delle 24:00 UTC. Fine settimana e festivi usano l'ultimo giorno lavorativo.
"""
from __future__ import annotations

import hashlib
import io
import json

import pandas as pd

from . import config, data, trials

ECB = ("https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
       "?startPeriod={s}&endPeriod={e}&format=csvdata")
FX = config.DATA / "fx"
MANIFEST = FX / "manifest.json"
MAX_GAP_DAYS = 5                      # giorni di calendario senza cambio oltre cui la serie non è valida


def download(start: str, end: str, get=data.http_get, st: str | None = None) -> bytes:
    data._check_limit(pd.Timestamp(end), st or trials.stage())
    return get(ECB.format(s=start, e=end))


def save(start: str, end: str, blob: bytes) -> str:
    FX.mkdir(parents=True, exist_ok=True)
    name = f"EURUSD-ECB_{start}_{end}.csv"
    (FX / name).write_bytes(blob)
    man = manifest()
    man[name] = hashlib.sha256(blob).hexdigest()
    MANIFEST.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    return man[name]


def manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def parse(blob: bytes) -> pd.Series:
    df = pd.read_csv(io.BytesIO(blob), usecols=["TIME_PERIOD", "OBS_VALUE"])
    s = pd.Series(df["OBS_VALUE"].astype(float).to_numpy(), index=pd.to_datetime(df["TIME_PERIOD"]),
                  name="usd_per_eur")
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def load(st: str | None = None) -> pd.Series:
    """Legge i file grezzi verificando impronte e limite di date dello stato attuale."""
    st = st or trials.stage()
    parts = []
    for name, digest in sorted(manifest().items()):
        blob = (FX / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise PermissionError(f"Impronta di {name} diversa dal manifest: file modificato")
        parts.append(parse(blob))
    if not parts:
        raise FileNotFoundError("Cambi BCE non scaricati (python -m pulse_mm.research.crypto_trend fetch)")
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    data._check_limit(s.index.max(), st)
    return s


def gaps(rate: pd.Series, start, end) -> dict:
    """Controllo della serie: giorni di calendario fra due cambi pubblicati. Non stampa rendimenti."""
    r = rate[(rate.index >= pd.Timestamp(start) - pd.Timedelta(days=MAX_GAP_DAYS)) & (rate.index <= end)]
    steps = r.index.to_series().diff().dt.days.dropna()
    longest = int(steps.max()) if len(steps) else None
    return {"rates": len(r), "first": r.index.min(), "last": r.index.max(), "longest_gap_days": longest,
            "ok": bool(len(r) and r.index.min() <= pd.Timestamp(start) and longest is not None
                       and longest <= MAX_GAP_DAYS)}


def to_eur(equity_usd: pd.Series, usd_per_eur: pd.Series) -> pd.Series:
    """Equity in EUR = equity in USD / (USD per EUR), con l'ultimo cambio pubblicato fino a quel giorno."""
    rate = usd_per_eur.reindex(usd_per_eur.index.union(equity_usd.index)).ffill().reindex(equity_usd.index)
    if rate.isna().any():
        raise ValueError(f"Manca il cambio BCE prima del {rate[rate.isna()].index.max().date()}")
    return equity_usd / rate


def returns_eur(res, usd_per_eur: pd.Series, start, end) -> pd.Series:
    eq = to_eur(res.equity, usd_per_eur)
    r = eq.pct_change()
    return r[(r.index >= start) & (r.index <= end)].fillna(0.0)
