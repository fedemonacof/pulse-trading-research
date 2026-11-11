"""Genera un diario DEMO con settimane di trading simulato, per vedere dashboard e monitor in azione
senza chiavi e senza spendere nulla. Prezzi, report e lezioni sono FINTI e marcati come tali.

    python main.py simulate          -> scrive demo.db
    DB_PATH=demo.db python main.py app
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .agents import CommitteeResult, PortfolioDecision, TargetPosition
from .broker import SimBroker
from .config import DEFAULT_UNIVERSE, Settings
from .data import NewsItem, SimData
from .engine import Engine
from .journal import Journal


class _Clock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class DemoCommittee:
    """Comitato finto: segue il quant_score con un po' di rumore e scrive report di esempio."""

    def __init__(self, rng: np.random.Generator):
        self.rng = rng

    def run(self, snaps, news, portfolio, limits, lessons=None, context=None):
        targets, lines = [], []
        regime = self.rng.choice(["risk-on", "neutro", "risk-off"], p=[0.45, 0.35, 0.2])
        tilt = {"risk-on": 1.0, "neutro": 0.7, "risk-off": 0.35}[regime]
        for s, v in snaps.items():
            score = (v.get("quant_score") or 0) * 0.7 + self.rng.normal(0, 0.2)
            w = float(np.clip(score, -1, 1)) * limits.max_position_pct * tilt
            conf = float(np.clip(0.55 + abs(score) * 0.4, 0, 0.95))
            targets.append(TargetPosition(
                symbol=s, target_weight=round(w, 3), confidence=round(conf, 2),
                thesis=f"[DEMO] {'trend rialzista' if w > 0 else 'debolezza relativa'}, RSI {v['rsi14']}",
                invalidation=f"[DEMO] chiusura {'sotto' if w > 0 else 'sopra'} la SMA50 ({v['sma50']})",
            ))
            lines.append(f"- {s}: stance {score:+.2f}, RSI {v['rsi14']}, quant {v.get('quant_score')}")
        strongest = max(snaps, key=lambda s: snaps[s].get("quant_score") or -9)
        weakest = min(snaps, key=lambda s: snaps[s].get("quant_score") or 9)
        hot = max(snaps, key=lambda s: snaps[s]["rsi14"])
        sw, ww, hv = snaps[strongest], snaps[weakest], snaps[hot]
        macro_txt = {
            "risk-on": "Curva dei rendimenti stabile, VIX sotto la media: il contesto premia il rischio.",
            "neutro": "Settimana con dati sull'inflazione in arrivo: mercato in attesa, volumi sotto la media.",
            "risk-off": "Rendimenti in salita e dollaro forte: pressione sui titoli growth, meglio ridurre.",
        }[regime]
        reports = {
            "tecnico": f"[DEMO] {strongest} ha il trend più pulito (quant {sw.get('quant_score')}, RSI {sw['rsi14']}). "
                       f"{weakest} resta sotto la SMA50 ({ww['sma50']}). {hot} è il più tirato, RSI {hv['rsi14']}.\n" + "\n".join(lines),
            "notizie": f"[DEMO] Nessuna notizia che cambi i fondamentali sulla watchlist. Flussi in uscita su {weakest}.",
            "macro": f"[DEMO] Regime {regime}. {macro_txt}",
            "fondamentale": f"[DEMO] {strongest}: crescita dei ricavi solida, valutazione sopra la media storica. "
                            f"{weakest}: stime degli analisti riviste al ribasso nell'ultimo mese.",
            "dibattito": (
                f"--- Round 1 ---\nRIALZISTA:\n[DEMO] Il trend su {strongest} è intatto e il momentum a 3 mesi è positivo. "
                f"Ridurre adesso vorrebbe dire uscire nel mezzo del movimento.\n\n"
                f"RIBASSISTA:\n[DEMO] {hot} ha RSI {hv['rsi14']}: il rapporto rischio/rendimento per nuovi acquisti è "
                f"peggiorato. {weakest} conferma la debolezza, lo short ha senso finché resta sotto la SMA50."
            ),
            "rischio": f"[DEMO] AGGRESSIVO: aumentare {strongest}.\nNEUTRALE: mantenere i pesi.\n"
                       f"CONSERVATIVO: ridurre l'esposizione prima dei dati macro.\n"
                       f"Esposizione lorda raccomandata: {tilt * 50:.0f}%\nRischi evento: dati sull'inflazione",
        }
        return CommitteeResult(reports, PortfolioDecision(
            market_view=f"[DEMO] Regime {regime}: esposizione {'piena' if tilt == 1 else 'ridotta'}.", targets=targets))

    def reflect(self, trades, lessons):
        pool = [
            "[DEMO] Ridurre le posizioni quando il regime passa a risk-off, prima che scattino gli stop.",
            "[DEMO] Gli short contro un quant_score positivo hanno perso più spesso: evitarli.",
            "[DEMO] Non riaprire subito un titolo appena uscito in trailing stop: aspettare conferma.",
            "[DEMO] Le posizioni con confidence < 0,7 hanno reso meno dei costi: dimensionarle più piccole.",
        ]
        losers = [t for t in trades if t["pnl"] < 0]
        new = pool[len(lessons) % len(pool)] if losers else pool[(len(lessons) + 2) % len(pool)]
        return (lessons + [new])[-8:] if new not in lessons else lessons


