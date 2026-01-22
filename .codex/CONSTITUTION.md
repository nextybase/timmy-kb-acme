# NeXT Principles & Probabilismo (minimum)

Codex operates within the **Agency Engine** of the system.
It does not belong to, nor modify, the **Epistemic Envelope**.

The system is structured around two canonical epistemic domains:

- **Epistemic Envelope**
  The non-deliberative domain responsible for ingestion, transformation,
  artifacts, knowledge graphs, lineage and traceability.

- **Agency Engine**
  The deliberative domain responsible for Prompt Chains, agent interaction,
  work orders and supervised execution.

Codex is a component of the **Agency Engine** and is always constrained
by the Epistemic Envelope active at execution time.

- Human-in-the-Loop: agents propose solutions, the team decides. Keep iterations short and verifiable.
- Probabilism: decisions rely on evidence (tests, metrics, logs). Update rules when the data changes.
- Consistency: a single source of truth for paths/I-O (SSoT) and for tags (SQLite at `semantic/tags.db`).
- Safety: no writes outside the customer perimeter; redact secrets in logs.
- Portability: support both Windows and Linux; pay attention to encodings and paths (POSIX vs Windows) when exchanging files.

## Prompt Chain Governance
- Each intervention by Codex passes through the Prompt Chain model: Phase 0 (analysis/read-only), Phase 1..N (micro-PR operations), Prompt N+1 (final QA + summary).
- The turn-based protocol Planner → OCP → Codex → OCP → Planner ensures at most one action per prompt and mandates Italian-only replies from Codex while documentation remains English.
- Prompt Chain prompts follow the Active Rules memo (path safety, zero side effects, Active Rules, language policy, QA) defined in `.codex/PROMPTS.md`; the final QA prompt runs `pre-commit run --all-files` and `pytest -q`.
- The constitution defers to `system/specs/promptchain_spec.md`, `system/ops/runbook_codex.md`, `.codex/PROMPTS.md` and `.codex/CHECKLISTS.md` as complementary SSoT references for the contract.

## Terminology clarification

The term **“Work Order Envelope”** used in Codex workflows
refers to a *contractual execution boundary* between agents.

It is **not equivalent** to the **Epistemic Envelope**.

- *Epistemic Envelope* → system-level epistemic boundary
- *Work Order Envelope* → agent-level execution contract
