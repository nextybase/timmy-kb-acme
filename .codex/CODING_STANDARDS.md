# Coding Standards  Timmy-KB (minimo)

- Type hints obbligatori nei moduli core; evita `Any` salvo casi motivati.
- Nessun `print()` nei moduli: usa `pipeline.logging_utils.get_structured_logger`.
- Path-safety: valida sempre con `pipeline.path_utils.ensure_within` prima di write/copy/delete.
- I/O: usa `pipeline.file_utils.safe_write_text/bytes` per scritture atomiche (mai open() diretto nei caller).
- Niente side-effect in import-time: esegui I/O solo in funzioni/`main`.
- Orchestratori gestiscono input utente e exit codes; moduli interni non chiamano `sys.exit()`/`input()`.
- Test: pytest, deterministici, senza rete; mock/bypass per Drive/Git. Solo `.md` in `book/` (i `.md.fp` tollerati).
- Lint: ruff + mypy coerenti con `pyproject.toml`; rispetta line-length e regole esistenti.

## Policy aggiuntive (pre-commit)

- Vietato usare `assert` runtime in `src/` (consentiti nei test): usa eccezioni tipizzate (`PipelineError`, `ConfigError`, ...).
  - Hook: `forbid-runtime-asserts` (scripts/dev/forbid_runtime_asserts.py)
- Vietato `Path.write_text/Path.write_bytes` in `src/`: usa `safe_write_text/bytes` (scrittura atomica) dopo guardia `ensure_within`.
  - Hook: `forbid-path-write-text-bytes` (scripts/dev/forbid_path_writetext_bytes.py)
- SSoT path-safety: chi scrive/copia/elimina deve invocare `ensure_within(base, target)` prima delloperazione.

## API di modulo e tipizzazione

- Esporta solo lAPI pubblica con `__all__ = [...]`; helper/Protocol interni restano con prefisso `_`.
- Preferisci `Protocol` locali per i parametri `context` quando servono solo pochi attributi; evita dipendenze forti inutili.
