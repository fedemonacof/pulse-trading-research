"""PULSE-ST: blocco del test, niente look-ahead, universo, settori, pesi, costi, conteggio delle prove."""
import json

import numpy as np
import pandas as pd
import pytest

from pulse_st import core, trials

DAYS = pd.bdate_range("2005-01-03", periods=700)


def panel(n=60, seed=0):
    rng = np.random.default_rng(seed)
    etf_r = pd.DataFrame(rng.normal(0.0003, 0.01, (len(DAYS), 10)), index=DAYS, columns=core.SECTOR_ETFS + ["SPY"])
    etf = 100 * (1 + etf_r).cumprod()
    cols = [f"S{i:02d}" for i in range(n)]
    home = [core.SECTOR_ETFS[i % 9] for i in range(n)]
    r = pd.DataFrame({c: etf_r[h] + rng.normal(0, 0.012, len(DAYS)) for c, h in zip(cols, home)}, index=DAYS)
    close = 50 * (1 + r).cumprod()
    open_ = close.shift(1).fillna(close) * (1 + rng.normal(0, 0.003, close.shape))
    vol = pd.DataFrame(rng.integers(1e5, 1e6, close.shape), index=DAYS, columns=cols).astype(float)
    vol.iloc[:, :5] *= 50                                      # i primi 5 sono i più scambiati
    p = core.Panel(open=open_, close=close, volume=vol, etf=etf, spy_open=etf["SPY"])
    return p, dict(zip(cols, home))


def test_test_period_is_locked():
    with pytest.raises(PermissionError):
        core.guard_dates(pd.bdate_range("2019-12-30", "2020-01-02"))
    core.guard_dates(pd.bdate_range("2019-12-02", "2019-12-31"))


def test_universe_top_by_dollar_volume_members_only_no_lookahead(monkeypatch):
    monkeypatch.setattr(core, "TOP_N", 10)
    p, _ = panel()
    member = pd.DataFrame(True, index=DAYS, columns=p.close.columns)
    member.loc[:, "S00"] = False                               # il più scambiato ma non membro
    uni = core.universe(p, member)
    assert not uni["S00"].any() and uni.loc[DAYS[100], ["S01", "S02", "S03", "S04"]].all()
    assert (uni.iloc[70:].sum(axis=1) == 10).all()
    p2, _ = panel()
    p2.volume.iloc[400:] *= 1000 * np.arange(60)[None, :] + 1  # volumi futuri diversi
    uni2 = core.universe(p2, member)
    pd.testing.assert_frame_equal(uni.iloc[:399], uni2.iloc[:399])


def test_sectors_by_correlation_with_hysteresis():
    p, home = panel()
    sec = core.sectors(p)
    last = sec.iloc[-1]
    assert sum(last[c] == h for c, h in home.items()) >= 0.9 * len(home)
    assert sec.iloc[:core.SECTOR_MIN_OBS].isna().all().all()     # niente settore senza 200 giorni di storia


def test_rsi_bounds():
    p, _ = panel()
    r = core.rsi(p.close, 2).iloc[5:]
    assert ((r >= 0) & (r <= 100)).all().all()


def test_weights_neutral_capped_and_max_hold():
    p, _ = panel()
    sec = core.sectors(p)
    uni = pd.DataFrame(True, index=DAYS, columns=p.close.columns)
    rl = core.rules(p, uni, sec, "F1", {"k": 1})
    W, _ = core.weights(rl, sec, uni)
    live = W.iloc[300:]
    lg, sh = live.clip(lower=0).sum(axis=1), -live.clip(upper=0).sum(axis=1)
    assert (abs(lg - sh) < 1e-9).all() and lg.max() <= 1 + 1e-9
    assert live.abs().max().max() <= core.NAME_CAP + 1e-12
    gross = live.abs().sum(axis=1)
    for e in core.SECTOR_ETFS:
        m = sec.iloc[300:] == e
        net = live.where(m, 0).sum(axis=1)
        assert (net.abs() <= core.SECTOR_NET_CAP * gross + 1e-9).all()
    # nessuna posizione dura più di 5 giorni consecutivi con lo stesso segno
    s = np.sign(W.to_numpy())
    run = np.zeros(s.shape[1])
    for t in range(1, len(s)):
        run = np.where((s[t] != 0) & (s[t] == s[t - 1]), run + 1, np.where(s[t] != 0, 1, 0))
        assert run.max() <= core.MAX_HOLD


def test_neutralize_exact_and_only_shrinks():
    rng = np.random.default_rng(9)
    for _ in range(200):
        n = rng.integers(4, 40)
        w = np.where(rng.random(n) < 0.5, 1.0, -1.0) * rng.uniform(0.005, 0.04, n)
        sec = rng.choice(core.SECTOR_ETFS[:4] + [np.nan], n)
        out = core.neutralize(w, sec)
        assert abs(out.sum()) < 1e-9                                       # gambe uguali
        assert (np.abs(out) <= np.abs(w) + 1e-15).all() and (np.sign(out) * np.sign(w) >= 0).all()
        g = np.abs(out).sum()
        for s in set(map(str, sec)):
            m = np.array([str(x) == s for x in sec])
            assert abs(out[m].sum()) <= 0.05 * g + 1e-9


def test_min_leg_flat():
    idx = DAYS[:10]
    cols = list("ABCDEFG")
    el = pd.DataFrame(False, index=idx, columns=cols)
    es = el.copy()
    el.iloc[2, :3] = True                                      # 3 long, 1 short: con min_leg 5 niente posizioni
    es.iloc[2, 3] = True
    rl = core.Rules(el, es, ~el, ~es, min_leg=5)
    sec = pd.DataFrame("XLK", index=idx, columns=cols)
    W, _ = core.weights(rl, sec, pd.DataFrame(True, index=idx, columns=cols))
    assert (W == 0).all().all()


