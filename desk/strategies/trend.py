"""Trend following: incrocio EMA 20/50 con filtro RSI.

Due punteggi per barra:
  score  -> per ENTRARE: serve il trend (EMA veloce sopra la lenta) E la conferma dell'RSI
  hold   -> per RESTARE: basta che il trend non si sia rotto (isteresi). L'RSI non fa uscire:
            un titolo che sale forte va in ipercomprato proprio quando il trade funziona.
Con conf="momentum" la convinzione viene dal rendimento a 6 mesi (momentum, Jegadeesh-Titman):
i posti limitati vanno ai trend più forti.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import rsi


class TrendFollowing:
    name = "trend"

    def __init__(self, fast: int = 20, slow: int = 50, rsi_n: int = 14,
                 long_rsi=(50.0, 75.0), short_rsi=(25.0, 50.0),
                 hysteresis: bool = True, conf: str = "momentum", mom_days: int = 126):
        self.fast, self.slow, self.rsi_n = fast, slow, rsi_n
        self.long_rsi, self.short_rsi = long_rsi, short_rsi
        self.hysteresis, self.conf_mode, self.mom_days = hysteresis, conf, mom_days

    def applies_to(self, symbol: str) -> bool:
        return True

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        c = df["close"]
        f = pd.DataFrame(index=df.index)
        f["close"] = c
        f["ema_fast"] = c.ewm(span=self.fast, adjust=False).mean()
        f["ema_slow"] = c.ewm(span=self.slow, adjust=False).mean()
        f["rsi"] = rsi(c, self.rsi_n)
        f["spread_pct"] = (f["ema_fast"] / f["ema_slow"] - 1) * 100
        f["momentum"] = c / c.shift(self.mom_days) - 1
        if self.conf_mode == "momentum":
            # long: più forte il rialzo a 6 mesi, più alta la convinzione (stesso per gli short, al contrario)
            conf_up = np.clip(55.0 + f["momentum"] * 100.0, 55.0, 95.0)
            conf_dn = np.clip(55.0 - f["momentum"] * 100.0, 55.0, 95.0)
        else:
            conf_up = conf_dn = np.minimum(95.0, 55.0 + f["spread_pct"].abs() * 12.0)
        up = (f["spread_pct"] > 0) & f["rsi"].between(*self.long_rsi)
        down = (f["spread_pct"] < 0) & f["rsi"].between(*self.short_rsi)
        f["score"] = np.where(up, conf_up, np.where(down, -conf_dn, 0.0))
        if self.hysteresis:
            f["hold"] = np.where(f["spread_pct"] > 0, conf_up, np.where(f["spread_pct"] < 0, -conf_dn, 0.0))
        else:
            f["hold"] = f["score"]
        warm = max(self.slow, self.mom_days if self.conf_mode == "momentum" else 0)
        f.loc[f.index[:warm], ["score", "hold"]] = np.nan   # indicatori non ancora affidabili
        return f

    def explain(self, row: pd.Series) -> str:
        sp, r = row["spread_pct"], row["rsi"]
        direction = "sopra" if sp > 0 else "sotto"
        base = f"EMA{self.fast} {direction} EMA{self.slow} di {abs(sp):.1f}%, RSI {r:.0f}"
        if self.conf_mode == "momentum" and pd.notna(row.get("momentum")):
            base += f", momentum 6 mesi {row['momentum'] * 100:+.0f}%"
        if row["score"] > 0:
            return base + ": trend rialzista confermato"
        if row["score"] < 0:
            return base + ": trend ribassista confermato"
        if sp > 0 and r > self.long_rsi[1]:
            return base + ": trend su ma ipercomprato, non si entra (chi è dentro resta)"
        if sp < 0 and r < self.short_rsi[0]:
            return base + ": trend giù ma ipervenduto, non si entra"
        return base + ": RSI non conferma il trend"
