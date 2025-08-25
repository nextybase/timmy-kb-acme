# src/adapters/content_fallbacks.py
"""
Adapter: fallback uniformi per contenuti GitBook/HonKit (README.md, SUMMARY.md).

Obiettivo:
- Centralizzare la logica di ripiego fuori dagli orchestratori.
- API pulita: ensure_readme_summary(context, logger, *, force=False).
- Nessun side-effect oltre a scritture atomiche dei file target.

Comportamento:
- ensure_readme_summary(context, logger, force=False)
  - Verifica l'esistenza/leggibilità di README.md e SUMMARY.md in book/.
  - Se mancano o sono vuoti (o force=True), genera versioni minime ma utili.
  - Non sovrascrive file non vuoti (a meno di force=True).
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import sorted_paths, ensure_within

__all__ = [
    "ensure_readme_summary",
    "build_summary_index",
    "build_default_readme",
]


# ------------------------------
# Helpers di costruzione contenuti
# ------------------------------
def build_default_readme(slug: str) -> str:
    """Ritorna un README minimale ma informativo."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"# Knowledge Base – {slug}\n\n"
        f"Generato il {ts}\n\n"
        "Raccolta generata a partire da PDF in `raw/` con arricchimento semantico opzionale.\n"
        "La navigazione è disponibile tramite `SUMMARY.md`.\n"
    )


def _title_from_filename(name: str) -> str:
    """Ricava un titolo umano dal filename, senza estensione."""
    base = Path(name).stem
    pretty = re.sub(r"[_\\/-]+", " ", base).strip()
    return pretty[:1].upper() + pretty[1:] if pretty else (base or "Documento")


def build_summary_index(book_dir: Path) -> str:
    """Costruisce un SOMMARIO minimale elencando i .md (esclusi README/SUMMARY)."""
    md_files = [
        p for p in sorted_paths(book_dir.glob("*.md"), base=book_dir)
        if p.name.lower() not in ("readme.md", "summary.md")
    ]
    lines = ["# Summary\n"]
    for p in md_files:
        title = _title_from_filename(p.name)
        lines.append(f"- [{title}]({p.name})")
    return "\n".join(lines) + "\n"  # newline finale per convenzione


# ------------------------------
# API principale per orchestratori
# ------------------------------
def ensure_readme_summary(context: Any, logger, *, force: bool = False) -> None:
    """
    Garantisce la presenza di README.md e SUMMARY.md in `book/` con fallback uniformi.

    - Se i file esistono e non sono vuoti: non fa nulla (a meno di force=True).
    - Se mancano o sono vuoti: genera contenuti minimi standardizzati (scrittura atomica).
    """
    # Risoluzione directory book/ (priorità: context.md_dir → context.base_dir/'book' → repo_root_dir/'book')
    md_dir = getattr(context, "md_dir", None)
    base_dir = getattr(context, "base_dir", None)
    repo_root = getattr(context, "repo_root_dir", None)

    if isinstance(md_dir, Path):
        book_dir = md_dir
        # se abbiamo la base, vincoliamo il perimetro di sicurezza alla sandbox cliente
        if isinstance(base_dir, Path):
            ensure_within(base_dir, book_dir)
    elif isinstance(base_dir, Path):
        book_dir = base_dir / "book"
        ensure_within(base_dir, book_dir)
    elif isinstance(repo_root, Path):
        book_dir = repo_root / "book"
        ensure_within(repo_root, book_dir)
    else:
        raise ConfigError("Contesto privo di percorsi utili: servono md_dir o base_dir o repo_root_dir.")

    slug = getattr(context, "slug", None) or "kb"
    book_dir.mkdir(parents=True, exist_ok=True)

    readme_path = book_dir / "README.md"
    summary_path = book_dir / "SUMMARY.md"

    # README
    needs_readme = force or (not readme_path.exists()) or (readme_path.stat().st_size == 0)
    if needs_readme:
        content = build_default_readme(slug)
        ensure_within(book_dir, readme_path)
        safe_write_text(readme_path, content, encoding="utf-8", atomic=True)
        logger.info("README.md generato (fallback)", extra={"file_path": str(readme_path)})

    # SUMMARY
    needs_summary = force or (not summary_path.exists()) or (summary_path.stat().st_size == 0)
    if needs_summary:
        content = build_summary_index(book_dir)
        ensure_within(book_dir, summary_path)
        safe_write_text(summary_path, content, encoding="utf-8", atomic=True)
        logger.info("SUMMARY.md generato (fallback)", extra={"file_path": str(summary_path)})

    if not needs_readme and not needs_summary and not force:
        logger.debug("README.md e SUMMARY.md già presenti: nessuna azione.")
