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

# --- Nuovi import minimali (non impattano le firme esistenti) ---
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor

# Logger di modulo (fallback). Il default in funzione userà quello contestualizzato.
logger = get_structured_logger("pipeline.content_utils")

# ----------------------------
# Default di concorrenza/skip
# ----------------------------
DEFAULT_SKIP_IF_UNCHANGED: bool = True
DEFAULT_MAX_WORKERS: int = 4


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


def _fingerprint_category(category: Path) -> str:
    """Calcola un fingerprint deterministico della categoria in base a albero PDF (path relativo+mtime+size)."""
    parts: List[str] = []
    for pdf in sorted(category.rglob("*.pdf")):
        try:
            st = pdf.stat()
            rel = pdf.relative_to(category).as_posix()
            parts.append(f"{rel}|{st.st_mtime_ns}|{st.st_size}")
        except FileNotFoundError:
            # file volatilizzato tra stat e uso: ignoriamo in modo resiliente
            continue
    src = "\n".join(parts) if parts else "EMPTY"
    return sha256(src.encode("utf-8")).hexdigest()


def _build_category_markdown(category: Path) -> str:
    """Costruisce il contenuto markdown per una singola categoria (senza I/O su md_path)."""
    content_parts: List[str] = [f"# {_titleize(category.name)}\n\n"]

    # Trova TUTTI i PDF annidati dentro la categoria (ricorsivo), ordinati in modo deterministico
    pdf_files = sorted(category.rglob("*.pdf"))

    # NEW: evita di ristampare le stesse intestazioni di cartella per PDF consecutivi
    last_parts: List[str] = []

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
                # Stampa le intestazioni solo se cambiano rispetto al precedente PDF
                if parts != last_parts:
                    heading_stack = _ensure_heading_stack(
                        current_depth, desired_depth, heading_stack, parts
                    )
                    last_parts = parts  # aggiorna lo stato dell'ultima gerarchia emessa

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

    return "".join(content_parts)


