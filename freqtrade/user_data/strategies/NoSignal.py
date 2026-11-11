"""Strategia vuota per il dry-run di riconciliazione di PULSE-CT (criterio 7).

Non genera mai segnali di entrata o di uscita: gli ordini arrivano solo da PULSE via REST (forceenter e
forceexit) secondo il calendario fisso. ROI e stop sono fuori portata, così freqtrade non chiude nulla da solo.
"""
from pandas import DataFrame

from freqtrade.strategy import IStrategy


class NoSignal(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    trailing_stop = False
    use_exit_signal = False
    process_only_new_candles = True
    startup_candle_count = 0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe
