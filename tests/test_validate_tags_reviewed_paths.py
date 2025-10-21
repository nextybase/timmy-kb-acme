from types import SimpleNamespace

import pytest

from pipeline.exceptions import PathTraversalError
from timmykb.tag_onboarding import validate_tags_reviewed


def test_validate_tags_reviewed_rejects_semantic_outside_base(tmp_path, monkeypatch):
    base_dir = tmp_path / "client"
    base_dir.mkdir()
    (base_dir / "raw").mkdir()
    context = SimpleNamespace(
        slug="acme",
        base_dir=base_dir,
        repo_root_dir=None,
        raw_dir=base_dir / "raw",
        semantic_dir=tmp_path.parent / "evil",
        redact_logs=False,
        run_id=None,
    )

    def fake_load(*args, **kwargs):
        return context

    monkeypatch.setattr("src.tag_onboarding.ClientContext.load", fake_load)

    with pytest.raises(PathTraversalError):
        validate_tags_reviewed("acme")
