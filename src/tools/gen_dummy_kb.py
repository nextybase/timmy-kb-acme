#!/usr/bin/env python3
# src/tools/gen_dummy_kb.py
"""
Tool: generazione sandbox *dummy* per Timmy-KB + tagging semantico iniziale (CSV).

Cosa fa
-------
- Crea una sandbox cliente in `output/timmy-kb-<slug>/` con struttura minima:
  * `raw/` (albero da `config/cartelle_raw.yaml`, **solo** sezione RAW)
  * `book/`, `semantic/`, `config/`, `logs/`
  * `semantic/cartelle_raw.yaml` (copia 1:1 del template)
  * `semantic/semantic_mapping.yaml` (merge: context + defaults + template)
  * `config/config.yaml` (minimale)
  * PDF *minimali* (1 pagina) per le sezioni RAW definite in `config/pdf_dummy.yaml`
  * `semantic/tags_raw.csv` generato via moduli `semantic.*`

- Garantisce **path-safety** (SSoT: `pipeline.path_utils.ensure_within`) e
  **scritture atomiche** (`pipeline.file_utils.safe_write_*`).

- **Niente print**: usa solo logging strutturato (`get_structured_logger`).
  Il main crea un *early logger* e poi, a sandbox creata, logga su file
  `logs/log.json` sotto la sandbox (se disponibile).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # PyYAML è richiesta
except Exception as e:  # pragma: no cover
    raise RuntimeError("PyYAML è richiesta per questo tool. Installa con: pip install pyyaml") from e

# ---------------------------------------------------------------------
# Percorsi repository
# ---------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_ROOT = REPO_ROOT / "output"

TEMPLATE_CARTELLE_RAW = CONFIG_DIR / "cartelle_raw.yaml"
TEMPLATE_MAPPING = CONFIG_DIR / "default_semantic_mapping.yaml"
TEMPLATE_PDF_DUMMY = CONFIG_DIR / "pdf_dummy.yaml"

DEFAULT_SLUG = "dummy"
DEFAULT_CLIENT_NAME = "Cliente Dummy"

# Assicura import moduli "semantic.*" e "pipeline.*"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
try:
    # semantic
    from pipeline.file_utils import safe_write_bytes, safe_write_text
    from pipeline.logging_utils import get_structured_logger, tail_path

    # pipeline (path-safety + atomic I/O + logging)
    from pipeline.path_utils import ensure_within, ensure_within_and_resolve, open_for_read_bytes_selfguard
    from semantic.auto_tagger import extract_semantic_candidates, render_tags_csv
    from semantic.config import load_semantic_config
    from semantic.normalizer import normalize_tags
    from semantic.tags_io import write_tagging_readme as _write_tagging_readme
    from semantic.tags_io import write_tags_review_stub_from_csv as _write_review_stub_from_csv

    try:
        from finance.api import import_csv as _fin_import_csv
    except Exception:  # pragma: no cover
        _fin_import_csv = None
except Exception as e:
    raise RuntimeError(
        (
            (
                "Impossibile importare i moduli richiesti. Verifica che il repo contenga 'src/semantic' e"
                "'src/pipeline' e che tu stia eseguendo lo script dalla root del progetto."
            )
        )
    ) from e


# ---------------------------------------------------------------------
# Utilità base
# ---------------------------------------------------------------------
def _read_yaml_required(p: Path) -> Dict[str, Any]:
    safe_path = ensure_within_and_resolve(p.parent, p)
    if not safe_path.exists():
        raise RuntimeError(f"File YAML mancante: {safe_path}")
    try:
        from pipeline.yaml_utils import yaml_read

        data = yaml_read(safe_path.parent, safe_path) or {}
    except Exception as e:
        raise RuntimeError(f"Errore lettura YAML {safe_path}: {e}")
    if not isinstance(data, dict):
        raise RuntimeError(f"Formato YAML non valido (atteso mapping/dict): {safe_path}")
    return data


def _write_text_in_base(base: Path, path: Path, content: str, *, overwrite: bool) -> None:
    """Scrittura atomica testo, con guardia STRONG sul perimetro base."""
    path = path.resolve()
    base = base.resolve()
    ensure_within(base, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return
    safe_write_text(path, content, encoding="utf-8", atomic=True)


def _write_bytes_in_base(base: Path, path: Path, data: bytes, *, overwrite: bool) -> None:
    """Scrittura atomica bytes, con guardia STRONG sul perimetro base."""
    path = path.resolve()
    base = base.resolve()
    ensure_within(base, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return
    safe_write_bytes(path, data, atomic=True)


def _now_date() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------
# PDF minimale (una pagina, titolo + paragrafi)
# ---------------------------------------------------------------------
def _wrap_lines(text: str, max_len: int = 90) -> List[str]:
    lines: List[str] = []
    for raw in (text or "").splitlines() or [""]:
        raw = raw.strip()
        if not raw:
            lines.append("")
            continue
        while len(raw) > max_len:
            lines.append(raw[:max_len])
            raw = raw[max_len:]
        lines.append(raw)
    return lines or [""]


def _make_minimal_pdf_bytes(title: str, paragraphs: List[str]) -> bytes:
    y = 780

    def esc(s: str) -> str:
        return s.replace("(", "[").replace(")", "]")

    cmds = [f"BT /F1 14 Tf 40 {y} Td ({esc(title)}) Tj ET"]
    y -= 22
    for par in paragraphs:
        for ln in _wrap_lines(par, 90):
            cmds.append(f"BT /F1 10 Tf 40 {y} Td ({esc(ln)}) Tj ET")
            y -= 14
            if y < 40:
                break
        if y < 40:
            break
        y -= 6
    stream = "\n".join(cmds)
    stream_len = len(stream.encode("latin-1", errors="ignore"))
    pdf = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length {stream_len}>>stream
{stream}
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000010 00000 n
0000000060 00000 n
0000000115 00000 n
0000000275 00000 n
0000000416 00000 n
trailer<</Root 1 0 R/Size 6>>
startxref
500
%%EOF
"""
    return pdf.encode("latin-1", errors="ignore")


