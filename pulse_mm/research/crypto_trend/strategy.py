"""Regola di PULSE-CT ipotesi 1 e simulazione giornaliera (sezione 1 della pre-registrazione).

Scelte d'implementazione dove il documento lascia un dettaglio (valgono per strategia e benchmark):
- Calendario: tutti i giorni. Un giorno senza candela non ha scambi; le posizioni si valutano all'ultima chiusura
  nota, e i segnali usano le chiusure portate avanti.
- Decisione una volta a settimana (revisione 1): il lunedì t, con le chiusure fino alla domenica t−1, esecuzione
  all'apertura della candela del lunedì. Il costo si paga a parte, in cassa, così il registro dei costi è esatto.
- Il cambio di livello di m si confronta con il livello alla decisione precedente di quell'asset.
- Volatilità: deviazione standard (ddof=1) dei rendimenti semplici giornalieri degli ultimi 63 giorni, × √365.
- Il riallineamento delle quote al 50/50 avviene al primo lunedì di ogni mese, in sola cassa, valutato alla
  chiusura della domenica, anche se manca la candela del lunedì (revisione 2, ambiguità 1).
- Il peso attuale per la soglia e per il tetto di leva si valuta alla chiusura della domenica; la quantità nuova è
  peso obiettivo × capitale della quota all'apertura / apertura, con i costi pagati dopo (revisione 2, 1-2).
- Tetto di leva 1: se il peso attuale supera 1 si scambia comunque, anche sotto la soglia dei 10 punti.
- Prima che segnale e volatilità esistano (riscaldamento), il peso obiettivo è 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ...core.costs import Cost, CostModelBp, Ledger
from . import config


def signals(close: pd.Series) -> pd.DataFrame:
    """s_h, m e volatilità annualizzata per ogni giorno, calcolati sulle chiusure fino a quel giorno incluso."""
    c = close.ffill()
    out = pd.DataFrame(index=c.index)
    for h in config.HORIZONS:
        out[f"s{h}"] = np.sign(c / c.shift(h) - 1.0)
    out["m"] = out[[f"s{h}" for h in config.HORIZONS]].mean(axis=1, skipna=False)
    r = c.pct_change()
    out["sigma"] = r.rolling(config.VOL_WINDOW, min_periods=config.VOL_WINDOW).std(ddof=1) * np.sqrt(config.ANN)
    return out


def exposure(sig: pd.DataFrame, variant: str) -> tuple[pd.Series, pd.Series]:
    """Esposizione prima del volatility targeting e il suo 'livello' (un cambio di livello forza lo scambio)."""
    if variant == "BENCH":
        e = pd.Series(1.0, index=sig.index).where(sig["sigma"].notna())
        return e, pd.Series(1.0, index=sig.index)
    if variant == "V1":
        lvl = sig["s252"]
        e = lvl.clip(lower=0)
    elif variant == "V2":
        lvl = sig["m"]
        e = (lvl > 0).astype(float).where(lvl.notna())
    elif variant == "V3":
        lvl = sig["m"]
        e = lvl.clip(lower=0)
    else:
        raise ValueError(variant)
    return e, lvl


def target_weights(sig: pd.DataFrame, variant: str) -> tuple[pd.Series, pd.Series]:
    e, lvl = exposure(sig, variant)
    scale = (config.VOL_TARGET / sig["sigma"]).clip(upper=config.MAX_LEV)
    w = (e * scale).where(sig["sigma"].notna())
    return w.fillna(0.0), lvl


@dataclass
class Result:
    equity: pd.Series
    gross_equity: pd.Series
    ledger: Ledger
    trades: list = field(default_factory=list)
    weights: pd.DataFrame | None = None
    realigned: list = field(default_factory=list)

    def returns(self, start, end) -> pd.Series:
        r = self.equity.pct_change()
        return r[(r.index >= start) & (r.index <= end)].fillna(0.0)


def cost_mult(day: pd.Timestamp, stress: float = 1.0) -> float:
    return (2.0 if day < config.COST_DOUBLE_BEFORE else 1.0) * stress


def is_decision_day(d: pd.Timestamp, weekday: int | None) -> bool:
    return weekday is None or d.weekday() == weekday


def is_realign_day(d: pd.Timestamp, weekday: int | None) -> bool:
    """Primo giorno di decisione del mese (con decisione giornaliera: il primo del mese)."""
    return d.day <= 7 and d.weekday() == weekday if weekday is not None else d.day == 1


def sleeve_shares(sig: dict[str, pd.DataFrame], i: int, split: str = "equal") -> dict[str, float]:
    """Quote di capitale al riallineamento: 50/50, oppure 1/σ₆₃ normalizzato (parità di rischio)."""
    assets = list(sig)
    if split == "risk_parity":
        inv = {a: 1.0 / float(sig[a]["sigma"].iloc[i]) for a in assets}
        if all(np.isfinite(v) and v > 0 for v in inv.values()):
            tot = sum(inv.values())
            return {a: inv[a] / tot for a in assets}
    return {a: config.SPLIT for a in assets}


def simulate(px: dict[str, pd.DataFrame], variant: str, model: CostModelBp, end, capital: float = 100_000.0,
             stress: float = 1.0, weekday: int | None = config.DECISION_WEEKDAY,
             threshold: float = config.THRESHOLD, split: str = "equal") -> Result:
    """Simula la regola dal primo giorno di dati fino a `end`. px: candele giornaliere per asset (open, close).

    `weekday=None` riproduce la regola giornaliera scartata nella revisione 1 (solo per documentarne il turnover).
    `split="risk_parity"` è la robustezza della sezione 2: al riallineamento mensile le quote vanno in proporzione a
    1/σ₆₃ di ogni asset alla chiusura della domenica, invece di 50/50. Prima che σ₆₃ esista resta 50/50.
    """
    if split not in ("equal", "risk_parity"):
        raise ValueError(f"split sconosciuto: {split}")
    end = pd.Timestamp(end)
    assets = list(config.ASSETS)
    px = {a: df[df.index >= config.WARMUP_START] for a, df in px.items()}   # sezione 3: dati dal riscaldamento
    start = min(px[a].index.min() for a in assets)
    days = pd.date_range(start, end, freq="D")
    opens = pd.DataFrame({a: px[a]["open"].reindex(days) for a in assets})
    closes_raw = pd.DataFrame({a: px[a]["close"].reindex(days) for a in assets})
    closes = closes_raw.ffill()
    tw, lv, sig = {}, {}, {}
    for a in assets:
        sig[a] = signals(closes_raw[a])
        tw[a], lv[a] = target_weights(sig[a], variant)

    units = {a: 0.0 for a in assets}
    cash = {a: capital * config.SPLIT for a in assets}
    ledger, trades = Ledger(), []
    eq = np.empty(len(days))
    weights = np.zeros((len(days), len(assets)))
    realigned = []
    last_lvl = {a: np.nan for a in assets}
    for i, d in enumerate(days):
        o = opens.iloc[i]
        mark = o.where(o.notna(), closes.iloc[i - 1] if i > 0 else o)   # prezzo di riferimento all'apertura
        if i == 0 or not is_decision_day(d, weekday):
            pass
        else:
            prev = closes.iloc[i - 1].fillna(0.0)          # chiusura della domenica: valutazione alla decisione
            realign_today = is_realign_day(d, weekday)
            if realign_today:
                total = sum(units[a] * prev[a] + cash[a] for a in assets)
                shares = sleeve_shares(sig, i - 1, split)
                for a in assets:
                    cash[a] = total * shares[a] - units[a] * prev[a]
                realigned.append((d, {a: units[a] * prev[a] + cash[a] for a in assets}))
            for a in assets:
                if pd.isna(o[a]):
                    continue                               # candela mancante: niente scambi su questo asset
                lvl_now = lv[a].iloc[i - 1]
                lvl_changed = bool(pd.notna(lvl_now) and pd.notna(last_lvl[a]) and lvl_now != last_lvl[a])
                last_lvl[a] = lvl_now
                cap_close = units[a] * prev[a] + cash[a]
                cap = units[a] * o[a] + cash[a]           # capitale della quota all'apertura: dimensione dello scambio
                if cap <= 0 or cap_close <= 0:
                    continue
                w_cur = units[a] * prev[a] / cap_close
                w_tgt = float(tw[a].iloc[i - 1])
                over = realign_today and w_cur > config.MAX_LEV + 1e-9   # solo dopo il riallineamento (3b)
                gap = abs(w_tgt - w_cur)
                if gap < 1e-12 or not (gap >= threshold - 1e-12 or lvl_changed or over):
                    continue
                new_units = w_tgt * cap / o[a]
                dq = new_units - units[a]
                notional = abs(dq) * o[a]
                cost = model.on(notional, cost_mult(d, stress))
                cash[a] -= dq * o[a] + cost.total
                units[a] = new_units
                ledger.add((d, a), cost, notional)
                trades.append({"date": d, "asset": a, "dq": dq, "price": float(o[a]), "notional": notional,
                               "cost": cost.total, "fee": cost.fee, "spread": cost.spread,
                               "slippage": cost.slippage,
                               "weight_after": units[a] * o[a] / (units[a] * o[a] + cash[a]),
                               "equity": sum(units[b] * (mark[b] if pd.notna(mark[b]) else 0.0) + cash[b] for b in assets)})
        c = closes.iloc[i]
        sleeve = {a: units[a] * (c[a] if pd.notna(c[a]) else 0.0) for a in assets}
        eq[i] = sum(sleeve[a] + cash[a] for a in assets)
        for j, a in enumerate(assets):
            cap = sleeve[a] + cash[a]
            weights[i, j] = sleeve[a] / cap if cap else 0.0
    equity = pd.Series(eq, index=days)
    return Result(equity=equity, gross_equity=replay_gross(trades, closes, capital, days), ledger=ledger,
                  trades=trades, weights=pd.DataFrame(weights, index=days, columns=assets), realigned=realigned)


def replay_gross(trades: list, closes: pd.DataFrame, capital: float, days: pd.DatetimeIndex) -> pd.Series:
    """Rigioca gli stessi scambi senza costi: serve a verificare il registro dei costi in modo indipendente."""
    units = {a: 0.0 for a in closes.columns}
    cash = capital
    by_day: dict = {}
    for t in trades:
        by_day.setdefault(t["date"], []).append(t)
    out = np.empty(len(days))
    for i, d in enumerate(days):
        for t in by_day.get(d, []):
            units[t["asset"]] += t["dq"]
            cash -= t["dq"] * t["price"]
        c = closes.iloc[i]
        out[i] = cash + sum(units[a] * (c[a] if pd.notna(c[a]) else 0.0) for a in closes.columns)
    return pd.Series(out, index=days)


def reconcile(res: Result) -> dict:
    """Ogni giorno: lordo − netto deve coincidere con i costi cumulati del registro, entro 0,01 bp del capitale."""
    cum = pd.Series(0.0, index=res.equity.index)
    for (d, _), _, c in res.ledger.rows:
        cum.loc[d] += c.total
    cum = cum.cumsum()
    err = ((res.gross_equity - res.equity) - cum).abs() / res.equity * 1e4
    return {"max_error_bp": float(err.max()), "ok": bool(err.max() <= 0.01),
            "costs_total": float(cum.iloc[-1])}


def turnover(res: Result, start, end) -> dict:
    """Turnover annuo = nozionale scambiato / capitale medio, annualizzato su 365 giorni."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    tr = [t for t in res.trades if start <= t["date"] <= end]
    eq = res.equity[(res.equity.index >= start) & (res.equity.index <= end)]
    days = len(eq)
    notional = sum(t["notional"] for t in tr)
    yearly = notional / eq.mean() * config.ANN / days if days else 0.0
    sizes = [t["notional"] / t["equity"] for t in tr if t["equity"]]
    return {"trades": len(tr), "turnover_per_year": yearly, "ok": yearly <= config.TURNOVER_MAX,
            "median_trade_share_of_capital": float(np.median(sizes)) if sizes else 0.0}


