# Changelog - Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

> **Nota metodologica:** ogni nuova sezione deve descrivere chiaramente il contesto delle modifiche (Added, Changed, Fixed, Security, ecc.), specificando file e funzioni interessate. Gli aggiornamenti devono essere allineati con la documentazione (`docs/`) e riflessi in README/User Guide/Developer Guide quando impattano la UX o le API pubbliche. Le versioni MINOR/MAJOR vanno accompagnate da note di migrazione.

---

## 2025-09-17 — Smoke tests UI & E2E

### Added
- `scripts/smoke_streamlit_finance.py`: smoke headless della tab **Finanza** (Streamlit + Playwright). Pre-crea il workspace sotto `REPO_ROOT_DIR`, carica un CSV di esempio e verifica la generazione di `semantic/finance.db`. Selettori robusti (sidebar, radio “Finanza”, upload nel container del bottone target) e screenshot diagnostici in caso di failure.
- `scripts/smoke_e2e.py`: smoke **end-to-end** (pre_onboarding ➜ import finanza ➜ orchestratore). Isola `REPO_ROOT_DIR` in temp, importa un CSV in `finance.db`, esegue `onboarding_full_main` con **push GitHub disabilitato** via env (`TIMMY_NO_GITHUB=1`, `SKIP_GITHUB_PUSH=1`) e valida output (log opzionale).

### Changed
- UI Finanza: bottone “Importa in finance.db” sempre abilitato, con **gating nell’handler** se il file è assente → niente race tra upload e rerun Streamlit durante i test.

---

## [fix] — 2025-09-17

### Security
- **Path-safety in lettura**: `src/semantic/vocab_loader.py` ora usa `ensure_within_and_resolve(...)` e opera sul path *risolto*. Questo impedisce traversal via `..`/symlink e allinea il modulo alle coding rules. Nessuna modifica all’API pubblica.

### Refactor & Reliability
- **SSoT `candidate_limit`**: introdotta `_default_candidate_limit()` in `src/retriever.py` come singola fonte di verità (eliminata la duplicazione del valore di default). Aggiornate:
  - `with_config_candidate_limit(...)`
  - `with_config_or_budget(...)`
  - `preview_effective_candidate_limit(...)`
- **`cosine(...)` iterator-safe**: riscritta per lavorare su iterabili senza slicing/indicizzazione, supportando `deque` e sequenze non indicizzabili. Stessa semantica su vettori di pari lunghezza e gestione norme nulle.

### Tests
- **Nuovi unit test** (`tests/test_retriever_unit.py`):
  - `cosine` con `deque`, lunghezze diverse e norme nulle.
  - Precedenze `candidate_limit` (esplicito/config/auto_by_budget/default) incl. `preview_effective_candidate_limit`.
- **Esito suite**: 104 passed, 1 skipped (symlink non supportati su Windows).

### Note per gli sviluppatori
- Nessun breaking change su API/CLI.
- Micro-ottimizzazione memoria su `cosine` (niente slice/copie).
- Consigliato eseguire i hook `pre-commit` per garantire allineamento lint/typecheck.


## [Unreleased]

### Tests
- Aggiunta suite per `semantic.api._call_convert_md` (fail-fast su non-callable, binding firma, supporto `md_dir` kw).
- Aggiunti test di validazione `retriever` (slug/scope/k/candidate_limit) ed early-return (query vuota, k=0, candidate_limit=0).
- Aggiunti test di scoring: tie-break deterministico e gestione `embedding` mancante.
- Aggiunti test di configurazione: precedenze `with_config_candidate_limit` / `with_config_or_budget`, mappatura `choose_limit_for_budget`, proprietà di monotonicità per budget > 0 e caso sentinella budget=0.
- Uniformati gli import dei test a `from src...`, stub `EmbeddingsClient` compatibile con Protocol, fix PEP8/Flake8 (E302/E402/F811/F401/W293).


## [Unreleased]

### Added
- Creato nuovo modulo `pipeline.errors` per centralizzare la gerarchia di eccezioni comuni (`TimmyError`, `ConfigError`, `RetrieverError`, `PreviewError`, `PushError`).

### Changed
- `retriever.py`: sostituiti i `ValueError` con `RetrieverError` tipizzata.
- Refactor del calcolo dello scoring:
  - estratta funzione `_score_candidates`.
  - introdotto uso di `heapq.nlargest` per ottimizzare il recupero dei top-k.
- Logging invariato, mantenuto tie-break deterministico (score desc, idx asc).

### Tests
- Aggiunto test di proprietà per verificare la monotonicità di `choose_limit_for_budget`.


## [fix] - 2025-09-14

### Changed
- `onboarding_ui.py`: spostato bootstrap e import dentro `main()` per evitare side-effects a import time (niente più E402); tipizzazione migliorata (`ClientContext`), helpers centralizzati per logging/redaction, uso di `sys.executable` nei subprocess, salvataggio impostazioni retriever via `get_client_config`/`update_config_with_drive_ids`.
- UI modularizzata: estratti i moduli `src/ui/tabs/finance.py` e `src/ui/tabs/preview.py`; la UI ora importa e usa questi componenti.

### Security
- `finance.api.import_csv`: path-safety rafforzata usando `open_for_read(sem_dir, csv_path, encoding="utf-8", newline="")` (previene path traversal); rimosse chiamate ridondanti a `ensure_within`.

### Fixed
- Pulizia mypy/flake8: rimossi `# type: ignore` inutilizzati e import non usati; normalizzate alcune righe >120 caratteri.
- Robustezza Windows: sostituito `["py", "..."]` con `[sys.executable, "..."]` per l’esecuzione del tool dummy.

### Internal
- Uniformato l’uso di `st.rerun`/`experimental_rerun`; messaggistica UI e logging più coerenti.


## [1.9.0] - 2025-09-12
### Added
- UI: introdotti asset locali configurabili in `assets/`:
  - `assets/html/app_skeleton.html` con placeholder espliciti per landing/schermata generale.
  - `assets/css/base.css` (tema light, banner sidebar, pill, card 2 colonne).
  - `assets/js/main.js` (micro-interazioni opzionali; degrada senza errori se assente).
- QA: hook pre-commit `qa-safe` (black/flake8/mypy se presenti) e hook pre-push `qa-safe --with-tests`.
- Makefile: target `qa-safe` e `ci-safe` per esecuzione degradabile dei check.
- Nuova utility `pipeline.yaml_utils.yaml_read` con cache opzionale.

### Changed
- Convergenza letture YAML: tutti i call-site di lettura YAML passano da `yaml_read` (SafeLoader, path-safety fail-closed, encoding utf-8, errori uniformi).
- Documentazione aggiornata (README sezione QA locale; CHANGELOG): nessuna modifica alle API pubbliche.

### Security
- Fail-closed su path fuori perimetro, file mancanti o YAML malformati (uniformato su `ConfigError`).

---
## [1.8.2] - 2025-09-07
### Added
- Introdotto `ensure_within_and_resolve` in `pipeline/path_utils.py` come wrapper unico per la validazione e normalizzazione dei path in lettura.

### Changed
- Tutte le letture di file (Markdown, CSV, YAML) nei moduli `semantic/*` e `pipeline/*` ora passano attraverso il wrapper di path-safety.
- Aggiornata la documentazione (`coding_rule.md`, `developer_guide.md`) per riflettere l’obbligo di usare il wrapper anche in lettura.

