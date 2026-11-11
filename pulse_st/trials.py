"""Conteggio delle prove (trials.jsonl) e impronta del codice di pulse_st/."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRIALS = ROOT / "trials.jsonl"
PREREG = ROOT.parent / "docs" / "prereg-pulse-st-v1.md"
N_MAX = 9
CODE_FILES = ["core.py", "trials.py", "__main__.py", "__init__.py"]


def fingerprint() -> str:
    lines = "".join(f"{hashlib.sha256((ROOT / f).read_bytes()).hexdigest()}  pulse_st/{f}\n" for f in CODE_FILES)
    return hashlib.sha256(lines.encode()).hexdigest()[:16]


def registered() -> str | None:
    m = re.search(r"Impronta del codice `pulse_st/` al congelamento: \*\*`([0-9a-f]{16})`\*\*",
                  PREREG.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def require_frozen() -> str:
    fp, reg = fingerprint(), registered()
    if reg is None:
        raise PermissionError("Codice non ancora congelato: la validazione parte solo dopo la firma dell'impronta")
    if fp != reg:
        raise PermissionError(f"Impronta del codice {fp} diversa da quella firmata {reg}: serve una nuova versione")
    return fp


def record(sample: str, family: str, params: dict, metrics: dict, path: Path = TRIALS) -> int:
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fingerprint": fingerprint(),
           "sample": sample, "family": family, "params": params, "metrics": metrics}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return count(path)


def count(path: Path = TRIALS) -> int:
    """N = coppie uniche famiglia + parametri eseguite su validazione o test (lo sviluppo non conta)."""
    if not path.exists():
        return 0
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["sample"] in ("val", "test"):
            seen.add((r["family"], json.dumps(r["params"], sort_keys=True)))
    return len(seen)


def runs_on(sample: str, family: str, params: dict, path: Path = TRIALS) -> int:
    if not path.exists():
        return 0
    key = json.dumps(params, sort_keys=True)
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if (r := json.loads(line))["sample"] == sample and r["family"] == family
               and json.dumps(r["params"], sort_keys=True) == key)
