# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError
from semantic import api as sapi
from semantic import convert_service
from tests._helpers.workspace_paths import local_workspace_dir
from tests.support.contexts import TestClientCtx
from timmy_kb.cli import semantic_headless as sh


@pytest.fixture(autouse=True)
def strict_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")


def test_headless_fails_without_vocab(tmp_path, monkeypatch):
    base = local_workspace_dir(tmp_path / "output", "dummy")
    book = base / "book"
    raw = base / "raw"
    for d in (book, raw):
        d.mkdir(parents=True, exist_ok=True)

    md = book / "my_first_doc.md"
    md.write_text("Body only\n", encoding="utf-8")

    ctx = TestClientCtx(
        slug="dummy",
        repo_root_dir=base,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )

    monkeypatch.setattr(convert_service, "convert_markdown", lambda *a, **k: [md.relative_to(book)])
    monkeypatch.setattr(sapi, "load_reviewed_vocab", lambda *a, **k: {})

    with pytest.raises(ConfigError):
        sh.build_markdown_headless(ctx, sapi.logging.getLogger("test.headless"), slug="dummy")


def test_main_logs_namespaced_events(monkeypatch, caplog):
    args = SimpleNamespace(slug="dummy", non_interactive=True, no_preview=True, log_level="INFO")
    monkeypatch.setattr(sh, "_parse_args", lambda: args)
    monkeypatch.setattr(
        sh,
        "_setup_logger",
        lambda level, slug=None: sh.get_structured_logger("test.headless", context={"slug": slug}),
    )

    def _boom(**_kwargs):
        raise sh.ConfigError("boom")

    monkeypatch.setattr("pipeline.context.ClientContext", SimpleNamespace(load=_boom))
    caplog.set_level("ERROR")

    exit_code = sh.main()

    assert exit_code == 2
    assert any(rec.message == "semantic.headless.context_load_failed" for rec in caplog.records)
