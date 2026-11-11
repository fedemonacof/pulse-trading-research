"""Broker: interfaccia comune, implementazione Alpaca e un broker simulato per test e demo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


@dataclass
class Position:
    symbol: str
    qty: float            # negativo = short
    avg_price: float
    market_price: float

    @property
    def market_value(self) -> float:
        return self.qty * self.market_price

    @property
    def unrealized_pl(self) -> float:
        return (self.market_price - self.avg_price) * self.qty


@dataclass
class Account:
    equity: float
    cash: float
    last_equity: float    # equity alla chiusura precedente: base per la perdita giornaliera


@dataclass
class Fill:
    """Uscita avvenuta sul broker (gamba di un bracket), da registrare nel diario."""
    symbol: str
    qty: float
    side: str
    price: float
    reason: str


def minutes_since_open(now: datetime) -> float:
    """Minuti dall'apertura regolare (9:30 New York) del giorno corrente."""
    local = now.astimezone(NY)
    open_ = local.replace(hour=9, minute=30, second=0, microsecond=0)
    return (local - open_).total_seconds() / 60


class Broker(Protocol):
    def account(self) -> Account: ...
    def positions(self) -> dict[str, Position]: ...
    def market_open(self) -> bool: ...
    def minutes_since_open(self) -> float | None: ...
    def submit(self, symbol: str, qty: float, side: str) -> str: ...
    def submit_bracket(self, symbol: str, qty: float, side: str, stop: float, take_profit: float) -> str: ...
    def cancel_orders(self, symbol: str | None = None) -> None: ...
    def close_position(self, symbol: str) -> None: ...
    def close_all(self) -> None: ...
    def take_fills(self) -> list[Fill]: ...


class AlpacaBroker:
    def __init__(self, key: str, secret: str, live: bool):
        from alpaca.trading.client import TradingClient

        if not key or not secret:
            raise SystemExit("Mancano ALPACA_API_KEY / ALPACA_SECRET_KEY nel file .env")
        self.client = TradingClient(key, secret, paper=not live)
        self._fills_after = datetime.now(timezone.utc)

    def account(self) -> Account:
        a = self.client.get_account()
        return Account(equity=float(a.equity), cash=float(a.cash), last_equity=float(a.last_equity))

    def positions(self) -> dict[str, Position]:
        out = {}
        for p in self.client.get_all_positions():
            qty = float(p.qty)
            if str(p.side).lower().endswith("short") and qty > 0:
                qty = -qty
            out[p.symbol] = Position(p.symbol, qty, float(p.avg_entry_price), float(p.current_price))
        return out

    def market_open(self) -> bool:
        return bool(self.client.get_clock().is_open)

    def minutes_since_open(self) -> float | None:
        clock = self.client.get_clock()
        return minutes_since_open(clock.timestamp) if clock.is_open else None

    def submit(self, symbol: str, qty: float, side: str) -> str:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        order = self.client.submit_order(order_data=MarketOrderRequest(
            symbol=symbol, qty=abs(int(qty)),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL, time_in_force=TimeInForce.DAY,
        ))
        return str(order.id)

    def submit_bracket(self, symbol: str, qty: float, side: str, stop: float, take_profit: float) -> str:
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

        order = self.client.submit_order(order_data=MarketOrderRequest(
            symbol=symbol, qty=abs(int(qty)),
            side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.GTC,            # le gambe del bracket restano attive nei giorni successivi
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(take_profit, 2)),
            stop_loss=StopLossRequest(stop_price=round(stop, 2)),
        ))
        return str(order.id)

    def cancel_orders(self, symbol: str | None = None) -> None:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        if symbol is None:
            self.client.cancel_orders()
            return
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol], nested=True)
        for o in self.client.get_orders(filter=req):
            for leg in [o, *(o.legs or [])]:
                try:
                    self.client.cancel_order_by_id(leg.id)
                except Exception:
                    pass  # già eseguito o già cancellato

    def close_position(self, symbol: str) -> None:
        self.cancel_orders(symbol)   # le gambe del bracket bloccherebbero la quantità
        self.client.close_position(symbol)

    def close_all(self) -> None:
        self.client.close_all_positions(cancel_orders=True)

    def take_fills(self) -> list[Fill]:
        """Gambe di bracket eseguite dall'ultima chiamata (stop o take profit scattati sul broker)."""
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        since, self._fills_after = self._fills_after, datetime.now(timezone.utc)
        out = []
        try:
            orders = self.client.get_orders(filter=GetOrdersRequest(
                status=QueryOrderStatus.CLOSED, after=since, nested=True))
        except Exception:
            return out
        for o in orders:
            for leg in o.legs or []:
                if str(leg.status).lower().endswith("filled") and leg.filled_avg_price:
                    kind = "take profit" if str(leg.order_type).lower().endswith("limit") else "stop loss"
                    out.append(Fill(leg.symbol, float(leg.filled_qty), str(leg.side).split(".")[-1].lower(),
                                    float(leg.filled_avg_price), f"{kind} (bracket sul broker)"))
        return out


