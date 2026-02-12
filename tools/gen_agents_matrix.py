#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "system" / "ops" / "agents_index.md"
MARK_BEGIN = "<!-- MATRIX:BEGIN -->"
MARK_END = "<!-- MATRIX:END -->"

CANDIDATES = [
    ("Root", REPO / "AGENTS.md"),
    ("Pipeline Core", REPO / "src" / "pipeline" / "AGENTS.md"),
    ("Semantica", REPO / "src" / "semantic" / "AGENTS.md"),
    ("UI (Streamlit)", REPO / "src" / "ui" / "AGENTS.md"),
    ("UI (Streamlit Pages)", REPO / "src" / "ui" / "pages" / "AGENTS.md"),
    ("UI Fine Tuning", REPO / "src" / "ui" / "fine_tuning" / "AGENTS.md"),
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
    "Task tipici dell'agente",
]

TASKS = {
    "Root": "Allineamento runbook `.codex/`<br>Verifica documenti obbligatori",
    "Pipeline Core": (
        "Hardening path-safety pipeline<br>"
        "Refactor I/O su utility SSoT<br>"
        "Log strutturato pipeline/run"
    ),
    "Semantica": (
        "Allineamento `semantic.api` vs service<br>"
        "Rigenerazione/migrazione `tags.db`<br>"
        "Rigenerazione README/SUMMARY idempotente"
    ),
    "UI (Streamlit)": (
        "Refactor orchestratori UI onboarding<br>"
        "Audit gating RAW/slug e router `st.navigation`<br>"
        "Messaggistica/log `ui.<pagina>` coerente"
    ),
    "UI (Streamlit Pages)": (
        "Sweep deprecazioni Streamlit 1.50<br>"
        "Router nativo `st.Page`/`st.navigation` compliance<br>"
        "Path-safety e logging per pagine"
    ),
    "UI Fine Tuning": (
        "Modal Assistant read-only + export<br>"
        "Dry-run con output grezzo<br>"
        "Proposte micro-PR per config Assistant"
    ),
    "Test": (
        "Mock Drive/Git e fixture dummy<br>"
        "Contract test su guard `book/`<br>"
        "Smoke E2E slug di esempio"
    ),
    "Documentazione": (
        "Sweep cSpell e frontmatter versione<br>"
        "Allineamento README/docs su nuove feature<br>"
        "Aggiornare guide con orchestratori correnti"
    ),
    "Codex (repo)": (
        "Esecuzione pipeline QA standard<br>"
        "Allineamento uso helper GitHub<br>"
        "Riuso tool vision/UI condivisi"
    ),
}


def extract_summary(md: str) -> Tuple[str, str]:
    """
    Estrae due righe sintetiche:
    - Override: riconosce varianti di heading e prende 1-2 bullet.
    - Accettazione: contiene i criteri/acceptance.
    Default: 'Non definito'
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

    override = bullets_after(
        r"^\s*#+\s*(Override|Regole|Rules|Rules \(overrides\)|Policy|Linee guida)\b",
        take=2,
    )
    accept = bullets_after(
        r"^\s*#+\s*(Accettazione|Acceptance|Acceptance Criteria|Criteri di accettazione|Criteri)\b",
        take=1,
    )

    default_override = "Non definito"
    default_accept = "Non definito"

    override_txt = "; ".join(override) if override else default_override
    accept_txt = "; ".join(accept) if accept else default_accept
    return override_txt, accept_txt


def make_row(area: str, path: Path) -> List[str]:
    area_key = area
    note = ""
    if "ui/pages" in path.as_posix():
        area_key = "UI (Streamlit Pages)"
    if not path.exists():
        return [
            area,
            f"`{path.relative_to(REPO)}`",
            "???'????",
            "???'????",
            "**MANCANTE**",
            TASKS.get(area_key, ""),
        ]

    md = path.read_text(encoding="utf-8", errors="ignore")
    override, accept = extract_summary(md)
    rel_path = path.relative_to(REPO).as_posix()
    rel = f"`{rel_path}`"
    if "streamlit" in area.lower():
        note = "UX guidata da stato"
    return [area, rel, override, accept, note or "", TASKS.get(area_key, "")]


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
        raise SystemExit("Marker MATRIX non trovati in system/ops/agents_index.md")
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
    print("MATRIX: rigenerata in system/ops/agents_index.md")


if __name__ == "__main__":
    import sys

    main(check="--check" in sys.argv)
