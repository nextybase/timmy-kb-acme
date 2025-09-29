# src/pipeline/content_utils.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, TypeAlias
from urllib.parse import quote

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.path_utils import ensure_within_and_resolve  # SSoT path-safety forte
from pipeline.path_utils import ensure_within
from semantic.types import ClientContextProtocol as _ClientCtx  # SSoT dei contratti

__all__ = [
    "validate_markdown_dir",
    "generate_readme_markdown",
    "generate_summary_markdown",
    "convert_files_to_structured_markdown",
]

# Alias per annotazioni lunghe (evita E501)
CategoryGroups: TypeAlias = list[tuple[Path, list[Path]]]


# -----------------------------
# Helpers
# -----------------------------


def _titleize(name: str) -> str:
    """Titolo leggibile da nome file/cartella."""
    parts = name.replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else name


def _ensure_safe(base_dir: Path, candidate: Path) -> Path:
    """Wrapper che applica path-safety (via ensure_within) e restituisce il path risolto.

    Mappa gli errori di configurazione in PipelineError per coerenza call-site.
    """
    try:
        ensure_within(base_dir, candidate)
    except ConfigError as e:
        raise PipelineError(f"Unsafe directory: {candidate}", file_path=str(candidate)) from e
    return Path(candidate).resolve()


def _sorted_pdfs(cat_dir: Path) -> list[Path]:
    # Nota: filtrato a valle in _filter_safe_pdfs (per base/raw_root)
    return sorted(
        (p for p in cat_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.as_posix().lower(),
    )


def _filter_safe_pdfs(base_dir: Path, raw_root: Path, pdfs: Iterable[Path]) -> list[Path]:
    """Applica path-safety per-file e scarta symlink o path fuori perimetro.

    Mantiene l'ordinamento ricevuto.
    """
    log = logging.getLogger("pipeline.content_utils")
    out: list[Path] = []
    for p in pdfs:
        try:
            if p.is_symlink():
                log.warning("Skip PDF symlink", extra={"file_path": str(p)})
                continue
            safe_p = ensure_within_and_resolve(raw_root, p)
        except Exception as e:  # pragma: no cover (error path)
            log.warning("Skip PDF non sicuro", extra={"file_path": str(p), "error": str(e)})
            continue
        out.append(safe_p)
    return out


def _append_folder_headings(lines: list[str], folder_parts: Iterable[str], *, emitted: set[tuple[int, str]]) -> None:
    """Appende heading per ogni sottocartella lungo il percorso."""
    cumulative: list[str] = []
    for depth, folder in enumerate(folder_parts):
        level = 2 + depth
        cumulative.append(folder)
        key_path = "/".join(part.lower() for part in cumulative)
        key = (depth, key_path)
        if key not in emitted:
            lines += ["", f"{'#' * level} {_titleize(folder)}"]
            emitted.add(key)


def _append_pdf_section(lines: list[str], file_stem: str, *, level: int, filename: str) -> None:
    lines += [
        f"{'#' * level} {_titleize(file_stem)}",
        f"(Contenuto estratto/conversione da `{filename}`)",
    ]


def _group_safe_pdfs_by_category(
    raw_root: Path,
    safe_pdfs: list[Path],
) -> tuple[list[Path], CategoryGroups]:
    """Dato un elenco di PDF *già* validati (risolti dentro raw_root),
    restituisce:
      - (root_pdfs, [(cat_dir, pdfs_in_cat), ...]) con cat_dir = directory immediata sotto raw_root.
    """
    root_pdfs = [p for p in safe_pdfs if p.parent == raw_root]
    groups: dict[Path, list[Path]] = {}
    for pdf in safe_pdfs:
        try:
            rel = pdf.relative_to(raw_root)
        except Exception:
            continue
        parts = list(rel.parts)
        if len(parts) < 2:
            continue
        cat_dir = raw_root / parts[0]
        groups.setdefault(cat_dir, []).append(pdf)

    items: list[tuple[Path, list[Path]]] = []
    for cat_dir in sorted(groups.keys(), key=lambda d: d.name.lower()):
        items.append((cat_dir, sorted(groups[cat_dir], key=lambda p: p.as_posix().lower())))
    return (sorted(root_pdfs, key=lambda p: p.as_posix().lower()), items)


def _iter_category_pdfs(raw_root: Path) -> list[tuple[Path, list[Path]]]:
    """Restituisce le categorie immediate e la lista dei PDF (ricorsiva) per ciascuna (percorso legacy)."""
    categories = sorted((d for d in raw_root.iterdir() if d.is_dir()), key=lambda d: d.name.lower())
    out: list[tuple[Path, list[Path]]] = []
    for cat_dir in categories:
        out.append((cat_dir, _sorted_pdfs(cat_dir)))
    return out


def _render_category_markdown(cat_dir: Path, pdfs: list[Path], *, rel_base: Path | None = None) -> str:
    """Costruisce il contenuto Markdown per una singola categoria."""
    lines: list[str] = [f"# {_titleize(cat_dir.name)}"]
    if not pdfs:
        lines += ["", "_Nessun PDF trovato in questa categoria._"]
        return "\n".join(lines)

    emitted_folders: set[tuple[int, str]] = set()
    for pdf in pdfs:
        base = rel_base or cat_dir
        try:
            rel_parts = list(pdf.relative_to(base).parts)
        except Exception:
            rel_parts = [pdf.name]
        folder_parts = rel_parts[:-1]
        _append_folder_headings(lines, folder_parts, emitted=emitted_folders)
        file_stem = Path(rel_parts[-1]).stem
        level = 2 + max(0, len(folder_parts))
        _append_pdf_section(lines, file_stem, level=level, filename=rel_parts[-1])
    return "\n".join(lines)


# -----------------------------
# API
# -----------------------------


def validate_markdown_dir(ctx: _ClientCtx, md_dir: Path | None = None) -> Path:
    """Verifica che la cartella markdown esista, sia una directory e sia 'safe' rispetto a ctx.base_dir."""
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)

    if not target.exists():
        raise PipelineError(
            f"Markdown directory does not exist: {target}",
            slug=getattr(ctx, "slug", None),
            file_path=str(target),
        )
    if not target.is_dir():
        raise PipelineError(
            f"Markdown path is not a directory: {target}",
            slug=getattr(ctx, "slug", None),
            file_path=str(target),
        )
    return target


