# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/gen_dummy_kb.py
# Genera una KB "dummy" passando dalle stesse funzioni usate dalla UI:
# pre_onboarding + Vision (+ Drive opzionale). Con flag per disabilitare Drive/Vision.

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, TypedDict

try:
    import yaml
except Exception:
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]


class _PayloadPaths(TypedDict):
    base: str
    config: str
    vision_pdf: str
    semantic_mapping: str
    cartelle_raw: str


class _PayloadConfigIds(TypedDict, total=False):
    drive_folder_id: Optional[str]
    drive_raw_folder_id: Optional[str]


class _DummyPayload(TypedDict):
    slug: str
    client_name: str
    paths: _PayloadPaths
    drive_min: Dict[str, Any]
    drive_build: Dict[str, Any]
    drive_readmes: Dict[str, Any]
    config_ids: _PayloadConfigIds
    vision_used: bool
    drive_used: bool
    fallback_used: bool
    local_readmes: List[str]
    health: Dict[str, Any]


from pipeline.capabilities import dummy_kb as dummy_kb_capabilities

# ------------------------------------------------------------
# Path bootstrap (repo root + src)
# ------------------------------------------------------------
from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard  # noqa: E402
from pipeline.workspace_layout import workspace_validation_policy  # noqa: E402
from pipeline.vision_template import load_vision_template_sections  # noqa: E402

try:
    _dummy_helpers = dummy_kb_capabilities.load_dummy_helpers()
except ImportError as exc:
    raise SystemExit(f"Dummy KB helpers mancanti: {exc}") from exc

HardCheckError = getattr(dummy_kb_capabilities, "HardCheckError", None)

try:
    _drive_helpers = dummy_kb_capabilities.load_dummy_drive_helpers()
except ImportError as exc:
    raise SystemExit(f"Dummy KB drive helpers mancanti: {exc}") from exc

_client_base_helper = _dummy_helpers.client_base
_pdf_path_helper = _dummy_helpers.pdf_path
_build_dummy_payload = _dummy_helpers.build_dummy_payload
_register_client_helper = _dummy_helpers.register_client
_validate_dummy_structure_helper = _dummy_helpers.validate_dummy_structure
_ensure_book_skeleton = _dummy_helpers.ensure_book_skeleton
_ensure_local_readmes = _dummy_helpers.ensure_local_readmes
_ensure_minimal_tags_db = _dummy_helpers.ensure_minimal_tags_db
_ensure_raw_pdfs = _dummy_helpers.ensure_raw_pdfs
_load_mapping_categories = _dummy_helpers.load_mapping_categories
_write_basic_semantic_yaml = _dummy_helpers.write_basic_semantic_yaml
_run_vision_with_timeout = _dummy_helpers.run_vision_with_timeout

_call_drive_build_from_mapping = _drive_helpers.call_drive_build_from_mapping
_call_drive_emit_readmes = _drive_helpers.call_drive_emit_readmes
_call_drive_min = _drive_helpers.call_drive_min


def _normalize_relative_path(value: str, *, var_name: str) -> Path:
    candidate = Path(value.strip())
    if not value.strip():
        raise SystemExit(f"{var_name} non può essere vuoto")
    if candidate.is_absolute():
        raise SystemExit(f"{var_name} deve indicare un percorso relativo (es. clients_db/clients.yaml)")
    normalised = Path()
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise SystemExit(f"{var_name}: componenti '..' non sono ammesse")
        normalised /= part
    if not normalised.parts:
        raise SystemExit(f"{var_name} non può essere vuoto")
    return normalised


# ------------------------------------------------------------
# Import delle API usate dalla UI
# ------------------------------------------------------------
# pre_onboarding: workspace locale + salvataggio Vision PDF (se fornito)
from timmy_kb.cli.pre_onboarding import ensure_local_workspace_for_ui  # type: ignore

# Vision (stesse firme UI)
_vision_mod = importlib.import_module("ui.services.vision_provision")
run_vision = getattr(_vision_mod, "run_vision")

# Drive runner (opzionale). Se non presente → si prosegue senza Drive.
try:
    _drive_mod = importlib.import_module("ui.services.drive_runner")
    ensure_drive_minimal_and_upload_config = getattr(_drive_mod, "ensure_drive_minimal_and_upload_config", None)
    build_drive_from_mapping = getattr(_drive_mod, "build_drive_from_mapping", None)
    emit_readmes_for_raw = getattr(_drive_mod, "emit_readmes_for_raw", None)
