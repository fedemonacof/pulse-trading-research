Ciao Grok, ho applicato i tuoi quattro punti. Ecco cosa è venuto fuori.

**1. L'ombra ora usa un universo definito da una regola.** I 100 membri attuali dell'S&P 500 con più volume in
dollari a 60 giorni, ricalcolati ogni mese, più QQQ e IWM. Le posizioni già aperte restano valutate anche se il
titolo esce dalla lista. Prima di qualsiasi dato in avanti ho scritto che conta solo questa ombra per la
riattivazione. I 15 titoli li ricostruisco a posteriori col backtester sugli stessi mesi, perché la strategia è
deterministica. Aspettativa scritta: improbabile che passi.

**2. Filtro a 200 giorni fuori dagli USA**, pre-registrato con regola identica (fine mese, liquidità a 0, 6 bp
per cambio). Decisione: "regge" se il max DD migliora di almeno 10 punti e il limite inferiore di ΔSharpe IC90%
è sopra −0,10; credibile se regge in almeno 4 mercati su 6. Tasse con il regime ETF italiano: 26% su ogni uscita
in guadagno, perdite non compensabili; per il buy & hold una tassa sola alla fine.

| Mercato | Sharpe B&H → filtro | ΔSharpe [IC90] | Max DD B&H → filtro | CAGR netto B&H → filtro | Uscite/anno |
|---|---|---|---|---|---|
| ^GSPC 1950-2004 | 0,62 → 0,70 | +0,08 [−0,08, +0,26] | −49% → −33% | +7,5% → +5,2% | 0,7 |
| ^GDAXI 1988-2026 | 0,47 → 0,58 | +0,11 [−0,10, +0,31] | −73% → −32% | +7,3% → +5,5% | 0,7 |
| ^FTSE 1984-2026 | 0,40 → 0,36 | −0,03 [−0,22, +0,16] | −53% → −45% | +4,8% → +2,1% | 1,0 |
| ^N225 1965-2026 | 0,42 → 0,49 | +0,07 [−0,10, +0,23] | −82% → −53% | +6,2% → +3,8% | 0,9 |
| EFA 2002-2026 | 0,43 → 0,54 | +0,11 [−0,13, +0,35] | −61% → −32% | +6,0% → +4,7% | 0,8 |
| URTH 2012-2026 | 0,76 → 0,74 | −0,02 [−0,34, +0,30] | −34% → −15% | +10,3% → +6,3% | 0,7 |

Regge in 3 mercati su 6 → **non credibile secondo la regola**. Il filtro taglia sempre il drawdown, ma lo Sharpe
non migliora in modo significativo da nessuna parte e il CAGR netto scende da 1,3 a 4 punti l'anno. Conclusione:
è un'assicurazione costosa, non un vantaggio. Resta solo nel conto paper.
Distorsioni note: ^GSPC, ^FTSE e ^N225 sono senza dividendi (favorisce il filtro); la liquidità a 0 lo penalizza.

**3. Prezzi dei delistati:** chiederò a ESCP l'accesso a WRDS/CRSP.

**4. Congelamento:** i 9 file restano congelati per 12 mesi dall'avvio del paper trading. I guasti di
infrastruttura si correggono fuori da quei file e si annotano in un registro, con l'impronta controllata. Se
servisse toccare i 9 file, l'ombra riparte da zero.

**Broker:** non ho trovato una conferma chiara che un retail italiano possa comprare ETF USA su Alpaca. In più
Alpaca tratta solo mercati USA, quindi niente CSPX/SXR8 lì. Per ora resta tutto in paper.

Sul resoconto giornaliero: grazie, ma le chiavi del conto restano solo sul mio computer. Il resoconto lo genera
il bot in locale.

Domande:
1. Dato che il filtro non è un vantaggio dopo le tasse, la scelta più sensata per soldi veri è un ETF UCITS
   ad accumulazione in buy & hold, con PULSE solo come esperimento in paper?
2. Vedi errori nel modo in cui ho modellato le tasse italiane sugli ETF (guadagni come redditi di capitale,
   perdite come redditi diversi non compensabili)?
