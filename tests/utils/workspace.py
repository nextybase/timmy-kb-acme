# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility per i test: crea layout workspace strict minimi."""

from pathlib import Path


def ensure_minimal_workspace_layout(base: Path, *, client_name: str = "proj") -> None:
    """Crea i percorsi minimi richiesti da WorkspaceLayout."""
    base.mkdir(parents=True, exist_ok=True)

    for name in ("raw", "normalized", "logs", "semantic"):
        (base / name).mkdir(parents=True, exist_ok=True)

    config_dir = base / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(f"meta:\n  client_name: {client_name}\n", encoding="utf-8")

    book_dir = base / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    for doc in ("README.md", "SUMMARY.md"):
        file_path = book_dir / doc
        if not file_path.exists():
            file_path.write_text(f"# {doc.replace('.md', '')}\n", encoding="utf-8")