except Exception:
    ensure_drive_minimal_and_upload_config = None
    build_drive_from_mapping = None
    emit_readmes_for_raw = None

try:
    from tools.clean_client_workspace import perform_cleanup as _perform_cleanup  # type: ignore
except Exception:  # pragma: no cover - il cleanup completo può non essere disponibile in ambienti ridotti
    _perform_cleanup = None  # type: ignore[assignment]

# Registry UI (clienti)
try:
    from ui.clients_store import ClientEntry, set_state, upsert_client  # type: ignore
except Exception:
    ClientEntry = None
    upsert_client = None
    set_state = None

# Util pipeline (facoltative)
try:
    from pipeline.config_utils import get_client_config  # type: ignore
except Exception:
    get_client_config = None

try:
    from pipeline.context import ClientContext  # type: ignore
except Exception:
    ClientContext = None

try:
    from pipeline.env_utils import ensure_dotenv_loaded, get_env_var  # type: ignore
except Exception:

    def ensure_dotenv_loaded() -> None:  # type: ignore
        return

    def get_env_var(name: str, default: str | None = None, **_: object) -> str | None:
        return os.environ.get(name, default)


try:
    from pipeline.file_utils import safe_write_bytes as _safe_write_bytes  # type: ignore
    from pipeline.file_utils import safe_write_text as _safe_write_text  # type: ignore
except Exception:

    def _safe_write_text(path: Path, text: str, *, encoding="utf-8", atomic=False) -> None:  # type: ignore
        raise RuntimeError("safe_write_text unavailable: install pipeline.file_utils dependency")  # pragma: no cover

    def _safe_write_bytes(path: Path, data: bytes, *, atomic=False) -> None:  # type: ignore
        raise RuntimeError("safe_write_bytes unavailable: install pipeline.file_utils dependency")  # pragma: no cover


# Compat: test_gen_dummy_kb_import_safety si aspetta che gli attributi pubblici siano None finché non si esegue il tool.
safe_write_text = None  # type: ignore
safe_write_bytes = None  # type: ignore
_fin_import_csv = None  # type: ignore

try:
    from storage import tags_store as _tags_store  # type: ignore
except Exception:  # pragma: no cover - opzionale
    _tags_store = None  # type: ignore[assignment]


def _ensure_dependencies() -> None:
    """Carica lazy le dipendenze opzionali e popola i placeholder pubblici."""
    if getattr(_ensure_dependencies, "_done", False):
        return

    global safe_write_text, safe_write_bytes, _fin_import_csv
    safe_write_text = _safe_write_text  # type: ignore
    safe_write_bytes = _safe_write_bytes  # type: ignore

    try:
        from finance.api import import_csv as fin_import_csv  # type: ignore
    except Exception:
        fin_import_csv = None
    _fin_import_csv = fin_import_csv  # type: ignore

    _ensure_dependencies._done = True  # type: ignore[attr-defined]


_ensure_dependencies._done = False  # type: ignore[attr-defined]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _client_base(slug: str) -> Path:
    return _client_base_helper(slug, REPO_ROOT, get_env_var)


def _pdf_path(slug: str) -> Path:
    return _pdf_path_helper(slug, REPO_ROOT, get_env_var)


def _register_client(slug: str, client_name: str) -> None:
    _register_client_helper(slug, client_name, ClientEntry=ClientEntry, upsert_client=upsert_client)


def _validate_dummy_structure(base_dir: Path, logger: logging.Logger) -> None:
    _validate_dummy_structure_helper(base_dir, logger)


