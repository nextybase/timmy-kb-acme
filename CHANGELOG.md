# Changelog - Timmy-KB (Sintesi)

> Formato: **Keep a Changelog** e **SemVer**
> Nota: elenco condensato ai soli punti chiave che impattano UX, sicurezza, API pubbliche o qualita.

## [Unreleased]

### Pending
- Push intermedio: integrazione UI Vision e adapter OpenAI (vector stores/responses/chat) ancora in debug; modifiche non definitive, seguiranno fix per completare il flusso nuovo cliente.

### Changed
- Dev tooling: rinominata la cartella root `tools/` in `scripts/`; aggiornati riferimenti in CI (`.github/workflows/ci.yaml`), pre-commit (`.pre-commit-config.yaml`), `makefile` e documentazione (`docs/*`, `README`).
- Indexing: indicizzazione parziale su mismatch `embeddings != contents` (troncamento al minimo comune) con telemetria aggiornata (`semantic.index.mismatched_embeddings`, `semantic.index.embedding_pruned`, `semantic.index.skips`).
- Telemetria phase_scope: i rami "no files" e "no contents" ora emettono sempre `artifact_count=0` e chiusura `semantic.index.done`.
- File I/O: `safe_append_text` passa ad append diretto O(1) per record, mantenendo lock e fsync opzionale.
- Retriever: logging armonizzato e short-circuit su embedding piatti `list[float]` con metriche `{total, embed, fetch, score_sort}` e contatori `coerce`; hardening su errori embedding (log `retriever.query.embed_failed` + ritorno `[]`) e check del budget di latenza prima di embedding/fetch.
- CLI pre-onboarding: dry-run e gestione errori loggano eventi strutturati (`cli.pre_onboarding.*`) con extra coerenti.
- Timmy KB Coder: gestione RAG piu tollerante (nessun hard fail senza streamlit) con eventi `coder.rag.disabled` e `coder.embeddings.ui_error`.
- Semantic index: eventi `semantic.index.embedding_pruned` arricchiti (cause mismatch/empty e contatori completi) e rimossi i messaggi testuali duplicati.
- Semantic vocab loader: slug derivato da `REPO_NAME_PREFIX` e logging uniformato (`semantic.vocab.db_missing`, `semantic.vocab.db_empty`, `semantic.vocab.loaded`).
- Retriever cosine: ora usa generatori con `itertools.tee`, evitando copie in memoria e mantenendo scaling numerico controllato.

### Added
- Test di integrazione su indexing (mismatch parziale, invariance ranking, metriche coerce, casi artifacts=0).
- Test per il retriever su vettori lunghi/estremi e ranking deterministico con candidati numerosi.
- Test per il vocabolario semantico con CapLog sui nuovi eventi e scenario `streamlit` assente in Timmy KB Coder.
- Test UI di parità firma wrapper `safe_write_text` UI vs backend; TypedDict `SearchResult` per l’output di `retriever.search`.
- Documentazione aggiornata su cache frontmatter LRU bounded e hardening retriever (developer guide + runbook).

### Compatibility
- Nessun breaking change; API pubbliche invariate, schema DB stabile.

### Fixed
- `src/tools/gen_dummy_kb.py`: import lazy e path workspace allineato a `output/timmy-kb-<slug>`.
- PDF discovery case-insensitive (.pdf/.PDF) in API, content_utils e tags_extractor.
- Cache frontmatter Markdown ora LRU bounded (evita crescita infinita su run lunghi).

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
