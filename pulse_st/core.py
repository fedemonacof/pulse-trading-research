"""PULSE-ST: reversal market neutral a 1-5 giorni (docs/prereg-pulse-st-v1.md, firmata il 2026-11-11).

Tutto è su tabelle larghe (giorni × titoli). Ogni scelta viene dal documento firmato; dove il documento lascia
un dettaglio d'implementazione, la scelta è scritta qui nel commento e vale per tutte le varianti.
"""
from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TEST_START = pd.Timestamp("2020-01-01")
SAMPLES = {"dev": ("2005-01-01", "2014-12-31"), "val": ("2015-01-01", "2019-12-31"),
           "test": ("2020-01-01", "2026-10-31")}
SECTOR_ETFS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
TOP_N = 200
DV_DAYS = 60
SECTOR_WINDOW, SECTOR_MIN_OBS, SECTOR_HYST = 252, 200, 0.05
MAX_HOLD = 5
NAME_CAP = 0.04               # 2% del lordo (lordo = 2 volte il capitale) = 4% del capitale per titolo
SECTOR_NET_CAP = 0.05         # netto per settore <= 5% del lordo
BASE_COST_BP = 8.0
BORROW_BASE = 0.005
SEC_FEE_BP = 0.28             # SEC + FINRA TAF sulle vendite, approssimati (circa 27,8 $ per milione)
MOC_EXTRA_BP = 5.0

VARIANTS = (
    [("F1", {"k": k}) for k in (1, 3, 5)]
    + [("F2", {"s": s}) for s in (0.8, 1.0, 1.5)]
    + [("F3", {"a": a}) for a in (5, 10, 15)]
)


# ---------------------------------------------------------------- Dati

@dataclass
class Panel:
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    etf: pd.DataFrame             # chiusure degli ETF settoriali + SPY
    spy_open: pd.Series
    dropped: list = field(default_factory=list)


def guard_dates(index: pd.DatetimeIndex, allow_test: bool = False) -> None:
    if not allow_test and len(index) and index.max() >= TEST_START:
        raise PermissionError("Dati dal 2020 in poi: il periodo di test è bloccato finché la validazione non è firmata")


def load(stocks_pkl="data/sp500/yahoo_2003_2020.pkl", etf_pkl="data/pulse_st/etf_1999_2019.pkl") -> Panel:
    from desk.universe import clean

    with open(stocks_pkl, "rb") as f:
        raw = {s: d[d.index < TEST_START] for s, d in pickle.load(f).items()}
    with open(etf_pkl, "rb") as f:
        etf = {s: d[d.index < TEST_START] for s, d in pickle.load(f).items()}
    stocks, dropped = clean({s: d for s, d in raw.items() if s not in etf})
    idx = etf["SPY"].index
    guard_dates(idx)

    def wide(col):
        return pd.DataFrame({s: d[col] for s, d in stocks.items()}).reindex(idx)

    return Panel(open=wide("open"), close=wide("close"), volume=wide("volume"),
                 etf=pd.DataFrame({s: d["close"] for s, d in etf.items()}).reindex(idx),
                 spy_open=etf["SPY"]["open"].reindex(idx), dropped=dropped)


# ---------------------------------------------------------------- Universo e settori (point-in-time)

def month_starts(idx: pd.DatetimeIndex) -> list[int]:
    m = idx.to_period("M")
    return [i for i in range(len(idx)) if i == 0 or m[i] != m[i - 1]]


def universe(p: Panel, member: pd.DataFrame) -> pd.DataFrame:
    """Ogni mese: membri S&P 500 di quel giorno, i primi 200 per volume in dollari medio dei 60 giorni prima."""
    idx = p.close.index
    dv = (p.close * p.volume).rolling(DV_DAYS, min_periods=int(DV_DAYS * 0.8)).mean()
    mem = member.reindex(index=idx, columns=p.close.columns, fill_value=False).fillna(False).astype(bool)
    out = pd.DataFrame(False, index=idx, columns=p.close.columns)
    starts = month_starts(idx) + [len(idx)]
    for a, b in zip(starts[:-1], starts[1:]):
        if a == 0:
            continue
        ranked = dv.iloc[a - 1].where(mem.iloc[a]).dropna().sort_values(ascending=False)
        out.iloc[a:b, out.columns.get_indexer(ranked.index[:TOP_N])] = True
    return out


