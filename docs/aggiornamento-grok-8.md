Ciao Grok, fatto tutto come concordato.

1. Ho aggiunto la curva a coorte fissa prima del congelamento (annotata nel registro, N resta 9). Sullo sviluppo, cumulato giorni 1..5 in bp (± errore standard raggruppato per data):
- F1 k=1: 0,6 / 4,1 / 6,6 / 6,5 / 8,6 (±1,1 … ±2,3)
- F1 k=3: 2,5 / 6,2 / 7,8 / 9,8 / 11,9 (±1,4 … ±2,9)
- F1 k=5: 2,8 / 4,9 / 9,8 / 9,9 / 11,7 (±1,5 … ±3,3)
- F2: da 5,6 a 9,5 al giorno 5, con errori di 3-6
- F3: rumore (a=15 vicino a 0)
Il segnale di F1 cresce fino al giorno 5 (t ≈ 3-4), quindi l'uscita a fascia è coerente. Ma un giro completo costa circa 16 bp per gamba.

2. Ho congelato il codice (impronta 2e28ab49223f98ad) ed eseguito la validazione 2015-2019 una sola volta. Nessuna variante promossa:

| Variante | Sharpe netto | t NW | Beta | Sharpe a 2 / 10 bp | Pareggio (bp/lato) |
|---|---|---|---|---|---|
| F1 k=1 | −4,23 | −8,95 | 0,08 | −0,38 / −5,50 | 1,8 |
| F1 k=3 | −3,22 | −7,70 | 0,09 | −0,76 / −4,04 | 0,4 |
| F1 k=5 | −2,53 | −6,00 | 0,12 | −0,58 / −3,18 | 0,5 |
| F2 s=0,8 | −3,17 | −5,93 | 0,00 | −0,91 / −3,89 | −0,2 |
| F2 s=1,0 | −3,70 | −7,21 | 0,02 | −0,79 / −4,63 | 0,7 |
| F2 s=1,5 | −4,37 | −8,67 | 0,05 | −0,60 / −5,60 | 1,4 |
| F3 a=5 | −0,01 | −0,02 | 0,00 | +0,56 / −0,20 | 8,1 (opera il 2% dei giorni) |
| F3 a=10 | −1,42 | −3,61 | 0,01 | −0,34 / −1,77 | 0,3 |
| F3 a=15 | −1,88 | −4,70 | 0,01 | −0,33 / −2,39 | 1,0 |

Il rischio sul beta di F1 k=5 non si è materializzato (0,12). Il MOC peggiora sempre.

Per regola il test 2020-2026 non si apre: filone PULSE-ST chiuso con esito negativo, N = 9 registrate.

Domande:
a) Confermi la lettura: il segnale lordo c'è (coorte fissa sullo sviluppo), ma nel 2015-2019 il lordo per unità di rotazione scende a 0,4-1,8 bp, ben sotto qualsiasi costo realistico per un privato?
b) Ha senso un'ultima pre-registrazione a più bassa rotazione (stesso reversal, ma ribilanciamento settimanale e holding di 5 giorni fisso), o a quel punto non è più "1-2 giorni" e conviene chiudere qui il breve termine?
c) Tra le famiglie escluse (gap, PEAD, ETF a leva), ce n'è una che con dati gratuiti ed esecuzione Alpaca abbia una probabilità realistica, o la conclusione onesta è che per un privato con dati giornalieri il breve termine sulle large cap non si sfrutta?
