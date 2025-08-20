-----
## <a name="docsdeveloper_guide.md"></a>docs/developer_guide.md
# <a name="guida-sviluppatore-timmykb-v1.0.5"></a>Guida Sviluppatore – Timmy‑KB (v1.0.5)
Questa guida è rivolta a chi sviluppa e mantiene la pipeline. È allineata a **v1.0.5** (patch di miglioramento strumenti) e incorpora tutti i perfezionamenti non-breaking apportati di recente (es. logging con redazione centralizzata, anteprima Docker sempre *detached*, push incrementale con governance del force-push).

-----
## <a name="obiettivi-e-principi"></a>🎯 Obiettivi e principi
- **Idempotenza** – dove possibile, ogni operazione può essere eseguita più volte senza effetti collaterali (skip automatici su file esistenti, controlli MD5/size). Side-effect (I/O, chiamate esterne) confinati in funzioni dedicate con gestione errori.
- **Separazione dei ruoli** – gli orchestratori gestiscono UX/CLI (prompt all’utente, conferme, determinazione modalità), mentre i moduli eseguono lavoro tecnico e **non** chiamano mai sys.exit() né input() (devono essere eseguibili anche in contesti batch).
- **Logging strutturato** – un unico file di log per cliente, generato dagli orchestratori e passato ai moduli. **No** print() nel codice pipeline: tutte le informazioni viaggiano tramite logger (con contesto e mascheramento integrato dove necessario).
- **Errori tipizzati** – le eccezioni appartengono alla tassonomia definita in exceptions.py (es. ConfigError, DriveDownloadError, PreviewError, PushError, etc.) e vengono mappate a codici di uscita stabili (EXIT\_CODES). Evitare eccezioni generiche non gestite.
-----
## <a name="struttura-del-repository"></a>🗂️ Struttura del repository
src/\
` `├─ pre\_onboarding.py           # orchestratore fase iniziale (setup locale + Drive)\
` `├─ onboarding\_full.py          # orchestratore completo (pipeline end-to-end)\
` `└─ pipeline/\
`     `├─ context.py             # gestisce env/.env, percorsi cliente, policy redazione log; inietta logger nel contesto\
`     `├─ logging\_utils.py       # get\_structured\_logger(...): logger con filtri contesto (slug, file) + redazione + rotazione file\
`     `├─ env\_utils.py           # funzioni utilità per env (get\_env\_var, get\_bool, get\_int); redaction segreti; allow-list branch force-push\
`     `├─ exceptions.py          # definizione eccezioni tipizzate + tabella EXIT\_CODES\
`     `├─ config\_utils.py        # gestione config.yaml (lettura, scrittura con backup, merge di configurazioni)\
`     `├─ drive\_utils.py         # integrazione Google Drive (BFS download, upload file/cartelle con retry esponenziale e backoff)\
`     `├─ content\_utils.py       # conversione PDF→Markdown, generazione README/SUMMARY, validazioni contenuti Markdown\
`     `├─ gitbook\_preview.py     # build & serve Docker HonKit per anteprima (sempre detached; rispetta log redatto; nessun prompt nel modulo)\
`     `├─ github\_utils.py        # push su GitHub (branch da env `GIT\_DEFAULT\_BRANCH`; push incrementale senza force di default; logging avanzato)\
`     `├─ cleanup\_utils.py       # pulizia artefatti locali post-push (es. cartelle .git temporanee), sicura e opzionale\
`     `├─ path\_utils.py          # utilità path/slug: is\_safe\_subpath, validate\_slug (regex da config), sanitize\_filename, cache regex slug\
`     `└─ constants.py           # costanti globali (nomi di file/dir comuni, etc.)

docs/ (documentazione) contiene i file Markdown: index.md, user\_guide.md, developer\_guide.md, architecture.md, coding\_rule.md, policy\_push.md, versioning\_policy.md – mantenuti allineati al codice.

-----
## <a name="orchestratori-ruolo-e-cli"></a>🔌 Orchestratori: ruolo e CLI
Gli orchestratori sono gli **unici** componenti autorizzati a:

