"""Rende importabile Nuova-Norma (pacchetto nn) dalla cartella accanto, per le regole della triade e il CSS comune.

Come per Anorma e PPaToS. Con NN_CARTELLA si puo indicare un'altra posizione.
"""

import os
import sys
from pathlib import Path

try:
    import nn  # noqa: F401
except ImportError:
    here = Path(__file__).resolve()
    cartella = Path(os.environ.get("NN_CARTELLA") or "")
    if not (cartella / "nn" / "__init__.py").exists():
        candidates = []
        for p in here.parents:
            candidates.extend([p / "nuova-norma.ch", p / "nuova-norma"])
        for candidata in candidates:
            if (candidata / "nn" / "__init__.py").exists():
                cartella = candidata
                break
    if not (cartella / "nn" / "__init__.py").exists():
        raise SystemExit(f"Non trovo Nuova-Norma in {cartella}: Atrium la usa per le regole del design. "
                         "Imposta NN_CARTELLA nel file .env o metti le due cartelle una accanto all'altra.")
    sys.path.insert(0, str(cartella))
    import nn  # noqa: F401,E402
