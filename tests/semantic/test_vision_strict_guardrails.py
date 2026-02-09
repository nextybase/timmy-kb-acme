# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import semantic.vision_provision as vp
from ai.types import AssistantConfig
from pipeline.exceptions import ConfigError


class _Ctx:
    def __init__(self, repo_root_dir: Path):
        self.repo_root_dir = str(repo_root_dir)
        # non serve Settings completo: _prepare_payload lavora su repo_root_dir + slug + file.


def _write_dummy_pdf(path: Path) -> None:
    # basta un header minimale: non deve essere parsato perché passiamo prepared_prompt.
    path.write_bytes(b"%PDF-1.4\n%\n")


def test_prepare_payload_strict_blocks_use_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Guardrail deterministico: in strict, Vision NON può mai usare File Search.
    Questo deve fallire presto (prima di qualsiasi run), con code stabile.
    """
    slug = "strict-use-kb"
    pdf = tmp_path / "vision.pdf"
    _write_dummy_pdf(pdf)
    ctx = _Ctx(tmp_path)

    config = AssistantConfig(
        model="gpt-4o-mini",
        assistant_id="asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )

    monkeypatch.setattr(vp, "is_beta_strict", lambda: True, raising=False)
    monkeypatch.setattr(vp, "make_openai_client", lambda: object(), raising=False)

    with pytest.raises(ConfigError) as excinfo:
        vp._prepare_payload(
            ctx,
            slug,
            pdf,
            prepared_prompt="prompt",
            config=config,
            logger=logging.getLogger("test"),
            retention_days=0,
        )
    assert excinfo.value.code == "vision.strict.retrieval_forbidden"


def test_prepare_payload_sets_instructions_by_use_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Contratto: a parità di pipeline, cambia SOLO il set di instructions (use_kb True/False).
    Serve per garantire che Dummy/smoke test e pipeline normale condividano lo stesso flow,
    variando esclusivamente l'eccezione esplicita.
    """
    slug = "dummy-instructions"
    pdf = tmp_path / "vision.pdf"
    _write_dummy_pdf(pdf)
    ctx = _Ctx(tmp_path)

    monkeypatch.setattr(vp, "is_beta_strict", lambda: False, raising=False)
    monkeypatch.setattr(vp, "make_openai_client", lambda: object(), raising=False)

    cfg_true = AssistantConfig(
        model="gpt-4o-mini",
        assistant_id="asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=True,
        strict_output=True,
    )
    prepared_true = vp._prepare_payload(
        ctx,
        slug,
        pdf,
        prepared_prompt="prompt",
        config=cfg_true,
        logger=logging.getLogger("test"),
        retention_days=0,
    )
    assert prepared_true.use_kb is True
    assert "File Search" in prepared_true.run_instructions

    cfg_false = AssistantConfig(
        model="gpt-4o-mini",
        assistant_id="asst",
        assistant_env="OBNEXT_ASSISTANT_ID",
        use_kb=False,
        strict_output=True,
    )
    prepared_false = vp._prepare_payload(
        ctx,
        slug,
        pdf,
        prepared_prompt="prompt",
        config=cfg_false,
        logger=logging.getLogger("test"),
        retention_days=0,
    )
    assert prepared_false.use_kb is False
    assert "IGNORARE File Search" in prepared_false.run_instructions
