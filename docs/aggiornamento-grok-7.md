Ciao Grok, documento v1.1 firmato l'11/11 (SHA-256 09a79696…). Il codice pulse_st/ è scritto, 101 test passano, e ho fatto i controlli di correttezza sul solo campione di sviluppo 2005-2014. Come d'accordo, lo Sharpe è registrato in trials.jsonl ma non l'ho guardato.

Bug corretti prima dei dati reali, annotati nel registro:
- neutralità: il metodo per tentativi poteva azzerare il portafoglio; ora una costruzione esatta che riduce soltanto;
- un titolo uscito per tempo massimo rientrava alla stessa chiusura, quindi i 5 giorni non scattavano mai; ora chi esce non rientra quel giorno.
Aggiunte due metriche di sola lettura: dimensione media delle gambe e osservazioni per giorno della curva di decadimento.

Controlli (universo 200 titoli al giorno, escluse CPWR, EP, FNMA, GR, scarto fra le gambe < 1e-15):

| Variante | Gamba media | Holding (gg) | Turnover/gg | Beta | Pareggio (bp/lato) | Decadimento g1..g5 (bp) | Osservazioni g1..g5 |
|---|---|---|---|---|---|---|---|
| F1 k=1 | 0,65 | 1,40 | 1,96 | 0,12 | 1,6 | 0,8 / 6,6 / 7,7 / 8,2 / 42,7 | 113k / 32k / 9k / 2,7k / 858 |
| F1 k=3 | 0,85 | 2,67 | 1,44 | 0,17 | 3,5 | 1,9 / 2,3 / 1,3 / 3,0 / 5,0 | 75k / 58k / 39k / 17k / 10k |
| F1 k=5 | 0,86 | 3,47 | 1,15 | 0,19 | 4,4 | 1,5 / 1,5 / 3,1 / 0,2 / 5,5 | 58k / 49k / 40k / 31k / 23k |
| F2 s=0,8 | 0,09 | 1,37 | 0,26 | 0,01 | 1,7 | 1,8 / 4,0 / 2,1 / 11,9 / 31,6 | 26k / 7k / 2k / 555 / 159 |
| F2 s=1,0 | 0,22 | 1,39 | 0,67 | 0,03 | 0,8 | 0,6 / 5,0 / 5,8 / 11,6 / 22,1 | 52k / 14k / 4k / 1,3k / 402 |
| F2 s=1,5 | 0,48 | 1,39 | 1,47 | 0,08 | 1,9 | 1,9 / 5,8 / 7,8 / 6,1 / 41,5 | 92k / 26k / 7k / 2,2k / 706 |
| F3 a=5 | 0,08 | 1,27 | 0,01 | 0,00 | −8,8 | (pochissime osservazioni) | 1,8k / 436 / 64 / 20 / 3 |
| F3 a=10 | 0,13 | 1,47 | 0,06 | 0,00 | 0,0 | −0,8 / 10,2 / −1,7 / 6,4 / 19,5 | 11k / 4k / 1,5k / 535 / 173 |
| F3 a=15 | 0,19 | 1,57 | 0,18 | 0,00 | −0,4 | −0,9 / 2,0 / 8,4 / 1,1 / 14,1 | 27k / 11k / 4k / 1,8k / 763 |

Cosa vedo:
1. Pareggio. Il rendimento lordo per unità di turnover non supera i 4,4 bp per lato in nessuna variante, contro un caso base di 8 bp. Già sullo sviluppo tutte perdono dopo i costi. Non cambio niente, perché è pre-registrato.
2. Decadimento. Il giorno 1 rende quasi zero (0,6-1,9 bp). I giorni 4-5 sembrano alti, ma le osservazioni crollano: è un effetto di selezione, cioè chi resta 4-5 giorni nel decile estremo è una serie di cali consecutivi, non lo stesso trade che matura. Per me questo non prova che l'uscita a fascia sia coerente.
3. F2 e F3 hanno gambe piccolissime (0,08-0,22): con il minimo di 5 titoli e i filtri, la RSI(2) market neutral è quasi sempre ferma o con pochi nomi.
4. Il beta di F1 k=5 è 0,19, vicino alla soglia di 0,2, anche se le gambe sono in pari in dollari: i perdenti del settore hanno beta più alto.

Domande:
a) Sei d'accordo che il codice è corretto e si può congelare (impronta 08015cf690fc9129) e passare alla validazione 2015-2019, sapendo che l'esito atteso è negativo?
b) La mia lettura della curva di decadimento come effetto di selezione è giusta? Andrebbe calcolata anche su una coorte fissa (stessi trade, giorno 1..5 senza condizionare alla permanenza) come secondo controllo, sempre senza contare come prova?
