# Prompt Chain Spec (SSoT)

## 1. Introduction
- **Purpose:** keep the planning phase (Planner → OCP) and the operational work (Codex) strictly separated while ensuring every step remains controlled, traceable, and compliant with the micro-PR discipline.
- **Why a SSoT:** this document is the authoritative reference for actors, expected outputs, governance rules, and template requirements across the Prompt Chain.
- **Principles:** turn-based rigor, micro-PR safety (path safety, atomic I/O), human oversight (HiTL), explicit QA, and strict adherence to the Phase model.
- **Support docs:** `.codex/PROMPTS.md` (template API), `.codex/CHECKLISTS.md` (checklist), `.codex/CLOSURE_AND_SKEPTIC.md` (closure packet), `system/ops/runbook_codex.md` (operational guide).

## 2. Mandatory Turn-Based Protocol
- Planner defines objectives and constraints, never editing the repository.
- OCP translates objectives into numbered prompts, keeps scope narrow, issues one prompt at a time, and never performs edits.
- Codex executes exactly one action per prompt: apply a micro-PR, provide a diff/report, and declare QA outcomes before pausing.
- After Codex responds, OCP evaluates and issues the next prompt (or the closing prompt): no batching, no unsolicited follow-ups, no prompt skipping.
- Every prompt turn must reference this protocol so that all participants remain aligned and the chain remains reproducible.
- **Skeptic Gate (MUST):** dopo ogni output operativo di Codex (Prompt 1..N e Prompt N+1) l’OCP conduce lo Skeptic Gate come atto decisionale; la catena avanza solo con Decision=PASS, PASS WITH CONDITIONS impone vincoli, BLOCK blocca la fase successiva.
- **Evidence Gate:** Prompt 1..N non avanza finché la risposta di Codex non include il memo Active Rules, il diff unificato, il report strutturato e la QA richiesta; l’OCP interrompe la catena senza questi artefatti.
- **Hard rule approvazione OPS/RUN:** nessun prompt operativo di tipo OPS/RUN (Phase 1..N o Prompt N+1) può essere inoltrato a Codex senza prima aver ricevuto dall’OCP una conferma umana esplicita. L’OCP resta l’unico responsabile della decisione di inviare il prompt, deve documentarla nel report e attivarla prima che Codex riceva istruzioni. Codex non deve richiedere né interpretare approvazioni, deve limitarsi a rispettare lo scope/path-safety e a produrre memo Active Rules + diff/report/QA. Se la conferma OCP manca, lo Skeptic Gate blocca il passaggio e il prompt è considerato non valido.

## 3. Verification & Progression Rules
- **Evidence required per step:** each prompt response constitutes progression only when Codex delivers a unified diff, a structured report describing the change and QA results, and, when asked, the intermediate QA output (`pytest -q -k "not slow"` or other tests detailed in the prompt). Those artifacts alone prove that Codex performed the requested work.
- **Push policy:** pushing to `main` is _not_ a default step; it happens only when the chain reaches Prompt N+1 (finalization), the OCP explicitly authorizes a push, or a change affects runtime behavior that cannot stay confined to a reviewable diff/report/QA set. The push is a synchronization event, never an implicit requirement.
- **OCP decision gate:** only the OCP decides whether the evidence is sufficient to advance the chain or request further iterations; Codex waits for the next OCP prompt before moving forward, reporting the artifacts produced and any blockers.
- **Prompt formatting requirement:** OCP → Codex prompts must be delivered as a single copyable structured block (see `.codex/PROMPTS.md`) to prevent ambiguity and ensure reproducibility.

## 4. Prompt Chain Phase Model
The Prompt Chain unfolds in three clearly delimited phases that map to numbered prompts. Each phase carries a precise mandate, acceptable actions, and deliverables.

### 4.1 Phase 0 – Analytical, read-only prompts (Prompt 0, 0x)

**Normative clarification (v1.1):** Prompt 0x (0a, 0b, … 0n) are not legacy, fallback, or deprecated. They are a formal extension of Phase 0 and an integral part of controlled uncertainty reduction.

#### Phase 0 — Purpose
Phase 0 exists to:
- build a shared, verifiable understanding of the system;
- identify constraints, risks, and objectives;
- make explicit the remaining uncertainties that prevent safe action.

Phase 0 does not aim at exhaustiveness; it aims at mapping the relevant ignorance.

#### Prompt 0 — Official entrypoint (role and limits)
Prompt 0 is the official entrypoint into the Prompt Chain. It is valid even when the output is:
- incomplete information;
- a list of open questions;
- an explicit inability to formulate a robust operational plan.

A Prompt 0 that declares missing information is a correct outcome, not a failure.

#### Prompt 0x — Exploratory Prompts
Prompt 0x prompts are Phase 0 read-only deep-dives, used exclusively during Phase 0.
Their purpose is to close specific uncertainties that emerged from:
- Prompt 0;
- previous Prompt 0x prompts.

**Epistemic governance (core rule):** Prompt 0x is not a procedural fallback. It persists until the OCP deems the information state sufficient to authorize entry into the operational phase.

