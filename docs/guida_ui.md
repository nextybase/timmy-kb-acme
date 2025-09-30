# Onboarding UI — Guida aggiornata (v1.9.6)

Questa guida descrive come usare e come funziona l'interfaccia `onboarding_ui.py`, il suo inserimento nella pipeline, le dipendenze e i casi d'errore più comuni.

> In sintesi: la UI è una app Streamlit con tre step operativi: Configurazione, Drive, Semantica, e un opzionale Preview Docker (HonKit). Tutte le funzioni delegano a utility stabili della pipeline; i fallback interni sono stati rimossi, salvo messaggi di avviso idempotenti quando un modulo non è disponibile.

---

## 1) Prerequisiti
- Python >= 3.11 e Streamlit installato
- Repository clonato e avviato dalla root
- Per la tab "Drive": credenziali Google Drive (`SERVICE_ACCOUNT_FILE`) e ID dell'unità (`DRIVE_ID`)
- Per la Preview: Docker installato e in esecuzione, porta TCP libera (configurabile in UI)
- Logging/Redazione (opzionale ma consigliato): variabili `LOG_REDACTION` / `LOG_REDACTED` o `ENV=prod`

---

## 2) Avvio
```bash
# macOS/Linux
streamlit run onboarding_ui.py

# Windows
py -m streamlit run onboarding_ui.py
```
Alla prima apertura, la landing chiede `slug` e `nome cliente`. Quando entrambi sono valorizzati, la UI si sblocca e salva lo stato in sessione. Il pulsante "Esci" termina il processo Streamlit in modo pulito.

---

## 3) Struttura logica e stato
- Lock cliente: blocca `slug`/`nome` dopo l'inserimento
- Stato Drive: avanza provisioning e download
- Gate Semantica: la tab Semantica appare solo dopo il download dei PDF in `raw/`
- Preview: nome container, porta e stato (running/stopped)

La redazione log preferisce la logica di pipeline (`compute_redact_flag`); in assenza, abilita la redazione se `ENV=prod` o variabili esplicite.

---

## 3bis) Landing Vision onboarding
- **Step 1 - upload**: con slug nuovo la landing mostra l'uploader dedicato a `VisionStatement.pdf`; il file viene salvato in `config/` con guardie `ensure_within_and_resolve`.
- **Step 2 - Genera da Vision (AI)**: il pulsante esplicito avvia la pipeline (`semantic.vision_provision.provision_from_vision`) e genera direttamente due YAML: `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml`.
- **Step 3 - Anteprima**: al termine vengono mostrati in expander gli YAML per revisione rapida.
- **Step 4 - Approva**: il bottone **"Approva e crea cartelle"** crea la gerarchia `docs/` leggendo `semantic/cartelle_raw.yaml`; nessuna cartella viene generata prima di questa approvazione.
- **Idempotenza**: se l'hash del PDF non cambia, la UI avvisa che gli artefatti sono già presenti e propone un toggle per rigenerare forzatamente (utile anche per cambiare modello).
> Screenshot (TODO): acquisire la landing Vision aggiornata e salvarla come `docs/assets/vision_onboarding.png` per documentazione e training.

**Pulsanti e stati rapidi**
- `Genera da Vision (AI)`: si abilita dopo l'upload del PDF e resta in stato di avanzamento finche' la generazione non termina.
- `Approva e crea cartelle`: compare dopo la generazione e rimane disabilitato finche' gli YAML non passano la validazione di schema.


> Nota: mantieni il flusso idempotente; se cambi modello attiva il toggle di rigenerazione, attendi il completamento degli step di avanzamento e poi ripeti l'approvazione.

## 4) Tab "Configurazione"
- Definisce/raffina il mapping semantico del cliente (categorie, descrizioni, alias/tag)
- Carica mapping rivisto se esiste, altrimenti un default
- Editor per una categoria alla volta (supporto HiTL)
- Validazione (duplicati, campi obbligatori, coerenza)
- Opzione di normalizzazione chiavi (kebab‑case)

Percorsi: mapping SSoT in `semantic/semantic_mapping.yaml` (workspace cliente).

---

## 5) Tab "Drive"
- Provisioning: genera struttura cartelle su Drive, incluse `raw/`
- Genera README per raw/: PDF (o TXT) di istruzioni upload
- Download contenuti: scarica file da Drive in `raw/`; aggiorna stato `raw_downloaded=True`
- Pulsante extra: "Rileva PDF in raw/" aggiorna lo stato senza download
- Vision: upload in landing; la generazione dei due YAML avviene dalla landing

