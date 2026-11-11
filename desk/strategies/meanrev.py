"""Mean reversion: bande di Bollinger sugli ETF indice (SPY, QQQ, IWM).

Con trend_filter (stile Connors) si compra l'eccesso di vendite solo se il prezzo è sopra la media
a 200 giorni: si comprano i ribassi dentro un mercato che sale, non i coltelli che cadono.
  score -> per ENTRARE: prezzo sotto la banda bassa (o sopra la alta, per gli short)
  hold  -> per RESTARE: finché il prezzo non torna alla banda centrale (la media)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class MeanReversion:
    name = "meanrev"

    def __init__(self, n: int = 20, k: float = 2.0, universe=("SPY", "QQQ", "IWM"),
                 trend_filter: bool = True, hysteresis: bool = True):
        self.n, self.k, self.universe = n, k, set(universe)
        self.trend_filter, self.hysteresis = trend_filter, hysteresis

    def applies_to(self, symbol: str) -> bool:
        return symbol in self.universe

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        c = df["close"]
        f = pd.DataFrame(index=df.index)
        f["close"] = c
        f["mid"] = c.rolling(self.n).mean()
        sd = c.rolling(self.n).std()
        f["upper"], f["lower"] = f["mid"] + self.k * sd, f["mid"] - self.k * sd
        f["pctb"] = (c - f["lower"]) / (f["upper"] - f["lower"])
        f["sma200"] = c.rolling(200).mean()
        b = f["pctb"]
        buy = 60 + np.minimum(35, (0.05 - b) * 200)
        sell = -(60 + np.minimum(35, (b - 0.95) * 200))
        if self.trend_filter:
            uptrend = c > f["sma200"]
            f["score"] = np.select([(b < 0.05) & uptrend, (b > 0.95) & ~uptrend], [buy, sell], default=0.0)
        else:
            f["score"] = np.select([b < 0.05, b > 0.95], [buy, sell], default=(0.5 - b) * 2 * 45)
        if self.hysteresis:
            # resta dentro (|hold| > soglia d'uscita) finché il prezzo non torna alla media
            f["hold"] = np.select([b < 0.5, b > 0.5], [40.0, -40.0], default=0.0)
        else:
            f["hold"] = f["score"]
        f.loc[f["pctb"].isna(), ["score", "hold"]] = np.nan
        if self.trend_filter:
            f.loc[f["sma200"].isna(), ["score", "hold"]] = np.nan
        return f

    def explain(self, row: pd.Series) -> str:
        b = row["pctb"]
        trend = ""
        if self.trend_filter and pd.notna(row.get("sma200")):
            trend = ", sopra la media a 200 giorni" if row["close"] > row["sma200"] else ", sotto la media a 200 giorni"
        if b < 0:
            return f"prezzo sotto la banda di Bollinger bassa (%B {b:.2f}){trend}: eccesso di vendite, rimbalzo atteso"
        if b < 0.05:
            return f"prezzo sulla banda bassa (%B {b:.2f}){trend}: vicino a un eccesso di vendite"
        if b > 1:
            return f"prezzo sopra la banda alta (%B {b:.2f}){trend}: eccesso di acquisti"
        if b > 0.95:
            return f"prezzo sulla banda alta (%B {b:.2f}){trend}: vicino a un eccesso di acquisti"
        return f"prezzo dentro le bande (%B {b:.2f}){trend}: nessun eccesso"
