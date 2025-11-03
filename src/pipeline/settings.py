# SPDX-License-Identifier: GPL-3.0-only
"""Loader centralizzato per config/config.yaml con helper typed."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional

from .env_utils import ensure_dotenv_loaded, get_env_var
from .exceptions import ConfigError
from .yaml_utils import yaml_read

_MISSING = object()


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
        """Carica config/config.yaml rispettando path-safety."""
        repo_root = repo_root.resolve()
        cfg_path = (config_path or (repo_root / "config" / "config.yaml")).resolve()
        payload = yaml_read(repo_root, cfg_path) or {}
        instance = cls(config_path=cfg_path, data=payload)
        if logger:
            extra = {"file_path": str(cfg_path)}
            if slug:
                extra["slug"] = slug
            logger.info("settings.config.loaded", extra=extra)
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

    @property
    def vision_model(self) -> Optional[str]:
        value = self.get_value("vision.model", default=None)
        return str(value) if value is not None else None

    @property
    def vision_engine(self) -> Optional[str]:
        value = self.get_value("vision.engine", default=None)
        return str(value) if value is not None else None

    @property
    def vision_assistant_env(self) -> Optional[str]:
        value = self.get_value("vision.assistant_id_env", default=None)
        return str(value) if value is not None else None

    @property
    def ui_skip_preflight(self) -> bool:
        return bool(self.get_value("ui.skip_preflight", default=False))

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
            raise ConfigError(str(exc), file_path=str(self.config_path)) from exc

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
        doc_url = "https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md#configurazione-env"
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
                "name": "ASSISTANT_ID",
                "required": False,
                "description": "Assistant fallback (compatibilità).",
                "doc_url": doc_url,
            },
            {
                "name": "GITHUB_TOKEN",
                "required": False,
                "description": "Token GitHub per automazioni (push, API).",
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
