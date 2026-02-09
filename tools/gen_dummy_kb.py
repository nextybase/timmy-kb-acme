# SPDX-License-Identifier: GPL-3.0-or-later
# tools/gen_dummy_kb.py
"""Tooling DEV/ADMIN-only per bootstrap, diagnostica e CI.

Non rappresenta un percorso runtime utente né un fallback supportato in ambienti strict.
Usa gli stessi entry point della UI (pre_onboarding + Vision + Drive opzionale)
per produrre artefatti deterministici destinati solo all'operatore.

Regola Beta 1.0:
- UI standard (runtime) = sempre strict (TIMMY_BETA_STRICT=1) e il flag è un invariante non modificabile dai tool.
- Tooling/Admin può eseguire step non-strict solo se isolati, espliciti e tracciati (es. vision_enrichment).
- Questo tool mantiene il flag strict durante tutta la run e delega ogni deroga puntuale a un audit nel ledger.
"""

from __future__ import annotations

if __name__ == "__main__":
    # Avvio diretto: assicura la repo root su sys.path per import deterministici di tools/*.
    import sys
    from pathlib import Path

    _repo_root = Path(__file__).resolve().parents[1]
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

import argparse
import importlib
import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, TextIO, TypedDict

from pipeline.paths import get_repo_root
REPO_ROOT = get_repo_root(allow_env=False)


