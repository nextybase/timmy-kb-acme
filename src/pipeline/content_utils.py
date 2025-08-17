# src/pipeline/content_utils.py

"""
src/pipeline/content_utils.py

Utility per la generazione e validazione di file markdown a partire da PDF raw,
nell'ambito della pipeline Timmy-KB.

Aggiornamenti:
- Conversione ora supporta strutture annidate (ricorsione). L'output rimane
  un file .md per ciascuna categoria top-level in raw/, ma le sezioni interne
  rispecchiano la gerarchia delle sottocartelle.
"""

import logging
from pathlib import Path
from typing import Optional, List

from pipeline.logging_utils import get_structured_logger
from pipeline.config_utils import safe_write_file  # ✅ Standard v1.0 stable
from pipeline.exceptions import PipelineError
from pipeline.context import ClientContext
from pipeline.path_utils import is_safe_subpath  # ✅ Controllo sicurezza path

logger = get_structured_logger("pipeline.content_utils")


def _titleize(name: str) -> str:
    """Converte un nome cartella/file in un titolo leggibile."""
    # Rimuove estensione, sostituisce separatori con spazio e capitalizza
    base = name.rsplit(".", 1)[0]
    return " ".join(part.capitalize() for part in base.replace("_", " ").replace("-", " ").split())


def _ensure_heading_stack(current_depth: int, desired_depth: int, headings: List[str], parts: List[str]) -> List[str]:
    """
    Garantisce che l'array di headings contenga le intestazioni fino a desired_depth,
    utilizzando i nomi in `parts`. Restituisce la lista aggiornata.
    Esempio: depth 1 => "## 2023", depth 2 => "### Q4", etc.
    """
    while current_depth < desired_depth:
        title = _titleize(parts[current_depth - 1])
        level = "#" * (current_depth + 1)  # depth 1 => "##", depth 2 => "###"
        headings.append(f"{level} {title}\n")
        current_depth += 1
    return headings


def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """
    Converte i PDF presenti nella cartella raw in file markdown univoci per categoria top-level.
    Supporta ora strutture annidate: le sezioni nel .md riflettono la gerarchia di sottocartelle.

    Args:
        context (ClientContext): contesto cliente con path e config.
        raw_dir (Path, opzionale): path alternativo alla cartella raw del contesto.
        md_dir (Path, opzionale): path alternativo alla cartella markdown.
        log (logger, opzionale): logger alternativo.

    Raises:
        PipelineError: se path non sicuro o errore in scrittura file.
    """
    raw_dir = raw_dir or context.raw_dir
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    # Ogni sottocartella immediata di raw/ è una "categoria" che genera un .md
    categories = [p for p in raw_dir.iterdir() if p.is_dir()]
    for category in categories:
        md_path = md_dir / f"{category.name}.md"
        try:
            # Header principale del file per la categoria
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

                    # Costruisci (se mancano) le intestazioni per i livelli di profondità correnti
                    heading_stack: List[str] = []
                    current_depth = 1  # prima sottocartella => "##"
                    desired_depth = len(parts)
                    if desired_depth > 0:
                        heading_stack = _ensure_heading_stack(current_depth, desired_depth, heading_stack, parts)

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
                    # Placeholder per contenuto estratto/conversione (da estendere con OCR/estrazione vera)
                    content_parts.append(f"(Contenuto estratto/conversione da `{pdf_path.name}`)\n\n")

            # Scrivi file
            local_logger.info(f"Creazione file markdown aggregato: {md_path}",
                              extra={"slug": context.slug, "file_path": md_path})
            safe_write_file(md_path, "".join(content_parts))
            local_logger.info(f"File markdown scritto correttamente: {md_path}",
                              extra={"slug": context.slug, "file_path": md_path})
        except Exception as e:
            local_logger.error(f"Errore nella creazione markdown {md_path}: {e}",
                               extra={"slug": context.slug, "file_path": md_path})
            raise PipelineError(str(e), slug=context.slug, file_path=md_path)


def generate_summary_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Genera il file SUMMARY.md nella directory markdown."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    summary_path = md_dir / "SUMMARY.md"
    try:
        content = "# Summary\n\n"
        for md_file in sorted(md_dir.glob("*.md")):
            if md_file.name not in ("SUMMARY.md", "README.md"):
                content += f"* [{md_file.stem}]({md_file.name})\n"

        local_logger.info(f"Generazione SUMMARY.md in {summary_path}",
                          extra={"slug": context.slug, "file_path": summary_path})
        safe_write_file(summary_path, content)
        local_logger.info("SUMMARY.md generato con successo.",
                          extra={"slug": context.slug, "file_path": summary_path})
    except Exception as e:
        local_logger.error(f"Errore generazione SUMMARY.md: {e}",
                           extra={"slug": context.slug, "file_path": summary_path})
        raise PipelineError(str(e), slug=context.slug, file_path=summary_path)


def generate_readme_markdown(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Genera il file README.md nella directory markdown."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di scrivere file in path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    readme_path = md_dir / "README.md"
    try:
        content = "# Documentazione Timmy-KB\n"
        local_logger.info(f"Generazione README.md in {readme_path}",
                          extra={"slug": context.slug, "file_path": readme_path})
        safe_write_file(readme_path, content)
        local_logger.info("README.md generato con successo.",
                          extra={"slug": context.slug, "file_path": readme_path})
    except Exception as e:
        local_logger.error(f"Errore generazione README.md: {e}",
                           extra={"slug": context.slug, "file_path": readme_path})
        raise PipelineError(str(e), slug=context.slug, file_path=readme_path)


def validate_markdown_dir(
    context: ClientContext,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None
):
    """Verifica che la directory markdown esista e sia valida."""
    md_dir = md_dir or context.md_dir
    local_logger = log or logger

    if not is_safe_subpath(md_dir, context.base_dir):
        raise PipelineError(f"Tentativo di accedere a un path non sicuro: {md_dir}",
                            slug=context.slug, file_path=md_dir)

    if not md_dir.exists():
        local_logger.error(f"La cartella markdown non esiste: {md_dir}",
                           extra={"slug": context.slug, "file_path": md_dir})
        raise FileNotFoundError(f"La cartella markdown non esiste: {md_dir}")
    if not md_dir.is_dir():
        local_logger.error(f"Il path non è una directory: {md_dir}",
                           extra={"slug": context.slug, "file_path": md_dir})
        raise NotADirectoryError(f"Il path non è una directory: {md_dir}")