#### Admissibility rules (Prompt 0x)
A Prompt 0x is admissible only if it:
- addresses an uncertainty explicitly declared in a previous prompt;
- has a distinct, non-redundant informational scope;
- is entirely read-only (no edits, no patch/diff, no build, no tests, no execution);
- is explicitly authorized by the OCP.

#### Allowed actions in Phase 0 (read-only inspections)
Phase 0 forbids any write, patch/diff generation, formatting, QA commands, tests, or builds.
Read-only inspection commands are permitted only if explicitly whitelisted by the OCP in the prompt itself (Prompt 0 or Prompt 0x), to keep SSoT ingestion verifiable.

#### Exit condition (leaving Phase 0)
Leaving Phase 0 is not automatic nor numerical. Phase 0 ends only when the OCP formally declares that the achieved information level is sufficient to formulate a robust, safe, and effective operational plan.
This declaration is a governance act and a prerequisite to issuing any operational prompt (Prompt 1..N).

#### Non-return rule (important)
Once the operational phase starts (Prompt 1), the emergence of new structural uncertainties must not be resolved via new Prompt 0x prompts; it is a BLOCK condition for the Prompt Chain.

### 4.2 Phase 1..N – Operational micro-PR prompts
- Purpose: implement scoped changes defined by the OCP while honoring path safety, template structure, and the Active Rules memo.
- Each prompt must emit a unified diff, a structured report, and at least `pytest -q -k "not slow"` (or a justified alternative) before moving forward.
- Codex must apply changes only to the files declared in the prompt, document assumptions, and run targeted tests when requested.
- **Skeptic Gate template (MUST):** Evidence check (memo/diff/report/QA presenti?) [YES/NO]; Scope check (file autorizzati?) [YES/NO]; Risk check (nuovi rischi/edge cases?) [OK/NOTED/BLOCK]; Decision: PASS / PASS WITH CONDITIONS / BLOCK.
- Dopo ogni risposta operativa Codex, lo **Skeptic Gate** viene attivato da l’OCP: il gate è un atto di governance, non un task operativo di Codex. OCP valuta rischi e limiti, annota osservazioni e decide se emettere il prompt successivo; Codex può indicare problemi ma non può autorizzare autonomamente il passaggio di fase.

### 4.3 Prompt N+1 – Final QA and chain closure
- Purpose: verify the entire change set with the full QA stack (`pre-commit run --all-files`, `pytest -q`), summarize the chain, and emit a one-line closing commit message in Italian (unless explicitly instructed otherwise).
- Codex may apply up to ten micro-fixes to satisfy QA; each rerun is documented in the report.
- Only after both QA commands pass and the closing summary is issued may the chain be considered complete.

## 5. Mandatory Language Policy
- All canonical documentation, templates, and artifacts referenced by the Prompt Chain are maintained in English, preserving the SSoT character.
- Codex must respond exclusively in Italian in every prompt of the chain, including embedded reports and QA summaries, unless a prompt explicitly authorizes another language.
- Conversations between Planner, OCP, and Codex must remain Italian to keep the human-in-the-loop flow consistent with this policy.

## 6. Prompt Template Expectations
- Templates for Prompt 0, Prompt 0x, Prompt 1..N, and Prompt N+1 live in `.codex/PROMPTS.md` and define the mandatory sections that each prompt must declare (purpose, allowed files, Active Rules memo, phase constraints, tests, etc.).
- Operational prompts (Phase 1..N) are the only ones authorized to generate diffs, touch files, and execute the intermediate QA mentioned above; Phase 0 prompts remain analytical, and Prompt N+1 focuses on final QA plus narrative closure.
- Every prompt must embed the Active Rules memo at the start of the response to remind all stakeholders of path safety, micro-PR scope, QA requirements, and the language policy.

  ### 6.1 Canonical Prompt Header
  - Il template canonico richiede che ogni prompt inizi con il blocco:

```
ROLE: Codex
PHASE: ...
SCOPE: ...
ACTIVE RULES MEMO: ...
EXPECTED OUTPUTS: ...
TESTS: ...
CONSTRAINTS: ...
STOP RULE: ...
```

    La riga `ROLE: Codex` deve precedere qualunque dettaglio operativo: senza di essa l’OCP considera il prompt incompleto e lo Skeptic Gate non autorizzerà l’avanzamento. Il template blocca il passaggio quando manca il `ROLE` o viene sostituito con un valore diverso, impedendo che prompt copiati da OCP o da altre fonti assumano impropriamente il ruolo di Codex. Evidence Gate e Skeptic Gate sono incaricati di verificare che il blocco sia presente prima di giudicare contenuti, limiti e rischi.

  ## 7. Protocol Violations (do not do)
- Breaking the Planner→OCP→Codex→OCP→Planner turn order or issuing multiple actions per prompt.
- Executing edits/QA during Phase 0 or skipping Phase N+1 altogether.
- Responding in any language other than Italian when not explicitly allowed.
- Touching files that lie outside the scope declared by the active prompt or the SSoT.
- Omitting the Active Rules memo or failing to document QA attempts and retries.

