# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def _setup_workspace(tmp_path: Path, *, create_pdf: bool = True) -> tuple[Path, Path, Path]:
    base = tmp_path / "output" / "timmy-kb-dummy"
    config_dir = base / "config"
    semantic_dir = base / "semantic"
    pdf = config_dir / "VisionStatement.pdf"
    yaml = config_dir / "visionstatement.yaml"
    mapping = semantic_dir / "semantic_mapping.yaml"
    config_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir.mkdir(parents=True, exist_ok=True)
    base.mkdir(parents=True, exist_ok=True)
    for child in ("raw", "book", "logs", "normalized"):
        (base / child).mkdir(parents=True, exist_ok=True)
    book_dir = base / "book"
    (book_dir / "README.md").write_text("# Dummy KB\n", encoding="utf-8")
    (book_dir / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")
    if create_pdf:
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    yaml.write_text(
        "client:" + "\n"
        "  slug: dummy\n"
        "  client_name: Dummy\n"
        "content:" + "\n"
        "  full_text: |\n"
        "    Vision focus text\n"
        "sections:\n"
        "  Vision: Dummy\n",
        encoding="utf-8",
    )
    mapping.write_text("context:\n  slug: dummy\n", encoding="utf-8")
    repo_config = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    target_cfg = config_dir / "config.yaml"
    if repo_config.exists():
        shutil.copy2(repo_config, target_cfg)
    else:
        target_cfg.write_text("ai:\n  vision:\n    model: test-model\n", encoding="utf-8")
    return base, yaml, mapping


def test_tuning_vision_provision_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from tools import tuning_vision_provision as tool

    base, _, mapping_path = _setup_workspace(tmp_path)

    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(base))
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "test-assistant")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _fake_provision(**kwargs: object) -> dict[str, str]:
        return {
            "mapping": str(mapping_path),
            "yaml_paths": {"mapping": str(mapping_path)},
        }

    monkeypatch.setattr(
        tool,
        "provision_from_vision_with_config",
        lambda *args, **kwargs: _fake_provision(**kwargs),
        raising=False,
    )

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(tool, "_dump", lambda payload: captured.append(payload))

    exit_code = tool.main(
        [
            "--repo-root",
            str(base),
            "--model",
            "test-model",
        ]
    )

    assert captured, "payload JSON mancante"
    payload = captured[-1]

    assert exit_code == 0, payload
    assert payload["status"] == "ok"
    assert payload["returncode"] == 0
    pdf_path = base / "config" / "VisionStatement.pdf"
    assert payload["paths"]["pdf"] == str(pdf_path)
    assert payload["paths"]["vision_yaml"].endswith("visionstatement.yaml")
    assert payload["paths"]["mapping"] == str(mapping_path)
    assert payload["artifacts"] == [str(mapping_path)]
    assert payload["timmy_beta_strict"] == "0"


def test_tuning_vision_provision_fails_without_pdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from tools import tuning_vision_provision as tool

    base, _, _ = _setup_workspace(tmp_path, create_pdf=False)

    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(base))
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "test-assistant")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(tool, "_dump", lambda payload: captured.append(payload))

    exit_code = tool.main(
        [
            "--repo-root",
            str(base),
            "--model",
            "test-model",
        ]
    )

    assert captured, "payload JSON mancante"
    payload = captured[-1]

    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["returncode"] == 1
    assert payload["paths"] == {}
    assert payload["errors"], "Errore atteso quando manca VisionStatement.pdf"
