from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, cast

from pipeline.constants import OUTPUT_DIR_NAME  # type: ignore
from pipeline.constants import REPO_NAME_PREFIX
from pipeline.exceptions import ConfigError  # type: ignore
from pipeline.file_utils import safe_write_text  # type: ignore
from pipeline.path_utils import ensure_within, sorted_paths  # type: ignore

# Content utils opzionali (compat con varianti di firma)
try:  # pragma: no cover - opzionale a runtime
    from pipeline.content_utils import (
        convert_files_to_structured_markdown as _convert_md,
    )  # type: ignore
    from pipeline.content_utils import generate_readme_markdown as _gen_readme
    from pipeline.content_utils import generate_summary_markdown as _gen_summary
    from pipeline.content_utils import validate_markdown_dir as _validate_md
except Exception:  # pragma: no cover - opzionale a runtime
    _convert_md = _gen_summary = _gen_readme = _validate_md = None  # type: ignore

from adapters.content_fallbacks import ensure_readme_summary  # type: ignore
from semantic.vocab_loader import load_reviewed_vocab as _load_reviewed_vocab
from semantic.tags_extractor import emit_tags_csv as _emit_tags_csv
from semantic.tags_io import write_tagging_readme as _write_tagging_readme
from semantic.types import EmbeddingsClient as _EmbeddingsClient
from kb_db import insert_chunks as _insert_chunks

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
    "build_mapping_from_vision",
    "build_tags_csv",
    "build_markdown_book",
    "index_markdown_to_db",
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


def load_reviewed_vocab(
    base_dir: Path, logger: logging.Logger
) -> Dict[str, Dict[str, Set[str]]]:
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
    # Preferisci i percorsi dal contesto se presenti, altrimenti convenzione SSoT
    paths = get_paths(slug)
    base_dir = getattr(context, "base_dir", None) or paths["base"]
    raw_dir = getattr(context, "raw_dir", None) or paths["raw"]
    book_dir = getattr(context, "md_dir", None) or paths["book"]
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, book_dir)
    if not raw_dir.exists():
        raise ConfigError(f"Cartella RAW locale non trovata: {raw_dir}")
    local_pdfs = [
        p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"
    ]
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
            logger.warning(
                "Impossibile leggere MD", extra={"file_path": str(md), "error": str(e)}
            )
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
            logger.info(
                "Frontmatter arricchito", extra={"file_path": str(md), "tags": tags}
            )
        except OSError as e:
            logger.warning(
                "Scrittura MD fallita", extra={"file_path": str(md), "error": str(e)}
            )
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
                "generate_summary_markdown fallita; procedo con fallback",
                extra={"error": str(e)},
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


