# src/ui/clients_store.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

REPO_ROOT: Path = Path(__file__).resolve().parents[2]


# ----------------------------- Path sicuri per DB clienti -----------------------------
def _resolve_db_path(path: Path) -> Path:
    anchored = REPO_ROOT / path if not path.is_absolute() else path
    return ensure_within_and_resolve(REPO_ROOT, anchored)


DB_DIR: Path = _resolve_db_path(Path(os.getenv("CLIENTS_DB_DIR", str(REPO_ROOT / "data" / "clients_db"))))
DB_FILE: Path = _resolve_db_path(Path(os.getenv("CLIENTS_DB_FILE", str(DB_DIR / "clients.yaml"))))


# ----------------------------- Modello -----------------------------
@dataclass
class ClientEntry:
    slug: str
    nome: str
    stato: str

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "nome": self.nome, "stato": self.stato}


# ----------------------------- I/O helpers -----------------------------
def ensure_db() -> None:
    """Garantisce l’esistenza del file DB (YAML)."""
    p = DB_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        safe_write_text(p, "[]\n", encoding="utf-8", atomic=True)


def load_clients() -> List[ClientEntry]:
    """Carica l’elenco clienti in modo *safe* (path-safe) e tollerante agli errori."""
    ensure_db()
    try:
        txt = read_text_safe(REPO_ROOT, DB_FILE, encoding="utf-8")
    except Exception:
        return []
    try:
        import yaml
    except Exception:
        return []
    try:
        payload = yaml.safe_load(txt) or []
        out: List[ClientEntry] = []
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug") or "").strip()
                if not slug:
                    continue
                nome = str(item.get("nome") or slug).strip() or slug
                stato = str(item.get("stato") or "nuovo").strip() or "nuovo"
                out.append(ClientEntry(slug=slug, nome=nome, stato=stato))
        return out
    except Exception:
        return []


def save_clients(entries: List[ClientEntry]) -> None:
    """Salva (atomicamente) l’elenco clienti."""
    try:
        import yaml
    except Exception:
        safe_write_text(DB_FILE, "[]\n", encoding="utf-8", atomic=True)
        return
    data = [e.to_dict() for e in entries]
    txt = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    safe_write_text(ensure_within_and_resolve(REPO_ROOT, DB_FILE), txt, encoding="utf-8", atomic=True)


# ----------------------------- API -----------------------------
def upsert_client(entry_or_slug: ClientEntry | str, nome: Optional[str] = None, stato: Optional[str] = None) -> None:
    """
    Inserisce o aggiorna un cliente. Accetta:
      - upsert_client(ClientEntry(...))
      - upsert_client("slug", nome="...", stato="...")
    Mantiene l’ordine: se esiste aggiorna *in place*, altrimenti appende.
    """
    if isinstance(entry_or_slug, ClientEntry):
        slug = entry_or_slug.slug.strip()
        nome_v = entry_or_slug.nome.strip() or entry_or_slug.slug
        stato_v = entry_or_slug.stato.strip() or "nuovo"
    else:
        slug = str(entry_or_slug).strip()
        nome_v = (nome or slug).strip()
        stato_v = (stato or "nuovo").strip()

    if not slug:
        return

    items = load_clients()
    idx = next((i for i, e in enumerate(items) if e.slug.lower() == slug.lower()), -1)
    if idx >= 0:
        items[idx].nome = nome_v
        items[idx].stato = stato_v
    else:
        items.append(ClientEntry(slug=slug, nome=nome_v, stato=stato_v))
    save_clients(items)


def get_state(slug: str) -> Optional[str]:
    """Ritorna lo stato del cliente (case-insensitive), oppure None se assente."""
    slug_norm = slug.strip().lower()
    if not slug_norm:
        return None
    for e in load_clients():
        if e.slug.lower() == slug_norm:
            return e.stato
    return None


def set_state(slug: str, nuovo_stato: str) -> bool:
    """Aggiorna lo stato *solo se il cliente esiste*. Restituisce True se aggiornato."""
    slug_norm = slug.strip().lower()
    if not slug_norm:
        return False
    items = load_clients()
    for i, e in enumerate(items):
        if e.slug.lower() == slug_norm:
            items[i].stato = nuovo_stato.strip() or e.stato
            save_clients(items)
            return True
    return False


def get_client_name(slug: str) -> Optional[str]:
    """Nome visuale del cliente, se presente."""
    slug_norm = slug.strip().lower()
    if not slug_norm:
        return None
    for e in load_clients():
        if e.slug.lower() == slug_norm:
            return e.nome
    return None
