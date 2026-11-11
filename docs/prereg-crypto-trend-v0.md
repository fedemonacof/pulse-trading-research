# PULSE-CT: pre-registrazione del trend crypto, ipotesi 1. Bozza v0 (Claude + Grok)

Non vale finché non è firmata in fondo. Prima della firma non si scarica nessun prezzo dal 2021 in poi. È un
filone **nuovo** del progetto multi-mercato ([progetto-multimercato-v1.md](progetto-multimercato-v1.md)),
distinto dalle azioni. Solo backtest e paper, non è consulenza finanziaria.

## 0. Domanda e aspettativa

Un filtro di trend long/flat su BTC ed ETH spot, con volatility targeting, riduce il drawdown massimo rispetto
allo stesso buy & hold con lo stesso volatility targeting, senza peggiorare lo Sharpe oltre 0,1, su dati mai
usati per questa regola?

**È dichiarato come filtro di trend, non come fonte di rendimento.**

**Aspettativa dichiarata:**
- esito più probabile **"non concludente"**: pochi anni di dati, due asset con correlazione intorno a 0,8, quindi in
  pratica una sola scommessa;
- se il filtro funziona, il profilo atteso è quello del filtro a 200 giorni sulle azioni: assicurazione contro i
  crolli, non un vantaggio di rendimento.

## 1. Regola (unica, test principale)

1. **Segnale per asset.**
   - s_h = segno del rendimento a h giorni, con h ∈ {21, 63, 252}, calcolato sulle chiusure giornaliere a 00:00
     UTC.
   - m = (s₂₁ + s₆₃ + s₂₅₂) / 3.
2. **Esposizione.**
   - peso = max(0, m) × min(1, 0,40 / σ₆₃).
   - σ₆₃ è la volatilità realizzata a 63 giorni dei rendimenti giornalieri, annualizzata con √365.
   - Il peso può valere 0, 1/3 o 1, poi viene ridotto se σ₆₃ supera il 40%.
   - **Tetto di leva 1:** con σ₆₃ sotto il 40% la strategia resta al 100% e quindi sotto il target di volatilità.
3. **Portafoglio.** 50% del capitale a BTC e 50% a ETH, ciascuno con il suo peso. Il resto in liquidità.
4. **Ribilanciamento.**
   - Decisione sulla candela giornaliera chiusa alle 00:00 UTC.
   - Esecuzione all'apertura della candela successiva, come ordine market da taker.
   - Si scambia solo se il peso obiettivo differisce da quello attuale di almeno **10 punti percentuali** del
     capitale dell'asset, oppure se m cambia livello.
5. **Liquidità:** rendimento 0%, salvo documento legale che indichi un rendimento sicuro e lecito.

**Benchmark.** Stessa costruzione con m = 1 sempre: stesso target del 40%, stessa σ₆₃, stesso tetto di leva,
stessa divisione 50/50, stesso orario e stessa soglia di ribilanciamento, stessi costi e stessa liquidità a 0%.

## 2. Varianti e conteggio delle prove (N = 3)

| Variante | Ruolo |
|---|---|
| V1: solo s₂₅₂ | considerata e scartata; riportata come **analisi di robustezza**, senza soglie |
| V2: media con regola binaria (peso 1 se m > 0) | considerata e scartata; non riportata come test |
| **V3: media con esposizione max(0, m)** | **test principale, dichiarato ora** |

- V1 e V2 sono contate nell'N ma **non possono diventare il risultato a posteriori**, anche se andassero meglio.
- Il Deflated Sharpe usa N = 3.
- Il documento finale riporta anche l'N complessivo della famiglia PULSE: PULSE-ST, PULSE-W se eseguito, e questo
  filone.
- Altre analisi di robustezza riportate senza soglie: pesi a parità di rischio fra BTC ed ETH, costi tripli,
  risultati in EUR.

## 3. Date (fissate ora, non si estendono)

| Periodo | Date di valutazione | Uso |
|---|---|---|
| Riscaldamento | dati dal 2016-06-01 | serve solo a calcolare s₂₅₂ e σ₆₃ |
| Sviluppo | 2018-01-01 → 2020-12-31 | debug, controllo del turnover, riconciliazione dei costi. Niente decisioni sulla regola |
| Validazione | 2021-01-01 → 2022-12-31 | eseguita **una volta**, dopo la firma |
| Test | 2023-01-01 → **2026-10-31** | bloccato. Si apre solo se la validazione passa. Data di fine fissa |

- **Un solo regime in validazione.** 2021-2022 contiene un solo ciclo completo, salita e crollo. Un esito positivo
  lì dice poco sugli altri regimi, e si dichiara.
- **Il caricatore rifiuta le date.** Come in `pulse_st`, prima della firma si rifiuta di leggere date dal
  2021-01-01 in poi. Dopo una validazione non passata si rifiuta di leggere date dal 2023-01-01 in poi.

## 4. Cosa sappiamo già (dichiarazione)

- **Federico** non ha mai eseguito questa regola, né il filtro a 200 giorni, né un'altra regola di trend, su dati
  crypto di nessun periodo. Il filtro a 200 giorni l'ha visto girare solo sulle azioni, in 6 mercati.
- **Conoscenza generale.** Federico, Claude e Grok conoscono a grandi linee la storia delle crypto 2017-2026: crolli
  del 2018 e del 2022, rialzo del 2021, ETF spot del 2024. Le scelte di design (1/3/12 mesi, target del 40%,
  long/flat) sono state fatte con questa conoscenza generale, senza calcoli su questi dati. È un bias a favore, e
  si dichiara.
- **Nessun calcolo esplorativo** su prezzi crypto è stato fatto per questo progetto prima della firma.

## 5. Dati

