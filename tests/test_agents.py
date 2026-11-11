"""Comitato AI (API Claude simulata), dati gratuiti (rete simulata), Telegram."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from desk.agents import (AnalystReport, Committee, Lessons, PortfolioDecision, RiskReview, SymbolView,
                         TargetPosition)
from desk.config import Settings
from desk.journal import Journal
from desk.telegram import Telegram

def decision(**weights):
    return PortfolioDecision(market_view="test", targets=[
        TargetPosition(symbol=s, target_weight=w, confidence=0.9, thesis=f"tesi {s}", invalidation="i")
        for s, w in weights.items()
    ])


def test_telegram_ignores_other_chats():
    j = Journal(":memory:")
    tg = Telegram("token", "42", j)
    tg._call = MagicMock(return_value={"result": [
        {"update_id": 1, "message": {"chat": {"id": 999}, "text": "/kill CONFERMA"}}]})
    tg.send = MagicMock()
    tg.poll_once()
    assert not j.get("kill_requested") and not tg.send.called


def _mock_client(text="ok", stop="end_turn"):
    client = MagicMock()
    seen = []

    def parse(**kw):
        seen.append(kw)
        schema = kw["output_format"]
        assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
        assert kw["thinking"] == {"type": "adaptive"} and kw["model"] == "claude-opus-5-5"
        out = {
            AnalystReport: AnalystReport(summary="ok", views=[SymbolView(symbol="AAA", stance=0.5, confidence=0.7, rationale="r")]),
            RiskReview: RiskReview(aggressive="a", neutral="n", conservative="c", recommended_gross_exposure=0.6, event_risks=["CPI"]),
            PortfolioDecision: decision(AAA=0.07),
            Lessons: Lessons(lessons=["l1"]),
        }[schema]
        return SimpleNamespace(stop_reason=stop, parsed_output=None if stop == "refusal" else out)

    client.beta.messages.parse.side_effect = parse
    final = SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])
    client.beta.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = final
    return client, seen


def test_committee_full_pipeline():
    s = Settings(symbols=["AAA"], debate_rounds=2)
    client, seen = _mock_client("report")
    res = Committee(s, client=client).run({"AAA": {"price": 1}}, [], {}, s.risk, lessons=["evita gli earnings"])
    assert res.decision.targets[0].target_weight == 0.07
    assert set(res.reports) == {"tecnico", "notizie", "macro", "fondamentale", "dibattito", "rischio"}
    assert "Round 2" in res.reports["dibattito"] and "CPI" in res.reports["rischio"]
    # macro + fondamentale con web search, 2 round x 2 ricercatori senza
    calls = client.beta.messages.stream.call_args_list
    assert len(calls) == 6
    assert sum(1 for c in calls if c.kwargs["tools"]) == 2
    assert calls[0].kwargs["tools"][0]["type"] == "web_search_20260209" or calls[1].kwargs["tools"]
    manager_prompt = [k for k in seen if k["output_format"] is PortfolioDecision][0]["messages"][0]["content"]
    assert "evita gli earnings" in manager_prompt and "PANEL DI RISCHIO" in manager_prompt


def test_committee_refusal_returns_no_decision():
    s = Settings(symbols=["AAA"])
    client, _ = _mock_client(stop="refusal")
    res = Committee(s, client=client).run({"AAA": {"price": 1}}, [], {}, s.risk)
    assert res.decision is None


def test_reflect_returns_lessons():
    s = Settings(symbols=["AAA"])
    client, _ = _mock_client()
    assert Committee(s, client=client).reflect([{"symbol": "AAA", "pnl": -10}], []) == ["l1"]


def _fake_web(fail=()):
    now = datetime.now(timezone.utc)
    rss = (f'<rss><channel><item><title>NVDA beats estimates</title><pubDate>{now:%a, %d %b %Y %H:%M:%S} +0000</pubDate>'
           '<description>&lt;b&gt;Strong&lt;/b&gt; quarter</description></item>'
           f'<item><title>NVDA Beats Estimates!</title><pubDate>{now:%a, %d %b %Y %H:%M:%S} +0000</pubDate></item>'
           '</channel></rss>').encode()
    fred = b"observation_date,DGS10\n" + b"\n".join(f"2026-10-{d:02d},{4 + d / 100}".encode() for d in range(1, 30)) + b"\n2026-10-30,."
    soon = (now + timedelta(days=2)).isoformat()
    far = (now + timedelta(days=30)).isoformat()
    cal = json.dumps([
        {"title": "CPI y/y", "country": "USD", "date": soon, "impact": "High", "forecast": "3.1%", "previous": "3.0%"},
        {"title": "Retail Sales", "country": "GBP", "date": soon, "impact": "High"},
        {"title": "Bank Holiday", "country": "USD", "date": soon, "impact": "Holiday"},
        {"title": "FOMC", "country": "USD", "date": far, "impact": "High"},
    ]).encode()
    tv = json.dumps({"data": [{"s": "NASDAQ:NVDA", "d": [int((now + timedelta(days=6)).timestamp()), 2.47, 21.3, 4.07e12,
                                                          "Electronic Technology", 1.8, 0.03]}]}).encode()

    def fetch(url, data=None, headers=None):
        for f in fail:
            if f in url:
                raise TimeoutError(f"{f} giù")
        if "yahoo" in url or "news.google" in url:
            return rss
        if "fred" in url:
            assert "Mozilla" not in headers["User-Agent"]   # FRED rifiuta gli UA da browser
            return fred
        if "faireconomy" in url:
            return cal
        if "tradingview" in url:
            assert b"NYSE:NVDA" in data and headers["Referer"].startswith("https://www.tradingview.com")
            return tv
        raise AssertionError(url)

    return fetch


def test_freedata_sources():
    import json as _j  # noqa: F401
    from desk.freedata import FreeData

    f = FreeData(fetch=_fake_web())
    news = f.news(["NVDA"])
    assert len(news) == 1 and news[0].symbols == ["NVDA"] and news[0].summary == "Strong quarter"   # doppione tolto
    m = f.macro()
    assert m["DGS10"]["valore"] == pytest.approx(4.29) and m["DGS10"]["var_1s"] == pytest.approx(0.05)
    cal = f.calendar()
    assert [e["evento"] for e in cal] == ["CPI y/y"]          # solo USD/EUR, impatto alto/medio, entro 7 giorni
    fund = f.fundamentals(["NVDA"])
    assert fund["NVDA"]["giorni_alla_trimestrale"] in (5, 6) and fund["NVDA"]["capitalizzazione_mld"] == 4070.0


def test_freedata_fallback_and_partial_failure():
    from desk.freedata import FreeData

    f = FreeData(fetch=_fake_web(fail=("yahoo", "tradingview")))
    b = f.briefing(["NVDA"])
    assert b["notizie"] and b["notizie"][0].source == "Google News"   # Yahoo giù -> Google News
    assert b["fondamentali"] == {} and b["fonti_non_disponibili"] == ["fondamentali"]
    assert b["calendario"] and b["macro"]["DGS10"]["valore"]


def test_freedata_cache():
    from desk.freedata import FreeData

    calls = []
    fetch = _fake_web()
    f = FreeData(fetch=lambda u, d=None, h=None: calls.append(u) or fetch(u, d, h))
    f.calendar()
    f.calendar()
    assert len(calls) == 2


def test_committee_uses_official_data_and_fewer_searches():
    s = Settings(symbols=["NVDA"])
    client, seen = _mock_client("report")
    ctx = {"macro": {"DGS10": {"valore": 4.88}}, "calendario": [{"evento": "CPI y/y"}],
           "fondamentali": {"NVDA": {"prossima_trimestrale": "2026-11-17"}}}
    Committee(s, client=client).run({"NVDA": {"price": 1}}, [], {}, s.risk, context=ctx)
    web_calls = [c.kwargs for c in client.beta.messages.stream.call_args_list if c.kwargs["tools"]]
    assert sorted(c["tools"][0]["max_uses"] for c in web_calls) == [3, 4]
    prompts = " ".join(c["messages"][0]["content"] for c in web_calls)
    assert "4.88" in prompts and "DATI UFFICIALI" in prompts
    risk_prompt = [k for k in seen if k["output_format"] is RiskReview][0]["messages"][0]["content"]
    assert "2026-11-17" in risk_prompt and "CPI y/y" in risk_prompt
