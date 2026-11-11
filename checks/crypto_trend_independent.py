"""Secondo calcolo indipendente di PULSE-CT, ipotesi 1 (docs/prereg-crypto-trend-v1.md).

Scritto partendo solo dal documento di pre-registrazione e dal formato dei file grezzi Coinbase.
Non importa nulla dal resto del repository. Solo libreria standard, numpy e pandas.

Le scelte prese dove il documento e' ambiguo o tace sono elencate in checks/out/ambiguities.md
e richiamate qui nei commenti con la sigla [Ann].

Uso (dalla radice del repository):
    .venv/bin/python -I checks/crypto_trend_independent.py

Stampa solo i percorsi dei file scritti e il numero di righe. Non calcola ne' stampa metriche di rendimento.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "crypto_trend" / "raw"
OUT = ROOT / "checks" / "out"

ASSETS = {
    "BTC-USD": "BTC-USD_2016-01-01_2020-12-31.jsonl",
    "ETH-USD": "ETH-USD_2016-01-01_2020-12-31.jsonl",
}

# Sezione 3 e 5
WARMUP_START = pd.Timestamp("2016-06-01")
SIM_END = pd.Timestamp("2020-12-31")
LOCK_DATE = pd.Timestamp("2021-01-01")  # prima della firma niente date dal 2021-01-01

# Sezione 1
HORIZONS = (21, 63, 252)
VOL_WINDOW = 63
VOL_TARGET = 0.40
ANNUALISATION = np.sqrt(365.0)
THRESHOLD = 0.10
INITIAL_CAPITAL = 100_000.0

# Sezione 6 (tariffa taker provvisoria: 10 bp)
TAKER_FEE_BP = 10.0
HALF_SPREAD_BP = 5.0
SLIPPAGE_BP = 5.0
DOUBLE_BEFORE = pd.Timestamp("2025-01-01")

EPS_TRADE = 1e-9   # [A20] scambi di taglia trascurabile (relativa alla quota) non si eseguono
EPS_THRESH = 1e-12  # [A13] tolleranza numerica sul confronto "almeno 10 punti"
EPS_LEV = 1e-12     # [R3] peso attuale "sopra 1" = oltre 1 + 1e-12
# [R3b] Il controllo del tetto di leva (revisione 2, punto 3) si applica solo dopo un riallineamento
# (primo lunedi' del mese). Con False si applica a ogni decisione settimanale.
LEVERAGE_CHECK_ONLY_ON_REALIGN = True


# --------------------------------------------------------------------------------------------------
# Dati
# --------------------------------------------------------------------------------------------------

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_asset(name: str, fname: str, manifest: dict) -> pd.DataFrame:
    path = RAW / fname
    expected = manifest.get(fname)
    actual = sha256(path)
    if expected is None or actual != expected:
        sys.exit(f"STOP: impronta SHA-256 diversa per {fname}: atteso {expected}, trovato {actual}")

    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.extend(json.loads(line))
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates(subset="time", keep="first").sort_values("time")
    df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None).dt.normalize()
    if (df["time"] % 86400 != 0).any():
        sys.exit(f"STOP: {name} ha candele non allineate alle 00:00 UTC")
    if df["date"].duplicated().any():
        sys.exit(f"STOP: {name} ha piu' candele nello stesso giorno")
    # [A2] blocco delle date: il caricatore rifiuta date dal 2021-01-01 in poi
    if (df["date"] >= LOCK_DATE).any():
        sys.exit(f"STOP: {name} contiene date dal 2021-01-01 in poi; rifiutate prima della firma")
    df = df.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float)
    # [A1] si usano solo i dati dal 2016-06-01 (inizio del riscaldamento)
    df = df.loc[WARMUP_START:SIM_END]
    return df


def quality_check(name: str, df: pd.DataFrame) -> None:
    """Sezione 5: barre impossibili -> stop, senza correggere."""
    lo, hi = df["low"], df["high"]
    tol_lo, tol_hi = lo * 0.99, hi * 1.01
    bad_oc = (
        (df["open"] < tol_lo) | (df["open"] > tol_hi) | (df["close"] < tol_lo) | (df["close"] > tol_hi)
    )
    bad_hl = hi < lo
    ratio = df["close"] / df["close"].shift(1)  # chiusure consecutive disponibili [A4]
    bad_jump = (ratio > 3.0) | (ratio < 1.0 / 3.0)
    bad = bad_oc | bad_hl | bad_jump.fillna(False)
    if bad.any():
        sys.exit(f"STOP: {name} ha {int(bad.sum())} barre impossibili, prima il {bad.idxmax().date()}")


def build_panel(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calendario giornaliero completo; open grezzo (NaN se manca la candela), close riportato in avanti."""
    cal = pd.date_range(WARMUP_START, SIM_END, freq="D")
    opens = pd.DataFrame({a: f["open"].reindex(cal) for a, f in frames.items()})
    raw_close = pd.DataFrame({a: f["close"].reindex(cal) for a, f in frames.items()})
    # [A5] giorno mancante: posizione valutata all'ultima chiusura nota
    close = raw_close.ffill()
    return opens, raw_close, close


