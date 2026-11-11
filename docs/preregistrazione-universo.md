# Pre-registrazione: il satellite su un universo storico dell'S&P 500 (2005-2019)

Questo documento è scritto **prima** di eseguire qualsiasi backtest su questo universo. Finora ho guardato solo
due cose: la composizione dell'indice e quanti titoli hanno un prezzo, cioè la copertura dei dati. Il rendimento
non l'ho guardato. Le regole sotto non cambiano dopo aver visto i risultati.

## Domanda

Il test 2005-2019 ha dato al satellite un Deflated Sharpe di 0,97. Quel test però usava 15 titoli **scelti oggi**,
fra cui NVDA, AVGO, META e AAPL, cioè i vincitori degli ultimi vent'anni. Le domande sono due:

1. Il risultato dipende dalla strategia o dal fatto che i titoli sono stati scelti col senno di poi?
2. La strategia funziona su un universo che si poteva conoscere a ogni data, cioè i membri dell'S&P 500 di quel
   giorno, compresi quelli usciti poi dall'indice?

## Versione congelata

Il codice che decide i trade è lo stesso del test precedente. L'impronta dei 9 file congelati
(`python main.py fingerprint`) è `7d054586a815bd0f`.

Impronta di questo test: 9 file congelati + `desk/universe.py` + `desk/research.py`.
Il comando `python main.py universe` si rifiuta di girare se è diversa:
**`49b6bafe09ba6e2c`**

Il satellite gira da solo (`core_enabled=False`, comitato a peso 0), con lo stesso walk-forward, gli stessi costi
(1 bp + 5 bp) e gli stessi limiti di rischio. Periodo valutato: 3/1/2005 - 31/12/2019.

## Universo storico

- **Composizione:** CSV pubblico `github.com/fja05680/sp500`. Per ogni data indica i componenti in vigore.
- **Prezzi:** Yahoo Finance, rettificati per split e dividendi. Copertura dei giorni-membro 2005-2019: 68,8% (1.297.122 su 1.886.453, 529 titoli con prezzi su 872).
  **Sotto il 90%: per la regola 5 questo test può solo dare un esito negativo.**
  I titoli mancanti sono soprattutto falliti, acquisiti o con ticker cambiato. Mancare i falliti rende i risultati
  **migliori del vero** (bias di sopravvivenza residuo). Per questo un esito positivo vale solo con una copertura
  di almeno il 90%.
- **Entrate:** un titolo può aprire una posizione solo nei giorni in cui era nell'indice.
- **Uscite:** chi esce dall'indice esce dalle posizioni con le regole normali. Chi smette di quotare viene chiuso
  all'ultima apertura disponibile.
- **ETF:** SPY, QQQ e IWM restano sempre nell'universo, come nella versione congelata. La mean reversion lavora
  su questi.

## Esperimenti

| | Universo | Scopo |
|---|---|---|
| U1 | S&P 500 storico, circa 850 titoli nel periodo | la strategia vale su un universo senza senno di poi? |
| U2 | i 15 titoli fissi (SPY, QQQ, IWM + 12 scelti oggi) | il riferimento del test precedente, rieseguito |
| U3 | 100 universi casuali: SPY, QQQ, IWM + 12 titoli estratti fra i membri del 3/1/2005 che hanno prezzi (285 su 495, seed 11) | quanto è "fortunata" la scelta dei 12 di oggi? |

In U3 si estrae solo fra i titoli con prezzi, quindi soprattutto fra quelli sopravvissuti. Questo favorisce U3:
la regola 4 diventa più difficile da far scattare ed è quindi prudente nel senso giusto.

## Metriche

Per ogni universo: CAGR, volatilità, Sharpe (tasso privo di rischio 0), drawdown massimo, numero di trade.
Per U1 si calcolano anche:
- il **Deflated Sharpe Ratio** con **N = 10 tentativi**: gli 8 del test precedente, più U1, più la famiglia U3
  contata come uno;
- la correlazione con SPY.

## Regole di decisione (fissate ora)

4. **Bias di selezione dei 15 titoli.** Si guarda la quota degli universi casuali U3 con Sharpe ≥ Sharpe(U2).
   Se è **≤ 10%**, la scelta dei 12 titoli è eccezionale rispetto al caso. In quel caso la conclusione 3 del test
   precedente ("DSR 0,97, evidenza di abilità") viene **ritirata**: era dovuta al senno di poi.
   Altrimenti la conclusione resta valida.
5. **Evidenza sull'universo ampio.** C'è evidenza solo se **DSR(U1) ≥ 0,95** e la copertura dei prezzi è
   **≥ 90%**. Se sì, il satellite in ombra passerà all'universo S&P 500 corrente: è lavoro separato, da fare dopo.
   Se no, il satellite in ombra resta sui 15 titoli e nei documenti si scrive "nessuna evidenza oltre i 15 titoli".
6. **Nessuna regola riattiva il satellite con soldi veri.** Vale solo la regola in avanti già scritta in
   `docs/risultati-2005-2019.md`: 12 mesi, 100 trade in ombra, P&L positivo e intervallo di ΔSharpe sopra zero.

Il test si esegue **una volta sola**. Se il codice di `desk/universe.py` va corretto dopo l'esecuzione, la
correzione richiede una nuova pre-registrazione e il risultato precedente resta nel documento.
