"""Dati storici di PULSE-CT: Coinbase Exchange, candele giornaliere UTC (sezione 5 della pre-registrazione).

- I file grezzi sono le risposte HTTP così come arrivano, una per riga, con l'impronta SHA-256 nel manifest.
- Il caricatore verifica le impronte e rifiuta qualsiasi data oltre il limite dello stato (trials.stage()).
  Non ha opzioni per disattivare il blocco.
- Il flusso dal vivo è un altro modulo (live.py) e non scrive mai qui.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import timedelta

import pandas as pd

from . import config, trials

CANDLES = "https://api.exchange.coinbase.com/products/{p}/candles?granularity=86400&start={s}&end={e}"
RAW = config.DATA / "raw"
MANIFEST = RAW / "manifest.json"
PAGE_DAYS = 290                       # l'API restituisce al massimo 300 candele per richiesta


def http_get(url: str) -> bytes:
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pulse-research/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError):
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download non riuscito: {url}")


def _check_limit(end: pd.Timestamp, st: str) -> None:
    limit = trials.data_limit(st)
    if end > limit:
        raise PermissionError(f"Date oltre {limit.date()} bloccate nello stato '{st}' della pre-registrazione")


def download(product: str, start: str, end: str, get=http_get, st: str | None = None) -> list[bytes]:
    """Scarica le pagine grezze fra start e end (inclusi). Il limite dipende dallo stato, non da un parametro."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    _check_limit(e, st or trials.stage())
    pages, cur = [], s
    while cur <= e:
        stop = min(cur + timedelta(days=PAGE_DAYS - 1), e)
        url = CANDLES.format(p=product, s=cur.strftime("%Y-%m-%dT00:00:00Z"), e=stop.strftime("%Y-%m-%dT00:00:00Z"))
        pages.append(get(url))
        cur = stop + timedelta(days=1)
        time.sleep(0.35)
    return pages


def save(product: str, start: str, end: str, pages: list[bytes]) -> str:
    RAW.mkdir(parents=True, exist_ok=True)
    name = f"{product}_{start}_{end}.jsonl"
    blob = b"\n".join(pages) + b"\n"
    (RAW / name).write_bytes(blob)
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    man[name] = hashlib.sha256(blob).hexdigest()
    MANIFEST.write_text(json.dumps(man, indent=2, sort_keys=True) + "\n")
    return man[name]


def parse(blob: bytes) -> pd.DataFrame:
    rows = []
    for line in blob.splitlines():
        if line.strip():
            rows.extend(json.loads(line))
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["t", "low", "high", "open", "close", "volume"])
    df.index = pd.to_datetime(df.pop("t"), unit="s").dt.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def load(st: str | None = None) -> dict[str, pd.DataFrame]:
    """Legge i file grezzi verificando le impronte e il limite di date dello stato attuale."""
    st = st or trials.stage()
    man = json.loads(MANIFEST.read_text())
    out: dict[str, list[pd.DataFrame]] = {a: [] for a in config.ASSETS}
    for name, digest in sorted(man.items()):
        blob = (RAW / name).read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise PermissionError(f"Impronta di {name} diversa dal manifest: file modificato")
        product = name.split("_")[0]
        if product in out:
            out[product].append(parse(blob))
    data = {}
    for a, parts in out.items():
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if len(df):
            _check_limit(df.index.max(), st)
        data[a] = df
    return data


def manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def quality(df: pd.DataFrame) -> list[str]:
    """Regola v2 di PULSE sulle barre impossibili. Una sola barra impossibile ferma il test."""
    o, h, lo, c = (df[k] for k in ("open", "high", "low", "close"))
    gap = c / c.shift()
    bad = (o > h * 1.01) | (o < lo * 0.99) | (c > h * 1.01) | (c < lo * 0.99) | (h < lo) | (gap > 3) | (gap < 1 / 3)
    return [d.strftime("%Y-%m-%d") for d in df.index[bad.fillna(False)]]


def coverage(df: pd.DataFrame, start, end) -> dict:
    """Quota dei giorni di calendario presenti e la serie più lunga di giorni mancanti."""
    days = pd.date_range(start, end, freq="D")
    have = days.isin(df.index)
    run = best = 0
    for h in have:
        run = 0 if h else run + 1
        best = max(best, run)
    return {"first": df.index.min().strftime("%Y-%m-%d") if len(df) else None, "days": len(days),
            "present": int(have.sum()), "share": float(have.mean()) if len(days) else 0.0, "max_missing_run": best,
            "ok": bool(have.mean() >= config.COVERAGE_MIN and best <= config.MISSING_RUN_MAX)}
