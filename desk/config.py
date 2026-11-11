"""Configurazione letta da .env. I limiti di rischio vivono qui e NON sono modificabili dagli agenti
né dalla revisione notturna (che può toccare solo i pesi delle strategie, entro limiti fissi)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_CONFIRMATION = "HO_CAPITO_CHE_POSSO_PERDERE_SOLDI_VERI"
# 15 large cap liquide + ETF (configurabile con SYMBOLS)
DEFAULT_UNIVERSE = "SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,GOOGL,META,AVGO,JPM,V,UNH,XOM,COST"


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si", "sì"}


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class RiskLimits:
    # --- Regole PULSE: controllate prima di ogni ordine, nessun modello le può scavalcare ---
    max_position_pct: float = 0.05        # max 5% dell'equity per posizione
    max_open_positions: int = 5           # max 5 posizioni aperte
    max_daily_loss_pct: float = 0.02      # -2% nel giorno -> chiude tutto e pausa fino alla prossima sessione
    no_trade_first_minutes: int = 5       # niente operazioni nei primi 5 minuti di sessione
    stop_loss_atr_mult: float = 2.0       # bracket: stop a 2 x ATR...
    take_profit_atr_mult: float = 3.0     # ...e take profit a 3 x ATR, su ogni entrata
    # --- Protezioni aggiuntive (freqtrade) ---
    max_gross_exposure_pct: float = 1.00
    trailing_atr_mult: float = 2.5
    trailing_activation_atr: float = 1.5
    min_confidence: float = 0.65          # sotto questa soglia il voto del comitato non conta
    max_trades_per_day: int = 20
    allow_short: bool = False             # solo long: gli short su large cap USA perdevano nel backtest
    min_cash_buffer_pct: float = 0.05
    max_drawdown_pct: float = 0.15
    cooldown_minutes: int = 120
    stoploss_guard_count: int = 3
    stoploss_guard_hours: int = 24
    stoploss_guard_pause_hours: int = 12
    # --- Core + satellite: il core (SPY) assorbe il capitale che il satellite non usa ---
    core_enabled: bool = True
    core_symbol: str = "SPY"
    core_cash_buffer_pct: float = 0.03    # liquidità sempre libera (commissioni, arrotondamenti)
    core_rebalance_band_pct: float = 0.02 # il core si ribilancia solo se si sposta di oltre il 2% dal target
    satellite_max_drawdown_pct: float = 0.05  # perdita del satellite dal suo massimo (in % dell'equity) -> kill switch
    # Decisioni del test pre-registrato 2005-2019 (docs/risultati-2005-2019.md):
    core_trend_filter: bool = True        # core in SPY solo se a fine mese SPY è sopra la MA200, altrimenti liquidità
    satellite_mode: str = "shadow"        # "shadow": decide e registra su un conto virtuale, nessun ordine vero


@dataclass(frozen=True)
class Settings:
    alpaca_key: str = ""
    alpaca_secret: str = ""
    base_url: str = PAPER_URL
    live: bool = False
    symbols: list[str] = field(default_factory=list)
    model: str = "claude-opus-5-5"
    analyst_effort: str = "medium"
    manager_effort: str = "high"
    tick_seconds: int = 60               # controllo prezzi/rischio: ogni minuto
    reflex_minutes: int = 15             # il riflesso valuta i segnali ogni 15 minuti
    committee_minutes: int = 30          # riunione del comitato AI
    trigger_move_pct: float = 0.015      # o prima, se un titolo si muove >1,5%
    use_committee: bool = True           # il voto del comitato entra nella fusione col riflesso
    db_path: str = "journal.db"
    reports_dir: str = "reports"
    debate_rounds: int = 1
    web_research: bool = True
    free_data: bool = True
    scheduler_enabled: bool = False      # resta spento finché non hai visto il backtest
    telegram_token: str = ""
    telegram_chat_id: str = ""
    risk: RiskLimits = field(default_factory=RiskLimits)

    @property
    def satellite_symbols(self) -> list[str]:
        """Il satellite non tratta il titolo del core: lo gestisce già il core."""
        if not self.risk.core_enabled:
            return list(self.symbols)
        return [x for x in self.symbols if x != self.risk.core_symbol]

    @property
    def mode(self) -> str:
        return "LIVE" if self.live else "PAPER"


def load_settings() -> Settings:
    base_url = os.getenv("ALPACA_BASE_URL", PAPER_URL).strip().rstrip("/")
    is_paper = base_url == PAPER_URL
    if not is_paper:
        if not _bool("LIVE_TRADING", False):
            raise SystemExit(
                f"ALPACA_BASE_URL={base_url} non è l'indirizzo paper ({PAPER_URL}). "
                "Per i soldi veri servono LIVE_TRADING=true e la conferma esplicita: "
                "resta in paper finché la strategia non ha mesi di risultati."
            )
        if os.getenv("LIVE_CONFIRMATION", "") != LIVE_CONFIRMATION:
            raise SystemExit(f"LIVE_TRADING=true richiede anche LIVE_CONFIRMATION={LIVE_CONFIRMATION} nel file .env.")
    symbols = [s.strip().upper() for s in os.getenv("SYMBOLS", DEFAULT_UNIVERSE).split(",") if s.strip()]
    risk = RiskLimits(
        max_position_pct=_float("MAX_POSITION_PCT", 0.05),
        max_open_positions=_int("MAX_OPEN_POSITIONS", 5),
        max_daily_loss_pct=_float("MAX_DAILY_LOSS_PCT", 0.02),
        no_trade_first_minutes=_int("NO_TRADE_FIRST_MINUTES", 5),
        stop_loss_atr_mult=_float("STOP_LOSS_ATR_MULT", 2.0),
        take_profit_atr_mult=_float("TAKE_PROFIT_ATR_MULT", 3.0),
        max_gross_exposure_pct=_float("MAX_GROSS_EXPOSURE_PCT", 1.0),
        trailing_atr_mult=_float("TRAILING_ATR_MULT", 2.5),
        trailing_activation_atr=_float("TRAILING_ACTIVATION_ATR", 1.5),
        min_confidence=_float("MIN_CONFIDENCE", 0.65),
        max_trades_per_day=_int("MAX_TRADES_PER_DAY", 20),
        allow_short=_bool("ALLOW_SHORT", False),
        max_drawdown_pct=_float("MAX_DRAWDOWN_PCT", 0.15),
        cooldown_minutes=_int("COOLDOWN_MINUTES", 120),
        stoploss_guard_count=_int("STOPLOSS_GUARD_COUNT", 3),
        stoploss_guard_hours=_int("STOPLOSS_GUARD_HOURS", 24),
        stoploss_guard_pause_hours=_int("STOPLOSS_GUARD_PAUSE_HOURS", 12),
        core_enabled=_bool("CORE_ENABLED", True),
        core_symbol=os.getenv("CORE_SYMBOL", "SPY").strip().upper(),
        core_cash_buffer_pct=_float("CORE_CASH_BUFFER_PCT", 0.03),
        core_rebalance_band_pct=_float("CORE_REBALANCE_BAND_PCT", 0.02),
        satellite_max_drawdown_pct=_float("SATELLITE_MAX_DRAWDOWN_PCT", 0.05),
        core_trend_filter=_bool("CORE_TREND_FILTER", True),
        satellite_mode=os.getenv("SATELLITE_MODE", "shadow").strip().lower(),
    )
    return Settings(
        alpaca_key=os.getenv("ALPACA_API_KEY", ""),
        alpaca_secret=os.getenv("ALPACA_SECRET_KEY", ""),
        base_url=base_url,
        live=not is_paper,
        symbols=symbols,
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5"),
        analyst_effort=os.getenv("ANALYST_EFFORT", "medium"),
        manager_effort=os.getenv("MANAGER_EFFORT", "high"),
        tick_seconds=_int("TICK_SECONDS", 60),
        reflex_minutes=_int("REFLEX_MINUTES", 15),
        committee_minutes=_int("COMMITTEE_MINUTES", 30),
        trigger_move_pct=_float("TRIGGER_MOVE_PCT", 0.015),
        use_committee=_bool("USE_COMMITTEE", True),
        db_path=os.getenv("DB_PATH", "journal.db"),
        reports_dir=os.getenv("REPORTS_DIR", "reports"),
        debate_rounds=_int("DEBATE_ROUNDS", 1),
        web_research=_bool("WEB_RESEARCH", True),
        free_data=_bool("FREE_DATA", True),
        scheduler_enabled=_bool("SCHEDULER_ENABLED", False),
        telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        risk=risk,
    )
