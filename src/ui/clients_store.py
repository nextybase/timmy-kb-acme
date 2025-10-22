# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/clients_store.py
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import yaml

from pipeline.context import validate_slug
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# Base sicura ancorata al repo
REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def _resolve_db_path(target: Path) -> Path:
    """Path-safety: garantisce che target resti entro il repo."""
    return cast(Path, ensure_within_and_resolve(REPO_ROOT, target))


DB_DIR: Path = _resolve_db_path(Path(os.getenv("CLIENTS_DB_DIR", str(REPO_ROOT / "clients_db"))))
DB_FILE: Path = _resolve_db_path(Path(os.getenv("CLIENTS_DB_FILE", str(DB_DIR / "clients.yaml"))))

LOG = logging.getLogger("ui.clients_store")


@dataclass
class ClientEntry:
    slug: str
    nome: str
    stato: str

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "nome": self.nome, "stato": self.stato}


def ensure_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_FILE.exists():
        safe_write_text(DB_FILE, "[]\n", encoding="utf-8", atomic=True)


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
            if slug:
                entries.append(ClientEntry(slug=slug, nome=nome, stato=stato))
    return entries


def load_clients() -> list[ClientEntry]:
    ensure_db()
    try:
        txt: str = read_text_safe(DB_DIR, DB_FILE, encoding="utf-8")
    except Exception:
        return []
    return _parse_entries(txt)


def save_clients(entries: list[ClientEntry]) -> None:
    ensure_db()
    payload: list[dict[str, Any]] = [e.to_dict() for e in entries]
    text: str = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    safe_write_text(DB_FILE, text, encoding="utf-8", atomic=True)


def upsert_client(entry: ClientEntry) -> None:
    """Inserisce o aggiorna un cliente (mantiene ordine: nuovo in testa, dedup per slug)."""
    entries = load_clients()
    seen: set[str] = set()
    out: list[ClientEntry] = []

    slug_norm = entry.slug.strip()
    validate_slug(slug_norm)
    out.append(ClientEntry(slug=slug_norm, nome=entry.nome, stato=entry.stato))
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
