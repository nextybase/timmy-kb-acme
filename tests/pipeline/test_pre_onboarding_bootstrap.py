# SPDX-License-Identifier: GPL-3.0-only
import logging
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from timmy_kb.cli import pre_onboarding


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test.pre_onboarding")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def _build_context(base: Path, slug: str) -> ClientContext:
    return ClientContext(
        slug=slug,
        repo_root_dir=base,
        base_dir=base,
        raw_dir=base / "raw",
        md_dir=base / "book",
        config_path=base / "config" / "config.yaml",
        output_dir=base,
    )


def test_pre_onboarding_local_structure_invokes_bootstrap(
    tmp_path: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "test-client"
    base = tmp_path / f"timmy-kb-{slug}"
    context = _build_context(base, slug)

    called: list[ClientContext] = []

    original = pre_onboarding.bootstrap_client_workspace

    def instrumented(ctx: ClientContext):
        called.append(ctx)
        return original(ctx)

    monkeypatch.setattr(pre_onboarding, "bootstrap_client_workspace", instrumented)

    config_path = pre_onboarding._create_local_structure(context, logger, client_name="Test Client")

    assert called == [context]
    assert config_path == context.config_path
    assert (base / "config" / "config.yaml").is_file()
    layout = pre_onboarding.WorkspaceLayout.from_context(context)
    assert layout.slug == slug
