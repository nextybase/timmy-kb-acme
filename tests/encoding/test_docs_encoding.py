# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

FIX_MOJIBAKE_PATH = REPO_ROOT / "tools" / "fix_mojibake.py"

spec = importlib.util.spec_from_file_location("fix_mojibake", FIX_MOJIBAKE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Impossibile caricare tools/fix_mojibake.py")

fix_mojibake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix_mojibake)
apply_replacements = fix_mojibake.apply_replacements


def _iter_target_docs() -> Iterable[Path]:
    docs_root = REPO_ROOT / "docs"
    if docs_root.is_dir():
        yield from docs_root.rglob("*.md")
    readme = REPO_ROOT / "README.md"
    if readme.is_file():
        yield readme


def _format_violation(path: Path, replacements: Sequence[tuple[str, int]]) -> str:
    details = ", ".join(f"{symbol}x{count}" for symbol, count in replacements)
    return f"{path.relative_to(REPO_ROOT)} -> {details}"


def test_docs_encoding_guard() -> None:
    violations: list[str] = []
    for doc_path in _iter_target_docs():
        text = doc_path.read_text(encoding="utf-8")
        fixed, counts = apply_replacements(text)
        if fixed == text:
            continue
        violations.append(_format_violation(doc_path, counts))

    if violations:
        hint = "Esegui `tools/fix_mojibake.py --apply` per correggere le sequenze rilevate."
        report = ["Mojibake individuato nei seguenti file:"] + violations + [hint]
        assert not violations, "\n".join(report)
