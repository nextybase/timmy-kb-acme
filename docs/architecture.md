# Architettura  —  Timmy‑KB (v1.6.1)

Questa pagina descrive l'architettura **aggiornata** del sistema: componenti, flussi end‑to‑end, struttura del repository e le API interne su cui si fonda la pipeline. Per estendere o modificare il codice, fai sempre riferimento anche a [Developer Guide](developer_guide.md) e alle regole di codifica. L'obiettivo è mantenere coerenza, riuso e sicurezza I/O (path‑safety + scritture atomiche).

> **Doppio approccio:** puoi lavorare da **terminale** (orchestratori in sequenza) **oppure** tramite **interfaccia (Streamlit)**.  
> Avvio interfaccia: `streamlit run onboarding_ui.py`  —  vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Panorama generale

- **Doppio approccio operativo**: orchestratori CLI *oppure* Interfaccia Streamlit (`onboarding_ui.py`) per l'onboarding end‑to‑end.
- **Obiettivo**: trasformare PDF in una **KB Markdown AI‑ready**, arricchita semanticamente e pronta per anteprima (HonKit/Docker) e push GitHub.
- **Scope RAW**: i PDF risiedono localmente in `output/timmy-kb-<slug>/raw/`. **Google Drive** è usato in:
  - **pre_onboarding** per creare la struttura remota e caricare il `config.yaml` di base. La struttura di cartelle su Drive è predisposta per consentire il caricamento dei pdf da parte del cliente;
  - Un altro accesso a Google Drive è effettuata da **tag_onboarding** per **scaricare i PDF (default)** nella sandbox locale (`raw/`).
- **Separazione ruoli**: orchestratori (UX/CLI, prompt, exit codes) vs moduli tecnici (logica pura, niente prompt/exit).
- **Sicurezza & coerenza**: `ensure_within` come **SSoT** per path‑safety; scritture atomiche via `safe_write_*`; redazione log centralizzata.
- **Split orchestratori**: conversione/enrichment/preview in `semantic_onboarding.py` (API pubblica per la UI esposta via `semantic.api`); push in `onboarding_full.py`.
- **Testing**: suite PyTest con **utente dummy** generato on‑demand, test unitari/middle/smoke end‑to‑end.
- **Performance**: CSV via scrittura streaming + commit atomico; enrichment ottimizzato con un **indice inverso** per sinonimi/tag.

---

## Flusso end‑to‑end (pipeline)

### 1) `pre_onboarding` → setup locale + (opz.) struttura Drive
**Input:** `slug` (+ nome cliente in interattivo). Variabili opzionali: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `YAML_STRUCTURE_FILE`.
**Azioni:** crea la sandbox locale (`raw/`, `book/`, `semantic/`, `config/`, `logs/`), risolve lo YAML struttura, (se configurato) crea la struttura su Drive e carica `config.yaml`, aggiorna il config locale con gli ID remoti.
**Output:** `output/timmy-kb-<slug>/…` + `config.yaml` aggiornato (inclusi ID Drive).

### 2) `tag_onboarding` → tagging semantico (HiTL) **con Drive di default**
**Input:** PDF. Per default, la sorgente è **Drive** (scaricati nella sandbox `raw/`). In alternativa `--source local`.
**Azioni:** genera `semantic/tags_raw.csv` (euristiche path/filename, scrittura streaming), checkpoint HiTL che produce `README_TAGGING.md` e `tags_reviewed.yaml` (stub di revisione umana).
**Output:** `tags_raw.csv` + `tags_reviewed.yaml` (stub) per la revisione.

### 3) `semantic_onboarding` → conversione + enrichment + preview (UI via `semantic.api`)
**Input:** `raw/` + (opz.) **vocabolario canonico** su SQLite (`semantic/tags.db`); lo YAML storico (`tags_reviewed.yaml`) è usato per authoring/migrazione.
**Azioni:** conversione PDF→Markdown in `book/`; arricchimento frontmatter (tags/areas) tramite vocabolario/sinonimi e **indice inverso**; generazione `README.md` e `SUMMARY.md` (utilità repo → fallback adapter); preview HonKit Docker con stop esplicito.
**Output:** Markdown pronti in `book/`; anteprima su `localhost:<port>`.

### 4) `onboarding_full` → push GitHub
**Input:** `book/` pronto e coerente.
**Azioni:** preflight su `book/` (accetta solo `.md`, ignora `.md.fp`), push su GitHub via `github_utils`.
**Output:** commit/push su repo remoto.

> **Nota sul vocabolario:** `tags_reviewed.yaml` è il file di **revisione umana** (HiTL). Da esso si ottiene/aggiorna il vocabolario **canonico** su SQLite, consumato in runtime dagli orchestratori e dalla UI (che accede tramite `semantic.api`) per l'arricchimento dei frontmatter.

---

## Architettura dei componenti

- **Orchestratori**
  - `pre_onboarding.py`: setup locale; opz. Drive structure + upload `config.yaml`.
  - `tag_onboarding.py`: ingest PDF (default Drive → RAW), `tags_raw.csv`, checkpoint HiTL → `tags_reviewed.yaml`.
  - `semantic_onboarding.py`: PDF→MD, enrichment, README/SUMMARY, preview Docker (UI integra tramite `semantic.api`).
  - `onboarding_full.py`: preflight `book/`, push GitHub.

- **Adapter**
  - `adapters/content_fallbacks.py`: generatori/validatori fallback per README/SUMMARY (idempotenti, atomici).
  - `adapters/preview.py`: start/stop contenitore HonKit.