def build_mapping_from_vision(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> Path:
    """Genera/aggiorna `config/semantic_mapping.yaml` a partire da `config/vision_statement.yaml`.

    Regole e scopo:
    - Non introduce dipendenze di rete; parsing deterministico del vision YAML.
    - Mappa liste e sezioni note in un mapping {concept: [keywords...]}, pronto per evoluzioni GPT future.
    - Idempotente: rilanci sicuri con scrittura atomica; nessun side-effect fuori perimetro cliente.
    - UI e interfacce pubbliche: additive (nuova API), nessuna rottura.
    """
    # Preferisci base_dir dal contesto, fallback alla convenzione SSoT
    base_dir = getattr(context, "base_dir", None) or get_paths(slug)["base"]
    config_dir = base_dir / "config"
    mapping_path = config_dir / "semantic_mapping.yaml"
    vision_yaml = config_dir / "vision_statement.yaml"

    # Path-safety e precondizioni minime
    ensure_within(base_dir, config_dir)
    ensure_within(config_dir, mapping_path)
    ensure_within(config_dir, vision_yaml)
    if not vision_yaml.exists():
        raise ConfigError(
            f"Vision YAML non trovato: {vision_yaml}", file_path=str(vision_yaml)
        )

    try:
        import yaml  # type: ignore
        raw = yaml.safe_load(vision_yaml.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise ConfigError(
            f"Errore lettura/parsing vision YAML: {e}", file_path=str(vision_yaml)
        ) from e

    def _as_list(val: object) -> list[str]:
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
        return []

    # Estrai sezioni note in concetti semplici; dedup case-insensitive preservando ordine
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
    # goals
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

    # Serializza mapping (anche se vuoto: preferiamo fallire chiaramente)
    if not mapping:
        raise ConfigError(
            "Vision YAML non contiene sezioni utili per il mapping.",
            file_path=str(vision_yaml),
        )

    config_dir.mkdir(parents=True, exist_ok=True)
    try:
        import yaml  # type: ignore
        safe = yaml.safe_dump(mapping, allow_unicode=True, sort_keys=True)
        safe_write_text(mapping_path, safe, encoding="utf-8", atomic=True)
    except Exception as e:
        raise ConfigError(
            f"Scrittura mapping fallita: {e}", file_path=str(mapping_path)
        ) from e

    logger.info(
        "vision.mapping.built",
        extra={
            "file_path": str(mapping_path),
            "concepts": len(mapping),
        },
    )
    return mapping_path


def build_tags_csv(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> Path:
    """Scansiona RAW e genera `semantic/tags_raw.csv` in modo deterministico.

    Azioni:
    - Emette `tags_raw.csv` sotto `semantic/` usando euristiche conservative su path/filename.
    - Scrive/aggiorna un README tagging rapido in `semantic/`.
    - Idempotente e con path-safety SSoT; no rete.
    """
    paths = get_paths(slug)
    base_dir = getattr(context, "base_dir", None) or paths["base"]
    raw_dir = getattr(context, "raw_dir", None) or paths["raw"]
    semantic_dir = base_dir / "semantic"
    csv_path = semantic_dir / "tags_raw.csv"

    # Path-safety
    ensure_within(base_dir, raw_dir)
    ensure_within(base_dir, semantic_dir)
    ensure_within(semantic_dir, csv_path)

    semantic_dir.mkdir(parents=True, exist_ok=True)
    # Genera CSV tag grezzi
    count = _emit_tags_csv(raw_dir, csv_path, logger)
    logger.info("tags.csv.built", extra={"file_path": str(csv_path), "count": count})
    # README tagging
    _write_tagging_readme(semantic_dir, logger)
    return csv_path


def build_markdown_book(
    context: ClientContextType, logger: logging.Logger, *, slug: str
) -> list[Path]:
    """Pipeline RAW → Markdown (uno per cartella) + README/SUMMARY + frontmatter.

    - Converte i PDF in `book/` (un `.md` per cartella di primo livello) via content_utils.
    - Garantisce `README.md` e `SUMMARY.md` in `book/`.
    - Arricchisce i frontmatter con title/tags usando il vocabolario consolidato su SQLite (se presente).
    - Idempotente; nessuna rete.
    """
    # 1) Conversione RAW → Markdown (riuso content_utils)
    convert_markdown(context, logger, slug=slug)

    # 2) Fallback README/SUMMARY
    write_summary_and_readme(context, logger, slug=slug)

    # 3) Arricchimento frontmatter con vocab (se disponibile)
    paths = get_paths(slug)
    vocab = load_reviewed_vocab(paths["base"], logger)
    if vocab:
        enrich_frontmatter(context, logger, vocab, slug=slug)

    # Ritorna lista aggiornata di MD
    book_dir = paths["book"]
    return list(sorted_paths(book_dir.glob("*.md"), base=book_dir))


def index_markdown_to_db(
    context: ClientContextType,
    logger: logging.Logger,
    *,
    slug: str,
    scope: str = "book",
    embeddings_client: _EmbeddingsClient,
) -> int:
    """Indicizza i Markdown in `book/` nel DB locale (SQLite) con chunk + embedding.

    Regole:
    - Un chunk per file (implementazione minimale; estendibile a chunking per heading).
    - Meta: {"file": name} e path relativo a `book/`.
    - Version: stringa YYYYMMDD (giorno), per rotazione semplice.
    - Path-safety SSoT, idempotente lato DB (nessuna de-duplicazione automatica).
    """
    paths = get_paths(slug)
    base_dir = getattr(context, "base_dir", None) or paths["base"]
    book_dir = getattr(context, "md_dir", None) or paths["book"]
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

    vecs = embeddings_client.embed_texts(contents)
    if not vecs or len(vecs) != len(contents):
        logger.warning(
            "Embedding client non ha prodotto vettori coerenti",
            extra={"count": len(vecs) if vecs else 0},
        )
        return 0

    from datetime import datetime as _dt

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
                db_path=None,
            )
        except Exception as e:
            logger.warning(
                "Inserimento DB fallito", extra={"file": rel_name, "error": str(e)}
            )
            continue
    logger.info("Indicizzazione completata", extra={"inserted": inserted_total, "files": len(rel_paths)})
    return inserted_total


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
            "---\n"
            + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
            + "\n---\n"
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


def _merge_frontmatter(
    existing: Dict, *, title: Optional[str], tags: List[str]
) -> Dict:
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
