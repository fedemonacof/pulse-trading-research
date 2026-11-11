"""Filtro a 200 giorni fuori USA: niente look-ahead, tasse italiane semplificate, conteggio operazioni."""
import numpy as np
import pandas as pd
import pytest

from desk.filter_intl import after_tax, filter_returns, one_market, weights


def series(values, start="2000-01-03"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_weights_use_previous_month_only():
    close = series(np.r_[np.linspace(100, 200, 400), np.linspace(200, 100, 300)])
    w = weights(close)
    changed = close.copy()
    changed.iloc[600:] *= 5
    pd.testing.assert_series_equal(w.iloc[:580], weights(changed).iloc[:580])
    assert w.iloc[-1] == 0 and w.iloc[300] == 1


def test_buy_hold_tax_only_on_final_gain():
    r = series([0.0] * 251 + [1.0])                  # raddoppia l'ultimo giorno: 1 anno
    t = after_tax(r, None)
    assert t["final"] == pytest.approx(1 + 1.0 * 0.74)


def test_filter_tax_on_each_gain_and_losses_not_offset():
    r = series([0.10, 0.0, -0.10, 0.0])
    w = series([1, 0, 1, 0])
    t = after_tax(r, w)
    # +10% tassato al 26% all'uscita -> 1.074; poi -10% senza credito d'imposta
    assert t["final"] == pytest.approx(1.074 * 0.9)


def test_one_market_reports_switches_and_decision():
    rng = np.random.default_rng(3)
    close = series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 3000))), start="1990-01-01")
    m = one_market(close, "1990-01-01", "2030-01-01")
    assert m["period"]["years"] > 10 and 0 <= m["invested_share"] <= 1
    assert m["exits_per_year"] >= 0 and isinstance(m["holds"], bool)
    r, w = filter_returns(close)
    assert (r[w == 0].abs() <= 6 / 10_000 + 1e-12).all()   # fuori mercato: solo l'eventuale costo del cambio
