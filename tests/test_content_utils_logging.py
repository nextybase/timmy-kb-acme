# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import pipeline.content_utils as cu
from pipeline.content_utils import _filter_safe_pdfs, convert_files_to_structured_markdown
from pipeline.exceptions import PathTraversalError, PipelineError


def test_filter_safe_pdfs_logs_symlink_event(tmp_path: Path, caplog, monkeypatch):
    raw = tmp_path / "kb" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    pdf = raw / "link.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    real_is_symlink = Path.is_symlink

    def _fake_is_symlink(self: Path) -> bool:  # type: ignore[override]
        return str(self) == str(pdf) or real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _fake_is_symlink)

    caplog.set_level(logging.WARNING)
    out = _filter_safe_pdfs(tmp_path, raw, [pdf], slug="dummy")
    assert out == []
    recs = [r for r in caplog.records if r.msg == "pipeline.content.skip_symlink"]
    assert recs, "evento skip_symlink mancante"
    assert getattr(recs[0], "slug", None) == "dummy"
    assert str(pdf) in getattr(recs[0], "file_path", "")


def test_filter_safe_pdfs_logs_unsafe_event_with_slug(tmp_path: Path, caplog):
    raw = tmp_path / "kb" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4\n")

    caplog.set_level(logging.WARNING)
    out = _filter_safe_pdfs(tmp_path, raw, [outside], slug="dummy")
    assert out == []
    recs = [r for r in caplog.records if r.msg == "pipeline.content.skip_unsafe"]
    assert recs, "evento skip_unsafe mancante"
    rec = recs[0]
    assert getattr(rec, "slug", None) == "dummy"
    assert str(outside) in getattr(rec, "file_path", "")
    assert getattr(rec, "reason", None) == "path_traversal"
    assert getattr(rec, "error_type", None) == "PathTraversalError"
    assert hasattr(rec, "error")


def test_filter_safe_pdfs_logs_one_event_per_blocked_pdf(tmp_path: Path, caplog):
    raw = tmp_path / "kb" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    outside_1 = tmp_path / "outside-1.pdf"
    outside_2 = tmp_path / "outside-2.pdf"
    outside_1.write_bytes(b"%PDF-1.4\n")
    outside_2.write_bytes(b"%PDF-1.4\n")

    caplog.set_level(logging.WARNING)
    out = _filter_safe_pdfs(tmp_path, raw, [outside_1, outside_2], slug="dummy")
    assert out == []

    recs = [r for r in caplog.records if r.msg == "pipeline.content.skip_unsafe"]
    assert len(recs) == 2
    assert {getattr(r, "file_path", None) for r in recs} == {str(outside_1), str(outside_2)}
    assert all(getattr(r, "reason", None) == "path_traversal" for r in recs)


@pytest.mark.parametrize("error_cls", [PermissionError, FileNotFoundError])
def test_filter_safe_pdfs_logs_io_error(tmp_path: Path, caplog, monkeypatch, error_cls):
    raw = tmp_path / "kb" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    pdf = raw / "blocked.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    original = cu.ensure_within_and_resolve

    def _fake(base_dir: Path, candidate: Path) -> Path:
        if candidate == pdf:
            raise error_cls("access denied")
        return original(base_dir, candidate)

    monkeypatch.setattr(cu, "ensure_within_and_resolve", _fake)

    caplog.set_level(logging.WARNING)
    out = _filter_safe_pdfs(tmp_path, raw, [pdf], slug="dummy")
    assert out == []
    recs = [r for r in caplog.records if r.msg == "pipeline.content.skip_unsafe"]
    assert recs, "evento skip_unsafe mancante"
    rec = recs[0]
    assert getattr(rec, "reason", None) == "io_error"
    assert getattr(rec, "error_type", None) == error_cls.__name__


