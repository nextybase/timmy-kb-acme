# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
from typing import Any

import pytest

from pipeline import path_utils, yaml_utils


def test_raw_cache_defaults_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    original_yaml_read = path_utils.yaml_read

    def fake_yaml_read(base: Any, path: Any, *, use_cache: bool = True):
        return {"raw_cache": {"ttl_seconds": 123, "max_entries": 5}}

    monkeypatch.setattr(path_utils, "yaml_read", fake_yaml_read)

    path_utils._load_raw_cache_defaults()

    assert path_utils._SAFE_PDF_CACHE_DEFAULT_TTL == 123
    assert path_utils._SAFE_PDF_CACHE_CAPACITY == 5

    # Restore defaults
    monkeypatch.setattr(path_utils, "yaml_read", original_yaml_read)
    path_utils._load_raw_cache_defaults()


def test_raw_cache_lazy_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    calls: list[Any] = []
    original_yaml_read = yaml_utils.yaml_read

    def fake_yaml_read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(yaml_utils, "yaml_read", fake_yaml_read)

    module = importlib.reload(path_utils)
    try:
        assert getattr(module, "_CACHE_DEFAULTS_LOADED") is False
        assert calls == []

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        list(module.iter_safe_pdfs(raw_dir, use_cache=True))
        assert len(calls) == 1

        list(module.iter_safe_pdfs(raw_dir, use_cache=True))
        assert len(calls) == 1
    finally:
        monkeypatch.setattr(yaml_utils, "yaml_read", original_yaml_read)
        importlib.reload(path_utils)


def test_raw_cache_defaults_remain_until_first_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    module = importlib.reload(path_utils)
    sentinel_ttl = 42.0
    sentinel_capacity = 2

    def fake_yaml_read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"raw_cache": {"ttl_seconds": sentinel_ttl, "max_entries": sentinel_capacity}}

    monkeypatch.setattr(module, "yaml_read", fake_yaml_read)
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
    module = importlib.reload(path_utils)
    call_count = 0

    def fake_yaml_read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {}

    monkeypatch.setattr(module, "yaml_read", fake_yaml_read)
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
