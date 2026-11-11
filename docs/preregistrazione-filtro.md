# Pre-registrazione: filtro a 200 giorni fuori dal campione USA 2005-2019

Scritta prima di scaricare i dati di questi mercati. Suggerita da Grok: se il filtro regge su più mercati, il
risultato è molto più credibile di un solo Sharpe americano.

## Regola testata (identica a quella del core, nessun parametro cambiato)

A fine mese, se l'indice chiude sopra la sua media a 200 giorni, si resta investiti per tutto il mese dopo.
Altrimenti si va in liquidità, con rendimento 0. Ogni cambio costa 6 bp. Il confronto è con il buy & hold dello
stesso indice.

## Mercati e periodi

| Simbolo | Periodo | Note |
|---|---|---|
| ^GSPC | 1950-2004 | S&P 500 prima del periodo già usato, solo prezzo |
| ^GDAXI | 1988-ott 2026 | DAX, total return |
| ^FTSE | 1984-ott 2026 | FTSE 100, solo prezzo |
| ^N225 | 1965-ott 2026 | Nikkei 225, solo prezzo |
| EFA | 2001-ott 2026 | ETF sviluppati non USA, con dividendi |
| URTH | 2012-ott 2026 | ETF MSCI World, con dividendi |

I primi 210 giorni servono a calcolare la media e non si valutano.

Tre distorsioni note:
- Per gli indici "solo prezzo" mancano i dividendi. Questo penalizza di più il buy & hold, che è sempre investito,
  e quindi **favorisce il filtro**.
- La liquidità a rendimento 0 **penalizza il filtro**.
- Gli indici in valuta locale non includono l'effetto cambio per un investitore in euro.

## Metriche

- **Per ogni mercato:** CAGR, Sharpe, drawdown massimo, quota di tempo investita, uscite all'anno.
- **ΔSharpe rispetto al buy & hold:** intervallo al 90% con bootstrap a blocchi (21 giorni, 5.000, seed 7).
- **Tasse italiane, regime ETF semplificato e prudente:**
  - il filtro paga il 26% su ogni uscita in guadagno;
  - le perdite non compensano i guadagni;
  - il buy & hold paga il 26% solo sul guadagno finale.

## Regole di decisione (fissate ora)

- **F1. Il filtro "regge" in un mercato** se migliora il drawdown massimo di almeno 10 punti e il limite inferiore
  di ΔSharpe al 90% è sopra −0,10. È la stessa soglia della regola 2 del test 2005-2019.
- **F2. Il filtro è credibile fuori dal campione USA** se regge in **almeno 4 mercati su 6**.
- **F3. Prima di soldi veri:**
  - con F2 = NO, il filtro resta solo nel conto paper e nei documenti si scrive che il risultato del 2005-2019
    può essere specifico degli USA;
  - con F2 = SÌ, si può valutare l'uso reale. Il costo fiscale e le operazioni all'anno vanno comunque mostrati
    accanto al risultato, senza soglia.

## Impronta

9 file congelati + `desk/filter_intl.py` + `desk/research.py`: **`7e85c5abca01e8c5`**.
`python main.py filter` si rifiuta di girare se è diversa. Il test si esegue una volta sola.
