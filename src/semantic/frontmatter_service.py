# SPDX-License-Identifier: GPL-3.0-or-later
"""Funzioni di frontmatter/README estratte da semantic.api."""

from __future__ import annotations

import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from pipeline.content_utils import generate_readme_markdown as _gen_readme
from pipeline.content_utils import generate_summary_markdown as _gen_summary
from pipeline.content_utils import validate_markdown_dir as _validate_md
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.frontmatter_utils import dump_frontmatter as _shared_dump_frontmatter
from pipeline.frontmatter_utils import parse_frontmatter as _shared_parse_frontmatter
from pipeline.logging_utils import phase_scope
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe
from pipeline.qa_gate import require_qa_gate_pass
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from semantic.config import load_semantic_config
from semantic.context_paths import resolve_context_paths
from semantic.embedding_service import list_content_markdown
from semantic.entities_frontmatter import enrich_frontmatter_with_entities
from semantic.layout_enricher import merge_non_distruttivo, suggest_layout
from semantic.types import ClientContextProtocol
from storage.tags_store import derive_db_path_from_yaml_path as _derive_tags_db_path
from storage.tags_store import get_conn as _get_tags_conn

__all__ = [
    "enrich_frontmatter",
    "write_summary_and_readme",
    "_build_inverse_index",
    "_merge_frontmatter",
    "_as_list_str",
    "_term_to_pattern",
    "_guess_tags_for_name",
    "_canonicalize_tags",
    "_dump_frontmatter",
    "_parse_frontmatter",
]


def _get_vision_statement_path(repo_root_dir: Path) -> Path:
    return vision_yaml_workspace_path(repo_root_dir)


def _load_vision_text(repo_root_dir: Path) -> str:
    path = _get_vision_statement_path(repo_root_dir)
    if not path.exists():
        return ""
    try:
        safe = ensure_within_and_resolve(repo_root_dir, path)
        text = read_text_safe(safe.parent, safe, encoding="utf-8")
        return str(text)
    except Exception:
        return ""


def _build_layout_constraints(base_yaml: Dict[str, Any]) -> Dict[str, Any]:
    tops = [k for k in base_yaml.keys() if isinstance(k, str) and k]
    if not tops:
        tops = ["strategy", "operations", "data"]
    max_nodes = max(12, len(tops) * 4)
    allowed = sorted({str(top).strip().lower() for top in tops})
    semantic_mapping: Dict[str, Tuple[str, ...]] = {}
    for key in allowed:
        semantic_mapping[key] = tuple()
    return {
        "max_depth": 3,
        "max_nodes": max_nodes,
        "allowed_prefixes": allowed,
        "semantic_mapping": semantic_mapping,
    }


def _read_layout_top_levels(layout_path: Path) -> list[str]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ConfigError(
            "Dipendenza opzionale mancante: impossibile importare 'yaml'.", file_path=layout_path
        ) from exc
    except Exception as exc:
        raise ConfigError(f"Import modulo yaml fallito: {exc!r}", file_path=layout_path) from exc

    if not layout_path.exists():
        return []
    try:
        safe = ensure_within_and_resolve(layout_path.parent, layout_path)
        text = read_text_safe(safe.parent, safe, encoding="utf-8")
        data_raw = yaml.safe_load(text)
    except (FileNotFoundError, OSError):
        return []
    except Exception as exc:
        raise ConfigError(f"Lettura layout_proposal.yaml fallita: {exc!r}", file_path=layout_path) from exc
    if not isinstance(data_raw, dict):
        return []
    data: Dict[str, Any] = dict(data_raw)
    # Nuovo layout: se presenti entità o aree, usali come top-level per note/sectioning
    if isinstance(data.get("entities"), list):
        names = [str(e.get("entity") or e.get("name") or e).strip() for e in data["entities"] if isinstance(e, dict)]
        return sorted({n for n in names if n})
    if isinstance(data.get("areas"), list):
        keys: list[str] = []
        for area_entry in data["areas"]:
            if isinstance(area_entry, dict):
                key_val = str(area_entry.get("key") or area_entry).strip()
            elif isinstance(area_entry, str):
                key_val = area_entry.strip()
            else:
                continue
            if key_val:
                keys.append(key_val)
        return sorted({k for k in keys if k})
    return sorted(str(key).strip() for key in data.keys() if key)


