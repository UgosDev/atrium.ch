"""Il sito e l'API di Atrium: pagine, ingresso, eventi, flusso in tempo reale, presenza reciproca, chiusura."""

import base64
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

os.environ.setdefault("ATRIUM_SILENZIO", "1")

from atrium import web  # noqa: E402
from atrium.porta import link_porta, pulisci  # noqa: E402
from atrium.registro import Registro  # noqa: E402
from atrium.smistatore import Smistatore  # noqa: E402


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


DATI = b64(b"\x07" * 300)
SEG_A, SEG_B, SEG_C = "A" * 32, "B" * 32, "C" * 32


class Flusso:
    """Lettore minimo di Server-Sent Events in un filo a parte."""

    def __init__(self, url):
        self.eventi = []
        self.r = urllib.request.urlopen(url, timeout=10)
        self.filo = threading.Thread(target=self._leggi, daemon=True)
        self.filo.start()

    def _leggi(self):
        tipo = None
        try:
            for riga in self.r:
                riga = riga.decode().rstrip("\n")
                if riga.startswith("event: "):
                    tipo = riga[7:]
                elif riga.startswith("data: "):
                    self.eventi.append((tipo, json.loads(riga[6:])))
        except Exception:
            pass

    def aspetta(self, tipo, n=1, attesa=5.0):
        fine = time.time() + attesa
        while time.time() < fine:
            trovati = [d for t, d in self.eventi if t == tipo]
            if len(trovati) >= n:
                return trovati
            time.sleep(0.02)
        raise AssertionError(f"non arrivato: {tipo} x{n}; ricevuti {[t for t, _ in self.eventi]}")

    def chiudi(self):
        try:
            self.r.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.r.close()


