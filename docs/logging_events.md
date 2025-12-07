# Eventi di logging canonici (estratto)

Questi eventi sono emessi con `logger.info/warning` e includono campi `extra` standardizzati per facilitare la raccolta e l'analisi.

- `pipeline.content.skip_symlink` extra: `slug`, `file_path`
  - Un PDF e' stato ignorato perche' symlink.
- `pipeline.content.skip_unsafe` extra: `slug`, `file_path`, `error`
  - Un percorso PDF e' stato scartato perche' fuori perimetro/non sicuro.
- `semantic.convert_markdown.done` extra: `slug`, `ms`, `artifacts={content_files}`
  - Conversione completata con conteggio dei Markdown di contenuto; emesso una sola volta.
- `semantic.index.db_inserted` extra: `slug`, `scope`, `path`, `version`, `rows`, `inserted`
  - Riepilogo inserimenti a batch nel DB (idempotente).
- `kb_db.fetch.invalid_meta_json` extra: `slug`, `scope`
  - Record con `meta_json` non valido; il valore viene ignorato.
- `kb_db.fetch.invalid_embedding_json` extra: `slug`, `scope`
  - Record con `embedding_json` non valido; l'embedding viene ignorato.
- `ui.gating.sem_hidden` extra: `slug`, `raw_ready`
  - La pagina Semantica e' stata nascosta perche' `raw/` non contiene PDF validi per lo slug attivo.
- `cli.pre_onboarding.drive.folder_created` extra: `client_folder_id` (mascherato)
  - Cartella cliente creata su Drive.
- `cli.pre_onboarding.drive.structure_created` extra: `config_tail`, `created_map_masked`
  - Struttura minima Drive (raw/contrattualistica/config) creata.
- `cli.pre_onboarding.workspace.created` extra: `slug`, `base`, `config`
  - Workspace locale predisposto (cartelle + config YAML scritto).
- `cli.pre_onboarding.drive.preflight` extra: `SERVICE_ACCOUNT_FILE` (mask), `DRIVE_ID` (mask)
  - Pre-flight Drive prima della creazione struttura remota.
- `cli.tag_onboarding.scan_completed` extra: `folders`, `documents`
  - Indicizzazione RAW -> DB completata.
- `cli.tag_onboarding.nlp_executor_configured` extra: `workers`, `batch_size`
  - Executor NLP configurato per run parallela.
- `cli.tag_onboarding.nlp_completed` extra: stats NLP (`terms`, `doc_terms`, `workers`, ...)
  - Pipeline NLP completata.
- `ui.startup` extra: `version`, `streamlit_version`, `port`, `mode`
  - Avvio dell'app Streamlit, utile per distinguere i run UI.
- `pipeline.processing.progress` extra: `slug`, `scope`, `processed`, `chunks`
  - Checkpoint di avanzamento batch ogni N elementi.
- `openai.api_calls` extra: `model`, `count`, `latency_ms`
  - Conteggio/latency delle chiamate embedding OpenAI.
- `ui.observability.settings_updated` extra: `stack_enabled`, `tracing_enabled`, `redact_logs`, `log_level`
  - Preferenze globali di osservabilita' aggiornate dal pannello Log/Osservabilita' (persistite in `observability.yaml`).
- Eventi CLI `cli.pre_onboarding.*`, `cli.tag_onboarding.*`, `cli.semantic_onboarding.*`
  - Gli orchestratori applicano automaticamente le preferenze di `observability.yaml` (livello/log redaction/tracing OTEL) come default nei logger; override ancora possibile via parametri espliciti.
- `retriever.query.started` extra: `slug`, `scope`, `response_id`, `k`, `candidate_limit`, `latency_budget_ms`, `throttle_key`, `query_len`
  - Punto di ingresso della query vettoriale; non logga il testo della query.
- `retriever.query.embedded` extra: `slug`, `scope`, `response_id`, `ms`, `embedding_dims`, `embedding_model`
  - Embedding della query completata; include dimensione embedding e modello se noto.
- `retriever.candidates.fetched` extra: `slug`, `scope`, `response_id`, `candidates_loaded`, `candidate_limit`, `ms`, `budget_hit`
  - Caricamento candidati dal DB completato; `budget_hit` segnala se il deadline era gia' esaurito.
- `retriever.evidence.selected` extra: `slug`, `scope`, `response_id`, `k`, `selected_count`, `budget_hit`, `evidence_ids`
  - Scelta finale dei top-k; `evidence_ids` contiene [{rank, score, source_id?, chunk_id?}] senza snippet/testo.
- `retriever.response.manifest` extra: `slug`, `scope`, `response_id`, `manifest_path`, `evidence_ids`, `k`, `selected_count`
  - Manifest per-risposta salvato su disco (path locale); i log non includono snippet o contenuti sensibili, solo ID/sintesi delle evidenze.

## Explainability & lineage

- `semantic.input.received` extra: `slug`, `scope`, `source_id`, `source_path`, `content_type`, `ingestion_run_id`
  - Evento di ingresso di un documento/Markdown prima del chunking o indicizzazione; registra SSoT di provenienza.
- `semantic.lineage.chunk_created` extra: `slug`, `scope`, `path`, `source_id`, `chunk_id`, `chunk_index`
  - Chunk derivato da una sorgente tracciata; associa il chunk all'identificativo di origine.
- `semantic.lineage.embedding_registered` extra: `slug`, `scope`, `path`, `source_id`, `chunk_id`, `embedding_id`, `version`
  - Embedding calcolata e persistita per un chunk con lineage noto (versione tipicamente `YYYYMMDD`).
- `semantic.lineage.hilt_override` extra: `slug`, `source_id`, `chunk_id`, `operator_id`, `reason`
  - Override manuale HiTL su un elemento di lineage; l'operator_id va mascherato/anonimizzato.

Note:
- Gli orchestratori e le API usano `phase_scope(logger, stage=..., customer=...)` per tracciare `phase_started/phase_completed/phase_failed` con `artifacts` numerici.
- Evitare string-log non strutturati per eventi di pipeline/CLI: il messaggio (`msg`) deve essere il codice evento. Usa `extra` per contesto/descrizione se serve.
