# SPDX-License-Identifier: GPL-3.0-or-later
"""Funzioni di supporto per la generazione della dummy KB (semantic/mapping/raw)."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Optional

try:
    import yaml
except Exception:
    yaml = None  # type: ignore

from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, to_kebab

try:
    from pipeline.file_utils import safe_write_bytes, safe_write_text
except Exception:  # pragma: no cover
    safe_write_bytes = None  # type: ignore
    safe_write_text = None  # type: ignore

try:
    from storage import tags_store as _tags_store  # type: ignore
except Exception:  # pragma: no cover - opzionale
    _tags_store = None  # type: ignore[assignment]

_MINIMAL_RAW_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _yaml_quote(value: str) -> str:
    """Serializza stringhe in stile YAML sfruttando json.dumps per escaping."""
    return json.dumps(str(value), ensure_ascii=False)


def _render_default_mapping_yaml(slug: str, client_name: str) -> str:
    return (
        dedent(
            f"""\
            context:
              slug: {_yaml_quote(slug)}
              client_name: {_yaml_quote(client_name)}
            contracts:
              ambito: "Contrattualistica e forniture"
              descrizione: "Documenti contrattuali, NDA, ordini di acquisto, accordi quadro e appendici."
              keywords:
                - "contratto"
                - "NDA"
                - "fornitore"
                - "ordine"
                - "appendice"
            reports:
              ambito: "Reportistica e analisi"
              descrizione: "Report periodici, metriche operative, analisi interne e rendicontazioni."
              keywords:
                - "report"
                - "analisi"
                - "rendiconto"
                - "KPI"
                - "metriche"
            presentations:
              ambito: "Presentazioni e materiali"
              descrizione: "Slide, presentazioni per stakeholder, materiali divulgativi e executive brief."
              keywords:
                - "presentazione"
                - "slide"
                - "deck"
                - "brief"
                - "stakeholder"
            synonyms:
              contracts:
                - "contratti"
                - "accordi"
                - "forniture"
              reports:
                - "rendiconti"
                - "analitiche"
                - "reportistica"
              presentations:
                - "slide"
                - "deck"
                - "presentazioni"
            system_folders:
              identity: "book/identity"
              glossario: "book/glossario"
            """
        ).strip()
        + "\n"
    )


def _render_default_cartelle_yaml(slug: str) -> str:
    return (
        dedent(
            f"""\
            version: 1
            folders:
              - "raw/contracts"
              - "raw/reports"
              - "raw/presentations"
            system_folders:
              identity: "book/identity"
              glossario: "book/glossario"
            meta:
              source: "dummy"
              slug: {_yaml_quote(slug)}
            """
        ).strip()
        + "\n"
    )


def _default_mapping_data(slug: str, client_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = {
        "context": {"slug": slug, "client_name": client_name},
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
            "contracts": ["contratti", "accordi", "forniture"],
            "reports": ["rendiconti", "analitiche", "reportistica"],
            "presentations": ["slide", "deck", "presentazioni"],
        },
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
    }
    cartelle = {
        "version": 1,
        "folders": ["raw/contracts", "raw/reports", "raw/presentations"],
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
        "meta": {"source": "dummy", "slug": slug},
    }
    return mapping, cartelle


def _mapping_categories_from_default(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    categories: dict[str, dict[str, Any]] = {}
    for key in ("contracts", "reports", "presentations"):
        section = mapping.get(key) or {}
        cat_key = to_kebab(str(key))
        categories[cat_key] = {
            "ambito": str(section.get("ambito") or key.title()),
            "descrizione": str(section.get("descrizione") or ""),
            "keywords": [str(x).strip() for x in section.get("keywords") or [] if str(x).strip()],
        }
    return categories


def _safe_dump_yaml(path: Path, data: Any, *, fallback: str) -> None:
    if yaml is not None and safe_write_text:
        safe_write_text(
            path,
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),  # type: ignore[arg-type]
            encoding="utf-8",
            atomic=True,
        )
        return
    if safe_write_text:
        safe_write_text(path, fallback, encoding="utf-8", atomic=True)


def write_basic_semantic_yaml(base_dir: Path, *, slug: str, client_name: str) -> dict[str, str]:
    """
    Genera YAML "basici" senza passare da Vision:
      - semantic/semantic_mapping.yaml
      - semantic/cartelle_raw.yaml
    Crea anche le cartelle raw/ di base (contracts/reports/presentations).
    """
    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = base_dir / "raw"
    for name in ("contracts", "reports", "presentations"):
        (raw_dir / name).mkdir(parents=True, exist_ok=True)

    mapping_data, cartelle_data = _default_mapping_data(slug, client_name)
    mapping_path = sem_dir / "semantic_mapping.yaml"
    cartelle_path = sem_dir / "cartelle_raw.yaml"
    _safe_dump_yaml(mapping_path, mapping_data, fallback=_render_default_mapping_yaml(slug, client_name))
    _safe_dump_yaml(cartelle_path, cartelle_data, fallback=_render_default_cartelle_yaml(slug))

    # Genera contenuti minimi in book/ per i test smoke (alpha/beta + README/SUMMARY).
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "alpha.md": "# Alpha\n\nContenuto di esempio per la cartella contracts.\n",
        "beta.md": "# Beta\n\nContenuto di esempio per la cartella reports.\n",
        "README.md": "# Dummy KB\n",
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
    }
    for name, content in defaults.items():
        target = book_dir / name
        if not target.exists() and safe_write_text:
            safe_write_text(target, content, encoding="utf-8", atomic=True)

    categories = _mapping_categories_from_default(mapping_data)

    return {"mapping": str(mapping_path), "cartelle": str(cartelle_path), "categories": categories}


def _render_local_readme_bytes(title: str, descr: str, examples: list[str]) -> tuple[bytes, str]:
    """Replica minimale del renderer PDF dei README (fallback su TXT se reportlab assente)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        x, y = 2 * cm, height - 2 * cm

        def draw_line(text: str, font: str = "Helvetica", size: int = 11, leading: int = 14) -> None:
            nonlocal y
            c.setFont(font, size)
            for line in (text or "").splitlines() or [""]:
                c.drawString(x, y, line[:120])
                y -= leading
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm

        c.setTitle(f"README - {title}")
        draw_line(f"README - {title}", font="Helvetica-Bold", size=14, leading=18)
        y -= 4
        draw_line("")
        draw_line("Ambito:", font="Helvetica-Bold", size=12, leading=16)
        draw_line(descr or "")
        draw_line("")
        draw_line("Esempi:", font="Helvetica-Bold", size=12, leading=16)
        for ex in examples or []:
            draw_line(f"- {ex}")
        c.showPage()
        c.save()
        data = buf.getvalue()
        buf.close()
        return data, "application/pdf"
    except Exception:
        lines = [f"README - {title}", "", "Ambito:", descr or "", "", "Esempi:"]
        lines.extend(f"- {ex}" for ex in (examples or []))
        return ("\n".join(lines)).encode("utf-8"), "text/plain"


