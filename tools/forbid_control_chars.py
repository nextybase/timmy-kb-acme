# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import argparse
import sys
import unicodedata
from importlib import import_module
from pathlib import Path
from typing import List, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

# Import dinamici post-bootstrapping per rispettare E402 (niente import dopo codice)
_file_utils = import_module("pipeline.file_utils")
_logging_utils = import_module("pipeline.logging_utils")
_path_utils = import_module("pipeline.path_utils")

safe_write_text = _file_utils.safe_write_text
get_structured_logger = _logging_utils.get_structured_logger
ensure_within_and_resolve = _path_utils.ensure_within_and_resolve

ALLOWED_CONTROLS = {0x09, 0x0A, 0x0D}  # tab, newline, carriage return
CONTROL_RANGES = (
    range(0x00, 0x20),  # C0 controls
    range(0x7F, 0x80),  # DEL
    range(0x80, 0xA0),  # C1 controls
)

logger = get_structured_logger("tools.forbid_control_chars")


def _is_forbidden_control(ch: str) -> bool:
    code = ord(ch)
    if code in ALLOWED_CONTROLS:
        return False
    return any(code in ctrl_range for ctrl_range in CONTROL_RANGES)


def _find_violations(text: str) -> List[dict[str, str | int]]:
    violations: List[dict[str, str | int]] = []
    line = 1
    col = 1
    for ch in text:
        if _is_forbidden_control(ch):
            violations.append(
                {
                    "line": line,
                    "column": col,
                    "code": f"U+{ord(ch):04X}",
                }
            )
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
    return violations


def _clean_text(text: str) -> str:
    filtered = "".join(ch for ch in text if not _is_forbidden_control(ch))
    return unicodedata.normalize("NFC", filtered)


def _process_path(path_str: str, *, fix: bool) -> int:
    try:
        resolved = ensure_within_and_resolve(_REPO_ROOT, Path(path_str))
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error(
            "forbid-control-chars: path traversal o risoluzione fallita",
            extra={"input_path": path_str, "error": str(exc)},
        )
        return 2

    try:
        original = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        logger.error(
            "forbid-control-chars: file non UTF-8",
            extra={"file_path": str(resolved), "error": str(exc)},
        )
        return 2

    violations = _find_violations(original)
    if not violations:
        if fix:
            cleaned = unicodedata.normalize("NFC", original)
            if cleaned != original:
                safe_write_text(resolved, cleaned, encoding="utf-8")
                logger.info(
                    "forbid-control-chars: applicata normalizzazione NFC",
                    extra={"file_path": str(resolved)},
                )
        return 0

    if fix:
        cleaned = _clean_text(original)
        safe_write_text(resolved, cleaned, encoding="utf-8")
        logger.info(
            "forbid-control-chars: rimossi caratteri di controllo",
            extra={
                "file_path": str(resolved),
                "removed": len(violations),
            },
        )
        return 0

    logger.error(
        "forbid-control-chars: caratteri di controllo individuati",
        extra={
            "file_path": str(resolved),
            "count": len(violations),
            "samples": violations[:5],
        },
    )
    return 1


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controlla la presenza di caratteri di controllo C0/C1 nei file passati",
    )
    parser.add_argument("paths", nargs="+", help="File da verificare")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rimuove i caratteri di controllo e applica NFC",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    exit_codes: List[int] = []
    for path in args.paths:
        exit_codes.append(_process_path(path, fix=args.fix))

    if not exit_codes:
        return 0

    if any(code == 2 for code in exit_codes):
        return 2
    if any(code == 1 for code in exit_codes):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    sys.exit(main())
