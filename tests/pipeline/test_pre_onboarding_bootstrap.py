# SPDX-License-Identifier: GPL-3.0-only
import logging
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.paths import workspace_paths
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


def test_bootstrap_semantic_templates_writes_cartelle_raw_only_in_workspace(
    tmp_path: Path, logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "test-client"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    template_src = repo_root / "_templates" / "cartelle_raw.yaml"
    template_src.parent.mkdir(parents=True)
    template_payload = "cartelle: []\n"
    template_src.write_text(template_payload, encoding="utf-8")

    layout = workspace_paths(slug, repo_root=repo_root, create=False)
    context = ClientContext(
        slug=slug,
        repo_root_dir=repo_root,
        base_dir=layout.workspace_root,
        raw_dir=layout.raw_dir,
        md_dir=layout.book_dir,
        config_path=layout.config_file,
        output_dir=layout.workspace_root,
    )

    monkeypatch.setattr(pre_onboarding, "_resolve_yaml_structure_file", lambda: template_src)

    pre_onboarding.bootstrap_semantic_templates(repo_root, context, client_name="Test Client", logger=logger)

    expected_dst = workspace_paths(slug, repo_root=repo_root, create=False).semantic_dir / "cartelle_raw.yaml"
    assert expected_dst.is_file()
    assert expected_dst.read_text(encoding="utf-8") == template_payload

    wrong_repo_dst = repo_root / "semantic" / "cartelle_raw.yaml"
    assert not wrong_repo_dst.exists()