class DemoFreeData:
    """Finti dati FRED / calendario / TradingView, con la stessa forma di freedata.FreeData.briefing."""

    def __init__(self, clock: _Clock, symbols: list[str], rng: np.random.Generator):
        self.clock, self.symbols, self.rng = clock, symbols, rng
        self.y10, self.y2, self.vix = 4.6, 4.3, 17.0
        self.earn = {s: int(rng.integers(3, 60)) for s in symbols if s not in ("SPY", "QQQ")}

    def briefing(self, symbols):
        now = self.clock()
        self.y10 += self.rng.normal(0, 0.01)
        self.y2 += self.rng.normal(0, 0.012)
        self.vix = float(np.clip(self.vix + self.rng.normal(0, 0.4), 11, 35))
        start = datetime(2026, 9, 28, tzinfo=timezone.utc)

        def pt(name, v, d):
            return {"nome": name, "valore": round(v, 2), "data": now.date().isoformat(),
                    "var_1s": round(d, 2), "var_1m": round(d * 3, 2)}

        events = [("CPI y/y", 2, 13.5, "3.1%", "3.0%"), ("Unemployment Claims", 1, 13.5, "221K", "218K"),
                  ("FOMC Statement", 6, 19, None, None), ("ECB President Lagarde Speaks", 3, 9.75, None, None)]
        days_in = (now - start).days
        cal = []
        for title, every, hour, fc, prev in events:
            d = now.replace(hour=0, minute=0) + timedelta(days=(every - days_in % every) % every or every, hours=hour)
            cal.append({"quando": d.isoformat(timespec="minutes"), "paese": "EUR" if "ECB" in title else "USD",
                        "evento": title, "impatto": "High" if title.startswith(("CPI", "FOMC")) else "Medium",
                        "previsione": fc, "precedente": prev})
        fund = {}
        for s in symbols:
            left = None
            if s in self.earn:
                left = (self.earn[s] - days_in) % 63
            fund[s] = {"prossima_trimestrale": (now + timedelta(days=left)).date().isoformat() if left is not None else None,
                       "giorni_alla_trimestrale": left, "pe_ttm": None if s in ("SPY", "QQQ") else round(float(self.rng.uniform(18, 45)), 1),
                       "settore": "ETF" if s in ("SPY", "QQQ") else "Tecnologia"}
        return {
            "fonti_non_disponibili": [],
            "macro": {"DGS3MO": pt("Treasury 3 mesi", 4.24, 0.0), "DGS2": pt("Treasury 2 anni", self.y2, -0.03),
                      "DGS10": pt("Treasury 10 anni", self.y10, 0.04), "DFF": pt("Fed funds effettivo", 3.88, 0.0),
                      "VIXCLS": pt("VIX", self.vix, float(self.rng.normal(0, 1))),
                      "curva_10a_2a": round(self.y10 - self.y2, 2)},
            "calendario": sorted(cal, key=lambda e: e["quando"]),
            "fondamentali": fund,
            "notizie": [
                NewsItem(created_at=now - timedelta(minutes=int(self.rng.integers(5, 600))), headline=f"[DEMO] {h}",
                         summary="", source=src, symbols=[sym])
                for sym, h, src in [
                    ("NVDA", "Chipmaker shares swing as investors weigh data-center demand", "Yahoo Finance"),
                    ("AAPL", "Analysts lift price targets ahead of holiday quarter", "Google News"),
                    ("MSFT", "Cloud growth steady, capex guidance in focus", "Yahoo Finance"),
                    ("AMZN", "Retail margins improve as logistics costs ease", "Google News"),
                    ("QQQ", "Tech-heavy index slips as Treasury yields rise", "Yahoo Finance"),
                ] if sym in symbols
            ],
        }


