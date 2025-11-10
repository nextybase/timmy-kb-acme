# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/oidc_utils.py
from __future__ import annotations

import json
import os
import pathlib
import typing
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Mapping, Optional

from pipeline.env_utils import get_env_var
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe

log = get_structured_logger("pipeline.oidc")


class OIDCError(RuntimeError):
    """Errore generico per il flusso OIDC."""


class OIDCConfig(typing.TypedDict, total=False):
    provider: str
    audience_env: str
    issuer_url_env: str
    role_arn_env: str
    gcp_provider_env: str
    azure_fedcred_env: str
    ci_required: bool
    vault: Dict[str, str]


def _read_yaml_settings(settings: Mapping[str, typing.Any]) -> OIDCConfig:
    """Estrae la sezione security.oidc dal settings YAML."""
    if not isinstance(settings, Mapping):
        return typing.cast(OIDCConfig, {})
    security = typing.cast(Mapping[str, typing.Any], settings.get("security") or {})
    oidc_cfg = typing.cast(OIDCConfig, security.get("oidc") or {})
    return oidc_cfg


def _github_actions_idtoken(audience: str) -> Optional[str]:
    """Ottiene un ID token OIDC nativo da GitHub Actions usando le ENV built-in.
    Ritorna None se non in ambiente Actions."""
    url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
    req_token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not req_token:
        return None
    try:
        url_with_aud = f"{url}{'&' if '?' in url else '?'}audience={urllib.parse.quote(audience)}"
        request = urllib.request.Request(url_with_aud)  # noqa: S310
        request.add_header("Authorization", f"Bearer {req_token}")
        opener = urllib.request.build_opener()
        with opener.open(request, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            token = typing.cast(str, payload.get("value") or "")
            return token or None
    except Exception as exc:
        log.error("oidc.github.token_error", extra={"event": "oidc_error", "error": str(exc)})
        raise OIDCError("Impossibile ottenere ID token OIDC da GitHub Actions") from exc


def _read_local_jwt(path: str) -> str:
    """Legge un file JWT locale (ad esempio per sviluppo)."""
    p = pathlib.Path(path).expanduser()
    return read_text_safe(pathlib.Path.cwd(), p, encoding="utf-8").strip()


def _vault_login_with_jwt(addr: str, role: str, jwt: str) -> str:
    """Esegue login JWT standard su Vault: POST /v1/auth/jwt/login."""
    payload = json.dumps({"role": role, "jwt": jwt}).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        f"{addr.rstrip('/')}/v1/auth/jwt/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        opener = urllib.request.build_opener()
        with opener.open(request, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            token = typing.cast(str, body.get("auth", {}).get("client_token") or "")
            if not token:
                raise OIDCError("Vault non ha restituito client_token")
            return token
    except urllib.error.HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="ignore")
        log.error("oidc.vault.http_error", extra={"event": "oidc_error", "status": exc.code})
        raise OIDCError(f"Vault login HTTP {exc.code}: {msg[:200]}") from exc
    except Exception as exc:  # pragma: no cover - best effort logging
        log.error("oidc.vault.error", extra={"event": "oidc_error", "error": str(exc)})
        raise


def ensure_oidc(settings: Mapping[str, typing.Any]) -> Dict[str, str]:
    """Esegue il wiring OIDC basandosi su security.oidc.

    Se `enabled` è True:
      - recupera l'ID token (GitHub Actions o file locale),
      - opzionalmente effettua il login Vault,
      - ritorna un dizionario di ENV informative da propagare.
    """
    cfg = _read_yaml_settings(settings)
    if not cfg or not cfg.get("enabled"):
        log.info("oidc.disabled", extra={"event": "oidc_disabled"})
        return {}

    provider = (cfg.get("provider") or os.getenv("OIDC_PROVIDER") or "").strip().lower()
    if not provider:
        raise OIDCError("OIDC provider non configurato")

    audience_env = cfg.get("audience_env") or "OIDC_AUDIENCE"
    issuer_env = cfg.get("issuer_url_env") or "OIDC_ISSUER_URL"
    audience = get_env_var(audience_env, default="") or ""
    issuer = get_env_var(issuer_env, default="") or ""

    id_token = ""
    if audience:
        id_token = _github_actions_idtoken(audience) or ""
    if not id_token:
        jwt_path_env = (cfg.get("vault") or {}).get("jwt_path_env") or "OIDC_JWT_PATH"
        jwt_path = get_env_var(jwt_path_env, default="")
        if jwt_path:
            id_token = _read_local_jwt(jwt_path)

    if not id_token:
        if cfg.get("ci_required"):
            raise OIDCError("OIDC richiesto ma ID token assente")
        log.warning("oidc.no_token", extra={"event": "oidc_missing"})
        return {}

    out: Dict[str, str] = {
        "OIDC_ID_TOKEN": id_token,
        "OIDC_ISSUER_URL": issuer,
        "OIDC_AUDIENCE": audience,
    }

    if provider == "vault":
        vault_cfg = cfg.get("vault") or {}
        addr_env = vault_cfg.get("addr_env") or "VAULT_ADDR"
        role_env = vault_cfg.get("role_env") or "VAULT_ROLE"
        try:
            addr = get_env_var(addr_env, required=True) or ""
            role = get_env_var(role_env, required=True) or ""
        except KeyError as exc:
            raise OIDCError(str(exc)) from exc
        vault_token = _vault_login_with_jwt(addr, role, id_token)
        os.environ["VAULT_TOKEN"] = vault_token
        out["VAULT_TOKEN"] = "<set>"  # noqa: S105
        log.info("oidc.vault.login_ok", extra={"event": "oidc_vault_ok"})
    elif provider in {"aws", "gcp", "azure", "generic"}:
        log.info("oidc.idtoken.ready", extra={"event": "oidc_idtoken_ready", "provider": provider})
    else:
        raise OIDCError(f"Provider OIDC non supportato: {provider}")

    role_env = cfg.get("role_arn_env")
    if role_env:
        out["OIDC_ROLE_ARN_ENV"] = role_env
    if cfg.get("gcp_provider_env"):
        out["OIDC_GCP_PROVIDER_ENV"] = cfg["gcp_provider_env"]
    if cfg.get("azure_fedcred_env"):
        out["OIDC_AZURE_FEDCRED_ENV"] = cfg["azure_fedcred_env"]

    return out


__all__ = [
    "OIDCConfig",
    "OIDCError",
    "ensure_oidc",
]
