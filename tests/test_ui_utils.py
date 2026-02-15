# SPDX-License-Identifier: GPL-3.0-or-later
# Focus: UI contract behavior only.
# This suite exercises UI-level helpers; it must not retest backend path-safety invariants
# (owned by tests/test_path_utils.py) unless the UI introduces genuinely distinct behavior.
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from storage.tags_store import save_tags_db
from ui.utils import workspace as ws


def test_normalized_ready_false_on_layout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "get_ui_workspace_layout", lambda *_a, **_k: (_ for _ in ()).throw(ConfigError("boom")))
    ready, path = ws.normalized_ready("dummy")
    assert ready is True
    assert path is None


def test_tagging_ready_requires_db_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    save_tags_db(
        str(tags_db),
        {
            "version": "2",
            "reviewed_at": "2025-01-01T00:00:00",
            "keep_only_listed": True,
            "tags": [{"name": "demo", "action": "keep", "synonyms": [], "note": ""}],
        },
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ws,
        "get_ui_workspace_layout",
        lambda *_a, **_k: SimpleNamespace(
            semantic_dir=sem_dir, tags_db=tags_db, normalized_dir=tmp_path / "normalized"
        ),
    )
    monkeypatch.setattr(ws, "normalized_ready", lambda _slug, **_kwargs: (True, tmp_path / "normalized"))

    ready, path = ws.tagging_ready("dummy")
    assert ready is True
    assert path == sem_dir

    tags_db.unlink()
    ready_missing, _ = ws.tagging_ready("dummy")
    assert ready_missing is False


def test_tagging_ready_false_when_tags_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    save_tags_db(
        str(tags_db),
        {
            "version": "2",
            "reviewed_at": "2025-01-01T00:00:00",
            "keep_only_listed": True,
            "tags": [],
        },
    )

    monkeypatch.setattr(
        ws,
        "get_ui_workspace_layout",
        lambda *_a, **_k: SimpleNamespace(
            semantic_dir=sem_dir, tags_db=tags_db, normalized_dir=tmp_path / "normalized"
        ),
    )
    monkeypatch.setattr(ws, "normalized_ready", lambda _slug, **_kwargs: (True, tmp_path / "normalized"))

    ready, _ = ws.tagging_ready("dummy")
    assert ready is False


def test_tagging_ready_true_ignores_legacy_tags_mode_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    save_tags_db(
        str(tags_db),
        {
            "version": "2",
            "reviewed_at": "2025-01-01T00:00:00",
            "keep_only_listed": True,
            "tags": [{"name": "demo", "action": "keep", "synonyms": [], "note": ""}],
        },
    )
    monkeypatch.setenv("TAGS_MODE", "stub")
    monkeypatch.setattr(
        ws,
        "get_ui_workspace_layout",
        lambda *_a, **_k: SimpleNamespace(
            semantic_dir=sem_dir, tags_db=tags_db, normalized_dir=tmp_path / "normalized"
        ),
    )
    monkeypatch.setattr(ws, "normalized_ready", lambda _slug, **_kwargs: (True, tmp_path / "normalized"))

    ready, _ = ws.tagging_ready("dummy")
    assert ready is True


def test_tagging_ready_no_legacy_fallback_when_layout_tags_db_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    save_tags_db(
        str(tags_db),
        {
            "version": "2",
            "reviewed_at": "2025-01-01T00:00:00",
            "keep_only_listed": True,
            "tags": [{"name": "demo", "action": "keep", "synonyms": [], "note": ""}],
        },
    )

    monkeypatch.setattr(
        ws,
        "get_ui_workspace_layout",
        lambda *_a, **_k: SimpleNamespace(
            semantic_dir=sem_dir,
            tags_db=None,
            normalized_dir=tmp_path / "normalized",
        ),
    )
    monkeypatch.setattr(ws, "normalized_ready", lambda _slug, **_kwargs: (True, tmp_path / "normalized"))

    ready, path = ws.tagging_ready("dummy")
    assert ready is False
    assert path == sem_dir


def test_tagging_ready_strict_raises_when_layout_tags_db_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    monkeypatch.setattr(
        ws,
        "get_ui_workspace_layout",
        lambda *_a, **_k: SimpleNamespace(
            semantic_dir=sem_dir,
            tags_db=None,
            normalized_dir=tmp_path / "normalized",
        ),
    )
    monkeypatch.setattr(ws, "normalized_ready", lambda _slug, **_kwargs: (True, tmp_path / "normalized"))

    with pytest.raises(ConfigError, match="missing tags_db path"):
        ws.tagging_ready("dummy", strict=True)
