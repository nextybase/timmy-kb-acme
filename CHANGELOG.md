# Changelog - Timmy-KB (Sintesi)

> Formato: **Keep a Changelog** e **SemVer**
> Nota: elenco condensato ai soli punti chiave che impattano UX, sicurezza, API pubbliche o qualita.

## [Unreleased]

### Pending
- Push intermedio: integrazione UI Vision e adapter OpenAI (vector stores/responses/chat) ancora in debug; modifiche non definitive, seguiranno fix per completare il flusso nuovo cliente.

## Import Contract unico + tools/ SSoT (breaking interna)
- Eliminato il doppio namespace: niente fallback `src.*`, healthcheck Vision senza sys.path hacking, dummy loader su `tools.dummy.*`, gen_vision_yaml come entrypoint tools/.
- Tooling consolidato: `tools/dummy/**` come package nativo, `tools/gen_dummy_kb.py` e `tools/gen_vision_yaml.py` sotto tools/, cleanup UI allineato a tools SSoT.
- Impatto: chi importava `src.tools.*` o manipolava `sys.path` deve migrare a `tools.*`/namespace top-level; nessun shim legacy.
- File principali: docs/import_contract.md, tools/gen_dummy_kb.py, tools/gen_vision_yaml.py, tools/dummy/*, tools/smoke/kb_healthcheck.py, src/ui/manage/cleanup.py, src/pipeline/capabilities/dummy_kb.py, tests/test_capabilities_dummy_kb.py, tests/test_cli_gen_vision_yaml.py.

### TODO (next session)
- Residui `src.*` fuori scope da ripulire: docs/import_contract.md (esempio), tests/semantic/test_manage_dedup.py, tests/test_gen_dummy_kb_import_safety.py (2 occorrenze).
- Comandi: `rg 'from\\s+src\\.|import\\s+src\\.|importlib\\.import_module\\(\"src\\.' -n` e `rg 'sys\\.path\\.(insert|append)' -n tools src`.
- Pulizia sys.path: rimuovere insert/append residui in tools (ci_dump_nav.py, forbid_control_chars.py, ci/oidc_probe.py, retriever_benchmark.py, dev/test_push_shallow.py, smoke/vision_alignment_check.py, smoke/smoke_semantic_from_drive.py, smoke/smoke_e2e.py, smoke/debug_vision_schema.py) e in src (ui/chrome.py, src/tools/gen_vision_yaml.py, src/tools/gen_dummy_kb.py, ui/pages/agents_network.py, timmy_kb/cli/semantic_onboarding.py, pipeline/paths.py); DoD: sys.path hacking solo in entrypoint motivati/documentati.
- DoD complessivo: zero import `src.*` nei moduli applicativi/test/docs; sys.path limitato agli entrypoint dichiarati; esempi/docs allineati all’Import Contract unico.

### Breaking
- Schema `config/config.yaml` riorganizzato in macro-sezioni `meta`, `ui`, `ai` (openai/vision), `pipeline` (retriever/raw_cache), `security`, `integrations`, `ops`, `finance`; aggiornare eventuali tool esterni che leggevano le chiavi legacy.
- Timmy KB Coder è stato rimosso insieme ai test/strumenti che si appoggiavano al DB globale `.timmykb`; il workflow 1.0 ora è totalmente slug-based e la documentazione riflette il flusso supportato.

### Changed
- Changelog: eliminata la duplicazione (il changelog canonico e' `CHANGELOG.md` in root).
- Documentazione: rimossi riferimenti al changelog duplicato; i riferimenti puntano al changelog canonico in root.
Delivery anchor: CHAIN_ID=PC-VERIFY-001 | SHA=086807675cea8e71b969a7296a1a01ab13071d9f | Date=2025-12-27
- Dev tooling: gli script legacy sono stati consolidati in `tools/` (`tools/smoke` per gli smoke); aggiornati riferimenti in CI (`.github/workflows/ci.yaml`), pre-commit (`.pre-commit-config.yaml`), `makefile` e documentazione (`docs/*`, `README`).
- Indexing: indicizzazione parziale su mismatch `embeddings != contents` (troncamento al minimo comune) con telemetria aggiornata (`semantic.index.mismatched_embeddings`, `semantic.index.embedding_pruned`, `semantic.index.skips`).
- Telemetria phase_scope: i rami "no files" e "no contents" ora emettono sempre `artifact_count=0` e chiusura `semantic.index.done`.
- File I/O: `safe_append_text` passa ad append diretto O(1) per record, mantenendo lock e fsync opzionale.
- Responses API: normalizzazione metadata in `run_json_model`/`run_text_model` (valori sempre stringa) e fallback senza `response_format` quando l’SDK non lo supporta.
- Path-safety: ingest/estrattori ora leggono PDF/Markdown solo tramite guardie `ensure_within_and_resolve` + handle sicuri; self-check usa `safe_write_text`.
- Retriever: logging armonizzato e short-circuit su embedding piatti `list[float]` con metriche `{total, embed, fetch, score_sort}` e contatori `coerce`; hardening su errori embedding (log `retriever.query.embed_failed` + ritorno `[]`) e check del budget di latenza prima di embedding/fetch.
- CLI pre-onboarding: dry-run e gestione errori loggano eventi strutturati (`cli.pre_onboarding.*`) con extra coerenti.
- Timmy KB Coder: RAG ora richiede `OPENAI_API_KEY` e non usa piu fallback `OPENAI_API_KEY_CODEX`; se la chiave manca il RAG si disabilita in modo esplicito con `coder.rag.disabled`, rendendo piu evidente la dipendenza dalla configurazione 1.0.
- Semantic index: eventi `semantic.index.embedding_pruned` arricchiti (cause mismatch/empty e contatori completi) e rimossi i messaggi testuali duplicati.
- Semantic vocab loader: slug derivato da `REPO_NAME_PREFIX` e logging uniformato (`semantic.vocab.db_missing`, `semantic.vocab.db_empty`, `semantic.vocab.loaded`).
- Retriever cosine: ora usa generatori con `itertools.tee`, evitando copie in memoria e mantenendo scaling numerico controllato.
- Vision & KGraph: chiamate Responses API ora modello-only (assistant_id solo per logging/metadata), istruzioni spostate in messaggio system e payload messaggi in formato `input_text`; `TagKgInput` adegua `to_messages` al formato Responses.
- Documentazione: `docs/developer/developer_guide.md` e `docs/developer/coding_rule.md` descrivono l'uso corretto dell'SDK OpenAI interno (model-only, input_text/output_text, assistant come SSoT di config, pattern di risoluzione modello) e il divieto dei pattern legacy thread/run.
- Debug tooling: `kg_debug_dummy` gestisce run offline con output sintetico e riduce eccezioni inattese; logging KGraph include dump raw in caso di JSON non valido.

### Status
- Prompt Chain e governance HiTL (ruoli, gate, template) completate e operative; fonti canoniche: `system/specs/promptchain_spec.md` e `.codex/CLOSURE_AND_SKEPTIC.md`.

### Added
- Test di integrazione su indexing (mismatch parziale, invariance ranking, metriche coerce, casi artifacts=0).
- Dummy tooling: writer vision YAML completo sempre applicato a fine orchestrazione, CLI di diagnostica sezioni Vision.
- Test per il retriever su vettori lunghi/estremi e ranking deterministico con candidati numerosi.
- Test per il vocabolario semantico con CapLog sui nuovi eventi e scenario `streamlit` assente in Timmy KB Coder.
- Test UI di parita firma wrapper `safe_write_text` UI vs backend; TypedDict `SearchResult` per l'output di `retriever.search`.
- Documentazione aggiornata su cache frontmatter LRU bounded e hardening retriever (developer guide + runbook).
- Test settings: copertura delle nuove sezioni ai (`prototimmy`, `planner_assistant`, `ocp_executor`, `kgraph`) e risoluzione modello KGraph; fixture Vision aggiornate alle nuove instructions.

### Compatibility
- Nessun breaking change; API pubbliche invariate, schema DB stabile.

### Fixed
- `src/tools/gen_dummy_kb.py`: import lazy e path workspace allineato a `output/timmy-kb-<slug>`.
- Dummy vision: uso coerente di `safe_write_*` e sovrascrittura del placeholder YAML con testo completo per evitare validator mancanti.
- PDF discovery case-insensitive (.pdf/.PDF) in API, content_utils e tags_extractor.
- Cache frontmatter Markdown ora LRU bounded (evita crescita infinita su run lunghi).
- Vision: estrazione PDF passa a pypdf/PyPDF2 (fallback) mantenendo codici di errore invariati; chiamate Responses API evitano keyword non supportate e sollevano ConfigError coerenti.

## [Unreleased] — Prompt Orchestration & Agency Design

### Added
- Cartella `instructions/` come SSoT temporaneo di design e orchestrazione.
- Modello di agency formale (Timmy/ProtoTimmy, Domain Gatekeepers, Control Plane, micro-agent).
- Registry di Intent/Action con whitelist, `allowed_actions` e governance HiTL.
- Prompt Chain lifecycle con fasi, HiTL, regole di linearità e state machine.
- Invarianti e failure modes minimi documentati (registry invariants, failure modes, stop/HiTL).

### Changed
- Chiarito il ruolo di OCP come Control Plane operativo, distinto da agenti cognitivi.
- Netta separazione tra decisione (Timmy), validazione (Domain Gatekeepers/OCP) ed esecuzione (micro-agent).
- Rafforzate le regole HiTL e i blocchi mandatory nel registry e nella timeline.

### Design Decisions
- Adozione di design-first prompt architecture e documenti come contratti verificabili.
- Separazione WHAT/HOW per prevenire codice intrecciato a specifiche.
- Documenti esistenti allineati a tabelle, invarianti e failure mode, non a narrazioni.

### Backlog (post-kernel)
- Consolidare l’adozione del contratto workspace in `instructions/05_pipeline_workspace_state_machine.md` e monitorare i gap residui.
- Verificare che `instructions/06_promptchain_workspace_mapping.md` e `instructions/07_gate_checklists.md` guidino i gate Evi/Skeptic e mantengano l’OCP-plane coerente.
- Mantenere centrata la formalizzazione dell’Evidence/Retry/QA Gate in `instructions/08_gate_evidence_and_retry_contract.md` durante la fine dell’alpha.

## [1.9.7] - 2025-09-28

### Added
- UI: editing congiunto di `semantic/semantic_mapping.yaml` e `semantic/cartelle_raw.yaml` con text area dedicate e pulsante "Annulla modifiche".
- UI: pulsante "Apri workspace" in sidebar con gating su slug valido e presenza YAML.
- UX: messaggi di successo/errore piu chiari e sezione informativa con elenco correzioni automatiche.

### Changed
- `semantic/vision_provision.py`: provisioning piu robusto con fallback a Chat Completions, normalizzazione dati e coercizione minima del context.
- `src/ai/client_factory.py`: creazione client OpenAI piu tollerante con fallback `http_client` e header `OpenAI-Beta: assistants=v2` best effort.
- UI landing: salvataggio YAML atomico e gestione stato sessione per ripristino contenuti.

---

*Per lo storico completo delle versioni precedenti consultare gli archivi del repository.*
