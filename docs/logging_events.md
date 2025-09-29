# Eventi di logging canonici (estratto)

Questi eventi sono emessi con `logger.info/warning` e includono campi `extra` standardizzati per facilitare la raccolta e l'analisi.

- `pipeline.content.skip_symlink` — extra: `slug`, `file_path`
  - Un PDF è stato ignorato perché symlink.
- `pipeline.content.skip_unsafe` — extra: `slug`, `file_path`, `error`
  - Un percorso PDF è stato scartato perché fuori perimetro/non sicuro.
- `semantic.convert_markdown.done` — extra: `slug`, `ms`, `artifacts={content_files}`
  - Conversione completata con conteggio dei Markdown di contenuto; emesso una sola volta.
- `semantic.index.db_inserted` — extra: `project_slug`, `scope`, `path`, `version`, `rows`, `inserted`
  - Riepilogo inserimenti a batch nel DB (idempotente).
- `kb_db.fetch.invalid_meta_json` — extra: `project_slug`, `scope`
  - Record con `meta_json` non valido; il valore viene ignorato.
- `kb_db.fetch.invalid_embedding_json` — extra: `project_slug`, `scope`
  - Record con `embedding_json` non valido; l'embedding viene ignorato.

Note:
- Gli orchestratori e le API usano `phase_scope(logger, stage=..., customer=...)` per tracciare `phase_started/phase_completed/phase_failed` con `artifacts` numerici.
- Evitare string-log non strutturati per eventi di pipeline; preferire l'uso di `extra`.
