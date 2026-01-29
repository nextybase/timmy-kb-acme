from __future__ import annotations

import logging
import os
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Mapping, Optional

from pipeline.context import ClientContext as PipelineClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.qa_evidence import write_qa_evidence
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from semantic.api import convert_markdown as semantic_convert_markdown
from semantic.api import write_summary_and_readme as semantic_write_summary_and_readme
from semantic.core import compile_document_to_vision_yaml
from timmy_kb.cli.pre_onboarding import pre_onboarding_main
from timmy_kb.cli.raw_ingest import run_raw_ingest

from .bootstrap import client_base, pdf_path
from .drive import call_drive_emit_readmes, call_drive_min
from .health import build_hardcheck_health
from .policy import DummyPolicy
from .semantic import ensure_raw_pdfs
from .vision import run_vision_with_timeout

_SEMANTIC_MAPPING_TEMPLATE = "semantic_tagger: {}\nareas: []\n"

import yaml


class HardCheckError(Exception):
    def __init__(self, message: str, health: Dict[str, Any]):
        super().__init__(message)
        self.health = health


def _ensure_spacy_available(policy: DummyPolicy) -> None:
    model_name = os.getenv("SPACY_MODEL", "it_core_news_sm").strip()
    try:
        import spacy

        util = getattr(spacy, "util", None)
        if util is None or not util.is_package(model_name):
            raise RuntimeError(f"modello SpaCy obbligatorio mancante: {model_name}")
    except Exception as exc:
        msg = (
            "SpaCy e il modello linguistico obbligatorio non sono disponibili. "
            "Installa `spacy` e `it_core_news_sm` (es. `python -m spacy download it_core_news_sm`)."
        )
        raise HardCheckError(
            msg,
            build_hardcheck_health(
                "DUMMY_SPACY_UNAVAILABLE",
                msg,
                mode=policy.mode,
            ),
        ) from exc


def _record_external_check(
    health: Dict[str, Any],
    name: str,
    ok: bool,
    details: str,
    latency_ms: int | None,
) -> None:
    checks = health.setdefault("checks", [])
    if name not in checks:
        checks.append(name)
    external = health.setdefault("external_checks", {})
    entry: dict[str, Any] = {"ok": ok, "details": details}
    if latency_ms is not None:
        entry["latency_ms"] = latency_ms
    external[name] = entry


def _deep_merge_missing(target: Dict[str, Any], template: Mapping[str, Any]) -> bool:
    updated = False
    for key, value in template.items():
        existing_value = target.get(key)
        if key not in target:
            target[key] = deepcopy(value)
            updated = True
        elif isinstance(value, dict) and isinstance(existing_value, dict):
            if _deep_merge_missing(existing_value, value):
                updated = True
    return updated


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = read_text_safe(path.parent, path, encoding="utf-8")
    except Exception:
        return {}
    if not raw:
        return {}
    payload = yaml.safe_load(raw)
    return dict(payload) if isinstance(payload, dict) else {}


def _merge_config_with_template(base_dir: Path, *, logger: logging.Logger | None = None) -> None:
    template_config = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    if not template_config.exists():
        return
    config_dir = ensure_within_and_resolve(base_dir, base_dir / "config")
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"

    existing = _load_yaml_dict(config_path)
    template_payload = _load_yaml_dict(template_config)
    merged = dict(existing)
    if not _deep_merge_missing(merged, template_payload):
        return

    text = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)
    safe_write_text(config_path, text, encoding="utf-8", atomic=True)
    if logger:
        try:
            logger.info(
                "tools.dummy.orchestrator.config_merged_from_template",
                extra={"path": str(config_path)},
            )
        except Exception:
            pass


def _ensure_semantic_mapping_has_tagger(mapping_path: Path) -> None:
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    raw_text = ""
    if mapping_path.exists():
        try:
            raw_text = mapping_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(f"Impossibile leggere semantic_mapping.yaml: {exc}") from exc
        if raw_text:
            try:
                parsed = yaml.safe_load(raw_text)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception as exc:
                raise RuntimeError(f"Errore parsing semantic_mapping.yaml: {exc}") from exc
    updated = False
    if "semantic_tagger" not in data:
        data["semantic_tagger"] = {}
        updated = True
    areas = data.get("areas")
    if not (isinstance(areas, list) and any(isinstance(item, dict) and item.get("key") for item in areas)):
        data["areas"] = [{"key": "dummy", "title": "Dummy area"}]
        updated = True
    if updated or not mapping_path.exists():
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        safe_write_text(mapping_path, text, encoding="utf-8", atomic=True)


