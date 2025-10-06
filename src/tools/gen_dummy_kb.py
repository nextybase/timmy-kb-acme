# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/gen_dummy_kb.py
from __future__ import annotations

import argparse
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml  # per leggere/scrivere template di config e clients_db

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
read_text_safe = None
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
REPO_ROOT = Path(__file__).resolve().parents[2]  # <project_root>


def _require_dependency(deps: types.SimpleNamespace, attr: str) -> Any:
    value = getattr(deps, attr, None)
    if value is None:
        raise RuntimeError(f"Dependency '{attr}' unavailable; install required extras or check PATH.")
    return value


def _ensure_dependencies() -> types.SimpleNamespace:
    """Carica le dipendenze runtime evitando side-effects a import-time.

    - Inserisce `src/` in `sys.path` se assente (anche se le dipendenze sono già in cache).
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
    from pipeline.path_utils import read_text_safe as _rts
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
        read_text_safe=_rts,
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
    # Default allineato alla suite di test: 'dummy'
    p.add_argument("--slug", default="dummy", help="Slug KB (default: dummy)")
    p.add_argument("--records", type=int, default=3, help="Numero di record fittizi finanziari (default: 3)")
    p.add_argument(
        "--base-dir",
        type=str,
        default="output",
        help="Cartella base in cui creare lo slug (default: output). Nei test usare tmp_path.",
    )
    p.add_argument("--client-name", default=None, help="Nome cliente (display). Se omesso: 'Dummy <slug>'")
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
    cfg = base / "config"
    return {"base": base, "raw": raw, "book": book, "sem": sem, "cfg": cfg}


def _write_dummy_docs(book: Path) -> None:
    """Crea due markdown fittizi nella cartella book/."""
    d = _ensure_dependencies()
    safe_write_text_fn = _require_dependency(d, "safe_write_text")
    book.mkdir(parents=True, exist_ok=True)
    safe_write_text_fn(book / "alpha.md", "# Alpha\n\n", encoding="utf-8", atomic=True)
    safe_write_text_fn(book / "beta.md", "# Beta\n\n", encoding="utf-8", atomic=True)


def _write_dummy_summary_readme(book: Path) -> None:
    """Genera SUMMARY.md e README.md fittizi per la knowledge base dummy."""
    d = _ensure_dependencies()
    safe_write_text_fn = _require_dependency(d, "safe_write_text")
    safe_write_text_fn(book / "SUMMARY.md", "* [Alpha](alpha.md)\n* [Beta](beta.md)\n", encoding="utf-8", atomic=True)
    safe_write_text_fn(book / "README.md", "# Dummy KB\n\n", encoding="utf-8", atomic=True)


def _maybe_write_dummy_finance(base: Path, records: int) -> None:
    """Opzionalmente crea un CSV finanziario dummy e lo importa con le API finance."""
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_text_fn = _require_dependency(d, "safe_write_text")
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
    safe_write_text_fn(tmp, buf.getvalue(), encoding="utf-8", atomic=True)
    try:
        d.fin_import_csv(base, tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ----------------------- CONFIG & PDF -----------------------

_DEFAULT_AI = {
    "ai": {
        "engine": "ASSISTENTE",  # "GPT" | "ASSISTENTE" | "AUTO"
        "model": "gpt-4.1-mini",  # usato solo se engine = GPT
        "inline_threshold": 15000,  # token stimati per inline vs vector
    }
}


def _load_repo_config_template() -> dict:
    """Carica <project_root>/config/config.yaml (o .example), fallback a _DEFAULT_AI.

    Lettura sicura con ensure_within_and_resolve + read_text_safe (base = REPO_ROOT).
    """
    d = _ensure_dependencies()
    ewr = _require_dependency(d, "ensure_within_and_resolve")
    rts = _require_dependency(d, "read_text_safe")

    candidates = [
        REPO_ROOT / "config" / "config.yaml",
        REPO_ROOT / "config" / "config.example.yaml",
    ]
    for c in candidates:
        try:
            safe_c = ewr(REPO_ROOT, c)
            if safe_c.exists():
                text = rts(REPO_ROOT, safe_c, encoding="utf-8")
                data = yaml.safe_load(text) or {}
                # merge soft con default ai
                merged = {**_DEFAULT_AI, **(data or {})}
                if "ai" not in merged:
                    merged["ai"] = _DEFAULT_AI["ai"]
                return merged
        except Exception:
            continue
    return _DEFAULT_AI.copy()


def _render_client_config(template: dict, *, slug: str, client_name: Optional[str] = None) -> dict:
    """Arricchisce il template con campi cliente e reference al VisionStatement."""
    cfg = dict(template)  # shallow copy
    cfg["client_name"] = client_name or f"Dummy {slug}"
    cfg["vision_statement_pdf"] = "config/VisionStatement.pdf"

    # rimpiazza eventuali placeholder {slug} in percorsi del template
    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(v) for v in obj]
        if isinstance(obj, str):
            return obj.replace("{slug}", slug)
        return obj

    return _walk(cfg)


def _safe_yaml_dump(d: dict) -> str:
    return yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=100)


def _ensure_config_written(base: Path, slug: str, client_name: str) -> tuple[Path, bool]:
    """Scrive <base>/config/config.yaml SOLO se assente. Ritorna (path, created?)."""
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_text_fn = _require_dependency(d, "safe_write_text")

    cfg_dir = base / "config"
    ensure_within_fn(base, cfg_dir)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.yaml"
    if cfg_path.exists():
        return cfg_path, False

    tmpl = _load_repo_config_template()
    rendered = _render_client_config(tmpl, slug=slug, client_name=client_name)
    safe_write_text_fn(cfg_path, _safe_yaml_dump(rendered), encoding="utf-8", atomic=True)
    return cfg_path, True


def _make_minimal_pdf_bytes(text: str) -> bytes:
    """Genera un PDF 1-pagina minimale con il testo dato, senza librerie esterne."""
    # Escapa parentesi nel contenuto PDF
    safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 20 Tf 72 720 Td ({safe_text}) Tj ET\n"
    stream = content.encode("latin-1", errors="ignore")

    parts: list[bytes] = []
    offsets: list[int] = []

    def _w(b: bytes) -> None:
        parts.append(b)

    # header
    _w(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    # obj 1: catalog
    offsets.append(sum(len(p) for p in parts))
    _w(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # obj 2: pages
    offsets.append(sum(len(p) for p in parts))
    _w(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # obj 3: page
    offsets.append(sum(len(p) for p in parts))
    _w(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n"
    )
    # obj 4: contents (stream)
    offsets.append(sum(len(p) for p in parts))
    _w(f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1"))
    _w(stream)
    _w(b"endstream\nendobj\n")
    # obj 5: font
    offsets.append(sum(len(p) for p in parts))
    _w(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    # xref
    xref_offset = sum(len(p) for p in parts)
    xref = ["xref\n0 6\n", "0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n")
    _w("".join(xref).encode("ascii"))
    # trailer
    _w(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n")
    _w(str(xref_offset).encode("ascii"))
    _w(b"\n%%EOF\n")

    return b"".join(parts)


def _ensure_dummy_vision_pdf(base: Path, *, slug: str, client_name: str) -> tuple[Path, bool]:
    """Scrive PDF minimale 'VisionStatement.pdf' sotto config/ (idempotente)."""
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_bytes_fn = _require_dependency(d, "safe_write_bytes")

    cfg_dir = base / "config"
    ensure_within_fn(base, cfg_dir)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = cfg_dir / "VisionStatement.pdf"
    if pdf_path.exists():
        return pdf_path, False

    title = f"Dummy Vision Statement — {client_name} ({slug})"
    pdf_bytes = _make_minimal_pdf_bytes(title)
    safe_write_bytes_fn(pdf_path, pdf_bytes, atomic=True)
    return pdf_path, True


# ----------------------- RAW/ DOCS & STUB SEMANTICI -----------------------


def _ensure_raw_structure(base: Path, *, slug: str, client_name: str) -> dict[str, Any]:
    """
    Crea sottocartelle e PDF dummy sotto raw/:
      - raw/contracts/sample.pdf
      - raw/reports/sample.pdf
      - raw/presentations/sample.pdf
    Ritorna percorsi assoluti creati e lista dei path relativi (per cartelle_raw.yaml).
    """
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_bytes_fn = _require_dependency(d, "safe_write_bytes")

    categories = ["contracts", "reports", "presentations"]
    folders_abs: list[Path] = []
    folders_rel: list[str] = []
    pdfs_abs: list[Path] = []

    raw_dir = base / "raw"
    ensure_within_fn(base, raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for cat in categories:
        cat_dir = raw_dir / cat
        ensure_within_fn(base, cat_dir)
        cat_dir.mkdir(parents=True, exist_ok=True)
        folders_abs.append(cat_dir)
        folders_rel.append(str(cat_dir.relative_to(base)).replace("\\", "/"))

        # un PDF per cartella
        title = f"{client_name} ({slug}) — {cat.capitalize()} — Dummy"
        pdf_bytes = _make_minimal_pdf_bytes(title)
        pdf_path = cat_dir / "sample.pdf"
        safe_write_bytes_fn(pdf_path, pdf_bytes, atomic=True)
        pdfs_abs.append(pdf_path)

    return {"folders_abs": folders_abs, "folders_rel": folders_rel, "pdfs_abs": pdfs_abs}


def _semantic_mapping_payload(slug: str, client_name: str) -> dict[str, Any]:
    """
    Costruisce semantic_mapping.yaml secondo la struttura reale:
    - context
    - tre aree predefinite con ambito/descrizione/keywords
    - opzionale blocco synonyms (vuoto ma presente per stabilità schema)
    """
    return {
        "context": {"slug": slug, "client_name": client_name},
        # aree (chiavi top-level come da pipeline.vision_provision)
        "contracts": {
            "ambito": "Contrattualistica e forniture",
            "descrizione": "Documenti contrattuali, NDA, ordini di acquisto, accordi quadro e appendici.",
            "keywords": ["contratto", "NDA", "fornitore", "ordine", "appendice"],
        },
        "reports": {
            "ambito": "Reportistica e analisi",
            "descrizione": "Report periodici, metriche operative, analisi interne e rendicontazioni.",
            "keywords": ["report", "analisi", "rendiconto", "KPI", "metriche"],
        },
        "presentations": {
            "ambito": "Presentazioni e materiali",
            "descrizione": "Slide, presentazioni per stakeholder, materiali divulgativi e executive brief.",
            "keywords": ["presentazione", "slide", "deck", "brief", "stakeholder"],
        },
        "synonyms": {
            # opzionale ma utile: la pipeline accetta questo blocco
            "contracts": ["contratti", "accordi", "forniture"],
            "reports": ["rendiconti", "analitiche", "reportistica"],
            "presentations": ["slide", "deck", "presentazioni"],
        },
    }


def _ensure_semantic_stubs(
    base: Path,
    slug: str,
    client_name: str,
    raw_folders_rel: list[str] | None = None,
) -> dict[str, Any]:
    """Crea, se mancanti, i due YAML: semantic_mapping.yaml (struttura cliente) e cartelle_raw.yaml."""
    d = _ensure_dependencies()
    ensure_within_fn = _require_dependency(d, "ensure_within")
    safe_write_text_fn = _require_dependency(d, "safe_write_text")

    sem_dir = base / "semantic"
    ensure_within_fn(base, sem_dir)
    sem_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = sem_dir / "semantic_mapping.yaml"
    cartelle_path = sem_dir / "cartelle_raw.yaml"

    created_mapping = False
    created_cartelle = False

    if not mapping_path.exists():
        mapping_payload = _semantic_mapping_payload(slug, client_name)
        safe_write_text_fn(
            mapping_path,
            yaml.safe_dump(mapping_payload, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
            atomic=True,
        )
        created_mapping = True

    if not cartelle_path.exists():
        folders_value: list[Any] = list(raw_folders_rel or ["raw/contracts", "raw/reports", "raw/presentations"])
        cartelle_stub = {
            "folders": folders_value,  # lista di path relativi (es. "raw/contracts")
            "meta": {"source": "dummy", "slug": slug},
        }
        safe_write_text_fn(
            cartelle_path,
            yaml.safe_dump(cartelle_stub, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
            atomic=True,
        )
        created_cartelle = True

    return {
        "mapping_path": mapping_path,
        "cartelle_path": cartelle_path,
        "mapping_created": created_mapping,
        "cartelle_created": created_cartelle,
    }


# ----------------------- CLIENTS_DB (repo root) -----------------------


def _resolve_clients_db_path() -> Path:
    """Sceglie un file YAML in <repo_root>/clients_db/. Se non esiste nulla, usa clients.yaml."""
    db_dir = REPO_ROOT / "clients_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        db_dir / "clients.yaml",
        db_dir / "clients.yml",
        db_dir / "clients_db.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # default: clients.yaml


def _update_clients_db(
    slug: str,
    client_name: str,
    base: Path,
    cfg_rel: str = "config/config.yaml",
    pdf_rel: str = "config/VisionStatement.pdf",
) -> dict[str, Any]:
    """
    Aggiunge/aggiorna il cliente in clients_db (idempotente).
    - Preserva il formato esistente (dict keyed by slug oppure list di dict).
    - Se il file non esiste o è vuoto, crea un dict keyed by slug.
    """
    d = _ensure_dependencies()
    safe_write_text_fn = _require_dependency(d, "safe_write_text")
    ewr = _require_dependency(d, "ensure_within_and_resolve")
    rts = _require_dependency(d, "read_text_safe")

    db_path = _resolve_clients_db_path()
    safe_db_path = ewr(REPO_ROOT, db_path)

    existing: Any = None
    if safe_db_path.exists():
        try:
            text = rts(REPO_ROOT, safe_db_path, encoding="utf-8")
            existing = yaml.safe_load(text)
        except Exception:
            existing = None

    record = {
        "slug": slug,
        "name": client_name,
        "base": str(base),
        "config": cfg_rel,
        "vision_pdf": pdf_rel,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    created = False
    updated = False

    if existing is None:
        # crea dict keyed by slug
        data = {slug: record}
        created = True
    elif isinstance(existing, dict):
        prev = existing.get(slug)
        existing[slug] = {**(prev or {}), **record}
        data = existing
        updated = prev is not None
        created = not updated
    elif isinstance(existing, list):
        # lista di record: cerca per slug
        found = False
        for i, item in enumerate(existing):
            if isinstance(item, dict) and item.get("slug") == slug:
                existing[i] = {**item, **record}
                found = True
                updated = True
                break
        if not found:
            existing.append(record)
            created = True
        data = existing
    else:
        # formato ignoto → migra a dict keyed by slug
        data = {slug: record}
        created = True

    safe_write_text_fn(
        safe_db_path, yaml.safe_dump(data, allow_unicode=True, sort_keys=True, width=100), encoding="utf-8", atomic=True
    )
    return {"path": safe_db_path, "created": created, "updated": updated}


# ----------------------- main CLI -----------------------


def main(argv: list[str] | None = None) -> int:
    """Punto di ingresso CLI per generare un workspace dummy (richiamabile dai test)."""
    args = _parse_args(argv)
    d = _ensure_dependencies()
    get_logger = _require_dependency(d, "get_structured_logger")
    log = get_logger("tools.gen_dummy_kb")

    try:
        client_name = args.client_name or f"Dummy {args.slug}"

        ws_base = make_workspace(args.slug, args.base_dir)
        paths = _workspace_paths(args.slug, ws_base)
        # Crea le directory minime
        paths["base"].mkdir(parents=True, exist_ok=True)
        paths["raw"].mkdir(parents=True, exist_ok=True)
        paths["book"].mkdir(parents=True, exist_ok=True)
        paths["sem"].mkdir(parents=True, exist_ok=True)
        paths["cfg"].mkdir(parents=True, exist_ok=True)
        (paths["base"] / "logs").mkdir(parents=True, exist_ok=True)

        # Contenuti book
        _write_dummy_docs(paths["book"])
        _write_dummy_summary_readme(paths["book"])

        # Finanza dummy opzionale
        _maybe_write_dummy_finance(paths["base"], args.records)

        # RAW: sottocartelle + PDF dummy
        raw_info = _ensure_raw_structure(paths["base"], slug=args.slug, client_name=client_name)

        # Config + Vision PDF + YAML semantici (struttura cliente + folders raw/*)
        cfg_path, cfg_created = _ensure_config_written(paths["base"], args.slug, client_name)
        pdf_path, pdf_created = _ensure_dummy_vision_pdf(paths["base"], slug=args.slug, client_name=client_name)
        sem_info = _ensure_semantic_stubs(
            paths["base"], args.slug, client_name=client_name, raw_folders_rel=raw_info["folders_rel"]
        )

        # Aggiorna clients_db (repo root)
        db_info = _update_clients_db(
            slug=args.slug,
            client_name=client_name,
            base=paths["base"],
            cfg_rel="config/config.yaml",
            pdf_rel="config/VisionStatement.pdf",
        )

        log.info(
            "dummy_kb_generated",
            extra={
                "slug": args.slug,
                "client_name": client_name,
                "base": str(paths["base"]),
                "config": str(cfg_path),
                "config_created": bool(cfg_created),
                "vision_pdf": str(pdf_path),
                "vision_pdf_created": bool(pdf_created),
                "raw_folders": [str(p) for p in raw_info["folders_abs"]],
                "raw_pdfs": [str(p) for p in raw_info["pdfs_abs"]],
                "semantic_mapping": str(sem_info["mapping_path"]),
                "semantic_mapping_created": bool(sem_info["mapping_created"]),
                "cartelle_raw": str(sem_info["cartelle_path"]),
                "cartelle_raw_created": bool(sem_info["cartelle_created"]),
                "clients_db": str(db_info["path"]),
                "clients_db_created": bool(db_info["created"]),
                "clients_db_updated": bool(db_info["updated"]),
            },
        )
        return 0
    except Exception as exc:
        log.error("dummy_kb_failed", extra={"slug": args.slug, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
