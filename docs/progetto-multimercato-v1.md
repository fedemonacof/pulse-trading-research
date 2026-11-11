# PULSE multi-mercato: progetto (v1, nessun codice)

Stato: v1. Integra tre fonti:
- la revisione di Grok della v0 ([progetto-multimercato-v0.md](progetto-multimercato-v0.md));
- la ricerca legale di Federico dell'11/11/2026 (`ricerca-connettori.md`);
- la valutazione di freqtrade.

Niente è implementato e niente è firmato. Questo documento non è un parere legale: prima di aprire un conto a
denaro reale serve un avvocato e un commercialista.

## Cosa cambia rispetto alla v0

| Tema | v0 | v1 |
|---|---|---|
| Mercati di previsione | Polymarket, Kalshi, Manifold | **solo Manifold (denaro finto)**: Polymarket e Kalshi sono nell'elenco ADM dei siti bloccati, l'ESMA vieta al retail i contratti su eventi economici. Betfair.it solo sport, senza ambiente di prova, eventualmente dopo |
| Crypto | Binance/Bybit via ccxt | **OKX Europe** (`myokx`, perpetual MiFID, demo API) prima scelta, **Kraken** seconda, Bybit EU solo spot. Binance, Bitget e Deribit esclusi |
| Motore crypto | connettore e backtest scritti da zero | **freqtrade** come processo separato, parlato via REST |
| Esecuzioni simulate | riempimento se il prezzo attraversa il limite | **solo da taker**: si paga lo spread e si consumano i livelli del book |
| Perdita peggiore sui perp | il minore fra stop e liquidazione | **il maggiore** fra la perdita fino alla liquidazione e 3 × distanza dello stop |
| Limite per sottostante | 10% per asset | 10% per **gruppo correlato**: tutte le crypto sono un gruppo solo |
| Binari, tetto di prezzo | niente sopra 0,97 | **tetto 0,99**, perché l'ipotesi longshot si sfrutta comprando NO a 0,95-0,99 |
| Ipotesi crypto | trend, carry, momentum fra coin | **trend su BTC/ETH**: prima long/flat sullo spot, il long/short sui perp solo dopo; carry rinviato, momentum fra coin scartato |
| Calcolo di potenza | soglia fissa | effetto minimo rilevabile con potenza 80% ≈ 4,9 punti con 300 cluster a p = 0,10 (confermato da Grok) |
| Soglia campione | 300 cluster fissi | soglia **derivata da un calcolo di potenza** sull'effetto minimo rilevabile |

## 0. Vincoli

### File congelati
I nove file in `desk/research.py`, `FROZEN_FILES` (risk, backtest, config, reflex, strategie) non si toccano. Il
pacchetto `pulse_mm/` li avvolge. Tre regole nuove, da Grok:
1. **Nessuna scorciatoia.** Un test percorre tutti i punti del codice che arrivano a un connettore e dimostra che
   nessun ordine parte senza il gate globale. È lo stesso tipo di test che oggi esiste per il `RiskGate`.
2. **Solo più restrittivo.** Il gate globale può rifiutare un ordine che il `RiskGate` congelato accetterebbe, mai
   il contrario. Un test lo verifica con casi limite.
3. **Doppio log.** Per ogni ordine il diario registra la decisione e il motivo di entrambi i gate.

### Costi divisi per componente (domanda di Grok)
Il backtest congelato (`desk/backtest.py`) **non** divide i costi. Ha due soli parametri, `cost_bps` (1) e
`slippage_bps` (5). Lo slippage è dentro il prezzo di esecuzione e il P&L del trade esce già al netto. Inoltre è solo
long, quindi senza prestito titoli e senza funding. `pulse_st/core.py` invece separa già commissioni+spread
(raddoppiati nei giorni di stress), tassa SEC/FINRA e prestito, ma in serie giornaliere e non per trade.

