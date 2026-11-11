"""python -m pulse_st dev | val | fingerprint

dev: controlli di correttezza sul 2005-2014 (lo Sharpe si registra in trials.jsonl ma NON si stampa).
val: una sola esecuzione per variante sul 2015-2019, solo con l'impronta del codice firmata.
Il test 2020-2026 non è eseguibile da qui: si sblocca solo con la validazione firmata.
"""
from __future__ import annotations

import json
import sys

from . import core, trials


def prepare():
    from desk.universe import membership

    p = core.load()
    member = membership("data/sp500/components.csv", p.close.index)
    uni = core.universe(p, member)
    sec = core.sectors(p)
    return p, uni, sec


def correctness(m: dict) -> dict:
    keep = ("entries", "avg_holding_days", "turnover", "days_invested", "days_both_legs_full", "leg_gap_max",
            "beta", "decay_bp", "decay_obs", "decay_cohort", "avg_leg", "breakeven_cost_bp")
    return {k: m[k] for k in keep}


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "dev"
    if cmd == "fingerprint":
        print(f"impronta {trials.fingerprint()} · firmata {trials.registered() or 'non ancora'}")
        return
    if cmd not in ("dev", "val"):
        raise SystemExit(__doc__)
    if cmd == "val":
        trials.require_frozen()
    p, uni, sec = prepare()
    print(f"Universo: {int(uni.sum(axis=1).median())} titoli al giorno (mediana) · serie escluse: {p.dropped}")
    for fam, params in core.VARIANTS:
        if cmd == "val" and trials.runs_on("val", fam, params):
            print(f"{fam} {params}: già eseguita sulla validazione, salto (una sola esecuzione)")
            continue
        m = core.run_variant(p, uni, sec, fam, params, cmd)
        n = trials.record(cmd, fam, params, m)
        shown = correctness(m) if cmd == "dev" else m
        print(f"{fam} {params}: {json.dumps(shown, default=lambda x: round(x, 3) if isinstance(x, float) else x)}")
        if n > trials.N_MAX:
            raise SystemExit(f"N = {n} > {trials.N_MAX}: il test non vale più")


if __name__ == "__main__":
    main(sys.argv[1:])