def _purge_previous_state(slug: str, client_name: str, logger: logging.Logger) -> None:
    """
    Rimuove eventuali residui precedenti (locale + Drive + registry) prima di rigenerare la Dummy KB.

    - Usa `tools.clean_client_workspace.perform_cleanup` se disponibile.
    - In ogni caso prova a cancellare la cartella locale `output/timmy-kb-<slug>`.
    """

    if callable(_perform_cleanup):
        try:
            results = _perform_cleanup(slug, client_name=client_name)
            exit_code = results.get("exit_code")
            logger.info(
                "tools.gen_dummy_kb.cleanup.completed",
                extra={"slug": slug, "exit_code": exit_code, "results": results},
            )
        except Exception as exc:
            logger.warning(
                "tools.gen_dummy_kb.cleanup.failed",
                extra={"slug": slug, "error": str(exc)},
            )

    base_dir = _client_base(slug)
    try:
        if base_dir.exists():
            shutil.rmtree(base_dir)
            logger.info("tools.gen_dummy_kb.cleanup.local_deleted", extra={"slug": slug})
    except Exception as exc:
        logger.warning(
            "tools.gen_dummy_kb.cleanup.local_failed",
            extra={"slug": slug, "error": str(exc)},
        )

    sentinel = base_dir / "semantic" / ".vision_hash"
    try:
        if sentinel.exists():
            sentinel.unlink()
    except Exception as exc:
        # L'assenza del sentinel è già sufficiente; eventuali errori qui non sono bloccanti.
        logger.debug(
            "tools.gen_dummy_kb.cleanup.sentinel_unlink_failed",
            extra={"slug": slug, "error": str(exc)},
        )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Genera una KB dummy usando gli entry-point della UI (pre_onboarding + Vision + (Drive opz.))."
    )
    ap.add_argument("--slug", default="dummy", help="Slug del cliente (default: dummy)")
    ap.add_argument("--name", default=None, help='Nome visuale del cliente (default: "Dummy <slug>")')
    ap.add_argument("--no-drive", action="store_true", help="Disabilita tutti i passi Drive")
    ap.add_argument("--no-vision", action="store_true", help="Non invocare Vision: genera YAML basici")
    ap.add_argument("--with-drive", action="store_true", help="Abilita Drive se possibile (compat)")
    ap.add_argument(
        "--base-dir",
        default=None,
        help="Directory radice in cui creare il workspace (override esplicito di REPO_ROOT_DIR).",
    )
    ap.add_argument(
        "--clients-db",
        dest="clients_db",
        default=None,
        help="(Override test/CI) Percorso relativo (clients_db/clients.yaml); imposta CLIENTS_DB_DIR/FILE per la UI.",
    )
    ap.add_argument(
        "--records",
        default=None,
        help="Numero di record finanza da generare (disabilita Vision).",
    )
    ap.add_argument(
        "--deep-testing",
        action="store_true",
        help="Attiva la modalità deep testing (modo log only).",
    )
    return ap.parse_args(argv)


def build_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    records_hint: Optional[str],
    deep_testing: bool = False,
    logger: logging.Logger,
) -> _DummyPayload:
    return _build_dummy_payload(
        slug=slug,
        client_name=client_name,
        enable_drive=enable_drive,
        enable_vision=enable_vision,
        records_hint=records_hint,
        deep_testing=deep_testing,
        logger=logger,
        repo_root=REPO_ROOT,
        ensure_local_workspace_for_ui=ensure_local_workspace_for_ui,
        run_vision=run_vision,
        get_env_var=get_env_var,
        ensure_within_and_resolve_fn=ensure_within_and_resolve,
        open_for_read_bytes_selfguard=open_for_read_bytes_selfguard,
        load_vision_template_sections=load_vision_template_sections,
        client_base=_client_base,
        pdf_path=_pdf_path,
        register_client_fn=_register_client,
        ClientContext=ClientContext,
        get_client_config=get_client_config,
        ensure_drive_minimal_and_upload_config=ensure_drive_minimal_and_upload_config,
        build_drive_from_mapping=build_drive_from_mapping,
        emit_readmes_for_raw=emit_readmes_for_raw,
        run_vision_with_timeout_fn=_run_vision_with_timeout,
        write_basic_semantic_yaml_fn=_write_basic_semantic_yaml,
        load_mapping_categories_fn=_load_mapping_categories,
        ensure_minimal_tags_db_fn=_ensure_minimal_tags_db,
        ensure_raw_pdfs_fn=_ensure_raw_pdfs,
        ensure_local_readmes_fn=_ensure_local_readmes,
        ensure_book_skeleton_fn=_ensure_book_skeleton,
        validate_dummy_structure_fn=_validate_dummy_structure,
        call_drive_min_fn=_call_drive_min,
        call_drive_build_from_mapping_fn=_call_drive_build_from_mapping,
        call_drive_emit_readmes_fn=_call_drive_emit_readmes,
    )


