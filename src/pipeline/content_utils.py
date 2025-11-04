# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/content_utils.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, TypeAlias, cast
from urllib.parse import quote

from pipeline.exceptions import PathTraversalError, PipelineError
from pipeline.file_utils import safe_write_text  # scritture atomiche
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, ensure_within_and_resolve  # SSoT path-safety forte
from semantic.auto_tagger import extract_semantic_candidates
from semantic.config import SemanticConfig, load_semantic_config
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


def _ensure_safe(base_dir: Path, candidate: Path, *, slug: str | None = None) -> Path:
    """Path-safety SSoT: risolve e valida `candidate` entro `base_dir` in un'unica operazione.

    Delegato a `pipeline.path_utils.ensure_within_and_resolve` per evitare TOCTOU/symlink games
    e mantenere le eccezioni tipizzate della pipeline (es. PathTraversalError/ConfigError).
    """
    try:
        return cast(Path, ensure_within_and_resolve(base_dir, candidate))
    except PathTraversalError as exc:
        raise PathTraversalError(str(exc), slug=slug, file_path=str(candidate)) from exc


def _sorted_pdfs(cat_dir: Path) -> list[Path]:
    # Nota: filtrato a valle in _filter_safe_pdfs (per base/raw_root)
    return sorted(
        (p for p in cat_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.as_posix().lower(),
    )


def _filter_safe_pdfs(base_dir: Path, raw_root: Path, pdfs: Iterable[Path], *, slug: str | None = None) -> list[Path]:
    """Applica path-safety per-file e scarta symlink o path fuori perimetro.

    Mantiene l'ordinamento ricevuto.
    """
    log = get_structured_logger("pipeline.content_utils")
    out: list[Path] = []
    for p in pdfs:
        try:
            if p.is_symlink():
                log.warning(
                    "pipeline.content.skip_symlink",
                    extra={"slug": slug, "file_path": str(p)},
                )
                continue
            safe_p = ensure_within_and_resolve(raw_root, p)
        except Exception as e:  # pragma: no cover (error path)
            log.warning(
                "pipeline.content.skip_unsafe",
                extra={"slug": slug, "file_path": str(p), "error": str(e)},
            )
            continue
        out.append(safe_p)
    return out


def _dump_frontmatter(meta: dict[str, Any]) -> str:
    """Serializza il dizionario `meta` in frontmatter YAML, con fallback minimo."""
    try:
        import yaml

        payload = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{payload}\n---\n"
    except Exception:
        lines = ["---"]
        for key, value in meta.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            elif value is not None:
                lines.append(f"{key}: {value}")
        lines.append("---\n")
        return "\n".join(lines)


def _write_markdown_for_pdf(
    pdf_path: Path,
    raw_root: Path,
    target_root: Path,
    candidates: Mapping[str, Mapping[str, Any]],
    cfg: SemanticConfig,
) -> Path:
    """Genera un file Markdown 1:1 per il PDF indicato, includendo frontmatter completo."""
    rel_pdf = pdf_path.relative_to(raw_root)
    md_candidate = target_root / rel_pdf.with_suffix(".md")
    md_path = ensure_within_and_resolve(target_root, md_candidate)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    candidate_meta = candidates.get(rel_pdf.as_posix(), {}) if candidates else {}
    tags_raw = candidate_meta.get("tags") or []

    meta: dict[str, Any] = {
        "title": _titleize(pdf_path.stem),
        "source_category": rel_pdf.parent.as_posix() or None,
        "source_file": rel_pdf.name,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "tags_raw": sorted({str(t).strip() for t in tags_raw if str(t).strip()}),
    }

    body = f"*Documento sincronizzato da `{rel_pdf.as_posix()}`.*\n"
    safe_write_text(md_path, _dump_frontmatter(meta) + body, encoding="utf-8", atomic=True)
    return md_path


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


# -----------------------------
# API
# -----------------------------


def validate_markdown_dir(ctx: _ClientCtx, md_dir: Path | None = None) -> Path:
    """Verifica che la cartella markdown esista, sia una directory e sia 'safe' rispetto a ctx.base_dir."""
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input, slug=getattr(ctx, "slug", None))

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
    target = _ensure_safe(ctx.base_dir, target_input, slug=getattr(ctx, "slug", None))
    target.mkdir(parents=True, exist_ok=True)

    title = getattr(ctx, "slug", None) or "Knowledge Base"
    readme = target / "README.md"

    sections: list[str] = []
    try:
        cfg = load_semantic_config(ctx.base_dir)
        areas_data = cfg.mapping.get("areas") if isinstance(cfg.mapping, dict) else None
        if isinstance(areas_data, dict):
            iterable = areas_data.items()
        elif isinstance(areas_data, list):
            iterable = (
                (item.get("key") or item.get("name") or f"area_{idx}", item)
                for idx, item in enumerate(areas_data)
                if isinstance(item, dict)
            )
        else:
            iterable = ()
        for key, meta in iterable:
            display = _titleize(str(key))
            descr = str((meta or {}).get("descrizione") or "").strip()
            section_body = f"## {display}\n"
            if descr:
                section_body += f"\n{descr}\n"
            sections.append(section_body.strip())
    except Exception:
        pass

    content = "\n\n".join(sections).strip() or "Contenuti generati/curati automaticamente."
    safe_write_text(
        readme,
        f"# {title}\n\n{content}\n",
        encoding="utf-8",
        atomic=True,
    )
    return readme