Funzioni (`ui.services.drive_runner`):
- `build_drive_from_mapping(slug, client_name, progress_cb)`
- `emit_readmes_for_raw(slug, ensure_structure=True)`
- `download_raw_from_drive_with_progress(slug)` o `download_raw_from_drive(slug)`

Requisiti ENV: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`

---

## 6) Tab "Semantica"
> Nota: `semantic/cartelle_raw.yaml` viene generato insieme a `semantic/semantic_mapping.yaml`; la creazione delle cartelle `docs/` rimane esplicita via pulsante nella landing.
- Conversione RAW > BOOK (PDF > Markdown)
- Arricchimento frontmatter: aggiunge tag canonici dal DB SQLite (`storage/tags_store`)
- Generazione e validazione di `README.md` e `SUMMARY.md`
- Preview Docker (opzionale): container `gitbook-<slug>`, porta configurabile, start/stop dalla UI

Funzioni (`semantic.api`):
- `convert_markdown(context, logger, *, slug)`
- `enrich_frontmatter(context, logger, vocab, *, slug)`
- `write_summary_and_readme(context, logger, *, slug)`
- `get_paths(slug)` / `load_reviewed_vocab(base_dir, logger)` (usa DB SQLite come SSoT)

Funzioni (`adapters.preview`):
- `start_preview(context, logger, *, port, container_name)`
- `stop_preview(logger, *, container_name)`

Output locale: `output/timmy-kb-<slug>/raw/`, `book/`, `README.md`, `SUMMARY.md`

---

## 7) Workspace cliente
```
output/
  timmy-kb-<slug>/
    raw/        # PDF scaricati
    book/       # Markdown generati
    semantic/
      semantic_mapping.yaml  # SSoT mapping
      tags.db                # SSoT runtime (SQLite)
    README.md
    SUMMARY.md
```
Il bootstrap crea sia cartelle_raw.yaml sia semantic_mapping.yaml; la UI legge semantic_mapping.yaml, runtime SSoT = SQLite (tags.db).
SSoT dei tag reviewed = DB SQLite.

---

## 8) Logging & redazione
- Usa logger strutturato pipeline; fallback a `logging.basicConfig`
- Redazione calcolata da pipeline o, in assenza, da ENV/variabili

---

## 9) Errori comuni & soluzioni
- Docker non attivo/porta occupata: avvia Docker Desktop, scegli porta libera
- Credenziali Drive mancanti: verifica variabili e riesegui tab Drive
- RAW vuota o conversione fallita: controlla PDF e log
- Validazione mapping: correggi duplicati o normalizza chiavi
- Container bloccato: usa "Stop Preview" o elimina manualmente

---

## 10) Best practice
- Vision onboarding: sfrutta il toggle di rigenerazione solo quando devi aggiornare il modello o hai cambiato il PDF; in caso contrario l'hash evita compute inutile.
- Procedere in ordine: Configurazione → Drive → Semantica → Preview
- Mantieni mapping coerente con i materiali effettivi
- Usa normalizzazione chiavi per consistenza
- Evita spazi/caratteri speciali nei file sorgenti
- Avvia Docker solo quando serve la preview

---

## 11) API surface
- ui.components.mapping_editor: `load_default_mapping`, `load_semantic_mapping`, `split_mapping`, `validate_categories`, `build_mapping`, `save_semantic_mapping`
- ui.services.drive_runner: `build_drive_from_mapping`, `emit_readmes_for_raw`, `download_raw_from_drive_with_progress`, `download_raw_from_drive`
- semantic.api: `get_paths`, `load_reviewed_vocab`, `convert_markdown`, `enrich_frontmatter`, `write_summary_and_readme`
- adapters.preview: `start_preview`, `stop_preview`

---

## 12) FAQ
- Posso usare Semantica senza Drive? Sì, se i PDF sono già in `raw/`
- Come fermo la UI? Pulsante "Esci" o interrompendo Streamlit
- Dove trovo i file generati? In `output/timmy-kb-<slug>/book/` + radice workspace

---

## 13) Novità e Deprecazioni
- API semantica pubblica: la UI importa solo da `semantic.api`. Disponibile anche un wrapper CLI (`src/semantic_onboarding.py`) che orchestri `convert_markdown` → `enrich_frontmatter` → `write_summary_and_readme` per simmetria con gli altri orchestratori.
- Mapping YAML: SSoT = `semantic/semantic_mapping.yaml`. I percorsi legacy non sono più utilizzati dalla UI.

---

## 14) CLI vs UI (in breve)
- Entry point: `pre_onboarding.py`, `tag_onboarding.py`, `onboarding_full.py` vs `onboarding_ui.py`
- Destinatari: DevOps/CI/power user vs utenti operativi/facilitatori
- Config: YAML + ENV vs editor interattivo mapping + Drive provisioning
- Preview: script adapters vs bottoni UI
- Requisiti extra: Token GitHub (push) vs Docker attivo e credenziali Drive




# Onboarding UI — Guida aggiornata (v1.9.6)

Questa guida descrive come usare e come funziona l'interfaccia `onboarding_ui.py`, il suo inserimento nella pipeline, le dipendenze e i casi d'errore più comuni.

> In sintesi: la UI è una app Streamlit con tre step operativi: Configurazione, Drive, Semantica, e un opzionale Preview Docker (HonKit). Tutte le funzioni delegano a utility stabili della pipeline; i fallback interni sono stati rimossi, salvo messaggi di avviso idempotenti quando un modulo non è disponibile.

---

## 1) Prerequisiti
- Python >= 3.11 e Streamlit installato
- Repository clonato e avviato dalla root
- Per la tab "Drive": credenziali Google Drive (`SERVICE_ACCOUNT_FILE`) e ID dell'unità (`DRIVE_ID`)
- Per la Preview: Docker installato e in esecuzione, porta TCP libera (configurabile in UI)
- Logging/Redazione (opzionale ma consigliato): variabili `LOG_REDACTION` / `LOG_REDACTED` o `ENV=prod`

---

## 2) Avvio
```bash
# macOS/Linux
streamlit run onboarding_ui.py

