# Artifacts Policy (Core vs Service) - v1.0 Beta

## Scope & intent
Questa policy definisce cosa si intende per "artefatto" nel sistema Timmy-KB
e stabilisce regole normative su determinismo, fallback, dipendenze opzionali
e tracciabilità.

Questa policy è normativa (SSoT). In caso di conflitto con `docs/` o `system/`,
prevale questa.

## Definitions

### Artifact
Un artefatto è un output materiale prodotto da pipeline/UI/CLI (file, snapshot, indice,
ledger entry, report, ecc.) che può essere consumato da persone o processi automatici.

### Core Artifact (Epistemic Envelope output)
È un artefatto:
- richiesto o implicato dalle fasi della foundation pipeline;
- consumato da step successivi come input deterministico;
- parte della catena di evidenze (audit/lineage/ledger) o della base KB.

Esempi tipici (non esaustivi): `normalized/`, `book/README.md`, `book/SUMMARY.md`,
`semantic/tags.db`, snapshot KG, ledger/lineage.

### Service Artifact (Support / UX / Tooling)
È un artefatto:
- utile per UX, diagnostica, packaging, preview o supporto operativo;
- non è prerequisito per la pipeline deterministica;
- non deve cambiare la semantica dei core artifacts né sostituirli.

Esempi: zip log, workspace summary, cache in-memory, preview, report "di servizio".

### Conditional CORE artifact
Alcuni artefatti sono CORE **solo** quando una capability o uno stage della pipeline è attivo.
In questi casi:
- se la condizione è soddisfatta e l'artefatto manca → FAIL-FAST (senza fallback);
- se la condizione non è soddisfatta → l'artefatto **non è richiesto** e **non deve** essere prodotto implicitamente.
“Conditional CORE” non implica comportamenti best-effort quando la condizione è attiva; la capacità deve governare la presenza dell’artefatto.

### Core-Gate Artifact (Gate prerequisite)
È un artefatto:
- usato come prerequisito normativo per sbloccare la produzione di core artifacts;
- può vivere in `logs/`, ma è trattato come CORE ai fini dei gate;
- non introduce fallback o downgrade: se manca, il gate blocca.

## Beta invariants (strict)

### 1) Core artifacts MUST be deterministic
Un core artifact deve essere riproducibile a parità di input e configurazione.
Sono vietate dipendenze "best effort" o output alternativi che cambiano formato/semantica.

### 2) No silent downgrade for core artifacts
Se un core artifact richiede una dipendenza opzionale o una capability non disponibile,
il comportamento ammesso è:
- STOP con errore tipizzato (fail-fast), e
- evento tracciato (log strutturato + ledger entry se applicabile).

È vietato sostituire automaticamente un core artifact con una variante "comunque ok"
(es. generare `.txt` al posto di `.pdf` o cambiare formato senza esplicita autorizzazione).

### 3) Service artifacts MAY be best-effort (but must not masquerade)
Per i service artifacts è ammesso best-effort o fallback, a queste condizioni:
- non altera o rimpiazza core artifacts;
- è esplicito (log strutturato) e identificabile come "SERVICE_ONLY";
- non introduce dipendenza implicita in step successivi.

### 4) Optional dependencies policy
Le dipendenze opzionali sono ammesse solo se:
- abilitate tramite capability-gating (config/extra esplicito), e
- il loro fallimento non produce "successo apparente" su core artifacts.

### 5) Time-based state and caching policy
Qualsiasi cache time-based (TTL, timestamp wall-clock) è considerata *entropia operativa*.
È ammessa solo come supporto (service behavior) se:
- non influenza decisioni, ordering o selezione degli input della pipeline;
- non viene usata come condizione per produrre o saltare core artifacts;
- è confinata a performance/UX e non modifica artefatti persistenti.

Se una cache time-based viene "prewarmata" automaticamente, deve restare
non osservabile ai fini della semantica e non può diventare requisito implicito.