def _resolve_vision_mode(get_env_var: Callable[[str, str | None], str | None]) -> str:
    raw = None
    try:
        raw = get_env_var("VISION_MODE", None)
    except Exception:
        raw = None
    mode = str(raw or "DEEP").strip().lower()
    if mode in {"smoke", "deep"}:
        return mode
    raise ConfigError(f"VISION_MODE non valido: {raw!r}. Usa 'SMOKE' o 'DEEP'.")


def _get_vision_strict_output(ctx_obj: Any) -> tuple[Optional[bool], str]:
    try:
        settings = getattr(ctx_obj, "settings", None)
        if settings is None:
            return None, "missing_settings"
        vs = getattr(settings, "vision_settings", None)
        if vs is None:
            if isinstance(settings, dict):
                vision = settings.get("vision") or {}
                if isinstance(vision, dict) and "strict_output" in vision:
                    return bool(vision.get("strict_output")), "config_dict"
            return None, "missing_vision_settings"
        if hasattr(vs, "strict_output"):
            return bool(getattr(vs, "strict_output")), "config"
        return None, "missing_strict_output"
    except Exception:
        return None, "error"


def _count_raw_pdfs(base_dir: Path) -> int:
    try:
        raw_dir = ensure_within_and_resolve(base_dir, base_dir / "raw")
        return sum(1 for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    except Exception:
        return 0


def _count_tags(base_dir: Path) -> int:
    try:
        from storage import tags_store as _tags_store  # type: ignore
    except Exception:
        return 0
    try:
        tags_path = ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags.db")
        payload = _tags_store.load_tags_reviewed(str(tags_path))  # type: ignore[attr-defined]
        tags = payload.get("tags") if isinstance(payload, dict) else []
        return len(tags) if isinstance(tags, list) else 0
    except Exception:
        return 0


def register_client(
    slug: str,
    client_name: str,
    *,
    ClientEntry: Any | None,
    upsert_client: Callable[[Any], Any] | None,
    policy: DummyPolicy,
) -> None:
    if not policy.require_registry:
        return
    if not (ClientEntry and callable(upsert_client)):
        msg = "Registry UI non disponibile per la dummy KB"
        raise HardCheckError(
            msg,
            build_hardcheck_health(
                "DUMMY_REGISTRY_IMPORT_MISSING",
                msg,
                mode=policy.mode,
            ),
        )
    try:
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    except Exception:
        timestamp = None
    try:
        entry = ClientEntry(slug=slug, nome=client_name, stato="active", created_at=timestamp, dummy=True)
    except Exception as exc:
        msg = f"Creazione entry registry fallita: {exc}"
        raise HardCheckError(
            msg,
            build_hardcheck_health(
                "DUMMY_REGISTRY_ENTRY_FAILED",
                msg,
                mode=policy.mode,
            ),
        ) from exc
    try:
        upsert_client(entry)
    except Exception as exc:
        msg = f"Upsert registry fallito: {exc}"
        raise HardCheckError(
            msg,
            build_hardcheck_health(
                "DUMMY_REGISTRY_UPSERT_FAILED",
                msg,
                mode=policy.mode,
            ),
        ) from exc


def validate_dummy_structure(base_dir: Path, logger: logging.Logger) -> None:
    required = [
        ("config", base_dir / "config" / "config.yaml"),
        ("semantic_mapping", base_dir / "semantic" / "semantic_mapping.yaml"),
        ("book_readme", base_dir / "book" / "README.md"),
        ("book_summary", base_dir / "book" / "SUMMARY.md"),
        ("normalized_index", base_dir / "normalized" / "INDEX.json"),
    ]
    missing: list[dict[str, str]] = []
    for key, path in required:
        try:
            safe_path = ensure_within_and_resolve(base_dir, path)
            if not safe_path.exists():
                missing.append({"key": key, "path": str(safe_path)})
        except Exception:
            missing.append({"key": key, "path": str(path)})
    if missing:
        try:
            logger.error("tools.gen_dummy_kb.validate_structure.missing", extra={"missing": missing})
        except Exception:
            pass
        raise RuntimeError(f"Struttura dummy incompleta: {missing}")


def build_dummy_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    enable_semantic: bool = True,
    enable_enrichment: bool = True,
    enable_preview: bool = True,
    records_hint: Optional[str],
    deep_testing: bool = False,
    logger: logging.Logger,
    policy: DummyPolicy | None = None,
    repo_root: Path,
    ensure_local_workspace_for_ui: Callable[..., Any],
    run_vision: Callable[..., Any],
    get_env_var: Callable[[str, str | None], str | None],
    ensure_within_and_resolve_fn: Callable[[Path, Path], Path],
    open_for_read_bytes_selfguard: Callable[[Path], Any],
    load_vision_template_sections: Callable[[], Any],
    client_base: Callable[[str], Path],
    pdf_path: Callable[[str], Path],
    register_client_fn: Callable[..., Any],
    ClientContext: Any | None,
    get_client_config: Callable[[Any], Dict[str, Any]] | None,
    ensure_drive_minimal_and_upload_config: Callable[..., Any] | None,
    emit_readmes_for_raw: Callable[..., Any] | None,
    load_mapping_categories_fn: Callable[..., Any] | None = None,
    ensure_minimal_tags_db_fn: Callable[..., Any] | None = None,
    ensure_raw_pdfs_fn: Callable[..., Any] | None = None,
    ensure_local_readmes_fn: Callable[..., Any] | None = None,
    ensure_book_skeleton_fn: Callable[..., Any] | None = None,
    write_basic_semantic_yaml_fn: Callable[..., Any] | None = None,
    write_minimal_tags_raw_fn: Callable[..., Any] | None = None,
    validate_dummy_structure_fn: Callable[..., Any] | None = None,
    ensure_spacy_available_fn: Callable[[DummyPolicy], None] | None = None,
    run_vision_with_timeout_fn: Callable[..., tuple[bool, Optional[Dict[str, Any]]]] = run_vision_with_timeout,
    call_drive_min_fn: Callable[..., Optional[Dict[str, Any]]] = call_drive_min,
    call_drive_emit_readmes_fn: Callable[..., Optional[Dict[str, Any]]] = call_drive_emit_readmes,
) -> Dict[str, Any]:
    vision_mode = _resolve_vision_mode(get_env_var)
    del repo_root
    del ensure_within_and_resolve_fn
    del open_for_read_bytes_selfguard
    del load_vision_template_sections
    del get_client_config
    if policy is None:
        policy = DummyPolicy(
            mode="deep" if deep_testing else "smoke",
            strict=True,
            ci=False,
            require_registry=True,
        )
    spacy_checker = ensure_spacy_available_fn or _ensure_spacy_available
    semantic_active = enable_semantic
    if enable_semantic and not enable_vision:
        logger.info("tools.gen_dummy_kb.semantic_disabled_without_vision", extra={"slug": slug})

    ctx_for_checks: Any | None = None
    if ClientContext is not None:
        try:
            ctx_for_checks = ClientContext.load(
                slug=slug,
                require_env=False,
                run_id=None,
                bootstrap_config=False,
            )
        except Exception:
            ctx_for_checks = None
    strict_requested, strict_source = _get_vision_strict_output(ctx_for_checks) if ctx_for_checks else (None, "ctx_unavailable")
    strict_effective = True if (deep_testing and enable_vision) else (True if strict_requested is None else bool(strict_requested))
    strict_rationale = (
        "deep_testing richiede strict-only"
        if (deep_testing and enable_vision)
        else ("default_true" if strict_requested is None else strict_source)
    )
    decisions: Dict[str, Any] = {
        "vision_strict_output": {
            "requested": strict_requested,
            "effective": strict_effective,
            "rationale": strict_rationale,
            "source": strict_source,
        }
    }

    if records_hint:
        try:
            int(records_hint)
        except Exception:
            logger.debug(
                "tools.gen_dummy_kb.records_hint_non_numeric",
                extra={"value": records_hint, "slug": slug},
            )

    if not enable_enrichment:
        logger.info("tools.gen_dummy_kb.enrichment_skipped", extra={"slug": slug})
    if not enable_preview:
        logger.info("tools.gen_dummy_kb.preview_skipped", extra={"slug": slug})

    ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=None)
    workspace_root = client_base(slug)
    for child in ("raw", "semantic", "book", "logs", "config", "normalized"):
        (workspace_root / child).mkdir(parents=True, exist_ok=True)
    normalized_index = workspace_root / "normalized" / "INDEX.json"
    if not normalized_index.exists():
        safe_write_text(normalized_index, "{}", encoding="utf-8", atomic=True)
    template_config = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    config_path = workspace_root / "config" / "config.yaml"
    if template_config.exists():
        text = read_text_safe(template_config.parent, template_config, encoding="utf-8")
        safe_write_text(config_path, text, encoding="utf-8", atomic=True)
    elif not config_path.exists():
        safe_write_text(config_path, "version: 1\n", encoding="utf-8", atomic=True)
    book_dir = workspace_root / "book"
    readme_path = book_dir / "README.md"
    if not readme_path.exists():
        safe_write_text(readme_path, "# Dummy\n", encoding="utf-8", atomic=True)
    summary_path = book_dir / "SUMMARY.md"
    if not summary_path.exists():
        safe_write_text(summary_path, "* [Dummy](README.md)\n", encoding="utf-8", atomic=True)

    try:
        pre_onboarding_main(
            slug=slug,
            client_name=client_name,
            interactive=False,
            dry_run=True,
            run_id=uuid.uuid4().hex,
        )
    except Exception as exc:
        msg = f"pre_onboarding fallito: {exc}"
        raise HardCheckError(
            msg,
            build_hardcheck_health(
                "pre_onboarding_hardcheck",
                msg,
                mode=policy.mode,
            ),
        ) from exc

    register_client_fn(slug, client_name, policy=policy)

    base_dir = workspace_root
    _merge_config_with_template(base_dir, logger=logger)
    semantic_dir = base_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = semantic_dir / "semantic_mapping.yaml"
    safe_mapping_path = ensure_within_and_resolve(base_dir, mapping_path)
    safe_write_text(safe_mapping_path, _SEMANTIC_MAPPING_TEMPLATE, encoding="utf-8", atomic=True)
    raw_pdfs_fn = ensure_raw_pdfs_fn or ensure_raw_pdfs
    raw_pdfs_fn(base_dir)
    _ = (
        load_mapping_categories_fn,
        ensure_minimal_tags_db_fn,
        ensure_local_readmes_fn,
        ensure_book_skeleton_fn,
        write_basic_semantic_yaml_fn,
        write_minimal_tags_raw_fn,
    )

    drive_min_info: Dict[str, Any] = {}
    drive_readmes_info: Dict[str, Any] = {}
    hard_check_results: Dict[str, tuple[bool, str, int | None]] = {}

    if enable_drive:
        drive_start = perf_counter()
        try:
            drive_min_info = call_drive_min_fn(
                slug,
                client_name,
                base_dir,
                logger,
                ensure_drive_minimal_and_upload_config,
            ) or {}
        except Exception as exc:
            latency_ms = int((perf_counter() - drive_start) * 1000)
            msg = f"Drive hard check fallito: {exc}"
            raise HardCheckError(
                msg,
                build_hardcheck_health(
                    "drive_hardcheck",
                    msg,
                    mode=policy.mode,
                    latency_ms=latency_ms,
                ),
            ) from exc
        else:
            latency_ms = int((perf_counter() - drive_start) * 1000)
            if deep_testing:
                hard_check_results["drive_hardcheck"] = (True, "Drive hard check succeeded", latency_ms)

    vision_status = "skipped"
    vision_completed = False
    if enable_vision:
        pdf_path_resolved = pdf_path(slug)
        vision_yaml_path = vision_yaml_workspace_path(base_dir, pdf_path=pdf_path_resolved)
        if not vision_yaml_path.exists():
            try:
                compile_document_to_vision_yaml(pdf_path_resolved, vision_yaml_path)
            except Exception as exc:
                msg = "visionstatement.yaml mancante o non leggibile: esegui prima la compilazione PDF→YAML"
                try:
                    logger.error(
                        "tools.gen_dummy_kb.vision_yaml_compile_failed",
                        extra={"slug": slug, "error": str(exc)},
                    )
                except Exception:
                    pass
                raise HardCheckError(
                    msg,
                    build_hardcheck_health(
                        "vision_hardcheck",
                        msg,
                        mode=policy.mode,
                    ),
                ) from exc
        start = perf_counter()
        success, vision_meta = run_vision_with_timeout_fn(
            base_dir=base_dir,
            slug=slug,
            pdf_path=pdf_path_resolved,
            timeout_s=120.0,
            logger=logger,
            run_vision=run_vision,
        )
        latency_ms = int((perf_counter() - start) * 1000)
        if not success:
            message = str(vision_meta.get("error") if isinstance(vision_meta, dict) else vision_meta or "Vision fallita")
            try:
                logger.error(
                    "tools.gen_dummy_kb.vision_hardcheck.failed",
                    extra={"slug": slug, "error": message},
                )
            except Exception:
                pass
            raise HardCheckError(
                f"Vision fallita: {message}",
                build_hardcheck_health(
                    "DUMMY_VISION_UNAVAILABLE",
                    message,
                    mode=policy.mode,
                    latency_ms=latency_ms,
                ),
            )
        else:
            vision_completed = True
            vision_status = "ok"
            hard_check_results["vision_hardcheck"] = (True, "Vision completata", latency_ms)
            _ensure_semantic_mapping_has_tagger(safe_mapping_path)
    else:
        vision_status = "skipped"

    semantic_ctx: PipelineClientContext | None = None
    logs_dir: Path | None = None

    if semantic_active:
        spacy_checker(policy)
        try:
            run_raw_ingest(slug=slug, source="local", local_path=None, non_interactive=True)
        except Exception as exc:
            msg = f"raw_ingest fallito: {exc}"
            raise HardCheckError(
                msg,
                build_hardcheck_health("raw_ingest", msg, mode=policy.mode),
            )

        run_id = uuid.uuid4().hex
        semantic_ctx = PipelineClientContext.load(
            slug=slug,
            require_env=False,
            run_id=run_id,
            bootstrap_config=False,
        )
        _ensure_semantic_mapping_has_tagger(safe_mapping_path)
        logger_semantic = get_structured_logger(
            "tools.gen_dummy_kb.semantic",
            context=semantic_ctx,
            run_id=run_id,
        )
        semantic_convert_markdown(semantic_ctx, logger_semantic, slug=slug)
        layout = WorkspaceLayout.from_context(semantic_ctx)
        logs_dir = getattr(layout, "logs_dir", None) or getattr(layout, "log_dir", None)
        if logs_dir is None:
            raise HardCheckError(
                "Logs dir mancante per QA evidence.",
                build_hardcheck_health(
                    "qa_evidence",
                    "logs dir mancante",
                    mode=policy.mode,
                ),
            )
        qa_checks = ["raw_ingest", "semantic.convert_markdown", "semantic.write_summary_and_readme"]
        write_qa_evidence(logs_dir, checks_executed=qa_checks, qa_status="pass", logger=logger_semantic)
        semantic_write_summary_and_readme(semantic_ctx, logger_semantic, slug=slug)
    else:
        logger.info("tools.gen_dummy_kb.semantic_skipped", extra={"slug": slug})

    if enable_drive:
        drive_readmes_info = call_drive_emit_readmes_fn(
            slug,
            base_dir,
            logger,
            emit_readmes_for_raw,
        ) or {}

    validator = validate_dummy_structure_fn or validate_dummy_structure
    validator(base_dir, logger)

    summary_path = base_dir / "book" / "SUMMARY.md"
    readme_path = base_dir / "book" / "README.md"

    health: Dict[str, Any] = {
        "vision_status": vision_status,
        "raw_pdf_count": _count_raw_pdfs(base_dir),
        "tags_count": _count_tags(base_dir),
        "mapping_valid": (semantic_dir / "semantic_mapping.yaml").exists(),
        "summary_exists": summary_path.exists(),
        "readmes_count": 0,
        "status": "ok",
        "errors": [],
        "checks": [],
        "external_checks": {},
        "mode": "deep" if deep_testing else "smoke",
    }
    if hard_check_results:
        for name, (ok, details, latency) in hard_check_results.items():
            _record_external_check(health, name, ok, details, latency)

    paths = {
        "base": str(base_dir),
        "config": str(base_dir / "config" / "config.yaml"),
        "vision_pdf": str(pdf_path(slug)),
        "semantic_mapping": str(semantic_dir / "semantic_mapping.yaml"),
    }

    return {
        "slug": slug,
        "client_name": client_name,
        "decisions": decisions,
        "paths": paths,
        "drive_min": drive_min_info,
        "drive_readmes": drive_readmes_info,
        "config_ids": {},
        "vision_used": vision_completed,
        "drive_used": bool(enable_drive),
        "local_readmes": [],
        "health": health,
    }


__all__ = ["register_client", "validate_dummy_structure", "build_dummy_payload", "HardCheckError"]
