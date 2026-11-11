Ciao Grok, ho letto la tua bozza v0 di PULSE-ST e la risposta. Tengo l'impianto: famiglie fissate prima, tre campioni, test bloccato via codice, trials.jsonl automatico, sensibilità ai costi. Ho scritto una v1 fusa con 6 modifiche. Dimmi se le contesti prima che firmiamo.

1. Rotazione e costi. Con k = 1 e uscita dopo h giorni la rotazione è quasi piena: 4 lati × 8 bp = 0,32% al giorno del capitale per gamba, circa 80% l'anno. Nessun reversal sulle large cap lo copre. Propongo una regola comune a tutte le famiglie, non contata come prova: entrata nel decile estremo, uscita quando il titolo torna nel 50% centrale o dopo 5 giorni (per F3: RSI(2) fra 30 e 70). E riporto sempre il rendimento lordo di pareggio.

2. Settori. Il GICS storico non è gratis, e per i delistati manca anche quello attuale. Assegno ogni titolo all'ETF SPDR (9 dal 1998) con la correlazione più alta sui 252 giorni precedenti, ricalcolata ogni mese. Non usa il futuro e copre anche i titoli usciti.

3. Dati sbagliati. Tolgo la regola "aperture fuori da [0,5×, 2×] senza evento societario": non abbiamo gli eventi societari e su 1 giorno quei salti sono spesso veri. Tengo la regola v2 (serie esclusa se ha barre impossibili). Aggiungo una robustezza con rendimenti limitati all'1°/99° percentile ogni giorno, perché per un reversal un picco falso è un guadagno falso: il caso GR l'ha già dimostrato.

4. F4 gap tolta, quindi N = 9. Il gap si conosce solo all'apertura, ma la regola di esecuzione entra all'apertura con un segnale della chiusura prima. Va in una pre-registrazione propria, con dati intraday.

5. Copertura. La soglia del 65% era tagliata sul 68,4% che abbiamo già. La rendo una condizione di validità: un esito positivo del test vale solo con copertura ≥ 90% nel periodo 2020-2026, che misuro prima di aprire il test.

6. Promozione. "Sharpe > 0,5" è più debole di "t > 2" su 5 anni (che richiede uno Sharpe di circa 0,9), quindi tengo solo t > 2 (Newey-West), |β| < 0,2 e Sharpe > 0 a 10 bp. Nel campione di sviluppo i parametri sono già fissati: serve solo a verificare il codice, non a scegliere.

Domande:
a) La regola di uscita a fascia (decile → 50% centrale) è standard nella letteratura sul reversal, o rischia di trasformarlo in un segnale diverso (più lento, più vicino al momentum)?
b) L'assegnazione dei settori per correlazione con gli ETF ti sembra accettabile, o preferisci la sola neutralità di mercato più la neutralità di beta?
c) Il proxy MOC (ingresso alla chiusura t con +5 bp) solo come robustezza: d'accordo che non deve contare per scegliere?
d) Con 3 famiglie e N = 9, e il test 2020-2026 (6,8 anni), che Sharpe minimo serve per DSR ≥ 0,95 secondo la tua stima?
