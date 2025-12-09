# Scopo

Regole operative per l'agente Codex nel repository (ambito `.codex/`), con focus su path-safety, scritture atomiche, QA e orchestrazione GitHub.



# Regole (override)

- Path-safety: scrivo solo in `src/`, `tests/`, `docs/`, `.codex/`; mai in `config/**`, `.env*`, `output/**`.
- I/O atomico via utility SSoT (`ensure_within*`, `safe_write_*`), nessun side-effect a import-time.
- Pipeline QA standard da eseguire: `isort`, `black`, `ruff --fix`, `mypy`, `pytest -q -k 'not slow'`.
- Per i push usare solo gli helper `_prepare_repo`, `_stage_changes`, `_push_with_retry`, `_force_push_with_lease` (stub nei test come in `tests/pipeline/test_github_push.py`).
- Strumenti vision/UI: riusare `_is_gate_error` (`ui.pages.tools_check`) e i builder `build_payload/emit_structure` di `tools.gen_dummy_kb`.
- Collaborazione con Senior Reviewer: micro-PR a scope singolo, riepilogo con riferimenti a `.codex/CONSTITUTION.md` e `docs/AGENTS_INDEX.md`, QA eseguita e dubbi esplicitati.
- Codex puo essere guidato da una Prompt Chain definita dall'OCP: ogni prompt e un micro-PR che rispetta AGENT-first/HiTL, path-safety, QA e SSoT `docs/AGENTS_INDEX.md`; l'OCP orchestra ma non modifica il repository. Per la definizione completa della chain fare riferimento a `docs/PromptChain_spec.md`.
- Prompt Chain: fermati dopo ogni risposta, attendi il prompt successivo dell'OCP e non inventare Prompt 2..N autonomi; segui il contratto operativo della Prompt Chain (modello turn-based) e riferisciti sempre a `docs/PromptChain_spec.md` come SSoT.



# Criteri di accettazione

- Path-safety rispettata (solo `src/`, `tests/`, `docs/`, `.codex/`; nessuna eccezione).
- Scritture atomiche, nessun effetto collaterale a import-time.
- QA locale completata con la pipeline standard.
- Micro-PR: un change set mirato, motivato; se tocco un'area aggiorno i relativi docs/test.
- Messaggi UI brevi; salvataggi solo via utility SSoT.
- Ogni change set derivante dalla Prompt Chain include il Prompt finale di QA (`pytest -q` + `pre-commit run --all-files`) e il commit finale deve aderire alla semantica descritta in `docs/PromptChain_spec.md`.



# Riferimenti

- docs/AGENTS_INDEX.md
- .codex/CONSTITUTION.md
- .codex/WORKFLOWS.md
- .codex/CODING_STANDARDS.md
- .codex/CHECKLISTS.md
- docs/runbook_codex.md
