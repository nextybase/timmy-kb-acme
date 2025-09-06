from __future__ import annotations

from pathlib import Path
from typing import Protocol, Iterable

from pipeline.exceptions import PipelineError
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.path_utils import ensure_within  # SSoT path-safety

__all__ = [
    "validate_markdown_dir",
    "generate_readme_markdown",
    "generate_summary_markdown",
    "convert_files_to_structured_markdown",
]


class _Context(Protocol):
    """Protocollo locale minimo richiesto da queste utilità Markdown.

    Richiede solo i campi usati: `base_dir`, `md_dir`, `raw_dir`, `slug`.
    """

    base_dir: Path
    md_dir: Path
    raw_dir: Path
    slug: str | None


# -----------------------------
# Helpers
# -----------------------------


def _titleize(name: str) -> str:
    """Titolo leggibile da nome file/cartella."""
    parts = name.replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else name


def _ensure_safe(base_dir: Path, candidate: Path) -> Path:
    """
    Wrapper locale che delega la guardia STRONG a `ensure_within` (SSoT)
    e restituisce il path risolto. Mantiene la semantica di errore del modulo
    convertendo in `PipelineError` per coerenza con i call-site esistenti.
    """
    try:
        ensure_within(base_dir, candidate)
    except Exception as e:
        raise PipelineError(f"Unsafe directory: {candidate}") from e
    return Path(candidate).resolve()


# ---- Helpers estratti per leggibilità --------------------------------------
def _sorted_pdfs(cat_dir: Path) -> list[Path]:
    return sorted(cat_dir.rglob("*.pdf"), key=lambda p: p.as_posix().lower())


def _append_folder_headings(
    lines: list[str], folder_parts: Iterable[str], *, emitted: set[tuple[int, str]]
) -> None:
    for depth, folder in enumerate(folder_parts):
        level = 2 + depth
        key = (depth, folder.lower())
        if key not in emitted:
            lines += ["", f"{'#' * level} {_titleize(folder)}"]
            emitted.add(key)


def _append_pdf_section(lines: list[str], file_stem: str, *, level: int, filename: str) -> None:
    lines += [
        f"{'#' * level} {_titleize(file_stem)}",
        f"(Contenuto estratto/conversione da `{filename}`)",
    ]


# -----------------------------
# API
# -----------------------------


def validate_markdown_dir(ctx: _Context, md_dir: Path | None = None) -> Path:
    """
    Verifica che la cartella markdown esista, sia una directory e sia "safe"
    rispetto a ctx.base_dir. Ritorna il Path risolto se valida.
    """
    # Evita passaggi di Path|None a Path(...)
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)

    if not target.exists():
        raise PipelineError(f"Markdown directory does not exist: {target}")
    if not target.is_dir():
        raise PipelineError(f"Markdown path is not a directory: {target}")
    return target


def generate_readme_markdown(ctx: _Context, md_dir: Path | None = None) -> Path:
    """
    Crea (o sovrascrive) README.md nella cartella markdown target.
    I test verificano solo l'esistenza del file.
    """
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)
    target.mkdir(parents=True, exist_ok=True)

    title = getattr(ctx, "slug", None) or "Knowledge Base"
    readme = target / "README.md"
    safe_write_text(
        readme,
        f"# {title}\n\n" "Contenuti generati/curati automaticamente.\n",
        encoding="utf-8",
        atomic=True,
    )
    return readme


def generate_summary_markdown(ctx: _Context, md_dir: Path | None = None) -> Path:
    """
    Genera SUMMARY.md elencando i .md nella cartella target
    (escludendo README.md e SUMMARY.md).
    """
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)
    target.mkdir(parents=True, exist_ok=True)

    summary = target / "SUMMARY.md"
    items: list[str] = []
    for p in sorted(target.glob("*.md"), key=lambda p: p.name.lower()):
        name = p.name.lower()
        if name in {"readme.md", "summary.md"}:
            continue
        items.append(f"- [{p.stem}]({p.name})")

    safe_write_text(
        summary, "# Summary\n\n" + "\n".join(items) + "\n", encoding="utf-8", atomic=True
    )
    return summary


def convert_files_to_structured_markdown(ctx: _Context, md_dir: Path | None = None) -> None:
    """
    Per ogni sotto-cartella diretta di ctx.raw_dir (categoria) crea un file
    <categoria>.md dentro md_dir con struttura:

      - H1: nome categoria (capitalizzato)
      - Heading per ogni livello di sottocartella (H2 = livello 0, H3 = livello 1, ...)
      - Heading del PDF a livello (2 + depth) e riga placeholder di contenuto

    Se una categoria non contiene PDF, scrive una riga informativa.
    """
    base = ctx.base_dir
    raw_root = ctx.raw_dir
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir

    # sicurezza percorso per target e raw_root (usa i path risolti)
    target = _ensure_safe(base, target_input)
    raw_root = _ensure_safe(base, raw_root)

    target.mkdir(parents=True, exist_ok=True)

    if not raw_root.exists():
        raise PipelineError(f"Raw directory does not exist: {raw_root}")
    if not raw_root.is_dir():
        raise PipelineError(f"Raw path is not a directory: {raw_root}")

    # categorie = sole directory immediate sotto raw/
    categories = sorted((d for d in raw_root.iterdir() if d.is_dir()), key=lambda d: d.name.lower())

    for cat_dir in categories:
        cat_name = cat_dir.name
        md_file = target / f"{cat_name}.md"

        lines: list[str] = [f"# {_titleize(cat_name)}"]

        # tutti i PDF ricorsivi nella categoria
        pdfs = _sorted_pdfs(cat_dir)
        if not pdfs:
            lines += ["", "_Nessun PDF trovato in questa categoria._"]
        else:
            # Evita heading duplicati per le stesse sottocartelle
            emitted_folders: set[tuple[int, str]] = set()

            for pdf in pdfs:
                rel_parts = list(
                    pdf.relative_to(cat_dir).parts
                )  # es. "2024/Q4/doc1.pdf" o "doc2.pdf"
                folder_parts = rel_parts[:-1]
                _append_folder_headings(lines, folder_parts, emitted=emitted_folders)

                # heading del PDF
                file_stem = Path(rel_parts[-1]).stem  # es. "doc1"
                level = 2 + max(0, len(folder_parts))  # depth=0 -> H2, depth=2 -> H4
                _append_pdf_section(lines, file_stem, level=level, filename=rel_parts[-1])

        safe_write_text(md_file, "\n".join(lines) + "\n", encoding="utf-8", atomic=True)
