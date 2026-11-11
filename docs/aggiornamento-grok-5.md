Grazie Grok, ho integrato tutte e sei le precisazioni nella v1.1:
- curva di decadimento dal giorno 1 al giorno 5, come controllo;
- solo i 9 SPDR originali, dichiarato come distorsione;
- isteresi di 0,05 sul cambio di settore;
- neutralità di beta come robustezza, in aggiunta a quella di settore;
- MOC: se una variante passa solo con il MOC, l'esito è negativo;
- copertura sotto il 90%: il test si esegue, vale solo un esito negativo, uno positivo resta sospeso fino a CRSP.

Ho ricontrollato la tua stima: con T = 6,8 e N = 9 indipendenti SR0 ≈ 0,58 e serve uno Sharpe di circa 1,21; con N = 3 effettive SR0 ≈ 0,33 e serve circa 0,96. Torna.

Ho fissato la firma in due tempi: prima il documento, poi l'impronta del codice dopo le verifiche sul solo campione di sviluppo e prima della prima esecuzione sulla validazione. Ti torna questa sequenza, o vuoi che anche il codice sia congelato prima di toccare il campione di sviluppo?
