# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_path() -> str:
    git_path = shutil.which("git")
    if not git_path:
        raise RuntimeError("Impossibile trovare il binario git.")
    return git_path


_SUSPICIOUS_CHARS_PY = {
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
_SUSPICIOUS_CHARS_MD = {
    "\ufffd": "U+FFFD",
}
_SUSPICIOUS_TOKENS = {
    "\u00e2\u20ac": "TOKEN:\\u00e2\\u20ac",
}


def _resolve_base_commit() -> str:
    git_path = _git_path()
    for target in ("origin/main", "main"):
        try:
            return subprocess.check_output(
                [git_path, "merge-base", "HEAD", target],
                cwd=REPO_ROOT,
                text=True,
                encoding="utf-8",
            ).strip()
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Impossibile determinare il merge-base con main.")


def _iter_delta_targets() -> list[Path]:
    base_commit = _resolve_base_commit()
    git_path = _git_path()
    output = subprocess.check_output(
        [git_path, "diff", "--name-only", base_commit, "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    )
    paths: list[Path] = []
    for entry in output.splitlines():
        entry = entry.strip()
        if not entry.endswith((".py", ".md")):
            continue
        path = REPO_ROOT / entry
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda path: path.as_posix())


def test_repo_encoding_hygiene() -> None:
    decode_errors: list[str] = []
    suspicious: list[tuple[str, int, str]] = []

    for path in _iter_delta_targets():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            decode_errors.append(rel_path)
            continue

        suspicious_chars = _SUSPICIOUS_CHARS_PY if path.suffix == ".py" else _SUSPICIOUS_CHARS_MD
        for line_no, line in enumerate(text.splitlines(), start=1):
            for ch, label in suspicious_chars.items():
                if ch in line:
                    suspicious.append((rel_path, line_no, label))
            for token, label in _SUSPICIOUS_TOKENS.items():
                if token in line:
                    suspicious.append((rel_path, line_no, label))

    if decode_errors or suspicious:
        report: list[str] = []
        if decode_errors:
            report.append("UTF-8 decode errors:")
            report.extend(f"- {path}" for path in sorted(decode_errors))
        if suspicious:
            report.append("Suspicious Unicode tokens:")
            for path, line_no, label in sorted(suspicious):
                report.append(f"- {path}:{line_no} {label}")
        raise AssertionError("\n".join(report))
