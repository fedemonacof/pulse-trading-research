# Ricerca: miglioramento delle strategie PULSE (11/11/2026)

## Metodo

- **Dati:** Yahoo Finance, 10 anni giornalieri sulle 15 large cap/ETF di default, prezzi rettificati.
- **Sviluppo:** 4/11/2019 → 5/11/2024 (5 anni, comprende il crollo del 2020 e il mercato ribassista del 2022).
  Le modifiche sono state scelte guardando solo questo periodo.
- **Verifica:** 6/11/2024 → 10/11/2026 (2 anni), eseguita **una sola volta** alla fine. Va detto che questo periodo
  era già stato visto con la versione precedente, quindi non è perfettamente "vergine".
- **Ogni backtest** è walk-forward (parametri scelti sui 6 mesi precedenti ogni trimestre), con 1 bp di commissione
  e 5 bp di slippage, ordini bracket e gli stessi limiti di rischio del bot dal vivo.
- **Benchmark giusto:** SPY alla stessa esposizione media. Con 5 posizioni al 5% il bot investe al massimo il 25%,
  quindi battere SPY al 100% in un periodo rialzista è quasi impossibile per costruzione.

## Diagnosi della versione precedente (periodo di sviluppo)

| Problema | Effetto |
|---|---|
| Short su large cap USA | −5.126 $, 32% di vincenti: si va contro la deriva rialzista |
| Il filtro RSI faceva anche USCIRE | i trade vincenti venivano chiusi appena il titolo diventava "ipercomprato" |
| Uscite a segnale | −16.131 $ in totale |
| Rotazione | 155 trade all'anno |

## Modifiche (dalla letteratura, decise prima di guardare i risultati)

1. **Solo long** (`ALLOW_SHORT=false`): la versione classica del trend following su azioni.
2. **Isteresi:** l'RSI conferma solo l'entrata; si resta dentro finché l'EMA20 è sopra l'EMA50.
   Per la mean reversion si resta finché il prezzo non torna alla banda centrale.
3. **Confidenza dal momentum a 6 mesi** (Jegadeesh-Titman): i 5 posti vanno ai trend più forti.
4. **Mean reversion stile Connors:** si comprano i ribassi solo se il prezzo è sopra la media a 200 giorni.

## Risultati sul periodo di sviluppo (5 anni)

| Variante | Totale | Sharpe | Max DD | Trade | PF |
|---|---|---|---|---|---|
| V0 versione precedente | +5,8% | 0,28 | −6,8% | 774 | 1,08 |
| V1 + solo long | +12,8% | 0,64 | −6,7% | 674 | 1,21 |
| V2 + isteresi | +27,2% | 1,18 | −5,9% | 436 | 1,53 |
| V3 + momentum 6 mesi | +28,3% | 1,28 | −5,2% | 439 | 1,56 |
| **V4 + filtro MA200 sulla MR (adottata)** | **+29,8%** | **1,32** | **−4,8%** | 429 | 1,62 |
| V5 + target a 5 ATR (scartata) | +26,0% | 1,15 | −4,8% | 281 | 1,67 |
| SPY alla stessa esposizione (~20%) | +17,5% | 0,78 | | | |
| SPY buy & hold | +102,7% | 0,78 | −33,7% | | |

## Verifica sugli ultimi 2 anni (una sola esecuzione)

| | Totale | Sharpe | Max DD | Trade | PF |
|---|---|---|---|---|---|
| V0 versione precedente | −4,3% | −0,55 | −4,8% | 296 | 0,86 |
| **V4 adottata** | **+0,7%** | 0,12 | −4,9% | 206 | 1,03 |
| SPY alla stessa esposizione (18%) | +5,3% | 0,86 | −3,6% | | |
| SPY buy & hold | +29,8% | 0,86 | −18,8% | | |

## Conclusione

Le modifiche migliorano la strategia in entrambi i periodi. Sul periodo di sviluppo battono SPY a parità di
esposizione, con Sharpe 1,32 contro 0,78. **Sugli ultimi 2 anni invece non lo battono** (Sharpe 0,12 contro 0,86):
si passa da una perdita a un pareggio, non a un vantaggio.

Il risultato più probabile è che il vantaggio sia piccolo e dipenda dal periodo. Non ho ritoccato nulla dopo la
verifica, perché sarebbe overfitting.

La confidenza resta poco calibrata: la fascia 85-100 vince il 37%. Il dato da guardare nei prossimi mesi di paper
trading è se i trade con confidenza alta vincono più spesso degli altri.

## Core + satellite (adottato come default)

Struttura: SPY (il core) tiene tutto il capitale che il satellite PULSE non usa, meno il 3% di liquidità.
Il core si ribilancia solo se si sposta di oltre il 2%. Così il conto resta investito al ~95% e batte SPY
solo se le scommesse del satellite rendono più di SPY.

Regole di rischio cambiate di conseguenza:
- **perdita giornaliera −2%** e **drawdown** si misurano sul P&L del satellite: un normale −2% di SPY non deve
  vendere l'indice;
- **drawdown del satellite oltre il 5% dell'equity:** il satellite si ferma, il core resta;
- **kill switch:** chiude tutto, core compreso;
- **stop e trailing:** valgono solo per il satellite;
- **scelta dei parametri walk-forward:** si fa sull'information ratio rispetto a SPY.

I parametri (3% di liquidità, banda del 2%, drawdown del satellite al 5%) sono stati fissati prima di guardare i risultati.

| Periodo | Core + satellite | SPY buy & hold | Attivo | Tracking error | IR | Max DD (vs SPY) |
|---|---|---|---|---|---|---|
| Sviluppo 2019-2024 | **+114,9%** | +102,7% | **+12,2%** | 2,6% | +0,43 | −33,4% (−33,7%) |
| Verifica 2024-2026 (una sola volta) | +23,5% | **+29,8%** | **−6,3%** | 2,7% | −0,98 | −18,3% (−18,8%) |

La struttura fa ciò che deve: segue SPY da vicino, con lo stesso rischio. Il risultato dipende tutto dal satellite,
che nel 2019-2024 ha aggiunto valore e negli ultimi 2 anni ne ha tolto. **Negli ultimi 2 anni non batte SPY.**
Il peggioramento comprende anche il costo del 3% tenuto in liquidità e quello dei ribilanciamenti.
