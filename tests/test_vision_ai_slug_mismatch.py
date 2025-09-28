from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pipeline.exceptions import ConfigError


class _DummyCtx:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = str(base_dir)
        self.client_name = None
        self.settings: dict[str, Any] | None = None


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.refusal = None


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Msg(content)
        self.finish_reason = None


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.choices = [_Choice(json.dumps(payload))]
        self.usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()


class _Client:
    class _Chat:
        class _Completions:
            def __init__(self, payload: dict[str, Any]) -> None:
                self._payload = payload

            def create(self, **_kwargs: Any) -> _Resp:  # type: ignore[override]
                return _Resp(self._payload)

        def __init__(self, payload: dict[str, Any]) -> None:
            self.completions = _Client._Chat._Completions(payload)

    def __init__(self, payload: dict[str, Any]) -> None:
        self.chat = _Client._Chat(payload)


def test_vision_ai_slug_mismatch_raises_and_writes_no_yaml(tmp_path, monkeypatch):
    # Arrange workspace
    slug = "acme"
    base = tmp_path / f"output/timmy-kb-{slug}"
    (base / "raw").mkdir(parents=True, exist_ok=True)
    pdf = base / "raw" / "VisionStatement.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    ctx = _DummyCtx(base)

    # Stub model client to return a mismatched slug
    payload = {
        "context": {"slug": "other", "client_name": "X"},
        "areas": [
            {"key": "k", "ambito": "a", "descrizione": "d", "esempio": ["e"]},
        ],
    }

    import src.semantic.vision_ai as v

    monkeypatch.setattr(v, "make_openai_client", lambda: _Client(payload), raising=True)
    monkeypatch.setattr(v, "_extract_pdf_text", lambda _p: "text", raising=True)

    # Act + Assert
    with pytest.raises(ConfigError):
        v.generate_pair(ctx, v.logging.getLogger("test"), slug=slug)

    # YAML non devono essere stati scritti
    mapping = Path(ctx.base_dir) / "semantic" / "semantic_mapping.yaml"
    cartelle = Path(ctx.base_dir) / "semantic" / "cartelle_raw.yaml"
    assert not mapping.exists()
    assert not cartelle.exists()
