"""Test pre-registrato del filtro a 200 giorni fuori dal campione USA 2005-2019 (docs/preregistrazione-filtro.md).

Stessa regola del core: a fine mese, indice sopra la media a 200 giorni -> investito il mese dopo, altrimenti
liquidità (rendimento 0), 6 bp per ogni cambio. Si aggiungono le tasse italiane e il numero di operazioni.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .research import FROZEN_FILES, block_bootstrap_delta_sharpe, fingerprint, summary

PREREG = "docs/preregistrazione-filtro.md"
TAX = 0.26
COST_BPS = 6.0
MARKETS = {   # simbolo Yahoo: (inizio, fine, nota)
    "^GSPC": ("1950-01-01", "2004-12-31", "S&P 500 prima del 2005 (periodo mai usato), solo prezzo"),
    "^GDAXI": ("1988-01-01", "2026-10-31", "DAX, indice total return"),
    "^FTSE": ("1984-01-01", "2026-10-31", "FTSE 100, solo prezzo"),
    "^N225": ("1965-01-01", "2026-10-31", "Nikkei 225, solo prezzo"),
    "EFA": ("2001-08-01", "2026-10-31", "ETF sviluppati non USA, dividendi reinvestiti"),
    "URTH": ("2012-01-12", "2026-10-31", "ETF MSCI World, dividendi reinvestiti"),
}
WARMUP = 210


def test_fingerprint() -> str:
    return fingerprint(FROZEN_FILES + ["desk/filter_intl.py", "desk/research.py"])


def weights(close: pd.Series) -> pd.Series:
    """1 = investito, 0 = liquidità. Segnale dell'ultimo giorno del mese PRECEDENTE (come research.faber_filter)."""
    sma = close.rolling(200).mean()
    month_end = close.groupby(close.index.to_period("M")).tail(1)
    signal = (month_end > sma.reindex(month_end.index)).astype(float)
    signal.index = signal.index.to_period("M")
    w = pd.Series([signal.get(d.to_period("M") - 1, np.nan) for d in close.index], index=close.index)
    return w.ffill().fillna(1.0)


def filter_returns(close: pd.Series, cost_bps: float = COST_BPS) -> tuple[pd.Series, pd.Series]:
    w = weights(close)
    r = close.pct_change().fillna(0)
    switches = w.diff().abs().fillna(0)
    return w * r - switches * cost_bps / 10_000, w


def after_tax(r: pd.Series, w: pd.Series | None, tax: float = TAX) -> dict:
    """Regime italiano degli ETF, semplificato e prudente:
    - ogni uscita in guadagno paga il 26% sul guadagno di quel periodo investito;
    - le perdite NON compensano i guadagni (per gli ETF sono redditi di natura diversa);
    - a fine periodo si liquida tutto e si paga il 26% sul guadagno ancora aperto.
    Buy & hold (w = None): una sola tassa sul guadagno finale."""
    v, basis, inv = 1.0, 1.0, True
    ws = w.to_numpy() if w is not None else np.ones(len(r))
    rs = r.to_numpy()
    for i in range(len(rs)):
        now = ws[i] > 0.5
        if inv and not now:                        # uscita: tassa sull'eventuale guadagno del periodo investito
            v -= max(v - basis, 0.0) * tax
        if now and not inv:
            basis = v
        inv = now
        v *= 1 + rs[i]
    if inv:
        v -= max(v - basis, 0.0) * tax
    years = len(rs) / 252
    return {"final": v, "cagr": v ** (1 / years) - 1 if years > 0 and v > 0 else float("nan")}


def one_market(close: pd.Series, start: str, end: str) -> dict:
    close = close[(close.index <= end)].dropna()
    r_bh_all = close.pct_change().fillna(0)
    r_f_all, w_all = filter_returns(close)
    first = max(close.index.searchsorted(pd.Timestamp(start)), WARMUP)
    idx = close.index[first:]
    r_bh, r_f, w = r_bh_all.reindex(idx), r_f_all.reindex(idx), w_all.reindex(idx)
    years = len(idx) / 252
    switches = float(w.diff().abs().fillna(0).sum())
    s_bh, s_f = summary(r_bh), summary(r_f)
    d = block_bootstrap_delta_sharpe(r_f, r_bh)
    return {
        "period": {"from": str(idx[0].date()), "to": str(idx[-1].date()), "years": round(years, 1)},
        "buy_hold": s_bh, "filter": s_f, "delta_sharpe": d,
        "invested_share": float(w.mean()), "switches_per_year": switches / years,
        "exits_per_year": float((w.diff() < 0).sum()) / years,
        "after_tax": {"buy_hold": after_tax(r_bh, None), "filter": after_tax(r_f, w)},
        "holds": bool((s_f["max_drawdown"] - s_bh["max_drawdown"] >= 0.10) and d["lo"] > -0.10),
    }


def run(prices: dict[str, pd.Series]) -> dict:
    out = {"markets": {}}
    for sym, (start, end, note) in MARKETS.items():
        if sym in prices:
            out["markets"][sym] = {"note": note, **one_market(prices[sym], start, end)}
    held = sum(m["holds"] for m in out["markets"].values())
    out["decisions"] = {"F1_markets_held": held, "F1_markets_total": len(out["markets"]),
                        "F2_credible": held >= 4}
    return out


def report(o: dict) -> str:
    def pct(x):
        return f"{x * 100:+.1f}%"

    L = ["# Risultati: filtro a 200 giorni fuori dal campione USA 2005-2019", "",
         "| Mercato | Periodo | CAGR B&H → filtro | Sharpe B&H → filtro | ΔSharpe [IC 90%] | Max DD B&H → filtro | "
         "Investito | Uscite/anno | CAGR netto tasse B&H → filtro | Regge |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for sym, m in o["markets"].items():
        b, f, d, t = m["buy_hold"], m["filter"], m["delta_sharpe"], m["after_tax"]
        L.append(f"| {sym} | {m['period']['from'][:4]}-{m['period']['to'][:4]} | {pct(b['cagr'])} → {pct(f['cagr'])} | "
                 f"{b['sharpe']:.2f} → {f['sharpe']:.2f} | {d['delta']:+.2f} [{d['lo']:+.2f}, {d['hi']:+.2f}] | "
                 f"{pct(b['max_drawdown'])} → {pct(f['max_drawdown'])} | {m['invested_share']:.0%} | "
                 f"{m['exits_per_year']:.1f} | {pct(t['buy_hold']['cagr'])} → {pct(t['filter']['cagr'])} | "
                 f"{'SÌ' if m['holds'] else 'NO'} |")
    d = o["decisions"]
    L += ["", "## Decisioni (regole pre-registrate)", "",
          f"F1. Il filtro regge in **{d['F1_markets_held']} mercati su {d['F1_markets_total']}**.",
          f"F2. Filtro credibile fuori dal campione USA (almeno 4 su 6): **{'SÌ' if d['F2_credible'] else 'NO'}**"]
    return "\n".join(L) + "\n"
