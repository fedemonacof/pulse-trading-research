"""Strategie, regime, riflesso, risk gate, configurazione."""
import numpy as np
import pandas as pd
import pytest

from conftest import make_daily
from desk.config import RiskLimits
from desk.reflex import DEFAULT_WEIGHTS, ENTER, SymbolState, clamp_weights, committee_score, decide, position_size
from desk.risk import GateContext, Order, RiskGate, RiskManager
from desk.broker import Position
from desk.strategies import MeanReversion, TrendFollowing, detect_regime
from desk.strategies.base import generate_signals

L = RiskLimits()
SHORTS = RiskLimits(allow_short=True)


# ---------- Strategie ----------

def test_trend_scores_direction_rsi_filter_and_hysteresis():
    up = make_daily(drift=0.0015, vol=0.008, seed=3)
    down = make_daily(drift=-0.0015, vol=0.008, seed=3)
    t = TrendFollowing()
    fu, fd = t.frame(up), t.frame(down)
    assert (fu["score"].dropna() >= 0).mean() > 0.6 and (fd["score"].dropna() <= 0).mean() > 0.6
    # RSI fuori dalla fascia: non si ENTRA (score 0) ma chi è dentro RESTA (hold > 0): isteresi
    hot = fu[(fu["spread_pct"] > 0) & (fu["rsi"] > 75)].dropna()
    assert len(hot) and (hot["score"] == 0).all() and (hot["hold"] > 0).all()
    assert fu["score"].abs().max() <= 95 and fu["score"].iloc[:126].isna().all()
    # confidenza dal momentum a 6 mesi: più forte il rialzo, più alta la convinzione
    long_rows = fu[fu["score"] > 0]
    assert long_rows["score"].corr(long_rows["momentum"]) > 0.9
    old = TrendFollowing(hysteresis=False, conf="spread").frame(up)
    assert (old["hold"].dropna() == old["score"].dropna()).all()


def test_meanrev_only_on_index_etfs_band_logic_and_ma200_filter():
    m = MeanReversion()
    assert m.applies_to("SPY") and not m.applies_to("NVDA")
    df = make_daily(n=260, drift=0.001, vol=0.004, seed=5)            # mercato che sale: sopra la MA200
    df.iloc[-1, df.columns.get_loc("close")] = df["close"].iloc[-21:-1].mean() * 0.97   # ribasso sotto la banda
    row = m.frame(df).iloc[-1]
    assert row["close"] > row["sma200"] and row["pctb"] < 0 and row["score"] >= 60
    assert row["hold"] == 40 and "sotto la banda" in m.explain(row)
    # stesso ribasso in un mercato sotto la MA200: niente acquisto (coltello che cade)
    bear = make_daily(n=260, drift=-0.001, vol=0.004, seed=5)
    bear.iloc[-1, bear.columns.get_loc("close")] = bear["close"].iloc[-21:-1].mean() * 0.97
    assert m.frame(bear).iloc[-1]["score"] <= 0
    sigs = generate_signals(m, {"SPY": df, "NVDA": df})
    assert [s.symbol for s in sigs] == ["SPY"] and sigs[0].side == "buy" and 0 <= sigs[0].confidence <= 100


def test_strategies_have_no_lookahead():
    df = make_daily(n=300, seed=9)
    for st in (TrendFollowing(), MeanReversion()):
        full = st.frame(df)["score"]
        for cut in (120, 200, 260):
            part = st.frame(df.iloc[:cut])["score"]
            pd.testing.assert_series_equal(full.iloc[:cut], part, check_names=False)


def test_regime_detection():
    assert detect_regime(make_daily(n=150)).name == "warming_up"
    calm_up = make_daily(n=320, drift=0.003, vol=0.004, seed=2)
    assert detect_regime(calm_up).name == "trending"
    wild = make_daily(n=320, drift=0.0, vol=0.03, seed=2)
    assert detect_regime(wild).name in ("high_vol", "crisis")
    crash = make_daily(n=320, drift=0.0005, vol=0.006, seed=2)
    crash.iloc[-25:, crash.columns.get_loc("close")] *= np.linspace(0.97, 0.70, 25)
    crash["low"] = crash[["low", "close"]].min(axis=1)
    assert detect_regime(crash).name == "crisis"


