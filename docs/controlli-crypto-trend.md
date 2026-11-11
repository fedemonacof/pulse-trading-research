# PULSE-CT ipotesi 1: controlli prima della firma (2026-11-11)

Riferimento: [prereg-crypto-trend-v1.md](prereg-crypto-trend-v1.md), sezione 9 e revisioni 1-5 (sezione 9b).
- Codice in `pulse_mm/research/crypto_trend/` e `pulse_mm/core/costs.py`.
- Secondo calcolo indipendente in `checks/crypto_trend_independent.py`; le sue scelte sono in
  `checks/out/ambiguities.md`.
- Impronta attuale `ed0adafbfb4d3e7d` (`python -m pulse_mm.research.crypto_trend fingerprint`). Non è firmata.
- Sul periodo di sviluppo **non è stata calcolata né stampata nessuna metrica di rendimento** (Sharpe, drawdown,
  CAGR): `dev` e `crosscheck` mostrano solo controlli e scarti.
- Impronte congelate invariate: `desk/` `7d054586a815bd0f`, `pulse_st/` `2e28ab49223f98ad`.
- 165 test verdi.

## Stato degli otto criteri

| # | Criterio | Stato |
|---|---|---|
| 1 | Codice con impronta, `trials.jsonl`, N = 4 dopo la revisione 1 | fatto |
| 2 | Caricatore storico con blocco delle date e impronte dei dati; flusso dal vivo separato | fatto, con test |
| 3 | Copertura di Coinbase | fatto: BTC dal 2016-01-01, ETH dal 2016-05-18, 100% dei giorni dal 2016-06-01 al 2020-12-31, nessuna barra impossibile |
| 4 | Registro dei costi: somma delle componenti = lordo − netto entro 0,01 bp | fatto: errore circa 1e-11 bp |
| 5 | Turnover ≤ 10 volte all'anno | fatto dopo la revisione 1: 4,3 (prima 11,8) |
| 6 | Secondo calcolo indipendente e lookahead (revisione 2) | **fatto**: 103/103 e 63/63 scambi coincidenti, scarti trascurabili, troncamento senza differenze |
| 7 | 28 giorni di dry-run con ordini di prova | **in corso** (revisione 3): dal 2026-11-13, piano con impronta `ef309217960d3c14` (revisione 3b: book e giorni agitati), freqtrade 2026.10 su `myokx` sotto launchd, controllo giornaliero alle 00:20 UTC |
| 8 | Tariffa taker di OKX Europe | **fatto**: 0,1000% = 10 bp (listino del 2026-11-11, `docs/evidenze/`); si rilegge il giorno della firma |

Robustezze EUR e parità di rischio: codice scritto e provato solo su dati sintetici (revisione 3). Si calcolano
una volta, insieme alla validazione.

## Revisione 1: decisione settimanale

| Sviluppo 2018-2020 | V3 giornaliera (scartata) | **V3 settimanale** | Benchmark |
|---|---|---|---|
| Scambi | 274 | **103** | 63 |
| Turnover annuo | 11,8 | **4,3** | 1,4 |
| Mediana dello scambio / capitale | 10,9% | 10,4% | 6,3% |

La regola di riserva, scritta prima di rimisurare, non scatta. N = 4.

## Revisione 2: secondo calcolo indipendente

1. **Primo confronto.**
   - V3: stesse 103 date, ma pesi diversi fino a 0,24 punti.
   - Benchmark: 62 scambi coincidenti su 63, scarto di 12,7 bp/anno.
   - Le cause erano cinque punti non fissati dal documento:
     - valutazione alla domenica o al lunedì;
     - dimensione dello scambio prima o dopo i costi;
     - tetto di leva;
     - primo livello di m;
     - riallineamento senza candela del lunedì.
2. **Risoluzione per scritto** nella pre-registrazione. Ognuno dei due calcoli si è poi allineato al testo per conto
   suo; il secondo ha ricevuto solo il testo.
3. **Un nuovo punto aperto (3b)**, risolto anche questo per scritto: il tetto di leva si controlla solo il lunedì del
   riallineamento. Un acquisto a peso 1 con i costi pagati dopo lascia una leva residua di circa 0,4%, accettata e
   dichiarata.
4. **Secondo confronto:**

| | V3 | Benchmark |
|---|---|---|
| Scambi coincidenti | 103 / 103 | 63 / 63 |
| Scarto massimo del peso | 5e-9 punti | 5e-9 punti |
| Scarto massimo del costo | 2e-11 bp | 5e-12 bp |
| Scarto del rendimento annualizzato | 3e-9 bp/anno | 4e-9 bp/anno |

**Lookahead:** con i dati troncati al 2019-06-30, pesi, scambi ed equity fino a quella data restano identici, sia sui
dati reali sia su quelli sintetici dei test.

**Limite dichiarato:** la sessione separata non ha visto il codice di PULSE, ma il documento che ha letto riportava i
conteggi 103 e 63 della revisione 1.

## Revisione 4: dopo la rilettura di Grok

- Grok è d'accordo su tutti e sei i dubbi del pacchetto di rilettura. La regola non cambia.
- Scritto prima della firma: "non concludente" è l'esito più probabile anche se il filtro funziona.
- Nuove robustezze senza soglie: drawdown su finestre di 63 giorni (con IC90 della differenza), drawdown medio,
  durata media sotto il massimo, liquidità al T-bill a 3 mesi (tetto, non stima).
- Controllo della leva: validazione e test non si riportano se un peso supera 1,01 in qualunque giorno. Sullo
  sviluppo il massimo è 0,95 (V3) e 0,95 (benchmark).
- T-bill FRED DTB3 scaricati fino al 2020-12-31, con impronta; nessun buco oltre 4 giorni.

## Revisione 5: esposizione diversa fra strategia e benchmark

- Esposizione media sullo sviluppo: 0,20 la strategia, 0,52 il benchmark. Un drawdown più basso arriverebbe in parte
  solo da qui: il giudice vero dell'ipotesi è il limite sullo Sharpe, che non cambia.
- Nuova robustezza senza soglie: benchmark scalato alla stessa esposizione media, con il rapporto calcolato sul
  periodo valutato.
- Nuovo test: `val` eseguito per intero su dati sintetici. L'avviso dei test viene da starlette/anyio, non tocca i
  calcoli.
