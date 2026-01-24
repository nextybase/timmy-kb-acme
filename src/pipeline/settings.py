# SPDX-License-Identifier: GPL-3.0-only
"""Loader centralizzato per config/config.yaml con helper typed."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional

from .env_utils import ensure_dotenv_loaded, get_env_var
from .exceptions import ConfigError
from .logging_utils import get_structured_logger
from .yaml_utils import yaml_read

_MISSING = object()
_ENV_DENY_LIST = {
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "GF_SECURITY_ADMIN_PASSWORD",
    "OPENAI_API_KEY",
    "SERVICE_ACCOUNT_FILE",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "TIMMY_OTEL_ENDPOINT",
    "TIMMY_SERVICE_NAME",
    "TIMMY_ENV",
}
_LOGGER = get_structured_logger("pipeline.settings")


def _mapping_or_empty(value: Any, dotted_key: str, *, config_path: Path) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    raise ConfigError(
        f"{dotted_key} deve essere un oggetto YAML (mapping).",
        file_path=str(config_path),
    )


def _extract_bool(value: Any, dotted_key: str, *, config_path: Path, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{dotted_key} deve essere booleano.", file_path=str(config_path))


def _extract_int(
    value: Any,
    dotted_key: str,
    *,
    config_path: Path,
    default: int,
    minimum: Optional[int] = None,
) -> int:
    if value is None:
        result = default
    elif isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{dotted_key} deve essere un intero.", file_path=str(config_path))
    else:
        result = value
    if minimum is not None and result < minimum:
        raise ConfigError(
            f"{dotted_key} deve essere >= {minimum}.",
            file_path=str(config_path),
        )
    return result


def _require_str(
    value: Any,
    dotted_key: str,
    *,
    config_path: Path,
) -> str:
    if value is None:
        raise ConfigError(
            f"Chiave obbligatoria mancante: {dotted_key}",
            file_path=str(config_path),
        )
    if not isinstance(value, str):
        raise ConfigError(
            f"{dotted_key} deve essere una stringa.",
            file_path=str(config_path),
        )
    candidate = value.strip()
    if not candidate:
        raise ConfigError(
            f"{dotted_key} non può essere vuoto.",
            file_path=str(config_path),
        )
    return candidate


def _extract_optional_str(
    value: Any,
    dotted_key: str,
    *,
    config_path: Path,
    default: Optional[str] = None,
    allow_empty: bool = True,
) -> Optional[str]:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{dotted_key} deve essere una stringa.", file_path=str(config_path))
    candidate = value.strip()
    if not candidate and not allow_empty:
        raise ConfigError(f"{dotted_key} non può essere vuoto.", file_path=str(config_path))
    return candidate if candidate or allow_empty else default


def _extract_enum(
    value: Any,
    dotted_key: str,
    *,
    config_path: Path,
    default: str,
    alias_map: Mapping[str, str],
) -> str:
    if value is None:
        candidate = default
    elif isinstance(value, str):
        candidate = value.strip().lower()
    else:
        raise ConfigError(f"{dotted_key} deve essere una stringa.", file_path=str(config_path))
    normalized = alias_map.get(candidate)
    if not normalized:
        allowed = ", ".join(sorted(set(alias_map.values())))
        raise ConfigError(
            f"{dotted_key} deve essere uno tra: {allowed}. Valore fornito: {value!r}",
            file_path=str(config_path),
        )
    return normalized


_VISION_ENGINE_ALIASES: dict[str, str] = {
    "assistant": "assistants",
    "assistant-beta": "assistants",
    "assistant-inline": "assistants",
    "assistants": "assistants",
    "assistants-v2": "assistants",
    "assistants-stream": "assistants-stream",
    "responses": "responses",
    "responses-stream": "responses-stream",
}


@dataclass(frozen=True)
class MetaSection:
    n_ver: int
    data_ver: Optional[str]
    client_name: Optional[str]
    semantic_mapping_yaml: Optional[str]
    vision_statement_pdf: Optional[str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "MetaSection":
        return cls(
            n_ver=_extract_int(
                data.get("N_VER"),
                "meta.N_VER",
                config_path=config_path,
                default=0,
                minimum=0,
            ),
            data_ver=_extract_optional_str(
                data.get("DATA_VER"),
                "meta.DATA_VER",
                config_path=config_path,
                default=None,
                allow_empty=True,
            ),
            client_name=_extract_optional_str(
                data.get("client_name"),
                "meta.client_name",
                config_path=config_path,
                default=None,
                allow_empty=False,
            ),
            semantic_mapping_yaml=_extract_optional_str(
                data.get("semantic_mapping_yaml"),
                "meta.semantic_mapping_yaml",
                config_path=config_path,
                default=None,
            ),
            vision_statement_pdf=_extract_optional_str(
                data.get("vision_statement_pdf"),
                "meta.vision_statement_pdf",
                config_path=config_path,
                default=None,
            ),
        )


@dataclass(frozen=True)
class OpenAISection:
    timeout: int = 120
    max_retries: int = 2
    http2_enabled: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "OpenAISection":
        return cls(
            timeout=_extract_int(
                data.get("timeout"),
                "ai.openai.timeout",
                config_path=config_path,
                default=cls.timeout,
                minimum=1,
            ),
            max_retries=_extract_int(
                data.get("max_retries"),
                "ai.openai.max_retries",
                config_path=config_path,
                default=cls.max_retries,
                minimum=0,
            ),
            http2_enabled=_extract_bool(
                data.get("http2_enabled"),
                "ai.openai.http2_enabled",
                config_path=config_path,
                default=cls.http2_enabled,
            ),
        )


@dataclass(frozen=True)
class VisionSection:
    model: Optional[str]
    engine: str
    assistant_id_env: Optional[str]
    snapshot_retention_days: int
    strict_output: bool
    use_kb: bool = True

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "VisionSection":
        return cls(
            model=_require_str(
                data.get("model"),
                "ai.vision.model",
                config_path=config_path,
            ),
            engine=_extract_enum(
                data.get("engine"),
                "ai.vision.engine",
                config_path=config_path,
                default="assistants",
                alias_map=_VISION_ENGINE_ALIASES,
            ),
            assistant_id_env=_extract_optional_str(
                data.get("assistant_id_env"),
                "ai.vision.assistant_id_env",
                config_path=config_path,
                default=None,
                allow_empty=False,
            ),
            snapshot_retention_days=_extract_int(
                data.get("snapshot_retention_days"),
                "ai.vision.snapshot_retention_days",
                config_path=config_path,
                default=30,
                minimum=0,
            ),
            strict_output=_extract_bool(
                data.get("strict_output"),
                "ai.vision.strict_output",
                config_path=config_path,
                default=True,
            ),
            use_kb=_extract_bool(
                data.get("use_kb"),
                "ai.vision.use_kb",
                config_path=config_path,
                default=True,
            ),
        )


@dataclass(frozen=True)
class UISection:
    skip_preflight: bool = False
    allow_local_only: bool = True
    admin_local_mode: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "UISection":
        return cls(
            skip_preflight=_extract_bool(
                data.get("skip_preflight"),
                "ui.skip_preflight",
                config_path=config_path,
                default=cls.skip_preflight,
            ),
            allow_local_only=_extract_bool(
                data.get("allow_local_only"),
                "ui.allow_local_only",
                config_path=config_path,
                default=cls.allow_local_only,
            ),
            admin_local_mode=_extract_bool(
                data.get("admin_local_mode"),
                "ui.admin_local_mode",
                config_path=config_path,
                default=cls.admin_local_mode,
            ),
        )


@dataclass(frozen=True)
class RetrieverThrottleSection:
    latency_budget_ms: int = 0
    candidate_limit: int = 4000
    parallelism: int = 1
    sleep_ms_between_calls: int = 0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "RetrieverThrottleSection":
        return cls(
            latency_budget_ms=_extract_int(
                data.get("latency_budget_ms"),
                "pipeline.retriever.throttle.latency_budget_ms",
                config_path=config_path,
                default=cls.latency_budget_ms,
                minimum=0,
            ),
            candidate_limit=_extract_int(
                data.get("candidate_limit"),
                "pipeline.retriever.throttle.candidate_limit",
                config_path=config_path,
                default=cls.candidate_limit,
                minimum=0,
            ),
            parallelism=_extract_int(
                data.get("parallelism"),
                "pipeline.retriever.throttle.parallelism",
                config_path=config_path,
                default=cls.parallelism,
                minimum=1,
            ),
            sleep_ms_between_calls=_extract_int(
                data.get("sleep_ms_between_calls"),
                "pipeline.retriever.throttle.sleep_ms_between_calls",
                config_path=config_path,
                default=cls.sleep_ms_between_calls,
                minimum=0,
            ),
        )


@dataclass(frozen=True)
class RetrieverSection:
    auto_by_budget: bool = False
    throttle: RetrieverThrottleSection = field(default_factory=RetrieverThrottleSection)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "RetrieverSection":
        throttle_mapping = _mapping_or_empty(
            data.get("throttle"), "pipeline.retriever.throttle", config_path=config_path
        )
        return cls(
            auto_by_budget=_extract_bool(
                data.get("auto_by_budget"),
                "pipeline.retriever.auto_by_budget",
                config_path=config_path,
                default=cls.auto_by_budget,
            ),
            throttle=RetrieverThrottleSection.from_mapping(throttle_mapping, config_path=config_path),
        )


@dataclass(frozen=True)
class OpsSection:
    log_level: str = "INFO"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, config_path: Path) -> "OpsSection":
        value = _extract_optional_str(
            data.get("log_level"),
            "ops.log_level",
            config_path=config_path,
            default=cls.log_level,
            allow_empty=False,
        )
        return cls(log_level=value or cls.log_level)


@dataclass
class Settings:
    """Wrapper typed attorno alla configurazione YAML del progetto."""

    config_path: Path
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        repo_root: Path,
        *,
        config_path: Optional[Path] = None,
        logger: Optional[logging.Logger] = None,
        slug: Optional[str] = None,
    ) -> "Settings":
        """Carica config/config.yaml (SSoT non segreto) rispettando path-safety.

        Nota: i segreti restano in .env e vanno risolti tramite *_env + resolve_env_ref().
        """
        repo_root = repo_root.resolve()
        cfg_path = (config_path or (repo_root / "config" / "config.yaml")).resolve()
        payload = yaml_read(repo_root, cfg_path) or {}
        instance = cls(config_path=cfg_path, data=payload)
        if logger:
            extra = {"file_path": str(cfg_path)}
            if slug:
                extra["slug"] = slug
            logger.debug("settings.config.loaded", extra=extra)
        return instance

    # --------------------------- Dict-like behaviour ---------------------------

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def keys(self) -> Iterable[str]:
        return self.data.keys()

    def items(self) -> Iterable[tuple[str, Any]]:
        return self.data.items()

    def values(self) -> Iterable[Any]:
        return self.data.values()

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)

    # ----------------------------- Typed accessors -----------------------------

    def _section_mapping(self, dotted_key: str, *, required: bool = False) -> Mapping[str, Any]:
        try:
            raw = self.get_value(dotted_key, default=None)
        except KeyError:
            raw = None
        if raw is None:
            if required:
                raise ConfigError(
                    f"Sezione mancante in config: {dotted_key}",
                    file_path=str(self.config_path),
                )
            return {}
        mapping = _mapping_or_empty(raw, dotted_key, config_path=self.config_path)
        for env_name in mapping.keys():
            if isinstance(env_name, str) and env_name.upper() in _ENV_DENY_LIST:
                try:
                    _LOGGER.warning(
                        "settings.yaml.env_denied",
                        extra={
                            "file_path": str(self.config_path),
                            "key": env_name,
                            "section": dotted_key,
                        },
                    )
                except Exception:
                    pass
        return mapping

    @cached_property
    def meta_settings(self) -> MetaSection:
        return MetaSection.from_mapping(
            self._section_mapping("meta", required=False),
            config_path=self.config_path,
        )

    @cached_property
    def openai_settings(self) -> OpenAISection:
        # Sezione obbligatoria: assenza o tipo errato -> ConfigError in from_mapping.
        return OpenAISection.from_mapping(
            self._section_mapping("ai.openai", required=True),
            config_path=self.config_path,
        )

    @cached_property
    def vision_settings(self) -> VisionSection:
        # Sezione obbligatoria: ai.vision.model deve essere presente e non vuoto.
        return VisionSection.from_mapping(
            self._section_mapping("ai.vision", required=True),
            config_path=self.config_path,
        )

    @cached_property
    def ui_settings(self) -> UISection:
        return UISection.from_mapping(
            self._section_mapping("ui", required=True),
            config_path=self.config_path,
        )

    @cached_property
    def retriever_settings(self) -> RetrieverSection:
        return RetrieverSection.from_mapping(
            self._section_mapping("pipeline.retriever", required=True),
            config_path=self.config_path,
        )

    @cached_property
    def ops_settings(self) -> OpsSection:
        return OpsSection.from_mapping(
            self._section_mapping("ops", required=True),
            config_path=self.config_path,
        )

    # ----------------------------- Typed accessors -----------------------------

    @property
    def client_name(self) -> Optional[str]:
        return self.meta_settings.client_name

    @property
    def vision_model(self) -> Optional[str]:
        return self.vision_settings.model

    @property
    def vision_engine(self) -> Optional[str]:
        return self.vision_settings.engine

    @property
    def vision_snapshot_retention_days(self) -> int:
        return self.vision_settings.snapshot_retention_days

    @property
    def vision_assistant_env(self) -> Optional[str]:
        return self.vision_settings.assistant_id_env

    @property
    def ui_skip_preflight(self) -> bool:
        return self.ui_settings.skip_preflight

    @property
    def ui_allow_local_only(self) -> bool:
        return self.ui_settings.allow_local_only

    @property
    def ui_admin_local_mode(self) -> bool:
        return self.ui_settings.admin_local_mode

    @property
    def retriever_auto_by_budget(self) -> bool:
        return self.retriever_settings.auto_by_budget

    @property
    def retriever_throttle(self) -> RetrieverThrottleSection:
        return self.retriever_settings.throttle

    @property
    def ops_log_level(self) -> str:
        return self.ops_settings.log_level

    # ----------------------------- Helper metodi ------------------------------

    def get_value(self, dotted_key: str, *, default: Any = _MISSING) -> Any:
        """Recupera un campo annidato usando dot-notation."""
        current: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(current, Mapping):
                if default is _MISSING:
                    raise KeyError(dotted_key)
                return default
            if part not in current:
                if default is _MISSING:
                    raise KeyError(dotted_key)
                return default
            current = current[part]
        return current

    def resolve_env_ref(
        self, dotted_key: str, *, required: bool = False, default: Optional[str] = None
    ) -> Optional[str]:
        """Risolvi un riferimento *_env leggendo il segreto corrispondente da ENV."""
        if not dotted_key.endswith("_env"):
            raise ConfigError(
                "resolve_env_ref richiede una chiave che termini con '_env'",
                file_path=str(self.config_path),
            )
        try:
            env_name = self.get_value(dotted_key)
        except KeyError as exc:
            if required:
                raise ConfigError(
                    f"Chiave non trovata: {dotted_key}",
                    file_path=str(self.config_path),
                ) from exc
            return default
        if env_name is None:
            if required:
                raise ConfigError(
                    f"Valore nullo per {dotted_key}",
                    file_path=str(self.config_path),
                )
            return default
        if not isinstance(env_name, str):
            raise ConfigError(
                f"Valore non stringa per {dotted_key}: {type(env_name).__name__}",
                file_path=str(self.config_path),
            )
        env_name = env_name.strip()
        if not env_name:
            if required:
                raise ConfigError(
                    f"Valore vuoto per {dotted_key}",
                    file_path=str(self.config_path),
                )
            return default
        try:
            return self.get_secret(env_name, required=required, default=default)
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError("Errore lettura segreto da ENV.", file_path=str(self.config_path)) from exc

    def get_secret(self, name: str, *, required: bool = False, default: Optional[str] = None) -> Optional[str]:
        """Recupera un segreto delegando a env_utils con load idempotente del .env."""
        try:
            ensure_dotenv_loaded()
        except Exception:
            pass
        try:
            return get_env_var(name, default=default, required=required)
        except KeyError as exc:
            raise ConfigError(
                f"Variabile d'ambiente mancante: {name}",
                file_path=str(self.config_path),
            ) from exc

    # ----------------------------- Cataloghi ausiliari -----------------------------

    @staticmethod
    def env_catalog() -> list[dict[str, Any]]:
        """Ritorna l'elenco delle variabili d'ambiente ritenute critiche/opzionali."""
        doc_url = "https://github.com/nextybase/timmy-kb-acme/blob/main/docs/user/guida_ui.md#configurazione-env"
        return [
            {
                "name": "SERVICE_ACCOUNT_FILE",
                "required": True,
                "description": "Percorso al JSON del Service Account Google Drive.",
                "doc_url": doc_url,
            },
            {
                "name": "DRIVE_ID",
                "required": True,
                "description": "ID dello Shared Drive dove risiedono i contenuti del cliente.",
                "doc_url": doc_url,
            },
            {
                "name": "DRIVE_PARENT_FOLDER_ID",
                "required": False,
                "description": "Cartella padre opzionale per provisioning Drive.",
                "doc_url": doc_url,
            },
            {
                "name": "OPENAI_API_KEY",
                "required": False,
                "description": "API key OpenAI per Vision/Assistant.",
                "doc_url": doc_url,
            },
            {
                "name": "OBNEXT_ASSISTANT_ID",
                "required": False,
                "description": "ID assistant principale (Vision).",
                "doc_url": doc_url,
            },
            {
                "name": "GOOGLE_CLIENT_ID",
                "required": False,
                "description": "Client ID OAuth Google per login amministrazione.",
                "doc_url": doc_url,
            },
            {
                "name": "GOOGLE_CLIENT_SECRET",
                "required": False,
                "description": "Client secret OAuth Google (mai committare).",
                "doc_url": doc_url,
            },
            {
                "name": "GOOGLE_REDIRECT_URI",
                "required": False,
                "description": "Redirect URI registrata per l'OAuth Admin.",
                "doc_url": doc_url,
            },
            {
                "name": "ALLOWED_GOOGLE_DOMAIN",
                "required": False,
                "description": "Dominio ammesso per l'accesso Admin.",
                "doc_url": doc_url,
            },
        ]