def sectors(p: Panel) -> pd.DataFrame:
    """Settore = ETF con la correlazione più alta sui 252 giorni prima di ogni mese, con isteresi di 0,05."""
    idx = p.close.index
    r = p.close.pct_change(fill_method=None)
    e = p.etf[SECTOR_ETFS].pct_change(fill_method=None)
    out = pd.DataFrame(np.nan, index=idx, columns=p.close.columns, dtype=object)
    current: dict[str, str] = {}
    starts = month_starts(idx) + [len(idx)]
    for a, b in zip(starts[:-1], starts[1:]):
        if a < SECTOR_MIN_OBS:
            continue
        win = slice(max(a - SECTOR_WINDOW, 0), a)
        rs, es = r.iloc[win], e.iloc[win]
        ok = rs.columns[rs.notna().sum() >= SECTOR_MIN_OBS]
        if not len(ok):
            continue
        both = pd.concat([rs[ok], es], axis=1)
        c = both.corr(min_periods=SECTOR_MIN_OBS).loc[ok, SECTOR_ETFS]
        best = c.idxmax(axis=1)
        for s in ok:
            nb = best[s]
            if not isinstance(nb, str):
                continue
            cur = current.get(s)
            if cur is None or c.at[s, nb] - c.at[s, cur] >= SECTOR_HYST:
                current[s] = nb
        assign = pd.Series({s: current[s] for s in ok if s in current}, dtype=object)
        out.iloc[a:b, out.columns.get_indexer(assign.index)] = assign.to_numpy()
    return out


# ---------------------------------------------------------------- Segnali

