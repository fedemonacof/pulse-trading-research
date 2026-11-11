# Registro degli interventi su PULSE-ST

Regole: [prereg-pulse-st-v1.md](prereg-pulse-st-v1.md), sezione 8. Sul campione di sviluppo si correggono solo
bug, mai scelte. Ogni intervento va qui.

| Data | Fase | File | Intervento | Tipo |
|---|---|---|---|---|
| 2026-11-11 | scrittura del codice, prima dei dati reali | `pulse_st/core.py` | Il secondo valore restituito da `weights` aveva la forma sbagliata | bug |
| 2026-11-11 | scrittura del codice, prima dei dati reali | `pulse_st/core.py` | Neutralità: il metodo per tentativi poteva ridurre il portafoglio quasi a zero e sforava il 5%. Sostituito con una costruzione esatta (`neutralize`), che pareggia le gambe e rispetta il netto di settore ≤ 5% del lordo riducendo solo | bug (stessa regola, implementazione corretta) |
| 2026-11-11 | scrittura del codice, prima dei dati reali | `pulse_st/core.py` | Un titolo uscito per tempo massimo poteva rientrare alla stessa chiusura: la regola dei 5 giorni non funzionava mai. Ora chi esce non rientra quel giorno | bug |
| 2026-11-12 | sviluppo, controlli di correttezza | `pulse_st/core.py`, `__main__.py` | Aggiunte due metriche di sola lettura: dimensione media delle gambe e osservazioni per giorno della curva di decadimento. "Gambe piene" era sempre 0, perché il limite del 2% del lordo per titolo tiene ogni gamba sotto 1 | metrica, nessuna regola toccata |
| 2026-11-12 | sviluppo, prima del congelamento | `pulse_st/core.py`, `__main__.py` | Aggiunta la curva di decadimento a coorte fissa, proposta da Grok: per tutte le entrate, rendimento cumulato dal giorno 1 al 5 anche dopo l'uscita, con errore standard raggruppato per data. Serve come controllo, non come prova | metrica, N resta 9 |
| 2026-11-12 | sviluppo | — | **Rischio noto:** F1 k=5 ha beta 0,19 sullo sviluppo. In validazione potrebbe superare 0,2 ed essere scartata per il beta, non per lo Sharpe | nota |

Scelte d'implementazione fissate nel codice, perché il documento non scende a questo dettaglio. Valgono per tutte
le varianti:
- F2: la media del volume a 20 giorni esclude il giorno stesso.
- Uscita "nel 50% centrale": long esce con rango < 75%, short con rango > 25%.
- F3: long esce con RSI(2) ≥ 30, short con RSI(2) ≤ 70.
- Un titolo che esce dall'universo mensile esce dalla posizione.
- RSI di Wilder.
- Commissioni SEC/FINRA: 0,28 bp sulle vendite.
