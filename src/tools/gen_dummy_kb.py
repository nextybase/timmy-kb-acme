#!/usr/bin/env python3
# src/tools/gen_dummy_kb.py
"""
Genera la sandbox *completa* per un cliente dummy, aderendo ai formati
in ./config e PRODUCENDO il CSV tramite i moduli di arricchimento semantico.

Template attesi in ./config:
- cartelle_raw.yaml  (schema fisso con root_folders/subfolders)
- default_semantic_mapping.yaml
- pdf_dummy.yaml     (dizionario: sezione -> {titolo, paragrafi: [...]})

Crea sotto output/timmy-kb-<slug>/ :
- SOLO l’albero raw/ dalla cartelle_raw.yaml (contrattualistica NON viene creata in locale)
- semantic/cartelle_raw.yaml (copia 1:1)
- semantic/semantic_mapping.yaml (context + semantic_tagger default + merge template)
- config/config.yaml (minimale)
- PDF per ogni sezione di pdf_dummy.yaml che appartiene a RAW (contrattualistica viene ignorata)
- semantic/tags_raw.csv generato da: config.load_semantic_config → auto_tagger.extract_semantic_candidates →
  normalizer.normalize_tags → auto_tagger.render_tags_csv

Uso:
  py src/tools/gen_dummy_kb.py [--slug dummy] [--name "Cliente Dummy"] [--overwrite]

Dipendenze:
  - PyYAML
  - I moduli locali: src/semantic/{config,auto_tagger,normalizer}
"""

from __future__ import annotations

import argparse
import os
import datetime as _dt
import sys
from pathlib import Path
from typing import Dict, Any, List

try:
    import yaml  # PyYAML è richiesta
except Exception as e:  # pragma: no cover
    raise RuntimeError("PyYAML è richiesta per questo tool. Installa con: pip install pyyaml") from e

# ----------------------------------------------------------------------------- #
# Percorsi repository
# ----------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_ROOT = REPO_ROOT / "output"

TEMPLATE_CARTELLE_RAW = CONFIG_DIR / "cartelle_raw.yaml"
TEMPLATE_MAPPING = CONFIG_DIR / "default_semantic_mapping.yaml"
TEMPLATE_PDF_DUMMY = CONFIG_DIR / "pdf_dummy.yaml"

DEFAULT_SLUG = "dummy"
DEFAULT_CLIENT_NAME = "Cliente Dummy"

# Assicura import moduli "src.semantic.*"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
try:
    from src.semantic.config import load_semantic_config
    from src.semantic.auto_tagger import extract_semantic_candidates, render_tags_csv
    from src.semantic.normalizer import normalize_tags
except Exception as e:
    raise RuntimeError(
        "Impossibile importare i moduli semantic. Verifica che il repo contenga 'src/semantic' "
        "e che tu stia eseguendo lo script dalla root del progetto."
    ) from e

# ----------------------------------------------------------------------------- #
# Utilità base
# ----------------------------------------------------------------------------- #

def _ensure_within(base: Path, target: Path) -> None:
    base = base.resolve()
    target = target.resolve()
    if target == base:
        return
    if not str(target).startswith(str(base) + os.sep):
        raise ValueError(f"Path non consentito: {target} non è sotto {base}")

def _read_yaml_required(p: Path) -> Dict[str, Any]:
    if not p.exists():
        raise RuntimeError(f"File YAML mancante: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Formato YAML non valido (atteso mapping/dict): {p}")
    return data