Serve quindi un adattatore, ed è **il primo compito della fase 1**: un registro dei costi
(`pulse_mm/core/costs.py`).
- Prende i trade di qualunque motore: backtest congelato, `pulse_st`, freqtrade.
- Ricostruisce le componenti `fee`, `spread`, `slippage`, `funding`, `borrow` e `other`.
- Per il backtest congelato le ricostruisce dai parametri noti: commissione = `cost_bps` × nozionale, slippage =
  `slippage_bps` × nozionale.
- Per freqtrade le legge dai campi del trade (commissioni di apertura e chiusura, funding). Quali campi esporta
  esattamente va **verificato** sulla versione installata.
- Prova di correttezza: la somma delle componenti deve coincidere con la differenza fra P&L lordo e netto,
  entro 0,01 bp.

## 1. Mercati e connettori

| Mercato | Piattaforma | Modalità massima oggi | Note |
|---|---|---|---|
| Azioni | Alpaca | paper | esistente, congelato |
| Crypto spot + perp | OKX Europe (`myokx` in freqtrade) | `data`, poi dry-run | **confermare in app** che i perpetual X-Perps siano abilitati dall'Italia |
| Crypto, alternativa | Kraken (`kraken`, `krakenfutures`) | `data` | la demo pubblica dei futures è stata dismessa il 14/7/2026 |
| Previsione | Manifold | `paper` (è già denaro finto) | serve per la meccanica e per il comitato, **non** dimostra un vantaggio con soldi veri |
| Previsione, sport | Betfair.it | `off` | concessione ADM, ma nessun ambiente di prova e futuro incerto nel 2027 |

Mai Polymarket, Kalshi o PredictIt, né VPN per aggirare i blocchi.

### Interfaccia comune
È invariata rispetto alla v0. Gli strumenti hanno un tipo (`spot_linear`, `perp_linear`, `binary`), una scadenza
e un sottostante. Le interfacce restano quattro e separate: `MarketData`, `Execution`, `Account` e `CostModel`.
Le modalità sono `off` / `data` / `paper` / `live`, e la dashboard non arriva mai a `live`.

### freqtrade come motore crypto
- **Confine GPL.** freqtrade è GPL-3.0 e PULSE è MIT. Gira come processo separato, con la sua configurazione, e
  `pulse_mm/connectors/freqtrade.py` ci parla solo via REST API. Nessun file di freqtrade viene copiato nel
  repository.
- **Cosa resta spento:** hyperopt, perché cerca i parametri migliori sui dati, cioè l'overfitting che le
  pre-registrazioni evitano. Restano spente anche le liste di coppie dinamiche basate sul volume di oggi.
- **Universo point-in-time:** i primi N per volume a ogni data li calcola PULSE e li passa come lista statica per
  periodo. Le coin delistate vanno incluse, altrimenti si ripete l'errore dei 15 titoli.
- **Prima di ogni pre-registrazione si eseguono:**
  - `lookahead-analysis` e `recursive-analysis` di freqtrade sulla strategia;
  - un confronto sullo stesso periodo fra il backtest di freqtrade e un ricalcolo indipendente in PULSE su
    barre giornaliere. La differenza deve stare entro 5 bp all'anno.
- **Statistiche:** bootstrap, Deflated Sharpe, `trials.jsonl` e impronta del codice girano in PULSE sui trade
  esportati. L'impronta copre la strategia freqtrade, la sua configurazione e la versione di freqtrade fissata.
- **Paper:** si usa il dry-run di freqtrade. Per i fill si applica la regola taker qui sotto; se il dry-run di
  freqtrade è più ottimista, vale la stima di PULSE.

### Bias del backtest di freqtrade: criteri di accettazione (revisione di Grok)

Ogni punto è un requisito della pre-registrazione crypto. Il suo output va allegato al documento firmato. Se un
punto non è soddisfatto, il test non parte.

