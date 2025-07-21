# 📦 CHANGELOG – OnBoarding NeXT

## v1.2.3 - 2025-07-22 - Naming & Logging Clean Release

### 📏 Uniformità naming e modularità
- Applicata una **naming convention rigorosa** per tutti i file, funzioni e variabili: ora ogni funzione segue il pattern `azione_oggetto[_origine_destinazione]` in snake_case, con nomi autoesplicativi e nessuna abbreviazione opaca.
- **Refactoring completo dei moduli**: accorpati e rinominati i file in `/src/pipeline/` per dominio funzionale (`drive_utils.py`, `config_utils.py`, `content_utils.py`, ecc.).
- Eliminata la distinzione fra “utils” e “ingest”: ora tutte le funzioni core della pipeline sono raccolte in `/src/pipeline/`.
- Separati i tool CLI di manutenzione/cleaning in `/src/tools/` con naming `<azione>_tool.py`.
- I moduli di enrichment/AI restano in `/src/semantic/`, ora anch’essi uniformati nei nomi e nel logging.

### 🪵 Logging strutturato centralizzato
- Introdotto il modulo unico `logging_utils.py` con la funzione `get_structured_logger` per una configurazione uniforme dei log.
- **Livelli di log** coerenti e sempre usati (DEBUG, INFO, WARNING, ERROR), con messaggi espliciti, contestuali e supporto emoji per ogni step rilevante.
- Possibilità di log su console e su file, configurabile via parametro e .env.
- Eliminati tutti i `print()` superflui: log e messaggi CLI separati in modo chiaro.

### 🧩 Robustezza, testabilità e orchestrazione
- Tutti i moduli interni accettano un oggetto `config: dict` come parametro principale (dove sensato), garantendo orchestrazione solida tra pre-onboarding, onboarding e enrichment.
- Funzioni di output e manipolazione file/cartelle ora sempre **fail-safe**: ogni path viene verificato e creato se mancante, con log dettagliati su ogni anomalia.
- Tutte le funzioni critiche restituiscono un valore di esito (bool/int), e gli errori sono sempre propagati agli orchestratori tramite logging e gestione eccezioni.
- **Docstring e commenti estesi** in ogni funzione pubblica per favorire manutenibilità e onboarding di nuovi dev.
- Pipeline testata end-to-end: tutti i passaggi, dall’input CLI fino al deploy GitHub, funzionano in modo robusto, tracciato e predicibile.

### 🔎 Revisione orchestratori e moduli semantic
- Aggiornati `pre_onboarding.py` e `onboarding_full.py` con i nuovi import e chiamate funzione, ora completamente aderenti alle naming rule.
- Aggiunto logging strutturato a tutti gli step dei main script.
- Moduli di semantic enrichment (`semantic_extractor.py`, `semantic_mapping.py`) allineati a naming, logging e robustezza pipeline, con fix dei riferimenti dopo i rename.

### 🛠️ Chiusura versioning e preparazione v1.2.4
- Rilasciata pipeline pronta per parsing PDF reale, arricchimento AI-driven e introduzione di nuovi tool/CLI.
- La struttura attuale è pronta per essere estesa e testata anche in ambienti CI/CD, con log e naming “AI-ready”.
- Il refactoring ha migliorato significativamente la leggibilità, la tracciabilità dei processi e la facilità di debugging/upgrade futuro.

**Upgrade altamente raccomandato per tutte le istanze operative e i team che contribuiscono al framework NeXT.**

---

## v1.2.2 - 2025-07-21 - Arricchimento semantico e refactoring struttura

### 🧠 Separazione tra pipeline e arricchimento semantico
- Creata la directory `src/semantic/` dedicata alle funzioni di semantic enrichment.
- Spostato e riprogettato `semantic_extractor.py`: ora gestisce la conversione PDF→Markdown *arricchito* (inserendo frontmatter semantico da mapping YAML), lavorando sia in modalità standalone sia come modulo richiamato dalla pipeline.
- Tutti i modelli e algoritmi AI/NLP futuri saranno inseriti **solo** in `/semantic/` senza mai modificare la pipeline di produzione.

### 🔄 Workflow idempotente e automatizzato
- In modalità standalone: cancellazione selettiva di tutti i markdown (inclusi README.md/SUMMARY.md) prima della nuova conversione, solo su richiesta esplicita dell’utente.
- Conversione batch di tutti i PDF presenti in `output/timmy-kb-<slug>/raw` e sottocartelle; output in `output/timmy-kb-<slug>/` con arricchimento semantico basato sul mapping YAML.
- Generazione e aggiornamento automatico di `SUMMARY.md` e `README.md` dopo ogni enrichment.

