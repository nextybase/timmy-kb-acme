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
import sys
from pathlib import Path
from typing import Any, Optional

import yaml


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
except Exception:
    ensure_drive_minimal_and_upload_config = None
    build_drive_from_mapping = None

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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)

    def _safe_write_bytes(path: Path, data: bytes, *, atomic=False) -> None:  # type: ignore
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


# Compat: test_gen_dummy_kb_import_safety si aspetta che gli attributi pubblici siano None finch� non si esegue il tool.
safe_write_text = None  # type: ignore
safe_write_bytes = None  # type: ignore
_fin_import_csv = None  # type: ignore


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

_DEFAULT_VISION_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 2\n0000000000 65535 f \n0000000010 00000 n \n"
    b"trailer\n<< /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
class _Ctx:
    """Contesto minimo compatibile con run_vision (serve .base_dir)."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


def _client_base(slug: str) -> Path:
    env_root = get_env_var("REPO_ROOT_DIR", default=None)
    if env_root:
        try:
            return Path(env_root).expanduser().resolve()
        except Exception:
            pass
    return REPO_ROOT / "output" / f"timmy-kb-{slug}"


def _pdf_path(slug: str) -> Path:
    return _client_base(slug) / "config" / "VisionStatement.pdf"


def _write_basic_semantic_yaml(base_dir: Path, *, slug: str, client_name: str) -> dict[str, str]:
    """
    Genera YAML "basici" senza passare da Vision:
      - semantic/semantic_mapping.yaml
      - semantic/cartelle_raw.yaml
    Crea anche le cartelle raw/ di base (contracts/reports/presentations).
    """
    sem_dir = base_dir / "semantic"
    sem_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = base_dir / "raw"
    for name in ("contracts", "reports", "presentations"):
        (raw_dir / name).mkdir(parents=True, exist_ok=True)

    mapping = {
        "context": {"slug": slug, "client_name": client_name},
        "contracts": {
            "ambito": "Contrattualistica e forniture",
            "descrizione": "Documenti contrattuali, NDA, ordini di acquisto, accordi quadro e appendici.",
            "keywords": ["contratto", "NDA", "fornitore", "ordine", "appendice"],
        },
        "reports": {
            "ambito": "Reportistica e analisi",
            "descrizione": "Report periodici, metriche operative, analisi interne e rendicontazioni.",
            "keywords": ["report", "analisi", "rendiconto", "KPI", "metriche"],
        },
        "presentations": {
            "ambito": "Presentazioni e materiali",
            "descrizione": "Slide, presentazioni per stakeholder, materiali divulgativi e executive brief.",
            "keywords": ["presentazione", "slide", "deck", "brief", "stakeholder"],
        },
        "synonyms": {
            "contracts": ["contratti", "accordi", "forniture"],
            "reports": ["rendiconti", "analitiche", "reportistica"],
            "presentations": ["slide", "deck", "presentazioni"],
        },
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
    }
    cartelle = {
        "folders": ["raw/contracts", "raw/reports", "raw/presentations"],
        "system_folders": {"identity": "book/identity", "glossario": "book/glossario"},
        "meta": {"source": "dummy", "slug": slug},
    }

    mapping_path = sem_dir / "semantic_mapping.yaml"
    cartelle_path = sem_dir / "cartelle_raw.yaml"
    _safe_write_text(mapping_path, yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False))
    _safe_write_text(cartelle_path, yaml.safe_dump(cartelle, allow_unicode=True, sort_keys=False))

    # Genera contenuti minimi in book/ per i test smoke (alpha/beta + README/SUMMARY).
    book_dir = base_dir / "book"
    book_dir.mkdir(parents=True, exist_ok=True)
    defaults = {
        "alpha.md": "# Alpha\n\nContenuto di esempio per la cartella contracts.\n",
        "beta.md": "# Beta\n\nContenuto di esempio per la cartella reports.\n",
        "README.md": "# Dummy KB\n",
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
    }
    for name, content in defaults.items():
        target = book_dir / name
        if not target.exists():
            _safe_write_text(target, content, encoding="utf-8", atomic=True)

    return {"mapping": str(mapping_path), "cartelle": str(cartelle_path)}


def _call_drive_min(slug: str, client_name: str, base_dir: Path, logger: logging.Logger) -> Optional[dict[str, Any]]:
    """Chiama ensure_drive_minimal_and_upload_config con firme UI. Skip silenzioso se non disponibile."""
    if not callable(ensure_drive_minimal_and_upload_config):
        return None
    ctx = _Ctx(base_dir)
    try:
        # firma principale (ctx, slug, client_folder_id=None, logger=None)
        return ensure_drive_minimal_and_upload_config(ctx, slug=slug, client_folder_id=None, logger=logger)  # type: ignore[arg-type]
    except TypeError:
        # fallback legacy: (slug, client_name)
        return ensure_drive_minimal_and_upload_config(slug=slug, client_name=client_name)  # type: ignore[misc]


def _call_drive_build_from_mapping(
    slug: str, client_name: str, base_dir: Path, logger: logging.Logger
) -> Optional[dict[str, Any]]:
    """Chiama build_drive_from_mapping come fa la UI (se disponibile)."""
    if not callable(build_drive_from_mapping):
        return None
    return build_drive_from_mapping(slug=slug, client_name=client_name)  # type: ignore[misc]


def _register_client(slug: str, client_name: str) -> None:
    """Registra il cliente nel registry UI come fa la pagina UI."""
    if ClientEntry and upsert_client and set_state:
        entry = ClientEntry(slug=slug, nome=client_name, stato="nuovo")  # type: ignore[call-arg]
        upsert_client(entry)  # type: ignore[misc]
        set_state(slug, "nuovo")  # type: ignore[misc]


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    ensure_dotenv_loaded()

    ap = argparse.ArgumentParser(
        description="Genera una KB dummy usando gli entry-point della UI (pre_onboarding + Vision + (Drive opz.))."
    )
    ap.add_argument("--slug", default="dummy", help="Slug del cliente (default: dummy)")
    ap.add_argument("--name", default=None, help='Nome visuale del cliente (default: "Dummy <slug>")')
    # Nuove opzioni richieste: disabilitare Drive / Vision
    ap.add_argument("--no-drive", action="store_true", help="Disabilita tutti i passi Drive")
    ap.add_argument("--no-vision", action="store_true", help="Non invocare Vision: genera YAML basici")
    # Back-compat (non usato dalla UI nuova): se qualcuno passa --with-drive
    ap.add_argument("--with-drive", action="store_true", help="(Legacy) Abilita Drive se possibile")
    # Opzioni legacy mantenute per compatibilità con test/script esistenti
    ap.add_argument(
        "--base-dir",
        default=None,
        help="(Legacy) Directory radice in cui creare il workspace (override di REPO_ROOT_DIR).",
    )
    ap.add_argument(
        "--clients-db",
        dest="clients_db",
        default=None,
        help="(Legacy) Percorso file clients_db.yaml; imposta CLIENTS_DB_DIR sulla cartella indicata.",
    )
    ap.add_argument(
        "--records",
        default=None,
        help="(Legacy) Numero di record finanza da generare (non più utilizzato).",
    )
    args = ap.parse_args(argv)

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

    # Gestione override legacy: REPO_ROOT_DIR e CLIENTS_DB_DIR
    prev_repo_root_dir = os.environ.get("REPO_ROOT_DIR")
    prev_clients_db_dir = os.environ.get("CLIENTS_DB_DIR")
    workspace_override: Optional[Path] = None
    try:
        if args.base_dir:
            base_override = Path(args.base_dir).expanduser().resolve()
            workspace_override = base_override / f"timmy-kb-{slug}"
            os.environ["REPO_ROOT_DIR"] = str(workspace_override)

        clients_db_path: Optional[Path] = None
        if args.clients_db:
            clients_db_path = Path(args.clients_db).expanduser().resolve()
            clients_db_path.parent.mkdir(parents=True, exist_ok=True)
            os.environ["CLIENTS_DB_DIR"] = str(clients_db_path.parent)

        # Logger stile UI
        logger = get_structured_logger("tools.gen_dummy_kb")
        logger.setLevel(logging.INFO)

        if records_hint:
            try:
                _ = int(records_hint)
            except Exception:
                logger.debug("records_hint_non_numeric", extra={"value": records_hint})

        try:
            # 0) PDF Vision dalla root del repo
            repo_pdf = REPO_ROOT / "config" / "VisionStatement.pdf"
            if repo_pdf.exists():
                try:
                    safe_pdf = ensure_within_and_resolve(REPO_ROOT, repo_pdf)
                    with open_for_read_bytes_selfguard(safe_pdf) as handle:
                        pdf_bytes = handle.read()
                except Exception:
                    logger.warning("vision_statement_template_unreadable", extra={"file_path": str(repo_pdf)})
                    pdf_bytes = _DEFAULT_VISION_PDF
            else:
                logger.warning("vision_statement_template_missing", extra={"file_path": str(repo_pdf)})
                pdf_bytes = _DEFAULT_VISION_PDF

            # 1) Workspace locale (UI helper)
            ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=pdf_bytes)

            base_dir = _client_base(slug)
            pdf_path = _pdf_path(slug)

            # 2) Drive (opzionale)
            drive_min_info = drive_build_info = None
            if enable_drive:
                try:
                    drive_min_info = _call_drive_min(slug, client_name, base_dir, logger)
                    drive_build_info = _call_drive_build_from_mapping(slug, client_name, base_dir, logger)
                except Exception as e:
                    logger.warning("drive_provisioning_failed", extra={"error": str(e)})

            # 3) Vision o YAML basici
            if enable_vision:
                ctx = _Ctx(base_dir)
                run_vision(ctx, slug=slug, pdf_path=pdf_path, logger=logger)
            else:
                _write_basic_semantic_yaml(base_dir, slug=slug, client_name=client_name)

            # 4) Registry UI
            _register_client(slug, client_name)

            # 5) Output diagnostico
            cfg_out: dict[str, Any] = {}
            if callable(get_client_config) and ClientContext:
                try:
                    ctx_cfg = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)  # type: ignore[misc]
                    cfg = get_client_config(ctx_cfg) or {}
                    cfg_out = {
                        "drive_folder_id": cfg.get("drive_folder_id"),
                        "drive_raw_folder_id": cfg.get("drive_raw_folder_id"),
                    }
                except Exception:
                    cfg_out = {}

            result = {
                "slug": slug,
                "client_name": client_name,
                "paths": {
                    "base": str(base_dir),
                    "config": str(base_dir / "config" / "config.yaml"),
                    "vision_pdf": str(pdf_path),
                    "semantic_mapping": str(base_dir / "semantic" / "semantic_mapping.yaml"),
                    "cartelle_raw": str(base_dir / "semantic" / "cartelle_raw.yaml"),
                },
                "drive_min": drive_min_info or {},
                "drive_build": drive_build_info or {},
                "config_ids": cfg_out,
                "vision_used": bool(enable_vision),
                "drive_used": bool(enable_drive),
            }
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            return 0

        except Exception as e:
            logger.error("dummy_kb_failed", extra={"slug": slug, "error": str(e)})
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            return 1
    finally:
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


if __name__ == "__main__":
    raise SystemExit(main())
