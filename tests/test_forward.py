"""Report in avanti: riattivazione, disastri, ombra contro backtest, comitato."""
from dataclasses import replace

import numpy as np
import pandas as pd

from conftest import make_daily
from desk import forward as fw
from desk.backtest import DEFAULT_PARAMS
from desk.config import RiskLimits
from desk.journal import Journal
from desk.universe import PITBacktester

SYMS = ["SPY", "QQQ", "IWM", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]


def put_equity(j, days, acc, shadow):
    for d, a, s in zip(days, acc, shadow):
        ts = f"{d.date()}T20:00:00"
        j._write("INSERT INTO equity (ts, mode, equity, cash, spy) VALUES (?,?,?,?,?)", (ts, "PAPER", a, 0, 400.0))
        j._write("INSERT INTO equity (ts, mode, equity, cash, spy) VALUES (?,?,?,?,?)", (ts, "SHADOW", s, 0, 400.0))


def test_reactivation_and_disaster():
    days = pd.bdate_range("2027-01-04", periods=260)
    rng = np.random.default_rng(1)
    acc = 100_000 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days)))
    j = Journal(":memory:")
    put_equity(j, days, acc, np.linspace(0, 3000, len(days)) + rng.normal(0, 50, len(days)))
    r = fw.reactivation(j)
    assert r["months"] > 12 and r["delta"]["delta"] > 0 and r["disaster"] is False
    assert r["conditions"]["12 mesi"] and not r["conditions"]["100 trade in ombra"]
    # ombra che perde in modo regolare e forte: scatta il controllo dei disastri
    j2 = Journal(":memory:")
    put_equity(j2, days[:150], acc[:150], np.linspace(0, -30_000, 150))
    assert fw.reactivation(j2)["disaster"] is True


def test_too_early():
    j = Journal(":memory:")
    put_equity(j, pd.bdate_range("2027-01-04", periods=10), [100_000] * 10, [0] * 10)
    assert fw.reactivation(j)["delta"] is None


def daily_universe(n=500):
    return {s: make_daily(n=n, drift=0.0007 * (1 if i % 2 else -0.4), vol=0.012, seed=70 + i, end="2027-12-31")
            for i, s in enumerate(SYMS)}


def test_shadow_matches_backtest_and_detects_mismatch():
    daily = daily_universe()
    idx = daily["SPY"].index
    history = {m: SYMS[3:] for m in sorted(set(idx.to_period("M").astype(str)))}
    start, end = idx[320], idx[-1]
    bt = PITBacktester(daily, replace(RiskLimits(), core_enabled=False), member=fw.member_frame(history, idx))
    _, _, trades, _ = bt.run(320, len(idx), DEFAULT_PARAMS)
    assert trades
    j = Journal(":memory:")
    j.set("shadow_universe_history", history)
    for t in trades:      # l'ombra "vera" fa esattamente quello che fa il backtest
        j._write("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                 (f"{t['entry_date'].date()}T15:00:00", "SHADOW", t["symbol"], "buy", t["qty"], "", "", "shadow"))
        j._write("INSERT INTO closed_trades (ts, mode, symbol, direction, qty, entry, exit, pnl, pnl_pct, reason, "
                 "entry_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (f"{t['exit_date'].date()}T15:00:00", "SHADOW", t["symbol"], "long", t["qty"], t["entry"], t["exit"],
                  t["pnl"], t["pnl_pct"], "", f"{t['entry_date'].date()}T15:00:00"))
    ok = fw.backtest_check(j, daily, start, end)
    assert ok["status"] == "OK" and ok["share_live_in_bt"] == 1.0 and ok["pnl_gap_bp"] < 1
    # un'ombra che compra altro: il controllo fallisce
    bad = Journal(":memory:")
    bad.set("shadow_universe_history", history)
    for d in idx[330:400:7]:
        bad._write("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                   (f"{d.date()}T15:00:00", "SHADOW", "GGG", "buy", 1, "", "", "shadow"))
    assert fw.backtest_check(bad, daily, start, end)["status"] == "FALLITO"


def test_committee_skill_and_no_skill():
    daily = daily_universe(400)
    closes = pd.DataFrame({s: d["close"] for s, d in daily.items()})
    days = closes.index[100:390]
    stocks = SYMS[3:]

    def journal(predictive: bool, model="claude-opus-5-5"):
        j = Journal(":memory:")
        rng = np.random.default_rng(5)
        for k in range(0, len(days) - 5, 5):
            d0, d1 = days[k], days[k + 5]
            ex = closes.loc[d1, stocks] / closes.loc[d0, stocks] - closes.loc[d1, "SPY"] / closes.loc[d0, "SPY"]
            for s in stocks:
                conv = float(np.tanh(ex[s] * 50)) if predictive else float(rng.uniform(-1, 1))
                j._write("INSERT INTO votes VALUES (?,?,?,?,?,?,?)",
                         (f"{d0.date()}T14:00:00", s, 0.05 * np.sign(conv), abs(conv), conv, 100.0, model))
                j._write("INSERT INTO signals VALUES (?,?,?,?,?)", (f"{d0.date()}T14:00:00", s, 100.0, 60.0, None))
        return j

    good = fw.committee(journal(True), closes, "claude-opus-5-5", "2020-01-01")
    assert good["windows"] >= 50 and good["spearman_mean"] > 0.9 and good["spearman_t"] > 2
    assert good["regression"]["committee"] > 0 and good["residual_spearman_mean"] > 0.9
    assert good["brier"] < 0.25
    noise = fw.committee(journal(False), closes, "claude-opus-5-5", "2020-01-01")
    assert abs(noise["spearman_mean"]) < 0.15 and not noise["weight_01"]
    # voti di un altro modello o prima della data limite non contano
    assert fw.committee(journal(True, model="altro"), closes, "claude-opus-5-5", "2020-01-01")["windows"] == 0
    assert fw.committee(journal(True), closes, "claude-opus-5-5", "2030-01-01")["windows"] == 0


def test_full_report_renders():
    daily = daily_universe()
    idx = daily["SPY"].index
    j = Journal(":memory:")
    put_equity(j, idx[300:], np.linspace(100_000, 110_000, len(idx) - 300), np.zeros(len(idx) - 300))
    j.set("shadow_universe_history", {m: SYMS[3:] for m in set(idx.to_period("M").astype(str))})
    out = fw.run(j, daily, "claude-opus-5-5")
    text = fw.report(out)
    assert "Riattivazione" in text and "Ombra contro backtest" in text and "Comitato" in text
    assert out["backtest_check"]["status"] in ("OK", "FALLITO")
