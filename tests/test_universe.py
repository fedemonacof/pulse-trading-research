"""Universo storico: stesso motore congelato, solo i titoli ammessi cambiano nel tempo."""
from dataclasses import replace

import numpy as np
import pandas as pd

from conftest import make_daily
from desk.backtest import DEFAULT_PARAMS, Backtester, walk_forward
from desk.config import RiskLimits
from desk.universe import PITBacktester, clean, membership, random_universes, walk_forward_pit

SYMS = ["SPY", "QQQ", "IWM", "AAA", "BBB", "CCC", "DDD"]
LIM = replace(RiskLimits(), core_enabled=False)


def universe(n=760):
    return {s: make_daily(n=n, drift=0.0006 * (1 if i % 2 else -0.3), vol=0.012, seed=40 + i)
            for i, s in enumerate(SYMS)}


def test_all_members_is_identical_to_frozen_backtester():
    """Il filtro dei candidati non cambia nulla: con tutti i titoli sempre ammessi il risultato è identico."""
    d = universe()
    a = Backtester(d, LIM).run(300, 760, DEFAULT_PARAMS)
    b = PITBacktester(d, LIM, member=None).run(300, 760, DEFAULT_PARAMS)
    assert [round(e, 6) for _, e in a[1]] == [round(e, 6) for _, e in b[1]]
    assert [(t["symbol"], t["entry_date"]) for t in a[2]] == [(t["symbol"], t["entry_date"]) for t in b[2]]
    assert a[2], "lo scenario deve produrre trade, altrimenti il confronto non prova nulla"
    wa, wb = walk_forward(d, LIM), walk_forward_pit(d, LIM, member=None, years=2)
    assert wa["equity"] == wb["equity"]


def test_no_entries_outside_membership():
    d = universe()
    idx = d["SPY"].index
    member = pd.DataFrame(True, index=idx, columns=SYMS)
    member.loc[idx[:500], "AAA"] = False            # AAA entra nell'indice solo dal giorno 500
    member.loc[idx[600:], "BBB"] = False            # BBB esce dal giorno 600
    bt = PITBacktester(d, LIM, member=member)
    _, _, trades, _ = bt.run(300, 760, DEFAULT_PARAMS)
    pos = {dt: i for i, dt in enumerate(idx)}
    for t in trades:
        decided = pos[t["entry_date"]] - 1          # decisione alla chiusura del giorno prima
        assert member[t["symbol"]].iloc[decided], t
    assert all(pos[t["entry_date"]] > 500 for t in trades if t["symbol"] == "AAA")


def test_delisted_position_is_closed_at_last_open():
    d = universe()
    idx = d["SPY"].index
    for s in ("AAA", "BBB", "CCC", "DDD"):          # tutti smettono di quotare al giorno 650
        d[s] = d[s].iloc[:650]
    bt = PITBacktester(d, LIM, member=None)
    book, curve, trades, _ = bt.run(300, 760, DEFAULT_PARAMS)
    assert not any(s in book.positions for s in ("AAA", "BBB", "CCC", "DDD"))
    late = [t for t in trades if t["symbol"] != "SPY" and t["exit_date"] >= idx[640]]
    assert all(t["exit_date"] <= idx[649] for t in late)
    assert all(np.isfinite(e) for _, e in curve)


def test_clean_drops_impossible_bars_only():
    d = universe()
    crash = d["BBB"].copy()
    crash.iloc[400:, :4] *= 0.4                     # crollo vero: gap del -60%, barre coerenti -> resta
    d["BBB"] = crash
    glitch = d["CCC"].copy()
    glitch.iloc[500, glitch.columns.get_loc("open")] *= 8   # apertura fuori dal range della barra -> esclusa
    d["CCC"] = glitch
    kept, dropped = clean(d)
    assert dropped == ["CCC"] and "BBB" in kept and "SPY" in kept


def test_membership_table_and_random_draws(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text('date,tickers\n2004-12-01,"AAA,BRK.B,CCC"\n2005-01-05,"AAA,CCC,DDD"\n')
    days = pd.bdate_range("2005-01-03", "2005-01-07")
    m = membership(str(p), days)
    assert m.loc["2005-01-04", "BRK-B"] and not m.loc["2005-01-05", "BRK-B"]
    assert m.loc["2005-01-05", "DDD"] and not m.loc["2005-01-04", "DDD"]
    u = random_universes(m, k=3, n_stocks=2, at="2005-01-03", seed=1)
    assert all(x[:3] == ["SPY", "QQQ", "IWM"] and len(x) == 5 for x in u)
    assert all(set(x[3:]) <= {"AAA", "BRK-B", "CCC"} for x in u)
