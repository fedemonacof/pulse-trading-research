# PULSE-W: pre-registrazione del reversal settimanale. Bozza v1 (Claude + Grok), pronta per la firma

Non vale finché non è firmata in fondo. Prima della firma non si scarica nessun prezzo dal 2020 in poi. È un
filone **nuovo**, distinto da PULSE-ST, che si è chiuso con esito negativo il 12/11/2026. Solo paper, non è
consulenza finanziaria.

## 0. Domanda e aspettativa

Un reversal cross-sectional a **una settimana**, market neutral, sulle large cap USA ha uno Sharpe netto positivo
dopo costi realistici, su dati mai visti?

**Aspettativa dichiarata: negativa.** Sul 2005-2014 la coorte fissa di PULSE-ST rendeva 8-12 bp lordi in 5 giorni,
contro circa 16 bp di un giro completo per gamba. Nel 2015-2019 il lordo è crollato. Questa prova serve a chiudere
anche l'orizzonte settimanale con una regola, non a sperare.

## 1. Cosa resta uguale a PULSE-ST v1.1

- **Universo:** membri S&P 500 point-in-time, ogni mese i primi 200 per volume in dollari a 60 giorni.
- **Dati:** regola v2 sulle barre impossibili.
- **Settori:** correlazione con i 9 SPDR originali, con isteresi di 0,05.
- **Costruzione:** gambe uguali in dollari, netto per settore ≤ 5% del lordo, massimo 2% del lordo per titolo.
- **Costi:** 8 bp per lato più stress, prestito 0,5%, SEC/FINRA. Sensibilità a 2, 5, 10 e 20 bp.
- **Strumenti:** Newey-West, DSR, bootstrap a blocchi, curva a coorte fissa.
- **Il codice di `pulse_st/` congelato (`2e28ab49223f98ad`) non si tocca.** PULSE-W vive in `pulse_w/`, con una
  sua impronta e un suo `trials.jsonl`.

## 2. Cosa cambia

| Punto | PULSE-ST | PULSE-W |
|---|---|---|
| Ribilanciamento | ogni giorno | **una volta a settimana**: segnale alla chiusura dell'ultimo giorno di borsa della settimana, ingresso all'apertura del primo giorno della settimana dopo |
| Uscita | a fascia, massimo 5 giorni | **fissa**: tutto si chiude e si riapre al ribilanciamento successivo. Restano invariati i titoli che sono ancora nel decile, così si pagano solo le differenze |
| Varianti | 9 | **N = 2** |

## 3. Le due varianti (N = 2)

- **W1:** −(rendimento a 5 giorni del titolo − rendimento a 5 giorni del suo ETF di settore). Long sul decile più
  alto, short sul più basso.
- **W2:** come W1, ma con il rendimento a 5 giorni del titolo **da solo**, senza togliere il settore. La
  neutralità di settore resta nella costruzione.

Non si aggiungono altre varianti.

## 4. Campioni

| Campione | Periodo | Uso |
|---|---|---|
| Sviluppo | 2005-01 → 2019-12 (già visto) | solo debug del codice e controlli di correttezza; lo Sharpe si registra ma non guida nulla |
| Validazione | **2020-01 → 2022-12** (mai visto) | una esecuzione per variante; promossa la migliore se t > 2 (NW), \|β\| < 0,2 e Sharpe > 0 a 10 bp |
| Test (bloccato) | **2023-01 → 2026-10** (mai visto) | una sola esecuzione, solo se una variante è promossa |

Con 3 anni di validazione, t > 2 vuol dire uno Sharpe di circa 1,15: è una soglia severa, ma è voluta.

## 5. Decisione sul test

Il test passa solo se valgono tutte:
- limite inferiore dell'IC90% dello Sharpe netto > 0;
- DSR ≥ 0,95 con **N = 11**, cioè le 9 prove di PULSE-ST più le 2 di PULSE-W, perché la domanda di fondo è la
  stessa;
- Sharpe > 0 a 10 bp.

Se la copertura dei prezzi nel periodo di test è sotto il 90%, vale solo un esito negativo.

## 6. Risposte di Grok (integrate nella v1)

1. **DSR con N = 11.** La domanda di fondo è la stessa, e le 9 prove di PULSE-ST hanno influenzato questa scelta.
   Il DSR con N = 2 si riporta solo come informazione, mai come criterio.
2. **Uscita fissa settimanale, pagando solo le differenze:** una regola in meno. Si riportano sempre la rotazione
   settimanale effettiva e il rendimento lordo di pareggio, come in PULSE-ST.
3. **Divisione 2020-2022 / 2023-2026 confermata.**
   **Distorsione dichiarata:** il 2020-2022 contiene il crollo e il rimbalzo del Covid, un periodo di alta
   volatilità molto favorevole ai reversal. Una promozione dovuta soprattutto al 2020 resta possibile ed è il test
   2023-2026 a metterla alla prova. Per questo si riporta lo Sharpe di validazione anche anno per anno, come
   informazione e non come criterio.

## 7. Firma

- Data:
- Versione:
- SHA-256 del documento (senza questa sezione):
- Impronta del codice `pulse_w/` al congelamento:
