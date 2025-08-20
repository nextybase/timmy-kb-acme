## <a name="header"></a><a name="content"></a><a name="readme.md"></a>README.md
# <a name="xb014f7d5516556b37fe1f684436ebd3b6f237b3"></a>Timmy-KB — Knowledge Base Pipeline (v1.0.5 Stable)
Pipeline modulare per trasformare i PDF del cliente in una **KB Markdown AI‑ready** (GitBook/Honkit), con anteprima Docker opzionale e push opzionale su GitHub.

Stato: **v1.0.5 Stable**. Documentazione aggiornata alle migliorie introdotte (strumenti CLI potenziati, fix minori) e allineata al CHANGELOG 1.0.5. Nessun cambiamento ai flussi principali rispetto alla 1.0.4.

-----
## <a name="tldr"></a>TL;DR
1. **Pre‑onboarding** (setup locale + Drive opzionale)

   py src/pre_onboarding.py --slug acme --non-interactive --dry-run
1. **Onboarding completo** (download → conversione → preview → push)

   # senza Drive e senza push (anteprima detached se Docker è disponibile)\
   py src/onboarding_full.py --slug acme --no-drive --non-interactive
-----
## <a name="requisiti"></a>Requisiti
- **Python ≥ 3.10**
- **Docker** (per la preview HonKit; se assente la preview viene saltata in batch)
- **Credenziali Google Drive** (Service Account JSON) per accedere alle API Drive
- **GitHub token** (GITHUB_TOKEN) solo se si vuole eseguire il push
### <a name="variabili-dambiente"></a>Variabili d’ambiente
- SERVICE_ACCOUNT_FILE / GOOGLE_APPLICATION_CREDENTIALS – path al file JSON del Service Account GCP
- DRIVE_ID / DRIVE_PARENT_FOLDER_ID – ID della radice (Drive condiviso o cartella) per i PDF del cliente
- GITHUB_TOKEN – token GitHub per autorizzare il push (opzionale, richiesto solo per push)
- GIT_DEFAULT_BRANCH – nome del branch Git predefinito per il push (default: main)
- LOG_REDACTION – policy di redazione log sensibili (auto|on|off)
-----
## <a name="struttura-di-output-per-cliente"></a>Struttura di output per cliente
output/timmy-kb-<slug>/\
`  `├─ raw/        # PDF scaricati (opzionale)\
`  `├─ book/       # Markdown generati + SUMMARY.md + README.md\
`  `├─ config/     # config.yaml (mapping semantico)\
`  `└─ logs/       # onboarding.log (unico log strutturato per cliente, rotazione opzionale)

-----
## <a name="flussi"></a>Flussi
### <a name="x505b8b28674f33bae77ed5795ca09a71975b05b"></a>A) Pre-onboarding (setup) — *flusso interattivo di base*
Per avviare la preparazione dell’ambiente cliente esegui:

py src/pre_onboarding.py

**Sequenza tipica (comportamento reale):**

1. **Slug cliente** – viene richiesto lo *slug* (es. acme). Se non valido, il sistema spiega il motivo e chiede un nuovo valore.
1. **Creazione struttura locale** – la pipeline **crea direttamente** le cartelle `raw/`, `book/`, `config/`, `logs/` e il file `config.yaml` (con backup `.bak` se era già presente). **Nessun prompt di conferma** in questa fase.
1. **Google Drive (opzionale)** –
   - Se le variabili Drive **sono configurate**, la pipeline **procede automaticamente** a creare/aggiornare la struttura su Drive e a caricare `config.yaml` nella cartella cliente.
   - Se le variabili Drive **non sono configurate** e **non** stai usando `--dry-run`, l’esecuzione termina con **ConfigError** (vedi *Troubleshooting*). Per predisporre solo l’ambiente **locale** senza toccare Drive, usa `--dry-run`.
1. **Riepilogo finale** – stampa le azioni eseguite e indica dove trovare i file generati.

*Nota:* in questa fase **non** viene eseguita alcuna anteprima né push. Il pre-onboarding serve unicamente a predisporre l’ambiente locale (e remoto su Drive, se richiesto).

-----
### <a name="x3eb9f8c87220d78972897c25749c6111c0e2dbd"></a>B) Onboarding completo — *flusso interattivo di base*
Per completare l’onboarding esegui:

