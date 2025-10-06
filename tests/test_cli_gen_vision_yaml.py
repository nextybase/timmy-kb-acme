# tests/test_cli_gen_vision_yaml.py
from __future__ import annotations

import sys
from pathlib import Path

# bootstrap: aggiungi src/ al path come fa la UI
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# importiamo il main della CLI
import tools.gen_vision_yaml as cli  # noqa: E402
from semantic import vision_ai  # noqa: E402


def test_cli_returns_zero_on_success(monkeypatch, dummy_workspace, dummy_ctx):
    ctx = dummy_ctx
    monkeypatch.setattr(
        cli.ClientContext,
        "load",
        lambda slug, interactive, require_env, run_id: ctx,
    )
    monkeypatch.setattr(
        vision_ai,
        "generate",
        lambda ctx, logger, slug: str(dummy_workspace["semantic_mapping"]),
    )
    monkeypatch.setattr(sys, "argv", ["prog", "--slug", dummy_workspace["slug"]])
    rc = cli.main()
    assert rc == 0


def test_cli_returns_2_on_config_error(monkeypatch, dummy_workspace, dummy_ctx):
    from semantic.vision_ai import ConfigError

    ctx = dummy_ctx
    monkeypatch.setattr(
        cli.ClientContext,
        "load",
        lambda slug, interactive, require_env, run_id: ctx,
    )

    def _raise(*_a, **_k):
        raise ConfigError("boom")

    monkeypatch.setattr(vision_ai, "generate", _raise)
    monkeypatch.setattr(sys, "argv", ["prog", "--slug", dummy_workspace["slug"]])
    rc = cli.main()
    assert rc == 2
