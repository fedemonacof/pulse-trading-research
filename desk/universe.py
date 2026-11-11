"""Universo storico dell'S&P 500 (point-in-time) per il test pre-registrato docs/preregistrazione-universo.md.

Il modulo NON fa parte del codice congelato. Usa il Backtester così com'è e cambia solo QUALI titoli possono entrare:
- un titolo può aprire una posizione solo nei giorni in cui era davvero nell'indice (composizione storica);
- dopo l'uscita dall'indice le posizioni aperte escono con le regole normali (punteggi "per restare");
- quando un titolo smette di quotare (delisting, fusione) la posizione viene chiusa all'ultima apertura disponibile.

Fonte della composizione: github.com/fja05680/sp500 (CSV con i componenti a ogni data di cambiamento).
"""
from __future__ import annotations

import math
import pickle
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd

from .backtest import Backtester, walk_forward
from .config import RiskLimits
from .reflex import ENTER
from . import backtest as bt_module
from .research import FROZEN_FILES, deflated_sharpe, fingerprint, summary

PREREG = "docs/preregistrazione-universo-v2.md"
ETFS = ["SPY", "QQQ", "IWM"]           # sempre nell'universo: la mean reversion lavora su questi
FIXED_15 = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "JPM", "V", "UNH",
            "XOM", "COST"]
FORCE_EXIT = -100.0


def test_fingerprint() -> str:
    """Impronta di questo test: codice congelato + il codice dell'universo e delle statistiche."""
    return fingerprint(FROZEN_FILES + ["desk/universe.py", "desk/research.py"])


def yahoo_symbol(t: str) -> str:
    return t.replace(".", "-")


