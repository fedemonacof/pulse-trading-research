# Risultati del test pre-registrato (2005-01-03 → 2019-12-31, 3775 giorni)

| | Portafoglio | CAGR | Vol | Sharpe | Max DD | ΔSharpe vs A [IC 90%] |
|---|---|---|---|---|---|---|
| A | 100% SPY | +8.9% | 18.3% | 0.56 | -55.2% | — |
| C | Core SPY + satellite PULSE | +9.7% | 17.9% | 0.61 | -55.0% | +0.05 [-0.01, +0.11] |
| B | 75% SPY + 25% liquidità | +6.8% | 13.6% | 0.55 | -44.8% | -0.00 [-0.01, +0.00] |
| D | 75% SPY + 25% PULSE (conto separato) | +7.5% | 14.0% | 0.59 | -45.5% | +0.03 [+0.00, +0.06] |
| E | SPY con filtro a 200 giorni | +9.4% | 12.1% | 0.80 | -20.9% | +0.24 [-0.08, +0.57] |

**Satellite PULSE da solo:** CAGR +2.9%, Sharpe 0.88, max DD -8.1%, correlazione con SPY 0.51, 1235 trade.
**Deflated Sharpe Ratio** (N = 8): 0.97 (Sharpe 0.88 contro una soglia attesa per caso di 0.38).

## Decisioni (regole pre-registrate)

1. Satellite nel core + satellite: **PASSA IN MODALITÀ OMBRA**
2. Filtro a 200 giorni sul core: **ADOTTATO**
3. Evidenza di abilità (DSR ≥ 0,95): **SÌ**

## Decisioni applicate (11/11/2026)

Le regole sono state applicate così come erano state scritte, senza eccezioni:

- **Satellite in modalità ombra** (`SATELLITE_MODE=shadow`). PULSE continua a decidere e a operare su un conto
  virtuale persistente, con prezzi reali e bracket simulati. I suoi trade vanno nel diario come `SHADOW`. Il conto
  vero tiene solo il core.
- **Filtro a 200 giorni sul core** (`CORE_TREND_FILTER=true`). A fine mese: SPY sopra la sua media a 200 giorni →
  core in SPY (97%), altrimenti liquidità.
- **Comitato AI a peso 0** (massimo 0,2). I voti si registrano.
- **Il DSR del satellite (0,97) è sopra 0,95,** ma la regola 1 prevale: l'intervallo di ΔSharpe(C−A) tocca lo zero.
  Il DSR usa un'approssimazione della varianza tra i tentativi (1/T), e l'universo ha un bias di selezione:
  il segnale c'è, il vantaggio nel portafoglio non è dimostrato.
- **Aggiornamento (regola 4 del test sull'universo storico): conclusione 3 RITIRATA.** Su 100 universi di 15 titoli
  estratti fra i membri S&P 500 del 2005, nessuno raggiunge lo Sharpe dei 15 titoli scelti oggi (0,88 contro una
  mediana di 0,41). Il DSR di 0,97 era dovuto al senno di poi nella scelta dei titoli, non alla strategia.
  Vedi [risultati-universo.md](risultati-universo.md).

**Controllo di coerenza** (non è una nuova prova: il periodo ormai è usato). La configurazione implementata, rigirata
su 2005-2019, dà CAGR +8,2%, Sharpe 0,73 e max DD −21,8%, contro il portafoglio E (+9,4%, 0,80, −20,9%) e SPY (+8,9%,
0,56, −55,2%). La differenza con E viene dal 3% di liquidità e dai costi.

Nuova impronta del codice dopo le decisioni: **`7d054586a815bd0f`** (`python main.py fingerprint`).

## Regola per riattivare il satellite (fissata ora, prima dei dati in avanti)

Il satellite torna a inviare ordini veri solo se, nel paper trading in avanti in modalità ombra, valgono **tutte**
queste condizioni:

1. almeno **12 mesi** di dati e almeno **100 trade** `SHADOW` chiusi;
2. P&L del satellite virtuale **> 0 dopo i costi**;
3. Sharpe del portafoglio "core + satellite virtuale" **maggiore** di quello del solo core, con il **limite inferiore
   dell'intervallo al 90%** di ΔSharpe (bootstrap a blocchi di 21 giorni) **> 0**;
4. il codice che decide i trade è rimasto quello con l'impronta qui sopra.

**Quale ombra conta (fissato l'11/11/2026, prima di qualsiasi dato in avanti).** Conta solo l'ombra sull'universo
**a regola**: i 100 membri attuali dell'S&P 500 con più volume in dollari a 60 giorni, ricalcolati ogni mese
(`desk/shadow_universe.py`), più QQQ e IWM. I 15 titoli scelti a mano servono solo come confronto e si
ricostruiscono a posteriori con il backtester sugli stessi mesi. Aspettativa realistica: sull'S&P 500 storico il
satellite ha fatto Sharpe 0,39 contro 0,56 di SPY, quindi superare questa regola è improbabile. Con 12 mesi
l'errore standard dello Sharpe è circa ±1: il vero filtro è il limite inferiore dell'intervallo, non la stima.

**Congelamento e interventi.** Dal giorno in cui parte il paper trading, i 9 file con l'impronta qui sopra non si
toccano per 12 mesi. I guasti di infrastruttura (dati, connessione ad Alpaca, scheduler, diario, dashboard,
notifiche) si possono correggere **fuori da quei file**. Ogni intervento va scritto in
[registro-interventi.md](registro-interventi.md) con data, file, motivo e conferma che l'impronta è invariata.
Se un guasto si può correggere solo dentro i 9 file, l'ombra riparte da zero con una nuova impronta.

Se anche una sola condizione manca, il satellite resta in ombra. Il comitato AI segue la stessa logica. Le
condizioni precise, cioè Spearman a 5 giorni in eccesso su SPY, t > 2, valore aggiunto sul punteggio delle
strategie e almeno 50 finestre, sono in [preregistrazione-avanti.md](preregistrazione-avanti.md). Lo stesso documento
spiega perché la fase in avanti serve a trovare guasti e non può dimostrare un vantaggio.