# --------------------------------------------------------------------------------------------------
# Segnali e pesi obiettivo (vettoriali)
# --------------------------------------------------------------------------------------------------

def signals(close: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """m e sigma63 sulla chiusura di ogni giorno t (cioe' disponibili per decidere a t+1 00:00 UTC)."""
    s = [np.sign(close / close.shift(h) - 1.0) for h in HORIZONS]  # [A6] [A7] [A8]
    m = (s[0] + s[1] + s[2]) / 3.0  # NaN finche' manca anche un solo orizzonte [A9]
    ret = close / close.shift(1) - 1.0  # [A10] rendimenti semplici
    sigma = ret.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std(ddof=1) * ANNUALISATION  # [A11]
    return m, sigma


def decision_table(close: pd.DataFrame, opens: pd.DataFrame) -> pd.DataFrame:
    m_close, sigma_close = signals(close)
    cal = close.index
    mondays = cal[(cal.day_of_week == 0)]
    # decisione del lunedi' D con le chiusure fino alla domenica D-1
    prev_day = mondays - pd.Timedelta(days=1)
    valid = prev_day >= cal[0]
    mondays, prev_day = mondays[valid], prev_day[valid]

    out = {}
    for a in close.columns:
        m = m_close[a].reindex(prev_day).to_numpy()
        sig = sigma_close[a].reindex(prev_day).to_numpy()
        scale = np.minimum(1.0, VOL_TARGET / sig)
        out[(a, "m")] = m
        out[(a, "w_v3")] = np.maximum(0.0, m) * scale        # NaN se m o sigma mancano
        out[(a, "w_bench")] = 1.0 * scale                   # m = 1 sempre; NaN se sigma manca
        out[(a, "close_prev")] = close[a].reindex(prev_day).to_numpy()
        out[(a, "open")] = opens[a].reindex(mondays).to_numpy()  # NaN se manca la candela del lunedi'
    tab = pd.DataFrame(out, index=mondays)
    tab.columns = pd.MultiIndex.from_tuples(tab.columns)
    # [A15] primo lunedi' del mese
    tab[("realign", "")] = mondays.day <= 7
    tab[("cost_rate", "")] = np.where(mondays < DOUBLE_BEFORE, 2.0, 1.0) * (
        TAKER_FEE_BP + HALF_SPREAD_BP + SLIPPAGE_BP) / 1e4
    tab[("mult", "")] = np.where(mondays < DOUBLE_BEFORE, 2.0, 1.0)
    return tab


# --------------------------------------------------------------------------------------------------
# Simulazione (ciclo sui soli lunedi': la soglia dipende dal peso attuale, quindi dal percorso)
# --------------------------------------------------------------------------------------------------

def simulate(tab: pd.DataFrame, close: pd.DataFrame, variant: str):
    assets = list(close.columns)
    wcol = "w_v3" if variant == "V3" else "w_bench"
    n = len(assets)

    qty = np.zeros(n)
    cash = np.full(n, INITIAL_CAPITAL / n)  # [A3] 50/50 in liquidita' al 2016-06-01
    prev_m = np.full(n, np.nan)

    trades = []
    state_idx, state_qty, state_cash = [], [], []

    C_PREV = np.column_stack([tab[(a, "close_prev")].to_numpy() for a in assets])
    OPEN = np.column_stack([tab[(a, "open")].to_numpy() for a in assets])
    W_TGT = np.column_stack([tab[(a, wcol)].to_numpy() for a in assets])
    M = np.column_stack([tab[(a, "m")].to_numpy() if variant == "V3" else np.ones(len(tab)) for a in assets])
    REALIGN = tab[("realign", "")].to_numpy().ravel().astype(bool)
    RATE = tab[("cost_rate", "")].to_numpy().ravel().astype(float)
    MULT = tab[("mult", "")].to_numpy().ravel().astype(float)

    for k, d in enumerate(tab.index):
        cprev, opn = C_PREV[k], OPEN[k]

        # [A15][A16] riallineamento delle quote alle 00:00 UTC del primo lunedi', valutato alla chiusura
        # della domenica; sposta solo liquidita' fra le quote, non genera scambi ne' costi.
        if REALIGN[k]:
            total = cash.sum() + (qty * cprev).sum()
            cash = total / n - qty * cprev

        rate, mult = RATE[k], MULT[k]

        for i, a in enumerate(assets):
            m = M[k, i]
            w_tgt = W_TGT[k, i]
            if np.isnan(opn[i]):
                continue  # [A17] manca la candela del lunedi': niente scambio e niente decisione registrata
            if np.isnan(w_tgt) or np.isnan(m):
                continue  # [A9] pesi non ancora definiti: si resta come si e' (in liquidita')

            # [A12] peso attuale alla chiusura della domenica (dopo l'eventuale riallineamento)
            pos_c = qty[i] * cprev[i]
            sleeve_c = cash[i] + pos_c
            w_cur = pos_c / sleeve_c if sleeve_c > 0 else 0.0

            # [A14][R4] la prima decisione con m definito non e' un cambio di livello
            level_change = (not np.isnan(prev_m[i])) and (m != prev_m[i])
            prev_m[i] = m
            # [R3] tetto di leva: peso attuale sopra 1 -> si scambia verso l'obiettivo anche sotto la soglia
            over_lev = (w_cur > 1.0 + EPS_LEV) and (REALIGN[k] or not LEVERAGE_CHECK_ONLY_ON_REALIGN)
            if not (abs(w_tgt - w_cur) >= THRESHOLD - EPS_THRESH or level_change or over_lev):
                continue

            # [A18][R2] esecuzione all'apertura del lunedi': quantita' nuova = peso obiettivo x capitale della
            # quota all'apertura / apertura; i costi si pagano dopo dalla cassa della quota.
            p0 = qty[i] * opn[i]
            s0 = cash[i] + p0
            p1 = w_tgt * s0
            notional = abs(p1 - p0)
            if notional <= EPS_TRADE * abs(s0):
                continue  # [A20]
            fee = notional * mult * TAKER_FEE_BP / 1e4
            spread = notional * mult * HALF_SPREAD_BP / 1e4
            slip = notional * mult * SLIPPAGE_BP / 1e4
            cost = fee + spread + slip
            cash[i] -= (p1 - p0) + cost
            qty[i] = p1 / opn[i]
            sleeve_after = cash[i] + p1
            trades.append({
                "date": d.strftime("%Y-%m-%d"),
                "asset": a,
                "weight_after": p1 / sleeve_after,
                "cost": cost,
                "fee": fee,
                "spread": spread,
                "slippage": slip,
            })

        state_idx.append(d)
        state_qty.append(qty.copy())
        state_cash.append(cash.copy())

    # equity giornaliera vettoriale: stato dopo gli scambi del lunedi', riportato fino al lunedi' seguente
    cal = close.index
    qty_df = pd.DataFrame(state_qty, index=state_idx, columns=assets).reindex(cal).ffill().fillna(0.0)
    cash_tot = pd.Series([c.sum() for c in state_cash], index=state_idx).reindex(cal).ffill()
    cash_tot = cash_tot.fillna(INITIAL_CAPITAL)
    equity = cash_tot + (qty_df * close).sum(axis=1)  # [A5] chiusure riportate in avanti
    eq = pd.DataFrame({"date": cal.strftime("%Y-%m-%d"), "equity": equity.to_numpy()})
    return pd.DataFrame(trades, columns=["date", "asset", "weight_after", "cost", "fee", "spread", "slippage"]), eq


def main() -> None:
    manifest = json.loads((RAW / "manifest.json").read_text())
    frames = {}
    for a, f in ASSETS.items():
        df = load_asset(a, f, manifest)
        quality_check(a, df)
        frames[a] = df
    opens, _raw_close, close = build_panel(frames)
    tab = decision_table(close, opens)

    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("V3", "BENCH"):
        trades, eq = simulate(tab, close, name)
        tp = OUT / f"independent_trades_{name}.csv"
        ep = OUT / f"independent_equity_{name}.csv"
        trades.to_csv(tp, index=False, float_format="%.10f")
        eq.to_csv(ep, index=False, float_format="%.6f")
        print(f"{tp.relative_to(ROOT)} {len(trades)}")
        print(f"{ep.relative_to(ROOT)} {len(eq)}")


if __name__ == "__main__":
    main()
