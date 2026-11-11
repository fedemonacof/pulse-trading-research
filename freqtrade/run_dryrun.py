"""Avvia il dry-run di freqtrade per il criterio 7 di PULSE-CT. Nessuna chiave dell'exchange.

Le credenziali dell'API locale (127.0.0.1) stanno in freqtrade/.env, fuori da git. caffeinate -is tiene il Mac
sveglio finché freqtrade gira (con l'alimentatore collegato). È in Python e non in zsh perché macOS lascia leggere
~/Documents ai job di launchd solo attraverso Python.
"""
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
for line in (HERE / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
subprocess.Popen(["/usr/bin/caffeinate", "-is", "-w", str(os.getpid())])
py = str(HERE / ".venv" / "bin" / "python")
os.execv(py, [py, "-m", "freqtrade", "trade", "--config", "config.dryrun.json", "--userdir", "user_data",
              "--logfile", "user_data/logs/dryrun.log"])
