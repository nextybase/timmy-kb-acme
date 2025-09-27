Timmy‑KB v1.8.0

Questa release rimuove legacy e fallback, introduce una façade semantica stabile e normalizza i log per ambienti Windows/console.

Breaking Changes
- YAML struttura: supporto unico al formato moderno
  - Usa solo: { raw: {...}, contrattualistica: {} }
  - Rimosso legacy root_folders e ogni alias RAW/YAML
- Mapping: accettato solo semantic/tags_reviewed.yaml (rimosso tags_reviews.yaml)
- Import obbligatori: UI e runner richiedono pipeline.* (rimossi fallback e stub)
- Semantica: façade unica semantic.api (rimosso src/semantic_onboarding.py)

Added
- pipeline.path_utils.to_kebab(s: str) (SSoT)
- src/semantic_headless.py — CLI minimale per convert → enrich → README/SUMMARY via façade

Changed
- src/ui/utils/core.py ora delega a pipeline (ensure_within, safe_write_text, to_kebab)
- Log console ASCII‑only (rimozione emoji/simboli)
- config/cartelle_raw.yaml in formato moderno

Fixed
- Messaggi logger normalizzati (pre_onboarding, gitbook_preview, github_utils, config_utils)
- Runner Drive: README PDF/TXT con titoli/elenchi ASCII e logging alias‑free

Migrazione
- Aggiorna cartelle_raw.yaml a:
  raw:
    categoria-kebab: {}
  contrattualistica: {}
- Assicurati che semantic/tags_reviewed.yaml esista (niente più tags_reviews.yaml)
- Verifica che UI/runner abbiano le dipendenze pipeline installate
- Adotta semantic.api per i flussi semantici

Esempio headless (semantic.api)
```
py - <<PY
from semantic.api import get_paths, convert_markdown, enrich_frontmatter, write_summary_and_readme
from semantic.vocab_loader import load_reviewed_vocab
from pipeline.context import ClientContext
import logging
slug = 'acme'
ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
log = logging.getLogger('semantic.release')
convert_markdown(ctx, log, slug=slug)
base = get_paths(slug)['base']
vocab = load_reviewed_vocab(base, log)
enrich_frontmatter(ctx, log, vocab, slug=slug)
write_summary_and_readme(ctx, log, slug=slug)
PY
```
