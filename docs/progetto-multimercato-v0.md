# PULSE multi-mercato: progetto (bozza v0, nessun codice)

Stato: proposta da discutere con Grok. Niente è implementato. Nessun mercato nuovo va oltre "solo dati" finché
la verifica legale per quel mercato non è scritta in questo documento.

## 0. Vincolo che cambia il progetto

Il risk layer e il backtest che si vorrebbero "comuni" sono proprio file congelati:
`desk/risk.py`, `desk/backtest.py`, `desk/config.py`, `desk/reflex.py` e `desk/strategies/*` (lista in
`desk/research.py`, `FROZEN_FILES`). Non si possono generalizzare sul posto.

Scelta: il pacchetto nuovo `pulse_mm/` **avvolge** il codice esistente e non lo modifica.
- Le azioni continuano a passare dal `RiskGate` congelato. Il nuovo gate globale si aggiunge prima: un ordine
  azionario deve superare entrambi.
- Il backtest azionario resta quello congelato. Crypto e mercati di previsione hanno i loro motori in `pulse_mm/`.
- Prova di non regressione a ogni fase: `python main.py fingerprint` invariato e i 102 test esistenti che passano.

## 1. Interfaccia comune dei connettori

Idea centrale: il resto del sistema non ragiona per "azione", "coin" o "contratto", ma per **strumento con un tipo
di payoff**. Ogni strumento sa dire quanto può perdere al massimo, e il risk layer lavora solo su quel numero.

### Strumento

| Campo | Significato |
|---|---|
| `id`, `venue` | identificativo stabile, es. `alpaca:SPY`, `binance:BTCUSDT-PERP`, `polymarket:<market>:YES` |
| `kind` | `spot_linear` (azioni, crypto spot), `perp_linear` (perpetual), `binary` (contratto 0/1) |
| `quote` | valuta di regolamento (USD, USDT, USDC, EUR) |
| `tick`, `lot`, `min_notional` | vincoli dell'ordine |
| `expiry` | `None` per spot/perp; data di risoluzione prevista per i binari |
| `underlying` | sottostante comune per aggregare l'esposizione (es. `BTC` per spot, perp e un binario "BTC sopra 100k") |
| `capabilities` | `short`, `bracket_native`, `paper`, `testnet`, `hours` (`session` / `24x7` / `until_expiry`) |

Per i binari il prezzo è sempre una probabilità in [0, 1] e la quantità è in quote che pagano 1 o 0.
Comprare NO equivale a vendere YES: il connettore lo normalizza, il resto del sistema vede solo `side` e `qty`.

### Quattro interfacce separate (non un'unica classe Broker)

1. **`MarketData`**
   - `bars(instr, start, end, freq)`: OHLCV; per i binari OHLC della probabilità.
   - `book(instr)`: miglior bid/ask e profondità. Serve per i costi e per i riempimenti simulati.
   - `funding(instr, start, end)`: solo perpetual.
   - `resolution(instr)`: solo binari. Esito, data, eventuale contestazione o annullamento.
   - `universe(asof)`: strumenti disponibili a quella data. Point-in-time obbligatorio: è la lezione dell'S&P 500.
2. **`Execution`**
   - `submit(OrderIntent) -> order_id`. `OrderIntent` contiene `instr`, `side`, `qty`, `type` (`limit`/`market`),
     `limit_price`, `reduce_only`, `tif` e `client_id`. Il `client_id` rende idempotente il reinvio dopo un errore
     di rete.
   - `cancel(order_id | instr | all)`, `close(instr)`, `close_all()`, `fills()`.
   - Le protezioni (stop, target) le gestisce il motore se `bracket_native` è falso: il comportamento è lo stesso
     ovunque.
3. **`Account`**
   - `equity()`, `cash()` e `positions()`. Una `Position` ha `qty`, `avg_price`, `mark` e `unrealized`, più i campi
     del tipo: `margin`, `liq_price` e `funding_paid` per i perp; `cost` (= perdita massima) e `payoff_if_yes`
     per i binari.