py src/onboarding_full.py

**Sequenza tipica:**

1. **Slug cliente** – viene richiesto lo *slug*, con validazione immediata; se non conforme, spiega l’errore e richiede un nuovo valore.
1. **Conversione PDF → Markdown** – parte automaticamente (nessun prompt) con log di avanzamento; al termine genera `SUMMARY.md` e `README.md` sotto `book/`.
1. **Anteprima HonKit (Docker)** –
   - Se Docker è disponibile: *«Avviare l’anteprima ora?»* (default **Sì**). In caso di conferma, la preview parte in modalità **detached** (non blocca la pipeline) e viene **fermata automaticamente** al termine.
   - Se Docker non è disponibile: *«Proseguire senza anteprima?»* (default **No**). Se confermi (rispondendo **Sì**), la pipeline continua senza avviare la preview.
1. **Pubblicazione su GitHub (opzionale)** –
   - *«Eseguire il push su GitHub?»* (default **No**). Se accetti, la pipeline verifica la presenza di `GITHUB_TOKEN` e propone il branch di destinazione di default (letto da `GIT_DEFAULT_BRANCH`, es. `main`), consentendoti di confermarlo o modificarlo.
1. **Pulizia finale** –
   - *«Eseguire il cleanup?»* (default **Sì**). Rimuove eventuali file temporanei e backup non più necessari, verificando che la preview sia stata arrestata. Se per qualche motivo il container dell’anteprima risultasse ancora attivo, viene proposta la chiusura forzata.

**Dettagli tecnici anteprima:**\
- Porta predefinita **4000** (puoi cambiarla via prompt o passando `--port 4000`).\
- Nome container Docker: `honkit_preview_<slug>`.

-----
## <a name="comandi-rapidi"></a>4) Comandi rapidi
### <a name="flusso-consigliato-interattivo"></a>Flusso consigliato (interattivo)
# 1) Setup cliente (solo locale + config Drive)\
py src/pre_onboarding.py\

# 2) Onboarding completo (conversione, anteprima, push opzionale, cleanup finale)\
py src/onboarding_full.py
### <a name="varianti-batchci-senza-prompt"></a>Varianti batch/CI (senza prompt)
# Setup minimale (nessun accesso a servizi remoti)\
py src/pre_onboarding.py --slug acme --non-interactive --dry-run\

# Onboarding senza Drive e anteprima (auto-skip preview se Docker non c'è), push disabilitato\
py src/onboarding_full.py --slug acme --no-drive --non-interactive\

# Onboarding completo con push esplicito (token e branch preimpostati)\
export GITHUB_TOKEN=ghp_xxx\
export GIT_DEFAULT_BRANCH=main\
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push

*Tip:* Su Linux/Mac usa `python` al posto di `py` se preferisci.

-----
## <a name="anteprima-honkit-docker"></a>Anteprima (HonKit + Docker)
- L’anteprima viene eseguita **in modalità detached** e **non** blocca il flusso della pipeline.
- L’orchestratore arresta **automaticamente** il container Docker alla fine dell’esecuzione (anche se salti la fase di push).
- In `--non-interactive` (batch/CI), se Docker non è disponibile la preview viene **saltata automaticamente**. In modalità interattiva, in assenza di Docker ti verrà chiesto se proseguire senza anteprima (default **NO**).

**Porta e container default:** porta HTTP **4000** (override con `--port`), container `honkit_preview_<slug>`.

-----
## <a name="push-su-github-opzionale"></a>Push su GitHub (opzionale)
- Gestito dal modulo `src/pipeline/github_utils.py` (funzione `push_output_to_github`).
- Richiede un `GITHUB_TOKEN` valido nel contesto.
- Il branch di destinazione è letto da `GIT_DEFAULT_BRANCH` (se non impostato, fallback su `main`).
- In modalità batch/CI, il push **non** avviene a meno di specificare `--push`. In interattivo viene sempre richiesta conferma prima di procedere.
- Vengono pubblicati **solo** i file `.md` sotto `book/` (ignora eventuali file di backup `.bak`).
- Dopo il push, l’orchestratore può proporre un cleanup degli artefatti legacy generati (es. repository temporaneo di push).

**Esempio – push in batch:**

