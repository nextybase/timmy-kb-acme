"""Client store helpers for the Streamlit UI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, cast

import yaml

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.yaml_utils import clear_yaml_cache, yaml_read

DB_VERSION = 1
DEFAULT_STATE = "nuovo"
CLIENT_STATES = {
    "nuovo",
    "inizializzato",
    "pronto",
    "arricchito",
    "finito",
    "archiviato",
}
REPO_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = REPO_ROOT / "clients_db"
DB_FILE = DB_DIR / "clients.yaml"


@dataclass(slots=True)
class ClientEntry:
    slug: str
    nome: str
    stato: str


def get_state(slug: str) -> str | None:
    """Ritorna lo stato normalizzato del cliente (o None se non esiste)."""
    slug_norm = slug.strip()
    if not slug_norm:
        return None
    entries = load_clients()
    for entry in entries:
        if entry.slug == slug_norm:
            return entry.stato
    return None


def ensure_db() -> None:
    """Create the YAML store if missing."""
    db_path = _resolved_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return
    payload = _dump_payload([])
    safe_write_text(db_path, payload, encoding="utf-8", atomic=True)
    clear_yaml_cache()


def load_clients() -> list[ClientEntry]:
    """Load client entries from disk."""
    ensure_db()
    db_path = _resolved_db_path()
    try:
        data = yaml_read(db_path.parent, db_path)
    except (ConfigError, Exception):
        return []
    return _coerce_entries(data)


def upsert_client(entry: ClientEntry) -> None:
    """Insert or replace a client by slug."""
    normalized = _normalize_entry(entry)
    if not normalized.slug:
        raise ValueError("slug is required")
    ensure_db()
    current = load_clients()
    updated: list[ClientEntry] = []
    replaced = False
    seen: set[str] = set()
    for existing in current:
        if existing.slug in seen:
            continue
        seen.add(existing.slug)
        if existing.slug == normalized.slug:
            updated.append(normalized)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(normalized)
    _write_entries(updated)


def set_state(slug: str, stato: str) -> None:
    """Update the state of an existing client."""
    slug_norm = slug.strip()
    if not slug_norm:
        return
    ensure_db()
    current = load_clients()
    target_state = _normalize_state(stato)
    changed = False
    updated: list[ClientEntry] = []
    seen: set[str] = set()
    for entry in current:
        if entry.slug in seen:
            continue
        seen.add(entry.slug)
        if entry.slug == slug_norm:
            if entry.stato != target_state:
                updated.append(ClientEntry(slug=entry.slug, nome=entry.nome, stato=target_state))
                changed = True
            else:
                updated.append(entry)
        else:
            updated.append(entry)
    if not changed:
        return
    _write_entries(updated)


def _resolved_db_path() -> Path:
    return cast(Path, ensure_within_and_resolve(REPO_ROOT, DB_FILE))


def _dump_payload(entries: Sequence[ClientEntry]) -> str:
    payload = {
        "version": DB_VERSION,
        "clients": [{"slug": item.slug, "nome": item.nome, "stato": item.stato} for item in entries],
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _coerce_entries(raw: Any) -> list[ClientEntry]:
    result: list[ClientEntry] = []
    if isinstance(raw, dict):
        raw_clients = raw.get("clients")
    elif isinstance(raw, list):
        raw_clients = raw
    else:
        raw_clients = None
    if not isinstance(raw_clients, list):
        return result
    seen: set[str] = set()
    for item in raw_clients:
        if not isinstance(item, dict):
            continue
        slug = _to_str(item.get("slug"))
        if not slug or slug in seen:
            continue
        seen.add(slug)
        nome = _to_str(item.get("nome"))
        stato = _normalize_state(item.get("stato"))
        result.append(ClientEntry(slug=slug, nome=nome, stato=stato))
    return result


def _normalize_state(value: Any) -> str:
    state = _to_str(value).lower()
    if state in CLIENT_STATES:
        return state
    return DEFAULT_STATE


def _normalize_entry(entry: ClientEntry) -> ClientEntry:
    return ClientEntry(
        slug=entry.slug.strip(),
        nome=_to_str(entry.nome),
        stato=_normalize_state(entry.stato),
    )


def _write_entries(entries: Sequence[ClientEntry]) -> None:
    db_path = _resolved_db_path()
    payload = _dump_payload(entries)
    safe_write_text(db_path, payload, encoding="utf-8", atomic=True)
    clear_yaml_cache()


def _to_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "ClientEntry",
    "ensure_db",
    "load_clients",
    "set_state",
    "upsert_client",
]
