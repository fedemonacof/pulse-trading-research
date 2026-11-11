# Pre-registrazione: fase in avanti (paper trading)

Scritta l'11/11/2026, prima di qualsiasi dato in avanti, insieme al congelamento descritto in
[risultati-2005-2019.md](risultati-2005-2019.md) e [registro-interventi.md](registro-interventi.md).

## Cosa questa fase può e non può dimostrare

Lo Sharpe annuo ha un errore standard di circa 1/√T, con T in anni. La probabilità che il limite inferiore
dell'IC90% superi lo zero è quindi circa Φ(SR·√T − 1,645).

| Sharpe vero | 12 mesi | 24 mesi | Anni per il 50% |
|---|---|---|---|
| 0,3 | 9% | 11% | 30 |
| 0,5 | 13% | 17% | 11 |

Con ΔSharpe va peggio, perché si misura una differenza. **La fase in avanti non può dimostrare un vantaggio.**
Serve a scoprire bug, differenze di esecuzione rispetto al backtest e disastri. La soglia di riattivazione resta
quella già fissata e non si abbassa: se passa, bene, ma non ci si aspetta che succeda.

## Confronti (dichiarati prima)

1. **Riattivazione del satellite**, valore marginale: "core filtrato + ombra" contro "core filtrato".
   Si usano le condizioni già fissate: 12 mesi, 100 trade, P&L > 0, limite inferiore di ΔSharpe IC90% > 0,
   impronta invariata.
2. **Soldi veri a PULSE, in qualsiasi forma:** tutto il sistema contro il buy & hold di un ETF UCITS
   ad accumulazione, al netto delle tasse italiane. Se il buy & hold netto non viene battuto, PULSE non gestisce
   soldi veri.

Si registrano entrambi.

## Controlli per i guasti (ogni mese, dal primo)

Ogni mese il backtester rigira gli stessi giorni con lo stesso universo a regola. Il risultato si confronta con
l'ombra.

- **Ordini:** almeno l'80% delle entrate dell'ombra deve comparire anche nel backtest dello stesso periodo,
  stesso titolo ed entrata entro 1 giorno di borsa, e viceversa.
- **P&L:** lo scarto medio di P&L per trade abbinato fra ombra e backtest deve restare entro **50 bp**.
- Se uno dei due controlli fallisce per **2 mesi di fila**, si indaga. La correzione va nel registro degli
  interventi. Se tocca i 9 file congelati, l'ombra riparte da zero.

## Controllo dei disastri a 6 mesi

Se dopo 6 mesi il **limite superiore** dell'IC90% di ΔSharpe(core filtrato + ombra − core filtrato) è sotto 0,
l'ombra si chiude e si cerca la causa. Questo succede solo con uno Sharpe osservato di circa −2,3 o peggio: non
è un giudizio di inutilità, ma un segnale che qualcosa è rotto.

## Comitato AI (peso 0, voti registrati)

- **Voti validi:** solo quelli dati dopo la data limite di addestramento del modello usato. Se cambiano il modello
  o il prompt, il conteggio riparte da zero.
- **Metrica principale:** correlazione di Spearman fra la convinzione con segno e il rendimento a 5 giorni in
  eccesso rispetto a SPY. Si calcola su tutti i titoli votati e su finestre di 5 giorni che non si sovrappongono,
  poi si fa la media nel tempo; t calcolato sulla serie delle correlazioni.
- **Valore aggiunto:** regressione del rendimento in eccesso a 5 giorni sul punteggio delle strategie e sul voto
  del comitato. Il coefficiente del comitato deve essere positivo, e il voto depurato dalla parte spiegata dal
  punteggio deve avere una correlazione positiva.
- **Secondarie:** Brier score delle direzioni e grafico di affidabilità.
- **Peso 0,1 solo con tutte queste condizioni:**
  - almeno 12 mesi;
  - almeno 50 finestre indipendenti;
  - correlazione media > 0 con t > 2;
  - valore aggiunto positivo rispetto al punteggio delle strategie.

  Una correlazione realistica sta fra 0,02 e 0,05: è probabile che servano 1-2 anni o più.

## Strumenti (pronti dall'11/11/2026)

- **`python main.py forward`** ([desk/forward.py](../desk/forward.py)) calcola i quattro blocchi e scrive
  `reports/forward-AAAA-MM.md`.
  - Lo **scarto di P&L** è la media del valore assoluto della differenza di `pnl_pct` fra trade abbinati,
    in bp.
  - Il backtest usa i parametri di default (20/50/2,0), uguali a quelli live, e gli universi mensili salvati
    in `shadow_universe_history`.
  - L'esito dei controlli di ogni mese si salva in `forward_checks`, per riconoscere due fallimenti di fila.
- **Il diario salva:**
  - `votes`: ogni voto del comitato, anche sotto la soglia, con modello e prezzo;
  - `signals`: i punteggi delle strategie non pesati, a ogni giro;
  - `equity` con mode `SHADOW`: il P&L cumulato dell'ombra.
- **Voti validi:** per la data limite di addestramento si usa `COMMITTEE_CUTOFF` (default 2026-07-01).
  Il cambio di modello azzera il conteggio in automatico; il cambio di prompt va annotato nel registro degli
  interventi.
- **Limite noto:** il confronto con il buy & hold al netto delle tasse si fa a fine periodo, con le vendite
  reali. Il report mensile mostra solo lo Sharpe di SPY.
