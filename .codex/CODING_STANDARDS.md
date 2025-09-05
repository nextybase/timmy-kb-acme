# Coding Standards – Timmy-KB (minimo)

- Type hints obbligatori nei moduli core; evita `Any` salvo casi motivati.
- Nessun `print()` nei moduli: usa `pipeline.logging_utils.get_structured_logger`.
- Path-safety: valida sempre con `pipeline.path_utils.ensure_within` prima di write/copy/delete.
- I/O: usa `pipeline.file_utils.safe_write_text/bytes` per scritture atomiche (mai open() diretto nei caller).
- Niente side-effect in import-time: esegui I/O solo in funzioni/`main`.
- Orchestratori gestiscono input utente e exit codes; moduli interni non chiamano `sys.exit()`/`input()`.
- Test: pytest, deterministici, senza rete; mock/bypass per Drive/Git. Solo `.md` in `book/` (i `.md.fp` tollerati).
- Lint: flake8 + mypy coerenti con `pyproject.toml`; rispetta line-length e regole esistenti.
