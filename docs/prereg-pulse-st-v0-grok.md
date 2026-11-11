# PULSE-ST — Pre-registrazione filone a breve termine (1-2 giorni) — BOZZA v0

> **Disclaimer:** questa è una bozza scritta da Grok come proposta da confrontare con la tua versione. Confrontiamoci e vediamo quale può essere la migliore (o uniamo le parti migliori di entrambe) **prima** di congelarla. Nulla di questo documento è valido finché non viene firmato con data e impronta SHA-256, e prima della firma non si guardano dati di test. Non è consulenza finanziaria; tutto resta in paper.

---

## 0. Scopo e domanda

**Domanda principale:** un segnale cross-sectional a 1-2 giorni, market neutral, sulle large cap USA ha rendimento positivo **dopo costi realistici**, fuori campione?

**Ipotesi nulla H0:** Sharpe netto ≤ 0.
**Aspettativa dichiarata:** improbabile che passi. La letteratura indica che i reversal di breve sulle large cap si sono molto attenuati e spesso spariscono dopo i costi.

**Cosa NON è:** non è un'estensione di PULSE swing. Codice, diario, impronta e conteggio delle varianti sono separati (`pulse_st/`).

---

## 1. Dati

| Elemento | Scelta |
|---|---|
| Universo | Membri S&P 500 point-in-time (CSV fja05680/sp500), filtrati ogni mese ai **primi 200 per volume in dollari a 60 giorni**, calcolato solo con dati disponibili a quella data |
| Prezzi | Giornalieri OHLC rettificati (Yahoo), con le stesse esclusioni delle barre impossibili della v2 (CPWR, EP, FNMA, GR) più la regola automatica: si escludono le barre con apertura fuori da [0,5×, 2×] la chiusura precedente senza un evento societario |
| Settori | Classificazione GICS a livello di settore, point-in-time se disponibile; altrimenti quella attuale, **dichiarata come distorsione** |
| Copertura | Si riporta la percentuale di giorni-membro con prezzo; il test vale solo con copertura ≥ 65% (attuale 68,4%) e si ripete con WRDS/CRSP quando arriva l'accesso |
| Calendario utili | Non usato nella v0 (niente PEAD) |

**Distorsioni note e dichiarate:** mancano i delistati, quindi il test è ottimistico; i settori potrebbero non essere point-in-time.

---

## 2. Campioni (scelti ora, mai modificati)

| Campione | Periodo | Uso |
|---|---|---|
| Sviluppo | 2005-01 → 2014-12 | Scegliere la parametrizzazione dentro le famiglie ammesse |
| Validazione | 2015-01 → 2019-12 | Scegliere **una** variante finale per famiglia; massimo 1 esecuzione per variante |
| Test (bloccato) | 2020-01 → 2026-10 | **Una sola esecuzione**, solo per le varianti promosse; nessuna modifica dopo |
| In avanti | Dalla data di firma, 12 mesi minimo | Paper e ombra, codice congelato |

Il test resta inaccessibile via codice (`assert date < TEST_START`) finché la validazione non è firmata.

---

## 3. Famiglie di segnali ammesse (N massimo = 12)

Ogni famiglia ha al massimo **3 parametrizzazioni fissate qui**. Non se ne aggiungono altre. **N totale = 12**, contato in `trials.jsonl`.

### F1 — Reversal di breve rispetto al settore (principale)
- Segnale: −(rendimento a k giorni del titolo − rendimento medio del suo settore), con k ∈ {1, 3, 5}.
- Ordinamento cross-sectional ogni giorno: long sul decile più basso, short sul decile più alto.
- Varianti: k=1, k=3, k=5 → **3 prove**.

