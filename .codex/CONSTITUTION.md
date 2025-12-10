# NeXT Principles & Probabilismo (minimum)

- Human-in-the-Loop: agents propose solutions, the team decides. Keep iterations short and verifiable.
- Probabilism: decisions rely on evidence (tests, metrics, logs). Update rules when the data changes.
- Consistency: a single source of truth for paths/I-O (SSoT) and for tags (SQLite at `semantic/tags.db`).
- Safety: no writes outside the customer perimeter; redact secrets in logs.
- Portability: support both Windows and Linux; pay attention to encodings and paths (POSIX vs Windows) when exchanging files.