- **Pipeline core**
  - `pipeline/path_utils.py`: **SSoT** path‑safety (`ensure_within`, `is_safe_subpath`), `sanitize_filename`, `sorted_paths`, `validate_slug`.
  - `pipeline/file_utils.py`: scritture atomiche (`safe_write_text/bytes`).
  - `pipeline/logging_utils.py`: logger strutturato + redazione.
  - `pipeline/exceptions.py`: eccezioni tipizzate + `EXIT_CODES`.
  - `pipeline/context.py`: `ClientContext` + caricamento settings/env.
  - `pipeline/config_utils.py`: lettura/scrittura/aggiornamento `config.yaml` (inclusi ID Drive).
  - `pipeline/content_utils.py`: utilità per conversione/validazione Markdown.
  - `pipeline/github_utils.py`: push su GitHub.
  - `pipeline/drive_utils.py`: API alto livello per Drive (client, download/upload, struttura da YAML).

- **Semantica**
  - `semantic/tags_io.py`: generazione README tagging e stub `tags_reviewed.yaml` da `tags_raw.csv`.
  - `semantic/tags_validator.py`: validazione struttura logica di `tags_reviewed.yaml`.
  - Altri moduli: estrazione/normalizzazione/mapping, pronti per evoluzioni future.

---

## Struttura del repository (aggiornata)

```
repo/
├─ README.md
├─ pytest.ini                         # config PyTest (pythonpath, testpaths, markers, coverage)
├─ tests/                             # **AREA TEST**
│  ├─ test_contract_defaults.py       # default CLI (es. tag_onboarding=drive)
│  ├─ test_smoke_dummy_e2e.py         # smoke end-to-end con utente dummy
│  ├─ test_unit_book_guard.py         # guard/contratto su book/ (solo .md, .md.fp ignorati)
│  ├─ test_unit_emit_tags_csv.py      # formato/header POSIX per tags_raw.csv
│  └─ test_unit_tags_validator.py     # validatore tags_reviewed.yaml (ok/errori/duplicati)
├─ config/
│  ├─ cartelle_raw.yaml               # struttura cartelle RAW (pre_onboarding)
│  ├─ pdf_dummy.yaml                  # fixture per tools/gen_dummy_kb.py
│  └─ ...
├─ docs/
│  ├─ index.md
│  ├─ user_guide.md
│  ├─ developer_guide.md
│  ├─ architecture.md                 # **questa pagina**
│  ├─ coding_rules.md
│  ├─ policy_push.md
│  └─ versioning_policy.md
├─ src/
│  ├─ pre_onboarding.py
│  ├─ tag_onboarding.py
│  ├─ semantic_onboarding.py
│  ├─ onboarding_full.py
│  ├─ tools/
│  │  └─ gen_dummy_kb.py              # generatore KB di test (dummy)
│  ├─ adapters/
│  │  ├─ content_fallbacks.py
│  │  └─ preview.py
│  ├─ semantic/
│  │  ├─ tags_io.py
│  │  ├─ tags_validator.py
│  │  └─ ...                          # altri moduli semantici
│  └─ pipeline/
│     ├─ constants.py
│     ├─ context.py
│     ├─ exceptions.py
│     ├─ env_utils.py
│     ├─ logging_utils.py
│     ├─ path_utils.py
│     ├─ file_utils.py
│     ├─ config_utils.py
│     ├─ content_utils.py
│     ├─ github_utils.py
│     └─ drive_utils.py
└─ output/                            # (GENERATO) timmy-kb-<slug>/{raw,book,semantic,config,logs}
```

---

## Integrazione Test (principi)

- **Utente dummy**: generato da `py src/tools/gen_dummy_kb.py --slug dummy` per popolare `raw/` con PDF di esempio e asset necessari al flusso.
- **Piramide test**: unit (validatori/CSV/guard), middle (contratti CLI), smoke E2E (dummy) per rilevare regressioni di flusso.
- **Isolamento esterni**: i test non richiedono credenziali reali; componenti Drive/Git sono mockati o bypassati dove sensato.
- **Compatibilità OS**: suite compatibile Windows/Linux; attenzione a path POSIX nei CSV.

---

## Variabili d'ambiente (rilevanti)

- **Drive**: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`
- **GitHub**: `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`
- **Build & Log**: `LOG_REDACTION`, `ENV`, `CI`
- **Struttura**: `YAML_STRUCTURE_FILE` (override per lo YAML cartelle)

---

## Gestione errori ed exit codes

- **Eccezioni**: `ConfigError`, `PipelineError`, `PushError`, `PreviewError`.
- **Codici**: `0` OK; `2` ConfigError; `30` PreviewError; `40` PushError (vedi `EXIT_CODES`).

---

## Invarianti architetturali

- **RAW locale come sorgente runtime**: tutto ciò che converte/arricchisce lavora su `output/timmy-kb-<slug>/raw` e `book` locali.
- **Idempotenza**: ripetere gli step non crea duplicazioni né corrompe i file; write atomiche sempre.
- **Path‑safety**: ogni write/copy/delete passa da `ensure_within`.
- **Redazione log**: masking automatico per segreti/ID; tracciamento con `run_id`.
- **Coerenza API**: funzioni orchestratrici e di servizio con firme consistenti.
- **Portabilità**: Windows/Linux supportati (encoding e path gestiti).

---

## Versioning

Questa pagina documenta la **release 1.6.1**. Cambi chiave rispetto alla 1.6.0:
- **Interfaccia Streamlit** per l'onboarding (alternativa agli orchestratori CLI), con gating iniziale *slug/nome cliente* e sblocco progressivo delle tab (Drive → Semantica).  
- Sezione **Download contenuti su raw/** nel tab *Drive* (pull PDF da Drive → locale).  
- Rifiniture di compatibilità Pylance/Streamlit e hardening path/atomiche.
