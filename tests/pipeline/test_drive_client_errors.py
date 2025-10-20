# tests/pipeline/test_drive_client_errors.py
from __future__ import annotations

import types
from typing import Any

import pytest

from pipeline.drive.client import get_file_metadata, list_drive_files
from pipeline.exceptions import ConfigError


class _ServiceStub(types.SimpleNamespace):
    """Stub minimale per simulare il resource Drive."""

    def files(self) -> Any:
        return self

    # get/list non verranno chiamati perché validiamo prima i parametri
    def get(self, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("get() non dovrebbe essere invocato su input non valido")

    def list(self, **_kwargs: Any) -> Any:  # pragma: no cover
        raise AssertionError("list() non dovrebbe essere invocato su input non valido")


def test_list_drive_files_parent_id_required():
    service = _ServiceStub()
    with pytest.raises(ConfigError):
        # parent_id mancante → ConfigError
        list_drive_files(service, parent_id="")


def test_get_file_metadata_file_id_required():
    service = _ServiceStub()
    with pytest.raises(ConfigError):
        # file_id mancante → ConfigError
        get_file_metadata(service, file_id="")
