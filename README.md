# PULSE: un trading bot messo alla prova

> **Research project, negative result. Not financial advice. Do not use with real money.**
> PULSE is an automated equity agent (Python, Alpaca paper trading, Next.js command center) and, above all,
> a set of **pre-registered tests** of its strategies: rules, data, costs and pass thresholds written and
> hashed before looking at the results. None of the strategies beat simply holding the market after costs.
> Case study: <https://federicomonaco.com/projects/pulse/>. The documentation is in Italian.

PULSE studia il mercato, sceglie i trade da strategie definite, li esegue su **Alpaca in paper trading** e ogni
notte valuta le proprie decisioni. I soldi veri si usano solo con due impostazioni esplicite (vedi `.env.example`).

> **Avvertenza.** Progetto di ricerca con esito negativo. Non è un consiglio d'investimento e non garantisce
> profitti: nei test pre-registrati **nessuna strategia batte il buy & hold dopo i costi**. Non usarlo con soldi veri.

## Risultati in breve

| Test (pre-registrato, eseguito una volta) | Esito | Documento |
|---|---|---|
| Core SPY + satellite, 2005-2019 | il satellite non aggiunge valore dimostrabile → in ombra | [docs/risultati-2005-2019.md](docs/risultati-2005-2019.md) |
| Universo S&P 500 storico + 100 universi casuali | il vantaggio veniva dai 15 titoli scelti col senno di poi (0,88 contro una mediana di 0,41) | [docs/risultati-universo.md](docs/risultati-universo.md) |
| Filtro a 200 giorni in 6 mercati | taglia i crolli, ma regge solo in 3 su 6 e costa 1,3-4 punti l'anno dopo le tasse | [docs/risultati-filtro.md](docs/risultati-filtro.md) |
| PULSE-ST: long/short a 1-5 giorni, 9 varianti | nessuna supera la validazione 2015-2019; il test 2020-2026 non è mai stato aperto | [docs/risultati-pulse-st.md](docs/risultati-pulse-st.md) |

Le pre-registrazioni sono in `docs/` (`preregistrazione-*.md`, `prereg-pulse-*.md`). Le revisioni incrociate con
Grok sono in `docs/aggiornamento-grok-*.md`.

## Dati

I prezzi non sono nel repository. Per rifare i test: `python scripts/fetch_data.py` (15-20 minuti), poi
`python main.py universe`, `python main.py filter` o `python -m pulse_st dev`. I comandi dei test pre-registrati
si rifiutano di girare se il codice non corrisponde all'impronta firmata.

## Architettura: due livelli, mai mescolati

```
IL CERVELLO (Python, lento)                     IL RIFLESSO (deterministico, veloce)
  strategie (solo long): trend 20/50 EMA + RSI    stato numerico compatto per titolo
             con momentum 6 mesi; mean reversion  (prezzo, ATR, punteggi, regime, voto AI, posizione)
             Bollinger su SPY/QQQ/IWM sopra MA200      │
  regime: trending / mean_reverting /                  ▼
          high_vol / crisis (ATR, SPY vs MA200)   compra / vendi / resta + confidenza 0-100 + motivo
  comitato AI (8 agenti Claude): VOTA                  │   soglie, pesi e dimensioni: tutto nel codice
  backtest walk-forward, revisione notturna            ▼
                                                  RISK LAYER (nessun modello lo può scavalcare)
                                                       │
                                                       ▼
                                                  Alpaca: ordine bracket (stop + target)
```

- **Riflesso** (`desk/reflex.py`): fonde i punteggi delle strategie, pesati per regime, con il voto del comitato
  AI. Il comitato parte a peso 0 (massimo 0,2) e non può aprire una posizione da solo. Soglie: entrata con |punteggio|
  ≥ 55, uscita sotto 20. Isteresi: l'RSI conferma solo l'entrata, si resta dentro finché il trend regge.
