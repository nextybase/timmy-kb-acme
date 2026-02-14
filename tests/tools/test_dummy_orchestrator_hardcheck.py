# SPDX-License-Identifier: GPL-3.0-or-later
# cspell:ignore defaul
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

import pytest

from pipeline.context import ClientContext
from pipeline.file_utils import safe_write_text
from pipeline.workspace_bootstrap import bootstrap_client_workspace
from tests._helpers.workspace_paths import local_workspace_dir
from tools.dummy import orchestrator
from tools.dummy.orchestrator import validate_dummy_structure
from tools.dummy.policy import DummyPolicy


@pytest.fixture
def logger() -> logging.Logger:
    log = logging.getLogger("test.dummy.hardcheck")
    log.addHandler(logging.NullHandler())
    log.setLevel(logging.INFO)
    return log


def _workspace_env_setter(base_dir: Path) -> Callable[..., None]:
    def _setter(*, slug: str, client_name: str, vision_statement_pdf: bytes | None) -> None:
        os.environ["WORKSPACE_ROOT_DIR"] = str(base_dir)

    return _setter


def _write_required_dummy_files(workspace_root: Path) -> None:
    (workspace_root / "config").mkdir(parents=True, exist_ok=True)
    (workspace_root / "semantic").mkdir(parents=True, exist_ok=True)
    (workspace_root / "book").mkdir(parents=True, exist_ok=True)
    (workspace_root / "raw").mkdir(parents=True, exist_ok=True)

    (workspace_root / "config" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (workspace_root / "semantic" / "semantic_mapping.yaml").write_text("context: {}\n", encoding="utf-8")
    (workspace_root / "semantic" / "tags.db").write_bytes(b"")
    (workspace_root / "book" / "README.md").write_text("# Dummy\n", encoding="utf-8")
    (workspace_root / "book" / "SUMMARY.md").write_text("* [Dummy](README.md)\n", encoding="utf-8")
    (workspace_root / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    normalized_dir = workspace_root / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    (normalized_dir / "INDEX.json").write_text("{}", encoding="utf-8")


def test_dummy_validate_structure_passes_when_mapping_present(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    workspace_root = local_workspace_dir(repo_root / "output", slug)
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        config_path=workspace_root / "config" / "config.yaml",
    )
    layout = bootstrap_client_workspace(context)

    _write_required_dummy_files(layout.repo_root_dir)

    validate_dummy_structure(layout.repo_root_dir, logger)


def test_dummy_validate_structure_fails_when_mapping_missing(tmp_path: Path, logger: logging.Logger) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-hc"
    workspace_root = local_workspace_dir(repo_root / "output", slug)
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        config_path=workspace_root / "config" / "config.yaml",
    )
    layout = bootstrap_client_workspace(context)

    _write_required_dummy_files(layout.repo_root_dir)
    (layout.semantic_dir / "semantic_mapping.yaml").unlink()

    with pytest.raises(RuntimeError) as exc:
        validate_dummy_structure(layout.repo_root_dir, logger)
    assert "semantic_mapping" in str(exc.value)


def test_register_client_requires_registry() -> None:
    policy = DummyPolicy(mode="smoke", strict=True, ci=False, allow_downgrade=False, require_registry=True)
    with pytest.raises(orchestrator.HardCheckError) as exc:
        orchestrator.register_client("dummy", "Dummy SaaS", ClientEntry=None, upsert_client=None, policy=policy)
    assert exc.value.health["stop_code"] == "DUMMY_REGISTRY_IMPORT_MISSING"


def test_register_client_reports_upsert_failure(tmp_path: Path) -> None:
    policy = DummyPolicy(mode="smoke", strict=True, ci=False, allow_downgrade=False, require_registry=True)

    class ClientEntry:
        def __init__(self, **kwargs: Any) -> None:
            self.slug = kwargs.get("slug")

    def failing_upsert(_: Any) -> None:
        raise RuntimeError("boom")

    with pytest.raises(orchestrator.HardCheckError) as exc:
        orchestrator.register_client(
            "dummy",
            "Dummy SaaS",
            ClientEntry=ClientEntry,
            upsert_client=failing_upsert,
            policy=policy,
        )
    assert exc.value.health["stop_code"] == "DUMMY_REGISTRY_UPSERT_FAILED"


def test_deep_compiles_yaml_before_vision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    slug = "dummy"
    base_dir = local_workspace_dir(tmp_path, slug)
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    (base_dir / "raw").mkdir(parents=True, exist_ok=True)

    order: list[str] = []

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        order.append("compile")
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        order.append("run_vision")
        assert (base_dir / "config" / "visionstatement.yaml").exists()
        return True, None

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)

    payload = orchestrator.build_dummy_payload(
        slug="dummy",
        client_name="Dummy",
        enable_drive=False,
        enable_vision=True,
        enable_semantic=False,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logger,
        repo_root=repo_root,
        ensure_local_workspace_for_ui=_workspace_env_setter(base_dir),
        run_vision=lambda **_: None,
        get_env_var=_get_env_var,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: base_dir,
        pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_args, **_kwargs: None,
        ClientContext=orchestrator.PipelineClientContext,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
        load_mapping_categories_fn=lambda _: {"contracts": {"ambito": "Contracts", "descrizione": "", "keywords": []}},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        ensure_spacy_available_fn=lambda policy: None,
        call_drive_min_fn=lambda *_args, **_kwargs: None,
        call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
    )

    assert payload["vision_used"] is True
    assert order == ["compile", "run_vision"]


