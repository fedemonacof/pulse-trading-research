"""PULSE-CT ipotesi 1: regola, blocco delle date, flusso dal vivo, registro dei costi, statistiche. Niente rete."""
import inspect
import json

import numpy as np
import pandas as pd
import pytest

from pulse_mm.core.costs import Cost, CostModelBp, Ledger
from pulse_mm.research.crypto_trend import config, data, live, stats, strategy, trials


def candles(n=900, start="2016-01-01", drift=0.001, vol=0.03, seed=1, p0=100.0):
    rng = np.random.default_rng(seed)
    close = p0 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.date_range(start, periods=n, freq="D")
    open_ = np.r_[p0, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.01,
                         "low": np.minimum(open_, close) * 0.99, "close": close, "volume": 1.0}, index=idx)


@pytest.fixture
def px():
    return {"BTC-USD": candles(seed=1), "ETH-USD": candles(seed=2)}


MODEL = CostModelBp(fee_bp=10, spread_bp=5, slippage_bp=5)


# ------------------------------------------------------------ segnale ed esposizione

def test_signal_levels_and_exposure():
    close = pd.Series(np.r_[np.linspace(100, 50, 300), np.linspace(50, 80, 40)],
                      index=pd.date_range("2016-01-01", periods=340, freq="D"))
    sig = strategy.signals(close)
    last = sig.iloc[-1]
    assert last["s21"] == 1 and last["s252"] == -1
    assert set(sig["m"].dropna().unique()) <= {-1.0, -1 / 3, 1 / 3, 1.0}
    w, _ = strategy.target_weights(sig, "V3")
    assert ((w >= 0) & (w <= config.MAX_LEV)).all()
    e = sig["m"].clip(lower=0) * (config.VOL_TARGET / sig["sigma"]).clip(upper=1)
    assert np.allclose(w.iloc[-1], e.iloc[-1])


def test_benchmark_is_always_long_with_same_vol_targeting():
    close = candles(400)["close"]
    sig = strategy.signals(close)
    w, lvl = strategy.target_weights(sig, "BENCH")
    ok = sig["sigma"].notna()
    assert np.allclose(w[ok], (config.VOL_TARGET / sig["sigma"][ok]).clip(upper=1))
    assert (lvl == 1).all()


def test_signal_uses_only_past_closes():
    df = candles(500)
    a = strategy.signals(df["close"])
    b = strategy.signals(df["close"].iloc[:400])
    pd.testing.assert_frame_equal(a.iloc[:400], b)


# ------------------------------------------------------------ simulazione

def test_cost_ledger_reconciles_with_gross_minus_net(px):
    res = strategy.simulate(px, "V3", MODEL, end=px["BTC-USD"].index[-1])
    rec = strategy.reconcile(res)
    assert rec["ok"] and rec["costs_total"] > 0
    assert len(res.trades) > 10


def test_no_trade_below_threshold_unless_level_changes_or_over_cap(px):
    res = strategy.simulate(px, "BENCH", MODEL, end=px["BTC-USD"].index[-1])
    for t in res.trades:
        w_change = abs(t["dq"]) * t["price"] / (t["equity"] * config.SPLIT)
        assert w_change >= config.THRESHOLD * 0.9   # ogni scambio del benchmark supera la soglia (circa)


def test_weights_never_above_one_after_trading(px):
    res = strategy.simulate(px, "V3", MODEL, end=px["BTC-USD"].index[-1])
    assert (res.weights.max() <= 1.0 + 0.10 + 1e-9).all()   # la deriva fra due ribilanciamenti resta limitata


def test_monthly_realignment_restores_half_split(px):
    res = strategy.simulate(px, "BENCH", CostModelBp(0, 0, 0), end=px["BTC-USD"].index[-1])
    assert len(res.realigned) >= 20
    for d, sleeves in res.realigned:
        assert d.weekday() == 0 and d.day <= 7          # primo lunedì del mese (revisione 1)
        assert sleeves["BTC-USD"] == pytest.approx(sleeves["ETH-USD"])


def test_cost_doubling_before_2025():
    assert strategy.cost_mult(pd.Timestamp("2024-12-31")) == 2.0
    assert strategy.cost_mult(pd.Timestamp("2025-01-01")) == 1.0


