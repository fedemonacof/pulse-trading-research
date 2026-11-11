# Risultati v1 (NON VALIDI): universo storico S&P 500 (2005-01-03 → 2019-12-31)

> **Esecuzione v1, conservata come da pre-registrazione ma non valida.** Il risultato dell'universo ampio
> (U1) dipende da un errore nei dati. La serie Yahoo di GR (Goodrich) ha 614 barre con aperture impossibili,
> per esempio un'apertura a 448 $ con una chiusura a 57 $. Quattro trade su GR valgono −94.000 $, quasi tutta la
> perdita di U1. Anche EP, CPWR e FNMA hanno barre impossibili.
> Correzione e nuova esecuzione: `docs/preregistrazione-universo-v2.md`.

Copertura dei prezzi: **68.8%** dei giorni-membro (1,297,122 su 1,886,453).

| Satellite PULSE da solo | CAGR | Vol | Sharpe | Max DD | Trade |
|---|---|---|---|---|---|
| S&P 500 storico (point-in-time) | -6.9% | 18.4% | -0.28 | -72.9% | 1372 |
| 15 titoli scelti oggi | +2.9% | 3.3% | 0.88 | -8.1% | 1235 |
| SPY buy & hold (riferimento) | +8.9% | 18.3% | 0.56 | -55.2% | |

**100 universi casuali** (12 titoli presi a caso tra i membri del 3/1/2005 + SPY, QQQ, IWM): Sharpe del satellite al 10°, 50° e 90° percentile = 0.15, 0.42, 0.64. Quota con Sharpe ≥ quello dei 15 titoli scelti oggi: **0%**.

**Deflated Sharpe Ratio** dell'universo ampio (N = 10): 0.00. Correlazione con SPY 0.12.

## Decisioni (regole pre-registrate)

4. Bias di selezione dei 15 titoli: **SÌ**
5. Evidenza sull'universo ampio: **NO** (copertura sotto il 90%: un esito positivo non sarebbe stato accettato)
