## <a name="docsarchitecture.md"></a>docs/architecture.md
# <a name="xd65d6c9a41bc0687650fccdac300771948f07ac"></a>Architettura Tecnica – Timmy-KB (v1.0.5 Stable)
Questa pagina descrive l’architettura **attuale** del progetto (patch di mantenimento). È allineata al CHANGELOG **1.0.5** e riflette i miglioramenti di robustezza introdotti (ottimizzazioni agli strumenti CLI di supporto) senza cambiamenti nei flussi principali della pipeline.

-----
## <a name="principi-architetturali"></a>1) Principi architetturali
- **Separazione dei ruoli:** gli **orchestratori** gestiscono UX/CLI (prompt utente, conferme, scelta modalità, gestione errori); i **moduli pipeline** eseguono operazioni tecniche e **non** terminano mai il processo (no sys.exit(), no input() nei moduli).
- **HiTL pragmatico:** intervento umano solo negli orchestratori (prompt interattivi); in batch (--non-interactive) l’esecuzione è completamente deterministica (nessun input richiesto).
- **Idempotenza & sicurezza:** rigore sui percorsi (*path-safety* con is\_safe\_subpath), scritture atomiche per file critici, log unificato per cliente, nessun segreto in chiaro nei log.
- **Coerenza documentale:** ogni modifica al comportamento della pipeline prevede un contestuale aggiornamento della documentazione (codice e doc evolvono insieme).
-----
## <a name="mappa-dei-componenti"></a>2) Mappa dei componenti
src/\
` `├─ pre\_onboarding.py          # Orchestratore Fase 0 (setup cliente + struttura Drive opzionale)\
` `├─ onboarding\_full.py         # Orchestratore Fase 1 (download → conversione → anteprima → push)\
` `└─ pipeline/\
`     `├─ context.py             # Gestione .env/ambiente, risoluzione percorsi cliente; logging centralizzato (no print)\
`     `├─ logging\_utils.py       # get\_structured\_logger(...): logger con filtri contesto, redazione e rotazione file\
`     `├─ exceptions.py          # Tassonomia errori + mappa codici EXIT\_CODES (usata dagli orchestratori)\
`     `├─ env\_utils.py           # Helpers per env: get\_env\_var/get\_bool/get\_int, redazione segreti, allow-list branch force-push\
`     `├─ config\_utils.py        # Gestione di config.yaml (lettura, scrittura con backup .bak, merge variabili)\
`     `├─ drive\_utils.py         # API Google Drive (facciata): download ricorsivo (BFS) PDF, creazione struttura remota da YAML (retry con tetto)\
`     `├─ content\_utils.py       # Conversione PDF→Markdown, generazione SUMMARY/README, validazioni struttura Markdown\
`     `├─ gitbook\_preview.py     # Generazione `book.json`/`package.json`; avvio Docker HonKit (build & serve) sempre senza prompt e \*detached\*\
`     `├─ github\_utils.py        # Push su GitHub (usa `GITHUB\_TOKEN`; branch letto da GIT\_DEFAULT\_BRANCH; push incrementale senza force di default)\
`     `└─ cleanup\_utils.py       # Pulizia post-push: rimozione artefatti locali legacy (es. repo .git temporanei) in modo sicuro

**Dati e output per cliente:** ogni cliente ha la propria struttura in output/timmy-kb-<slug>/ con sottocartelle raw/, book/, config/, logs/. Il log strutturato risiede in logs/onboarding.log (unico file di log per tutte le fasi, con opzione di rotazione se abilitata).

-----
## <a name="flussi-end-to-end-immutati"></a>3) Flussi end-to-end (immutati)
### <a name="a-pre_onboarding.py-setup-iniziale"></a>A) pre\_onboarding.py (setup iniziale)
1. **Input** – accetta lo slug (posizionale o --slug), il nome cliente --name (opzionale), --dry-run e --non-interactive.
1. **Setup locale** – crea la struttura di cartelle locale: raw/, book/, config/, logs/. Genera (o aggiorna) il file config.yaml nella cartella config/ (effettuando backup automatico se già esistente).
1. **Drive (opzionale)** – se **non** è specificato --dry-run, utilizza le API di Google Drive per creare la cartella del cliente nello Shared Drive (o nella cartella padre indicata) e generare l’intera struttura di cartelle su Drive basandosi su uno YAML di riferimento. Carica quindi il config.yaml su Drive e aggiorna il file locale con gli **ID Drive** ottenuti.
1. **Log** – tutte le azioni vengono registrate nel file output/timmy-kb-<slug>/logs/onboarding.log (nessun output con print(): l’orchestratore usa esclusivamente il logger strutturato).
### <a name="b-onboarding_full.py-pipeline-completa"></a>B) onboarding\_full.py (pipeline completa)
1. **Input** – accetta slug, --non-interactive, --dry-run, --no-drive (per saltare fase Drive), --push|--no-push, --port (porta anteprima, default 4000).\
   *Opzioni avanzate:* --allow-offline-env (ignora mancanza variabili env in contesti CI particolari) e --docker-retries (tentativi max per rilevare Docker in interattivo, default 3). Inoltre, dalla v1.0.4, sono disponibili --force-push e --force-ack <TAG> per richiedere eventualmente un push forzato (con gate a due fattori).
