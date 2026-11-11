# PULSE-ST: pre-registrazione del filone a breve termine (1-2 giorni). Bozza v1.1, fusa

Questa versione unisce la v0 di Grok ([prereg-pulse-st-v0-grok.md](prereg-pulse-st-v0-grok.md)) e le correzioni
di Claude. Grok ha accettato le 6 modifiche e ha aggiunto 6 precisazioni (v1.1):
- la curva di decadimento;
- solo i 9 ETF settoriali originali;
- l'isteresi di 0,05 sul settore;
- la neutralità di beta come robustezza;
- la regola sul MOC;
- la regola per una copertura sotto il 90%.

Secondo Grok, la v1.1 si può firmare. Non vale finché non viene firmata, con data e impronte, in fondo al documento. Prima della firma non si
scarica né si guarda nessun dato del periodo di test. È solo paper: non è consulenza finanziaria.

## Cosa cambia rispetto alla v0

| Punto | v0 (Grok) | v1 | Perché |
|---|---|---|---|
| Rotazione | uscita fissa dopo h giorni | **entrata nel decile estremo, uscita quando il titolo torna nel 50% centrale**, oppure dopo 5 giorni | Con k = 1 e rotazione piena i costi sono 4 lati × 8 bp = 0,32% al giorno, circa 80% l'anno: un pareggio impossibile |
| Settori | GICS, attuale se manca quello storico | **ETF SPDR con la correlazione più alta sui 252 giorni precedenti** (9 ETF dal 1998) | Il GICS storico non è gratis e per i delistati manca anche quello attuale. La correlazione non usa il futuro |
| Dati sbagliati | escluse le aperture fuori da [0,5×, 2×] senza evento societario | **regola v2**: serie esclusa per intero se ha barre impossibili. In più, robustezza con rendimenti limitati all'1°/99° percentile | Non c'è un calendario degli eventi societari, e su 1 giorno quei salti sono spesso veri. Per un reversal un picco falso è un guadagno falso (caso GR) |
| F4 gap | 3 prove | **tolta** (N = 9) | Il gap si conosce solo all'apertura, ma l'ingresso è fissato all'apertura con un segnale della chiusura prima. Andrà in una pre-registrazione propria, con dati intraday |
| Copertura minima | ≥ 65% | si riporta e basta. **Un esito positivo vale solo con copertura ≥ 90% nel periodo di test** | La soglia del 65% era tagliata sul 68,4% che abbiamo già. Per 2020-2026 la copertura dovrebbe essere più alta (meno delistati mancanti): si misura prima di aprire il test |
| Promozione dalla validazione | Sharpe > 0,5 e t > 2 | **t > 2** (Newey-West, che su 5 anni vuol dire Sharpe circa > 0,9), **β < 0,2**, **Sharpe > 0 a 10 bp** | "Sharpe > 0,5" era più debole di t > 2 su 5 anni, quindi ridondante |
| Ombra contro backtest | 30 bp | 30 bp, con gli stessi prezzi del modello di costi | Uguale (la v0 era più severa del filone swing, giustamente) |

## 0. Domanda

Un segnale cross-sectional di reversal a 1-2 giorni, market neutral, sulle large cap USA ha uno Sharpe positivo
**dopo costi realistici**, fuori campione? Ipotesi nulla H0: Sharpe netto ≤ 0. **Aspettativa dichiarata:
improbabile.**

Codice, diario, impronta e conteggio delle prove sono separati da PULSE swing (`pulse_st/`). I 9 file congelati
non si toccano.

## 1. Dati

- **Universo:** membri S&P 500 point-in-time (fja05680/sp500). Ogni mese si tengono i **primi 200 per volume in
  dollari a 60 giorni**, calcolato solo con dati fino a quella data.
- **Prezzi:** Yahoo, giornalieri, OHLC rettificati. Si applica la regola v2 sulle barre impossibili.
- **Settori:** ogni mese, ogni titolo va nell'ETF fra XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY con la
  correlazione dei rendimenti giornalieri più alta nei 252 giorni precedenti. Servono almeno 200 giorni di dati.
  - Per tutto il periodo si usano **solo i 9 ETF originali del 1998**. XLRE (2015) e XLC (2018) sono esclusi per
    coerenza, e lo si dichiara come distorsione.
  - **Isteresi:** un titolo cambia ETF solo se la correlazione con il nuovo supera quella con l'attuale di
    almeno 0,05.
