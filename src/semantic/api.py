# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/api.py
from __future__ import annotations

import logging
import re
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

from kb_db import insert_chunks as _insert_chunks
from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.content_utils import convert_files_to_structured_markdown as _convert_md
from pipeline.content_utils import generate_readme_markdown as _gen_readme
from pipeline.content_utils import generate_summary_markdown as _gen_summary
from pipeline.content_utils import validate_markdown_dir as _validate_md
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within, sorted_paths
from semantic.tags_extractor import copy_local_pdfs_to_raw as _copy_local_pdfs_to_raw
from semantic.tags_extractor import emit_tags_csv as _emit_tags_csv
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab

if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType
else:
    from semantic.types import ClientContextProtocol as ClientContextType

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
    "build_mapping_from_vision",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
    "copy_local_pdfs_to_raw",
]


def get_paths(slug: str) -> Dict[str, Path]:
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    return cast(Dict[str, Dict[str, Set[str]]], _load_reviewed_vocab(base_dir, logger))


class _CtxShim:
    base_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str

    def __init__(self, *, base_dir: Path, raw_dir: Path, md_dir: Path, slug: str) -> None:
        self.base_dir = base_dir
        self.raw_dir = raw_dir
        self.md_dir = md_dir
        self.slug = slug


def _resolve_ctx_paths(context: ClientContextType, slug: str) -> tuple[Path, Path, Path]:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or paths["raw"])
    md_dir = cast(Path, getattr(context, "md_dir", None) or paths["book"])
    return base_dir, raw_dir, md_dir


def _call_convert_md(func: Any, ctx: _CtxShim, md_dir: Path) -> None:
    if not callable(func):
        raise ConversionError("convert_md target is not callable", slug=ctx.slug, file_path=md_dir)
    sig = inspect.signature(func)
    params = sig.parameters
    kwargs: Dict[str, Any] = {}
    if "md_dir" in params:
        kwargs["md_dir"] = md_dir
    bound = sig.bind_partial(ctx, **kwargs)
    bound.apply_defaults()
    func(*bound.args, **bound.kwargs)


def convert_markdown(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> List[Path]:
    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, book_dir)
    if not raw_dir.exists():
        raise ConfigError(
            f"Cartella RAW locale non trovata: {raw_dir}", slug=slug, file_path=raw_dir
        )
    book_dir.mkdir(parents=True, exist_ok=True)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=book_dir, slug=slug)
    _call_convert_md(_convert_md, shim, book_dir)
    mds = list(sorted_paths(book_dir.glob("*.md"), base=book_dir))
    if mds:
        return mds
    local_pdfs = [p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    if not local_pdfs:
        raise ConfigError(
            f"Nessun PDF trovato in RAW locale: {raw_dir}", slug=slug, file_path=raw_dir
        )
    raise ConversionError("La conversione non ha prodotto Markdown.", slug=slug, file_path=book_dir)


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    from pipeline.path_utils import read_text_safe

    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)  # noqa: F841
    # ✅ ripristino path-safety: l'override deve comunque ricadere sotto base_dir
    ensure_within(base_dir, book_dir)

    mds = sorted_paths(book_dir.glob("*.md"), base=book_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)

    for md in mds:
        name = md.name
        title = (
            re.sub(r"[_\/\-\s]+", " ", Path(name).stem).strip().replace("  ", " ") or "Documento"
        )
        tags = _guess_tags_for_name(name, vocab, inv=inv)
        try:
            text = read_text_safe(book_dir, md, encoding="utf-8")
        except OSError as e:
            logger.warning("Impossibile leggere MD", extra={"file_path": str(md), "error": str(e)})
            continue
        meta, body = _parse_frontmatter(text)
        new_meta = _merge_frontmatter(meta, title=title, tags=tags)
        if meta == new_meta:
            continue
        fm = _dump_frontmatter(new_meta)
        try:
            ensure_within(book_dir, md)
            safe_write_text(md, fm + body, encoding="utf-8", atomic=True)
            touched.append(md)
            logger.info("Frontmatter arricchito", extra={"file_path": str(md), "tags": tags})
        except OSError as e:
            logger.warning("Scrittura MD fallita", extra={"file_path": str(md), "error": str(e)})
    return touched