4. **`CostModel`**
   - `expected(intent, book) -> Cost` prima dell'ordine e `realized(fill) -> Cost` dopo.
   - `Cost` ha campi separati: `fee`, `spread`, `slippage`, `funding`, `borrow`, `other`. Così il diario può
     dire da dove viene ogni punto base perso.
   - Una sola regola per tutti i mercati: i backtest usano il costo stimato **raddoppiato** nei giorni di stress,
     come in PULSE-ST.

### Modalità per connettore

`off` → `data` (solo lettura) → `paper` → `live`.
- `paper` per crypto: preferire **riempimenti ombra sul book reale** (`connectors/shadow.py`) ai testnet. I testnet
  hanno prezzi e liquidità finti e quindi falsano i costi. Il testnet serve solo a provare la meccanica degli ordini.
- `paper` per i mercati di previsione: solo riempimenti ombra. Un ordine si considera eseguito solo se il prezzo
  attraversa il limite, con una penalità di coda.
- `live`: stessa doppia conferma di oggi, più `LEGAL_CHECKED_<VENUE>=<data>` scritto a mano. La dashboard può
  spostare un connettore tra `off`, `data` e `paper`, **mai** su `live`.

## 2. Risk layer: limiti fissi proposti

Un solo numero comune: la **perdita nel caso peggiore** (`worst_case_loss`) in EUR per ogni posizione.
- Binario: il premio pagato, esatto.
- Spot: valore × movimento di stress (3 × ATR giornaliero, minimo 20% per le crypto).
- Perp: il minore fra la perdita allo stop e la perdita alla liquidazione, più le commissioni di liquidazione.
  Si conta comunque l'intero margine se lo stop non è garantito.

### Globali (tutti i mercati insieme)

| Regola | Valore |
|---|---|
| Perdita giornaliera | −2% dell'equity totale → chiude tutto ovunque, pausa fino al giorno dopo (giorno UTC per i 24x7) |
| Drawdown massimo | 15% → stop totale, ripartenza solo a mano |
| Somma delle `worst_case_loss` aperte | ≤ 6% dell'equity |
| Esposizione per sottostante (es. BTC su spot + perp + binari) | ≤ 10% dell'equity in valore netto |
| Budget per mercato | azioni ≤ 100%, crypto ≤ 30%, previsione ≤ 10% dell'equity |
| Kill switch | uno solo, chiude tutti i connettori |
| Dati vecchi | nessun ordine se l'ultimo prezzo ha più di 60 s (crypto) o 5 min (binari) |

### Crypto spot
- Universo: solo i primi 10 per volume a quella data, con volume a 24 ore ≥ 50 milioni di $. Stablecoin escluse.
- Massimo 5% dell'equity per posizione e 3 posizioni aperte. Stop a 2 × ATR come per le azioni.

### Perpetual (solo se legali e solo BTC ed ETH)
- Solo margine **isolato**, mai cross.
- Leva per posizione ≤ 2, leva lorda del conto ≤ 1,5.
- Distanza dal prezzo di liquidazione ≥ 40% del mark. Lo stop deve stare entro un terzo di quella distanza.
- Funding:
  - non si apre se il funding annualizzato contro la posizione supera il 30%;
  - si chiude se il funding pagato supera lo 0,5% del nozionale.
- Nessuna posizione aperta nei 15 minuti attorno al calcolo del funding, se la strategia non lo prevede.

### Binari
- Massimo 1% dell'equity per mercato e 3% per gruppo correlato (stesso evento o tema, es. tutte le elezioni USA).
- Totale binari ≤ 10%: il capitale resta bloccato fino alla risoluzione.
- Non si compra sopra 0,97 o sotto 0,03: la commissione e il rischio di risoluzione mangiano tutto.
- Scadenza ≤ 90 giorni.
- Ordine ≤ 10% della profondità visibile entro 2 centesimi.
- Lista nera: mercati con criteri di risoluzione ambigui o già contestati.

## 3. Ipotesi testabili con dati gratuiti, e cosa evitare

### Crypto

