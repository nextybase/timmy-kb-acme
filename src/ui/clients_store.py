# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/clients_store.py
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union, cast

import yaml

from pipeline.context import validate_slug
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# Base sicura ancorata al repo
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_DB_DIR: Path = Path("clients_db")
DEFAULT_DB_FILE: Path = Path("clients.yaml")
# Allow override (solo percorsi relativi rispetto alla repo root)
DB_DIR: Path = DEFAULT_DB_DIR
DB_FILE: Path = DEFAULT_DB_FILE
PATH_ENV = "CLIENTS_DB_PATH"


def _optional_env(name: str) -> Optional[str]:
    try:
        value = cast(Optional[str], get_env_var(name, default=None))
        return value
    except KeyError:
        return None
    except Exception:
        return None


def _base_repo_root() -> Path:
    override = os.environ.get("REPO_ROOT_DIR")
    if override:
        try:
            return Path(override).expanduser().resolve()
        except Exception:
            return REPO_ROOT
    return REPO_ROOT


def _normalize_relative(value: Union[str, Path], *, var_name: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ConfigError(f"{var_name} deve essere un percorso relativo")
    normalised = Path()
    for part in candidate.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ConfigError(f"{var_name}: componenti '..' non sono ammessi")
        normalised /= part
    if not normalised.parts:
        raise ConfigError(f"{var_name} non può essere vuoto")
    return normalised


def _require_clients_db_prefix(path: Path, *, var_name: str) -> None:
    if not path.parts or path.parts[0] != DEFAULT_DB_DIR.as_posix():
        raise ConfigError(f"{var_name} deve iniziare con '{DEFAULT_DB_DIR.as_posix()}'")


def _path_override() -> Optional[tuple[Path, Path]]:
    raw = _optional_env(PATH_ENV)
    if not raw:
        return None
    relative = _normalize_relative(raw, var_name=PATH_ENV)
    _require_clients_db_prefix(relative, var_name=PATH_ENV)
    rel_dir = relative.parent
    rel_file = Path(relative.name)
    return rel_dir, rel_file


def _db_dir() -> Path:
    base_root = _base_repo_root()
    path_override = _path_override()
    if path_override:
        rel_dir, _ = path_override
        target = base_root / rel_dir
        return cast(Path, ensure_within_and_resolve(base_root, target))
    value = _optional_env("CLIENTS_DB_DIR")
    if value:
        relative = _normalize_relative(value, var_name="CLIENTS_DB_DIR")
        _require_clients_db_prefix(relative, var_name="CLIENTS_DB_DIR")
    else:
        relative = _normalize_relative(DB_DIR, var_name="DB_DIR")
    target = base_root / relative
    return cast(Path, ensure_within_and_resolve(base_root, target))


def _db_file() -> Path:
    base_dir = _db_dir()
    path_override = _path_override()
    if path_override:
        _, rel_file = path_override
        target = base_dir / rel_file
        return cast(Path, ensure_within_and_resolve(base_dir, target))
    value = _optional_env("CLIENTS_DB_FILE")
    if value:
        relative = _normalize_relative(value, var_name="CLIENTS_DB_FILE")
    else:
        relative = _normalize_relative(DB_FILE, var_name="DB_FILE")
    target = base_dir / relative
    return cast(Path, ensure_within_and_resolve(base_dir, target))


LOG = get_structured_logger("ui.clients_store")


@dataclass
class ClientEntry:
    slug: str
    nome: str
    stato: str
    created_at: str | None = None
    dummy: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"slug": self.slug, "nome": self.nome, "stato": self.stato}
        if self.created_at:
            payload["created_at"] = self.created_at
        if self.dummy is not None:
            payload["dummy"] = bool(self.dummy)
        return payload


def ensure_db() -> None:
    db_dir = _db_dir()
    db_file = _db_file()
    db_dir.mkdir(parents=True, exist_ok=True)
    if not db_file.exists():
        safe_write_text(db_file, "[]\n", encoding="utf-8", atomic=True)
        _cached_clients.cache_clear()


