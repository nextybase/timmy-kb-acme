# Workflow operativi (UI/CLI)

## Panorama
- Doppio approccio: **orchestratori CLI** o **UI Streamlit** (`onboarding_ui.py`).
- Obiettivo: trasformare PDF in **KB Markdown AI‑ready** con frontmatter coerente, README/SUMMARY e **preview HonKit (Docker)**; infine **push**.

## Flusso end-to-end
1) **pre_onboarding** → crea sandbox locale (`output/timmy-kb-<slug>/...`), risolve YAML struttura, opzionale **provisioning Drive** + upload `config.yaml`.
2) **tag_onboarding** → genera `semantic/tags_raw.csv` (euristiche filename/path) + checkpoint HiTL → `tags_reviewed.yaml` (stub revisione).
3) **Tag KG Builder** (`kg_build.py` / UI "Knowledge Graph dei tag") → legge `semantic/tags_raw.json`, invoca l’assistant OpenAI `build_tag_kg`, salva `semantic/kg.tags.json` + `semantic/kg.tags.md` e mantiene la vista human-first per revisioni (occhio ai namespace).
4) **semantic_onboarding** (UI via `semantic.api` / CLI) → **PDF→Markdown** in `book/`, arricchimento frontmatter usando **vocabolario canonico su SQLite (`tags.db`)**, rigenera il frontmatter, costruisce `README/SUMMARY` e prepara la preview Docker.
4) **onboarding_full** → preflight (solo `.md` in `book/`) → **push GitHub**.

### Gating in UI
La tab **Semantica** compare **solo dopo** il download RAW locale (Drive → `raw/`).
Preview Docker: start/stop con nome container sicuro e validazione porta.

### SSoT dei tag
- Authoring umano: `semantic/tags_reviewed.yaml` (revisione).
- **Runtime**: `semantic/tags.db` (SQLite) consumato da orchestratori/UI per l’arricchimento.
- **Knowledge Graph**: `semantic/kg.tags.json` (machine-first) e `semantic/kg.tags.md` (human-friendly) costruiti da `kg_build.py`/UI `Knowledge Graph dei tag` e consumati dai futuri ingest/embedding.

### Invarianti
- **Idempotenza** (rilanci sicuri), **path‑safety** (tutte le write passano da util dedicate),
- **Logging con redazione** dove richiesto; **portabilità** Win/Linux.

## API Semantiche Additive (v1)

Queste funzioni estendono la pipeline semantica senza cambiare i flussi UI/CLI. Sono idempotenti, offline e rispettano la path‑safety (SSoT) con scritture atomiche.

- build_mapping_from_vision(context, logger, slug) -> Path:
  genera `config/semantic_mapping.yaml` a partire da `config/vision_statement.yaml`.
  Input: vision YAML. Output: mapping normalizzato. Errori chiari, nessuna rete.

- build_tags_csv(context, logger, slug) -> Path:
  scandisce `raw/` (PDF) e produce `semantic/tags_raw.csv` (euristica conservativa) + `README_TAGGING.md`.
  Idempotente; CSV con header esteso: `relative_path | suggested_tags | entities | keyphrases | score | sources`.

- build_markdown_book(context, logger, slug) -> list[Path]:
  converte RAW→Markdown (uno `.md` per cartella di primo livello) e garantisce `README.md`/`SUMMARY.md` in `book/`.
  Se presente il vocabolario consolidato (`semantic/tags.db`), arricchisce i frontmatter (title/tags). Fallback minimale se i repo util non sono disponibili.

- index_markdown_to_db(context, logger, slug, scope="book", embeddings_client, db_path=None) -> int:
  indicizza i `.md` in SQLite (un chunk per file, embedding via `embeddings_client`).
  Meta: `{file: <name>}`; versione giornaliera `YYYYMMDD`. Parametro `db_path` per storage isolato nei test.

Invarianti comuni
- Path‑safety: `pipeline.path_utils.ensure_within(...)` su output (e input dove sensato).
- Scritture atomiche: `pipeline.file_utils.safe_write_text/bytes`.
- Logging strutturato via `pipeline.logging_utils.get_structured_logger`.
