# Workflow operativi (UI/CLI)

## Panorama
- Doppio approccio: **orchestratori CLI** o **UI Streamlit** (`onboarding_ui.py`).
- Obiettivo: trasformare PDF in **KB Markdown AI‑ready** con frontmatter coerente, README/SUMMARY e **preview HonKit (Docker)**; infine **push**.

## Flusso end-to-end
1) **pre_onboarding** → crea sandbox locale (`output/timmy-kb-<slug>/...`), risolve YAML struttura, opzionale **provisioning Drive** + upload `config.yaml`.
2) **tag_onboarding** → genera `semantic/tags_raw.csv` (euristiche filename/path) + checkpoint HiTL → `tags_reviewed.yaml` (stub revisione).
3) **semantic_onboarding** (UI via `semantic.api`) → **PDF→Markdown** in `book/` + **frontmatter enrichment** usando **vocabolario canonico su SQLite (`tags.db`)**, quindi **README/SUMMARY** (util repo → fallback idempotenti) e **preview Docker**.
4) **onboarding_full** → preflight (solo `.md` in `book/`) → **push GitHub**.

### Gating in UI
La tab **Semantica** compare **solo dopo** il download RAW locale (Drive → `raw/`).  
Preview Docker: start/stop con nome container sicuro e validazione porta.

### SSoT dei tag
- Authoring umano: `semantic/tags_reviewed.yaml` (revisione).
- **Runtime**: `semantic/tags.db` (SQLite) consumato da orchestratori/UI per l’arricchimento.

### Invarianti
- **Idempotenza** (rilanci sicuri), **path‑safety** (tutte le write passano da util dedicate),
- **Logging con redazione** dove richiesto; **portabilità** Win/Linux.
