# Architettura - Timmy-KB (v1.7.0)

Questa pagina descrive l'architettura aggiornata del sistema: componenti, flussi end-to-end, struttura del repository e le API interne su cui si fonda la pipeline. Per estendere o modificare il codice, fai sempre riferimento anche a [Developer Guide](developer_guide.md) e alle regole di codifica. L'obiettivo è mantenere coerenza, riuso e sicurezza I/O (path-safety + scritture atomiche).

> Doppio approccio: puoi lavorare da terminale (orchestratori in sequenza) oppure tramite interfaccia (Streamlit).  
> Avvio interfaccia: `streamlit run onboarding_ui.py` — vedi [Guida UI (Streamlit)](guida_ui.md).

---

## Panorama generale

- Doppio approccio operativo: orchestratori CLI oppure interfaccia Streamlit (`onboarding_ui.py`) per l'onboarding end-to-end.
- Obiettivo: trasformare PDF in una KB Markdown AI‑ready, arricchita semanticamente e pronta per anteprima (HonKit/Docker) e push GitHub.
- Scope RAW: i PDF risiedono localmente in `output/timmy-kb-<slug>/raw/`. Google Drive è usato in:
  - pre_onboarding per creare la struttura remota e caricare il `config.yaml` di base (preparazione cartelle su Drive per caricamento PDF da parte del cliente);
  - tag_onboarding per scaricare i PDF (default) nella sandbox locale (`raw/`).
- Separazione ruoli: orchestratori (UX/CLI, prompt, exit codes) vs moduli tecnici (logica pura, niente prompt/exit).
- Sicurezza & coerenza: `ensure_within` come SSoT per path-safety; scritture atomiche via `safe_write_*`; redazione log centralizzata.
- Orchestrazione semantica esposta via `semantic.api` (UI e script usano solo la façade pubblica). Il vecchio `semantic_onboarding.py` è deprecato.
- Testing: suite PyTest con utente dummy generato on-demand, test unitari/middle/smoke end-to-end.
- Performance: CSV via scrittura streaming + commit atomico; enrichment ottimizzato con un indice inverso per sinonimi/tag.

---

## Flusso end-to-end (pipeline)

### 1) `pre_onboarding` — setup locale + (opz.) struttura Drive
Input: `slug` (+ nome cliente in interattivo). Variabili opzionali: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`, `YAML_STRUCTURE_FILE`.
Azioni: crea la sandbox locale (`raw/`, `book/`, `semantic/`, `config/`, `logs/`), risolve lo YAML struttura, (se configurato) crea la struttura su Drive e carica `config.yaml`, aggiorna il config locale con gli ID remoti.
Output: `output/timmy-kb-<slug>/...` + `config.yaml` aggiornato (inclusi ID Drive).

### 2) `tag_onboarding` — tagging semantico (HiTL) con Drive di default
Input: PDF. Per default, la sorgente è Drive (scaricati nella sandbox `raw/`). In alternativa `--source local`.
Azioni: genera `semantic/tags_raw.csv` (euristiche path/filename, scrittura streaming), checkpoint HiTL che produce `README_TAGGING.md` e `tags_reviewed.yaml` (stub di revisione umana).
Output: `tags_raw.csv` + `tags_reviewed.yaml` (stub) per la revisione.

### 3) Semantica — conversione + enrichment + preview (facade `semantic.api`)
Input: `raw/` + (opz.) vocabolario canonico su SQLite (`semantic/tags.db`); lo YAML storico (`tags_reviewed.yaml`) è usato per authoring/migrazione.
Azioni: conversione PDF→Markdown in `book/`; arricchimento frontmatter (tags/aree) tramite vocabolario/sinonimi e indice inverso; generazione `README.md` e `SUMMARY.md` (util di repo o fallback adapter); preview HonKit Docker con stop esplicito.
Output: Markdown pronti in `book/`; anteprima su `localhost:<port>`.

### 4) `onboarding_full` — push GitHub
Input: `book/` pronto e coerente.
Azioni: preflight su `book/` (accetta solo `.md`, ignora `.md.fp`), push su GitHub via `github_utils`.
Output: commit/push su repo remoto.

> Nota sul vocabolario: `tags_reviewed.yaml` è il file di revisione umana (HiTL). Da esso si ottiene/aggiorna il vocabolario canonico su SQLite, consumato in runtime dagli orchestratori e dalla UI (che accede tramite `semantic.api`) per l'arricchimento dei frontmatter.

---

## Architettura dei componenti

- Orchestratori
  - `pre_onboarding.py`: setup locale; opz. Drive structure + upload `config.yaml`.
  - `tag_onboarding.py`: ingest PDF (default Drive→RAW), `tags_raw.csv`, checkpoint HiTL → `tags_reviewed.yaml`.
  - Facade `semantic.api`: PDF→MD, enrichment, README/SUMMARY, preview (via adapters), usata da UI/CLI.
  - `onboarding_full.py`: preflight `book/`, push GitHub.

- Adapter
  - `adapters/content_fallbacks.py`: generatori/validatori fallback per README/SUMMARY (idempotenti, atomici).
  - `adapters/preview.py`: start/stop contenitore HonKit.

- Pipeline core
  - `pipeline/path_utils.py`: SSoT path-safety (`ensure_within`, `is_safe_subpath`), `sanitize_filename`, `sorted_paths`, `validate_slug`.
  - `pipeline/file_utils.py`: scritture atomiche (`safe_write_text/bytes`).
  - `pipeline/content_utils.py`: util per README/SUMMARY (se disponibili).
  - `pipeline/constants.py`: nomi standard file/dir e costanti.

- Semantica
  - `semantic/vocab_loader.py`: loader vocabolario canonico da SQLite (`tags.db`).
  - `semantic/tags_io.py`: README_TAGGING e stub revisione da CSV (persistenza su DB).
  - `semantic/api.py`: facade pubblica per la UI.

- Storage (SQLite)
  - `storage/tags_store.py`: schema v1/v2, CRUD, migrazioni e helpers (`ensure_schema_v2`, `migrate_to_v2`, ecc.).

Output (per cliente):
```
output/
  timmy-kb-<slug>/
    raw/
    book/
    semantic/
    config/
    logs/
