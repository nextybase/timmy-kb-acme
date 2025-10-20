#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src"

INCLUDE_EXT = {".py"}
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "tests",
}

GLOBAL_RULES = {
    r"\bexperimental_": "Uso di API experimental_* vietato",
    r"\buse_container_width\b": "Parametro use_container_width vietato",
    r"@st\.cache\(": "Decorator @st.cache obsoleto (usa @st.cache_data/@st.cache_resource)",
    r"\bunsafe_allow_html\s*=": "unsafe_allow_html vietato (usa st.html(...))",
    r"\bst\.(beta_|legacy_)": "API beta/legacy vietate",
}

REQUIRED_IN_ONBOARDING = {
    r"\bst\.navigation\(": "onboarding_ui deve usare st.navigation(...)",
}


def _legacy_regex(parts: tuple[str, ...], *, leading_underscore: bool = False) -> str:
    joined = "_".join(parts)
    needle = f"_{joined}" if leading_underscore else joined
    return rf"\b{needle}\b"


LEGACY_ROUTER_RULES = [
    {
        "parts": ("active", "tab"),
        "message": 'Stato legacy "active tab" non consentito in beta0',
    },
    {
        "parts": ("render", "sidebar", "tab", "switches"),
        "message": "Switcher legacy non consentito in beta0",
    },
    {
        "parts": ("init", "tab", "state"),
        "leading_underscore": True,
        "message": "Router legacy: init tab state non consentito in beta0",
    },
    {
        "parts": ("render", "tabs", "router"),
        "leading_underscore": True,
        "message": "Router legacy: render tabs router non consentito in beta0",
    },
]

FORBIDDEN_IN_ONBOARDING = {
    _legacy_regex(
        rule["parts"],
        leading_underscore=rule.get("leading_underscore", False),
    ): rule["message"]
    for rule in LEGACY_ROUTER_RULES
}


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in INCLUDE_EXT:
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def scan_global_rules() -> list[str]:
    findings: list[str] = []
    compiled = {re.compile(pattern): message for pattern, message in GLOBAL_RULES.items()}
    for file_path in iter_source_files(SOURCE_ROOT):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for regex, message in compiled.items():
            for match in regex.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"[GLOBAL] {file_path}:{line_no}: {message}: '{match.group(0)}'")
    return findings


def scan_onboarding_file() -> list[str]:
    findings: list[str] = []
    onboarding = REPO_ROOT / "onboarding_ui.py"
    if not onboarding.exists():
        findings.append("[STRUCT] onboarding_ui.py non trovato nella root")
        return findings

    content = onboarding.read_text(encoding="utf-8", errors="ignore")

    for required_pattern, message in REQUIRED_IN_ONBOARDING.items():
        if not re.search(required_pattern, content):
            findings.append(f"[ONBOARDING] onboarding_ui.py: manca requisito: {message}")

    for forbidden_pattern, message in FORBIDDEN_IN_ONBOARDING.items():
        match = re.search(forbidden_pattern, content)
        if match:
            line_no = content.count("\n", 0, match.start()) + 1
            findings.append(f"[ONBOARDING] onboarding_ui.py:{line_no}: {message}")

    return findings


def scan_legacy_structure() -> list[str]:
    legacy_dir = REPO_ROOT / "pages"
    if legacy_dir.exists():
        return ["[STRUCT] directory legacy 'pages/' presente. Rimuovere per beta0."]
    return []


def main() -> int:
    violations: list[str] = []
    violations.extend(scan_global_rules())
    violations.extend(scan_onboarding_file())
    violations.extend(scan_legacy_structure())

    if violations:
        print("Violazioni beta0 trovate:\n")
        for violation in violations:
            print("-", violation)
        return 1

    print("UI beta0 compliance: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
