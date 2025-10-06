# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/gen_dummy_kb.py
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path
from typing import Any, Optional

# Nota: nessun side-effect a import-time (no sys.path mutations, no I/O).
# Le dipendenze runtime sono risolte lazy in _ensure_dependencies().

# Placeholders valorizzati da _ensure_dependencies()
safe_write_bytes = None
safe_write_text = None
get_structured_logger = None
tail_path = None
ensure_within = None
ensure_within_and_resolve = None
open_for_read_bytes_selfguard = None
extract_semantic_candidates = None
render_tags_csv = None
load_semantic_config = None
normalize_tags = None
_write_tagging_readme = None
_write_review_stub_from_csv = None
_fin_import_csv = None

# Cache interna delle dipendenze risolte; non influisce sui placeholder sopra (restano None)
_DEPS: types.SimpleNamespace | None = None

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _require_dependency(deps: types.SimpleNamespace, attr: str) -> Any:
    value = getattr(deps, attr, None)
    if value is None:
        raise RuntimeError(f"Dependency '{attr}' unavailable; install required extras or check PATH.")
    return value


def _ensure_dependencies() -> types.SimpleNamespace:
    """Carica le dipendenze runtime evitando side-effects a import-time.

    - Inserisce `SRC_ROOT` in `sys.path` se assente (anche se le dipendenze sono già in cache).
    - Risolve e cache le dipendenze alla prima chiamata; i placeholder globali restano None.
    """
    global _DEPS

    # Assicura che `src/` sia importabile, senza duplicare voci
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    if _DEPS is not None:
        return _DEPS

    from pipeline.file_utils import safe_write_bytes as _swb
    from pipeline.file_utils import safe_write_text as _swt
    from pipeline.logging_utils import get_structured_logger as _gsl
    from pipeline.logging_utils import tail_path as _tail
    from pipeline.path_utils import ensure_within as _ew
    from pipeline.path_utils import ensure_within_and_resolve as _ewr
    from pipeline.path_utils import open_for_read_bytes_selfguard as _ofr
    from semantic.auto_tagger import extract_semantic_candidates as _esc
    from semantic.auto_tagger import render_tags_csv as _rtc
    from semantic.config import load_semantic_config as _lsc
    from semantic.normalizer import normalize_tags as _nt
    from semantic.tags_io import write_tagging_readme as _wtr
    from semantic.tags_io import write_tags_review_stub_from_csv as _wrs

    try:
        from finance.api import import_csv as _fic  # opzionale
    except Exception:
        _fic = None

    _DEPS = types.SimpleNamespace(
        safe_write_bytes=_swb,
        safe_write_text=_swt,
        get_structured_logger=_gsl,
        tail_path=_tail,
        ensure_within=_ew,
        ensure_within_and_resolve=_ewr,
        open_for_read_bytes_selfguard=_ofr,
        extract_semantic_candidates=_esc,
        render_tags_csv=_rtc,
        load_semantic_config=_lsc,
        normalize_tags=_nt,
        write_tagging_readme=_wtr,
        write_tags_review_stub_from_csv=_wrs,
        fin_import_csv=_fic,
    )
    return _DEPS


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera una knowledge base dummy per demo/test locali.")
    p.add_argument("--slug", default="timmy-kb-dummy", help="Slug KB (default: timmy-kb-dummy)")
    p.add_argument("--records", type=int, default=3, help="Numero di record fittizi finanziari (default: 3)")
    p.add_argument(
        "--base-dir",
        type=str,
        default="output",
        help="Cartella base in cui creare lo slug (default: output). Nei test usare tmp_path.",
    )
    return p.parse_args(argv)


def make_workspace(slug: str, base_dir: str) -> Path:
    """Ritorna la cartella base del workspace standard (base_dir/timmy-kb-<slug>). Idempotente."""
    base = Path(base_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / f"timmy-kb-{slug}"


def _workspace_paths(slug: str, base_override: Optional[Path]) -> dict[str, Path]:
    """Calcola i percorsi fondamentali del workspace dummy."""
    if base_override is not None:
        base = base_override
    else:
        # Fallback: usa la struttura standard di semantic.api (output/timmy-kb-<slug>)
        _ensure_dependencies()
        from semantic.api import get_paths  # import leggero

        paths = get_paths(slug)
        base = paths["base"]

    raw = base / "raw"
    book = base / "book"
    sem = base / "semantic"
    return {"base": base, "raw": raw, "book": book, "sem": sem}


def _write_dummy_docs(book: Path) -> None:
    """Crea due markdown fittizi nella cartella book/."""
    d = _ensure_dependencies()
    safe_write_text = _require_dependency(d, "safe_write_text")
    book.mkdir(parents=True, exist_ok=True)
    safe_write_text(book / "alpha.md", "# Alpha\n\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "beta.md", "# Beta\n\n", encoding="utf-8", atomic=True)


def _write_dummy_summary_readme(book: Path) -> None:
    """Genera SUMMARY.md e README.md fittizi per la knowledge base dummy."""
    d = _ensure_dependencies()
    safe_write_text = _require_dependency(d, "safe_write_text")
    safe_write_text(book / "SUMMARY.md", "* [Alpha](alpha.md)\n* [Beta](beta.md)\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "README.md", "# Dummy KB\n\n", encoding="utf-8", atomic=True)


def _maybe_write_dummy_finance(base: Path, records: int) -> None:
    """Opzionalmente crea un CSV finanziario dummy e lo importa con le API finance."""
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_text = _require_dependency(d, "safe_write_text")
    sem = base / "semantic"
    ensure_within_fn(base, sem)
    sem.mkdir(parents=True, exist_ok=True)

    if d.fin_import_csv is None or records <= 0:
        return

    # Genera CSV in modo atomico
    import csv
    from io import StringIO

    buf = StringIO()
    wr = csv.writer(buf)
    wr.writerow(["metric", "period", "value"])
    for i in range(records):
        wr.writerow(["m_revenue", f"2024Q{i%4+1}", i + 1])

    tmp = sem / "dummy-finance.csv"
    safe_write_text(tmp, buf.getvalue(), encoding="utf-8", atomic=True)
    try:
        d.fin_import_csv(base, tmp)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    """Punto di ingresso CLI per generare un workspace dummy (richiamabile dai test)."""
    args = _parse_args(argv)
    d = _ensure_dependencies()
    get_logger = _require_dependency(d, "get_structured_logger")
    log = get_logger("tools.gen_dummy_kb")

    try:
        ws_base = make_workspace(args.slug, args.base_dir)
        paths = _workspace_paths(args.slug, ws_base)
        # Crea le directory minime
        paths["base"].mkdir(parents=True, exist_ok=True)
        paths["raw"].mkdir(parents=True, exist_ok=True)
        paths["book"].mkdir(parents=True, exist_ok=True)
        (paths["base"] / "config").mkdir(parents=True, exist_ok=True)

        _write_dummy_docs(paths["book"])
        _write_dummy_summary_readme(paths["book"])
        _maybe_write_dummy_finance(paths["base"], args.records)
        log.info("dummy_kb_generated", extra={"slug": args.slug, "base": str(paths["base"])})
        return 0
    except Exception as exc:
        log.error("dummy_kb_failed", extra={"slug": args.slug, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
