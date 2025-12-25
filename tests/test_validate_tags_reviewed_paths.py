# SPDX-License-Identifier: GPL-3.0-only
from types import SimpleNamespace

from timmy_kb.cli.tag_onboarding import validate_tags_reviewed


def test_validate_tags_reviewed_rejects_semantic_outside_base(tmp_path, monkeypatch):
    base_dir = tmp_path / "client"
    base_dir.mkdir()
    (base_dir / "raw").mkdir()
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
