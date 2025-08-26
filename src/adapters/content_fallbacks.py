# src/adapters/content_fallbacks.py
"""
Adapter: fallback uniformi per contenuti GitBook/HonKit (README.md, SUMMARY.md).

Scopo del modulo
----------------
Centralizza la generazione dei file minimi necessari alla navigazione della
knowledge base quando gli orchestratori non hanno (o non vogliono avere) logica
di presentazione. Le operazioni sono **idempotenti** e **atomiche**.

Funzioni esposte
----------------
- `build_default_readme(slug) -> str`  
  Restituisce un README.md minimale, informativo e timestamped.

- `build_summary_index(book_dir: Path) -> str`  
  Crea un SUMMARY.md che elenca i file Markdown nella cartella `book/`
  (escludendo README/SUMMARY), con titoli “umanizzati” a partire dai filename.

- `ensure_readme_summary(context, logger, *, force=False) -> None`  
  Verifica/garantisce la presenza di README.md e SUMMARY.md in `book/`.
  Se mancano o sono vuoti (o `force=True`), li (ri)genera con scrittura atomica.
  Esegue **path-safety STRONG** via `ensure_within(...)` prima delle scritture.

Note
----
- Nessuna I/O “lato utente” (niente `print()`); il chiamante passa un `logger`.
- I path del contesto possono essere `Path` **o** `str` (alcuni adapter li impostano
  come stringhe): questo modulo li accetta e li normalizza.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

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
    """Genera il contenuto di un README.md minimale per la KB di `slug`."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"# Knowledge Base – {slug}\n\n"
        f"Generato il {ts}\n\n"
        "Raccolta generata a partire da PDF in `raw/` con arricchimento semantico opzionale.\n"
        "La navigazione è disponibile tramite `SUMMARY.md`.\n"
    )


def _title_from_filename(name: str) -> str:
    """Ricava un titolo leggibile dal nome file (senza estensione)."""
    base = Path(name).stem
    pretty = re.sub(r"[_\\/-]+", " ", base).strip()
    return pretty[:1].upper() + pretty[1:] if pretty else (base or "Documento")


def build_summary_index(book_dir: Path) -> str:
    """
    Costruisce un indice minimale (SUMMARY.md) elencando i .md presenti in `book_dir`,
    esclusi README.md e SUMMARY.md. L’ordine è deterministico tramite `sorted_paths`.
    """
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
# Normalizzazione path dal contesto
# ------------------------------
def _as_path(value: Any) -> Optional[Path]:
    """Converte `value` in Path se è un Path o una stringa non vuota; altrimenti None."""
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value)
    return None


# ------------------------------
# API principale per orchestratori
# ------------------------------
def ensure_readme_summary(context: Any, logger: logging.Logger, *, force: bool = False) -> None:
    """
    Garantisce la presenza di README.md e SUMMARY.md in `book/` con fallback uniformi.

    Comportamento:
      - Se i file esistono e non sono vuoti → non fa nulla (a meno di `force=True`).
      - Se mancano o sono vuoti → genera contenuti minimi standardizzati (scrittura atomica).
      - Effettua **guardie STRONG** sui path prima di scrivere (via `ensure_within`).

    Args:
        context: oggetto che preferibilmente espone `md_dir`, `base_dir` o `repo_root_dir`
                 (accettati sia come `Path` che come `str`), e opzionalmente `slug`.
        logger:  logger strutturato per i messaggi di esito.
        force:   rigenera sempre i file, anche se presenti e non vuoti.
    """
    # Risoluzione directory book/ con tolleranza a Path/str
    md_dir = _as_path(getattr(context, "md_dir", None))
    base_dir = _as_path(getattr(context, "base_dir", None))
    repo_root = _as_path(getattr(context, "repo_root_dir", None))

    if md_dir is not None:
        book_dir = md_dir
        # se abbiamo la base, vincoliamo il perimetro di sicurezza alla sandbox cliente
        if base_dir is not None:
            ensure_within(base_dir, book_dir)
    elif base_dir is not None:
        book_dir = base_dir / "book"
        ensure_within(base_dir, book_dir)
    elif repo_root is not None:
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
