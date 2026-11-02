/* Atrium: la parte che gira nel browser. Cifra, firma e parla con il server.
 *
 * La chiave della stanza (32 byte casuali) sta nel frammento del link: #k=...  Il browser non la invia mai al server.
 * Ogni evento e un oggetto JSON firmato dall'autore (ECDSA P-256, chiave creata nel browser per questa stanza),
 * imbottito a un formato fisso (256 B, 1, 4, 16 o 64 KiB, cosi la lunghezza non tradisce il contenuto) e cifrato con
 * AES-GCM. Anche la presenza (chi c'e, dove, se scrive) viaggia cifrata.
 *
 * Usabile anche dai prodotti: window.Atrium.linkPorta(base, oggetto) apre una questione nuova con un oggetto dentro.
 */
(function () {
  'use strict';
  var enc = new TextEncoder(), dec = new TextDecoder();
  var FORMATI = [256, 1024, 4096, 16384, 65536];
  var INIZIO = new Array(65).join('0');

  function b64u(bytes) {
    var b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes), s = '';
    for (var i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function daB64u(t) {
    t = String(t || '').replace(/-/g, '+').replace(/_/g, '/');
    while (t.length % 4) t += '=';
    var s = atob(t), b = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) b[i] = s.charCodeAt(i);
    return b;
  }
  function esa(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  }
  function casuale(n) { return crypto.getRandomValues(new Uint8Array(n)); }

  // --- cifratura ---------------------------------------------------------------------------------------------------

  function generaChiave() { return b64u(casuale(32)); }

  function importaChiave(k) {
    var raw = daB64u(k);
    if (raw.length !== 32) return Promise.reject(new Error('chiave non valida'));
    return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']);
  }

  function imbottisci(bytes) {
    var n = bytes.length + 4, f = null;
    for (var i = 0; i < FORMATI.length; i++) if (FORMATI[i] >= n) { f = FORMATI[i]; break; }
    if (!f) throw new Error('testo troppo lungo');
    var out = new Uint8Array(f);
    new DataView(out.buffer).setUint32(0, bytes.length);
    out.set(bytes, 4);
    return out;
  }
  function togliImbottitura(b) {
    var n = new DataView(b.buffer, b.byteOffset, b.byteLength).getUint32(0);
    if (n > b.length - 4) throw new Error('blocco non valido');
    return b.subarray(4, 4 + n);
  }
  function aad(stanza, tipo) { return enc.encode('atrium|' + stanza + '|' + tipo); }

  function cifra(chiave, stanza, tipo, oggetto) {
    var iv = casuale(12);
    var testo = imbottisci(enc.encode(JSON.stringify(oggetto)));
    return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv, additionalData: aad(stanza, tipo) }, chiave, testo)
      .then(function (ct) {
        ct = new Uint8Array(ct);
        var out = new Uint8Array(12 + ct.length);
        out.set(iv); out.set(ct, 12);
        return b64u(out);
      });
  }

  function decifra(chiave, stanza, tipo, testo) {
    try {
      var b = daB64u(testo);
      return crypto.subtle.decrypt({ name: 'AES-GCM', iv: b.subarray(0, 12), additionalData: aad(stanza, tipo) },
        chiave, b.subarray(12))
        .then(function (pt) { return JSON.parse(dec.decode(togliImbottitura(new Uint8Array(pt)))); })
        .catch(function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }

  // --- identita e firme --------------------------------------------------------------------------------------------

  function canonico(o) {
    if (o === null || typeof o !== 'object') return JSON.stringify(o === undefined ? null : o);
    if (Array.isArray(o)) return '[' + o.map(canonico).join(',') + ']';
    return '{' + Object.keys(o).sort().filter(function (k) { return o[k] !== undefined; })
      .map(function (k) { return JSON.stringify(k) + ':' + canonico(o[k]); }).join(',') + '}';
  }

  function autoreDa(pub) {
    return crypto.subtle.digest('SHA-256', enc.encode(pub.crv + '|' + pub.x + '|' + pub.y))
      .then(function (h) { return b64u(new Uint8Array(h)).slice(0, 16); });
  }

  function nuovaIdentita() {
    return crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify'])
      .then(function (kp) {
        return Promise.all([crypto.subtle.exportKey('jwk', kp.publicKey), crypto.subtle.exportKey('jwk', kp.privateKey)]);
      })
      .then(function (j) {
        var pub = { kty: 'EC', crv: j[0].crv, x: j[0].x, y: j[0].y };
        return autoreDa(pub).then(function (autore) {
          return { pub: pub, priv: j[1], autore: autore, membro: b64u(casuale(24)) };
        });
      });
  }

  function firma(priv, contenuto) {
    return crypto.subtle.importKey('jwk', priv, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign'])
      .then(function (k) { return crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, k, enc.encode(canonico(contenuto))); })
      .then(function (s) { return b64u(new Uint8Array(s)); });
  }

  function verifica(pub, contenuto, f) {
    try {
      return crypto.subtle.importKey('jwk', { kty: 'EC', crv: 'P-256', x: pub.x, y: pub.y, ext: true },
        { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify'])
        .then(function (k) { return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, k, daB64u(f), enc.encode(canonico(contenuto))); })
        .catch(function () { return false; });
    } catch (e) { return Promise.resolve(false); }
  }

  /* Controlla un evento decifrato. Per l'ingresso la chiave pubblica e nel corpo e deve corrispondere all'autore;
     per gli altri eventi serve la chiave dell'autore, presa dal suo ingresso. */
  function verificaEvento(stanza, ev, pubNoto) {
    if (!ev || typeof ev !== 'object' || ev.stanza !== stanza || !ev.firma || !ev.autore) return Promise.resolve(false);
    var contenuto = { v: ev.v, tipo: ev.tipo, corpo: ev.corpo, autore: ev.autore, ts: ev.ts, stanza: ev.stanza };
    if (ev.tipo === 'ingresso') {
      var pub = ev.corpo && ev.corpo.pub;
      if (!pub || !pub.x || !pub.y) return Promise.resolve(false);
      return autoreDa(pub).then(function (a) { return a === ev.autore ? verifica(pub, contenuto, ev.firma) : false; });
    }
    return pubNoto ? verifica(pubNoto, contenuto, ev.firma) : Promise.resolve(false);
  }

  function improntaEvento(stanza, ev) {
    var testa = enc.encode(stanza + '|' + ev.seq + '|' + ev.ts + '|' + ev.prec + '|'), dati = daB64u(ev.dati);
    var b = new Uint8Array(testa.length + dati.length);
    b.set(testa); b.set(dati, testa.length);
    return crypto.subtle.digest('SHA-256', b).then(esa);
  }

  // --- memoria del browser -----------------------------------------------------------------------------------------
  // Solo su questo computer: chi ha accesso al browser puo riaprire la questione. «Esci» la toglie.

  function leggi(chiave) { try { return JSON.parse(localStorage.getItem(chiave) || 'null'); } catch (e) { return null; } }
  function scrivi(chiave, v) { try { localStorage.setItem(chiave, JSON.stringify(v)); return true; } catch (e) { return false; } }
  function togli(chiave) { try { localStorage.removeItem(chiave); } catch (e) { /* niente */ } }

  // --- server ------------------------------------------------------------------------------------------------------

  function chiedi(base, percorso, corpo, keepalive) {
    return fetch(base + percorso, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo || {}),
      credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer', keepalive: !!keepalive
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error(d.errore || ('errore ' + r.status)); e.stato = r.status; throw e; }
        return d;
      });
    });
  }

  function creaStanza(base) { return chiedi(base || '', '/api/stanze', {}); }

  /* Una questione aperta in questa scheda. mem: { membro, autore, pub, priv, presenza } */
  function Questione(opz) {
    this.base = opz.base || '';
    this.stanza = opz.stanza;
    this.chiave = opz.chiave;
    this.mem = opz.mem;
    this.ultimo = 0;
    this.slot = null;
    this.es = null;
    this.fermo = false;
    this.ascoltatori = {};
    this._coda = Promise.resolve();
    this._tentativi = 0;
  }

  Questione.prototype._evento = function (tipo, corpo) {
    var m = this.mem, stanza = this.stanza, chiave = this.chiave;
    var contenuto = { v: 1, tipo: tipo, corpo: corpo, autore: m.autore, ts: new Date().toISOString(), stanza: stanza };
    return firma(m.priv, contenuto).then(function (f) {
      contenuto.firma = f;
      return cifra(chiave, stanza, 'e', contenuto);
    });
  };

  Questione.prototype._manda = function (azione, tipo, corpo) {
    var self = this;
    return this._evento(tipo, corpo).then(function (dati) {
      return chiedi(self.base, '/api/stanze/' + encodeURIComponent(self.stanza) + '/' + azione, { membro: self.mem.membro, dati: dati });
    });
  };

  Questione.prototype.entra = function (corpo) { return this._manda('ingresso', 'ingresso', corpo); };
  Questione.prototype.invia = function (tipo, corpo) { return this._manda('eventi', tipo, corpo); };
  Questione.prototype.esci = function () { this.ferma(); return this._manda('uscita', 'uscita', {}); };
  Questione.prototype.chiudi = function (amministrazione) {
    return chiedi(this.base, '/api/stanze/' + encodeURIComponent(this.stanza) + '/chiudi', { amministrazione: amministrazione });
  };

  /* stato: { stato: 'legge' | 'scrive' | 'via', dove: 'stanza' | 'cronologia' }. «via» toglie subito la propria
     presenza agli altri (scheda chiusa, attivita nascosta): senza, sparirebbe alla scadenza. */
  Questione.prototype.presenza = function (stato) {
    if (!this.slot || !this.mem.presenza) return Promise.resolve(false);
    var self = this, corpo = { autore: this.mem.autore, stato: stato.stato, dove: stato.dove, ts: Date.now() };
    return cifra(this.chiave, this.stanza, 'p', corpo).then(function (dati) {
      return chiedi(self.base, '/api/stanze/' + encodeURIComponent(self.stanza) + '/presenza',
        { membro: self.mem.membro, slot: self.slot, dati: dati }, true);
    }).then(function () { return true; }, function () { return false; });
  };

  /* Ascolta il flusso. Callback: evento(ev, chiaro), presenza(slot, chiaro), via(slot), pronto(ultimo),
     collegato(slot), stato('rete' | 'rifiutato' | 'chiusa'), chiusa(). Gli eventi arrivano in ordine. */
  Questione.prototype.ascolta = function (ascoltatori) {
    this.ascoltatori = ascoltatori || {};
    this.fermo = false;
    this._apri();
  };

  Questione.prototype._chiama = function (nome) {
    var f = this.ascoltatori[nome];
    if (f) { try { return f.apply(null, Array.prototype.slice.call(arguments, 1)); } catch (e) { console.error(e); } }
  };

  Questione.prototype._url = function () {
    return this.base + '/api/stanze/' + encodeURIComponent(this.stanza) + '/flusso?membro=' + encodeURIComponent(this.mem.membro) +
      '&dopo=' + this.ultimo + '&presenza=' + (this.mem.presenza ? '1' : '0');
  };

  Questione.prototype._apri = function () {
    var self = this;
    if (this.fermo) return;
    var es = new EventSource(this._url());
    this.es = es;
    es.addEventListener('benvenuto', function (m) {
      self._tentativi = 0;
      var d = JSON.parse(m.data);
      self.slot = d.presenza ? d.slot : null;
      self._chiama('collegato', self.slot);
    });
    es.addEventListener('evento', function (m) {
      var ev = JSON.parse(m.data);
      self._coda = self._coda.then(function () {
        if (ev.seq <= self.ultimo) return;
        self.ultimo = ev.seq;
        return decifra(self.chiave, self.stanza, 'e', ev.dati).then(function (chiaro) { return self._chiama('evento', ev, chiaro); });
      });
    });
    es.addEventListener('pronto', function (m) {
      var d = JSON.parse(m.data);
      self._coda = self._coda.then(function () { self._chiama('pronto', d.ultimo); });
    });
    es.addEventListener('presenza', function (m) {
      var d = JSON.parse(m.data);
      decifra(self.chiave, self.stanza, 'p', d.dati).then(function (chiaro) { if (chiaro) self._chiama('presenza', d.slot, chiaro); });
    });
    es.addEventListener('via', function (m) { self._chiama('via', JSON.parse(m.data).slot); });
    es.addEventListener('chiusa', function () { self.ferma(); self._chiama('chiusa'); });
    es.onerror = function () {
      es.close();
      if (self.fermo) return;
      self.slot = null;
      self._tentativi += 1;
      // EventSource non dice perche il server ha rifiutato: lo chiediamo con una richiesta normale.
      var ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
      fetch(self._url(), { cache: 'no-store', credentials: 'omit', signal: ac ? ac.signal : undefined }).then(function (r) {
        if (ac) ac.abort();
        if (r.status === 403) { self.ferma(); self._chiama('stato', 'rifiutato'); return; }
        if (r.status === 404 || r.status === 410) { self.ferma(); self._chiama('stato', 'chiusa'); return; }
        self._riprova();
      }, function () { self._chiama('stato', 'rete'); self._riprova(); });
    };
  };

  Questione.prototype._riprova = function () {
    var self = this, attesa = Math.min(30000, 1000 * Math.pow(2, Math.min(this._tentativi, 5)));
    if (this.fermo) return;
    setTimeout(function () { self._apri(); }, attesa);
  };

  Questione.prototype.riconnetti = function () {
    if (this.es) this.es.close();
    this.slot = null;
    this.fermo = false;
    this._apri();
  };

  Questione.prototype.ferma = function () {
    this.fermo = true;
    if (this.es) this.es.close();
  };

  // --- porta dei prodotti -----------------------------------------------------------------------------------------

  var LIMITI = { prodotto: 20, titolo: 200, testo: 1800, fonte: 200, url: 500 };
  function pulisciOggetto(o) {
    var out = {};
    if (!o || typeof o !== 'object') return null;
    Object.keys(LIMITI).forEach(function (k) {
      var v = String(o[k] == null ? '' : o[k]).trim();
      if (v.length > LIMITI[k]) v = v.slice(0, LIMITI[k] - 1) + '…';
      if (v) out[k] = v;
    });
    if (['anorma', 'nuova-norma', 'ppatos'].indexOf(out.prodotto) < 0) out.prodotto = 'anorma';
    if (out.url && !/^https?:\/\//.test(out.url)) delete out.url;
    return out.titolo || out.testo ? out : null;
  }
  function linkPorta(base, oggetto) {
    var o = pulisciOggetto(oggetto);
    return String(base || '').replace(/\/$/, '') + '/#o=' + b64u(enc.encode(JSON.stringify(o)));
  }

  window.Atrium = {
    b64u: b64u, daB64u: daB64u, generaChiave: generaChiave, importaChiave: importaChiave,
    cifra: cifra, decifra: decifra, nuovaIdentita: nuovaIdentita, autoreDa: autoreDa,
    firma: firma, verifica: verifica, verificaEvento: verificaEvento, improntaEvento: improntaEvento, INIZIO: INIZIO,
    canonico: canonico, creaStanza: creaStanza, Questione: Questione,
    leggi: function (s) { return leggi('atrium:' + s); },
    salva: function (s, v) { return scrivi('atrium:' + s, v); },
    dimentica: function (s) { togli('atrium:' + s); },
    leggiNuova: function (s) { return leggi('atrium:nuova:' + s); },
    salvaNuova: function (s, v) { return scrivi('atrium:nuova:' + s, v); },
    dimenticaNuova: function (s) { togli('atrium:nuova:' + s); },
    pulisciOggetto: pulisciOggetto, linkPorta: linkPorta
  };
})();
