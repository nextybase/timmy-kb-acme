# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/clients_store.py
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, cast

from pipeline.path_utils import read_text_safe

yaml: Any | None
try:
    import yaml as _yaml

    yaml = cast(Any, _yaml)
except Exception:  # pragma: no cover
    yaml = None

st: Any | None
try:
    import streamlit as _streamlit_module

    st = cast(Any, _streamlit_module)
except Exception:  # pragma: no cover
    st = None

# --------------------------------------------------------------------------------------
# Path del "database" YAML (monkeypatchabile nei test)
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directory e file predefiniti; possono essere sovrascritti via env o monkeypatchati nei test
DB_DIR: Path = Path(os.getenv("CLIENTS_DB_DIR", str(REPO_ROOT / "data" / "clients_db"))).resolve()
DB_FILE: Path = Path(os.getenv("CLIENTS_DB_FILE", str(DB_DIR / "clients.yaml"))).resolve()


# --------------------------------------------------------------------------------------
# Modello dati
# --------------------------------------------------------------------------------------


@dataclass
class ClientEntry:
    slug: str
    nome: str = ""
    stato: str = ""  # es. "ready", "open", ecc.

    @staticmethod
    def from_obj(obj: object) -> "ClientEntry | None":
        if isinstance(obj, ClientEntry):
            return ClientEntry(slug=obj.slug, nome=obj.nome, stato=obj.stato)
        if not isinstance(obj, Mapping):
            return None

        data = {str(key): value for key, value in obj.items()}

        slug = str(data.get("slug") or "").strip()
        if not slug:
            return None

        nome = str(data.get("nome") or "").strip()
        stato = str(data.get("stato") or "").strip()
        return ClientEntry(slug=slug, nome=nome, stato=stato)

    def to_dict(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "nome": self.nome,
            "stato": self.stato,
        }


# --------------------------------------------------------------------------------------
# I/O YAML + bootstrap file
# --------------------------------------------------------------------------------------


def ensure_db(db_path: Optional[Path] = None) -> Path:
    """
    Garantisce l'esistenza del file YAML dei clienti; se manca, crea '[]\\n'.
    Ritorna il Path effettivo.
    """
    p = (db_path or DB_FILE).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("[]\n", encoding="utf-8")
    return p


def get_db_path() -> Path:
    """Ritorna il Path del DB (creando la dir se serve, non il file)."""
    p = DB_FILE.resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_raw_entries(p: Path) -> list[dict[str, Any]]:
    ensure_db(p)
    if yaml is None:  # pragma: no cover
        return []
    try:
        raw_text = read_text_safe(p.parent, p, encoding="utf-8")
    except Exception:
        return []
    try:
        data = yaml.safe_load(raw_text) or []
        if isinstance(data, list):
            return [{str(key): value for key, value in d.items()} for d in data if isinstance(d, dict)]
        return []
    except Exception:
        return []


def _write_raw_entries(p: Path, entries: Iterable[ClientEntry]) -> None:
    ensure_db(p)
    if yaml is None:  # pragma: no cover
        p.write_text("[]\n", encoding="utf-8")
        return
    payload: list[dict[str, Any]] = [e.to_dict() for e in entries]
    txt = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    p.write_text(txt, encoding="utf-8")


# --------------------------------------------------------------------------------------
# Cache della lista clienti (Beta 0 compliant)
# --------------------------------------------------------------------------------------


def _load_clients_core(db_path: Path) -> tuple[ClientEntry, ...]:
    items = _read_raw_entries(db_path)
    out: list[ClientEntry] = []
    for raw in items:
        entry = ClientEntry.from_obj(raw)
        if entry is not None:
            out.append(entry)
    return tuple(out)


_load_clients_cached: Callable[[Path], tuple[ClientEntry, ...]]

if st is not None and hasattr(st, "cache_data"):
    _load_clients_cached = cast(
        Callable[[Path], tuple[ClientEntry, ...]],
        st.cache_data(show_spinner=False, ttl=10)(_load_clients_core),
    )
else:
    _load_clients_cached = _load_clients_core


def invalidate_clients_cache() -> None:
    if st is not None:
        cache_clear = getattr(_load_clients_cached, "clear", None)
        if callable(cache_clear):
            try:
                cache_clear()
            except Exception:
                pass


# --------------------------------------------------------------------------------------
# API pubblica
# --------------------------------------------------------------------------------------


def load_clients(db_path: Optional[Path] = None) -> list[ClientEntry]:
    """Carica la lista dei clienti dal DB (cache-ata)."""
    p = (db_path or get_db_path()).resolve()
    return list(_load_clients_cached(p))


def save_clients(entries: Iterable[ClientEntry], db_path: Optional[Path] = None) -> None:
    """Salva l’elenco completo (sovrascrive). Invalida la cache."""
    p = (db_path or get_db_path()).resolve()
    _write_raw_entries(p, entries)
    invalidate_clients_cache()


def list_clients(db_path: Optional[Path] = None) -> list[str]:
    """Comodo per UI/test: ritorna gli slug normalizzati."""
    return [e.slug for e in load_clients(db_path)]


def get_state(slug: Optional[str], db_path: Optional[Path] = None) -> Optional[str]:
    """
    Ritorna lo stato normalizzato del cliente (o None se non esiste).
    Confronto case-insensitive sullo slug.
    """
    s = (slug or "").strip().lower()
    if not s:
        return None
    for entry in load_clients(db_path):
        if entry.slug.strip().lower() == s:
            return entry.stato.strip().lower()
    return None


def upsert_client(entry: ClientEntry, db_path: Optional[Path] = None) -> ClientEntry:
    """
    Inserisce/aggiorna un cliente mantenendo l’ordine di inserimento.
    Se lo slug esiste già viene sovrascritto con l’entry più recente.
    """
    slug_norm = entry.slug.strip().lower()
    if not slug_norm:
        raise ValueError("slug obbligatorio")

    normalized = ClientEntry(
        slug=slug_norm,
        nome=entry.nome.strip(),
        stato=entry.stato.strip(),
    )

    p = (db_path or get_db_path()).resolve()
    ensure_db(p)
    items = load_clients(p)

    for idx, existing in enumerate(items):
        if existing.slug.strip().lower() == slug_norm:
            items[idx] = normalized
            save_clients(items, p)
            return normalized

    items.append(normalized)
    save_clients(items, p)
    return normalized


def set_state(slug: str, stato: str, db_path: Optional[Path] = None) -> bool:
    """
    Aggiorna lo stato di un cliente esistente. Ritorna True se l’update va a buon fine.
    """
    slug_norm = slug.strip().lower()
    if not slug_norm:
        return False

    p = (db_path or get_db_path()).resolve()
    items = load_clients(p)
    new_state = (stato or "").strip()

    for idx, existing in enumerate(items):
        if existing.slug.strip().lower() == slug_norm:
            items[idx] = ClientEntry(
                slug=existing.slug,
                nome=existing.nome,
                stato=new_state,
            )
            save_clients(items, p)
            return True

    return False


__all__ = [
    "ClientEntry",
    "DB_DIR",
    "DB_FILE",
    "ensure_db",
    "get_db_path",
    "load_clients",
    "save_clients",
    "list_clients",
    "get_state",
    "upsert_client",
    "set_state",
    "invalidate_clients_cache",
]