def costs_in_period(res: Result, start, end) -> dict:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sub = Ledger([r for r in res.ledger.rows if start <= r[0][0] <= end])
    return sub.in_bp()


def avg_exposure(res: Result, start, end) -> float:
    w = res.weights[(res.weights.index >= start) & (res.weights.index <= end)]
    return float(w.mean().mean())


def truncation_check(px: dict[str, pd.DataFrame], variant: str, model: CostModelBp, cut, end) -> dict:
    """Controllo di lookahead (revisione 2): con i dati troncati a `cut`, pesi e scambi fino a `cut` non cambiano."""
    cut = pd.Timestamp(cut)
    full = simulate(px, variant, model, end=end)
    short = simulate({a: df[df.index <= cut] for a, df in px.items()}, variant, model, end=cut)
    key = lambda t: (t["date"], t["asset"], round(t["dq"], 9), round(t["cost"], 9))
    a = [key(t) for t in full.trades if t["date"] <= cut]
    b = [key(t) for t in short.trades]
    w_full = full.weights[full.weights.index <= cut]
    w_diff = float((w_full - short.weights).abs().max().max())
    eq_diff = float((full.equity[full.equity.index <= cut] - short.equity).abs().max())
    return {"cut": cut.strftime("%Y-%m-%d"), "trades_compared": len(b), "trades_equal": a == b,
            "max_weight_diff": w_diff, "max_equity_diff": eq_diff,
            "ok": a == b and w_diff < 1e-12 and eq_diff < 1e-6}


def cost_model(provisional: bool = False) -> CostModelBp:
    taker = config.TAKER_BP
    if taker is None:
        if not provisional:
            raise PermissionError("Tariffa taker di OKX Europe non scritta (criterio 8)")
        taker = config.PROVISIONAL_TAKER_BP
    return CostModelBp(fee_bp=taker, spread_bp=config.HALF_SPREAD_BP, slippage_bp=config.SLIPPAGE_BP)


__all__ = ["signals", "target_weights", "simulate", "reconcile", "turnover", "cost_model", "Cost"]