class SimBroker:
    """Broker finto in memoria: esegue al prezzo corrente, zero commissioni, gestisce i bracket."""

    def __init__(self, cash: float = 100_000.0, prices: dict[str, float] | None = None):
        self.cash = cash
        self.start_equity = cash
        self.prices = dict(prices or {})
        self._pos: dict[str, Position] = {}
        self.brackets: dict[str, tuple[float, float]] = {}   # simbolo -> (stop, take profit)
        self.is_open = True
        self.minutes_open: float | None = 60.0
        self.orders: list[tuple[str, float, str]] = []
        self._fills: list[Fill] = []

    def set_price(self, symbol: str, price: float, low: float | None = None, high: float | None = None) -> None:
        self.prices[symbol] = price
        if symbol in self._pos:
            self._pos[symbol].market_price = price
        self._check_bracket(symbol, low if low is not None else price, high if high is not None else price)

    def _check_bracket(self, symbol: str, low: float, high: float) -> None:
        p, legs = self._pos.get(symbol), self.brackets.get(symbol)
        if not p or not legs:
            return
        stop, tp = legs
        long_ = p.qty > 0
        hit_stop = low <= stop if long_ else high >= stop
        hit_tp = high >= tp if long_ else low <= tp
        if hit_stop or hit_tp:  # se scattano entrambi nella stessa barra si assume lo stop (prudente)
            level = stop if hit_stop else tp
            side = "sell" if long_ else "buy"
            qty = abs(p.qty)
            self.prices[symbol] = level
            p.market_price = level
            self.submit(symbol, qty, side)
            self._fills.append(Fill(symbol, qty, side, level,
                                    f"{'stop loss' if hit_stop else 'take profit'} (bracket sul broker)"))

    def account(self) -> Account:
        equity = self.cash + sum(p.market_value for p in self._pos.values())
        return Account(equity=equity, cash=self.cash, last_equity=self.start_equity)

    def positions(self) -> dict[str, Position]:
        return {k: Position(**vars(v)) for k, v in self._pos.items()}

    def market_open(self) -> bool:
        return self.is_open

    def minutes_since_open(self) -> float | None:
        return self.minutes_open if self.is_open else None

    def submit(self, symbol: str, qty: float, side: str) -> str:
        qty = abs(int(qty))
        signed = qty if side == "buy" else -qty
        price = self.prices[symbol]
        self.cash -= signed * price
        cur = self._pos.get(symbol)
        if cur is None:
            self._pos[symbol] = Position(symbol, signed, price, price)
        else:
            new_qty = cur.qty + signed
            if new_qty == 0:
                del self._pos[symbol]
                self.brackets.pop(symbol, None)
            else:
                same_dir = (cur.qty > 0) == (signed > 0)
                avg = (cur.avg_price * cur.qty + price * signed) / new_qty if same_dir else cur.avg_price
                if (cur.qty > 0) != (new_qty > 0):  # posizione ribaltata
                    avg = price
                self._pos[symbol] = Position(symbol, new_qty, avg, price)
        self.orders.append((symbol, qty, side))
        return f"sim-{len(self.orders)}"

    def submit_bracket(self, symbol: str, qty: float, side: str, stop: float, take_profit: float) -> str:
        oid = self.submit(symbol, qty, side)
        self.brackets[symbol] = (stop, take_profit)
        return oid

    def cancel_orders(self, symbol: str | None = None) -> None:
        if symbol is None:
            self.brackets.clear()
        else:
            self.brackets.pop(symbol, None)

    def close_position(self, symbol: str) -> None:
        self.cancel_orders(symbol)
        p = self._pos.get(symbol)
        if p:
            self.submit(symbol, abs(p.qty), "sell" if p.qty > 0 else "buy")

    def close_all(self) -> None:
        self.cancel_orders()
        for s in list(self._pos):
            self.close_position(s)

    def take_fills(self) -> list[Fill]:
        out, self._fills = self._fills, []
        return out
