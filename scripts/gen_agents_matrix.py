#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "docs" / "AGENTS_INDEX.md"
MARK_BEGIN = "<!-- MATRIX:BEGIN -->"
MARK_END = "<!-- MATRIX:END -->"

CANDIDATES = [
    ("Root", REPO / "AGENTS.md"),
    ("Pipeline Core", REPO / "src" / "pipeline" / "AGENTS.md"),
    ("Semantica", REPO / "src" / "semantic" / "AGENTS.md"),
    ("UI (Streamlit)", REPO / "src" / "ui" / "AGENTS.md"),
    ("UI (Streamlit)", REPO / "src" / "ui" / "pages" / "AGENTS.md"),
    ("Test", REPO / "tests" / "AGENTS.md"),
    ("Documentazione", REPO / "docs" / "AGENTS.md"),
    ("Codex (repo)", REPO / ".codex" / "AGENTS.md"),
]

HEADERS = [
    "Area",
    "File",
    "Override chiave (sintesi)",
    "Criteri di accettazione (key)",
    "Note",
]


def extract_summary(md: str) -> Tuple[str, str]:
    """
    Estrae due righe sintetiche:
    - Override: cerca sezioni 'Override'/'Regole' e prende 1-2 bullet.
    - Accettazione: cerca 'Accettazione'/'Acceptance' e prende 1 bullet.
    Fallback: '—'
    """

    def bullets_after(heading_regex: str, take: int = 2) -> List[str]:
        match = re.search(heading_regex, md, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            return []
        start = match.end()
        lines = md[start:].splitlines()
        out: List[str] = []
        for line in lines:
            if re.match(r"^\s*#+\s", line):
                break
            if re.match(r"^\s*[-*]\s+", line):
                out.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
            if len(out) >= take:
                break
        return out

    override = bullets_after(r"^\s*##\s*(Override|Regole)\b", take=2)
    accept = bullets_after(r"^\s*##\s*(Accettazione|Acceptance)\b", take=1)

    override_txt = "; ".join(override) if override else "—"
    accept_txt = "; ".join(accept) if accept else "—"
    return override_txt, accept_txt


def make_row(area: str, path: Path) -> List[str]:
    note = ""
    if not path.exists():
        return [area, f"`{path.relative_to(REPO)}`", "—", "—", "**MANCANTE**"]

    md = path.read_text(encoding="utf-8", errors="ignore")
    override, accept = extract_summary(md)
    rel_path = path.relative_to(REPO).as_posix()
    rel = f"`{rel_path}`"
    if "streamlit" in area.lower():
        note = "UX guidata da stato"
    return [area, rel, override, accept, note or ""]


def render_table(rows: List[List[str]]) -> str:
    header = "| " + " | ".join(HEADERS) + " |"
    sep = "|" + "|".join(["-" * (len(h) + 2) for h in HEADERS]) + "|"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    preface = (
        "> **Matrice di override (panoramica rapida)**\n"
        "> Gli `AGENTS.md` locali definiscono solo le deroghe/override; le policy comuni restano in questo indice.\n\n"
    )
    return preface + "\n".join([header, sep, *body]) + "\n"


def replace_block(text: str, payload: str) -> str:
    if MARK_BEGIN not in text or MARK_END not in text:
        raise SystemExit("Marker MATRIX non trovati in docs/AGENTS_INDEX.md")
    pattern = rf"{re.escape(MARK_BEGIN)}.*?{re.escape(MARK_END)}"
    return re.sub(pattern, lambda _m: f"{MARK_BEGIN}\n{payload}\n{MARK_END}", text, flags=re.DOTALL)


def main(check: bool = False) -> None:
    rows = [make_row(area, path) for area, path in CANDIDATES]
    table = render_table(rows)
    content = INDEX.read_text(encoding="utf-8")
    updated = replace_block(content, table)
    if check:
        if updated == content:
            return
        print("MATRIX: aggiornamento necessario (rigenera la tabella).")
        raise SystemExit(1)
    INDEX.write_text(updated, encoding="utf-8")
    print("MATRIX: rigenerata in docs/AGENTS_INDEX.md")


if __name__ == "__main__":
    import sys

    main(check="--check" in sys.argv)
