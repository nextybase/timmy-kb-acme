# src/pipeline/content_utils.py
"""
Utility per generare e validare i Markdown a partire dai PDF in `raw/` nella
pipeline Timmy-KB.

Cosa fa questo modulo
---------------------
- Converte i PDF organizzati in sottocartelle (anche annidate) in file `.md`
  **aggregati per categoria top-level** sotto `book/`, preservando la gerarchia
  con intestazioni Markdown.
- Salta la rigenerazione se non ci sono cambiamenti (fingerprint dell’albero PDF).
- Genera `SUMMARY.md` e `README.md` nella cartella `book/`.
- Applica **path-safety STRONG** (`ensure_within`) e scritture **atomiche**
  (SSoT) con `safe_write_text`.
- Niente `print()`: solo logging strutturato.

Note implementative
-------------------
- Le write usano sempre `pipeline.file_utils.safe_write_text` (no wrapper legacy).
- I nomi dei file `SUMMARY.md` e `README.md` provengono da `pipeline.constants`.
- Concorrenza a grana grossa per categoria (configurabile).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

from pipeline.logging_utils import get_structured_logger
from pipeline.file_utils import safe_write_text  # ✅ SSoT scrittura atomica
from pipeline.exceptions import PipelineError, InputDirectoryMissing
from pipeline.context import ClientContext
from pipeline.path_utils import ensure_within, sanitize_filename  # STRONG + sanitizzazione
from pipeline import constants as _C  # per nomi file e default

# Logger di modulo (fallback). Le funzioni preferiscono un logger contestualizzato.
logger = get_structured_logger("pipeline.content_utils")

# ----------------------------
# Default di concorrenza/skip
# ----------------------------
DEFAULT_SKIP_IF_UNCHANGED: bool = True
DEFAULT_MAX_WORKERS: int = 4


def _titleize(name: str) -> str:
    """Converte un nome cartella/file in un titolo leggibile."""
    base = name.rsplit(".", 1)[0]
    return " ".join(part.capitalize() for part in base.replace("_", " ").replace("-", " ").split())


def _ensure_heading_stack(
    current_depth: int,
    desired_depth: int,
    headings: List[str],
    parts: List[str],
) -> List[str]:
    """Garantisce le intestazioni fino a `desired_depth` incluso."""
    while current_depth <= desired_depth:
        title = _titleize(parts[current_depth - 1])
        level = "#" * (current_depth + 1)  # depth 1 => "##", depth 2 => "###", ...
        headings.append(f"{level} {title}\n")
        current_depth += 1
    return headings


def _fingerprint_category(category: Path) -> str:
    """Fingerprint deterministico basato su (path relativo, mtime_ns, size) dei PDF."""
    parts: List[str] = []
    for pdf in sorted(category.rglob("*.pdf")):
        try:
            st = pdf.stat()
            rel = pdf.relative_to(category).as_posix()
            parts.append(f"{rel}|{st.st_mtime_ns}|{st.st_size}")
        except FileNotFoundError:
            continue
    src = "\n".join(parts) if parts else "EMPTY"
    return sha256(src.encode("utf-8")).hexdigest()


def _build_category_markdown(category: Path) -> str:
    """Costruisce il contenuto markdown per una singola categoria (senza I/O)."""
    content_parts: List[str] = [f"# {_titleize(category.name)}\n\n"]

    pdf_files = sorted(category.rglob("*.pdf"))
    last_parts: List[str] = []

    if not pdf_files:
        content_parts.append("_Nessun PDF trovato in questa categoria._\n")
    else:
        for pdf_path in pdf_files:
            rel = pdf_path.parent.relative_to(category)  # path rispetto alla categoria
            parts = list(rel.parts) if rel.parts else []

            # Intestazioni gerarchiche per sottocartelle (stampate solo se cambiano)
            heading_stack: List[str] = []
            current_depth = 1
            desired_depth = len(parts)
            if desired_depth > 0 and parts != last_parts:
                heading_stack = _ensure_heading_stack(current_depth, desired_depth, heading_stack, parts)
                last_parts = parts

            # Titolo del PDF
            pdf_title = _titleize(pdf_path.name)
            pdf_level = "#" * (desired_depth + 2)  # depth 0 => "##"
            heading_line = ("## " + pdf_title + "\n") if desired_depth == 0 else f"{pdf_level} {pdf_title}\n"

            if heading_stack:
                content_parts.extend(heading_stack)
            content_parts.append(heading_line)
            content_parts.append(f"(Contenuto estratto/conversione da `{pdf_path.name}`)\n\n")

    return "".join(content_parts)


def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
    *,
    skip_if_unchanged: Optional[bool] = None,
    max_workers: Optional[int] = None,
) -> None:
    """Converte i PDF in `raw/` in file Markdown aggregati per categoria top-level."""
    raw_dir = Path(raw_dir or context.raw_dir)
    md_dir = Path(md_dir or context.md_dir)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    # Parametri: prova a leggere da constants, altrimenti fallback
    if skip_if_unchanged is None:
        skip_if_unchanged = bool(getattr(_C, "SKIP_IF_UNCHANGED", DEFAULT_SKIP_IF_UNCHANGED))
    if max_workers is None:
        max_workers = int(getattr(_C, "MAX_CONCURRENCY", DEFAULT_MAX_WORKERS))

    # STRONG guard: RAW e MD devono stare nella base cliente
    try:
        ensure_within(context.base_dir, raw_dir)
        ensure_within(context.base_dir, md_dir)
    except Exception as e:
        raise PipelineError(
            f"Path non sicuro per conversione: {e}",
            slug=context.slug,
            file_path=str(raw_dir if not raw_dir.is_relative_to(context.base_dir) else md_dir),  # best-effort
        )

    if not raw_dir.exists():
        local_logger.error("La cartella raw non esiste", extra={"slug": context.slug, "file_path": str(raw_dir)})
        raise InputDirectoryMissing(f"La cartella raw non esiste: {raw_dir}", slug=context.slug, file_path=raw_dir)
    if not raw_dir.is_dir():
        local_logger.error("Il path raw non è una directory", extra={"slug": context.slug, "file_path": str(raw_dir)})
        raise InputDirectoryMissing(f"Il path raw non è una directory: {raw_dir}", slug=context.slug, file_path=raw_dir)

    md_dir.mkdir(parents=True, exist_ok=True)

    # Ogni sottocartella immediata di raw/ è una categoria che genera un .md
    categories = sorted([p for p in raw_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    def _process(category: Path) -> tuple[Path, str, str]:
        content = _build_category_markdown(category)
        fp = _fingerprint_category(category)
        return (category, content, fp)

    results: list[tuple[Path, str, str]] = []
    if (max_workers or 0) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for out in ex.map(_process, categories):
                results.append(out)
    else:
        for c in categories:
            results.append(_process(c))

    # Scrittura risultati in ordine deterministico, con skip opzionale
    for category, content, fp in sorted(results, key=lambda x: x[0].name.lower()):
        safe_name = sanitize_filename(category.name)
        md_path = md_dir / f"{safe_name}.md"
        fp_path = md_path.with_suffix(md_path.suffix + ".fp")

        # STRONG: validare gli output prima di scrivere
        try:
            ensure_within(md_dir, md_path)
            ensure_within(md_dir, fp_path)
        except Exception as e:
            local_logger.error(
                "Path di output non sicuro (fuori dal book dir)",
                extra={"slug": context.slug, "file_path": str(md_path), "error": str(e)},
            )
            raise PipelineError(f"Path di output non sicuro per {md_path}", slug=context.slug, file_path=md_path)

        try:
            # Skip se fingerprint invariato
            if skip_if_unchanged and fp_path.exists():
                try:
                    old_fp = fp_path.read_text(encoding="utf-8").strip()
                except Exception:
                    old_fp = ""
                if old_fp == fp:
                    local_logger.info(
                        "Skip generazione: nessuna modifica",
                        extra={"slug": context.slug, "file_path": str(md_path)},
                    )
                    continue

            local_logger.info(
                "Creazione file markdown aggregato",
                extra={"slug": context.slug, "file_path": str(md_path)},
            )
            # ✅ scritture atomiche (SSoT)
            safe_write_text(md_path, content, encoding="utf-8", atomic=True)
            safe_write_text(fp_path, fp + "\n", encoding="utf-8", atomic=True)

            local_logger.info(
                "File markdown scritto correttamente",
                extra={"slug": context.slug, "file_path": str(md_path)},
            )
        except Exception as e:
            local_logger.error(
                "Errore nella creazione markdown",
                extra={"slug": context.slug, "file_path": str(md_path), "error": str(e)},
            )
            raise PipelineError(str(e), slug=context.slug, file_path=md_path)


def generate_summary_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Genera `SUMMARY.md` in `md_dir` elencando tutti i `.md` (esclusi SUMMARY/README)."""
    md_dir = Path(md_dir or context.md_dir)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    try:
        ensure_within(context.base_dir, md_dir)
    except Exception as e:
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir} ({e})",
            slug=context.slug,
            file_path=md_dir,
        )

    summary_path = md_dir / _C.SUMMARY_MD_NAME
    try:
        ensure_within(md_dir, summary_path)
    except Exception as e:
        raise PipelineError(
            f"Path di output non sicuro per SUMMARY.md: {summary_path} ({e})",
            slug=context.slug,
            file_path=summary_path,
        )

    try:
        content = "# Summary\n\n"
        for md_file in sorted(md_dir.glob("*.md")):
            if md_file.name not in (_C.SUMMARY_MD_NAME, _C.README_MD_NAME):
                content += f"- [{md_file.stem}]({md_file.name})\n"

        local_logger.info("Generazione SUMMARY.md", extra={"slug": context.slug, "file_path": str(summary_path)})
        safe_write_text(summary_path, content, encoding="utf-8", atomic=True)
        local_logger.info("SUMMARY.md generato con successo", extra={"slug": context.slug, "file_path": str(summary_path)})
    except Exception as e:
        local_logger.error("Errore generazione SUMMARY.md", extra={"slug": context.slug, "file_path": str(summary_path), "error": str(e)})
        raise PipelineError(str(e), slug=context.slug, file_path=summary_path)


