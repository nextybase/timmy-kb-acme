# AGENT — Semantica (enrichment/frontmatter)
> Nota: policy comuni in `docs/AGENTS_INDEX.md`; questo file contiene solo override specifici.

## Obiettivi
- Arricchimento frontmatter coerente e ripetibile (idempotente) sui Markdown in `book/`.
- Uso esclusivo della **facade `semantic.api`** per le API pubbliche.

## Regole
- **SSoT tag runtime: SQLite (`semantic/tags.db`)**; YAML `tags_reviewed.yaml` è solo authoring/migrazione.
- Non importare o invocare funzioni `_private`; mantenere compatibilità della façade.
- README/SUMMARY: usa util repo; se assenti, fallback **idempotenti** (niente sovrascritture distruttive).
- Nessun side‑effect in import‑time; funzioni pure dove possibile.

## Accettazione
- Enrichment non duplica tag, rispetta sinonimi/alias e non altera contenuti non frontmatter.
- In assenza di `tags.db`: proporre rigenerazione/migrazione, non forzare fallback silenziosi.
