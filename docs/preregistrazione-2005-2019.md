# Pre-registrazione: test PULSE su 2005-2019

Scritta **prima** di scaricare e guardare i dati 2005-2019. Le regole qui sotto valgono così come sono:
dopo aver visto i risultati non si cambia nulla, né il codice né le soglie. Qualsiasi modifica successiva richiede
una nuova pre-registrazione e una verifica su dati nuovi (paper trading in avanti).

## Versione congelata

Impronta del codice che decide i trade (SHA-256 dei 9 file elencati in fondo): **`3d2d4af3b02ca4a1`**

- **Strategie:** solo long. Trend EMA20/50 con RSI 50-75 per entrare, isteresi per restare, confidenza dal momentum
  a 6 mesi. Mean reversion Bollinger su SPY/QQQ/IWM sopra la MA200.
- **Comitato AI:** peso **0**. Non partecipa: il test è solo sulla parte deterministica.
- **Rischio:** 5% per posizione, massimo 5 posizioni, bracket a 2/3 ATR, −2% giornaliero sul satellite, drawdown
  del satellite al 5%.
- **Core:** SPY con il 3% di liquidità e banda di ribilanciamento al 2%.
- **Walk-forward:** parametri scelti sui 6 mesi precedenti, provati sui 3 successivi. Costi: 1 bp di commissione
  + 5 bp di slippage. Ordini eseguiti all'apertura del giorno dopo il segnale.
- **Universo:** gli stessi 15 titoli. Bias di selezione noto: sono scelti oggi, e AVGO (2009), V (2008) e META (2012)
  entrano solo quando esistono. L'universo storico reale sarà un passo successivo.

## Portafogli confrontati (periodo 3/1/2005 - 31/12/2019)

| | Portafoglio | Regole |
|---|---|---|
| A | 100% SPY | buy & hold |
| B | 75% SPY + 25% liquidità | ribilanciamento mensile, liquidità a rendimento 0 (prudente) |
| C | Core SPY + satellite PULSE | il default attuale, codice congelato |
| D | 75% SPY + 25% PULSE | satellite da solo come conto separato, ribilanciamento mensile |
| E | SPY con filtro a 200 giorni | a fine mese: SPY sopra la MA200 → 100% SPY, altrimenti liquidità; 6 bp per cambio |

## Metriche e inferenza

- **Per ogni portafoglio:** CAGR, volatilità, Sharpe (tasso privo di rischio = 0), drawdown massimo.
  Correlazione giornaliera tra il satellite PULSE e SPY.
- **Differenza di Sharpe rispetto ad A:** intervallo di confidenza al 90% da un bootstrap circolare a blocchi di 21
  giorni, 5.000 ricampionamenti, seed 7.
- **Deflated Sharpe Ratio** (Bailey e López de Prado) del satellite da solo, con **N = 8 tentativi** (varianti
  V0-V5, satellite da solo, core + satellite).

## Regole di decisione (fissate ora)

1. **Satellite nel core + satellite (C).** Il satellite resta attivo solo se **Sharpe(C) > Sharpe(A)** e il
   **limite inferiore dell'intervallo al 90% di ΔSharpe(C−A) è > 0**. Altrimenti il satellite passa in **modalità
   ombra**: calcola e registra le decisioni ma non invia ordini, e il core tiene SPY.
2. **Filtro a 200 giorni sul core (E).** Si adotta solo se il drawdown massimo di E è migliore di A di **almeno 10
   punti** e il limite inferiore di ΔSharpe(E−A) al 90% è **> −0,10**. Altrimenti no.
3. **Deflated Sharpe Ratio.** Se il DSR del satellite è **< 0,95**, si conclude che "non c'è evidenza di abilità"
   (informativo, coerente con la regola 1).
4. **D (75/25 con conto separato)** è solo informativo: non cambia il default.

Il periodo 2024-2026 è già stato usato e qui non conta. La prova successiva sarà il paper trading in avanti,
anch'esso con regole fissate prima.

## Impronte dei file congelati

Verifica: `python main.py fingerprint` deve restituire la stessa impronta.

```
f2ff88d4a6ef2d7db50185a6ef6cd574fda57d4c923ef4e2f6549995e88e098f  desk/config.py
8a750deee28173602c63d6fc8f945264754b2d8fe527dccf0ae6f3d765141299  desk/reflex.py
1d414a0303f63e7f3ba50733f2e2603e7561c7bf4d47ca90db0264934bef626d  desk/risk.py
5e0e5b9af0da9ca19e015a73a240b119061486829738c4b1711f2b4dd366a2b6  desk/backtest.py
e81797bf217a64e30bb59fe6840556ce977706828234e15f0e2f7d0d0597f6bb  desk/strategies/__init__.py
6b4e10e0ed09e43628ecb41b076f05b90f7f6e2d408c6f44d928ac06c3c84eb4  desk/strategies/base.py
f0e08c725975bc11d2588d58475191f7d0ff00de1efedada1e09171c0ab8144c  desk/strategies/meanrev.py
df2d7318135b2de228b319dc32f5748426da1d8c3244b6beeabc8f819aa6b257  desk/strategies/regime.py
012550741f96267f94f377f365f6dbe8854f8c855ced0e7f25cbaa7bb8735762  desk/strategies/trend.py
```