def generate_readme_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Genera `README.md` in `md_dir`."""
    md_dir = Path(md_dir or context.md_dir)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    try:
        ensure_within(context.base_dir, md_dir)
    except Exception as e:
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir} ({e})",
            slug=context.slug,
            file_path=md_dir,
        )

    readme_path = md_dir / _C.README_MD_NAME
    try:
        ensure_within(md_dir, readme_path)
    except Exception as e:
        raise PipelineError(
            f"Path di output non sicuro per README.md: {readme_path} ({e})",
            slug=context.slug,
            file_path=readme_path,
        )

    try:
        content = "# Documentazione Timmy-KB\n"
        local_logger.info("Generazione README.md", extra={"slug": context.slug, "file_path": str(readme_path)})
        safe_write_text(readme_path, content, encoding="utf-8", atomic=True)
        local_logger.info("README.md generato con successo", extra={"slug": context.slug, "file_path": str(readme_path)})
    except Exception as e:
        local_logger.error("Errore generazione README.md", extra={"slug": context.slug, "file_path": str(readme_path), "error": str(e)})
        raise PipelineError(str(e), slug=context.slug, file_path=readme_path)


def validate_markdown_dir(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Verifica che la directory Markdown esista e sia valida.

    Raises:
        InputDirectoryMissing: se la cartella non esiste o non è una directory.
        PipelineError: se il path è fuori dalla base consentita.
    """
    md_dir = Path(md_dir or context.md_dir)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    try:
        ensure_within(context.base_dir, md_dir)
    except Exception as e:
        raise PipelineError(
            f"Tentativo di accedere a un path non sicuro: {md_dir} ({e})",
            slug=context.slug,
            file_path=md_dir,
        )

    if not md_dir.exists():
        local_logger.error("La cartella markdown non esiste", extra={"slug": context.slug, "file_path": str(md_dir)})
        raise InputDirectoryMissing(f"La cartella markdown non esiste: {md_dir}", slug=context.slug, file_path=md_dir)
    if not md_dir.is_dir():
        local_logger.error("Il path non è una directory", extra={"slug": context.slug, "file_path": str(md_dir)})
        raise InputDirectoryMissing(f"Il path non è una directory: {md_dir}", slug=context.slug, file_path=md_dir)
