"""Report mensile della fase in avanti (regole in docs/preregistrazione-avanti.md).

Quattro blocchi, tutti calcolati dal diario e da barre giornaliere:
1. regola di riattivazione del satellite: "core filtrato + ombra" contro "core filtrato";
2. controllo dei disastri a 6 mesi;
3. controllo dei guasti: l'ombra contro il backtest degli stessi giorni con lo stesso universo a regola;
4. comitato AI: Spearman a 5 giorni in eccesso su SPY, valore aggiunto sul punteggio, Brier.

Il modulo legge e basta: non tocca ordini, pesi o file congelati.
"""
from __future__ import annotations

import math
import os
from dataclasses import replace

import numpy as np
import pandas as pd

from .backtest import DEFAULT_PARAMS
from .config import RiskLimits
from .research import block_bootstrap_delta_sharpe, summary
from .universe import ETFS, PITBacktester

MATCH_MIN = 0.80           # quota minima di entrate abbinate, in entrambe le direzioni
PNL_GAP_BP = 50.0          # scarto medio massimo di P&L per trade abbinato
DISASTER_DAYS = 126        # ~6 mesi di borsa
REACTIVATE = {"months": 12, "trades": 100}
COMMITTEE = {"months": 12, "windows": 50, "t": 2.0}
HORIZON = 5


# ---------------------------------------------------------------- Serie dal diario

def _daily_last(rows: list[dict], col: str = "equity") -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["ts"].str[:10])
    return df.groupby("day")[col].last().astype(float)


