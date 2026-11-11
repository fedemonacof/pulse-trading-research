"""Confronto con il secondo calcolo indipendente (revisione 2, criterio 6).

Il secondo calcolo (checks/crypto_trend_independent.py) è scritto senza vedere questo codice e scrive i suoi
scambi e la sua equity in checks/out/. Qui si confrontano, sul periodo di sviluppo:
- scambio per scambio: stesse date e asset, peso dopo lo scambio entro 0,1 punti, costo entro 0,01 bp del capitale;
- rendimento annualizzato: scarto entro 5 bp all'anno. Si stampa solo lo scarto, mai i rendimenti.
"""
from __future__ import annotations

import pandas as pd

from . import config, data, strategy

OUT = config.ROOT / "checks" / "out"
W_TOL = 0.001          # 0,1 punti percentuali di peso
COST_TOL = 1e-6        # 0,01 bp del capitale
RET_TOL_BP = 5.0       # bp all'anno


def load_independent(name: str) -> tuple[pd.DataFrame, pd.Series]:
    tr = pd.read_csv(OUT / f"independent_trades_{name}.csv", parse_dates=["date"])
    eq = pd.read_csv(OUT / f"independent_equity_{name}.csv", parse_dates=["date"]).set_index("date")["equity"]
    return tr, eq


def compare(name: str, px: dict, model) -> dict:
    s, e = config.PERIODS["dev"]
    res = strategy.simulate(px, name, model, end=e)
    mine = pd.DataFrame(res.trades)
    mine = mine[(mine.date >= s) & (mine.date <= e)].copy()
    theirs, eq_i = load_independent(name)
    theirs = theirs[(theirs.date >= s) & (theirs.date <= e)].copy()
    mine["cost_share"] = mine["cost"] / res.equity.reindex(mine["date"]).to_numpy()
    theirs["cost_share"] = theirs["cost"] / eq_i.reindex(theirs["date"]).to_numpy()
    m = mine.merge(theirs, on=["date", "asset"], how="outer", suffixes=("_pulse", "_ind"), indicator=True)
    both = m[m["_merge"] == "both"]
    w_diff = (both["weight_after_pulse"] - both["weight_after_ind"]).abs()
    c_diff = (both["cost_share_pulse"] - both["cost_share_ind"]).abs()
    bad = both[(w_diff > W_TOL) | (c_diff > COST_TOL)]
    r_p = res.equity.pct_change()
    r_i = eq_i.pct_change()
    sl = lambda r: r[(r.index >= s) & (r.index <= e)].fillna(0.0)
    diff_bp = abs(sl(r_p).mean() - sl(r_i).mean()) * config.ANN * 1e4
    only_p = m[m["_merge"] == "left_only"][["date", "asset", "weight_after_pulse"]]
    only_i = m[m["_merge"] == "right_only"][["date", "asset", "weight_after_ind"]]
    ok = only_p.empty and only_i.empty and bad.empty and diff_bp <= RET_TOL_BP
    return {
        "trades_pulse": len(mine), "trades_independent": len(theirs), "matched": len(both),
        "only_pulse": [(d.strftime("%Y-%m-%d"), a, round(w, 4)) for d, a, w in only_p.itertuples(index=False)][:15],
        "only_independent": [(d.strftime("%Y-%m-%d"), a, round(w, 4)) for d, a, w in only_i.itertuples(index=False)][:15],
        "max_weight_diff_pts": float(w_diff.max() * 100) if len(both) else None,
        "max_cost_diff_bp": float(c_diff.max() * 1e4) if len(both) else None,
        "mismatches": [(r.date.strftime("%Y-%m-%d"), r.asset, round(r.weight_after_pulse, 4), round(r.weight_after_ind, 4))
                       for r in bad.itertuples()][:15],
        "annual_return_gap_bp": float(diff_bp),
        "ok": bool(ok),
    }


def run() -> dict:
    px = data.load()
    model = strategy.cost_model(provisional=config.TAKER_BP is None)
    return {name: compare(name, px, model) for name in (config.MAIN, "BENCH")}
