"""Motore PULSE.

Ogni minuto (tick):   kill switch, uscite dei bracket, perdita giornaliera, drawdown, trailing stop.
Ogni 15 minuti:       il RIFLESSO valuta ogni titolo e decide compra / vendi / resta.
Ogni 30 minuti:       il COMITATO AI si riunisce e aggiorna il suo voto (che il riflesso fonde con le strategie).
Ogni ordine passa da RiskGate.check(): questo file è l'unico che parla col broker.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from . import shadow_universe
from .broker import NY, Broker, Position, SimBroker
from .config import Settings
from .data import MarketData
from .indicators import snapshot
from .journal import Journal
from .reflex import Decision, SymbolState, clamp_weights, committee_score, decide, position_size
from .risk import STOP_LOSS, TRAILING, GateContext, Order, RiskGate, RiskManager
from .strategies import MeanReversion, TrendFollowing, detect_regime
from .strategies.base import atr as atr_series

log = logging.getLogger("desk.engine")

REFLECT_AFTER_TRADES = 3
VERDICT = {"enter_long": "BUY", "enter_short": "SELL", "exit": "EXIT", "hold": "HOLD", "skip": "SKIP"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Engine:
    def __init__(self, settings: Settings, broker: Broker, data: MarketData, committee, journal: Journal,
                 notifier=None, clock=utcnow, free=None):
        self.s = settings
        self.broker = broker
        self.data = data
        self.free = free          # freedata.FreeData: macro, calendario, fondamentali, notizie gratuite
        self.committee = committee
        self.j = journal
        self.notify = notifier.send if notifier else (lambda text: None)
        self.now = clock
        self.risk = RiskManager(settings.risk)
        self.gate = RiskGate(settings.risk)
        self.strategies = [TrendFollowing(), MeanReversion()]
        self.atr: dict[str, float] = journal.get("atr", {})
        self.last_committee: datetime | None = None
        self.last_reflex: datetime | None = None
        self.committee_prices: dict[str, float] = {}
        self._daily: tuple[str, dict] | None = None
        self.universe = list(dict.fromkeys(settings.symbols + ["SPY"]))   # SPY serve sempre per il regime
        # Satellite in OMBRA (decisione del test 2005-2019): decide e opera su un broker virtuale persistente,
        # i suoi trade finiscono nel diario come "SHADOW". Sono la prova in avanti per riattivarlo.
        self.shadow = settings.risk.core_enabled and settings.risk.satellite_mode == "shadow"
        self.sat = self._load_shadow() if self.shadow else broker
        self.core_signal: bool | None = journal.get("core_signal")
        # Universo dell'ombra definito da una regola (desk/shadow_universe.py): top 100 per volume, ogni mese
        self.shadow_rule = self.shadow and shadow_universe.enabled()
        self._set_universe((journal.get("shadow_universe") or {}).get("symbols", []))

    def _set_universe(self, shadow_symbols: list[str]) -> None:
        self.shadow_symbols = list(shadow_symbols) if self.shadow_rule else []
        new = list(dict.fromkeys(self.s.symbols + ["SPY"] + self.shadow_symbols))
        if new != getattr(self, "universe", None):
            self.universe = new
            self._daily = None                       # nuove barre giornaliere al prossimo giro

    def _sat_symbols(self) -> list[str]:
        """Titoli che il satellite valuta: la regola (+ QQQ, IWM) se attiva, sempre anche quelli già in posizione."""
        if not (self.shadow_rule and self.shadow_symbols):
            return self.s.satellite_symbols
        held = [s for s in self.sat.positions() if not self._is_core(s)]
        return list(dict.fromkeys(shadow_universe.ALWAYS + self.shadow_symbols + held))

    # ---------- Satellite in ombra: broker virtuale salvato nel diario ----------

    def _load_shadow(self) -> SimBroker:
        # Cassa iniziale 0: il libro virtuale misura solo il P&L del satellite. Con posizioni aperte la cassa
        # è negativa (ne vale il costo) ed equity = cassa + valore posizioni = P&L. Le taglie usano l'equity vera.
        b = SimBroker(cash=0.0)
        st = self.j.get("shadow_book")
        if st:
            b.cash = st["cash"]
            b.prices = st["prices"]
            b.brackets = {k: tuple(v) for k, v in st["brackets"].items()}
            b._pos = {k: Position(**v) for k, v in st["positions"].items()}
        b.minutes_open = None
        return b

    def _save_shadow(self) -> None:
        if self.shadow:
            b = self.sat
            self.j.set("shadow_book", {"cash": b.cash, "prices": b.prices, "brackets": b.brackets,
                                       "positions": {k: vars(v) for k, v in b._pos.items()}})
            self.j.set("shadow_positions", [vars(p) for p in b.positions().values()])

    def _shadow_prices(self, prices: dict[str, float]) -> None:
        if self.shadow:
            for sym, px in prices.items():
                self.sat.set_price(sym, px)          # fa scattare anche stop e target del bracket virtuale

    @property
    def sat_label(self) -> str:
        return "SHADOW" if self.shadow else self.s.mode

    # ---------- Stato persistente ----------

    @property
    def halted(self) -> bool:
        return bool(self.j.get("halted", False))

    def _session_day(self) -> str:
        return self.now().astimezone(NY).date().isoformat()

    def session_paused(self) -> bool:
        return self.j.get("paused_session") == self._session_day()

    def _cooldowns(self) -> set[str]:
        now = self.now()
        return {s for s, until in self.j.get("cooldowns", {}).items() if datetime.fromisoformat(until) > now}

    def _entries_paused(self) -> bool:
        until = self.j.get("entries_paused_until")
        return bool(until) and datetime.fromisoformat(until) > self.now()

    def _is_core(self, symbol: str) -> bool:
        return self.s.risk.core_enabled and symbol == self.s.risk.core_symbol

    def _flatten(self, reason: str, include_core: bool = True) -> None:
        sat = self.sat.positions()
        for s, p in sat.items():
            if not self._is_core(s):
                self._record_close(s, abs(p.qty), p.market_price, f"chiusura totale: {reason}", p)
        if self.shadow:
            self.sat.close_all()
        if include_core or not self.s.risk.core_enabled:
            self.broker.close_all()          # cancella anche tutti gli ordini aperti (bracket compresi)
        elif not self.shadow:                # solo il satellite: il core resta investito
            for s in sat:
                if not self._is_core(s):
                    self.broker.close_position(s)
        self.j.set("peaks", {})
        self._save_shadow()

    def halt(self, reason: str) -> None:
        """Kill switch: cancella tutto, chiude tutto, si ferma finché non lo riattivi a mano."""
        log.error("KILL SWITCH: %s", reason)
        self._flatten(reason)
        self.j.set("halted", True)
        self.j.event("halt", {"reason": reason})
        self.notify(f"🛑 KILL SWITCH: {reason}. Ordini cancellati, posizioni chiuse.")

    def pause_session(self, reason: str) -> None:
        """Perdita giornaliera oltre il limite: chiude il satellite e riparte da solo alla prossima sessione.
        Con il core attivo il core NON viene venduto: un normale -2% di SPY non deve liquidare l'indice."""
        log.error("PAUSA DI SESSIONE: %s", reason)
        self._flatten(reason, include_core=False)
        self.j.set("paused_session", self._session_day())
        self.j.event("session_pause", {"reason": reason, "session": self._session_day()})
        self.notify(f"⏸️ {reason}. Posizioni chiuse, riprendo alla prossima sessione.")

    def satellite_pnl(self, positions: dict[str, Position] | None = None) -> float:
        """Realizzato + non realizzato dei soli trade del satellite (il core è escluso)."""
        positions = self.sat.positions() if positions is None else positions
        realized = self.j.db_query("SELECT COALESCE(SUM(pnl), 0) FROM closed_trades WHERE mode=?", (self.sat_label,))[0][0]
        return realized + sum(p.unrealized_pl for s, p in positions.items() if not self._is_core(s))

    def satellite_halted(self) -> bool:
        return bool(self.j.get("satellite_halted", False))

    # ---------- Diario dei trade ----------

    def _record_close(self, symbol: str, qty: float, exit_price: float, reason: str, p: Position | None) -> None:
        if p is None or p.qty == 0:
            return
        entries = self.j.get("entries", {})
        meta = entries.get(symbol, {})
        d = 1 if p.qty > 0 else -1
        qty = min(qty, abs(p.qty))
        held = None
        if meta.get("ts"):
            held = round((self.now() - datetime.fromisoformat(meta["ts"])).total_seconds() / 60, 1)
        self.j.closed_trade(self.sat_label, {
            "symbol": symbol, "direction": "long" if d > 0 else "short", "qty": qty,
            "entry": p.avg_price, "exit": exit_price,
            "pnl": round((exit_price - p.avg_price) * qty * d, 2),
            "pnl_pct": round((exit_price / p.avg_price - 1) * d, 4),
            "reason": reason, "thesis": meta.get("reason", ""), "regime": meta.get("regime"),
            "strategy": meta.get("strategy"), "confidence": meta.get("confidence"),
            "entry_ts": meta.get("ts"), "holding_minutes": held,
        })
        if qty >= abs(p.qty):
            entries.pop(symbol, None)
            self.j.set("entries", entries)

    def _after_stop(self, symbol: str, reason: str) -> None:
        """Protezioni stile freqtrade: CooldownPeriod sul titolo e StoplossGuard sul conto."""
        r = self.s.risk
        now = self.now()
        cds = self.j.get("cooldowns", {})
        cds[symbol] = (now + timedelta(minutes=r.cooldown_minutes)).isoformat()
        self.j.set("cooldowns", cds)
        if reason.startswith(STOP_LOSS):
            window = now - timedelta(hours=r.stoploss_guard_hours)
            stops = [t for t in self.j.get("stop_times", []) if datetime.fromisoformat(t) > window]
            stops.append(now.isoformat())
            self.j.set("stop_times", stops)
            if len(stops) >= r.stoploss_guard_count:
                until = now + timedelta(hours=r.stoploss_guard_pause_hours)
                self.j.set("entries_paused_until", until.isoformat())
                self.j.event("stoploss_guard", {"stops": len(stops), "until": until})
                self.notify(f"⚠️ StoplossGuard: {len(stops)} stop in {r.stoploss_guard_hours}h. "
                            f"Nuove entrate bloccate fino alle {until:%H:%M} UTC.")

    def _handle_fills(self, before: dict[str, Position]) -> None:
        """Stop e take profit scattati sul broker (gambe del bracket) dall'ultimo controllo."""
        fills = self.broker.take_fills() + (self.sat.take_fills() if self.shadow else [])
        for f in fills:
            p = before.get(f.symbol)
            meta = self.j.get("entries", {}).get(f.symbol)
            if (p is None or p.qty == 0) and meta and meta.get("price"):
                # la posizione è già chiusa sul broker: ricostruita dai dati salvati all'entrata
                p = Position(f.symbol, f.qty if f.side == "sell" else -f.qty, meta["price"], f.price)
            self._record_close(f.symbol, f.qty, f.price, f.reason, p)
            self.j.order(self.sat_label, f.symbol, f.side, f.qty, f.reason, "", "filled")
            self.j.event("fill", {"symbol": f.symbol, "price": f.price, "reason": f.reason})
            self.notify(f"🎯 {f.symbol}: {f.reason} a {f.price:.2f}")
            if f.reason.startswith(STOP_LOSS):
                self._after_stop(f.symbol, f.reason)

    def maybe_reflect(self, force: bool = False) -> None:
        trades = self.j.unreflected_trades()
        if not trades or not hasattr(self.committee, "reflect") or self.committee is None:
            return
        if len(trades) < REFLECT_AFTER_TRADES and not force:
            return
        lessons = self.committee.reflect(trades, self.j.get("lessons", []))
        self.j.set("lessons", lessons)
        self.j.mark_reflected([t["rowid"] for t in trades])
        self.j.event("reflection", {"trades": len(trades), "lessons": lessons})

    # ---------- Esecuzione: l'unico punto che parla col broker ----------

    def _gate_context(self, broker=None) -> GateContext:
        acc = self.broker.account()                  # l'equity è sempre quella del conto vero
        pos = (broker or self.broker).positions()
        return GateContext(
            market_open=self.broker.market_open(), minutes_since_open=self.broker.minutes_since_open(),
            equity=acc.equity, last_equity=acc.last_equity,
            gross_exposure=sum(abs(p.market_value) for p in pos.values()) / acc.equity if acc.equity else 0,
            open_positions=len([x for x in pos if not self._is_core(x)]),
            halted=self.halted, session_paused=self.session_paused() or self.satellite_halted(),
            entries_paused=self._entries_paused(),
            cooldowns=self._cooldowns(),
            trades_today=self.j.db_query("SELECT COUNT(*) FROM orders WHERE ts >= ? AND status=?",
                                         (self.now().date().isoformat(),
                                          "shadow" if broker is not None and broker is not self.broker else "submitted"))[0][0],
        )

    def _execute(self, orders: list[Order], decisions: dict[str, Decision] | None = None, broker=None) -> None:
        if not orders:
            return
        broker = broker or self.broker
        virtual = broker is not self.broker
        ctx = self._gate_context(broker)
        positions = broker.positions()
        for o in orders:
            veto = self.gate.check(o, ctx)
            d = (decisions or {}).get(o.symbol)
            if veto:
                log.info("VETO %s %s: %s", o.side, o.symbol, veto)
                self.j.order(self.s.mode, o.symbol, o.side, o.qty, f"{o.reason} | veto: {veto}", "", "vetoed")
                if d:
                    self.j.decision(d.to_dict(), "VETO", veto)
                continue
            try:
                if o.is_entry:
                    oid = broker.submit_bracket(o.symbol, o.qty, o.side, o.stop, o.take_profit)
                elif o.intent == "core":
                    oid = broker.submit(o.symbol, o.qty, o.side)
                else:
                    p = positions.get(o.symbol)
                    if p and o.qty >= abs(p.qty):
                        broker.close_position(o.symbol)   # cancella prima le gambe del bracket
                        oid = "close"
                    else:
                        oid = broker.submit(o.symbol, o.qty, o.side)
            except Exception as e:  # un ordine rifiutato non deve fermare gli altri
                log.exception("Ordine rifiutato %s %s", o.side, o.symbol)
                self.j.order(self.sat_label if virtual else self.s.mode, o.symbol, o.side, o.qty,
                             f"{o.reason} | errore: {e}", "", "rejected")
                continue
            log.info("ORDINE %s %s x%d — %s", o.side.upper(), o.symbol, o.qty, o.reason)
            self.j.order(self.sat_label if virtual else self.s.mode, o.symbol, o.side, o.qty, o.reason, oid,
                         "shadow" if virtual else "submitted")
            if d:
                self.j.decision(d.to_dict(), VERDICT[d.intent])
            if not virtual:
                self.notify(f"{'🟢' if o.side == 'buy' else '🔴'} {o.side.upper()} {o.symbol} x{o.qty} — {o.reason}")
            if o.is_entry:
                entries = self.j.get("entries", {})
                entries[o.symbol] = {"ts": self.now().isoformat(), "regime": d.regime if d else None,
                                     "strategy": d.strategy if d else None, "confidence": d.confidence if d else None,
                                     "reason": o.reason, "stop": o.stop, "take_profit": o.take_profit,
                                     "price": o.price}
                self.j.set("entries", entries)
                ctx.open_positions += 1
                ctx.gross_exposure += o.qty * (o.price or 0) / ctx.equity
                ctx.trades_today += 1
            elif o.intent == "core":
                ctx.gross_exposure += o.qty * (o.price or 0) / ctx.equity * (1 if o.side == "buy" else -1)
            else:
                p = positions.get(o.symbol)
                self._record_close(o.symbol, o.qty, p.market_price if p else (o.price or 0), o.reason, p)
                positions.pop(o.symbol, None)
                ctx.open_positions = max(0, ctx.open_positions - 1)
                if o.protective and o.reason.startswith((STOP_LOSS, TRAILING)):
                    self._after_stop(o.symbol, o.reason)

    # ---------- Ciclo ----------

    def tick(self) -> None:
        if self.j.get("kill_requested"):
            self.j.set("kill_requested", False)
            self.halt("kill switch dalla dashboard o da Telegram")
            return
        if self.halted:
            log.info("Bot fermo (kill switch). Usa la dashboard o `python main.py resume`.")
            return
        before = {**self.broker.positions(), **(self.sat.positions() if self.shadow else {})}
        if self.shadow and self.broker.market_open():
            self._shadow_prices(self.data.latest_prices(self.universe))
        self._handle_fills(before)
        if not self.broker.market_open():
            log.info("Mercato chiuso.")
            return

        prices = self.data.latest_prices(self.universe)
        acc = self.broker.account()
        self.j.equity(self.s.mode, acc.equity, acc.cash, prices.get("SPY"))
        if self.shadow:                            # P&L cumulato dell'ombra (cassa iniziale 0): serve al report in avanti
            sa = self.sat.account()
            self.j.equity("SHADOW", sa.equity, sa.cash, prices.get("SPY"))
        peak_equity = max(self.j.get("equity_peak", acc.equity), acc.equity)
        self.j.set("equity_peak", peak_equity)
        if self.s.risk.core_enabled:
            if self._satellite_risk(acc):
                return
        else:
            if self.risk.drawdown_breached(acc.equity, peak_equity):
                self.halt(f"drawdown oltre il {self.s.risk.max_drawdown_pct:.0%} dal massimo")
                return
            if not self.session_paused() and self.risk.daily_loss_breached(acc):
                self.pause_session(f"perdita giornaliera oltre il {self.s.risk.max_daily_loss_pct:.0%}")
                return

        # stop e trailing lato client valgono solo per il satellite: il core non ha stop per costruzione
        positions = {k: p for k, p in self.sat.positions().items() if not self._is_core(k)}
        peaks = self.risk.update_peaks(positions, self.j.get("peaks", {}))
        self.j.set("peaks", peaks)
        self._execute(self.risk.stop_orders(positions, self.atr, peaks), broker=self.sat)

        if self.committee is not None and self.s.use_committee and self._committee_due(prices):
            self.run_committee(prices)
        if self._reflex_due():
            self.run_reflex(prices)
        self.j.set("positions", [vars(p) for p in self.broker.positions().values()])
        self._save_shadow()

    def _satellite_risk(self, acc) -> bool:
        """Perdita giornaliera e drawdown misurati sul P&L del satellite, in % dell'equity."""
        r, day = self.s.risk, self._session_day()
        pnl = self.satellite_pnl()
        start = self.j.get("satellite_session")
        if not start or start.get("day") != day:
            start = {"day": day, "pnl": pnl}
            self.j.set("satellite_session", start)
        base = acc.last_equity or acc.equity
        if not self.session_paused() and (pnl - start["pnl"]) / base <= -r.max_daily_loss_pct:
            self.pause_session(f"perdita giornaliera del satellite oltre il {r.max_daily_loss_pct:.0%}")
            return True
        peak = max(self.j.get("satellite_peak", pnl), pnl)
        self.j.set("satellite_peak", peak)
        if not self.satellite_halted() and (peak - pnl) / acc.equity >= r.satellite_max_drawdown_pct:
            log.error("SATELLITE FERMO: drawdown del satellite oltre il %.0f%%", r.satellite_max_drawdown_pct * 100)
            self._flatten("drawdown del satellite", include_core=False)
            self.j.set("satellite_halted", True)
            self.j.event("satellite_halt", {"pnl": pnl, "peak": peak})
            self.notify("⛔ Satellite fermo per drawdown: il core resta investito. Riattiva con `python main.py resume`.")
            return True
        return False

    def _core_orders(self, planned_satellite_value: float, side: str) -> list[Order]:
        """Il core prende tutto ciò che il satellite non usa, meno la riserva di liquidità."""
        r = self.s.risk
        if not r.core_enabled or self.halted:
            return []
        acc = self.broker.account()
        pos = self.broker.positions()
        core = pos.get(r.core_symbol)
        px = self.data.latest_prices([r.core_symbol]).get(r.core_symbol) or (core.market_price if core else None)
        if not px or acc.equity <= 0:
            return []
        target = acc.equity * (1 - r.core_cash_buffer_pct) - planned_satellite_value
        if r.core_trend_filter and self.core_signal is False:
            target = 0.0                     # SPY sotto la MA200 a fine mese: il core sta in liquidità
        current = core.market_value if core else 0.0
        diff = target - current
        if abs(diff) / acc.equity < r.core_rebalance_band_pct:
            return []
        if side == "sell" and diff < 0:
            qty = min(int(-diff / px) + 1, int(core.qty) if core else 0)
            return [Order(r.core_symbol, qty, "sell", f"core: libero liquidità per il satellite ({-diff:,.0f} $)",
                          intent="core", price=px)] if qty > 0 else []
        if side == "buy" and diff > 0:
            qty = int(diff / px)
            return [Order(r.core_symbol, qty, "buy", f"core: reinvesto la liquidità non usata ({diff:,.0f} $)",
                          intent="core", price=px)] if qty > 0 else []
        return []

    def _reflex_due(self) -> bool:
        return self.last_reflex is None or self.now() - self.last_reflex >= timedelta(minutes=self.s.reflex_minutes)

    def _committee_due(self, prices: dict[str, float]) -> bool:
        if self.last_committee is None:
            return True
        if self.now() - self.last_committee >= timedelta(minutes=self.s.committee_minutes):
            return True
        for s, p in prices.items():
            ref = self.committee_prices.get(s)
            if ref and abs(p / ref - 1) >= self.s.trigger_move_pct:
                log.info("%s si è mosso del %+.1f%%: convoco il comitato in anticipo", s, (p / ref - 1) * 100)
                return True
        return False

    # ---------- Dati ----------

    def daily_bars(self, prices: dict[str, float] | None = None) -> dict[str, pd.DataFrame]:
        """Barre giornaliere (scaricate una volta al giorno) con l'ultima barra aggiornata al prezzo attuale."""
        day = self._session_day()
        if not self._daily or self._daily[0] != day:
            self._daily = (day, self.data.daily_bars(self.universe, days=320))
        out = {}
        for s, df in self._daily[1].items():
            df = df.copy()
            px = (prices or {}).get(s)
            if px and len(df):
                i = df.index[-1]
                df.loc[i, "close"] = px
                df.loc[i, "high"] = max(df.loc[i, "high"], px)
                df.loc[i, "low"] = min(df.loc[i, "low"], px)
            out[s] = df
        return out

    # ---------- Il riflesso ----------

    def run_reflex(self, prices: dict[str, float] | None = None) -> list[Decision]:
        self.last_reflex = self.now()
        if self.shadow_rule:
            fresh = shadow_universe.refresh(self.j, self.data, self.now(), self.s.risk.core_symbol)
            if fresh is not None:
                self._set_universe(fresh)
        prices = prices or self.data.latest_prices(self.universe)
        daily = self.daily_bars(prices)
        if "SPY" not in daily:
            log.warning("Senza SPY non posso stimare il regime: il riflesso salta questo giro.")
            return []
        regime = detect_regime(daily["SPY"])
        weights = clamp_weights(self.j.get("weights"))
        stances = self.j.get("committee_stances", {}) if self.s.use_committee else {}
        self._shadow_prices(prices)
        self._update_core_signal(daily)
        positions = self.sat.positions()
        frames = {st.name: {s: st.frame(df) for s, df in daily.items() if st.applies_to(s) and len(df) > 60}
                  for st in self.strategies}
        self.atr = {s: float(atr_series(df).iloc[-1]) for s, df in daily.items() if len(df) > 15}
        self.j.set("atr", self.atr)

        decisions: list[Decision] = []
        raw: list[tuple] = []
        for s in self._sat_symbols():
            if s not in daily or s not in self.atr:
                continue
            tr = frames["trend"].get(s)
            mr = frames["meanrev"].get(s)
            st = stances.get(s)

            def last(f, col):
                if f is None or col not in f or pd.isna(f[col].iloc[-1]):
                    return None
                return float(f[col].iloc[-1])

            state = SymbolState(
                symbol=s, price=float(prices.get(s, daily[s]["close"].iloc[-1])), atr=self.atr[s],
                regime=regime.name,
                trend_score=last(tr, "score"), trend_hold=last(tr, "hold"),
                trend_reason=self.strategies[0].explain(tr.iloc[-1]) if tr is not None else "",
                mr_score=last(mr, "score"), mr_hold=last(mr, "hold"),
                mr_reason=self.strategies[1].explain(mr.iloc[-1]) if mr is not None else "",
                committee_score=st["score"] if st else None, committee_reason=st["reason"] if st else "",
                position_qty=positions[s].qty if s in positions else 0.0,
            )
            decisions.append(decide(state, weights, self.s.risk))
            raw.append((s, state.price, state.trend_score, state.mr_score))
        self.j.signals(raw)                       # punteggi NON pesati, per la regressione sul comitato

        acc = self.broker.account()
        orders, by_symbol = [], {}
        # Prima le uscite, poi le entrate dalla più convinta: i posti liberi vanno ai segnali migliori
        for d in sorted(decisions, key=lambda d: (d.intent != "exit", -d.confidence)):
            if d.intent in ("hold", "skip"):
                self.j.decision(d.to_dict(), VERDICT[d.intent])
                continue
            by_symbol[d.symbol] = d
            if d.intent == "exit":
                qty = int(abs(positions[d.symbol].qty))
            else:
                qty = position_size(acc.equity, d.price, d.confidence, d.regime, self.s.risk)
            orders.append(Order(d.symbol, qty, d.action, d.reason, intent=d.intent,
                                stop=d.stop, take_profit=d.take_profit, price=d.price))
        if self.s.risk.core_enabled:
            # valore del satellite VERO dopo gli ordini previsti: prima si vende il core se serve liquidità
            sat_now = 0.0 if self.shadow else sum(abs(p.market_value) for x, p in positions.items() if not self._is_core(x))
            planned = sat_now if self.shadow else sat_now + sum(
                o.qty * (o.price or 0) * (1 if o.is_entry else -1) for o in orders)
            self._execute(self._core_orders(max(planned, 0), "sell"))
        self._execute(orders, by_symbol, broker=self.sat)
        if self.s.risk.core_enabled:
            now = self.broker.positions()
            self._execute(self._core_orders(
                sum(abs(p.market_value) for x, p in now.items() if not self._is_core(x)), "buy"))
        self._save_shadow()
        self._save_observables(daily, regime, frames)
        return decisions

    def _update_core_signal(self, daily: dict[str, pd.DataFrame]) -> None:
        """Filtro a 200 giorni: SPY sopra la sua media a 200 giorni all'ultima chiusura del mese PRECEDENTE."""
        r = self.s.risk
        df = daily.get(r.core_symbol)
        if not (r.core_enabled and r.core_trend_filter) or df is None or len(df) < 210:
            return
        c = df["close"]
        sma = c.rolling(200).mean()
        this_month = pd.Timestamp(self.now().astimezone(NY).date()).to_period("M")
        past = c[c.index.to_period("M") < this_month]
        if past.empty:
            return
        month_end = past.groupby(past.index.to_period("M")).tail(1).index[-1]
        signal = bool(c[month_end] > sma[month_end])
        if signal != self.core_signal:
            self.j.event("core_filter", {"signal": signal, "month_end": str(month_end.date()),
                                         "close": float(c[month_end]), "sma200": float(sma[month_end])})
            self.notify(f"{'📈' if signal else '📉'} Filtro 200 giorni: core {'in SPY' if signal else 'in liquidità'}")
        self.core_signal = signal
        self.j.set("core_signal", signal)

    def _save_observables(self, daily, regime, frames) -> None:
        trend = frames.get("trend", {})
        above = [float(f["spread_pct"].iloc[-1]) > 0 for f in trend.values()]
        vol_ratio = [float(df["volume"].iloc[-1] / df["volume"].tail(20).mean())
                     for df in daily.values() if len(df) > 20 and df["volume"].tail(20).mean() > 0]
        mom = [float(df["close"].iloc[-1] / df["close"].iloc[-64] - 1) for df in daily.values() if len(df) > 64]
        self.j.observables({
            "regime": regime.name, "regime_reason": regime.reason,
            "volatility": regime.vol20, "atr_pct": regime.atr_pct, "dist_sma200": regime.dist_sma200,
            "breadth": float(np.mean(above)) if above else None,
            "volume": float(np.mean(vol_ratio)) if vol_ratio else None,
            "momentum": float(np.mean(mom)) if mom else None,
        })
        # Per la dashboard (che legge solo il diario): correlazioni a 60 giorni e barre dei titoli in gioco
        rets = pd.DataFrame({s: df["close"].pct_change() for s, df in daily.items() if s in self.s.symbols}).tail(60)
        corr = rets.corr().round(2)
        self.j.set("correlations", {"symbols": list(corr.columns),
                                    "matrix": corr.fillna(0).values.tolist()})
        focus = set(self.broker.positions()) | set(self.sat.positions()) | set(self.j.get("entries", {}))
        self.j.set("charts", {s: [[str(i.date()), round(float(r.open), 2), round(float(r.high), 2),
                                   round(float(r.low), 2), round(float(r.close), 2)]
                                  for i, r in daily[s].tail(90).iterrows()]
                              for s in focus if s in daily})

    # ---------- Il comitato AI: vota, non ordina ----------

    def run_committee(self, prices: dict[str, float] | None = None) -> None:
        self.maybe_reflect()
        syms = self.s.symbols
        prices = prices or self.data.latest_prices(self.universe)
        daily = self.daily_bars(prices)
        intraday = self.data.intraday_bars(syms)
        snaps = {s: snapshot(daily[s], intraday.get(s)) for s in syms if s in daily and len(daily[s]) > 30}
        acc = self.broker.account()
        positions = self.broker.positions()
        portfolio = {
            "equity": round(acc.equity, 2), "cash": round(acc.cash, 2),
            "pl_oggi_pct": round(acc.equity / acc.last_equity - 1, 4) if acc.last_equity else 0,
            "posizioni": {s: {"qty": p.qty, "prezzo_carico": p.avg_price,
                              "peso": round(p.market_value / acc.equity, 4),
                              "pl_non_realizzato": round(p.unrealized_pl, 2)} for s, p in positions.items()},
            "titoli_in_cooldown": sorted(self._cooldowns()),
            "nuove_entrate_bloccate": self._entries_paused(),
            "nota": "Il tuo peso target diventa un VOTO che il riflesso fonde con le strategie; "
                    f"limite {self.s.risk.max_position_pct:.0%} per titolo, massimo {self.s.risk.max_open_positions} posizioni.",
        }
        try:
            news = self.data.news(syms, self.now() - timedelta(hours=24))
        except Exception as e:
            log.warning("Notizie Alpaca non disponibili: %s", e)
            news = []
        context: dict = {}
        if self.free:
            from .freedata import dedupe

            context = self.free.briefing(syms)
            news = dedupe([news, context.pop("notizie", [])])
        lessons = self.j.get("lessons", [])

        log.info("Comitato riunito su %d titoli, %d notizie, %d lezioni", len(snaps), len(news), len(lessons))
        result = self.committee.run(snaps, news, portfolio, self.s.risk, lessons=lessons, context=context)
        self.last_committee = self.now()
        self.committee_prices = dict(prices)

        stances = {}
        if result.decision:
            for t in result.decision.targets:
                # voto grezzo, anche sotto la soglia: convinzione con segno = direzione × confidenza
                direction = max(-1.0, min(1.0, t.target_weight / self.s.risk.max_position_pct))
                self.j.vote(t.symbol.upper(), t.target_weight, t.confidence, round(direction * t.confidence, 4),
                            prices.get(t.symbol.upper()), self.s.model)
                sc = committee_score(t.target_weight, t.confidence, self.s.risk)
                if sc is not None:
                    stances[t.symbol.upper()] = {"score": round(sc, 1), "reason": f"comitato: {t.thesis}",
                                                 "confidence": t.confidence, "ts": self.now().isoformat()}
            self.notify(f"🧠 Comitato: {result.decision.market_view[:300]}")
        self.j.set("committee_stances", stances)
        self.j.event("committee", {
            "reports": result.reports,
            "decision": result.decision.model_dump() if result.decision else None,
            "snapshots": snaps, "context": context, "stances": stances,
            "headlines": [{"t": n.created_at, "s": n.symbols, "h": n.headline, "src": n.source} for n in news[:25]],
        })
        self.last_reflex = None   # il riflesso rivaluta subito col voto nuovo

    def run_forever(self) -> None:
        log.info("Avvio in modalità %s su %s", self.s.mode, ", ".join(self.s.symbols))
        self.notify(f"▶️ PULSE avviato ({self.s.mode}) su {', '.join(self.s.symbols)}")
        while True:
            started = time.monotonic()
            try:
                self.tick()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.exception("Errore nel ciclo: continuo al prossimo tick")
                self.notify(f"❗ Errore nel ciclo: {e}")
            time.sleep(max(1.0, self.s.tick_seconds - (time.monotonic() - started)))
