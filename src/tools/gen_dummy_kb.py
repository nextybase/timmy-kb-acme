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


# ------------------------------------------------------------
# Path bootstrap (repo root + src)
# ------------------------------------------------------------
def _add_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]  # <repo>/
    src_dir = repo_root / "src"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return repo_root, src_dir


REPO_ROOT, SRC_DIR = _add_paths()
SRC_ROOT = SRC_DIR
from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard  # noqa: E402
from pipeline.vision_template import load_vision_template_sections  # noqa: E402

try:
    from .dummy.bootstrap import client_base as _client_base_helper  # type: ignore[misc]  # noqa: E402
    from .dummy.bootstrap import pdf_path as _pdf_path_helper  # type: ignore[misc]  # noqa: E402
    from .dummy.orchestrator import build_dummy_payload as _build_dummy_payload  # type: ignore[misc]  # noqa: E402
    from .dummy.orchestrator import register_client as _register_client_helper  # type: ignore[misc]  # noqa: E402
    from .dummy.orchestrator import (  # type: ignore[misc]  # noqa: E402
        validate_dummy_structure as _validate_dummy_structure_helper,
    )
    from .dummy.semantic import ensure_book_skeleton as _ensure_book_skeleton  # type: ignore[misc]  # noqa: E402
    from .dummy.semantic import ensure_local_readmes as _ensure_local_readmes  # type: ignore[misc]  # noqa: E402
    from .dummy.semantic import ensure_minimal_tags_db as _ensure_minimal_tags_db
    from .dummy.semantic import ensure_raw_pdfs as _ensure_raw_pdfs
    from .dummy.semantic import load_mapping_categories as _load_mapping_categories
    from .dummy.semantic import write_basic_semantic_yaml as _write_basic_semantic_yaml
    from .dummy.vision import run_vision_with_timeout as _run_vision_with_timeout  # type: ignore[misc]  # noqa: E402
except ImportError:
    # Esecuzione diretta come script (__package__=None): garantisce sys.path e importa via prefisso src.tools.*
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    for candidate in (repo_root, src_root):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    from src.tools.dummy.bootstrap import client_base as _client_base_helper  # type: ignore[misc]  # noqa: E402
    from src.tools.dummy.bootstrap import pdf_path as _pdf_path_helper  # type: ignore[misc]  # noqa: E402
    from src.tools.dummy.orchestrator import (  # type: ignore[misc]  # noqa: E402
        build_dummy_payload as _build_dummy_payload,
    )
    from src.tools.dummy.orchestrator import (  # type: ignore[misc]  # noqa: E402
        register_client as _register_client_helper,
    )
    from src.tools.dummy.orchestrator import (  # type: ignore[misc]  # noqa: E402
        validate_dummy_structure as _validate_dummy_structure_helper,
    )
    from src.tools.dummy.semantic import (  # type: ignore[misc]  # noqa: E402
        ensure_book_skeleton as _ensure_book_skeleton,
    )
    from src.tools.dummy.semantic import (  # type: ignore[misc]  # noqa: E402
        ensure_local_readmes as _ensure_local_readmes,
    )
    from src.tools.dummy.semantic import ensure_minimal_tags_db as _ensure_minimal_tags_db
    from src.tools.dummy.semantic import ensure_raw_pdfs as _ensure_raw_pdfs
    from src.tools.dummy.semantic import load_mapping_categories as _load_mapping_categories
    from src.tools.dummy.semantic import write_basic_semantic_yaml as _write_basic_semantic_yaml
    from src.tools.dummy.vision import (  # type: ignore[misc]  # noqa: E402
        run_vision_with_timeout as _run_vision_with_timeout,
    )

try:
    from pipeline.exceptions import ConfigError  # type: ignore
except Exception:  # pragma: no cover
    ConfigError = Exception  # type: ignore[assignment]


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
from pre_onboarding import ensure_local_workspace_for_ui  # type: ignore

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
    from .dummy.drive import (  # type: ignore[misc]  # noqa: E402
        call_drive_build_from_mapping as _call_drive_build_from_mapping,
    )
    from .dummy.drive import call_drive_emit_readmes as _call_drive_emit_readmes  # type: ignore[misc]  # noqa: E402
    from .dummy.drive import call_drive_min as _call_drive_min  # type: ignore[misc]  # noqa: E402
except ImportError:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from src.tools.dummy.drive import (  # type: ignore[misc]  # noqa: E402
        call_drive_build_from_mapping as _call_drive_build_from_mapping,
    )
    from src.tools.dummy.drive import (  # type: ignore[misc]  # noqa: E402
        call_drive_emit_readmes as _call_drive_emit_readmes,
    )
    from src.tools.dummy.drive import call_drive_min as _call_drive_min  # type: ignore[misc]  # noqa: E402
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


# Compat: test_gen_dummy_kb_import_safety si aspetta che gli attributi pubblici siano None finch� non si esegue il tool.
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

    for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

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
    ap.add_argument("--with-drive", action="store_true", help="(Legacy) Abilita Drive se possibile")
    ap.add_argument(
        "--base-dir",
        default=None,
        help="(Legacy) Directory radice in cui creare il workspace (override di REPO_ROOT_DIR).",
    )
    ap.add_argument(
        "--clients-db",
        dest="clients_db",
        default=None,
        help="(Legacy) Percorso relativo (clients_db/clients.yaml); imposta CLIENTS_DB_DIR/FILE per la UI.",
    )
    ap.add_argument(
        "--records",
        default=None,
        help="(Legacy) Numero di record finanza da generare (non più utilizzato).",
    )
    return ap.parse_args(argv)


def build_payload(
    *,
    slug: str,
    client_name: str,
    enable_drive: bool,
    enable_vision: bool,
    records_hint: Optional[str],
    logger: logging.Logger,
) -> _DummyPayload:
    return _build_dummy_payload(
        slug=slug,
        client_name=client_name,
        enable_drive=enable_drive,
        enable_vision=enable_vision,
        records_hint=records_hint,
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

        logger = get_structured_logger("tools.gen_dummy_kb", context={"slug": slug})
        logger.setLevel(logging.INFO)

        _purge_previous_state(slug, client_name, logger)

        try:
            payload = build_payload(
                slug=slug,
                client_name=client_name,
                enable_drive=enable_drive,
                enable_vision=enable_vision,
                records_hint=records_hint,
                logger=logger,
            )
            emit_structure(payload)
            return 0
        except Exception as exc:
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
