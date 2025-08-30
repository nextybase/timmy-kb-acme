# src/config_ui/vision_parser.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from .utils import ensure_within_and_resolve, safe_write_text_compat, yaml_dump

_OVM_KEYS = ("organization", "vision", "mission")
_hr_re = re.compile(r"^[\-=_]{3,}\s*$")


def _is_plausible_heading(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if _hr_re.match(s):
        return True
    low = s.lower()
    if low in {
        "executive summary",
        "valori",
        "pilastri strategici",
        "offerta",
        "mercati prioritari",
        "operating model",
        "roadmap ad alto livello",
        "metriche chiave",
        "rischi & mitigazioni",
        "appendice",
        "appendix",
        "organization",
        "vision",
        "mission",
    }:
        return True
    if len(s) > 80 or s.endswith((".", ":", ";")):
        return False
    words = re.findall(r"[A-Za-z0-9&'\-]+", s)
    if not words or len(words) > 8:
        return False
    cap = sum(
        1 for w in words if w.isupper() or (w[0].isupper() and (len(w) == 1 or w[1:].islower()))
    )
    return (cap / len(words)) >= 0.6


def _clean_section_body(text: str) -> str:
    lines = [(line or "").strip() for line in (text or "").splitlines()]
    cleaned: List[str] = []
    for line in lines:
        if not line:
            cleaned.append("")
            continue
        if re.fullmatch(r"\d{1,3}", line):  # numeri pagina
            continue
        if re.fullmatch(r"[•·\-–—%]", line):  # bullet isolati
            continue
        if _hr_re.match(line):
            continue
        cleaned.append(line)
    # collassa blank consecutive
    out: List[str] = []
    blank = 0
    for line in cleaned:
        if line == "":
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip()


def extract_ovm_sections(text: str) -> Dict[str, str]:
    """
    Estrae SOLO Organization / Vision / Mission:
    - heading su riga singola (case-insensitive), opzionale ":"
    - termina alla riga successiva che appare come heading plausibile
    """
    sections: Dict[str, str] = {k: "" for k in _OVM_KEYS}
    if not text:
        return sections

    s = re.sub(r"\r\n?", "\n", text)
    lines = s.split("\n")

    # heading O/V/M
    ovm_positions: List[Tuple[int, str]] = []
    for idx, line in enumerate(lines):
        m = re.match(r"^\s*(Organization|Vision|Mission)\s*:?\s*$", line, flags=re.IGNORECASE)
        if m:
            ovm_positions.append((idx, m.group(1).lower().strip()))

    if not ovm_positions:
        return sections

    for _idx, (start_idx, key) in enumerate(ovm_positions):
        end_idx = len(lines)
        for j in range(start_idx + 1, len(lines)):
            if _is_plausible_heading(lines[j]) and j > start_idx + 1:
                end_idx = j
                break
        body = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        sections[key] = _clean_section_body(body)

    return sections


def write_vision_yaml(slug: str, ovm: Dict[str, str], *, base_root: Path | str = "output") -> Path:
    """
    Scrive output/timmy-kb-<slug>/semantic/vision.yaml in modo atomico (solo O/V/M).
    """
    base_root = Path(base_root)
    client_root = ensure_within_and_resolve(base_root, base_root / f"timmy-kb-{slug}")
    sem_dir = ensure_within_and_resolve(client_root, client_root / "semantic")
    path = ensure_within_and_resolve(sem_dir, sem_dir / "vision.yaml")

    payload = {
        "organization": (ovm.get("organization") or "").strip(),
        "vision": (ovm.get("vision") or "").strip(),
        "mission": (ovm.get("mission") or "").strip(),
    }
    safe_write_text_compat(path, yaml_dump(payload))
    return path
