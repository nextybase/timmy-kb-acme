## <a name="docsarchitecture.md"></a>docs/architecture.md
# <a name="xd65d6c9a41bc0687650fccdac300771948f07ac"></a>Architettura Tecnica – Timmy-KB (v1.0.5 Stable)
Questa pagina descrive l’architettura **attuale** del progetto (patch di mantenimento). È allineata al CHANGELOG **1.0.5** e riflette i miglioramenti di robustezza introdotti sugli strumenti CLI di supporto **senza** cambiamenti nei flussi principali della pipeline.

-----
## <a name="principi-architetturali"></a>1) Principi architetturali
- **Separazione dei ruoli:** gli **orchestratori** gestiscono UX/CLI (prompt utente, conferme, scelta modalità, gestione errori); i **moduli pipeline** eseguono operazioni tecniche e **non** terminano mai il processo (**no** `sys.exit()`, **no** `input()` nei moduli).
- **HiTL pragmatico:** intervento umano solo negli orchestratori (prompt interattivi); in batch (`--non-interactive`) l’esecuzione è deterministica (nessun input richiesto).
- **Idempotenza & sicurezza:** rigore sui percorsi (*path-safety* con `is_safe_subpath`), scritture **atomiche** per file critici, log **unificato** per cliente, nessun segreto in chiaro nei log.
- **Coerenza documentale:** ogni modifica al comportamento della pipeline richiede un aggiornamento contestuale della documentazione (codice e doc evolvono insieme).

-----
## <a name="mappa-dei-componenti"></a>2) Mappa dei componenti
```
src/
 ├─ pre_onboarding.py          # Orchestratore Fase 0 (setup cliente + struttura Drive opzionale)
 ├─ onboarding_full.py         # Orchestratore Fase 1 (download → conversione → anteprima → push)
 └─ pipeline/
     ├─ context.py             # Gestione .env/ambiente, risoluzione percorsi cliente; logging centralizzato (no print)
     ├─ logging_utils.py       # get_structured_logger(...): logger con filtri contesto, redazione e rotazione file
     ├─ exceptions.py          # Tassonomia errori + mappa codici EXIT_CODES (usata dagli orchestratori)
     ├─ env_utils.py           # Helpers per env: get_env_var/get_bool/get_int, redazione segreti, allow-list branch force-push
     ├─ config_utils.py        # Gestione di config.yaml (lettura, scrittura con backup .bak, merge variabili)
     ├─ drive_utils.py         # API Google Drive (facciata): download ricorsivo PDF (BFS), creazione struttura remota da YAML (retry con tetto)
     ├─ content_utils.py       # Conversione PDF→Markdown, generazione SUMMARY/README, validazioni struttura Markdown
     ├─ gitbook_preview.py     # Generazione book.json/package.json; avvio Docker HonKit (build & serve) sempre senza prompt e *detached*
     ├─ github_utils.py        # Push su GitHub (usa GITHUB_TOKEN; branch da GIT_DEFAULT_BRANCH; push incrementale senza force di default)
     └─ cleanup_utils.py       # Pulizia post-push: rimozione artefatti locali legacy (repo .git temporanei) in modo sicuro
```
**Dati e output per cliente:** ogni cliente ha la propria struttura `output/timmy-kb-<slug>/` con sottocartelle `raw/`, `book/`, `config/`, `logs/`. Il log strutturato risiede in `logs/onboarding.log` (unico file per tutte le fasi, con eventuale rotazione).

-----
## <a name="flussi-end-to-end-immutati"></a>3) Flussi end-to-end (immutati)
### <a name="a-pre_onboarding.py-setup-iniziale"></a>A) `pre_onboarding.py` (setup iniziale)
1. **Input** – accetta lo `slug` (posizionale o `--slug`), il nome cliente `--name` (opzionale), `--dry-run` e `--non-interactive`.
2. **Setup locale** – crea la struttura locale `raw/`, `book/`, `config/`, `logs/`. Genera/aggiorna `config.yaml` in `config/` (con backup automatico `.bak` se già presente).
3. **Drive (opzionale)** – se **non** è specificato `--dry-run` **e** le variabili Drive sono configurate, crea la cartella del cliente nello Shared Drive (o nella cartella padre indicata) e genera l’intera struttura remota da YAML. Carica quindi `config.yaml` su Drive e aggiorna il file locale con gli **ID Drive** ottenuti.
   - Se le variabili Drive **mancano** e **non** stai usando `--dry-run`, l’esecuzione termina con **ConfigError** (nessun prompt “procedere senza Drive”).  
4. **Log** – tutte le azioni sono registrate nel file `output/timmy-kb-<slug>/logs/onboarding.log`. I moduli **non** usano `print()`.

### <a name="b-onboarding_full.py-pipeline-completa"></a>B) `onboarding_full.py` (pipeline completa)
1. **Input** – accetta `slug`, `--non-interactive`, `--dry-run`, `--no-drive` (per saltare Drive), `--push|--no-push`, `--port` (porta anteprima, default 4000).  
   *Opzioni avanzate:* `--force-push` e `--force-ack <TAG>` (gateway a due fattori, introdotti in 1.0.4) con **allow-list** branch (`GIT_FORCE_ALLOWED_BRANCHES`).
