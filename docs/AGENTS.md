# AGENT — Documentazione

> Nota: le policy comuni restano in `AGENTS_INDEX.md`; qui vanno solo gli override specifici del dominio documentazione.

## Strategia
- I contenuti testuali della documentazione rimangono in **italiano**; i documenti architetturali possono restare in inglese ma vanno esplicitati nell’indice.
- Ogni aggiornamento di codice che impatta UX/flow deve propagarsi alle guide entro lo stesso PR (SSoT).
- Teniamo coerenti titoli/frontmatter con la versione comunicata (`v1.0 Beta` finché non cambia la linea guida centrale).

## Regole
- **cSpell**: eseguire `pre-commit run cspell --all-files` (o `--files docs/...`) prima del commit; aggiungere nuove parole solo se sono termini di dominio verificati.
- **Frontmatter & titoli**: i file Markdown devono indicare la versione coerente; niente numerazioni divergenti tra README e docs/.
- **Link & snippet**: privilegiare link relativi; per snippet usare blocchi con linguaggio e mantenere esempi aggiornati (Python 3.11, Streamlit 1.50.0).
- **Verifiche automatiche**: usare `pre-commit run agents-matrix-check --all-files` quando si toccano gli `AGENTS.md` per mantenere la matrice aggiornata.
- **Pattern aggiornati**: documentare sempre l’uso dei nuovi orchestratori (`pipeline.github_push_flow._prepare_repo/_stage_changes/_push_with_retry/_force_push_with_lease`, `tools.gen_dummy_kb.build_payload`) e dei guardrail condivisi (`ui.pages.tools_check._is_gate_error`) quando la guida cita workflow Streamlit o CLI.
- **Moduli semantic**: quando si tocchi `semantic.api`, preferire i service dedicati (`semantic.convert_service`, `semantic.frontmatter_service`, `semantic.embedding_service`, `semantic.mapping_loader`). I test possono monkeypatchare i wrapper re-esportati in `semantic.api`.

## Accettazione
- Spell check pulito su `docs/` e `README.md`, senza ignorare file.
- Titoli/frontmatter sincronizzati alla versione pubblicata.
- ADR/changelog aggiornati quando si introdurranno nuove prassi o strumenti documentali.