# ---------- Riflesso ----------

def state(**kw):
    base = dict(symbol="AAA", price=100.0, atr=2.0, regime="trending", trend_score=80.0)
    return SymbolState(**{**base, **kw})


def test_reflex_enters_with_bracket_on_correct_sides():
    d = decide(state(), DEFAULT_WEIGHTS, L)
    assert d.intent == "enter_long" and d.stop == 96.0 and d.take_profit == 106.0
    assert decide(state(trend_score=-80.0), DEFAULT_WEIGHTS, L).intent == "skip"      # default: solo long
    s = decide(state(trend_score=-80.0), DEFAULT_WEIGHTS, SHORTS)
    assert s.intent == "enter_short" and s.stop == 104.0 and s.take_profit == 94.0
    assert 0 <= d.confidence <= 100 and d.reason.startswith("compro")


def test_reflex_uses_hold_scores_only_with_open_position():
    # entrata: conta lo score (RSI non conferma -> 0 -> resto fuori)
    assert decide(state(trend_score=0.0, trend_hold=80.0), DEFAULT_WEIGHTS, L).intent == "skip"
    # posizione aperta: conta l'hold (trend intatto -> resto dentro, anche se l'RSI è ipercomprato)
    assert decide(state(trend_score=0.0, trend_hold=80.0, position_qty=5), DEFAULT_WEIGHTS, L).intent == "hold"
    assert decide(state(trend_score=80.0, trend_hold=-60.0, position_qty=5), DEFAULT_WEIGHTS, L).intent == "exit"


def test_reflex_thresholds_and_exits():
    assert decide(state(trend_score=50.0), DEFAULT_WEIGHTS, L).intent == "skip"
    assert decide(state(trend_score=10.0, position_qty=5), DEFAULT_WEIGHTS, L).intent == "exit"
    assert decide(state(trend_score=40.0, position_qty=5), DEFAULT_WEIGHTS, L).intent == "hold"
    assert decide(state(trend_score=-10.0, position_qty=-5), DEFAULT_WEIGHTS, L).intent == "exit"


def test_reflex_regimes_crisis_and_warmup():
    assert decide(state(regime="crisis"), DEFAULT_WEIGHTS, L).intent == "skip"          # niente nuovi long
    assert decide(state(regime="crisis", trend_score=-80.0), DEFAULT_WEIGHTS, SHORTS).intent == "enter_short"
    assert decide(state(regime="warming_up"), DEFAULT_WEIGHTS, L).intent == "skip"
    no_short = RiskLimits(allow_short=False)
    assert decide(state(trend_score=-80.0), DEFAULT_WEIGHTS, no_short).intent == "skip"


def test_committee_vote_is_bounded_and_off_by_default():
    assert committee_score(0.05, 0.9, L) == pytest.approx(90.0)
    assert committee_score(0.20, 1.0, L) == 100.0              # tagliato a ±100
    assert committee_score(0.05, 0.5, L) is None               # sotto la confidenza minima non vota
    # default: peso 0, il voto viene registrato ma non sposta nulla
    assert DEFAULT_WEIGHTS["committee"] == 0.0
    off = decide(state(trend_score=40.0, committee_score=100.0), DEFAULT_WEIGHTS, L)
    assert off.score == pytest.approx(40.0) and off.intent == "skip"
    # anche chiedendo un peso altissimo, il comitato resta al massimo al 20%
    w = clamp_weights({"committee": 0.95, "trend": 9})
    assert w == {"trend": 1.5, "meanrev": 1.0, "committee": 0.2}
    with_vote = decide(state(trend_score=40.0, committee_score=100.0), w, L)
    assert with_vote.score == pytest.approx(52.0) and with_vote.intent == "skip"
    alone = decide(state(trend_score=0.0, committee_score=100.0), w, L)
    assert alone.score == pytest.approx(20.0) and alone.intent == "skip"   # da solo non apre mai


def test_position_size_respects_5pct_and_regime():
    full = position_size(100_000, 100, 100, "trending", L)
    assert full * 100 <= 5_000 and full == 50
    assert position_size(100_000, 100, 100, "high_vol", L) == 25
    assert position_size(100_000, 100, 55, "trending", L) < full


