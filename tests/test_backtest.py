"""Backtest walk-forward: niente look-ahead, bracket corretti, costi, confronto con SPY."""
import numpy as np
import pandas as pd
import pytest

from conftest import make_daily
from desk.backtest import BTPosition, Backtester, Book, DEFAULT_PARAMS, walk_forward
from desk.config import RiskLimits

SYMS = ["SPY", "QQQ", "IWM", "AAA", "BBB", "CCC"]


def universe(n=760, seed=0):
    return {s: make_daily(n=n, drift=0.0004 * (1 if i % 2 else -0.5), vol=0.01, seed=seed + i)
            for i, s in enumerate(SYMS)}


def test_walk_forward_runs_and_reports_vs_spy():
    r = walk_forward(universe(), RiskLimits(satellite_mode="live"))
    assert r["period"]["days"] > 200 and r["windows"]
    assert set(r["strategy"]) >= {"total_return", "sharpe", "max_drawdown"}
    assert isinstance(r["beats_spy"], bool) and "batte spy" in r["verdict"].lower()
    assert len(r["equity"]) == len(r["spy_equity"])
    for w in r["windows"]:   # ogni finestra ha parametri scelti solo sul passato
        assert w["params"] in [{"fast": f, "slow": s, "k": k} for f, s in ((10, 30), (20, 50), (30, 100))
                               for k in (1.8, 2.0, 2.2)]
    for t in r["trade_list"]:
        assert t["entry_date"] <= t["exit_date"] and t["regime"] and t["strategy"]


def test_decisions_never_use_future_data():
    """Cambiare i prezzi da un certo giorno in poi non cambia nulla di ciò che è successo prima."""
    a = universe()
    b = {s: df.copy() for s, df in a.items()}
    cut = 600
    for df in b.values():
        df.iloc[cut:, :4] *= 1.5
    ra = Backtester(a, RiskLimits(satellite_mode="live")).run(300, cut, DEFAULT_PARAMS)
    rb = Backtester(b, RiskLimits(satellite_mode="live")).run(300, cut, DEFAULT_PARAMS)
    assert [round(e, 6) for _, e in ra[1]] == [round(e, 6) for _, e in rb[1]]
    assert len(ra[2]) == len(rb[2])


def test_costs_reduce_returns():
    d = universe()
    cheap = walk_forward(d, RiskLimits(satellite_mode="live"), cost_bps=0, slippage_bps=0)
    dear = walk_forward(d, RiskLimits(satellite_mode="live"), cost_bps=10, slippage_bps=20)
    if cheap["trades"]["count"]:
        assert dear["strategy"]["total_return"] < cheap["strategy"]["total_return"]


def test_bracket_fills_stop_first_and_gaps():
    d = universe(n=320)
    bt = Backtester(d, RiskLimits(satellite_mode="live"), cost_bps=0, slippage_bps=0)
    i = 310
    idx = bt.idx[i]
    a = bt.arr["AAA"] = {k: v.copy() for k, v in bt.arr["AAA"].items()}   # pandas 3: array in sola lettura
    op = a["open"][i]
    # stop e take profit entrambi dentro la barra: si assume lo stop
    a["low"][i], a["high"][i] = op * 0.9, op * 1.1
    book = Book(cash=0, positions={"AAA": BTPosition(10, op, op * 0.95, op * 1.05, idx, "trending", "trend", 80)})
    _, _, trades, _ = bt.run(i, i + 1, DEFAULT_PARAMS, book=book)
    assert trades[0]["reason"].startswith("stop loss") and trades[0]["exit"] == pytest.approx(op * 0.95)
    # apertura già oltre lo stop (gap): si esce all'apertura, peggio dello stop
    a["low"][i] = op * 0.98
    book = Book(cash=0, positions={"AAA": BTPosition(10, op, op * 1.02, op * 1.2, idx, "trending", "trend", 80)})
    _, _, trades, _ = bt.run(i, i + 1, DEFAULT_PARAMS, book=book)
    assert trades[0]["exit"] == pytest.approx(op)


def test_backtest_respects_risk_limits():
    r = walk_forward(universe(), RiskLimits(satellite_mode="live"))
    by_day = {}
    for t in r["trade_list"]:
        for day in pd.bdate_range(t["entry_date"], t["exit_date"])[:-1]:
            by_day[day] = by_day.get(day, 0) + 1
            assert t["qty"] * t["entry"] <= 100_000 * 1.1 * 0.05 * 1.3   # 5% (con margine per equity cresciuta)
    assert max(by_day.values(), default=0) <= 5


def test_shadow_mode_core_only_follows_200d_filter():
    """Satellite in ombra: il portafoglio è solo il core, che va in liquidità quando SPY è sotto la MA200."""
    d = universe()
    spy = d["SPY"]
    close = spy["close"].to_numpy().copy()
    close[:500] = np.linspace(80, 120, 500)                                 # prima sale: sopra la MA200
    close[500:] = close[499] * np.linspace(1.0, 0.6, len(close) - 500)      # poi lungo ribasso: sotto la MA200
    for k in ("open", "high", "low", "close"):
        spy[k] = close
    bt = Backtester(d, RiskLimits())                  # default: ombra + filtro
    assert bt.shadow and not bt.core_on[-1] and bt.core_on[300]
    book, curve, trades, _ = bt.run(300, len(bt.idx), DEFAULT_PARAMS)
    assert trades == [] and book.core_qty == 0         # nessun trade del satellite, core uscito a fine mese
    assert curve[-1][1] > 100_000 * 0.8                # ha evitato quasi tutto il -40%
