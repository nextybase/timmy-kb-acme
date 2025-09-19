from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, cast

from pipeline.file_utils import safe_write_text

if TYPE_CHECKING:

    from pipeline.path_utils import ensure_within

yaml_module: Any | None = None
try:
    import yaml as _yaml

    yaml_module = _yaml
except Exception:  # pragma: no cover
    yaml_module = None


def _read_pdf_text(pdf_path: Path) -> str:
    try:  # lazy import to avoid hard dependency at import time
        import importlib

        module = importlib.import_module("PyPDF2")
        PdfReader = module.PdfReader
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyPDF2 non disponibile: impossibile estrarre testo dal PDF.") from e

    try:
        reader = PdfReader(str(pdf_path))
        texts: List[str] = []
        for page in getattr(reader, "pages", []) or []:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t:
                texts.append(t)
        return "\n\n".join(texts).strip()
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Estrazione testo fallita: {e}") from e


def _normalize_text(s: str) -> str:
    # Normalizza newline e spazi multipli
    s = re.sub(r"\r\n?", "\n", s or "")
    # Unifica spazi tra parole
    s = re.sub(r"[ \t\x0b\x0c\u00A0]+", " ", s)
    return s.strip()


def _split_sections(text: str) -> Dict[str, str]:
    """Placeholder: splitta per heading noti (case-insensitive)."""
    if not text:
        return {}
    # Titoli noti (regex) -> chiave canonical del modello
    patterns: List[Tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bvision\b", re.IGNORECASE), "vision"),
        (re.compile(r"\bmission\b", re.IGNORECASE), "mission"),
        (re.compile(r"framework[-\s]?etico", re.IGNORECASE), "ethical_framework"),
        (re.compile(r"goal\s*generali", re.IGNORECASE), "goals_general"),
        (re.compile(r"basket[_\s]?3\b", re.IGNORECASE), "goals_b3"),
        (re.compile(r"basket[_\s]?6\b", re.IGNORECASE), "goals_b6"),
        (re.compile(r"basket[_\s]?12\b", re.IGNORECASE), "goals_b12"),
        (re.compile(r"\buvp\b|unique value proposition", re.IGNORECASE), "uvp"),
        (re.compile(r"scenario\s*stakeholder.*impatto", re.IGNORECASE), "stakeholders_impact"),
        (re.compile(r"metriche\s*chiave", re.IGNORECASE), "key_metrics"),
        (
            re.compile(r"rischi\s*principali|rischi\s*&\s*mitigazioni", re.IGNORECASE),
            "risks_mitigations",
        ),
        (re.compile(r"modello\s*operativo|operating\s*model", re.IGNORECASE), "operating_model"),
        (
            re.compile(r"architettura.*alto\s*livello|architecture.*principles", re.IGNORECASE),
            "architecture_principles",
        ),
        (
            re.compile(r"strumenti.*governance.*etica|ethics.*governance", re.IGNORECASE),
            "ethics_governance_tools",
        ),
        (re.compile(r"roadmap.*basket", re.IGNORECASE), "roadmap_baskets"),
    ]

    # Trova posizioni heading
    hit_positions: List[Tuple[int, str]] = []
    for m, key in patterns:
        for hit in m.finditer(text):
            hit_positions.append((hit.start(), key))
    if not hit_positions:
        return {}
    hit_positions.sort(key=lambda x: x[0])

    sections: Dict[str, str] = {}
    for i, (start, key) in enumerate(hit_positions):
        end = hit_positions[i + 1][0] if i + 1 < len(hit_positions) else len(text)
        body = text[start:end]
        # Rimuovi heading dalla sezione (prima riga fino a newline)
        body = re.sub(r"^.*?(\n|$)", "", body, count=1, flags=re.DOTALL)
        sections[key] = body.strip()
    return sections


def _to_list(body: str) -> List[str]:
    # Placeholder: split per righe non vuote, normalizzate
    lines = []
    for ln in (body or "").splitlines():
        s = ln.strip().lstrip("-•*")
        s = re.sub(r"\s+", " ", s)
        if s:
            lines.append(s)
    return lines


def pdf_to_vision_yaml(pdf_path: Path, out_yaml_path: Path) -> Path:
    """Estrae testo dal PDF e genera `out_yaml_path` con schema YAML stabile.

    Schema:
      meta.title, vision, mission,
      ethical_framework[], goals.general[], goals.baskets.{b3,b6,b12}[],
      uvp[], stakeholders_impact[], key_metrics[], risks_mitigations[],
      operating_model[], architecture_principles[], ethics_governance_tools[], roadmap_baskets[]
    """
    pdf_path = Path(pdf_path)
    out_yaml_path = Path(out_yaml_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")

    text = _read_pdf_text(pdf_path)
    text = _normalize_text(text)
    if not text:
        raise RuntimeError("Estrazione PDF vuota: impossibile generare vision_statement.yaml")

    sections = _split_sections(text)

    # Costruisci payload strutturato
    payload: Dict[str, object] = {
        "meta": {"title": pdf_path.stem},
        "vision": sections.get("vision", ""),
        "mission": sections.get("mission", ""),
        "ethical_framework": _to_list(sections.get("ethical_framework", "")),
        "goals": {
            "general": _to_list(sections.get("goals_general", "")),
            "baskets": {
                "b3": _to_list(sections.get("goals_b3", "")),
                "b6": _to_list(sections.get("goals_b6", "")),
                "b12": _to_list(sections.get("goals_b12", "")),
            },
        },
        "uvp": _to_list(sections.get("uvp", "")),
        "stakeholders_impact": _to_list(sections.get("stakeholders_impact", "")),
        "key_metrics": _to_list(sections.get("key_metrics", "")),
        "risks_mitigations": _to_list(sections.get("risks_mitigations", "")),
        "operating_model": _to_list(sections.get("operating_model", "")),
        "architecture_principles": _to_list(sections.get("architecture_principles", "")),
        "ethics_governance_tools": _to_list(sections.get("ethics_governance_tools", "")),
        "roadmap_baskets": _to_list(sections.get("roadmap_baskets", "")),
    }

    # Serializza YAML in modo sicuro/atomico
    # Evita scritture fuori perimetro
    base_dir = out_yaml_path.parent.parent if out_yaml_path.name else out_yaml_path.parent
    ensure_within(base_dir, out_yaml_path)

    if yaml_module is None:
        raise RuntimeError("Libreria YAML non disponibile")

    yaml_api = cast(Any, yaml_module)
    content = yaml_api.safe_dump(payload, allow_unicode=True, sort_keys=False)
    safe_write_text(out_yaml_path, content, encoding="utf-8", atomic=True)
    return out_yaml_path