Dati gratuiti:
- `data.binance.vision`: barre, aggTrades e funding storico di spot e perp, scaricabili in blocco;
- API pubbliche di Bybit e OKX;
- CoinGecko per la capitalizzazione storica (limiti stretti).

| Ipotesi | Perché è testabile | Rischio principale |
|---|---|---|
| **Trend a serie storica su BTC ed ETH** (es. sopra/sotto media lunga, con volatility targeting) | bassa rotazione, i costi pesano poco; c'è letteratura (momentum delle crypto) | pochi cicli indipendenti (3-4 dal 2015): potenza bassa, il 2017 e il 2020-21 dominano |
| **Carry del funding** (long spot / short perp quando il funding è alto) | il funding storico è pubblico e il rendimento è quasi meccanico | rischio controparte, affollamento, serve l'accesso ai perp (legalità) |
| **Momentum fra coin** (top-N per volume) | dati disponibili | sopravvivenza: servono le coin delistate e l'universo a quella data, altrimenti si ripete l'errore dei 15 titoli |

Da evitare:
- reversal a 1-5 giorni sulle altcoin (PULSE-ST l'ha già mostrato: il segnale c'è ed è più piccolo dei costi);
- combinazioni di indicatori tecnici (RSI/MACD/Bollinger);
- microstruttura del book senza colocation;
- sentiment dai social: dati non gratuiti, alto rischio di overfitting;
- "l'LLM prevede la direzione del prezzo".

### Mercati di previsione

Dati gratuiti:
- API pubbliche di Polymarket (Gamma per i mercati, CLOB per prezzi e storico);
- dati pubblici di Kalshi;
- dump completi di Manifold (denaro finto: utile per la meccanica, non per il vantaggio).

| Ipotesi | Perché è testabile | Rischio principale |
|---|---|---|
| **Calibrazione / favorite-longshot bias**: i prezzi bassi (2-15%) si avverano meno spesso di quanto dicono | basta lo storico dei mercati risolti a orizzonti fissi | rendimento piccolo per capitale bloccato; poche code catastrofiche cancellano molti piccoli guadagni |
| **Deriva prima della risoluzione** (es. ultimi 7 giorni) | snapshot a orizzonti fissi | spread largo vicino alla scadenza |
| **Comitato AI come previsore** contro il prezzo di mercato (Brier) | il comitato vota già a peso 0 | **solo in avanti**: su eventi passati l'LLM conosce l'esito, quindi un backtest è guardare il futuro |

