# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/gen_dummy_kb.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

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

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _ensure_dependencies() -> None:
    """Carica le dipendenze runtime evitando effetti collaterali a import-time."""
    global safe_write_bytes, safe_write_text, get_structured_logger, tail_path
    global ensure_within, ensure_within_and_resolve, open_for_read_bytes_selfguard
    global extract_semantic_candidates, render_tags_csv, load_semantic_config, normalize_tags
    global _write_tagging_readme, _write_review_stub_from_csv, _fin_import_csv

    if safe_write_text is not None:  # idempotente
        return

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))

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

    # Bind espliciti per evitare false positive F824 su global non assegnati
    safe_write_bytes = _swb
    safe_write_text = _swt
    get_structured_logger = _gsl
    tail_path = _tail
    ensure_within = _ew
    ensure_within_and_resolve = _ewr
    open_for_read_bytes_selfguard = _ofr
    extract_semantic_candidates = _esc
    render_tags_csv = _rtc
    load_semantic_config = _lsc
    normalize_tags = _nt
    _write_tagging_readme = _wtr
    _write_review_stub_from_csv = _wrs
    _fin_import_csv = _fic


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera una knowledge base dummy per demo/test locali.")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--records", type=int, default=3, help="Numero di record fittizi finanziari (default: 3)")
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="Cartella base del workspace da generare (es. /tmp/kb). Se omessa usa output/timmy-kb-<slug>.",
    )
    return p.parse_args()


def _workspace_paths(slug: str, base_override: Optional[Path]) -> dict[str, Path]:
    """Calcola i percorsi fondamentali del workspace dummy."""
    _ensure_dependencies()
    from semantic.api import get_paths  # import leggero

    if base_override:
        base = base_override
        raw = base / "raw"
        book = base / "book"
        sem = base / "semantic"
        return {"base": base, "raw": raw, "book": book, "sem": sem}

    paths = get_paths(slug)
    base = paths["base"]
    raw = paths["raw"]
    book = paths["book"]
    sem = base / "semantic"
    return {"base": base, "raw": raw, "book": book, "sem": sem}


def _write_dummy_docs(book: Path) -> None:
    """Crea due markdown fittizi nella cartella book/."""
    _ensure_dependencies()
    assert safe_write_text is not None
    book.mkdir(parents=True, exist_ok=True)
    safe_write_text(book / "alpha.md", "# Alpha\n\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "beta.md", "# Beta\n\n", encoding="utf-8", atomic=True)


def _write_dummy_summary_readme(book: Path) -> None:
    """Genera SUMMARY.md e README.md fittizi per la knowledge base dummy."""
    _ensure_dependencies()
    assert safe_write_text is not None
    safe_write_text(book / "SUMMARY.md", "* [Alpha](alpha.md)\n* [Beta](beta.md)\n", encoding="utf-8", atomic=True)
    safe_write_text(book / "README.md", "# Dummy KB\n\n", encoding="utf-8", atomic=True)


def _maybe_write_dummy_finance(base: Path, records: int) -> None:
    """Opzionalmente crea un CSV finanziario dummy e lo importa con le API finance."""
    _ensure_dependencies()
    assert ensure_within is not None and safe_write_text is not None
    sem = base / "semantic"
    ensure_within(base, sem)
    sem.mkdir(parents=True, exist_ok=True)

    if _fin_import_csv is None or records <= 0:
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
        _fin_import_csv(base, tmp)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    """Punto di ingresso CLI per generare un workspace dummy."""
    args = _parse_args()
    _ensure_dependencies()
    assert get_structured_logger is not None
    log = get_structured_logger("tools.gen_dummy_kb")

    try:
        base_override = Path(args.out).resolve() if args.out else None
        paths = _workspace_paths(args.slug, base_override)
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