def test_simulate_costs_and_timing():
    idx = DAYS[:6]
    cols = ["A", "B"]
    open_ = pd.DataFrame({"A": [100, 100, 110, 110, 110, 110], "B": [100, 100, 100, 100, 100, 100]},
                         index=idx, dtype=float)
    etf = pd.DataFrame(100.0, index=idx, columns=core.SECTOR_ETFS + ["SPY"])
    p = core.Panel(open=open_, close=open_, volume=open_ * 0 + 1, etf=etf, spy_open=etf["SPY"])
    W = pd.DataFrame(0.0, index=idx, columns=cols)
    W.iloc[0] = [0.5, -0.5]                                    # deciso alla chiusura del giorno 0, eseguito all'apertura 1
    out = core.simulate(p, W, cost_bp=10, borrow=0.0)
    # giorno 1: in mano da apertura 1 ad apertura 2, A +10% -> +5%; costi: entrata 1.0 di turnover x 10 bp
    assert out["gross"].iloc[1] == pytest.approx(0.05)
    assert out["turnover"].iloc[1] == pytest.approx(1.0)
    sells = 0.5 * core.SEC_FEE_BP / 1e4
    assert out["net"].iloc[1] == pytest.approx(0.05 - 0.001 - sells)
    assert out["turnover"].iloc[2] == pytest.approx(1.0)       # uscita il giorno dopo


def test_no_lookahead_end_to_end():
    p, _ = panel()
    sec = core.sectors(p)
    uni = pd.DataFrame(True, index=DAYS, columns=p.close.columns)
    W1, _ = core.weights(core.rules(p, uni, sec, "F3", {"a": 15}), sec, uni)
    p2, _ = panel()
    cut = 500
    for df in (p2.close, p2.open):
        df.iloc[cut:] *= np.linspace(1, 3, len(DAYS) - cut)[:, None]
    sec2 = core.sectors(p2)
    W2, _ = core.weights(core.rules(p2, uni, sec2, "F3", {"a": 15}), sec2, uni)
    pd.testing.assert_frame_equal(W1.iloc[:cut - 1], W2.iloc[:cut - 1])


def test_newey_west_close_to_plain_t_on_iid():
    x = np.random.default_rng(3).normal(0.001, 0.01, 5000)
    plain = x.mean() / (x.std() / np.sqrt(len(x)))
    assert core.newey_west_t(x) == pytest.approx(plain, rel=0.1)


def test_trials_count_and_freeze(tmp_path, monkeypatch):
    path = tmp_path / "t.jsonl"
    trials.record("dev", "F1", {"k": 1}, {}, path)
    assert trials.count(path) == 0                             # lo sviluppo non conta
    trials.record("val", "F1", {"k": 1}, {}, path)
    trials.record("val", "F1", {"k": 1}, {}, path)
    trials.record("val", "F3", {"a": 5}, {}, path)
    assert trials.count(path) == 2 and trials.runs_on("val", "F1", {"k": 1}, path) == 2
    doc = tmp_path / "p.md"
    doc.write_text("- Impronta del codice `pulse_st/` al congelamento:\n")
    monkeypatch.setattr(trials, "PREREG", doc)
    with pytest.raises(PermissionError):
        trials.require_frozen()
    doc.write_text(f"- Impronta del codice `pulse_st/` al congelamento: **`{trials.fingerprint()}`**\n")
    assert trials.require_frozen() == trials.fingerprint()
    doc.write_text("- Impronta del codice `pulse_st/` al congelamento: **`0000000000000000`**\n")
    with pytest.raises(PermissionError):
        trials.require_frozen()


def test_variants_are_the_registered_nine():
    assert len(core.VARIANTS) == trials.N_MAX == 9
    assert {f for f, _ in core.VARIANTS} == {"F1", "F2", "F3"}
    assert json.dumps(core.VARIANTS) == json.dumps(
        [["F1", {"k": 1}], ["F1", {"k": 3}], ["F1", {"k": 5}], ["F2", {"s": 0.8}], ["F2", {"s": 1.0}],
         ["F2", {"s": 1.5}], ["F3", {"a": 5}], ["F3", {"a": 10}], ["F3", {"a": 15}]])


def test_decay_cohort_follows_trade_after_exit():
    idx = DAYS[:12]
    cols = ["A", "B", "C"]
    open_ = pd.DataFrame(100.0, index=idx, columns=cols)
    open_["A"] = 100 * 1.01 ** np.arange(12)                  # A sale dell'1% al giorno
    etf = pd.DataFrame(100.0, index=idx, columns=core.SECTOR_ETFS + ["SPY"])
    p = core.Panel(open=open_, close=open_, volume=open_ * 0 + 1, etf=etf, spy_open=etf["SPY"])
    W = pd.DataFrame(0.0, index=idx, columns=cols)
    W.iloc[2, 0] = 0.5                                        # long su A deciso il giorno 2, tenuto 1 solo giorno
    uni = pd.DataFrame(True, index=idx, columns=cols)
    out = core.decay_cohort(p, W, uni, (str(idx[0].date()), str(idx[-1].date())))
    ex = 0.01 - 0.01 / 3                                      # in eccesso sulla media dell'universo
    for d in range(1, 6):                                     # cumulato anche dopo l'uscita
        assert out["cum_bp"][d - 1] == pytest.approx(d * ex * 1e4, rel=1e-6)
    assert out["dates"][0] == 1
