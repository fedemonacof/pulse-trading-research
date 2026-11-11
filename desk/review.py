"""Revisione notturna: misura come sono andate le decisioni e corregge i pesi, entro limiti fissi.

Calcola per strategia: % vincenti, profit factor, drawdown massimo, Sharpe e calibrazione della
confidenza. Scrive un report markdown in reports/. Può spostare SOLO i pesi delle strategie e del
comitato, di poco e dentro WEIGHT_BOUNDS. I limiti di rischio non vengono mai toccati.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .config import Settings
from .journal import Journal
from .reflex import WEIGHT_BOUNDS, clamp_weights

STEP = 0.1          # di quanto può muoversi un peso in una notte
MIN_TRADES = 10     # sotto questo numero di trade nella finestra non si tocca nulla
WINDOW_DAYS = 30


def _pf(pnl: np.ndarray) -> float | None:
    losses = -pnl[pnl < 0].sum()
    return float(pnl[pnl > 0].sum() / losses) if losses > 0 else None


def strategy_stats(trades: pd.DataFrame, equity0: float) -> dict:
    if trades.empty:
        return {"trades": 0}
    pnl = trades["pnl"].to_numpy()
    cum = np.cumsum(pnl) + equity0
    peak = np.maximum.accumulate(np.r_[equity0, cum])[1:]
    daily = trades.groupby(trades["ts"].str[:10])["pnl"].sum() / equity0
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else None
    return {
        "trades": int(len(pnl)), "win_rate": float((pnl > 0).mean()), "profit_factor": _pf(pnl),
        "pnl": float(pnl.sum()), "max_drawdown": float((cum / peak - 1).min()), "sharpe": sharpe,
        "avg_holding_min": float(trades["holding_minutes"].dropna().mean()) if trades["holding_minutes"].notna().any() else None,
    }


def calibration(trades: pd.DataFrame) -> list[dict]:
    out = []
    for lo, hi in ((55, 65), (65, 75), (75, 85), (85, 101)):
        b = trades[(trades["confidence"] >= lo) & (trades["confidence"] < hi)] if "confidence" in trades else trades.iloc[:0]
        out.append({"bucket": f"{lo}-{min(hi, 100)}", "trades": int(len(b)),
                    "win_rate": float((b["pnl"] > 0).mean()) if len(b) else None})
    return out


def adjust_weights(current: dict, per_strategy: dict) -> tuple[dict, list[str]]:
    w, notes = clamp_weights(current), []
    for key in WEIGHT_BOUNDS:
        st = per_strategy.get(key, {})
        if st.get("trades", 0) < MIN_TRADES or st.get("profit_factor") is None:
            continue
        pf = st["profit_factor"]
        delta = STEP if pf > 1.2 else -STEP if pf < 0.8 else 0.0
        if key == "committee":
            delta /= 2
        if delta:
            new = clamp_weights({**w, key: w[key] + delta})[key]
            if new != w[key]:
                notes.append(f"{key}: {w[key]:.2f} → {new:.2f} (profit factor {pf:.2f} su {st['trades']} trade)")
                w[key] = new
    return w, notes


def nightly_review(j: Journal, settings: Settings, now: datetime | None = None, write: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    trades = pd.DataFrame(j.rows("SELECT * FROM closed_trades ORDER BY ts"))
    eq = pd.DataFrame(j.rows("SELECT ts, equity FROM equity WHERE mode != 'SHADOW' ORDER BY ts"))
    equity0 = float(eq["equity"].iloc[0]) if len(eq) else 100_000.0
    since = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    recent = trades[trades["ts"] >= since] if len(trades) else trades

    per_strategy = {}
    if len(recent):
        for name, g in recent.groupby(recent["strategy"].fillna("altro")):
            per_strategy[name] = strategy_stats(g, equity0)
    overall = strategy_stats(recent, equity0) if len(recent) else {"trades": 0}
    account = {}
    if len(eq) > 2:
        e = eq.set_index(pd.to_datetime(eq["ts"]))["equity"].resample("1D").last().dropna()
        r = e.pct_change().dropna()
        account = {"equity": float(e.iloc[-1]), "max_drawdown": float((e / e.cummax() - 1).min()),
                   "sharpe": float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 2 and r.std() > 0 else None}

    old = clamp_weights(j.get("weights"))
    new, notes = adjust_weights(old, per_strategy)
    report = {
        "date": now.date().isoformat(), "window_days": WINDOW_DAYS, "overall": overall, "account": account,
        "per_strategy": per_strategy, "calibration": calibration(recent) if len(recent) else [],
        "weights_before": old, "weights_after": new, "changes": notes,
        "risk_limits_untouched": True,
    }
    if write:
        j.set("weights", new)
        hist = j.get("weights_history", [])
        hist.append({"date": report["date"], **new})
        j.set("weights_history", hist[-90:])
        j.event("nightly_review", report)
        os.makedirs(settings.reports_dir, exist_ok=True)
        path = os.path.join(settings.reports_dir, f"revisione-{report['date']}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(to_markdown(report))
        report["path"] = path
    return report


def to_markdown(r: dict) -> str:
    def pct(x):
        return "—" if x is None else f"{x:.1%}"

    def num(x, d=2):
        return "—" if x is None else f"{x:.{d}f}"

    o = r["overall"]
    lines = [f"# Revisione notturna PULSE — {r['date']}", "",
             f"Finestra: ultimi {r['window_days']} giorni. Trade chiusi: {o.get('trades', 0)}.", ""]
    if r["account"]:
        a = r["account"]
        lines += [f"Equity {a['equity']:,.0f} $ · drawdown massimo {pct(a['max_drawdown'])} · Sharpe {num(a['sharpe'])}", ""]
    lines += ["## Per strategia", "", "| Strategia | Trade | Vincenti | Profit factor | Max DD | Sharpe |",
              "|---|---|---|---|---|---|"]
    for k, s in r["per_strategy"].items():
        lines.append(f"| {k} | {s['trades']} | {pct(s.get('win_rate'))} | {num(s.get('profit_factor'))} | "
                     f"{pct(s.get('max_drawdown'))} | {num(s.get('sharpe'))} |")
    if not r["per_strategy"]:
        lines.append("| — | 0 | — | — | — | — |")
    lines += ["", "## Calibrazione", "", "Una confidenza più alta dovrebbe vincere più spesso.", "",
              "| Confidenza | Trade | Vincenti |", "|---|---|---|"]
    lines += [f"| {c['bucket']} | {c['trades']} | {pct(c['win_rate'])} |" for c in r["calibration"]]
    lines += ["", "## Pesi", ""]
    lines += [f"- {n}" for n in r["changes"]] or [f"- Nessuna modifica (servono almeno {MIN_TRADES} trade per strategia)."]
    lines += ["", f"Pesi in vigore: {', '.join(f'{k} {v:.2f}' for k, v in r['weights_after'].items())}.",
              "I limiti di rischio non sono stati modificati: la revisione non può toccarli.", ""]
    return "\n".join(lines)