### Security
- Prevenzione completa di path traversal e accessi non autorizzati a file fuori dal `base_dir` anche in fase di lettura.
- Aggiunti test specifici per traversal `../` e symlink esterni.

---
## [1.8.2] - 2025-09-06

### Changed
- UI Onboarding (`onboarding_ui.py`):
  - Introdotto helper `_mark_modified_and_bump_once` per centralizzare il bump versione (N_VER) e il flag `modified`, rimuovendo duplicazioni.
  - Sblocco tab “Semantica” ottimizzato: cache di `raw_ready` in sessione per evitare scansioni FS ripetute; aggiunto pulsante “Rileva PDF in raw/” per aggiornare lo stato senza nuovo download.
  - Generazione README su Drive ora chiama `emit_readmes_for_raw(..., ensure_structure=True)` per garantire la struttura quando necessario.
- Runner Drive (`src/ui/services/drive_runner.py`):
  - Evitata ricreazione non necessaria della struttura in `emit_readmes_for_raw` con nuovo parametro `ensure_structure` (default: False) e lookup della cartella `raw/` via listing.
  - De-duplicazione download: `download_raw_from_drive` delega alla variante con progress (`download_raw_from_drive_with_progress` con `on_progress=None`).
  - Pre-scan delle liste Drive eseguito solo se serve la barra di avanzamento; in caso semplice, singolo passaggio per ridurre le chiamate API.
- Test: suite invariata (nessun cambiamento ai contratti pubblici); refactor trasparente.

### Added
- Vision parser placeholder: `semantic/vision_parser.pdf_to_vision_yaml()` genera `config/vision_statement.yaml` dal PDF `config/VisionStatement.pdf` durante il nuovo onboarding (UI slug-first).

### Removed
- Rimosso il parser legacy `src/semantic/vision_parser.py` e il vecchio flusso `semantic/vision.yaml`. Il file canonico ora è `config/vision_statement.yaml`.

### Fixed
- UI: normalizzati caratteri e simboli (“→”, accenti) in titoli e didascalie.
- Documentazione: ripulita “mojibake” in `docs/guida_ui.md`, `docs/user_guide.md`, `docs/index.md`; aggiunte note su “ensure_structure” e pulsante “Rileva PDF in raw/”.

### Notes
- Nessun breaking change; migliorate performance e manutenibilità (DRY) su UI/Drive. Tutti i test passano: 46 passed.

## [1.8.1] - 2025-09-06

### Added
- Test unitari/E2E per semantica:
  - `tests/test_semantic_extractor.py`: `_list_markdown_files`, `extract_semantic_concepts` (`max_scan_bytes`, short-circuit mapping vuoto).
  - `tests/test_semantic_mapping.py`: normalizzazione varianti (`keywords`/`esempio`/`tags`), fallback e errori.
  - `tests/test_semantic_api_frontmatter.py`: parse/dump/merge frontmatter, indice inverso e tag guessing.
  - `tests/test_semantic_api_enrich_frontmatter.py`: flusso E2E con scrittura sicura.
  - `tests/test_semantic_api_summary_readme.py`: generatori + fallback + validazione.
- Makefile: target `type-pyright` per eseguire Pyright (o `npx pyright`).

### Changed
- Refactor per SSoT dei contratti: uso di `semantic.types.ClientContextProtocol` in `pipeline.content_utils` e `semantic.semantic_extractor`; rimozione dei `Protocol` locali duplicati.
- DRY validazioni: `enrich_markdown_folder` ora delega a `_list_markdown_files` per path-safety/esistenza.
- SRP `content_utils`: estratti helper `_iter_category_pdfs` e `_render_category_markdown` per separare traversal/rendering.
- Documentazione aggiornata (README, Developer Guide, Coding Rules, Index) con note su contratti SSoT e type checking.
 - Error handling: `_ensure_safe` in `pipeline.content_utils` ora cattura solo `ConfigError` (propaga altre eccezioni), evitando di mascherare errori imprevisti.

### Fixed
- Pulizia `flake8` e formattazione Black nei nuovi test e moduli toccati.

### Notes
- Nessun breaking change; refactor interni e copertura test ampliata.

## [1.8.0] - 2025-09-06

### Breaking
- YAML struttura: supporto unico al formato moderno { raw: {...}, contrattualistica: {} }.
- Drive: rimossi alias nel risultato (RAW/YAML), usare solo chiavi effettive.
- Mapping: accettato solo semantic/tags_reviewed.yaml (rimosso alias 	ags_reviews.yaml).
- UI/Runner: dipendenze pipeline.* obbligatorie (rimossi import opzionali e stubs).
- Semantica: façade semantic.api unica; rimosso src/semantic_onboarding.py.

### Added
- pipeline.path_utils.to_kebab(s: str) come SSoT per normalizzazione chiavi.
- src/semantic_headless.py (CLI minimale) per conversione/enrichment/README&SUMMARY via façade.

### Changed
- src/ui/utils.py ora delega alle utility pipeline (ensure_within, safe_write_text, to_kebab).
- Log ASCII-only per messaggi console; rimossi emoji/simboli non ASCII.
- config/cartelle_raw.yaml convertito al formato moderno.
- Refactor leggibilità `content_utils`: estratti helper puri e `__all__` per API chiara.
- Ottimizzazione `semantic_extractor.extract_semantic_concepts`: pre-normalizzazione keyword e early-exit per file.
- Tipizzazione: introdotti `Protocol` locali (`_Context`, `_Ctx`) in moduli che usano subset del contesto.

### Fixed
- Normalizzati messaggi logger in vari moduli (pre_onboarding, gitbook_preview, github_utils, config_utils).
- Runner Drive: generazione README coerente (titoli ed elenchi ASCII) e logging alias-free.
- Path-safety e scritture atomiche: `vscode_bridge.py` ora usa `safe_write_text` + `ensure_within` (niente `Path.write_text`).
- Fail-fast coerente: rimossi `assert` runtime in `proc_utils.py` e `tag_onboarding.py` sostituiti con eccezioni tipizzate.

### Tooling / Governance
- Pre-commit: aggiunti hook locali
  - `forbid-runtime-asserts` (blocca `assert` in `src/`),
  - `forbid-path-write-text-bytes` (blocca `Path.write_text/bytes` in `src/`).
- Documentazione aggiornata:
  - `.codex/CODING_STANDARDS.md`: policy pre-commit, API di modulo con `__all__`, uso `Protocol`.
  - `.codex/CHECKLISTS.md`: sezione “Pre-commit policies”.

---## [1.7.0] - 2025-09-01

