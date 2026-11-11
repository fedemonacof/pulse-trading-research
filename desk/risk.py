"""Risk layer deterministico. L'ultima parola è sempre di questo file, non del comitato né del riflesso.

Ogni ordine passa da RiskGate.check() prima di arrivare al broker: non esiste un'altra strada
(engine._execute è l'unico punto che chiama broker.submit*).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .broker import Account, Position
from .config import RiskLimits

STOP_LOSS = "stop loss"
TRAILING = "trailing stop"
TAKE_PROFIT = "take profit"
PROTECTIVE_EXITS = (STOP_LOSS, TRAILING, TAKE_PROFIT)


@dataclass
class Order:
    symbol: str
    qty: int
    side: str                    # "buy" | "sell"
    reason: str
    intent: str = "exit"         # "enter_long" | "enter_short" | "exit"
    stop: float | None = None    # bracket: obbligatori sulle entrate
    take_profit: float | None = None
    price: float | None = None   # prezzo di riferimento per il controllo della dimensione

    @property
    def protective(self) -> bool:
        return self.reason.startswith(PROTECTIVE_EXITS)

    @property
    def is_entry(self) -> bool:
        return self.intent.startswith("enter")


@dataclass
class GateContext:
    market_open: bool
    minutes_since_open: float | None
    equity: float
    last_equity: float
    open_positions: int
    gross_exposure: float = 0.0              # valore assoluto delle posizioni / equity
    halted: bool = False
    session_paused: bool = False
    entries_paused: bool = False             # StoplossGuard
    cooldowns: set[str] = field(default_factory=set)
    trades_today: int = 0


class RiskGate:
    """Le regole PULSE, in ordine. Restituisce None se l'ordine passa, altrimenti il motivo del veto."""

    def __init__(self, limits: RiskLimits):
        self.l = limits

    def check(self, o: Order, c: GateContext) -> str | None:
        l = self.l
        if c.halted:
            return "kill switch attivo: bot fermo"
        if not c.market_open:
            return "mercato chiuso: si opera solo in orario regolare"
        if c.minutes_since_open is not None and c.minutes_since_open < l.no_trade_first_minutes:
            return f"primi {l.no_trade_first_minutes} minuti di sessione: niente operazioni"
        if o.qty <= 0:
            return "dimensione zero"
        if o.intent == "core":
            # Il core (un ETF indice tenuto a lungo) non ha i limiti per singola posizione del satellite,
            # ma non può mai portare l'esposizione totale oltre il limite (niente leva).
            if o.side == "buy" and o.price and c.equity > 0 and \
                    c.gross_exposure + o.qty * o.price / c.equity > l.max_gross_exposure_pct:
                return "il core porterebbe l'esposizione totale oltre il limite"
            return None
        if not o.is_entry:
            return None                               # le uscite riducono il rischio: passano
        if c.session_paused:
            return "perdita giornaliera oltre il limite: pausa fino alla prossima sessione"
        if c.last_equity > 0 and c.equity / c.last_equity - 1 <= -l.max_daily_loss_pct:
            return f"perdita giornaliera oltre il {l.max_daily_loss_pct:.0%}"
        if c.open_positions >= l.max_open_positions:
            return f"già {c.open_positions} posizioni aperte (massimo {l.max_open_positions})"
        if o.stop is None or o.take_profit is None:
            return "ordine senza bracket (stop loss e take profit obbligatori)"
        if o.price:
            if o.qty * o.price > c.equity * l.max_position_pct * 1.001:
                return f"posizione oltre il {l.max_position_pct:.0%} dell'equity"
            bad = (o.side == "buy" and not (o.stop < o.price < o.take_profit)) or \
                  (o.side == "sell" and not (o.take_profit < o.price < o.stop))
            if bad:
                return "stop e take profit dalla parte sbagliata del prezzo"
            if c.gross_exposure + o.qty * o.price / c.equity > l.max_gross_exposure_pct:
                return "esposizione totale oltre il limite"
        if c.entries_paused:
            return "StoplossGuard: troppi stop di recente, niente nuove entrate"
        if o.symbol in c.cooldowns:
            return "titolo in pausa dopo uno stop"
        if c.trades_today >= l.max_trades_per_day:
            return f"limite di {l.max_trades_per_day} operazioni al giorno"
        return None


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.l = limits

    # --- Interruttori di emergenza ---

    def daily_loss_breached(self, acc: Account) -> bool:
        if acc.last_equity <= 0:
            return False
        return acc.equity / acc.last_equity - 1 <= -self.l.max_daily_loss_pct

    def drawdown_breached(self, equity: float, peak_equity: float) -> bool:
        return peak_equity > 0 and equity / peak_equity - 1 <= -self.l.max_drawdown_pct

    # --- Uscite protettive lato client (il bracket sul broker resta la prima difesa) ---

    @staticmethod
    def update_peaks(positions: dict[str, Position], peaks: dict[str, float]) -> dict[str, float]:
        """Miglior prezzo raggiunto da ogni posizione aperta (massimo per i long, minimo per gli short)."""
        out = {}
        for s, p in positions.items():
            best = peaks.get(s, p.avg_price)
            out[s] = max(best, p.market_price) if p.qty > 0 else min(best, p.market_price)
        return out

    def stop_orders(self, positions: dict[str, Position], atr: dict[str, float],
                    peaks: dict[str, float] | None = None) -> list[Order]:
        out = []
        peaks = peaks or {}
        for s, p in positions.items():
            a = atr.get(s)
            if not a or p.qty == 0:
                continue
            d = 1 if p.qty > 0 else -1
            move = (p.market_price - p.avg_price) * d
            best_move = (peaks.get(s, p.market_price) - p.avg_price) * d
            giveback = best_move - move
            side = "sell" if p.qty > 0 else "buy"
            qty = int(abs(p.qty))
            if move <= -self.l.stop_loss_atr_mult * a:
                out.append(Order(s, qty, side, f"{STOP_LOSS} ({move:+.2f} vs ATR {a:.2f})"))
            elif (self.l.trailing_atr_mult > 0 and best_move >= self.l.trailing_activation_atr * a
                  and giveback >= self.l.trailing_atr_mult * a):
                out.append(Order(s, qty, side, f"{TRAILING} (picco {best_move:+.2f}, ora {move:+.2f})"))
            elif self.l.take_profit_atr_mult > 0 and move >= self.l.take_profit_atr_mult * a:
                out.append(Order(s, qty, side, f"{TAKE_PROFIT} ({move:+.2f} vs ATR {a:.2f})"))
        return out
