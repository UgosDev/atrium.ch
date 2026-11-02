"""Il sito di Atrium (porta 8768): pagina iniziale, pagina della questione, API cifrata e flusso in tempo reale.

Il tempo reale usa Server-Sent Events (il server parla) e richieste POST (il browser scrive): niente librerie esterne,
lo stesso server della libreria standard usato da Nuova-Norma, Anorma e PPaToS.

Cosa vede il server: identificativi casuali delle stanze, impronte dei segreti dei membri, blocchi cifrati di
dimensione arrotondata, l'ora di ogni evento. Non vede nomi, titoli, messaggi, fatti ne chi sta leggendo cosa.
La chiave della stanza sta nel frammento del link (#k=...), che il browser non invia mai al server.
Il registro dei collegamenti non riporta gli indirizzi completi (contengono il codice del membro).
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.parse
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import _nn  # noqa: F401  rende importabile nn dalla cartella accanto
from nn import triade
from nn.web import CSS, serve_static

from . import __version__
from .registro import ErroreRegistro, Registro, impronta_segreto
from .smistatore import FINE, Smistatore, da_ambiente

QUI = Path(__file__).resolve().parent
STATICO = {
    "/atrium/atrium.js": QUI / "statico" / "atrium.js",
    "/atrium/pagina.js": QUI / "statico" / "pagina.js",
}
MAX_CORPO = 200 * 1024
BATTITO = 15.0


def percorso_db() -> Path:
    return Path(os.environ.get("ATRIUM_DB") or QUI.parent / "data" / "atrium.sqlite")


def b64u(dati: bytes) -> str:
    return base64.urlsafe_b64encode(dati).rstrip(b"=").decode("ascii")


def da_b64u(testo: str) -> bytes:
    if not isinstance(testo, str) or len(testo) > 200_000:
        raise ErroreRegistro("contenuto cifrato non valido")
    try:
        return base64.urlsafe_b64decode(testo + "=" * (-len(testo) % 4))
    except (ValueError, TypeError):
        raise ErroreRegistro("contenuto cifrato non valido")


def evento_json(ev: dict) -> dict:
    return {"seq": ev["seq"], "ts": ev["ts"], "dati": b64u(ev["dati"]), "prec": ev["prec"], "impronta": ev["impronta"]}


class Limitatore:
    """Limite di richieste per chiave (indirizzo o membro) in una finestra di tempo. Solo in memoria: le chiavi
    spariscono con la finestra, nessun indirizzo viene conservato oltre."""

    def __init__(self, massimo: int, finestra: float):
        self.massimo, self.finestra = massimo, finestra
        self._lock = threading.Lock()
        self._colpi: dict[str, list[float]] = {}

    def consenti(self, chiave: str) -> bool:
        ora = time.time()
        with self._lock:
            if len(self._colpi) > 10000:
                self._colpi = {k: v for k, v in self._colpi.items() if v and v[-1] > ora - self.finestra}
            colpi = [t for t in self._colpi.get(chiave, []) if t > ora - self.finestra]
            if len(colpi) >= self.massimo:
                self._colpi[chiave] = colpi
                return False
            colpi.append(ora)
            self._colpi[chiave] = colpi
            return True


# --- pagine ---------------------------------------------------------------------------------------------------------

CSS_ATRIUM = """
body{background:var(--bg)}
header .in{max-width:1240px;padding-left:2rem;padding-right:2rem;box-sizing:border-box}
main.at{max-width:1240px;margin:0 auto;padding:32px 2rem 96px}
.at-nascosto{display:none!important}
.at-intro{max-width:760px;margin:24px 0 40px}
main.at form:not(.at-scrivi){display:block;margin:0}
.at-intro .occhiello{margin-bottom:14px}
.at-intro h1{font-size:44px;font-weight:500;letter-spacing:-.03em;line-height:1.1;margin:0 0 16px}
.at-intro p{font-size:19px;line-height:1.55;color:var(--muted);margin:0}
.at-scheda{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:24px 28px}
.at-campo{display:flex;flex-direction:column;gap:8px;margin:0 0 18px}
.at-campo label{font-size:15px;color:var(--muted)}
.at-campo input,.at-campo textarea{min-height:48px;box-sizing:border-box;border:1px solid var(--ctrl);border-radius:12px;padding:10px 14px;
 font:inherit;font-size:16px;background:var(--card);color:var(--fg)}
