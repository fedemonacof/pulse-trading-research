# PULSE-CT ipotesi 1: pacchetto di rilettura prima della firma (2026-11-11)

Per Grok. Il documento non è firmato. Il dry-run del criterio 7 parte il 2026-11-13 e finisce fra il 2026-12-10 e il
2026-12-13. Questa rilettura si fa adesso, così a dicembre manca solo il resoconto del dry-run.

Tutto il codice è su GitHub, ramo `main`:
<https://github.com/fedemonacof/pulse-trading-research/tree/main>

## Cosa leggere, in ordine

| # | File | Cosa controllare |
|---|---|---|
| 1 | [docs/prereg-crypto-trend-v1.md](https://github.com/fedemonacof/pulse-trading-research/blob/main/docs/prereg-crypto-trend-v1.md) | La regola, gli esiti e le revisioni 1, 2, 3, 3b, 4 e 5. È il documento che si firma |
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

**Prima lettura.** Grok è d'accordo su tutti e sei i dubbi che avevo sollevato. Sono **chiusi** dalla revisione 4
della pre-registrazione:

| # | Dubbio | Come si è chiuso |
|---|---|---|
| 1 | Potenza del test sul drawdown | aspettativa "non concludente" scritta prima della firma; robustezze del drawdown su finestre di 63 giorni, drawdown medio, durata sotto il massimo |
| 2 | Liquidità allo 0% | resta il caso base, dichiarato contro la strategia; robustezza con il T-bill a 3 mesi, trattato come tetto |
| 3 | Costi raddoppiati prima del 2025 | restano, dichiarati |
| 4 | Leva residua dello 0,4% | resta dichiarata; in più il resoconto si blocca se un peso supera 1,01 in qualunque giorno |
| 5 | Sfasamento del cambio BCE | dichiarato; ultimo cambio pubblicato prima della mezzanotte UTC |
| 6 | Indipendenza del secondo calcolo | resta dichiarata come nella revisione 2 |

**Seconda lettura, su pacchetto e output.** Nessun blocco alla firma. Grok ha notato che l'esposizione media sullo
sviluppo è 0,20 per la strategia e 0,52 per il benchmark, quindi un drawdown più basso arriverebbe in parte solo
dalla minore esposizione. Registrato nella revisione 5: il limite sullo Sharpe è il vero giudice dell'ipotesi, e si
aggiunge il benchmark scalato alla stessa esposizione media. L'avviso dei test viene da starlette/anyio e non tocca
i calcoli.

**Prima della firma mancano:** il resoconto del dry-run e la nuova lettura della tariffa OKX il giorno della firma.

## Cosa non è nel pacchetto

- Nessun rendimento, Sharpe, drawdown o CAGR sullo sviluppo: non è mai stato calcolato.
- Le curve di equity del secondo calcolo restano solo in locale (`checks/out/*.csv`, fuori da git).
- Il resoconto del dry-run arriva a dicembre.