### 6) QA evidence è CORE-GATE (README/SUMMARY)
`logs/qa_passed.json` è un **core-gate artifact**: è prerequisito normativo
per generare i core artifacts `book/README.md` e `book/SUMMARY.md`.
La sua assenza o invalidità blocca il gate.

Il campo `timestamp` può esistere come telemetria, ma **non** deve entrare
nel confronto deterministico/manifest dei core artifacts.

## Classification rule (practical)
Quando un modulo produce un file:
- se finisce in directory della pipeline (workspace layout) o viene citato come prerequisito:
  trattalo come CORE (o CORE-GATE se è un prerequisito di gate).
- se è diagnostica, packaging, preview, export UI:
  trattalo come SERVICE.

In dubbio: CORE.

## Compliance hooks (normative expectations)
- I Gatekeepers e i micro-agent (Work Order Envelope) devono trattare come violazione
  qualsiasi produzione "alternativa" non autorizzata di core artifacts.
- Un "OK" non è valido se i core artifacts attesi non sono stati prodotti nella forma prevista.

## Allowed exceptions (strictness/caching)
Nessuna eccezione attiva (2026-01-25).

Qualsiasi uso in core di:
- `sanitize_filename(..., strict=False)` o `allow_fallback=True`
- `iter_safe_pdfs(..., use_cache=True)` o TTL cache per selezione/ordering

deve essere elencato qui con motivazione e test dedicato.

## Runtime Rules
- Core artifacts devono essere prodotti deterministically.
- L’assenza o la corruzione di un core artifact blocca la pipeline (fail-fast) e deve essere tracciata.
- Il fallback silenzioso o il downgrade non sono ammessi.
- Per i conditional CORE artifacts:
  - “Skip with warning” non è un comportamento valido finché la condizione è attiva.
  - La condizione deve essere esplicita e verificabile (niente euristiche di fallback).

## Notes
- Gli artefatti workspace vengono validati in base alla configurazione delle capability attive.
- Le artifact richieste da capability inattive non devono essere forzate.
- Chiarimento: la presenza di un conditional CORE artifact non attiva una capability; sono le capability che attivano gli artefatti.

## Appendice A - Inventario runtime (src/)
Metodo: scansione statica dei producer in `src/` (runtime UI/CLI/pipeline). Esclusi `tools/` e `tests/`.
Include scritture file/DB/log/zip individuate tramite `safe_write_*`, sqlite3, handler log e zip.
Limite: scritture dinamiche via plugin/ENV potrebbero non risultare dalla scansione.

Legenda: CORE = artefatto deterministico della pipeline; CORE-GATE = prerequisito normativo per sbloccare core; SERVICE = supporto/UX/diagnostica.