def _append_layout_note_to_readme(
    repo_root_dir: Path,
    book_dir: Path,
    logger: logging.Logger,
    *,
    slug: str,
) -> None:
    readme_path = book_dir / "README.md"
    ensure_within(repo_root_dir, readme_path)
    if not readme_path.exists():
        return
    try:
        content = read_text_safe(book_dir, readme_path, encoding="utf-8")
    except Exception:
        return
    layout_path = repo_root_dir / "semantic" / "layout_proposal.yaml"
    top_levels = _read_layout_top_levels(layout_path)
    note_lines = ["\n\n## Layout (service)", "Struttura semantica proposta:"]
    note_lines.extend(f"- {entry}" for entry in top_levels)
    note_lines.append("Vedi `semantic/layout_summary.md` per il riepilogo strutturale del servizio.")
    note = "\n".join(note_lines) + "\n"
    if "## Layout (service)" in content:
        return
    updated = content.rstrip() + "\n" + note
    safe_write_text(readme_path, updated, encoding="utf-8", atomic=True)
    logger.info(
        "semantic.readme.layout_note_added",
        extra={"slug": slug, "file_path": str(readme_path)},
    )


def _layout_summary_text(top_levels: list[str]) -> str:
    bullets = "\n".join(f"- **{entry}**: sezione proposta nel layout canonico" for entry in top_levels)
    return (
        "# Layout della knowledge base\n\n"
        "La struttura suggerita da `layout_enricher` viene di seguito elencata per facilitare "
        "l'allineamento con GitBook e Drive.\n\n"
        f"{bullets}\n"
    )


def _write_layout_summary(repo_root_dir: Path, book_dir: Path, logger: logging.Logger, *, slug: str) -> None:
    layout_path = repo_root_dir / "semantic" / "layout_proposal.yaml"
    top_levels = _read_layout_top_levels(layout_path)
    if not top_levels:
        return
    summary_path = book_dir / "layout_summary.md"
    try:
        ensure_within(repo_root_dir, summary_path)
    except Exception:
        return
    content = _layout_summary_text(top_levels)
    safe_write_text(summary_path, content, encoding="utf-8", atomic=True)
    logger.info(
        "semantic.layout_summary.written",
        extra={"slug": slug, "file_path": str(summary_path)},
    )


def _layout_section_from_md(md: Path, book_dir: Path, layout_keys: list[str]) -> str | None:
    """Determina la sezione di layout (top level) in base al path relativo."""
    if not layout_keys:
        return None
    try:
        relative = md.relative_to(book_dir)
    except Exception:
        return None
    parts = [part.strip().lower() for part in relative.parts if part.strip()]
    if not parts:
        return None
    cand = parts[0]
    for key in layout_keys:
        if cand == str(key).strip().lower():
            return key
    return None


