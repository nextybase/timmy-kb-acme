# 📦 CHANGELOG – OnBoarding NeXT

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