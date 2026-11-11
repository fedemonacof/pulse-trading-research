"""Registro dei costi divisi per componente (progetto-multimercato-v1, sezione 0).

Ogni scambio produce un `Cost` con le componenti separate. Il registro le somma e le confronta con la differenza
fra P&L lordo e netto: se non coincidono entro 0,01 bp, il modello dei costi o il motore hanno un errore.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

COMPONENTS = ("fee", "spread", "slippage", "venue_basis", "funding", "borrow", "other")


@dataclass
class Cost:
    """Importi nella valuta del conto, tutti >= 0 quando sono costi."""
    fee: float = 0.0
    spread: float = 0.0
    slippage: float = 0.0
    venue_basis: float = 0.0
    funding: float = 0.0
    borrow: float = 0.0
    other: float = 0.0

    @property
    def total(self) -> float:
        return sum(getattr(self, k) for k in COMPONENTS)


@dataclass
class CostModelBp:
    """Costo per lato in punti base del nozionale, con un moltiplicatore per i periodi a costi più alti."""
    fee_bp: float
    spread_bp: float
    slippage_bp: float

    def on(self, notional: float, mult: float = 1.0) -> Cost:
        n = abs(notional) * mult / 1e4
        return Cost(fee=n * self.fee_bp, spread=n * self.spread_bp, slippage=n * self.slippage_bp)

    def scaled(self, k: float) -> "CostModelBp":
        return CostModelBp(self.fee_bp * k, self.spread_bp * k, self.slippage_bp * k)


@dataclass
class Ledger:
    rows: list = field(default_factory=list)

    def add(self, key, cost: Cost, notional: float) -> None:
        self.rows.append((key, abs(notional), cost))

    def totals(self) -> dict:
        out = {k: sum(getattr(c, k) for _, _, c in self.rows) for k in COMPONENTS}
        out["total"] = sum(out[k] for k in COMPONENTS)
        out["notional"] = sum(n for _, n, _ in self.rows)
        return out

    def in_bp(self) -> dict:
        """Componenti in punti base del nozionale scambiato."""
        t = self.totals()
        n = t["notional"] or 1.0
        return {k: t[k] / n * 1e4 for k in (*COMPONENTS, "total")}

    @staticmethod
    def reconcile(gross_minus_net: float, ledger_total: float, scale: float, tol_bp: float = 0.01) -> dict:
        """Confronta lordo − netto con la somma del registro. `scale` è il nozionale (o il capitale) di riferimento."""
        err_bp = abs(gross_minus_net - ledger_total) / scale * 1e4 if scale else 0.0
        return {"error_bp": err_bp, "ok": err_bp <= tol_bp}


def as_dict(c: Cost) -> dict:
    return asdict(c)