class DemoData(SimData):
    """SimData che aggiunge una barra giornaliera vera a ogni giorno simulato: strategie e regime evolvono."""

    def add_day(self, date, bars: dict[str, tuple[float, float, float, float]]) -> None:
        for sym, (o, h, l, c) in bars.items():
            df = self._daily[sym]
            vol = float(df["volume"].tail(20).mean() * np.random.default_rng(len(df)).uniform(0.7, 1.4))
            self._daily[sym] = pd.concat([df, pd.DataFrame(
                {"open": [o], "high": [h], "low": [l], "close": [c], "volume": [vol]},
                index=[pd.Timestamp(date.date())])])


def simulate(path: str = "demo.db", days: int = 30, seed: int = 11) -> str:
    if os.path.exists(path):
        os.remove(path)
    rng = np.random.default_rng(seed)
    symbols = DEFAULT_UNIVERSE.split(",")
    start = datetime(2026, 9, 28, 13, 30, tzinfo=timezone.utc)
    clock = _Clock(start)
    s = Settings(symbols=symbols, db_path=path, committee_minutes=120, reflex_minutes=30)
    data = DemoData(symbols, seed=seed, days=300)
    for sym in symbols:   # storico finito il giorno prima della simulazione
        df = data._daily[sym]
        data._daily[sym] = df.set_axis(pd.bdate_range(end=start.date() - timedelta(days=3), periods=len(df)))
    broker = SimBroker(100_000, {sym: float(data._daily[sym]["close"].iloc[-1]) for sym in symbols})
    data.overrides.update(broker.prices)
    j = Journal(path, clock=clock)
    j.set("demo", True)
    eng = Engine(s, broker, data, DemoCommittee(rng), j, clock=clock, free=DemoFreeData(clock, symbols, rng))
    vols = {sym: 0.0045 * (1.8 if sym in ("NVDA", "AVGO") else 0.7 if sym in ("SPY", "V", "COST") else 1.0)
            for sym in symbols}
    drift = {sym: rng.normal(0.0002, 0.0005) for sym in symbols}

    day = start
    for _ in range(days):
        while day.weekday() >= 5:
            day += timedelta(days=1)
        broker.start_equity = broker.account().equity     # base della perdita giornaliera
        ohlc = {sym: [broker.prices[sym]] * 4 for sym in symbols}
        for step in range(14):                            # un tick ogni 30 minuti, 6,5 ore
            clock.t = day + timedelta(minutes=30 * step)
            broker.minutes_open = 30 * step               # al primo tick scatta la regola dei 5 minuti
            for sym in symbols:
                prev = broker.prices[sym]
                p = prev * float(np.exp(rng.normal(drift[sym], vols[sym])))
                lo, hi = min(prev, p) * (1 - vols[sym] / 3), max(prev, p) * (1 + vols[sym] / 3)
                broker.set_price(sym, p, low=lo, high=hi)  # il broker esegue gli stop dei bracket
                data.overrides[sym] = broker.prices[sym]
                o = ohlc[sym]
                o[1], o[2], o[3] = max(o[1], hi), min(o[2], lo), broker.prices[sym]
            eng.tick()
        data.add_day(day, {sym: tuple(v) for sym, v in ohlc.items()})
        day += timedelta(days=1)
    return path
