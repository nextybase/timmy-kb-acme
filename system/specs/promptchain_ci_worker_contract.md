# Prompt Chain -- CI Worker Contract (Codex)

This document is the Single Source of Truth for how Codex must respond during a Prompt Chain.

## Why this exists
Prompt Chain is an evidence-gated workflow. Progress is allowed only when the evidence is complete,
verbatim, and auditable (status + diff + logs + exit status).

## Non-negotiable rules

### No-omission rule (HARD)
Forbidden phrases (examples):
- "omitted for brevity"
- "output omitted"
- "as shown above"
- "same as earlier"
- "identical to the previous log"

If you feel tempted to omit, you MUST chunk instead.

### Chunking
If output is long, split into messages:
- `Part 1/N`, `Part 2/N`, ...
- No truncation.
- Keep headings identical across parts.

### Evidence format (operational prompts)
Operational prompts (usually Prompt 1..N and Prompt N+1) MUST use:

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
<max 5 lines>
```

Notes:
- `git diff` must include all changed files in the current work.
- Each command must show full output and explicit exit status.
- If a command cannot be run, write `NOT RUN` and still include an exit status line.

## Scope enforcement
If the work order limits file scope, modifications outside scope are a contract breach.
Stop and respond with:
`NEED_INPUT: request to expand scope (file path + reason)`

## Read-only enforcement (Phase 0)
When the work order says read-only:
- No file changes.
- No patch proposals.
- Provide analysis and file references only.