def test_deep_testing_downgrades_vision_on_quota_and_still_runs_drive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    slug = "dummy"
    base_dir = local_workspace_dir(tmp_path, slug)
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        return False, {
            "error": "Error code: 429 insufficient_quota - check your plan and billing",
            "file_path": "",
        }

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    drive_calls = {"min": 0, "readmes": 0}

    def _call_drive_min_fn(*_args: object, **_kwargs: object) -> dict[str, Any]:
        drive_calls["min"] += 1
        return {"ok": True}

    def _call_drive_emit_readmes_fn(*_args: object, **_kwargs: object) -> dict[str, Any]:
        drive_calls["readmes"] += 1
        return {"ok": True}

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)
    monkeypatch.setattr(orchestrator, "run_raw_ingest", lambda **_: None)
    policy = DummyPolicy(mode="deep", strict=True, ci=False, allow_downgrade=True, require_registry=True)

    with pytest.raises(orchestrator.HardCheckError) as excinfo:
        orchestrator.build_dummy_payload(
            slug="dummy",
            client_name="Dummy",
            enable_drive=True,
            enable_vision=True,
            enable_semantic=False,
            enable_enrichment=False,
            enable_preview=False,
            records_hint=None,
            deep_testing=True,
            logger=logger,
            repo_root=repo_root,
            ensure_local_workspace_for_ui=_workspace_env_setter(base_dir),
            run_vision=lambda **_: None,
            get_env_var=_get_env_var,
            ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
            open_for_read_bytes_selfguard=lambda path: path.open("rb"),
            load_vision_template_sections=lambda: [],
            client_base=lambda _: base_dir,
            pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
            register_client_fn=lambda *_args, **_kwargs: None,
            ClientContext=None,
            get_client_config=None,
            ensure_drive_minimal_and_upload_config=None,
            emit_readmes_for_raw=None,
            run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
            load_mapping_categories_fn=lambda _: {},
            ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
            ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
            ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
            ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
            write_basic_semantic_yaml_fn=lambda *_args, **_kwargs: {"categories": {"contracts": {}}},
            write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
            validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
            ensure_spacy_available_fn=lambda policy: None,
            call_drive_min_fn=_call_drive_min_fn,
            call_drive_emit_readmes_fn=_call_drive_emit_readmes_fn,
            policy=policy,
        )

    assert "insufficient_quota" in str(excinfo.value).lower()
    assert drive_calls == {"min": 1, "readmes": 0}