| Bias | Correzione richiesta |
|---|---|
| Stop e target dentro la stessa candela, risolti in modo ottimistico | `--timeframe-detail 1m`; dove il dettaglio manca, si assume che sia scattato **prima lo stop** |
| Slippage zero di default | penalità fissa per lato, calibrata sullo spread reale di OKX Europe nelle ore operative; il test si ripete con la penalità **raddoppiata** |
| Commissioni | tariffa **taker** del livello reale del conto, mai maker né scontata |
| Funding mancante trattato come zero | storico scaricato con `--candle-types funding_rate mark`; un controllo fallisce se mancano tassi nel periodo; l'intervallo non si assume: si legge **dall'API di OKX per ogni tasso storico scaricato**, perché alcuni exchange lo accorciano quando il mercato è agitato. Un controllo fallisce se trova un intervallo diverso da quello usato nel registro dei costi. Serve solo per l'ipotesi 2 |
| Liquidazione su mark, backtest su last | distanza dalla liquidazione e limite del 40% ricalcolati sulle candele **mark** |
| Buchi e code anomale nei dati | controllo delle candele mancanti; ispezione dei crolli di marzo 2020, maggio 2021 e novembre 2022; discontinuità fra contratti e delisting gestiti nell'universo point-in-time |
| Lookahead e ricorsione | `lookahead-analysis` e `recursive-analysis` obbligatori, output salvato come allegato |
| Ordini limit in dry-run eseguiti appena toccati | in paper solo ordini market o simulati da taker (sezione "Esecuzioni simulate"); versione di freqtrade fissata; un test piazza un ordine limit in dry-run e registra quando risulta eseguito rispetto al prezzo. Se risulta eseguito appena toccato, vale la regola taker |

**Test di riconciliazione, prima della firma.**
- Stessi segnali per alcune settimane: i trade del backtest si confrontano con quelli del dry-run sullo stesso
  periodo.
- Si misura lo scarto medio per trade fra prezzo eseguito in dry-run e prezzo del backtest, costi compresi.
- Se lo scarto medio supera i costi ipotizzati nel modello, il modello dei costi si rivede **prima** di firmare.
  La revisione si registra nel documento.
- Questo controllo si aggiunge al confronto con il ricalcolo indipendente in PULSE.

### Esecuzioni simulate (paper)
- **Sempre da taker.** Un ordine consuma i livelli del book visibile al momento della decisione e paga lo spread.
  Non si simulano ordini passivi in coda, perché non si può sapere se sarebbero stati eseguiti.
- **Funding a parte.** Il funding dei perp è una voce di costo separata, addebitata a ogni scadenza di funding
  con il tasso reale.

## 2. Risk layer

Un solo numero comune: la **perdita nel caso peggiore** (`worst_case_loss`) in EUR.
- Binario: il premio pagato.
- Spot: valore × movimento di stress (3 × ATR giornaliero, minimo 20% per le crypto).
- Perp: **il maggiore** fra la perdita fino alla liquidazione (in margine isolato, il margine impegnato più le
  commissioni di liquidazione) e 3 × la perdita alla distanza dello stop. Nelle crypto i gap sono frequenti e uno
  stop non è garantito.

### Globali

| Regola | Valore |
|---|---|
| Perdita giornaliera | −2% dell'equity totale → chiude tutto ovunque (giorno UTC per i mercati 24x7) |
| Drawdown massimo | 15% → stop totale, ripartenza solo a mano |
| Somma delle `worst_case_loss` aperte | ≤ 6% dell'equity |
| Esposizione netta per **gruppo correlato** | ≤ 10% dell'equity. Tutte le crypto (spot, perp, binari su crypto) sono **un gruppo solo**: BTC ed ETH hanno una correlazione di circa 0,8 |
| Budget per mercato | azioni ≤ 100%, crypto ≤ 30% dell'equity; Manifold ha un budget in Mana a parte, mai convertito |
| Kill switch | uno solo, chiude tutti i connettori e ferma freqtrade |
| Dati vecchi | nessun ordine se l'ultimo prezzo ha più di 60 s (crypto) o 5 min (binari) |

