# Scopo
Regole per i flussi semantici (enrichment/frontmatter) mantenendo SSoT e idempotenza.

# Regole (override)
- Uso della facade pubblica `semantic.api`; niente import/invocazioni di funzioni `_private`.
- SSoT tag runtime: `semantic/tags.db`; `tags_reviewed.yaml` solo per authoring/migrazione.
- README/SUMMARY tramite utility repo con fallback idempotenti (nessuna sovrascrittura distruttiva).
- Nessun side-effect a import-time; funzioni pure dove possibile.

# Criteri di accettazione
- Enrichment non duplica tag, rispetta sinonimi/alias e non altera contenuti non frontmatter.
- Se `tags.db` manca, proporre rigenerazione/migrazione invece di fallback silenziosi.

# Riferimenti
- docs/AGENTS_INDEX.md