- **Fonte unica per tutto il periodo:** Coinbase Exchange, coppie BTC-USD ed ETH-USD, candele giornaliere
  dall'API pubblica. OKX Europe non copre il periodo e i dati spot dei primi anni di altri exchange hanno volumi
  gonfiati.
  - **Da verificare prima della firma:** che la copertura di ETH-USD parta prima del 2016-06-01. Se non è così, il
    riscaldamento si accorcia e lo sviluppo parte più tardi. Si scrive qui prima di firmare.
- **Fuso:** UTC. Il giorno va da 00:00 a 24:00 UTC.
- **Impronta:** SHA-256 di ogni file grezzo scaricato, scritto in questo documento alla firma. Il caricatore
  rifiuta file con un'impronta diversa.
- **Qualità:**
  - una barra è impossibile se apertura o chiusura cadono fuori da [minimo, massimo] di oltre l'1%, se il massimo
    è sotto il minimo, oppure se c'è un salto sopra 3× o sotto 1/3 fra chiusure consecutive (regola v2 di PULSE);
  - con una barra impossibile il test si ferma e si segnala, non si corregge a mano.
- **Candele mancanti:**
  - un giorno mancante → nessuno scambio quel giorno, posizione valutata all'ultima chiusura nota;
  - più di 3 giorni consecutivi mancanti, o copertura sotto il 99% in un periodo → quel periodo vale solo per un
    esito negativo.
- **Valuta di riferimento: USD** per segnale, rendimenti e confronto. È la serie più lunga e pulita, e il cambio
  EUR/USD aggiungerebbe una variabile che non c'entra con l'ipotesi.
  - I risultati in EUR (cambio di riferimento BCE del giorno) si riportano come robustezza, perché per Federico
    conta l'EUR.
  - La liquidità è in USD (stablecoin) per coerenza.

## 6. Costi

- **Base:**
  - tariffa taker del livello di partenza di OKX Europe, letta sul listino EEA il giorno della firma e scritta qui;
  - più metà dello spread e slippage, fissati a 5 + 5 bp per lato.
- **Prima del 2025-01-01** i costi base si **raddoppiano**. È una data convenzionale, fissata ora: negli anni
  precedenti gli spread erano più larghi e OKX Europe non era disponibile in Italia. La data esatta di avvio va
  verificata, ma la soglia non si sposta.
- **Sensibilità riportata:** costi × 3 su tutto il periodo, senza soglie.
- **Controllo del turnover sullo sviluppo, prima della firma.** Turnover annuo = nozionale scambiato / capitale
  medio. Se supera **10 volte**, la regola di ribilanciamento si rivede prima di firmare e la revisione si registra
  qui.

## 7. Statistiche ed esiti

- **Metriche:** rendimenti giornalieri, Sharpe annualizzato con √365, drawdown massimo, CAGR, esposizione media,
  turnover.
- **Inferenza:**
  - IC90 da **block bootstrap** su blocchi di 21 giorni, 5.000 ricampionamenti;
  - si ricampionano le coppie di giorni strategia/benchmark, per le differenze strategia − benchmark.
- **DSR** con N = 3, riportato. Non è una soglia, perché l'ipotesi è sul drawdown e non sul rendimento.

| Esito | Condizione (su ciascun periodo, prima validazione poi test) |
|---|---|
| **Passa** | IC90 di ΔDD massimo tutto sotto zero **e** limite inferiore dell'IC90 di ΔSharpe sopra −0,1 |
| **Fallisce** | IC90 di ΔDD non tutto sotto zero, **oppure** limite superiore dell'IC90 di ΔSharpe sotto −0,1 |
| **Non concludente** | ogni altro caso |

Il margine vale sull'intervallo, non sulla stima.

## 8. Regola di stop

- **Validazione:**
  - "fallisce" o "non concludente" → l'ipotesi si **chiude**: il test 2023-2026 non si apre, la regola non si
    ritocca e l'ipotesi 2 (long/short) non si apre;
  - "passa" → si apre il test, una volta sola.
- **Test:**
  - l'esito è definitivo, qualunque sia;
  - solo un "passa" sul test autorizza il paper con riempimenti da taker (fase 5 del progetto).
- **Dopo la chiusura**, qualunque idea nuova sulle crypto è una pre-registrazione nuova, che conta questa nell'N
  della famiglia.

## 9. Prima della firma (criteri di accettazione)

1. Codice in `pulse_mm/research/crypto_trend/` con impronta SHA-256, e un suo `trials.jsonl` con le 3 varianti.
2. Caricatore con il blocco delle date (sezione 3) e il controllo delle impronte dei dati (sezione 5).
3. Copertura di Coinbase verificata e scritta nella sezione 5.
4. Registro dei costi: la somma delle componenti coincide con lordo meno netto entro 0,01 bp.
5. Controllo del turnover sullo sviluppo (sezione 6).
6. Strategia freqtrade equivalente:
   - `lookahead-analysis` e `recursive-analysis` senza errori, output allegato;
   - backtest freqtrade sullo sviluppo entro 5 bp all'anno dal calcolo PULSE.
   Il risultato ufficiale è quello di PULSE.
7. Riconciliazione con alcune settimane di dry-run, senza soldi e senza chiavi. Lo scarto medio per trade non deve
   superare i costi ipotizzati, altrimenti si rivedono i costi.
8. Tariffa taker di OKX Europe letta e scritta nella sezione 6.

## 10. Firma

| Campo | Valore |
|---|---|
| Data | — |
| Firmato da | — |
| SHA-256 del documento (senza questa sezione) | — |
| Impronta del codice | — |
| Impronte dei dati grezzi | — |

## 11. Esito

Vuoto finché la validazione non è stata eseguita.
