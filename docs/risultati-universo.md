# Risultati: universo storico S&P 500 (2005-01-03 → 2019-12-31)

Copertura dei prezzi: **68.4%** dei giorni-membro (1,291,185 su 1,886,453). Serie escluse per dati impossibili: CPWR, EP, FNMA, GR.

| Satellite PULSE da solo | CAGR | Vol | Sharpe | Max DD | Trade |
|---|---|---|---|---|---|
| S&P 500 storico (point-in-time) | +1.7% | 4.6% | 0.39 | -14.4% | 1338 |
| 15 titoli scelti oggi | +2.9% | 3.3% | 0.88 | -8.1% | 1235 |
| SPY buy & hold (riferimento) | +8.9% | 18.3% | 0.56 | -55.2% | |

**100 universi casuali** (12 titoli presi a caso tra i membri del 3/1/2005 + SPY, QQQ, IWM): Sharpe del satellite al 10°, 50° e 90° percentile = 0.25, 0.41, 0.62. Quota con Sharpe ≥ quello dei 15 titoli scelti oggi: **0%**.

**Deflated Sharpe Ratio** dell'universo ampio (N = 10): 0.47. Correlazione con SPY 0.51.

## Decisioni (regole pre-registrate)

4. Bias di selezione dei 15 titoli: **SÌ**
5. Evidenza sull'universo ampio: **NO** (copertura sotto il 90%: un esito positivo non sarebbe stato accettato)

## Cosa significa

- **I 15 titoli scelti oggi erano la causa del risultato.** Il satellite su quei 15 ha Sharpe 0,88. Su 15 titoli
  presi a caso fra i membri del 2005 ha una mediana di 0,41, e nessuno dei 100 universi arriva a 0,88. Il "segnale"
  del test precedente (DSR 0,97) era quindi senno di poi: conoscere oggi quali titoli sarebbero diventati NVDA,
  AAPL o AVGO.
- **Sull'universo che si poteva conoscere davvero, la strategia non mostra abilità.** Sullo storico dell'S&P 500
  ha Sharpe 0,39, contro 0,56 di SPY, e DSR 0,47. Con poco capitale investito rende +1,7% l'anno contro +8,9%.
  Il dato è anche troppo generoso: mancano i prezzi del 31,6% dei giorni-membro, soprattutto titoli falliti o
  acquisiti.
- **Cosa cambia nel bot:** niente nel codice. Il satellite resta in ombra sui 15 titoli. L'universo ampio non
  passa al satellite perché la regola 5 non è soddisfatta. La sola via per riattivarlo resta la regola in avanti
  (12 mesi, 100 trade in ombra, ΔSharpe con intervallo sopra zero).
- **La parte che ha retto a entrambi i test è il core SPY con il filtro a 200 giorni.** Non batte SPY in
  rendimento, ma nel 2005-2019 ha dimezzato il drawdown (−21,8% contro −55,2%).

Esecuzione v1 (non valida per un errore nei dati di GR): [risultati-universo-v1-non-valido.md](risultati-universo-v1-non-valido.md).
Pre-registrazioni: [v1](preregistrazione-universo.md), [v2](preregistrazione-universo-v2.md).
