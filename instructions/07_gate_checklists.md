# 07 - Modular Gate Checklists (Engineering Gatekeeper / OCP-plane)

**Status:** ACTIVE
**Authority:** Operational checklist, subordinate to SSoT
**Scope:** cognitive and operational checklists supporting decisions
PASS / PASS_WITH_CONDITIONS / BLOCK on workspace state transitions.

This document **does not define** bindings, states, or advancement semantics.
It provides **evaluation tools** for the Engineering Gatekeeper (AI),
operating exclusively through the OCP-plane.

Normative references:
- instructions/05_pipeline_state_machine.md
- instructions/06_promptchain_workspace_mapping.md
- instructions/08_gate_evidence_and_retry_contract.md
- instructions/02_prompt_chain_lifecycle.md

---

## Global Principles (Beta 1.0)
- Each module corresponds to **a single workspace transition**.
- Checklists **do not produce states**: they support Decision Record issuance.
- Gatekeepers:
  - do not execute actions,
  - do not alter artefacts,
  - evaluate only **verifiable evidence**.
- Every verdict (PASS / BLOCK / FAIL / PASS_WITH_CONDITIONS) must be formalized via **append-only Decision Records**.
- Gate applicability per transition is defined in instructions/06_promptchain_workspace_mapping.md.
- All gates MUST comply with instructions/10_runtime_strict_contract_beta.md; any violation implies BLOCK.

## Virtual Environment (venv)
- Before executing generative scripts (e.g., 	ools/gen_dummy_kb.py), ensure the venv has SpaCy model it_core_news_sm installed.
- Recommended steps for creating/restoring the venv:
  1. env\Scripts\python -m pip install -e .
  2. env\Scripts\python -m pip install spacy==3.7.4
  3. env\Scripts\python -m pip install https://github.com/explosion/spacy-models/releases/download/it_core_news_sm-3.7.0/it_core_news_sm-3.7.0.tar.gz
  4. With this setup, semantic gating scripts find SpaCy and the required language model.

## Module 1 - WORKSPACE_BOOTSTRAP ? SEMANTIC_INGEST

**Required gates:**
- Evidence Gate (layout & artefacts)
- Skeptic Gate (OCP supervision)

**Evidence anchors (minimum):**
- Directories
aw/, config/, semantic/, ledger
- config/config.yaml
- Logs: pre_onboarding.workspace.created, context.config.bootstrap

**Checklist:**
1. **Layout integrity**: WorkspaceLayout created all canonical directories?
2. **Config validity**: config/config.yaml exists and is readable?
3. **Scope safety**: All paths validated via ensure_within*?
4. **Ledger readiness**: Ledger is writable (required for Decision Record)?
5. **Stop / BLOCK**: WorkspaceLayoutInvalid or WorkspaceNotFound ? BLOCK. Action: regenerate workspace (ootstrap_client_workspace).
