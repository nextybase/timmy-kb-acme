# SPDX-License-Identifier: GPL-3.0-only
from types import SimpleNamespace

from pipeline.file_utils import safe_write_text
from timmy_kb.cli.tag_onboarding import validate_tags_reviewed


def test_validate_tags_reviewed_rejects_semantic_outside_base(tmp_path, monkeypatch):
    base_dir = tmp_path / "client"
    base_dir.mkdir()
    (base_dir / "raw").mkdir()
    (base_dir / "normalized").mkdir()
    book_dir = base_dir / "book"
    book_dir.mkdir()
    safe_write_text(book_dir / "README.md", "# Dummy book\n", encoding="utf-8")
    safe_write_text(book_dir / "SUMMARY.md", "* [Dummy](README.md)\n", encoding="utf-8")
    (base_dir / "semantic").mkdir()
    (base_dir / "logs").mkdir()
    config_dir = base_dir / "config"
    config_dir.mkdir()
    safe_write_text(config_dir / "config.yaml", "ops: {}\n", encoding="utf-8")
    context = SimpleNamespace(
        slug="dummy",
        base_dir=base_dir,
        repo_root_dir=base_dir,
        raw_dir=base_dir / "raw",
        semantic_dir=tmp_path.parent / "evil",
        redact_logs=False,
        run_id=None,
    )

    def fake_load(*args, **kwargs):
        return context

    monkeypatch.setattr("timmy_kb.cli.tag_onboarding.ClientContext.load", fake_load)

    assert validate_tags_reviewed("dummy") == 1
