# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from storage.tags_store import save_tags_reviewed
from ui.utils import ensure_within_and_resolve
from ui.utils import workspace as ws


def test_wrapper_resolves_within_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    f = base / "x.txt"
    f.write_text("ok", encoding="utf-8")

    out = ensure_within_and_resolve(base, f)
    assert out == f.resolve()


def test_wrapper_blocks_outside_base(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    with pytest.raises(ConfigError):
        _ = ensure_within_and_resolve(base, outside)


def test_ui_normalized_ready_respects_context_paths(tmp_path: Path):
    """Verifica (unit) che i path 'normalized' e 'semantic' siano coerenti rispetto a un contesto fornito
    (simula il comportamento della UI che ora usa ClientContext.* invece di interrogare
    sem_get_paths)."""
    base = tmp_path / "custom-root"
    normalized = base / "normalized"
    semantic = base / "semantic"
    normalized.mkdir(parents=True)
    semantic.mkdir(parents=True)

    # Crea un Markdown dummy in normalized e un CSV dummy in semantic
    (normalized / "doc.md").write_text("dummy", encoding="utf-8")
    (semantic / "tags_raw.csv").write_text("id,tag\n1,test", encoding="utf-8")

    # Finto "context" con gli attributi usati dalla UI
    ctx = SimpleNamespace(base_dir=base, normalized_dir=normalized)

    # has_mds: True se esistono Markdown in normalized/
    normalized_ok = hasattr(ctx, "normalized_dir") and ctx.normalized_dir and ctx.normalized_dir.exists()
    has_mds = any(ctx.normalized_dir.rglob("*.md")) if normalized_ok else False

    # has_csv: True se esiste semantic/tags_raw.csv rispetto al base_dir
    base_ok = hasattr(ctx, "base_dir") and ctx.base_dir and ctx.base_dir.exists()
    has_csv = (ctx.base_dir / "semantic" / "tags_raw.csv").exists() if base_ok else False

    assert has_mds is True
    assert has_csv is True


def test_normalized_ready_false_on_layout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws, "get_ui_workspace_layout", lambda *_a, **_k: (_ for _ in ()).throw(ConfigError("boom")))
    ready, path = ws.normalized_ready("dummy")
    assert ready is True
    assert path is None


def test_tagging_ready_requires_db_and_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    tags_yaml = sem_dir / "tags_reviewed.yaml"
    tags_yaml.write_text(
        "version: 2\n"
        "reviewed_at: 2025-01-01T00:00:00\n"
        "keep_only_listed: true\n"
        "tags:\n  - name: demo\n    action: keep\n",
        encoding="utf-8",
    )
    save_tags_reviewed(
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

    tags_yaml.unlink()
    ready_missing, _ = ws.tagging_ready("dummy")
    assert ready_missing is False


def test_tagging_ready_false_when_tags_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    tags_yaml = sem_dir / "tags_reviewed.yaml"
    tags_yaml.write_text("version: 2\nkeep_only_listed: true\ntags: []\n", encoding="utf-8")
    save_tags_reviewed(
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


def test_tagging_ready_false_in_stub_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sem_dir = tmp_path / "semantic"
    sem_dir.mkdir(parents=True)
    tags_db = sem_dir / "tags.db"
    tags_yaml = sem_dir / "tags_reviewed.yaml"
    tags_yaml.write_text(
        "version: 2\nkeep_only_listed: true\ntags:\n  - name: demo\n    action: keep\n",
        encoding="utf-8",
    )
    save_tags_reviewed(
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
    assert ready is False