def generate_summary_markdown(ctx: _ClientCtx, md_dir: Path | None = None) -> Path:
    """Genera SUMMARY.md elencando i .md nella cartella target (escludendo README.md e SUMMARY.md)."""
    target_input: Path = md_dir if md_dir is not None else ctx.md_dir
    target = _ensure_safe(ctx.base_dir, target_input, slug=getattr(ctx, "slug", None))
    target.mkdir(parents=True, exist_ok=True)

    summary = target / "SUMMARY.md"
    lines: list[str] = ["# Summary", ""]

    def iter_markdown() -> Iterable[Path]:
        for md in sorted(target.rglob("*.md"), key=lambda p: p.relative_to(target).as_posix().lower()):
            name = md.name.lower()
            if name in {"readme.md", "summary.md"}:
                continue
            yield md.relative_to(target)

    emitted_headers: set[str] = set()
    for rel in iter_markdown():
        parts = list(rel.parts)
        file_name = parts.pop()
        for depth, part in enumerate(parts):
            key = "/".join(parts[: depth + 1])
            if key not in emitted_headers:
                indent = "    " * depth
                lines.append(f"{indent}- **{_titleize(part)}**")
                emitted_headers.add(key)
        indent = "    " * len(parts)
        lines.append(f"{indent}- [{_titleize(Path(file_name).stem)}]({quote(rel.as_posix())})")

    safe_write_text(summary, "\n".join(lines).rstrip() + "\n", encoding="utf-8", atomic=True)
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
    target = _ensure_safe(base, target_input, slug=getattr(ctx, "slug", None))
    raw_root = _ensure_safe(base, raw_root, slug=getattr(ctx, "slug", None))

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

    cfg = load_semantic_config(base)
    candidates = extract_semantic_candidates(raw_root, cfg)

    written: set[Path] = set()

    if safe_pdfs is not None:
        root_pdfs, cat_items = _group_safe_pdfs_by_category(raw_root, safe_pdfs)
    else:
        root_pdfs = _filter_safe_pdfs(
            base,
            raw_root,
            sorted(raw_root.glob("*.pdf"), key=lambda p: p.name.lower()),
            slug=getattr(ctx, "slug", None),
        )
        cat_items = _iter_category_pdfs(raw_root)

    for pdf in root_pdfs:
        written.add(_write_markdown_for_pdf(pdf, raw_root, target, candidates, cfg))

    for _cat_dir, pdfs in cat_items:
        safe_list = (
            pdfs if safe_pdfs is not None else _filter_safe_pdfs(base, raw_root, pdfs, slug=getattr(ctx, "slug", None))
        )
        for pdf in safe_list:
            written.add(_write_markdown_for_pdf(pdf, raw_root, target, candidates, cfg))

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