def _dump_layout_yaml(data: Dict[str, Any]) -> str | None:
    try:
        import yaml
    except Exception:
        return None
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _persist_layout_proposal(layout: WorkspaceLayout, logger: logging.Logger, *, slug: str) -> None:
    repo_root_dir = layout.repo_root_dir
    try:
        cfg = load_semantic_config(repo_root_dir, slug=slug)
    except Exception as exc:
        logger.debug(
            "semantic.layout_proposal.config_failed",
            extra={"slug": slug, "error": str(exc)},
        )
        return

    mapping_all = cfg.mapping if isinstance(cfg.mapping, dict) else {}
    entities = mapping_all.get("entities")
    if isinstance(entities, list) and entities:
        entity_blocks: list[dict[str, Any]] = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            name = ent.get("name")
            if not name:
                continue
            entity_blocks.append(
                {
                    "entity": name,
                    "category": ent.get("category", ""),
                    "description": ent.get("description", ""),
                }
            )
        layout_dict: dict[str, Any] = {
            "version": mapping_all.get("version", 1),
            "source": mapping_all.get("source", "vision"),
            "context": mapping_all.get("context", {}),
            "entities": entity_blocks,
            "relations": mapping_all.get("relations", []),
            "areas": mapping_all.get("areas", []),
            "er_model": mapping_all.get("er_model", {}),
        }
        layout_yaml = _dump_layout_yaml(layout_dict)
    else:
        base_yaml = mapping_all if isinstance(mapping_all, dict) else {}
        if not base_yaml:
            return
        constraints = _build_layout_constraints(base_yaml)
        vision_text = _load_vision_text(repo_root_dir)
        try:
            proposal = suggest_layout(base_yaml, vision_text, constraints)
        except Exception as exc:
            logger.warning(
                "semantic.layout_proposal.failed",
                extra={"slug": slug, "error": str(exc)},
            )
            return
        if not proposal:
            return
        merged = merge_non_distruttivo(base_yaml, proposal)
        layout_yaml = _dump_layout_yaml(merged)

    if not layout_yaml:
        return

    semantic_dir = repo_root_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    layout_path = semantic_dir / "layout_proposal.yaml"
    safe_write_text(layout_path, layout_yaml, encoding="utf-8", atomic=True)
    logger.info(
        "semantic.layout_proposal.written",
        extra={"slug": slug, "file_path": str(layout_path)},
    )


