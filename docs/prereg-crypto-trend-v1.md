# PULSE-CT: pre-registrazione del trend crypto, ipotesi 1. Bozza v1 (Claude + Grok)

v1: integra la revisione di Grok della v0 (segno del drawdown, esiti, ribilanciamento fra BTC ed ETH, bootstrap
sul drawdown, definizione del peso, separazione fra dati storici e flusso dal vivo) e il calendario degli ordini di
prova per la riconciliazione.

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
   - **Quota di un asset:** la parte di capitale assegnata a quell'asset, cioè la sua posizione più la sua
     liquidità.
   - **Riallineamento delle quote:** il **primo lunedì di ogni mese** alle 00:00 UTC ogni quota torna al 50% del
     capitale totale (revisione 1). Fra un riallineamento e l'altro le quote derivano con i prezzi.
   - Dopo il riallineamento si applica la regola di ribilanciamento qui sotto, con la stessa soglia: il
     riallineamento da solo non forza uno scambio sotto la soglia.
4. **Ribilanciamento.**
   - **Decisione una volta a settimana** (revisione 1): il lunedì alle 00:00 UTC, con le chiusure fino alla
     candela della domenica.
   - Esecuzione all'apertura della candela del lunedì, come ordine market da taker.
   - Se manca la candela del lunedì per un asset, quella settimana non si scambia quell'asset.
   - **Peso attuale** = valore di mercato della posizione / capitale della quota dell'asset, ricalcolato a ogni
     chiusura. Così la soglia tiene conto della deriva dei prezzi.
   - Si scambia solo se il peso obiettivo differisce dal peso attuale di almeno **10 punti percentuali**, oppure se
     m è a un livello diverso da quello della decisione precedente.
5. **Liquidità:** rendimento 0%, salvo documento legale che indichi un rendimento sicuro e lecito.

**Benchmark.** Stessa costruzione con m = 1 sempre: stesso target del 40%, stessa σ₆₃, stesso tetto di leva,
stessa divisione 50/50 con lo stesso riallineamento al primo lunedì del mese, stessa decisione settimanale del
lunedì e stessa soglia di ribilanciamento,
stessi costi e stessa liquidità a 0%.

## 2. Varianti e conteggio delle prove (N = 4)

| Variante | Ruolo |
|---|---|
| V1: solo s₂₅₂ | considerata e scartata; riportata come **analisi di robustezza**, senza soglie |
| V2: media con regola binaria (peso 1 se m > 0) | considerata e scartata; non riportata come test |
| V3 con decisione giornaliera | regola originale, scartata per il turnover nella revisione 1; contata nell'N |
| **V3: media con esposizione max(0, m), decisione settimanale** | **test principale** |

