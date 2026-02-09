## SECTION 1 - Behavioral Constants
- Path-safety is always ON: every filesystem interaction must go through the safe path and atomic write helpers (`pipeline.path_utils.ensure_within*`, `pipeline.path_utils.ensure_within_and_resolve`, `pipeline.file_utils.safe_write_*`). Raw joins / manual I/O / direct `open` calls are prohibited.
- Changes must be micro-PRs: small, focused, idempotent, and reversible, respecting the scope defined by the current prompt. Avoid sprawling refactors or mass edits.
- Zero unintended side effects: avoid import-time work, unwanted env changes, or network calls unless the prompt explicitly allows them.
- Documentation must be updated alongside any behavior change; consult the relevant docs (Developer Guide, Coding Rules, system/ops/agents_index.md, etc.).
- Never alter the repository structure (renaming directories, moving files outside scope) without explicit instruction.
- Enforce structured logging (use `pipeline.logging_utils.get_structured_logger` with redaction when secrets exist) and keep SSoT consistency in mind.

## SECTION 2 - Build, QA & Verification
- Follow the documented install steps (`pip install -r requirements*.txt`, optional Docker for preview) and prefer the provided `make qa-safe` target when available.
- Intermediate QA for each prompt: `pytest -q -k 'not slow'`. Run only when prompted; document any skips/errors and retry up to twice on failure before requesting guidance.
- Final QA (Prompt final of the chain): run the full suite `pytest -q` plus `pre-commit run --all-files`. Failures must halt progress, trigger corrections, and only resume once the commands pass (max 10 retries per PromptChain_spec).
- Treat QA failures as blocking: do not continue without fixing the root cause and rerunning the required commands until they succeed.

## SECTION 3 - Repository Conventions
- The writable areas for Codex are limited to `src/`, `tests/`, `docs/`, and `.codex/`. Respect path safety by routing all writes through the safe helpers mentioned above.
- Always keep documentation aligned with behavior. If the change touches functionality, configuration, workflows, or onboarding, update the corresponding `docs/` files and note the change in related AGENTS/workflow indexes.
- Tests must reflect behavior adjustments: add or update tests when logic changes, explaining the rationale in the commit summary and ensuring they run under the same QA contract.
- SSoT principles mean that configuration/config overrides belong in the versioned files (`config/config.yaml`, `.env.example`) and secrets stay out of the repository.

## SECTION 4 - Prompt Chain Governance
- The agent interaction follows the OCP<->Codex turn-based model described in `system/specs/promptchain_spec.md`: Onboarding -> meta analysis -> operational prompts -> final QA -> Prompt N+1 report.
- Always respond to one prompt at a time, never invent future prompts, and leave the channel after each answer awaiting the next instruction.
- After completing Prompt 0, prepend the memo "Active rules: path-safety ON, micro-PR, zero side-effects, update docs if needed." to the start of every subsequent prompt response, keeping the active rule reminder visible.
- Each operational prompt is treated as a micro-PR: produce one focused diff, document tests run, state QA status, and summarize the impact plus next steps in the final reply.

### SECTION 4.1 - Output Contract (MUST, zero ambiguity)
For Prompt 1..N and Prompt N+1, the response must follow the **canonical Evidence Pack** order defined in `.codex/PROMPTS.md` ("EVIDENCE FORMAT (MUST)") and reinforced by `system/specs/promptchain_spec.md` (Evidence Gate).

Hard rules:
- No "omitted for brevity", no partial diffs, no "identical to previous log".
- The diff MUST be a real unified diff with `diff --git`, `index`, `---/+++`, `@@`.
- If you touched multiple files, include all their diff blocks.
- If any required artifact is missing, assume the Evidence Gate will BLOCK: fix the response format proactively (do not ask the OCP how to format it).

Self-check before sending (must be true):
- `git status --porcelain=v1` present
- unified diff markers present
- report present
- QA output present + exit status stated

## SECTION 5 - Agents & Priority Rules
- The local `.codex/AGENTS.md` is the authoritative AGENT configuration for this repository and overrides any user-level or external AGENTS files.
- External or global agent configs (e.g., `~/.codex/AGENTS.md`) must not override the repository-local rules; resolve conflicts in favor of the repository-level instructions.
- When in doubt, reference `system/ops/agents_index.md` and the local AGENTS documents to determine the active policy for the area being modified.