def write_summary_and_readme(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> None:
    base_dir, raw_dir, book_dir = _resolve_ctx_paths(context, slug)
    shim = _CtxShim(base_dir=base_dir, raw_dir=raw_dir, md_dir=book_dir, slug=slug)

    errors: list[str] = []
    try:
        _gen_summary(shim)
        logger.info("SUMMARY.md scritto")
    except Exception as e:  # pragma: no cover
        errors.append(f"summary: {e}")
    try:
        _gen_readme(shim)
        logger.info("README.md scritto")
    except Exception as e:  # pragma: no cover
        errors.append(f"readme: {e}")
    if errors:
        raise ConversionError("; ".join(errors), slug=slug, file_path=book_dir)
    _validate_md(shim)
    logger.info("Validazione directory MD OK")


def build_mapping_from_vision(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> Path:
    base_dir = cast(Path, getattr(context, "base_dir", None) or get_paths(slug)["base"])
    config_dir = base_dir / "config"
    mapping_path = config_dir / "semantic_mapping.yaml"
    vision_yaml = config_dir / "vision_statement.yaml"

    ensure_within(base_dir, config_dir)
    ensure_within(config_dir, mapping_path)
    ensure_within(config_dir, vision_yaml)
    if not vision_yaml.exists():
        raise ConfigError(
            f"Vision YAML non trovato: {vision_yaml}", slug=slug, file_path=vision_yaml
        )

    try:
        from pipeline.yaml_utils import yaml_read

        raw = yaml_read(vision_yaml.parent, vision_yaml) or {}
    except Exception as e:
        raise ConfigError(
            f"Errore lettura/parsing vision YAML ({vision_yaml}): {e}",
            slug=slug,
            file_path=vision_yaml,
        ) from e

    def _as_list(val: object) -> list[str]:
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    mapping: dict[str, list[str]] = {}
    sections: list[tuple[str, object]] = [
        ("ethical_framework", raw.get("ethical_framework")),
        ("uvp", raw.get("uvp")),
        ("key_metrics", raw.get("key_metrics")),
        ("risks_mitigations", raw.get("risks_mitigations")),
        ("operating_model", raw.get("operating_model")),
        ("architecture_principles", raw.get("architecture_principles")),
        ("ethics_governance_tools", raw.get("ethics_governance_tools")),
        ("stakeholders_impact", raw.get("stakeholders_impact")),
    ]
    goals = raw.get("goals") or {}
    if isinstance(goals, dict):
        sections.append(("goals_general", (goals.get("general") or [])))
        baskets = goals.get("baskets") or {}
        if isinstance(baskets, dict):
            sections.append(("goals_b3", baskets.get("b3") or []))
            sections.append(("goals_b6", baskets.get("b6") or []))
            sections.append(("goals_b12", baskets.get("b12") or []))

    for concept, payload in sections:
        values = _as_list(payload)
        if not values:
            continue
        seen: set[str] = set()
        norm: list[str] = []
        for v in values:
            key = v.lower()
            if key not in seen:
                seen.add(key)
                norm.append(v)
        if norm:
            mapping[concept] = norm

    if not mapping:
        raise ConfigError(
            f"Vision YAML non contiene sezioni utili per il mapping ({vision_yaml}).",
            slug=slug,
            file_path=vision_yaml,
        )

    config_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yaml

        safe = yaml.safe_dump(mapping, allow_unicode=True, sort_keys=True)
        safe_write_text(mapping_path, safe, encoding="utf-8", atomic=True)
    except Exception as e:
        raise ConfigError(
            f"Scrittura mapping fallita ({mapping_path}): {e}", slug=slug, file_path=mapping_path
        ) from e

    logger.info(
        "vision.mapping.built", extra={"file_path": str(mapping_path), "concepts": len(mapping)}
    )
    return mapping_path


def build_tags_csv(context: ClientContextType, logger: logging.Logger, *, slug: str) -> Path:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    raw_dir = cast(Path, getattr(context, "raw_dir", None) or paths["raw"])
    semantic_dir = base_dir / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    semantic_dir.mkdir(parents=True, exist_ok=True)
    count = _emit_tags_csv(raw_dir, csv_path, logger)
    logger.info("tags.csv.built", extra={"file_path": str(csv_path), "count": count})
    _write_tagging_readme(semantic_dir, logger)
    return csv_path


def copy_local_pdfs_to_raw(src_dir: Path, raw_dir: Path, logger: logging.Logger) -> int:
    return _copy_local_pdfs_to_raw(src_dir, raw_dir, logger)


def build_markdown_book(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> list[Path]:
    mds = convert_markdown(context, logger, slug=slug)
    write_summary_and_readme(context, logger, slug=slug)
    paths = get_paths(slug)
    vocab = load_reviewed_vocab(paths["base"], logger)
    if vocab:
        enrich_frontmatter(context, logger, vocab, slug=slug)
    return mds


def index_markdown_to_db(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    scope: str = "book",
    embeddings_client: _EmbeddingsClient,
    db_path: Path | None = None,
) -> int:
    paths = get_paths(slug)
    base_dir = cast(Path, getattr(context, "base_dir", None) or paths["base"])
    book_dir = cast(Path, getattr(context, "md_dir", None) or paths["book"])
    ensure_within(base_dir, book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)

    files = list(sorted_paths(book_dir.glob("*.md"), base=book_dir))
    if not files:
        logger.info("Nessun Markdown da indicizzare", extra={"book": str(book_dir)})
        return 0

    from pipeline.path_utils import read_text_safe

    contents: list[str] = []
    rel_paths: list[str] = []
    for f in files:
        try:
            text = read_text_safe(book_dir, f, encoding="utf-8")
        except Exception as e:
            logger.warning("Lettura MD fallita", extra={"file_path": str(f), "error": str(e)})
            continue
        contents.append(text)
        rel_paths.append(f.name)

    if not contents:
        logger.info("Nessun contenuto valido da indicizzare", extra={"book": str(book_dir)})
        return 0

    from datetime import datetime as _dt

    vecs = embeddings_client.embed_texts(contents)
    if not vecs or len(vecs) != len(contents):
        logger.warning(
            "Embedding client non ha prodotto vettori coerenti",
            extra={"count": len(vecs) if vecs else 0},
        )
        return 0

    version = _dt.utcnow().strftime("%Y%m%d")
    inserted_total = 0
    for text, rel_name, emb in zip(contents, rel_paths, vecs):
        meta = {"file": rel_name}
        try:
            inserted_total += _insert_chunks(
                project_slug=slug,
                scope=scope,
                path=rel_name,
                version=version,
                meta_dict=meta,
                chunks=[text],
                embeddings=[list(emb)],
                db_path=db_path,
            )
        except Exception as e:
            logger.warning("Inserimento DB fallito", extra={"file": rel_name, "error": str(e)})
            continue
    logger.info(
        "Indicizzazione completata", extra={"inserted": inserted_total, "files": len(rel_paths)}
    )
    return inserted_total


def _build_inverse_index(vocab: Dict[str, Dict[str, Set[str]]]) -> Dict[str, Set[str]]:
    inv: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        for term in {canon, *(meta.get("aliases") or set())}:
            t = str(term).strip().lower()
            if t:
                inv.setdefault(t, set()).add(canon)
    return inv


def _parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        return {}, md_text
    try:
        import yaml
    except Exception:
        return {}, md_text
    try:
        import re as _re

        m = _re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=_re.DOTALL)
        if not m:
            return {}, md_text
        header = m.group(1)
        body = md_text[m.end() :]
        meta = yaml.safe_load(header) or {}
        if not isinstance(meta, dict):
            return {}, md_text
        return cast(Dict[str, Any], meta), body
    except Exception:
        return {}, md_text


def _dump_frontmatter(meta: Dict[str, Any]) -> str:
    try:
        import yaml

        return (
            "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip() + "\n---\n"
        )
    except Exception:
        lines = ["---"]
        if "title" in meta:
            title_val = str(meta["title"]).replace('"', '\\"')
            lines.append(f'title: "{title_val}"')
        if "tags" in meta and isinstance(meta["tags"], list):
            lines.append("tags:")
            lines.extend([f"  - {t}" for t in meta["tags"]])
        lines.append("---\n")
        return "\n".join(lines)


def _as_list_str(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    if isinstance(x, (list, tuple, set)):
        out: list[str] = []
        for it in x:
            if it is None:
                continue
            s = str(it).strip()
            if s:
                out.append(s)
        return out
    s = str(x).strip()
    return [s] if s else []


def _merge_frontmatter(
    existing: Dict[str, Any], *, title: Optional[str], tags: List[str]
) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        left = _as_list_str(meta.get("tags"))
        merged = sorted(set(left + list(tags)))
        meta["tags"] = merged
    return meta


def _term_to_pattern(term: str) -> re.Pattern[str]:
    """
    Costruisce un pattern robusto a confini parola *semantici*:
    - lookaround espliciti: (?<!\\w) ... (?!\\w) per includere token con punteggiatura (c++, ml/ops, data+)
    - re.escape(term) per i simboli
    - spazi del termine mappati in \\s+ per tollerare separatori multipli
    """
    esc = re.escape(term.strip().lower())
    esc = esc.replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){esc}(?!\w)")


def _guess_tags_for_name(
    name_like_path: str,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    inv: Optional[Dict[str, Set[str]]] = None,
) -> List[str]:
    if not vocab:
        return []
    if inv is None:
        inv = _build_inverse_index(vocab)
    s = name_like_path.lower()
    s = re.sub(r"[_\/\-\s]+", " ", s)

    found: Set[str] = set()
    for term, canon_set in inv.items():
        if not term:
            continue
        pat = _term_to_pattern(term)
        if pat.search(s):
            found.update(canon_set)
    return sorted(found)
