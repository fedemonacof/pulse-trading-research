"""Impronta del codice, conteggio delle esecuzioni (trials.jsonl) e stato della pre-registrazione.

Lo stato decide fin dove si possono leggere i dati:
- "unsigned": documento non firmato → solo fino alla fine dello sviluppo (2020-12-31);
- "val": firmato, validazione non ancora passata → fino alla fine della validazione (2022-12-31);
- "test": validazione passata → fino alla fine del test (2026-10-31).
Non esiste un'opzione per saltare questo controllo.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config

PKG = Path(__file__).resolve().parent
TRIALS = PKG / "trials.jsonl"
CODE_FILES = [PKG / f for f in ("__init__.py", "__main__.py", "config.py", "data.py", "fx.py", "live.py",
                                "strategy.py", "stats.py", "trials.py", "crosscheck.py", "dryrun.py",
                                "robust.py")] + [PKG.parents[1] / "core" / "costs.py"]


def fingerprint() -> str:
    lines = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(config.ROOT)}\n"
                    for p in CODE_FILES)
    return hashlib.sha256(lines.encode()).hexdigest()[:16]


def registered(doc: Path | None = None) -> str | None:
    """Impronta scritta nella tabella della firma (sezione 10). '—' vuol dire non firmato."""
    text = (doc or config.DOC).read_text(encoding="utf-8")
    m = re.search(r"\|\s*Impronta del codice\s*\|\s*`?([0-9a-f]{16})`?\s*\|", text)
    return m.group(1) if m else None


def rows(path: Path = TRIALS) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stage(doc: Path | None = None, path: Path = TRIALS) -> str:
    if registered(doc) is None:
        return "unsigned"
    passed = any(r["sample"] == "val" and r["variant"] == config.MAIN and r.get("outcome") == "passa"
                 for r in rows(path))
    return "test" if passed else "val"


def data_limit(st: str):
    return {"unsigned": config.PERIODS["dev"][1], "val": config.PERIODS["val"][1],
            "test": config.PERIODS["test"][1]}[st]


def require_frozen(doc: Path | None = None) -> str:
    fp, reg = fingerprint(), registered(doc)
    if reg is None:
        raise PermissionError("Documento non firmato: validazione e test partono solo dopo la firma dell'impronta")
    if fp != reg:
        raise PermissionError(f"Impronta del codice {fp} diversa da quella firmata {reg}: serve una nuova versione")
    if config.TAKER_BP is None:
        raise PermissionError("Tariffa taker di OKX Europe non scritta (criterio 8)")
    return fp


def runs_on(sample: str, variant: str, path: Path = TRIALS) -> int:
    return sum(1 for r in rows(path) if r["sample"] == sample and r["variant"] == variant)


def record(sample: str, variant: str, metrics: dict, outcome: str | None = None, path: Path = TRIALS) -> None:
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fingerprint": fingerprint(),
           "sample": sample, "variant": variant, "outcome": outcome, "metrics": metrics}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