export GITHUB_TOKEN=ghp_xxx\
export GIT_DEFAULT_BRANCH=main\
py src/onboarding_full.py --slug acme --no-drive --non-interactive --push

-----
## <a name="regole-operative-estratto"></a>Regole operative (estratto)
- **Orchestratori:** gestiscono UX/CLI, prompt e mappatura deterministica delle eccezioni → `EXIT_CODES`.
- **Moduli pipeline:** eseguono azioni tecniche; **no** `input()` e **no** `sys.exit()` (non terminano mai il processo).
- **Logging:** utilizzare sempre logger strutturati (file `onboarding.log` unico per cliente); niente `print()`. La redazione dei log sensibili è abilitabile via policy centralizzata.
- **Sicurezza I/O:** verificare i percorsi con `is_safe_subpath`; usare scritture atomiche; mai includere segreti nei log.
- **Slug:** validato tramite regex definita in `config/config.yaml` (viene **messa in cache**, con funzione di clear in caso di modifica runtime).
- **Alias deprecati:** `--skip-drive` e `--skip-push` sono accettati solo per retrocompatibilità (generano un warning) e vengono rimappati internamente a `--no-drive` e `--no-push`.
-----
## <a name="exit-codes-estratto"></a>Exit codes (estratto)
- **0** → esecuzione completata con successo
- **2** → `ConfigError` (es. variabili richieste mancanti, slug non valido in modalità batch)
- **21** → `DriveDownloadError` (errore durante download da Google Drive)
- **30** → `PreviewError` (errore nella fase di anteprima Docker)
- **40** → `PushError` (errore nella fase di push su GitHub)
- **41** → `ForcePushError` (tentativo di push forzato non consentito)

La mappatura completa dei codici di uscita è definita nel file `pipeline/exceptions.py` ed è documentata nella Guida Utente.

-----
## <a name="tools"></a>Tools
Gli strumenti ausiliari in `src/tools/` sono script **standalone interattivi** (vanno eseguiti manualmente da terminale). Servono per compiti di manutenzione e debug del repository.

- **cleanup_repo.py** – Pulizia sicura degli artefatti locali di uno specifico slug e, se richiesto, eliminazione del repository GitHub corrispondente (tramite CLI `gh`).\
  *Uso:*

  py src/tools/cleanup_repo.py
- **gen_dummy_kb.py** – Genera una KB di test completa con slug fissato `dummy`. Crea la struttura `raw/`, `book/`, `config/` usando gli YAML di esempio (`config/cartelle_raw.yaml` e `config/pdf_dummy.yaml`) e produce PDF fittizi (usa file `.txt` se la libreria `fpdf` non è disponibile).\
  *Uso:*

  py src/tools/gen_dummy_kb.py
- **refactor_tool.py** – Utility interattiva per ricerca/sostituzione nel codice. Offre due modalità: **1) Trova** (solo ricerca, elenca file e occorrenze) e **2) Trova & Sostituisci** (richiede conferma prima di applicare modifiche). Crea backup automatici con estensione `.bak` per ogni file modificato.\
  *Uso:*

  py src/tools/refactor_tool.py

*Tutti i log generati dagli strumenti sono strutturati come quelli della pipeline.* Le azioni di skip o i percorsi non trovati vengono registrati a livello **DEBUG** (non interrompono l’esecuzione).

-----
## <a name="troubleshooting"></a>Troubleshooting
- **Docker non installato:** in modalità batch la preview viene saltata automaticamente; in interattivo potrai scegliere se proseguire senza anteprima.
- **Token GitHub mancante:** il push fallisce con errore; assicurati di impostare `GITHUB_TOKEN` oppure esegui con `--no-push` per evitare il tentativo.
- **Slug non valido:** in modalità batch l’esecuzione termina con errore (exit code **2**); in interattivo viene richiesto di inserirne uno valido finché non soddisfa la regex.
- **Drive non configurato:** se esegui `pre_onboarding.py` senza `--dry-run` ma non hai impostato `DRIVE_ID`/`DRIVE_PARENT_FOLDER_ID` e credenziali, otterrai un **ConfigError**. Usa `--dry-run` o configura le variabili richieste.
-----
## <a name="licenza"></a>Licenza
Questo progetto è distribuito sotto licenza **GNU GPL v3.0**. Per dettagli, consulta il file [LICENSE](LICENSE.md).