- **Risk layer** (`desk/risk.py`, `RiskGate`): viene controllato prima di ogni ordine. Un test verifica che nessun
  percorso arrivi al broker senza il suo via libera.

| Regola | Valore |
|---|---|
| Peso massimo per posizione | 5% dell'equity |
| Posizioni aperte | massimo 5 |
| Ogni entrata | ordine bracket: stop a 2×ATR, target a 3×ATR |
| Perdita giornaliera | −2% → chiude tutto e pausa fino alla prossima sessione |
| Kill switch | endpoint + pulsante: cancella tutti gli ordini, chiude tutto, si ferma |
| Orari | solo sessione regolare, niente nei primi 5 minuti |
| Extra (freqtrade) | trailing stop, cooldown dopo uno stop, StoplossGuard, drawdown massimo 15% |

- **Paper per default**: il bot rifiuta di partire se `ALPACA_BASE_URL` non è l'indirizzo paper. Per i soldi veri
  servono insieme `LIVE_TRADING=true` e una frase di conferma esplicita.

## Configurazione attuale (decisa da un test pre-registrato)

| Componente | Stato | Perché |
|---|---|---|
| **Core SPY con filtro a 200 giorni** | attivo | a fine mese SPY sopra la sua media a 200 giorni → SPY, altrimenti liquidità |
| **Satellite PULSE** | **in ombra** | decide e opera su un conto virtuale (trade `SHADOW`), nessun ordine vero |
| **Comitato AI** | peso 0 (max 0,2) | vota e si registra: si valuta solo in avanti |

La configurazione viene dal test **pre-registrato** su 2005-2019, un periodo mai usato prima che comprende la crisi
del 2008. Le regole di decisione sono state scritte prima di vedere i dati
([docs/preregistrazione-2005-2019.md](docs/preregistrazione-2005-2019.md)).

| 2005-2019 | CAGR | Sharpe | Max DD |
|---|---|---|---|
| 100% SPY | +8,9% | 0,56 | −55,2% |
| Core + satellite PULSE | +9,7% | 0,61 | −55,0% |
| SPY con filtro a 200 giorni | +9,4% | **0,80** | **−20,9%** |

- **Il satellite batte SPY** (+0,8% all'anno), ma l'intervallo di confidenza tocca lo zero: niente vantaggio
  dimostrato, quindi resta in ombra.
- **Il filtro a 200 giorni** riduce il drawdown massimo da −55% a −21% a parità di rendimento, quindi è adottato.
- **Riattivazione del satellite:** avviene solo con la regola fissata in [docs/risultati-2005-2019.md](docs/risultati-2005-2019.md)
  (12 mesi di ombra, almeno 100 trade, miglioramento dello Sharpe con intervallo sopra zero).
- **Universo storico S&P 500** (secondo test pre-registrato): il buon risultato del satellite veniva dai 15 titoli
  scelti oggi. Con 15 titoli presi a caso fra i membri del 2005 lo Sharpe mediano è 0,41 contro 0,88. Sull'S&P 500
  storico lo Sharpe è 0,39 contro 0,56 di SPY. **Nessuna evidenza di abilità del satellite**, che resta in ombra.
  Dettagli: [docs/risultati-universo.md](docs/risultati-universo.md) (`python main.py universe`).
- **Filtro a 200 giorni fuori dagli USA** (terzo test pre-registrato, 6 mercati): taglia sempre il drawdown, ma
  regge secondo le regole solo in 3 mercati su 6 e costa da 1,3 a 4 punti di CAGR l'anno dopo le tasse italiane.
  È un'assicurazione contro i crolli, non un vantaggio di rendimento: resta nel conto paper.
  [docs/risultati-filtro.md](docs/risultati-filtro.md) (`python main.py filter`).
- **Ombra a regola:** il satellite in ombra guarda i 100 membri attuali dell'S&P 500 con più volume in dollari,
  ricalcolati ogni mese (`SHADOW_UNIVERSE=top100`). Conta solo questa ombra per la riattivazione. Gli interventi
  durante il congelamento vanno in [docs/registro-interventi.md](docs/registro-interventi.md).
- **Fase in avanti:** [docs/preregistrazione-avanti.md](docs/preregistrazione-avanti.md). Con 12 mesi la
  probabilità di riconoscere un vantaggio vero è sotto il 15%: il paper trading serve a trovare guasti e
  differenze rispetto al backtest. Il diario salva i voti grezzi del comitato (`votes`) e i punteggi non pesati
  delle strategie (`signals`).
- **Soldi veri dall'Italia:** Alpaca negozia solo su mercati USA e non è chiaro se un conto retail italiano possa
  comprare ETF americani (regole KID/PRIIPs). Gli ETF UCITS come CSPX o SXR8 non si comprano su Alpaca. Il paper
  trading invece funziona da qualsiasi paese.
- **Ricerche precedenti** (2019-2026, varianti, core + satellite): [docs/ricerca-strategie.md](docs/ricerca-strategie.md).

Il codice che decide i trade ha un'impronta: `python main.py fingerprint` dice se è cambiato rispetto a quello testato.

## Comandi

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd dashboard && npm install && npm run build)       # compila il command center in dashboard/out
cp .env.example .env                                 # chiavi Anthropic + Alpaca PAPER

