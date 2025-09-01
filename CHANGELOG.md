# Changelog – Timmy-KB

Tutte le modifiche rilevanti a questo progetto saranno documentate in questo file, seguendo il formato [Keep a Changelog](https://keepachangelog.com/it/1.0.0/) e aderendo a [Semantic Versioning](https://semver.org/lang/it/).

> **Nota metodologica:** ogni nuova sezione deve descrivere chiaramente il contesto delle modifiche (Added, Changed, Fixed, Security, ecc.), specificando file e funzioni interessate. Gli aggiornamenti devono essere allineati con la documentazione (`docs/`) e riflessi in README/User Guide/Developer Guide quando impattano la UX o le API pubbliche. Le versioni MINOR/MAJOR vanno accompagnate da note di migrazione.
---
## [Unreleased]

### Added
- cSpell: nuove parole di progetto in `cspell.json` (es. “Pydantic”, “versionare”, “sottocartella”, “versionati”, “idempotente”, “versionato”, “conftest”, “versioniamo”, “taggata”, “rilasciabile”).
- cSpell: `ignoreRegExpList` per gestire contrazioni italiane con apostrofo tipografico/ASCII (es. `dell’utente`, `dell'utente`).
- Script `scripts/fix_mojibake.py` (usa `ftfy`) per normalizzare caratteri UTF‑8 nei Markdown.

### Changed
- Priorità lingua cSpell impostata a `it,en` in `cspell.json` e `.vscode/settings.json`.
- Normalizzazione encoding e tipografia nei Markdown sotto `docs/` (accenti, em-dash, frecce, “façade”).

### Fixed
- Risolti avvisi cSpell residui in `docs/guida_ui.md`, `docs/test_suite.md`, `docs/versioning_policy.md`, `docs/policy_push.md`.
- Ripristinati caratteri corretti e rimosso “mojibake” in `docs/policy_push.md`, `docs/test_suite.md`, `docs/index.md` e altri file `docs/*`.
## [1.6.1] – 2025-08-30

### Added
- Nuovo task **CILite** in `tools/dev/tasks.ps1` per esecuzione rapida di check locali:
  `black --check`, `flake8`, `pytest -k 'unit or content_utils' -ra`.
  Include opzionalmente `mypy -p config_ui`.

### Changed
- Pulizia e tipizzazione modulo **config_ui**:
  - Rimossi `# type: ignore` inutilizzati.
  - Annotazioni `Optional`/`Callable` per i compat (`_repo_ensure_within`, `_repo_safe_write_text`).
  - Stub logger `_Stub` annotato con `Any` e ritorno `None`.
  - Funzioni helper (`_get_logger`, `_drive_list_folders`, `_drive_upload_bytes`, ecc.) con firme tipizzate.
  - Soppressione mirata `# type: ignore[import-untyped]` per import `MediaIoBaseUpload/Download`.

- **pyproject.toml**: override `[[tool.mypy.overrides]]` per `config_ui.*` con `follow_imports = "skip"`, così mypy non scende in pipeline/* durante l’analisi mirata.

### Fixed
- **flake8**: portato a 0 errori (inclusi wrapping docstring lunghi).
- **pytest (unit + content_utils)**: ora **13 test passati / 10 deselezionati**, tutto verde.
- **mypy -p config_ui**: azzerati gli errori locali, residui confinati ai pacchetti `pipeline/*`.

---

## 1.6.0 — 2025-08-29 — Interfaccia Streamlit

### Added
- **Nuova UI Streamlit (`onboarding_ui.py`)**
  - Schermata iniziale “full-screen” con due soli input: **Slug cliente** e **Nome cliente**; al completamento i valori vengono **bloccati** e appare la UI completa.
  - Header con **Cliente** e **Slug** e pulsante **Chiudi UI** (terminazione controllata del processo).
- **Tab “Configurazione”**
  - Editor del *mapping semantico* con **accordion per categoria** (Ambito, Descrizione, Esempi) e **Salva** puntuale per-voce.
  - Validazione e **salvataggio atomico** del mapping rivisto (`tags_reviewed.yaml`). Normalizzazione chiavi via **SSoT `to_kebab()`**.
- **Tab “Drive”**
  - Pulsante **Crea/aggiorna struttura** (cartella cliente su Drive, `raw/`, `contrattualistica/`, upload `config.yaml`).
  - Pulsante **Genera README in raw/** (emette `README.pdf` o `.txt` in ogni sotto-cartella `raw/`, con ambito/descrizione/esempi).
  - **Nuova sezione “Download contenuti su raw/”**: pulsante **Scarica PDF da Drive** nella struttura locale `raw/`. Al termine sblocca la tab *Semantica*. Messaggio guida operativo accanto al pulsante.
- **Tab “Semantica”**
  - Integrazione con `src/semantic_onboarding.py`:
    1) **Converti PDF in Markdown** (RAW → BOOK)
    2) **Arricchisci frontmatter** con vocabolario rivisto (`tags_reviewed.yaml`)
    3) **Genera/valida README & SUMMARY**
    4) **Preview Docker (HonKit)** avvio/stop con porta configurabile.
- **Runner Drive**
  - Nuova funzione `download_raw_from_drive(slug, ...)` con **path-safety** (`ensure_within_and_resolve`), **scritture atomiche**, sanitizzazione nomi file e **logging strutturato**.

### Changed
- **Gating dell’interfaccia**: la UI compare solo dopo lo sblocco iniziale (slug+cliente). La tab *Semantica* è nascosta finché non si completa il download dei PDF su `raw/`.
- **Streamlit re-run**: introdotto `_safe_streamlit_rerun()` che usa `st.rerun` (fallback su `experimental_rerun` se presente) per compatibilità con gli stub Pylance.
- **Pylance-compat nei runner Drive**: uso di `_require_callable(...)` per *narrowing* delle API opzionali (niente più `reportOptionalCall`), applicato a `get_drive_service`, `create_drive_folder`, `create_drive_structure_from_yaml`, `upload_config_to_drive_folder`.
- **Coerenza logging/redazione**: inizializzazione del flag via `compute_redact_flag`; propagazione `context.redact_logs` nei call-site.

### Fixed
- Eliminati warning Pylance su accessi opzionali (`.strip` su `None`) con `_norm_str`.
- Rimosso uso di `key=` non supportato su `st.expander` in alcune versioni; **key** univoche per i widget dove necessario.
- Messaggistica d’errore UI più chiara e resilienza ai fallimenti delle operazioni Drive.

### Security / Hardening
- **Path-safety** estesa ai download Drive e alle generazioni locali; guardie anti path traversal.
- **Scritture atomiche** per file generati/aggiornati (README, SUMMARY, Markdown convertiti).
- Redazione automatica di identificativi/sensibili nei log quando abilitata.

### Migration notes
- Impostare credenziali Google Drive e **`DRIVE_ID`** nell’ambiente.
- Flusso consigliato per nuovi clienti:
  1) Compilare **Slug** e **Nome cliente** (sblocco UI)
  2) Tab **Drive** → *Crea struttura* → *Genera README in raw/*
  3) **Scarica PDF** su `raw/` (sblocca tab **Semantica**)
  4) Tab **Semantica** → *Converti* → *Arricchisci* → *README & SUMMARY* → *(opz.) Preview Docker*
- Se esistono riferimenti a `st.experimental_rerun`, sostituirli con `_safe_streamlit_rerun()`.

---


## 1.5.0 fixing — 2025-08-28

### Added
- **Editing per-voce (UI Configurazione):** anteprima trasformata in *accordion*; ogni categoria ha campi propri (Ambito, Descrizione, Esempi) e pulsante **Salva** puntuale.
- **Pulsante “Chiudi UI”**: aggiunto in **sidebar** (sotto gli input di contesto) per terminare Streamlit dal terminale (SIGTERM, fallback sicuro).

### Changed
- **Nasconde `context` nella UI**: l’anteprima/edit non mostra più `context: {slug, client_name, created_at}`.
- **Requisiti d’avvio più stringenti:** per procedere servono **slug** e **nome cliente**.
- **Normalizzazione chiavi centralizzata:** introdotta `to_kebab()` in `src/config_ui/utils.py` e riuso in tutta la UI.
- **Logger coerente**: uso di `get_structured_logger(..., context=...)` anche nei runner, con redazione attiva via `compute_redact_flag`.

### Fixed
- **Bottone “Genera README in raw/”**: risolto crash (duplica logica/mancato import). Ora la generazione usa la `to_kebab()` centralizzata e funziona correttamente.
- **StreamlitDuplicateElementId**: assegnate **key univoche** a tutti i `button` e agli `expander`.
- **Allineamento runner Drive**: cleanup import e coerenza con le API `pipeline.drive_utils` (client, creazione struttura, upload config).

### Notes
- Patch **backward-compatible**; nessun breaking change.
- Confermate **path-safety** e **scritture atomiche**; rispetto della regola di **riuso** delle funzioni di pipeline.

---

## [Unreleased] — 2025-08-28

### Added
- **Nuova tab “Configurazione” (prima posizione)**: editor del *mapping semantico* basato su `config/default_semantic_mapping.yaml`, con:
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
- Flusso UI rivisto: l’editor delle cartelle *raw* è stato sostituito dall’**editor del mapping**; la struttura `raw/` viene ora derivata da `tags_reviewed.yaml`.
- La tab “Struttura (Editor — mapping)” è stata rinominata in **“Configurazione”** e portata al primo posto.
- Anteprima YAML del mapping trasformata in **expander apri/chiudi**.

### Fixed
- Estrazione O/V/M dal PDF: migliorata la rilevazione dei titoli, la delimitazione dei paragrafi e la pulizia (linee orizzontali, bullet isolati, numeri pagina).
- Serializzazione YAML di `vision.yaml` e `tags_reviewed.yaml`: struttura corretta e ordinata, con scrittura **atomica**.
- **NameError `re`** nel generatore di README: centralizzata la normalizzazione in `utils.to_kebab()` ed import sistemati.

### Removed
- Pulsante **“Imposta in config.yaml (raw)”** e selettori sorgente YAML/“sezione” non più necessari nel nuovo flusso.
- Editor ad albero della vecchia `cartelle_raw.yaml` dall’interfaccia.

### Internal
- Introdotto package **`src/config_ui/`** che separa la logica dall’UI:
  - `utils.py` (path-safety `ensure_within_and_resolve`, scritture atomiche `safe_write_text_compat`, `yaml_load/dump`, `to_kebab`, estrazione PDF);
  - `mapping_editor.py` (split/build/validate mapping, persistenza `tags_reviewed.yaml`, derivazione struttura `raw/`);
  - `vision_parser.py` (parser O/V/M e writer `vision.yaml`);
  - `drive_runner.py` (creazione struttura Drive e upload README).
- Aggiornati gli import per usare, ove disponibili, le API di `src/pipeline` (context/drive/upload/logging).
- **Hardening**: più controlli sui path, fallback su librerie PDF, gestione errori UI più chiara.
- Nota di compatibilità: il vecchio `src/config_onboarding.py` resta temporaneamente nel repo per continuità; verrà rimosso quando tutte le tab saranno migrate sui nuovi runner.

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
- **Preview porta configurabile**: `preview_port` ora può essere impostata via config/env (fallback a 4000).
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
  - Raccolta deterministica dei `.md` (no `.bak`) e cleanup temporanei più robusto.

### Fixed
- `gen_dummy_kb`: definizioni mancanti e ordine funzioni; ora build sandbox dummy completa senza `NameError`.
- Vari log message normalizzati (emoji opzionali, chiavi `extra` consistenti).

### Internal
- Orchestratori: separazione netta tra log “early” e log su file per sandbox.
- Maggiore adesione al contratto “solo `.md`” in `book/` con preflight e messaggi di errore esplicativi.
- Best-effort cleanup di container Docker in preview.

> **Note di migrazione**
> - Se usavi la preview con porta fissa, verifica `PREVIEW_PORT` (o config equivalente).
> - Per il push “force”, assicurati che `GIT_FORCE_ALLOWED_BRANCHES` includa il branch desiderato e passa `force_ack`.


---
## [1.5.0] — 2025-08-27 — Test & Documentazione

### Added
- **Nuova area test** `tests/` con suite PyTest:
  - `tests/test_contract_defaults.py` — verifica default CLI (es. `tag_onboarding`).
  - `tests/test_smoke_dummy_e2e.py` — smoke end-to-end su dataset dummy.
  - `tests/test_unit_book_guard.py` — contratto `book/` (solo `.md`, `.md.fp` ignorati).
  - `tests/test_unit_emit_tags_csv.py` — header e path POSIX in `tags_raw.csv`.
  - `tests/test_unit_tags_validator.py` — validazione `tags_reviewed.yaml` (ok/errori/duplicati).
- **`pytest.ini`** con `pythonpath=.` e `testpaths=tests` per import stabili su tutti gli OS.
- **Dataset utente dummy**: uso ufficiale di `py src/tools/gen_dummy_kb.py --slug dummy` per popolare `raw/` prima dei test.
- **Documentazione test dedicata**: `docs/test_suite.md` (lancio globale, singoli file, selezione per keyword, coverage, principi di isolamento).

### Changed
- **Default sorgente in `tag_onboarding` → `drive`** (con `--source local` come alternativa). Allineati i test di contratto.
- **Architettura**: aggiornata a **v1.5.0** in `docs/architecture.md` con sezione **tests/**, principi, piramide (unit/contract/smoke).
- **User Guide**: sezione “Test minimi” resa sintetica e rimandata a `docs/test_suite.md`.

### Fixed
- **Preflight `book/`**: chiarita e verificata la regola “solo `.md`” (ignora `.md.fp`) prima del push.
- Allineamento doc↔codice su flussi test e precondizioni (creazione utente dummy).

### Migrazione / Note operative
- Prima di eseguire i test:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy
  pytest -ra
  ---
  I test non richiedono credenziali reali (Drive/GitHub mockati o bypassati); l’E2E “manuale” è documentato in docs/test_suite.md.
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
- Hardening `semantic_onboarding`: gestione YAML e arricchimento frontmatter più robusti.

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
- **Documentazione interna**: sezione “SSoT scritture → `safe_write_text`” (I/O & Path-safety) con pattern minimi.
- **CI/QA**:
  - **Qodana**: configurazione consigliata (incluso controllo licenze/dependenze).
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
- **Dipendenze**: versioni aggiornate/pinnate per ripetibilità build (PyGithub, google-api-python-client, PyYAML, docker, spaCy, ecc.).

### Fixed
- Eliminato rischio di **path traversal** su write/delete grazie a `ensure_within` su tutti i punti critici.
- Affidabilità preview HonKit: readiness check sulla porta e gestione container duplicati.
- Coerenza logging: rimosse stampe dirette; solo **logging strutturato**.

### Security
- Scritture **atomiche** ed **idempotenti**; backup `.bak` dove opportuno.
- Redazione automatica dei segreti nei log; autenticazione GitHub via header HTTP (niente token in argv).

### Known Issues
- La cancellazione del repo via API/CLI richiede permessi **admin** sul repository; in assenza di permessi si riceve 401/403 dalla API o errore dalla CLI. Lo strumento gestisce e logga il fallback, ma non può bypassare i permessi.

### Migration Notes
- Se presenti vecchi file `.yml`, rinominarli in `.yaml` per allineamento e per i riferimenti nei workflow/strumenti.

---

## 1.3.0 - 2025-08-26

### Changed
- Refactor orchestratori (`pre_onboarding.py`, `tag_onboarding.py`, `semantic_onboarding.py`) per rispettare le linee guida Codex:
  - Estrazione sottoprocedure in funzioni pure, unit-testabili (<80 righe).
  - Uniformata la gestione di fallback/adapters → ora tutte le funzioni usano `(context, logger, **opts)`.
- Migliorata la pipeline di tagging (`tag_onboarding.py`):
  - Passaggio a scrittura **CSV streaming riga-per-riga** con commit atomico.
  - Validazione YAML più robusta e reporting strutturato.
- Aggiornato `semantic_onboarding.py`:
  - Arricchimento frontmatter ottimizzato tramite dizionario inverso dei sinonimi (O(1) lookup).
  - Consolidato l’uso di `ensure_readme_summary` come fallback centralizzato per README/SUMMARY.

### Documentation
- Aggiornati **Architecture.md**, **Developer Guide** e **Coding Rules** (v1.3.0):
  - Documentati i nuovi invarianti (funzioni pure negli orchestratori, streaming CSV, enrichment indicizzato).
  - Allineati esempi di logging ed error handling.
  - Esplicitato l’uso centralizzato degli adapter e delle firme coerenti.


## [1.2.2] fix generici e armonizzazione funzioni - 2025-08-26

### Added
- **Test suite di configurazione (pytest + Pydantic)**
  - `tests/test_config_utils.py`: copertura completa dei moduli `pipeline.config_utils` (Settings, client config, pre-onboarding, scritture atomiche, aggiornamento Drive IDs).
  - Fixture `conftest.py` consolidata: genera sempre una sandbox dummy pulita (`--overwrite`), forza ambiente UTF-8 e gestisce teardown automatico salvo `KEEP_DUMMY_KB=1`.
- **Refactor tool interattivo**
  - `src/tools/refactor_tool.py`: menu interattivo grafico (box ASCII) con 3 voci:
    1. 🔎 Trova (solo ricerca)
    2. ✏️ Trova & Sostituisci
    3. 📌 Cerca TODO/FIXME
  - Logging strutturato, dry-run con diff unificato leggibile, estendibile per futuri strumenti di refactor.

### Changed
- **`src/semantic/normalizer.py`**
  - Bug fix: `normalize_tags` ora ritorna correttamente `normed` (prima restituiva `""`).
  - Robustezza mapping: canonical/merge normalizzati a lowercase; coercizione prudente delle liste `synonyms`.
- **`src/tools/cleanup_repo.py`**
  - Flusso interattivo semplificato:
    - Conferma obbligatoria per la cancellazione locale di `output/timmy-kb-<slug>`, evidenziando che è irreversibile.
    - Solo se confermata, viene chiesto se eliminare anche il repo GitHub remoto (`gh repo delete`).
  - Uso coerente di `pipeline.logging_utils.redact_secrets` al posto di `env_utils`.

### Fixed
- Import path per `pipeline.*` nei tool (`gen_dummy_kb.py`, `cleanup_repo.py`, `refactor_tool.py`) resi consistenti con il bootstrap della cartella `src/`.
- Errori di compatibilità Windows (`ModuleNotFoundError: pipeline`) gestiti allineando sys.path a livello di progetto.

### Migration notes
- Per avviare i test singoli:
  ```bash
  pytest tests/test_config_utils.py -v
  pytest tests/test_dummy_pipeline.py -v


## [1.2.2] - 2025-08-25

### Added
- **Test suite dummy (pytest + Pydantic)**:
  - `tests/conftest.py`: fixture `dummy_kb` che rigenera la sandbox con `--overwrite` e valida i file chiave.
  - `tests/test_dummy_pipeline.py`: 4 test (struttura, coerenza CSV↔PDF, idempotenza semantic, assenza `contrattualistica/`).
- **Robustezza Windows nei test**: forzato `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` al lancio di `gen_dummy_kb.py`.

### Changed
- **`src/tools/gen_dummy_kb.py`** riscritto:
  - Genera la sandbox dummy completa da `config/*.yaml`.
  - Produce PDF dummy coerenti con `pdf_dummy.yaml`.
  - Copia `cartelle_raw.yaml` in `semantic/` e crea `semantic_mapping.yaml` con blocco `semantic_tagger` default.
  - Genera `tags_raw.csv` tramite i moduli semantic (`extract_semantic_candidates → normalize_tags → render_tags_csv`).
- **`src/tag_onboarding.py`**:
  - `_emit_tags_csv` ora produce path base-relative (`raw/...`) e colonne extra (`entities`, `keyphrases`, `score`, `sources`) per compatibilità futura.

### Fixed
- Crash su Windows (`UnicodeEncodeError` da emoji ✅, `NameError: json`).
- Path incoerenti tra CSV generati da strumenti diversi (ora formato unificato).
- Errore `relative_to` su `contrattualistica/` (cartella rimossa per design).

### Removed
- Generazione locale della cartella `contrattualistica/` nel dummy.

### Migration notes
- Rigenera la sandbox dummy:
  ```bash
  py src/tools/gen_dummy_kb.py --slug dummy --name "Cliente Dummy" --overwrite

## [1.2.1] Intermedio — 2025-08-25

> Release intermedia di consolidamento, applicata dopo le indicazioni di Codex e completata con refactor/test end-to-end sugli orchestratori. Focus su **pipeline core**; l’area semantica resta placeholder per la fase successiva.

### Changed
- **github_utils**
  - Estratto `_collect_md_files`, `_ensure_or_create_repo`, `_push_with_retry` e helper correlati per ridurre complessità di `push_output_to_github` (~400→ <150 righe).
  - Migliorata leggibilità e testabilità mantenendo lo stesso comportamento.
- **onboarding_full.py**
  - Orchestratore snellito: usa `_git_push` dedicato con error handling coerente.
  - Conferme interattive più chiare, non-interactive totalmente silente.
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
- L’area semantica (`semantic_extractor`, ecc.) resta ancora con built-in exceptions: da aggiornare in release successiva.


## [1.2.1] — 2025-08-24

> Hardening trasversale: SSoT per path-safety, redazione log centralizzata e orchestratori resi più coesi.

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
  - Conversione RAW→BOOK con gerarchie annidate; fingerprint per skip idempotente; nomi file sanificati; scritture atomiche e path-safety; generatori `SUMMARY.md`/`README.md`.
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

## [1.2.1] — 2025-08-24

> Release focalizzata su refactor, documentazione e split chiaro degli orchestratori.
> PR correlate: **PR-5** (Semantic Onboarding), **PR-6** (Docs v1.2.1).

### Added
- **Nuovo orchestratore**
  - `src/semantic_onboarding.py`: gestisce conversione RAW→BOOK, arricchimento frontmatter e preview Docker; nessun push GitHub.
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
- Spostato l’import `from __future__ import annotations` all’inizio dei file per evitare `SyntaxError`.
- Allineamento docstring e logica di gestione dei file tra moduli e orchestratori.

### Documentation
- Aggiornati a v1.2.1:
  - `docs/architecture.md`: riflesso lo split orchestratori (`semantic_onboarding` vs `onboarding_full`).
  - `docs/developer_guide.md`: bootstrap `ClientContext`, policy redazione, responsabilità orchestratori.
  - `docs/user_guide.md`: nuovo flusso operativo con `semantic_onboarding`.
  - `docs/coding_rules.md`: chiariti punti su atomicità e adapter.
  - `docs/policy_push.md`: rivista policy di pubblicazione.
  - `README.md` e `docs/index.md`: aggiornati esempi CLI e versioni.

### Migration notes
- Usare ora `semantic_onboarding.py` per conversione/enrichment/preview.
- `onboarding_full.py` va utilizzato solo per il push.
- Nei moduli, sostituire eventuali riferimenti a `file_utils.ensure_within` con `path_utils.ensure_within`.

---

## [1.2.0] — 2025-08-24

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
    - Fallback `context.redact_logs` se mancante → `compute_redact_flag()`.
  - `src/pre_onboarding.py`:
    - Risoluzione robusta `YAML_STRUCTURE_FILE`; messaggistica più chiara; uso coerente di `repo_root_dir` ed env helpers (no cambi funzionali in assenza di Drive).
- **ENV/Redaction**
  - `pipeline/env_utils.py`: `compute_redact_flag(env, log_level)` come single source of truth; orchestratori inizializzano `context.redact_logs` se non presente.
- **Demo tool**
  - `src/tools/gen_dummy_kb.py`: migrazione delle scritture a `safe_write_text` e verifiche path (dove applicabile).

### Fixed
- Allineata firma `ensure_readme_summary(...)` negli orchestratori (rimosso argomento non supportato `book_dir`).
- Log più robusti e non verbosi su assenza opzionale di PyYAML; migliorata resilienza del parsing frontmatter.

### Security / Hardening
- **Scritture atomiche di default** per file generati dalla pipeline → evita file troncati su interruzioni.
- **Path-safety**: `ensure_within`/`is_safe_subpath` applicati alle destinazioni sensibili.
- **Redazione log uniforme**: `compute_redact_flag` applicato/propagato agli adapter (preview) e agli orchestratori.

### Deprecated
- `is_log_redaction_enabled(context)` rimane per retro-compat ma **deprecato** in favore di `compute_redact_flag`.
- Uso diretto e sporadico di `os.environ` negli orchestratori → **usare** `env_utils.get_env_var/get_bool/get_int`.

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
  - Fallback inline → `adapters.content_fallbacks.ensure_readme_summary(context, logger)`.
  - Chiamate dirette a `pipeline.gitbook_preview.*` → `adapters.preview.start_preview/stop_preview`.
  - `Path.write_text(...)` → `safe_write_text(...)` (+ `ensure_within` o `is_safe_subpath`).
- Inizializzare `context.redact_logs` **subito dopo** `ClientContext.load(...)` se non presente:
  ```python
  from pipeline.env_utils import compute_redact_flag
  if not hasattr(context, "redact_logs"):
      context.redact_logs = compute_redact_flag(context.env, log_level="INFO")

## [1.1.0] — 2025-08-23 · Lancio baseline stabile

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
