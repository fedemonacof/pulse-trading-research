# Risultati: filtro a 200 giorni fuori dal campione USA 2005-2019

| Mercato | Periodo | CAGR B&H → filtro | Sharpe B&H → filtro | ΔSharpe [IC 90%] | Max DD B&H → filtro | Investito | Uscite/anno | CAGR netto tasse B&H → filtro | Regge |
|---|---|---|---|---|---|---|---|---|---|
| ^GSPC | 1950-2004 | +8.1% → +7.2% | 0.62 → 0.70 | +0.08 [-0.08, +0.26] | -49.1% → -33.2% | 69% | 0.7 | +7.5% → +5.2% | SÌ |
| ^GDAXI | 1988-2026 | +8.1% → +7.7% | 0.47 → 0.58 | +0.11 [-0.10, +0.31] | -72.7% → -31.8% | 71% | 0.7 | +7.3% → +5.5% | SÌ |
| ^FTSE | 1984-2026 | +5.5% → +3.6% | 0.40 → 0.36 | -0.03 [-0.22, +0.16] | -52.6% → -45.0% | 69% | 1.0 | +4.8% → +2.1% | NO |
| ^N225 | 1965-2026 | +6.7% → +6.0% | 0.42 → 0.49 | +0.07 [-0.10, +0.23] | -81.9% → -52.7% | 63% | 0.9 | +6.2% → +3.8% | SÌ |
| EFA | 2002-2026 | +7.1% → +6.7% | 0.43 → 0.54 | +0.11 [-0.13, +0.35] | -61.0% → -31.5% | 72% | 0.8 | +6.0% → +4.7% | NO |
| URTH | 2012-2026 | +12.1% → +8.7% | 0.76 → 0.74 | -0.02 [-0.34, +0.30] | -34.0% → -15.0% | 81% | 0.7 | +10.3% → +6.3% | NO |

## Decisioni (regole pre-registrate)

F1. Il filtro regge in **3 mercati su 6**.
F2. Filtro credibile fuori dal campione USA (almeno 4 su 6): **NO**

## Cosa significa

- **Il filtro funziona sempre come assicurazione.** In tutti e 6 i mercati riduce il drawdown massimo, da 8 a
  41 punti: DAX da −73% a −32%, Nikkei da −82% a −53%.
- **Non è un vantaggio di rendimento.** Lo Sharpe sale in 4 mercati su 6, ma l'intervallo al 90% comprende sempre
  lo zero. Il CAGR scende in tutti i mercati, da 0,4 a 3,4 punti l'anno.
- **Con le tasse italiane il costo raddoppia.** Il buy & hold rinvia la tassa alla fine, mentre il filtro la paga a
  ogni uscita in guadagno e non recupera le perdite. Il CAGR netto scende da 1,3 a 4 punti l'anno. Le uscite sono
  circa 0,7-1 all'anno.
- **F2 = NO (3 mercati su 6).** EFA e URTH migliorano molto il drawdown ma non superano la soglia sullo Sharpe;
  il FTSE non migliora abbastanza nessuno dei due. Per la regola F3 il filtro resta nel conto paper.
  Lo Sharpe di 0,80 del 2005-2019 è probabilmente in parte una particolarità di quel periodo negli USA:
  due crolli lenti, 2008 e la discesa del 2001-2002 alla sua soglia, che sono il caso ideale per un filtro mensile.
- **In pratica,** per soldi veri la scelta è fra rendimento (buy & hold) e drawdown più piccoli (filtro). Non c'è
  un pranzo gratis. Per un investitore italiano il buy & hold di un ETF UCITS ad accumulazione è più efficiente
  fiscalmente.

## Limiti del modello fiscale (precisazioni ricevute dopo l'esecuzione, da verificare con un commercialista)

- **Perdite:** sugli ETF non si compensano con i guadagni di altri ETF, che sono redditi di capitale. Si possono
  però compensare entro 4 anni con altri redditi diversi, per esempio guadagni su singole azioni, ETC o
  certificati. Il modello, che contiene solo ETF, le tratta come perse: è corretto qui, ma nella realtà dipende dal
  resto del conto.
- **Imposta di bollo dello 0,2% l'anno** sul deposito: non è nel modello. Pesa su entrambe le strategie, quindi
  abbassa tutti e due i rendimenti netti ma cambia poco il confronto.
- **ETF americani (SPY, EFA, URTH) detenuti direttamente** da un residente italiano sono fondi non armonizzati:
  i guadagni vanno a IRPEF progressiva, non al 26%. Il modello usa il 26%, che vale per gli ETF UCITS.
- La quota di titoli di Stato dentro alcuni ETF è tassata al 12,5%, e il regime (amministrato o dichiarativo)
  cambia gli adempimenti. Questi aspetti non sono nel modello.

Queste note non sono consulenza fiscale o finanziaria.