### Crypto spot
- Universo: i primi 10 per volume a quella data, con volume a 24 ore ≥ 50 milioni di $. Stablecoin escluse.
- Massimo 5% per posizione e 3 posizioni aperte.

### Perpetual (solo BTC ed ETH, solo se abilitati dall'Italia)
- Margine isolato, mai cross. Leva per posizione ≤ 2 e leva lorda del conto ≤ 1,5. Il limite di 2 copre anche il
  caso in cui le autorità applichino il 2:1 indicato dall'ESMA a febbraio 2026.
- Distanza dalla liquidazione ≥ 40% del mark. Lo stop deve stare entro un terzo di quella distanza.
- Funding:
  - non si apre se il funding annualizzato contro la posizione supera il 30%;
  - si chiude se il funding pagato supera lo 0,5% del nozionale.

### Binari (Manifold, in Mana)
- Massimo 1% del budget per mercato, 3% per gruppo correlato (stesso evento o tema), totale ≤ 10%.
- Prezzi ammessi per l'acquisto: **da 0,01 a 0,99**. L'ipotesi longshot si sfrutta comprando il NO quando il SÌ è
  sopravvalutato, quindi spesso a 0,95-0,99. La pre-registrazione dichiara la fascia testata.
- Scadenza ≤ 90 giorni. Ordine ≤ 10% della profondità visibile. Lista nera dei mercati con criteri di risoluzione
  ambigui.

## 3. Ipotesi

### Crypto: il trend su BTC/ETH, in due ipotesi separate

**Ipotesi 1: long/flat sullo spot (decisa con Grok).**
- **Segnale: media fissa a 1, 3 e 12 mesi, una sola regola (decisa con Grok).**
  - Per ogni orizzonte h ∈ {21, 63, 252} giorni il segnale è il segno del rendimento a h giorni.
  - Media con pesi uguali: m = (s₂₁ + s₆₃ + s₂₅₂) / 3, quindi m ∈ {−1, −1/3, 1/3, 1}.
  - **Regola di combinazione proposta:** esposizione = max(0, m), cioè 0, 1/3 o 1. Con m = −1/3 si sta in
    liquidità, con m = 1/3 a un terzo dell'esposizione, con m = 1 pieni.
  - **Volatility targeting con target fisso al 40% annuo**, dichiarato ora e non stimato dai dati. Usare la
    volatilità media del periodo di sviluppo sarebbe un parametro stimato in più e una piccola fuga di informazione
    verso validazione e test.
    - Peso per asset = max(0, m) × min(1, 40% / volatilità realizzata a 63 giorni annualizzata).
    - **Tetto di leva 1, scritto esplicitamente:** quando la volatilità realizzata scende sotto il 40%, la
      strategia non va a leva. Resta al 100% e quindi sotto il target di volatilità. Quando la volatilità supera il
      40%, l'esposizione scende sotto il 100%.
  - **Due asset, 50/50 (deciso con Grok).** Metà del capitale a BTC e metà a ETH, ognuno con il suo m e il suo
    volatility targeting. È già quasi una parità di rischio: aggiungere pesi inversi alla volatilità correggerebbe
    due volte la stessa cosa e aggiungerebbe un parametro. I pesi a parità di rischio si riportano solo come analisi
    di robustezza.
  - **Liquidità:** la parte non investita va in stablecoin o EUR, da fissare con il documento legale.
    - **Rendimento della liquidità = 0%** nel test, salvo che il documento legale indichi un rendimento sicuro e
      lecito.
    - Vale per strategia e benchmark allo stesso modo, perché anche il benchmark tiene liquidità quando la
      volatilità supera il 40%.
    - Lo 0% penalizza la strategia, che sta più spesso in liquidità. Si dichiara.
  - **Ribilanciamento:**
    - una volta al giorno, alle 00:00 UTC, sulla candela giornaliera appena chiusa;
    - esecuzione alle 00:05 UTC con ordini market, quindi costo da taker;
    - si tocca la posizione solo se il peso obiettivo differisce da quello attuale di almeno **10 punti
      percentuali** del capitale dell'asset, oppure se m cambia livello;
    - la soglia evita i piccoli aggiustamenti del volatility targeting che si mangiano i costi;
    - è fissa, non legata a un guadagno atteso, che sarebbe un modello in più da stimare e da contare.
  - **Controllo del turnover, prima della firma.** Il registro dei costi calcola il turnover annuo (nozionale
    scambiato / capitale medio) sul periodo di sviluppo.
    - **Soglia: 10 volte il capitale.** A 10-15 bp per lato, 20 volte costerebbe già 2-3% l'anno, troppo per una
      strategia di trend.
    - Se il turnover supera la soglia, la regola di ribilanciamento si rivede prima di firmare. La revisione si
      registra nel documento.
