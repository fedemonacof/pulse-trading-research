"""Backtest walk-forward di PULSE, con lo stesso codice del bot dal vivo.

- Stesse strategie (strategies/), stesso regime, stesso riflesso (reflex.decide) e stesso
  RiskGate: niente logica duplicata che possa divergere.
- Decisione a chiusura del giorno t, esecuzione all'apertura di t+1 con slippage e commissioni:
  nessun dato futuro entra in una decisione.
- Ordini bracket simulati sui massimi e minimi del giorno; se nella stessa barra si toccano sia lo
  stop sia il take profit, si assume lo stop (prudente). Se il prezzo apre oltre lo stop, si esce all'apertura.
- Walk-forward: per ogni finestra di test (3 mesi) i parametri si scelgono sui 6 mesi precedenti,
  mai su quelli di test. Il risultato è la concatenazione dei soli periodi fuori campione.
- Il comitato AI NON è incluso: rigiocarlo sul passato costerebbe molto e sarebbe falsato (il modello
  conosce già com'è andata). Questo backtest misura la parte deterministica.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import RiskLimits
from .reflex import DEFAULT_WEIGHTS, SymbolState, decide, position_size
from .risk import GateContext, Order, RiskGate
from .strategies import MeanReversion, TrendFollowing
from .strategies.base import atr as atr_series
from .strategies.regime import regime_series

DEFAULT_PARAMS = {"fast": 20, "slow": 50, "k": 2.0}
PARAM_GRID = [{"fast": f, "slow": s, "k": k} for f, s in ((10, 30), (20, 50), (30, 100)) for k in (1.8, 2.0, 2.2)]


@dataclass
class BTPosition:
    qty: int                 # negativo = short
    entry: float
    stop: float
    take_profit: float
    entry_date: pd.Timestamp
    regime: str
    strategy: str
    confidence: float


@dataclass
class Book:
    cash: float
    positions: dict[str, BTPosition] = field(default_factory=dict)
    pending: list[tuple[Order, dict]] = field(default_factory=list)
    prev_equity: float | None = None
    # core + satellite
    core_qty: int = 0
    core_target: int | None = None
    core_cost_today: float = 0.0
    sat_cum: float = 0.0          # P&L cumulato del satellite
    sat_peak: float = 0.0
    sat_halt_until: int = -1      # dopo un drawdown il satellite resta fermo per 21 giorni (nel live: fino a resume)
    gross_hist: list = field(default_factory=list)


class Backtester:
    def __init__(self, daily: dict[str, pd.DataFrame], limits: RiskLimits, cost_bps: float = 1.0,
                 slippage_bps: float = 5.0, weights: dict | None = None, variant: dict | None = None):
        if "SPY" not in daily:
            raise ValueError("Serve lo storico di SPY: definisce il regime e il benchmark")
        self.idx = daily["SPY"].index
        self.data = {s: df.reindex(self.idx) for s, df in daily.items()}
        self.symbols = list(daily)
        self.limits = limits
        self.cost = cost_bps / 10_000
        self.slip = slippage_bps / 10_000
        self.weights = weights or DEFAULT_WEIGHTS
        self.gate = RiskGate(limits)
        self.regime = regime_series(daily["SPY"]).reindex(self.idx).fillna("warming_up").to_numpy()
        self.atr = {s: atr_series(df.dropna()).reindex(self.idx).to_numpy() for s, df in self.data.items()}
        self.arr = {s: {k: df[k].to_numpy() for k in ("open", "high", "low", "close")} for s, df in self.data.items()}
        self._cache: dict[tuple, dict] = {}
        self.core = limits.core_enabled and limits.core_symbol in daily
        self.core_sym = limits.core_symbol
        self.sat_symbols = [s for s in self.symbols if not (self.core and s == self.core_sym)]
        # satellite in ombra: nel portafoglio reale non opera (si valuta a parte, in avanti)
        self.shadow = self.core and limits.satellite_mode == "shadow"
        # filtro a 200 giorni sul core: segnale di fine mese PRECEDENTE (niente look-ahead)
        self.core_on = np.ones(len(self.idx), dtype=bool)
        if self.core and limits.core_trend_filter:
            c = self.data[self.core_sym]["close"]
            sma = c.rolling(200).mean()
            last = c.groupby(c.index.to_period("M")).transform("last") == c      # ultimo giorno di ogni mese
            sig = pd.Series(np.where(last, (c > sma) | sma.isna(), np.nan), index=self.idx).ffill().fillna(1)
            self.core_on = sig.to_numpy().astype(bool)
        # variante delle strategie (parametri extra di TrendFollowing / MeanReversion), per i confronti
        self.variant = variant or {}

    # ---------- Segnali (calcolati una volta per set di parametri, solo con dati passati) ----------

    def scores(self, p: dict) -> dict:
        key = (p["fast"], p["slow"], p["k"])
        if key not in self._cache:
            tr = TrendFollowing(p["fast"], p["slow"], **self.variant.get("trend", {}))
            mr = MeanReversion(k=p["k"], **self.variant.get("meanrev", {}))
            out = {"trend": {}, "meanrev": {}, "trend_hold": {}, "meanrev_hold": {}}
            for s, df in self.data.items():
                d = df.dropna()
                if len(d) < 60:
                    continue
                f = tr.frame(d)
                out["trend"][s] = f["score"].reindex(self.idx).to_numpy()
                out["trend_hold"][s] = f["hold"].reindex(self.idx).to_numpy()
                if mr.applies_to(s):
                    g = mr.frame(d)
                    out["meanrev"][s] = g["score"].reindex(self.idx).to_numpy()
                    out["meanrev_hold"][s] = g["hold"].reindex(self.idx).to_numpy()
            self._cache[key] = out
        return self._cache[key]

    # ---------- Simulazione ----------

    def _fill(self, side: str, px: float) -> float:
        return px * (1 + self.slip) if side == "buy" else px * (1 - self.slip)

    def _close(self, book: Book, s: str, px: float, date, reason: str, trades: list) -> None:
        p = book.positions.pop(s)
        side = "sell" if p.qty > 0 else "buy"
        fill = self._fill(side, px)
        book.cash += p.qty * fill - abs(p.qty) * fill * self.cost
        d = 1 if p.qty > 0 else -1
        trades.append({
            "symbol": s, "direction": "long" if d > 0 else "short", "entry_date": p.entry_date, "exit_date": date,
            "entry": p.entry, "exit": fill, "qty": abs(p.qty),
            "pnl": (fill - p.entry) * p.qty - abs(p.qty) * (p.entry + fill) * self.cost,
            "pnl_pct": (fill / p.entry - 1) * d, "reason": reason, "regime": p.regime, "strategy": p.strategy,
            "confidence": p.confidence, "holding_days": int((date - p.entry_date).days),
        })

    def _core_trade(self, book: Book, dq: int, px: float) -> None:
        side = "buy" if dq > 0 else "sell"
        fill = self._fill(side, px)
        fee = abs(dq) * fill * self.cost
        book.cash -= dq * fill + fee
        book.core_qty += dq
        book.core_cost_today += fee + dq * (fill - px)   # commissione + slippage: costi del core, non del satellite

    def _plan_core(self, book: Book, i: int, equity: float) -> None:
        """A chiusura: il core per domani = equity meno riserva meno il satellite previsto dopo gli ordini."""
        c = self.arr[self.core_sym]["close"][i]
        if not np.isfinite(c) or equity <= 0:
            return
        sat = sum(abs(p.qty * self.arr[s]["close"][i]) for s, p in book.positions.items())
        for o, _ in book.pending:
            sat += (o.qty * (o.price or 0)) * (1 if o.is_entry else -1)
        target = equity * (1 - self.limits.core_cash_buffer_pct) - max(sat, 0)
        if not self.core_on[i]:
            target = 0.0                                  # SPY sotto la MA200 a fine mese: core in liquidità
        if abs(target - book.core_qty * c) / equity > self.limits.core_rebalance_band_pct:
            book.core_target = max(int(target / c), 0)

    def _flatten_satellite(self, book: Book, i: int, date, reason: str, trades: list) -> None:
        for s in list(book.positions):
            self._close(book, s, self.arr[s]["close"][i], date, reason, trades)
        book.pending = []

    def equity(self, book: Book, i: int) -> float:
        val = book.cash
        if book.core_qty:
            val += book.core_qty * self.arr[self.core_sym]["close"][i]
        for s, p in book.positions.items():
            c = self.arr[s]["close"][i]
            val += p.qty * (c if np.isfinite(c) else p.entry)
        return val

    def run(self, start: int, end: int, params: dict, book: Book | None = None, initial: float = 100_000.0):
        """Simula i giorni [start, end). Restituisce (book, curva di equity, trade chiusi, numero di veti)."""
        book = book or Book(cash=initial)
        sc = self.scores(params)
        curve, trades, vetoes = [], [], 0
        for i in range(start, end):
            date = self.idx[i]
            core_before, book.core_cost_today = book.core_qty, 0.0
            core_open = self.arr[self.core_sym]["open"][i] if self.core else np.nan
            # 1. Ordini decisi ieri sera, all'apertura: prima si vende il core (libera liquidità), poi il satellite,
            #    poi si ricompra il core con ciò che avanza. Come nel bot dal vivo.
            if self.core and book.core_target is not None and book.core_target < book.core_qty and np.isfinite(core_open):
                self._core_trade(book, book.core_target - book.core_qty, core_open)
            for o, meta in book.pending:
                op = self.arr[o.symbol]["open"][i]
                if not np.isfinite(op):
                    continue
                if o.is_entry:
                    fill = self._fill(o.side, op)
                    q = o.qty if o.side == "buy" else -o.qty
                    book.cash -= q * fill + o.qty * fill * self.cost
                    book.positions[o.symbol] = BTPosition(q, fill, o.stop, o.take_profit, date,
                                                          meta["regime"], meta["strategy"], meta["confidence"])
                elif o.symbol in book.positions:
                    self._close(book, o.symbol, op, date, o.reason, trades)
            book.pending = []
            if self.core and book.core_target is not None and book.core_target > book.core_qty and np.isfinite(core_open):
                self._core_trade(book, book.core_target - book.core_qty, core_open)
            book.core_target = None
            # 2. Bracket durante la giornata
            for s in list(book.positions):
                p, a = book.positions[s], self.arr[s]
                op, hi, lo = a["open"][i], a["high"][i], a["low"][i]
                if not np.isfinite(hi):
                    continue
                if p.qty > 0:
                    if lo <= p.stop:
                        self._close(book, s, min(op, p.stop), date, "stop loss (bracket)", trades)
                    elif hi >= p.take_profit:
                        self._close(book, s, max(op, p.take_profit), date, "take profit (bracket)", trades)
                else:
                    if hi >= p.stop:
                        self._close(book, s, max(op, p.stop), date, "stop loss (bracket)", trades)
                    elif lo <= p.take_profit:
                        self._close(book, s, min(op, p.take_profit), date, "take profit (bracket)", trades)
            # 3. Perdita giornaliera: in chiusura (il bot dal vivo lo fa nel minuto in cui succede)
            eq = self.equity(book, i)
            if self.core:
                # misurata sul SATELLITE: variazione dell'equity meno il P&L del core
                c_now, c_prev = self.arr[self.core_sym]["close"][i], self.arr[self.core_sym]["close"][i - 1]
                core_pnl = 0.0
                if np.isfinite(core_open) and np.isfinite(c_prev):
                    core_pnl = core_before * (core_open - c_prev) + book.core_qty * (c_now - core_open) - book.core_cost_today
                sat_day = (eq - book.prev_equity - core_pnl) if book.prev_equity else 0.0
                book.sat_cum += sat_day
                if book.prev_equity and sat_day / book.prev_equity <= -self.limits.max_daily_loss_pct:
                    self._flatten_satellite(book, i, date, "perdita giornaliera del satellite: chiusura", trades)
                    eq = self.equity(book, i)
                book.sat_peak = max(book.sat_peak, book.sat_cum)
                if (book.sat_peak - book.sat_cum) / eq >= self.limits.satellite_max_drawdown_pct:
                    self._flatten_satellite(book, i, date, "drawdown del satellite: stop", trades)
                    eq = self.equity(book, i)
                    book.sat_halt_until, book.sat_peak = i + 21, book.sat_cum
            elif book.prev_equity and eq / book.prev_equity - 1 <= -self.limits.max_daily_loss_pct:
                for s in list(book.positions):
                    self._close(book, s, self.arr[s]["close"][i], date, "perdita giornaliera: chiusura totale", trades)
                eq = self.equity(book, i)
            # 4. Decisioni a chiusura, eseguite domani
            if i < end - 1:
                if not (self.core and i < book.sat_halt_until) and not self.shadow:
                    vetoes += self._decide(book, i, sc, eq)
                if self.core:
                    self._plan_core(book, i, eq)
            gross = sum(abs(p.qty * self.arr[s]["close"][i]) for s, p in book.positions.items())
            if book.core_qty:
                gross += book.core_qty * self.arr[self.core_sym]["close"][i]
            book.gross_hist.append((date, gross / eq if eq else 0.0))
            curve.append((date, eq))
            book.prev_equity = eq
        return book, curve, trades, vetoes

    def _decide(self, book: Book, i: int, sc: dict, equity: float) -> int:
        regime = str(self.regime[i])
        decisions = []
        for s in self.sat_symbols:
            c, a = self.arr[s]["close"][i], self.atr[s][i]
            if not (np.isfinite(c) and np.isfinite(a)):
                continue
            def val(key):
                arr = sc[key].get(s)
                return None if arr is None or not np.isfinite(arr[i]) else float(arr[i])

            pos = book.positions.get(s)
            st = SymbolState(symbol=s, price=float(c), atr=float(a), regime=regime, trend_score=val("trend"),
                             mr_score=val("meanrev"), trend_hold=val("trend_hold"), mr_hold=val("meanrev_hold"),
                             position_qty=pos.qty if pos else 0)
            decisions.append(decide(st, self.weights, self.limits))
        gross = sum(abs(p.qty * self.arr[s]["close"][i]) for s, p in book.positions.items()) / equity
        ctx = GateContext(market_open=True, minutes_since_open=60, equity=equity,
                          last_equity=book.prev_equity or equity, open_positions=len(book.positions),
                          gross_exposure=gross)
        vetoes = 0
        for d in sorted(decisions, key=lambda d: (d.intent != "exit", -d.confidence)):
            if d.intent in ("hold", "skip"):
                continue
            if d.intent == "exit":
                qty = abs(book.positions[d.symbol].qty)
            else:
                qty = position_size(equity, d.price, d.confidence, d.regime, self.limits)
            o = Order(d.symbol, qty, d.action, d.reason, intent=d.intent, stop=d.stop,
                      take_profit=d.take_profit, price=d.price)
            if self.gate.check(o, ctx):          # stesso cancello del bot dal vivo
                vetoes += 1
                continue
            book.pending.append((o, {"regime": d.regime, "strategy": d.strategy, "confidence": d.confidence}))
            if o.is_entry:
                ctx.open_positions += 1
                ctx.gross_exposure += qty * d.price / equity
        return vetoes


# ---------- Statistiche ----------

def stats(curve: pd.Series, exposure: float | None = None) -> dict:
    r = curve.pct_change().dropna()
    years = max(len(r) / 252, 1e-9)
    vol = float(r.std() * np.sqrt(252)) if len(r) > 1 else 0.0
    total = float(curve.iloc[-1] / curve.iloc[0] - 1)
    return {
        "total_return": total, "cagr": float((1 + total) ** (1 / years) - 1), "volatility": vol,
        "sharpe": float(r.mean() * 252 / vol) if vol > 0 else 0.0,
        "max_drawdown": float((curve / curve.cummax() - 1).min()), "exposure": exposure,
    }


def trade_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"count": 0}
    pnl = np.array([t["pnl"] for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    return {
        "count": len(trades), "win_rate": float((pnl > 0).mean()),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
        "avg_pnl": float(pnl.mean()), "avg_holding_days": float(np.mean([t["holding_days"] for t in trades])),
    }


def calibration(trades: list[dict]) -> list[dict]:
    """La confidenza dichiarata corrisponde alla frequenza di successo? (dovrebbe salire con la confidenza)"""
    out = []
    for lo, hi in ((55, 65), (65, 75), (75, 85), (85, 101)):
        b = [t for t in trades if t.get("confidence") is not None and lo <= t["confidence"] < hi]
        out.append({"bucket": f"{lo}-{min(hi, 100)}", "trades": len(b),
                    "win_rate": float(np.mean([t["pnl"] > 0 for t in b])) if b else None})
    return out


def walk_forward(daily: dict[str, pd.DataFrame], limits: RiskLimits, years: int = 2, train: int = 126,
                 test: int = 63, cost_bps: float = 1.0, slippage_bps: float = 5.0,
                 initial: float = 100_000.0, variant: dict | None = None) -> dict:
    bt = Backtester(daily, limits, cost_bps, slippage_bps, variant=variant)
    n = len(bt.idx)
    ready = int(np.argmax(bt.regime != "warming_up"))
    start = max(ready + train, n - years * 252)
    if start >= n - 20:
        raise ValueError("Storico insufficiente: servono circa 200 giorni di riscaldamento + 6 mesi + il periodo di test")

    spy_all = daily["SPY"]["close"].reindex(bt.idx)

    def score(c, a, b):
        """Senza core: Sharpe. Con il core: information ratio (rendimento oltre SPY per unità di rischio)."""
        e = pd.Series([x for _, x in c])
        if not bt.core:
            return stats(e)["sharpe"]
        act = e.pct_change().to_numpy()[1:] - spy_all.iloc[a:b].pct_change().to_numpy()[1:]
        act = act[np.isfinite(act)]
        return float(act.mean() / act.std() * np.sqrt(252)) if len(act) > 2 and act.std() > 0 else 0.0

    book, curve, trades, vetoes, windows = Book(cash=initial), [], [], 0, []
    for w in range(start, n, test):
        end = min(w + test, n)
        best, best_sharpe = DEFAULT_PARAMS, None
        for p in PARAM_GRID:                       # scelta SOLO sui 6 mesi precedenti la finestra
            _, c, _, _ = bt.run(w - train, w, p, initial=initial)
            sh = score(c, w - train, w)
            if best_sharpe is None or sh > best_sharpe + 1e-9 or (p == DEFAULT_PARAMS and sh >= best_sharpe - 1e-9):
                best, best_sharpe = p, sh
        book, c, t, v = bt.run(w, end, best, book=book)
        curve += c
        trades += t
        vetoes += v
        windows.append({"from": str(bt.idx[w].date()), "to": str(bt.idx[end - 1].date()), "params": best,
                        "train_sharpe": round(best_sharpe or 0, 2)})

    eq = pd.Series([e for _, e in curve], index=[d for d, _ in curve])
    spy = daily["SPY"]["close"].reindex(bt.idx)
    spy_curve = spy.iloc[start - 1:] / spy.iloc[start - 1] * initial
    spy_curve = spy_curve.iloc[1:]
    # esposizione media (core compreso), per il confronto con SPY "a parità di rischio"
    avg_exp = float(np.mean([g for _, g in book.gross_hist])) if book.gross_hist else 0.0
    spy_ret = spy_curve.pct_change().fillna(0)
    spy_scaled = (1 + spy_ret * avg_exp).cumprod() * initial

    s_stats, b_stats = stats(eq, avg_exp), stats(spy_curve, 1.0)
    by_strategy = {}
    for name in sorted({t["strategy"] for t in trades}):
        by_strategy[name] = trade_stats([t for t in trades if t["strategy"] == name])
    by_regime = {r: trade_stats([t for t in trades if t["regime"] == r]) for r in sorted({t["regime"] for t in trades})}
    beats = s_stats["total_return"] > b_stats["total_return"]
    act = (eq.pct_change() - spy_curve.reindex(eq.index).pct_change()).dropna()
    te = float(act.std() * np.sqrt(252)) if len(act) > 2 else None
    active = {"return": s_stats["total_return"] - b_stats["total_return"], "tracking_error": te,
              "information_ratio": float(act.mean() * 252 / te) if te else None}
    return {
        "core": {"enabled": bt.core, "symbol": bt.core_sym if bt.core else None,
                 "satellite_symbols": bt.sat_symbols},
        "active": active,
        "period": {"from": str(eq.index[0].date()), "to": str(eq.index[-1].date()), "days": len(eq)},
        "costs": {"commission_bps": cost_bps, "slippage_bps": slippage_bps},
        "strategy": s_stats, "spy": b_stats, "spy_same_exposure": stats(spy_scaled, avg_exp),
        "trades": trade_stats(trades), "by_strategy": by_strategy, "by_regime": by_regime,
        "calibration": calibration(trades), "vetoes": vetoes, "windows": windows,
        "beats_spy": beats,
        "verdict": ("La strategia BATTE SPY buy & hold dopo i costi in questo periodo." if beats else
                    "La strategia NON batte SPY buy & hold dopo i costi in questo periodo."),
        "equity": [(str(d.date()), round(float(v), 2)) for d, v in eq.items()],
        "spy_equity": [(str(d.date()), round(float(v), 2)) for d, v in spy_curve.items()],
        "trade_list": [{**t, "entry_date": str(t["entry_date"].date()), "exit_date": str(t["exit_date"].date())}
                       for t in trades],
    }


def format_report(r: dict) -> str:
    def row(name, s):
        return (f"{name:34s} {s['total_return']:+8.1%} {s['cagr']:+7.1%} {s['volatility']:6.1%} "
                f"{s['sharpe']:6.2f} {s['max_drawdown']:+7.1%} {(s['exposure'] or 0):6.0%}")

    t = r["trades"]
    lines = [
        f"Periodo fuori campione: {r['period']['from']} → {r['period']['to']} ({r['period']['days']} giorni di borsa)",
        f"Costi: commissione {r['costs']['commission_bps']} bps + slippage {r['costs']['slippage_bps']} bps per esecuzione",
        "",
        f"{'':34s} {'Totale':>8s} {'CAGR':>7s} {'Vol':>6s} {'Sharpe':>6s} {'MaxDD':>7s} {'Espos.':>6s}",
        row("PULSE core+satellite" if r.get("core", {}).get("enabled") else "PULSE (riflesso, senza comitato)",
            r["strategy"]),
        row("SPY buy & hold", r["spy"]),
        row("SPY alla stessa esposizione media", r["spy_same_exposure"]),
        "",
        f"Trade: {t.get('count', 0)}" + (f" | vincenti {t['win_rate']:.0%} | profit factor "
                                          f"{t['profit_factor'] or 0:.2f} | durata media {t['avg_holding_days']:.1f} giorni"
                                          if t.get("count") else ""),
        f"Ordini bloccati dal risk layer: {r['vetoes']}",
        (f"Rendimento attivo vs SPY: {r['active']['return']:+.1%} · tracking error {r['active']['tracking_error'] or 0:.1%}"
         f" · information ratio {r['active']['information_ratio'] or 0:.2f}") if r.get("active") else "",
        "",
        "Per strategia: " + "; ".join(f"{k} {v['count']} trade, vincenti {v['win_rate']:.0%}, PF "
                                       f"{(v['profit_factor'] or 0):.2f}" for k, v in r["by_strategy"].items() if v["count"]),
        "Calibrazione (confidenza → % vincenti): " + ", ".join(
            f"{c['bucket']}: {c['win_rate']:.0%} su {c['trades']}" if c["win_rate"] is not None else f"{c['bucket']}: —"
            for c in r["calibration"]),
        "",
        "VERDETTO: " + r["verdict"],
    ]
    return "\n".join(lines)
