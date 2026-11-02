/* Atrium: le due pagine (iniziale e questione). Tutto il testo delle persone entra nella pagina come testo, mai come HTML. */
(function () {
  'use strict';
  var A = window.Atrium;
  var pagina = document.body.getAttribute('data-pagina');
  var COLORI = ['#a3245c', '#8a6d00', '#0b7a8f', '#55702a', '#4b3fa0', '#9a3f2a', '#44515c'];
  var PRODOTTI = {
    'anorma': { nome: 'Risposta di Anorma', colore: 'var(--c-an)' },
    'nuova-norma': { nome: 'Nuova-Norma', colore: 'var(--c-nn)' },
    'ppatos': { nome: 'Bozza di PPaToS', colore: 'var(--c-pp)' }
  };
  var DELTA = 'M121.85,0L0,248.78h243.7L121.85,0ZM121.85,37.81l64.88,196.29H25.71L121.85,37.81Z';

  function $(id) { return document.getElementById(id); }
  function el(tag, attr) {
    var e = document.createElement(tag);
    if (attr) Object.keys(attr).forEach(function (k) {
      var v = attr[k];
      if (v == null || v === false) return;
      if (k === 'class') e.className = v;
      else if (k === 'testo') e.textContent = v;
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var f = arguments[i];
      if (f == null || f === false) continue;
      e.appendChild(typeof f === 'string' ? document.createTextNode(f) : f);
    }
    return e;
  }
  function delta(size, colore) {
    var ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg'), p = document.createElementNS(ns, 'path');
    s.setAttribute('width', size); s.setAttribute('height', Math.round(size * 248.78 / 243.7));
    s.setAttribute('viewBox', '0 0 243.7 248.78'); s.setAttribute('aria-hidden', 'true');
    s.style.color = colore || 'var(--accent)'; s.style.flex = 'none';
    p.setAttribute('fill', 'currentColor'); p.setAttribute('fill-rule', 'evenodd'); p.setAttribute('d', DELTA);
    s.appendChild(p);
    return s;
  }
  function mostra(n, si) { if (n) n.classList.toggle('at-nascosto', !si); }
  var timerToast = null;
  function toast(testo, errore) {
    var t = document.querySelector('.tr-toast');
    if (t) t.remove();
    t = el('div', { class: 'tr-toast' + (errore ? ' tr-errore' : ''), role: 'status' }, testo);
    document.body.appendChild(t);
    clearTimeout(timerToast);
    timerToast = setTimeout(function () { t.remove(); }, errore ? 6000 : 3200);
  }
  function frammento() {
    var h = new URLSearchParams(location.hash.slice(1));
    return { k: h.get('k'), da: h.get('da'), o: h.get('o') };
  }
  function leggiOggetto(o) {
    if (!o) return null;
    try { return A.pulisciOggetto(JSON.parse(new TextDecoder().decode(A.daB64u(o)))); } catch (e) { return null; }
  }
  function ora(ts) {
    var d = new Date(ts);
    if (isNaN(d)) return '';
    return d.toLocaleString('it-CH', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function giorno(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? m[3] + '.' + m[2] + '.' + m[1] : (iso || '');
  }
  function oggi() {
    var d = new Date(), z = function (n) { return ('0' + n).slice(-2); };
    return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate());
  }
  // I colori delle persone seguono l'ordine d'ingresso, uguale per tutti: i primi sette sono sempre diversi.
  function coloreDi(autore) {
    var h = 0;
    for (var i = 0; i < autore.length; i++) h = (h * 31 + autore.charCodeAt(i)) >>> 0;
    return COLORI[h % COLORI.length];
  }
  function iniziale(nome) { return (String(nome || '?').trim()[0] || '?').toUpperCase(); }

  // =====================================================================================================================
  // Pagina iniziale: apri una questione

  function paginaIniziale() {
    var oggetto = leggiOggetto(frammento().o);
    if (oggetto) {
      $('at-porta-titolo').textContent = oggetto.titolo || '';
      $('at-porta-testo').textContent = oggetto.testo || '';
      mostra($('at-porta'), true);
      if (!$('at-titolo').value && oggetto.titolo) $('at-titolo').value = oggetto.titolo.slice(0, 120);
    }
    $('at-nuova').addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = e.target.querySelector('button');
      btn.disabled = true;
      $('at-errore').textContent = '';
      A.creaStanza('').then(function (d) {
        var k = A.generaChiave();
        A.salvaNuova(d.stanza, { titolo: $('at-titolo').value.trim().slice(0, 120), oggetto: oggetto, amministrazione: d.amministrazione });
        location.href = '/q/' + encodeURIComponent(d.stanza) + '#k=' + k;
      }).catch(function (err) {
        btn.disabled = false;
        $('at-errore').textContent = 'Non sono riuscito ad aprire la questione: ' + err.message + '.';
      });
    });
  }

  // =====================================================================================================================
  // Pagina della questione

  function paginaQuestione() {
    var stanza = decodeURIComponent(location.pathname.split('/')[2] || '');
    var fr = frammento();
    var mem = A.leggi(stanza);
    var chiaveB64 = fr.k || (mem && mem.chiave);
    var nuova = A.leggiNuova(stanza);

    function stato(testo, conLink) {
      var s = $('at-stato');
      s.textContent = testo;
      if (conLink) { s.appendChild(document.createTextNode(' ')); s.appendChild(el('a', { href: '/' }, 'Apri una questione nuova')); s.appendChild(document.createTextNode('.')); }
      mostra(s, true);
      mostra($('at-ingresso'), false);
      mostra($('at-stanza'), false);
    }

    if (!chiaveB64) {
      stato('Questo link non contiene la chiave della questione, quindi non posso aprirla. Chiedi a chi ti ha invitato di mandarti il link completo, con la parte dopo il segno #.');
      return;
    }
    A.importaChiave(chiaveB64).then(function (chiave) {
      try { history.replaceState(null, '', location.pathname + '#k=' + chiaveB64); } catch (e) { /* niente */ }
      if (mem && mem.membro && mem.chiave === chiaveB64) apriStanza(chiave);
      else ingresso(chiave);
    }, function () {
      stato('La chiave nel link non è valida. Chiedi a chi ti ha invitato di mandarti di nuovo il link.');
    });

    // --- ingresso -------------------------------------------------------------------------------------------------

    function ingresso(chiave) {
      $('at-invitato').textContent = nuova
        ? 'Hai aperto questa questione. Scegli il nome con cui ti vedranno le persone che inviterai.'
        : 'Ti hanno invitato in una questione su Atrium. Scegli il nome con cui ti vedranno qui: può essere anche solo il nome di battesimo.';
      mostra($('at-ingresso'), true);
      $('at-nome').focus();
      $('at-entra').addEventListener('submit', function (e) {
        e.preventDefault();
        var nome = $('at-nome').value.trim().slice(0, 40);
        if (!nome) return;
        var btn = e.target.querySelector('button');
        btn.disabled = true;
        A.nuovaIdentita().then(function (id) {
          mem = { chiave: chiaveB64, membro: id.membro, autore: id.autore, pub: id.pub, priv: id.priv, nome: nome,
                  colore: coloreDi(id.autore), presenza: true, amministrazione: nuova ? nuova.amministrazione : null };
          var q = new A.Questione({ stanza: stanza, chiave: chiave, mem: mem });
          return q.entra({ nome: nome, colore: mem.colore, pub: id.pub, invitatoDa: fr.da || null, apre: !!nuova }).then(function () {
            A.salva(stanza, mem);
            var passi = Promise.resolve();
            if (nuova) {
              if (nuova.titolo) passi = passi.then(function () { return q.invia('titolo', { testo: nuova.titolo }); });
              if (nuova.oggetto) passi = passi.then(function () { return q.invia('oggetto', nuova.oggetto); });
              passi = passi.then(function () { A.dimenticaNuova(stanza); });
            }
            return passi.then(function () { mostra($('at-ingresso'), false); apriStanza(chiave, q); });
          });
        }).catch(function (err) {
          btn.disabled = false;
          toast('Non sono riuscito a farti entrare: ' + err.message + '.', true);
        });
      });
    }

    // --- stanza ---------------------------------------------------------------------------------------------------

    function apriStanza(chiave, qEsistente) {
      var q = qEsistente || new A.Questione({ stanza: stanza, chiave: chiave, mem: mem });
      var membri = {};          // autore -> { nome, colore, pub, invitatoDa, dentro, apre }
      var fatti = {};           // seq -> { data, testo, autore, ts, correzioni: [], nodo }
      var presenze = {};        // slot -> { autore, stato, dove, scade }
      var catena = { prec: A.INIZIO, atteso: 1, ok: true, n: 0 };
      var pronto = false, salutato = false;
      var mio = { stato: 'legge', dove: 'stanza' }, timerScrive = null, timerRinnovo = null;

      mostra($('at-stanza'), true);
      $('at-mio-nome').textContent = mem.nome;
      $('at-data').value = oggi();
      aggiornaInterruttore();
      if (mem.amministrazione) mostra($('at-chiudi'), true);

      function nomeDi(autore) { return membri[autore] ? membri[autore].nome : 'Qualcuno'; }
      function coloreAutore(autore) { return membri[autore] ? membri[autore].colore : 'var(--muted)'; }
      function pallino(autore) { var p = el('span', { class: 'at-pallino', 'aria-hidden': 'true' }); p.style.background = coloreAutore(autore); return p; }
      function scorriGiu(lista) { if (lista.scrollHeight - lista.scrollTop - lista.clientHeight < 160 || !pronto) lista.scrollTop = lista.scrollHeight; }

      function riga(testo, autore) {
        var l = $('at-messaggi');
        l.appendChild(el('div', { class: 'at-sis' }, autore ? pallino(autore) : null, testo));
        scorriGiu(l);
      }

      function avvisoFirma(valido) {
        return valido ? null : el('span', { class: 'etichetta e-aperto', style: 'font-size:12px;padding:2px 8px' }, 'firma non verificata');
      }

      function applica(ev, chiaro) {
        controllaCatena(ev);
        if (!chiaro) { riga('Un messaggio non si è potuto leggere: forse è stato scritto con una chiave diversa.'); return; }
        var pubNoto = membri[chiaro.autore] && membri[chiaro.autore].pub;
        return A.verificaEvento(stanza, chiaro, pubNoto).then(function (valido) { mostraEvento(chiaro, valido, ev.seq); });
      }

      function mostraEvento(e, valido, seq) {
        var c = e.corpo || {};
        if (e.tipo === 'ingresso') {
          if (!valido) { riga('Un ingresso non ha una firma valida ed è stato ignorato.'); return; }
          var gia = membri[e.autore];
          membri[e.autore] = { nome: String(c.nome || 'Senza nome').slice(0, 40), colore: gia ? gia.colore : COLORI[Object.keys(membri).length % COLORI.length],
                               pub: c.pub, invitatoDa: c.invitatoDa || null, dentro: true, apre: !!c.apre, ts: e.ts };
          var t = c.apre ? membri[e.autore].nome + ' apre la questione'
            : membri[e.autore].nome + ' entra nella stanza' + (c.invitatoDa && membri[c.invitatoDa] ? ', su invito di ' + membri[c.invitatoDa].nome : '');
          riga(t + ' · ' + ora(e.ts), e.autore);
          aggiornaMembri();
          return;
        }
        if (e.tipo === 'uscita') {
          if (membri[e.autore] && valido) membri[e.autore].dentro = false;
          riga(nomeDi(e.autore) + ' lascia la questione · ' + ora(e.ts), e.autore);
          aggiornaMembri();
          return;
        }
        if (e.tipo === 'titolo') {
          if (valido && c.testo) { $('at-nome-questione').textContent = String(c.testo).slice(0, 120); document.title = String(c.testo).slice(0, 120) + ' · Atrium'; }
          return;
        }
        if (e.tipo === 'messaggio') {
          var l = $('at-messaggi');
          l.appendChild(el('div', { class: 'at-msg' + (e.autore === mem.autore ? ' mio' : '') },
            el('span', { class: 'chi' }, pallino(e.autore), el('b', null, e.autore === mem.autore ? 'Tu' : nomeDi(e.autore)), ora(e.ts), avvisoFirma(valido)),
            el('span', { class: 'testo' }, String(c.testo || '').slice(0, 8000))));
          scorriGiu(l);
          return;
        }
        if (e.tipo === 'oggetto') {
          var o = A.pulisciOggetto(c) || {}, pr = PRODOTTI[o.prodotto] || PRODOTTI.anorma;
          var da = el('span', { class: 'da' }, delta(13, pr.colore), pr.nome);
          da.style.color = pr.colore;
          var fonte = o.fonte ? (o.url ? el('a', { href: o.url, target: '_blank', rel: 'noopener noreferrer' }, o.fonte) : el('span', null, o.fonte)) : null;
          $('at-oggetti').appendChild(el('article', { class: 'at-oggetto' }, da,
            o.titolo ? el('strong', null, o.titolo) : null,
            o.testo ? el('span', { class: 'serif' }, o.testo) : null,
            el('span', { class: 'piede' }, fonte, fonte ? ' · ' : '', 'portato da ' + nomeDi(e.autore) + ', ' + ora(e.ts), ' ', avvisoFirma(valido))));
          return;
        }
        if (e.tipo === 'fatto') {
          fatti[seq] = { data: String(c.data || '').slice(0, 10), testo: String(c.testo || '').slice(0, 4000), autore: e.autore, ts: e.ts, seq: seq, valido: valido, correzioni: [] };
          disegnaFatti();
          return;
        }
        if (e.tipo === 'correzione') {
          var f = fatti[c.rif];
          if (f) { f.correzioni.push({ testo: String(c.testo || '').slice(0, 4000), autore: e.autore, ts: e.ts, valido: valido }); disegnaFatti(); }
          return;
        }
      }

      function disegnaFatti() {
        var ol = $('at-fatti');
        ol.textContent = '';
        var elenco = Object.keys(fatti).map(function (k) { return fatti[k]; });
        elenco.sort(function (a, b) { return a.data < b.data ? -1 : a.data > b.data ? 1 : a.seq - b.seq; });
        if (!elenco.length) {
          ol.appendChild(el('li', { class: 'at-nota', style: 'padding:14px 0' }, 'Ancora nessun fatto. Cominciate da ciò che è successo per primo: una data e due righe bastano.'));
          return;
        }
        elenco.forEach(function (f) {
          var corpo = el('div', null,
            el('div', { class: 'serif' }, f.testo),
            el('div', { class: 'chi' }, pallino(f.autore), f.autore === mem.autore ? 'Tu' : nomeDi(f.autore), ' · ' + ora(f.ts), ' ', avvisoFirma(f.valido)));
          f.correzioni.forEach(function (cr) {
            corpo.appendChild(el('div', { class: 'at-corr' },
              el('div', null, cr.testo),
              el('div', { class: 'chi' }, pallino(cr.autore), 'Correzione di ' + (cr.autore === mem.autore ? 'te' : nomeDi(cr.autore)) + ' · ' + ora(cr.ts), ' ', avvisoFirma(cr.valido))));
          });
          var btn = el('button', { type: 'button', class: 'btn btn-testo btn-piccolo', style: 'padding:0;min-height:36px' }, 'Correggi o aggiungi');
          btn.addEventListener('click', function () {
            btn.remove();
            var ta = el('textarea', { maxlength: '4000', 'aria-label': 'Correzione del fatto del ' + giorno(f.data) });
            var invia = el('button', { type: 'submit', class: 'btn btn-bordo btn-piccolo' }, 'Aggiungi la correzione');
            var form = el('form', { class: 'at-scrivi', style: 'margin-top:10px' }, ta, el('div', { class: 'at-riga' }, invia));
            form.addEventListener('submit', function (ev) {
              ev.preventDefault();
              var testo = ta.value.trim();
              if (!testo) return;
              invia.disabled = true;
              q.invia('correzione', { rif: f.seq, testo: testo }).catch(function (err) { invia.disabled = false; toast('Correzione non inviata: ' + err.message + '.', true); });
            });
            corpo.appendChild(form);
            ta.focus();
            ta.addEventListener('focus', function () { segnala('scrive', 'cronologia'); });
          });
          corpo.appendChild(btn);
          ol.appendChild(el('li', { class: 'at-fatto' }, el('span', { class: 'data' }, giorno(f.data)), corpo));
        });
      }

      function aggiornaMembri() {
        var dentro = Object.keys(membri).filter(function (a) { return membri[a].dentro; });
        var volti = $('at-volti');
        volti.textContent = '';
        dentro.slice(0, 6).forEach(function (a) {
          var v = el('span', { class: 'at-volto', title: membri[a].nome }, iniziale(membri[a].nome));
          v.style.background = membri[a].colore;
          volti.appendChild(v);
        });
        if (dentro.length > 6) volti.appendChild(el('span', { class: 'at-volto', style: 'background:var(--muted)' }, '+' + (dentro.length - 6)));
        $('at-membri-btn').textContent = dentro.length === 1 ? '1 membro' : dentro.length + ' membri';
        var lista = $('at-membri');
        lista.textContent = '';
        Object.keys(membri).forEach(function (a) {
          var m = membri[a], v = el('span', { class: 'at-volto' }, iniziale(m.nome));
          v.style.background = m.colore;
          var info = m.apre ? 'ha aperto la questione' : (m.invitatoDa && membri[m.invitatoDa] ? 'su invito di ' + membri[m.invitatoDa].nome : 'entrato con il link');
          lista.appendChild(el('div', null, v, el('span', null, m.nome + (a === mem.autore ? ' (tu)' : ''), el('br'), el('small', null, info + ' · ' + ora(m.ts) + (m.dentro ? '' : ' · ha lasciato la questione')))));
        });
        disegnaPresenza();
      }

      // --- catena delle impronte: la verifica anche il browser ------------------------------------------------------

      var coda = Promise.resolve();
      function controllaCatena(ev) {
        coda = coda.then(function () {
          if (ev.seq !== catena.atteso || ev.prec !== catena.prec) { catena.ok = false; return; }
          return A.improntaEvento(stanza, ev).then(function (h) {
            if (h !== ev.impronta) catena.ok = false;
            catena.prec = ev.impronta; catena.atteso = ev.seq + 1; catena.n = ev.seq;
          });
        }).then(disegnaCatena);
      }
      function disegnaCatena() {
        var c = $('at-catena');
        c.classList.toggle('rotta', !catena.ok);
        c.textContent = catena.ok
          ? 'Registro integro: ' + catena.n + (catena.n === 1 ? ' evento' : ' eventi') + ', nessuno tolto o cambiato.'
          : 'Attenzione: il registro ricevuto non torna (un evento manca o è stato cambiato). Avvisa chi ha aperto la questione.';
      }

      // --- presenza -------------------------------------------------------------------------------------------------

      function disegnaPresenza() {
        var p = $('at-presenza');
        p.textContent = '';
        if (!mem.presenza) { p.textContent = 'Hai nascosto la tua attività: non vedi nemmeno quella degli altri.'; return; }
        var adesso = Date.now(), per = {};
        Object.keys(presenze).forEach(function (s) {
          var x = presenze[s];
          if (x.scade < adesso) { delete presenze[s]; return; }
          if (x.autore === mem.autore || !membri[x.autore] || !membri[x.autore].dentro) return;
          if (!per[x.autore] || x.stato === 'scrive') per[x.autore] = x;
        });
        var chi = Object.keys(per);
        if (!chi.length) { p.textContent = 'Per ora ci sei solo tu, qui.'; return; }
        chi.forEach(function (a, i) {
          if (i) p.appendChild(document.createTextNode(' · '));
          var x = per[a];
          p.appendChild(el('b', null, nomeDi(a)));
          p.appendChild(document.createTextNode(x.stato === 'scrive' ? (x.dove === 'cronologia' ? ' scrive nella cronologia' : ' sta scrivendo')
            : (x.dove === 'cronologia' ? ' legge i fatti' : ' legge')));
        });
        if (!salutato && pronto) {
          salutato = true;
          var b = $('at-non-solo');
          b.textContent = '';
          b.appendChild(delta(16));
          b.appendChild(document.createTextNode('Non sei solo qui: ' + chi.map(nomeDi).join(', ') + (chi.length === 1 ? ' è qui adesso.' : ' sono qui adesso.')));
          mostra(b, true);
          setTimeout(function () { mostra(b, false); }, 9000);
        }
      }

      function segnala(stato, dove) {
        if (mio.stato === stato && mio.dove === dove) return;
        mio = { stato: stato, dove: dove };
        q.presenza(mio);
        if (stato === 'scrive') {
          clearTimeout(timerScrive);
          timerScrive = setTimeout(function () { segnala('legge', mio.dove); }, 5000);
        }
      }

      function aggiornaInterruttore() {
        $('at-mostra').setAttribute('aria-checked', mem.presenza ? 'true' : 'false');
      }

      setInterval(disegnaPresenza, 10000);

      // --- flusso ---------------------------------------------------------------------------------------------------

      q.ascolta({
        collegato: function (slot) {
          clearInterval(timerRinnovo);
          if (slot) {
            q.presenza(mio);
            timerRinnovo = setInterval(function () { if (!document.hidden) q.presenza(mio); }, 15000);
          }
        },
        evento: applica,
        pronto: function () {
          pronto = true;
          disegnaFatti();
          var l = $('at-messaggi');
          l.scrollTop = l.scrollHeight;
          coda.then(disegnaCatena);
        },
        presenza: function (slot, x) {
          if (!x || typeof x.autore !== 'string') return;
          if (x.stato === 'via') { delete presenze[slot]; disegnaPresenza(); return; }
          presenze[slot] = { autore: x.autore, stato: x.stato === 'scrive' ? 'scrive' : 'legge', dove: x.dove === 'cronologia' ? 'cronologia' : 'stanza', scade: Date.now() + 40000 };
          disegnaPresenza();
        },
        via: function (slot) { delete presenze[slot]; disegnaPresenza(); },
        chiusa: function () {
          A.dimentica(stanza);
          stato('Questa questione è stata chiusa da chi l\'ha aperta. Tutto ciò che conteneva è stato cancellato.', true);
        },
        stato: function (s) {
          if (s === 'rifiutato') {
            A.dimentica(stanza);
            stato('Non risulti più dentro questa questione: forse ne sei uscito da un altro computer. Puoi rientrare dal link: chi è dentro vedrà il tuo nuovo ingresso.');
            var s2 = $('at-stato');
            s2.appendChild(document.createTextNode(' '));
            s2.appendChild(el('a', { href: location.pathname + '#k=' + chiaveB64 + '&r=' + Date.now() }, 'Rientra'));
            s2.lastChild.addEventListener('click', function () { setTimeout(function () { location.reload(); }, 10); });
          } else if (s === 'chiusa') {
            A.dimentica(stanza);
            stato('Questa questione non c\'è più: chi l\'ha aperta l\'ha chiusa, e tutto ciò che conteneva è stato cancellato.', true);
          } else if (s === 'rete') {
            $('at-presenza').textContent = 'Collegamento interrotto: riprovo da solo. Quello che scrivi nel frattempo non viene inviato.';
          }
        }
      });

      // --- azioni ---------------------------------------------------------------------------------------------------

      var testo = $('at-testo');
      testo.addEventListener('input', function () { segnala('scrive', 'stanza'); });
      testo.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('at-scrivi').requestSubmit(); }
      });
      $('at-scrivi').addEventListener('submit', function (e) {
        e.preventDefault();
        var t = testo.value.trim();
        if (!t) return;
        var btn = e.target.querySelector('button');
        btn.disabled = true;
        q.invia('messaggio', { testo: t.slice(0, 8000) }).then(function () {
          testo.value = '';
          segnala('legge', 'stanza');
        }, function (err) { toast('Messaggio non inviato: ' + err.message + '.', true); })
          .then(function () { btn.disabled = false; testo.focus(); });
      });

      $('at-fatto').addEventListener('input', function () { segnala('scrive', 'cronologia'); });
      $('at-nuovo-fatto').addEventListener('submit', function (e) {
        e.preventDefault();
        var t = $('at-fatto').value.trim(), d = $('at-data').value;
        if (!t || !d) return;
        var btn = e.target.querySelector('button');
        btn.disabled = true;
        q.invia('fatto', { data: d, testo: t.slice(0, 4000) }).then(function () {
          $('at-fatto').value = '';
          segnala('legge', 'cronologia');
          toast('Fatto aggiunto alla cronologia.');
        }, function (err) { toast('Fatto non aggiunto: ' + err.message + '.', true); })
          .then(function () { btn.disabled = false; });
      });

      $('at-membri-btn').addEventListener('click', function () {
        var aperto = $('at-membri').classList.contains('at-nascosto');
        mostra($('at-membri'), aperto);
        this.setAttribute('aria-expanded', aperto ? 'true' : 'false');
      });

      $('at-invita').addEventListener('click', function () {
        var link = location.origin + '/q/' + encodeURIComponent(stanza) + '#k=' + chiaveB64 + '&da=' + mem.autore;
        var fatto = function () { toast('Link copiato. Chi lo riceve può entrare: mandalo solo a chi vuoi qui.'); };
        try {
          navigator.clipboard.writeText(link).then(fatto, function () { window.prompt('Copia questo link e mandalo a chi vuoi invitare:', link); });
        } catch (e) { window.prompt('Copia questo link e mandalo a chi vuoi invitare:', link); }
      });

      $('at-mostra').addEventListener('click', function () {
        var prima = mem.presenza ? q.presenza({ stato: 'via', dove: mio.dove }) : Promise.resolve();
        prima.then(function () {
          mem.presenza = !mem.presenza;
          A.salva(stanza, mem);
          aggiornaInterruttore();
          presenze = {};
          disegnaPresenza();
          q.riconnetti();
        });
      });

      function conferma(btn, testoConferma, azione) {
        if (btn.dataset.conferma === '1') { azione(); return; }
        var prima = btn.textContent;
        btn.dataset.conferma = '1';
        btn.textContent = testoConferma;
        setTimeout(function () { btn.dataset.conferma = ''; btn.textContent = prima; }, 6000);
      }

      $('at-esci').addEventListener('click', function () {
        var btn = this;
        conferma(btn, 'Conferma: esci dalla questione', function () {
          btn.disabled = true;
          q.presenza({ stato: 'via', dove: mio.dove });
          q.esci().then(function () {
            A.dimentica(stanza);
            stato('Sei uscito dalla questione. Quello che hai scritto resta, con il tuo nome. Se hai ancora il link puoi rientrare: gli altri vedranno il nuovo ingresso.');
          }, function (err) { btn.disabled = false; toast('Non sono riuscito a farti uscire: ' + err.message + '.', true); });
        });
      });

      $('at-chiudi').addEventListener('click', function () {
        var btn = this;
        $('at-chiudi-nota').textContent = 'Chiudendo la questione si cancella tutto, per tutti: messaggi, fatti, membri. Non si può annullare.';
        conferma(btn, 'Conferma: chiudi e cancella tutto', function () {
          btn.disabled = true;
          q.chiudi(mem.amministrazione).then(function () {
            A.dimentica(stanza);
            stato('Hai chiuso la questione. Tutto ciò che conteneva è stato cancellato.', true);
          }, function (err) { btn.disabled = false; toast('Non sono riuscito a chiuderla: ' + err.message + '.', true); });
        });
      });

      document.addEventListener('visibilitychange', function () { if (!document.hidden) q.presenza(mio); });
      window.addEventListener('pagehide', function () { q.presenza({ stato: 'via', dove: mio.dove }); });
      disegnaFatti();
    }
  }

  if (pagina === 'iniziale') paginaIniziale();
  else if (pagina === 'questione') paginaQuestione();
})();