def _force_utf8_stdio() -> None:
    """Assicura che stdout/stderr usino UTF-8 (usato anche nei test legacy)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    os.environ.setdefault("PYTHONIOENCODING", "UTF-8")
    os.environ.setdefault("PYTHONUTF8", "1")


_force_utf8_stdio()


class _PayloadPaths(TypedDict):
    base: str
    config: str
    vision_pdf: str
    semantic_mapping: str


class _PayloadConfigIds(TypedDict, total=False):
    drive: Dict[str, Optional[str]]


class _DummyPayload(TypedDict):
    slug: str
    client_name: str
    paths: _PayloadPaths
    drive_min: Dict[str, Any]
    drive_readmes: Dict[str, Any]
    config_ids: _PayloadConfigIds
    vision_used: bool
    drive_used: bool
    fallback_used: bool
    local_readmes: List[str]
    health: Dict[str, Any]


from pipeline.capabilities import dummy_kb as dummy_kb_capabilities
from tools.dummy import bootstrap as dummy_bootstrap
from tools.dummy.health import build_hardcheck_health
from tools.dummy.policy import DummyPolicy

# ------------------------------------------------------------
# Path bootstrap (repo root + src)
# ------------------------------------------------------------
from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.env_constants import WORKSPACE_ROOT_ENV  # noqa: E402
from pipeline.env_utils import get_env_var  # noqa: E402
from pipeline.path_utils import (  # noqa: E402
    ensure_within_and_resolve,
    open_for_read_bytes_selfguard,
    read_text_safe,
)
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
_write_basic_semantic_yaml = getattr(_dummy_helpers, "write_basic_semantic_yaml", None)
_run_vision_with_timeout = _dummy_helpers.run_vision_with_timeout

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
# Helpers per import lento
# ------------------------------------------------------------
def _strict_optional_import(
    module_name: str,
    *,
    feature_name: str,
    attrs: Optional[Dict[str, str]] = None,
) -> tuple[Optional[ModuleType], Dict[str, Any], Optional[str]]:
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        return None, {}, f"{feature_name}.missing_module:{module_name}"
    except Exception as exc:
        raise RuntimeError(f"Errore import {feature_name} ({module_name}): {exc}") from exc
    values: Dict[str, Any] = {}
    if attrs:
        for public_name, attr_name in attrs.items():
            try:
                values[public_name] = getattr(module, attr_name)
            except AttributeError as exc:
                raise AttributeError(
                    f"Errore import {feature_name}: attributo mancante {attr_name} in {module_name}"
                ) from exc
    return module, values, None


# ------------------------------------------------------------
# Import delle API usate dalla UI
# ------------------------------------------------------------
# Vision (stesse firme UI)
_vision_mod = importlib.import_module("ui.services.vision_provision")
run_vision = getattr(_vision_mod, "run_vision")

# Drive runner (opzionale). Se non presente → si prosegue senza Drive.
_drive_mod, _drive_attrs, _drive_import_error = _strict_optional_import(
    "ui.services.drive_runner",
    feature_name="drive_runner",
    attrs={
        "ensure_drive_minimal_and_upload_config": "ensure_drive_minimal_and_upload_config_ui",
        "emit_readmes_for_raw": "emit_readmes_for_raw",
    },
)
ensure_drive_minimal_and_upload_config = _drive_attrs.get("ensure_drive_minimal_and_upload_config")
emit_readmes_for_raw = _drive_attrs.get("emit_readmes_for_raw")

_cleanup_mod, _cleanup_attrs, _cleanup_import_error = _strict_optional_import(
    "src.tools.clean_client_workspace",
    feature_name="cleanup",
    attrs={"perform_cleanup": "perform_cleanup"},
)
_perform_cleanup = _cleanup_attrs.get("perform_cleanup")  # type: ignore[assignment]

# Registry UI (clienti)
_registry_mod, _registry_attrs, _registry_import_error = _strict_optional_import(
    "ui.clients_store",
    feature_name="ui_registry",
    attrs={"ClientEntry": "ClientEntry", "set_state": "set_state", "upsert_client": "upsert_client"},
)
ClientEntry = _registry_attrs.get("ClientEntry")
upsert_client = _registry_attrs.get("upsert_client")
set_state = _registry_attrs.get("set_state")

# Util pipeline (facoltative)
_config_mod, _config_attrs, _config_import_error = _strict_optional_import(
    "pipeline.config_utils",
    feature_name="config_utils",
    attrs={"get_client_config": "get_client_config"},
)
get_client_config = _config_attrs.get("get_client_config")

_context_mod, _context_attrs, _context_import_error = _strict_optional_import(
    "pipeline.context",
    feature_name="client_context",
    attrs={"ClientContext": "ClientContext"},
)
ClientContext = _context_attrs.get("ClientContext")

try:
    from pipeline.env_utils import ensure_dotenv_loaded, get_env_var  # type: ignore
except (ImportError, ModuleNotFoundError) as exc:
    raise SystemExit(f"pipeline.env_utils mancante: {exc}") from exc

try:
    from pipeline.file_utils import safe_write_bytes as _safe_write_bytes  # type: ignore
    from pipeline.file_utils import safe_write_text as _safe_write_text  # type: ignore
except (ImportError, ModuleNotFoundError) as exc:
    raise SystemExit(f"pipeline.file_utils mancante: {exc}") from exc


# Compat: test_gen_dummy_kb_import_safety si aspetta che gli attributi pubblici siano None finché non si esegue il tool.
safe_write_text = None  # type: ignore
safe_write_bytes = None  # type: ignore
_fin_import_csv = None  # type: ignore

_tags_store_mod, _tags_store_attrs, _tags_store_import_error = _strict_optional_import(
    "storage.tags_store",
    feature_name="tags_store",
)
_tags_store = _tags_store_mod  # type: ignore[assignment]


def _ensure_dependencies() -> None:
    """Carica lazy le dipendenze opzionali e popola i placeholder pubblici."""
    if getattr(_ensure_dependencies, "_done", False):
        return

    global safe_write_text, safe_write_bytes, _fin_import_csv
    safe_write_text = _safe_write_text  # type: ignore
    safe_write_bytes = _safe_write_bytes  # type: ignore

    _finance_mod, _finance_attrs, _finance_import_error = _strict_optional_import(
        "finance.api",
        feature_name="finance_api",
        attrs={"import_csv": "import_csv"},
    )
    fin_import_csv = _finance_attrs.get("import_csv")
    _fin_import_csv = fin_import_csv  # type: ignore

    _ensure_dependencies._done = True  # type: ignore[attr-defined]


_ensure_dependencies._done = False  # type: ignore[attr-defined]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _client_base(slug: str) -> Path:
    return _require_workspace_root(slug)


def _pdf_path(slug: str) -> Path:
    return _require_workspace_root(slug) / "config" / "VisionStatement.pdf"


def _register_client(slug: str, client_name: str, *, policy: DummyPolicy) -> None:
    _register_client_helper(
        slug,
        client_name,
        ClientEntry=ClientEntry,
        upsert_client=upsert_client,
        policy=policy,
    )


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


def _brute_reset_dummy(*, logger: logging.Logger) -> Path:
    # Legacy reset for tooling/devers: still removes repo-local output only.
    target = ensure_within_and_resolve(REPO_ROOT, REPO_ROOT / "output" / "timmy-kb-dummy")
    if target.exists():
        shutil.rmtree(target)
        logger.info("tools.gen_dummy_kb.brute_reset.deleted", extra={"path": str(target)})
    else:
        logger.info("tools.gen_dummy_kb.brute_reset.not_found", extra={"path": str(target)})
    return target


def _clean_local_workspace_before_generation(
    *,
    slug: str,
    logger: logging.Logger,
    workspace_override: Optional[Path] = None,
) -> None:
    """Assicura workspace locale pulito prima della generazione. Per Dummy: sempre."""
    if slug != "dummy":
        return
    if workspace_override is not None:
        target = ensure_within_and_resolve(workspace_override.parent, workspace_override)
    else:
        target = _client_base(slug)
    if target.exists():
        shutil.rmtree(target)
        logger.info("tools.gen_dummy_kb.local_clean.deleted", extra={"slug": slug, "path": str(target)})


def _require_workspace_root(slug: str) -> Path:
    expected = f"timmy-kb-{slug}"
    try:
        raw = get_env_var(WORKSPACE_ROOT_ENV, required=True)
    except ConfigError as exc:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} obbligatorio: {exc}",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.gen_dummy_kb",
        ) from exc
    if "<slug>" in raw:
        raw = raw.replace("<slug>", slug)
    try:
        workspace_root = Path(raw).expanduser().resolve()
    except Exception as exc:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} non valido: {raw}",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.gen_dummy_kb",
        ) from exc
    if workspace_root.name != expected:
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} deve puntare al workspace canonico '.../{expected}' (trovato: {workspace_root})",
            slug=slug,
            code="workspace.root.invalid",
            component="tools.gen_dummy_kb",
        )
    return workspace_root


def _ensure_local_workspace_for_tooling(*, slug: str, client_name: str, vision_statement_pdf: bytes) -> None:
    workspace_root = _require_workspace_root(slug)

    for child in ("raw", "semantic", "book", "logs", "config", "normalized"):
        (workspace_root / child).mkdir(parents=True, exist_ok=True)

    config_path = ensure_within_and_resolve(workspace_root, workspace_root / "config" / "config.yaml")
    if not config_path.exists():
        template = REPO_ROOT / "config" / "config.yaml"
        if template.exists():
            text = read_text_safe(template.parent, template, encoding="utf-8")
            _safe_write_text(config_path, text, encoding="utf-8", atomic=True)
        else:
            _safe_write_text(
                config_path,
                "ai:\n  vision:\n    vision_statement_pdf: config/VisionStatement.pdf\n",
                encoding="utf-8",
                atomic=True,
            )

    pdf_path = ensure_within_and_resolve(workspace_root, workspace_root / "config" / "VisionStatement.pdf")
    if not pdf_path.exists():
        _safe_write_bytes(pdf_path, vision_statement_pdf, atomic=True)


# Alias pubblico mantenuto per compat dei test: percorso unico layout-first.
ensure_local_workspace_for_ui = _ensure_local_workspace_for_tooling

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    # Parser per tooling DEV/ADMIN: i flag disponibili servono a orchestrare test controllati, non a modificare il runtime.
    ap = argparse.ArgumentParser(
        description="Genera una KB dummy usando gli entry-point della UI (pre_onboarding + Vision + (Drive opz.))."
    )
    ap.add_argument("--slug", default="dummy", help="Slug del cliente (default: dummy)")
    ap.add_argument("--name", default=None, help='Nome visuale del cliente (default: "Dummy <slug>")')
    ap.add_argument("--no-drive", action="store_true", help="Disabilita tutti i passi Drive")
    ap.add_argument("--no-vision", action="store_true", help="Non invocare Vision (nessun artefatto alternativo)")
    ap.add_argument("--with-drive", action="store_true", help="Abilita Drive se possibile (compat)")
    ap.add_argument(
        "--base-dir",
        default=None,
        help="Directory radice in cui creare il workspace (override esplicito di WORKSPACE_ROOT_DIR).",
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
    ap.add_argument(
        "--ci",
        action="store_true",
        help="Segnala che l'esecuzione è parte della pipeline CI (no downgrade).",
    )
    ap.add_argument(
        "--allow-downgrade",
        action="store_true",
        help="Permette di degradare a smoke quando Vision non è disponibile (default: off).",
    )
    ap.add_argument(
        "--brute-reset",
        action="store_true",
        help="Reset manuale: elimina output/timmy-kb-dummy e termina (solo slug dummy).",
    )
    ap.add_argument(
        "--reset",
        action="store_true",
        help="Reset completo Dummy: cleanup cliente (locale + Drive + registry) e termina (solo slug dummy).",
    )
    semantic_group = ap.add_mutually_exclusive_group()
    semantic_group.add_argument(
        "--semantic",
        action="store_true",
        help="Abilita esplicitamente il passo Semantic (default: attivo).",
    )
    semantic_group.add_argument(
        "--no-semantic",
        action="store_true",
        help="Disabilita il passo Semantic.",
    )
    enrich_group = ap.add_mutually_exclusive_group()
    enrich_group.add_argument(
        "--enrichment",
        action="store_true",
        help="Abilita esplicitamente il passo Enrichment (default: attivo).",
    )
    enrich_group.add_argument(
        "--no-enrichment",
        action="store_true",
        help="Disabilita il passo Enrichment.",
    )
    preview_group = ap.add_mutually_exclusive_group()
    preview_group.add_argument(
        "--preview",
        action="store_true",
        help="Abilita esplicitamente il passo Preview (default: attivo).",
    )
    preview_group.add_argument(
        "--no-preview",
        action="store_true",
        help="Disabilita il passo Preview.",
    )
    return ap.parse_args(argv)


def _load_vision_statement_pdf_bytes() -> bytes:
    candidate = REPO_ROOT / "config" / "VisionStatement.pdf"
    if candidate.exists():
        try:
            return candidate.read_bytes()
        except Exception as exc:
            raise SystemExit(f"VisionStatement.pdf non leggibile: {exc}") from exc
    return dummy_bootstrap.DEFAULT_VISION_PDF


def build_payload(
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
    allow_local_only_override: bool = False,
) -> _DummyPayload:
    vision_statement_pdf_bytes = _load_vision_statement_pdf_bytes()

    def _ensure_workspace(
        *,
        slug: str,
        client_name: str,
        vision_statement_pdf: bytes | None,
    ) -> None:
        ensure_local_workspace_for_ui(
            slug=slug,
            client_name=client_name,
            vision_statement_pdf=vision_statement_pdf_bytes,
        )

    return _build_dummy_payload(
        slug=slug,
        client_name=client_name,
        enable_drive=enable_drive,
        enable_vision=enable_vision,
        enable_semantic=enable_semantic,
        enable_enrichment=enable_enrichment,
        enable_preview=enable_preview,
        records_hint=records_hint,
        deep_testing=deep_testing,
        logger=logger,
        repo_root=REPO_ROOT,
        ensure_local_workspace_for_ui=_ensure_workspace,
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
        emit_readmes_for_raw=emit_readmes_for_raw,
        run_vision_with_timeout_fn=_run_vision_with_timeout,
        load_mapping_categories_fn=_load_mapping_categories,
        ensure_minimal_tags_db_fn=_ensure_minimal_tags_db,
        ensure_raw_pdfs_fn=_ensure_raw_pdfs,
        ensure_local_readmes_fn=_ensure_local_readmes,
        ensure_book_skeleton_fn=_ensure_book_skeleton,
        validate_dummy_structure_fn=_validate_dummy_structure,
        policy=policy,
        call_drive_min_fn=_call_drive_min,
        call_drive_emit_readmes_fn=_call_drive_emit_readmes,
        allow_local_only_override=allow_local_only_override,
    )


def emit_structure(payload: _DummyPayload | Dict[str, Any], *, stream: TextIO = sys.stdout) -> None:
    stream.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    stream.write("\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    # Entrypoint DEV/ADMIN per generare Dummy KB; non deve essere invocato dal runtime utente strict-only.
    ensure_dotenv_loaded()

    args = parse_args(argv)

    slug = args.slug.strip()
    client_name = (args.name or f"Dummy {slug}").strip()
    local_only_override = args.no_drive and not args.with_drive
    enable_vision = not args.no_vision
    enable_semantic = not args.no_semantic
    enable_enrichment = not args.no_enrichment
    enable_preview = not args.no_preview
    records_hint = args.records

    if args.reset:
        if slug != "dummy":
            raise SystemExit("--reset consentito solo con slug 'dummy'")
        logger = get_structured_logger("tools.gen_dummy_kb", context={"slug": slug})
        logger.setLevel(logging.INFO)
        if not callable(_perform_cleanup):
            raise SystemExit("Cleanup non disponibile: tools.clean_client_workspace non importabile.")
        results = _perform_cleanup(slug, client_name=client_name)
        emit_structure({"slug": slug, "reset": True, "results": results})
        return int(results.get("exit_code", 1))

    if args.brute_reset:
        if slug != "dummy":
            raise SystemExit("--brute-reset consentito solo con slug 'dummy'")
        if args.base_dir or args.clients_db or args.records:
            raise SystemExit("--brute-reset non accetta --base-dir/--clients-db/--records")
        logger = get_structured_logger("tools.gen_dummy_kb", context={"slug": slug})
        logger.setLevel(logging.INFO)
        target = _brute_reset_dummy(logger=logger)
        emit_structure({"slug": slug, "brute_reset": True, "deleted_path": str(target)})
        return 0

    if records_hint is not None and not args.no_vision:
        enable_vision = False

    prev_repo_root_dir = os.environ.get("REPO_ROOT_DIR")
    prev_workspace_root_dir = os.environ.get("WORKSPACE_ROOT_DIR")
    prev_vision_mode = os.environ.get("VISION_MODE")
    prev_clients_db_dir = os.environ.get("CLIENTS_DB_DIR")
    prev_clients_db_file = os.environ.get("CLIENTS_DB_FILE")
    workspace_override: Optional[Path] = None

    try:
        # CONTROL PLANE: manteniamo TIMMY_BETA_STRICT=1 e confiniamo eventuali deroghe a step locali.
        if not enable_vision and prev_vision_mode is None:
            os.environ["VISION_MODE"] = "SMOKE"

        if args.base_dir:
            base_override = Path(args.base_dir).expanduser().resolve()
            workspace_override = base_override / f"timmy-kb-{slug}"
            os.environ["WORKSPACE_ROOT_DIR"] = str(workspace_override)
            # Bootstrap minimale del workspace dummy: crea le cartelle base per evitare
            # fallimenti di validazione (raw/semantic/book/logs/config).
            for child in ("raw", "semantic", "book", "logs", "config", "normalized"):
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

        logger.info(
            "tools.gen_dummy_kb.control_plane",
            extra={"slug": slug, "timmy_beta_strict": os.environ.get("TIMMY_BETA_STRICT")},
        )
        logger.info(
            "tools.gen_dummy_kb.mode",
            extra={"mode": mode_label, "local_only": local_only_override},
        )

        enable_drive = not local_only_override

        if workspace_override:
            for child in ("raw", "semantic", "book", "logs", "config", "normalized"):
                (workspace_override / child).mkdir(parents=True, exist_ok=True)

        policy = DummyPolicy(
            mode=mode_label,
            strict=True,  # policy interna dummy (non coincide con TIMMY_BETA_STRICT)
            ci=args.ci,
            allow_downgrade=args.allow_downgrade,
            require_registry=True,
        )
        if policy.ci and policy.allow_downgrade:
            msg = "--allow-downgrade non è consentito durante la CI"
            health = build_hardcheck_health("DUMMY_POLICY_INVALID", msg, mode=policy.mode)
            if HardCheckError is not None:
                raise HardCheckError(msg, health)
            raise SystemExit(msg)

        try:
            workspace_root = workspace_override or _client_base(slug)
            _clean_local_workspace_before_generation(
                slug=slug,
                logger=logger,
                workspace_override=workspace_override,
            )
            for child in ("raw", "semantic", "book", "logs", "config", "normalized"):
                (workspace_root / child).mkdir(parents=True, exist_ok=True)

            payload = build_payload(
                slug=slug,
                client_name=client_name,
                enable_drive=enable_drive,
                enable_vision=enable_vision,
                enable_semantic=enable_semantic,
                enable_enrichment=enable_enrichment,
                enable_preview=enable_preview,
                records_hint=records_hint,
                logger=logger,
                deep_testing=args.deep_testing,
                policy=policy,
                allow_local_only_override=local_only_override,
            )
            emit_structure(payload)
            return 0
        except Exception as exc:
            if HardCheckError is not None and isinstance(exc, HardCheckError):
                logger.error(
                    "tools.gen_dummy_kb.hardcheck.failed",
                    extra={"slug": slug, "error": str(exc)},
                )
                payload = {"slug": slug, "client_name": client_name, "health": exc.health}
                emit_structure(payload)
                return 1
            logger.error(
                "tools.gen_dummy_kb.run_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            emit_structure({"error": str(exc)}, stream=sys.stderr)
            return 1
    finally:
        # cache UI base (se importabile)
        try:
            from ui.utils.workspace import clear_base_cache  # late import per evitare dipendenze circolari
        except Exception:  # pragma: no cover
            clear_base_cache = None  # type: ignore[assignment]
        if callable(clear_base_cache):
            clear_base_cache(slug=slug)

        # Ripristina gli override locali impostati da questo tool.
        if args.base_dir:
            if prev_repo_root_dir is None:
                os.environ.pop("REPO_ROOT_DIR", None)
            else:
                os.environ["REPO_ROOT_DIR"] = prev_repo_root_dir
            if prev_workspace_root_dir is None:
                os.environ.pop("WORKSPACE_ROOT_DIR", None)
            else:
                os.environ["WORKSPACE_ROOT_DIR"] = prev_workspace_root_dir

        if prev_vision_mode is None:
            os.environ.pop("VISION_MODE", None)
        else:
            os.environ["VISION_MODE"] = prev_vision_mode

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