def test_validation_refuses_without_taker_fee(monkeypatch):
    monkeypatch.setattr(config, "TAKER_BP", None)
    with pytest.raises(PermissionError):
        strategy.cost_model()


def test_taker_fee_from_okx_eu_list():
    assert config.TAKER_BP == 10.0                      # listino OKX Europe del 2026-11-11 (criterio 8)
    assert strategy.cost_model().fee_bp == 10.0


# ------------------------------------------------------------ dati, blocco delle date, flusso dal vivo

def test_downloader_refuses_dates_after_dev_before_signature():
    with pytest.raises(PermissionError):
        data.download("BTC-USD", "2020-12-01", "2021-01-05", get=lambda u: b"[]", st="unsigned")
    with pytest.raises(PermissionError):
        data.download("BTC-USD", "2022-12-01", "2023-01-05", get=lambda u: b"[]", st="val")


def test_loader_has_no_switch_to_disable_the_date_block():
    params = set(inspect.signature(data.load).parameters)
    assert params == {"st"}
    assert "allow" not in inspect.getsource(data)


def test_loader_refuses_test_period_data(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(data, "RAW", raw)
    monkeypatch.setattr(data, "MANIFEST", raw / "manifest.json")
    t = int(pd.Timestamp("2021-01-02").timestamp())
    data.save("BTC-USD", "2021-01-01", "2021-01-02", [json.dumps([[t, 1, 2, 1.5, 1.6, 10]]).encode()])
    data.save("ETH-USD", "2021-01-01", "2021-01-02", [json.dumps([[t, 1, 2, 1.5, 1.6, 10]]).encode()])
    with pytest.raises(PermissionError):
        data.load(st="unsigned")
    assert len(data.load(st="val")["BTC-USD"]) == 1


def test_loader_rejects_modified_files(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(data, "RAW", raw)
    monkeypatch.setattr(data, "MANIFEST", raw / "manifest.json")
    t = int(pd.Timestamp("2018-01-02").timestamp())
    for a in config.ASSETS:
        data.save(a, "2018-01-01", "2018-01-02", [json.dumps([[t, 1, 2, 1.5, 1.6, 10]]).encode()])
    (raw / "BTC-USD_2018-01-01_2018-01-02.jsonl").write_bytes(b"[]\n")
    with pytest.raises(PermissionError):
        data.load(st="unsigned")


def test_parse_coinbase_rows_order():
    t = int(pd.Timestamp("2018-01-02").timestamp())
    df = data.parse(json.dumps([[t, 1.0, 2.0, 1.5, 1.6, 10.0]]).encode())
    row = df.iloc[0]
    assert (row["low"], row["high"], row["open"], row["close"]) == (1.0, 2.0, 1.5, 1.6)
    assert df.index[0] == pd.Timestamp("2018-01-02")


def test_quality_flags_impossible_bar():
    df = candles(30)
    df.iloc[10, df.columns.get_loc("close")] = df["high"].iloc[10] * 1.5
    assert data.quality(df)


def test_coverage_counts_missing_runs():
    df = candles(100).drop(pd.date_range("2016-02-01", periods=4, freq="D"))
    cov = data.coverage(df, "2016-01-01", "2016-04-09")
    assert cov["max_missing_run"] == 4 and not cov["ok"]


def test_live_feed_refuses_dates_before_november_2026():
    feed = live.LiveFeed(lambda s: (pd.Timestamp("2026-10-31 23:00", tz="UTC"), 1.0))
    with pytest.raises(PermissionError):
        feed.price("BTC-USD")
    ok = live.LiveFeed(lambda s: (pd.Timestamp("2026-11-12 00:05", tz="UTC"), 1.0))
    assert ok.price("BTC-USD")[1] == 1.0
    with pytest.raises(PermissionError):
        feed.bars(pd.DataFrame(index=pd.date_range("2026-10-30", periods=3)))


def test_live_feed_writes_outside_historical_store():
    assert live.LIVE_DIR != data.RAW and data.RAW not in live.LIVE_DIR.parents


# ------------------------------------------------------------ stato della pre-registrazione

def test_stage_from_document_and_trials(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("| Impronta del codice | — |\n")
    tr = tmp_path / "trials.jsonl"
    assert trials.stage(doc, tr) == "unsigned"
    doc.write_text("| Impronta del codice | `0123456789abcdef` |\n")
    assert trials.stage(doc, tr) == "val"
    trials.record("val", config.MAIN, {}, outcome="non concludente", path=tr)
    assert trials.stage(doc, tr) == "val"
    trials.record("val", config.MAIN, {}, outcome="passa", path=tr)
    assert trials.stage(doc, tr) == "test"


def test_real_document_is_unsigned_and_blocks_validation():
    assert trials.registered() is None
    with pytest.raises(PermissionError):
        trials.require_frozen()


# ------------------------------------------------------------ registro dei costi e statistiche

def test_cost_components_sum():
    c = MODEL.on(10_000, mult=2)
    assert c.fee == 20 and c.spread == 10 and c.slippage == 10 and c.total == 40
    led = Ledger()
    led.add("x", c, 10_000)
    assert led.in_bp()["total"] == pytest.approx(40)
    assert Ledger.reconcile(40.0, c.total, 1e6)["ok"]
    assert not Ledger.reconcile(41.0, c.total, 1e5)["ok"]
    assert Cost(venue_basis=1.0).total == 1.0


def test_max_dd_is_positive():
    assert stats.max_dd(np.array([0.1, -0.5, 0.2])) == pytest.approx(0.5)
    assert stats.max_dd(np.array([0.01, 0.02])) == 0.0


@pytest.mark.parametrize("b,expected", [
    ({"d_dd_lo": -0.2, "d_dd_hi": -0.05, "d_sharpe_lo": -0.05, "d_sharpe_hi": 0.3}, "passa"),
    ({"d_dd_lo": 0.01, "d_dd_hi": 0.1, "d_sharpe_lo": 0.0, "d_sharpe_hi": 0.3}, "fallisce"),
    ({"d_dd_lo": -0.2, "d_dd_hi": -0.05, "d_sharpe_lo": -0.6, "d_sharpe_hi": -0.15}, "fallisce"),
    ({"d_dd_lo": -0.2, "d_dd_hi": 0.05, "d_sharpe_lo": 0.0, "d_sharpe_hi": 0.3}, "non concludente"),
    ({"d_dd_lo": -0.2, "d_dd_hi": -0.05, "d_sharpe_lo": -0.3, "d_sharpe_hi": 0.2}, "non concludente"),
])
def test_outcome_table(b, expected):
    assert stats.outcome(b) == expected


def test_bootstrap_is_deterministic_with_seed():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2021-01-01", periods=400, freq="D")
    s, b = pd.Series(rng.normal(0, 0.02, 400), idx), pd.Series(rng.normal(0, 0.03, 400), idx)
    x = stats.paired_bootstrap(s, b, n=200)
    y = stats.paired_bootstrap(s, b, n=200)
    assert x == y and x["d_dd_lo"] <= x["d_dd"] <= x["d_dd_hi"] + 1e-9


def test_fingerprint_covers_cost_ledger():
    names = [p.name for p in trials.CODE_FILES]
    assert "costs.py" in names and "strategy.py" in names and len(trials.fingerprint()) == 16


def test_weekly_decisions_only_on_monday(px):
    res = strategy.simulate(px, "V3", MODEL, end=px["BTC-USD"].index[-1])
    assert res.trades and all(t["date"].weekday() == 0 for t in res.trades)
    daily = strategy.simulate(px, "V3", MODEL, end=px["BTC-USD"].index[-1], weekday=None)
    assert len(daily.trades) > len(res.trades)
    assert any(t["date"].weekday() != 0 for t in daily.trades)


def test_benchmark_uses_same_weekly_schedule(px):
    res = strategy.simulate(px, "BENCH", MODEL, end=px["BTC-USD"].index[-1])
    assert all(t["date"].weekday() == 0 for t in res.trades)


def test_higher_threshold_trades_less(px):
    end = px["BTC-USD"].index[-1]
    a = strategy.simulate(px, "BENCH", MODEL, end=end)
    b = strategy.simulate(px, "BENCH", MODEL, end=end, threshold=config.THRESHOLD_FALLBACK)
    assert len(b.trades) <= len(a.trades)


def test_n_trials_after_revision_1():
    assert config.N_TRIALS == 4 and "V3-daily" in config.VARIANTS


@pytest.mark.parametrize("variant", ["V3", "BENCH"])
def test_truncating_data_does_not_change_the_past(px, variant):
    end = px["BTC-USD"].index[-1]
    for cut in ("2017-03-15", "2017-09-04", "2018-01-01"):
        r = strategy.truncation_check(px, variant, MODEL, cut, end)
        assert r["ok"] and r["trades_compared"] > 0, r


def test_data_before_warmup_is_ignored(px):
    end = px["BTC-USD"].index[-1]
    a = strategy.simulate(px, "V3", MODEL, end=end)
    early = {k: pd.concat([candles(60, start="2015-11-01", seed=9), v]) for k, v in px.items()}
    b = strategy.simulate(early, "V3", MODEL, end=end)
    assert a.equity.index[0] == config.WARMUP_START
    pd.testing.assert_series_equal(a.equity, b.equity)


# ------------------------------------------------------------ robustezze: parità di rischio ed EUR (solo codice)

def test_equal_split_is_default_and_unchanged(px):
    a = strategy.simulate(px, "V3", MODEL, end="2018-06-01")
    b = strategy.simulate(px, "V3", MODEL, end="2018-06-01", split="equal")
    pd.testing.assert_series_equal(a.equity, b.equity)


def test_risk_parity_sleeves_follow_inverse_vol():
    calm, wild = candles(seed=1, vol=0.02), candles(seed=2, vol=0.06)
    p = {"BTC-USD": calm, "ETH-USD": wild}
    res = strategy.simulate(p, "BENCH", MODEL, end="2018-06-01", split="risk_parity")
    closes = pd.DataFrame({a: p[a]["close"] for a in p}).loc[config.WARMUP_START:]
    sig = {a: strategy.signals(closes[a].reindex(pd.date_range(closes.index[0], "2018-06-01"))) for a in p}
    checked = 0
    for d, sleeves in res.realigned:
        i = sig["BTC-USD"].index.get_loc(d) - 1
        s_b, s_e = sig["BTC-USD"]["sigma"].iloc[i], sig["ETH-USD"]["sigma"].iloc[i]
        if np.isfinite(s_b) and np.isfinite(s_e):
            assert sleeves["BTC-USD"] / sleeves["ETH-USD"] == pytest.approx(s_e / s_b, rel=1e-9)
            checked += 1
    assert checked >= 10
    assert strategy.reconcile(res)["ok"]


def test_risk_parity_falls_back_to_equal_without_sigma():
    sig = {"A": pd.DataFrame({"sigma": [np.nan]}), "B": pd.DataFrame({"sigma": [0.5]})}
    assert strategy.sleeve_shares(sig, 0, "risk_parity") == {"A": 0.5, "B": 0.5}
    with pytest.raises(ValueError):
        strategy.simulate({}, "V3", MODEL, end="2018-01-01", split="altro")


ECB_CSV = (b"KEY,FREQ,TIME_PERIOD,OBS_VALUE\n"
           b"EXR.D.USD.EUR.SP00.A,D,2020-01-02,1.10\n"
           b"EXR.D.USD.EUR.SP00.A,D,2020-01-03,1.20\n"
           b"EXR.D.USD.EUR.SP00.A,D,2020-01-06,1.25\n")


def test_eur_conversion_uses_last_published_rate():
    from pulse_mm.research.crypto_trend import fx
    rate = fx.parse(ECB_CSV)
    eq = pd.Series(120.0, index=pd.date_range("2020-01-02", "2020-01-06"))
    eur = fx.to_eur(eq, rate)
    assert eur["2020-01-02"] == pytest.approx(120 / 1.10)
    assert eur["2020-01-04"] == pytest.approx(100.0)            # sabato: cambio di venerdì
    assert eur["2020-01-06"] == pytest.approx(96.0)
    with pytest.raises(ValueError):
        fx.to_eur(pd.Series(1.0, index=pd.date_range("2020-01-01", periods=2)), rate)


def test_eur_with_constant_rate_keeps_usd_returns(px):
    from pulse_mm.research.crypto_trend import fx
    res = strategy.simulate(px, "V3", MODEL, end="2018-06-01")
    rate = pd.Series(1.25, index=pd.date_range("2015-12-01", "2018-06-01", freq="B"))
    s, e = pd.Timestamp("2018-01-01"), pd.Timestamp("2018-06-01")
    pd.testing.assert_series_equal(fx.returns_eur(res, rate, s, e), res.returns(s, e), check_names=False)


def test_fx_respects_date_lock_and_hashes(tmp_path, monkeypatch):
    from pulse_mm.research.crypto_trend import fx
    with pytest.raises(PermissionError):
        fx.download("2020-12-01", "2021-01-05", get=lambda u: b"", st="unsigned")
    monkeypatch.setattr(fx, "FX", tmp_path)
    monkeypatch.setattr(fx, "MANIFEST", tmp_path / "manifest.json")
    fx.save("2020-01-01", "2020-01-06", ECB_CSV)
    assert len(fx.load(st="unsigned")) == 3
    (tmp_path / "EURUSD-ECB_2020-01-01_2020-01-06.csv").write_bytes(ECB_CSV + b"x")
    with pytest.raises(PermissionError):
        fx.load(st="unsigned")


def test_fx_gap_check():
    from pulse_mm.research.crypto_trend import fx
    rate = pd.Series(1.1, index=pd.date_range("2018-01-01", "2018-03-01", freq="B"))
    assert fx.gaps(rate, "2018-01-01", "2018-03-01")["ok"]
    assert not fx.gaps(rate.drop(rate.index[10:20]), "2018-01-01", "2018-03-01")["ok"]


# ------------------------------------------------------------ dry-run del criterio 7 (senza rete)

from datetime import date, datetime, timedelta, timezone  # noqa: E402

from pulse_mm.research.crypto_trend import dryrun  # noqa: E402


class FakeFT:
    def __init__(self, venue="myokx", dry=True):
        self.trades, self.next, self.venue, self.dry = {}, 1, venue, dry

    def show_config(self):
        return {"dry_run": self.dry, "exchange": self.venue}

    def open_trade(self, pair):
        return next((t for t in self.trades.values() if t["pair"] == pair and t["open"]), None)

    def trade(self, tid):
        return self.trades[tid]

    def buy(self, pair, stake):
        tid, self.next = self.next, self.next + 1
        px = 100.1 if pair.startswith("BTC") else 10.01
        self.trades[tid] = {"trade_id": tid, "pair": pair, "open": True,
                            "orders": [{"ft_order_side": "buy", "filled": stake / px, "safe_price": px}]}
        return {"trade_id": tid}

    def sell(self, tid):
        t = self.trades[tid]
        px = 99.9 if t["pair"].startswith("BTC") else 9.99
        t["orders"].append({"ft_order_side": "sell", "filled": 1.0, "safe_price": px})
        t["open"] = False
        return {"result": "ok"}


def quote_ok(asset):
    mid = 100.0 if asset.startswith("BTC") else 10.0
    return {"bid": mid * 0.9999, "ask": mid * 1.0001, "mid": mid, "ts": "2026-12-01T00:05:00+00:00"}


def book_ok(asset):
    mid = 100.0 if asset.startswith("BTC") else 10.0
    lv = lambda sgn: [[mid * (1 + sgn * 1e-4 * k), 50_000 / mid] for k in range(1, 5)]   # 50.000 USDC a livello
    return {"bids": lv(-1), "asks": lv(1), "ts": "2026-12-01T00:05:00+00:00"}


def cb_ok(asset, day):
    return 100.0 if asset.startswith("BTC") else 10.0


@pytest.fixture
def dr(tmp_path):
    sp, lg = tmp_path / "start.json", tmp_path / "orders.jsonl"
    p = dryrun.start("2026-12-01", today=date(2026, 11, 20), path=sp)
    return sp, lg, p


def at(day, minute=5, second=10):
    return datetime(2026, 12, day, 0, minute, second, tzinfo=timezone.utc)


def test_dryrun_plan_written_before_first_order(dr, tmp_path):
    sp, _, p = dr
    assert p["stake_usdc"] == pytest.approx(10_400.0)
    assert p["valid_days_needed"] == 28 and p["max_missed"] == 3 and p["time_utc"] == "00:05"
    assert p["last_day_max"] == "2026-12-31"
    assert p["fingerprint"] == dryrun.plan_fingerprint()
    with pytest.raises(FileExistsError):
        dryrun.start("2026-12-02", today=date(2026, 11, 20), path=sp)
    with pytest.raises(ValueError):
        dryrun.start("2026-11-20", today=date(2026, 11, 20), path=tmp_path / "x.json")
    with pytest.raises(PermissionError):
        dryrun.start("2026-10-30", today=date(2026, 10, 1), path=tmp_path / "y.json")


def test_dryrun_alternates_and_measures(dr):
    sp, lg, _ = dr
    ft = FakeFT()
    day1 = dryrun.tick(ft, now=at(1), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    assert [r["side"] for r in day1] == ["buy", "buy"]
    assert dryrun.tick(ft, now=at(1, 6), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg) == []  # idempotente
    day2 = dryrun.tick(ft, now=at(2), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    assert [r["side"] for r in day2] == ["sell", "sell"]
    m = [dryrun.measures(r) for r in day1 + day2]
    assert all(x["exec_gap_bp"] == pytest.approx(10.0) for x in m)    # comprato a +10 bp, venduto a -10 bp
    assert all(x["venue_basis_bp"] == pytest.approx(0.0) for x in m)
    rep = dryrun.report(log=lg)
    assert rep["orders"] == 4 and rep["costs_hold"]                  # 10 bp = tetto di 5 + 5 bp


def test_dryrun_flags_missing_okx_price_and_late_runs(dr):
    sp, lg, _ = dr
    ft = FakeFT()

    def no_btc(asset):
        if asset.startswith("BTC"):
            raise TimeoutError("OKX non risponde")
        return quote_ok(asset)

    dryrun.tick(ft, now=at(1), quote=no_btc, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    dryrun.tick(ft, now=at(2, minute=30), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)   # Mac sveglio tardi
    dryrun.tick(ft, now=at(3), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    c = dryrun.check(now=at(5, minute=0), start_path=sp, log=lg)
    assert c["valid_days"] == 1 and c["missed_days"] == 3 and c["state"] == "in corso"
    issues = {a["day"]: " ".join(a["issues"]) for a in c["alerts"]}
    assert "prezzo OKX mancante" in issues["2026-12-01"]
    assert "ritardo" in issues["2026-12-02"]
    assert "non partito" in issues["2026-12-04"]
    assert ft.open_trade("BTC/USDC") is not None                      # 3 dic: BTC compra (1 dic saltato), ETH vende


def test_dryrun_fails_after_fourth_missed_day(dr):
    sp, lg, _ = dr
    c = dryrun.check(now=at(6), start_path=sp, log=lg)
    assert c["missed_days"] == 4 and c["state"].startswith("fallito")


def test_dryrun_completes_with_recovered_days(dr):
    sp, lg, _ = dr
    ft = FakeFT()
    start = datetime(2026, 12, 1, 0, 5, 10, tzinfo=timezone.utc)
    for k in range(31):
        if k in (3, 10):
            continue                                               # due giorni saltati, recuperati in coda
        dryrun.tick(ft, now=start + timedelta(days=k), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    c = dryrun.check(now=start + timedelta(days=40), start_path=sp, log=lg)
    assert c["valid_days"] == 28 and c["missed_days"] == 2 and c["state"] == "completo"
    assert c["last_checked"] == "2026-12-30"


def test_dryrun_refuses_wrong_venue_and_changed_plan(dr, monkeypatch):
    sp, lg, _ = dr
    r = dryrun.tick(FakeFT(venue="okx"), now=at(1), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    assert {x["status"] for x in r} == {"order_failed"}
    monkeypatch.setattr(dryrun, "plan_fingerprint", lambda: "0" * 16)
    with pytest.raises(PermissionError):
        dryrun.tick(FakeFT(), now=at(2), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)


def test_dryrun_live_feed_refuses_old_dates():
    old = json.dumps([[int(pd.Timestamp("2026-10-30").timestamp()), 1, 2, 1.5, 1.6, 10]]).encode()
    with pytest.raises(PermissionError):
        dryrun.coinbase_open("BTC-USD", date(2026, 10, 30), get=lambda u: old)


def test_walk_cost_on_book():
    book = {"asks": [[101.0, 100.0], [102.0, 100.0]], "bids": [[99.0, 100.0], [98.0, 100.0]]}
    assert dryrun.walk_cost_bp(book, "buy", 10_100.0, 100.0) == pytest.approx(100.0)       # tutto al primo livello
    vwap = 20_300.0 / (100.0 + 100.0)
    assert dryrun.walk_cost_bp(book, "buy", 20_300.0, 100.0) == pytest.approx((vwap - 100) / 100 * 1e4)
    assert dryrun.walk_cost_bp(book, "sell", 9_900.0, 100.0) == pytest.approx(100.0)
    assert dryrun.walk_cost_bp(book, "buy", 1e9, 100.0) is None                              # book troppo sottile


def test_dryrun_report_depth_spread_and_stress(dr):
    sp, lg, _ = dr
    ft = FakeFT()
    for k in (1, 2):
        dryrun.tick(ft, now=at(k), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    rets = {"BTC-USD": pd.Series([0.01, -0.06], index=pd.to_datetime(["2026-12-01", "2026-12-02"])),
            "ETH-USD": pd.Series([0.02, 0.03], index=pd.to_datetime(["2026-12-01", "2026-12-02"]))}
    rep = dryrun.report(log=lg, returns=rets)
    d = rep["depth_cost_by_size"]
    assert d["x1"]["mean_bp"] == pytest.approx(1.0)          # 10.400 USDC entrano nel primo livello (+1 bp)
    assert d["x5"]["mean_bp"] > d["x1"]["mean_bp"] and d["x10"]["book_too_thin"] == 0
    assert rep["spread_bp_mean"] == pytest.approx(2.0)
    assert list(rep["stress"]["stress_days"]) == ["2026-12-02"] and rep["stress"]["limit"] is None
    calm = dryrun.report(log=lg, returns={a: s * 0 for a, s in rets.items()})
    assert calm["stress"]["limit"].startswith("nessun giorno agitato")


def test_missing_book_does_not_invalidate_day(dr):
    sp, lg, _ = dr

    def no_book(asset):
        raise TimeoutError("book non disponibile")

    dryrun.tick(FakeFT(), now=at(1), quote=quote_ok, cb_open=cb_ok, book=no_book, start_path=sp, log=lg)
    c = dryrun.check(now=at(2, minute=0), start_path=sp, log=lg)
    assert c["valid_days"] == 1
    assert dryrun.report(log=lg)["depth_cost_by_size"]["x1"]["no_snapshot"] == 2


def test_dashboard_dryrun_state(dr):
    from desk.web import crypto_dryrun_state
    sp, lg, _ = dr
    ft = FakeFT()
    for k in (1, 2, 3):
        dryrun.tick(ft, now=at(k), quote=quote_ok, cb_open=cb_ok, book=book_ok, start_path=sp, log=lg)
    s = crypto_dryrun_state(now=at(5, minute=0), start_path=sp, log=lg, ft_up=lambda: True)
    assert s["planned"] and s["fingerprint_ok"] and s["state"] == "in corso"
    assert s["valid_days"] == 3 and s["missed_days"] == 1                # 4 dicembre: nessun ordine
    assert [d["status"] for d in s["days"][:5]] == ["ok", "ok", "ok", "missed", "pending"]
    assert s["next_decision"].startswith("2026-12-05T00:05")
    assert s["orders"][0]["day"] == "2026-12-03" and "book" not in s["orders"][0]
    assert s["report"]["orders"] == 6
    assert not crypto_dryrun_state(start_path=sp.parent / "nessuno.json", log=lg, ft_up=lambda: False)["planned"]


# ------------------------------------------------------------ revisione 4: leva, drawdown, liquidità al T-bill

from pulse_mm.research.crypto_trend import robust  # noqa: E402


def test_leverage_check_passes_and_fails(px):
    res = strategy.simulate(px, "BENCH", MODEL, end="2018-06-01")
    s, e = pd.Timestamp("2018-01-01"), pd.Timestamp("2018-06-01")
    ok = robust.leverage_check(res, s, e)
    assert ok["ok"] and ok["max_weight"] <= 1.01 and ok["limit"] == pytest.approx(1.01)
    res.weights.loc["2018-03-01", "BTC-USD"] = 1.02
    bad = robust.leverage_check(res, s, e)
    assert not bad["ok"] and bad["on"] == pd.Timestamp("2018-03-01")


def test_drawdown_measures_on_known_series():
    r = np.r_[np.full(63, 0.0), -0.10, np.full(62, 0.0), 0.5]            # 2 finestre piene + 1 giorno scartato
    assert robust.dd_windows(r) == pytest.approx(0.05)                   # (0 + 0,10) / 2
    flat = np.zeros(10)
    assert robust.mean_dd(flat) == 0.0 and robust.mean_underwater_days(flat) == 0.0
    x = np.r_[-0.5, 0.0, 1.0, 0.1, -0.1, 0.0]                           # sotto il massimo: 2 giorni, poi 2 giorni
    assert robust.mean_underwater_days(x) == pytest.approx(2.0)
    path = np.cumprod(1 + x)
    peak = np.maximum.accumulate(np.r_[1.0, path])[1:]
    assert robust.mean_dd(x) == pytest.approx(np.mean(1 - path / peak))
    assert np.isnan(robust.dd_windows(np.zeros(10)))


def test_paired_bootstrap_metric_is_zero_for_identical_series():
    r = pd.Series(np.random.default_rng(3).normal(0, 0.02, 400))
    out = robust.paired_bootstrap_metric(r, r, robust.dd_windows, n=200)
    assert out["point"] == 0.0 and out["lo"] == 0.0 and out["hi"] == 0.0 and out["seed"] == config.SEED


def test_tbill_parse_and_no_lookahead():
    blob = b"observation_date,DTB3\n2020-01-02,1.50\n2020-01-03,.\n2020-01-06,1.60\n"
    t = robust.tbill_parse(blob)
    assert list(t.index.strftime("%Y-%m-%d")) == ["2020-01-02", "2020-01-06"]
    days = pd.date_range("2020-01-03", "2020-01-07")
    r = robust.daily_cash_rate(t, days)
    assert r["2020-01-03"] == pytest.approx(0.015 / 360)                # valore del 2 gennaio, valido dal 3
    assert r["2020-01-06"] == pytest.approx(0.015 / 360)                # il 6 non usa ancora il valore del 6
    assert r["2020-01-07"] == pytest.approx(0.016 / 360)
    with pytest.raises(ValueError):
        robust.daily_cash_rate(t, pd.date_range("2020-01-01", "2020-01-03"))


def test_tbill_respects_date_lock_and_hashes(tmp_path, monkeypatch):
    with pytest.raises(PermissionError):
        robust.tbill_download("2020-12-01", "2021-01-05", get=lambda u: b"", st="unsigned")
    monkeypatch.setattr(robust, "TB_DIR", tmp_path)
    monkeypatch.setattr(robust, "TB_MANIFEST", tmp_path / "manifest.json")
    blob = b"observation_date,DTB3\n2020-01-02,1.50\n2020-01-03,1.55\n"
    robust.tbill_save("2020-01-01", "2020-01-03", blob)
    assert len(robust.tbill_load(st="unsigned")) == 2
    (tmp_path / "DTB3-FRED_2020-01-01_2020-01-03.csv").write_bytes(blob + b"x")
    with pytest.raises(PermissionError):
        robust.tbill_load(st="unsigned")


def test_simulate_with_cash_rate_reconciles(px):
    base = strategy.simulate(px, "V3", MODEL, end="2018-06-01")
    same = strategy.simulate(px, "V3", MODEL, end="2018-06-01", cash_rate=None)
    pd.testing.assert_series_equal(base.equity, same.equity)
    assert base.interest.abs().max() == 0.0
    rate = pd.Series(0.05 / 360, index=base.equity.index)
    tb = strategy.simulate(px, "V3", MODEL, end="2018-06-01", cash_rate=rate)
    assert tb.interest.iloc[-1] > 0
    assert strategy.reconcile(tb)["ok"]
    assert tb.equity.iloc[-1] > base.equity.iloc[-1]
