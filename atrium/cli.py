"""Comandi di Atrium.

  py -m atrium sito [--porta 8768] [--host 127.0.0.1] [--senza-browser]
  py -m atrium catena <stanza>        controlla la catena delle impronte di una questione
  py -m atrium link --titolo ... --testo ... [--prodotto anorma] [--fonte ...] [--url ...]
                                      link per aprire una questione con un oggetto da portare dentro
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="atrium", description=f"Atrium {__version__}, lo spazio condiviso della triade")
    sub = ap.add_subparsers(dest="comando", required=True)
    s = sub.add_parser("sito", help="avvia il sito (porta 8768)")
    s.add_argument("--porta", type=int, default=8768)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--senza-browser", action="store_true")
    c = sub.add_parser("catena", help="controlla la catena delle impronte di una questione")
    c.add_argument("stanza")
    lk = sub.add_parser("link", help="link per aprire una questione con un oggetto dentro")
    lk.add_argument("--titolo", required=True)
    lk.add_argument("--testo", default="")
    lk.add_argument("--prodotto", default="anorma", choices=["anorma", "nuova-norma", "ppatos"])
    lk.add_argument("--fonte", default="")
    lk.add_argument("--url", default="")
    lk.add_argument("--base", default="http://127.0.0.1:8768")
    a = ap.parse_args(argv)

    if a.comando == "sito":
        from .web import serve
        serve(a.porta, not a.senza_browser, a.host)
    elif a.comando == "catena":
        from .registro import Registro
        from .web import percorso_db
        reg = Registro(percorso_db())
        ok, seq = reg.verifica_catena(a.stanza)
        print("Catena integra." if ok else f"Catena interrotta all'evento {seq}.")
        sys.exit(0 if ok else 1)
    elif a.comando == "link":
        from .porta import link_porta
        print(link_porta({"prodotto": a.prodotto, "titolo": a.titolo, "testo": a.testo, "fonte": a.fonte,
                          "url": a.url}, a.base))