def rsi(close: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """RSI di Wilder (media esponenziale con alpha = 1/n)."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + up / dn)
    return out.where(dn > 0, 100.0).where(close.notna())


def sector_relative(p: Panel, sec: pd.DataFrame, k: int) -> pd.DataFrame:
    stock = p.close / p.close.shift(k) - 1
    etf = p.etf[SECTOR_ETFS] / p.etf[SECTOR_ETFS].shift(k) - 1
    bench = pd.DataFrame(np.nan, index=stock.index, columns=stock.columns)
    for e in SECTOR_ETFS:
        mask = sec == e
        bench = bench.mask(mask, pd.DataFrame(np.repeat(etf[e].to_numpy()[:, None], stock.shape[1], 1),
                                              index=stock.index, columns=stock.columns))
    return -(stock - bench)               # alto = è sceso più del suo settore -> candidato long


@dataclass
class Rules:
    """Per ogni giorno t (alla chiusura): chi può entrare long/short e chi deve uscire."""
    enter_long: pd.DataFrame
    enter_short: pd.DataFrame
    exit_long: pd.DataFrame
    exit_short: pd.DataFrame
    min_leg: int = 1


def rules(p: Panel, uni: pd.DataFrame, sec: pd.DataFrame, family: str, params: dict) -> Rules:
    live = uni & p.close.notna()
    if family in ("F1", "F2"):
        k = params.get("k", 1)
        sig = sector_relative(p, sec, k).where(live & sec.notna())
        rank = sig.rank(axis=1, pct=True)
        el, es = rank >= 0.9, rank <= 0.1                     # decili estremi
        if family == "F2":
            # volume del giorno sotto s volte la media dei 20 giorni PRIMA (oggi escluso dalla media)
            calm = p.volume < params["s"] * p.volume.rolling(20, min_periods=15).mean().shift(1)
            el, es = el & calm, es & calm
        xl = (rank < 0.75) | rank.isna()                      # tornato almeno nel 50% centrale
        xs = (rank > 0.25) | rank.isna()
        return Rules(el, es, xl, xs)
    if family == "F3":
        a = params["a"]
        r2 = rsi(p.close, 2)
        sma = p.close.rolling(200, min_periods=200).mean()
        el = live & (r2 < a) & (p.close > sma)
        es = live & (r2 > 100 - a) & (p.close < sma)
        xl = (r2 >= 30) | r2.isna()
        xs = (r2 <= 70) | r2.isna()
        return Rules(el, es, xl, xs, min_leg=5)
    raise ValueError(family)


# ---------------------------------------------------------------- Portafoglio

def weights(rl: Rules, sec: pd.DataFrame, uni: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pesi decisi alla chiusura di ogni giorno (in unità di capitale) e giorni di detenzione."""
    idx, cols = rl.enter_long.index, rl.enter_long.columns
    EL, ES = rl.enter_long.fillna(False).to_numpy(bool), rl.enter_short.fillna(False).to_numpy(bool)
    XL, XS = rl.exit_long.fillna(True).to_numpy(bool), rl.exit_short.fillna(True).to_numpy(bool)
    U = uni.to_numpy(bool)
    S = sec.to_numpy(object)
    W = np.zeros((len(idx), len(cols)))
    held = np.zeros(len(cols), dtype=int)                      # +n long da n giorni, -n short da n giorni
    for t in range(len(idx)):
        days = np.abs(held)
        out_l = (held > 0) & (XL[t] | (days >= MAX_HOLD) | ~U[t])
        out_s = (held < 0) & (XS[t] | (days >= MAX_HOLD) | ~U[t])
        held[out_l | out_s] = 0
        held[held > 0] += 1
        held[held < 0] -= 1
        free = (held == 0) & ~(out_l | out_s)                   # chi esce oggi non rientra alla stessa chiusura
        new_l = free & EL[t]
        new_s = free & ES[t] & ~new_l
        held[new_l], held[new_s] = 1, -1
        L, Sh = np.flatnonzero(held > 0), np.flatnonzero(held < 0)
        if len(L) < rl.min_leg or len(Sh) < rl.min_leg:
            continue                                            # gamba troppo corta: niente posizioni oggi
        w = np.zeros(len(cols))
        w[L] = min(1 / len(L), NAME_CAP)
        w[Sh] = -min(1 / len(Sh), NAME_CAP)
        W[t] = neutralize(w, S[t])
    return pd.DataFrame(W, index=idx, columns=cols), pd.DataFrame(held[None, :], index=[idx[-1]], columns=cols)


def neutralize(w: np.ndarray, sector: np.ndarray, cap: float = SECTOR_NET_CAP) -> np.ndarray:
    """Gambe uguali in dollari e netto di ogni settore <= cap × lordo. I titoli senza settore sono un gruppo a parte.
    Si riduce solo (mai si aumenta): il lato in eccesso di ogni settore, poi la gamba più grande nei soli settori
    dove domina, così il pareggio non peggiora nessun netto. Si ripete finché il lordo smette di scendere."""
    w = w.copy()
    labels = np.array([s if isinstance(s, str) else "NA" for s in sector])
    groups = [labels == g for g in np.unique(labels)]
    G = np.abs(w).sum()
    for _ in range(200):
        c = cap * G
        for m in groups:
            lp, sp = w[m & (w > 0)].sum(), -w[m & (w < 0)].sum()
            if lp > sp + c:
                w[m & (w > 0)] *= (sp + c) / lp
            elif sp > lp + c:
                w[m & (w < 0)] *= (lp + c) / sp
        D = w[w > 0].sum() + w[w < 0].sum()                     # gamba long - gamba short
        if abs(D) > 0:
            sign = 1.0 if D > 0 else -1.0
            dom = [(m, sign * w[m].sum()) for m in groups if sign * w[m].sum() > 0]
            total = sum(x for _, x in dom)
            for m, x in dom:
                side = m & (np.sign(w) == sign)
                tot = np.abs(w[side]).sum()
                if tot > 0:
                    w[side] *= max(tot - abs(D) * x / total, 0.0) / tot
        G_new = np.abs(w).sum()
        nets_ok = all(abs(w[m].sum()) <= cap * G_new + 1e-12 for m in groups)
        legs_ok = abs(w[w > 0].sum() + w[w < 0].sum()) <= 1e-12
        if nets_ok and legs_ok:
            break
        G = G_new
    return w


# ---------------------------------------------------------------- Rendimenti e costi

def stress_days(p: Panel) -> pd.Series:
    """Costi doppi quando la volatilità di SPY a 20 giorni supera il 90° percentile dei 5 anni precedenti."""
    r = p.etf["SPY"].pct_change(fill_method=None)
    vol = r.rolling(20).std()
    thr = vol.shift(1).rolling(1260, min_periods=252).quantile(0.9)
    return (vol > thr).fillna(False)


def simulate(p: Panel, W: pd.DataFrame, cost_bp: float = BASE_COST_BP, borrow: float = BORROW_BASE,
             mode: str = "open", winsor: bool = False, beta_neutral: bool = False) -> pd.DataFrame:
    """Rendimenti giornalieri. mode="open": pesi decisi alla chiusura t, eseguiti all'apertura t+1 (caso base).
    mode="moc": eseguiti alla chiusura t con 5 bp in più (solo robustezza)."""
    if mode == "open":
        px = p.open
        spy = p.spy_open
        extra = 0.0
    else:
        px = p.close
        spy = p.etf["SPY"]
        extra = MOC_EXTRA_BP
    r = (px.shift(-1) / px - 1)                                 # rendimento da un'esecuzione alla successiva
    if winsor:
        lo, hi = r.quantile(0.01, axis=1), r.quantile(0.99, axis=1)
        r = r.clip(lower=lo, upper=hi, axis=0)
    r = r.fillna(0.0)
    held = W.shift(1).fillna(0.0) if mode == "open" else W.copy()   # "open": in mano da t+1; "moc": da t
    gross_ret = (held * r).sum(axis=1)
    if beta_neutral:
        sr = (spy.shift(-1) / spy - 1).fillna(0.0)           # rendimento di SPY nello stesso intervallo
        rr = px.pct_change(fill_method=None)                  # rendimenti passati dei titoli
        sp = spy.pct_change(fill_method=None)                 # rendimenti passati di SPY
        mean = lambda x: x.rolling(60, min_periods=40).mean()  # noqa: E731
        cov = mean(rr.mul(sp, axis=0)).sub(mean(rr).mul(mean(sp), axis=0))
        var = mean(sp * sp) - mean(sp) ** 2
        beta = cov.div(var, axis=0)                           # beta a 60 giorni, solo con dati fino a ieri
        port_beta = (held * beta.shift(1).fillna(1.0)).sum(axis=1)
        gross_ret = gross_ret - port_beta * sr
    trade = held.diff().fillna(held)
    turnover = trade.abs().sum(axis=1)
    c = (cost_bp + extra) / 1e4 * np.where(stress_days(p).reindex(W.index).fillna(False), 2.0, 1.0)
    sells = trade.clip(upper=0).abs().sum(axis=1)               # vendite (anche allo scoperto): commissioni SEC/FINRA
    costs = turnover * c + sells * SEC_FEE_BP / 1e4
    borrow_cost = held.clip(upper=0).abs().sum(axis=1) * borrow / 252
    net = gross_ret - costs - borrow_cost
    return pd.DataFrame({"gross": gross_ret, "net": net, "turnover": turnover,
                         "long": held.clip(lower=0).sum(axis=1), "short": -held.clip(upper=0).sum(axis=1)})


# ---------------------------------------------------------------- Metriche

def newey_west_t(x: np.ndarray, lags: int = 12) -> float:
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 2:
        return float("nan")
    e = x - x.mean()
    v = (e @ e) / n
    for L in range(1, lags + 1):
        v += 2 * (1 - L / (lags + 1)) * (e[L:] @ e[:-L]) / n
    return float(x.mean() / math.sqrt(v / n)) if v > 0 else float("nan")


def sharpe(x: pd.Series) -> float:
    sd = x.std()
    return float(x.mean() / sd * math.sqrt(252)) if sd > 0 else 0.0


def decay_cohort(p: Panel, W: pd.DataFrame, uni: pd.DataFrame, sample: tuple[str, str]) -> dict:
    """Coorte fissa: per OGNI entrata, rendimento lordo cumulato (con segno, in eccesso sulla media dell'universo)
    dal giorno 1 al giorno 5, anche dopo l'uscita, come se il trade fosse rimasto aperto. Errore standard
    raggruppato per data d'ingresso: prima la media dei trade di ogni data, poi l'errore fra le date."""
    r = (p.open.shift(-1) / p.open - 1)
    E = r.sub(r.where(uni).mean(axis=1), axis=0).to_numpy()
    H = np.sign(W.shift(1).fillna(0.0)).to_numpy()            # posizione in mano da apertura t ad apertura t+1
    start = np.zeros_like(H, dtype=bool)
    start[1:] = (H[1:] != 0) & (H[1:] != H[:-1])
    start[0] = H[0] != 0
    idx = W.index
    lo, hi = idx.searchsorted(pd.Timestamp(sample[0])), idx.searchsorted(pd.Timestamp(sample[1]), side="right")
    T = len(idx)
    means, ses, ns = [], [], []
    for d in range(1, MAX_HOLD + 1):
        per_date = []
        for t in range(lo, min(hi, T - d)):
            cols = np.flatnonzero(start[t])
            if not len(cols):
                continue
            cum = np.nansum(E[t:t + d, cols], axis=0) * H[t, cols]
            per_date.append(float(cum.mean()))
        x = np.array(per_date)
        means.append(float(x.mean() * 1e4) if len(x) else float("nan"))
        ses.append(float(x.std(ddof=1) / math.sqrt(len(x)) * 1e4) if len(x) > 1 else float("nan"))
        ns.append(len(x))
    return {"cum_bp": means, "se_bp": ses, "dates": ns}


def decay(p: Panel, W: pd.DataFrame, uni: pd.DataFrame) -> list[float]:
    """Rendimento lordo medio (con segno, in eccesso sulla media dell'universo) per giorno di detenzione 1..5, in bp."""
    r = (p.open.shift(-1) / p.open - 1)
    ex = r.sub(r.where(uni).mean(axis=1), axis=0)
    held = np.sign(W.shift(1).fillna(0.0))
    run = np.zeros(W.shape[1])
    prev = np.zeros(W.shape[1])
    H = held.to_numpy()
    A = np.zeros_like(H)
    for t in range(len(H)):
        run = np.where((H[t] != 0) & (H[t] == prev), run + 1, np.where(H[t] != 0, 1, 0))
        A[t] = run
        prev = H[t]
    E = ex.to_numpy()
    out, obs = [], []
    for d in range(1, MAX_HOLD + 1):
        m = (A == d) & np.isfinite(E)
        out.append(float((H[m] * E[m]).mean() * 1e4) if m.any() else float("nan"))
        obs.append(int(m.sum()))
    decay.obs = obs                                             # osservazioni per giorno (titolo-giorni)
    return out


def evaluate(p: Panel, W: pd.DataFrame, uni: pd.DataFrame, sample: tuple[str, str]) -> dict:
    a, b = pd.Timestamp(sample[0]), pd.Timestamp(sample[1])
    sl = slice(a, b)
    base = simulate(p, W).loc[sl]
    spy_r = (p.spy_open.shift(-1) / p.spy_open - 1).loc[sl]
    net = base["net"]
    cov = np.cov(net.fillna(0), spy_r.fillna(0))
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else float("nan")
    curve = (1 + net).cumprod()
    tr = base["turnover"].mean()
    held_days = (W.loc[sl] != 0).sum().sum()
    entries = ((W.loc[sl] != 0) & (W.shift(1).loc[sl] == 0)).sum().sum()
    out = {
        "days": int(len(net)),
        "sharpe": sharpe(net), "nw_t": newey_west_t(net.to_numpy()), "beta": beta,
        "cagr": float(curve.iloc[-1] ** (252 / len(net)) - 1) if len(net) else float("nan"),
        "max_dd": float((curve / curve.cummax() - 1).min()),
        "turnover": float(tr), "gross_daily_bp": float(base["gross"].mean() * 1e4),
        "breakeven_cost_bp": float(base["gross"].mean() / tr * 1e4) if tr > 0 else float("nan"),
        "avg_holding_days": float(held_days / entries) if entries else float("nan"),
        "entries": int(entries),
        "days_both_legs_full": float(((base["long"] > 0.99) & (base["short"] > 0.99)).mean()),
        "days_invested": float((base["long"] > 0).mean()),
        "leg_gap_max": float((base["long"] - base["short"]).abs().max()),
        "decay_bp": decay(p, W, uni)[:MAX_HOLD],
        "decay_obs": list(decay.obs),
        "decay_cohort": decay_cohort(p, W, uni, sample),
        "avg_leg": float(base["long"][base["long"] > 0].mean()) if (base["long"] > 0).any() else 0.0,
        "sharpe_by_cost": {c: sharpe(simulate(p, W, cost_bp=c).loc[sl]["net"]) for c in (2, 5, 10, 20)},
        "sharpe_by_borrow": {b_: sharpe(simulate(p, W, borrow=b_).loc[sl]["net"]) for b_ in (0.0025, 0.01, 0.03)},
        "robust": {
            "moc": sharpe(simulate(p, W, mode="moc").loc[sl]["net"]),
            "beta_neutral": sharpe(simulate(p, W, beta_neutral=True).loc[sl]["net"]),
            "winsor": sharpe(simulate(p, W, winsor=True).loc[sl]["net"]),
        },
    }
    return out


def run_variant(p: Panel, uni: pd.DataFrame, sec: pd.DataFrame, family: str, params: dict, sample: str) -> dict:
    rl = rules(p, uni, sec, family, params)
    W, _ = weights(rl, sec, uni)
    return evaluate(p, W, uni, SAMPLES[sample])