# ---------- Risk gate ----------

def ctx(**kw):
    base = dict(market_open=True, minutes_since_open=60, equity=100_000, last_equity=100_000, open_positions=0)
    return GateContext(**{**base, **kw})


def entry(**kw):
    base = dict(symbol="AAA", qty=40, side="buy", reason="test", intent="enter_long", stop=96.0,
                take_profit=106.0, price=100.0)
    return Order(**{**base, **kw})


@pytest.mark.parametrize("order,context,needle", [
    (entry(), ctx(halted=True), "kill switch"),
    (entry(), ctx(market_open=False), "orario regolare"),
    (entry(), ctx(minutes_since_open=3), "primi 5 minuti"),
    (entry(), ctx(session_paused=True), "prossima sessione"),
    (entry(), ctx(equity=97_900), "perdita giornaliera"),
    (entry(), ctx(open_positions=5), "massimo 5"),
    (entry(stop=None), ctx(), "bracket"),
    (entry(qty=60), ctx(), "5%"),
    (entry(stop=101.0), ctx(), "parte sbagliata"),
    (entry(), ctx(entries_paused=True), "StoplossGuard"),
    (entry(), ctx(cooldowns={"AAA"}), "pausa dopo uno stop"),
    (entry(), ctx(trades_today=20), "operazioni al giorno"),
    (entry(qty=0), ctx(), "dimensione zero"),
])
def test_gate_vetoes(order, context, needle):
    veto = RiskGate(L).check(order, context)
    assert veto and needle in veto


def test_gate_approves_valid_entry_and_lets_exits_through_when_paused():
    g = RiskGate(L)
    assert g.check(entry(), ctx()) is None
    exit_ = Order("AAA", 40, "sell", "uscita", intent="exit")
    assert g.check(exit_, ctx(session_paused=True, open_positions=9, entries_paused=True)) is None
    assert g.check(exit_, ctx(minutes_since_open=2)) is not None     # i primi 5 minuti valgono per tutti


def test_gate_core_orders_skip_satellite_limits_but_not_leverage():
    g = RiskGate(L)
    core = Order("SPY", 900, "buy", "core", intent="core", price=100.0)    # 90%: oltre il 5%, ma è il core
    assert g.check(core, ctx(open_positions=5)) is None
    assert "esposizione totale" in g.check(core, ctx(gross_exposure=0.2))
    assert "kill switch" in g.check(core, ctx(halted=True))
    assert "primi 5 minuti" in g.check(core, ctx(minutes_since_open=1))


def test_trailing_and_peaks():
    rm = RiskManager(RiskLimits(stop_loss_atr_mult=2, trailing_atr_mult=2.5, trailing_activation_atr=1.5,
                                take_profit_atr_mult=0))
    assert rm.stop_orders({"A": Position("A", 10, 100, 107)}, {"A": 1}, {"A": 110})[0].reason.startswith("trailing")
    assert rm.stop_orders({"A": Position("A", 10, 100, 97)}, {"A": 1})[0].reason.startswith("stop loss")
    peaks = RiskManager.update_peaks({"A": Position("A", 1, 100, 105), "B": Position("B", -1, 100, 95)}, {})
    assert peaks == {"A": 105, "B": 95}


# ---------- Configurazione: paper per default ----------

def test_config_refuses_live_url_without_explicit_approval(monkeypatch):
    from desk import config

    monkeypatch.setenv("ALPACA_BASE_URL", config.PAPER_URL)
    monkeypatch.delenv("SYMBOLS", raising=False)
    s = config.load_settings()
    assert not s.live and s.mode == "PAPER" and len(s.symbols) == 15 and not s.scheduler_enabled
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.delenv("LIVE_TRADING", raising=False)
    with pytest.raises(SystemExit, match="non è l'indirizzo paper"):
        config.load_settings()
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.delenv("LIVE_CONFIRMATION", raising=False)
    with pytest.raises(SystemExit, match="LIVE_CONFIRMATION"):
        config.load_settings()
    monkeypatch.setenv("LIVE_CONFIRMATION", config.LIVE_CONFIRMATION)
    assert config.load_settings().live