# Windows
py -m streamlit run onboarding_ui.py
```
Alla prima apertura, la landing chiede `slug` e `nome cliente`. Quando entrambi sono valorizzati, la UI si sblocca e salva lo stato in sessione. Il pulsante "Esci" termina il processo Streamlit in modo pulito.

---

## 3) Struttura logica e stato
- Lock cliente: blocca `slug`/`nome` dopo l'inserimento
- Stato Drive: avanza provisioning e download
- Gate Semantica: la tab Semantica appare solo dopo il download dei PDF in `raw/`
- Preview: nome container, porta e stato (running/stopped)

La redazione log preferisce la logica di pipeline (`compute_redact_flag`); in assenza, abilita la redazione se `ENV=prod` o variabili esplicite.

---

## 3bis) Landing Vision onboarding
- Step 1 - upload: con slug nuovo la landing mostra l'uploader dedicato a `VisionStatement.pdf`; il file viene salvato in `config/` con guardie `ensure_within_and_resolve`.
- Step 2 - Genera da Vision (AI): il pulsante esplicito avvia la pipeline (`semantic.vision_provision.provision_from_vision`) e genera direttamente due YAML: `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml`.
- Step 3 - Anteprima: al termine vengono mostrati in expander gli YAML per revisione rapida.
- Step 4 - Approva: il bottone "Approva e crea cartelle" crea la gerarchia `docs/` leggendo `semantic/cartelle_raw.yaml`; nessuna cartella viene generata prima di questa approvazione.
- Idempotenza: se l'hash del PDF non cambia, la UI avvisa che gli artefatti sono già presenti e propone un toggle per rigenerare forzatamente (utile anche per cambiare modello).
> Screenshot (TODO): acquisire la landing Vision aggiornata e salvarla come `docs/assets/vision_onboarding.png` per documentazione e training.

Pulsanti e stati rapidi
- "Genera da Vision (AI)": si abilita dopo l'upload del PDF e resta in stato di avanzamento finché la generazione non termina.
- "Approva e crea cartelle": compare dopo la generazione e rimane disabilitato finché gli YAML non passano la validazione di schema.

> Nota: mantieni il flusso idempotente; se cambi modello attiva il toggle di rigenerazione, attendi il completamento degli step di avanzamento e poi ripeti l'approvazione.

## 4) Tab "Configurazione"
- Definisce/raffina il mapping semantico del cliente (categorie, descrizioni, alias/tag)
- Carica mapping rivisto se esiste, altrimenti un default
- Editor per una categoria alla volta (supporto HiTL)
- Validazione (duplicati, campi obbligatori, coerenza)
- Opzione di normalizzazione chiavi (kebab‑case)

Percorsi: mapping SSoT in `semantic/semantic_mapping.yaml` (workspace cliente).

---

## 5) Tab "Drive"
- Provisioning: genera struttura cartelle su Drive, incluse `raw/`
- Genera README per raw/: PDF (o TXT) di istruzioni upload
- Download contenuti: scarica file da Drive in `raw/`; aggiorna stato `raw_downloaded=True`
- Pulsante extra: "Rileva PDF in raw/" aggiorna lo stato senza download
- Vision: upload in landing; la generazione dei due YAML avviene dalla landing

Funzioni (`ui.services.drive_runner`):
- `build_drive_from_mapping(slug, client_name, progress_cb)`
- `emit_readmes_for_raw(slug, ensure_structure=True)`
- `download_raw_from_drive_with_progress(slug)` o `download_raw_from_drive(slug)`

Requisiti ENV: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`