def ensure_raw_pdfs(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]] = None) -> None:
    """
    Deposita un PDF minimale in ogni sottocartella di raw/ (inclusa la root).

    Serve per i test/gating che richiedono la presenza di almeno un PDF valido
    anche in ambienti privi di reportlab.
    """
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    candidate_dirs: set[Path] = {raw_dir}
    for sub in raw_dir.iterdir():
        if sub.is_dir():
            candidate_dirs.add(sub)

    catalogue = categories or {}
    for key in catalogue.keys():
        candidate_dirs.add(raw_dir / to_kebab(key))

    for subdir in sorted(candidate_dirs):
        subdir.mkdir(parents=True, exist_ok=True)
        existing_pdf = next((p for p in subdir.iterdir() if p.suffix.lower() == ".pdf"), None)
        if existing_pdf is None and safe_write_bytes:
            target = subdir / "sample.pdf"
            safe_write_bytes(target, _MINIMAL_RAW_PDF, atomic=True)


def ensure_minimal_tags_db(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]], *, logger) -> None:
    """Crea un tags.db minimale (schema v2) per sbloccare il gating semantico dei dummy."""
    if _tags_store is None:
        return

    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    try:
        db_path = ensure_within_and_resolve(sem_dir, sem_dir / "tags.db")
        _tags_store.ensure_schema_v2(str(db_path))
        payload_tags: list[dict[str, Any]] = []
        catalogue = categories or {}
        if catalogue:
            for key, meta in catalogue.items():
                canonical = str(meta.get("ambito") or key or "tag").strip() or "tag"
                aliases = [str(a).strip() for a in meta.get("keywords") or [] if str(a).strip()]
                payload_tags.append({"name": canonical, "action": "keep", "synonyms": aliases, "note": None})
        else:
            payload_tags.append({"name": "dummy", "action": "keep", "synonyms": ["placeholder"], "note": None})

        payload = {
            "version": "2",
            "reviewed_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "keep_only_listed": False,
            "tags": payload_tags,
        }
        _tags_store.save_tags_reviewed(str(db_path), payload)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning(
            "tools.gen_dummy_kb.tags_db_seed_failed",
            extra={"slug": base_dir.name, "error": str(exc)},
        )