- **Distorsioni dichiarate:**
  - mancano i delistati, e questo favorisce la strategia;
  - i settori sono statistici, non ufficiali;
  - il costo di prestito è costante;
  - l'impatto di mercato è solo lo slippage fisso;
  - la liquidità rende 0, e questo penalizza la strategia.

## 2. Campioni (fissati ora)

| Campione | Periodo | Uso |
|---|---|---|
| Sviluppo | 2005-01 → 2014-12 | Verifiche del codice e statistiche descrittive. **Le parametrizzazioni sono già fissate qui, non si scelgono** |
| Validazione | 2015-01 → 2019-12 | Una esecuzione per variante; si promuove al massimo una variante per famiglia |
| Test (bloccato) | 2020-01 → 2026-10 | Una sola esecuzione. Il loader rifiuta via codice qualsiasi data ≥ 2020-01-01 finché la validazione non è firmata |
| In avanti | 12 mesi minimo dalla firma | Paper e ombra, codice congelato |

## 3. Famiglie di segnali (N = 9, contate in `trials.jsonl`)

- **F1. Reversal rispetto al settore:** segnale −(rendimento a k giorni − rendimento dell'ETF del settore),
  con k ∈ {1, 3, 5}. **3 prove.**
- **F2. Reversal con volume basso:** F1 con k = 1, solo per i titoli con volume del giorno < s × media a 20
  giorni, con s ∈ {0,8, 1,0, 1,5}. **3 prove.**
- **F3. RSI(2) market neutral:** long se RSI(2) < a e prezzo > SMA200; short se RSI(2) > 100 − a e prezzo
  < SMA200, con a ∈ {5, 10, 15}. Nessun trade se una gamba ha meno di 5 titoli. **3 prove.**

**Esclusi con motivo:**
- overnight contro intraday (si usa solo per l'orario di esecuzione);
- PEAD (serve un calendario degli utili point-in-time);
- ETF a leva (servono dati intraday);
- gap (va in una pre-registrazione propria).

## 4. Portafoglio

- **Market neutral:** gambe uguali in dollari, 100% long + 100% short.
- **Settori:** esposizione netta per settore ≤ 5% del lordo.
- **Pesi:** uguali dentro ogni gamba, massimo 2% del lordo per titolo.
- **Entrata e uscita (regola comune, non è una prova):**
  - F1 e F2: si entra nel decile estremo; si esce quando il titolo torna nel 50% centrale, o dopo 5 giorni.
  - F3: si esce quando l'RSI(2) torna fra 30 e 70, o dopo 5 giorni.
- **Esecuzione:** segnale alla chiusura t, ingresso all'**apertura t+1**, uscita all'apertura del giorno in cui
  scatta l'uscita. Nessuno stop intraday.
- **Robustezza, riportata ma mai usata per scegliere:**
  - ingresso alla chiusura t con 5 bp in più, come approssimazione di un ordine MOC basato sui prezzi delle 15:50.
    **Se una variante passa solo con il MOC e non con l'apertura del giorno dopo, l'esito è negativo;**
  - neutralità di beta, in aggiunta a quella di settore e non al suo posto, perché coprono rischi diversi;
  - rendimenti limitati all'1°/99° percentile.
- **Controllo della curva di decadimento** (non è una prova, N non cambia): rendimento lordo medio per giorno di
  detenzione, dal giorno 1 al giorno 5, sui trade di ogni variante.
  - Se il lordo arriva quasi tutto il giorno 1 e poi si appiattisce, l'uscita a fascia diluisce il segnale.
    Lo si scrive nel risultato.
  - Se cresce fino al giorno 3-5, la regola è coerente.

## 5. Costi

| Voce | Caso base | Sensibilità |
|---|---|---|
| Slippage + metà spread, per lato | 8 bp | 2 / 5 / 10 / 20 bp |
| Stress | costi doppi quando la volatilità di SPY a 20 giorni supera il 90° percentile dei 5 anni precedenti | — |
| Commissioni regolamentari sulle vendite | SEC + FINRA TAF, approssimate | — |
| Prestito per gli short | 0,5% annuo | 0,25 / 1 / 3% |
| Titoli difficili da prestare | niente short sotto il 20° percentile di capitalizzazione dell'universo (approssimata con il volume in dollari) | — |

Si riportano sempre la rotazione giornaliera e il **rendimento lordo di pareggio**: quanto deve rendere il segnale
prima dei costi.

## 6. Decisioni

- **Validazione:** promossa la variante migliore per famiglia (per t di Newey-West), solo se:
  - t > 2;
  - |β| < 0,2;
  - Sharpe a 10 bp > 0.
- **Test** (una sola esecuzione). Passa solo se valgono tutte e quattro:
  - limite inferiore dell'IC90% dello Sharpe netto > 0 (bootstrap a blocchi di 21 giorni, 5.000 ricampionamenti);
  - DSR ≥ 0,95 con **N = 9**;
  - Sharpe a 10 bp > 0;
  - copertura ≥ 90%.

  Se passano più famiglie, si riporta la combinazione a pesi uguali senza ottimizzarla.
- **Copertura sotto il 90% nel periodo di test:** il test si esegue lo stesso, ma vale solo un esito negativo.
  Un esito positivo resta **sospeso** finché non si può ripetere con i dati CRSP (delistati compresi), con lo
  stesso codice e la stessa impronta.
- **Soglia attesa** (stima di Grok, ricontrollata). Con T = 6,8 anni e N = 9 prove indipendenti, per un DSR ≥ 0,95
  serve uno Sharpe netto osservato di circa **1,2**. Con circa 3 prove effettive, perché le varianti sono correlate,
  ne serve circa **1,0**. Code grasse e asimmetria negativa lo alzano ancora. Per un reversal sulle large cap dopo
  8 bp per lato è molto ambizioso.
- **In avanti:** stesse regole del filone swing ([preregistrazione-avanti.md](preregistrazione-avanti.md)),
  con ombra contro backtest a 30 bp. Si registrano anche:
  - i rifiuti di prestito di Alpaca;
  - le chiusure nello stesso giorno, che contano per la regola PDT.

## 7. Controllo delle prove

- `pulse_st/trials.jsonl` si scrive in automatico a ogni esecuzione, con data, impronta, campione, famiglia,
  parametri e metriche.
- N = numero di coppie uniche famiglia + parametri eseguite su validazione o test.
- Con N > 9 il test non vale.
- Un bug trovato dopo la validazione si corregge ripartendo dallo sviluppo e si annota nel registro.
- Il test non si riesegue mai.

## 8. Firma (in due tempi)

1. **Documento:** si firma prima di scrivere il codice. Da quel momento le regole sopra non cambiano.
2. **Codice:** si congela dopo averlo scritto e verificato sul solo campione di sviluppo, e prima della prima
   esecuzione sulla validazione. L'impronta si scrive qui e in `trials.jsonl`.

Condizioni sul campione di sviluppo (aggiunte su proposta di Grok):
- **Si correggono solo bug, non scelte.** Ogni modifica va nel registro degli interventi con il motivo. Nessuna
  modifica può toccare soglie, famiglie, costi o regole di uscita fissate qui. Se una correzione cambia una regola,
  serve una nuova versione della pre-registrazione.
- **Nessuna ottimizzazione nascosta.** Si guardano solo i controlli di correttezza: numero di trade, neutralità
  delle gambe, rotazione, curva di decadimento come verifica del codice. Lo Sharpe di sviluppo si registra, ma non
  è mai un criterio per correggere.
- **L'impronta si firma prima della prima riga di validazione.** Il codice di validazione e di test si rifiuta di
  girare se l'impronta non corrisponde, come nel filone swing. `trials.jsonl` conta le prove da quel momento.

- Data della firma del documento: **2026-11-11** (approvata da Federico, Grok d'accordo)
- Versione scelta: **v1.1 fusa**
- SHA-256 di questo documento (calcolato senza questa sezione): **`09a79696fc7e08ef582a273af23c91b3b87ed4adce34df6cd0dd9d120cc7d9eb`**
- Impronta del codice `pulse_st/` al congelamento: **`2e28ab49223f98ad`** (2026-11-12, prima della validazione)

## 9. Esito della validazione (12/11/2026)

Eseguita una volta con l'impronta `2e28ab49223f98ad`, N = 9. **Nessuna variante promossa**, quindi il test
2020-2026 non si apre. Dettagli in [risultati-pulse-st.md](risultati-pulse-st.md).
