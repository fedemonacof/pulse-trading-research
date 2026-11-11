"""Scheduler 24/7 (APScheduler): tick ogni minuto e revisione notturna dopo la chiusura di Wall Street.

Resta bloccato finché SCHEDULER_ENABLED non è true: prima si guarda il backtest, poi si accende.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from .review import nightly_review

log = logging.getLogger("desk.scheduler")


def build_scheduler(engine, settings: Settings, scheduler_cls=BlockingScheduler):
    if not settings.scheduler_enabled:
        raise SystemExit(
            "Lo scheduler è spento. Prima guarda il backtest (python main.py backtest), "
            "poi, se ti convince, metti SCHEDULER_ENABLED=true nel file .env."
        )
    sched = scheduler_cls(timezone="America/New_York")

    def tick():
        try:
            engine.tick()
        except Exception as e:  # un errore non deve spegnere il bot
            log.exception("Errore nel tick")
            engine.notify(f"❗ Errore nel ciclo: {e}")

    def review():
        try:
            engine.maybe_reflect(force=True)
            r = nightly_review(engine.j, settings)
            engine.notify(f"🌙 Revisione notturna: {r['overall'].get('trades', 0)} trade, "
                          f"{'; '.join(r['changes']) or 'pesi invariati'}")
        except Exception:
            log.exception("Errore nella revisione notturna")

    sched.add_job(tick, IntervalTrigger(seconds=settings.tick_seconds), id="tick",
                  max_instances=1, coalesce=True, misfire_grace_time=30)
    sched.add_job(review, CronTrigger(day_of_week="mon-fri", hour=17, minute=15), id="nightly_review",
                  max_instances=1, coalesce=True)
    return sched