def write_minimal_tags_raw(base_dir: Path) -> Path:
    """
    Scrive un tags_raw.json minimale compatibile con kg_builder.
    """
    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    target = sem_dir / "tags_raw.json"
    payload = [
        {
            "label": "contratti",
            "path": "book/alpha.md",
            "contexts": ["contratti", "forniture"],
        },
        {
            "label": "report",
            "path": "book/beta.md",
            "contexts": ["reportistica", "metriche"],
        },
    ]
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if safe_write_text:
        safe_write_text(target, data + "\n", encoding="utf-8", atomic=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            handle.write(data + "\n")
    return target


def write_dummy_vision_yaml(base_dir: Path) -> Path:
    """
    Scrive un visionstatement.yaml fittizio ma completo per il dummy.
    Include tutte le sezioni canoniche con testo non vuoto compatibile col validator.
    Path SSoT: <base_dir>/config/visionstatement.yaml (schema v1 con full_text).
    """
    cfg_dir = ensure_within_and_resolve(base_dir, base_dir / "config")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    target = cfg_dir / "visionstatement.yaml"

    content_lines = [
        "Vision",
        "Visione fittizia per il workspace dummy; usata solo per i test di validazione.",
        "",
        "Mission",
        "Missione fittizia che descrive come il dummy realizza la vision.",
        "",
        "Framework Etico",
        "Principi etici fittizi: trasparenza, supervisione umana, gestione sicura dei dati.",
        "",
        "Goal",
        "Obiettivi fittizi a breve/medio periodo per il dummy (es. completare setup KB).",
        "",
        "Contesto Operativo",
        "Contesto operativo fittizio: settore dimostrativo, utenza interna, lingua italiana.",
    ]

    payload = {
        "version": 1,
        "metadata": {
            "source_pdf": "config/VisionStatement.pdf",
            "generated_for": "dummy",
        },
        "content": {
            "full_text": "\n".join(content_lines),
        },
    }

    if yaml is not None and safe_write_text:
        safe_write_text(
            target,
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),  # type: ignore[arg-type]
            encoding="utf-8",
            atomic=True,
        )
    elif safe_write_text:
        safe_write_text(target, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", atomic=True)
    else:  # pragma: no cover - fallback emergenza
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))

    return target


