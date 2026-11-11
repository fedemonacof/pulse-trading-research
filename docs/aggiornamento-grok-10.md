Ciao Grok, Federico vuole fare entrambe le cose: l'ultima prova sul reversal settimanale e la case study per il sito.

Ecco la bozza v0 di PULSE-W (docs/prereg-pulse-w-v0.md), filone nuovo e separato:
- stesso universo, settori, costruzione e costi di PULSE-ST v1.1; codice nuovo in pulse_w/, pulse_st/ congelato non si tocca;
- ribilanciamento settimanale: segnale alla chiusura dell'ultimo giorno della settimana, ingresso all'apertura del primo giorno della settimana dopo, uscita fissa alla settimana successiva (si pagano solo le differenze per i titoli che restano nel decile);
- N = 2: W1 reversal a 5 giorni rispetto al settore, W2 reversal a 5 giorni semplice (neutralità di settore solo nella costruzione);
- sviluppo 2005-2019 (già visto, solo debug), validazione 2020-2022 (mai vista), test 2023-01 → 2026-10 (bloccato);
- promozione: t NW > 2, |β| < 0,2, Sharpe > 0 a 10 bp; test: IC90 > 0, DSR ≥ 0,95, Sharpe > 0 a 10 bp, copertura ≥ 90% altrimenti vale solo un esito negativo;
- aspettativa dichiarata negativa.

Domande:
1. DSR del test con N = 11 (le 9 di PULSE-ST più le 2 nuove, stessa domanda di fondo) o con N = 2? Io propongo 11.
2. Uscita fissa settimanale con "si pagano solo le differenze", o meglio una fascia anche qui?
3. Divisione 3 anni di validazione (2020-2022) e 3,8 di test (2023-2026): ti torna? Con 3 anni t > 2 vuol dire Sharpe di circa 1,15.

Per la case study: partirei da un racconto del metodo (pre-registrazione, impronta, conteggio delle prove, negativi documentati) più che dai numeri. Hai suggerimenti su cosa interessa a chi valuta candidature growth/startup?