### F2 — Reversal condizionato al volume (movimenti "senza notizie")
- Come F1 con k=1, ma solo per i titoli con volume del giorno < 1,0× la media a 20 giorni (l'idea è che i movimenti senza volume anomalo rientrino di più).
- Varianti: soglia di volume ∈ {0,8×, 1,0×, 1,5×} → **3 prove**.

### F3 — RSI(2) cross-sectional (in stile Connors, versione market neutral)
- Long se RSI(2) < 10 e prezzo > SMA200; short se RSI(2) > 90 e prezzo < SMA200.
- Gambe bilanciate in dollari ogni giorno con i segnali disponibili; nessun trade se una gamba ha meno di 5 titoli.
- Varianti: soglie (10/90), (5/95), (15/85) → **3 prove**.

### F4 — Gap di apertura contro il settore (esplorativo)
- Segnale: −(gap di apertura del titolo − gap medio del settore), ingresso in apertura e uscita in chiusura il giorno dopo.
- Varianti: solo i gap oltre {1σ, 2σ, nessun filtro} della volatilità a 20 giorni → **3 prove**.

**Esclusi dalla v0, con motivo:** overnight contro intraday (costi doppi ogni giorno, usato solo come informazione sull'orario di esecuzione), PEAD (serve un calendario utili point-in-time, orizzonte più lungo), ribilanciamento degli ETF a leva (servono dati intraday).

---

## 4. Costruzione del portafoglio

- **Market neutral:** gambe long e short uguali in dollari; **neutralità di beta** verso SPY (beta a 60 giorni, rapporto di copertura ricalcolato ogni giorno) come variante di robustezza, **non** come prova in più.
- **Neutralità settoriale:** esposizione netta per settore ≤ 5% del capitale lordo.
- **Pesi:** uguali dentro ogni gamba; massimo 2% del capitale lordo per titolo.
- **Lordo:** 100% long + 100% short (leva lorda 2×, in paper).
- **Orizzonte:** uscita dopo h giorni, con h=1 per F1/F2/F4 e h=2 per F3; nessuno stop intraday nel backtest (gli stop creano day trade e dipendenze dal percorso dei prezzi che con dati giornalieri non si possono modellare).
- **Esecuzione nel backtest:** segnale calcolato alla chiusura t, ingresso all'**apertura t+1**, uscita all'apertura t+1+h. Variante di robustezza: ingresso alla chiusura t+1.

---

## 5. Modello di costi

| Voce | Caso base | Sensibilità |
|---|---|---|
| Slippage + metà spread, per lato | **8 bp** | 2 / 5 / 10 / 20 bp |
| Scenario di stress | Costo doppio nei giorni con VIX > 30, o con volatilità realizzata di SPY a 20 giorni sopra il suo 90° percentile | — |
| Commissioni | 0 (Alpaca) | — |
| Commissioni regolamentari SEC + FINRA TAF sulle vendite | Incluse alle aliquote del periodo, approssimate | — |
| Prestito per gli short | **0,5% annuo** | 0,25% / 1% / 3% |
| Titoli difficili da prendere in prestito | Si escludono dagli short i titoli sotto il 20° percentile di capitalizzazione dell'universo | — |
| Liquidità | Rendimento 0 sulla liquidità e sul ricavato degli short (prudente) | Tasso T-bill come variante |

**Regola di robustezza ai costi:** una variante è valida solo se lo Sharpe netto resta > 0 anche a **10 bp per lato**.

---

## 6. Metriche e regole di decisione

### 6.1 In validazione (2015-2019), per ogni variante
- Sharpe netto annualizzato, t-stat di Newey-West (12 lag) sui rendimenti giornalieri, rotazione giornaliera, holding medio, beta verso SPY, max drawdown, percentuale di giorni con tutte e due le gambe piene.
- **Promossa al test** solo la variante migliore per famiglia, e solo se: Sharpe netto > 0,5, t > 2, beta |β| < 0,2, Sharpe a 10 bp > 0.

### 6.2 In test (2020-2026), una sola esecuzione
- **Passa** se: Sharpe netto > 0 con IC90% da bootstrap a blocchi di 21 giorni (5.000 ricampionamenti) e limite inferiore > 0, **e** DSR ≥ 0,95 con **N = 12** (tutte le prove, anche quelle non promosse), **e** Sharpe a 10 bp > 0.
- Se passano più famiglie, si riporta anche la combinazione a pesi uguali, **senza** riottimizzarla.

### 6.3 In avanti (paper, minimo 12 mesi)
- Potenza dichiarata: bassa (stessa logica del filone swing).
- Controllo disastri a 6 mesi: si chiude se il limite superiore dell'IC90% dello Sharpe è < 0.
- Ombra contro backtest ogni mese: entrate abbinate ≥ 80%, |Δpnl| medio ≤ 30 bp per trade; due mesi falliti di fila → indagare.
- Si registrano i rifiuti di prestito di Alpaca e gli ordini non eseguiti.

---

## 7. Controllo delle prove

- `trials.jsonl`: una riga per ogni esecuzione su sviluppo, validazione o test, con data, impronta SHA-256 del codice, famiglia, parametri e metriche. **N = numero di righe uniche famiglia+parametri.**
- Se N supera 12, il test non vale: serve una nuova pre-registrazione con un nuovo periodo di test.
- I bug si correggono ripartendo dallo sviluppo, segnalati nel registro degli interventi; il test non si riesegue mai dopo la sua unica esecuzione.

---

## 8. Vincoli pratici (Alpaca, paper)

- Conto margine paper per gli short; si registrano i titoli "easy to borrow" ogni giorno.
- Holding ≥ 1 notte, quindi nessun day trade intenzionale. Si registra ogni chiusura accidentale nello stesso giorno, che conta per la regola PDT.
- Ordini market-on-open o limit all'apertura, se supportati; altrimenti market nei primi minuti, con lo slippage registrato rispetto all'apertura ufficiale.
- Le esecuzioni paper di Alpaca sono ottimistiche: il confronto col backtest usa i **prezzi del modello di costi**, non quelli eseguiti in paper.
- Conto live da residente italiano non verificato, quindi **fuori dallo scopo**.

---

## 9. Distorsioni dichiarate (si favoriscono a vicenda o no)

| Distorsione | Effetto |
|---|---|
| Delistati mancanti | Favorisce la strategia (soprattutto la gamba long sui titoli crollati) |
| Settori non point-in-time | Incerto |
| Costo di prestito costante | Favorisce gli short nei periodi di stress |
| Nessun impatto di mercato oltre allo slippage fisso | Favorisce la strategia, poco rilevante per titoli molto liquidi e capitale piccolo |
| Liquidità a 0 | Penalizza la strategia |

---

## 10. Firma

- Data di firma: ____
- SHA-256 di questo documento: ____
- SHA-256 del codice di `pulse_st/` al congelamento: ____
- Versione scelta dopo il confronto (questa / la tua / fusa): ____