- leggere **input interattivi** dall’utente (prompt, conferme);
- determinare la **modalità** di esecuzione (batch vs interattivo) in base ai flag --non-interactive, --dry-run, --no-drive, --push|--no-push etc.;
- gestire la logica di **anteprima Docker** (controllo presenza Docker, eventuale prompt o auto-skip, avvio e stop del container);
- mappare le eccezioni dei moduli su codici di uscita (EXIT\_CODES) e terminare il processo con sys.exit() appropriati.
### <a name="convenzioni-cli-v1.0.5"></a>Convenzioni CLI (v1.0.5)
- **Slug “soft”** – può essere passato come argomento posizionale o tramite --slug. In modalità interattiva, se lo slug non è fornito, verrà richiesto via prompt. In modalità batch la mancanza dello slug causa errore.
- **Preview** –
- in **non‑interattivo**: se Docker non è disponibile viene **saltata automaticamente** (nessun blocco);
- in **interattivo**: se Docker non c’è, viene chiesto all’utente se proseguire senza anteprima (default **No**); se Docker c’è, chiede conferma per avviare l’anteprima (default **Sì**).
- **Push** –
- in **non‑interattivo**: è disabilitato di default (avviene solo se si passa esplicitamente --push);
- in **interattivo**: viene sempre chiesto all’utente se eseguire il push (default **No**). Di base il push è **incrementale** (pull–rebase → commit → push) e **non forza** gli aggiornamenti remoti salvo esplicita richiesta.
- **Force-push** – in entrambe le modalità è soggetto a restrizioni: richiede due flag --force-push **e** --force-ack <TAG> contemporanei (in batch, se anche uno manca, il push forzato viene bloccato con errore). In interattivo, se viene passato --force-push senza ack, l’orchestratore chiederà conferma e un tag di ACK dall’utente prima di procedere col force. Inoltre, il branch di destinazione deve essere tra quelli ammessi dalla policy (GIT\_FORCE\_ALLOWED\_BRANCHES), altrimenti il force viene rifiutato.
-----
## <a name="moduli-pipeline-linee-guida"></a>🧱 Moduli pipeline/\*: linee guida
### <a name="logging"></a>Logging
- Usa sempre get\_structured\_logger(name, log\_file=..., context=..., run\_id=..., extra\_base=..., rotate=...) per ottenere un logger configurato. Includi il context se disponibile così che il logger aggiunga automaticamente i metadati (slug, ecc.).
- La **redazione** di informazioni sensibili è centralizzata nel logger: se context.redact\_logs è True, tutti i messaggi e le eccezioni passati al logger verranno filtrati (via env\_utils.redact\_secrets) per mascherare token, ID e percorsi sensibili. I moduli **non devono** implementare logica di redazione propria.
- **Vietato** usare print() nei moduli; per output informativi utilizza sempre logger.info(), logger.warning(), logger.error(), ecc., così da rispettare il formato strutturato e la destinazione (file log e/o console).
- Unico file log per cliente: output/timmy-kb-<slug>/logs/onboarding.log. I moduli scrivono su questo file attraverso il logger fornito (il logger effettua rotazione se configurata).
- Includi nei log tutti i metadati utili (es. slug, file\_path, drive\_id, step corrente) usando il parametro extra={...} del logger. Evita di loggare messaggi vaghi senza contesto.
- Degradazione **sicura**: se il file log non è scrivibile (es. disco in sola lettura), il logger passa automaticamente a modalità console-only con avviso; in questo modo la pipeline continua a funzionare senza perdere completamente i log.
### <a name="gestione-degli-errori"></a>Gestione degli errori
- Solleva solo eccezioni definite in exceptions.py (o loro subclass) per segnalare errori: ad es. usa ConfigError per problemi di configurazione (slug non valido, variabile d’ambiente mancante, ecc.), DriveDownloadError per errori durante operazioni Drive, PreviewError per problemi nella preview Docker, e così via.
- **Non chiamare sys.exit() nei moduli**: se una condizione è critica, lancia un’eccezione appropriata e lascia che sia l’orchestratore a terminare il programma in modo controllato.
- Evita except Exception generici; intercetta invece errori specifici (es. FileNotFoundError, HTTPError, ecc.) e avvolgili in un’eccezione della pipeline con contesto (ad esempio: raise DriveDownloadError("messaggio") from e). In questo modo la causa originale non va persa ma l’eccezione è comunque tipizzata.
- Nei moduli, fai attenzione a rilasciare eventuali risorse (file, connessioni) in caso di errore se non usi contesti (with statement); la robustezza include pulire lo stato parziale quando necessario (es. se scrivi su un temp file, cancellalo su eccezione per evitare residui).
### <a name="path-io"></a>Path & I/O
- Usa pathlib.Path per gestire percorsi e file system (no stringhe grezze per path). Imposta encoding utf-8 nelle operazioni di I/O su file di testo.
- Prima di leggere o scrivere file, verifica sempre il percorso con is\_safe\_subpath(path, base\_dir) per assicurarti di operare dentro la sandbox prevista (output/timmy-kb-<slug> o sottodir). Questo previene incidenti in cui un path malformato potrebbe portare fuori dall’area di lavoro.
- Per scrivere file importanti, utilizza scritture **atomiche**: ad esempio scrivi su un file temporaneo e poi usa temp\_path.replace(dest\_path) per rimpiazzare, oppure funzioni dedicate (es. safe\_write\_file se presente). In caso di crash durante la scrittura, eviterai di lasciare file troncati o inconsistenze.
- Mantieni la struttura di output standard: utilizza i path forniti da ClientContext (context.raw\_dir, context.md\_dir, context.config\_dir, ecc.) invece di costruire stringhe manualmente. Questo garantisce coerenza e permette al contesto di applicare eventuali variazioni centralmente.
### <a name="x015cfbee10d796c698b6009f72bdb2a5829787e"></a>Dipendenze esterne (moduli pipeline chiave)
- **Google Drive** – Le operazioni Drive risiedono in drive\_utils.py (che a sua volta delega a moduli interni drive/): l’approccio è un download ricorsivo in ampiezza (BFS) per recuperare tutti i PDF, con meccanismi di retry esponenziale e tetto massimo di backoff. Le funzioni di upload creano l’intera struttura di cartelle sul Drive remoto partendo dallo YAML fornito. Usa i parametri redact\_logs in queste funzioni per assicurarti che nel log non compaiano ID o nomi sensibili di cartelle.
- **Conversione Markdown** – Implementata in content\_utils.py: converte PDF → Markdown usando strumenti esterni (es. PDF miner) e organizza i contenuti in maniera gerarchica. Genera inoltre i file indice README.md e SUMMARY.md. Assicurati che ogni nuova categoria o variazione nella struttura dei PDF sia gestita correttamente qui (es. evitare duplicati di heading, come fixato in v1.0.5).
- **Anteprima (Docker HonKit)** – Modulo gitbook\_preview.py: costruisce l’immagine Docker HonKit e lancia il container in modalità *detached* per servire la preview su http://localhost:4000. Non effettua prompt (tutta la logica interattiva è nell’orchestratore). Raccoglie comunque l’output e gli errori di Docker nel log strutturato. Il parametro redact\_logs viene passato per mascherare eventuali stringhe sensibili nel log di Docker (anche se di norma il container non stampa segreti).
- **Git & GitHub** – Modulo github\_utils.py: fornisce la funzione push\_output\_to\_github(context, ...) che esegue clonazione, commit e push. Il branch di destinazione è calcolato come descritto in architettura (risolve GIT\_DEFAULT\_BRANCH). Il push è incrementale: se il remoto rifiuta (non fast-forward), tenta un pull --rebase e riprova una volta. Logga i dettagli (branch, SHA locali/remoti, ecc.) e *non* mette mai il token in log (usa il header HTTP come da best practice). In v1.0.4+ supporta i parametri force\_push e force\_ack: se force\_push=True, usa git push --force-with-lease anziché push normale; l’ACK viene inserito come trailer Force-Ack: nel commit.
- **Pulizia post-push** – Modulo cleanup\_utils.py: contiene funzioni per ripulire eventuali residui del push, ad esempio il repository temporaneo .push\_<rand> che potrebbe essere rimasto in output/timmy-kb-<slug> in caso di interruzioni. La funzione clean\_push\_leftovers(context) elimina in sicurezza queste cartelle se l’utente acconsente (orchestratore chiede conferma). Logga a livello INFO i dettagli dell’operazione (quali file/cartelle ha rimosso) e cattura eventuali errori senza far fallire la pipeline (warning in caso di eccezioni non critiche).
-----
## <a name="variabili-dambiente-per-sviluppatori"></a>🌿 Variabili d’ambiente (per sviluppatori)
- GIT\_DEFAULT\_BRANCH – Branch Git di default utilizzato per il push e il checkout iniziale (es: "main"). Influenza il comportamento di github\_utils.push\_output\_to\_github.
- GITHUB\_TOKEN – Personal Access Token GitHub usato per autenticare le operazioni di push. Deve avere permessi repo (è passato in header, non in CLI).
- DRIVE\_ID / DRIVE\_PARENT\_FOLDER\_ID – ID dello Shared Drive (o cartella specifica) dove creare la cartella del cliente su Google Drive. Almeno uno deve essere configurato per abilitare l’upload/download da Drive.
- SERVICE\_ACCOUNT\_FILE / GOOGLE\_APPLICATION\_CREDENTIALS – Path al file JSON del Service Account Google utilizzato per autenticarsi alle API Drive. Obbligatorio (uno dei due) se si vuole utilizzare le funzionalità Drive.
- LOG\_REDACTION – Policy di redazione log sensibili: auto (comportamento automatico in base a ambiente, default), on (forza sempre mascheramento) oppure off (disabilita mascheramento). In modalità auto, la redazione viene abilitata se l’ambiente è prod/production o CI=true, e disabilitata in debug locale.
- ENV – Nome dell’ambiente logico (es. dev, prod, production, ci). Usato insieme a CI per determinare la redazione automatica dei log. Convenzione: settare ENV=production in ambienti reali, ENV=dev in sviluppo locale.
- CI – Se settato a true (ad esempio dalle piattaforme CI), viene considerato equivalente a ENV=ci per abilitare comportamenti specifici (come la redazione log auto e il silenziamento di prompt interattivi).
- GIT\_FORCE\_ALLOWED\_BRANCHES – (Introdotta in v1.0.4) Elenco di pattern (separati da virgola o newline) dei branch su cui è **consentito** il force push. Esempio: main,release/\* consente push forzato solo su main e sui branch che iniziano per release/. Se la variabile non è impostata o vuota, per default l’orchestratore interpreta che **non ci sono vincoli** (ma può comunque decidere di bloccare force push a sua discrezione quando non strettamente necessario).