## 8. Part A – Governance (Planner + OCP)

### 8.1 Actors
- **Planner:** defines the business goals, constraints, and success criteria; it does not modify the repository or run commands.
- **OCP (OrchestratoreChainPrompt):** translates Planner directives into numbered prompts, enforces this spec (sections 2-6), ensures each prompt covers one turn, and never edits files.
- **Codex:** executes the current prompt alone, respecting the declared scope, template, Active Rules memo, and the Phase model before pausing for the next instruction.

### 8.2 Onboarding Task Codex (mandatory entry point)
- Runs once at the start of every chain, ensuring Codex loads `system/ops/agents_index.md`, the relevant `AGENTS.md`, `.codex/AGENTS.md`, and the other SSoT documents listed in `.codex/PROMPTS.md`.
- Establishes path safety, QA expectations, and the requirement to plan before coding; sets the tone for micro-PR discipline.
- Activates the Phase model: Prompt 0 (analysis) always precedes any operational prompt; skipping or collapsing phases is forbidden.

### 8.3 Prompt Chain definition
- The chain is a numbered, turn-based sequence (Prompt 0…N+1) with a clear scope for each prompt as per section 6.
- Each prompt addresses a single concern; no prompt may inject future requests, combine unrelated scopes, or expand its declared file set.
- Prompt templates require the Active Rules memo, list of allowed/prohibited files, expected outputs (diff/report/QA), and explicit statements about the phase and language policy.

### 8.4 Prompt Chain lifecycle
- **Kick-off:** Planner decides on the chain; Onboarding Task codifies the plan and loads the SSoT; only after this may the OCP issue Prompt 0.
- **Execution:** OCP issues prompts sequentially; Codex responds with one micro-PR (diff + report + intermediate QA), then waits for the next prompt. Each operational response includes the memo from section 6 and confirms compliance with the turn-based protocol.
- **Closure:** OCP issues Prompt N+1 with final QA requirements; Codex runs `pytest -q` and `pre-commit run --all-files` (repeating up to ten times if needed), documents every rerun, summarizes the entire chain, and ends with a one-line Italian commit message.
- If QA fails more than twice per prompt, Codex rewrites the patch and retries; after the third failure, Codex explicitly requests guidance from the OCP.

## 9. Part B – Operational Contract for Codex

### 9.1 What is a Prompt Chain for Codex?
- A sequence of numbered prompts aligned to the Phase model; Codex must execute only the current prompt and never anticipate future phases.
- Each prompt corresponds to a micro-PR defined in the template from section 6 and obeys the mandatory language policy from section 5.

### 9.2 Core rules
- Respect path safety, atomic writes, the AGENTS matrices, this spec, and the QA pipeline (intermediate `pytest -q -k "not slow"`, final `pytest -q` + `pre-commit run --all-files`).
- Run the static pre-check described in `.codex/PROMPTS.md` before generating a patch; failing pre-checks halt QA and require corrective action.
- Handle retries cleanly, document them in each report, and stop to ask the OCP if the same issue persists after two autocorrections.
- All conversational exchanges with OCP and Planner must stay Italian.
- **Trial window:** lo Skeptic Gate è MUST per le prossime due Prompt Chain complete; dopo il secondo ciclo l’OCP guida una retrospettiva obbligatoria per decidere se mantenerlo o ritararlo.

### 9.3 Prompt format
- Every prompt declares purpose, allowed/prohibited files, expected outputs (diff, report, QA), and explicit prohibitions as defined in `.codex/PROMPTS.md`.
- The Active Rules memo from section 6 must appear at the start of every operational response.

### 9.4 Required output per prompt
- Provide a unified diff when changes exist.
- Deliver a structured report describing the changes, their impact, the QA executed, and suggested next steps.
- Mention any assumptions, blockers, or unanswered questions.

### 9.5 Anti-patterns
- Combining unrelated domains in the same prompt, touching unspecified files, adding spurious context outside the template, or neglecting the memo/language/phase guardrails.

## 10. Codex Smoke Chain – Diagnostic Test
- Objective: simulate a miniature Prompt Chain (S0–S4) to prove turn-taking, memo awareness, QA policy, escalation limits, Italian language, and pre-check validation without editing the repo.
- Flow:
  - S0: OCP sends a toy prompt; Codex acknowledges the Active Rules memo.
  - S1: Codex describes how it would pre-check a mock diff with no files changed.
  - S2: OCP issues a sample operational prompt; Codex replies conceptually with a micro-PR summary.
  - S3: Codex states the intermediate QA (`pytest -q -k "not slow"`) it would run, explaining how it would interpret the outcome without executing the command.
  - S4: Codex describes the escalation path (max two autocorrections), the final QA (`pytest -q` + `pre-commit run --all-files`), and reconfirms Italian-language compliance.
- Rules: no disk writes, no QA execution, always respect path safety, micro-PR discipline, and the Italian-only policy.
- Use cases: governance health check, Prompt Chain metadata validation, and documentation of OCP→Codex alignment.