def test_filter_safe_pdfs_propagates_unexpected_error(tmp_path: Path, caplog, monkeypatch):
    raw = tmp_path / "kb" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    pdf = raw / "fail.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    original = cu._ensure_safe

    def _fake(perimeter: Path, candidate: Path, *, slug: str | None = None) -> Path:
        if candidate == pdf:
            raise RuntimeError("boom")
        return original(perimeter, candidate, slug=slug)

    monkeypatch.setattr(cu, "_ensure_safe", _fake)

    caplog.set_level(logging.WARNING)
    with pytest.raises(RuntimeError):
        _filter_safe_pdfs(tmp_path, raw, [pdf], slug="dummy")

    recs = [r for r in caplog.records if r.msg == "pipeline.content.skip_unsafe"]
    assert recs, "evento skip_unsafe mancante"
    rec = recs[0]
    assert getattr(rec, "reason", None) == "unexpected_error"
    assert getattr(rec, "error_type", None) == "RuntimeError"


def test_convert_files_to_structured_markdown_logs_events_with_slug(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    semantic_dir = base / "semantic"
    normalized_dir = base / "normalized"
    config_dir = base / "config"
    logs_dir = base / "logs"
    (raw / "cat").mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    (book / "README.md").write_text("# README\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (semantic_dir / "semantic_mapping.yaml").write_text("areas: {}\n", encoding="utf-8")
    (config_dir / "config.yaml").write_text("{}", encoding="utf-8")

    root_pdf = raw / "x.pdf"
    cat_pdf = raw / "cat" / "y.pdf"
    root_pdf.write_bytes(b"%PDF-1.4\n")
    cat_pdf.write_bytes(b"%PDF-1.4\n")

    # Simula symlink per root_pdf
    real_is_symlink = Path.is_symlink

    def _fake_is_symlink(self: Path) -> bool:  # type: ignore[override]
        return str(self) == str(root_pdf) or real_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _fake_is_symlink)

    # Simula path non sicuro per cat_pdf
    def _fake_ensure_within_and_resolve(base_dir: Path, candidate: Path) -> Path:  # noqa: ARG001
        if str(candidate) == str(cat_pdf):
            raise PathTraversalError("path traversal")
        return candidate.resolve()

    monkeypatch.setattr(
        "pipeline.content_utils.ensure_within_and_resolve",
        _fake_ensure_within_and_resolve,
    )

    ctx = type(
        "C",
        (),
        {"base_dir": base, "repo_root_dir": base, "raw_dir": raw, "book_dir": book, "slug": "dummy"},
    )()
    caplog.set_level(logging.WARNING)
    convert_files_to_structured_markdown(ctx)

    msgs = [r.msg for r in caplog.records]
    assert "pipeline.content.skip_symlink" in msgs
    assert "pipeline.content.skip_unsafe" in msgs
    # Controlla slug propagato
    for key, p in (("pipeline.content.skip_symlink", root_pdf), ("pipeline.content.skip_unsafe", cat_pdf)):
        recs = [r for r in caplog.records if r.msg == key]
        assert recs, f"evento {key} mancante"
        assert getattr(recs[0], "slug", None) == "dummy"
        assert str(p) in getattr(recs[0], "file_path", "")


def test_safe_log_non_strict_never_raises_in_worst_case(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenLogger:
        def info(self, *_a, **_k):
            raise RuntimeError("structured boom")

    class _BrokenFallback:
        def warning(self, *_a, **_k):
            raise RuntimeError("fallback warning boom")

        def info(self, *_a, **_k):
            raise RuntimeError("fallback info boom")

    logger = _BrokenLogger()
    monkeypatch.setattr(cu, "_FALLBACK_LOG", _BrokenFallback())
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")

    cu._safe_log(logger, "info", "pipeline.content.test_worst_case", extra={"k": "v"})


def test_safe_log_strict_raises_explicit_failure(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class _BrokenLogger:
        def info(self, *_a, **_k):
            raise RuntimeError("structured boom")

    class _BrokenFallback:
        def warning(self, *_a, **_k):
            raise RuntimeError("fallback warning boom")

        def info(self, *_a, **_k):
            raise RuntimeError("fallback info boom")

    logger = _BrokenLogger()
    monkeypatch.setattr(cu, "_FALLBACK_LOG", _BrokenFallback())
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")

    with pytest.raises(PipelineError, match="strict runtime"):
        cu._safe_log(logger, "info", "pipeline.content.test_worst_case", extra={"k": "v"})

    captured = capsys.readouterr()
    assert captured.err == ""