def convert_files_to_structured_markdown(
    context: ClientContext,
    raw_dir: Optional[Path] = None,
    md_dir: Optional[Path] = None,
    log: Optional[logging.Logger] = None,
    *,
    # default "morbidi": leggili da constants se presenti; altrimenti fallback safe
    skip_if_unchanged: Optional[bool] = None,
    max_workers: Optional[int] = None,
) -> None:
    """Converte i PDF in `raw/` in file Markdown univoci per categoria top-level.

    Supporta strutture annidate: le sezioni nel `.md` riflettono la gerarchia di
    sottocartelle relative alla categoria.
    """
    # Cast sicuri a Path
    raw_dir = Path(raw_dir or context.raw_dir)
    md_dir = Path(md_dir or context.md_dir)
    # DEFAULT aggiornato: preferisci un logger contestualizzato (eredita redact_logs)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    # Parametri di tuning: prova a caricarli da constants se non specificati
    if skip_if_unchanged is None or max_workers is None:
        try:
            from pipeline import constants as _C  # import locale per evitare hard dependency
            if skip_if_unchanged is None:
                skip_if_unchanged = bool(getattr(_C, "SKIP_IF_UNCHANGED", DEFAULT_SKIP_IF_UNCHANGED))
            if max_workers is None:
                max_workers = int(getattr(_C, "MAX_CONCURRENCY", DEFAULT_MAX_WORKERS))
        except Exception:
            skip_if_unchanged = DEFAULT_SKIP_IF_UNCHANGED if skip_if_unchanged is None else skip_if_unchanged
            max_workers = DEFAULT_MAX_WORKERS if max_workers is None else max_workers

    # 🔒 Guard-rail anche su RAW (coerente con md_dir)
    if not is_safe_subpath(raw_dir, Path(context.base_dir)):
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

    if not is_safe_subpath(md_dir, Path(context.base_dir)):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )
    md_dir.mkdir(parents=True, exist_ok=True)

    # Ogni sottocartella immediata di raw/ è una "categoria" che genera un .md
    # Ordinamento deterministico sul nome della directory
    categories = sorted([p for p in raw_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    def _process(category: Path) -> tuple[Path, str, str]:
        # Costruzione contenuto e fingerprint calcolato sull'albero PDF
        content = _build_category_markdown(category)
        fp = _fingerprint_category(category)
        return (category, content, fp)

    results: list[tuple[Path, str, str]] = []

    # Concorrenza a grana grossa (per categoria), ma scrittura in ordine deterministico
    if (max_workers or 0) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for out in ex.map(_process, categories):
                results.append(out)
    else:
        for c in categories:
            results.append(_process(c))

    # Scrittura risultati in ordine deterministico, con skip opzionale
    for category, content, fp in sorted(results, key=lambda x: x[0].name.lower()):
        safe_name = sanitize_filename(category.name)  # ✅ usa nome sanificato per il file .md
        md_path = md_dir / f"{safe_name}.md"
        fp_path = md_path.with_suffix(md_path.suffix + ".fp")

        # 🔒 path-safety su ogni file di output
        if not is_safe_subpath(md_path, md_dir) or not is_safe_subpath(fp_path, md_dir):
            local_logger.error(
                "Path di output non sicuro (fuori dal book dir).",
                extra={"slug": context.slug, "file_path": md_path},
            )
            raise PipelineError(
                f"Path di output non sicuro per {md_path}",
                slug=context.slug,
                file_path=md_path,
            )

        try:
            # Skip se fingerprint invariato
            if skip_if_unchanged and fp_path.exists():
                try:
                    old_fp = fp_path.read_text(encoding="utf-8").strip()
                except Exception:
                    old_fp = ""
                if old_fp == fp:
                    local_logger.info(
                        f"Skip generazione: nessuna modifica per {md_path}",
                        extra={"slug": context.slug, "file_path": md_path},
                    )
                    continue

            # Header principale del file per la categoria (titolo leggibile → dall'originale)
            local_logger.info(
                f"Creazione file markdown aggregato: {md_path}",
                extra={"slug": context.slug, "file_path": md_path},
            )
            safe_write_file(md_path, content)
            # Aggiorna fingerprint sidecar (scrittura atomica)
            safe_write_file(fp_path, fp + "\n")
            local_logger.info(
                "File markdown scritto correttamente",
                extra={"slug": context.slug, "file_path": md_path},
            )
        except (OSError, ValueError) as e:
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
    md_dir = Path(md_dir or context.md_dir)
    # DEFAULT aggiornato: preferisci un logger contestualizzato (eredita redact_logs)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    if not is_safe_subpath(md_dir, Path(context.base_dir)):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )

    summary_path = md_dir / "SUMMARY.md"
    # 🔒 path-safety sull’output specifico
    if not is_safe_subpath(summary_path, md_dir):
        raise PipelineError(
            f"Path di output non sicuro per SUMMARY.md: {summary_path}",
            slug=context.slug,
            file_path=summary_path,
        )

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
    except OSError as e:
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
    md_dir = Path(md_dir or context.md_dir)
    # DEFAULT aggiornato: preferisci un logger contestualizzato (eredita redact_logs)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    if not is_safe_subpath(md_dir, Path(context.base_dir)):
        raise PipelineError(
            f"Tentativo di scrivere file in path non sicuro: {md_dir}",
            slug=context.slug,
            file_path=md_dir,
        )

    readme_path = md_dir / "README.md"
    # 🔒 path-safety sull’output specifico
    if not is_safe_subpath(readme_path, md_dir):
        raise PipelineError(
            f"Path di output non sicuro per README.md: {readme_path}",
            slug=context.slug,
            file_path=readme_path,
        )

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
    except OSError as e:
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
    md_dir = Path(md_dir or context.md_dir)
    # DEFAULT aggiornato: preferisci un logger contestualizzato (eredita redact_logs)
    local_logger = log or get_structured_logger("pipeline.content_utils", context=context)

    if not is_safe_subpath(md_dir, Path(context.base_dir)):
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
