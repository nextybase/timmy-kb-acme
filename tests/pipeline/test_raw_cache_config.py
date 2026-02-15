# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib
from typing import Any

import pytest

from pipeline import path_utils


def test_raw_cache_defaults_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    path_utils._load_raw_cache_defaults(
        loader=lambda: {"pipeline": {"raw_cache": {"ttl_seconds": 123, "max_entries": 5}}}
    )

    assert path_utils._SAFE_PDF_CACHE_DEFAULT_TTL == 123
    assert path_utils._SAFE_PDF_CACHE_CAPACITY == 5

    # Restore defaults
    path_utils._load_raw_cache_defaults(loader=lambda: {})


def test_raw_cache_lazy_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    calls = 0

    module = importlib.reload(path_utils)
    original_loader = module._load_raw_cache_defaults

    def counting_loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {}

    def patched(loader: Any | None = None) -> None:
        return original_loader(loader=loader or counting_loader)

    monkeypatch.setattr(module, "_load_raw_cache_defaults", patched)

    assert getattr(module, "_CACHE_DEFAULTS_LOADED") is False
    assert calls == 0

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    list(module.iter_safe_pdfs(raw_dir, use_cache=True))
    assert calls == 1

    list(module.iter_safe_pdfs(raw_dir, use_cache=True))
    assert calls == 1

    importlib.reload(path_utils)


def test_raw_cache_defaults_remain_until_first_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    module = importlib.reload(path_utils)
    sentinel_ttl = 42.0
    sentinel_capacity = 2

    original_loader = module._load_raw_cache_defaults

    def patched(loader: Any | None = None) -> None:
        return original_loader(
            loader=loader
            or (lambda: {"pipeline": {"raw_cache": {"ttl_seconds": sentinel_ttl, "max_entries": sentinel_capacity}}})
        )

    monkeypatch.setattr(module, "_load_raw_cache_defaults", patched)
    module._CACHE_DEFAULTS_LOADED = False

    assert module._SAFE_PDF_CACHE_DEFAULT_TTL == module._DEFAULT_RAW_CACHE_TTL
    assert module._SAFE_PDF_CACHE_CAPACITY == module._DEFAULT_RAW_CACHE_CAPACITY

    raw_dir = tmp_path / "client" / "raw"
    raw_dir.mkdir(parents=True)

    list(module.iter_safe_pdfs(raw_dir, use_cache=True))

    assert module._CACHE_DEFAULTS_LOADED is True
    assert module._SAFE_PDF_CACHE_DEFAULT_TTL == pytest.approx(sentinel_ttl)
    assert module._SAFE_PDF_CACHE_CAPACITY == sentinel_capacity


@pytest.mark.parametrize(
    "invoker",
    ("clear", "preload", "refresh", "iter"),
)
def test_raw_cache_guard_invoked_in_public_apis(
    invoker: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    module = importlib.reload(path_utils)
    call_count = 0

    original_loader = module._load_raw_cache_defaults

    def patched(loader: Any | None = None) -> None:
        nonlocal call_count

        def counting_loader() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {}

        return original_loader(loader=loader or counting_loader)

    monkeypatch.setattr(module, "_load_raw_cache_defaults", patched)
    module._CACHE_DEFAULTS_LOADED = False

    raw_dir = tmp_path / "customer" / "raw"
    raw_dir.mkdir(parents=True)

    if invoker == "clear":
        module.clear_iter_safe_pdfs_cache()
    elif invoker == "preload":
        module.preload_iter_safe_pdfs_cache(raw_dir)
    elif invoker == "refresh":
        target = raw_dir / "doc.pdf"
        target.touch()
        module.refresh_iter_safe_pdfs_cache_for_path(target)
    elif invoker == "iter":
        list(module.iter_safe_pdfs(raw_dir, use_cache=True))
    else:
        pytest.fail(f"Unexpected invoker {invoker}")

    assert call_count == 1