---

## 6) Tab "Semantica"
> Nota: `semantic/cartelle_raw.yaml` viene generato insieme a `semantic/semantic_mapping.yaml`; la creazione delle cartelle `docs/` rimane esplicita via pulsante nella landing.
- Conversione RAW → BOOK (PDF → Markdown)
- Arricchimento frontmatter: aggiunge tag canonici dal DB SQLite (`storage/tags_store`)
- Generazione e validazione di `README.md` e `SUMMARY.md`
- Preview Docker (opzionale): container `gitbook-<slug>`, porta configurabile, start/stop dalla UI

Funzioni (`semantic.api`):
- `convert_markdown(context, logger, *, slug)`
- `enrich_frontmatter(context, logger, vocab, *, slug)`
- `write_summary_and_readme(context, logger, *, slug)`
- `get_paths(slug)` / `load_reviewed_vocab(base_dir, logger)` (usa DB SQLite come SSoT)

Funzioni (`adapters.preview`):
- `start_preview(context, logger, *, port, container_name)`
- `stop_preview(logger, *, container_name)`

Output locale: `output/timmy-kb-<slug>/raw/`, `book/`, `README.md`, `SUMMARY.md`

---

## 7) Workspace cliente
```
output/
  timmy-kb-<slug>/
    raw/        # PDF scaricati
    book/       # Markdown generati
    semantic/
      semantic_mapping.yaml  # SSoT mapping
      tags.db                # SSoT runtime (SQLite)
    README.md
    SUMMARY.md
```
Il bootstrap crea sia tags_reviewed.yaml sia semantic_mapping.yaml; la UI legge semantic_mapping.yaml, runtime SSoT = SQLite (tags.db).
SSoT dei tag reviewed = DB SQLite. YAML solo per bootstrap, SSoT runtime = SQLite.

---

## 8) Logging & redazione
- Usa logger strutturato pipeline; fallback a `logging.basicConfig`
- Redazione calcolata da pipeline o, in assenza, da ENV/variabili

---

## 9) Errori comuni & soluzioni
- Docker non attivo/porta occupata: avvia Docker Desktop, scegli porta libera
- Credenziali Drive mancanti: verifica variabili e riesegui tab Drive
- RAW vuota o conversione fallita: controlla PDF e log
- Validazione mapping: correggi duplicati o normalizza chiavi
- Container bloccato: usa "Stop Preview" o elimina manualmente

---

## 10) Best practice
- Vision onboarding: sfrutta il toggle di rigenerazione solo quando devi aggiornare il modello o hai cambiato il PDF; in caso contrario l'hash evita compute inutile.
- Procedere in ordine: Configurazione → Drive → Semantica → Preview
- Mantieni mapping coerente con i materiali effettivi
- Usa normalizzazione chiavi per consistenza
- Evita spazi/caratteri speciali nei file sorgenti
- Avvia Docker solo quando serve la preview

---

## 11) API surface
- ui.components.mapping_editor: `load_default_mapping`, `load_semantic_mapping`, `split_mapping`, `validate_categories`, `build_mapping`, `save_semantic_mapping`
- ui.services.drive_runner: `build_drive_from_mapping`, `emit_readmes_for_raw`, `download_raw_from_drive_with_progress`, `download_raw_from_drive`
- semantic.api: `get_paths`, `load_reviewed_vocab`, `convert_markdown`, `enrich_frontmatter`, `write_summary_and_readme`
- adapters.preview: `start_preview`, `stop_preview`

---

## 12) FAQ
- Posso usare Semantica senza Drive? Sì, se i PDF sono già in `raw/`
- Come fermo la UI? Pulsante "Esci" o interrompendo Streamlit
- Dove trovo i file generati? In `output/timmy-kb-<slug>/book/` + radice workspace

---

## 13) CLI vs UI (in breve)
- Entry point: `pre_onboarding.py`, `tag_onboarding.py`, `onboarding_full.py` vs `onboarding_ui.py`
- Destinatari: DevOps/CI/power user vs utenti operativi/facilitatori
- Config: YAML + ENV vs editor interattivo mapping + Drive provisioning
- Preview: script adapters vs bottoni UI
- Requisiti extra: Token GitHub (push) vs Docker attivo e credenziali Drive