### A.1 Workspace & config
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/workspace_bootstrap.py:bootstrap_client_workspace`<br>`bootstrap_dummy_workspace`<br>`migrate_or_repair_workspace` | `output/timmy-kb-<slug>/config/config.yaml`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | YAML + Markdown | `pipeline.context`, `WorkspaceLayout`, UI/CLI | CORE | Template `config/config.yaml` | No (fail-fast se template assente) |
| `src/pipeline/workspace_bootstrap.py:bootstrap_client_workspace`<br>`bootstrap_dummy_workspace`<br>`migrate_or_repair_workspace` | `output/timmy-kb-<slug>/{raw,normalized,semantic,book,logs,config}/` | Directory layout | `WorkspaceLayout`, UI/CLI | CORE | FS permissions | No (fail-fast su errori FS) |
| `src/pipeline/context.py:_ensure_config` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | `Settings.load`, UI/CLI | CORE | Template `config/config.yaml` | No (fail-fast se template assente) |
| `src/pipeline/config_utils.py:write_client_config_file`<br>`merge_client_config_from_template`<br>`update_config_with_drive_ids` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | Pipeline/CLI/UI | CORE | PyYAML, path-safety | No (fail-fast su errori) |
| `src/pipeline/config_utils.py:write_client_config_file`<br>`merge_client_config_from_template` | `output/timmy-kb-<slug>/config/config.yaml.bak` | Backup YAML | Operatore (rollback) | SERVICE | FS copy | No (se backup fallisce, errore) |
| `src/ui/config_store.py:_save_repo_config`<br>`_save_config`<br>`src/ui/pages/configurazione.py:_write_config` | `config/config.yaml` | YAML | `Settings.load`, UI/CLI | CORE | PyYAML | No (fail-fast su errori) |
| `src/ui/pages/new_client.py:_mirror_repo_config_into_client`<br>`src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/config.yaml` | YAML | Pipeline/CLI/UI | CORE | PyYAML, template config | No (fail-fast su errori) |
| `src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/assistant_vision_system_prompt.txt` | TXT prompt | Vision provisioning | CORE (cond.) | Sorgente `config/assistant_vision_system_prompt.txt` | Condition:<br>- richiesto **solo** se la capability Vision è attiva (Vision assistant in strict/structured output);<br>Behavior:<br>- se Vision è attiva e il prompt manca o è vuoto → FAIL-FAST (ConfigError / PipelineError).<br>- se Vision è inattiva → l’artefatto non è richiesto e non viene sintetizzato implicitamente.;<br>Note:<br>- la versione workspace (se presente) è un SERVICE artifact e non deve influire sul runtime quando Vision è inattiva. |
| `src/ui/pages/new_client.py`<br>`src/timmy_kb/cli/pre_onboarding.py:ensure_local_workspace_for_ui` | `output/timmy-kb-<slug>/config/VisionStatement.pdf` | PDF | `visionstatement.yaml` + mapping | CORE (cond.) | Upload utente | No (mancanza blocca Vision) |
| `src/ui/fine_tuning/vision_modal.py:_ensure_workspace_pdf` | `output/timmy-kb-<slug>/config/VisionStatement.pdf` | PDF | UI Vision modal | CORE (cond.) | Nessuna | No (mancanza blocca Vision) |

### A.2 Vision & mapping
Nota: `visionstatement.yaml` esiste solo nel workspace (`output/timmy-kb-<slug>/config/visionstatement.yaml`); nel repo root resta solo `config/vision_template.yaml` come contract.
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/core.py:compile_document_to_vision_yaml` | `output/timmy-kb-<slug>/config/visionstatement.yaml` | YAML (vision) | `semantic.vision_provision`, `pipeline.vision_runner`, UI Vision | CORE | PyYAML, estrazione PDF | No (fail-fast su errore) |
| `src/semantic/vision_provision.py:_persist_outputs` | `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml` | YAML mapping | Tagging/Semantica | CORE | Vision responses, schema valido | No |
| `src/ui/components/mapping_editor.py:save_semantic_mapping`<br>`src/ui/components/yaml_editors.py:_write_yaml_text` | `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml` | YAML mapping | Tagging/Semantica | CORE | UI + YAML valido | No |
| `src/ui/components/mapping_editor.py:write_raw_structure_yaml` | `output/timmy-kb-<slug>/semantic/_raw_from_mapping.yaml` | YAML (struttura RAW) | Drive runner (opz.) | SERVICE | Mapping presente | No |
| `src/semantic/vision_provision.py:_write_audit_line` | `output/timmy-kb-<slug>/logs/semantic.vision.log` | JSONL audit log | Diagnostica | SERVICE | FS write | No |
| `src/ai/responses.py:_diagnose_json_schema_format` | `output/debug/vision_schema_sent.json` | JSON debug | Diagnostica | SERVICE | Debug locale | Yes (best-effort, warning su fallimento) |