def test_deep_testing_vision_quota_without_downgrade_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    policy = DummyPolicy(mode="deep", strict=True, ci=False, allow_downgrade=False, require_registry=True)

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        return False, {
            "error": "Error code: 429 insufficient_quota - check your plan and billing",
            "file_path": "",
        }

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", lambda *_: None)

    with pytest.raises(orchestrator.HardCheckError) as exc:
        orchestrator.build_dummy_payload(
            slug="dummy",
            client_name="Dummy",
            enable_drive=False,
            enable_vision=True,
            enable_semantic=False,
            enable_enrichment=False,
            enable_preview=False,
            records_hint=None,
            deep_testing=True,
            logger=logger,
            repo_root=repo_root,
            ensure_local_workspace_for_ui=lambda **_: None,
            run_vision=lambda **_: None,
            get_env_var=_get_env_var,
            ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
            open_for_read_bytes_selfguard=lambda path: path.open("rb"),
            load_vision_template_sections=lambda: [],
            client_base=lambda _: base_dir,
            pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
            register_client_fn=lambda *_args, **_kwargs: None,
            ClientContext=None,
            get_client_config=None,
            ensure_drive_minimal_and_upload_config=None,
            emit_readmes_for_raw=None,
            run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
            load_mapping_categories_fn=lambda _: {},
            ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
            ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
            ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
            ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
            write_basic_semantic_yaml_fn=None,
            write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
            validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
            ensure_spacy_available_fn=lambda policy: None,
            call_drive_min_fn=lambda *_args, **_kwargs: None,
            call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
            policy=policy,
        )
    assert exc.value.health["stop_code"] == "DUMMY_VISION_UNAVAILABLE"


def test_deep_testing_non_quota_vision_failure_still_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    logger: logging.Logger,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    base_dir = tmp_path / "workspace"
    (base_dir / "config").mkdir(parents=True, exist_ok=True)
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-TEST")

    def _compile(_pdf_path: Path, yaml_target: Path) -> None:
        yaml_target.write_text("version: 1\n", encoding="utf-8")

    def _run_vision_with_timeout_fn(**_: object) -> tuple[bool, dict[str, object] | None]:
        return False, {"error": "permission denied", "file_path": ""}

    def _get_env_var(name: str, default: str | None = None) -> str | None:
        if name == "VISION_MODE":
            return "DEEP"
        return default

    monkeypatch.setattr(orchestrator, "compile_document_to_vision_yaml", _compile)

    with pytest.raises(orchestrator.HardCheckError):
        orchestrator.build_dummy_payload(
            slug="dummy",
            client_name="Dummy",
            enable_drive=True,
            enable_vision=True,
            enable_semantic=False,
            enable_enrichment=False,
            enable_preview=False,
            records_hint=None,
            deep_testing=True,
            logger=logger,
            repo_root=repo_root,
            ensure_local_workspace_for_ui=lambda **_: None,
            run_vision=lambda **_: None,
            get_env_var=_get_env_var,
            ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
            open_for_read_bytes_selfguard=lambda path: path.open("rb"),
            load_vision_template_sections=lambda: [],
            client_base=lambda _: base_dir,
            pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
            register_client_fn=lambda *_args, **_kwargs: None,
            ClientContext=None,
            get_client_config=None,
            ensure_drive_minimal_and_upload_config=None,
            emit_readmes_for_raw=None,
            run_vision_with_timeout_fn=_run_vision_with_timeout_fn,
            load_mapping_categories_fn=lambda _: {},
            ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
            ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
            ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
            ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
            write_basic_semantic_yaml_fn=None,
            write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
            validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
            call_drive_min_fn=lambda *_args, **_kwargs: None,
            call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
        )


