"""python -m pulse_mm.research.crypto_trend fingerprint | fetch | dev | crosscheck | val | test

fingerprint: impronta del codice e stato della pre-registrazione.
fetch:       scarica le candele Coinbase fino al limite dello stato attuale (prima della firma: 2020-12-31).
dev:         controlli della sezione 9 sul periodo di sviluppo. NON stampa Sharpe, drawdown o rendimenti.
crosscheck:  confronto con il secondo calcolo indipendente (revisione 2), solo scarti.
val, test:   una sola esecuzione, solo con il documento firmato e l'impronta che coincide.
dryrun plan | start AAAA-MM-GG | tick | check | report | smoke
             dry-run del criterio 7 con freqtrade in un processo separato (freqtrade/run_dryrun.py, sotto launchd).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import config, crosscheck, data, dryrun, fx, robust, stats, strategy, trials


def _fmt(x):
    if hasattr(x, "item"):                       # tipi numpy
        x = x.item()
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, (bool, int, str)) or x is None:
        return x
    return str(x)


def show(obj) -> str:
    return json.dumps(obj, default=_fmt, indent=2, ensure_ascii=False)


def fetch() -> None:
    st = trials.stage()
    end = trials.data_limit(st).strftime("%Y-%m-%d")
    have = data.manifest()
    for a in config.ASSETS:
        start = config.FETCH_START
        mine = [k for k in have if k.startswith(a + "_")]
        if mine:
            start = (max(pd.Timestamp(k.split("_")[2][:10]) for k in mine) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if pd.Timestamp(start) > pd.Timestamp(end):
            print(f"{a}: già scaricato fino a {end}")
            continue
        pages = data.download(a, start, end, st=st)
        digest = data.save(a, start, end, pages)
        print(f"{a}: {start} → {end} · sha256 {digest}")
    have_fx = fx.manifest()
    start = config.FETCH_START
    if have_fx:
        start = (max(pd.Timestamp(k.split("_")[2][:10]) for k in have_fx) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if pd.Timestamp(start) <= pd.Timestamp(end):
        digest = fx.save(start, end, fx.download(start, end, st=st))
        print(f"EUR/USD BCE: {start} → {end} · sha256 {digest}")
    have_tb = robust.tbill_manifest()
    start = config.FETCH_START
    if have_tb:
        start = (max(pd.Timestamp(k.split("_")[2][:10]) for k in have_tb) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if pd.Timestamp(start) <= pd.Timestamp(end):
        digest = robust.tbill_save(start, end, robust.tbill_download(start, end, st=st))
        print(f"T-bill 3 mesi FRED DTB3: {start} → {end} · sha256 {digest}")


def checks(px: dict) -> dict:
    """Controlli dei dati: qualità (regola v2) e copertura dal riscaldamento alla fine dello sviluppo."""
    start, end = config.WARMUP_START, config.PERIODS["dev"][1]
    out = {}
    for a, df in px.items():
        sub = df[df.index <= end]
        out[a] = {"impossible_bars": data.quality(sub), "coverage": data.coverage(sub, start, end)}
    return out


def dev() -> None:
    px = data.load()
    dq = checks(px)
    print("Dati (criterio 3):\n" + show(dq))
    print("Cambio BCE per la robustezza in EUR, solo copertura:\n"
          + show(fx.gaps(fx.load(), config.WARMUP_START, config.PERIODS["dev"][1])))
    print("T-bill a 3 mesi per la robustezza della liquidità, solo copertura:\n"
          + show(robust.tbill_gaps(robust.tbill_load(), config.WARMUP_START, config.PERIODS["dev"][1])))
    if any(v["impossible_bars"] for v in dq.values()):
        raise SystemExit("Barre impossibili: il test si ferma (regola v2)")
    s, e = config.PERIODS["dev"]
    model = strategy.cost_model(provisional=config.TAKER_BP is None)
    report = {"taker_bp": model.fee_bp, "taker_provisional": config.TAKER_BP is None}
    for name in (config.MAIN, "BENCH"):
        res = strategy.simulate(px, name, model, end=e)
        report[name] = {
            "reconcile_costs (criterio 4)": strategy.reconcile(res),
            "turnover (criterio 5)": strategy.turnover(res, s, e),
            "costs_bp_of_notional": strategy.costs_in_period(res, s, e),
            "avg_weight": strategy.avg_exposure(res, s, e),
        }
        report[name]["lookahead_truncation (revisione 2)"] = strategy.truncation_check(px, name, model, "2019-06-30", e)
        report[name]["leverage (revisione 4)"] = robust.leverage_check(res, s, e)
        trials.record("dev", name, report[name])
    print("Sviluppo 2018-2020, solo controlli (nessuna metrica di rendimento):\n" + show(report))


def evaluate(sample: str) -> None:
    trials.require_frozen()
    if sample == "test" and trials.stage() != "test":
        raise PermissionError("Il test si apre solo dopo una validazione passata")
    if trials.runs_on(sample, config.MAIN):
        raise SystemExit(f"{sample}: già eseguito (una sola esecuzione)")
    px = data.load()
    s, e = config.PERIODS[sample]
    for a, df in px.items():
        bad = data.quality(df[df.index <= e])
        if bad:
            raise SystemExit(f"{a}: barre impossibili {bad[:5]}: il test si ferma")
    cov = {a: data.coverage(df[df.index <= e], s, e) for a, df in px.items()}
    usd_per_eur = fx.load()
    fx_cov = fx.gaps(usd_per_eur, s, e)
    model = strategy.cost_model()
    runs = {k: strategy.simulate(px, k, model, end=e) for k in (config.MAIN, "BENCH", "V1")}
    lev = {k: robust.leverage_check(v, s, e) for k, v in runs.items()}
    if not all(x["ok"] for x in lev.values()):
        raise SystemExit(f"Leva oltre {1 + robust.LEV_TOL:.2f} (revisione 4): il calcolo non si riporta. {lev}")
    tbill = robust.tbill_load()
    tb_cov = robust.tbill_gaps(tbill, s, e)
    r = {k: v.returns(s, e) for k, v in runs.items()}
    boot = stats.paired_bootstrap(r[config.MAIN], r["BENCH"])
    verdict = stats.outcome(boot)
    if not all(c["ok"] for c in cov.values()) and verdict != "fallisce":
        verdict = "non concludente"   # copertura insufficiente: vale solo un esito negativo
    stress = {k: strategy.simulate(px, k, model, end=e, stress=config.COST_STRESS_SENSITIVITY).returns(s, e)
              for k in (config.MAIN, "BENCH")}
    rp = {k: strategy.simulate(px, k, model, end=e, split="risk_parity") for k in (config.MAIN, "BENCH")}
    r_rp = {k: v.returns(s, e) for k, v in rp.items()}
    r_eur = {k: fx.returns_eur(runs[k], usd_per_eur, s, e) for k in (config.MAIN, "BENCH")}
    rate = robust.daily_cash_rate(tbill, runs[config.MAIN].equity.index)
    tb = {k: strategy.simulate(px, k, model, end=e, cash_rate=rate) for k in (config.MAIN, "BENCH")}
    r_tb = {k: v.returns(s, e) for k, v in tb.items()}
    expo = robust.exposure_ratio(runs[config.MAIN], runs["BENCH"], s, e)
    r_bk = robust.scaled_benchmark(r["BENCH"], expo["k"])
    out = {
        "outcome": verdict,
        "coverage": cov,
        "main": {"strategy": stats.summary(r[config.MAIN]), "benchmark": stats.summary(r["BENCH"]),
                 "bootstrap_21": boot, "dsr": stats.deflated_sharpe(r[config.MAIN]),
                 "reconcile": strategy.reconcile(runs[config.MAIN]),
                 "turnover": strategy.turnover(runs[config.MAIN], s, e), "leverage": lev},
        "robustness (senza soglie)": {
            "bootstrap_63": stats.paired_bootstrap(r[config.MAIN], r["BENCH"], block=config.BOOT_BLOCK_ROBUST),
            "costs_x3": {"strategy": stats.summary(stress[config.MAIN]), "benchmark": stats.summary(stress["BENCH"])},
            "V1_s252_only": stats.summary(r["V1"]),
            "eur (cambio BCE)": {"fx_coverage": fx_cov,
                                 "strategy": stats.summary(r_eur[config.MAIN]),
                                 "benchmark": stats.summary(r_eur["BENCH"]),
                                 "bootstrap_21": stats.paired_bootstrap(r_eur[config.MAIN], r_eur["BENCH"])},
            "risk_parity (1/σ63 al riallineamento)": {
                "strategy": stats.summary(r_rp[config.MAIN]), "benchmark": stats.summary(r_rp["BENCH"]),
                "bootstrap_21": stats.paired_bootstrap(r_rp[config.MAIN], r_rp["BENCH"]),
                "reconcile": strategy.reconcile(rp[config.MAIN])},
            "drawdown (revisione 4)": {
                "strategy": robust.dd_profile(r[config.MAIN]), "benchmark": robust.dd_profile(r["BENCH"]),
                "dd_windows_63_diff": robust.paired_bootstrap_metric(r[config.MAIN], r["BENCH"], robust.dd_windows)},
            "benchmark_same_exposure (revisione 5)": {
                **expo, "strategy": stats.summary(r[config.MAIN]), "benchmark_scaled": stats.summary(r_bk),
                "bootstrap_21": stats.paired_bootstrap(r[config.MAIN], r_bk)},
            "cash_tbill_3m (revisione 4)": {
                "coverage": tb_cov, "strategy": stats.summary(r_tb[config.MAIN]),
                "benchmark": stats.summary(r_tb["BENCH"]),
                "bootstrap_21": stats.paired_bootstrap(r_tb[config.MAIN], r_tb["BENCH"]),
                "reconcile": strategy.reconcile(tb[config.MAIN])},
        },
    }
    trials.record(sample, config.MAIN, out, outcome=verdict)
    print(show(out))


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "fingerprint"
    if cmd == "fingerprint":
        print(f"impronta {trials.fingerprint()} · firmata {trials.registered() or 'non ancora'} · "
              f"stato {trials.stage()} · dati fino a {trials.data_limit(trials.stage()).date()}")
    elif cmd == "fetch":
        fetch()
    elif cmd == "dev":
        dev()
    elif cmd == "crosscheck":
        print(show(crosscheck.run()))
    elif cmd in ("val", "test"):
        evaluate(cmd)
    elif cmd == "dryrun":
        sub = argv[1] if len(argv) > 1 else "plan"
        if sub == "plan":
            print(show(dryrun.plan(datetime.now(timezone.utc).date() + timedelta(days=1))))
        elif sub == "start":
            print(show(dryrun.start(argv[2])))
        elif sub == "tick":
            print(show(dryrun.tick(dryrun.client_or_none())))
            dryrun.fill_coinbase()
        elif sub == "check":
            dryrun.fill_coinbase()
            print(show(dryrun.check()))
        elif sub == "report":
            c = dryrun.check()
            if c["state"] != "completo":
                raise SystemExit(f"Dry-run {c['state']}: il resoconto si legge solo a dry-run completo")
            p = dryrun.load_start()
            d0 = datetime.fromisoformat(p["start"]).date()
            d1 = datetime.fromisoformat(c["last_checked"]).date()
            rets = {a: dryrun.coinbase_returns(a, d0, d1) for a in config.ASSETS}
            print(show(dryrun.report(returns=rets)))
        elif sub == "smoke":
            print(show(dryrun.smoke(dryrun.client_from_env())))
        else:
            raise SystemExit(__doc__)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
