# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple, cast

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within
from semantic.document_ingest import read_document

try:
    import yaml as _yaml
except Exception:  # pragma: no cover
    yaml_module: Any | None = None
else:
    yaml_module = _yaml


vision_run_params = SimpleNamespace(run_for_vision=SimpleNamespace(use_kb=False))
# Forziamo la prima fase Vision a NON usare la KB per evitare contaminazioni semantiche


def _read_pdf_text(pdf_path: Path) -> str:
    try:
        doc = read_document(pdf_path)
        return doc.full_text
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Impossibile leggere il PDF: {exc}") from exc


def _clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    replacements = {
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "\u2022": "-",
        "\u2011": "-",
        "🔹": "-",
        "\ufffd": "'",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    return normalized


def _normalize_text(raw: str) -> str:
    text = re.sub(r"\r\n?", "\n", raw or "")
    text = text.replace("\u00A0", " ")
    text = re.sub(r"\n[ \t]+\n", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return _clean_text(text.strip())


def _split_sections(text: str) -> Dict[str, str]:
    if not text:
        return {}

    patterns: List[Tuple[re.Pattern[str], str]] = [
        (re.compile(r"^\s*vision\b", re.IGNORECASE | re.MULTILINE), "vision"),
        (re.compile(r"^\s*mission\b", re.IGNORECASE | re.MULTILINE), "mission"),
        (re.compile(r"^\s*framework[\s-]+etico", re.IGNORECASE | re.MULTILINE), "framework_etico"),
        (re.compile(r"^\s*goal\b", re.IGNORECASE | re.MULTILINE), "goal"),
        (re.compile(r"^\s*descrizione\s+prodotto", re.IGNORECASE | re.MULTILINE), "prodotto_azienda"),
        (re.compile(r"^\s*descrizione\s+mercato", re.IGNORECASE | re.MULTILINE), "mercato"),
    ]

    positions: List[Tuple[int, str]] = []
    for matcher, key in patterns:
        match = matcher.search(text)
        if match:
            positions.append((match.start(), key))

    if not positions:
        return {}

    positions.sort(key=lambda item: item[0])
    sections: Dict[str, str] = {}

    for idx, (start, key) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        body = text[start:end]
        body = re.sub(r"^.*?(\n|$)", "", body, count=1, flags=re.DOTALL)
        sections[key] = body.strip()

    return sections


def _normalize_block(body: str) -> str:
    if not body:
        return ""

    text = body.replace("\u00A0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    paragraphs: List[str] = []
    for chunk in re.split(r"\n\s*\n", text):
        piece = re.sub(r"\s+", " ", chunk).strip()
        if piece:
            paragraphs.append(_clean_text(piece))
    if not paragraphs:
        return ""
    counts = [len(p.split()) for p in paragraphs if p]
    if counts and (sum(counts) / len(counts)) <= 3:
        return " ".join(paragraphs)
    return "\n\n".join(paragraphs)


def _format_bullets(text: str) -> str:
    rewritten = re.sub(r"\s*-\s+", "\n- ", text).strip()
    if not rewritten:
        return ""

    prefix_parts: List[str] = []
    bullets: List[str] = []
    current: List[str] = []

    for raw_line in rewritten.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            content = line[2:].strip()
            if content.lower().startswith("goal") or not bullets:
                if current:
                    bullets.append(" ".join(current).strip())
                    current = []
                if prefix_parts and not bullets:
                    # finalize prefix before first bullet
                    bullets.append(" ".join(prefix_parts).strip())
                    prefix_parts = []
                bullets.append(f"- {content}")
            else:
                if bullets:
                    bullets[-1] = f"{bullets[-1]} {content}"
                else:
                    prefix_parts.append(content)
        else:
            if bullets:
                bullets[-1] = f"{bullets[-1]} {line}"
            else:
                prefix_parts.append(line)

    if current:
        bullets.append(" ".join(current).strip())

    header = " ".join(prefix_parts).strip()
    body = "\n".join(bullets).strip()
    return "\n".join(part for part in (header, body) if part)


def _strip_heading(text: str, *labels: str) -> str:
    lowered = text.lower()
    for label in labels:
        target = label.lower()
        if lowered.startswith(target):
            return text[len(label) :].lstrip(" :-")
    return text


def _split_goal_baskets(goal_text: str) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {"b3": [], "b6": [], "b12": []}
    if not goal_text:
        return buckets

    formatted = _format_bullets(goal_text)
    pattern = re.compile(
        r"^-+\s*Goal\s*(\d+)\s*[-–]?\s*(.*?)(?=\n-+\s*Goal\s*\d+|\Z)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    for match in pattern.finditer(formatted):
        number = int(match.group(1))
        body = _clean_text(" ".join(match.group(2).split()))
        if not body:
            continue
        if number <= 1:
            buckets["b3"].append(body)
        elif number == 2:
            buckets["b6"].append(body)
        else:
            buckets["b12"].append(body)

    if all(not values for values in buckets.values()):
        fallback = _to_list(formatted)
        for idx, body in enumerate(fallback):
            if idx == 0:
                buckets["b3"].append(body)
            elif idx == 1:
                buckets["b6"].append(body)
            else:
                buckets["b12"].append(body)

    return buckets


def _to_list(body: str) -> List[str]:
    if not body:
        return []

    text = body.replace("\u00A0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n[ \t]*(\n[ \t]*)+", "\n\n", text)

    items: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                items.append(" ".join(current))
                current = []
            continue

        bullet = re.match(r"^[-*•\u2022]+\s*", stripped)
        if bullet:
            remainder = stripped[bullet.end() :].strip()
            parts = remainder.split()
            is_subword = len(parts) <= 2 and not remainder.endswith((".", "!", "?", ";", ":"))
            if current and not is_subword:
                items.append(" ".join(current))
                current = []
            stripped = remainder

        if stripped:
            current.append(stripped)

    if current:
        items.append(" ".join(current))

    cleaned = [_clean_text(re.sub(r"\s+", " ", item).strip()) for item in items if item.strip()]
    if cleaned:
        avg_len = sum(len(entry.split()) for entry in cleaned) / len(cleaned)
        if avg_len <= 2:
            return [_normalize_block(" ".join(cleaned))]
    return cleaned


def pdf_to_vision_yaml(pdf_path: Path, out_yaml_path: Path) -> Path:
    pdf_path = Path(pdf_path)
    out_yaml_path = Path(out_yaml_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF non trovato: {pdf_path}")

    text = _read_pdf_text(pdf_path)
    text = _normalize_text(text)
    if not text:
        raise RuntimeError("Estrazione PDF vuota: impossibile generare vision_statement.yaml")

    sections = _split_sections(text)

    vision = _normalize_block(sections.get("vision", ""))
    mission = _strip_heading(_normalize_block(sections.get("mission", "")), "mission")
    framework = _strip_heading(
        _normalize_block(sections.get("framework_etico", "")),
        "framework etico",
    )
    goal = _strip_heading(_normalize_block(sections.get("goal", "")), "goal")
    prodotto = _strip_heading(
        _normalize_block(sections.get("prodotto_azienda", "")),
        "descrizione prodotto/azienda",
        "prodotto/azienda",
        "descrizione prodotto",
    )
    mercato = _strip_heading(
        _normalize_block(sections.get("mercato", "")),
        "descrizione mercato",
        "mercato",
    )

    goal_buckets = _split_goal_baskets(goal)

    payload: Dict[str, object] = {
        "meta": {"title": pdf_path.stem},
        "sections": {
            "vision": vision,
            "mission": mission,
            "framework_etico": _format_bullets(framework),
            "goal": _format_bullets(goal),
            "prodotto_azienda": _format_bullets(prodotto),
            "mercato": _format_bullets(mercato),
        },
        "goals": {
            "b3": goal_buckets["b3"],
            "b6": goal_buckets["b6"],
            "b12": goal_buckets["b12"],
        },
    }

    base_dir = out_yaml_path.parent.parent if out_yaml_path.name else out_yaml_path.parent
    ensure_within(base_dir, out_yaml_path)

    if yaml_module is None:
        raise RuntimeError("Libreria YAML non disponibile")

    yaml_api = cast(Any, yaml_module)
    content = yaml_api.safe_dump(payload, allow_unicode=True, sort_keys=False)
    safe_write_text(out_yaml_path, content, encoding="utf-8", atomic=True)
    return out_yaml_path
