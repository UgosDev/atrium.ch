"""Il registro delle questioni: stanze, membri ed eventi cifrati, in SQLite.

Il server non legge niente di cio che conserva. Ogni evento e un blocco cifrato nel browser (AES-GCM con la chiave della
stanza); qui ha solo un numero d'ordine, un'ora e un'impronta. Le impronte formano una catena: ognuna dipende dalla
precedente, quindi un evento tolto, spostato o alterato si vede (lo controllano anche i browser dei membri).

Regole:
- nessun evento si modifica o si cancella: le correzioni sono eventi nuovi. Solo chi ha aperto la questione puo
  chiuderla, e allora sparisce tutto (eventi e membri), non solo una parte;
- i membri sono conosciuti solo per l'impronta del loro segreto (un codice casuale del browser), mai per nome:
  il nome sta dentro l'evento d'ingresso, cifrato;
- per leggere e scrivere bisogna essere entrati: l'ingresso e un evento che tutti vedono, quindi nessuno legge
  da invisibile.

Per la produzione la stessa interfaccia andra su PostgreSQL (tabella che si puo solo allungare); vedi README.
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import sqlite3
import threading
from pathlib import Path

INIZIO = "0" * 64
MIN_DATI = 12 + 16 + 4       # vettore iniziale, etichetta di autenticazione, almeno la lunghezza del testo
MAX_DATI = 66 * 1024         # il formato piu grande e 64 KiB, piu il vettore e l'etichetta

SCHEMA = """
CREATE TABLE IF NOT EXISTS stanze (
  id TEXT PRIMARY KEY,
  creata TEXT NOT NULL,
  amministrazione TEXT NOT NULL,
  chiusa TEXT
);
CREATE TABLE IF NOT EXISTS membri (
  stanza TEXT NOT NULL,
  membro TEXT NOT NULL,
  entrato INTEGER NOT NULL,
  uscito INTEGER,
  PRIMARY KEY (stanza, membro)
);
CREATE TABLE IF NOT EXISTS eventi (
  stanza TEXT NOT NULL,
  seq INTEGER NOT NULL,
  ts TEXT NOT NULL,
  dati BLOB NOT NULL,
  prec TEXT NOT NULL,
  impronta TEXT NOT NULL,
  PRIMARY KEY (stanza, seq)
);
"""


class ErroreRegistro(Exception):
    """Errore con un messaggio da mostrare e lo stato HTTP corrispondente."""

    def __init__(self, messaggio: str, stato: int = 400):
        super().__init__(messaggio)
        self.stato = stato


def impronta_segreto(segreto: str) -> str:
    return hashlib.sha256(("atrium-membro|" + segreto).encode("utf-8")).hexdigest()


def impronta_evento(stanza: str, seq: int, ts: str, prec: str, dati: bytes) -> str:
    return hashlib.sha256(f"{stanza}|{seq}|{ts}|{prec}|".encode("utf-8") + dati).hexdigest()


def _ora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valida_id(stanza: str) -> None:
    if not stanza or len(stanza) > 64 or not all(c.isalnum() or c in "-_" for c in stanza):
        raise ErroreRegistro("questione non trovata", 404)


def _valida_segreto(segreto: str) -> None:
    if not isinstance(segreto, str) or not (20 <= len(segreto) <= 128):
        raise ErroreRegistro("codice del membro non valido", 403)


def _valida_dati(dati: bytes) -> None:
    if not isinstance(dati, (bytes, bytearray)) or not (MIN_DATI <= len(dati) <= MAX_DATI):
        raise ErroreRegistro("contenuto cifrato non valido o troppo grande", 413 if dati and len(dati) > MAX_DATI else 400)


class Registro:
    def __init__(self, percorso: str | Path):
        self.percorso = str(percorso)
        if self.percorso != ":memory:":
            Path(self.percorso).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(self.percorso, check_same_thread=False, isolation_level=None)
        self._lock = threading.Lock()
        try:
            self._con.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self._con.execute("PRAGMA busy_timeout=10000")
        self._con.executescript(SCHEMA)

    def chiudi_connessione(self) -> None:
        with self._lock:
            self._con.close()

    # --- stanze -------------------------------------------------------------------------------------------------

    def crea_stanza(self) -> tuple[str, str]:
        """Una questione nuova. Restituisce l'identificativo (128 bit casuali) e il codice di amministrazione,
        che serve solo a chiuderla. Del codice si conserva l'impronta."""
        stanza = secrets.token_urlsafe(16)
        amministrazione = secrets.token_urlsafe(24)
        with self._lock:
            self._con.execute("INSERT INTO stanze (id, creata, amministrazione) VALUES (?, ?, ?)",
                              (stanza, _ora(), hashlib.sha256(amministrazione.encode()).hexdigest()))
        return stanza, amministrazione

    def aperta(self, stanza: str) -> bool:
        try:
            _valida_id(stanza)
        except ErroreRegistro:
            return False
        with self._lock:
            r = self._con.execute("SELECT chiusa FROM stanze WHERE id = ?", (stanza,)).fetchone()
        return bool(r) and r[0] is None

    def _richiedi_aperta(self, stanza: str) -> None:
        _valida_id(stanza)
        r = self._con.execute("SELECT chiusa FROM stanze WHERE id = ?", (stanza,)).fetchone()
        if not r:
            raise ErroreRegistro("questione non trovata", 404)
        if r[0] is not None:
            raise ErroreRegistro("questione chiusa", 410)

    def chiudi(self, stanza: str, amministrazione: str) -> None:
        """Chiude la questione per tutti: cancella eventi e membri. Resta solo la riga della stanza, segnata come
        chiusa, perche il suo identificativo non venga riusato."""
        _valida_id(stanza)
        attesa = hashlib.sha256((amministrazione or "").encode()).hexdigest()
        with self._lock:
            r = self._con.execute("SELECT amministrazione, chiusa FROM stanze WHERE id = ?", (stanza,)).fetchone()
            if not r:
                raise ErroreRegistro("questione non trovata", 404)
            if r[1] is not None:
                raise ErroreRegistro("questione già chiusa", 410)
            if not secrets.compare_digest(r[0], attesa):
                raise ErroreRegistro("solo chi ha aperto la questione può chiuderla", 403)
            self._con.execute("BEGIN IMMEDIATE")
            try:
                self._con.execute("DELETE FROM eventi WHERE stanza = ?", (stanza,))
                self._con.execute("DELETE FROM membri WHERE stanza = ?", (stanza,))
                self._con.execute("UPDATE stanze SET chiusa = ?, amministrazione = '' WHERE id = ?", (_ora(), stanza))
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise

    # --- membri ---------------------------------------------------------------------------------------------------

    def e_membro(self, stanza: str, segreto: str) -> bool:
        try:
            _valida_id(stanza)
            _valida_segreto(segreto)
        except ErroreRegistro:
            return False
        with self._lock:
            r = self._con.execute("SELECT uscito FROM membri m JOIN stanze s ON s.id = m.stanza "
                                  "WHERE m.stanza = ? AND m.membro = ? AND s.chiusa IS NULL",
                                  (stanza, impronta_segreto(segreto))).fetchone()
        return bool(r) and r[0] is None

    def numero_membri(self, stanza: str) -> int:
        with self._lock:
            return self._con.execute("SELECT COUNT(*) FROM membri WHERE stanza = ? AND uscito IS NULL",
                                     (stanza,)).fetchone()[0]

    # --- eventi ---------------------------------------------------------------------------------------------------

    def _accoda(self, stanza: str, dati: bytes) -> dict:
        """Aggiunge un evento in coda alla catena. Va chiamato dentro una transazione, con il lock preso."""
        ultimo = self._con.execute("SELECT seq, impronta FROM eventi WHERE stanza = ? ORDER BY seq DESC LIMIT 1",
                                   (stanza,)).fetchone()
        seq, prec = (ultimo[0] + 1, ultimo[1]) if ultimo else (1, INIZIO)
        ts = _ora()
        impronta = impronta_evento(stanza, seq, ts, prec, bytes(dati))
        self._con.execute("INSERT INTO eventi (stanza, seq, ts, dati, prec, impronta) VALUES (?, ?, ?, ?, ?, ?)",
                          (stanza, seq, ts, bytes(dati), prec, impronta))
        return {"seq": seq, "ts": ts, "dati": bytes(dati), "prec": prec, "impronta": impronta}

    def _in_transazione(self, funzione):
        with self._lock:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                risultato = funzione()
                self._con.execute("COMMIT")
                return risultato
            except Exception:
                self._con.execute("ROLLBACK")
                raise

    def entra(self, stanza: str, segreto: str, dati: bytes) -> dict:
        """L'ingresso di un membro: registra l'impronta del suo segreto e accoda l'evento d'ingresso (cifrato,
        con il nome scelto per questa stanza). Chi era uscito puo rientrare, con un nuovo ingresso visibile a tutti."""
        _valida_segreto(segreto)
        _valida_dati(dati)
        m = impronta_segreto(segreto)

        def fai():
            self._richiedi_aperta(stanza)
            r = self._con.execute("SELECT uscito FROM membri WHERE stanza = ? AND membro = ?", (stanza, m)).fetchone()
            if r and r[0] is None:
                raise ErroreRegistro("sei già entrato in questa questione", 409)
            ev = self._accoda(stanza, dati)
            self._con.execute("INSERT INTO membri (stanza, membro, entrato, uscito) VALUES (?, ?, ?, NULL) "
                              "ON CONFLICT(stanza, membro) DO UPDATE SET entrato = excluded.entrato, uscito = NULL",
                              (stanza, m, ev["seq"]))
            return ev
        return self._in_transazione(fai)

    def aggiungi(self, stanza: str, segreto: str, dati: bytes) -> dict:
        _valida_segreto(segreto)
        _valida_dati(dati)
        m = impronta_segreto(segreto)

        def fai():
            self._richiedi_aperta(stanza)
            r = self._con.execute("SELECT uscito FROM membri WHERE stanza = ? AND membro = ?", (stanza, m)).fetchone()
            if not r or r[0] is not None:
                raise ErroreRegistro("per scrivere bisogna essere entrati nella questione", 403)
            return self._accoda(stanza, dati)
        return self._in_transazione(fai)

    def esci(self, stanza: str, segreto: str, dati: bytes) -> dict:
        """L'uscita e un evento come gli altri (cifrato, visibile a tutti). Cio che il membro ha scritto resta."""
        _valida_segreto(segreto)
        _valida_dati(dati)
        m = impronta_segreto(segreto)

        def fai():
            self._richiedi_aperta(stanza)
            r = self._con.execute("SELECT uscito FROM membri WHERE stanza = ? AND membro = ?", (stanza, m)).fetchone()
            if not r or r[0] is not None:
                raise ErroreRegistro("non sei dentro questa questione", 403)
            ev = self._accoda(stanza, dati)
            self._con.execute("UPDATE membri SET uscito = ? WHERE stanza = ? AND membro = ?", (ev["seq"], stanza, m))
            return ev
        return self._in_transazione(fai)

    def eventi(self, stanza: str, dopo: int = 0, limite: int = 1000) -> list[dict]:
        _valida_id(stanza)
        with self._lock:
            righe = self._con.execute("SELECT seq, ts, dati, prec, impronta FROM eventi WHERE stanza = ? AND seq > ? "
                                      "ORDER BY seq LIMIT ?", (stanza, max(0, int(dopo)), int(limite))).fetchall()
        return [{"seq": s, "ts": t, "dati": bytes(d), "prec": p, "impronta": i} for s, t, d, p, i in righe]

    def verifica_catena(self, stanza: str) -> tuple[bool, int | None]:
        """Ricalcola la catena delle impronte. (True, None) se e integra, altrimenti (False, primo seq sbagliato)."""
        prec, atteso = INIZIO, 1
        for ev in self.eventi(stanza, 0, 10 ** 9):
            if ev["seq"] != atteso or ev["prec"] != prec or \
                    impronta_evento(stanza, ev["seq"], ev["ts"], ev["prec"], ev["dati"]) != ev["impronta"]:
                return False, ev["seq"]
            prec, atteso = ev["impronta"], atteso + 1
        return True, None
