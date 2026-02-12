# SPDX-License-Identifier: GPL-3.0-or-later
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from tools import tuning_pdf_to_yaml as pdf_tool
from tools import tuning_system_prompt as prompt_tool
from tools import tuning_vision_provision as vision_tool


@contextmanager
def _fake_context_manager(step_list, step_name):
    @contextmanager
    def _manager(*, logger=None, slug=None, base_dir=None):
        step_list.append((step_name, slug, base_dir))
        yield

    yield _manager


def test_vision_tuning_uses_non_strict_step(monkeypatch, tmp_path):
    os.environ["TIMMY_BETA_STRICT"] = "1"
    called: list[tuple[str, str | None, Path | None]] = []

    @contextmanager
    def fake_step(step_name, *, logger, slug, base_dir):
        called.append((step_name, slug, base_dir))
        yield

    monkeypatch.setattr(vision_tool, "non_strict_step", fake_step)
    workspace = tmp_path / "workspace"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    pdf_path = config_dir / "VisionStatement.pdf"
    pdf_path.write_text("PDF", encoding="utf-8")
    vision_yaml = config_dir / "vision.yaml"
    vision_yaml.write_text("sections: []\n", encoding="utf-8")

    class FakeContext:
        def __init__(self, repo_root_dir: Path):
            self.repo_root_dir = repo_root_dir
            self.client_name = "dummy"

    monkeypatch.setattr(
        vision_tool,
        "ClientContext",
        SimpleNamespace(load=lambda **kwargs: FakeContext(kwargs["repo_root_dir"])),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        vision_tool,
        "WorkspaceLayout",
        SimpleNamespace(
            from_context=lambda ctx: SimpleNamespace(config_path=config_dir / "config.yaml")
        ),  # type: ignore[assignment]
    )
    monkeypatch.setattr(vision_tool, "_resolve_pdf_path", lambda **kwargs: pdf_path)
    monkeypatch.setattr(vision_tool, "vision_yaml_workspace_path", lambda repo_root, pdf_path: vision_yaml)
    monkeypatch.setattr(vision_tool, "load_workspace_yaml", lambda slug: {})
    monkeypatch.setattr(vision_tool, "build_prompt_from_yaml", lambda data, slug, client_name: "prompt")
    monkeypatch.setattr(vision_tool, "get_vision_model", lambda: "model")
    monkeypatch.setattr(
        vision_tool,
        "provision_from_vision_with_config",
        lambda ctx, logger, slug, pdf_path, model, prepared_prompt: {"status": "ok", "mapping": "", "yaml_paths": {}},
    )

    ret = vision_tool.main(["--slug", "dummy", "--repo-root", str(workspace)])
    assert ret == 0
    assert called == [("vision_enrichment", "dummy", workspace)]
    assert os.environ["TIMMY_BETA_STRICT"] == "1"


def test_system_prompt_tool_uses_non_strict_step(monkeypatch):
    os.environ["TIMMY_BETA_STRICT"] = "1"
    called: list[str] = []

    @contextmanager
    def fake_step(step_name, *, logger, slug, base_dir=None):
        called.append(step_name)
        yield

    monkeypatch.setattr(prompt_tool, "non_strict_step", fake_step)
    monkeypatch.setattr(prompt_tool, "build_openai_client", lambda: object())
    monkeypatch.setattr(prompt_tool, "load_remote_system_prompt", lambda assistant_id, client: {})
    monkeypatch.setattr(prompt_tool, "resolve_assistant_id", lambda: "A")
    monkeypatch.setattr(prompt_tool, "save_remote_system_prompt", lambda assistant_id, instructions, client: None)

    ret = prompt_tool.main(["--slug", "dummy", "--mode", "get"])
    assert ret == 0
    assert called == ["prompt_tuning"]
    assert os.environ["TIMMY_BETA_STRICT"] == "1"


def test_pdf_to_yaml_tool_uses_non_strict_step(monkeypatch, tmp_path):
    os.environ["TIMMY_BETA_STRICT"] = "1"
    called: list[tuple[str, str | None, Path | None]] = []

    @contextmanager
    def fake_step(step_name, *, logger, slug, base_dir):
        called.append((step_name, slug, base_dir))
        yield

    monkeypatch.setattr(pdf_tool, "non_strict_step", fake_step)
    workspace = tmp_path / "workspace"
    config_dir = workspace / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    pdf_path = config_dir / "VisionStatement.pdf"
    pdf_path.write_text("PDF", encoding="utf-8")
    vision_yaml = config_dir / "vision.yaml"
    vision_yaml.write_text("sections: []\n", encoding="utf-8")

    class FakeContext:
        def __init__(self, repo_root_dir: Path):
            self.repo_root_dir = repo_root_dir

    monkeypatch.setattr(
        pdf_tool,
        "ClientContext",
        SimpleNamespace(
            load=lambda **kwargs: (
                FakeContext(
                    kwargs["slug"],
                )
                if False
                else FakeContext(workspace)
            )
        ),
    )  # noqa: E731
