"""Registro e smistatore di Atrium, senza rete."""

import os
import tempfile
import unittest

from atrium.registro import ErroreRegistro, Registro, impronta_evento
from atrium.smistatore import FINE, Smistatore

DATI = b"\x01" * 300
SEG_A, SEG_B = "a" * 32, "b" * 32


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registro(os.path.join(self.tmp.name, "a.sqlite"))
        self.stanza, self.amm = self.reg.crea_stanza()

    def tearDown(self):
        self.reg.chiudi_connessione()
        self.tmp.cleanup()

    def test_identificativi_casuali(self):
        altra, amm = self.reg.crea_stanza()
        self.assertNotEqual(altra, self.stanza)
        self.assertGreaterEqual(len(self.stanza), 22)       # 128 bit
        self.assertTrue(self.reg.aperta(self.stanza))
        self.assertFalse(self.reg.aperta("non-esiste"))

    def test_bisogna_entrare_per_scrivere(self):
        with self.assertRaises(ErroreRegistro) as e:
            self.reg.aggiungi(self.stanza, SEG_A, DATI)
        self.assertEqual(e.exception.stato, 403)
        self.assertFalse(self.reg.e_membro(self.stanza, SEG_A))
        self.reg.entra(self.stanza, SEG_A, DATI)
        self.assertTrue(self.reg.e_membro(self.stanza, SEG_A))
        ev = self.reg.aggiungi(self.stanza, SEG_A, DATI)
        self.assertEqual(ev["seq"], 2)

    def test_doppio_ingresso_rifiutato_ma_rientro_possibile(self):
        self.reg.entra(self.stanza, SEG_A, DATI)
        with self.assertRaises(ErroreRegistro) as e:
            self.reg.entra(self.stanza, SEG_A, DATI)
        self.assertEqual(e.exception.stato, 409)
        self.reg.esci(self.stanza, SEG_A, DATI)
        self.assertFalse(self.reg.e_membro(self.stanza, SEG_A))
        with self.assertRaises(ErroreRegistro):
            self.reg.aggiungi(self.stanza, SEG_A, DATI)
        self.reg.entra(self.stanza, SEG_A, DATI)      # rientro: nuovo evento d'ingresso
        self.assertEqual([e["seq"] for e in self.reg.eventi(self.stanza)], [1, 2, 3])

    def test_catena_delle_impronte(self):
        self.reg.entra(self.stanza, SEG_A, DATI)
        self.reg.entra(self.stanza, SEG_B, b"\x02" * 300)
        self.reg.aggiungi(self.stanza, SEG_A, b"\x03" * 1100)
        evs = self.reg.eventi(self.stanza)
        self.assertEqual(evs[0]["prec"], "0" * 64)
        for a, b in zip(evs, evs[1:]):
            self.assertEqual(b["prec"], a["impronta"])
        e = evs[1]
        self.assertEqual(impronta_evento(self.stanza, e["seq"], e["ts"], e["prec"], e["dati"]), e["impronta"])
        self.assertEqual(self.reg.verifica_catena(self.stanza), (True, None))
        # un evento alterato a mano si vede
        self.reg._con.execute("UPDATE eventi SET dati = ? WHERE stanza = ? AND seq = 2", (b"\x09" * 300, self.stanza))
        self.assertEqual(self.reg.verifica_catena(self.stanza), (False, 2))

    def test_dimensioni(self):
        self.reg.entra(self.stanza, SEG_A, DATI)
        with self.assertRaises(ErroreRegistro):
            self.reg.aggiungi(self.stanza, SEG_A, b"x" * 10)
        with self.assertRaises(ErroreRegistro) as e:
            self.reg.aggiungi(self.stanza, SEG_A, b"x" * (70 * 1024))
        self.assertEqual(e.exception.stato, 413)

    def test_chiusura_cancella_tutto(self):
        self.reg.entra(self.stanza, SEG_A, DATI)
        with self.assertRaises(ErroreRegistro) as e:
            self.reg.chiudi(self.stanza, "sbagliato")
        self.assertEqual(e.exception.stato, 403)
        self.reg.chiudi(self.stanza, self.amm)
        self.assertFalse(self.reg.aperta(self.stanza))
        self.assertEqual(self.reg.eventi(self.stanza), [])
        self.assertFalse(self.reg.e_membro(self.stanza, SEG_A))
        with self.assertRaises(ErroreRegistro) as e:
            self.reg.entra(self.stanza, SEG_B, DATI)
        self.assertEqual(e.exception.stato, 410)

    def test_il_segreto_non_e_salvato(self):
        self.reg.entra(self.stanza, SEG_A, DATI)
        righe = self.reg._con.execute("SELECT membro FROM membri").fetchall()
        self.assertNotIn(SEG_A, [r[0] for r in righe])


class TestSmistatore(unittest.TestCase):
    def test_reciprocita_della_presenza(self):
        sm = Smistatore()
        visibile = sm.iscrivi("s", "m1", presenza=True)
        nascosto = sm.iscrivi("s", "m2", presenza=False)
        sm.presenza("s", visibile.slot, "dati")
        sm.evento("s", {"seq": 1})
        self.assertEqual(visibile.prossimo(0.1)["t"], "presenza")
        self.assertEqual(visibile.prossimo(0.1)["t"], "evento")
        self.assertEqual(nascosto.prossimo(0.1)["t"], "evento")     # gli eventi si, la presenza no
        self.assertIsNone(nascosto.prossimo(0.05))
        self.assertIsNone(sm.slot_di("s", nascosto.slot, "m2"))      # chi non si mostra non puo inviare presenza
        self.assertIs(sm.slot_di("s", visibile.slot, "m1"), visibile)
        self.assertIsNone(sm.slot_di("s", visibile.slot, "m2"))      # lo slot e legato al membro

    def test_presenza_scade_e_sparisce_alla_chiusura(self):
        sm = Smistatore()
        a = sm.iscrivi("s", "m1", presenza=True)
        b = sm.iscrivi("s", "m2", presenza=True)
        sm.presenza("s", a.slot, "x")
        self.assertEqual(len(sm.presenze_attuali("s")), 1)
        sm.disiscrivi(a)
        self.assertEqual(sm.presenze_attuali("s"), [])
        msgs = [b.prossimo(0.1), b.prossimo(0.1)]
        self.assertEqual([m["t"] for m in msgs], ["presenza", "via"])

    def test_espulsione_e_chiusura(self):
        sm = Smistatore()
        a = sm.iscrivi("s", "m1", presenza=False)
        b = sm.iscrivi("s", "m2", presenza=False)
        sm.espelli("s", "m1")
        self.assertIs(a.prossimo(0.1), FINE)
        self.assertIsNone(b.prossimo(0.05))
        sm.chiusa("s")
        self.assertEqual(b.prossimo(0.1)["t"], "chiusa")
        self.assertIs(b.prossimo(0.1), FINE)


if __name__ == "__main__":
    unittest.main()