def generate_readme_markdown(ctx: _ClientCtx, md_dir: Path | None = None) -> Path:
    """Crea (o sovrascrive) README.md nella cartella markdown target."""
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)
    target.mkdir(parents=True, exist_ok=True)

    title = getattr(ctx, "slug", None) or "Knowledge Base"
    readme = target / "README.md"
    safe_write_text(
        readme,
        f"# {title}\n\nContenuti generati/curati automaticamente.\n",
        encoding="utf-8",
        atomic=True,
    )
    return readme


def generate_summary_markdown(ctx: _ClientCtx, md_dir: Path | None = None) -> Path:
    """Genera SUMMARY.md elencando i .md nella cartella target (escludendo README.md e SUMMARY.md)."""
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input)
    target.mkdir(parents=True, exist_ok=True)

    summary = target / "SUMMARY.md"
    items: list[str] = []
    for p in sorted(target.glob("*.md"), key=lambda p: p.name.lower()):
        name = p.name.lower()
        if name in {"readme.md", "summary.md"}:
            continue
        items.append(f"- [{p.stem}]({quote(p.name)})")

    safe_write_text(summary, "# Summary\n\n" + "\n".join(items) + "\n", encoding="utf-8", atomic=True)
    return summary


def convert_files_to_structured_markdown(
    ctx: _ClientCtx,
    md_dir: Path | None = None,
    *,
    safe_pdfs: list[Path] | None = None,
) -> None:
    """Converte i PDF in RAW in un set di .md strutturati nella cartella `md_dir`.

    Se `safe_pdfs` è fornito, **non** esegue alcuna discovery su disco e assume
    che la lista sia già validata e risolta all’interno di `ctx.raw_dir`.
    """
    base = ctx.base_dir
    raw_root = ctx.raw_dir
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir

    # sicurezza percorso per target e raw_root
    target = _ensure_safe(base, target_input)
    raw_root = _ensure_safe(base, raw_root)

    target.mkdir(parents=True, exist_ok=True)

    if not raw_root.exists():
        raise PipelineError(
            f"Raw directory does not exist: {raw_root}",
            slug=getattr(ctx, "slug", None),
            file_path=str(raw_root),
        )
    if not raw_root.is_dir():
        raise PipelineError(
            f"Raw path is not a directory: {raw_root}",
            slug=getattr(ctx, "slug", None),
            file_path=str(raw_root),
        )

    written: set[Path] = set()

    # Sorgente PDF: o elenco già validato (nuovo) o discovery legacy
    if safe_pdfs is not None:
        root_pdfs, cat_items = _group_safe_pdfs_by_category(raw_root, safe_pdfs)
    else:
        root_pdfs = _filter_safe_pdfs(base, raw_root, sorted(raw_root.glob("*.pdf"), key=lambda p: p.name.lower()))
        cat_items = _iter_category_pdfs(raw_root)

    # PDF direttamente in raw/: produce un file aggregato
    if root_pdfs:
        root_md = target / f"{raw_root.name}.md"
        content = _render_category_markdown(raw_root, root_pdfs)
        safe_write_text(root_md, content + "\n", encoding="utf-8", atomic=True)
        written.add(root_md)

    # Categorie = directory immediate sotto raw/
    for cat_dir, pdfs in cat_items:
        md_file = target / f"{cat_dir.name}.md"
        cat_dir_resolved = ensure_within_and_resolve(raw_root, cat_dir)
        safe_list = pdfs if safe_pdfs is not None else _filter_safe_pdfs(base, raw_root, pdfs)
        content = _render_category_markdown(cat_dir, safe_list, rel_base=cat_dir_resolved)
        safe_write_text(md_file, content + "\n", encoding="utf-8", atomic=True)
        written.add(md_file)

    # Cleanup idempotente: rimuovi .md orfani in book/ (escludi README.md e SUMMARY.md)
    for candidate in target.glob("*.md"):
        low = candidate.name.lower()
        if low in {"readme.md", "summary.md"}:
            continue
        if candidate not in written:
            ensure_within(target, candidate)
            try:
                candidate.unlink(missing_ok=True)
            except TypeError:
                try:
                    candidate.unlink()
                except FileNotFoundError:
                    pass