- V1 e V2 sono contate nell'N ma **non possono diventare il risultato a posteriori**, anche se andassero meglio.
- Il Deflated Sharpe usa N = 4 (revisione 1). Diventa N = 5 se scatta la regola di riserva della revisione 1.
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
- **Dati storici e flusso dal vivo sono separati.**
  - Il caricatore storico legge solo i file grezzi con impronta, con il blocco delle date.
  - Il flusso dal vivo (dry-run di riconciliazione, poi paper) è un percorso di codice diverso, che accetta solo
    date **dal 2026-11-01 in poi**, cioè dopo la fine del test. Non scrive mai nell'archivio storico.
  - Un test verifica entrambe le cose: il flusso dal vivo rifiuta date fino al 2026-10-31, e il caricatore
    storico non ha un'opzione per disattivare il blocco.
  - **Il dry-run di riconciliazione non usa il segnale.** Il segnale di oggi richiederebbe 252 + 63 giorni di
    prezzi, cioè dati del periodo di test. Per questo la riconciliazione usa un **calendario fisso di ordini di
    prova** (acquisti e vendite di taglia fissa a orari fissi), che misura solo lo scarto fra esecuzione e prezzo
    del backtest. Il segnale vero gira dal vivo solo dopo il verdetto del test.
  - **Calendario e taglia fissati prima di iniziare:**
    - ogni giorno alle 00:05 UTC, per **28 giorni consecutivi**, un ordine market su BTC e uno su ETH;
    - si alterna acquisto e vendita: un giorno si compra, il giorno dopo si vende la stessa quantità;
    - la taglia è la mediana del nozionale per scambio della strategia nel periodo di sviluppo, calcolata nel
      controllo del turnover e scritta qui prima di iniziare;
    - 28 giorni di fila coprono giorni tranquilli e agitati senza sceglierli.
  - **Cosa si misura**, per ogni ordine, in punti base:
    - **scarto di esecuzione** = prezzo eseguito in dry-run − prezzo di OKX Europe all'istante della decisione;
    - **differenza fra sedi** = prezzo di OKX Europe all'istante della decisione − apertura della candela
      Coinbase usata dal backtest.

    Le due componenti vanno separate nel registro dei costi (`slippage` e `venue_basis`). La differenza fra OKX e
    Coinbase non va confusa con lo slippage.
  - **Avvertenza: è un limite basso.** Il dry-run di freqtrade simula l'esecuzione e non manda ordini veri, quindi
    lo scarto misurato è il **limite basso** dei costi reali, non quello alto.
    - Superare il controllo non dimostra che i costi ipotizzati bastino. Dimostra solo che non sono già sotto il
      minimo.
    - Se lo scarto medio supera i costi ipotizzati, i costi si rivedono prima della firma.

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
  - **Copertura verificata il 2026-11-11** (criterio 3): BTC-USD dal 2016-01-01, ETH-USD dal **2016-05-18**.
    Dal 2016-06-01 al 2020-12-31 entrambe hanno il 100% dei giorni (1.675 su 1.675), nessuna barra impossibile.
    Il riscaldamento dal 2016-06-01 regge.
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
    - **letta il 2026-11-11** (criterio 8): spot, conto solo spot, utente regolare, taker **0,1000% = 10 bp per
      lato** (maker 0,0800%). Prova in `docs/evidenze/okx_eu_spot_2026-11-11.md`;
    - si rilegge il giorno della firma: se è cambiata, vale il nuovo valore e la modifica si registra in 9b;
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
- **Segno del drawdown.**
  - DD = perdita massima dal picco, scritta come **numero positivo** (es. 0,50 per un calo del 50%).
  - ΔDD = DD strategia − DD benchmark: la strategia è **migliore se ΔDD < 0**.
  - ΔSharpe = Sharpe strategia − Sharpe benchmark.
- **Inferenza:**
  - IC90 da **block bootstrap** su blocchi di 21 giorni, 5.000 ricampionamenti, **seed 20261111**;
  - si ricampionano le coppie di giorni strategia/benchmark, per le differenze strategia − benchmark;
  - **robustezza sul drawdown:** stesso bootstrap con blocchi di 63 giorni, riportato senza cambiare l'esito. Il
    drawdown dipende dall'intero percorso, e i blocchi da 21 giorni spezzano i ribassi lunghi come quello del 2022;
  - in validazione c'è in pratica **un solo episodio di drawdown** (il 2022), quindi l'intervallo di ΔDD sarà
    largo. Si dichiara.
- **DSR** con N = 4 (o 5, revisione 1), riportato. Non è una soglia, perché l'ipotesi è sul drawdown e non sul rendimento.

| Esito | Condizione (su ciascun periodo, prima validazione poi test) |
|---|---|
| **Passa** | IC90 di ΔDD massimo tutto sotto zero **e** limite inferiore dell'IC90 di ΔSharpe sopra −0,1 |
| **Fallisce** | IC90 di ΔDD **tutto sopra zero**, **oppure** limite superiore dell'IC90 di ΔSharpe sotto −0,1 |
| **Non concludente** | ogni altro caso, per esempio IC90 di ΔDD a cavallo dello zero, oppure IC90 di ΔSharpe che contiene −0,1 |

