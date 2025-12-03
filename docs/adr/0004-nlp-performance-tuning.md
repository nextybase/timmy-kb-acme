# ADR-0004: Ottimizzazione performance pipeline NLP e cache RAW
- Stato: Accepted
- Data: 2025-11-06
- Responsabili: Team Timmy KB / Codex Agent

## Contesto
Su workspace con centinaia di PDF la fase di tag onboarding soffriva di tempi lunghi:

- `iter_safe_pdfs` scansionava continuamente `raw/`, duplicando I/O;
- le query SQLite (doc_terms/folders) venivano ripetute per documento e cartella;
- l'estrazione NLP (spacy/yake/keybert) era totalmente sequenziale, saturando un solo core;
- il lock GitHub per i push aveva timeout/poll fissi poco adatti a workspace condivisi.

Serve ridurre la latenza preservando path-safety, idempotenza e HiTL.

## Decisione
- **Cache RAW eager**: `safe_write_*` e le copy verso `raw/` invalidano e pre-riscaldano la cache LRU di `iter_safe_pdfs`; TTL/cap configurabili in `config/config.yaml` (`pipeline.raw_cache`).
- **Preload DB**: `_collect_raw_docs` costruisce mapping cartelle/documenti ed indice doc_terms in memoria; `_persist_sections` usa una sola scansione di `doc_terms`.
- **Parallelizzazione controllata**: `run_nlp_to_db` usa `ThreadPoolExecutor` con coda in-order e tuning `--nlp-workers`, `--nlp-batch-size`, `--nlp-no-parallel`.
- **Lock GitHub configurabile**: `TIMMY_GITHUB_LOCK_TIMEOUT_S`, `TIMMY_GITHUB_LOCK_POLL_S`, `TIMMY_GITHUB_LOCK_DIRNAME` tarano il lease su workspace multi-utente.

Documentazione aggiornata (`docs/runbook_codex.md`, `docs/codex_integrazione.md`), nuovo test su invalidazione cache e CLI ampliata.

## Alternative considerate
- **ProcessPoolExecutor**: scartato per overhead nel caricare modelli NLP per processo e logging piu complesso.
- **Caching nei caller**: avrebbe duplicato logica e violato la SSoT di `path_utils`.
- **Query SQL incremental-only**: riduce parzialmente i round-trip ma non scala sui grandi dataset.

## Revisione
- Monitorare durata media `run_nlp_to_db` (target <50% rispetto al baseline su 5k PDF).
- Rivalutare con: nuovi modelli NLP, dataset >20k PDF o regressione >10%.
- Se la cache RAW cresce troppo, rivedere `pipeline.raw_cache.max_entries`/`ttl_seconds`.
