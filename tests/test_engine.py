"""Motore PULSE con broker simulato: riflesso, bracket, risk layer, kill switch, pausa di sessione."""
from datetime import timedelta

import numpy as np

import pytest

from conftest import Clock, FakeData, FakeStrategy, make_daily
from desk.agents import CommitteeResult, PortfolioDecision, TargetPosition
from desk.broker import SimBroker
from desk.config import RiskLimits, Settings
from desk.engine import Engine
from desk.journal import Journal

SYMS = ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]


class Committee:
    def __init__(self, targets=None):
        self.targets = targets or {}
        self.calls = 0

    def run(self, snaps, news, portfolio, limits, lessons=None, context=None):
        self.calls += 1
        dec = PortfolioDecision(market_view="test", targets=[
            TargetPosition(symbol=s, target_weight=w, confidence=0.9, thesis=f"tesi {s}", invalidation="-")
            for s, w in self.targets.items()])
        return CommitteeResult({"fake": "ok"}, dec)


def make(scores, committee=None, use_committee=False, core=False, satellite_mode="live", core_trend_filter=False, **risk):
    daily = {s: make_daily(n=320, drift=0.0008, vol=0.005, seed=i + 1) for i, s in enumerate(SYMS)}
    data = FakeData(daily)
    s = Settings(symbols=SYMS, db_path=":memory:", use_committee=use_committee,
                 risk=RiskLimits(core_enabled=core, satellite_mode=satellite_mode,
                                 core_trend_filter=core_trend_filter, **risk))
    broker = SimBroker(100_000, data.latest_prices(SYMS))
    clock = Clock()
    eng = Engine(s, broker, data, committee, Journal(":memory:", clock=clock), clock=clock)
    eng.strategies = [FakeStrategy("trend", scores), FakeStrategy("meanrev", {}, universe=set())]
    return eng, broker, data, clock


def verdicts(eng):
    return {r["symbol"]: (r["verdict"], r["veto"]) for r in eng.j.rows("SELECT * FROM decisions ORDER BY ts")}


def test_reflex_opens_top5_with_brackets_and_vetoes_the_sixth():
    scores = {"AAA": 90, "BBB": 85, "CCC": 80, "DDD": 75, "EEE": 70, "FFF": 65, "SPY": 0}
    eng, broker, data, _ = make(scores)
    eng.tick()
    pos = broker.positions()
    assert set(pos) == {"AAA", "BBB", "CCC", "DDD", "EEE"}
    eq = broker.account().equity
    for s, p in pos.items():
        assert p.market_value <= eq * 0.05 + 1e-6            # max 5% per posizione
        stop, tp = broker.brackets[s]                         # ogni entrata ha il bracket sul broker
        assert stop < p.avg_price < tp
    v = verdicts(eng)
    assert v["FFF"][0] == "VETO" and "massimo 5" in v["FFF"][1]
    assert v["AAA"][0] == "BUY" and v["SPY"][0] == "SKIP"
    entries = eng.j.get("entries")
    assert entries["AAA"]["regime"] and entries["AAA"]["strategy"] == "trend"


def test_no_trades_in_first_5_minutes_or_when_closed():
    eng, broker, _, _ = make({"AAA": 90})
    broker.minutes_open = 3
    eng.tick()
    assert broker.orders == [] and "primi 5 minuti" in verdicts(eng)["AAA"][1]
    eng2, broker2, _, _ = make({"AAA": 90})
    broker2.is_open = False
    eng2.tick()
    assert broker2.orders == []


def test_exit_when_signal_fades_records_trade_journal():
    eng, broker, data, clock = make({"AAA": 90})
    eng.tick()
    assert "AAA" in broker.positions()
    eng.strategies[0].scores["AAA"] = 5
    clock.t += timedelta(minutes=16)
    eng.tick()
    assert "AAA" not in broker.positions()
    t = eng.j.rows("SELECT * FROM closed_trades")[0]
    assert t["symbol"] == "AAA" and t["regime"] and t["strategy"] == "trend" and t["holding_minutes"] == 16.0
    assert t["confidence"] == pytest.approx(90, abs=1)


def test_bracket_stop_on_broker_is_journaled_and_starts_cooldown():
    eng, broker, data, clock = make({"AAA": 90})
    eng.tick()
    stop, _ = broker.brackets["AAA"]
    broker.set_price("AAA", stop - 0.5)                       # il broker esegue lo stop
    clock.t += timedelta(minutes=1)
    eng.tick()
    t = eng.j.rows("SELECT * FROM closed_trades")[0]
    assert t["reason"].startswith("stop loss") and t["exit"] == pytest.approx(stop) and t["pnl"] < 0
    assert "AAA" in eng._cooldowns()
    clock.t += timedelta(minutes=16)
    eng.tick()                                                # il riflesso vuole rientrare: cooldown
    assert "AAA" not in broker.positions() and "pausa dopo uno stop" in verdicts(eng)["AAA"][1]