def enrich_frontmatter(
    context: ClientContextProtocol,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Sequence[str]]],
    *,
    slug: str,
    allow_empty_vocab: bool = False,
) -> List[Path]:
    from pipeline.frontmatter_utils import read_frontmatter as _read_fm

    start_ts = time.perf_counter()
    if not vocab and not allow_empty_vocab:
        tags_db = Path(_derive_tags_db_path(Path("semantic") / "tags_reviewed.yaml"))
        raise ConfigError(
            "Vocabolario canonico assente: impossibile arricchire i front-matter senza tags canonici.",
            slug=slug,
            file_path=tags_db,
        )
    layout = WorkspaceLayout.from_context(context)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    repo_root_dir, book_dir = paths.repo_root_dir, paths.book_dir
    ensure_within(repo_root_dir, book_dir)
    layout_keys = _read_layout_top_levels(repo_root_dir / "semantic" / "layout_proposal.yaml")
    mapping_all: Dict[str, Any] = {}
    try:
        cfg = load_semantic_config(context)
        mapping_all = cfg.mapping if isinstance(cfg.mapping, dict) else {}
    except Exception:
        mapping_all = {}
    vision_entities: list[str] = []
    entities_raw = mapping_all.get("entities")
    if isinstance(entities_raw, list):
        vision_entities = [
            str(ent.get("name")).strip()
            for ent in entities_raw
            if isinstance(ent, dict) and str(ent.get("name", "")).strip()
        ]
    relations_raw = mapping_all.get("relations")
    relations_all: list[Any] = relations_raw if isinstance(relations_raw, list) else []

    if not vocab:
        tags_db = Path(_derive_tags_db_path(repo_root_dir / "semantic" / "tags_reviewed.yaml"))
        logger.info(
            "semantic.frontmatter.skip_tags",
            extra={"slug": slug, "reason": "empty_vocab_allowed", "file_path": str(tags_db)},
        )

    mds = list_content_markdown(book_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)

    with phase_scope(logger, stage="enrich_frontmatter", customer=slug) as scope:
        for md in mds:
            name = md.name
            title = re.sub(r"[_\/\-\s]+", " ", Path(name).stem).strip().replace("  ", " ") or "Documento"
            try:
                meta, body = _read_fm(book_dir, md, encoding="utf-8", use_cache=True)
            except OSError as exc:
                logger.warning(
                    "semantic.frontmatter.read_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(exc)},
                )
                continue

            raw_list = _as_list_str(meta.get("tags_raw"))
            canonical_from_raw = _canonicalize_tags(raw_list, inv)
            tags = canonical_from_raw or _guess_tags_for_name(name, vocab, inv=inv)
            new_meta = _merge_frontmatter(meta, title=title, tags=tags)
            section = _layout_section_from_md(md, book_dir, layout_keys)
            if section and not new_meta.get("layout_section"):
                new_meta["layout_section"] = section
            # Enrichment ER-driven: entity/area/relation_hints
            inferred_entity: Optional[str] = None
            tag_candidates = _as_list_str(new_meta.get("tags")) + _as_list_str(new_meta.get("tags_raw"))
            for t in tag_candidates:
                if t.strip().lower() in {e.lower() for e in vision_entities}:
                    inferred_entity = next((e for e in vision_entities if e.lower() == t.strip().lower()), None)
                    break
            if inferred_entity and not new_meta.get("entity"):
                new_meta["entity"] = inferred_entity
            if not new_meta.get("relation_hints") and new_meta.get("entity"):
                rel_hints: list[dict[str, str]] = []
                for rel in relations_all:
                    if not isinstance(rel, dict):
                        continue
                    src = str(rel.get("from", "")).strip()
                    dst = str(rel.get("to", "")).strip()
                    rtype = str(rel.get("type", "")).strip()
                    if not (src and dst and rtype):
                        continue
                    if src == new_meta["entity"]:
                        rel_hints.append({"type": rtype, "target": dst})
                    elif dst == new_meta["entity"]:
                        rel_hints.append({"type": rtype, "target": src})
                if rel_hints:
                    new_meta["relation_hints"] = rel_hints
            # Arricchimento additivo da doc_entities (se presenti e approvate)
            tags_db = Path(_derive_tags_db_path(repo_root_dir / "semantic" / "tags_reviewed.yaml"))
            try:
                if tags_db.exists():
                    with _get_tags_conn(str(tags_db)) as conn:
                        new_meta = enrich_frontmatter_with_entities(
                            new_meta,
                            conn,
                            getattr(paths, "semantic_mapping", {}),
                        )
            except Exception as exc:
                err_line = str(exc).splitlines()[0].strip() if str(exc) else ""
                err_type = type(exc).__name__
                raise ConfigError(
                    f"Arricchimento doc_entities fallito: {err_type}: {err_line}",
                    slug=slug,
                    file_path=tags_db,
                ) from exc
            if meta == new_meta:
                continue

            fm = _dump_frontmatter(new_meta)
            try:
                ensure_within(book_dir, md)
                safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
                touched.append(md)
                logger.info(
                    "semantic.frontmatter.updated",
                    extra={
                        "slug": slug,
                        "file_path": str(md),
                        "tags": tags,
                        "tags_raw": raw_list,
                        "canonical_from_raw": canonical_from_raw,
                    },
                )
            except OSError as exc:
                logger.warning(
                    "semantic.frontmatter.write_failed",
                    extra={"slug": slug, "file_path": str(md), "error": str(exc)},
                )
        try:
            scope.set_artifacts(len(touched))
        except Exception:
            scope.set_artifacts(None)

    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.enrich_frontmatter.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"updated": len(touched)}},
    )
    return touched


