# src/pipeline/content_utils.py
"""
Utility per la generazione e validazione di file Markdown a partire da PDF raw
nell'ambito della pipeline Timmy-KB.

Aggiornamenti:
- La conversione supporta strutture annidate (ricorsione). L'output rimane
  un file `.md` per ciascuna categoria top-level in `raw/`, ma le sezioni interne
  rispecchiano la gerarchia delle sottocartelle.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import safe_write_file  # ✅ Standard v1.0 stable
from pipeline.exceptions import PipelineError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # ✅ Controllo sicurezza path
from pipeline.path_utils import sanitize_filename  # ✅ Sanitizzazione nomi file

# ✅ quick win: usa eccezioni dominio per input directory mancanti/non valide
from pipeline.exceptions import InputDirectoryMissing

logger = get_structured_logger("pipeline.content_utils")


def _titleize(name: str) -> str:
    """Converte un nome cartella/file in un titolo leggibile.

    Operazioni:
      - rimuove l'estensione
      - sostituisce `_` e `-` con spazio
      - capitalizza ogni parola
    """
    base = name.rsplit(".", 1)[0]
    return " ".join(part.capitalize() for part in base.replace("_", " ").replace("-", " ").split())


def _ensure_heading_stack(
    current_depth: int,
    desired_depth: int,
    headings: List[str],
    parts: List[str],
) -> List[str]:
    """Garantisce le intestazioni fino a `desired_depth` **incluso**.

    Esempio: parts=['2024','Q4'] -> depth 1 => '## 2024', depth 2 => '### Q4'.
    """
    while current_depth <= desired_depth:
        title = _titleize(parts[current_depth - 1])
        level = "#" * (current_depth + 1)  # depth 1 => "##", depth 2 => "###", ...
        headings.append(f"{level} {title}\n")
        current_depth += 1
    return headings


def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Converte i PDF in `raw/` in file Markdown univoci per categoria top-level.

    Supporta strutture annidate: le sezioni nel `.md` riflettono la gerarchia di
    sottocartelle relative alla categoria.
    """
    raw_dir = raw_dir or context.raw_dir
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    # 🔒 Guard-rail anche su RAW (coerente con md_dir)
    if not is_safe_subpath(raw_dir, context.base_dir):
        raise PipelineError(
            f"Tentativo di leggere da un path non sicuro: {raw_dir}",
            slug=context.slug,
            file_path=raw_dir,
        )
    if not raw_dir.exists():
        local_logger.error(
            f"La cartella raw non esiste: {raw_dir}",
            extra={"slug": context.slug, "file_path": raw_dir},
        )
        # ✅ dominio: directory mancante
        raise InputDirectoryMissing(f"La cartella raw non esiste: {raw_dir}", slug=context.slug, file_path=raw_dir)
    if not raw_dir.is_dir():
        local_logger.error(
            f"Il path raw non è una directory: {raw_dir}",
            extra={"slug": context.slug, "file_path": raw_dir},
        )
        # ✅ dominio: path non directory
        raise InputDirectoryMissing(f"Il path raw non è una directory: {raw_dir}", slug=context.slug, file_path=raw_dir)

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )
    md_dir.mkdir(parents=True, exist_ok=True)

    # Ogni sottocartella immediata di raw/ è una "categoria" che genera un .md
    categories = [p for p in raw_dir.iterdir() if p.is_dir()]
    for category in categories:
        safe_name = sanitize_filename(category.name)  # ✅ usa nome sanificato per il file .md
        md_path = md_dir / f"{safe_name}.md"
        try:
            # Header principale del file per la categoria (titolo leggibile → dall'originale)
            content_parts: List[str] = [f"# {_titleize(category.name)}\n\n"]

            # Trova TUTTI i PDF annidati dentro la categoria (ricorsivo)
            pdf_files = sorted(category.rglob("*.pdf"))

            # Se non ci sono PDF sotto questa categoria, scrivi comunque un placeholder
            if not pdf_files:
                content_parts.append("_Nessun PDF trovato in questa categoria._\n")
            else:
                # Manteniamo le sezioni in base al percorso relativo dentro la categoria
                # Esempio: RAW/Contratti/2023/Q4/doc.pdf
                #   -> ## 2023
                #      ### Q4
                #      #### doc.pdf
                for pdf_path in pdf_files:
                    rel = pdf_path.parent.relative_to(category)  # path rispetto alla categoria
                    parts = list(rel.parts) if rel.parts else []

                    # Costruisci (se mancano) le intestazioni per tutti i livelli
                    heading_stack: List[str] = []
                    current_depth = 1  # prima sottocartella => "##"
                    desired_depth = len(parts)
                    if desired_depth > 0:
                        heading_stack = _ensure_heading_stack(
                            current_depth, desired_depth, heading_stack, parts
                        )

                    # Titolo del PDF come sezione terminale
                    pdf_title = _titleize(pdf_path.name)
                    pdf_level = "#" * (desired_depth + 2)  # se depth=0 => "##", se 1 => "###", etc.
                    # Evita duplicazione di heading se non ci sono sottocartelle (desired_depth == 0)
                    if desired_depth == 0:
                        heading_line = "## " + pdf_title + "\n"
                    else:
                        heading_line = f"{pdf_level} {pdf_title}\n"

                    # Assembla blocco
                    if heading_stack:
                        content_parts.extend(heading_stack)
                    content_parts.append(heading_line)
                    # Placeholder contenuto estratto (da estendere con OCR/estrazione vera)
                    content_parts.append(f"(Contenuto estratto/conversione da `{pdf_path.name}`)\n\n")

            # Scrivi file
            local_logger.info(
                f"Creazione file markdown aggregato: {md_path}",
                extra={"slug": context.slug, "file_path": md_path},
            )
            safe_write_file(md_path, "".join(content_parts))
            local_logger.info(
                f"File markdown scritto correttamente: {md_path}",
                extra={"slug": context.slug, "file_path": md_path},
            )
        except Exception as e:
            local_logger.error(
                f"Errore nella creazione markdown {md_path}: {e}",
                extra={"slug": context.slug, "file_path": md_path},
            )
            raise PipelineError(str(e), slug=context.slug, file_path=md_path)