- **Benchmark alla pari:** buy & hold 50/50 BTC/ETH con lo **stesso target del 40%**, lo stesso tetto di leva 1, la
  stessa volatilità a 63 giorni, lo stesso orario e la stessa soglia di ribilanciamento. L'unica differenza è che
  il benchmark ha sempre m = 1.
  - Motivo della scelta: le crypto hanno cicli più corti delle azioni, e un solo lookback a 12 mesi reagisce tardi
    a crolli e ripartenze. La media riduce anche il rischio di aver scelto il lookback fortunato.
- **Robustezza, non test:** il solo segnale a 12 mesi si riporta come analisi di robustezza, senza soglie.
- **N dell'ipotesi 1 = 3**, contando le varianti considerate e scartate:
  1. 12 mesi da solo;
  2. media con regola binaria (long se m > 0);
  3. media con esposizione proporzionale.
  **Il test principale è la 3, dichiarato ora.** La 1 e la 2 restano tentativi contati nell'N e non possono
  diventare il risultato a posteriori, anche se andassero meglio. Il Deflated Sharpe usa N = 3. Il documento
  riporta anche l'N complessivo della famiglia PULSE.
- **Si dichiara per quello che è: un filtro di trend.** L'ipotesi è che il filtro riduca il drawdown massimo
  rispetto al buy & hold **a parità di rendimento corretto per il rischio**.
- **Benchmark:** buy & hold di BTC/ETH con la **stessa volatilità target**, non zero e non il buy & hold nudo.
  Dettagli più sotto, in "Benchmark alla pari".
- **Tre esiti possibili, dichiarati prima.** Gli intervalli sono IC90 da block bootstrap su blocchi di 21 giorni,
  differenze strategia − benchmark.

  | Esito | Condizione |
  |---|---|
  | **Passa** | IC90 della differenza di drawdown massimo tutto sotto zero **e** limite inferiore dell'IC90 della differenza di Sharpe sopra −0,1 |
  | **Fallisce** | IC90 della differenza di drawdown non tutto sotto zero, **oppure** limite superiore dell'IC90 della differenza di Sharpe sotto −0,1 |
  | **Non concludente** | ogni altro caso, tipicamente un IC90 dello Sharpe che contiene −0,1 |

- Il margine vale sull'intervallo, non sulla stima. Con pochi anni di dati l'IC90 dello Sharpe sarà largo, quindi
  **"non concludente" è l'esito più probabile** e si dichiara prima. Non concludente vale come non passato:
  l'ipotesi 2 non si apre.
- Niente CAGR rettificato per volatilità: con le due strategie alla stessa volatilità target dice quasi la stessa
  cosa dello Sharpe ed è più rumoroso.
- **Precedente:** il filtro a 200 giorni sulle azioni ha avuto lo stesso profilo, un'assicurazione contro i crolli
  e non un vantaggio di rendimento. Si dichiara in anticipo che l'esito più probabile è lo stesso.
- **Perché spot:** senza funding, liquidazione e prezzo mark, le verifiche si dimezzano. I criteri sui perpetual
  della tabella dei bias (funding, mark, liquidazione) non si applicano all'ipotesi 1.

