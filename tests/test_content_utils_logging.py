from __future__ import annotations

import logging
from pathlib import Path

from pipeline.content_utils import _filter_safe_pdfs, convert_files_to_structured_markdown


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
    assert hasattr(rec, "error")


def test_convert_files_to_structured_markdown_logs_events_with_slug(tmp_path: Path, caplog, monkeypatch):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    (raw / "cat").mkdir(parents=True, exist_ok=True)
    book.mkdir(parents=True, exist_ok=True)

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
            raise RuntimeError("unsafe")
        return candidate.resolve()

    monkeypatch.setattr(
        "pipeline.content_utils.ensure_within_and_resolve",
        _fake_ensure_within_and_resolve,
    )

    ctx = type("C", (), {"base_dir": base, "raw_dir": raw, "md_dir": book, "slug": "dummy"})()
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