"Fallisce" e "non concludente" chiudono entrambi l'ipotesi (sezione 8). La distinzione serve solo a un
resoconto onesto: un intervallo a cavallo dello zero non è una prova contro.

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
2. Caricatore storico con il blocco delle date e il controllo delle impronte dei dati, e flusso dal vivo separato
   che rifiuta le date fino al 2026-10-31 (sezioni 3 e 5).
3. Copertura di Coinbase verificata e scritta nella sezione 5.
4. Registro dei costi: la somma delle componenti coincide con lordo meno netto entro 0,01 bp.
5. Controllo del turnover sullo sviluppo (sezione 6).
6. **Secondo calcolo indipendente** (sostituisce freqtrade, revisione 2):
   - calcolo vettoriale, scritto da zero partendo solo da questo documento;
   - confronto scambio per scambio sullo sviluppo e scarto entro 5 bp all'anno;
   - test di troncamento contro il lookahead.

   Il risultato ufficiale resta quello di PULSE.
7. Riconciliazione con 28 giorni di dry-run su un calendario fisso di ordini di prova (sezione 3), senza segnale,
   senza soldi e senza chiavi. Scarto di esecuzione e differenza fra sedi registrati separatamente, dichiarati come
   limite basso dei costi. Lo scarto medio per trade non deve
   superare i costi ipotizzati, altrimenti si rivedono i costi.
8. Tariffa taker di OKX Europe letta e scritta nella sezione 6.

## 9b. Revisioni registrate prima della firma

### Revisione 1, 2026-11-11: decisione settimanale

- **Cosa si è visto.** Sullo sviluppo il controllo del turnover (criterio 5) ha dato **11,8** volte il capitale
  all'anno per V3 con decisione giornaliera, contro il limite di 10. Il benchmark è a 1,4. Non è stata calcolata né
  guardata nessuna metrica di rendimento.
- **Causa.** Il segno a 21 giorni cambia spesso da un giorno all'altro e ogni cambio di livello di m forza uno
  scambio.
- **Modifica** (scelta con Grok, guardando solo il turnover):
  - decisione una volta a settimana, il lunedì alle 00:00 UTC;
  - riallineamento delle quote al primo lunedì del mese;
  - il cambio di livello si confronta con la decisione precedente.

  Identica per il benchmark.
- **Conteggio.** La regola giornaliera resta fra i tentativi: **N = 4**.
- **Regola di riserva, scritta prima di rimisurare.**
  - Se con la decisione settimanale il turnover sullo sviluppo supera ancora 10, si alza la soglia di
    ribilanciamento a **20 punti** e **N = 5**.
  - Se supera ancora 10 anche così, l'ipotesi si **chiude prima della firma**, senza un terzo giro.
- **Esito della rimisura, 2026-11-11:** turnover di V3 settimanale sullo sviluppo **4,3** volte all'anno, 103
  scambi (benchmark 1,4, 63 scambi). Sotto il limite di 10: la regola di riserva **non scatta** e **N resta 4**.
  Mediana dello scambio: 10,4% del capitale, che diventa la taglia degli ordini di prova (criterio 7).

### Revisione 2, 2026-11-11: secondo calcolo indipendente al posto di freqtrade (criterio 6)

- **Motivo.** Con decisione settimanale su candele giornaliere e posizioni frazionarie, una strategia freqtrade
  equivalente richiede `adjust_trade_position` e adattamenti che aggiungerebbero errori propri. Il criterio 6
  serviva a verificare che il calcolo di PULSE non abbia errori di lookahead o di contabilità. Un secondo calcolo
  scritto da zero con un metodo diverso lo verifica meglio (decisa con Grok).
- **Indipendenza.**
  - Il secondo calcolo è scritto da una sessione separata, che legge solo questo documento e il formato dei
    file grezzi, senza vedere il codice di `pulse_mm/`.
  - Legge i file grezzi per conto suo e non importa niente da `pulse_mm/` né da `desk/`.
  - È vettoriale con pandas, mentre PULSE è un ciclo evento per evento.