**Ipotesi 2: long/short, solo se l'ipotesi 1 passa la validazione.**
- Pre-registrazione a parte, con la sua N, sui perpetual OKX Europe: margine isolato, **leva 1**, funding
  registrato nel registro dei costi.
- **Motivo del rinvio.** Lo short sulle crypto paga di solito un funding positivo nelle fasi rialziste e va contro
  un drift storicamente al rialzo. Nella letteratura sul trend in crypto quasi tutto il valore viene dal lato long
  e dall'evitare i crolli.
- L'infrastruttura per i perpetual (candele mark, controlli sul funding, distanza dalla liquidazione) si costruisce
  solo se si arriva qui.

**Regole comuni alle due ipotesi.**
- **Perché questa:** ha letteratura, ruota poco ed è poco sensibile ai dettagli di esecuzione.
- **Onestà sull'N:** BTC ed ETH sono in pratica una sola scommessa. Dal 2015 ci sono 3-4 cicli indipendenti. Il
  test storico avrà poca potenza, quindi la pre-registrazione dichiara che servono anni di dati in avanti per una
  conclusione.
- **Rinviato:** il carry sul funding. Vive di commissioni ed esecuzione su due gambe, e il grosso del rendimento
  storico viene dal 2021.
- **Scartato:** momentum fra coin (sopravvivenza), reversal a 1-5 giorni, indicatori tecnici combinati, sentiment,
  LLM che prevede il prezzo.

### Mercati di previsione: calibrazione / longshot su Manifold
- **Limite dichiarato:** Manifold usa denaro finto. Incentivi e partecipanti sono diversi da un mercato a soldi
  veri, quindi una distorsione trovata lì non dimostra che esista con soldi veri. L'esito vale per Manifold e basta.
- **Comitato AI:** solo in avanti, con Brier contro il prezzo del mercato. Sul passato l'LLM conosce gli esiti.

## 4. Backtest e pre-registrazione dei mercati di previsione

### Soglia di campione da un calcolo di potenza
La soglia non si fissa prima: si ricava dall'effetto minimo che si vuole poter vedere.

Con un contratto a prezzo p, l'esito ha deviazione standard σ = √(p(1−p)). Il numero di cluster indipendenti
necessario, con α = 5% bilaterale e potenza 80%, è:

n = ((1,96 + 0,84) × σ / δ)² × DEFF

- δ è la distorsione minima da rilevare, in punti di probabilità.
- DEFF è l'effetto di disegno dovuto ai mercati correlati dentro lo stesso cluster. Si stima sui dati di
  sviluppo e si dichiara prima del test.

| p | σ | δ = 2 punti | δ = 3 punti | δ = 5 punti |
|---|---|---|---|---|
| 0,10 | 0,30 | 1.764 cluster | 784 | 282 |
| 0,05 | 0,22 | 931 | 414 | 149 |

Valori con DEFF = 1. Con 300 cluster e p = 0,10 l'errore standard è di circa 1,7 punti, quindi si rileva solo una
distorsione di circa 5 punti con potenza 80%. Se i dati di sviluppo suggeriscono un effetto più piccolo, il test
si dichiara sottodimensionato **prima** di eseguirlo, oppure si aspetta di avere più dati in avanti.

### Altre regole
- **Unità:** il mercato, raggruppato in cluster (evento o tema × mese di risoluzione). L'inferenza usa un
  bootstrap per cluster.
- **Orizzonti:** T−30, T−7 e T−1 giorni sono **tre test** e contano tutti nell'N di `trials.jsonl`.
- **Prezzi:** bid e ask a quel momento. Si escludono i mercati sotto la soglia di liquidità *a quel momento*.
- **Mercati annullati, risolti N/A o contestati:** si dichiarano con il loro numero e si trattano con la regola
  scritta prima (rimborso del premio). Non si scartano in silenzio.
