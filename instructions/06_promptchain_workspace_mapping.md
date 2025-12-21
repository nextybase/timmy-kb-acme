# 07 — Modular Gate Checklists (for Engineering Gatekeeper via OCP-plane)
**Status:** ACTIVE
**Scope:** checklist cognitive per decisioni PASS / PASS WITH CONDITIONS / BLOCK sulle transizioni workspace, rivolte all’Engineering Gatekeeper (assistant AI) che opera attraverso l’OCP-plane.
**Authority:** si basa sui contratti di `instructions/05_pipeline_workspace_state_machine.md` e `instructions/06_promptchain_workspace_mapping.md` e mantiene ferme le autorità già definite in `instructions/02_prompt_chain_lifecycle.md`.

## Global Rules
- Modulare: un modulo per ciascuna transizione workspace (05), usato prima di decidere PASS / BLOCK.
- L’Engineering Gatekeeper (OCP-role) opera tramite il Control Plane (OCP-plane); non esegue azioni, valuta artefatti, segnali e log.
- Le evidenze devono essere verificabili (file, log, segnali runtime); se un’ancora di evidenza non è formalizzata, va indicata esplicitamente come “non formalizzato”.

---

## Modulo 1 — bootstrap → raw_ready
- **Gate coinvolti:** Evidence Gate (layout integrity) + Skeptic Gate (supervisione OCP)
- **Evidence anchors:**
  `output/timmy-kb-<slug>/raw/`, `config/config.yaml`, log `pre_onboarding.workspace.created`, `context.config.bootstrap`
- **Checklist:**
  1. **Integrità artefatti/layout:** `config/config.yaml` esiste ed è path-safe? `raw/` è conforme a `WorkspaceLayout`?
  2. **Coerenza stato workspace:** `WorkspaceLayout.from_context` non solleva eccezioni?
  3. **Scope safety:** tutti i path sono validati tramite `ensure_within*`?
  4. **Osservabilità:** i log `context.config.bootstrap` e `pipeline.paths.repo_root.detected` confermano il bootstrap?
  5. **Stop / HiTL:** `WorkspaceLayoutInvalid` o `WorkspaceNotFound` ⇒ **BLOCK**; azione attesa: repair via `bootstrap_client_workspace`.

---

## Modulo 2 — raw_ready → tagging_ready
- **Gate:** Skeptic Gate (Gatekeeper + OCP) dopo Evidence Gate
- **Evidence anchors:**
  `semantic/tags_raw.csv`, `tags_reviewed.yaml`, `semantic/tags.db`, segnale `has_raw_pdfs`
- **Checklist:**
  1. **Artefatti:** `tags_raw.csv` è presente e coerente? `tags_reviewed.yaml` esiste e non è vuoto?
  2. **Stato workspace:** `raw_ready` è TRUE (PDF presenti)?
  3. **Scope safety:** `raw/` e `semantic/` sono sotto layout canonico?
  4. **Osservabilità:** log `ui.semantics.gating_allowed` / `ui.semantics.gating_blocked` riflettono lo stato reale?
  5. **Stop / HiTL:** `_raise_semantic_unavailable` ⇒ **BLOCK**; azione attesa: caricare PDF o ripetere `tag_onboarding`.

---

## Modulo 3 — tagging_ready → pronto
- **Gate:** Evidence Gate (Codex) + Skeptic Gate (OCP)
- **Evidence anchors:**
  Markdown in `book/`, log `ui.semantics.gating_allowed`, `has_raw_pdfs`
- **Checklist:**
  1. **Artefatti:** `book/` contiene nuovi file `.md`? La conversione è completa?
  2. **Stato workspace:** `tagging_ready` è inferibile dai checkpoint (`tags.db`, `tags_reviewed.yaml`)?
  3. **Scope safety:** la conversione usa solo API e path pubblici (`semantic.api`, `ensure_within`)?
  4. **Osservabilità:** `_run_convert` registra correttamente lo stato o eventuali errori?
  5. **Stop / HiTL:** `raw` non pronto ⇒ **BLOCK**; azione: sistemare `raw/` o rigenerare `tags.db`.

---

## Modulo 4 — pronto → arricchito
- **Gate:** Skeptic Gate (Gatekeeper + OCP)
- **Evidence anchors:**
  `semantic/tags.db` aggiornato, log `semantic.book.frontmatter`, `load_reviewed_vocab`
- **Checklist:**
  1. **Artefatti:** il vocabolario è caricato correttamente (`load_reviewed_vocab`)?
  2. **Stato workspace:** lo stato `pronto` è registrato via `_update_client_state`?
  3. **Scope safety:** `enrich_frontmatter` utilizza solo funzioni pubbliche di pipeline?
  4. **Osservabilità:** non ci sono duplicazioni o errori silenti in `ui.semantics.state_update_failed`?
  5. **Stop / HiTL:** `ConfigError` ⇒ **BLOCK**; azione: rifare tagging e rigenerare vocabolario.

---

## Modulo 5 — arricchito → finito
- **Gate:** Evidence Gate (Codex) + QA Gate (diff / report)
- **Evidence anchors:**
  `README.md`, `SUMMARY.md`, log `context.step.status`, `ui.semantics.state_update_failed`
- **Checklist:**
  1. **Artefatti:** `README.md` e `SUMMARY.md` sono presenti, aggiornati e path-safe?
  2. **Stato workspace:** lo stato `arricchito` è confermato prima della sintesi?
  3. **Scope safety:** `write_summary_and_readme` usa `safe_write_*`?
  4. **Osservabilità:** `context.step.status` segnala completamento corretto?
  5. **Stop / HiTL:** fallimento scrittura ⇒ **BLOCK**; azione: correggere frontmatter o mapping.

---

## Modulo 6 — finito → out-of-scope handover
- **Gate:** QA Gate finale (`pre-commit`, `pytest`) + Skeptic Gate (OCP)
- **Evidence anchors:**
  report QA, log `pipeline.github_utils.phase_started`, `phase_completed`, `phase_failed`
- **Checklist:**
  1. **Artefatti:** i report `pre-commit run --all-files` e `pytest -q` sono disponibili?
  2. **Stato workspace:** lo stato `finito` è confermato prima del push?
  3. **Scope safety:** il push rispetta `GIT_FORCE_ALLOWED_BRANCHES`?
  4. **Osservabilità:** `phase_started` / `phase_completed` indicano successo?
  5. **Stop / HiTL:** `phase_failed` ⇒ **BLOCK**; azione: risolvere errori CI e ripetere QA.
