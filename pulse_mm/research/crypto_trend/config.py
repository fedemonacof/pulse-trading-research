"""PULSE-CT, ipotesi 1: costanti della pre-registrazione docs/prereg-crypto-trend-v1.md.

Ogni numero qui è scritto nel documento. Cambiare un valore cambia l'impronta del codice: dopo la firma serve una
nuova versione del documento.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "prereg-crypto-trend-v1.md"
DATA = ROOT / "data" / "crypto_trend"

ASSETS = ("BTC-USD", "ETH-USD")
FETCH_START = "2016-01-01"            # si scarica da qui per verificare dove parte lo storico
WARMUP_START = pd.Timestamp("2016-06-01")
PERIODS = {
    "dev": (pd.Timestamp("2018-01-01"), pd.Timestamp("2020-12-31")),
    "val": (pd.Timestamp("2021-01-01"), pd.Timestamp("2022-12-31")),
    "test": (pd.Timestamp("2023-01-01"), pd.Timestamp("2026-10-31")),
}
LIVE_START = pd.Timestamp("2026-11-01")  # il flusso dal vivo accetta solo date da qui in poi

# Segnale ed esposizione (sezione 1)
HORIZONS = (21, 63, 252)
VOL_WINDOW = 63
ANN = 365                              # le crypto si scambiano tutti i giorni
VOL_TARGET = 0.40
MAX_LEV = 1.0
THRESHOLD = 0.10                       # punti di peso sotto cui non si tocca la posizione
THRESHOLD_FALLBACK = 0.20              # regola di riserva della revisione 1, se il turnover supera ancora 10
DECISION_WEEKDAY = 0                   # revisione 1: decisione il lunedì alle 00:00 UTC
SPLIT = 0.5                            # 50% BTC, 50% ETH

# Costi (sezione 6). TAKER_BP letto sul listino OKX Europe il 2026-11-11 (criterio 8):
# spot, conto solo spot, utente regolare, taker 0,1000%. Prova in docs/evidenze/okx_eu_spot_2026-11-11.md.
# Si rilegge il giorno della firma; se cambia, vale il nuovo valore e la modifica si registra nel documento.
TAKER_BP: float | None = 10.0
PROVISIONAL_TAKER_BP = 10.0            # usato solo se TAKER_BP torna None
HALF_SPREAD_BP = 5.0
SLIPPAGE_BP = 5.0
COST_DOUBLE_BEFORE = pd.Timestamp("2025-01-01")
COST_STRESS_SENSITIVITY = 3.0
TURNOVER_MAX = 10.0                    # volte il capitale all'anno

# Dry-run di riconciliazione (sezione 3, criterio 7). Fissati prima del primo ordine; l'impronta li congela.
DRYRUN_DAYS = 28                       # giorni validi da raggiungere
DRYRUN_TIME_UTC = (0, 5)               # ogni giorno alle 00:05 UTC
DRYRUN_MAX_DELAY_S = 120               # un ordine partito oltre 2 minuti dopo le 00:05 non vale
DRYRUN_MAX_MISSED = 3                  # giorni saltati recuperati in coda; al quarto il dry-run riparte da zero
DRYRUN_SIZE_FRAC = 0.104               # mediana dello scambio / capitale sullo sviluppo (revisione 1)
DRYRUN_CAPITAL = 100_000.0             # dry_run_wallet di freqtrade, in USDC
DRYRUN_PAIRS = {"BTC-USD": "BTC/USDC", "ETH-USD": "ETH/USDC"}       # freqtrade, sede myokx (OKX Europe)
DRYRUN_OKX_INST = {"BTC-USD": "BTC-USDC", "ETH-USD": "ETH-USDC"}    # API pubblica di OKX Europe
DRYRUN_OKX_TICKER = "https://eea.okx.com/api/v5/market/ticker?instId={i}"
DRYRUN_COST_BP = HALF_SPREAD_BP + SLIPPAGE_BP                        # 10 bp: tetto dello scarto medio
DRYRUN_OKX_BOOK = "https://eea.okx.com/api/v5/market/books?instId={i}&sz=400"   # fotografia del book
DRYRUN_DEPTH_MULTS = (1, 5, 10)        # costo della stessa taglia moltiplicata, calcolato sul book fotografato
# Giorno agitato (revisione 3b): rendimento giornaliero Coinbase, chiusura su chiusura, oltre circa 2 deviazioni
# standard giornaliere tipiche (BTC ~45% annuo, ETH ~65% annuo), oppure spread OKX alla decisione oltre 5 bp.
DRYRUN_STRESS_ABS_RET = {"BTC-USD": 0.05, "ETH-USD": 0.07}
DRYRUN_STRESS_SPREAD_BP = 5.0
FREQTRADE_VERSION = "2026.10"
FREQTRADE_API = "http://127.0.0.1:8080/api/v1"

# Dati (sezione 5)
MISSING_RUN_MAX = 3
COVERAGE_MIN = 0.99

# Statistiche (sezione 7)
BOOT_N = 5000
BOOT_BLOCK = 21
BOOT_BLOCK_ROBUST = 63
SEED = 20261111
LEVEL = 0.90
SHARPE_MARGIN = -0.10

# Varianti (sezione 2): N = 4 dopo la revisione 1 (la regola giornaliera resta fra i tentativi)
VARIANTS = {
    "V1": "solo s252 (robustezza riportata, senza soglie)",
    "V2": "media 1/3/12 mesi, regola binaria (scartata, contata nell'N)",
    "V3-daily": "V3 con decisione giornaliera (scartata per il turnover, revisione 1)",
    "V3": "media 1/3/12 mesi, esposizione max(0, m), decisione settimanale (test principale)",
}
MAIN = "V3"
N_TRIALS = 4
