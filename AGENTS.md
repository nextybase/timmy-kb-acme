# Codex Agent Instructions

This repository uses a strict, spec-driven workflow called "Prompt Chain".
When a Prompt Chain work order is in progress, Codex MUST behave like a CI worker:
auditability and verifiable evidence are more important than readability.

## Prompt Chain CI Worker Output Contract (HARD)

### 0) Forbidden behaviors
- Do NOT write: "omitted for brevity", "output omitted", "same as above", "see previous log",
  "identical to earlier", or any equivalent wording.
- Do NOT summarize diffs or command outputs that are required by the work order.
- Do NOT reference previous messages as a substitute for required evidence.

### 1) Chunking rule (when output is long)
If the required evidence does not fit in a single message:
- Split into multiple messages labeled: `Part 1/N`, `Part 2/N`, ...
- Continue with the SAME section headers.
- Never truncate. Never omit.

### 2) Mandatory response skeleton (operational prompts)
For any Prompt Chain phase that requires evidence (typically Prompt 1..N and N+1),
respond using EXACTLY the following sections and order:

```
[PC:STATE]
git status --porcelain=v1
<verbatim output>

[PC:DIFF]
git diff
<verbatim unified diff output, COMPLETE>

[PC:LOGS]
<command 1>
<verbatim output>
Exit status: <0/1/...>

<command 2>
<verbatim output>
Exit status: <0/1/...>

[PC:SUMMARY]
<max 5 lines: what changed + why, no new plans, no refactors>
```

Rules:
- "verbatim" means copy/paste the raw terminal output.
- The diff MUST include `diff --git`, `index`, `---/+++`, and `@@` hunks for every file touched.
- Every command in [PC:LOGS] MUST include an `Exit status:` line.
- If a command was requested but cannot be run: write `NOT RUN` and a one-line reason, still keep Exit status.

### 3) Phase 0 (Planning / Read-only) strictness
If the work order says "read-only":
- Do NOT modify files.
- Do NOT run write actions.
- Provide analysis and file references only.

### 4) Scope strictness
If the work order defines "FILES IN SCOPE":
- Modify ONLY those files.
- If you believe another file is necessary, STOP and respond with:
  `NEED_INPUT: request to expand scope (file path + reason)`

## Single Source of Truth
See: system/specs/promptchain_ci_worker_contract.md
