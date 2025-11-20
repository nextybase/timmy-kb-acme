# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_workspace_helpers.py
from pathlib import Path

import pytest

import ui.utils.workspace as workspace
from ui.utils.workspace import count_pdfs_safe, iter_pdfs_safe


def test_iter_pdfs_safe_basic(tmp_path: Path):
    root = tmp_path / "raw"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.pdf").write_text("%PDF-1.4")
    (root / "a" / "y.txt").write_text("nope")
    assert list(iter_pdfs_safe(root)) == [root / "a" / "x.pdf"]
    assert count_pdfs_safe(root) == 1


def test_iter_pdfs_safe_symlink(tmp_path: Path):
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "ext.pdf").write_text("%PDF-1.4")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink non permessi su questo sistema")
    # Non deve vedere file fuori perimetro
    assert count_pdfs_safe(root) == 0


def test_iter_pdfs_safe_passes_cache_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()

    captured: dict[str, object] = {}

    def _fake_iter_safe(
        root_arg: object,
        *,
        on_skip: object = None,
        use_cache: bool = False,
        cache_ttl_s: float | None = None,
    ):
        captured["kwargs"] = {
            "on_skip": on_skip,
            "use_cache": use_cache,
            "cache_ttl_s": cache_ttl_s,
        }
        return iter(())

    monkeypatch.setattr(workspace, "iter_safe_pdfs", _fake_iter_safe)

    list(workspace.iter_pdfs_safe(root, use_cache=True, cache_ttl_s=1.5))
    assert captured.get("kwargs") == {"on_skip": None, "use_cache": True, "cache_ttl_s": 1.5}
