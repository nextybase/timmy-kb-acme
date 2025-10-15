# tests/test_vision_cfg.py

import pytest

from ingest import get_vision_cfg
from pipeline.exceptions import ConfigError


def test_get_vision_cfg_requires_assistant_id(monkeypatch):
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)
    with pytest.raises(ConfigError):
        get_vision_cfg({})


def test_get_vision_cfg_ok(monkeypatch):
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_123")
    cfg = get_vision_cfg({})
    assert cfg["engine"] == "assistant"
    assert cfg["assistant_id"] == "asst_123"
    assert cfg["input_mode"] == "inline"
    assert cfg["fs_mode"] is None
    assert cfg["model"] is None
    assert cfg["strict_output"] is True
