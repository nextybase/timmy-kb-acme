# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from types import MappingProxyType

import pytest

from pipeline.exceptions import ConfigError
from rosetta.client import OpenAIRosettaClient, RosettaConfig, get_rosetta_client


def test_get_rosetta_client_disabled_returns_none():
    client = get_rosetta_client(config=RosettaConfig(enabled=False))
    assert client is None


def test_get_rosetta_client_openai_without_client(monkeypatch):
    cfg = RosettaConfig(enabled=True, provider="openai")
    with pytest.raises(ConfigError):
        get_rosetta_client(
            config=cfg,
            client_factory=lambda: (_ for _ in ()).throw(
                ConfigError("OPENAI_API_KEY mancante"),
            ),
        )


def test_rosetta_methods_do_not_fail(monkeypatch):
    cfg = RosettaConfig(enabled=True, provider="openai", model="gpt-4o-mini")
    stub_client = object()
    client = get_rosetta_client(
        config=cfg,
        client_factory=lambda: stub_client,
        slug="dummy",
    )
    assert isinstance(client, OpenAIRosettaClient)

    coherence = client.check_coherence(
        assertions=[MappingProxyType({"id": "a"})],
        run_id="run123",
        metadata={"ticket": "t1"},
    )
    assert coherence["status"] == "ok"

    proposal = client.propose_updates(
        assertion_id="a",
        candidate={"value": 1},
        provenance={"source": "test"},
        run_id="run123",
    )
    assert proposal["decision"] in {"accept", "keep_candidate", "conflict"}

    explanation = client.explain(assertion_id="a", run_id="run123")
    assert explanation["assertion_id"] == "a"


def test_invalid_provider_raises_config_error():
    cfg = RosettaConfig(enabled=True, provider="unknown")
    with pytest.raises(ConfigError):
        get_rosetta_client(config=cfg)
