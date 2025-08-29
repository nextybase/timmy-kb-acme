from __future__ import annotations

from pathlib import Path

from pipeline.exceptions import PipelineError


# -----------------------------
# Helpers
# -----------------------------

def _titleize(name: str) -> str:
    """Titolo leggibile da nome file/cartella."""
    parts = name.replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else name


def _ensure_safe(base_dir: Path, candidate: Path) -> Path:
    """
    Ritorna candidate.resolve() se è sotto base_dir.resolve(),
    altrimenti solleva PipelineError (protezione path traversal).
    """
    base = Path(base_dir).resolve()
    cand = Path(candidate).resolve()
    try:
        cand.relative_to(base)
    except ValueError:
        raise PipelineError(f"Unsafe directory: {candidate}")
    return cand


# -----------------------------
# API
# -----------------------------

def validate_markdown_dir(ctx, md_dir: Path | None = None) -> Path:
    """
    Verifica che la cartella markdown esista, sia una directory e sia "safe"
    rispetto a ctx.base_dir. Ritorna il Path risolto se è valida.
    """
    target = Path(md_dir) if md_dir is not None else Path(ctx.md_dir)
    target = _ensure_safe(Path(ctx.base_dir), target)

    if not target.exists():
        raise PipelineError(f"Markdown directory does not exist: {target}")
    if not target.is_dir():
        raise PipelineError(f"Markdown path is not a directory: {target}")
    return target


def generate_readme_markdown(ctx, md_dir: Path | None = None) -> Path:
    """
    Crea (o sovrascrive) README.md nella cartella markdown target.
    I test verificano solo l'esistenza del file.
    """
    target = Path(md_dir) if md_dir is not None else Path(ctx.md_dir)
    target = _ensure_safe(Path(ctx.base_dir), target)
    target.mkdir(parents=True, exist_ok=True)

    title = getattr(ctx, "slug", None) or "Knowledge Base"
    readme = target / "README.md"
    readme.write_text(
        f"# {title}\n\n"
        "Contenuti generati/curati automaticamente.\n",
        encoding="utf-8",
    )
    return readme


def generate_summary_markdown(ctx, md_dir: Path | None = None) -> Path:
    """
    Genera SUMMARY.md elencando i .md nella cartella target
    (escludendo README.md e SUMMARY.md).
    """
    target = Path(md_dir) if md_dir is not None else Path(ctx.md_dir)
    target = _ensure_safe(Path(ctx.base_dir), target)
    target.mkdir(parents=True, exist_ok=True)

    summary = target / "SUMMARY.md"
    items: list[str] = []
    for p in sorted(target.glob("*.md"), key=lambda p: p.name.lower()):
        name = p.name.lower()
        if name in {"readme.md", "summary.md"}:
            continue
        items.append(f"- [{p.stem}]({p.name})")

    summary.write_text("# Summary\n\n" + "\n".join(items) + "\n", encoding="utf-8")
    return summary


def convert_files_to_structured_markdown(ctx, md_dir: Path | None = None) -> None:
    """
    Per ogni sotto-cartella diretta di ctx.raw_dir (categoria) crea un file
    <categoria>.md dentro md_dir con struttura:

      - H1: nome categoria (capitalizzato)
      - Heading per ogni livello di sottocartella (H2 = livello 0, H3 = livello 1, ...)
      - Heading del PDF a livello (2 + depth) e riga placeholder di contenuto

    Se una categoria non contiene PDF, scrive una riga informativa.
    """
    base = Path(ctx.base_dir)
    raw_root = Path(ctx.raw_dir)
    target = Path(md_dir) if md_dir is not None else Path(ctx.md_dir)

    # sicurezza percorso per target
    _ensure_safe(base, target)
    target.mkdir(parents=True, exist_ok=True)

    if not raw_root.exists():
        raise PipelineError(f"Raw directory does not exist: {raw_root}")
    if not raw_root.is_dir():
        raise PipelineError(f"Raw path is not a directory: {raw_root}")

    # categorie = sole directory immediate sotto raw/
    categories = sorted(
        (d for d in raw_root.iterdir() if d.is_dir()),
        key=lambda d: d.name.lower(),
    )

    for cat_dir in categories:
        cat_name = cat_dir.name
        md_file = target / f"{cat_name}.md"

        lines: list[str] = [f"# {_titleize(cat_name)}"]

        # tutti i PDF ricorsivi nella categoria
        pdfs = sorted(cat_dir.rglob("*.pdf"), key=lambda p: p.as_posix().lower())
        if not pdfs:
            lines += ["", "_Nessun PDF trovato in questa categoria._"]
        else:
            # Evita heading duplicati per le stesse sottocartelle
            emitted_folders: set[tuple[int, str]] = set()

            for pdf in pdfs:
                rel = pdf.relative_to(cat_dir)  # es. "2024/Q4/doc1.pdf" o "doc2.pdf"
                parts = list(rel.parts)

                # heading delle sottocartelle
                folder_parts = parts[:-1]
                for depth, folder in enumerate(folder_parts):  # depth 0 -> H2, depth 1 -> H3, ...
                    level = 2 + depth
                    key = (depth, folder.lower())
                    if key not in emitted_folders:
                        lines += ["", f"{'#' * level} {_titleize(folder)}"]
                        emitted_folders.add(key)

                # heading del PDF
                file_stem = Path(parts[-1]).stem  # es. "doc1"
                level = 2 + max(0, len(folder_parts))  # depth=0 -> H2, depth=2 -> H4
                lines += [
                    f"{'#' * level} {_titleize(file_stem)}",
                    f"(Contenuto estratto/conversione da `{parts[-1]}`)",
                ]

        md_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
