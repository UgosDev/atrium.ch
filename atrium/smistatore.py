"""Lo smistatore: porta in tempo reale eventi e presenza a chi e collegato a una questione.

Il server fa da centralino cieco: inoltra blocchi cifrati senza leggerli.

- Gli eventi (messaggi, fatti, ingressi...) sono gia salvati nel registro: qui si avvisano solo i collegati.
- La presenza (chi c'e, dove, se scrive) non si salva mai: resta in memoria finche viene rinnovata (ogni 15 secondi
  dal browser) e scade dopo SCADENZA_PRESENZA secondi. E cifrata come il resto.
- Reciprocita: chi si collega senza presenza non riceve quella degli altri e non puo inviarne. Nessuno vede da
  invisibile chi invece si mostra.

Due versioni:
- Smistatore: in memoria, un solo processo (sviluppo, prova, piccola installazione).
- SmistatoreValkey: piu processi o server, collegati da Valkey/Redis Pub/Sub (ATRIUM_VALKEY_URL). Valkey non salva
  niente: va avviato senza salvataggio su disco (save "" e appendonly no), in rete privata, con TLS e utenti ACL.
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import threading
import time

SCADENZA_PRESENZA = 40       # secondi; il browser rinnova ogni 15
CODA_MASSIMA = 2000          # messaggi in attesa per collegamento; oltre, il collegamento e chiuso e il browser riparte

FINE = object()              # segnale di chiusura di un collegamento


class Iscrizione:
    """Un collegamento aperto (una scheda del browser) a una questione."""

    def __init__(self, stanza: str, membro: str, presenza: bool):
        self.stanza = stanza
        self.membro = membro             # impronta del segreto, mai il segreto
        self.presenza = presenza
        self.slot = secrets.token_urlsafe(9)   # identificativo opaco della presenza di questo collegamento
        self.coda: queue.Queue = queue.Queue(maxsize=CODA_MASSIMA)
        self.chiusa = False

    def consegna(self, messaggio) -> None:
        if self.chiusa:
            return
        try:
            self.coda.put_nowait(messaggio)
        except queue.Full:
            self.chiusa = True
            try:
                self.coda.get_nowait()
            except queue.Empty:
                pass
            self.coda.put_nowait(FINE)

    def prossimo(self, attesa: float):
        """Il prossimo messaggio, o None se nel frattempo non arriva niente (per il battito)."""
        try:
            return self.coda.get(timeout=attesa)
        except queue.Empty:
            return None


class Smistatore:
    def __init__(self):
        self._lock = threading.Lock()
        self._iscritti: dict[str, set[Iscrizione]] = {}
        self._presenze: dict[str, dict[str, tuple[str, float]]] = {}   # stanza -> slot -> (dati, scadenza)

    # --- collegamenti -----------------------------------------------------------------------------------------

    def iscrivi(self, stanza: str, membro: str, presenza: bool) -> Iscrizione:
        isc = Iscrizione(stanza, membro, presenza)
        with self._lock:
            self._iscritti.setdefault(stanza, set()).add(isc)
        return isc

    def disiscrivi(self, isc: Iscrizione) -> None:
        with self._lock:
            gruppo = self._iscritti.get(isc.stanza)
            if gruppo:
                gruppo.discard(isc)
                if not gruppo:
                    self._iscritti.pop(isc.stanza, None)
            aveva = self._presenze.get(isc.stanza, {}).pop(isc.slot, None)
        isc.chiusa = True
        if aveva:
            self._pubblica(isc.stanza, {"t": "via", "slot": isc.slot})

    def collegati(self, stanza: str) -> int:
        with self._lock:
            return len(self._iscritti.get(stanza, ()))

    def slot_di(self, stanza: str, slot: str, membro: str) -> Iscrizione | None:
        """Il collegamento con quella presenza, se appartiene a quel membro e mostra la sua attivita."""
        with self._lock:
            for isc in self._iscritti.get(stanza, ()):
                if isc.slot == slot and isc.membro == membro and isc.presenza and not isc.chiusa:
                    return isc
        return None

    # --- messaggi -----------------------------------------------------------------------------------------------

    def evento(self, stanza: str, ev: dict) -> None:
        self._pubblica(stanza, {"t": "evento", "ev": ev})

    def presenza(self, stanza: str, slot: str, dati: str) -> None:
        self._pubblica(stanza, {"t": "presenza", "slot": slot, "dati": dati})

    def chiusa(self, stanza: str) -> None:
        self._pubblica(stanza, {"t": "chiusa"})

    def espelli(self, stanza: str, membro: str) -> None:
        """Chiude i collegamenti di un membro uscito."""
        self._pubblica(stanza, {"t": "espelli", "membro": membro})

    def presenze_attuali(self, stanza: str) -> list[dict]:
        ora = time.time()
        with self._lock:
            tutte = self._presenze.get(stanza, {})
            for slot in [s for s, (_, scad) in tutte.items() if scad < ora]:
                tutte.pop(slot, None)
            return [{"slot": s, "dati": d} for s, (d, _) in tutte.items()]

    # --- consegna -----------------------------------------------------------------------------------------------

    def _pubblica(self, stanza: str, messaggio: dict) -> None:
        """In memoria la pubblicazione e la consegna coincidono; SmistatoreValkey passa da Valkey."""
        self._consegna(stanza, messaggio)

    def _consegna(self, stanza: str, messaggio: dict) -> None:
        t = messaggio.get("t")
        with self._lock:
            if t == "presenza":
                self._presenze.setdefault(stanza, {})[messaggio["slot"]] = (messaggio["dati"],
                                                                           time.time() + SCADENZA_PRESENZA)
            elif t == "via":
                self._presenze.get(stanza, {}).pop(messaggio["slot"], None)
            elif t == "chiusa":
                self._presenze.pop(stanza, None)
            destinatari = list(self._iscritti.get(stanza, ()))
        for isc in destinatari:
            if t in ("presenza", "via"):
                if isc.presenza:
                    isc.consegna(messaggio)
            elif t == "espelli":
                if isc.membro == messaggio.get("membro"):
                    isc.consegna(FINE)
            elif t == "chiusa":
                isc.consegna(messaggio)
                isc.consegna(FINE)
            else:
                isc.consegna(messaggio)

    def ferma(self) -> None:
        pass


class SmistatoreValkey(Smistatore):
    """Smistatore tra piu processi tramite Valkey (o Redis) Pub/Sub. Serve il pacchetto «redis» (py -m pip install redis),
    che parla anche con Valkey. Ogni processo tiene la propria copia delle presenze, aggiornata dai messaggi: un
    collegamento nuovo su un altro processo vede le presenze al rinnovo successivo (al massimo 15 secondi)."""

    CANALE = "atrium:"

    def __init__(self, url: str, client=None):
        super().__init__()
        if client is None:
            import redis  # import tardivo: serve solo con piu processi
            client = redis.Redis.from_url(url)
        self._client = client
        self._pubsub = client.pubsub(ignore_subscribe_messages=True)
        self._pubsub.psubscribe(self.CANALE + "*")
        self._attivo = True
        self._filo = threading.Thread(target=self._ascolta, name="atrium-valkey", daemon=True)
        self._filo.start()

    def _pubblica(self, stanza: str, messaggio: dict) -> None:
        self._client.publish(self.CANALE + stanza, json.dumps(messaggio, separators=(",", ":")))

    def _ascolta(self) -> None:
        while self._attivo:
            try:
                m = self._pubsub.get_message(timeout=1.0)
            except Exception:
                time.sleep(1.0)
                continue
            if not m or m.get("type") not in ("pmessage", "message"):
                continue
            canale = m.get("channel")
            canale = canale.decode() if isinstance(canale, bytes) else str(canale)
            dati = m.get("data")
            try:
                messaggio = json.loads(dati.decode() if isinstance(dati, bytes) else dati)
            except (ValueError, AttributeError):
                continue
            self._consegna(canale[len(self.CANALE):], messaggio)

    def ferma(self) -> None:
        self._attivo = False
        try:
            self._pubsub.close()
        except Exception:
            pass


def da_ambiente() -> Smistatore:
    url = os.environ.get("ATRIUM_VALKEY_URL", "").strip()
    return SmistatoreValkey(url) if url else Smistatore()
