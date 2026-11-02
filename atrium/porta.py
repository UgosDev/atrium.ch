"""La porta dei prodotti verso Atrium: un link che apre una questione nuova con un oggetto gia dentro.

Le regole stanno in nn/triade.py (oggetto_atrium, link_atrium, porta_atrium_html), cosi Nuova-Norma, Anorma e PPaToS
le usano senza importare Atrium. Qui restano i nomi usati da Atrium e dalla riga di comando.

L'oggetto viaggia nel frammento del link (#o=...), che il browser non invia al server: Atrium lo mostra prima di aprire
la questione, poi lo cifra con la chiave della stanza e lo fissa tra «I fatti». Campi: prodotto (anorma, nuova-norma,
ppatos), titolo, testo, fonte, url. I testi lunghi vengono accorciati, perche il link resti utilizzabile.
"""

from __future__ import annotations

from . import _nn  # noqa: F401
from nn import triade

LIMITI = triade.LIMITI_ATRIUM


def pulisci(oggetto: dict) -> dict:
    return triade.oggetto_atrium(oggetto)


def link_porta(oggetto: dict, base: str = "http://127.0.0.1:8768") -> str:
    return triade.link_atrium(oggetto, base)
