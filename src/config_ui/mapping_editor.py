# src/config_ui/mapping_editor.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import to_kebab  # SSoT per la normalizzazione in kebab-case
from .utils import ensure_within_and_resolve, safe_write_text_compat, yaml_dump, yaml_load

MAPPING_RESERVED = {
    "context",
    "taxonomy",
    "synonyms",
    "canonical",
    "rules",
    "meta",
    "defaults",
    "settings",
    "about",
    "note",
}

# -------- Caricamento mapping di default (da config/) --------


def load_default_mapping() -> Dict[str, Any]:
    """Carica config/default_semantic_mapping.yaml a partire dalla root repo."""
    repo_root = Path(__file__).resolve().parents[2]  # .../src/config_ui -> .../src -> repo
    path = repo_root / "config" / "default_semantic_mapping.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Mapping default non trovato: {path}")
    return yaml_load(path)


# -------- Split/Build/Validate (editor) --------


def split_mapping(root: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """
    Ritorna (categorie_editabili, blob_riservato).
    Categorie = {cat: {"ambito": str, "descrizione": str, "esempio": List[str]}}
    """
    reserved = {k: v for k, v in root.items() if k in MAPPING_RESERVED}
    cats: Dict[str, Dict[str, Any]] = {}
    for k, v in root.items():
        if k in reserved:
            continue
        if isinstance(v, dict):
            cats[k] = {
                "ambito": str(v.get("ambito", "")),
                "descrizione": str(v.get("descrizione", "")),
                "esempio": list(v.get("esempio", []) or []),
            }
    return cats, reserved


def build_mapping(
    categories: Dict[str, Dict[str, Any]],
    reserved: Dict[str, Any],
    *,
    slug: str,
    client_name: str,
    normalize_keys: bool,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # preserva sezioni riservate
    for k, v in reserved.items():
        out[k] = v
    # context
    ctx = dict(out.get("context", {}))
    if slug:
        ctx["slug"] = slug
    if client_name:
        ctx["client_name"] = client_name
    if ctx:
        out["context"] = ctx
    # categorie
    for k, data in categories.items():
        key = to_kebab(k) if normalize_keys else k
        out[key] = {
            "ambito": str(data.get("ambito", "")),
            "descrizione": str(data.get("descrizione", "")),
            "esempio": [str(x) for x in (data.get("esempio") or []) if str(x).strip()],
        }
    return out


def validate_categories(
    categories: Dict[str, Dict[str, Any]], *, normalize_keys: bool
) -> Optional[str]:
    seen = set()
    for k in categories.keys():
        kk = to_kebab(k) if normalize_keys else k.strip()
        if not kk:
            return "Chiave categoria vuota."
        if kk in seen:
            return f"Categoria duplicata: {kk!r}"
        seen.add(kk)
    return None


# ---- Helpers per la UI (lista <-> items con id) ----


def examples_to_items(lst: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if isinstance(lst, list):
        import uuid

        for v in lst:
            out.append({"id": uuid.uuid4().hex, "value": str(v)})
    return out


def items_to_examples(items: List[Dict[str, str]]) -> List[str]:
    return [str(it.get("value", "")).strip() for it in items if str(it.get("value", "")).strip()]


# ---- Persistenza del mapping rivisto ----


def save_tags_reviewed(
    slug: str, mapping: Dict[str, Any], *, base_root: Path | str = "output"
) -> Path:
    base_root = Path(base_root)
    client_root = ensure_within_and_resolve(base_root, base_root / f"timmy-kb-{slug}")
    sem_dir = ensure_within_and_resolve(client_root, client_root / "semantic")
    path = ensure_within_and_resolve(sem_dir, sem_dir / "tags_reviewed.yaml")
    safe_write_text_compat(path, yaml_dump(mapping))
    return path


# -------- API aggiuntive usate dai runner Drive --------


def load_tags_reviewed(slug: str, *, base_root: Path | str = "output") -> Dict[str, Any]:
    """
    Carica il mapping rivisto del cliente (formato unico: 'tags_reviewed.yaml').
    """
    base_root = Path(base_root)
    sem_dir = ensure_within_and_resolve(
        base_root / f"timmy-kb-{slug}",
        base_root / f"timmy-kb-{slug}" / "semantic",
    )
    path = sem_dir / "tags_reviewed.yaml"
    if path.is_file():
        return yaml_load(path)
    raise FileNotFoundError(f"Mapping non trovato: {path}.")


def mapping_to_raw_structure(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converte il mapping categorie -> struttura cartelle in formato moderno:
      { 'raw': {categoria_kebab: {} ...}, 'contrattualistica': {} }
    """
    cats, _ = split_mapping(mapping)
    raw_children: Dict[str, Dict[str, Any]] = {
        to_kebab(k): {} for k in sorted(cats.keys(), key=lambda x: to_kebab(x))
    }
    return {
        "raw": raw_children,
        "contrattualistica": {},
    }


def write_raw_structure_yaml(
    slug: str, structure: Dict[str, Any], *, base_root: Path | str = "output"
) -> Path:
    """
    Scrive un YAML sintetico della struttura RAW in semantic/_raw_from_mapping.yaml (locale).
    """
    base_root = Path(base_root)
    sem_dir = ensure_within_and_resolve(
        base_root / f"timmy-kb-{slug}",
        base_root / f"timmy-kb-{slug}" / "semantic",
    )
    path = ensure_within_and_resolve(sem_dir, sem_dir / "_raw_from_mapping.yaml")
    safe_write_text_compat(path, yaml_dump(structure))
    return path
