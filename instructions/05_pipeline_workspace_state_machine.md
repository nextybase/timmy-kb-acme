# 05 — Pipeline/Workspace State Machine (SSoT)
**Status:** ACTIVE
**Scope:** pipeline/workspace artifacts e workflow di bootstrap/enrichment, indipendente dal lifecycle dei prompt.
**Authority:** questo contratto è allineato al MANIFEST, al Prompt Chain Spec (`system/specs/promptchain_spec.md`) e alle istruzioni operative (`system/ops/runbook_codex.md`, `.codex/WORKFLOWS.md`). Non sostituisce le regole di governance pubblicate in `instructions/`; il binding lifecycle↔workspace↔gate vive in `instructions/06_promptchain_workspace_mapping.md` e il vincolo QA↔FINITO in `instructions/08_gate_evidence_and_retry_contract.md`.

## Definitions
- **State labels (persisted/logical storage):**
  1. `pronto` — assegnato via `_update_client_state(..., "pronto", ...)` dopo `_run_convert` (`src/ui/pages/semantics.py`).
  2. `arricchito` — assegnato da `_run_enrich` dopo `enrich_frontmatter`.
  3. `finito` — assegnato da `_run_summary` dopo `write_summary_and_readme`.
- **Derived states (artifact-based, non persistenti):**
  - `bootstrap` — workspace creato da `pipeline.workspace_bootstrap.bootstrap_client_workspace` (UI/CLI `pre_onboarding`), con directory `raw/`, `semantic/`, `book/`, `logs/`, `config/config.yaml`.
  - `raw_ready` — raw directory contiene almeno un PDF (`has_raw_pdfs` in `src/ui/utils/workspace.py`).
  - `tagging_ready` — derivato dalla presenza di `semantic/tags.db` e `tags_reviewed.yaml` prodotti da `tag_onboarding`; è un derived state inferito a runtime dagli artefatti e non è imposto da una singola predicate nel codice.
- **Canonical artifacts:**
  | Artifact | Significato attuale | Produttore | Fonte |
  |---|---|---|---|
  | `output/timmy-kb-<slug>/raw/` | sorgente PDF per conversione | `pipeline.workspace_bootstrap` + Drive provisioning/`tag_onboarding` | `pipeline.workspace_bootstrap.py`, `docs/user/user_guide.md` |
  | `semantic/semantic_mapping.yaml` | mapping Vision generato da `tools/gen_vision_yaml.py` | Vision statement workflow | `docs/user/user_guide.md` |
  | `semantic/tags.db` | SSoT tag per enrichment | `tag_onboarding`, `ui.services.tags_adapter` | `docs/user/user_guide.md`, `_run_enrich` |
  | `semantic/tags_raw.csv`, `tags_reviewed.yaml` | checkpoint HiTL | `tag_onboarding` | `docs/user/user_guide.md` |
  | `book/README.md`, `SUMMARY.md`, `.md` | artefatti finali | `semantic_onboarding`, `write_summary_and_readme` | `docs/user/user_guide.md`, `_run_summary` |
  | `config/config.yaml` | configurazione canonica del workspace | `ClientContext._ensure_config`, `bootstrap_client_workspace` | `src/pipeline/context.py`, `pipeline.workspace_bootstrap.py` |
  | `logs/` + `logs/log.txt` | logging strutturato | tutti i moduli (Pipeline/UI) | `src/pipeline/workspace_layout.py`, `README.md` |