# ---------------------------------------------------------------------
# Builders mapping/config
# ---------------------------------------------------------------------
def _yaml_dump_context(slug: str, client_name: str) -> Dict[str, Any]:
    return {"context": {"slug": slug, "client_name": client_name, "created_at": _now_date()}}


def _yaml_dump_semantic_tagger_defaults() -> Dict[str, Any]:
    return {
        "semantic_tagger": {
            "lang": "it",
            "max_pages": 5,
            "top_k": 10,
            "score_min": 0.40,
            "ner": True,
            "keyphrases": True,
            "embeddings": False,
            "stop_tags": ["bozza", "varie"],
        }
    }


def _merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dicts(out[k], v)
        else:
            out[k] = v
    return out


def _build_semantic_mapping_yaml(slug: str, client_name: str, template_mapping: Dict[str, Any]) -> str:
    data: Dict[str, Any] = {}
    data = _merge_dicts(data, _yaml_dump_context(slug, client_name))
    data = _merge_dicts(data, _yaml_dump_semantic_tagger_defaults())
    data = _merge_dicts(data, template_mapping or {})
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _min_config_yaml(client_name: str) -> str:
    """Config minimale per sandbox dummy, allineato al template di repo.

    Include i nuovi campi di versioning gestiti dalla UI/pipeline:
    - N_VER: parte da 0
    - DATA_VER: null
    """
    return yaml.safe_dump(
        {
            "client_name": client_name,
            "semantic_defaults": {"lang": "it"},
            "N_VER": 0,
            "DATA_VER": None,
        },
        allow_unicode=True,
        sort_keys=False,
    )


# ---------------------------------------------------------------------
# Costruzione SOLO dell’albero raw/ da cartelle_raw.yaml
# ---------------------------------------------------------------------
def _create_tree_from_spec(root_base: Path, node: Dict[str, Any]) -> None:
    name = str(node.get("name") or "").strip()
    if not name:
        return
    base = root_base / name
    base.mkdir(parents=True, exist_ok=True)
    subs = node.get("subfolders") or []
    if isinstance(subs, list):
        for child in subs:
            if isinstance(child, dict):
                _create_tree_from_spec(base, child)