1. **Download RAW (opzionale)** – se **non** è attivo --no-drive **e** non è --dry-run, scarica ricorsivamente tutti i PDF dalla cartella Drive identificata da drive\_raw\_folder\_id (specificato in config.yaml) dentro la cartella locale raw/. Preserva la struttura delle sottocartelle e salta i file già scaricati (idempotenza basata su MD5/size). Se --no-drive è attivo oppure --dry-run, questa fase viene saltata (loggando lo skip).
1. **Conversione Markdown** – converte tutti i PDF in raw/ producendo i file Markdown strutturati corrispondenti in book/. Al termine genera i file indice SUMMARY.md e README.md nella cartella book/ e valida la consistenza della directory book/ generata.
1. **Anteprima (Docker)** –
1. Se la pipeline rileva Docker installato: in modalità **interattiva** viene chiesto se avviare l’anteprima HonKit (default **Sì**); in **non-interactive** l’anteprima viene avviata automaticamente (senza prompt). L’anteprima gira sempre in modalità *detached* (non blocca la pipeline) e l’orchestratore si occupa di **fermare automaticamente** il container Docker all’uscita, indipendentemente dall’esito del push.
1. Se Docker **non** è disponibile: in **non-interactive** la preview viene **saltata automaticamente**; in **interattivo** viene chiesto *«Proseguire senza anteprima?»* (default **No**), permettendo all’utente di decidere.
1. **Push (opzionale)** – se l’esecuzione è in batch e l’utente ha specificato --push (oppure, in interattivo, se l’utente conferma al prompt *«Eseguire il push su GitHub?»*), l’orchestratore avvia la procedura di push: verifica la presenza di GITHUB\_TOKEN, determina il branch di destinazione da GIT\_DEFAULT\_BRANCH (o main se non definito) e invoca push\_output\_to\_github(...) passando i flag di contesto (inclusi force\_push e force\_ack se richiesti). Il push avviene in modo **incrementale** (no force di default), con eventuale *retry* in caso di divergenze (gestito internamente da github\_utils).
1. **Log & exit** – tutte le operazioni sono tracciate nel log strutturato. In caso di errori, vengono sollevate eccezioni tipizzate che l’orchestratore cattura, mappandole su codici di uscita deterministici (EXIT\_CODES definiti). Il processo termina con sys.exit(0) in caso di successo, oppure con il codice specifico in caso di errore.
-----
## <a name="decisioni-runtime-state-machine-minimale"></a>4) Decisioni runtime (state machine minimale)
- **Slug:** se fornito sia posizionalmente che con --slug, prevale il posizionale; se manca in batch → errore (exit code 2); in interattivo, se mancante, viene richiesto via prompt. La validazione avviene sempre appena possibile (loop finché non valido, o errore in batch).
- **Modalità interactive vs batch:**
- In --non-interactive **non** ci sono prompt: la preview viene automaticamente saltata se Docker non c’è; il push è disabilitato a meno di esplicito --push.
- In modalità interattiva: l’utente è guidato con prompt (conferma anteprima se Docker assente; conferma push).
- **Alias deprecati:** se l’utente usa --skip-drive o --skip-push, l’orchestratore li riconosce e li rimappa internamente a --no-drive/--no-push, mostrando un warning di deprecazione.
- **Branch Git di destinazione:** determinato in ordine da context.env["GIT\_DEFAULT\_BRANCH"] (impostato da .env) o context.env["GITHUB\_BRANCH"], altrimenti dalle variabili d’ambiente di processo con lo stesso ordine di precedenza, altrimenti fallback su main. Questo branch viene utilizzato sia per il checkout iniziale che per il push.
-----
## <a name="logging-errori-sicurezza"></a>5) Logging, errori, sicurezza
- **Logger unico per cliente:** ogni orchestratore inizializza un logger strutturato nominato (pre\_onboarding/onboarding\_full), che scrive su file output/timmy-kb-<slug>/logs/onboarding.log. Nessun modulo usa print() per output: tutta la messaggistica passa per il logger.
- **Niente output sensibili:** i logger sono configurati con filtri di **redazione** che mascherano automaticamente token e ID sensibili (attivabili con LOG\_REDACTION o in automatico se l’ambiente è production/CI). I messaggi di log e le eccezioni non contengono segreti o credenziali in chiaro.
- **Tassonomia di errori tipizzati:** i moduli alzano eccezioni specifiche (ConfigError, DriveDownloadError, PreviewError, PushError, ecc.) che derivano tutte da PipelineError. Ogni eccezione è associata a un codice di uscita in EXIT\_CODES (ad es. ConfigError=2, DriveDownloadError=21, PreviewError=30, PushError=40, ForcePushError=41, ecc.). Gli orchestratori catturano queste eccezioni e terminano con sys.exit(<codice>).
- **Path-safety:** ogni operazione su file o directory utilizza percorsi risolti con pathlib.Path e viene preceduta da una verifica is\_safe\_subpath rispetto alla sandbox del cliente (output/timmy-kb-<slug>). Questo impedisce scritture/letture accidentali fuori dal percorso previsto. Inoltre, i file cruciali (es. config, markdown) vengono scritti in modo **atomico** (scrittura su file temporaneo e poi replace).
- **Credenziali e sicurezza:** le credenziali (token GitHub, file JSON di Drive) sono lette solo da variabili d’ambiente (o .env) e **mai** salvate su disco dalla pipeline. Nei log non compaiono mai token o informazioni sensibili (grazie alla redazione). Le chiamate esterne (API, comandi git/gh) sono effettuate in modo sicuro (es. il token GitHub è passato via header HTTP con GIT\_HTTP\_EXTRAHEADER per evitare leak su CLI).
-----
## <a name="modifiche-di-questa-release-v1.0.5"></a>6) Modifiche di questa release (v1.0.5)
- **Orchestratori:** invariati rispetto alla versione precedente nei flussi core; permane l’utilizzo dell’early logger nello \_\_main\_\_ e la gestione dei nuovi flag di force-push introdotti in 1.0.4 (due fattori obbligatori e controllo branch ammessi). Nessuna nuova logica aggiunta in 1.0.5.
- **Strumenti ausiliari:** migliorati (refactor tool, cleanup repo) come parte della manutenzione complessiva, senza però impattare l’architettura pipeline principale.
- **Preview Docker:** confermato comportamento *detached* senza prompt a livello di modulo (gitbook\_preview.py non fa mai input); orchestratore garantisce lo **stop automatico** del container all’uscita.
- **Push GitHub:** rimane incrementale di default; la validazione del token è esplicita e, se vengono usati i flag di force push, l’orchestratore applica il gate (richiede ack e rispetta GIT\_FORCE\_ALLOWED\_BRANCHES).
- **Slug:** la regex di validazione continua a essere letta da config.yaml all’avvio e **cachata**; disponibile la funzione clear\_slug\_regex\_cache() (in path\_utils.py) per invalidarla se necessario.