.at-campo textarea{min-height:88px;resize:vertical}
.at-tre{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;margin:40px 0 0}
.at-tre div{background:var(--soft);border-radius:20px;padding:24px;font-size:15px;line-height:1.55;color:var(--muted)}
.at-tre strong{display:block;color:var(--fg);font-size:17px;margin-bottom:6px;font-weight:600}
.at-porta{display:flex;flex-direction:column;gap:8px;margin:0 0 24px;padding:18px 20px;border:1px solid var(--line);border-radius:16px;background:var(--tint)}
.at-porta .serif{font-size:16px;line-height:1.55;white-space:pre-line;overflow-wrap:anywhere}
.at-barra{display:flex;align-items:center;gap:20px;flex-wrap:wrap;padding:16px 24px;border:1px solid var(--line);border-radius:20px;background:var(--card)}
.at-titolo{display:flex;flex-direction:column;gap:2px;min-width:220px;flex:1}
.at-titolo .occhiello{margin:0;color:var(--accent)}
.at-titolo h1{margin:0;font-size:22px;font-weight:600;letter-spacing:-.01em}
.at-volti{display:flex;align-items:center}
.at-volto{width:34px;height:34px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;color:#fff;
 font-size:13px;font-weight:600;border:2px solid var(--card);box-sizing:border-box;flex:none}
