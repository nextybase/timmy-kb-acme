# Scopo
Regole dedicate alla documentazione: lingua, aggiornamento coerente con UX/flow e allineamento di versioni/frontmatter.

# Regole (override)
- Documentazione in italiano; i documenti architetturali possono restare in inglese se dichiarato nell'indice.
- Gli aggiornamenti di codice che toccano UX/flow devono riflettersi nei testi nello stesso PR.
- Titoli/frontmatter allineati alla versione corrente (`v1.0 Beta`) e coerenti tra README e docs/.
- Eseguire `pre-commit run cspell --all-files` (o `--files docs/...`) e usare link relativi con snippet aggiornati (es. Python 3.11, Streamlit 1.50.0).
- Se la guida cita workflow Streamlit/CLI, documentare gli orchestratori correnti (`pipeline.github_push_flow.*`, `tools.gen_dummy_kb.build_payload`, `ui.pages.tools_check._is_gate_error`).
- Preferire i service `semantic.*_service`/`semantic.mapping_loader` quando si documenta `semantic.api`; nei test esempi di monkeypatch sui wrapper riesportati.

# Criteri di accettazione
- Spell check pulito su `docs/` e `README.md` senza ignorati ad hoc.
- Frontmatter/titoli coerenti con la versione pubblicata.
- ADR/changelog aggiornati quando cambiano prassi o strumenti documentali.

# Riferimenti
- docs/AGENTS_INDEX.md
- docs/runbook_codex.md