def generate_summary_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Genera il file `SUMMARY.md` nella directory Markdown.

    Elenca tutti i file `.md` (esclusi `SUMMARY.md` e `README.md`) presenti
    in `md_dir`, creando voci di indice in formato GitBook/Honkit.
    """
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )

    summary_path = md_dir / "SUMMARY.md"
    try:
        content = "# Summary\n\n"
        for md_file in sorted(md_dir.glob("*.md")):
            if md_file.name not in ("SUMMARY.md", "README.md"):
                content += f"* [{md_file.stem}]({md_file.name})\n"

        local_logger.info(
            f"Generazione SUMMARY.md in {summary_path}",
            extra={"slug": context.slug, "file_path": summary_path},
        )
        safe_write_file(summary_path, content)
        local_logger.info(
            "SUMMARY.md generato con successo.",
            extra={"slug": context.slug, "file_path": summary_path},
        )
    except Exception as e:
        local_logger.error(
            f"Errore generazione SUMMARY.md: {e}",
            extra={"slug": context.slug, "file_path": summary_path},
        )
        raise PipelineError(str(e), slug=context.slug, file_path=summary_path)


def generate_readme_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
) -> None:
    """Genera il file `README.md` nella directory Markdown."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )

    readme_path = md_dir / "README.md"
    try:
        content = "# Documentazione Timmy-KB\n"
        local_logger.info(
            f"Generazione README.md in {readme_path}",
            extra={"slug": context.slug, "file_path": readme_path},
        )
        safe_write_file(readme_path, content)
        local_logger.info(
            "README.md generato con successo.",
            extra={"slug": context.slug, "file_path": readme_path},
        )
    except Exception as e:
        local_logger.error(
            f"Errore generazione README.md: {e}",
            extra={"slug": context.slug, "file_path": readme_path},
        )
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
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(
            f"Tentativo di accedere a un path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )

    if not md_dir.exists():
        local_logger.error(
            f"La cartella markdown non esiste: {md_dir}",
            extra={"slug": context.slug, "file_path": md_dir},
        )
        # ✅ dominio: directory mancante
        raise InputDirectoryMissing(f"La cartella markdown non esiste: {md_dir}", slug=context.slug, file_path=md_dir)
    if not md_dir.is_dir():
        local_logger.error(
            f"Il path non è una directory: {md_dir}",
            extra={"slug": context.slug, "file_path": md_dir},
        )
        # ✅ dominio: path non directory
        raise InputDirectoryMissing(f"Il path non è una directory: {md_dir}", slug=context.slug, file_path=md_dir)