### 🛡️ Robustezza e modularità
- Patchata la gestione degli import cross-platform per consentire sia l’uso CLI che pipeline senza errori di path/package.
- L’arricchimento semantico ora è completamente disaccoppiato dal core della pipeline (drive, ingest, build, push), garantendo la massima estendibilità futura.
- Tutto il codice semantic-ready può essere testato e aggiornato indipendentemente dalle evoluzioni della pipeline principale.

## v1.2 1.2.1 - 2025-07-20 - Gestione percorsi e anteprima docker

### 🧠 Refactoring della struttura: 
suddivisione della pipeline in moduli dedicati (drive_utils, config_loader, pdf_to_md, semantic_extractor, build_summary, gitbook_preview, github_push, cleanup) e script principali separati per Pre-Onboarding e Onboarding completo. Centralizzati percorsi e parametri in .env per garantire coerenza tra le fasi.
Config & naming unificati: introdotto file config.yaml per ogni cliente (contenente slug e nome) generato in pre-onboarding e caricato in onboarding completo. Utilizzo sistematico dello slug cliente per nominare cartelle (es. cartella Drive e output locale timmy_kb_<slug>) e repository GitHub (timmy-kb-<slug>), migliorando uniformità e identificazione dei clienti.

### 🔄 Gestione percorsi migliorata: 
utilizzati template configurabili (RAW_DIR_TEMPLATE, OUTPUT_DIR_TEMPLATE in .env) combinati con lo slug per calcolare dinamicamente i path dei dati grezzi e dell’output. Rimosse stringhe hardcoded in favore di pathlib e variabili d’ambiente, aumentando portabilità (supporto percorsi Windows/*nix).
Logging strutturato: uniformato il logging su tutti i moduli con formato standard timestamp/level/message e uso di emoji (✅, ❌, ⚠️, ℹ️) per evidenziare esiti e fasi. Messaggi più espliciti per errori (es. indicazione variabili mancanti, file non trovati) e rimozione di stampe non strutturate, facilitando debug e tracciabilità.
Conferme manuali & sicurezza: aggiunte richieste di conferma interattiva prima di azioni critiche: upload struttura su Google Drive, push du GitHub, cancellazione file locali. Implementata pulizia finale non distruttiva: lo script ora svuota la cartella output invece di cancellarla interamente, con verifica del percorso atteso per evitare rimozioni errate.

### 🛠️ Integrazione GitHub e anteprima: 
automatizzato il deploy su GitHub via GitHub CLI gh (init repo, commit, gh repo create --push in un solo comando). Introdotta anteprima locale con Docker Honkit (GitBook) su localhost:4000 pre-deploy, con avvio e terminazione controllati dallo script.
Pipeline end-to-end completa: garantito flusso continuo nonostante funzionalità placeholder – download ricorsivo dei PDF dal Drive (anche in sottocartelle), conversione PDF→MD simulata con segnaposto, estrazione semantica di base in JSON – mantenendo l’architettura pronta per integrazioni future senza modificare l’interfaccia.

### 🛠️ Bugfix: 
risolti problemi di path e permessi su Windows (es. rimozione file aperti), aggiunti fallback per variabili d’ambiente non impostate (default per SERVICE_ACCOUNT_FILE, GITBOOK_IMAGE, ecc.). Corretta gestione errori delle API esterne: ora eventuali eccezioni durante chiamate Google Drive o subprocess (Docker/Git) vengono intercettate e loggate, con terminazione pulita del processo se necessario.

## v1.2 – Idempotenza, rollback e GitHub intelligente (luglio 2025)

### 🧠 Miglioramenti robustezza

- ✅ Check anticipato: la pipeline ora verifica se la **repo GitHub esiste** prima di eseguire l'onboarding.
- ⚠️ Prompt interattivo per scegliere se pushare su repo esistente o annullare.
- ✅ Il check viene fatto **prima del download** dei PDF, evitando operazioni inutili.

### 🔄 Idempotenza e fail-safe

- 🧹 Se la creazione della cartella cliente su Drive fallisce, viene eseguito un **rollback automatico** (delete da Drive).
- 📁 Verifica anche se la cartella Drive esiste già → chiede conferma prima di procedere.
- ❌ Tutte le esecuzioni ora falliscono con messaggi chiari se manca una variabile `.env`.

### 🛠️ Moduli aggiornati

- `pre_onboarding.py`: logging + rollback + validazione `cartelle_raw.yaml`
- `drive_utils.py`: funzione `delete_folder_by_id`, validazione env, fail-safe
- `github_push.py`: fallback su repo esistente, separazione in `github_utils.py`
- `onboarding_full.py`: check repo esistente anticipato

### 📄 Documentazione aggiornata

- `README.md`, `pre_onboarding_readme.md`, `onboarding_pipeline_timmy_kb_v1.3.md`
- Nuove sezioni: idempotenza, rollback, check GitHub, flussi fail-fast


## v1.1 – Pipeline dinamica e Google Drive ricorsivo (luglio 2025)

### 🚀 Principali novità

- 🏗 **Pipeline 100% parametrica**: tutti i path, ID, repo e configurazioni ora sono caricati dinamicamente da `.env` o dalla config del cliente. Nessun path hardcoded nei moduli.
- 💬 **Interfaccia CLI migliorata**: avvio della pipeline onboarding (`onboarding_full.py`) ora richiede solo lo slug cliente come input interattivo; il nome cliente viene recuperato dalla configurazione.
- ☁️ **Download PDF ricorsivo da Google Drive**: la pipeline scarica automaticamente **tutti i PDF** presenti nella cartella `raw` del cliente su Google Drive, **inclusi quelli in sottocartelle**, ricostruendo la struttura locale. Questo rende superflua la sincronizzazione locale del drive.
- 🔄 **Compatibilità totale con pipeline esistente**: nessuna modifica richiesta ai moduli ingest o di conversione, che lavorano già su struttura locale annidata.
- 📑 **README e documentazione aggiornati**:  
  - Pre-onboarding e onboarding ora includono note sulle variabili `.env` richieste e sulla portabilità.
  - Flussi documentati per riflettere le modifiche e l’uso delle temp dir e path dinamici.
- 🧹 **Pulizia e rollback migliorati**: gestione automatica dei file temporanei e cleanup a fine procedura.
- 🧪 **Logging uniforme**: tutte le operazioni e i messaggi ora sono gestiti tramite il modulo `logging` di Python, con livelli INFO/WARNING/ERROR.

---

### 📄 Altre modifiche

- 🛡 **Fail-fast**: la pipeline esce con messaggio chiaro se manca una variabile `.env` o un parametro fondamentale.
- 🌐 **Portabilità**: testata su Windows, Mac e Linux; zero dipendenze da path di sistema.
- 📦 **Refactor moduli chiave** (`config_loader.py`, `pre_onboarding.py`, `onboarding_full.py`): ora centralizzano la lettura di config/env e calcolano tutti i parametri da template.
- 📚 **Template `.env` ufficiale** aggiornato con tutte le voci richieste per entrambe le fasi.

---

### 📝 Aggiornamenti documentazione

- README ufficiale aggiornato per evidenziare:
    - Input CLI minimale (solo slug)
    - Download ricorsivo PDF
    - Pipeline cross-platform e AI-ready
    - Sicurezza (occhio a `.env` e `service_account.json`)
- Guide specifiche (`pre_onboarding_readme.md`, `onboarding_pipeline_timmy_kb_v1.2.md`) integrate con dettagli e tabella variabili `.env`.

---

**Upgrade consigliato a tutte le istanze, repository e cloni NeXT/Timmy.**


## v1.0 – Baseline iniziale (luglio 2025)

Questa versione rappresenta il primo consolidamento completo della pipeline di onboarding NeXT. È da considerarsi il **punto zero ufficiale** da cui partirà il versionamento semantico.

---

### 🚀 Principali novità

- ✅ **Integrazione completa** delle fasi **Pre-Onboarding** e **Onboarding**
- 📁 **Struttura unica e coerente** delle cartelle di progetto, moduli Python e file di configurazione
- 🔧 **Funzionalità consolidate**:
  - Generazione cartelle cliente su Google Drive da `cartelle_raw.yaml`
  - Creazione e validazione manuale del file `config.yaml`
  - Parsing semantico dei PDF (Markdown + JSON)
  - Generazione automatica di `README.md` e `SUMMARY.md`
  - Preview GitBook via Docker (`localhost:4000`)
  - Deploy GitHub automatico da template via CLI
  - Pulizia rollback (`temp_config/`) e cleanup completo

---

### 📄 Documentazione allegata

Due documenti nella root descrivono in dettaglio le due fasi operative:

- [`pre_onboarding_readme.md`](./pre_onboarding_readme.md): guida completa alla creazione iniziale della struttura cliente
- [`onboarding_readme.md`](./onboarding_readme.md): guida alla pipeline completa di parsing e pubblicazione

---

### 🧩 Tecnologie e dipendenze

- `Python >= 3.10`
- Librerie: `PyMuPDF`, `spacy`, `pydantic`, `pyyaml`, `python-slugify`, `google-api-python-client`, `docker`, `requests`
- Requisiti extra:
  - Docker installato per preview GitBook
  - GitHub CLI (`gh`) configurato
  - Chiave `service_account.json` per accesso Google Drive

---

### ⚠️ Nota importante

Questa versione **sostituisce completamente la versione precedente del repository online**. Eventuali file o struttura già presenti sono da considerarsi **obsoleti** e saranno sovrascritti con questa baseline v1.0.

---