2. **Download RAW (opzionale)** – se **non** è attivo `--no-drive` **e** non è `--dry-run`, scarica ricorsivamente i PDF da Drive nella cartella locale `raw/` (idempotenza su MD5/size, preservando le sottocartelle). Se `--no-drive` o `--dry-run`, la fase è **saltata** (log dello skip).
3. **Conversione Markdown** – converte i PDF in `raw/` generando i `.md` in `book/`. Al termine crea `SUMMARY.md` e `README.md` in `book/` e valida la consistenza della directory.
4. **Anteprima (Docker)** –
   - **Interattivo:** se Docker è disponibile, l’orchestratore chiede *«Avviare l’anteprima ora?»* (default **Sì**) e lancia HonKit in modalità **detached**; se Docker **non** c’è, chiede *«Proseguire senza anteprima?»* (default **No**).  
   - **Non-interactive (batch/CI):** **nessun prompt**; se Docker **non** è disponibile, la preview viene **saltata automaticamente**. L’orchestratore garantisce comunque lo **stop automatico** del container all’uscita se la preview è stata avviata.
5. **Push (opzionale)** – in batch, avviene **solo** con `--push`; in interattivo, previo consenso esplicito. Verifica `GITHUB_TOKEN`, determina il branch da `GIT_DEFAULT_BRANCH` (fallback `main`) ed esegue un push **incrementale** (no force di default, con eventuale *retry*). I soli file pubblicati sono i `.md` sotto `book/` (esclusi `.bak`).  
6. **Log & exit** – gli orchestratori mappano eccezioni tipizzate in codici deterministici (`EXIT_CODES`) e terminano col codice appropriato.

-----
## <a name="decisioni-runtime-state-machine-minimale"></a>4) Decisioni runtime (state machine minimale)
- **Slug:** se fornito sia posizionalmente sia con `--slug`, prevale il posizionale; in batch, se manca/valido → errore (exit 2); in interattivo si richiede reinserimento finché non valido.
- **Interactive vs batch:** in `--non-interactive` **non** ci sono prompt; la preview viene saltata automaticamente se Docker non è disponibile; il push è disabilitato a meno di `--push`.
- **Alias deprecati:** `--skip-drive` e `--skip-push` rimappati internamente a `--no-drive`/`--no-push` con warning di deprecazione.
- **Branch Git di destinazione:** determinato in ordine da `context.env["GIT_DEFAULT_BRANCH"]` (o `GITHUB_BRANCH`), poi variabili d’ambiente di processo, altrimenti fallback `main`.

-----
## <a name="logging-errori-sicurezza"></a>5) Logging, errori, sicurezza
- **Logger unico per cliente:** ogni orchestratore inizializza un logger strutturato (pre_onboarding/onboarding_full) che scrive su `output/timmy-kb-<slug>/logs/onboarding.log`.
- **Redazione log:** filtri automatici mascherano token/ID sensibili (abilitati da `LOG_REDACTION` o in contesti CI/prod); in `DEBUG` la redazione è disattivata.
- **Tassonomia errori:** i moduli alzano eccezioni specifiche (`ConfigError`, `DriveDownloadError`, `PreviewError`, `PushError`, `ForcePushError`, …) → mappate in `EXIT_CODES` dagli orchestratori.
- **Path-safety:** percorsi risolti con `pathlib.Path` e verificati da `is_safe_subpath` rispetto alla sandbox cliente (`output/timmy-kb-<slug>`). Scritture **atomiche** per file critici.
- **Credenziali:** lette solo da env/.env, **mai** salvate su disco dalla pipeline; le invocazioni esterne (API, git/gh) non espongono segreti.

-----
## <a name="modifiche-di-questa-release-v1.0.5"></a>6) Modifiche di questa release (v1.0.5)
- **Orchestratori:** flussi core **immutati** rispetto alla 1.0.4 (inclusi i gate `--force-push`/`--force-ack` e allow-list branch).
- **Strumenti ausiliari:** migliorati (`refactor_tool.py`, `cleanup_repo.py`, `gen_dummy_kb.py`) — nessun impatto sui flussi core.
- **Preview Docker:** confermato comportamento *detached* a livello di modulo; orchestratore garantisce **stop automatico** del container.
- **Push GitHub:** incrementale by default, retry su divergenze; pubblicazione **solo** dei `.md` in `book/`.
- **Slug:** regex letta da `config.yaml` all’avvio e **cachata**; funzione `clear_slug_regex_cache()` per invalidarla.

*Nota:* la v1.0.5 è retro‑compatibile con la 1.0.4 e non introduce breaking changes nei flussi operativi.

-----
## <a name="x3b02949f0e392e5b17fa80cb8080610598e5047"></a>7) Variabili d’ambiente (rilevanti in architettura)
- `GIT_DEFAULT_BRANCH` – branch Git di default per checkout/push (es. `main`).
- `GITHUB_TOKEN` – token GitHub per autenticare il push.
- `DRIVE_ID` / `DRIVE_PARENT_FOLDER_ID` – ID della radice su Google Drive (uno dei due deve essere impostato per abilitare le operazioni Drive).
- `GOOGLE_APPLICATION_CREDENTIALS` / `SERVICE_ACCOUNT_FILE` – path al JSON del Service Account Google (per Drive API).
- `GIT_FORCE_ALLOWED_BRANCHES` – allow-list dei branch su cui consentire eventuali force-push (es. `main,release/*`). Se vuota, la decisione finale rimane all’orchestratore (che di default li blocca).
- `LOG_REDACTION` – policy di redazione log sensibili: `auto` (default), `on`, `off`.
- `ENV` – ambiente logico (`dev`, `prod`, `production`, `ci`); con `CI` influenza la redazione automatica.
- `CI` – flag di contesto CI: se true e `LOG_REDACTION=auto`, abilita la redazione automatica.

-----
## <a name="xeba6b3f418bbcabe853b1aa8701811a446a9a4b"></a>8) Appendice – Sequenza sintetica (diagramma ASCII)
*(Illustrazione testuale dei passi principali dei flussi `pre_onboarding` e `onboarding_full`, se presente nel documento originale.)*
