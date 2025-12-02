# Eventi di logging canonici (estratto)

Questi eventi sono emessi con `logger.info/warning` e includono campi `extra` standardizzati per facilitare la raccolta e l'analisi.

- `pipeline.content.skip_symlink` – extra: `slug`, `file_path`
  - Un PDF è stato ignorato perché symlink.
- `pipeline.content.skip_unsafe` – extra: `slug`, `file_path`, `error`
  - Un percorso PDF è stato scartato perché fuori perimetro/non sicuro.
- `semantic.convert_markdown.done` – extra: `slug`, `ms`, `artifacts={content_files}`
  - Conversione completata con conteggio dei Markdown di contenuto; emesso una sola volta.
- `semantic.index.db_inserted` – extra: `slug`, `scope`, `path`, `version`, `rows`, `inserted`
  - Riepilogo inserimenti a batch nel DB (idempotente).
- `kb_db.fetch.invalid_meta_json` – extra: `slug`, `scope`
  - Record con `meta_json` non valido; il valore viene ignorato.
- `kb_db.fetch.invalid_embedding_json` – extra: `slug`, `scope`
  - Record con `embedding_json` non valido; l'embedding viene ignorato.
- `ui.gating.sem_hidden` – extra: `slug`, `raw_ready`
  - La pagina Semantica è stata nascosta perché `raw/` non contiene PDF validi per lo slug attivo.
- `cli.pre_onboarding.drive.folder_created` – extra: `client_folder_id` (mascherato)
  - Cartella cliente creata su Drive.
- `cli.pre_onboarding.drive.structure_created` – extra: `config_tail`, `created_map_masked`
  - Struttura minima Drive (raw/contrattualistica/config) creata.
- `cli.tag_onboarding.scan_completed` – extra: `folders`, `documents`
  - Indicizzazione RAW -> DB completata.
- `cli.tag_onboarding.nlp_executor_configured` – extra: `workers`, `batch_size`
  - Executor NLP configurato per run parallela.
- `cli.tag_onboarding.nlp_completed` – extra: stats NLP (`terms`, `doc_terms`, `workers`, ...)
  - Pipeline NLP completata.
- `ui.startup` – extra: `version`, `streamlit_version`, `port`, `mode`
  - Avvio dell’app Streamlit, utile per distinguere i run UI.
- `pipeline.processing.progress` – extra: `slug`, `scope`, `processed`, `chunks`
  - Checkpoint di avanzamento batch ogni N elementi.
- `openai.api_calls` – extra: `model`, `count`, `latency_ms`
  - Conteggio/latency delle chiamate embedding OpenAI.
- `ui.observability.settings_updated` – extra: `stack_enabled`, `tracing_enabled`, `redact_logs`, `log_level`
  - Preferenze globali di osservabilità aggiornate dal pannello Log/Osservabilità (persistite in `observability.yaml`).
- Eventi CLI `cli.pre_onboarding.*`, `cli.tag_onboarding.*`, `cli.semantic_onboarding.*`
  - Gli orchestratori applicano automaticamente le preferenze di `observability.yaml` (livello/log redaction/tracing OTEL) come default nei logger; override ancora possibile via parametri espliciti.

Note:
- Gli orchestratori e le API usano `phase_scope(logger, stage=..., customer=...)` per tracciare `phase_started/phase_completed/phase_failed` con `artifacts` numerici.
- Evitare string-log non strutturati per eventi di pipeline/CLI: il messaggio (`msg`) deve essere il codice evento. Usa `extra` per contesto/descrizione se serve.