### A.3 Raw ingest
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/drive/download.py:download_drive_pdfs_to_local`<br>`src/pipeline/ingest/provider.py:DriveIngestProvider.ingest_raw` | `output/timmy-kb-<slug>/raw/<categoria>/<file>.pdf` | PDF (raw) | Raw ingest | CORE (cond.) | Drive capability + googleapiclient | No (fail-fast) |
| `src/semantic/tags_extractor.py:copy_local_pdfs_to_raw`<br>`src/pipeline/ingest/provider.py:LocalIngestProvider.ingest_raw` | `output/timmy-kb-<slug>/raw/<rel>.pdf` | PDF (raw) | Raw ingest | CORE (cond.) | Local FS | No |
| `src/pipeline/vision_runner.py:_materialize_raw_structure` | `output/timmy-kb-<slug>/raw/<area>/` | Directory structure | Drive/local ingest | CORE (cond.) | `semantic/semantic_mapping.yaml` | No (fail-fast se mapping invalido) |
| `src/pipeline/raw_transform_service.py:PdfTextTransformService.transform` | `output/timmy-kb-<slug>/normalized/<rel>.md` | Markdown normalizzato | Tagging/Semantica | CORE | `nlp.nlp_keywords.extract_text_from_pdf` | No (fail-fast se dipendenza assente) |
| `src/pipeline/normalized_index.py:write_index` | `output/timmy-kb-<slug>/normalized/INDEX.json` | JSON index | Raw ingest gating | CORE | JSON serialization | No |

### A.4 Tagging & vocabolario
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/auto_tagger.py:render_tags_csv` | `output/timmy-kb-<slug>/semantic/tags_raw.csv` | CSV suggerimenti | Revisione HiTL | CORE | Mapping + normalized | No |
| `src/ui/manage/tags.py:handle_tags_raw_save` | `output/timmy-kb-<slug>/semantic/tags_raw.csv` | CSV | Revisione HiTL | CORE | UI editor | No |
| `src/semantic/review_writer.py:write_review_stub` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML revisione | Tagging/DB | CORE | CSV valido | No |
| `src/semantic/tags_io.py:write_tags_reviewed_from_nlp_db` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML revisione | Tagging/DB | CORE | tags.db presente | No |
| `src/ui/manage/tags.py:open_tags_editor_modal`<br>`src/ui/components/yaml_editors.py:_write_yaml_text` | `output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | YAML revisione | Tagging/DB | CORE | UI editor | No |
| `src/storage/tags_store.py:ensure_schema_v2`<br>`get_conn`/`upsert_*` | `output/timmy-kb-<slug>/semantic/tags.db` | SQLite DB | Semantica/frontmatter | CORE | sqlite3 | No (fail-fast su legacy) |
| `src/semantic/tags_io.py:write_tagging_readme` | `output/timmy-kb-<slug>/semantic/README_TAGGING.md` | Markdown guida | UX tagging | SERVICE | FS write | No |
| `src/semantic/tags_validator.py:write_validation_report` | `output/timmy-kb-<slug>/semantic/<report>.json` | JSON report | Diagnostica | SERVICE | JSON serialization | No |
| `src/timmy_kb/cli/kg_builder.py:_save_outputs`<br>`src/ui/services/tag_kg_builder.py:run_tag_kg_builder` | `output/timmy-kb-<slug>/semantic/kg.tags.json`<br>`output/timmy-kb-<slug>/semantic/kg.tags.md` | JSON + Markdown (KG) | Review/diagnostica | SERVICE | OpenAI assistant + `semantic/tags_raw.json` | Yes (skip se `tags_raw.json` assente a monte) |

### A.5 Semantic onboarding & book
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/semantic/convert_service.py:_write_markdown_for_normalized`<br>`src/pipeline/content_utils.py:convert_files_to_structured_markdown` | `output/timmy-kb-<slug>/book/<rel>.md` | Markdown book | Preview/KB | CORE | normalized/*.md | No |
| `src/semantic/frontmatter_service.py:write_readme`<br>`src/pipeline/content_utils.py:generate_readme_markdown` | `output/timmy-kb-<slug>/book/README.md` | Markdown | Preview/KB | CORE | mapping + contenuti (+ layout_proposal.yaml opz.) | No |
| `src/semantic/frontmatter_service.py:write_summary`<br>`src/pipeline/content_utils.py:generate_summary_markdown` | `output/timmy-kb-<slug>/book/SUMMARY.md` | Markdown | Preview/KB | CORE | book/*.md | No |
| `src/semantic/frontmatter_service.py:_maybe_write_layout_proposal` | `output/timmy-kb-<slug>/semantic/layout_proposal.yaml` | YAML proposta layout | Diagnostica/UX | SERVICE | Vision text | Yes (best-effort, log only) |
| `src/semantic/frontmatter_service.py:_write_layout_summary` | `output/timmy-kb-<slug>/book/layout_summary.md` | Markdown | UX/preview | SERVICE | `semantic/layout_proposal.yaml` | Yes (skip se layout assente) |

### A.6 DB, ledger, preview
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/kb_db.py:init_db`/`insert_chunks` | `output/timmy-kb-<slug>/semantic/kb.sqlite` | SQLite embeddings | Retriever | CORE (cond.) | sqlite3, embeddings client | No |
| `src/storage/decision_ledger.py:open_ledger`/`_init_schema` | `output/timmy-kb-<slug>/config/ledger.db` | SQLite ledger | Audit/lineage | CORE | sqlite3 | No |
| `src/pipeline/honkit_preview.py:ensure_book_json` | `output/timmy-kb-<slug>/book/book.json` | JSON config | Preview | SERVICE | HonKit preview | Yes (idempotente, solo se mancante) |
| `src/pipeline/honkit_preview.py:ensure_package_json` | `output/timmy-kb-<slug>/book/package.json` | JSON config | Preview | SERVICE | HonKit preview | Yes (idempotente, solo se mancante) |

### A.7 Log, diagnostica, stato UI
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/logging_utils.py:get_structured_logger` | `output/timmy-kb-<slug>/logs/onboarding.log`<br>`.timmy_kb/logs/ui.log` | Log file | Operatore/diagnostica | SERVICE | FS write | Yes (console fallback) |
| `src/ui/pages/preview.py:_write_stub_log` | `logs/preview/<slug>.log` (o `PREVIEW_LOG_DIR`) | Log stub | UX preview | SERVICE | FS write | Yes (stub only) |
| `src/pipeline/qa_evidence.py:write_qa_evidence` | `output/timmy-kb-<slug>/logs/qa_passed.json` | JSON QA | QA gate → README/SUMMARY | CORE-GATE | JSON serialization | No |
| `src/ui/gating.py:write_gate_capability_manifest` | `output/timmy-kb-<slug>/logs/gate_capabilities.json` | JSON capability | UI gating | SERVICE | FS write | No |
| `src/explainability/serialization.py:safe_write_manifest`<br>`src/timmy_kb/cli/retriever_manifest.py:_write_manifest_if_configured` | `output/timmy-kb-<slug>/semantic/explainability/<response_id>.json` (base dir configurata) | JSON manifest | Audit/lineage | SERVICE | retriever + `explain_base_dir` configurato | Yes (skip se base dir non impostata) |
| `src/ui/utils/diagnostics.py:build_logs_archive` | ZIP bytes (in-memory) + `workspace_summary.json` | ZIP report | Supporto | SERVICE | zipfile | Yes (best-effort, None su failure) |
| `src/pipeline/system_self_check.py:_check_output_writable` | `output/.selfcheck_tmp` | Probe file | Self-check | SERVICE | FS write | Yes (cleanup best-effort) |
| `src/pipeline/observability_config.py:update_observability_settings` | `~/.timmy_kb/observability.yaml` | YAML prefs | UI observability | SERVICE | PyYAML | No |
| `src/ui/clients_store.py:_save_registry` | `clients_db/clients.yaml` | YAML registry | UI/CLI | SERVICE | PyYAML | No |
| `src/ui/utils/slug.py:_save_persisted` | `clients_db/ui_state.json` | JSON state | UI | SERVICE | FS write | Yes (errori suppressi) |
| `src/ui/semantic_progress.py:_write_progress` | `clients_db/semantic_progress/<slug>.json` | JSON state | UI gating | SERVICE | JSON serialization | No |
| `src/pipeline/ownership.py:ensure_ownership_file` | `clients_db/clients/<slug>/ownership.yaml` | YAML ownership | UI/ACL | SERVICE | PyYAML | No |
| `src/ui/pages/agents_network.py:_save_agents_sections` | `AGENTS.md` / `system/ops/agents_index.md` | Markdown governance | Governance UI | SERVICE | FS write | No |

### A.8 Drive (remote)
| Producer (file:funzione) | Path target | Tipo output | Consumer | Class | Dipendenze/capability | Fallback |
| --- | --- | --- | --- | --- | --- | --- |
| `src/pipeline/drive/upload.py:create_drive_folder` | `Drive/<client_folder>/` | Cartella Drive | Provisioning/Drive ingest | CORE (cond.) | Drive API + creds | No (fail-fast) |
| `src/pipeline/drive/upload.py:create_drive_minimal_structure` | `Drive/<client_folder>/{raw,contrattualistica}/` | Cartelle Drive | Ingest/contratti | CORE (cond.) | Drive API + creds | No |
| `src/pipeline/drive/upload.py:upload_config_to_drive_folder` | `Drive/<client_folder>/config.yaml` | YAML (Drive) | Sync/operatore | CORE (cond.) | Drive API + creds | No |
| `src/pipeline/drive/upload.py:create_drive_structure_from_names` | `Drive/<client_folder>/raw/<area>/` | Cartelle Drive | Raw ingest (Drive) | CORE (cond.) | Drive API + mapping | No (fail-fast se mapping invalido) |
| `src/ui/services/drive_runner.py:emit_readmes_for_raw` | `Drive/<client_folder>/raw/<area>/README.pdf`<br>`Drive/<client_folder>/raw/<area>/README.txt` | PDF/TXT | UX/operatore | SERVICE | ReportLab (opz.) | Yes (SERVICE_ONLY + structured log + Drive appProperties) |

## Appendice B - CORE artifacts attesi per fase
| Fase (runbook) | CORE artifacts attesi | Note/condizioni |
| --- | --- | --- |
| pre_onboarding | `output/timmy-kb-<slug>/config/config.yaml`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | Bootstrap idempotente; se Vision attiva: `output/timmy-kb-<slug>/config/VisionStatement.pdf`, `output/timmy-kb-<slug>/config/visionstatement.yaml`, `output/timmy-kb-<slug>/semantic/semantic_mapping.yaml`. |
| raw_ingest | `output/timmy-kb-<slug>/normalized/<rel>.md`<br>`output/timmy-kb-<slug>/normalized/INDEX.json` | Qualsiasi file `OK` in INDEX deve esistere su disco. |
| tag_onboarding | `output/timmy-kb-<slug>/semantic/tags_raw.csv`<br>`output/timmy-kb-<slug>/semantic/tags_reviewed.yaml` | `tags.db` è CORE quando la revisione viene applicata (fase di sync/abilitazione semantica). |
| semantic_onboarding | `output/timmy-kb-<slug>/book/<rel>.md`<br>`output/timmy-kb-<slug>/book/README.md`<br>`output/timmy-kb-<slug>/book/SUMMARY.md` | Enrichment richiede `semantic/tags.db` presente e valido. `logs/qa_passed.json` è prerequisito CORE-GATE per README/SUMMARY. |
| honkit_preview | Nessun CORE artifact nuovo | Preview = SERVICE-only (`book.json`, `package.json`, log preview). |
| cross-phase (ledger) | `output/timmy-kb-<slug>/config/ledger.db` | CORE evidence: se il ledger è attivo, deve essere scritto in modo deterministico. |