def test_daily_loss_flattens_and_pauses_until_next_session():
    eng, broker, data, clock = make({"AAA": 90, "BBB": 90})
    eng.tick()
    assert broker.positions()
    broker.start_equity = broker.account().equity * 1.03       # equity sotto del 3% rispetto a ieri
    clock.t += timedelta(minutes=1)
    eng.tick()
    assert broker.positions() == {} and broker.brackets == {} and eng.session_paused()
    clock.t += timedelta(minutes=30)
    eng.tick()
    assert broker.positions() == {}                            # stessa sessione: niente entrate
    broker.start_equity = broker.account().equity              # giorno dopo
    clock.t += timedelta(days=1)
    eng.last_reflex = None
    eng.tick()
    assert not eng.session_paused() and broker.positions()


def test_kill_switch_cancels_and_flattens_then_stays_off():
    eng, broker, _, clock = make({"AAA": 90})
    eng.tick()
    eng.j.set("kill_requested", True)
    clock.t += timedelta(minutes=1)
    eng.tick()
    assert eng.halted and broker.positions() == {} and broker.brackets == {}
    n = len(broker.orders)
    clock.t += timedelta(minutes=30)
    eng.tick()
    assert len(broker.orders) == n


def test_drawdown_from_peak_halts():
    eng, broker, _, _ = make({}, max_drawdown_pct=0.05, max_daily_loss_pct=0.5)
    eng.j.set("equity_peak", 110_000)
    eng.tick()
    assert eng.halted


def test_committee_votes_are_recorded_but_weigh_zero_by_default():
    comm = Committee({"BBB": 0.05})
    eng, broker, _, clock = make({"AAA": 40, "BBB": 40}, committee=comm, use_committee=True)
    eng.tick()
    assert comm.calls == 1 and eng.j.get("committee_stances")["BBB"]["score"] == 90.0   # voto registrato
    assert "BBB" not in broker.positions()            # ma con peso 0 non fa entrare nulla
    # dati grezzi per la valutazione in avanti: voto con segno e punteggi NON pesati
    v = eng.j.rows("SELECT symbol, conviction, price, model FROM votes")
    assert v == [{"symbol": "BBB", "conviction": 0.9, "price": pytest.approx(broker.prices["BBB"]),
                  "model": eng.s.model}]
    sig = {r["symbol"]: r for r in eng.j.rows("SELECT * FROM signals")}
    assert sig["BBB"]["trend_score"] == 40 and sig["AAA"]["price"] > 0
    eng.j.set("weights", {"committee": 0.2})          # peso massimo consentito
    eng.strategies[0].scores["BBB"] = 50
    clock.t += timedelta(minutes=16)
    eng.tick()                                        # 0.8*50 + 0.2*90 = 58 >= 55
    assert "BBB" in broker.positions()
    comm.targets = {s: 0.05 for s in "AAA BBB CCC DDD EEE FFF".split()}
    eng.strategies[0].scores.update({s: 60 for s in "AAA CCC DDD EEE FFF".split()})
    clock.t += timedelta(minutes=31)
    eng.tick()
    assert len(broker.positions()) == 5               # il risk layer resta sopra a tutto


def test_every_broker_order_passes_the_risk_gate():
    """Nessun percorso porta al broker senza RiskGate.check approvato."""
    eng, broker, _, clock = make({"AAA": 90, "BBB": 85, "CCC": 80, "DDD": 75, "EEE": 70, "FFF": 65})
    approved, calls = [], []
    real_check = eng.gate.check
    eng.gate.check = lambda o, c: (lambda v: (approved.append(o.symbol) if v is None else None) or v)(real_check(o, c))
    for name in ("submit", "submit_bracket", "close_position"):
        real = getattr(broker, name)
        setattr(broker, name, (lambda r, n: lambda *a, **k: (calls.append((n, a[0])), r(*a, **k))[1])(real, name))
    eng.tick()
    eng.strategies[0].scores.update({"AAA": 0, "BBB": 0})
    clock.t += timedelta(minutes=16)
    eng.tick()
    broker_symbols = [s for n, s in calls if n in ("submit_bracket", "close_position")]
    assert broker_symbols and sorted(broker_symbols) == sorted(approved)



# ---------- Core + satellite ----------

def gross(broker):
    acc = broker.account()
    return sum(abs(p.market_value) for p in broker.positions().values()) / acc.equity


def test_core_takes_unused_capital_and_satellite_is_funded_by_selling_core():
    eng, broker, _, clock = make({}, core=True)
    eng.tick()                                        # nessun segnale: tutto nel core
    pos = broker.positions()
    assert set(pos) == {"SPY"} and 0.94 <= gross(broker) <= 0.97
    assert eng.j.rows("SELECT * FROM closed_trades") == []      # il core non è un trade del satellite
    eng.strategies[0].scores.update({"AAA": 90, "BBB": 85})
    clock.t += timedelta(minutes=16)
    eng.tick()
    pos = broker.positions()
    assert {"AAA", "BBB", "SPY"} <= set(pos)
    assert gross(broker) <= 1.0 + 1e-9                # niente leva: il core è stato venduto prima
    core_w = pos["SPY"].market_value / broker.account().equity
    sat_w = (pos["AAA"].market_value + pos["BBB"].market_value) / broker.account().equity
    assert core_w + sat_w == pytest.approx(0.97, abs=0.025)
    assert "SPY" not in {r["symbol"] for r in eng.j.rows("SELECT symbol FROM decisions")}   # SPY non è nel satellite


