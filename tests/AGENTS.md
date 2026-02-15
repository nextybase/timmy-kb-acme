# Purpose
Testing guidance emphasizing the unit -> middle/contract -> smoke E2E pyramid on dummy datasets.


# Rules (overrides)
- Generate dummy data with dedicated tools; never use real datasets.
- Avoid network dependencies: mock or bypass Drive/Git interactions.
- Enforce contract tests around the `book/` guard (`.md` files only; ignore `.md.fp`).


# Acceptance Criteria
- Local builds/tests pass with smoke E2E executed on reproducible dummy slugs.


# References
- system/ops/agents_index.md
