from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml

from src.pre_onboarding import ensure_local_workspace_for_ui


def test_mirror_repo_config_preserves_client_overrides(monkeypatch, tmp_path: Path) -> None:
    slug = "acme"
    repo_root = tmp_path / "repo"
    template_dir = repo_root / "config"
    template_dir.mkdir(parents=True, exist_ok=True)

    template_config = template_dir / "config.yaml"
    template_config.write_text(
        "\n".join(
            [
                "client_name: TEMPLATE",
                "vision_statement_pdf: template/VisionStatement.pdf",
                "retriever:",
                "  top_k: 5",
            ]
        ),
        encoding="utf-8",
    )

    class _StreamlitStub:
        def __init__(self) -> None:
            self.session_state: dict[str, object] = {}

        def subheader(self, *args: object, **kwargs: object) -> None:
            return None

        def text_input(self, *args: object, **kwargs: object) -> str:
            return ""

        def file_uploader(self, *args: object, **kwargs: object):
            return None

        def button(self, *args: object, **kwargs: object) -> bool:
            return False

        def warning(self, *args: object, **kwargs: object) -> None:
            return None

        def stop(self) -> None:
            return None

        def error(self, *args: object, **kwargs: object) -> None:
            return None

        def status(self, *args: object, **kwargs: object):
            class _Status:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc_val, exc_tb) -> bool:
                    return False

                def update(self_inner, *inner_args: object, **inner_kwargs: object) -> None:
                    return None

            return _Status()

        def success(self, *args: object, **kwargs: object) -> None:
            return None

        def rerun(self) -> None:
            return None

        def progress(self, *args: object, **kwargs: object):
            class _Progress:
                def progress(self_inner, *inner_args: object, **inner_kwargs: object) -> None:
                    return None

            return _Progress()

        def empty(self, *args: object, **kwargs: object):
            class _Empty:
                def markdown(self_inner, *inner_args: object, **inner_kwargs: object) -> None:
                    return None

            return _Empty()

        def html(self, *args: object, **kwargs: object) -> None:
            return None

    monkeypatch.setitem(sys.modules, "streamlit", _StreamlitStub())

    import ui.chrome as chrome

    monkeypatch.setattr(chrome, "header", lambda *a, **k: None)
    monkeypatch.setattr(chrome, "sidebar", lambda *a, **k: None)

    new_client = importlib.import_module("src.ui.pages.new_client")
    monkeypatch.setattr(new_client, "_repo_root", lambda: repo_root)

    client_root = repo_root / "output" / f"timmy-kb-{slug}"
    monkeypatch.setenv("REPO_ROOT_DIR", str(client_root))

    cfg_path = client_root / "config" / "config.yaml"
    ensure_local_workspace_for_ui(slug, client_name="ACME", vision_statement_pdf=b"%PDF")
    pre_merge = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    new_client._mirror_repo_config_into_client(slug, pdf_bytes=b"%PDF")

    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    assert config["client_name"] == "ACME"
    assert config["vision_statement_pdf"] == "config/VisionStatement.pdf"
    assert "retriever" in config
    assert config["retriever"].get("top_k") == 5
    if isinstance(pre_merge.get("retriever"), dict):
        for key, value in pre_merge["retriever"].items():
            assert config["retriever"].get(key) == value