def emit_structure(payload: _DummyPayload | Dict[str, Any], *, stream: TextIO = sys.stdout) -> None:
    stream.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    stream.write("\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ensure_dotenv_loaded()

    args = parse_args(argv)

    slug = args.slug.strip()
    client_name = (args.name or f"Dummy {slug}").strip()
    enable_drive = (not args.no_drive) or args.with_drive
    enable_vision = not args.no_vision
    records_hint = args.records

    if records_hint is not None and not args.no_vision:
        enable_vision = False
        enable_drive = False

    if not args.with_drive and (args.base_dir or args.clients_db):
        enable_drive = False
        if not args.no_vision:
            enable_vision = False

    prev_repo_root_dir = os.environ.get("REPO_ROOT_DIR")
    prev_clients_db_dir = os.environ.get("CLIENTS_DB_DIR")
    prev_clients_db_file = os.environ.get("CLIENTS_DB_FILE")
    workspace_override: Optional[Path] = None
    try:
        if args.base_dir:
            base_override = Path(args.base_dir).expanduser().resolve()
            workspace_override = base_override / f"timmy-kb-{slug}"
            os.environ["REPO_ROOT_DIR"] = str(workspace_override)
            # Bootstrap minimale del workspace dummy: crea le cartelle base per evitare
            # fallimenti di validazione (raw/semantic/book/logs/config).
            for child in ("raw", "semantic", "book", "logs", "config"):
                (workspace_override / child).mkdir(parents=True, exist_ok=True)

        if args.clients_db:
            clients_db_relative = _normalize_relative_path(args.clients_db, var_name="--clients-db")
            if len(clients_db_relative.parts) < 2:
                raise SystemExit("--clients-db deve includere anche il nome file (es. clients_db/clients.yaml)")
            if clients_db_relative.parts[0] != "clients_db":
                raise SystemExit("--clients-db deve iniziare con 'clients_db/'")
            db_dir_override = Path(*clients_db_relative.parts[:-1])
            db_file_override = Path(clients_db_relative.parts[-1])
            os.environ["CLIENTS_DB_DIR"] = str(db_dir_override)
            os.environ["CLIENTS_DB_FILE"] = str(db_file_override)

        mode_label = "deep" if args.deep_testing else "smoke"
        logger = get_structured_logger("tools.gen_dummy_kb", context={"slug": slug})
        logger.setLevel(logging.INFO)
        logger.info("tools.gen_dummy_kb.mode", extra={"mode": mode_label})

        _purge_previous_state(slug, client_name, logger)
        if workspace_override:
            for child in ("raw", "semantic", "book", "logs", "config"):
                (workspace_override / child).mkdir(parents=True, exist_ok=True)

        try:
            with workspace_validation_policy(skip_validation=True):
                try:
                    import pipeline.workspace_layout as _wl
                    _wl._SKIP_VALIDATION = True
                except Exception:
                    pass
                workspace_root = workspace_override or _client_base(slug)
                for child in ("raw", "semantic", "book", "logs", "config"):
                    (workspace_root / child).mkdir(parents=True, exist_ok=True)
                payload = build_payload(
                    slug=slug,
                    client_name=client_name,
                    enable_drive=enable_drive,
                    enable_vision=enable_vision,
                    records_hint=records_hint,
                    logger=logger,
                    deep_testing=args.deep_testing,
                )
            emit_structure(payload)
            return 0
        except Exception as exc:
            if HardCheckError is not None and isinstance(exc, HardCheckError):
                logger.error(
                    "tools.gen_dummy_kb.hardcheck.failed",
                    extra={"slug": slug, "error": str(exc)},
                )
                payload = {
                    "slug": slug,
                    "client_name": client_name,
                    "health": exc.health,
                }
                emit_structure(payload)
                return 1
            logger.error(
                "tools.gen_dummy_kb.run_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            emit_structure({"error": str(exc)}, stream=sys.stderr)
            return 1
    finally:
        try:
            from ui.utils.workspace import clear_base_cache  # late import per evitare dipendenze circolari
        except Exception:  # pragma: no cover
            clear_base_cache = None  # type: ignore[assignment]
        if callable(clear_base_cache):
            clear_base_cache(slug=slug)
        if args.base_dir:
            if prev_repo_root_dir is None:
                os.environ.pop("REPO_ROOT_DIR", None)
            else:
                os.environ["REPO_ROOT_DIR"] = prev_repo_root_dir
        if args.clients_db:
            if prev_clients_db_dir is None:
                os.environ.pop("CLIENTS_DB_DIR", None)
            else:
                os.environ["CLIENTS_DB_DIR"] = prev_clients_db_dir
            if prev_clients_db_file is None:
                os.environ.pop("CLIENTS_DB_FILE", None)
            else:
                os.environ["CLIENTS_DB_FILE"] = prev_clients_db_file


if __name__ == "__main__":
    raise SystemExit(main())
