# Architettura — Timmy‑KB (v1.5.0)

Questa pagina descrive l’architettura **aggiornata** del sistema: componenti, flussi end‑to‑end, struttura del repository e le API interne su cui si fonda la pipeline. Per estendere o modificare il codice, fai sempre riferimento anche a [Developer Guide](developer_guide.md) e alle regole di codifica. L’obiettivo è mantenere coerenza, riuso e sicurezza I/O (path‑safety + scritture atomiche).

---

## Panorama generale

- **Obiettivo**: trasformare PDF in una **KB Markdown AI‑ready**, arricchita semanticamente e pronta per anteprima (HonKit/Docker) e push GitHub.
- **Scope RAW**: i PDF risiedono localmente in `output/timmy-kb-<slug>/raw/`. **Google Drive** è usato in:
  - **pre_onboarding** per creare la struttura remota e caricare `config.yaml`;
  - **tag_onboarding** per **scaricare i PDF (default)** nella sandbox locale (`raw/`).
- **Separazione ruoli**: orchestratori (UX/CLI, prompt, exit codes) vs moduli tecnici (logica pura, niente prompt/exit).
- **Sicurezza & coerenza**: `ensure_within` come **SSoT** per path‑safety; scritture atomiche via `safe_write_*`; redazione log centralizzata.
- **Split orchestratori**: conversione/enrichment/preview in `semantic_onboarding.py`; push in `onboarding_full.py`.
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

### 3) `semantic_onboarding` → conversione + enrichment + preview
**Input:** `raw/` + (opz.) **vocabolario canonico** `semantic/tags.yaml` (derivato dalla revisione).
**Azioni:** conversione PDF→Markdown in `book/`; arricchimento frontmatter (tags/areas) tramite vocabolario/sinonimi e **indice inverso**; generazione `README.md` e `SUMMARY.md` (utilità repo → fallback adapter); preview HonKit Docker con stop esplicito.
**Output:** Markdown pronti in `book/`; anteprima su `localhost:<port>`.

### 4) `onboarding_full` → push GitHub
**Input:** `book/` pronto e coerente.
**Azioni:** preflight su `book/` (accetta solo `.md`, ignora `.md.fp`), push su GitHub via `github_utils`.
**Output:** commit/push su repo remoto.

> **Nota sul vocabolario:** `tags_reviewed.yaml` è il file di **revisione umana** (HiTL). Da esso si ottiene/aggiorna il vocabolario **canonico** `tags.yaml`, che è quello consumato in runtime da `semantic_onboarding` per l’arricchimento dei frontmatter.

---

## Architettura dei componenti

- **Orchestratori**
  - `pre_onboarding.py`: setup locale; opz. Drive structure + upload `config.yaml`.
  - `tag_onboarding.py`: ingest PDF (default Drive → RAW), `tags_raw.csv`, checkpoint HiTL → `tags_reviewed.yaml`.
  - `semantic_onboarding.py`: PDF→MD, enrichment, README/SUMMARY, preview Docker.
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
├─ tests/                             # **NUOVA AREA TEST**
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

## Variabili d’ambiente (rilevanti)

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

Questa pagina documenta la **release 1.5.0**. Cambi chiave rispetto alla 1.4.0:
- `tag_onboarding` usa **Drive come default** per il download dei PDF (opzione `--source local` disponibile).
- Introdotta e documentata l’**area `tests/`** con suite PyTest e utente dummy.
- Allineata la catena semantica: `tags_reviewed.yaml` (revisione HiTL) → `tags.yaml` (vocabolario canonico consumato in runtime).
- Rafforzate le regole di preflight su `book/` in `onboarding_full` (accetta solo `.md`, ignora `.md.fp`).