- **Divisione per data di risoluzione:** sviluppo, validazione e test bloccato, mai casuale.
- **Soglie di successo:** IC90 del rendimento medio per cluster > 0, più un test sulla pendenza di calibrazione.
- **Fase in avanti subito:** il raccoglitore di snapshot su Manifold va acceso nella fase 2, perché ogni mese
  raccolto in avanti è dato pulito, mai visto.

## 5. Struttura delle cartelle

```
pulse_mm/
  core/
    instrument.py      strumento, tipo di payoff, capabilities
    interfaces.py      MarketData, Execution, Account, CostModel (Protocol)
    costs.py           registro dei costi per componente (primo compito della fase 1)
    clock.py           sessione / 24x7 / fino a scadenza
    exposure.py        gruppi correlati, worst_case_loss
    risk.py            gate globale, solo più restrittivo di desk/risk.py, doppio log
    modes.py           off / data / paper / live, conferme
  connectors/
    alpaca.py          adattatore sopra desk/broker.py, senza modificarlo
    freqtrade.py       client REST verso il processo freqtrade (OKX Europe, Kraken)
    manifold.py        API ufficiale, dryRun per i test
    shadow.py          esecuzioni simulate da taker sul book reale
  data/
    crypto_fetch.py    barre e funding storici, universo point-in-time
    manifold_snap.py   raccoglitore in avanti + ricostruzione dei mercati risolti
  backtest/
    check_freqtrade.py ricalcolo indipendente per confrontare il backtest di freqtrade
    events.py          backtest a eventi per i binari, bootstrap per cluster
  research/
    crypto_trend/      una cartella per pre-registrazione, come pulse_st/
    manifold_calib/
  tests/
freqtrade/             fuori dal pacchetto: config, strategia, versione fissata (GPL, processo separato)
docs/
  legale-okx.md, legale-kraken.md, legale-manifold.md
  prereg-crypto-trend-v0.md
  prereg-manifold-calib-v0.md
```

## 6. Piano a fasi

1. **Fase 0: legalità.**
   - La ricerca generale è fatta.
   - Restano da fare: la conferma in app dei perpetual OKX Europe dall'Italia, la richiesta a Kraken
     dell'ambiente di test e un documento `legale-<venue>.md` per piattaforma.
   - Un mercato senza documento resta `off`.
2. **Fase 1: fondamenta.**
   - Registro dei costi, interfacce e adattatore Alpaca.
   - Gate globale con i tre test: nessuna scorciatoia, solo più restrittivo, doppio log.
   - Criterio di uscita: impronta invariata e tutti i test esistenti verdi.
3. **Fase 2: solo dati.**
   - Si scarica lo storico di BTC ed ETH.
   - Si accende il raccoglitore Manifold.
   - Si installa freqtrade in `data`, con la versione fissata.
   - Le date di sviluppo, validazione e test si fissano prima di guardare.
4. **Fase 3: pre-registrazione del trend crypto, ipotesi 1 (long/flat sullo spot).** L'ipotesi 2 si apre solo se
   la 1 passa la validazione.
   - Prima il confronto fra freqtrade e il ricalcolo PULSE, poi la tabella dei bias.
   - Poi alcune settimane di dry-run senza soldi per il test di riconciliazione. Il dry-run serve solo a
     misurare i costi: i suoi rendimenti non entrano nel test.
   - Revisione con Grok, firma, una sola esecuzione.
5. **Fase 4: pre-registrazione della calibrazione su Manifold.** Calcolo di potenza, poi firma.
6. **Fase 5: paper.** Dry-run di freqtrade su OKX Europe con esecuzioni da taker, solo se la fase 3 passa. Manifold
   in Mana, con il comitato AI a peso 0 valutato con il Brier.
7. **Fase 6: live.** Solo crypto, solo con documento legale, 12 mesi di paper nelle regole, parere di un
   commercialista (imposta del 33% sulle crypto) e approvazione esplicita.

Aspettativa dichiarata: negativa. Il valore è l'infrastruttura e una risposta pulita per ogni mercato.