.at-volti .at-volto+.at-volto{margin-left:-8px}
.at-presenza{margin:12px 4px 0;font-size:15px;color:var(--muted);line-height:1.5;min-height:22px}
.at-presenza b{color:var(--fg);font-weight:600}
.at-solo{margin:12px 0 0;display:flex;align-items:center;gap:12px;padding:14px 18px;border-radius:16px;background:var(--tint);font-size:15px}
.at-griglia{display:flex;flex-wrap:wrap;gap:32px;align-items:flex-start;margin-top:28px}
.at-col{flex:1 1 420px;min-width:0;display:flex;flex-direction:column;gap:16px}
.at-col h2{font-size:24px;font-weight:500;letter-spacing:-.01em;margin:0}
.at-nota{font-size:14px;color:var(--muted);line-height:1.5;margin:0}
.at-lista{display:flex;flex-direction:column;gap:2px;max-height:560px;overflow:auto;padding:4px 2px}
.at-msg{display:flex;flex-direction:column;gap:4px;padding:12px 14px;border-radius:16px}
.at-msg.mio{background:var(--tint)}
.at-msg .chi{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--muted)}
.at-msg .chi b{color:var(--fg);font-weight:600}
.at-msg .testo{font-size:16px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}
.at-sis{font-size:14px;color:var(--muted);padding:6px 14px;display:flex;align-items:center;gap:8px}
.at-pallino{width:9px;height:9px;border-radius:999px;flex:none;display:inline-block}
.at-scrivi{display:flex;flex-direction:column;gap:10px}
.at-scrivi textarea{min-height:72px;box-sizing:border-box;width:100%;border:1px solid var(--ctrl);border-radius:14px;padding:12px 14px;font:inherit;font-size:16px;background:var(--card);color:var(--fg);resize:vertical}
.at-riga{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.at-oggetto{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;display:flex;flex-direction:column;gap:8px}
.at-oggetto .da{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600}
.at-oggetto .serif{font-size:16px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}
.at-oggetto .piede{font-size:13px;color:var(--muted)}
.at-fatti{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.at-fatto{display:grid;grid-template-columns:104px minmax(0,1fr);gap:16px;padding:14px 0;border-bottom:1px solid var(--line)}
.at-fatto .data{font-size:14px;color:var(--muted);font-variant-numeric:tabular-nums;padding-top:3px}
.at-fatto .serif{font-size:16px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.at-fatto .chi{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:6px}
.at-corr{margin-top:10px;padding:10px 12px;border-radius:12px;background:var(--soft);font-size:15px;line-height:1.5}
.at-corr .chi{margin-top:4px}
.at-membri{display:flex;flex-direction:column;gap:0;margin-top:12px;border-top:1px solid var(--line)}
.at-membri div{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);font-size:15px}
.at-membri small{color:var(--muted);font-size:13px}
.at-imp{margin-top:28px}
.at-imp summary{font-size:16px;color:var(--fg)}
.at-interruttore{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:44px;width:100%;
 background:transparent;border:0;padding:0;color:var(--fg);font:inherit;font-size:15px;text-align:left;cursor:pointer}
.at-interruttore .tr{width:42px;height:24px;border-radius:999px;background:var(--line);position:relative;flex:none}
.at-interruttore .tr:after{content:"";position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:999px;background:#fff;
 box-shadow:0 0 0 1px var(--ctrl);transition:left .15s}
.at-interruttore[aria-checked=true] .tr{background:var(--accent)}
.at-interruttore[aria-checked=true] .tr:after{left:21px;box-shadow:none}
.at-avviso{display:flex;gap:10px;align-items:flex-start;padding:14px 16px;border-radius:14px;background:var(--warn-bg);font-size:15px;line-height:1.5}
.at-avviso svg{flex:none;color:var(--warn);margin-top:2px}
.at-catena{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:6px;margin-top:8px}
.at-catena.rotta{color:var(--warn)}
footer.at-piede{max-width:1240px;margin:0 auto;padding:24px 2rem 48px;color:var(--muted);font-size:14px;border-top:1px solid var(--line)}
@media (max-width:640px){.at-intro h1{font-size:34px}.at-fatto{grid-template-columns:1fr}.at-barra{padding:14px 16px}}
"""

ICONA_AVVISO = ('<svg aria-hidden="true" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" '
                'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3l7 14H3z"/>'
                '<path d="M10 9v3M10 14.5v.01"/></svg>')


def _pagina(titolo: str, corpo: str, dati: str) -> bytes:
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer">
<title>{escape(titolo)} · Atrium</title>
<style>{CSS}{triade.tema_css("atrium")}{CSS_ATRIUM}</style>{triade.favicon_init("atrium")}</head>
<body data-pagina="{escape(dati)}"><header><div class="in"><a href="/" class="marchio" aria-label="Atrium, pagina iniziale">{triade.marchio_html("atrium", 24)}</a></div></header>
<main class="at">{corpo}</main>
<footer class="at-piede">Atrium {escape(__version__)} · Ciò che scrivi viene cifrato nel tuo browser: il server conserva solo testo illeggibile.
Atrium non è una consulenza legale.</footer>
<script src="/atrium/atrium.js"></script><script src="/atrium/pagina.js"></script></body></html>""".encode("utf-8")


def pagina_iniziale() -> bytes:
    corpo = f"""
<section class="at-intro">
<p class="occhiello">Atrium · lo spazio tra le tre stanze</p>
<h1>Non devi affrontarla da solo.</h1>
<p>Apri una questione e invita chi vuoi: amici, famiglia, colleghi. Parlatene, mettete in fila i fatti, portate le
risposte di Anorma e gli articoli di Nuova-Norma. Solo chi ha il link può entrare, e chi entra si vede.</p>
</section>
<section class="at-scheda" style="max-width:760px">
<div id="at-porta" class="at-porta at-nascosto" aria-live="polite">
<span class="occhiello" style="margin:0">Porterai nella questione</span>
<strong id="at-porta-titolo"></strong><span id="at-porta-testo" class="serif"></span></div>
<form id="at-nuova">
<div class="at-campo"><label for="at-titolo">Come la chiamiamo? Facoltativo: lo vedono solo i membri</label>
<input id="at-titolo" name="titolo" maxlength="120" autocomplete="off" placeholder="Per esempio: Disdette durante la malattia"></div>
<button class="btn btn-primario btn-grande" type="submit">Apri una questione</button>
<p class="at-nota" id="at-errore" role="alert" style="margin-top:12px"></p>
</form>
</section>
<div class="at-tre">
<div><strong>Cifrato nel tuo browser</strong>La chiave sta nel link e non arriva mai ai nostri server. Noi vediamo solo
testo illeggibile.</div>
<div><strong>Chi entra si vede</strong>Ogni ingresso è annunciato a tutti, con chi ha invitato chi. Nessuno legge da
invisibile.</div>
<div><strong>Niente si cancella di nascosto</strong>I fatti si correggono e la storia resta. Ogni voce porta il nome di
chi l'ha scritta.</div>
</div>"""
    return _pagina("Apri una questione", corpo, "iniziale")


def pagina_questione() -> bytes:
    corpo = f"""
<div id="at-stato" class="at-scheda at-nascosto" role="alert"></div>

<section id="at-ingresso" class="at-scheda at-nascosto" style="max-width:760px">
<p class="occhiello" style="color:var(--accent)">Atrium · questione</p>
<h1 style="font-size:32px;font-weight:500;letter-spacing:-.02em;margin:0 0 8px">Entra nella questione</h1>
<p class="at-nota" id="at-invitato" style="font-size:16px;margin:0 0 20px"></p>
<form id="at-entra">
<div class="at-campo"><label for="at-nome">Il tuo nome qui. Lo vedono solo i membri di questa questione</label>
<input id="at-nome" maxlength="40" required autocomplete="off" placeholder="Per esempio: Marta R."></div>
<div class="at-avviso" style="margin:0 0 18px">{ICONA_AVVISO}<span>Chi è già dentro vedrà che sei entrato. Quello che scrivi
resta: si può correggere, non cancellare. Nessuna app può impedire una fotografia dello schermo: scrivi pensando che
possa essere letto anche fuori. E parla dei fatti, non insultare: un insulto a una persona riconoscibile può avere
conseguenze anche qui.</span></div>
<button class="btn btn-primario btn-grande" type="submit">Entra</button>
</form>
</section>

<section id="at-stanza" class="at-nascosto">
<div class="at-barra">
<div class="at-titolo"><span class="occhiello">{triade.delta_svg(12, "var(--accent)", "vertical-align:-1px;margin-right:6px")}Atrium · questione</span>
<h1 id="at-nome-questione">Questione senza titolo</h1></div>
<div class="at-volti" id="at-volti" aria-label="Chi è nella questione"></div>
<button class="btn btn-bordo btn-piccolo" type="button" id="at-membri-btn" aria-expanded="false" aria-controls="at-membri">1 membro</button>
<button class="btn btn-primario btn-piccolo" type="button" id="at-invita">Invita qualcuno</button>
</div>
<div id="at-membri" class="at-membri at-nascosto"></div>
<p class="at-presenza" id="at-presenza" aria-live="polite"></p>
<div class="at-solo at-nascosto" id="at-non-solo"></div>

<div class="at-griglia">
<section class="at-col" aria-labelledby="at-h-stanza">
<h2 id="at-h-stanza">Parliamone</h2>
<div class="at-lista" id="at-messaggi" aria-live="polite"></div>
<form class="at-scrivi" id="at-scrivi">
<label for="at-testo" class="at-nota">Scrivi a tutti. Invio per mandare, Maiusc + Invio per andare a capo</label>
<textarea id="at-testo" maxlength="8000"></textarea>
<div class="at-riga"><button class="btn btn-primario btn-piccolo" type="submit">Invia</button></div>
</form>
</section>

<section class="at-col" aria-labelledby="at-h-fatti">
<h2 id="at-h-fatti">I fatti</h2>
<div id="at-oggetti" style="display:flex;flex-direction:column;gap:12px"></div>
<p class="at-nota">Cronologia dei fatti. Le voci non si cancellano: si correggono, e resta la storia.</p>
<ol class="at-fatti" id="at-fatti"></ol>
<form class="at-scrivi" id="at-nuovo-fatto">
<div class="at-riga">
<div class="at-campo" style="margin:0;flex:0 0 170px"><label for="at-data">Quando</label><input id="at-data" type="date" required></div>
</div>
<div class="at-campo" style="margin:0"><label for="at-fatto">Che cosa è successo</label><textarea id="at-fatto" maxlength="4000" required></textarea></div>
<div class="at-riga"><button class="btn btn-bordo btn-piccolo" type="submit">Aggiungi alla cronologia</button></div>
</form>
<p class="at-catena" id="at-catena"></p>
</section>
</div>

<details class="at-imp at-scheda">
<summary>Le tue impostazioni in questa questione</summary>
<div style="display:flex;flex-direction:column;gap:12px;margin-top:16px;max-width:620px">
<p style="margin:0">Il tuo nome qui: <b id="at-mio-nome"></b></p>
<button type="button" class="at-interruttore" role="switch" aria-checked="true" id="at-mostra">
<span><span style="display:block">Mostra dove sono e cosa scrivo</span><span class="at-nota">Se lo spegni, non vedi nemmeno gli altri.</span></span><span class="tr" aria-hidden="true"></span></button>
<div class="at-riga" style="margin-top:8px">
<button class="btn btn-bordo btn-piccolo" type="button" id="at-esci">Esci dalla questione</button>
<button class="btn btn-testo btn-piccolo at-nascosto" type="button" id="at-chiudi">Chiudi la questione per tutti</button>
</div>
<p class="at-nota" id="at-chiudi-nota"></p>
</div>
</details>
</section>"""
    return _pagina("Questione", corpo, "questione")


# --- server -------------------------------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Atrium/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # niente query string nei registri: contiene il codice del membro
        if os.environ.get("ATRIUM_SILENZIO"):
            return
        percorso = self.path.split("?", 1)[0]
        parti = percorso.split("/")
        if len(parti) > 2 and parti[1] == "q":
            parti[2] = "…"
        elif len(parti) > 3 and parti[1] == "api":
            parti[3] = "…"
        percorso = "/".join(parti)
        print(f"{self.log_date_time_string()} {self.command} {percorso} {args[1] if len(args) > 1 else ''}")

    # --- risposte -------------------------------------------------------------------------------------------------

    def _intestazioni_sicure(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                         "form-action 'self'; object-src 'none'")

    def _invia(self, stato: int, corpo: bytes, tipo: str, cache: str = "no-store"):
        self.send_response(stato)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", cache)
        self._intestazioni_sicure()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, stato: int, dati: dict):
        self._invia(stato, json.dumps(dati, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, stato: int, corpo: bytes):
        self._invia(stato, corpo, "text/html; charset=utf-8")

    def _corpo_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_CORPO:
            raise ErroreRegistro("richiesta troppo grande", 413)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ErroreRegistro("serve JSON", 415)
        try:
            d = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ErroreRegistro("JSON non valido")
        if not isinstance(d, dict):
            raise ErroreRegistro("JSON non valido")
        return d

    def _indirizzo(self) -> str:
        if os.environ.get("ATRIUM_DIETRO_PROXY"):
            avanti = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if avanti:
                return avanti
        return self.client_address[0]

    # --- GET ------------------------------------------------------------------------------------------------------

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p = url.path
        try:
            if p in STATICO:
                corpo = STATICO[p].read_bytes()
                return self._invia(200, corpo, "application/javascript; charset=utf-8", "no-cache")
            if p.startswith("/nn/") and serve_static(self, p):
                return
            if p in ("/", "/nuova"):
                return self._html(200, pagina_iniziale())
            if p.startswith("/q/"):
                stanza = p[3:].strip("/")
                if not self.server.registro.aperta(stanza):
                    return self._html(404, _pagina("Questione non trovata", """<section class="at-intro">
<p class="occhiello">Atrium</p><h1>Questa questione non c'è.</h1>
<p>Il link potrebbe essere incompleto, oppure chi l'ha aperta l'ha chiusa: in quel caso tutto ciò che conteneva è stato
cancellato. <a href="/">Apri una questione nuova</a>.</p></section>""", "assente"))
                return self._html(200, pagina_questione())
            parti = p.strip("/").split("/")
            if len(parti) == 4 and parti[0] == "api" and parti[1] == "stanze" and parti[3] == "flusso":
                return self._flusso(parti[2], urllib.parse.parse_qs(url.query))
            if p == "/salute":
                return self._json(200, {"ok": True, "versione": __version__})
            return self._html(404, _pagina("Pagina non trovata", """<section class="at-intro"><h1>Pagina non trovata.</h1>
<p><a href="/">Torna alla pagina iniziale</a>.</p></section>""", "assente"))
        except ErroreRegistro as e:
            self._json(e.stato, {"errore": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _flusso(self, stanza: str, q: dict):
        """Il flusso in tempo reale di una questione (Server-Sent Events): prima gli eventi dopo «dopo», poi le
        presenze attuali (se il collegamento mostra la propria), poi tutto cio che arriva, con un battito ogni 15 s."""
        reg, sm = self.server.registro, self.server.smistatore
        segreto = (q.get("membro") or [""])[0]
        dopo = int((q.get("dopo") or ["0"])[0] or 0) if (q.get("dopo") or ["0"])[0].isdigit() else 0
        presenza = (q.get("presenza") or ["1"])[0] != "0"
        if not reg.aperta(stanza):
            return self._json(410, {"errore": "questione chiusa o inesistente"})
        if not reg.e_membro(stanza, segreto):
            return self._json(403, {"errore": "per leggere bisogna essere entrati nella questione"})
        isc = sm.iscrivi(stanza, impronta_segreto(segreto), presenza)
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self._intestazioni_sicure()
            self.end_headers()

            def manda(tipo: str, dati: dict):
                self.wfile.write(f"event: {tipo}\ndata: {json.dumps(dati, separators=(',', ':'))}\n\n".encode("utf-8"))

            manda("benvenuto", {"slot": isc.slot, "presenza": presenza})
            ultimo = dopo
            while True:
                pagina = reg.eventi(stanza, ultimo, 500)
                for ev in pagina:
                    manda("evento", evento_json(ev))
                    ultimo = ev["seq"]
                if len(pagina) < 500:
                    break
            manda("pronto", {"ultimo": ultimo})
            if presenza:
                for pr in sm.presenze_attuali(stanza):
                    if pr["slot"] != isc.slot:
                        manda("presenza", pr)
            self.wfile.flush()
            while True:
                m = isc.prossimo(BATTITO)
                if m is None:
                    self.wfile.write(b": battito\n\n")
                elif m is FINE:
                    break
                elif m["t"] == "evento":
                    if m["ev"]["seq"] > ultimo:
                        manda("evento", m["ev"])
                        ultimo = m["ev"]["seq"]
                elif m["t"] == "presenza":
                    if m["slot"] != isc.slot:
                        manda("presenza", {"slot": m["slot"], "dati": m["dati"]})
                elif m["t"] == "via":
                    manda("via", {"slot": m["slot"]})
                elif m["t"] == "chiusa":
                    manda("chiusa", {})
                    break
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            sm.disiscrivi(isc)

    # --- POST -----------------------------------------------------------------------------------------------------

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        parti = p.strip("/").split("/")
        reg, sm = self.server.registro, self.server.smistatore
        try:
            if parti == ["api", "stanze"]:
                if not self.server.limite_stanze.consenti(self._indirizzo()):
                    raise ErroreRegistro("troppe questioni aperte da qui in poco tempo: riprova tra un'ora", 429)
                self._corpo_json()
                stanza, amministrazione = reg.crea_stanza()
                return self._json(201, {"stanza": stanza, "amministrazione": amministrazione})
            if len(parti) != 4 or parti[0] != "api" or parti[1] != "stanze":
                raise ErroreRegistro("indirizzo sconosciuto", 404)
            stanza, azione = parti[2], parti[3]
            d = self._corpo_json()
            if azione == "chiudi":
                reg.chiudi(stanza, str(d.get("amministrazione") or ""))
                sm.chiusa(stanza)
                return self._json(200, {"chiusa": True})
            segreto = str(d.get("membro") or "")
            chiave_limite = stanza + "|" + impronta_segreto(segreto)[:16]
            if azione == "presenza":
                if not self.server.limite_presenza.consenti(chiave_limite):
                    raise ErroreRegistro("troppi aggiornamenti", 429)
                dati = da_b64u(str(d.get("dati") or ""))
                if not (28 <= len(dati) <= 4096 + 64):
                    raise ErroreRegistro("presenza non valida")
                if not reg.e_membro(stanza, segreto):
                    raise ErroreRegistro("per mostrarsi bisogna essere entrati", 403)
                if not sm.slot_di(stanza, str(d.get("slot") or ""), impronta_segreto(segreto)):
                    raise ErroreRegistro("collegamento senza presenza: chi non si mostra non vede gli altri", 409)
                sm.presenza(stanza, str(d["slot"]), b64u(dati))
                return self._json(200, {"ok": True})
            if not self.server.limite_eventi.consenti(chiave_limite):
                raise ErroreRegistro("troppi messaggi in poco tempo: aspetta un momento", 429)
            dati = da_b64u(str(d.get("dati") or ""))
            if azione == "ingresso":
                ev = reg.entra(stanza, segreto, dati)
            elif azione == "eventi":
                ev = reg.aggiungi(stanza, segreto, dati)
            elif azione == "uscita":
                ev = reg.esci(stanza, segreto, dati)
            else:
                raise ErroreRegistro("azione sconosciuta", 404)
            sm.evento(stanza, evento_json(ev))
            if azione == "uscita":
                sm.espelli(stanza, impronta_segreto(segreto))
            return self._json(201, {"seq": ev["seq"], "impronta": ev["impronta"]})
        except ErroreRegistro as e:
            self._json(e.stato, {"errore": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, indirizzo, gestore=Handler, registro: Registro | None = None,
                 smistatore: Smistatore | None = None):
        super().__init__(indirizzo, gestore)
        self.registro = registro or Registro(percorso_db())
        self.smistatore = smistatore or da_ambiente()
        self.limite_stanze = Limitatore(int(os.environ.get("ATRIUM_STANZE_ORA", "20")), 3600)
        self.limite_eventi = Limitatore(120, 60)
        self.limite_presenza = Limitatore(90, 60)

    def server_close(self):
        super().server_close()
        self.smistatore.ferma()


def serve(porta: int = 8768, apri_browser: bool = True, host: str = "127.0.0.1") -> None:
    server = Server((host, porta))
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{porta}/"
    print(f"Atrium {__version__} su {url}  (archivio: {server.registro.percorso})")
    print("Chiudi con Ctrl+C.")
    if apri_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
