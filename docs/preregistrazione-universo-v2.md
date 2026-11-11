# Pre-registrazione v2: universo storico S&P 500 con filtro sui dati

La v1 (`docs/preregistrazione-universo.md`) è stata eseguita una volta. Il risultato, in
`docs/risultati-universo-v1-non-valido.md`, non è valido per un errore nei dati: la serie Yahoo di GR ha aperture
impossibili e da sola spiega la perdita dell'universo ampio.

## Cosa cambia rispetto alla v1

**Solo questo:** prima del test si escludono le serie con barre impossibili (`desk/universe.py`, `clean`). Una barra
è impossibile se:
- l'apertura o la chiusura sono fuori da [minimo, massimo] di oltre l'1%;
- il massimo è sotto il minimo;
- l'apertura è più di 3 volte, o meno di 1/3, della chiusura precedente.

Una serie con anche una sola barra impossibile viene esclusa per intero. Sui dati scaricati la regola esclude
4 serie: CPWR, EP, FNMA e GR. Non esclude i titoli crollati davvero nel 2008-2009, come AIG, MS e HIG, che hanno
barre coerenti.

Restano identici:
- esperimenti U1, U2 e U3 (seed 11; per U3 l'estrazione avviene fra i membri con dati validi);
- metriche e DSR con N = 10;
- regole 4, 5 e 6 e la soglia di copertura al 90%;
- periodo e codice congelato (`7d054586a815bd0f`).

## Onestà sul processo

Questa v2 è scritta **dopo** aver visto i risultati della v1, compresi U2 e U3. La regola sui dati è meccanica:
riguarda la coerenza interna delle barre, non il rendimento. È stata scelta per correggere il difetto trovato,
non per migliorare un numero. Chi legge però deve sapere che non è cieca come la v1. La copertura resta 68,8%,
sotto il 90%: anche nella v2 **l'universo ampio può dare solo un esito negativo.**

## Impronta di questo test

9 file congelati + `desk/universe.py` + `desk/research.py`: **`b17db00acf5145b9`**
