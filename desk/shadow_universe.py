"""Universo del satellite in ombra definito da una regola, non scelto a mano (consiglio di Grok, 11/2026).

Regola: i 100 membri ATTUALI dell'S&P 500 con il volume in dollari medio più alto negli ultimi 60 giorni,
ricalcolati il primo giro di ogni mese. QQQ e IWM restano sempre (la mean reversion lavora su questi). SPY è il core.

È questa ombra che conta per la regola di riattivazione. Il confronto con i 15 titoli fissi si ricostruisce
a posteriori con il backtester sugli stessi mesi: la strategia è deterministica, non serve un secondo conto virtuale.

Il modulo non tocca i file congelati: cambia QUALI titoli il satellite guarda, non COME decide.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd

RULE = "top100_dollar_volume_60d_monthly"
N_TOP = 100
LOOKBACK = 60
ALWAYS = ["QQQ", "IWM"]


def enabled() -> bool:
    return os.getenv("SHADOW_UNIVERSE", "top100").lower() == "top100"


def members_path() -> str:
    return os.getenv("SHADOW_MEMBERS_CSV", "data/sp500/components.csv")


def current_members(path: str | None = None, today: datetime | None = None) -> list[str]:
    """Composizione S&P 500 in vigore oggi (ultima riga con data <= oggi). Ticker in formato Alpaca (BRK.B)."""
    comp = pd.read_csv(path or members_path(), parse_dates=["date"]).sort_values("date")
    if today is not None:
        comp = comp[comp["date"] <= pd.Timestamp(today.date() if hasattr(today, "date") else today)]
    if comp.empty:
        return []
    return sorted(comp["tickers"].iloc[-1].split(","))


def top_by_dollar_volume(daily: dict[str, pd.DataFrame], n: int | None = None, days: int = LOOKBACK) -> list[str]:
    n = N_TOP if n is None else n
    dv = {}
    for s, df in daily.items():
        d = df.dropna(subset=["close", "volume"]).tail(days)
        if len(d) >= days * 0.8:                        # serve quasi tutta la finestra: niente titoli appena quotati
            dv[s] = float((d["close"] * d["volume"]).mean())
    return [s for s, _ in sorted(dv.items(), key=lambda x: (-x[1], x[0]))[:n]]


def refresh(journal, data, now: datetime, core_symbol: str = "SPY") -> list[str] | None:
    """Ricalcola la lista se è cambiato il mese. Restituisce la lista nuova, oppure None se non è cambiato nulla."""
    st = journal.get("shadow_universe") or {}
    month = now.strftime("%Y-%m")
    if st.get("month") == month and st.get("symbols"):
        return None
    try:
        members = current_members(today=now)
    except FileNotFoundError:
        journal.event("shadow_universe", f"composizione S&P 500 non trovata ({members_path()}): tengo la lista precedente")
        return None
    bars = data.daily_bars(members, days=LOOKBACK + 10)
    top = [s for s in top_by_dollar_volume(bars) if s != core_symbol]
    if len(top) < N_TOP // 2:                          # dati insufficienti: meglio la lista vecchia che una monca
        journal.event("shadow_universe", f"solo {len(top)} titoli con dati: tengo la lista precedente")
        return None
    journal.set("shadow_universe", {"month": month, "asof": now.isoformat(), "rule": RULE,
                                    "members": len(members), "symbols": top})
    history = journal.get("shadow_universe_history") or {}
    history[month] = top                               # il report in avanti rigira il backtest con queste liste
    journal.set("shadow_universe_history", history)
    journal.event("shadow_universe", f"universo dell'ombra {month}: {len(top)} titoli per volume in dollari "
                                     f"a {LOOKBACK} giorni (primi: {', '.join(top[:5])})")
    return top
