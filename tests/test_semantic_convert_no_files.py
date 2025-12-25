# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

import semantic.api as sapi
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger


@dataclass
class _Ctx:
    base_dir: Path
    repo_root_dir: Path
    raw_dir: Path
    md_dir: Path
    slug: str


def _write_minimal_layout(base: Path) -> None:
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (base / "book" / "README.md").write_text("# KB\n", encoding="utf-8")
    (base / "book" / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")


def test_convert_no_files_logs_event_and_raises(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    base = tmp_path / "output" / "timmy-kb-dummy"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    _write_minimal_layout(base)

    ctx = _Ctx(base_dir=base, repo_root_dir=base, raw_dir=raw, md_dir=book, slug="dummy")
    logger = get_structured_logger("tests.convert.no_files", context=ctx)

    caplog.set_level(logging.INFO, logger="tests.convert.no_files")

    with pytest.raises(ConfigError):
        sapi.convert_markdown(ctx, logger, slug="dummy")

    # Deve comparire l’evento esplicito prima del fail-fast
    assert any(
        (getattr(rec, "event", rec.getMessage()) == "semantic.convert.no_files") for rec in caplog.records
    ), "Evento semantic.convert.no_files non trovato nei log"