*Nota:* la v1.0.5 è interamente retro-compatibile con la 1.0.4 e non introduce breaking changes nei flussi operativi.

-----
## <a name="x3b02949f0e392e5b17fa80cb8080610598e5047"></a>7) Variabili d’ambiente (rilevanti in architettura)
- GIT\_DEFAULT\_BRANCH – branch Git di default per checkout/push (es. main).
- GITHUB\_TOKEN – token GitHub usato per autenticare il push.
- DRIVE\_ID / DRIVE\_PARENT\_FOLDER\_ID – ID della cartella radice su Google Drive (uno dei due deve essere impostato per abilitare le operazioni Drive).
- GOOGLE\_APPLICATION\_CREDENTIALS / SERVICE\_ACCOUNT\_FILE – path al file JSON con le credenziali del Service Account Google (per accesso Drive API).
- GIT\_FORCE\_ALLOWED\_BRANCHES – lista di branch ammessi per eventuali push forzati (esempio: main,release/\*). Se non impostata (o vuota), il force push è consentito su qualunque branch (la decisione finale spetta comunque all’orchestratore che può bloccare di default).
- LOG\_REDACTION – policy di redazione log sensibili: auto (default, decide in base all’ambiente), on (forza mascheramento) o off (nessuna mascheratura).
- ENV – ambiente logico (dev, prod, production, ci): usato insieme a CI per determinare la redazione in modalità auto.
- CI – flag implicito (es. variabile settata nei pipeline CI): se presente/true e LOG\_REDACTION=auto, abilita la redazione log automatica.
-----
## <a name="xeba6b3f418bbcabe853b1aa8701811a446a9a4b"></a>8) Appendice – Sequenza sintetica (diagramma ASCII)
*(Illustrazione testuale dei passi principali dei flussi pre\_onboarding e onboarding\_full, se presente nel documento originale.)*

