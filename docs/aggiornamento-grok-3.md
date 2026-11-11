Ciao Grok, ti aggiorno. Poi c'è un cambio di direzione da discutere.

**Fatto: le tue regole sono nella pre-registrazione della fase in avanti.**
- Potenza dichiarata: 9-13% a 12 mesi.
- Confronto marginale per la riattivazione; buy & hold UCITS al netto delle tasse per decidere sui soldi veri.
- Controllo dei disastri a 6 mesi.
- Ombra contro backtest ogni mese: entrate abbinate ≥ 80% in entrambe le direzioni, scarto medio |Δpnl_pct| ≤ 50 bp; due mesi falliti di fila → indagare.
- Comitato: Spearman a 5 giorni in eccesso su SPY su finestre che non si sovrappongono, regressione sul punteggio delle strategie, Spearman del voto depurato, Brier. Peso 0,1 solo con 12 mesi, 50 finestre, t > 2 e valore aggiunto positivo.

Il report mensile è implementato e testato. Il diario ora salva:
- i voti grezzi del comitato, anche sotto soglia, con il modello;
- i punteggi delle strategie non pesati;
- il P&L giornaliero dell'ombra;
- l'universo di ogni mese.

**Il cambio di direzione.** Quello che volevo davvero era un bot long E short con orizzonte di 1-2 giorni. Quello che c'è adesso è swing long-only: holding medio di circa 17 giorni, short tolti perché nel 2019-2024 perdevano. Vorrei aprire un filone di ricerca separato, con lo stesso rigore:
- pre-registrazione;
- universo S&P 500 point-in-time;
- costi realistici;
- impronta congelata;
- solo paper.

Domande:
1. Quali famiglie di segnali a 1-2 giorni hanno ancora evidenza pubblicata dopo i costi su large cap USA? Penso a reversal di breve (Connors RSI(2)), rendimenti overnight contro intraday, gap, deriva post-utili, ribilanciamento degli ETF a leva. Quali sono ormai morte?
2. Costi: per un orizzonte di 1-2 giorni che slippage e che costo di prestito per gli short useresti nel backtest? I 5 bp attuali bastano su titoli molto liquidi?
3. Long/short market neutral (gambe bilanciate) o direzionale? Con 12 mesi di potenza statistica così bassa, il market neutral almeno riduce la varianza: ha senso partire da lì?
4. Vincoli pratici con Alpaca: PDT sotto 25k$ (con 1-2 giorni non dovrebbero essere day trade), short solo con conto margine, e da residente italiano il conto live è incerto. Vedi altri ostacoli?
5. Quanti segnali o varianti posso provare prima che il Deflated Sharpe renda inutile il test? Mi conviene fissare N in anticipo?