## State Machine Table
| State | Type | Entry conditions | Allowed actions | Transition event | Next state | Fail-fast / stop |
|---|---|---|---|---|---|---|
| `bootstrap` | DERIVED | `ClientContext.load` valida slug e `WorkspaceLayout.from_context` fallisce su asset mancanti (`WorkspaceNotFound`, `WorkspaceLayoutInvalid`) | `bootstrap_client_workspace` / UI “Nuovo cliente” / `pre_onboarding` | completamento `bootstrap_client_workspace` | `raw_ready` | eccezioni `WorkspaceNotFound`/`WorkspaceLayoutInvalid` → stop |
| `raw_ready` | DERIVED | `has_raw_pdfs(slug)` ritorna `(True, raw_dir)` e caching TTL 3s | abilitazione tab Semantica (`_require_semantic_gating`) / `tag_onboarding` | `tag_onboarding` produce `semantic/tags.db` + `tags_reviewed.yaml` | `tagging_ready` | gating `_raise_semantic_unavailable` se `raw` vuoto → blocco UI |
| `tagging_ready` | DERIVED | `semantic/tags.db` esiste e `tags_reviewed.yaml` scritto (HiTL) | `semantic_onboarding`, `_run_convert` | `_run_convert` (conversione PDF → Markdown) | `pronto` | `ConfigError` se `tags.db` mancante/vuoto → gating blocked |
| `pronto` | STATE_LABEL | `_run_convert` chiama `_update_client_state(..., "pronto", ...)` | `_run_enrich` (enrichment) | `_run_enrich` | `arricchito` | `_require_semantic_gating` blocca se raw non ready; `_update_client_state` logga warning |
| `arricchito` | STATE_LABEL | `_run_enrich` logga success | `_run_summary`, `write_summary_and_readme` | `_run_summary` | `finito` | fallimento `ConfigError` su vocab (`load_reviewed_vocab` fallisce) riporta stato `pronto` e mostra errore |
| `finito` | STATE_LABEL | `_run_summary` completa `README/SUMMARY` con QA PASS prerequisito | `onboarding_full` (Git push) / `pipeline.github_utils` | `onboarding_full` (preflight + push) | **out-of-scope: agency (Timmy)** | `pytest`, `pre-commit` fail → Skeptic Gate blocca; `pipeline.github_utils` lancia `phase_failed` |

## HiTL Checkpoints
- `tags_reviewed.yaml` rappresenta la validazione umana (aggiunta da `tag_onboarding`, citata in `docs/user/user_guide.md`). Se manca, `semantic_onboarding` e `_require_semantic_gating` falliscono con `ConfigError` e `_raise_semantic_unavailable`, bloccando la tab Semantica e impedendo il progresso.
- La guardia `_require_semantic_gating` (`src/ui/pages/semantics.py`) usa `has_raw_pdfs` + `state in ALLOWED_STATES`; se raw non è pronto o lo stato non è riconosciuto logga `ui.semantics.gating_blocked`, mostra messaggi e impedisce l’esecuzione di `convert`, `enrich`, `summary`.

## Retry / Resume Policy
- Il layout è fail-fast: `WorkspaceNotFound`, `WorkspaceLayoutInvalid`, `WorkspaceLayoutInconsistent` (da `WorkspaceLayout.from_*`) interrompono il flow e richiedono intervento manuale.
- `_update_client_state` e `_reset_gating_cache` permettono una nuova esecuzione sullo stesso stato dopo un errore, ma **in assenza di una policy formale di retry, ogni ripetizione è considerata una nuova esecuzione sullo stesso stato.**
- Le API di bootstrap (`bootstrap_client_workspace`, `migrate_or_repair_workspace`) riparano asset mancanti; ogni errore viene propagato (non salvato) e il flow resta bloccato finché l’asset non è disponibile.

## Observability Signals
- `ui.semantics.gating_allowed` / `ui.semantics.gating_blocked` (`src/ui/pages/semantics.py`) — gate raw/se state.
- `ui.semantics.state_update_failed` — errori durante `_update_client_state`.
- `context.step.status` / `context.config.loaded` / `context.config.bootstrap` (`src/pipeline/context.py`) — segnali di progresso e bootstrap.
- `pipeline.paths.repo_root.detected`, `pre_onboarding.workspace.created` (citati in README/Runbook) — indicano che il workspace è stato creato.
- `semantic.book.frontmatter` event (nota User Guide) — quantifica i file arricchiti.

## Gaps & TODO
- La policy di retry automatizzato non è formalizzata; riferirsi a `instructions/08_gate_evidence_and_retry_contract.md` e al binding in `instructions/06_promptchain_workspace_mapping.md` per QA↔FINITO e gating.