*Nota:* non aggiungere mai file di credenziali (.env, JSON del service account, token in chiaro) al repository. Utilizzare .gitignore e variabili d’ambiente locali per gestire questi dati sensibili.
### <a name="policy-di-redazione-log-richiamo"></a>Policy di redazione log (richiamo)
- Il flag effettivo per la redazione vive nel ClientContext.redact\_logs ed è calcolato in ClientContext.load() considerando:
- LOG\_REDACTION=on|always|1|true|yes ⇒ **redazione forzata ON** (maschera sempre token, ID, percorsi).
- LOG\_REDACTION=off|never|0|false|no ⇒ **redazione forzata OFF** (mai mascherare).
- LOG\_REDACTION=auto (default) ⇒ abilita la redazione solo se: l’ambiente è di produzione/CI (ENV impostato a prod/production o CI=true) **oppure** se sono presenti credenziali sensibili nel contesto (es. GITHUB\_TOKEN o credenziali Google Drive). Se il livello di log è DEBUG, la redazione auto viene comunque disattivata per facilitare il troubleshooting locale.
- I moduli **non devono implementare logiche aggiuntive** di mascheramento; si limitano a utilizzare il logger strutturato passando il contesto, così che la policy suddetta sia applicata in modo uniforme in tutta la pipeline.
- Qualora il pattern di mascheramento (es. regex dello slug) venga aggiornato in runtime (ad esempio caricando un nuovo config con regex diversa), assicurarsi di richiamare la funzione clear\_slug\_regex\_cache() in path\_utils.py per evitare di continuare a usare la vecchia regex in cache.
-----
## <a name="flussi-tecnici-sintesi"></a>🧩 Flussi tecnici (sintesi)
*(Eventuale sezione riassuntiva dei flussi implementativi interni, se prevista, con diagrammi o elenco puntato dei passi interni principali.)*

-----