def test_satellite_daily_loss_pauses_satellite_but_keeps_core():
    eng, broker, _, clock = make({"AAA": 90}, core=True)
    eng.tick()
    p = broker.positions()["AAA"]
    broker.brackets.clear()                           # niente stop sul broker: la perdita resta aperta
    broker.set_price("AAA", p.avg_price * 0.5)        # crollo: satellite -2,5% dell'equity
    clock.t += timedelta(minutes=1)
    eng.tick()
    pos = broker.positions()
    assert eng.session_paused() and "AAA" not in pos and "SPY" in pos


def test_normal_spy_drop_does_not_trigger_daily_loss_with_core():
    eng, broker, _, clock = make({}, core=True)
    eng.tick()
    broker.set_price("SPY", broker.prices["SPY"] * 0.96)   # SPY -4%: conto -4%, satellite 0%
    clock.t += timedelta(minutes=1)
    eng.tick()
    assert not eng.session_paused() and not eng.halted and "SPY" in broker.positions()


def test_satellite_drawdown_stops_satellite_only_and_resume_restarts_it():
    eng, broker, _, clock = make({"AAA": 90}, core=True, max_daily_loss_pct=0.5, satellite_max_drawdown_pct=0.01)
    eng.tick()
    broker.brackets.clear()
    broker.set_price("AAA", broker.positions()["AAA"].avg_price * 0.7)
    clock.t += timedelta(minutes=1)
    eng.tick()
    assert eng.satellite_halted() and not eng.halted and set(broker.positions()) == {"SPY"}
    clock.t += timedelta(minutes=16)
    eng.tick()
    assert "AAA" not in broker.positions()            # niente nuove entrate finché non lo riattivi


def test_kill_switch_closes_core_too():
    eng, broker, _, clock = make({"AAA": 90}, core=True)
    eng.tick()
    eng.j.set("kill_requested", True)
    clock.t += timedelta(minutes=1)
    eng.tick()
    assert eng.halted and broker.positions() == {}



# ---------- Decisioni del test 2005-2019: satellite in ombra, filtro 200 giorni sul core ----------

def test_shadow_satellite_trades_virtually_and_survives_restart():
    eng, broker, data, clock = make({"AAA": 90, "BBB": 85}, core=True, satellite_mode="shadow")
    eng.tick()
    assert set(broker.positions()) == {"SPY"}                         # sul conto vero: solo il core
    assert set(eng.sat.positions()) == {"AAA", "BBB"}                 # il satellite opera sul conto virtuale
    assert {r[0] for r in eng.j.db_query("SELECT DISTINCT status FROM orders WHERE symbol='AAA'")} == {"shadow"}
    assert 0.94 <= gross(broker) <= 0.97                              # il core non lascia spazio al satellite
    # riavvio: il conto virtuale è nel diario
    eng2 = Engine(eng.s, broker, data, None, eng.j, clock=clock)
    assert set(eng2.sat.positions()) == {"AAA", "BBB"}
    # il satellite virtuale esce: trade registrato come SHADOW
    eng2.strategies = eng.strategies
    eng2.strategies[0].scores["AAA"] = 0
    clock.t += timedelta(minutes=16)
    eng2.tick()
    t = eng2.j.rows("SELECT mode, symbol FROM closed_trades")
    assert t == [{"mode": "SHADOW", "symbol": "AAA"}] and set(broker.positions()) == {"SPY"}


def test_shadow_bracket_stop_is_recorded():
    eng, broker, data, clock = make({"AAA": 90}, core=True, satellite_mode="shadow")
    eng.tick()
    stop, _ = eng.sat.brackets["AAA"]
    data.overrides["AAA"] = stop - 0.5
    clock.t += timedelta(minutes=1)
    eng.tick()
    t = eng.j.rows("SELECT mode, reason FROM closed_trades")[0]
    assert t["mode"] == "SHADOW" and t["reason"].startswith("stop loss")


def test_core_200d_filter_moves_core_to_cash_and_back():
    eng, broker, data, clock = make({}, core=True, satellite_mode="shadow", core_trend_filter=True)
    spy = data.daily["SPY"]
    close = spy["close"].to_numpy().copy()
    close[-60:] = close[-61] * np.linspace(1.0, 0.75, 60)              # SPY scende sotto la MA200
    for k in ("open", "high", "low", "close"):
        spy[k] = close
    data.overrides["SPY"] = float(close[-1])
    eng.tick()
    assert eng.core_signal is False and broker.positions() == {}       # core in liquidità
    assert eng.j.rows("SELECT kind FROM events WHERE kind='core_filter'")