def _build_only_raw(base_dir: Path, spec: Dict[str, Any]) -> None:
    """Crea solo la root 'raw' e le sue sotto-cartelle (ignora altre sezioni).

    Formato supportato (v1.8.0): mapping moderno con chiave 'raw'.
    Esempio: { "raw": { "identity": {}, ... }, "contrattualistica": {} }
    """
    raw_map = spec.get("raw")
    if not isinstance(raw_map, dict):
        raise RuntimeError("cartelle_raw.yaml: atteso mapping moderno con chiave 'raw': {raw: {...}}.")
    raw_base = base_dir / "raw"
    raw_base.mkdir(parents=True, exist_ok=True)

    def _mk_from_map(base: Path, mapping: Dict[str, Any]) -> None:
        for k, v in (mapping or {}).items():
            child = base / str(k)
            child.mkdir(parents=True, exist_ok=True)
            if isinstance(v, dict):
                _mk_from_map(child, v)
            elif isinstance(v, (list, tuple)):
                for leaf in v:
                    (child / str(leaf)).mkdir(parents=True, exist_ok=True)

    _mk_from_map(raw_base, raw_map)


# ---------------------------------------------------------------------
# PDF da pdf_dummy.yaml (RAW soltanto)
# ---------------------------------------------------------------------
_RAW_SECTIONS = {
    "identity": "identity",
    "organizzazione": "organizzazione",
    "artefatti-operativi": "artefatti-operativi",
    "glossario": "glossario",
    "best-practices": "best-practices",
    "normativa": "normativa",
    "scenario": "scenario",
    "economy": "economy",
    "template-documenti": "template-documenti",
}


def _emit_pdfs_from_pdf_dummy(
    base: Path, raw_dir: Path, pdf_dummy: Dict[str, Any], slug: str, overwrite: bool
) -> List[Path]:
    """Genera PDF SOLO per le sezioni RAW."""
    created: List[Path] = []
    for section, payload in pdf_dummy.items():
        if not isinstance(payload, dict):
            raise RuntimeError(f"pdf_dummy.yaml: sezione '{section}' non è un mapping (titolo/paragrafi).")
        titolo = str(payload.get("titolo") or section).strip()
        paragrafi = payload.get("paragrafi")
        if not isinstance(paragrafi, list) or not paragrafi:
            raise RuntimeError(f"pdf_dummy.yaml: sezione '{section}' richiede 'paragrafi: [ ... ]' non vuoto.")

        if section == "raw":
            dst_dir = raw_dir
            file_name = f"_readme_{slug}.pdf"
        else:
            sub = _RAW_SECTIONS.get(section)
            if not sub:
                continue  # NON RAW (es. contrattualistica) -> skip
            dst_dir = raw_dir / sub
            file_name = f"{sub}_intro_{slug}.pdf"

        dst_dir.mkdir(parents=True, exist_ok=True)
        out = (dst_dir / file_name).resolve()
        ensure_within(base.resolve(), out)
        pdf_bytes = _make_minimal_pdf_bytes(titolo, [str(p) for p in paragrafi])
        if out.exists() and not overwrite:
            continue
        safe_write_bytes(out, pdf_bytes, atomic=True)
        created.append(out)
    return created