def _write_text(path: Path, content: str, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return
    path.write_text(content, encoding="utf-8")

def _copy_file(src: Path, dst: Path, *, overwrite: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not overwrite:
        return
    dst.write_bytes(src.read_bytes())

def _now_date() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d")

# ----------------------------------------------------------------------------- #
# PDF minimale (una pagina, titolo + paragrafi)
# ----------------------------------------------------------------------------- #

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

# ----------------------------------------------------------------------------- #
# Builders mapping/config
# ----------------------------------------------------------------------------- #

def _yaml_dump_context(slug: str, client_name: str) -> Dict[str, Any]:
    return {"context": {"slug": slug, "client_name": client_name, "created_at": _now_date()}}

def _yaml_dump_semantic_tagger_defaults() -> Dict[str, Any]:
    return {"semantic_tagger": {
        "lang": "it", "max_pages": 5, "top_k": 10, "score_min": 0.40,
        "ner": True, "keyphrases": True, "embeddings": False,
        "stop_tags": ["bozza", "varie"],
    }}

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
    return yaml.safe_dump({"client_name": client_name, "semantic_defaults": {"lang": "it"}}, allow_unicode=True, sort_keys=False)

# ----------------------------------------------------------------------------- #
# Costruzione SOLO dell’albero raw/ da cartelle_raw.yaml
# ----------------------------------------------------------------------------- #

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
    """
    Crea solo la root 'raw' e le sue sotto-cartelle (ignora altre root come 'contrattualistica').
    """
    roots = spec.get("root_folders")
    if not isinstance(roots, list):
        raise RuntimeError("cartelle_raw.yaml: atteso campo 'root_folders: [...]' con nodi {name, subfolders}.")
    raw_node = next((n for n in roots if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == "raw"), None)
    # garantiamo comunque raw/ anche senza specifica
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    if raw_node:
        # crea SOLO l’albero sotto raw/
        _create_tree_from_spec(base_dir, raw_node)

# ----------------------------------------------------------------------------- #
# PDF da pdf_dummy.yaml (RAW soltanto)
# ----------------------------------------------------------------------------- #

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

def _emit_pdfs_from_pdf_dummy(base: Path, raw_dir: Path, pdf_dummy: Dict[str, Any], slug: str, overwrite: bool) -> List[Path]:
    """
    Genera PDF SOLO per le sezioni RAW.
      - sezioni RAW note -> raw/<sezione>/<sezione>_intro_<slug>.pdf
      - 'raw'            -> raw/_readme_<slug>.pdf
      - 'contrattualistica' (e altre non RAW) -> IGNORATE (gestite su Drive)
    """
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
                # sezione NON RAW (es. contrattualistica) -> salta
                continue
            dst_dir = raw_dir / sub
            file_name = f"{sub}_intro_{slug}.pdf"

        dst_dir.mkdir(parents=True, exist_ok=True)
        out = dst_dir / file_name
        _ensure_within(base, out)
        pdf_bytes = _make_minimal_pdf_bytes(titolo, [str(p) for p in paragrafi])
        if out.exists() and not overwrite:
            continue
        out.write_bytes(pdf_bytes)
        created.append(out)
    return created

# ----------------------------------------------------------------------------- #
# Builder principale
# ----------------------------------------------------------------------------- #

def build_dummy_kb(slug: str, client_name: str, *, overwrite: bool) -> Path:
    # 1) leggi template contrattuali
    cartelle = _read_yaml_required(TEMPLATE_CARTELLE_RAW)
    pdf_dummy = _read_yaml_required(TEMPLATE_PDF_DUMMY)
    mapping_template = _read_yaml_required(TEMPLATE_MAPPING)

    # 2) destinazione sandbox
    base = (OUTPUT_ROOT / f"timmy-kb-{slug}").resolve()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _ensure_within(OUTPUT_ROOT, base)

    # 3) crea cartelle standard + SOLO l’albero raw/
    book_dir = base / "book"
    semantic_dir = base / "semantic"
    config_dir = base / "config"
    logs_dir = base / "logs"
    for d in (book_dir, semantic_dir, config_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    _build_only_raw(base, cartelle)
    raw_dir = base / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)  # garantiamo comunque raw/

    # 4) copia template in semantic + mapping con context/tagger defaults
    _copy_file(TEMPLATE_CARTELLE_RAW, semantic_dir / "cartelle_raw.yaml", overwrite=overwrite)
    mapping_text = _build_semantic_mapping_yaml(slug, client_name, mapping_template)
    _write_text(semantic_dir / "semantic_mapping.yaml", mapping_text, overwrite=overwrite)

    # 5) config/config.yaml minimale
    _write_text(config_dir / "config.yaml", _min_config_yaml(client_name), overwrite=overwrite)

    # 6) genera PDF SOLO per RAW da pdf_dummy.yaml
    _ = _emit_pdfs_from_pdf_dummy(base, raw_dir, pdf_dummy, slug, overwrite=overwrite)

    # 7) >>> GENERAZIONE DINAMICA DEL CSV via moduli semantic (scansione RAW) <<<
    cfg = load_semantic_config(base)                         # carica defaults + mapping
    candidates = extract_semantic_candidates(cfg.raw_dir, cfg)   # euristiche path/filename (RAW)
    candidates_norm = normalize_tags(candidates, cfg.mapping)    # canonical/synonyms/rules
    render_tags_csv(candidates_norm, cfg.semantic_dir / "tags_raw.csv")

    return base

# ----------------------------------------------------------------------------- #
# CLI
# ----------------------------------------------------------------------------- #

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Genera sandbox cliente dummy (RAW-only) + tags_raw.csv via moduli semantic")
    p.add_argument("--slug", type=str, default=DEFAULT_SLUG, help="Slug cliente (default: dummy)")
    p.add_argument("--name", type=str, default=DEFAULT_CLIENT_NAME, help="Nome cliente (default: Cliente Dummy)")
    p.add_argument("--overwrite", action="store_true", help="Sovrascrive file già esistenti")
    return p.parse_args()

def main():
    args = _parse_args()
    base = build_dummy_kb(
        slug=(args.slug or DEFAULT_SLUG).strip(),
        client_name=(args.name or DEFAULT_CLIENT_NAME).strip(),
        overwrite=bool(args.overwrite),
    )
    print(f"✅ Sandbox creata in: {base}")

if __name__ == "__main__":
    main()
