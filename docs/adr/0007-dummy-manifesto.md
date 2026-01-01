# ADR-0007: Dummy Manifesto

- Status: Proposed
- Date: 2026-01-01
- Owners: Timmy KB Architecture Group; Franco Mennella

## Context

The Dummy must be elevated from a utility into a governed architectural object because the system's
pipeline, UI, and CI are tightly coupled and regressions can propagate across boundaries. A single,
normative fixture is required to validate end-to-end behavior, enforce consistent entry points, and
provide deterministic health signals for both humans and automation.

## Decision

Define the Dummy as a first-class architectural fixture.

### Architectural Role

- The Dummy is a synthetic but semantically real client.
- The Dummy is the system-wide counterproof for the full pipeline.

### Entry Points

- The Dummy MUST use the same entrypoints as real clients.
- No bypasses and no alternate pipelines are allowed.

### Idempotency and Cleanup

- Dummy generation MUST be repeatable without global resets.
- Each step cleans only the artifacts it regenerates.
- No global workspace resets are permitted.

### Step Selection

- Each major step (Drive, Vision, Semantic, Enrichment, Preview) can be enabled or disabled.
- Disabled steps MUST NOT execute and MUST NOT modify artifacts.

### Smoke vs Deep Modes

- Smoke mode is CI-oriented, fast, and deterministic.
- Deep mode is manual, diagnostic, and runs the full pipeline.
- CI executes smoke mode only.

### UI Responsibilities

- The UI orchestrates the Dummy workflow but does not reimplement logic.
- The UI MUST NOT bypass CLI or pipeline contracts.

### Health Contract

- Dummy generation produces a structured health report.
- Health is a contract, not free-form logs.

## Alternatives Considered

- Ad-hoc smoke tests are insufficient to govern system-wide behavior.
- Multiple partial fixtures increase entropy and weaken guarantees.
- Keeping the Dummy as a tool-only artifact was rejected.

## Consequences

### Positive

- Single canonical fixture.
- Stronger guarantees against regressions.
- Clear governance boundaries.

### Trade-offs

- Higher upfront rigor.
- Stronger coupling between Dummy and pipeline evolution.

## Revision

- ADR-0006 will be aligned to this Manifesto.
- Future ADRs involving the Dummy must reference ADR-0007.
