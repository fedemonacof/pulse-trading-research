# Ambiguità e scelte del secondo calcolo indipendente (PULSE-CT, ipotesi 1)

Calcolo: `checks/crypto_trend_independent.py`, scritto leggendo solo `docs/prereg-crypto-trend-v1.md` e i file
grezzi. Le sigle [A..] sono richiamate nei commenti del codice. Per ogni punto: cosa dice (o non dice) il
documento, la scelta fatta, e dove serve l'alternativa più probabile.

Parametri fissati dal compito e non dal documento: tariffa taker provvisoria 10 bp; capitale iniziale 100.000 USD;
fine della simulazione 2020-12-31.

## Aggiornamento dopo "Ambiguità risolte dopo il primo confronto" (revisione 2)

Il codice è stato riallineato al testo nuovo. Legenda usata sotto: **[CAMBIATA]** = la scelta di prima è stata
sostituita; **[CONFERMATA]** = il documento ora scrive la stessa scelta; **[NUOVA]** = ambiguità rimasta aperta.

- **Cambiate:**
  - A19: taglia dello scambio, ora quantità = peso obiettivo × capitale della quota all'apertura / apertura, con i
    costi pagati dopo. Non è più la forma chiusa.
  - A27: di conseguenza weight_after non coincide più col peso obiettivo.
  - A16: il tetto di leva ora forza uno scambio quando il peso attuale supera 1 dopo il riallineamento (punto 3).
  - A14: la prima decisione con m definito non è più un cambio di livello (punto 4).
