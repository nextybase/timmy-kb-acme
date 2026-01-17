# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [REPO_ROOT / "src", REPO_ROOT / "docs", REPO_ROOT / ".codex"]
SCAN_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml"}


class _Pattern:
    def __init__(self, name: str, regex: str, message: str) -> None:
        self.name = name
        self.regex = re.compile(regex)
        self.message = message


BANNED_PATTERNS = [
    _Pattern(
        "yaml_structure_env",
        r"YAML_STRUCTURE_FILE",
        "YAML_STRUCTURE_FILE is forbidden (hardline policy).",
    ),
    _Pattern(
        "legacy_cartelle_raw_path",
        r"(src[/\\\\]config[/\\\\]cartelle_raw\.yaml|config[/\\\\]cartelle_raw\.yaml)",
        "cartelle_raw.yaml must live under system/assets/templates/ only.",
    ),
    _Pattern(
        "legacy_cartelle_raw_join",
        r"src\s*/\s*\"config\"\s*/\s*\"cartelle_raw\.yaml\"",
        "cartelle_raw.yaml must not be resolved via src/config shims.",
    ),
    _Pattern(
        "repo_root_semantic_mapping_candidate",
        r"(repo_root_dir|repo_root)[^\n]*(semantic[/\\\\]semantic_mapping\.yaml|\"semantic\"\s*/\s*\"semantic_mapping\.yaml\")",
        "Repo-root semantic_mapping.yaml candidate is forbidden.",
    ),
]

MAPPING_LOADER = REPO_ROOT / "src" / "semantic" / "mapping_loader.py"
MAPPING_LOADER_PATTERNS = [
    _Pattern(
        "repo_candidate_label",
        r"\byield\s+\"repo\"",
        "iter_mapping_candidates must not yield repo candidates.",
    ),
    _Pattern(
        "repo_root_semantic_candidate",
        r"(Path\(\s*repo_root_dir\s*\)\s*/\s*\"semantic\"|repo_root_dir\s*/\s*\"semantic\")",
        "Repo-root semantic_mapping.yaml candidate is forbidden.",
    ),
]


def _iter_files(base: Path) -> Iterable[Path]:
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        yield path


def _scan_file(path: Path, patterns: List[_Pattern]) -> List[Tuple[Path, int, str, str]]:
    violations: List[Tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            if pattern.regex.search(line):
                violations.append((path, line_no, pattern.name, pattern.message))
    return violations


def main() -> int:
    log = logging.getLogger("tools.smoke.template_hardline")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    violations: List[Tuple[Path, int, str, str]] = []

    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in _iter_files(base):
            violations.extend(_scan_file(path, BANNED_PATTERNS))

    if MAPPING_LOADER.exists():
        violations.extend(_scan_file(MAPPING_LOADER, MAPPING_LOADER_PATTERNS))

    if violations:
        for path, line_no, name, message in violations:
            log.error(
                "template_hardline_violation path=%s line=%s rule=%s msg=%s",
                path.as_posix(),
                line_no,
                name,
                message,
            )
        return 1

    log.info("template_hardline_check_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
