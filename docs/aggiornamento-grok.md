Ciao Grok, ecco l'aggiornamento sul tuo piano per PULSE: congelamento, test 2005-2019, universo storico e calibrazione.

**1. Fatto: codice congelato.** Comitato AI a peso 0. L'impronta SHA-256 dei 9 file che decidono i trade è
registrata e un comando la controlla. Ogni test si rifiuta di girare se il codice è cambiato.

**2. Fatto: test pre-registrato 2005-2019** (walk-forward, costi 1 + 5 bp, esecuzione all'apertura del giorno
dopo, bootstrap a blocchi di 21 giorni con 5.000 ricampionamenti, DSR con N = 8).
- A, 100% SPY: Sharpe 0,56, max DD −55,2%.
- C, core + satellite: Sharpe 0,61. ΔSharpe IC90% [−0,01, +0,11].
- E, SPY con filtro a 200 giorni: Sharpe 0,80, max DD −20,9%.
- DSR del satellite: 0,97.

Decisioni secondo le regole fissate prima: il satellite passa in ombra (conto virtuale, trade registrati) e il
filtro a 200 giorni sul core viene adottato. Regola per riattivare il satellite in avanti: almeno 12 mesi, almeno
100 trade in ombra, P&L positivo, limite inferiore di ΔSharpe IC90% > 0, codice invariato.

**3. Fatto: universo storico S&P 500**, con una seconda pre-registrazione.
- Composizione point-in-time dal CSV fja05680/sp500. Prezzi da Yahoo, con copertura del 68,4% dei giorni-membro
  (i delistati mancano).
- Entrate solo se il titolo è nell'indice quel giorno. Uscita forzata al delisting.
- È una sottoclasse del backtester congelato. Un test dimostra che dà risultati identici quando tutti i titoli
  sono sempre ammessi.
- Prima esecuzione non valida: la serie Yahoo di GR aveva aperture impossibili (448 $ con chiusura a 57 $).
  L'ho dichiarata non valida e conservata. Nella v2, pre-registrata dopo, si escludono le serie con barre
  impossibili: CPWR, EP, FNMA, GR.

Risultati v2 (satellite da solo, 2005-2019):
- 15 titoli scelti oggi: Sharpe 0,88.
- 100 universi da 15 titoli estratti fra i membri del 2005: percentili 10/50/90 = 0,25 / 0,41 / 0,62. Lo 0%
  supera 0,88 → **bias di selezione confermato, il DSR di 0,97 è ritirato.**
- S&P 500 storico: CAGR +1,7%, Sharpe 0,39 (SPY 0,56), max DD −14,4%, DSR 0,47 con N = 10 → **nessuna evidenza.**
  È anche ottimistico, perché mancano i prezzi dei falliti.

**4. Non fatto: calibrazione della confidenza.** Il tuo piano la condizionava a un segnale con informazione, e il
segnale non c'è.

**Stato attuale:**
- Conto vero: core SPY con filtro a 200 giorni.
- Satellite: in ombra sui 15 titoli, per raccogliere evidenza in avanti.
- Scheduler spento. Ancora nessuna chiave inserita.

**Domande per te:**
1. Ha senso continuare l'ombra sui 15 titoli, o conviene un universo diverso, scelto con una regola
   point-in-time e senza senno di poi?
2. Il filtro a 200 giorni è l'unica cosa che ha retto. Andrebbe validato fuori dagli USA (MSCI World, altri indici)
   prima di affidargli soldi veri?
3. Esistono fonti gratuite di prezzi dei delistati per alzare la copertura sopra il 90%?
4. Va bene fermarsi qui con la ricerca sulle strategie, accendere il paper trading in avanti e non toccare più il
   codice per 12 mesi?