.venv/bin/python main.py backtest                    # backtest su dati gratuiti Yahoo (2 anni)
.venv/bin/python main.py backtest alpaca             # lo stesso sulle barre storiche Alpaca
.venv/bin/python main.py app                         # command center su http://127.0.0.1:8000
.venv/bin/python main.py once                        # un giro completo (comitato + riflesso)
.venv/bin/python main.py run                         # 24/7: solo con SCHEDULER_ENABLED=true
.venv/bin/python main.py review                      # revisione notturna adesso
.venv/bin/python main.py fingerprint                 # il codice è quello testato?
.venv/bin/python main.py kill                        # kill switch da riga di comando
.venv/bin/python main.py simulate                    # demo.db per provare la dashboard senza chiavi
.venv/bin/python -m pytest                           # 71 test offline
```

Docker: `docker build -t pulse .` poi `docker run --env-file .env -p 127.0.0.1:8000:8000 -v pulse-data:/data pulse app`.

## Command center

Next.js + TypeScript + Tailwind, sfera di particelle in WebGL (three.js), grafici TradingView Lightweight Charts
e Recharts. Lo stato arriva via WebSocket, con ripiego sul polling. Ogni numero viene dal diario o dal backtest:
se manca, la dashboard mostra "—".

THE CORE (sfera dei segnali + pila dei verdetti + osservabili) · STATE (P&L di oggi) · LIFE OF A DECISION ·
WHERE IT LANDS (entrata/stop/target) · EQUITY VS SPY + drawdown · CORRELATION MAP · AGENT LOG · STRATEGY ENGINE ·
AI COUNCIL · BACKTEST · nastri LIVE FEED e RISK.

## Revisione notturna

Ogni sera feriale alle 17:15 di New York la revisione calcola per strategia la percentuale di trade vincenti,
il profit factor, il drawdown massimo, lo Sharpe e la calibrazione della confidenza. Poi scrive un report in
`reports/` e sposta i pesi delle strategie di ±0,1 al massimo, entro limiti fissi (0,5-1,5; il comitato 0-0,5).
**Non tocca mai i limiti di rischio.**

## Da dove vengono le idee

TradingAgents (dibattito rialzista/ribassista, panel di rischio), ai-hedge-fund (analisti specializzati),
freqtrade (protezioni, Telegram, paper per default), OpenTerminal (fonti dati gratuite FRED, Forex Factory,
TradingView, RSS), Hyperliquid, Alpha Arena e QuantumOrb (stile del command center).

## Licenza

MIT, vedi [LICENSE](LICENSE). I dati di mercato restano dei rispettivi fornitori e non sono inclusi.
