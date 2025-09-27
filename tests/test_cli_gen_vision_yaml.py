# tests/test_cli_gen_vision_yaml.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# bootstrap: aggiungi src/ al path come fa la UI
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# importiamo il main della CLI
import tools.gen_vision_yaml as cli  # noqa: E402
from semantic import vision_ai  # noqa: E402


class DummyCtx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


class _NoopLogger:
    def info(self, *args, **kwargs): ...
    def error(self, *args, **kwargs): ...
    def exception(self, *args, **kwargs): ...


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "VisionStatement.pdf").write_bytes(b"%PDF dummy")
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def test_cli_returns_zero_on_success(monkeypatch, tmp_workspace: Path):
    # mock ClientContext.load per evitare dipendenze
    monkeypatch.setattr(
        cli.ClientContext, "load", lambda slug, interactive, require_env, run_id: DummyCtx(base_dir=tmp_workspace)
    )
    # mock generate per non toccare OpenAI
    monkeypatch.setattr(
        vision_ai, "generate", lambda ctx, logger, slug: str(tmp_workspace / "semantic" / "semantic_mapping.yaml")
    )
    # esegui main con arg finti
    monkeypatch.setattr(sys, "argv", ["prog", "--slug", "dummy"])
    rc = cli.main()
    assert rc == 0


def test_cli_returns_2_on_config_error(monkeypatch, tmp_workspace: Path):
    from semantic.vision_ai import ConfigError

    monkeypatch.setattr(
        cli.ClientContext, "load", lambda slug, interactive, require_env, run_id: DummyCtx(base_dir=tmp_workspace)
    )

    def _raise(*a, **k):
        raise ConfigError("boom")

    monkeypatch.setattr(vision_ai, "generate", _raise)
    monkeypatch.setattr(sys, "argv", ["prog", "--slug", "dummy"])
    rc = cli.main()
    assert rc == 2