def _parse_entries(text: str) -> list[ClientEntry]:
    try:
        data = yaml.safe_load(text) or []
    except Exception:
        data = []
    entries: list[ClientEntry] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            nome = str(item.get("nome", "")).strip()
            stato = str(item.get("stato", "")).strip()
            created_at = item.get("created_at")
            dummy_flag = item.get("dummy")
            if slug:
                entries.append(
                    ClientEntry(
                        slug=slug,
                        nome=nome,
                        stato=stato,
                        created_at=str(created_at).strip() if created_at else None,
                        dummy=bool(dummy_flag) if isinstance(dummy_flag, bool) else None,
                    )
                )
    return entries


@lru_cache(maxsize=32)
def _cached_clients(db_dir: str, db_file: str, mtime: float) -> tuple[ClientEntry, ...]:
    try:
        text = read_text_safe(Path(db_dir), Path(db_file), encoding="utf-8")
    except Exception:
        return ()
    return tuple(_parse_entries(text))


def load_clients() -> list[ClientEntry]:
    ensure_db()
    db_dir = _db_dir()
    db_file = _db_file()
    try:
        mtime = float(db_file.stat().st_mtime)
    except Exception:
        mtime = 0.0
    return list(_cached_clients(str(db_dir), str(db_file), mtime))


def save_clients(entries: list[ClientEntry]) -> None:
    ensure_db()
    payload: list[dict[str, Any]] = [e.to_dict() for e in entries]
    text: str = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    safe_write_text(_db_file(), text, encoding="utf-8", atomic=True)
    _cached_clients.cache_clear()


def upsert_client(entry: ClientEntry) -> None:
    """Inserisce o aggiorna un cliente (mantiene ordine: nuovo in testa, dedup per slug)."""
    entries = load_clients()
    seen: set[str] = set()
    out: list[ClientEntry] = []

    slug_norm = entry.slug.strip()
    validate_slug(slug_norm)
    out.append(
        ClientEntry(
            slug=slug_norm,
            nome=entry.nome,
            stato=entry.stato,
            created_at=entry.created_at,
            dummy=entry.dummy,
        )
    )
    seen.add(slug_norm)

    for e in entries:
        s = e.slug.strip()
        if s in seen:
            continue
        out.append(e)
        seen.add(s)

    save_clients(out)


def set_state(slug: str, new_state: str) -> bool:
    """Aggiorna lo stato di un cliente esistente. Ritorna True se modificato."""
    slug_norm = slug.strip()
    if not slug_norm:
        return False
    validate_slug(slug_norm)
    entries = load_clients()
    changed = False
    found = False
    for i, e in enumerate(entries):
        if e.slug.strip() == slug_norm:
            found = True
            if e.stato != new_state:
                entries[i] = ClientEntry(slug=e.slug, nome=e.nome, stato=new_state)
                changed = True
            break
    if changed:
        save_clients(entries)
        try:
            LOG.info("client_state_updated", extra={"slug": slug_norm, "state": new_state})
        except Exception:
            pass
    else:
        try:
            event = "client_state_noop" if found else "client_state_missing"
            LOG.warning(event, extra={"slug": slug_norm, "state": new_state})
        except Exception:
            pass
    return changed


def get_state(slug: str) -> Optional[str]:
    """Ritorna lo stato normalizzato del cliente, se presente."""
    slug_norm = slug.strip()
    if not slug_norm:
        return None
    for e in load_clients():
        if e.slug.strip() == slug_norm:
            return e.stato
    return None


def get_all() -> list[ClientEntry]:
    return load_clients()


def get_ui_state_path() -> Path:
    """Restituisce il percorso persistito per lo slug attivo."""
    base = _db_dir()
    target = base / "ui_state.json"
    return cast(Path, ensure_within_and_resolve(base, target))


def get_registry_paths() -> tuple[Path, Path]:
    """
    Ritorna la coppia (directory, file) dell'archivio clienti,
    applicando eventuali override di ambiente.
    """
    db_file = _db_file()
    return db_file.parent, db_file