- **Confermate:** A5, A7, A9, A10, A11, A12, A13, A14 (confronto con l'ultima decisione, anche senza scambio),
  A15 (riallineamento anche senza la candela del lunedì), A16 (valutazione alla chiusura della domenica, solo
  cassa), A17, A21, A36.
- **Nuova: R3b.** Resta aperto quando si applica il controllo del tetto di leva.
- **Righe prodotte dopo l'aggiornamento:**
  - V3: 135 scambi, 103 nello sviluppo;
  - benchmark: 94 scambi (prima 93), 63 nello sviluppo;
  - equity: 1675 righe ciascuna.

## Dati e calendario (sezioni 3 e 5)

- **[A1] Inizio dei dati e della simulazione (sez. 3, 5).** Il riscaldamento parte "dal 2016-06-01". Si leggono
  solo le candele dal 2016-06-01 al 2020-12-31 per entrambi gli asset, anche se BTC ha dati dal 2016-01-01 ed ETH
  dal 2016-05-18. La simulazione (capitale, curva di equity) parte il 2016-06-01. Alternativa: usare i dati BTC
  precedenti per anticipare il segnale di BTC; scartata perché il documento fissa un'unica data di inizio.
- **[A2] Blocco delle date (sez. 3).** Se un file contenesse date dal 2021-01-01 in poi, il calcolo si ferma
  (non le scarta in silenzio). I file attuali finiscono il 2020-12-31.
- **[A3] Capitale iniziale (sez. 1.3).** 50.000 USD a BTC e 50.000 USD a ETH, tutto in liquidità il 2016-06-01.
  Il primo riallineamento al 50% è comunque il primo lunedì di giugno (2016-06-06), dove non cambia nulla.
- **[A4] Controllo delle barre impossibili (sez. 5).** Applicato solo al periodo usato (2016-06-01 → 2020-12-31).
  "Fuori da [minimo, massimo] di oltre l'1%" letto come apertura o chiusura < 0,99 × minimo oppure > 1,01 ×
  massimo. Il salto 3× / 1/3 si misura fra chiusure di candele consecutive presenti (se manca un giorno, fra le
  due chiusure disponibili). Con una barra impossibile il programma si ferma. Nessuna barra impossibile trovata.
- **[A5] Candele mancanti (sez. 5).** Il calendario è giornaliero completo. Un giorno mancante: la chiusura si
  riporta in avanti (posizione valutata all'ultima chiusura nota); il rendimento di quel giorno vale 0 nella
  volatilità e i ritardi h si contano in giorni di calendario. Le regole "più di 3 giorni consecutivi" e
  "copertura sotto il 99%" non cambiano il calcolo (sono regole di interpretazione dell'esito) e non sono
  implementate come segnalazione. Nel periodo usato non manca nessuna candela, quindi queste scelte non hanno
  effetto sui numeri prodotti.
- **[A30] Duplicati nei file grezzi.** Righe con lo stesso timestamp: si tiene la prima incontrata nell'ordine del
  file. Nei file attuali non ci sono duplicati.

## Segnale (sezione 1.1)

- **[A6] Rendimento a h giorni.** r_h = chiusura(domenica) / chiusura(domenica − h giorni) − 1, con h in giorni di
  calendario (equivalenti a candele, perché le crypto quotano 7 giorni su 7 e i dati sono completi). Quindi s₂₅₂
  richiede 253 chiusure.
- **[A7] Segno di un rendimento esattamente nullo.** sign(0) = 0 (convenzione numpy). In quel caso m potrebbe
  valere 0 o ±2/3, livelli che il documento non prevede ("il peso può valere 0, 1/3 o 1"). Alternativa: trattare 0
  come −1 (flat). Con prezzi a due decimali è un caso rarissimo.
- **[A8] Momento del segnale.** La decisione del lunedì D usa le chiusure fino alla candela della domenica D−1
  inclusa (sez. 1.4). Nessun dato del lunedì entra nel segnale o nella volatilità.
- **[A9] Prima che il segnale esista (sez. 3, 1).** Il documento non dice cosa fare durante il riscaldamento. Se
  m o σ₆₃ non sono calcolabili il peso obiettivo è indefinito: nessuno scambio, la quota resta in liquidità.
  - V3 inizia a decidere al primo lunedì con s₂₅₂ disponibile (primo scambio 2017-02-13).
  - Il benchmark (m = 1 sempre) ha bisogno solo di σ₆₃, quindi inizia prima, al primo lunedì con 63 rendimenti
    (primo scambio 2016-08-08). Alternativa importante: far partire il benchmark insieme a V3, quando anche s₂₅₂ è
    disponibile. Per il periodo di sviluppo (dal 2018) la differenza resta solo nel percorso delle quote e nella
    deriva fra BTC ed ETH, che il riallineamento mensile riassorbe in parte.
- **[A10] Rendimenti per la volatilità.** Rendimenti semplici giornalieri chiusura/chiusura − 1 (non logaritmici).
- **[A11] Stimatore di σ₆₃.** Deviazione standard campionaria (ddof = 1, con media stimata, non zero) degli ultimi
  63 rendimenti giornalieri fino alla domenica inclusa (servono 64 chiusure), × √365. Alternative: ddof = 0,
  media zero, rendimenti log, 63 chiusure invece di 63 rendimenti.

## Peso, soglia e decisione (sezione 1.2, 1.4, revisione 1)

- **Peso obiettivo.** V3: max(0, m) × min(1, 0,40 / σ₆₃). Benchmark: min(1, 0,40 / σ₆₃). Nessun arrotondamento.
- **[A12] "Peso attuale" al momento della decisione.** Il documento dice "ricalcolato a ogni chiusura". Scelta:
  peso attuale = valore della posizione alla chiusura della domenica / capitale della quota alla chiusura della
  domenica, calcolato **dopo** l'eventuale riallineamento del primo lunedì. Alternativa: valutarlo all'apertura del
  lunedì (prezzo di esecuzione).
- **[A13] Soglia di 10 punti.** "Almeno 10 punti" letto come |peso obiettivo − peso attuale| ≥ 0,10, confine
  incluso (con tolleranza numerica 1e-12).
- **[A14] Cambio di livello di m "rispetto alla decisione precedente".** Si confronta m di oggi con m del lunedì
  precedente in cui c'è stata una decisione per quell'asset, **anche se quella decisione non ha prodotto uno
  scambio** [CONFERMATA]. Alternativa: confrontare con m dell'ultimo scambio eseguito.
  - **[CAMBIATA, R4]** Prima: alla prima decisione con m definito il cambio di livello contava come avvenuto. Ora:
    non conta, perché non c'è un livello precedente, e si scambia solo se lo scarto supera la soglia. Il cambio di livello si misura su m, non su
  max(0, m): un passaggio da −1 a −1/3 è un cambio di livello, ma il peso obiettivo resta 0 e con posizione nulla
  non produce uno scambio (vedi [A20]). Per il benchmark m = 1 sempre, quindi scatta solo la soglia.
- **[A36] Scambio forzato dal cambio di livello.** Quando scatta per il cambio di livello, si porta il peso
  esattamente all'obiettivo, anche se la differenza è sotto i 10 punti.

## Riallineamento delle quote (sezione 1.3, revisione 1)

- **[A15] Primo lunedì del mese.** Lunedì con giorno del mese ≤ 7. Il riallineamento avviene anche nei mesi in
  cui non c'è ancora segnale, e anche se manca la candela del lunedì per un asset.
- **[A16] Come si riallinea.** Alle 00:00 UTC del primo lunedì, prima della decisione, con le posizioni valutate
  alla chiusura della domenica: capitale totale = liquidità + posizioni; ogni quota viene riportata al 50% del
  totale spostando **solo liquidità** fra le quote. Non è uno scambio e non ha costi. Alternativa: valutare il
  totale all'apertura del lunedì.
  - Conseguenza: se una quota ha una posizione che vale più del 50% del totale, la sua liquidità diventa negativa
    e il suo peso supera 1 (nel benchmark succede in 3 riallineamenti). Il documento dice che il riallineamento da
    solo non forza uno scambio sotto la soglia, quindi se la differenza dall'obiettivo è sotto i 10 punti il peso
    resta sopra 1 fino alla decisione seguente (5 settimane in tutto nel benchmark, 0 in V3). La liquidità totale
    del portafoglio non è mai negativa. Il "tetto di leva 1" è applicato solo al peso obiettivo, non al peso che
    deriva dal riallineamento. Alternativa: forzare uno scambio quando il peso supera 1.
  - **[CAMBIATA, R3]** Ora: se dopo il riallineamento il peso attuale, valutato alla chiusura della domenica,
    supera 1 (con tolleranza 1e-12), si scambia verso il peso obiettivo anche sotto la soglia.
  - **[NUOVA, R3b] Quando si applica il controllo.** Il testo dice "dopo il riallineamento". Scelta: il controllo
    vale solo nei lunedì di riallineamento (primo lunedì del mese).
    - Motivo: con i costi pagati dopo (R2), uno scambio verso il peso 1 lascia il peso un poco sopra 1 (cassa della
      quota negativa per l'importo dei costi). Se il controllo valesse ogni settimana, produrrebbe micro-scambi
      ripetuti finché l'obiettivo resta 1.
    - Alternativa, attivabile con `LEVERAGE_CHECK_ONLY_ON_REALIGN = False`: controllo a ogni decisione
      settimanale.
    - Effetto misurato sui conteggi: V3 invariato. Il benchmark passa da 94 a 100 scambi, tutti i 6 in più prima
      del 2018. Lo sviluppo resta a 63 scambi in entrambi i casi.
    - Il controllo usa "peso > 1": un peso uguale a 1 non lo fa scattare.

## Esecuzione e costi (sezione 1.4, sezione 6)

- **[A17] Candela del lunedì mancante.** Per quell'asset quella settimana non si decide e non si scambia; m di
  quella settimana non diventa il riferimento per il cambio di livello. Nel periodo usato non manca nessuna
  candela, quindi non ha effetto.
- **[A18] Prezzo e costi.** Esecuzione al prezzo di apertura della candela del lunedì. Spread e slippage non
  spostano il prezzo: sono costi in USD in proporzione al nozionale scambiato, come la tariffa. Nozionale =
  |variazione del valore della posizione| all'apertura.
- **[A21] Raddoppio prima del 2025-01-01.** Si raddoppiano tutte e tre le componenti (tariffa, metà spread,
  slippage), in base alla data dello scambio. Sullo sviluppo: 20 + 10 + 10 = 40 bp per lato. Alternativa: raddoppiare
  solo spread e slippage.
- **[A22] Tariffa taker.** Provvisoria a 10 bp (il documento la lascerà fissare dal listino OKX Europe alla firma).
- **[A19] [CAMBIATA, R2] Dimensione dello scambio.**
  - Ora: quantità nuova = peso obiettivo × capitale della quota all'apertura del lunedì / prezzo di apertura,
    cioè P₁ = w × S₀. Costi pagati dopo, dalla cassa della quota.
  - Il peso dopo lo scambio è leggermente diverso dall'obiettivo: sopra in acquisto, sotto in vendita.
  - Con w = 1 la cassa della quota diventa negativa per l'importo dei costi, quindi il peso supera di poco 1. Nel
    benchmark succede in 3 scambi; vedi R3b.
  - Testo precedente, ora superato: il capitale della quota è rivalutato all'apertura
  del lunedì. La taglia è risolta in forma chiusa perché, **dopo aver pagato i costi**, il peso sia esattamente
  quello obiettivo: in acquisto P₁ = w (S₀ + c P₀) / (1 + w c), in vendita P₁ = w (S₀ − c P₀) / (1 − w c), con
  P₀ e P₁ valore della posizione prima e dopo, S₀ capitale della quota, c costo per unità di nozionale. Con w = 1 la
  liquidità della quota va esattamente a zero (niente leva). Alternativa più semplice: P₁ = w × S₀ e costi pagati
  dopo; il peso dopo lo scambio risulterebbe più alto fino a circa c × nozionale/S₀, cioè fino a ~0,4 punti
  sullo sviluppo, oltre la tolleranza del confronto (0,1 punti). Punto da allineare per primo se i pesi non
  coincidono.
- **[A27] Definizione di weight_after nel file degli scambi.** Valore della posizione / capitale della quota dopo
  lo scambio (costi già pagati), entrambi al prezzo di esecuzione. La definizione è invariata, ma dopo R2 il
  valore non coincide più col peso obiettivo **[CAMBIATA nell'effetto]**.
- **[A32] Chi paga i costi.** La liquidità della quota dell'asset scambiato.
- **[A20] Scambi trascurabili.** Se il nozionale è ≤ 1e-9 × capitale della quota non si esegue nulla e non si
  registra uno scambio (per esempio cambio di livello di m fra due valori negativi con posizione già nulla).
- **[A31] Arrotondamenti.** Nessuno: quantità frazionarie, nessun lotto minimo, nessun importo minimo d'ordine.

## Valutazione giornaliera e uscite

- **[A26] Equity giornaliera.** Equity netta alla chiusura di ogni giorno dal 2016-06-01 al 2020-12-31 =
  liquidità totale + Σ quantità × chiusura. Il lunedì include gli scambi eseguiti all'apertura e i loro costi.
  Fino al primo scambio vale 100.000.
- **Liquidità (sez. 1.5).** Rendimento 0%.
- **Calcolo vettoriale.** Segnali, volatilità, pesi obiettivo, calendario dei lunedì, riallineamenti, moltiplicatore
  dei costi ed equity giornaliera sono vettoriali (pandas/numpy). C'è un ciclo solo sui lunedì (e sui due asset),
  perché la soglia dipende dal peso attuale e quindi dal percorso.

## Controlli fatti senza guardare metriche di rendimento

- Impronte SHA-256 dei due file grezzi coincidono con `manifest.json`.
- Nessuna candela mancante e nessuna barra impossibile dal 2016-06-01 al 2020-12-31.
- Numero di scambi nel periodo di sviluppo (2018-01-01 → 2020-12-31): V3 103, benchmark 63, uguali ai conteggi
  scritti nella revisione 1. Somma delle componenti di costo = costo totale (scarto < 1e-9 USD).
