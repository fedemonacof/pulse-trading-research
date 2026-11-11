# Registro degli interventi durante il congelamento

Regola (in [risultati-2005-2019.md](risultati-2005-2019.md)): per 12 mesi dall'avvio del paper trading i 9 file che
decidono i trade non cambiano, cioè l'impronta resta `7d054586a815bd0f` (`python main.py fingerprint`).

I guasti di infrastruttura si correggono fuori da quei file e si annotano qui, uno per riga. Se l'impronta cambia,
il periodo in ombra riparte da zero.

| Data | File | Motivo | Impronta dopo |
|---|---|---|---|
| — | — | Il congelamento parte con il paper trading (data da inserire all'avvio) | `7d054586a815bd0f` |
