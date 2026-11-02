# Atrium 0.1

Lo spazio condiviso tra le tre stanze della triade: Nuova-Norma *sa*, Anorma *risponde*, PPaToS *scrive*. Atrium
non è un prodotto: è il luogo dove una questione si affronta insieme ad amici, famiglia o colleghi, per non restare
soli davanti a un problema legale.

```
py -m atrium sito                 # http://127.0.0.1:8768/
py -m atrium sito --senza-browser --porta 8768
py -m unittest discover -s tests -t .   # dalla cartella atrium
```

Nessuna dipendenza esterna: libreria standard di Python e il pacchetto `nn` di Nuova-Norma (cartella accanto, o
`NN_CARTELLA`) per le regole del design della triade. Valkey/Redis serve solo con più processi (vedi sotto).

## Cosa c'è

- **Pagina iniziale** (`/`): apri una questione, con un titolo facoltativo. Se il link porta un oggetto da un prodotto
  (`/#o=...`, vedi «Porta dei prodotti»), la pagina lo mostra e lo fissa tra i fatti della questione nuova.
- **Questione** (`/q/<stanza>#k=<chiave>`):
  - ingresso con il nome scelto per quella stanza e l'avviso unico (ingresso visibile, niente si cancella, fotografie
    dello schermo, insulti);
  - barra della questione: titolo, volti, «N membri» con chi ha invitato chi, «Invita qualcuno» (copia il link con la
    chiave e `&da=` per l'invito);
  - presenza in parole («Marta scrive nella cronologia · Luca legge»), «Non sei solo qui» una volta per visita;
  - **Parliamone**: i messaggi, con ingressi e uscite annunciati («Luca entra nella stanza, su invito di Marta»);
  - **I fatti**: gli oggetti portati dai prodotti, nel colore del prodotto; la cronologia dei fatti con data,
    autore e correzioni (nessuna voce si cancella);
  - verifica della catena delle impronte anche nel browser («Registro integro: N eventi»);
  - impostazioni: mostrare o no la propria attività (reciproco), uscire, chiudere la questione per tutti (solo chi
    l'ha aperta).

## Sicurezza

| Che cosa | Dove sta | Chi lo legge |
|---|---|---|
| Chiave della stanza (32 byte casuali) | nel frammento del link `#k=...` e nel browser | solo i membri; il browser non la invia mai al server |
| Messaggi, fatti, nomi, titolo, oggetti | blocchi AES-GCM nel registro | solo i membri |
| Presenza (chi, dove, se scrive) | in memoria, cifrata, scade in 40 s | solo i membri che mostrano la propria |
| Identità del membro | segreto casuale del browser; il server ne tiene l'impronta | nessuno |
| Firma di ogni evento | ECDSA P-256, chiave creata nel browser per quella stanza | tutti i membri la verificano |

- Ogni evento è imbottito a un formato fisso (256 B, 1, 4, 16 o 64 KiB) prima della cifratura: la lunghezza non
  tradisce il contenuto. Il dato associato alla cifratura lega ogni blocco alla sua stanza e al suo tipo.
- Le impronte degli eventi formano una catena (`sha256(stanza|seq|ora|precedente|dati)`): un evento tolto, spostato o
  alterato si vede, sia con `py -m atrium catena <stanza>` sia nel browser di ogni membro.
- Per leggere bisogna essere entrati, e l'ingresso è un evento che tutti vedono: **nessuno legge da invisibile**.
- Chi nasconde la propria attività non riceve quella degli altri e non può inviarne (controllato dal server).
- Pagine con Content-Security-Policy restrittiva, `Referrer-Policy: no-referrer`, niente cookie, niente servizi esterni.
  Il registro dei collegamenti non scrive il codice del membro né l'identificativo della stanza.
- Limiti: 20 questioni nuove all'ora per indirizzo (`ATRIUM_STANZE_ORA`), 120 eventi e 90 aggiornamenti di presenza al
  minuto per membro. Solo in memoria. Dietro un proxy: `ATRIUM_DIETRO_PROXY=1` per usare `X-Forwarded-For`.

Limiti noti, da dire alle persone: chi ha il link completo può entrare (lo vedranno tutti); il browser conserva chiave e
identità nella sua memoria locale, quindi chi usa lo stesso computer può riaprire la questione («Esci» la toglie);
la garanzia regge solo se il codice servito al browser non viene alterato.

## Variabili

| Variabile | Uso |
|---|---|
| `ATRIUM_DB` | percorso del registro SQLite (predefinito `atrium/data/atrium.sqlite`, fuori da git) |
| `ATRIUM_VALKEY_URL` | es. `rediss://utente:password@host:6380/0`: più processi collegati da Valkey Pub/Sub |
| `ATRIUM_STANZE_ORA` | questioni nuove all'ora per indirizzo (20) |
| `ATRIUM_DIETRO_PROXY` | `1` per leggere l'indirizzo da `X-Forwarded-For` |
| `ATRIUM_SILENZIO` | `1` per non stampare i collegamenti |
| `NN_CARTELLA` | dove si trova Nuova-Norma, se non è nella cartella accanto |

### Valkey (più processi)

`py -m pip install redis` (il client parla anche con Valkey). Valkey va avviato **senza salvataggio su disco**
(`save ""`, `appendonly no`), in rete privata, con TLS e un utente ACL che può solo `PUBLISH`, `PSUBSCRIBE` e `PING` sui
canali `atrium:*`. Ogni processo tiene la propria copia delle presenze, aggiornata dai messaggi.

## Porte d'ingresso dai prodotti

Le regole stanno in `nuova-norma/nn/triade.py` (`oggetto_atrium`, `link_atrium`, `porta_atrium_html`, `ATRIUM_SITO`
da `NN_ATRIUM_SITO`, predefinito `http://127.0.0.1:8768`; vuoto per togliere tutte le porte). L'oggetto viaggia nel
frammento `#o=...`, che non arriva al server: Atrium lo mostra («Porterai nella questione») prima di aprire la
questione e lo cifra solo dopo.

| Dove | Riquadro | Che cosa porta |
|---|---|---|
| Anorma, sotto ogni risposta completa | «Non devi tenerla per te» · Parlane con qualcuno | la questione centrale, la risposta breve, la prima fonte con il link ufficiale. I fatti raccontati restano in Anorma |
| PPaToS, sotto la bozza | «Rivedila con qualcuno» · Invita un socio o il tuo avvocato | titolo del documento, numero di clausole, fino a sei punti aperti. La bozza e le risposte restano in PPaToS |
| Nuova-Norma, pagina dell'articolo | «Segui questa legge con altri» · Apri una questione con questo articolo | numero e titolo, testo in vigore, data, link a Fedlex |
| Menu del clic destro, in tutti e tre | «Porta in Atrium» (`nn/copia.js`) | il testo selezionato con la sua fonte |

Da Python: `triade.link_atrium(oggetto)` o `atrium.porta.link_porta(oggetto, base)`. Nel browser:
`Atrium.linkPorta(base, oggetto)`. Da riga di comando: `py -m atrium link --titolo "..." --testo "..."`.
Copie dei file prima delle porte: `_backup-atrium/porte/`.

## Struttura

| File | Cosa fa |
|---|---|
| `atrium/registro.py` | SQLite: stanze, membri (impronte), eventi cifrati in catena; ingresso, uscita, chiusura |
| `atrium/smistatore.py` | tempo reale: eventi, presenza con scadenza e reciprocità, espulsione, chiusura; versione Valkey |
| `atrium/web.py` | pagine, API (`/api/stanze`, `/ingresso`, `/eventi`, `/uscita`, `/presenza`, `/chiudi`), flusso SSE |
| `atrium/statico/atrium.js` | cifratura, imbottitura, firme, catena, collegamento con ripresa |
| `atrium/statico/pagina.js` | le due pagine; il testo delle persone entra solo come testo, mai come HTML |
| `atrium/porta.py` | link dai prodotti |
| `../nuova-norma/nn/triade.py` | `SPAZI["atrium"]`: pietra `#5c4e40` / scuro `#e3d3bd`, marchio con il delta al posto della A |

## Eventi (dentro la cifratura)

`{v, tipo, corpo, autore, ts, stanza, firma}`; tipi: `ingresso` (nome, chiave pubblica, invitatoDa, apre),
`uscita`, `titolo`, `messaggio`, `oggetto` (prodotto, titolo, testo, fonte, url), `fatto` (data, testo),
`correzione` (rif = numero dell'evento del fatto, testo).

## Da fare (collegamenti)

- PostgreSQL al posto di SQLite in produzione (stessa interfaccia di `Registro`, tabella che si può solo allungare).
- messaggi.ch, appunti.ch (scrittura insieme in tempo reale), taccuino.ch; accesso con USSO.
- Gesto «Indica» e Ugo come ospite su richiesta.
- Ottavo colore delle persone, dopo la verifica di contrasto e daltonismo.