def membership(components_csv: str, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Tabella giorni × ticker: True se quel giorno il titolo era nell'S&P 500."""
    comp = pd.read_csv(components_csv, parse_dates=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    snap = comp.set_index("date")["tickers"]
    snap = snap.reindex(snap.index.union(days)).ffill().reindex(days).dropna()   # composizione in vigore quel giorno
    sets = {d: {yahoo_symbol(s) for s in t.split(",")} for d, t in snap.items()}
    tickers = sorted(set().union(*sets.values())) if sets else []
    col = {s: j for j, s in enumerate(tickers)}
    m = np.zeros((len(days), len(tickers)), dtype=bool)
    row = {d: i for i, d in enumerate(days)}
    for d, ss in sets.items():
        m[row[d], [col[s] for s in ss]] = True
    return pd.DataFrame(m, index=days, columns=tickers)


def clean(daily: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Esclude le serie con barre impossibili (dati sbagliati o ticker riusati), regola fissata nella v2:
    apertura o chiusura fuori da [minimo, massimo] di oltre l'1%, massimo < minimo, o apertura > 3× / < 1/3
    della chiusura precedente."""
    keep, dropped = {}, []
    for s, df in daily.items():
        o, h, lo, c = (df[k] for k in ("open", "high", "low", "close"))
        gap = o / c.shift()
        bad = (o > h * 1.01) | (o < lo * 0.99) | (c > h * 1.01) | (c < lo * 0.99) | (h < lo) | (gap > 3) | (gap < 1 / 3)
        if bad.any() and s not in ETFS:
            dropped.append(s)
        else:
            keep[s] = df
    return keep, sorted(dropped)


def coverage(member: pd.DataFrame, daily: dict[str, pd.DataFrame]) -> dict:
    """Quota dei giorni-membro per cui esiste un prezzo."""
    tot = int(member.to_numpy().sum())
    have = 0
    for s in member.columns:
        if s in daily:
            have += int(member[s][member[s]].index.isin(daily[s].index).sum())
    return {"member_days": tot, "covered": have, "share": have / tot if tot else 0.0}


class PITBacktester(Backtester):
    """Backtester con universo che cambia nel tempo. Le regole di decisione e di rischio sono quelle congelate."""

    def __init__(self, daily, limits, member: pd.DataFrame | None = None, always: list[str] = ETFS, **kw):
        super().__init__(daily, limits, **kw)
        n = len(self.idx)
        self.member = {}
        for s in self.sat_symbols:
            if member is not None and s in member.columns and s not in always:
                self.member[s] = member[s].reindex(self.idx, fill_value=False).to_numpy()
            elif member is None or s in always:
                self.member[s] = np.ones(n, dtype=bool)
            else:
                self.member[s] = np.zeros(n, dtype=bool)
        # ultimo giorno con un prezzo: da lì in poi il titolo non c'è più
        self.last_bar = {}
        for s in self.sat_symbols:
            ok = np.flatnonzero(np.isfinite(self.arr[s]["open"]))
            self.last_bar[s] = int(ok[-1]) if len(ok) else -1
        self._cand: dict[tuple, tuple] = {}

    def scores(self, p: dict) -> dict:
        key = (p["fast"], p["slow"], p["k"])
        fresh = key not in self._cache
        out = super().scores(p)
        if fresh:
            n = len(self.idx)
            for s in self.sat_symbols:
                gone = self.last_bar[s]
                for kind in ("trend", "meanrev"):
                    if s not in out[kind]:
                        continue
                    entry, hold = out[kind][s].copy(), out[f"{kind}_hold"][s].copy()
                    entry[~self.member[s]] = np.nan                 # fuori dall'indice: niente nuove entrate
                    if 0 <= gone < n - 1:                            # titolo che smette di quotare
                        entry[max(gone - 1, 0):] = np.nan
                        hold[max(gone - 1, 0):] = FORCE_EXIT        # decisione la sera prima, uscita all'ultima apertura
                    out[kind][s], out[f"{kind}_hold"][s] = entry, hold
            # matrice dei candidati all'entrata: |punteggio| >= ENTER in almeno una strategia
            syms = self.sat_symbols
            best = np.full((n, len(syms)), -np.inf)
            for j, s in enumerate(syms):
                for kind in ("trend", "meanrev"):
                    a = out[kind].get(s)
                    if a is not None:
                        best[:, j] = np.fmax(best[:, j], np.abs(np.nan_to_num(a, nan=-np.inf)))
            self._cand[key] = (np.asarray(syms), best >= ENTER)
        return out

    def _decide(self, book, i, sc, equity):
        # Solo i titoli che possono cambiare qualcosa: quelli in posizione e quelli sopra la soglia d'entrata.
        # Per gli altri decide() restituirebbe "skip" (la fusione pesata non supera mai il massimo dei punteggi).
        key = next(k for k, v in self._cache.items() if v is sc)
        syms, mask = self._cand[key]
        full = self.sat_symbols
        self.sat_symbols = sorted(set(syms[mask[i]]) | set(book.positions))
        try:
            return super()._decide(book, i, sc, equity)
        finally:
            self.sat_symbols = full


def walk_forward_pit(daily, limits, member=None, years=15, **kw) -> dict:
    """walk_forward congelato, con il Backtester point-in-time al posto di quello normale."""
    original = bt_module.Backtester
    bt_module.Backtester = lambda d, l, c, s, variant=None: PITBacktester(d, l, member, cost_bps=c, slippage_bps=s,
                                                                          variant=variant)
    try:
        return walk_forward(daily, limits, years=years, **kw)
    finally:
        bt_module.Backtester = original


# ---------------------------------------------------------------- Il test

def _sat_returns(res: dict, start: str) -> pd.Series:
    eq = pd.Series({pd.Timestamp(d): v for d, v in res["equity"]})
    return eq.pct_change().reindex(eq.index[eq.index >= start]).fillna(0)


def _one_random(args):
    data, member, symbols, start, years = args
    res = walk_forward_pit(data, replace(RiskLimits(), core_enabled=False), member=member, years=years)
    r = _sat_returns(res, start)
    return {"symbols": symbols, "sharpe": summary(r)["sharpe"], "cagr": summary(r)["cagr"],
            "trades": res["trades"].get("count", 0)}


def random_universes(member: pd.DataFrame, k: int, n_stocks: int, at: str, seed: int,
                     available: set | None = None) -> list[list[str]]:
    pool = sorted(member.columns[member.loc[pd.Timestamp(at)].to_numpy()])
    if available is not None:
        pool = [s for s in pool if s in available]      # solo titoli con prezzi: ogni universo ha davvero n titoli
    rng = np.random.default_rng(seed)
    return [ETFS + sorted(rng.choice([s for s in pool if s not in ETFS], n_stocks, replace=False).tolist())
            for _ in range(k)]


def run(daily: dict[str, pd.DataFrame], member: pd.DataFrame, start="2005-01-03", end="2019-12-31",
        k=100, seed=11, workers=6) -> dict:
    daily, dropped = clean({s: d[d.index <= end] for s, d in daily.items()})
    n_eval = int((daily["SPY"].index >= start).sum())
    years = math.ceil(n_eval / 252)
    sat_limits = replace(RiskLimits(), core_enabled=False)
    member = member[(member.index >= daily["SPY"].index[0]) & (member.index <= end)]

    broad = {s: daily[s] for s in set(member.columns) | set(ETFS) if s in daily}
    res_broad = walk_forward_pit(broad, sat_limits, member=member, years=years)
    res_15 = walk_forward(daily_subset(daily, FIXED_15), sat_limits, years=years)
    r_broad, r_15 = _sat_returns(res_broad, start), _sat_returns(res_15, start)
    spy = daily["SPY"]["close"].pct_change().reindex(r_broad.index).fillna(0)

    draws = random_universes(member, k, len(FIXED_15) - len(ETFS), start, seed, available=set(daily))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = [(daily_subset(daily, u), member[[s for s in u if s in member.columns]], u, start, years) for u in draws]
        rand = list(pool.map(_one_random, jobs))
    sh_15 = summary(r_15)["sharpe"]
    share_ge = float(np.mean([x["sharpe"] >= sh_15 for x in rand]))

    cov = coverage(member[member.index >= start], daily)
    out = {
        "period": {"from": str(r_broad.index[0].date()), "to": str(r_broad.index[-1].date()), "days": len(r_broad)},
        "coverage": cov, "dropped": dropped,
        "spy": summary(spy),
        "broad": {**summary(r_broad), "trades": res_broad["trades"], "dsr": deflated_sharpe(r_broad, n_trials=10),
                  "corr_spy": float(r_broad.corr(spy))},
        "fixed15": {**summary(r_15), "trades": res_15["trades"]},
        "random": {"k": k, "seed": seed, "sharpe": [x["sharpe"] for x in rand], "cagr": [x["cagr"] for x in rand],
                   "median_sharpe": float(np.median([x["sharpe"] for x in rand])),
                   "share_ge_fixed15": share_ge, "draws": rand},
    }
    out["decisions"] = {
        "R4_selection_bias": share_ge <= 0.10,
        "R5_broad_evidence": out["broad"]["dsr"]["dsr"] >= 0.95 and cov["share"] >= 0.90,
        "R5_coverage_ok": cov["share"] >= 0.90,
    }
    return out


def daily_subset(daily, symbols):
    return {s: daily[s] for s in symbols if s in daily}


def load_cache(path="data/sp500/yahoo_2003_2020.pkl") -> dict[str, pd.DataFrame]:
    with open(path, "rb") as f:
        return pickle.load(f)


def report(o: dict) -> str:
    def pct(x):
        return f"{x * 100:+.1f}%"

    b, f, rnd, c = o["broad"], o["fixed15"], o["random"], o["coverage"]
    q = np.percentile(rnd["sharpe"], [10, 50, 90])
    L = [f"# Risultati: universo storico S&P 500 ({o['period']['from']} → {o['period']['to']})", "",
         f"Copertura dei prezzi: **{c['share']:.1%}** dei giorni-membro ({c['covered']:,} su {c['member_days']:,}). "
         f"Serie escluse per dati impossibili: {', '.join(o.get('dropped', [])) or 'nessuna'}.", "",
         "| Satellite PULSE da solo | CAGR | Vol | Sharpe | Max DD | Trade |", "|---|---|---|---|---|---|",
         f"| S&P 500 storico (point-in-time) | {pct(b['cagr'])} | {b['vol'] * 100:.1f}% | {b['sharpe']:.2f} | "
         f"{pct(b['max_drawdown'])} | {b['trades'].get('count', 0)} |",
         f"| 15 titoli scelti oggi | {pct(f['cagr'])} | {f['vol'] * 100:.1f}% | {f['sharpe']:.2f} | "
         f"{pct(f['max_drawdown'])} | {f['trades'].get('count', 0)} |",
         f"| SPY buy & hold (riferimento) | {pct(o['spy']['cagr'])} | {o['spy']['vol'] * 100:.1f}% | "
         f"{o['spy']['sharpe']:.2f} | {pct(o['spy']['max_drawdown'])} | |", "",
         f"**{rnd['k']} universi casuali** (12 titoli presi a caso tra i membri del 3/1/2005 + SPY, QQQ, IWM): "
         f"Sharpe del satellite al 10°, 50° e 90° percentile = {q[0]:.2f}, {q[1]:.2f}, {q[2]:.2f}. "
         f"Quota con Sharpe ≥ quello dei 15 titoli scelti oggi: **{rnd['share_ge_fixed15']:.0%}**.", "",
         f"**Deflated Sharpe Ratio** dell'universo ampio (N = {b['dsr']['n_trials']}): {b['dsr']['dsr']:.2f}. "
         f"Correlazione con SPY {b['corr_spy']:.2f}.", "", "## Decisioni (regole pre-registrate)", ""]
    d = o["decisions"]
    L.append(f"4. Bias di selezione dei 15 titoli: **{'SÌ' if d['R4_selection_bias'] else 'NO'}**")
    L.append(f"5. Evidenza sull'universo ampio: **{'SÌ' if d['R5_broad_evidence'] else 'NO'}**"
             + ("" if d["R5_coverage_ok"] else " (copertura sotto il 90%: un esito positivo non sarebbe stato accettato)"))
    return "\n".join(L) + "\n"
