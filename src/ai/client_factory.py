# SPDX-License-Identifier: GPL-3.0-or-later
# src/ai/client_factory.py
from __future__ import annotations

from pathlib import Path
from typing import Dict

from pipeline.beta_flags import is_beta_strict
from pipeline.capabilities import get_openai_ctor
from pipeline.env_constants import REPO_ROOT_ENV, WORKSPACE_ROOT_ENV
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings


def _normalize_base_url(raw: str) -> str:
    base = raw.strip()
    if not base:
        return "https://api.openai.com/v1"
    if "://" not in base:
        base = "https://" + base
    if not base.rstrip("/").endswith("/v1"):
        base = base.rstrip("/") + "/v1"
    return base


def make_openai_client():
    """
    Costruisce un client OpenAI (SDK >= 2) applicando le policy del progetto.

    Richiede che `OPENAI_API_KEY` sia impostata.
    """
    ensure_dotenv_loaded()

    try:
        api_key = get_env_var("OPENAI_API_KEY", required=True)
    except KeyError as exc:
        raise ConfigError(
            "Manca la API key. Imposta la variabile di ambiente OPENAI_API_KEY.",
            code="openai.client.config.invalid",
            component="client_factory",
        ) from exc

    OpenAI = get_openai_ctor()

    default_headers: Dict[str, str] = {"OpenAI-Beta": "assistants=v2"}
    client_kwargs: Dict[str, object] = {
        "api_key": api_key,
        "default_headers": default_headers,
    }

    base_url_env = get_env_var("OPENAI_BASE_URL", default=None)
    project_env = get_env_var("OPENAI_PROJECT", default=None)
    settings_obj = _load_settings()
    openai_cfg = settings_obj.openai_settings
    client_kwargs["timeout"] = float(openai_cfg.timeout)
    client_kwargs["max_retries"] = int(openai_cfg.max_retries)
    if openai_cfg.http2_enabled:
        client_kwargs["http2"] = True
    LOGGER.info("openai.client.config_from_yaml", extra={"source": "config"})

    if base_url_env:
        client_kwargs["base_url"] = _normalize_base_url(base_url_env)
    if project_env:
        client_kwargs["project"] = project_env

    try:
        return OpenAI(**client_kwargs)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ConfigError(
            "La versione del pacchetto 'openai' è troppo vecchia per questi parametri. Aggiorna a openai>=2.0.",
            code="openai.client.config.invalid",
            component="client_factory",
        ) from exc


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _reject_repo_sentinels(root: Path, *, context: str) -> None:
    if (root / ".git").exists() or (root / "pyproject.toml").exists():
        raise ConfigError(
            f"{context} non valido: punta alla repo root, non al workspace.",
            code="config.root.invalid",
            component="client_factory",
        )


def _resolve_settings_root() -> Path:
    workspace_root = get_env_var(WORKSPACE_ROOT_ENV, default=None)
    repo_root_env = get_env_var(REPO_ROOT_ENV, default=None)
    if workspace_root:
        try:
            resolved = Path(str(workspace_root)).expanduser().resolve()
        except Exception as exc:
            raise ConfigError(
                f"{WORKSPACE_ROOT_ENV} non valido: {workspace_root}",
                code="config.root.invalid",
                component="client_factory",
            ) from exc
        _reject_repo_sentinels(resolved, context=WORKSPACE_ROOT_ENV)
        return resolved
    if is_beta_strict():
        raise ConfigError(
            f"{WORKSPACE_ROOT_ENV} mancante: in strict mode la config deve provenire dal workspace.",
            code="config.root.missing",
            component="client_factory",
        )
    if repo_root_env:
        try:
            return Path(str(repo_root_env)).expanduser().resolve()
        except Exception as exc:
            raise ConfigError(
                f"{REPO_ROOT_ENV} non valido: {repo_root_env}",
                code="config.root.invalid",
                component="client_factory",
            ) from exc
    return _REPO_ROOT


def _load_settings() -> Settings:
    try:
        root = _resolve_settings_root()
        return Settings.load(root)
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ConfigError):
            raise
        # Beta 1.0 STRICT: niente degradazioni silenziose in runtime.
        # Se la config globale non è caricabile è un errore di provisioning.
        try:
            LOGGER.error(
                "openai.client.settings_load_failed",
                extra={"error": repr(exc), "repo_root": str(_REPO_ROOT)},
            )
        except Exception:
            # In caso di logger non disponibile o handler rotti, non mascheriamo l'errore.
            pass
        raise ConfigError(
            "Impossibile caricare la configurazione globale (config/config.yaml). "
            "In Beta 1.0 il runtime è strict: correggi la config o il provisioning e riprova.",
            code="openai.client.settings.load_failed",
            component="client_factory",
        ) from exc


LOGGER = get_structured_logger("ai.client_factory")