Da evitare:
- reazione veloce alle notizie (i bot arrivano prima);
- arbitraggio fra piattaforme (non eseguibile dall'Italia e capitale bloccato su più conti);
- mercati illiquidi o con criteri di risoluzione vaghi.

## 4. Backtest e pre-registrazione per i mercati di previsione

- **Unità di osservazione: il mercato, non il giorno.** I mercati sullo stesso evento non sono indipendenti.
  Si raggruppano in cluster (evento o tema × mese di risoluzione) e l'inferenza usa un **bootstrap per cluster**.
- **Snapshot point-in-time** a orizzonti fissi prima della risoluzione: T−30, T−7 e T−1 giorni.
  - Prezzi: si usano ask e bid, non il prezzo medio né l'ultimo scambio.
  - Si scartano i mercati sotto una soglia di liquidità *a quel momento*.
- **Niente sopravvivenza**: si includono i mercati annullati, contestati e chiusi senza esito. Hanno una regola
  scritta prima: rimborso, oppure perdita del premio.
- **Divisione per data di risoluzione**, mai casuale: sviluppo, validazione e test bloccato, come PULSE-ST.
- **Soglia di campione**: se il test ha meno di 300 cluster indipendenti, l'esito vale solo come esplorativo. Si
  dichiara prima.
- **Cosa si pre-registra**:
  - filtri di selezione (categoria, liquidità, durata minima);
  - orizzonte di ingresso e regola di uscita (tenere fino alla risoluzione o no);
  - modello dei costi;
  - N varianti;
  - soglie: IC90 del rendimento medio per cluster > 0 dopo i costi, più un test sulla pendenza di calibrazione.
- **Fase in avanti già da subito**: il raccoglitore di snapshot va acceso prima di tutto il resto, perché lo
  storico è corto. Ogni mese in più di dati raccolti in avanti è dato pulito, mai visto.
- **Conteggio delle prove**: `trials.jsonl` separato per mercato, ma il documento finale riporta anche l'N
  complessivo della famiglia PULSE.

## 5. Struttura delle cartelle

```
pulse_mm/
  core/
    instrument.py      strumento, tipo di payoff, capabilities
    interfaces.py      MarketData, Execution, Account, CostModel (Protocol)
    costs.py           Cost con componenti separate, regola dello stress
    clock.py           sessione / 24x7 / fino a scadenza
    exposure.py        aggregazione per sottostante, worst_case_loss
    risk.py            gate globale + gate per tipo; si somma a desk/risk.py congelato
    modes.py           off / data / paper / live, conferme
  connectors/
    alpaca.py          adattatore sopra desk/broker.py, senza modificarlo
    crypto.py          ccxt (Binance/Bybit/Kraken), modalità sandbox
    polymarket.py      solo dati finché la legalità non è chiara
    shadow.py          riempimenti simulati sul book reale, comune a tutti
  data/
    crypto_fetch.py    data.binance.vision, funding storico, universo a quella data
    pm_snapshots.py    raccoglitore in avanti + ricostruzione point-in-time dallo storico
  backtest/
    bars.py            walk-forward a barre per spot/perp, con funding e liquidazione
    events.py          backtest a eventi per i binari, bootstrap per cluster
  research/
    crypto_trend/      una cartella per pre-registrazione, come pulse_st/
    pm_calibration/
  journal.py           tabelle nuove (venue, instrument_kind, cost_*), il diario esistente resta intatto
  tests/
docs/
  progetto-multimercato.md
  legale-<venue>.md    esito della verifica legale, data, fonti
  prereg-crypto-*.md
  prereg-pm-*.md
```

Dashboard:
- un selettore del mercato;
- lo stato di ogni connettore (`off` / `data` / `paper`, con data della verifica legale);
- costi scomposti per componente;
- per i binari, una vista della calibrazione al posto della curva di equity.

## 6. Piano a fasi

1. **Fase 0: legalità.** Federico scrive `docs/legale-<venue>.md` per ogni piattaforma. Un mercato senza
   documento resta `off`. Note da verificare, non conclusioni:
   - lo spot crypto da un prestatore autorizzato MiCA dovrebbe essere il caso più semplice;
   - i perpetual per i clienti retail ricadono nelle regole sui derivati;
   - in Italia le scommesse sono riservate ai concessionari ADM: Polymarket e Kalshi sono probabilmente esclusi,
     Betfair Exchange Italia andrebbe controllato.
2. **Fase 1: interfacce e adattatore Alpaca.** Nessun mercato nuovo. Criterio di uscita: impronta invariata,
   102 test verdi, la dashboard mostra le azioni passando da `pulse_mm`.
3. **Fase 2: solo dati.**
   - Si scarica lo storico crypto.
   - Si accende subito il raccoglitore di snapshot dei mercati di previsione.
   - Le date di sviluppo, validazione e test si fissano **prima** di guardare i dati.
4. **Fase 3: pre-registrazione crypto** (massimo 2 ipotesi: trend su BTC/ETH e, se i perp sono legali, carry del
   funding). Revisione con Grok, firma, una sola esecuzione.
5. **Fase 4: pre-registrazione dei mercati di previsione** (calibrazione / longshot) sul backtest a eventi.
6. **Fase 5: paper con riempimenti ombra**, solo per ciò che supera la fase 3 o 4. Il comitato AI registra le
   sue probabilità in avanti sui binari (peso 0, Brier contro il mercato).
7. **Fase 6: live.** Solo con verifica legale scritta, 12 mesi di paper che rispettano le regole e approvazione
   esplicita.

Aspettativa dichiarata: negativa, come per le azioni. Il valore del progetto è l'infrastruttura (un solo risk layer,
costi scomposti, pre-registrazione portabile) e una risposta pulita per ogni mercato.
