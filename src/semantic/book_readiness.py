# SPDX-License-Identifier: GPL-3.0-only
"""
Utilities per verificare che la cartella `book/` di un workspace
sia pronta per l'anteprima (HonKit) e per l'uso come knowledge base.

Criteri di "book pronta":
- La directory esiste ed è una directory.
- Contiene un README.md di root.
- Contiene un SUMMARY.md di root.
- Contiene almeno un altro file .md di contenuto
  (esclusi README.md e SUMMARY.md).

Questo modulo NON dipende da Streamlit o dalla UI.
La funzione principale è `check_book_dir`, che può essere usata
sia dalla UI che dai CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("semantic.book_readiness")

# Proviamo a riutilizzare le costanti di progetto, se esistono.
try:
    from semantic.constants import README_MD_NAME, SUMMARY_MD_NAME
except Exception as exc:  # pragma: no cover - default di sicurezza
    README_MD_NAME = "README.md"
    SUMMARY_MD_NAME = "SUMMARY.md"
    logger.warning(
        "semantic.book_readiness.constants_fallback",
        extra={"error": str(exc)},
    )


def _iter_markdown_files(book_dir: Path) -> List[Path]:
    """
    Restituisce tutti i file .md sotto `book_dir`, in modo robusto.

    Non fa assunzioni sulla struttura delle sottocartelle.
    """
    if not book_dir.exists() or not book_dir.is_dir():
        return []

    return sorted(book_dir.rglob("*.md"))


def check_book_dir(book_dir: Path) -> Tuple[bool, list[str]]:
    """
    Verifica che la cartella `book/` sia strutturalmente pronta.

    Parameters
    ----------
    book_dir:
        Path della directory `book/` del workspace
        (es. .../output/timmy-kb-<slug>/book).

    Returns
    -------
    (ready, errors):
        - ready: True se la cartella è "ok" per l'anteprima.
        - errors: elenco di messaggi di errore (vuoto se ready=True).
    """
    errors: list[str] = []

    if not book_dir:
        errors.append("Percorso book_dir mancante o non valido.")
        return False, errors

    if not book_dir.exists():
        errors.append(f"Directory inesistente: {book_dir!s}")
        return False, errors

    if not book_dir.is_dir():
        errors.append(f"Non è una directory: {book_dir!s}")
        return False, errors

    md_files = _iter_markdown_files(book_dir)
    if not md_files:
        errors.append("Nessun file .md trovato in book/.")
        return False, errors

    # README.md e SUMMARY.md di root
    readme_path = book_dir / README_MD_NAME
    summary_path = book_dir / SUMMARY_MD_NAME

    if not readme_path.exists():
        errors.append(f"File README mancante: {readme_path.name}")
    if not summary_path.exists():
        errors.append(f"File SUMMARY mancante: {summary_path.name}")

    # File di contenuto: tutti i .md tranne README/SUMMARY root
    content_mds: list[Path] = []
    for path in md_files:
        # escludiamo solo i README/SUMMARY nella root di book
        if path == readme_path or path == summary_path:
            continue
        content_mds.append(path)

    if not content_mds:
        errors.append("Nessun file Markdown di contenuto trovato in book/ " "(solo README/SUMMARY).")

    ready = not errors

    # Logging di supporto per debug/observability
    if ready:
        logger.info(
            "book.readiness.ok",
            extra={"book_dir": str(book_dir), "content_files": len(content_mds)},
        )
    else:
        logger.warning(
            "book.readiness.fail",
            extra={"book_dir": str(book_dir), "errors": errors},
        )

    return ready, errors


def is_book_ready(book_dir: Path) -> bool:
    """
    Shortcut booleano su `check_book_dir`.

    Utile nei gating logici (UI/CLI) quando ti serve solo un sì/no.
    """
    ready, _ = check_book_dir(book_dir)
    return ready