# ---------------------------------------------------------------------
# Builder principale
# ---------------------------------------------------------------------
def build_dummy_kb(
    slug: str,
    client_name: str,
    *,
    overwrite: bool,
    logger: logging.Logger | None = None,
) -> Path:
    """Costruisce la sandbox *dummy* per un cliente, generando cartelle, file YAML minimi, PDF di
    test e CSV dei tag.

    Args:
        slug: identificatore cliente.
        client_name: nome cliente.
        overwrite: se True, sovrascrive file già presenti.
        logger: logger strutturato per audit (opzionale).

    Restituisce:
        Path della sandbox cliente generata.
    """
    # Log iniziale
    if logger:
        logger.info(
            "Start build sandbox dummy",
            extra={"slug": slug, "client_name": client_name},
        )

    # 1) leggi template contrattuali
    if logger:
        logger.info(
            "Caricamento template YAML",
            extra={
                "cartelle_raw": str(TEMPLATE_CARTELLE_RAW),
                "mapping": str(TEMPLATE_MAPPING),
                "pdf_dummy": str(TEMPLATE_PDF_DUMMY),
            },
        )
    template_cartelle_path = ensure_within_and_resolve(CONFIG_DIR, TEMPLATE_CARTELLE_RAW)
    template_pdf_path = ensure_within_and_resolve(CONFIG_DIR, TEMPLATE_PDF_DUMMY)
    template_mapping_path = ensure_within_and_resolve(CONFIG_DIR, TEMPLATE_MAPPING)
    cartelle = _read_yaml_required(template_cartelle_path)
    with open_for_read_bytes_selfguard(template_cartelle_path) as cartelle_file:
        cartelle_bytes = cartelle_file.read()
    pdf_dummy = _read_yaml_required(template_pdf_path)
    mapping_template = _read_yaml_required(template_mapping_path)

    # 2) destinazione sandbox
    base = (OUTPUT_ROOT / f"timmy-kb-{slug}").resolve()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_within(OUTPUT_ROOT.resolve(), base)
    if logger:
        logger.info(
            "Base destinazione risolta",
            extra={"base": str(base), "tail": tail_path(base)},
        )

    # 3) crea cartelle standard + SOLO l’albero raw/
    book_dir = base / "book"
    semantic_dir = base / "semantic"
    config_dir = base / "config"
    logs_dir = base / "logs"
    for d in (book_dir, semantic_dir, config_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)
    if logger:
        logger.info(
            "Cartelle base create",
            extra={
                "book": str(book_dir),
                "semantic": str(semantic_dir),
                "config": str(config_dir),
                "logs": str(logs_dir),
            },
        )

    _build_only_raw(base, cartelle)
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if logger:
        logger.info("Albero RAW creato/garantito", extra={"raw": str(raw_dir)})

    # 4) template in semantic + mapping con context/tagger defaults
    _write_bytes_in_base(
        base,
        semantic_dir / "cartelle_raw.yaml",
        cartelle_bytes,
        overwrite=overwrite,
    )
    if logger:
        logger.info(
            "cartelle_raw.yaml copiato in semantic/",
            extra={"file_path": str(semantic_dir / "cartelle_raw.yaml")},
        )

    mapping_text = _build_semantic_mapping_yaml(slug, client_name, mapping_template)
    _write_text_in_base(base, semantic_dir / "semantic_mapping.yaml", mapping_text, overwrite=overwrite)
    if logger:
        logger.info(
            "semantic_mapping.yaml generato",
            extra={"file_path": str(semantic_dir / "semantic_mapping.yaml")},
        )

    # 5) config/config.yaml minimale
    _write_text_in_base(
        base,
        config_dir / "config.yaml",
        _min_config_yaml(client_name),
        overwrite=overwrite,
    )
    if logger:
        logger.info(
            "config.yaml minimale scritto",
            extra={"file_path": str(config_dir / "config.yaml")},
        )

    # 6) genera PDF SOLO per RAW
    created_pdfs = _emit_pdfs_from_pdf_dummy(base, raw_dir, pdf_dummy, slug, overwrite=overwrite)
    if logger:
        logger.info(
            "PDF dummy generati",
            extra={
                "count": len(created_pdfs),
                "first_files": [p.name for p in created_pdfs[:5]],
                "target_root": str(raw_dir),
            },
        )

    # 7) CSV via moduli semantic (RAW -> tags_raw.csv)
    if logger:
        logger.info("Estrazione candidati semantici (RAW -> tags_raw.csv)")
    cfg = load_semantic_config(base)

    candidates = extract_semantic_candidates(cfg.raw_dir, cfg)
    cand_len: int | None
    try:
        cand_len = len(candidates)
    except Exception:
        cand_len = None
    if logger:
        logger.info("Candidati estratti", extra={"count": cand_len})

    candidates_norm = normalize_tags(candidates, cfg.mapping)
    norm_len: int | None
    try:
        norm_len = len(candidates_norm)
    except Exception:
        norm_len = None
    tags_csv_path = cfg.semantic_dir / "tags_raw.csv"
    render_tags_csv(candidates_norm, tags_csv_path, base_dir=base)
    if logger:
        logger.info(
            "CSV semantico scritto",
            extra={
                "file_path": str(tags_csv_path),
                "candidates": cand_len,
                "normalized": norm_len,
            },
        )

    # README_TAGGING e stub reviewed -> genera DB SQLite minimale (tags.db)
    try:
        _write_tagging_readme(semantic_dir, logger or get_structured_logger("gen_dummy_kb"))
        _write_review_stub_from_csv(
            semantic_dir,
            tags_csv_path,
            logger or get_structured_logger("gen_dummy_kb"),
            top_n=8,
        )
        if logger:
            logger.info(
                "tags_reviewed stub generato in DB (da CSV)",
                extra={"csv": str(tags_csv_path), "db": str(semantic_dir / "tags.db")},
            )
    except Exception as e:
        if logger:
            logger.warning("Impossibile generare stub reviewed/DB", extra={"error": str(e)})

    # (Opz.) Finanza: genera un CSV minimo e importalo in semantic/finance.db
    try:
        if _fin_import_csv is not None:
            fin_csv = semantic_dir / "finance_dummy.csv"
            fin_rows = [
                "metric,period,value,unit,currency,canonical_term\n",
                "revenues,2023,1250000,EUR,EUR,fatturato\n",
                "ebitda,2023Q4,210000,EUR,EUR,ebitda\n",
                "market_share,2024H1,0.123,, ,quota-mercato\n",
            ]
            _write_text_in_base(base, fin_csv, "".join(fin_rows), overwrite=True)
            res = _fin_import_csv(base, fin_csv)
            if logger:
                logger.info(
                    "Finanza: import CSV",
                    extra={
                        "csv": str(fin_csv),
                        "rows": getattr(res, "rows", None) if res is not None else None,
                        "db": getattr(res, "db", None) if res is not None else None,
                    },
                )
    except Exception as e:
        if logger:
            logger.warning("Import finanza fallito (opzionale)", extra={"error": str(e)})

    if logger:
        logger.info(
            "Sandbox dummy creata",
            extra={
                "base": str(base),
                "base_tail": tail_path(base),
                "raw_tail": tail_path(raw_dir),
            },
        )
    return base


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Genera sandbox cliente dummy (RAW-only) + tags_raw.csv via moduli semantic"
    )
    p.add_argument(
        "--out",
        required=False,
        help="Cartella di output in cui creare la sandbox (es. temp dir di pytest)",
    )
    p.add_argument("--slug", type=str, default=DEFAULT_SLUG, help="Slug cliente (default: dummy)")
    p.add_argument(
        "--name",
        type=str,
        default=DEFAULT_CLIENT_NAME,
        help="Nome cliente (default: Cliente Dummy)",
    )
    p.add_argument("--overwrite", action="store_true", help="Sovrascrive file già esistenti")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    # Fallback: forza stdout/stderr UTF-8 per console Windows (evita UnicodeEncodeError)
    try:
        stdout_reconf = getattr(sys.stdout, "reconfigure", None)
        stderr_reconf = getattr(sys.stderr, "reconfigure", None)
        if not callable(stdout_reconf) or not callable(stderr_reconf):
            raise AttributeError("reconfigure not callable")
        stdout_reconf(encoding="utf-8", errors="replace")
        stderr_reconf(encoding="utf-8", errors="replace")
    except Exception:
        try:
            import io as _io

            buffer_out = getattr(sys.stdout, "buffer", None)
            if isinstance(buffer_out, _io.BufferedWriter):
                sys.stdout = _io.TextIOWrapper(buffer_out, encoding="utf-8", errors="replace")
            buffer_err = getattr(sys.stderr, "buffer", None)
            if isinstance(buffer_err, _io.BufferedWriter):
                sys.stderr = _io.TextIOWrapper(buffer_err, encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Override dinamico della root di output solo se passato da CLI
    if getattr(args, "out", None):
        from pathlib import Path as _Path

        global OUTPUT_ROOT
        OUTPUT_ROOT = _Path(args.out)
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("gen_dummy_kb", run_id=run_id)

    try:
        base = build_dummy_kb(
            slug=(args.slug or DEFAULT_SLUG).strip(),
            client_name=(args.name or DEFAULT_CLIENT_NAME).strip(),
            overwrite=bool(args.overwrite),
            logger=early_logger,
        )
        # Dopo la build, spostiamo il logging sul file per-cliente
        log_file = (base / "logs" / "log.json").resolve()
        try:
            ensure_within(base, log_file)
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logger = get_structured_logger("gen_dummy_kb", log_file=log_file, run_id=run_id)
        except Exception:
            logger = early_logger  # fallback

        logger.info(
            "Fine: sandbox pronta",
            extra={"base": str(base), "base_tail": tail_path(base)},
        )
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        early_logger.error(f"Errore nella generazione sandbox: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