def equity_series(j) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(conto vero, P&L cumulato dell'ombra, SPY) a fine giornata."""
    acc_rows = j.rows("SELECT ts, equity, spy FROM equity WHERE mode != 'SHADOW' ORDER BY ts")
    acc = _daily_last(acc_rows)
    spy = _daily_last([r for r in acc_rows if r["spy"] is not None], "spy")
    sh = _daily_last(j.rows("SELECT ts, equity FROM equity WHERE mode = 'SHADOW' ORDER BY ts"))
    sh = sh.reindex(acc.index).ffill().fillna(0.0) if len(acc) else sh
    return acc, sh, spy


def reactivation(j) -> dict:
    acc, sh, spy = equity_series(j)
    trades = j.db_query("SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM closed_trades WHERE mode='SHADOW'")[0]
    out = {"days": len(acc), "months": round(len(acc) / 21, 1), "trades": int(trades[0]),
           "shadow_pnl": float(sh.iloc[-1]) if len(sh) else 0.0, "realized_pnl": float(trades[1])}
    if len(acc) < 30:
        out.update(delta=None, disaster=None, conditions=None, note="meno di 30 giorni: troppo presto per i conti")
        return out
    r_core = acc.pct_change().dropna()
    r_both = (acc + sh).pct_change().dropna()
    d = block_bootstrap_delta_sharpe(r_both, r_core.reindex(r_both.index).fillna(0))
    out["delta"] = d
    out["core"], out["core_plus_shadow"] = summary(r_core), summary(r_both)
    if len(spy) > 30:
        out["spy"] = summary(spy.pct_change().dropna())
    out["disaster"] = bool(len(acc) >= DISASTER_DAYS and d["hi"] < 0)
    out["conditions"] = {
        "12 mesi": out["months"] >= REACTIVATE["months"],
        "100 trade in ombra": out["trades"] >= REACTIVATE["trades"],
        "P&L ombra > 0": out["shadow_pnl"] > 0,
        "limite inferiore ΔSharpe > 0": d["lo"] > 0,
    }
    return out


# ---------------------------------------------------------------- Guasti: ombra contro backtest

def member_frame(history: dict[str, list[str]], index: pd.DatetimeIndex) -> pd.DataFrame:
    syms = sorted({s for v in history.values() for s in v})
    m = pd.DataFrame(False, index=index, columns=syms)
    months = index.to_period("M").astype(str)
    for month, symbols in history.items():
        rows = months == month
        m.loc[rows, [s for s in symbols if s in m.columns]] = True
    return m


def _match(a: list[tuple], b: list[tuple], days: pd.DatetimeIndex) -> float:
    """Quota delle entrate in a con un'entrata in b sullo stesso titolo entro 1 giorno di borsa."""
    if not a:
        return 1.0
    pos = {d: i for i, d in enumerate(days)}
    bset = {}
    for s, d in b:
        bset.setdefault(s, []).append(pos.get(d, -10))
    hit = sum(any(abs(pos.get(d, -99) - x) <= 1 for x in bset.get(s, [])) for s, d in a)
    return hit / len(a)


def backtest_check(j, daily: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp,
                   fixed: list[str] | None = None) -> dict:
    history = j.get("shadow_universe_history") or {}
    if not history and fixed and "SPY" in daily:        # ombra sulla lista fissa (SHADOW_UNIVERSE=fixed)
        history = {m: list(fixed) for m in set(daily["SPY"].index.to_period("M").astype(str))}
    if not history or "SPY" not in daily:
        return {"status": "non disponibile", "note": "manca la storia dell'universo o lo storico di SPY"}
    bt = PITBacktester(daily, replace(RiskLimits(), core_enabled=False),
                       member=member_frame(history, daily["SPY"].index))
    days = bt.idx
    i0, i1 = int(days.searchsorted(start)), int(days.searchsorted(end, side="right"))
    if i1 - i0 < 2:
        return {"status": "non disponibile", "note": "periodo troppo corto"}
    book, _, trades, _ = bt.run(i0, i1, DEFAULT_PARAMS)
    bt_entries = [(t["symbol"], pd.Timestamp(t["entry_date"])) for t in trades]
    bt_entries += [(s, pd.Timestamp(p.entry_date)) for s, p in book.positions.items()]
    live = j.rows("SELECT ts, symbol FROM orders WHERE status='shadow' AND side='buy' ORDER BY ts")
    live_entries = sorted({(r["symbol"], pd.Timestamp(r["ts"][:10])) for r in live
                           if start <= pd.Timestamp(r["ts"][:10]) <= end})
    share_live, share_bt = _match(live_entries, bt_entries, days), _match(bt_entries, live_entries, days)
    # P&L dei trade chiusi abbinati
    gaps = []
    pos = {d: i for i, d in enumerate(days)}
    for r in j.rows("SELECT symbol, entry_ts, pnl_pct FROM closed_trades WHERE mode='SHADOW' AND entry_ts IS NOT NULL"):
        d = pd.Timestamp(r["entry_ts"][:10])
        if not (start <= d <= end):
            continue
        cand = [t for t in trades if t["symbol"] == r["symbol"]
                and abs(pos.get(pd.Timestamp(t["entry_date"]), -99) - pos.get(d, 99)) <= 1]
        if cand:
            gaps.append(abs(r["pnl_pct"] - cand[0]["pnl_pct"]) * 10_000)
    gap = float(np.mean(gaps)) if gaps else None
    ok = share_live >= MATCH_MIN and share_bt >= MATCH_MIN and (gap is None or gap <= PNL_GAP_BP)
    return {"status": "OK" if ok else "FALLITO", "live_entries": len(live_entries), "bt_entries": len(bt_entries),
            "share_live_in_bt": share_live, "share_bt_in_live": share_bt, "matched_closed": len(gaps),
            "pnl_gap_bp": gap}


# ---------------------------------------------------------------- Comitato AI

def _spearman(x: pd.Series, y: pd.Series) -> float:
    if len(x) < 5 or x.nunique() < 2 or y.nunique() < 2:
        return float("nan")
    return float(np.corrcoef(x.rank(), y.rank())[0, 1])


def committee(j, closes: pd.DataFrame, model: str, cutoff: str) -> dict:
    """closes: chiusure giornaliere (colonne = titoli, SPY compreso)."""
    votes = pd.DataFrame(j.rows("SELECT ts, symbol, conviction, model FROM votes ORDER BY ts"))
    if votes.empty:
        return {"windows": 0, "note": "nessun voto registrato"}
    votes = votes[(votes["model"] == model) & (votes["ts"] >= cutoff)]
    sig = pd.DataFrame(j.rows("SELECT ts, symbol, trend_score, mr_score FROM signals ORDER BY ts"))
    if votes.empty or "SPY" not in closes:
        return {"windows": 0, "note": "nessun voto valido (modello attuale, dopo la data limite)"}
    votes["day"] = pd.to_datetime(votes["ts"].str[:10])
    if not sig.empty:
        sig["day"] = pd.to_datetime(sig["ts"].str[:10])
        sig["score"] = sig["trend_score"].fillna(sig["mr_score"]).fillna(0.0)
    days = closes.index[closes.index >= votes["day"].min()]
    rows, corr, corr_res = [], [], []
    for k in range(0, len(days) - HORIZON, HORIZON):          # finestre che non si sovrappongono
        d0, d1 = days[k], days[k + HORIZON]
        lo = days[max(k - HORIZON + 1, 0)]
        v = votes[(votes["day"] >= lo) & (votes["day"] <= d0)].groupby("symbol")["conviction"].last()
        v = v[[s for s in v.index if s in closes.columns and s != "SPY"]]
        if v.empty:
            continue
        ret = closes.loc[d1, v.index] / closes.loc[d0, v.index] - 1
        excess = ret - (closes.loc[d1, "SPY"] / closes.loc[d0, "SPY"] - 1)
        score = pd.Series(0.0, index=v.index)
        if not sig.empty:
            s = sig[sig["day"] <= d0].groupby("symbol")["score"].last()
            score = s.reindex(v.index).fillna(0.0)
        ok = excess.notna()
        v, excess, score = v[ok], excess[ok], score[ok]
        for s in v.index:
            rows.append((d0, s, float(v[s]), float(score[s]), float(excess[s])))
        c = _spearman(v, excess)
        if not math.isnan(c):
            corr.append(c)
    out = {"windows": len(corr), "votes": len(votes), "first_vote": str(votes["day"].min().date())}
    if len(corr) >= 2:
        c = np.array(corr)
        out["spearman_mean"] = float(c.mean())
        sd = c.std(ddof=1)
        out["spearman_t"] = (float(c.mean() / sd * math.sqrt(len(c))) if sd > 1e-12
                             else math.copysign(math.inf, c.mean()) if c.mean() else 0.0)
    if len(rows) >= 10:
        df = pd.DataFrame(rows, columns=["d", "symbol", "conv", "score", "excess"])
        X = np.column_stack([np.ones(len(df)), df["score"] / 100, df["conv"]])
        beta, *_ = np.linalg.lstsq(X, df["excess"].to_numpy(), rcond=None)
        out["regression"] = {"intercept": float(beta[0]), "score": float(beta[1]), "committee": float(beta[2])}
        # voto depurato dalla parte spiegata dal punteggio
        Xs = np.column_stack([np.ones(len(df)), df["score"] / 100])
        g, *_ = np.linalg.lstsq(Xs, df["conv"].to_numpy(), rcond=None)
        df["res"] = df["conv"] - Xs @ g
        for _, w in df.groupby("d"):
            cr = _spearman(w["res"], w["excess"])
            if not math.isnan(cr):
                corr_res.append(cr)
        out["residual_spearman_mean"] = float(np.mean(corr_res)) if corr_res else None
        p_up = (0.5 + df["conv"] / 2).clip(0, 1)
        out["brier"] = float(((p_up - (df["excess"] > 0)) ** 2).mean())
        out["reliability"] = (df.assign(b=pd.cut(p_up, [0, .2, .4, .6, .8, 1.0], include_lowest=True))
                              .groupby("b", observed=True)["excess"].agg(lambda x: float((x > 0).mean()))
                              .rename(lambda i: str(i)).to_dict())
    months = (days[-1] - votes["day"].min()).days / 30.4 if len(days) else 0
    out["months"] = round(months, 1)
    out["weight_01"] = bool(
        months >= COMMITTEE["months"] and out["windows"] >= COMMITTEE["windows"]
        and out.get("spearman_mean", 0) > 0 and out.get("spearman_t", 0) > COMMITTEE["t"]
        and out.get("regression", {}).get("committee", 0) > 0 and (out.get("residual_spearman_mean") or 0) > 0)
    return out


# ---------------------------------------------------------------- Report

def run(j, daily: dict[str, pd.DataFrame], model: str, cutoff: str | None = None,
        start: pd.Timestamp | None = None, end: pd.Timestamp | None = None, fixed: list[str] | None = None) -> dict:
    cutoff = cutoff or os.getenv("COMMITTEE_CUTOFF", "2026-07-01")
    acc, _, _ = equity_series(j)
    start = start or (acc.index[0] if len(acc) else None)
    end = end or (acc.index[-1] if len(acc) else None)
    out = {"period": {"from": str(start.date()) if start is not None else None,
                      "to": str(end.date()) if end is not None else None},
           "reactivation": reactivation(j)}
    if start is not None:
        out["backtest_check"] = backtest_check(j, daily, start, end, fixed)
    closes = pd.DataFrame({s: d["close"] for s, d in daily.items()}).sort_index()
    out["committee"] = committee(j, closes, model, cutoff)
    # due controlli dei guasti falliti di fila -> indagare
    checks = j.get("forward_checks") or {}
    if start is not None and out.get("backtest_check", {}).get("status") in ("OK", "FALLITO"):
        checks[str(end.date())[:7]] = out["backtest_check"]["status"] == "OK"
        j.set("forward_checks", checks)
    last2 = [checks[k] for k in sorted(checks)[-2:]]
    out["investigate"] = len(last2) == 2 and not any(last2)
    j.event("forward_report", {k: v for k, v in out.items() if k != "committee"})
    return out


def report(o: dict) -> str:
    def pct(x):
        return "—" if x is None else f"{x * 100:+.1f}%"

    r = o["reactivation"]
    L = [f"# Report in avanti ({o['period']['from']} → {o['period']['to']})", "",
         "## 1. Riattivazione del satellite (core filtrato + ombra contro core filtrato)", "",
         f"{r['days']} giorni di borsa ({r['months']} mesi) · {r['trades']} trade in ombra · "
         f"P&L ombra {r['shadow_pnl']:+,.0f} $ (realizzato {r['realized_pnl']:+,.0f} $)."]
    if r.get("delta"):
        d = r["delta"]
        L.append(f"ΔSharpe {d['delta']:+.2f} [IC 90% {d['lo']:+.2f}, {d['hi']:+.2f}]. "
                 f"Sharpe core {r['core']['sharpe']:.2f}, core + ombra {r['core_plus_shadow']['sharpe']:.2f}"
                 + (f", SPY {r['spy']['sharpe']:.2f}" if r.get("spy") else "") + ".")
        L += [""] + [f"- {'✅' if ok else '⬜'} {k}" for k, ok in r["conditions"].items()]
        L.append(f"\n**Satellite: {'si può riattivare' if all(r['conditions'].values()) else 'resta in ombra'}.**")
        L += ["", "## 2. Controllo dei disastri a 6 mesi", "",
              "**SCATTATO: chiudere l'ombra e cercare la causa.**" if r["disaster"] else
              ("Nessun segnale di guasto grave." if r["days"] >= DISASTER_DAYS else "Si valuta dopo 126 giorni di borsa.")]
    else:
        L.append(r.get("note", ""))
    b = o.get("backtest_check", {})
    L += ["", "## 3. Ombra contro backtest degli stessi giorni", ""]
    if b.get("status") in ("OK", "FALLITO"):
        gap = "—" if b["pnl_gap_bp"] is None else f"{b['pnl_gap_bp']:.0f} bp"
        L.append(f"**{b['status']}** · entrate ombra {b['live_entries']}, backtest {b['bt_entries']} · "
                 f"abbinate {b['share_live_in_bt']:.0%} / {b['share_bt_in_live']:.0%} (min {MATCH_MIN:.0%}) · "
                 f"scarto P&L medio {gap} su {b['matched_closed']} trade (max {PNL_GAP_BP:.0f} bp).")
    else:
        L.append(b.get("note", "non disponibile"))
    if o.get("investigate"):
        L.append("\n**Due mesi di fila falliti: indagare e annotare in docs/registro-interventi.md.**")
    c = o["committee"]
    L += ["", "## 4. Comitato AI (peso 0)", ""]
    if c.get("windows", 0) >= 2:
        reg = c.get("regression", {})
        L.append(f"{c['votes']} voti validi dal {c['first_vote']} · {c['windows']} finestre da 5 giorni · "
                 f"Spearman medio {c.get('spearman_mean', float('nan')):+.3f} (t {c.get('spearman_t', 0):+.2f}) · "
                 f"coefficiente del comitato {reg.get('committee', float('nan')):+.4f} · "
                 f"Spearman del voto depurato {c.get('residual_spearman_mean') or 0:+.3f} · "
                 f"Brier {c.get('brier', float('nan')):.3f}.")
        L.append(f"\n**Peso 0,1: {'condizioni soddisfatte' if c['weight_01'] else 'non ancora'}** "
                 f"(servono 12 mesi, 50 finestre, t > 2 e valore aggiunto positivo).")
    else:
        L.append(c.get("note") or f"{c.get('windows', 0)} finestre: troppo presto.")
    L += ["", "_Promemoria: con 12 mesi la probabilità di riconoscere un vantaggio vero è sotto il 15%. "
              "Questo report serve soprattutto a trovare guasti._"]
    return "\n".join(L) + "\n"