- **Confronto sul periodo di sviluppo, senza stampare metriche di rendimento.**
  - Per ogni lunedì e ogni asset devono coincidere la data dello scambio, il peso dopo lo scambio (entro 0,1 punti
    percentuali) e il costo pagato (entro 0,01 bp del capitale).
  - Lo scarto fra i rendimenti annualizzati dei due calcoli deve stare entro 5 bp all'anno. Si stampa solo lo
    scarto, non i rendimenti.
- **Lookahead.** Al posto di `lookahead-analysis` e `recursive-analysis`, un test tronca i dati a una data e
  verifica che pesi e scambi fino a quella data non cambino. Gira su dati sintetici e sui dati reali di sviluppo.
- **Ambiguità.** Ogni ambiguità del documento emersa dal confronto si risolve per scritto qui, prima della firma.
- **Freqtrade** si usa solo per il dry-run del criterio 7.

#### Ambiguità risolte dopo il primo confronto (2026-11-11)

Primo confronto sullo sviluppo:
- V3: 103 scambi in entrambi i calcoli, tutti alle stesse date. Pesi diversi fino a 0,24 punti, sopra la
  tolleranza di 0,1.
- Benchmark: 62 scambi su 63 coincidono. Lo scarto annuo è 12,7 bp, sopra la tolleranza di 5.

Le cause sono punti che il documento non fissava. Si risolvono così, e valgono per strategia e benchmark. Poi
entrambi i calcoli si allineano al testo, ciascuno per conto suo.

1. **Valutazione al momento della decisione.**
   - Il peso attuale usato per la soglia e per il tetto di leva si calcola alla **chiusura della domenica**: è
     l'informazione disponibile alle 00:00 UTC.
   - Anche il riallineamento del primo lunedì del mese si valuta alla chiusura della domenica, in sola cassa.
     Avviene anche se manca la candela del lunedì.
2. **Dimensione dello scambio.**
   - Quantità nuova = peso obiettivo × capitale della quota all'apertura del lunedì / prezzo di apertura.
   - I costi si pagano dopo, dalla cassa della quota. Il peso dopo lo scambio è quindi leggermente diverso dal
     peso obiettivo.
   - È quello che fa un ordine reale, che non conosce in anticipo i costi esatti.
3. **Tetto di leva.** Se dopo il riallineamento il peso attuale supera 1, si scambia comunque verso il peso
   obiettivo, anche sotto la soglia dei 10 punti.
   - **3b.** Il controllo si fa **solo il lunedì del riallineamento**, non ogni settimana.
   - Un acquisto fino a peso 1 con i costi pagati dopo lascia la cassa della quota negativa per l'importo dei
     costi, quindi il peso resta appena sopra 1 (circa 0,4%).
   - Controllarlo ogni settimana produrrebbe micro-scambi ripetuti. Questa leva residua si accetta e si dichiara.
4. **Primo livello.** La prima decisione con m definito non conta come cambio di livello: non c'è un livello
   precedente. Si scambia solo se lo scarto supera la soglia.
5. **Scelte già uguali nei due calcoli, ora scritte:**
   - rendimenti semplici sulle chiusure, sfasamenti in giorni di calendario;
   - σ₆₃ = deviazione standard campionaria (ddof = 1) degli ultimi 63 rendimenti giornalieri × √365;
   - segno(0) = 0;
   - prima che m e σ esistano il peso obiettivo è 0, quindi il benchmark, che non usa m, comincia prima di V3.
     Succede tutto prima dello sviluppo;
   - soglia con il confine incluso;
   - un cambio di livello porta al peso obiettivo anche sotto la soglia;
   - con la candela del lunedì mancante, quella settimana non si scambia quell'asset e m non diventa il livello
     di riferimento;
   - prima del 2025-01-01 si raddoppiano tutte e tre le componenti di costo;
   - le regole sulle candele mancanti consecutive e sulla copertura valgono per la validità dell'esito
     (sezione 5), non dentro la simulazione.