def ensure_local_readmes(base_dir: Path, categories: Optional[dict[str, dict[str, Any]]] = None) -> list[str]:
    raw_dir = base_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    catalogue = categories or {}
    candidate_dirs: set[Path] = {p for p in raw_dir.iterdir() if p.is_dir()}
    for key in catalogue.keys():
        candidate_dirs.add(raw_dir / to_kebab(key))

    for subdir in sorted(candidate_dirs):
        subdir.mkdir(parents=True, exist_ok=True)
        cat_key = to_kebab(subdir.name)
        meta = catalogue.get(cat_key) or catalogue.get(subdir.name) or {}
        title = str(meta.get("ambito") or subdir.name.replace("-", " ").title())
        descr = str(meta.get("descrizione") or "")
        raw_keywords = meta.get("keywords")
        if isinstance(raw_keywords, list):
            keywords = [str(x).strip() for x in raw_keywords if str(x).strip()]
        else:
            keywords = []
        data, mime = _render_local_readme_bytes(title, descr, keywords)
        filename = "README.pdf" if mime == "application/pdf" else "README.txt"
        target = subdir / filename
        if mime == "application/pdf" and safe_write_bytes:
            safe_write_bytes(target, data, atomic=True)
        elif safe_write_text:
            safe_write_text(target, data.decode("utf-8"), encoding="utf-8", atomic=True)
        written.append(str(target))
    return written


def load_mapping_categories(base_dir: Path) -> dict[str, dict[str, Any]]:
    mapping_path = base_dir / "semantic" / "semantic_mapping.yaml"
    if not mapping_path.exists():
        return {}
    if yaml is None:
        return {}
    try:
        text = read_text_safe(base_dir, mapping_path, encoding="utf-8")  # type: ignore[arg-type]
        data = yaml.safe_load(text) or {}
    except Exception:
        return {}

    categories: dict[str, dict[str, Any]] = {}

    areas = data.get("areas")
    if isinstance(areas, list):
        for area in areas:
            if not isinstance(area, dict):
                continue
            key = to_kebab(str(area.get("key") or area.get("ambito") or area.get("title") or ""))
            if not key:
                continue
            keywords: list[str] = []
            for field in ("documents", "artefatti", "chunking_hints"):
                raw = area.get(field)
                if isinstance(raw, list):
                    keywords.extend(str(x).strip() for x in raw if str(x).strip())
            descr = str(
                area.get("descrizione_breve") or area.get("descrizione") or area.get("ambito") or key.replace("-", " ")
            )
            categories[key] = {
                "ambito": str(area.get("ambito") or key.replace("-", " ").title()),
                "descrizione": descr,
                "keywords": keywords,
            }
    if categories:
        return categories

    for key, section in data.items():
        if key in {"context", "synonyms", "system_folders"}:
            continue
        if not isinstance(section, dict):
            continue
        cat_key = to_kebab(str(key))
        if not cat_key:
            continue
        keywords = section.get("keywords") if isinstance(section.get("keywords"), list) else []
        categories[cat_key] = {
            "ambito": str(section.get("ambito") or cat_key.replace("-", " ").title()),
            "descrizione": str(section.get("descrizione") or section.get("descrizione_breve") or ""),
            "keywords": [str(x).strip() for x in keywords if str(x).strip()],
        }
    return categories


__all__ = [
    "write_basic_semantic_yaml",
    "ensure_minimal_tags_db",
    "ensure_raw_pdfs",
    "ensure_local_readmes",
    "load_mapping_categories",
    "ensure_book_skeleton",
    "write_minimal_tags_raw",
    "write_dummy_vision_yaml",
    "_MINIMAL_RAW_PDF",
]


def ensure_book_skeleton(base_dir: Path) -> None:
    """Garantisce la presenza di book/README.md e book/SUMMARY.md con contenuti minimi."""
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "alpha.md": "# Alpha\n",
        "beta.md": "# Beta\n",
        "README.md": "# Dummy KB\n",
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
    }
    for name, content in defaults.items():
        target = book_dir / name
        if not target.exists() and safe_write_text:
            safe_write_text(target, content, encoding="utf-8", atomic=True)
