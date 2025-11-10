# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utilità minime per integrare OIDC in CI senza effetti collaterali.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, Mapping, Optional, Protocol

from .env_utils import ensure_dotenv_loaded, get_env_var
from .logging_utils import get_structured_logger

if TYPE_CHECKING:  # pragma: no cover
    from .settings import Settings as SettingsType
else:

    class SettingsType(Protocol):
        def as_dict(self) -> Mapping[str, Any]: ...


__all__ = ["fetch_github_id_token", "ensure_oidc_context"]

_LOG_NAME = "pipeline.oidc"


def _read_env(name: str, *, required: bool = False) -> Optional[str]:
    if not name:
        return None
    try:
        value = get_env_var(name, default=None, required=required)
    except Exception:
        return None
    if isinstance(value, str):
        return value
    return None


def fetch_github_id_token(
    audience: str,
    *,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """
    Best-effort: recupera il token OIDC messo a disposizione da GitHub Actions.
    """
    log = logger or get_structured_logger(_LOG_NAME)
    if not audience:
        log.debug("oidc.github.unavailable", extra={"reason": "missing_audience"})
        return None

    req_url = _read_env("ACTIONS_ID_TOKEN_REQUEST_URL")
    req_token = _read_env("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not req_url or not req_token:
        log.debug("oidc.github.unavailable", extra={"reason": "env_missing"})
        return None
    try:
        encoded = urllib.parse.quote_plus(audience)
    except Exception:
        encoded = audience
    if not req_url.startswith("https://"):
        log.warning(
            "oidc.github.unavailable",
            extra={"reason": "invalid_scheme"},
        )
        return None
    sep = "&" if "?" in req_url else "?"
    request = urllib.request.Request(  # noqa: S310 - endpoint GitHub OIDC è sempre HTTPS
        f"{req_url}{sep}audience={encoded}",
        headers={"Authorization": f"Bearer {req_token}"},
    )
    try:
        with getattr(urllib.request, "urlopen")(request, timeout=10) as resp:  # noqa: S310 - chiamata HTTPS controllata
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:  # pragma: no cover - rete non disponibile in locale
        log.warning(
            "oidc.github.token.error",
            extra={"err": str(exc).splitlines()[:1]},
        )
        return None

    token_raw = payload.get("value") or payload.get("id_token")
    token = token_raw if isinstance(token_raw, str) else None
    if token:
        log.info("oidc.github.token.ok")
        return token
    log.debug("oidc.github.token.empty")
    return None


def ensure_oidc_context(
    settings: SettingsType | Mapping[str, Any],
    *,
    logger: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    """
    Risolve i parametri OIDC dal config ed esegue un fetch best-effort del token GitHub.
    Ritorna solo metadati (mai il token).
    """
    log = logger or get_structured_logger(_LOG_NAME)
    ensure_dotenv_loaded()

    data = settings.as_dict() if hasattr(settings, "as_dict") else dict(settings or {})
    security = data.get("security") or {}
    sec_oidc = security.get("oidc") or {}

    enabled = bool(sec_oidc.get("enabled"))
    provider = str(sec_oidc.get("provider") or "github").strip().lower()
    if not enabled:
        log.debug("oidc.disabled")
        return {"enabled": False, "provider": provider, "has_token": False}

    audience_name = str(sec_oidc.get("audience_env") or "")
    role_name = str(sec_oidc.get("role_env") or "")
    token_url_env = str(sec_oidc.get("token_request_url_env") or "")
    token_token_env = str(sec_oidc.get("token_request_token_env") or "")

    # Pre-carica eventuali ENV personalizzate
    audience = _read_env(audience_name)
    role = _read_env(role_name)
    if token_url_env:
        _ = _read_env(token_url_env)  # warm up eventuale env custom
    if token_token_env:
        _ = _read_env(token_token_env)

    has_token = False
    if provider == "github" and audience:
        token = fetch_github_id_token(audience, logger=log)
        has_token = bool(token)

    log.info(
        "oidc.context",
        extra={
            "enabled": True,
            "provider": provider,
            "has_token": has_token,
            "role": role,
        },
    )
    return {
        "enabled": True,
        "provider": provider,
        "has_token": has_token,
        "role": role,
    }
