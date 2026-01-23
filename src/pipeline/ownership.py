# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, TypedDict

import yaml

from .env_utils import get_env_var
from .exceptions import ConfigError
from .file_utils import safe_write_text
from .logging_utils import get_structured_logger
from .path_utils import ensure_within_and_resolve, read_text_safe

OwnershipRole = Literal["user", "dev", "architecture"]

ROLE_KEYS: tuple[OwnershipRole, ...] = ("user", "dev", "architecture")


class OwnersDict(TypedDict, total=False):
    user: List[str]
    dev: List[str]
    architecture: List[str]


class OwnershipConfig(TypedDict, total=False):
    schema_version: str
    slug: str
    owners: OwnersDict


OWNERSHIP_FILENAME = "ownership.yaml"
TEMPLATE_SLUG = "example"
CODE_COMPONENT = "ownership"
GLOBAL_SUPERADMIN_ENV = "TIMMY_GLOBAL_SUPERADMINS"

LOGGER = get_structured_logger("pipeline.ownership")


def _clients_root(repo_root_dir: Path) -> Path:
    base = Path(repo_root_dir)
    return ensure_within_and_resolve(base, base / "clients_db" / "clients")


def _ownership_file(repo_root_dir: Path, slug: str) -> Path:
    clients_root = _clients_root(repo_root_dir)
    slug_dir = ensure_within_and_resolve(clients_root, clients_root / slug)
    return ensure_within_and_resolve(slug_dir, slug_dir / OWNERSHIP_FILENAME)


def load_ownership(slug: str, repo_root_dir: Path | str) -> OwnershipConfig:
    repo_root = Path(repo_root_dir)
    path = _ownership_file(repo_root, slug)
    if not path.exists():
        raise ConfigError(
            "Ownership non configurata (percorso canonico mancante)",
            slug=slug,
            file_path=str(path),
            code="ownership.missing",
            component=CODE_COMPONENT,
        )
    try:
        text = read_text_safe(path.parent, path, encoding="utf-8")
        payload = yaml.safe_load(text) or {}
    except ConfigError:
        raise
    except Exception as exc:  # pragma: no cover
        raise ConfigError(
            "Ownership non valida",
            slug=slug,
            file_path=str(path),
            code="ownership.invalid",
            component=CODE_COMPONENT,
        ) from exc
    return validate_ownership(payload, slug)


def validate_ownership(cfg: OwnershipConfig | Dict[str, object], slug: str) -> OwnershipConfig:
    raw_slug = cfg.get("slug") if isinstance(cfg, dict) else None
    if raw_slug and raw_slug != slug:
        raise ConfigError(
            "Ownership non valida: slug mismatch",
            slug=slug,
            code="ownership.invalid",
            component=CODE_COMPONENT,
        )

    owners: Dict[OwnershipRole, List[str]] = {key: [] for key in ROLE_KEYS}
    raw_owners = cfg.get("owners") if isinstance(cfg, dict) else None
    if raw_owners is not None and not isinstance(raw_owners, dict):
        raise ConfigError(
            "Ownership non valida: owners deve essere mappato",
            slug=slug,
            code="ownership.invalid",
            component=CODE_COMPONENT,
        )

    if isinstance(raw_owners, dict):
        for key, value in raw_owners.items():
            if key not in ROLE_KEYS:
                raise ConfigError(
                    "Ownership non valida: ruolo sconosciuto",
                    slug=slug,
                    code="ownership.invalid",
                    component=CODE_COMPONENT,
                )
            if value is None:
                owners[key] = []
                continue
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConfigError(
                    "Ownership non valida: lista di owner invalida",
                    slug=slug,
                    code="ownership.invalid",
                    component=CODE_COMPONENT,
                )
            owners[key] = list(value)

    schema_version = cfg.get("schema_version") if isinstance(cfg, dict) else None
    if schema_version is None:
        schema_version = "1"

    return {
        "schema_version": schema_version,
        "slug": slug,
        "owners": owners,
    }


def _template_file(repo_root_dir: Path) -> Path:
    clients_root = _clients_root(repo_root_dir)
    template_dir = ensure_within_and_resolve(clients_root, clients_root / TEMPLATE_SLUG)
    return ensure_within_and_resolve(template_dir, template_dir / OWNERSHIP_FILENAME)


def ensure_ownership_file(slug: str, repo_root_dir: Path | str) -> Path:
    repo_root = Path(repo_root_dir)
    path = _ownership_file(repo_root, slug)
    if path.exists():
        return path
    template = _template_file(repo_root)
    if not template.exists():
        raise ConfigError(
            "Template ownership mancante",
            slug=slug,
            file_path=str(template),
            code="ownership.template.missing",
            component=CODE_COMPONENT,
        )
    try:
        text = read_text_safe(template.parent, template, encoding="utf-8")
        payload = yaml.safe_load(text) or {}
    except Exception as exc:  # pragma: no cover
        raise ConfigError(
            "Template ownership non valido",
            slug=slug,
            file_path=str(template),
            code="ownership.invalid",
            component=CODE_COMPONENT,
        ) from exc

    payload["slug"] = slug
    payload.setdefault("schema_version", "1")
    payload.setdefault("owners", {})

    safe_write_text(path, yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def get_global_superadmins() -> List[str]:
    raw = get_env_var(GLOBAL_SUPERADMIN_ENV, default="")
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(",")]
    entries = []
    for part in parts:
        if not part:
            continue
        if " " in part:
            raise ConfigError(
                "Superadmin globale non valido",
                code="ownership.superadmin.invalid",
                component=CODE_COMPONENT,
            )
        entries.append(part)
    return entries


__all__ = [
    "OwnershipRole",
    "OwnershipConfig",
    "load_ownership",
    "validate_ownership",
    "ensure_ownership_file",
    "get_global_superadmins",
]