def write_summary_and_readme(context: ClientContextProtocol, logger: logging.Logger, *, slug: str) -> None:
    start_ts = time.perf_counter()
    layout = WorkspaceLayout.from_context(context)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    repo_root_dir = paths.repo_root_dir
    book_dir = paths.book_dir
    require_qa_gate_pass(layout.logs_dir, slug=slug)
    summary_func = _gen_summary
    readme_func = _gen_readme
    validate_func = _validate_md

    errors: List[str] = []
    with phase_scope(logger, stage="write_summary_and_readme", customer=slug) as scope:
        try:
            summary_func(paths)
            logger.info(
                "semantic.summary.written",
                extra={"slug": slug, "file_path": str(book_dir / "SUMMARY.md")},
            )
        except Exception as exc:  # pragma: no cover
            summary_path = book_dir / "SUMMARY.md"
            logger.exception(
                "semantic.summary.failed",
                extra={"slug": slug, "file_path": str(summary_path), "error": str(exc)},
            )
            errors.append(f"summary: {exc}")

        try:
            readme_func(paths)
            logger.info(
                "semantic.readme.written",
                extra={"slug": slug, "file_path": str(book_dir / "README.md")},
            )
            _append_layout_note_to_readme(repo_root_dir, book_dir, logger, slug=slug)
            _write_layout_summary(repo_root_dir, book_dir, logger, slug=slug)
        except Exception as exc:  # pragma: no cover
            readme_path = book_dir / "README.md"
            logger.error(
                "frontmatter.readme_generation_failed",
                extra={"slug": slug, "file_path": str(readme_path)},
            )
            logger.exception(
                "semantic.readme.failed",
                extra={"slug": slug, "file_path": str(readme_path), "error": str(exc)},
            )
            errors.append(f"readme: {exc}")

        if errors:
            raise ConversionError("; ".join(errors), slug=slug, file_path=book_dir)

        validate_func(paths)
        logger.info("semantic.book.validated", extra={"slug": slug, "book_dir": str(book_dir)})
        _persist_layout_proposal(layout, logger, slug=slug)
        scope.set_artifacts(2)

    ms = int((time.perf_counter() - start_ts) * 1000)
    logger.info(
        "semantic.summary_readme.done",
        extra={"slug": slug, "ms": ms, "artifacts": {"summary": True, "readme": True}},
    )


def _build_inverse_index(vocab: Dict[str, Dict[str, Sequence[str]]]) -> Dict[str, Set[str]]:
    inverse: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        aliases = meta.get("aliases") or []
        for term in {canon, *aliases}:
            normalized = str(term).strip().lower()
            if normalized:
                inverse.setdefault(normalized, set()).add(canon)
    return inverse


def _as_list_str(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            stripped = str(item).strip()
            if stripped:
                out.append(stripped)
        return out
    stripped = str(value).strip()
    return [stripped] if stripped else []


def _merge_frontmatter(existing: Dict[str, Any], *, title: Optional[str], tags: List[str]) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        left = _as_list_str(meta.get("tags"))
        merged = sorted(set([*left, *tags]))
        meta["tags"] = merged
    return meta


@lru_cache(maxsize=1024)
def _term_to_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.strip().lower())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){escaped}(?!\w)")


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Sequence[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)
    lowered = name_like_path.lower()
    lowered = re.sub(r"[_\/\-\s]+", " ", lowered)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if not term:
            continue
        pattern = _term_to_pattern(term)
        if pattern.search(lowered):
            found.update(canon_set)
    return sorted(found)


def _canonicalize_tags(raw_tags: List[str], inv: Dict[str, Set[str]]) -> List[str]:
    canonical: Set[str] = set()
    for tag in raw_tags:
        normalized = tag.strip().lower()
        if not normalized:
            continue
        mapped = inv.get(normalized)
        if mapped:
            canonical.update(mapped)
        else:
            canonical.add(tag.strip())
    return sorted(canonical)


def _parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    meta_raw, body = _shared_parse_frontmatter(md_text)
    meta_dict: Dict[str, Any] = dict(meta_raw or {})
    return meta_dict, body


def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    meta_dict: Dict[str, Any] = dict(meta)
    return cast(str, _shared_dump_frontmatter(meta_dict))
