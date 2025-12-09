# SPDX-License-Identifier: GPL-3.0-or-later
"""
Diagnostica sezioni Vision per il workspace dummy.

Carica visionstatement.yaml del dummy, esegue analyze_vision_sections e stampa uno stato sintetico.
"""
from __future__ import annotations

from ai.check import debug_dummy_vision_sections


def main() -> None:
    report = debug_dummy_vision_sections(slug="dummy")
    print("YAML path:", report.get("yaml_path"))
    print("=== TEXT PREVIEW ===")
    print(report.get("text_preview", ""))
    print("=== SECTIONS ===")
    for section in report.get("sections", []):
        print(f"- {section['name']}: {section['status']}")
        preview = section.get("text_preview") or ""
        if preview:
            print("  ", preview.replace("\n", " ")[:120])
            print()


if __name__ == "__main__":
    main()
