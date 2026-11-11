"""Flusso dal vivo di PULSE-CT, separato dai dati storici (sezione 3 della pre-registrazione).

Accetta solo date dal 2026-11-01 in poi, cioè dopo la fine del test, e salva in una cartella sua. Serve al dry-run
di riconciliazione con il calendario fisso di ordini di prova, che non usa il segnale.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import config

LIVE_DIR = config.DATA / "live"


def check_dates(index) -> None:
    idx = pd.DatetimeIndex(index)
    if len(idx) and idx.min() < config.LIVE_START:
        raise PermissionError(f"Il flusso dal vivo accetta solo date dal {config.LIVE_START.date()} in poi: "
                              f"ricevuto {idx.min().date()}")


class LiveFeed:
    """Prezzi dal vivo. `fetch(symbol)` restituisce (istante UTC, prezzo); è iniettabile per i test."""

    def __init__(self, fetch):
        self.fetch = fetch

    def price(self, symbol: str) -> tuple[datetime, float]:
        ts, px = self.fetch(symbol)
        ts = pd.Timestamp(ts).tz_convert(timezone.utc) if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts, tz="UTC")
        check_dates([ts.tz_localize(None)])
        return ts.to_pydatetime(), float(px)

    def bars(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Barre ricevute dal vivo: rifiutate se contengono date prima del 2026-11-01."""
        check_dates(frame.index)
        return frame
