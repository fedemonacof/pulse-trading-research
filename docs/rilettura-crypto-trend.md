# PULSE-CT ipotesi 1: pacchetto di rilettura prima della firma (2026-11-11)

Per Grok. Il documento non è firmato. Il dry-run del criterio 7 parte il 2026-11-13 e finisce fra il 2026-12-10 e il
2026-12-13. Questa rilettura si fa adesso, così a dicembre manca solo il resoconto del dry-run.

Tutto il codice è su GitHub, ramo `main`:
<https://github.com/fedemonacof/pulse-trading-research/tree/main>

## Cosa leggere, in ordine

| # | File | Cosa controllare |
|---|---|---|
| 1 | [docs/prereg-crypto-trend-v1.md](https://github.com/fedemonacof/pulse-trading-research/blob/main/docs/prereg-crypto-trend-v1.md) | La regola, gli esiti e le revisioni 1, 2, 3 e 3b. È il documento che si firma |
| 2 | [pulse_mm/research/crypto_trend/config.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/config.py) | Ogni numero deve coincidere con il documento |
| 3 | [strategy.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/strategy.py) | Segnale, pesi, decisione del lunedì, riallineamento, costi. Il punto dove un errore pesa di più |
| 4 | [stats.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/stats.py) | Sharpe, drawdown positivo, bootstrap appaiato, regola degli esiti, Deflated Sharpe con N = 4 |
| 5 | [trials.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/trials.py) e [data.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/data.py) | Impronta, blocco delle date in base allo stato, impronte dei dati |
| 6 | [__main__.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/__main__.py) | `val` e `test`: una sola esecuzione, firma obbligatoria, robustezze riportate senza soglie |
| 7 | [fx.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/fx.py) | Conversione in EUR |
| 7b | [robust.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/robust.py) | Revisione 4: controllo della leva, drawdown su 63 giorni, T-bill |
| 8 | [dryrun.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/pulse_mm/research/crypto_trend/dryrun.py) | Calendario, giorni validi, misure, book, giorni agitati |
| 9 | [checks/crypto_trend_independent.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/checks/crypto_trend_independent.py) e [checks/out/ambiguities.md](https://github.com/fedemonacof/pulse-trading-research/blob/main/checks/out/ambiguities.md) | Il secondo calcolo e le sue scelte |
| 10 | [tests/test_crypto_trend.py](https://github.com/fedemonacof/pulse-trading-research/blob/main/tests/test_crypto_trend.py) | Cosa è coperto dai test e cosa no |

Output dei controlli, senza metriche di rendimento:
[docs/evidenze/controlli-crypto-trend-2026-11-11.txt](https://github.com/fedemonacof/pulse-trading-research/blob/main/docs/evidenze/controlli-crypto-trend-2026-11-11.txt).
Lo stato dei criteri è in
[docs/controlli-crypto-trend.md](https://github.com/fedemonacof/pulse-trading-research/blob/main/docs/controlli-crypto-trend.md).

## Stato dei criteri

| # | Criterio | Stato |
|---|---|---|
| 1 | Impronta e `trials.jsonl` | fatto |
| 2 | Blocco delle date, flusso dal vivo separato | fatto, con test |
| 3 | Copertura di Coinbase | fatto: 100% dei giorni dal 2016-06-01 al 2020-12-31 |
| 4 | Registro dei costi | fatto: errore circa 1e-11 bp |
| 5 | Turnover ≤ 10 | fatto: 4,3 (revisione 1) |
| 6 | Secondo calcolo e lookahead | fatto: 103/103 e 63/63, scarti circa 1e-9 |
| 7 | Dry-run di 28 giorni | parte il 2026-11-13, piano `ef309217960d3c14` |
| 8 | Tariffa taker OKX Europe | fatto: 10 bp, da rileggere il giorno della firma |

## Esito della rilettura (2026-11-11)

Grok è d'accordo su tutti e sei i punti. Ha chiesto due aggiunte, entrambe fatte nella revisione 4: un controllo che
blocca il resoconto se la leva supera 1,01 in qualunque giorno, e la liquidità al T-bill a 3 mesi come robustezza.
Ha suggerito anche le robustezze del drawdown (finestre di 63 giorni, drawdown medio, durata media sotto il
massimo). Precisazione mia: il T-bill è un tetto di quello che la liquidità poteva rendere, non una stima.

## I miei dubbi, su cui vorrei il tuo parere

Non li ho risolti da solo perché toccano scelte già scritte nel documento. Cambiarle ora è ancora possibile, ma solo
con una revisione registrata e senza aver visto risultati.

1. **Potenza del test sul drawdown.**
   - La validazione dura 2 anni, cioè 730 giorni e circa 35 blocchi da 21 giorni.
   - Il drawdown massimo dipende quasi tutto da un solo episodio, il crollo del 2022. Il bootstrap a blocchi lo
     spezza e lo ricompone, quindi l'IC90 di ΔDD rischia di essere molto largo.
   - Mi aspetto che "non concludente" sia l'esito più probabile anche se il filtro funziona.
   - Non propongo di cambiare la regola: propongo di scrivere questa aspettativa nel documento prima della firma,
     così un "non concludente" non sembra una sorpresa.
   - Tu cosa ne pensi? Vale la pena aggiungere come robustezza, senza soglie, il drawdown medio dei blocchi, che è
     meno legato a un solo episodio?
2. **Liquidità allo 0%.**
   - La strategia sta in liquidità molto più del benchmark, quindi lo 0% la penalizza.
   - È una scelta prudente e la tengo. Però nel 2023-2026 le stablecoin rendevano il 4-5% annuo, quindi il confronto
     sul test sarà conservativo.
   - Lo dichiarerei come limite che va contro la strategia.
3. **Costi raddoppiati prima del 2025.**
   - Tutta la validazione (2021-2022) usa 20 + 10 + 10 = 40 bp per lato.
   - Il turnover è basso (4,3), quindi il peso è contenuto. È comunque una scelta convenzionale, e "non concludente"
     o "fallisce" potrebbero dipendere in parte da lì.
   - La sensibilità × 3 c'è già. Non aggiungerei altro.
4. **Leva residua dello 0,4% (punto 3b).**
   - Dopo un acquisto a peso 1, i costi pagati dopo lasciano un peso leggermente sopra 1 fino al riallineamento
     successivo.
   - Mi sembra trascurabile, ma è una deviazione dalla regola "massimo 1". Va bene così o preferisci che il tetto si
     controlli ogni lunedì? Cambierebbe la regola e il secondo calcolo andrebbe riallineato.
5. **Cambio in EUR.**
   - Il fixing BCE è delle 14:15 CET, mentre la chiusura crypto è alle 24:00 UTC: c'è uno sfasamento di circa 11 ore.
   - Per una robustezza senza soglie mi sembra accettabile, e lo dichiarerei.
6. **Indipendenza del secondo calcolo.**
   - La sessione separata ha visto i conteggi 103 e 63 nel documento.
   - È dichiarato. Se pensi che basti a indebolire il criterio 6, l'alternativa è rifarlo con una copia del documento
     senza quei numeri.

## Cosa non è nel pacchetto

- Nessun rendimento, Sharpe, drawdown o CAGR sullo sviluppo: non è mai stato calcolato.
- Le curve di equity del secondo calcolo restano solo in locale (`checks/out/*.csv`, fuori da git).
- Il resoconto del dry-run arriva a dicembre.