### Added
- cSpell: nuove parole di progetto in cspell.json (es. "Pydantic", "versionare", "sottocartella", "versionati", "idempotente", "versionato", "conftest", "versioniamo", "taggata", "rilasciabile").
- cSpell: ignoreRegExpList per gestire contrazioni italiane con apostrofo tipografico/ASCII (es. dellutente, dell'utente).
- Script scripts/fix_mojibake.py (usa tfy) per normalizzare caratteri UTF-8 nei Markdown.

### Changed
- Priorità lingua cSpell impostata a it,en in cspell.json e .vscode/settings.json.
- Normalizzazione encoding e tipografia nei Markdown sotto docs/ (accenti, em-dash, frecce, "facade").

### Fixed
- Risolti avvisi cSpell residui in docs/guida_ui.md, docs/test_suite.md, docs/versioning_policy.md, docs/policy_push.md.
- Ripristinati caratteri corretti e rimosso "mojibake" in docs/policy_push.md, docs/test_suite.md, docs/index.md e altri file docs/*.

### Added
- cSpell: nuove parole di progetto in `cspell.json` (es. Pydantic, versionare, sottocartella, versionati, idempotente, versionato, conftest, versioniamo, taggata, rilasciabile).
- cSpell: `ignoreRegExpList` per gestire contrazioni italiane con apostrofo tipografico/ASCII (es. `dellutente`, `dell'utente`).
- Script `scripts/fix_mojibake.py` (usa `ftfy`) per normalizzare caratteri UTF8 nei Markdown.

### Changed
- Priorità lingua cSpell impostata a `it,en` in `cspell.json` e `.vscode/settings.json`.
- Normalizzazione encoding e tipografia nei Markdown sotto `docs/` (accenti, em-dash, frecce, faÃ§ade).

### Fixed
- Risolti avvisi cSpell residui in `docs/guida_ui.md`, `docs/test_suite.md`, `docs/versioning_policy.md`, `docs/policy_push.md`.
- Ripristinati caratteri corretti e rimosso mojibake in `docs/policy_push.md`, `docs/test_suite.md`, `docs/index.md` e altri file `docs/*`.
## [1.6.1]  2025-08-30

### Added
- Nuovo task **CILite** in `tools/dev/tasks.ps1` per esecuzione rapida di check locali:
  `black --check`, `flake8`, `pytest -k 'unit or content_utils' -ra`.
  Include opzionalmente `mypy -p ui`.

### Changed
- Pulizia e tipizzazione modulo **ui**:
  - Rimossi `# type: ignore` inutilizzati.
  - Annotazioni `Optional`/`Callable` per i compat (`_repo_ensure_within`, `_repo_safe_write_text`).
  - Stub logger `_Stub` annotato con `Any` e ritorno `None`.
  - Funzioni helper (`_get_logger`, `_drive_list_folders`, `_drive_upload_bytes`, ecc.) con firme tipizzate.
  - Soppressione mirata `# type: ignore[import-untyped]` per import `MediaIoBaseUpload/Download`.

- **pyproject.toml**: override `[[tool.mypy.overrides]]` per `ui.*` con `follow_imports = "skip"`, cosÃ¬ mypy non scende in pipeline/* durante l'analisi mirata.

### Fixed
- **flake8**: portato a 0 errori (inclusi wrapping docstring lunghi).
- **pytest (unit + content_utils)**: ora **13 test passati / 10 deselezionati**, tutto verde.
- **mypy -p ui**: azzerati gli errori locali, residui confinati ai pacchetti `pipeline/*`.

---

## [1.10.0] - 2025-09-13
### Added
- Infra/Retriever: metriche leggere in `src/retriever.py::search` (embed_ms, fetch_ms, score+sort_ms, total_ms).
- Tools: script di calibrazione `src/tools/retriever_calibrate.py` per misurare latenza vs `candidate_limit` (+ opzionale dump top-k JSONL).
- UI: sezione Sidebar "Ricerca (retriever)" con box apri/chiudi per `candidate_limit` e "budget di latenza"; salvataggio atomico in `config.yaml` (`retriever.candidate_limit`, `latency_budget_ms`).

### Changed
- Sicurezza letture: `src/tag_onboarding.py::compute_sha256` ora usa wrapper di lettura binaria con path-safety (`open_for_read_bytes_selfguard`).
- Lint: aggiunto `import json` in `src/tag_onboarding.py` e pulizia import inutilizzati.

### Removed
- Semantica: rimossi tutti i fallback in `src/semantic/api.py`:
  - Eliminata `_fallback_markdown_from_raw` (nessuna generazione placeholder dei `.md`).
  - `write_summary_and_readme` non usa più `ensure_readme_summary` (niente fallback automatico su README/SUMMARY);
    ora tenta i generatori e solleva in caso di errori.
- Drive: rimossi placeholder/stub in `src/pipeline/drive_utils.py` (niente `MediaIoBaseDownload` placeholder, niente stub su `download_drive_pdfs_to_local`).

### Breaking
- `semantic.api` richiede ora le utilità reali di contenuto (`pipeline.content_utils`) e fallisce senza fallback:
  - `convert_markdown` richiede PDF presenti in `raw/` e il convertitore disponibile.
  - `write_summary_and_readme` solleva se i generatori falliscono (nessun fallback a contenuti di comodo).
- `pipeline.drive_utils` esegue import "hard" di `googleapiclient` e dei moduli Drive:
  - In assenza di `google-api-python-client` l'import del modulo fallisce con `ImportError` esplicito.
  - I test sono stati aggiornati per accettare/skip in ambienti senza la dipendenza.

### Notes
- I pochi fallback cosmetici di UI (es. favicon mancante, rerun sperimentale) restano per comodità e non impattano le API.
- Suite aggiornata: 70 passed, 1 skipped (symlink su Windows).
## 1.6.0  2025-08-29  Interfaccia Streamlit

### Added
- **Nuova UI Streamlit (`onboarding_ui.py`)**
  - Schermata iniziale full-screen con due soli input: **Slug cliente** e **Nome cliente**; al completamento i valori vengono **bloccati** e appare la UI completa.
  - Header con **Cliente** e **Slug** e pulsante **Chiudi UI** (terminazione controllata del processo).
- **Tab Configurazione**
  - Editor del *mapping semantico* con **accordion per categoria** (Ambito, Descrizione, Esempi) e **Salva** puntuale per-voce.
  - Validazione e **salvataggio atomico** del mapping rivisto (`tags_reviewed.yaml`). Normalizzazione chiavi via **SSoT `to_kebab()`**.
- **Tab Drive**
  - Pulsante **Crea/aggiorna struttura** (cartella cliente su Drive, `raw/`, `contrattualistica/`, upload `config.yaml`).
  - Pulsante **Genera README in raw/** (emette `README.pdf` o `.txt` in ogni sotto-cartella `raw/`, con ambito/descrizione/esempi).
  - **Nuova sezione Download contenuti su raw/**: pulsante **Scarica PDF da Drive** nella struttura locale `raw/`. Al termine sblocca la tab *Semantica*. Messaggio guida operativo accanto al pulsante.
- **Tab Semantica**
  - Integrazione con `src/semantic_onboarding.py`:
    1) **Converti PDF in Markdown** (RAW  BOOK)
    2) **Arricchisci frontmatter** con vocabolario rivisto (`tags_reviewed.yaml`)
    3) **Genera/valida README & SUMMARY**
    4) **Preview Docker (HonKit)** avvio/stop con porta configurabile.
- **Runner Drive**
  - Nuova funzione `download_raw_from_drive(slug, ...)` con **path-safety** (`ensure_within_and_resolve`), **scritture atomiche**, sanitizzazione nomi file e **logging strutturato**.

### Changed
- **Gating dell'interfaccia**: la UI compare solo dopo lo sblocco iniziale (slug+cliente). La tab *Semantica* Ã¨ nascosta finchÃ© non si completa il download dei PDF su `raw/`.
- **Streamlit re-run**: introdotto `_safe_streamlit_rerun()` che usa `st.rerun` (fallback su `experimental_rerun` se presente) per compatibilità  con gli stub Pylance.
- **Pylance-compat nei runner Drive**: uso di `_require_callable(...)` per *narrowing* delle API opzionali (niente piÃ¹ `reportOptionalCall`), applicato a `get_drive_service`, `create_drive_folder`, `create_drive_structure_from_yaml`, `upload_config_to_drive_folder`.
- **Coerenza logging/redazione**: inizializzazione del flag via `compute_redact_flag`; propagazione `context.redact_logs` nei call-site.

### Fixed
- Eliminati warning Pylance su accessi opzionali (`.strip` su `None`) con `_norm_str`.
- Rimosso uso di `key=` non supportato su `st.expander` in alcune versioni; **key** univoche per i widget dove necessario.
- Messaggistica di errore UI chiara e resilienza ai fallimenti delle operazioni Drive.

### Security / Hardening
- **Path-safety** estesa ai download Drive e alle generazioni locali; guardie anti path traversal.
- **Scritture atomiche** per file generati/aggiornati (README, SUMMARY, Markdown convertiti).
- Redazione automatica di identificativi/sensibili nei log quando abilitata.

### Migration notes
- Impostare credenziali Google Drive e **`DRIVE_ID`** nell'ambiente.
- Flusso consigliato per nuovi clienti:
  1) Compilare **Slug** e **Nome cliente** (sblocco UI)
  2) Tab **Drive**  *Crea struttura*  *Genera README in raw/*
  3) **Scarica PDF** su `raw/` (sblocca tab **Semantica**)
  4) Tab **Semantica**  *Converti*  *Arricchisci*  *README & SUMMARY*  *(opz.) Preview Docker*
- Se esistono riferimenti a `st.experimental_rerun`, sostituirli con `_safe_streamlit_rerun()`.

---


## 1.5.0 fixing  2025-08-28

### Added
- **Editing per-voce (UI Configurazione):** anteprima trasformata in *accordion*; ogni categoria ha campi propri (Ambito, Descrizione, Esempi) e pulsante **Salva** puntuale.
- **Pulsante Chiudi UI**: aggiunto in **sidebar** (sotto gli input di contesto) per terminare Streamlit dal terminale (SIGTERM, fallback sicuro).

### Changed
- **Nasconde `context` nella UI**: l'anteprima/edit non mostra `context: {slug, client_name, created_at}`.
- **Requisiti avvio:** per procedere servono **slug** e **nome cliente**.
- **Normalizzazione chiavi centralizzata:** introdotta `to_kebab()` in `src/ui/utils/core.py` e riuso in tutta la UI.
- **Logger coerente**: uso di `get_structured_logger(..., context=...)` anche nei runner, con redazione attiva via `compute_redact_flag`.

### Fixed
- **Bottone Genera README in raw/**: risolto crash (duplica logica/mancato import). Ora la generazione usa la `to_kebab()` centralizzata e funziona correttamente.
- **StreamlitDuplicateElementId**: assegnate **key univoche** a tutti i `button` e agli `expander`.
- **Allineamento runner Drive**: cleanup import e coerenza con le API `pipeline.drive_utils` (client, creazione struttura, upload config).

### Notes
- Patch **backward-compatible**; nessun breaking change.
- Confermate **path-safety** e **scritture atomiche**; rispetto della regola di **riuso** delle funzioni di pipeline.

---

## [1.7.0] - 2025-09-01

### Added
- cSpell: nuove parole di progetto in cspell.json (es. "Pydantic", "versionare", "sottocartella", "versionati", "idempotente", "versionato", "conftest", "versioniamo", "taggata", "rilasciabile").
- cSpell: ignoreRegExpList per gestire contrazioni italiane con apostrofo tipografico/ASCII (es. dellutente, dell'utente).
- Script scripts/fix_mojibake.py (usa tfy) per normalizzare caratteri UTF-8 nei Markdown.

### Changed
- Priorità lingua cSpell impostata a it,en in cspell.json e .vscode/settings.json.
- Normalizzazione encoding e tipografia nei Markdown sotto docs/ (accenti, em-dash, frecce, "facade").

### Fixed
- Risolti avvisi cSpell residui in docs/guida_ui.md, docs/test_suite.md, docs/versioning_policy.md, docs/policy_push.md.
- Ripristinati caratteri corretti e rimosso "mojibake" in docs/policy_push.md, docs/test_suite.md, docs/index.md e altri file docs/*.  2025-08-28

### Added
- **Nuova tab Configurazione (prima posizione)**: editor del *mapping semantico* basato su `config/default_semantic_mapping.yaml`, con:
  - schede per categoria (tabs, titolo = nome cartella);
  - campi **Ambito**, **Descrizione**, **Esempi** (lista dinamica);
  - validazione e **anteprima YAML** (expander apri/chiudi);
  - salvataggio atomico in `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml`.
- **Caricamento Vision PDF (pre-onboarding)**:
  - estrazione robusta delle sole sezioni **Organization / Vision / Mission**;
  - normalizzazione testo e scrittura di `output/timmy-kb-<slug>/semantic/vision.yaml`.
- **Runner Drive**:
  - creazione cartella cliente `<slug>` su Drive + upload `config.yaml`;
  - generazione della struttura **raw/** e **contrattualistica/** derivata da `tags_reviewed.yaml`;
  - emissione automatica di **README.pdf** (o `.txt` fallback) in ogni sotto-cartella di `raw/`, contenente ambito, descrizione ed esempi.

### Changed
- Flusso UI rivisto: editor delle cartelle *raw* sostituito dall**editor del mapping**; la struttura `raw/` viene ora derivata da `tags_reviewed.yaml`.
- La tab Struttura (Editor  mapping) Ã¨ stata rinominata in **Configurazione** e portata al primo posto.
- Anteprima YAML del mapping trasformata in **expander apri/chiudi**.

### Fixed
- Estrazione O/V/M dal PDF: migliorata la rilevazione dei titoli, la delimitazione dei paragrafi e la pulizia (linee orizzontali, bullet isolati, numeri pagina).
- Serializzazione YAML di `vision.yaml` e `tags_reviewed.yaml`: struttura corretta e ordinata, con scrittura **atomica**.
- **NameError `re`** nel generatore di README: centralizzata la normalizzazione in `utils.to_kebab()` ed import sistemati.

### Removed
- Pulsante **Imposta in config.yaml (raw)** e selettori sorgente YAML/sezione non piÃ¹ necessari nel nuovo flusso.
- Editor ad albero della vecchia `cartelle_raw.yaml` da interfaccia.

### Internal
- Introdotto package **`src/ui/`** che separa la logica dallUI:
  - `utils.py` (path-safety `ensure_within_and_resolve`, scritture atomiche `safe_write_text_compat`, `yaml_load/dump`, `to_kebab`, estrazione PDF);
  - `mapping_editor.py` (split/build/validate mapping, persistenza `tags_reviewed.yaml`, derivazione struttura `raw/`);
  - `vision_parser.py` (parser O/V/M e writer `vision.yaml`);
  - `drive_runner.py` (creazione struttura Drive e upload README).
- Aggiornati gli import per usare, ove disponibili, le API di `src/pipeline` (context/drive/upload/logging).
- **Hardening**: piÃ¹ controlli sui path, fallback su librerie PDF, gestione errori UI piÃ¹ chiara.
- Nota di compatibilità : il vecchio `src/config_onboarding.py` resta temporaneamente nel repo per continuità ; verrà  rimosso quando tutte le tab saranno migrate sui nuovi runner.

---

## [1.5.0] Fixing e allineamenti - 2025-08-27

### Added
- Docstring coerenti su funzioni chiave degli orchestratori (es. `tag_onboarding`, `onboarding_full`, CLI `_parse_args`).
- Supporto a `pytest-cov` per report di coverage (opzionale in dev).

### Changed
- **Logging unificato e strutturato**:
  - Uso sistematico di `get_structured_logger` con `slug`/`run_id` in extra.
  - Rimozione di `print()` a favore di log strutturati.
- **Path-safety STRONG**: validazioni con `ensure_within(...)` prima di scrivere/copiare/rimuovere file e nel mount Docker.
- **Scritture atomiche**: adozione di `safe_write_text`/`safe_write_bytes` nei moduli che generano file (es. preview, review writer, tags I/O).
- **Preview porta configurabile**: `preview_port` ora puÃ² essere impostata via config/env (fallback a 4000).
- **Adapter Preview** (`src/adapters/preview.py`):
  - Firma coerente: `start_preview(context, logger, *, port, container_name) -> str` e `stop_preview(logger, *, container_name)`.
  - Propagazione `context.redact_logs`.
  - Validazioni conservative su `port` e `container_name`.
- **Tipizzazione logger**: parametri `logger` annotati come `logging.Logger` nei moduli:
  - `semantic_*`, `adapters/preview`, `onboarding_full`, `pipeline/github_utils`, `pipeline/cleanup_utils` ( `_rmtree_safe` ).
- **Coerenza errori dominio**:
  - Sostituiti errori generici/di filesystem con eccezioni di dominio (`ConfigError`, `PipelineError`, `PushError`, `PreviewError`, ecc.).
  - `review_writer`: usa `ConfigError` quando manca PyYAML.
  - `semantic_mapping`/`semantic_extractor`: `FileNotFoundError`/`NotADirectoryError` rimpiazzati con errori di pipeline coerenti e messaggi migliorati.
- **github_utils**:
  - Refactor push con `_push_with_retry` e `_force_push_with_lease` (governati), env sicuro con `GIT_HTTP_EXTRAHEADER`.
  - Raccolta deterministica dei `.md` (no `.bak`) e cleanup temporanei piÃ¹ robusto.

### Fixed
- `gen_dummy_kb`: definizioni mancanti e ordine funzioni; ora build sandbox dummy completa senza `NameError`.
- Vari log message normalizzati (emoji opzionali, chiavi `extra` consistenti).

### Internal
- Orchestratori: separazione netta tra log early e log su file per sandbox.
- Maggiore adesione al contratto solo `.md` in `book/` con preflight e messaggi di errore esplicativi.
- Best-effort cleanup di container Docker in preview.

> **Note di migrazione**
> - Se usavi la preview con porta fissa, verifica `PREVIEW_PORT` (o config equivalente).
> - Per il push force, assicurati che `GIT_FORCE_ALLOWED_BRANCHES` includa il branch desiderato e passa `force_ack`.


---
## [1.5.0]  2025-08-27  Test & Documentazione

### Added
- **Nuova area test** `tests/` con suite PyTest:
  - `tests/test_contract_defaults.py`  verifica default CLI (es. `tag_onboarding`).
  - `tests/test_smoke_dummy_e2e.py`  smoke end-to-end su dataset dummy.
  - `tests/test_unit_book_guard.py`  contratto `book/` (solo `.md`, `.md.fp` ignorati).
  - `tests/test_unit_emit_tags_csv.py`  header e path POSIX in `tags_raw.csv`.
  - `tests/test_unit_tags_validator.py`  validazione `tags_reviewed.yaml` (ok/errori/duplicati).
- **`pytest.ini`** con `pythonpath=.` e `testpaths=tests` per import stabili su tutti gli OS.
- **Dataset utente dummy**: uso ufficiale di `py src/tools/gen_dummy_kb.py --slug dummy` per popolare `raw/` prima dei test.
- **Documentazione test dedicata**: `docs/test_suite.md` (lancio globale, singoli file, selezione per keyword, coverage, principi di isolamento).

### Changed
- **Default sorgente in `tag_onboarding`  `drive`** (con `--source local` come alternativa). Allineati i test di contratto.
- **Architettura**: aggiornata a **v1.5.0** in `docs/architecture.md` con sezione **tests/**, principi, piramide (unit/contract/smoke).
- **User Guide**: sezione Test minimi resa sintetica e rimandata a `docs/test_suite.md`.

### Fixed
- **Preflight `book/`**: chiarita e verificata la regola solo `.md` (ignora `.md.fp`) prima del push.
- Allineamento doc-codice su flussi test e precondizioni (creazione utente dummy).

### Migrazione / Note operative
- Prima di eseguire i test:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ---
  I test non richiedono credenziali reali (Drive/GitHub mockati o bypassati); lE2E manuale Ã¨ documentato in docs/test_suite.md.
---

## [1.4.0] - fixing 2025-08-27
### Added
- Validatore `tags_reviewed.yaml` con report JSON.
- Guard preflight in `onboarding_full` (solo `.md`, `.md.fp` ignorati).
- Default `local` in `tag_onboarding` (Drive opt-in).
- Iniezione blocco `context` in `semantic_mapping.yaml`.

### Changed
- SSoT: ora la pipeline usa `tags_reviewed.yaml` come unica fonte semantica.
- Orchestratori riallineati: path-safety forte, logger tipizzato, errori mappati su `EXIT_CODES`.

### Fixed
- Hardening `semantic_onboarding`: gestione YAML e arricchimento frontmatter piÃ¹ robusti.

## [1.4.0] - 2025-08-26

### Added
- **Proc utils**: nuovo modulo `src/pipeline/proc_utils.py` con `run_cmd` (timeout/retry/backoff, logging strutturato), `wait_for_port`, helper Docker (`run_docker_preview`, `stop_docker_preview`).
- **Preview HonKit/GitBook**:
  - `src/pipeline/gitbook_preview.py`: build/serve in Docker, readiness check, stop best-effort.
  - `src/adapters/preview.py`: adapter semplice `start_preview/stop_preview`, default `gitbook-<slug>`, propagazione `redact_logs`.
- **Semantica**:
  - `src/semantic/tags_extractor.py`: copia PDF sicura + `emit_tags_csv` (schema esteso: `relative_path|suggested_tags|entities|keyphrases|score|sources`).
  - `src/semantic/tags_io.py`: `write_tagging_readme`, `write_tags_review_stub_from_csv` (dedup/normalize, path-safety, scrittura atomica).
  - `src/semantic/tags_review_validator.py`: validazione YAML + `write_validation_report`.
- **Documentazione interna**: sezione SSoT scritture  `safe_write_text` (I/O & Path-safety) con pattern minimi.
- **CI/QA**:
  - **Qodana**: configurazione consigliata (incluso controllo licenze/dipendenze).
  - **GitHub Actions**: workflow CI con step separati **flake8**, **mypy**, **pytest**, cache pip e artifact dei log.

### Changed
- **SSoT scritture**: rimpiazzati `open(...).write(...)` con `safe_write_text` / `safe_write_bytes` e **guard-rail STRONG** `ensure_within` prima di ogni scrittura/eliminazione.
- **GitHub push** (`src/pipeline/github_utils.py`, refactor Patch 5):
  - Risoluzione branch via env (`GIT_DEFAULT_BRANCH`/`GITHUB_BRANCH`) con fallback `main`.
  - Creazione/ensure repo via PyGithub; clone in **working dir temporanea dentro la sandbox**; commit deterministico; push con retry.
  - **Force push governato**: `--force-with-lease` + allow-list branch e `force_ack` obbligatorio.
  - Autenticazione HTTP via `GIT_HTTP_EXTRAHEADER` (token non nei comandi); cleanup tmp idempotente; logging strutturato e redazione segreti.
- **Contenuti Markdown** (`src/pipeline/content_utils.py`):
  - Conversione annidata per categorie, fingerprint `.fp` per *skip if unchanged*, concorrenza per categoria.
  - `SUMMARY.md` e `README.md` generati in modo atomico e sicuro.
- **Orchestratore tagging** (`src/tag_onboarding.py`):
  - Download/copia PDF con path-safety; **CSV streaming atomico**; checkpoint HiTL; validazione YAML con report JSON.
- **Tool dummy** (`src/tools/gen_dummy_kb.py`): rimosso `print()`, logging strutturato, log sugli step PDF/CSV, scritture atomiche centralizzate.
- **Cleanup**:
  - `src/pipeline/cleanup_utils.py`: rimozione sicura di artefatti legacy (`book/.git`) con `ensure_within`.
  - `src/tools/cleanup_repo.py`: cancellazione repo remoto via **API (PyGithub)** con fallback automatico a **CLI `gh`**, owner auto-detected; messaggistica migliorata.
- **Consistenza YAML**: uniformato su estensione `.yaml` anche per configurazioni CI/Qodana.
- **Dipendenze**: versioni aggiornate/pinnate per ripetibilità  build (PyGithub, google-api-python-client, PyYAML, docker, spaCy, ecc.).

### Fixed
- Eliminato rischio di **path traversal** su write/delete grazie a `ensure_within` su tutti i punti critici.
- Affidabilità preview HonKit: readiness check sulla porta e gestione container duplicati.
- Coerenza logging: rimosse stampe dirette; solo **logging strutturato**.

### Security
- Scritture **atomiche** ed **idempotenti**; backup `.bak` dove opportuno.
- Redazione automatica dei segreti nei log; autenticazione GitHub via header HTTP (niente token in argv).

### Known Issues
- La cancellazione del repo via API/CLI richiede permessi **admin** sul repository; in assenza di permessi si riceve 401/403 dalla API o errore dalla CLI. Lo strumento gestisce e logga il fallback, ma non puÃ² bypassare i permessi.

### Migration Notes
- Se presenti vecchi file `.yml`, rinominarli in `.yaml` per allineamento e per i riferimenti nei workflow/strumenti.

---

## 1.3.0 - 2025-08-26

### Changed
- Refactor orchestratori (`pre_onboarding.py`, `tag_onboarding.py`, `semantic_onboarding.py`) per rispettare le linee guida Codex:
  - Estrazione sottoprocedure in funzioni pure, unit-testabili (<80 righe).
  - Uniformata la gestione di fallback/adapters  ora tutte le funzioni usano `(context, logger, **opts)`.
- Migliorata la pipeline di tagging (`tag_onboarding.py`):
  - Passaggio a scrittura **CSV streaming riga-per-riga** con commit atomico.
  - Validazione YAML piÃ¹ robusta e reporting strutturato.
- Aggiornato `semantic_onboarding.py`:
  - Arricchimento frontmatter ottimizzato tramite dizionario inverso dei sinonimi (O(1) lookup).
  - Consolidato uso di `ensure_readme_summary` come fallback centralizzato per README/SUMMARY.

### Documentation
- Aggiornati **Architecture.md**, **Developer Guide** e **Coding Rules** (v1.3.0):
  - Documentati i nuovi invarianti (funzioni pure negli orchestratori, streaming CSV, enrichment indicizzato).
  - Allineati esempi di logging ed error handling.
  - Esplicitato uso centralizzato degli adapter e delle firme coerenti.


## [1.2.2] fix generici e armonizzazione funzioni - 2025-08-26

### Added
- **Test suite di configurazione (pytest + Pydantic)**
  - `tests/test_config_utils.py`: copertura completa dei moduli `pipeline.config_utils` (Settings, client config, pre-onboarding, scritture atomiche, aggiornamento Drive IDs).
  - Fixture `conftest.py` consolidata: genera sempre una sandbox dummy pulita (`--overwrite`), forza ambiente UTF-8 e gestisce teardown automatico salvo `KEEP_DUMMY_KB=1`.
- **Refactor tool interattivo**
  - `src/tools/refactor_tool.py`: menu interattivo grafico (box ASCII) con 3 voci:
    1.  Trova (solo ricerca)
    2. ï¸ Trova & Sostituisci
    3.  Cerca TODO/FIXME
  - Logging strutturato, dry-run con diff unificato leggibile, estendibile per futuri strumenti di refactor.

### Changed
- **`src/semantic/normalizer.py`**
  - Bug fix: `normalize_tags` ora ritorna correttamente `normed` (prima restituiva `""`).
  - Robustezza mapping: canonical/merge normalizzati a lowercase; coercizione prudente delle liste `synonyms`.
- **`src/tools/cleanup_repo.py`**
  - Flusso interattivo semplificato:
    - Conferma obbligatoria per la cancellazione locale di `output/timmy-kb-<slug>`, evidenziando che Ã¨ irreversibile.
    - Solo se confermata, viene chiesto se eliminare anche il repo GitHub remoto (`gh repo delete`).
  - Uso coerente di `pipeline.logging_utils.redact_secrets` al posto di `env_utils`.

### Fixed
- Import path per `pipeline.*` nei tool (`gen_dummy_kb.py`, `cleanup_repo.py`, `refactor_tool.py`) resi consistenti con il bootstrap della cartella `src/`.
- Errori di compatibilità  Windows (`ModuleNotFoundError: pipeline`) gestiti allineando sys.path a livello di progetto.

### Migration notes
- Per avviare i test singoli:
  ```bash
  pytest tests/test_config_utils.py -v
  pytest tests/test_dummy_pipeline.py -v


## [1.2.2] - 2025-08-25

### Added
- **Test suite dummy (pytest + Pydantic)**:
  - `tests/conftest.py`: fixture `dummy_kb` che rigenera la sandbox con `--overwrite` e valida i file chiave.
  - `tests/test_dummy_pipeline.py`: 4 test (struttura, coerenza CSV-PDF, idempotenza semantic, assenza `contrattualistica/`).
- **Robustezza Windows nei test**: forzato `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` al lancio di `gen_dummy_kb.py`.

### Changed
- **`src/tools/gen_dummy_kb.py`** riscritto:
  - Genera la sandbox dummy completa da `config/*.yaml`.
  - Produce PDF dummy coerenti con `pdf_dummy.yaml`.
  - Copia `cartelle_raw.yaml` in `semantic/` e crea `semantic_mapping.yaml` con blocco `semantic_tagger` default.
  - Genera `tags_raw.csv` tramite i moduli semantic (`extract_semantic_candidates  normalize_tags  render_tags_csv`).
- **`src/tag_onboarding.py`**:
  - `_emit_tags_csv` ora produce path base-relative (`raw/...`) e colonne extra (`entities`, `keyphrases`, `score`, `sources`) per compatibilità futura.

### Fixed
- Crash su Windows (`UnicodeEncodeError` da emoji , `NameError: json`).
- Path incoerenti tra CSV generati da strumenti diversi (ora formato unificato).
- Errore `relative_to` su `contrattualistica/` (cartella rimossa per design).

### Removed
- Generazione locale della cartella `contrattualistica/` nel dummy.

### Migration notes
- Rigenera la sandbox dummy:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy --name "Cliente Dummy" --overwrite

## [1.2.1] Intermedio  2025-08-25

> Release intermedia di consolidamento, applicata dopo le indicazioni di Codex e completata con refactor/test end-to-end sugli orchestratori. Focus su **pipeline core**; area semantica resta placeholder per la fase successiva.

### Changed
- **github_utils**
  - Estratto `_collect_md_files`, `_ensure_or_create_repo`, `_push_with_retry` e helper correlati per ridurre complessità di `push_output_to_github` (~400 <150 righe).
  - Migliorata leggibilità e testabilità mantenendo lo stesso comportamento.
- **onboarding_full.py**
  - Orchestratore snellito: usa `_git_push` dedicato con error handling coerente.
  - Conferme interattive piÃ¹ chiare, non-interactive totalmente silente.
- **logging_utils**
  - Refactor completo: `get_structured_logger` ora unica entrypoint.
  - Filtri di contesto e redazione applicati a tutti i call-sites.
  - Formatter coerente console/file con extra (`slug`, `run_id`, `branch`, `repo`).
- **Orchestratori (pre_onboarding, tag_onboarding, semantic_onboarding)**
  - Allineati a nuovo logging strutturato.
  - Path-safety rafforzata su tutti i call-site I/O di pipeline core.

### Fixed
- Nessun uso residuo di `FileNotFoundError`/`NotADirectoryError` in pipeline core (`src/pipeline`, `src/adapters`).
- Eliminati logger fallback o duplicati: tutti i moduli passano da `logging_utils`.

### Migration notes
- Usare sempre `get_structured_logger(...)` per creare logger.
- Gestire la redazione solo via `context.redact_logs` (inizializzato da `compute_redact_flag`).
- Area semantica (`semantic_extractor`, ecc.) resta ancora con built-in exceptions: da aggiornare in release successiva.


## [1.2.1]  2025-08-24

> Hardening trasversale: SSoT per path-safety, redazione log centralizzata e orchestratori resi piÃ¹ coesi.

### Added
- **logging_utils**
  - Filtro di redazione centralizzato (mascheratura su `msg/args/extra`).
  - Helper riusabili: `mask_partial`, `tail_path`, `mask_id_map`, `mask_updates`.
  - Metriche leggere: `metrics_scope`, `log_with_metrics`.

### Changed
- **env_utils**
  - Reso *puro*: nessuna mascheratura; introdotta `compute_redact_flag(env, log_level)` come fonte unica del flag.
  - Utilities per governance del force-push: `get_force_allowed_branches`, `is_branch_allowed_for_force`.
- **path_utils**
  - `ensure_within(base, target)` promosso a **Single Source of Truth** per path-safety; `is_safe_subpath` resta SOFT.
  - Aggiunti `ensure_valid_slug`, `sanitize_filename`, `sorted_paths`; cache regex slug + fallback robusto.
- **cleanup_utils**
  - Rimozioni protette: uso di `ensure_within` prima di delete; log strutturati coerenti.
- **github_utils**
  - Hardening push: selezione deterministica file, working dir temporanea sotto base cliente, retry con `pull --rebase`, lease per force-push e allow-list branch.
  - Env sanificato per subprocess; redazione opzionale lato logger.
- **gitbook_preview**
  - Build/serve via `proc_utils.run_cmd`; scritture atomiche (`safe_write_file`); `ensure_within` sulle destinazioni; `wait_until_ready` e stop best-effort.
- **content_utils**
  - Conversione RAW-BOOK con gerarchie annidate; fingerprint per skip idempotente; nomi file sanificati; scritture atomiche e path-safety; generatori `SUMMARY.md`/`README.md`.
- **drive/download**
  - Scansione BFS, idempotenza (MD5/size), verifica integrità post-download, path-safety forte e log redatti.
- **Orchestratori**
  - `pre_onboarding.py`: estratto `_sync_env()`, validazione slug centralizzata, redazione propagata.
  - `tag_onboarding.py`: CSV + stub semantico con scritture atomiche e guardie `ensure_within`.
  - `semantic_onboarding.py`: conversione/enrichment/README+SUMMARY/preview (nessun push).
  - `onboarding_full.py`: solo **push GitHub** (con conferma solo in interattivo).

### Fixed
- Import uniformati: **spostata la mascheratura** da `env_utils` a `logging_utils` (aggiornati i call-sites).
- Robustezza frontmatter/preview: gestione assenza PyYAML e correzioni su path relativi/assoluti.

### Security / Hardening
- **Path-safety** consolidata con `ensure_within` su tutte le scritture/copie/rimozioni sensibili.
- **Scritture atomiche** come default per file generati dalla pipeline.

### Migration notes
- Importare ora `redact_secrets` da `pipeline.logging_utils`.
- Inizializzare il flag di redazione negli orchestratori appena caricato il contesto:
  ```python
  from pipeline.env_utils import compute_redact_flag
  if not hasattr(context, "redact_logs"):
      context.redact_logs = compute_redact_flag(context.env, getattr(context, "log_level", "INFO"))

---

## [1.2.1]  2025-08-24

> Release focalizzata su refactor, documentazione e split chiaro degli orchestratori.
> PR correlate: **PR-5** (Semantic Onboarding), **PR-6** (Docs v1.2.1).

### Added
- **Nuovo orchestratore**
  - `src/semantic_onboarding.py`: gestisce conversione RAW-BOOK, arricchimento frontmatter e preview Docker; nessun push GitHub.
- **Docs**
  - Aggiunta guida aggiornata per `semantic_onboarding` nei manuali (User/Developer/Architecture).

### Changed
- **Orchestratori**
  - `onboarding_full.py`: ridotto a gestire solo il **push GitHub** (in futuro anche GitBook).
  - Precedente logica di conversione/enrichment/preview spostata in `semantic_onboarding.py`.
- **Adapter**
  - Uso uniforme di `ensure_within` da `pipeline.path_utils` come SSoT per path-safety.
- **Tool**
  - `gen_dummy_kb.py`: refactor secondo le nuove regole di atomicità e path-safety.

### Fixed
- Spostato import `from __future__ import annotations` ad inizio file per evitare `SyntaxError`.
- Allineamento docstring e logica di gestione dei file tra moduli e orchestratori.

### Documentation
- Aggiornati a v1.2.1:
  - `docs/architecture.md`: riflesso lo split orchestratori (`semantic_onboarding` vs `onboarding_full`).
  - `docs/developer_guide.md`: bootstrap `ClientContext`, policy redazione, responsabilità orchestratori.
  - `docs/user_guide.md`: nuovo flusso operativo con `semantic_onboarding`.
  - `docs/coding_rule.md`: chiariti punti su atomicità e adapter.
  - `docs/policy_push.md`: rivista policy di pubblicazione.
  - `README.md` e `docs/index.md`: aggiornati esempi CLI e versioni.

### Migration notes
- Usare ora la faÃ§ade `semantic.api` per conversione/enrichment/preview (deprecated: `semantic_onboarding.py`).
- `onboarding_full.py` va utilizzato solo per il push.
- Nei moduli, sostituire eventuali riferimenti a `file_utils.ensure_within` con `path_utils.ensure_within`.

---

## [1.2.0]  2025-08-24

> Release di stabilizzazione e hardening della pipeline. Introduce fallback uniformi, preview adapter, scritture atomiche e aggiornamento completo della documentazione.
> PR correlate: **PR-1** (Redaction SSoT), **PR-2** (Fallback & Preview adapter), **PR-3** (Atomic FS & Path-safety), **PR-4** (API cleanup & Docs).

### Added
- **Adapters**
  - `src/adapters/content_fallbacks.py`: `ensure_readme_summary(context, logger)` con fallback standard e idempotenti per `README.md` e `SUMMARY.md`.
  - `src/adapters/preview.py`: `start_preview(context, logger, *, port=4000, container_name=None)` e `stop_preview(logger, *, container_name=None)`; propagazione automatica `context.redact_logs`.
- **File utilities**
  - `pipeline/file_utils.py`: `safe_write_text`, `safe_write_bytes` (temp + `os.replace` atomico + fsync best-effort) e `ensure_within` (guardia anti path traversal).
- **Docs**
  - Nuovo `docs/SUMMARY.md` (indice top-level per GitHub/HonKit).

### Changed
- **Orchestratori**
  - `src/onboarding_full.py`:
    - Usa `adapters.content_fallbacks.ensure_readme_summary` per i fallback; rimosse logiche inline.
    - Preview unificata via `adapters.preview.start_preview/stop_preview`.
    - Scritture frontmatter con `safe_write_text` + `ensure_within`.
    - Firma helpers interna allineata a stile `(context, logger, **opts)`.
  - `src/tag_onboarding.py`:
    - Emissione `tags_raw.csv`, `README_TAGGING.md`, `tags_reviewed.yaml`, `tags_review_validation.json` con `safe_write_text`; guardie `ensure_within`/`is_safe_subpath`.
    - Fallback `context.redact_logs` se mancante  `compute_redact_flag()`.
  - `src/pre_onboarding.py`:
    - Risoluzione robusta `YAML_STRUCTURE_FILE`; messaggistica piÃ¹ chiara; uso coerente di `repo_root_dir` ed env helpers (no cambi funzionali in assenza di Drive).
- **ENV/Redaction**
  - `pipeline/env_utils.py`: `compute_redact_flag(env, log_level)` come single source of truth; orchestratori inizializzano `context.redact_logs` se non presente.
- **Demo tool**
  - `src/tools/gen_dummy_kb.py`: migrazione delle scritture a `safe_write_text` e verifiche path (dove applicabile).

### Fixed
- Allineata firma `ensure_readme_summary(...)` negli orchestratori (rimosso argomento non supportato `book_dir`).
- Log piÃ¹ robusti e non verbosi su assenza opzionale di PyYAML; migliorata resilienza del parsing frontmatter.

### Security / Hardening
- **Scritture atomiche di default** per file generati dalla pipeline  evita file troncati su interruzioni.
- **Path-safety**: `ensure_within`/`is_safe_subpath` applicati alle destinazioni sensibili.
- **Redazione log uniforme**: `compute_redact_flag` applicato/propagato agli adapter (preview) e agli orchestratori.

### Deprecated
- `is_log_redaction_enabled(context)` rimane per retro-compat ma **deprecato** in favore di `compute_redact_flag`.
- Uso diretto e sporadico di `os.environ` negli orchestratori  **usare** `env_utils.get_env_var/get_bool/get_int`.

### Documentation
- Aggiornati e riallineati:
  - `docs/architecture.md` (SSoT `repo_root_dir`, fallback uniformi, scritture atomiche).
  - `docs/developer_guide.md` (bootstrap `ClientContext`, policy redazione, responsabilità orchestratori vs moduli).
  - `docs/user_guide.md` (flussi interattivo/CLI, opzioni preview/push, troubleshooting).
  - `docs/coding_rule.md` (regole I/O sicure, atomicità, logging).
  - `docs/policy_push.md` (uso `--no-push`, `--force-push` + `--force-ack`, `GIT_DEFAULT_BRANCH`).
  - `docs/versioning_policy.md` (SemVer leggero, requisiti di release).
  - `docs/index.md` e **README** (sezioni riviste, esempi CLI aggiornati).

### Migration notes
- Rimpiazzare nei flussi:
  - Fallback inline  `adapters.content_fallbacks.ensure_readme_summary(context, logger)`.
  - Chiamate dirette a `pipeline.gitbook_preview.*`  `adapters.preview.start_preview/stop_preview`.
  - `Path.write_text(...)`  `safe_write_text(...)` (+ `ensure_within` o `is_safe_subpath`).
- Inizializzare `context.redact_logs` **subito dopo** `ClientContext.load(...)` se non presente:
  ```python
  from pipeline.env_utils import compute_redact_flag
  if not hasattr(context, "redact_logs"):
      context.redact_logs = compute_redact_flag(context.env, log_level="INFO")

## [1.1.0]  2025-08-23 Â· Lancio baseline stabile

### Added
- Prima versione stabile della pipeline con orchestratori separati (`pre_onboarding`, `tag_onboarding`, `onboarding_full`).
- Struttura modulare in `src/pipeline/` con gestione centralizzata di:
  - logging (`logging_utils`),
  - eccezioni tipizzate (`exceptions`),
  - variabili di ambiente e redazione (`env_utils`),
  - configurazioni e path safety (`config_utils`, `path_utils`).
- Documentazione completa in `docs/` (User Guide, Developer Guide, Architecture, Coding Rules, Policy Push, Versioning).

### Changed
- Allineamento di orchestratori e moduli al principio **UX vs logica tecnica**: prompt e `sys.exit()` confinati agli orchestratori; moduli puri e testabili.
- Output standardizzato in `output/timmy-kb-<slug>/` con sottocartelle (`raw`, `book`, `semantic`, `config`, `logs`).

### Notes
- Questa versione rappresenta la **base di partenza ufficiale**: da qui in poi ogni refactor, fix o nuova feature dovrà essere registrata come incremento SemVer e mantenere la compatibilità documentale.


## [1.9.2] - 2025-09-19
## [1.9.2] - 2025-09-19

### Added
- Content pipeline: supporto ai PDF nel root di `raw/` con generazione file aggregato in `book/` (es. `raw.md`).
- Test: copertura per PDF in root, cleanup orfani in `book/`, percent-encoding nel SUMMARY, writer CSV hardened e vocab loader fail-closed.

### Changed
- `pipeline.content_utils`:
  - `convert_files_to_structured_markdown`: traccia i file generati e rimuove `.md` orfani in `book/` (idempotente, path-safe).
  - `generate_summary_markdown`: percent-encoding dei link (label leggibile, link encoded) per gestire spazi/caratteri speciali.
- `semantic.auto_tagger.render_tags_csv`: firma aggiornata con `*, base_dir`; path-safety forte via `ensure_within_and_resolve` + `ensure_within`; scrittura atomica. Call-site aggiornati in `src/tools/gen_dummy_kb.py` e `semantic.api`.
- `semantic.vocab_loader.load_reviewed_vocab`: SSoT “fail-closed” su `tags.db`:
  - se manca il DB → `ConfigError` con istruzioni operative;
  - se il DB è vuoto → warning esplicito;
  - se valido → info con conteggio canonicals.

### Deprecated
- `semantic.tags_extractor.emit_tags_csv` deprecato. Usare `semantic.api.build_tags_csv(...)` oppure il writer low-level `semantic.auto_tagger.render_tags_csv(..., base_dir=...)`.

### Notes
- Nessun breaking sulle API pubbliche; migliorata la sicurezza I/O e la UX con messaggi espliciti.
- Nessun breaking sulle API pubbliche; migliorata la sicurezza I/O e la UX con messaggi espliciti.