class TestSito(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.reg = Registro(os.path.join(cls.tmp.name, "atrium.sqlite"))
        cls.server = web.Server(("127.0.0.1", 0), web.Handler, registro=cls.reg, smistatore=Smistatore())
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.reg.chiudi_connessione()
        cls.tmp.cleanup()

    def get(self, percorso):
        try:
            with urllib.request.urlopen(self.base + percorso, timeout=10) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def post(self, percorso, dati):
        req = urllib.request.Request(self.base + percorso, data=json.dumps(dati).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def nuova(self):
        st, d = self.post("/api/stanze", {})
        self.assertEqual(st, 201)
        return d["stanza"], d["amministrazione"]

    def test_pagine(self):
        st, html, h = self.get("/")
        self.assertEqual(st, 200)
        self.assertIn("Apri una questione", html)
        self.assertIn("#5c4e40", html)                  # la pietra dell'Atrium
        self.assertIn('aria-label="Atrium"', html)
        self.assertEqual(h.get("Referrer-Policy"), "no-referrer")
        self.assertIn("frame-ancestors 'none'", h.get("Content-Security-Policy", ""))
        stanza, _ = self.nuova()
        st, html, _ = self.get("/q/" + stanza)
        self.assertEqual(st, 200)
        self.assertIn('data-pagina="questione"', html)
        st, html, _ = self.get("/q/inesistente")
        self.assertEqual(st, 404)
        st, js, _ = self.get("/atrium/atrium.js")
        self.assertEqual(st, 200)
        self.assertIn("window.Atrium", js)
        st, _, _ = self.get("/nn/favicon.js")
        self.assertEqual(st, 200)

    def test_percorso_completo(self):
        stanza, amm = self.nuova()
        # senza ingresso non si legge e non si scrive
        st, _, _ = self.get(f"/api/stanze/{stanza}/flusso?membro={SEG_A}")
        self.assertEqual(st, 403)
        st, _ = self.post(f"/api/stanze/{stanza}/eventi", {"membro": SEG_A, "dati": DATI})
        self.assertEqual(st, 403)
        # ingresso di A, poi flusso con presenza
        st, d = self.post(f"/api/stanze/{stanza}/ingresso", {"membro": SEG_A, "dati": DATI})
        self.assertEqual((st, d["seq"]), (201, 1))
        fa = Flusso(f"{self.base}/api/stanze/{stanza}/flusso?membro={SEG_A}&dopo=0&presenza=1")
        slot_a = fa.aspetta("benvenuto")[0]["slot"]
        fa.aspetta("evento")
        fa.aspetta("pronto")
        # B entra senza mostrarsi: A vede l'ingresso, B non riceve presenze e non puo inviarne
        self.post(f"/api/stanze/{stanza}/ingresso", {"membro": SEG_B, "dati": DATI})
        fb = Flusso(f"{self.base}/api/stanze/{stanza}/flusso?membro={SEG_B}&dopo=0&presenza=0")
        slot_b = fb.aspetta("benvenuto")[0]["slot"]
        self.assertEqual(len(fb.aspetta("evento", 2)), 2)
        self.assertEqual(len(fa.aspetta("evento", 2)), 2)
        st, d = self.post(f"/api/stanze/{stanza}/presenza", {"membro": SEG_B, "slot": slot_b, "dati": DATI})
        self.assertEqual(st, 409)
        st, _ = self.post(f"/api/stanze/{stanza}/presenza", {"membro": SEG_B, "slot": slot_a, "dati": DATI})
        self.assertEqual(st, 409)                    # lo slot di A non si puo usare con il codice di B
        # C entra e si mostra: riceve la presenza di A, B no
        st, _ = self.post(f"/api/stanze/{stanza}/presenza", {"membro": SEG_A, "slot": slot_a, "dati": DATI})
        self.assertEqual(st, 200)
        self.post(f"/api/stanze/{stanza}/ingresso", {"membro": SEG_C, "dati": DATI})
        fc = Flusso(f"{self.base}/api/stanze/{stanza}/flusso?membro={SEG_C}&dopo=0&presenza=1")
        self.assertEqual(fc.aspetta("presenza")[0]["slot"], slot_a)
        time.sleep(0.2)
        self.assertEqual([d for t, d in fb.eventi if t == "presenza"], [])
        # un messaggio arriva a tutti, in tempo reale, una volta sola
        st, d = self.post(f"/api/stanze/{stanza}/eventi", {"membro": SEG_C, "dati": DATI})
        self.assertEqual((st, d["seq"]), (201, 4))
        for f in (fa, fb, fc):
            seqs = [e["seq"] for e in f.aspetta("evento", 4)]
            self.assertEqual(seqs[:4], [1, 2, 3, 4])
        # ripresa dopo un'interruzione: solo gli eventi mancanti
        fr = Flusso(f"{self.base}/api/stanze/{stanza}/flusso?membro={SEG_B}&dopo=3&presenza=0")
        self.assertEqual([e["seq"] for e in fr.aspetta("evento")], [4])
        fr.chiudi()
        # C esce: il suo flusso si chiude, poi non puo piu scrivere
        st, _ = self.post(f"/api/stanze/{stanza}/uscita", {"membro": SEG_C, "dati": DATI})
        self.assertEqual(st, 201)
        st, _ = self.post(f"/api/stanze/{stanza}/eventi", {"membro": SEG_C, "dati": DATI})
        self.assertEqual(st, 403)
        fc.filo.join(3)
        self.assertFalse(fc.filo.is_alive())
        # la catena ricevuta torna
        evs = fa.aspetta("evento", 5)
        for a, b in zip(evs, evs[1:]):
            self.assertEqual(b["prec"], a["impronta"])
        # chiusura: solo con il codice di amministrazione, e arriva a tutti
        st, _ = self.post(f"/api/stanze/{stanza}/chiudi", {"amministrazione": "no"})
        self.assertEqual(st, 403)
        st, _ = self.post(f"/api/stanze/{stanza}/chiudi", {"amministrazione": amm})
        self.assertEqual(st, 200)
        fa.aspetta("chiusa")
        fb.aspetta("chiusa")
        st, _, _ = self.get("/q/" + stanza)
        self.assertEqual(st, 404)
        for f in (fa, fb):
            f.chiudi()

    def test_errori(self):
        stanza, _ = self.nuova()
        st, d = self.post(f"/api/stanze/{stanza}/ingresso", {"membro": "corto", "dati": DATI})
        self.assertEqual(st, 403)
        st, d = self.post(f"/api/stanze/{stanza}/ingresso", {"membro": SEG_A, "dati": "%%%"})
        self.assertEqual(st, 400)
        st, d = self.post(f"/api/stanze/{stanza}/sconosciuta", {"membro": SEG_A, "dati": DATI})
        self.assertEqual(st, 404)
        req = urllib.request.Request(self.base + "/api/stanze", data=b"x", method="POST",
                                     headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(e.exception.code, 415)

    def test_limite_di_creazione(self):
        lim = web.Limitatore(2, 60)
        self.assertTrue(lim.consenti("x"))
        self.assertTrue(lim.consenti("x"))
        self.assertFalse(lim.consenti("x"))
        self.assertTrue(lim.consenti("y"))


class TestPorta(unittest.TestCase):
    def test_link(self):
        url = link_porta({"prodotto": "anorma", "titolo": "Posso essere licenziato?", "testo": "x" * 5000,
                          "url": "javascript:alert(1)"}, "https://atrium.example")
        self.assertTrue(url.startswith("https://atrium.example/#o="))
        o = json.loads(base64.urlsafe_b64decode(url.split("#o=")[1] + "=="))
        self.assertEqual(len(o["testo"]), 1800)
        self.assertNotIn("url", o)
        self.assertEqual(pulisci({"prodotto": "altro", "titolo": "t"})["prodotto"], "anorma")

    def test_riquadro_dei_prodotti(self):
        from nn import triade
        html = triade.porta_atrium_html({"prodotto": "ppatos", "titolo": "<b>x</b>", "testo": "riga 1\nriga 2"},
                                        "Rivedila con qualcuno", "Testo", "Invita", base="http://a.example")
        self.assertIn('class="porta-atrium"', html)
        self.assertIn('href="http://a.example/#o=', html)
        self.assertNotIn("<b>x</b>", html)
        o = json.loads(base64.urlsafe_b64decode(html.split("#o=")[1].split('"')[0] + "=="))
        self.assertEqual(o["testo"], "riga 1\nriga 2")          # gli a capo del testo restano
        self.assertEqual(triade.porta_atrium_html({"titolo": "t"}, "a", "b", "c", base=""), "")
        self.assertIn('"sitoAtrium"', triade.copia_init("anorma"))


if __name__ == "__main__":
    unittest.main()
