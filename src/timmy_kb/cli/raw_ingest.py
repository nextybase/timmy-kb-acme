# SPDX-License-Identifier: GPL-3.0-only
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Optional

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.context import ClientContext
from pipeline.env_utils import ensure_dotenv_loaded
from pipeline.exceptions import ArtifactPolicyViolation, ConfigError, PipelineError, exit_code_for
from pipeline.ingest.provider import build_ingest_provider
from pipeline.logging_utils import get_structured_logger
from pipeline.normalized_index import NormalizedIndexRecord, write_index
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import (
    ensure_valid_slug,
    ensure_within_and_resolve,
    iter_safe_paths,
    open_for_read_bytes_selfguard,
)
from pipeline.raw_transform_service import STATUS_FAIL, STATUS_OK, STATUS_SKIP, get_default_raw_transform_service
from pipeline.workspace_layout import WorkspaceLayout, workspace_validation_policy
from storage import decision_ledger


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _obs_kwargs() -> dict[str, Any]:
    settings = get_observability_settings()
    return {
        "level": settings.log_level,
        "redact_logs": settings.redact_logs,
        "enable_tracing": settings.tracing_enabled,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open_for_read_bytes_selfguard(path) as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_evidence_refs(
    layout: WorkspaceLayout,
    *,
    transformer_name: str,
    transformer_version: str,
    ruleset_hash: str,
    stats: dict[str, int],
) -> list[str]:
    return [
        f"path:{layout.config_path}",
        f"path:{layout.raw_dir}",
        f"path:{layout.normalized_dir}",
        f"path:{layout.normalized_dir / 'INDEX.json'}",
        f"transformer_name:{transformer_name}",
        f"transformer_version:{transformer_version}",
        f"ruleset_hash:{ruleset_hash}",
        f"stats:{json.dumps(stats, sort_keys=True, separators=(',', ':'))}",
    ]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Raw ingest (RAW -> normalized)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument(
        "--source",
        choices=("drive", "local"),
        default="drive",
        help="Sorgente PDF (default: drive).",
    )
    p.add_argument(
        "--local-path",
        type=str,
        help="Percorso locale sorgente PDF (usato solo con --source=local).",
    )
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p.parse_args()


def run_raw_ingest(
    *,
    slug: str,
    source: str,
    local_path: Optional[str],
    non_interactive: bool,
) -> None:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("raw_ingest", run_id=run_id, **_obs_kwargs())
    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=input, logger=logger)

    if source == "drive":
        ensure_dotenv_loaded(strict=True, allow_fallback=False)

    context = ClientContext.load(
        slug=slug,
        require_env=(source == "drive"),
        run_id=run_id,
        bootstrap_config=False,
    )
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(context)

    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(ledger_conn, run_id=run_id, slug=slug, started_at=_utc_now_iso())

    provider = build_ingest_provider(source)
    ingest_logger = get_structured_logger("raw_ingest.ingest", run_id=run_id, context=context, **_obs_kwargs())
    provider.ingest_raw(
        context=context,
        raw_dir=layout.raw_dir,
        logger=ingest_logger,
        non_interactive=non_interactive,
        local_path=Path(local_path).expanduser().resolve() if local_path else None,
    )

    transform = get_default_raw_transform_service()
    records: list[NormalizedIndexRecord] = []
    ok_count = 0
    skip_count = 0
    fail_count = 0

    for raw_path in iter_safe_paths(layout.raw_dir, include_dirs=False, include_files=True, suffixes=(".pdf",)):
        safe_raw = ensure_within_and_resolve(layout.raw_dir, raw_path)
        rel_raw = safe_raw.relative_to(layout.raw_dir).as_posix()
        normalized_candidate = layout.normalized_dir / Path(rel_raw).with_suffix(".md")
        input_hash = _sha256(safe_raw)
        try:
            result = transform.transform(input_path=safe_raw, output_path=normalized_candidate)
        except Exception as exc:
            fail_count += 1
            records.append(
                NormalizedIndexRecord(
                    source_path=rel_raw,
                    normalized_path=None,
                    status=STATUS_FAIL,
                    input_hash=input_hash,
                    output_hash=None,
                    transformer_name=getattr(transform, "transformer_name", "unknown"),
                    transformer_version=getattr(transform, "transformer_version", "unknown"),
                    ruleset_hash=getattr(transform, "ruleset_hash", "unknown"),
                    error=str(exc),
                )
            )
            continue

        output_hash = None
        normalized_rel = None
        if result.status == STATUS_OK and result.output_path is not None:
            ok_count += 1
            normalized_rel = result.output_path.relative_to(layout.normalized_dir).as_posix()
            output_hash = _sha256(result.output_path)
        elif result.status == STATUS_SKIP:
            skip_count += 1
        else:
            fail_count += 1

        records.append(
            NormalizedIndexRecord(
                source_path=rel_raw,
                normalized_path=normalized_rel,
                status=result.status,
                input_hash=input_hash,
                output_hash=output_hash,
                transformer_name=result.transformer_name,
                transformer_version=result.transformer_version,
                ruleset_hash=result.ruleset_hash,
                error=result.error,
            )
        )

    if ok_count == 0:
        raise ConfigError("Nessun file normalizzato (OK=0).")

    index_path = ensure_within_and_resolve(layout.normalized_dir, layout.normalized_dir / "INDEX.json")
    write_index(index_path, records)

    stats = {"ok": ok_count, "skip": skip_count, "fail": fail_count}
    try:
        enforce_core_artifacts("raw_ingest", layout=layout)
    except ArtifactPolicyViolation as exc:
        decision_ledger.record_normative_decision(
            ledger_conn,
            decision_ledger.NormativeDecisionRecord(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                slug=slug,
                gate_name="normalize_raw",
                from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
                to_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
                verdict=decision_ledger.NORMATIVE_BLOCK,
                subject="raw_ingest",
                decided_at=_utc_now_iso(),
                actor="cli.raw_ingest",
                evidence_refs=[
                    *_build_evidence_refs(
                        layout,
                        transformer_name=getattr(transform, "transformer_name", "unknown"),
                        transformer_version=getattr(transform, "transformer_version", "unknown"),
                        ruleset_hash=getattr(transform, "ruleset_hash", "unknown"),
                        stats=stats,
                    ),
                    *exc.evidence_refs,
                ],
                stop_code=decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION,
                rationale="deny_artifact_policy_violation",
            ),
        )
        raise
    decision_ledger.record_normative_decision(
        ledger_conn,
        decision_ledger.NormativeDecisionRecord(
            decision_id=uuid.uuid4().hex,
            run_id=run_id,
            slug=slug,
            gate_name="normalize_raw",
            from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
            to_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
            verdict=decision_ledger.NORMATIVE_PASS,
            subject="raw_ingest",
            decided_at=_utc_now_iso(),
            actor="cli.raw_ingest",
            evidence_refs=_build_evidence_refs(
                layout,
                transformer_name=getattr(transform, "transformer_name", "unknown"),
                transformer_version=getattr(transform, "transformer_version", "unknown"),
                ruleset_hash=getattr(transform, "ruleset_hash", "unknown"),
                stats=stats,
            ),
            rationale="ok",
        ),
    )
    logger.info("cli.raw_ingest.completed", extra={"slug": slug, **stats})


def main() -> int:
    args = _parse_args()
    slug = (args.slug_pos or args.slug or "").strip()
    if not slug:
        raise ConfigError("Slug mancante per raw_ingest.")
    try:
        run_raw_ingest(
            slug=slug,
            source=args.source,
            local_path=args.local_path,
            non_interactive=bool(args.non_interactive),
        )
    except (ConfigError, PipelineError) as exc:
        return int(exit_code_for(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
