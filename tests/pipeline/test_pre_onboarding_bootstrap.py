# SPDX-License-Identifier: GPL-3.0-or-later
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
        config_path=base / "config" / "config.yaml",
    )


def test_pre_onboarding_local_structure_invokes_bootstrap(
    tmp_path: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "test-client"
    base = tmp_path / f"timmy-kb-{slug}"
    context = _build_context(base, slug)

    src_timmy_kb = Path(pre_onboarding.__file__).resolve().parents[1]
    spurious_paths = [
        src_timmy_kb / "output" / "timmy-kb-dummy",
        src_timmy_kb / "output" / f"timmy-kb-{slug}",
    ]
    existing_spurious = [str(path) for path in spurious_paths if path.exists()]
    assert not existing_spurious, (
        "Trovate directory spurie sotto src/timmy_kb/output (non devono essere create dai test):\n"
        + "\n".join(f"- {path}" for path in existing_spurious)
        + "\nSuggerimento: rimuovile manualmente e verifica la regressione su repo_root."
    )

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

    # Regression guard: non creare output spurio sotto src/timmy_kb/
    assert not (src_timmy_kb / "output" / "timmy-kb-dummy").exists()
    assert not (src_timmy_kb / "output" / f"timmy-kb-{slug}").exists()
