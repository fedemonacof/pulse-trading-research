"""Il riflesso: decisione veloce e deterministica a partire da uno stato numerico compatto.

    stato (prezzo, ATR, punteggi delle strategie, regime, voto del comitato, posizione)
        -> compra / vendi / resta, con confidenza 0-100 e un motivo in italiano

Soglie, pesi per regime e dimensionamento sono costanti qui. Il comitato AI entra solo come
un voto pesato (al massimo il 50%) e non può aprire posizioni da solo; il risk layer viene dopo.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .config import RiskLimits
from .strategies.regime import LABELS, REGIMES

ENTER = 55.0     # |punteggio| minimo per aprire
EXIT = 20.0      # sotto questo |punteggio| una posizione aperta si chiude

# Pesi che la revisione notturna può spostare, ma sempre dentro questi limiti
# Il comitato AI parte a peso 0: vota e i voti si registrano, ma non contano finché non c'è un'evidenza raccolta
# IN AVANTI (paper trading). Non si può testare sul passato: Claude conosce già com'è andata la storia.
DEFAULT_WEIGHTS = {"trend": 1.0, "meanrev": 1.0, "committee": 0.0}
WEIGHT_BOUNDS = {"trend": (0.5, 1.5), "meanrev": (0.5, 1.5), "committee": (0.0, 0.2)}


def clamp_weights(w: dict | None) -> dict:
    w = {**DEFAULT_WEIGHTS, **(w or {})}
    return {k: min(max(float(w[k]), lo), hi) for k, (lo, hi) in WEIGHT_BOUNDS.items()}


@dataclass
class SymbolState:
    symbol: str
    price: float
    atr: float | None
    regime: str
    trend_score: float | None = None
    trend_reason: str = ""
    mr_score: float | None = None
    mr_reason: str = ""
    committee_score: float | None = None   # -100..100, già pesato per la sua confidenza
    committee_reason: str = ""
    position_qty: float = 0.0
    trend_hold: float | None = None        # punteggi "per restare" (isteresi): usati solo con posizione aperta
    mr_hold: float | None = None


@dataclass
class Decision:
    symbol: str
    action: str          # "buy" | "sell" | "hold"
    intent: str          # "enter_long" | "enter_short" | "exit" | "hold" | "skip"
    confidence: float    # 0-100
    score: float         # -100..100 dopo la fusione
    reason: str
    regime: str
    strategy: str        # la componente che ha pesato di più
    price: float
    stop: float | None = None
    take_profit: float | None = None
    components: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def committee_score(target_weight: float, confidence: float, limits: RiskLimits) -> float | None:
    """Converte il peso target del gestore in un voto -100..100. Sotto la confidenza minima non vota."""
    if confidence < limits.min_confidence:
        return None
    return max(-1.0, min(1.0, target_weight / limits.max_position_pct)) * 100.0 * confidence


def decide(s: SymbolState, weights: dict, limits: RiskLimits) -> Decision:
    w = clamp_weights(weights)
    reg = REGIMES.get(s.regime, REGIMES["warming_up"])
    base = dict(symbol=s.symbol, regime=s.regime, price=s.price)

    if s.regime == "warming_up" or s.atr is None or not math.isfinite(s.price):
        if s.position_qty:
            return Decision(**base, action="hold", intent="hold", confidence=0, score=0,
                            reason="dati insufficienti: mantengo la posizione", strategy="-")
        return Decision(**base, action="hold", intent="skip", confidence=0, score=0,
                        reason="dati insufficienti per decidere", strategy="-")

    # 1. Strategie, pesate per regime e per i pesi della revisione notturna.
    #    Con una posizione aperta contano i punteggi "per restare" (isteresi), se la strategia li fornisce.
    in_pos = s.position_qty != 0
    ts = s.trend_hold if in_pos and s.trend_hold is not None else s.trend_score
    ms = s.mr_hold if in_pos and s.mr_hold is not None else s.mr_score
    parts, num, den = {}, 0.0, 0.0
    if ts is not None:
        k = reg["trend"] * w["trend"]
        parts["trend"] = (ts, k)
        num, den = num + ts * k, den + k
    if ms is not None:
        k = reg["meanrev"] * w["meanrev"]
        parts["meanrev"] = (ms, k)
        num, den = num + ms * k, den + k
    strat = num / den if den else 0.0

    # 2. Voto del comitato AI (se c'è), con peso limitato
    if s.committee_score is not None:
        wc = w["committee"]
        parts["committee"] = (s.committee_score, wc)
        final = (1 - wc) * strat + wc * s.committee_score
    else:
        final = strat
    final = max(-100.0, min(100.0, final))

    contrib = {k: v * kw for k, (v, kw) in parts.items()}
    dominant = max(contrib, key=lambda k: abs(contrib[k])) if contrib else "-"
    reasons = {"trend": s.trend_reason, "meanrev": s.mr_reason, "committee": s.committee_reason}
    why = reasons.get(dominant) or "nessun segnale"
    tail = f"regime {LABELS[s.regime].lower()}"
    if s.committee_score is not None and dominant != "committee":
        tail += f", comitato {s.committee_score:+.0f}"

    # 3. Soglie: tutte nel codice
    conf = round(abs(final), 1)
    long_, short_ = s.position_qty > 0, s.position_qty < 0
    if long_:
        if final <= EXIT:
            return Decision(**base, action="sell", intent="exit", confidence=conf, score=round(final, 1),
                            reason=f"chiudo il long: segnale sceso a {final:+.0f}. {why}; {tail}",
                            strategy=dominant, components=contrib)
        return Decision(**base, action="hold", intent="hold", confidence=conf, score=round(final, 1),
                        reason=f"tengo il long ({final:+.0f}). {why}; {tail}", strategy=dominant, components=contrib)
    if short_:
        if final >= -EXIT:
            return Decision(**base, action="buy", intent="exit", confidence=conf, score=round(final, 1),
                            reason=f"chiudo lo short: segnale salito a {final:+.0f}. {why}; {tail}",
                            strategy=dominant, components=contrib)
        return Decision(**base, action="hold", intent="hold", confidence=conf, score=round(final, 1),
                        reason=f"tengo lo short ({final:+.0f}). {why}; {tail}", strategy=dominant, components=contrib)

    if final >= ENTER and reg["longs"]:
        return Decision(**base, action="buy", intent="enter_long", confidence=conf, score=round(final, 1),
                        reason=f"compro: {why}; {tail}", strategy=dominant, components=contrib,
                        stop=round(s.price - limits.stop_loss_atr_mult * s.atr, 2),
                        take_profit=round(s.price + limits.take_profit_atr_mult * s.atr, 2))
    if final <= -ENTER and limits.allow_short:
        return Decision(**base, action="sell", intent="enter_short", confidence=conf, score=round(final, 1),
                        reason=f"vendo allo scoperto: {why}; {tail}", strategy=dominant, components=contrib,
                        stop=round(s.price + limits.stop_loss_atr_mult * s.atr, 2),
                        take_profit=round(s.price - limits.take_profit_atr_mult * s.atr, 2))
    note = "nuovi long sospesi in regime di crisi" if final >= ENTER and not reg["longs"] else "segnale sotto la soglia"
    return Decision(**base, action="hold", intent="skip", confidence=conf, score=round(final, 1),
                    reason=f"resto fuori ({final:+.0f}, {note}). {why}; {tail}", strategy=dominant, components=contrib)


def position_size(equity: float, price: float, confidence: float, regime: str, limits: RiskLimits) -> int:
    """Azioni intere: 5% dell'equity al massimo, ridotto in alta volatilità e con poca convinzione."""
    if price <= 0:
        return 0
    mult = REGIMES.get(regime, REGIMES["warming_up"])["size"] * (0.6 + 0.4 * min(confidence, 100) / 100)
    return int(equity * limits.max_position_pct * mult / price)
