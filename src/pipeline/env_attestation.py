# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from inspect import Parameter
from inspect import signature as inspect_signature
from pathlib import Path
from typing import Any, Mapping

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.paths import get_repo_root

LOGGER = get_structured_logger("pipeline.env_attestation")

ATTESTATION_RELATIVE_PATH = Path(".timmy") / "env_attestation.json"
REQUIRED_OPENAI_VERSION = "2.3.0"
_REQUIREMENTS_FILES: tuple[str, ...] = ("requirements.txt", "requirements-dev.txt")
_ATTESTATION_OK_CACHE: dict[tuple[str, str], bool] = {}


@dataclass(frozen=True, slots=True)
class EnvAttestationStatus:
    ok: bool
    path: Path
    errors: tuple[str, ...]


def _attestation_path(repo_root: Path) -> Path:
    return ensure_within_and_resolve(repo_root, repo_root / ATTESTATION_RELATIVE_PATH)


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _requirements_hashes(repo_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in _REQUIREMENTS_FILES:
        candidate = ensure_within_and_resolve(repo_root, repo_root / rel)
        if not candidate.exists():
            continue
        raw = read_text_safe(repo_root, candidate, encoding="utf-8")
        hashes[rel] = _sha256_text(raw)
    if not hashes:
        raise ConfigError(
            "Nessun file requirements trovato per l'attestazione ambiente.",
            file_path=str(repo_root),
            code="env.attestation.requirements_missing",
            component="pipeline.env_attestation",
        )
    return dict(sorted(hashes.items()))


def _openai_runtime_probe() -> dict[str, Any]:
    try:
        import openai  # type: ignore
    except Exception as exc:  # pragma: no cover - dipende dall'ambiente
        raise ConfigError(
            f"Import openai fallito: {type(exc).__name__}: {exc}",
            code="env.attestation.openai_import_failed",
            component="pipeline.env_attestation",
        ) from exc

    try:
        openai_version = metadata.version("openai")
    except Exception as exc:
        raise ConfigError(
            f"Impossibile leggere la versione del pacchetto openai: {exc}",
            code="env.attestation.openai_version_missing",
            component="pipeline.env_attestation",
        ) from exc

    if openai_version != REQUIRED_OPENAI_VERSION:
        raise ConfigError(
            f"Versione openai non valida: trovata {openai_version}, richiesta {REQUIRED_OPENAI_VERSION}.",
            code="env.attestation.openai_version_mismatch",
            component="pipeline.env_attestation",
        )

    try:
        client = openai.OpenAI(api_key="attestation-check")
    except Exception as exc:
        raise ConfigError(
            f"Inizializzazione OpenAI client fallita: {exc}",
            code="env.attestation.client_init_failed",
            component="pipeline.env_attestation",
        ) from exc

    responses_api = getattr(client, "responses", None)
    create_fn = getattr(responses_api, "create", None) if responses_api is not None else None
    if not callable(create_fn):
        raise ConfigError(
            "responses.create assente o non invocabile.",
            code="env.attestation.responses_missing",
            component="pipeline.env_attestation",
        )

    signature = inspect_signature(create_fn)
    params = list(signature.parameters.values())
    supports_text = "text" in signature.parameters or any(param.kind is Parameter.VAR_KEYWORD for param in params)
    if not supports_text:
        raise ConfigError(
            "responses.create non supporta text.format.",
            code="env.attestation.responses_signature_invalid",
            component="pipeline.env_attestation",
        )

    return {
        "openai_version": openai_version,
        "responses_create_signature": str(signature),
        "responses_create_supports_text": True,
    }


def build_env_attestation_payload(
    *,
    repo_root: Path | None = None,
    installed_by: str | None = None,
) -> dict[str, Any]:
    root = repo_root or get_repo_root(allow_env=False)
    runtime_probe = _openai_runtime_probe()
    payload: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "sys_executable": str(Path(sys.executable).resolve()),
        "openai_required_version": REQUIRED_OPENAI_VERSION,
        "openai_version": runtime_probe["openai_version"],
        "responses_create_signature": runtime_probe["responses_create_signature"],
        "responses_create_supports_text": runtime_probe["responses_create_supports_text"],
        "requirements_hashes": _requirements_hashes(root),
        "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    if installed_by:
        payload["installed_by"] = installed_by
    return payload


def write_env_attestation(
    *,
    repo_root: Path | None = None,
    installed_by: str | None = None,
) -> Path:
    root = repo_root or get_repo_root(allow_env=False)
    path = _attestation_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_env_attestation_payload(repo_root=root, installed_by=installed_by)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    safe_write_text(path, serialized, encoding="utf-8", atomic=True)
    LOGGER.info(
        "env.attestation.written",
        extra={"file_path": str(path), "openai_version": payload["openai_version"]},
    )
    return path


def _load_env_attestation(repo_root: Path) -> Mapping[str, Any]:
    path = _attestation_path(repo_root)
    if not path.exists():
        raise ConfigError(
            "Attestato ambiente mancante. Esegui: python -m timmy_kb.cli env-attest",
            file_path=str(path),
            code="env.attestation.missing",
            component="pipeline.env_attestation",
        )
    raw = read_text_safe(repo_root, path, encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "Attestato ambiente JSON non valido.",
            file_path=str(path),
            code="env.attestation.invalid_json",
            component="pipeline.env_attestation",
        ) from exc
    if not isinstance(payload, Mapping):
        raise ConfigError(
            "Attestato ambiente non valido: atteso oggetto JSON.",
            file_path=str(path),
            code="env.attestation.invalid_shape",
            component="pipeline.env_attestation",
        )
    return payload


def validate_env_attestation(*, repo_root: Path | None = None) -> EnvAttestationStatus:
    root = repo_root or get_repo_root(allow_env=False)
    path = _attestation_path(root)
    errors: list[str] = []

    try:
        payload = _load_env_attestation(root)
    except ConfigError as exc:
        base_message = str(exc.args[0]) if exc.args else str(exc)
        return EnvAttestationStatus(ok=False, path=path, errors=(base_message,))

    expected_python = sys.version.split()[0]
    actual_python = str(payload.get("python_version", ""))
    if actual_python != expected_python:
        errors.append(f"python_version mismatch: atteso {expected_python}, attestato {actual_python}")

    expected_exe = str(Path(sys.executable).resolve())
    actual_exe = str(payload.get("sys_executable", ""))
    if actual_exe != expected_exe:
        errors.append(f"sys.executable mismatch: atteso {expected_exe}, attestato {actual_exe}")

    try:
        current_openai = metadata.version("openai")
    except Exception as exc:
        errors.append(f"openai version unreadable: {exc}")
        current_openai = ""

    if current_openai != REQUIRED_OPENAI_VERSION:
        errors.append(f"openai mismatch: atteso {REQUIRED_OPENAI_VERSION}, trovato {current_openai or 'unknown'}")

    attested_openai = str(payload.get("openai_version", ""))
    if attested_openai != REQUIRED_OPENAI_VERSION:
        errors.append(
            "attestato openai_version non conforme: "
            f"atteso {REQUIRED_OPENAI_VERSION}, attestato {attested_openai or 'unknown'}"
        )

    supports_text = bool(payload.get("responses_create_supports_text", False))
    if not supports_text:
        errors.append("responses_create_supports_text=false nell'attestato")

    attested_hashes_raw = payload.get("requirements_hashes")
    if not isinstance(attested_hashes_raw, Mapping):
        errors.append("requirements_hashes assente o non valido nell'attestato")
    else:
        expected_hashes = _requirements_hashes(root)
        attested_hashes = {str(k): str(v) for k, v in attested_hashes_raw.items()}
        if attested_hashes != expected_hashes:
            errors.append("requirements_hashes mismatch: rieseguire env-attest")

    return EnvAttestationStatus(ok=not errors, path=path, errors=tuple(errors))


def ensure_env_attestation(*, repo_root: Path | None = None) -> None:
    root = repo_root or get_repo_root(allow_env=False)
    cache_key = (str(root.resolve()), str(Path(sys.executable).resolve()))
    if _ATTESTATION_OK_CACHE.get(cache_key, False):
        return

    status = validate_env_attestation(repo_root=root)
    if status.ok:
        _ATTESTATION_OK_CACHE[cache_key] = True
        return
    detail = "; ".join(status.errors)
    LOGGER.error(
        "env.attestation.invalid",
        extra={"file_path": str(status.path), "errors": list(status.errors)},
    )
    raise ConfigError(
        f"Environment invalid - reinstall required. {detail}",
        file_path=str(status.path),
        code="env.attestation.invalid",
        component="pipeline.env_attestation",
    )
