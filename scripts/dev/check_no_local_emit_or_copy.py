#!/usr/bin/env python3
"""
Fail-fast su helper duplicati per ingest/CSV:
- Vietate definizioni locali di `_copy_local_pdfs_to_raw` fuori da `src/semantic/`.
- Vietati import/usi diretti di `semantic.tags_extractor` fuori da `src/semantic/`.

Scopo: forzare l'uso di `semantic.api` come SSoT.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def main() -> int:
    bad: list[tuple[Path, str]] = []
    for py in SRC.rglob("*.py"):
        # Consenti tutto dentro semantic/
        try:
            rel = py.relative_to(SRC)
        except Exception:
            continue
        parts = rel.as_posix().split("/")
        if parts and parts[0] == "semantic":
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "def _copy_local_pdfs_to_raw" in text:
            bad.append((py, "definizione helper duplicato"))
        if "semantic.tags_extractor" in text or "from semantic.tags_extractor import" in text:
            bad.append((py, "uso diretto semantic.tags_extractor"))

    if bad:
        print("[check_no_local_emit_or_copy] Violazioni trovate:")
        for path, msg in bad:
            print(f" - {path}: {msg}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