#### Esito del confronto dopo l'allineamento (2026-11-11)

Ognuno dei due calcoli si è allineato al testo qui sopra per conto suo; il secondo ha ricevuto solo il testo.

| Sviluppo 2018-2020 | V3 | Benchmark |
|---|---|---|
| Scambi (PULSE / indipendente / coincidenti) | 103 / 103 / 103 | 63 / 63 / 63 |
| Scarto massimo del peso dopo lo scambio | 5e-9 punti | 5e-9 punti |
| Scarto massimo del costo | 2e-11 bp del capitale | 5e-12 bp del capitale |
| Scarto del rendimento annualizzato | 3e-9 bp/anno | 4e-9 bp/anno |

- Il troncamento dei dati al 2019-06-30 lascia identici pesi, scambi ed equity fino a quella data, per V3 e
  per il benchmark.
- **Criterio 6 superato.**
- **Limite dell'indipendenza.** La sessione separata non ha visto il codice di PULSE. Il documento che ha letto
  riportava però il numero di scambi della revisione 1 (103 e 63). Il confronto scambio per scambio, con date,
  pesi e costi, non si può ottenere solo conoscendo quei due numeri, ma si dichiara.

### Revisione 3, 2026-11-11: dettagli del dry-run e delle robustezze, scritti prima del primo ordine

- **Motivo.** Il criterio 7 e le due robustezze della sezione 2 lasciavano aperti dettagli di esecuzione. Si
  fissano qui prima del primo ordine del dry-run e senza aver calcolato nessuna metrica di rendimento (deciso con
  Grok).
