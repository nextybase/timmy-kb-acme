# 08 — Gate Evidence and Retry Contract (SSoT)
**Status:** ACTIVE
**Scope:** formalizzazione di Evidence Gate PASS, predicate derived states (`raw_ready`, `tagging_ready`), policy di retry/resume e collegamento QA Gate → stato `finito`.
**Authority:** costruito su `instructions/05_pipeline_workspace_state_machine.md`, `instructions/06_promptchain_workspace_mapping.md`, `instructions/07_gate_checklists.md` e `instructions/02_prompt_chain_lifecycle.md`.

## Evidence Gate — PASS Artifacts (Log-based)
| Transition | Required log event(s) | Producer module |
|---|---|---|
| `bootstrap → raw_ready` | `pre_onboarding.workspace.created`, `context.config.bootstrap`, `pipeline.paths.repo_root.detected` | `pre_onboarding`, `pipeline.context`, `pipeline.paths` |
| `raw_ready → tagging_ready` | `ui.semantics.gating_allowed`, `ui.semantics.gating_blocked` transitions to allowed | `src/ui/pages/semantics.py` |
| `tagging_ready → pronto` | `ui.semantics.state_update_failed` absent, `semantic.book.frontmatter` log | `semantic.api`, `ui.pages.semantics` |
| `pronto → arricchito` | `semantic.book.frontmatter` updated, `load_reviewed_vocab` success log | `semantic.api`, `ui.pages.semantics` |
| `arricchito → finito` | `context.step.status` updates to “summary”, absence of `ui.semantics.state_update_failed` | `pipeline.context`, `ui.pages.semantics` |
| `finito → out-of-scope` | `pipeline.github_utils.phase_started`/`phase_completed`, absence of `phase_failed` | `pipeline.github_utils` |
*Nota:* l’Evidence Gate si basa su log strutturati; dove manca un evento canonico si annota “non formalizzato” nel rispettivo modulo.

## Derived State Predicates
- **raw_ready:** `has_raw_pdfs(slug)` restituisce `True` *e* il layout (`WorkspaceLayout`) esiste con directory `raw/` e config validi; la derivazione viene ricavata a runtime, non persiste su disco.
- **tagging_ready:** `semantic/tags.db` esiste, `tags_reviewed.yaml` è presente e aggiornato, `has_raw_pdfs` continua a restituire `True`; è un derived state inferito dagli artefatti, non vincolato a un’unica predicate codice.
- Entrambi rimangono derived states (non persistenti) e sono validati dall’Engineering Gatekeeper tramite il Control Plane prima di attivare la transizione successiva.

## Retry / Resume Contract
- Una ripetizione post-fallimento (`_run_convert`, `_run_enrich`, `_run_summary`) è considerata una *nuova esecuzione sullo stesso stato* (richiamata da instructions/05: “in assenza di policy formale…”).
- Evidence richiesta per retry: artefatti precedenti ancora intatti (`raw/`, `book/`, `semantic/tags.db`), log `context.step.status` che indica “retry in corso” o “reset di stato”.
- Retry è BLOCCATO se: `WorkspaceLayoutInvalid`, `WorkspaceNotFound`, o `ConfigError` persistono senza essere risolti; in tal caso serve intervento manuale (HiTL) e il gate restituisce BLOCK.

## QA Gate ↔ Workspace State
- Il QA Gate è prerequisito per dichiarare lo stato `finito`: prima della transizione `arricchito → finito` occorre presentare `pre-commit run --all-files` + `pytest -q` con esito PASS e i relativi log strutturati.
- L’Evidence per QA include l’output dei comandi, il report `context.step.status` aggiornato e `semantic.book.frontmatter` privo di errori; solo dopo il passaggio QA l’Engineering Gatekeeper tramite OCP-plane può consentire `finito`.

## Non-goals
- Non introduce nuovi stati (usa quelli definiti in instructions/05).
- Non modifica codice o logiche operative (documenta solo i contratti).
- Non automatizza le decisioni del gate; resta un documento per l’assistente Engineering Gatekeeper via OCP-plane.
