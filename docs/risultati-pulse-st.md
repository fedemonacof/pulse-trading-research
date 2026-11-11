# PULSE-ST: risultati della validazione 2015-2019 (esecuzione unica, 12/11/2026)

Regole: [prereg-pulse-st-v1.md](prereg-pulse-st-v1.md) (documento `09a79696…`, codice `2e28ab49223f98ad`).
Universo di 200 titoli al giorno; escluse le serie con dati impossibili (CPWR, EP, FNMA, GR). Costi del caso base:
8 bp per lato, doppi nei giorni di stress, prestito 0,5% annuo, commissioni SEC/FINRA. N = 9.

| Variante | Sharpe netto | t (Newey-West) | Beta | Sharpe a 2 / 5 / 10 / 20 bp | Lordo (bp/giorno) | Pareggio (bp/lato) | Max DD | MOC | Promossa |
|---|---|---|---|---|---|---|---|---|---|
| F1 k=1 | −4,23 | −8,95 | 0,08 | −0,38 / −2,31 / −5,50 / −11,63 | +3,5 | 1,8 | −84% | −7,38 | no |
| F1 k=3 | −3,22 | −7,70 | 0,09 | −0,76 / −1,99 / −4,04 / −8,05 | +0,6 | 0,4 | −80% | −5,09 | no |
| F1 k=5 | −2,53 | −6,00 | 0,12 | −0,58 / −1,56 / −3,18 / −6,38 | +0,6 | 0,5 | −72% | −3,97 | no |
| F2 s=0,8 | −3,17 | −5,93 | 0,00 | −0,91 / −2,06 / −3,89 / −7,05 | −0,1 | −0,2 | −30% | −4,63 | no |
| F2 s=1,0 | −3,70 | −7,21 | 0,02 | −0,79 / −2,25 / −4,63 / −8,91 | +0,5 | 0,7 | −54% | −6,02 | no |
| F2 s=1,5 | −4,37 | −8,67 | 0,05 | −0,60 / −2,49 / −5,60 / −11,41 | +2,1 | 1,4 | −77% | −7,33 | no |
| F3 a=5 | −0,01 | −0,02 | 0,00 | +0,56 / +0,28 / −0,20 / −1,10 | +0,2 | 8,1 | −2% | 0,00 | no |
| F3 a=10 | −1,42 | −3,61 | 0,01 | −0,34 / −0,88 / −1,77 / −3,42 | +0,0 | 0,3 | −12% | −1,76 | no |
| F3 a=15 | −1,88 | −4,70 | 0,01 | −0,33 / −1,11 / −2,39 / −4,78 | +0,3 | 1,0 | −24% | −2,95 | no |

## Decisione (regola pre-registrata)

**Nessuna variante supera la validazione** (servivano t > 2, |β| < 0,2 e Sharpe > 0 a 10 bp). Quindi il periodo
di test 2020-2026 **non si apre**, e il filone PULSE-ST, così come è definito, si chiude con esito negativo.
Le 9 prove sono registrate in `pulse_st/trials.jsonl`.

## Cosa significa

- **Il segnale esiste, i costi lo mangiano.** Sullo sviluppo la curva a coorte fissa di F1 cresce in modo
  regolare: 9-12 bp in 5 giorni, con t fra 3 e 4. Ma un giro completo costa circa 16 bp per gamba. Nel 2015-2019
  il rendimento lordo per unità di rotazione è sceso a 0,4-1,8 bp per lato, contro 8 bp di costi.
- **Anche a 2 bp per lato**, un costo irrealistico per un privato, tutte le varianti F1 e F2 restano sotto zero.
  F3 a=5 sfiora lo zero solo perché opera il 2% dei giorni.
- **Il MOC peggiora sempre**, perché aggiunge 5 bp, e la neutralità di beta non cambia il quadro.
- È coerente con la letteratura citata da Grok: sulle large cap USA il reversal di breve si è molto attenuato e
  dopo i costi sparisce.

## Cosa non dice

- **Non dice** che il reversal non esista: dice che con dati giornalieri, ingresso all'apertura e costi da
  privato non si sfrutta.
- **Non dice** nulla sulle famiglie escluse (gap, PEAD, ETF a leva, overnight). Ognuna richiede una
  pre-registrazione propria e dati diversi: intraday, oppure un calendario degli utili.

## Revisione di Grok (12/11/2026)

- **Conferma la lettura.** Il segnale lordo esisteva nel 2005-2014 (coorte fissa, t ≈ 3-4), ma nel 2015-2019 si
  è ridotto sotto qualsiasi costo realistico. La procedura ha chiuso con un negativo pulito, senza aprire il test.
- **Reversal settimanale** (5 giorni fissi, ribilanciamento settimanale): è un altro filone, con una sua
  letteratura. Si fa solo con una pre-registrazione nuova, N = 1-2 e un campione di validazione dal 2020 in poi,
  mai visto. Il 2015-2019 non si può riusare. Aspettativa negativa: il lordo a 5 giorni sullo sviluppo era 8-12 bp,
  contro circa 16 bp per un giro completo.
- **Famiglie escluse:** gap ed ETF a leva richiedono dati intraday ed esecuzione da professionisti. La PEAD vive
  su settimane e richiede utili e stime point-in-time che gratis non si trovano in forma affidabile. Nessuna ha una
  probabilità realistica con dati giornalieri gratuiti e Alpaca.
- **Conclusione:** il vantaggio realistico di un privato è la pazienza e i costi bassi, cioè il buy & hold di un
  ETF UCITS.
