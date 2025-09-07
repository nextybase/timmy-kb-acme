from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Set, TYPE_CHECKING, Optional, Tuple, cast

from pipeline.constants import OUTPUT_DIR_NAME, REPO_NAME_PREFIX  # type: ignore
from pipeline.exceptions import ConfigError  # type: ignore
from pipeline.path_utils import ensure_within, sorted_paths  # type: ignore
from pipeline.file_utils import safe_write_text  # type: ignore

# Content utils opzionali (compat con varianti di firma)
try:  # pragma: no cover - opzionale a runtime
    from pipeline.content_utils import (  # type: ignore
        convert_files_to_structured_markdown as _convert_md,
        generate_summary_markdown as _gen_summary,
        generate_readme_markdown as _gen_readme,
        validate_markdown_dir as _validate_md,
    )
except Exception:  # pragma: no cover - opzionale a runtime
    _convert_md = _gen_summary = _gen_readme = _validate_md = None  # type: ignore

from adapters.content_fallbacks import ensure_readme_summary  # type: ignore
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab

# Tipi: a compile-time usiamo il tipo concreto per matchare le firme interne,
# a runtime restiamo decoupled con il Protocol strutturale.
if TYPE_CHECKING:
    from pipeline.context import ClientContext as ClientContextType  # type: ignore
else:
    from semantic.types import ClientContextProtocol as ClientContextType  # type: ignore

__all__ = [
    "get_paths",
    "load_reviewed_vocab",
    "convert_markdown",
    "enrich_frontmatter",
    "write_summary_and_readme",
]


def get_paths(slug: str) -> Dict[str, Path]:
    """Percorsi base/raw/book/semantic per uno slug cliente (formato SSoT)."""
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    return {
        "base": base_dir,
        "raw": base_dir / "raw",
        "book": base_dir / "book",
        "semantic": base_dir / "semantic",
    }


def load_reviewed_vocab(base_dir: Path, logger: logging.Logger) -> Dict[str, Dict[str, Set[str]]]:
    """Wrapper pubblico: carica il vocabolario canonico da SQLite (SSoT).

    Note:
    - La fonte canonica è il DB SQLite sotto `semantic/` (es. `tags.db`).
    - Lo YAML legacy (`tags_reviewed.yaml`) può esistere per migrazione/authoring,
      ma a runtime si legge dal DB per coerenza e tracciabilità.
    """
    return _load_reviewed_vocab(base_dir, logger)


def convert_markdown(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> List[Path]:
    """Converte i PDF in raw/ in Markdown sotto book/ (via content_utils se disponibili)."""
    paths = get_paths(slug)
    raw_dir = paths["raw"]
    book_dir = paths["book"]
    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}")
    local_pdfs = [p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"]
    if not local_pdfs and _convert_md is not None:
        raise ConfigError(f"Nessun PDF trovato in RAW locale: {raw_dir}")
    book_dir.mkdir(parents=True, exist_ok=True)
    if _convert_md is None:
        logger.warning(
            "convert_files_to_structured_markdown non disponibile: skip conversione (fallback)"
        )
        return list(sorted_paths(book_dir.glob("*.md"), base=book_dir))

    # Compat firma: prova con kwargs opzionali
    try:
        import inspect  # local to avoid import-time cost

        kwargs = {}
        try:
            sig = inspect.signature(_convert_md)
            params = sig.parameters
            if "skip_if_unchanged" in params:
                kwargs["skip_if_unchanged"] = None
            if "max_workers" in params:
                kwargs["max_workers"] = None
        except Exception:
            kwargs = {"skip_if_unchanged": None, "max_workers": None}

        ctxp = cast(ClientContextType, context)
        if kwargs:
            _convert_md(ctxp, **kwargs)  # type: ignore[misc]
        else:
            _convert_md(ctxp)  # type: ignore[misc]
    except TypeError:
        _convert_md(cast(ClientContextType, context))  # type: ignore[misc]

    return list(sorted_paths(book_dir.glob("*.md"), base=book_dir))


def enrich_frontmatter(
    context: ClientContextType,
    logger: logging.Logger,
    vocab: Dict[str, Dict[str, Set[str]]],
    *,
    slug: str,
) -> List[Path]:
    """Arricchisce i frontmatter dei Markdown con title e tag canonici."""
    paths = get_paths(slug)
    book_dir = paths["book"]
    mds = sorted_paths(book_dir.glob("*.md"), base=book_dir)
    touched: List[Path] = []
    inv = _build_inverse_index(vocab)
    for md in mds:
        name = md.name
        title = re.sub(r"[_\\/\-]+", " ", Path(name).stem).strip() or "Documento"
        tags = _guess_tags_for_name(name, vocab, inv=inv)
        try:
            from pipeline.path_utils import read_text_safe
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
    """Garantisce la generazione/validazione di SUMMARY.md e README.md sotto book/."""
    ctxp = cast(ClientContextType, context)
    if _gen_summary is not None:
        try:
            _gen_summary(ctxp)  # type: ignore[misc]
            logger.info("SUMMARY.md scritto (repo util)")
        except Exception as e:
            logger.warning(
                "generate_summary_markdown fallita; procedo con fallback", extra={"error": str(e)}
            )
    if _gen_readme is not None:
        try:
            _gen_readme(ctxp)  # type: ignore[misc]
            logger.info("README.md scritto (repo util)")
        except Exception as e:
            logger.warning(
                "generate_readme_markdown fallita; potrei usare il fallback",
                extra={"error": str(e)},
            )
    ensure_readme_summary(context, logger)
    if _validate_md is not None:
        try:
            _validate_md(ctxp)  # type: ignore[misc]
            logger.info("Validazione directory MD OK")
        except Exception as e:
            logger.warning("Validazione directory MD fallita", extra={"error": str(e)})


# ---- Helpers interni (copiati da semantic_onboarding, senza side effects CLI) ----
def _build_inverse_index(vocab: Dict[str, Dict[str, Set[str]]]) -> Dict[str, Set[str]]:
    inv: Dict[str, Set[str]] = {}
    for canon, meta in (vocab or {}).items():
        for term in {canon, *(meta.get("aliases") or set())}:
            t = str(term).strip().lower()
            if t:
                inv.setdefault(t, set()).add(canon)
    return inv


def _parse_frontmatter(md_text: str) -> Tuple[Dict, str]:
    if not md_text.startswith("---"):
        return {}, md_text
    try:
        import yaml  # type: ignore
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
        return meta, body
    except Exception:
        return {}, md_text


def _dump_frontmatter(meta: Dict) -> str:
    try:
        import yaml  # type: ignore

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


def _merge_frontmatter(existing: Dict, *, title: Optional[str], tags: List[str]) -> Dict:
    meta = dict(existing or {})
    if title and not meta.get("title"):
        meta["title"] = title
    if tags:
        meta["tags"] = sorted(set((meta.get("tags") or []) + tags))
    return meta


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
    s = re.sub(r"[_\\/\-\s]+", " ", s)
    found: Set[str] = set()
    for term, canon_set in inv.items():
        if term and term in s:
            found.update(canon_set)
    return sorted(found)
