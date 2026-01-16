# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".rst",
}

CHECK_CODEPOINTS_EXTS = {".py", ".md"}

FORBIDDEN_CODEPOINTS = {
    "\u2018": "U+2018",
    "\u2019": "U+2019",
    "\u201c": "U+201C",
    "\u201d": "U+201D",
    "\u2013": "U+2013",
    "\u2014": "U+2014",
    "\u2011": "U+2011",
    "\u00a0": "U+00A0",
    "\ufffd": "U+FFFD",
}

MOJIBAKE_TOKENS = {
    "\u00e2\u20ac": "MOJIBAKE_TOKEN_E2_20AC",
    "\u00e2\u20ac\u2014": "MOJIBAKE_PREFIX_E2_20AC_2014",
    "\u00e2\u20ac\u2013": "MOJIBAKE_PREFIX_E2_20AC_2013",
}


def _iter_tracked_text_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    )
    paths: list[Path] = []
    for entry in output.splitlines():
        entry = entry.strip()
        if not entry:
            continue
        path = REPO_ROOT / entry
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda item: item.as_posix())


def _scan_mojibake_prefix_c3(line: str) -> bool:
    idx = 0
    while True:
        idx = line.find("\u00c3", idx)
        if idx == -1:
            return False
        next_pos = idx + 1
        if next_pos < len(line) and line[next_pos].isalpha():
            return True
        idx = next_pos


def test_repo_encoding_guardrail() -> None:
    findings: list[tuple[str, int, str]] = []
    decode_errors: list[str] = []

    for path in _iter_tracked_text_files():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            decode_errors.append(rel_path)
            continue

        if path.suffix.lower() not in CHECK_CODEPOINTS_EXTS:
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            for ch, label in FORBIDDEN_CODEPOINTS.items():
                if ch in line:
                    findings.append((rel_path, line_no, label))
            for token, label in MOJIBAKE_TOKENS.items():
                if token in line:
                    findings.append((rel_path, line_no, label))
            if _scan_mojibake_prefix_c3(line):
                findings.append((rel_path, line_no, "MOJIBAKE_PREFIX_C3_ALPHA"))

    for rel_path in decode_errors:
        findings.append((rel_path, 1, "UTF8_DECODE_ERROR"))

    if findings:
        lines = [
            f"{path}:{line_no} {label}"
            for path, line_no, label in sorted(findings)
        ]
        report = ["Encoding guardrail violations:"] + lines
        raise AssertionError("\n".join(report))
