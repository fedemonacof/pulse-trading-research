"""Strumenti del test pre-registrato: bootstrap, Deflated Sharpe, filtro a 200 giorni, mix mensile, impronta."""
import numpy as np
import pandas as pd
import pytest

from desk.research import (block_bootstrap_delta_sharpe, deflated_sharpe, faber_filter, fingerprint, monthly_mix,
                           registered_fingerprint)


def returns(mu=0.0004, sd=0.01, n=2000, seed=1):
    idx = pd.bdate_range("2005-01-03", periods=n)
    return pd.Series(np.random.default_rng(seed).normal(mu, sd, n), index=idx)


def test_bootstrap_same_series_is_zero_and_better_series_is_positive():
    r = returns()
    same = block_bootstrap_delta_sharpe(r, r, n=300)
    assert same["delta"] == 0 and same["lo"] == 0 and same["hi"] == 0
    better = block_bootstrap_delta_sharpe(r + 0.001, r, n=300)
    assert better["delta"] > 0 and better["lo"] > 0


def test_deflated_sharpe_penalizes_more_trials():
    r = returns(mu=0.0006)
    one, many = deflated_sharpe(r, 1 + 1), deflated_sharpe(r, 100)
    assert 0 <= many["dsr"] < one["dsr"] <= 1 and many["sr0_annual"] > one["sr0_annual"]
    assert deflated_sharpe(returns(mu=0.0), 8)["dsr"] < 0.95


def test_faber_filter_uses_last_month_signal_only():
    idx = pd.bdate_range("2004-01-01", periods=700)
    close = pd.Series(np.r_[np.linspace(100, 200, 500), np.linspace(200, 120, 200)], index=idx)
    r = faber_filter(close, idx[300:])
    # cambiare i prezzi dopo una data non cambia i rendimenti del filtro prima di quella data
    close2 = close.copy()
    close2.iloc[600:] *= 3
    r2 = faber_filter(close2, idx[300:])
    cut = idx[580]
    pd.testing.assert_series_equal(r[:cut], r2[:cut])
    assert (r.iloc[-20:] == 0).all()                  # a fine discesa il filtro è in liquidità


def test_monthly_mix_with_cash():
    r = returns(n=300)
    mix = monthly_mix(r, pd.Series(0.0, index=r.index), 0.75)
    assert mix.std() == pytest.approx(r.std() * 0.75, rel=0.05)
    assert len(mix) == len(r)


def test_fingerprint_guard():
    """Dopo le decisioni del test il codice è cambiato: `research` deve rifiutarsi di rigirare quel test."""
    assert len(fingerprint()) == 16 and len(registered_fingerprint()) == 16
    assert fingerprint() != registered_fingerprint()
