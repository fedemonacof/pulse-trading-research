"""PULSE // agente autonomo su azioni ed ETF USA (Alpaca, paper per default) — comandi:

  python main.py backtest [yahoo|alpaca] [anni]  backtest walk-forward contro SPY (default: yahoo, 2 anni)
  python main.py run          avvia lo scheduler 24/7 (solo con SCHEDULER_ENABLED=true, dopo il backtest)
  python main.py once         un giro completo: comitato + riflesso, poi esce
  python main.py app [porta]  command center su http://127.0.0.1:8000 (DB_PATH=demo.db per i dati demo)
  python main.py status       conto, posizioni e ultime decisioni
  python main.py review       revisione notturna adesso: report in reports/, pesi entro limiti fissi
  python main.py reflect      il comitato rilegge i trade chiusi e aggiorna le lezioni
  python main.py kill         KILL SWITCH: cancella tutti gli ordini, chiude tutte le posizioni, si ferma
  python main.py resume       riattiva il bot dopo il kill switch
  python main.py monitor      monitor live nel terminale
  python main.py research     test pre-registrato 2005-2019 (docs/preregistrazione-2005-2019.md)
  python main.py universe     test pre-registrato sull'S&P 500 storico (docs/preregistrazione-universo.md)
  python main.py filter       test pre-registrato del filtro a 200 giorni fuori USA (docs/preregistrazione-filtro.md)
  python main.py forward      report mensile della fase in avanti (docs/preregistrazione-avanti.md)
  python main.py fingerprint  verifica che il codice che decide i trade sia quello congelato
  python main.py simulate     crea demo.db: 6 settimane di trading finto per provare la dashboard
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from desk.config import load_settings
from desk.journal import Journal


def build(settings, journal: Journal | None = None):
    from desk.agents import Committee
    from desk.broker import AlpacaBroker
    from desk.data import AlpacaData
    from desk.engine import Engine
    from desk.freedata import FreeData
    from desk.telegram import Telegram

    j = journal or Journal(settings.db_path)
    tg = Telegram(settings.telegram_token, settings.telegram_chat_id, j) \
        if settings.telegram_token and settings.telegram_chat_id else None
    eng = Engine(
        settings,
        AlpacaBroker(settings.alpaca_key, settings.alpaca_secret, settings.live),
        AlpacaData(settings.alpaca_key, settings.alpaca_secret),
        Committee(settings) if settings.use_committee else None,
        j,
        notifier=tg,
        free=FreeData() if settings.free_data else None,
    )
    return eng, tg


def backtest(settings, source: str, years: int) -> dict:
    from desk.backtest import format_report, walk_forward
    from desk.histdata import AlpacaHistory, YahooHistory

    syms = list(dict.fromkeys(settings.symbols + ["SPY"]))
    hist = AlpacaHistory(settings.alpaca_key, settings.alpaca_secret) if source == "alpaca" else YahooHistory()
    # +1 anno di riscaldamento: la media a 200 giorni e i 6 mesi di scelta dei parametri
    daily = hist.daily(syms, years=years + 2)
    print(f"Fonte dati: {source} · {len(daily)} titoli · {years} anni fuori campione\n")
    r = walk_forward(daily, settings.risk, years=years)
    text = format_report(r)
    print(text)
    os.makedirs(settings.reports_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    base = os.path.join(settings.reports_dir, f"backtest-{source}-{stamp}")
    with open(base + ".json", "w") as f:
        json.dump({**r, "source": source}, f, default=str)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(f"# Backtest PULSE ({source})\n\n```\n{text}\n```\n")
    Journal(settings.db_path).set("last_backtest", {k: r[k] for k in (
        "period", "costs", "strategy", "spy", "spy_same_exposure", "trades", "by_strategy", "calibration",
        "vetoes", "beats_spy", "verdict", "windows", "core", "active")} | {"source": source, "equity": r["equity"],
                                                          "spy_equity": r["spy_equity"]})
    print(f"\nReport salvato in {base}.md e .json")
    return r


def status(settings) -> None:
    eng, _ = build(settings)
    j = eng.j
    acc = eng.broker.account()
    print(f"Modalità {settings.mode} | equity {acc.equity:,.2f} $ | cash {acc.cash:,.2f} $ | "
          f"oggi {acc.equity / acc.last_equity - 1:+.2%} | kill switch={j.get('halted', False)} | "
          f"pausa di sessione={eng.session_paused()}")
    for p in eng.broker.positions().values():
        print(f"  {p.symbol:5s} qty {p.qty:+8.2f}  carico {p.avg_price:9.2f}  P/L {p.unrealized_pl:+10.2f}")
    for d in j.rows("SELECT ts, symbol, verdict, confidence, reason, veto FROM decisions ORDER BY ts DESC LIMIT 10"):
        print(f"  {d['ts'][11:16]} {d['symbol']:5s} {d['verdict']:5s} {d['confidence']:5.1f}  "
              f"{d['veto'] or d['reason']}")
    pnl = j.db_query("SELECT COUNT(*), SUM(pnl), AVG(pnl > 0) FROM closed_trades")[0]
    if pnl[0]:
        print(f"\nTrade chiusi: {pnl[0]} | P/L realizzato {pnl[1]:+,.2f} $ | in profitto {pnl[2]:.0%}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    if cmd == "simulate":
        from desk.simulate import simulate

        logging.getLogger("desk").setLevel(logging.WARNING)
        path = simulate()
        print(f"Diario demo scritto in {path}. Aprilo con:\n  DB_PATH={path} .venv/bin/python main.py app")
        return
    if cmd == "app":
        from desk.web import serve

        port = int(args[1]) if len(args) > 1 else 8000
        print(f"PULSE command center su http://127.0.0.1:{port}  (Ctrl+C per chiudere)")
        return serve(port)
    settings = load_settings()
    if cmd == "backtest":
        source = next((a for a in args[1:] if a in ("yahoo", "alpaca")), "yahoo")
        years = next((int(a) for a in args[1:] if a.isdigit()), 2)
        backtest(settings, source, years)
    elif cmd == "run":
        from desk.scheduler import build_scheduler

        if not settings.scheduler_enabled:
            build_scheduler(None, settings)   # esce col messaggio, prima di collegarsi al broker
        eng, tg = build(settings)
        if tg:
            tg.start_polling()
        sched = build_scheduler(eng, settings)
        eng.notify(f"▶️ PULSE avviato ({settings.mode}) su {', '.join(settings.symbols)}")
        sched.start()
    elif cmd == "once":
        eng, _ = build(settings)
        if eng.committee is not None:
            eng.run_committee()
        eng.run_reflex()
    elif cmd == "status":
        status(settings)
    elif cmd == "fingerprint":
        from desk.research import fingerprint, registered_fingerprint

        fp, reg = fingerprint(), registered_fingerprint()
        print(f"impronta attuale {fp} · pre-registrata {reg} · {'OK, codice congelato' if fp == reg else 'DIVERSA'}")
    elif cmd == "research":
        from desk.research import fingerprint, registered_fingerprint, report, run, yahoo_between

        fp, reg = fingerprint(), registered_fingerprint()
        if fp != reg:
            raise SystemExit(f"Il codice che decide i trade è cambiato ({fp} invece di {reg}): il test pre-registrato "
                             "non vale più. Serve una nuova pre-registrazione.")
        syms = list(dict.fromkeys(settings.symbols + ["SPY"]))
        daily = yahoo_between(syms, "2003-06-01", "2020-01-01")
        print(f"Dati 2003-2019: {len(daily)} titoli · impronta {fp} OK\n")
        out = run(daily)
        text = report(out)
        print(text)
        os.makedirs("docs", exist_ok=True)
        with open("docs/risultati-2005-2019.md", "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(settings.reports_dir, "risultati-2005-2019.json"), "w") as f:
            json.dump(out, f, default=str, indent=1)
    elif cmd == "universe":
        from desk.research import fingerprint, registered_fingerprint
        from desk.universe import PREREG, load_cache, membership, report, run, test_fingerprint

        fp, reg = test_fingerprint(), registered_fingerprint(PREREG)
        if fp != reg:
            raise SystemExit(f"Il codice del test è cambiato ({fp} invece di {reg}): serve una nuova pre-registrazione.")
        daily = load_cache()
        member = membership("data/sp500/components.csv", daily["SPY"].index)
        print(f"Dati: {len(daily)} serie · impronta {fp} OK · codice congelato {fingerprint()}\n")
        out = run(daily, member)
        text = report(out)
        print(text)
        with open("docs/risultati-universo.md", "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(settings.reports_dir, "risultati-universo.json"), "w") as f:
            json.dump(out, f, default=str, indent=1)
    elif cmd == "filter":
        from desk.filter_intl import MARKETS, PREREG, report, run, test_fingerprint
        from desk.research import registered_fingerprint, yahoo_between

        fp, reg = test_fingerprint(), registered_fingerprint(PREREG)
        if fp != reg:
            raise SystemExit(f"Il codice del test è cambiato ({fp} invece di {reg}): serve una nuova pre-registrazione.")
        data = yahoo_between(list(MARKETS), "1949-01-01", "2026-11-01")
        print(f"Dati: {', '.join(f'{s} {len(d)}' for s, d in data.items())} · impronta {fp} OK\n")
        out = run({s: d["close"] for s, d in data.items()})
        text = report(out)
        print(text)
        with open("docs/risultati-filtro.md", "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(settings.reports_dir, "risultati-filtro.json"), "w") as f:
            json.dump(out, f, default=str, indent=1)
    elif cmd == "forward":
        import pandas as pd

        from desk.forward import report as forward_report
        from desk.forward import run as forward_run
        from desk.research import yahoo_between

        j = Journal(settings.db_path)
        first = j.db_query("SELECT MIN(ts) FROM equity WHERE mode != 'SHADOW'")[0][0]
        if not first:
            raise SystemExit("Il diario non ha ancora dati di equity: il report si fa dopo l'avvio del paper trading.")
        hist = j.get("shadow_universe_history") or {}
        syms = {s for v in hist.values() for s in v} | {"SPY", "QQQ", "IWM"} | set(settings.symbols)
        syms |= {r[0] for r in j.db_query("SELECT DISTINCT symbol FROM votes")}
        syms |= {r[0] for r in j.db_query("SELECT DISTINCT symbol FROM closed_trades WHERE mode='SHADOW'")}
        start = (pd.Timestamp(first[:10]) - pd.Timedelta(days=500)).date().isoformat()
        end = (pd.Timestamp.now() + pd.Timedelta(days=1)).date().isoformat()
        raw = yahoo_between([s.replace(".", "-") for s in sorted(syms)], start, end)
        daily = {s.replace("-", "."): d for s, d in raw.items()}
        print(f"Dati: {len(daily)} serie su {len(syms)} · dal {start}\n")
        out = forward_run(j, daily, settings.model, fixed=settings.satellite_symbols)
        text = forward_report(out)
        print(text)
        name = f"forward-{out['period']['to'][:7]}"
        os.makedirs(settings.reports_dir, exist_ok=True)
        with open(os.path.join(settings.reports_dir, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(settings.reports_dir, f"{name}.json"), "w") as f:
            json.dump(out, f, default=str, indent=1)
    elif cmd == "review":
        from desk.review import nightly_review

        r = nightly_review(Journal(settings.db_path), settings)
        print(open(r["path"], encoding="utf-8").read())
    elif cmd == "monitor":
        from desk.monitor import run

        run(settings.db_path)
    elif cmd == "reflect":
        eng, _ = build(settings)
        eng.maybe_reflect(force=True)
        print("\n".join(f"• {l}" for l in eng.j.get("lessons", [])) or "Nessun trade chiuso da analizzare.")
    elif cmd == "kill":
        build(settings)[0].halt("kill switch da riga di comando")
        print("Ordini cancellati, posizioni chiuse, bot fermo.")
    elif cmd == "resume":
        j = Journal(settings.db_path)
        j.set("halted", False)
        j.set("satellite_halted", False)
        j.set("satellite_peak", None)
        print("Bot riattivato (kill switch e satellite).")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
