"""Simulatore, API e WebSocket del command center, revisione notturna, scheduler, storico Yahoo."""
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from desk.config import Settings
from desk.journal import Journal


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    from desk.simulate import simulate

    path = str(tmp_path_factory.mktemp("demo") / "demo.db")
    simulate(path, days=8)
    return path


def test_simulation_exercises_the_whole_pipeline(demo_db):
    j = Journal(demo_db)
    verdicts = {r[0] for r in j.db_query("SELECT DISTINCT verdict FROM decisions")}
    assert {"BUY", "HOLD", "SKIP", "VETO"} <= verdicts
    assert j.db_query("SELECT COUNT(*) FROM decisions WHERE veto LIKE 'primi 5 minuti%'")[0][0] > 0
    assert j.db_query("SELECT COUNT(*) FROM equity WHERE spy IS NOT NULL")[0][0] > 50
    assert j.get("correlations")["symbols"] and j.get("charts")


def test_state_api_has_every_panel(demo_db, tmp_path):
    c = TestClient(create(demo_db, tmp_path))
    s = c.get("/api/state").json()
    for key in ("counters", "verdicts", "observables", "life", "landing", "correlations", "log", "strategies",
                "equity", "spy", "drawdown", "ticker", "account", "limits"):
        assert key in s, key
    assert set(s["counters"]) == {"trades_today", "signals_today", "blocked_today"}
    assert len({v["symbol"] for v in s["verdicts"]}) == len(s["verdicts"]) == 14   # SPY è il core, non il satellite
    assert "SPY" in {p["symbol"] for p in s["positions"]}
    assert s["observables"]["regime"]["value"] and len(s["observables"]["volatility"]["history"]) > 5
    times = [p["time"] for p in s["equity"]]
    assert times == sorted(set(times))
    assert s["landing"]["bars"] and s["life"][0]["tag"] == "SIGNAL"
    with c.websocket_connect("/ws") as ws:
        assert json.loads(ws.receive_text())["counters"] == s["counters"]


def create(db, tmp_path):
    from desk.web import create_app

    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    (ui / "index.html").write_text("<html>PULSE</html>")
    return create_app(db, dashboard_dir=ui)


def test_kill_switch_endpoints(tmp_path):
    from desk.web import create_app

    db = str(tmp_path / "k.db")
    Journal(db)
    c = TestClient(create_app(db, dashboard_dir=tmp_path / "missing"))
    assert c.get("/").status_code == 503                          # dashboard non compilata: messaggio chiaro
    assert c.get("/api/state").json()["empty"] is True
    assert c.post("/api/kill", json={"confirm": False}).status_code == 400
    assert not Journal(db).get("kill_requested")
    assert c.post("/api/kill", json={"confirm": True}).status_code == 200
    assert Journal(db).get("kill_requested") is True
    c.post("/api/kill/cancel")
    assert Journal(db).get("kill_requested") is False
    Journal(db).set("halted", True)
    c.post("/api/resume")
    assert Journal(db).get("halted") is False


def test_serves_built_dashboard(demo_db, tmp_path):
    c = TestClient(create(demo_db, tmp_path))
    assert "PULSE" in c.get("/").text


def test_nightly_review_adjusts_weights_within_bounds_only(tmp_path):
    from desk.review import nightly_review

    j = Journal(str(tmp_path / "r.db"))
    j.equity("PAPER", 100_000, 100_000)
    for i in range(12):   # trend: 12 trade molto buoni -> peso su; meanrev: 12 pessimi -> peso giù
        for strat, pnl in (("trend", 100 if i % 4 else -20), ("meanrev", -100 if i % 4 else 10)):
            j.closed_trade("PAPER", {"symbol": "SPY", "direction": "long", "qty": 1, "entry": 1, "exit": 1, "pnl": pnl,
                                     "pnl_pct": 0.01, "reason": "x", "strategy": strat, "confidence": 80, "regime": "trending"})
    j.set("weights", {"trend": 1.5, "meanrev": 0.55, "committee": 0.3})
    s = Settings(reports_dir=str(tmp_path / "reports"))
    r = nightly_review(j, s, now=datetime.now(timezone.utc))
    assert r["weights_after"]["trend"] == 1.5            # già al massimo: non sale oltre
    assert r["weights_after"]["meanrev"] == 0.5          # scende, ma non sotto il minimo
    assert r["risk_limits_untouched"] and j.get("weights") == r["weights_after"]
    text = open(r["path"]).read()
    assert "Per strategia" in text and "trend" in text and "Calibrazione" in text


def test_scheduler_refuses_until_enabled():
    from desk.scheduler import build_scheduler

    with pytest.raises(SystemExit, match="backtest"):
        build_scheduler(object(), Settings(scheduler_enabled=False))

    class FakeSched:
        def __init__(self, timezone):
            self.jobs = []

        def add_job(self, fn, trigger, id, **kw):
            self.jobs.append(id)

    sched = build_scheduler(object(), Settings(scheduler_enabled=True), scheduler_cls=FakeSched)
    assert sched.jobs == ["tick", "nightly_review"]


def test_yahoo_history_parses_and_adjusts():
    from desk.histdata import YahooHistory

    ts = [1700000000 + 86400 * i for i in range(5)]
    payload = {"chart": {"result": [{"timestamp": ts, "indicators": {
        "quote": [{"open": [10, 11, 12, 13, 14], "high": [11, 12, 13, 14, 15], "low": [9, 10, 11, 12, 13],
                   "close": [10, 11, 12, 13, 14], "volume": [1, 2, 3, 4, 5]}],
        "adjclose": [{"adjclose": [5, 5.5, 6, 6.5, 7]}]}}]}}
    h = YahooHistory(fetch=lambda url: json.dumps(payload).encode())
    df = h.one("SPY", years=2)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].iloc[-1] == pytest.approx(7) and df["open"].iloc[0] == pytest.approx(5)   # rettificato


def test_monitor_renders(demo_db):
    from rich.console import Console

    from desk.monitor import render

    Console(file=open("/dev/null", "w"), width=120).print(render(Journal(demo_db)))