- **Dry-run (criterio 7).**
  - Sede: freqtrade **2026.10** (versioni delle dipendenze in `freqtrade/requirements.lock`), exchange `myokx`
    cioè OKX Europe, in dry-run, senza chiavi. Config in `freqtrade/config.dryrun.json`, strategia vuota
    `NoSignal`. PULSE manda gli ordini via REST su 127.0.0.1 (`pulse_mm/research/crypto_trend/dryrun.py`).
  - Coppie BTC/USDC ed ETH/USDC. Capitale simulato 100.000 USDC; ogni acquisto vale **10.400 USDC** (10,4%).
  - Per ogni asset: se non c'è una posizione aperta si compra, altrimenti si vende la quantità comprata.
  - **Prezzo di OKX all'istante della decisione** = metà fra bid e ask dell'API pubblica di OKX Europe, letta
    subito prima dell'ordine. Lo scarto di esecuzione si misura quindi contro il prezzo medio e comprende
    mezzo spread e slippage: si confronta con 5 + 5 = **10 bp**. La commissione è a parte (criterio 8).
  - Scarto di esecuzione col segno del costo: (eseguito − medio) / medio per gli acquisti, il contrario per le
    vendite. La differenza fra sedi si riporta col suo segno e anche col segno del costo.
  - La differenza fra sedi confronta le 00:05 su OKX con l'apertura delle 00:00 su Coinbase: comprende cinque
    minuti di movimento del prezzo, e si dichiara.
  - **Giorno valido:** per entrambi gli asset c'è il prezzo OKX, l'ordine parte entro **120 secondi** dalle 00:05
    UTC, il dry-run lo esegue, l'apertura Coinbase del giorno esiste.
  - **Giorno non valido: si recupera in coda.** Si registra con la causa e il calendario si allunga di un giorno,
    fino a 31 giorni di calendario. Al **quarto** giorno non valido il dry-run fallisce: si corregge la causa e
    si riparte da zero con una nuova data, tenendo e riportando il registro del tentativo fallito.
  - Senza prezzo OKX l'ordine non parte. Un'esecuzione partita in ritardo non manda ordini.
  - **Impronta del piano.** `dryrun start` scrive data d'inizio, taglia e impronta di codice, config, strategia
    e versioni. Ogni giorno l'esecuzione si rifiuta se l'impronta è cambiata: un cambio invalida il dry-run.
  - **Controllo giornaliero** (`dryrun check`, 15 minuti dopo l'ordine): segnala ordini non partiti, prezzi OKX
    mancanti, ritardi, ordini non eseguiti e aperture Coinbase mancanti; conta giorni validi e saltati.
  - Prova di collegamento del 2026-11-11, fuori dal conteggio: un acquisto e una vendita per asset, tutti
    eseguiti. Il registro della prova è separato e non entra nel risultato.
- **Avvio, scritto il 2026-11-11 prima del primo ordine:** primo giorno **2026-11-13**, ultimo giorno possibile
  2026-12-13, impronta del piano **`ef309217960d3c14`** (in `data/crypto_trend/live/dryrun/start.json`). Sostituisce
  il piano `13eaed2b36f78662`, archiviato senza nessun ordine eseguito, per le aggiunte della revisione 3b.
  - Gira sul Mac di Federico con tre job di launchd (`freqtrade/launchd/`): freqtrade sempre acceso, ordini alle
    01:05 e controllo alle 01:20 ora italiana (00:05 e 00:20 UTC, valido finché vale l'ora solare).
  - `caffeinate` impedisce lo stop per inattività finché freqtrade gira. Con il coperchio chiuso o senza
    alimentatore il Mac può dormire: quel giorno conta come non valido.
- **Robustezze, senza soglie, calcolate solo insieme a validazione e test.**
  - **EUR:** equity in USD divisa per il cambio di riferimento BCE (USD per un euro, serie
    EXR.D.USD.EUR.SP00.A), usando per ogni giorno l'ultimo cambio pubblicato fino a quel giorno. File grezzo con
    impronta e stesso blocco delle date delle candele. Si riportano metriche e bootstrap in EUR.
  - **Parità di rischio:** al riallineamento del primo lunedì del mese le quote vanno in proporzione a 1/σ₆₃ di
    ogni asset alla chiusura della domenica, invece di 50/50. Prima che σ₆₃ esista resta 50/50. Tutto il resto
    è identico, benchmark compreso.
  - Prima della firma il codice si prova solo su dati sintetici. Sullo sviluppo si controlla solo la copertura
    dei cambi BCE (ok: nessun buco oltre 5 giorni).

### Revisione 3b, 2026-11-11: cosa dimostra il dry-run, profondità del book e giorni agitati

- **Limite riconosciuto prima di iniziare.** Con 10.400 USDC per ordine il dry-run di freqtrade riempie quasi
  sempre al primo livello del book (prova di collegamento: scarti fra 0 e 1,5 bp contro il tetto di 10 bp).
  - Il criterio 7 quindi **verifica la catena di esecuzione e la differenza fra sedi**.
  - Sullo slippage può fallire solo in casi estremi: resta un limite basso dei costi.
  - La misura vera dello slippage resta al paper trading con riempimenti da taker sul book reale, dopo un
    eventuale "passa" sul test (fase 5). Niente ordini reali piccoli: misurerebbero ancora meno e
    richiederebbero soldi veri (discusso con Grok).
- **Profondità del book.** A ogni ordine si salva la fotografia dei primi 400 livelli del book di OKX Europe,
  letta subito dopo la quotazione. Si calcola il costo rispetto al prezzo medio della stessa taglia ×1, ×5 e ×10
  (10.400, 52.000 e 104.000 USDC). Se il book fotografato non basta, si conta e si riporta. Il book mancante non
  rende il giorno non valido.
- **Spread e giorni agitati.** Lo spread di OKX alla decisione si riporta già (bid e ask in ogni riga). Un giorno è
  **agitato** se:
  - il rendimento giornaliero Coinbase, chiusura su chiusura, supera in valore assoluto il **5% per BTC** o il
    **7% per ETH** (circa due deviazioni standard giornaliere con volatilità annue del 45% e del 65%), oppure
  - lo spread di OKX alla decisione supera **5 bp**.

  Se nei giorni del dry-run non ce n'è nessuno, si dichiara che il risultato vale per giorni calmi.

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
