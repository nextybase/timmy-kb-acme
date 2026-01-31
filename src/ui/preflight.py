# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import json
import socket
from pathlib import Path
from typing import Any, Iterable, List, Tuple, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

import pipeline.env_utils as _env_utils
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

CheckItem = Tuple[str, bool, str]


def _logger():
    return get_structured_logger("ui.preflight")


DEPENDENCY_CHECKS = [
    ("PyMuPDF", "fitz", "pip install pymupdf"),
    ("ReportLab", "reportlab", "pip install reportlab"),
    ("Google API Client", "googleapiclient.discovery", "pip install google-api-python-client"),
]


def _maybe_load_dotenv() -> None:
    """Carica .env solo quando serve (no side-effects a import-time)."""
    env_path = Path(".env")
    _env_utils._ENV_LOADED = False
    try:
        loaded = ensure_dotenv_loaded(strict=True)
    except Exception as exc:
        _logger().error(
            "ui.preflight.dotenv_error",
            extra={"path": str(env_path)},
        )
        raise ConfigError("dotenv load failed", file_path=str(env_path)) from exc
    _logger().info(
        "ui.preflight.dotenv_loaded",
        extra={"loaded": bool(loaded), "path": str(env_path)},
    )


def _is_importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def _docker_ok() -> tuple[bool, str]:
    from pipeline.docker_utils import check_docker_status

    status, hint = check_docker_status()
    return bool(status), str(hint or "")


def _pipeline_origin_ok() -> tuple[bool, str]:
    """
    Verifica che i moduli core siano importabili dalla stessa root della UI.
    In caso di venv incoerente segnala un hint per l'installazione editable.
    """
    try:
        import pipeline.context as _ctx
    except Exception as exc:  # pragma: no cover - ambiente minimale
        return (
            False,
            "Moduli di pipeline non importabili "
            f"({exc}). Attiva il venv corretto ed esegui `pip install -e .` dalla root del repo.",
        )

    pkg_file_raw = getattr(_ctx, "__file__", None)
    if not pkg_file_raw:
        return True, "Origine moduli pipeline non determinabile (__file__ mancante)."
    try:
        pkg_file = Path(pkg_file_raw).resolve()
    except Exception:
        return True, "Origine moduli pipeline non determinabile (__file__ mancante)."

    ui_root = Path(__file__).resolve().parents[1]
    pkg_root = pkg_file.parents[1]
    if ui_root == pkg_root:
        return True, f"OK (UI e pipeline allineate in {pkg_root})"

    hint = (
        "UI e pipeline provengono da root diversi.\n"
        f" - UI: {ui_root}\n"
        f" - pipeline: {pkg_root}\n"
        "Probabile installazione vecchia nel venv. "
        "Attiva il venv corretto e riesegui `pip install -e .` nella root del repo."
    )
    try:
        _logger().warning(
            "ui.preflight.pipeline_mismatch",
            extra={"ui_root": str(ui_root), "pkg_root": str(pkg_root)},
        )
    except Exception:
        pass
    return False, hint


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _run_optional_import_checks(defs: Iterable[tuple[str, str, str]]) -> list[CheckItem]:
    """Costruisce i check di import opzionali con hint di installazione."""
    checks: list[CheckItem] = []
    for name, module, hint in defs:
        checks.append((name, _is_importable(module), hint))
    return checks


def _has_openai_key() -> bool:
    if get_env_var("OPENAI_API_KEY", default=None):
        return True
    if st is not None:
        try:
            return bool(st.secrets.get("OPENAI_API_KEY", ""))
        except Exception:
            return False
    return False


def _vision_schema_ok() -> tuple[bool, str]:
    def _resolve_schema_path(repo_root: Path) -> Path:
        from pipeline.path_utils import ensure_within_and_resolve

        return cast(
            Path,
            ensure_within_and_resolve(repo_root, repo_root / "src" / "ai" / "schemas" / "VisionOutput.schema.json"),
        )

    def _load_schema_text(repo_root: Path, schema_path: Path) -> tuple[bool, str]:
        from pipeline.path_utils import read_text_safe

        if not schema_path.exists():
            return False, f"schema mancante: {schema_path}"
        schema_text = read_text_safe(repo_root, schema_path, encoding="utf-8")
        return True, schema_text

    def _parse_schema(schema_text: str) -> tuple[bool, dict[str, Any] | str]:
        try:
            return True, json.loads(schema_text)
        except json.JSONDecodeError as exc:
            return False, f"schema JSON invalido: {exc}"

    def _compare_required(schema: dict[str, Any]) -> tuple[bool, str]:
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        missing = props - required
        extra = required - props
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"mancano in required: {', '.join(sorted(missing))}")
            if extra:
                parts.append(f"required contiene chiavi assenti: {', '.join(sorted(extra))}")
            return False, "; ".join(parts)
        return True, "Vision schema allineato"

    repo_root = Path(__file__).resolve().parents[2]
    schema_path = _resolve_schema_path(repo_root)

    ok, payload = _load_schema_text(repo_root, schema_path)
    if not ok:
        return False, str(payload)

    parsed_ok, parsed = _parse_schema(payload)
    if not parsed_ok:
        return False, str(parsed)

    return _compare_required(cast(dict[str, Any], parsed))


def _collect_schema_checks() -> list[CheckItem]:
    schema_ok, schema_msg = _vision_schema_ok()
    return [("Vision schema", schema_ok, schema_msg)]


def _collect_docker_and_pipeline_checks() -> tuple[list[CheckItem], bool]:
    docker_ok, hint = _docker_ok()
    pipe_ok, pipe_hint = _pipeline_origin_ok()
    return [
        ("Docker", docker_ok, hint or "OK"),
        ("Pipeline install", pipe_ok, pipe_hint),
    ], docker_ok


def _collect_dependency_checks() -> list[CheckItem]:
    return _run_optional_import_checks(DEPENDENCY_CHECKS)


def _collect_env_checks() -> list[CheckItem]:
    return [("OPENAI_API_KEY", _has_openai_key(), "Imposta .env o st.secrets e riavvia")]


def _collect_port_check(docker_ok: bool) -> bool:
    port_val = get_env_var("PORT", default="4000")
    try:
        port_num = int(port_val or "4000")
    except Exception:
        port_num = 4000
    return _port_in_use(port_num) if docker_ok else False


def run_preflight() -> tuple[List[CheckItem], bool]:
    """Esegue i check di preflight (import-safe, dipendenze, schema, porte)."""
    _logger().info("ui.preflight.run_start")
    _maybe_load_dotenv()
    results: List[CheckItem] = []

    results.extend(_collect_schema_checks())

    docker_and_pipe_checks, docker_ok = _collect_docker_and_pipeline_checks()
    results.extend(docker_and_pipe_checks)

    results.extend(_collect_dependency_checks())
    results.extend(_collect_env_checks())

    port_busy = _collect_port_check(docker_ok)
    for name, ok, hint in results:
        if not ok:
            _logger().warning("ui.preflight.check_failed", extra={"check": name, "hint": hint})

    _logger().info(
        "ui.preflight.run_complete",
        extra={"checks": len(results), "port_busy": port_busy},
    )
    return results, port_busy
