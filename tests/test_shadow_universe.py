"""Universo dell'ombra a regola: top per volume in dollari fra i membri attuali, ricalcolato ogni mese."""
from datetime import timedelta

import pytest

from desk import shadow_universe as su
from test_engine import make


@pytest.fixture
def members(tmp_path, monkeypatch):
    p = tmp_path / "c.csv"
    p.write_text('date,tickers\n2020-01-02,"OLD"\n2026-01-02,"AAA,BBB,CCC,DDD,EEE,FFF,NODATA"\n')
    monkeypatch.setenv("SHADOW_MEMBERS_CSV", str(p))
    monkeypatch.setattr(su, "N_TOP", 3)
    return p


def set_volume(data, vols):
    for s, v in vols.items():
        data.daily[s] = data.daily[s].assign(volume=v)


def test_ranking_by_dollar_volume():
    eng, _, data, _ = make({})
    set_volume(data, {"AAA": 10, "BBB": 1e6, "CCC": 5e5, "DDD": 1})
    top = su.top_by_dollar_volume(data.daily_bars(["AAA", "BBB", "CCC", "DDD"]), n=2)
    assert top == ["BBB", "CCC"]


def test_engine_uses_rule_universe_and_refreshes_monthly(members):
    scores = {"AAA": 90, "BBB": 85, "CCC": 80, "DDD": 75, "EEE": 70, "FFF": 65, "SPY": 0}
    eng, broker, data, clock = make(scores, core=True, satellite_mode="shadow")
    set_volume(data, {"AAA": 1, "BBB": 1, "CCC": 1, "DDD": 9e6, "EEE": 8e6, "FFF": 7e6})
    eng.tick()
    st = eng.j.get("shadow_universe")
    assert st["symbols"] == ["DDD", "EEE", "FFF"] and st["rule"] == su.RULE
    assert set(eng.sat.positions()) == {"DDD", "EEE", "FFF"}       # AAA ha il punteggio più alto ma è fuori regola
    assert set(broker.positions()) == {"SPY"}
    assert list(eng.j.get("shadow_universe_history").values()) == [["DDD", "EEE", "FFF"]]
    modes = {r["mode"] for r in eng.j.rows("SELECT mode FROM equity")}
    assert modes == {eng.s.mode, "SHADOW"}                              # P&L dell'ombra per il report in avanti
    # stesso mese: nessun ricalcolo anche se i volumi cambiano
    set_volume(data, {"AAA": 9e9})
    clock.t += timedelta(minutes=16)
    eng.tick()
    assert eng.j.get("shadow_universe")["symbols"] == ["DDD", "EEE", "FFF"]
    # mese dopo: AAA entra, FFF esce dalla lista ma resta valutato finché è in posizione
    clock.t += timedelta(days=31)
    eng.run_reflex()
    st = eng.j.get("shadow_universe")
    assert st["symbols"] == ["AAA", "DDD", "EEE"]
    assert "FFF" in eng._sat_symbols() and "FFF" in eng.sat.positions()


def test_missing_data_keeps_previous_list(members, monkeypatch):
    monkeypatch.setattr(su, "N_TOP", 100)                              # servirebbero almeno 50 titoli con dati
    eng, _, _, _ = make({"AAA": 90}, core=True, satellite_mode="shadow")
    eng.tick()
    assert eng.j.get("shadow_universe") is None
    assert eng._sat_symbols() == eng.s.satellite_symbols                # ripiego: la lista fissa


def test_rule_off(members, monkeypatch):
    monkeypatch.setenv("SHADOW_UNIVERSE", "fixed")
    eng, _, _, _ = make({"AAA": 90}, core=True, satellite_mode="shadow")
    eng.tick()
    assert eng.j.get("shadow_universe") is None and not eng.shadow_rule