def test_dummy_pipeline_outputs_normalized_index_and_book_assets(
    tmp_path: Path,
    logger: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    slug = "dummy-pipeline"
    workspace_root = local_workspace_dir(repo_root / "output", slug)
    context = ClientContext(
        slug=slug,
        repo_root_dir=workspace_root,
        config_path=workspace_root / "config" / "config.yaml",
    )
    layout = bootstrap_client_workspace(context)

    base_dir = layout.repo_root_dir
    (base_dir / "config" / "VisionStatement.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    vision_yaml_path = orchestrator.vision_yaml_workspace_path(
        base_dir, pdf_path=base_dir / "config" / "VisionStatement.pdf"
    )
    vision_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    vision_yaml_path.write_text("sections: []\n", encoding="utf-8")
    safe_write_text(
        base_dir / "config" / "config.yaml",
        "meta:\n  client_name: Dummy Pipeline\n",
        encoding="utf-8",
        atomic=True,
    )
    safe_write_text(
        base_dir / "semantic" / "semantic_mapping.yaml",
        "default:\n  - dummy\n",
        encoding="utf-8",
        atomic=True,
    )
    (base_dir / "semantic" / "tags.db").write_bytes(b"")
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    (base_dir / "raw" / "sample.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr(
        orchestrator,
        "run_raw_ingest",
        lambda **_: safe_write_text(
            base_dir / "normalized" / "dummy.md",
            "# dummy\n",
            encoding="utf-8",
            atomic=True,
        )
        or safe_write_text(
            base_dir / "book" / "dummy.md",
            "# dummy book page\n",
            encoding="utf-8",
            atomic=True,
        ),
    )
    monkeypatch.setattr(orchestrator, "semantic_convert_markdown", lambda *_, **__: None)
    monkeypatch.setattr(orchestrator, "semantic_write_summary_and_readme", lambda *_, **__: None)

    class _DummyCtx:
        @staticmethod
        def load(**__: Any) -> Any:
            class _Ctx:
                def __init__(self) -> None:
                    self.logs_dir = layout.logs_dir

                def with_run_id(self, run_id: str) -> "_Ctx":
                    return self

                def with_stage(self, stage: str) -> "_Ctx":
                    return self

            return _Ctx()

    monkeypatch.setattr(orchestrator, "PipelineClientContext", _DummyCtx)
    monkeypatch.setattr(
        orchestrator,
        "WorkspaceLayout",
        type(
            "DummyWL",
            (),
            {
                "from_context": staticmethod(lambda _ctx: layout),
                "from_workspace": staticmethod(lambda workspace, slug: layout),
            },
        ),
    )

    def _vision_stub(**_: Any) -> tuple[bool, None]:
        return True, None

    payload = orchestrator.build_dummy_payload(
        slug=slug,
        client_name="Pipeline Dummy",
        enable_drive=False,
        enable_vision=True,
        enable_semantic=True,
        enable_enrichment=False,
        enable_preview=False,
        records_hint=None,
        deep_testing=False,
        logger=logger,
        repo_root=repo_root,
        ensure_local_workspace_for_ui=_workspace_env_setter(base_dir),
        run_vision=lambda **_: None,
        get_env_var=lambda *_: None,
        ensure_within_and_resolve_fn=orchestrator.ensure_within_and_resolve,
        open_for_read_bytes_selfguard=lambda path: path.open("rb"),
        load_vision_template_sections=lambda: [],
        client_base=lambda _: base_dir,
        pdf_path=lambda _: base_dir / "config" / "VisionStatement.pdf",
        register_client_fn=lambda *_args, **_kwargs: None,
        ClientContext=orchestrator.PipelineClientContext,
        get_client_config=None,
        ensure_drive_minimal_and_upload_config=None,
        emit_readmes_for_raw=None,
        run_vision_with_timeout_fn=_vision_stub,
        load_mapping_categories_fn=lambda _: {},
        ensure_minimal_tags_db_fn=lambda *_args, **_kwargs: None,
        ensure_raw_pdfs_fn=lambda *_args, **_kwargs: None,
        ensure_local_readmes_fn=lambda *_args, **_kwargs: [],
        ensure_book_skeleton_fn=lambda *_args, **_kwargs: None,
        write_basic_semantic_yaml_fn=None,
        write_minimal_tags_raw_fn=lambda *_args, **_kwargs: base_dir / "semantic" / "tags_raw.json",
        validate_dummy_structure_fn=lambda *_args, **_kwargs: None,
        ensure_spacy_available_fn=lambda policy: None,
        call_drive_min_fn=lambda *_args, **_kwargs: None,
        call_drive_emit_readmes_fn=lambda *_args, **_kwargs: None,
    )

    normalized_index = layout.normalized_dir / "INDEX.json"
    normalized_md_files = [p for p in layout.normalized_dir.rglob("*.md") if p.is_file()]
    qa_passed = layout.logs_dir / "qa_passed.json"
    summary_path = layout.book_dir / "SUMMARY.md"
    readme_path = layout.book_dir / "README.md"
    book_pages = [
        p for p in layout.book_dir.iterdir() if p.suffix.lower() == ".md" and p.name not in {"README.md", "SUMMARY.md"}
    ]

    assert payload["health"]["status"] == "ok"
    assert normalized_index.exists()
    assert summary_path.exists()
    assert readme_path.exists()
    assert book_pages, "Almeno un file diverso da README/SUMMARY deve esistere in book/"
    assert normalized_md_files, "La pipeline deve produrre almeno un file Markdown in normalized/"
    assert qa_passed.exists(), "Il gate QA deve produrre logs/qa_passed.json"
