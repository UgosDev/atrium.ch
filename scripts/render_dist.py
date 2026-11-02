"""Renderizza la distribuzione statica di Atrium.ch con il design autentico della triade."""

import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["NN_SITO"] = "http://nuova-norma.pagine.ch"
os.environ["ANORMA_SITO"] = "http://anorma.pagine.ch"
os.environ["PPATOS_SITO"] = "http://ppatos.pagine.ch"
os.environ["NN_ATRIUM_SITO"] = "http://atrium.pagine.ch"

from atrium import web

DIST = ROOT / "dist"
if DIST.exists():
    shutil.rmtree(DIST)
DIST.mkdir(parents=True, exist_ok=True)

# 1. Homepage Atrium (Design autentico pietra: Lo spazio tra le tre stanze)
home_html = web.pagina_iniziale()
(DIST / "index.html").write_bytes(home_html)
print(f"✅ Generato dist/index.html ({len(home_html):,} bytes)")

# 2. Pagina Questione (Stanza con crittografia end-to-end e registro eventi)
q_dir = DIST / "q"
q_dir.mkdir(parents=True, exist_ok=True)
q_html = web.pagina_questione()
(q_dir / "index.html").write_bytes(q_html)
print(f"✅ Generato dist/q/index.html ({len(q_html):,} bytes)")

# 3. Risorse statiche specifiche di Atrium (atrium.js, pagina.js)
atrium_static = DIST / "atrium"
atrium_static.mkdir(parents=True, exist_ok=True)

atrium_src = ROOT / "atrium" / "statico"
if atrium_src.exists():
    for name in ["atrium.js", "pagina.js"]:
        src = atrium_src / name
        if src.exists():
            shutil.copy2(src, atrium_static / name)
            shutil.copy2(src, DIST / name)
print("✅ Risorse Atrium sincronizzate in dist/atrium/")

# 4. Risorse statiche condivise della triade (citazioni, copia, favicon, logo)
nn_static = DIST / "nn"
nn_static.mkdir(parents=True, exist_ok=True)

nn_src = ROOT.parent / "nuova-norma.ch" / "nn"
if nn_src.exists():
    for name in ["citazioni.js", "copia.js", "favicon.js", "logo.css"]:
        src = nn_src / name
        if src.exists():
            shutil.copy2(src, nn_static / name)
            shutil.copy2(src, DIST / name)
print("✅ Risorse Triade sincronizzate in dist/nn/")

# 5. Copia configurazione pch.json
shutil.copy2(ROOT / "pch.json", DIST / "pch.json")
print("✅ Configurazione pch.json sincronizzata in dist/")
