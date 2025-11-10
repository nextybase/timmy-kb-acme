# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import Any

import pytest

from pipeline import path_utils


def test_raw_cache_defaults_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    original_yaml_read = path_utils.yaml_read

    def fake_yaml_read(base: Any, path: Any, *, use_cache: bool = True):
        return {"raw_cache": {"ttl_seconds": 123, "max_entries": 5}}

    monkeypatch.setattr(path_utils, "yaml_read", fake_yaml_read)
    monkeypatch.delenv("TIMMY_SAFE_PDF_CACHE_TTL", raising=False)
    monkeypatch.delenv("TIMMY_SAFE_PDF_CACHE_CAPACITY", raising=False)

    path_utils._load_raw_cache_defaults()

    assert path_utils._SAFE_PDF_CACHE_DEFAULT_TTL == 123
    assert path_utils._SAFE_PDF_CACHE_CAPACITY == 5

    # Restore defaults
    monkeypatch.setattr(path_utils, "yaml_read", original_yaml_read)
    path_utils._load_raw_cache_defaults()


def test_raw_cache_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    original_yaml_read = path_utils.yaml_read
    monkeypatch.setattr(path_utils, "yaml_read", lambda *_args, **_kwargs: {})
    monkeypatch.setenv("TIMMY_SAFE_PDF_CACHE_TTL", "42")
    monkeypatch.setenv("TIMMY_SAFE_PDF_CACHE_CAPACITY", "2")

    path_utils._load_raw_cache_defaults()

    assert path_utils._SAFE_PDF_CACHE_DEFAULT_TTL == 42
    assert path_utils._SAFE_PDF_CACHE_CAPACITY == 2

    # Cleanup
    monkeypatch.delenv("TIMMY_SAFE_PDF_CACHE_TTL", raising=False)
    monkeypatch.delenv("TIMMY_SAFE_PDF_CACHE_CAPACITY", raising=False)
    monkeypatch.setattr(path_utils, "yaml_read", original_yaml_read)
    path_utils._load_raw_cache_defaults()
