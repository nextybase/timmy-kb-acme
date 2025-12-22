# 07 — Modular Gate Checklists (for Engineering Gatekeeper via OCP-plane)
**Status:** ACTIVE
**Scope:** checklist cognitive per decisioni PASS / PASS WITH CONDITIONS / BLOCK sulle transizioni workspace, rivolte all’Engineering Gatekeeper (assistant AI) che opera attraverso l’OCP-plane. Il binding lifecycle↔workspace↔gate↔event è definito in `instructions/06_promptchain_workspace_mapping.md`.
**Authority:** si basa sui contratti di `instructions/05_pipeline_workspace_state_machine.md`, `instructions/06_promptchain_workspace_mapping.md` e `instructions/02_prompt_chain_lifecycle.md`. Questo documento fornisce checklist operative, non logica di binding.

## Global Rules
- Modulare: un modulo per ciascuna transizione workspace (05), usato prima di decidere PASS/BLOCK.
- Il Gatekeeper OCP-role lavora tramite il Control Plane (OCP-plane); non esegue azioni, valuta artefatti/segni.
- Le evidenze devono essere verificabili (file, log, segnali); se un artefatto non è formalizzato, si annota “non formalizzato”.
- L’applicabilità dei gate per transizione è definita in `instructions/06_promptchain_workspace_mapping.md`.

## Modulo 1 — bootstrap → raw_ready
- **Gate coinvolti:** Evidence Gate (layout integrity) + Skeptic Gate (OCP supervision)
- **Evidence anchors:** `output/timmy-kb-<slug>/raw/`, `config/config.yaml`, log `pre_onboarding.workspace.created`, `context.config.bootstrap` (Evidence Gate).
- **Checklist:**
  1. Integrità artefatti/layout: `config/config.yaml` esiste e `raw/` è diretto da WorkspaceLayout?
  2. Coerenza stato workspace: WorkspaceLayout segnala “bootstrap” valido?
  3. Scope safety: tutti i path passano da `ensure_within*`?
  4. Osservabilità: log `context.config.bootstrap` e `pipeline.paths.repo_root.detected` confermano la creazione?
  5. Stop/HiTL: `WorkspaceLayoutInvalid`/`WorkspaceNotFound` → BLOCK; aspettarsi repair `bootstrap_client_workspace`.

## Modulo 2 — raw_ready → tagging_ready
- **Gate:** Skeptic Gate (Gatekeeper + OCP) dopo Evidence Gate
- **Evidence anchors:** `semantic/tags_raw.csv`, `tags_reviewed.yaml`, `semantic/tags.db`, segnale `has_raw_pdfs`.
- **Checklist:**
  1. Artefatti: `semantic/tags_raw.csv` è presente e coerente? `tags_reviewed.yaml` esiste e non è vuoto?
  2. Stato workspace: raw_ready era TRUE (hanno PDF)?
  3. Scope safety: raw dentro `ensure_within` e `semantic` sotto layout?
  4. Osservabilità: log `ui.semantics.gating_allowed`/`blocked` e `ui.semantics.state_update_failed` riflettono gating?
  5. Stop/HiTL: `_raise_semantic_unavailable` → BLOCK; azione attesa: caricare PDF o ripetere `tag_onboarding`.

## Modulo 3 — tagging_ready → pronto
- **Gate:** Evidence Gate (Codex) + Skeptic Gate (OCP)
- **Evidence anchors:** Markdown `book/`, log `ui.semantics.gating_allowed`, `has_raw_pdfs`.
- **Checklist:**
  1. Artefatti: `book/` contiene i nuovi `.md`? `semantic/book.frontmatter` loggato?
  2. Stato workspace: tagging_ready confermato dai checkpoint?
  3. Scope safety: conversione passa per `semantic.api` e `ensure_within`?
  4. Osservabilità: `_run_convert` logga `ui.semantics.state_update_failed` solo se errore?
  5. Stop/HiTL: `_raise_semantic_unavailable` se raw non ready → BLOCK; azione: sistemare raw o `tags.db`.

## Modulo 4 — pronto → arricchito
- **Gate:** Skeptic Gate (Gatekeeper + OCP)
- **Evidence anchors:** `semantic/tags.db` aggiornato, log `semantic.book.frontmatter`, `load_reviewed_vocab`.
- **Checklist:**
  1. Artefatti: Vocabulary caricato con `load_reviewed_vocab`? Cloud?
  2. Stato workspace: stato `pronto` registrato in `_update_client_state`?
  3. Scope safety: `enrich_frontmatter` usa solo `pipeline.*` pubblici?
  4. Osservabilità: evento `ui.semantics.state_update_failed` non duplicato?
  5. Stop/HiTL: `ConfigError` ⇒ BLOCK; azione: rifare tag e rigenerare vocab.

## Modulo 5 — arricchito → finito
- **Gate:** Evidence Gate (Codex) + QA Gate (diff/report)
- **Evidence anchors:** `README.md`, `SUMMARY.md`, log `ui.semantics.state_update_failed`, `context.step.status`.
- **Checklist:**
  1. Artefatti: README/SUMMARY sono freschi e path-safe?
  2. Stato workspace: stato `arricchito` confermato da `_update_client_state`?
  3. Scope safety: `write_summary_and_readme` ha usato `safe_write_*`?
  4. Osservabilità: `context.step.status` segnala success?
  5. Stop/HiTL: fallimento `write_summary_and_readme` → BLOCK; azione: correggere frontmatter/mapping.

## Modulo 6 — finito → out-of-scope handover
- **Gate:** QA Gate finale (`pre-commit run --all-files`, `pytest -q`) + Skeptic Gate (OCP)
- **Evidence anchors:** report QA, log `pipeline.github_utils.phase_started/completed`, `phase_failed`.
- **Checklist:**
  1. Artefatti: QA log (`pre-commit`, `pytest`) esibiti?
  2. Stato workspace: `finito` confermato?
  3. Scope safety: push to GitHub rispetta `GIT_FORCE_ALLOWED_BRANCHES`?
  4. Osservabilità: `phase_started`/`phase_completed` mostrano successo?
  5. Stop/HiTL: `phase_failed` → BLOCK; azione: correggere errori CI e ripetere QA.

## Gaps & TODO
- Mancano PASS artifact formali per Evidence Gate su ogni transizione (`raw_ready`, `tagging_ready`).
- derived states (raw_ready/tagging_ready) non hanno una predicate unica nel codice; “non formalizzato”.
- Retry/resume dopo fallimento non è definito; documentare la policy (solo log warning attuali).
- Il binding QA↔FINITO e l’applicabilità dei gate sono definiti in `instructions/06_promptchain_workspace_mapping.md`.