```

---

## Integrazione Test (principi)

- Utente dummy: generato da `py src/tools/gen_dummy_kb.py --slug dummy` per popolare `raw/` con PDF di esempio e asset necessari al flusso.
- Piramide test: unit (validatori/CSV/guard), middle (contratti CLI), smoke E2E (dummy) per rilevare regressioni di flusso.
- Isolamento esterni: i test non richiedono credenziali reali; componenti Drive/Git sono mockati o bypassati dove sensato.
- Compatibilità OS: suite compatibile Windows/Linux; attenzione a path POSIX nei CSV.

---

## Variabili d'ambiente (rilevanti)

- Drive: `SERVICE_ACCOUNT_FILE`, `DRIVE_ID`
- GitHub: `GITHUB_TOKEN`, `GIT_DEFAULT_BRANCH`
- Build & Log: `LOG_REDACTION`, `ENV`, `CI`
- Struttura: `YAML_STRUCTURE_FILE` (override per lo YAML cartelle)

---

## Gestione errori ed exit codes

- Eccezioni: `ConfigError`, `PipelineError`, `PushError`, `PreviewError`.
- Codici: `0` OK; `2` ConfigError; `30` PreviewError; `40` PushError (vedi `EXIT_CODES`).

---

## Invarianti architetturali

- RAW locale come sorgente runtime: tutto ciò che converte/arricchisce lavora su `output/timmy-kb-<slug>/raw` e `book` locali.
- Idempotenza: ripetere gli step non crea duplicazioni né corrompe i file; write atomiche sempre.
- Path-safety: ogni write/copy/delete passa da `ensure_within`.
- Redazione log: masking automatico per segreti/ID; tracciamento con `run_id`.
- Coerenza API: funzioni orchestratrici e di servizio con firme consistenti.
- Portabilità: Windows/Linux supportati (encoding e path gestiti).

---

## Versioning

Questa pagina documenta la release 1.7.0. Cambi chiave rispetto alla 1.6.0:
- Interfaccia Streamlit per l'onboarding (alternativa agli orchestratori CLI), con gating iniziale slug/nome cliente e sblocco progressivo delle tab (Drive → Semantica).  
- Sezione “Download contenuti su raw/” nel tab Drive (pull PDF da Drive → locale).  
- Rifiniture di compatibilità Pylance/Streamlit e hardening path/atomiche.
