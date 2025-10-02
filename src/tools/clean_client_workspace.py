# src/tools/clean_client_workspace.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Delete a client's local workspace under output/ and remove its record
from clients_db/clients.yaml.

Usage:
  python -m src.tools.clean_client_workspace --slug <slug>
  python -m src.tools.clean_client_workspace --slug <slug> --force
  python -m src.tools.clean_client_workspace --slug <slug> --dry-run
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Any, List, Tuple

# Prefer existing utilities if available; otherwise, provide safe fallbacks.
try:
    from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe  # type: ignore
except Exception:  # pragma: no cover

    def ensure_within(base: Path, target: Path) -> None:
        base_r = base.resolve()
        tgt_r = target.resolve()
        if base_r not in tgt_r.parents and base_r != tgt_r:
            raise ValueError(f"{tgt_r} is not within {base_r}")

    def ensure_within_and_resolve(base: Path, target: Path) -> Path:
        ensure_within(base, target)
        return target.resolve()

    def read_text_safe(base: Path, target: Path, *, encoding: str = "utf-8") -> str:
        ensure_within(base, target)
        with target.open("r", encoding=encoding) as handle:
            return handle.read()


try:
    from pipeline.yaml_utils import yaml_dump, yaml_read  # type: ignore
except Exception:  # pragma: no cover
    import yaml  # type: ignore

    def yaml_read(
        base: Path | str | None = None,
        path: Path | str | None = None,
        *,
        text: str | None = None,
        encoding: str = "utf-8",
        use_cache: bool = False,
    ) -> Any:
        if text is not None:
            return yaml.safe_load(text)
        if base is None or path is None:
            raise ValueError("yaml_read fallback requires either text or (base, path)")
        base_path = Path(base)
        target_path = Path(path)
        payload = read_text_safe(base_path, target_path, encoding=encoding)
        return yaml.safe_load(payload)

    def yaml_dump(data: Any) -> str:
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


try:
    from pipeline.file_utils import safe_write_text  # type: ignore
except Exception:  # pragma: no cover

    def safe_write_text(
        path: Path,
        data: str,
        *,
        encoding: str = "utf-8",
        atomic: bool = True,
        fsync: bool = False,
    ) -> None:
        ensure_within(path.parent, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding=encoding)
        tmp.replace(path)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "output"
CLIENTS_DB = REPO_ROOT / "clients_db" / "clients.yaml"


def _validate_slug(slug: str) -> None:
    """
    Accept kebab-case only: [a-z0-9-], no leading/trailing hyphen, at least 1 char.
    """
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", slug):
        raise ValueError(
            f"Slug '{slug}' non valido. Usa minuscole, numeri e '-', senza spazi "
            f"e senza '-' iniziale/finale (es: 'acme-corp')."
        )


def _delete_workspace(slug: str, dry_run: bool) -> Tuple[bool, Path]:
    base = OUTPUT_ROOT / f"timmy-kb-{slug}"
    ensure_within(OUTPUT_ROOT, base)
    if not base.exists():
        return False, base
    if dry_run:
        print(f"[dry-run] Eliminerei cartella: {base}")
        return True, base
    shutil.rmtree(base)
    print(f"✅ Eliminata cartella: {base}")
    return True, base


def _remove_from_clients_db(slug: str, dry_run: bool) -> bool:
    """
    Rimuove lo slug da clients_db/clients.yaml.
    Supporta strutture: dict con 'clients': [ {slug: ...}, ... ],
    lista di dict, o dict keyed-by-slug.
    """
    if not CLIENTS_DB.exists():
        print(f"ℹ️  File non trovato, salto: {CLIENTS_DB}")
        return False

    try:
        data = yaml_read(CLIENTS_DB.parent, CLIENTS_DB)
    except Exception as e:
        print(f"⚠️  YAML non leggibile ({CLIENTS_DB}): {e}")
        return False

    changed = False

    # Caso 1: dict con chiave 'clients' -> lista
    if isinstance(data, dict) and isinstance(data.get("clients"), list):
        lst: List[Any] = data["clients"]
        before = len(lst)
        lst = [
            item
            for item in lst
            if not (
                (isinstance(item, dict) and str(item.get("slug", "")) == slug)
                or (isinstance(item, str) and item == slug)
            )
        ]
        if len(lst) != before:
            data["clients"] = lst
            changed = True

    # Caso 2: lista pura
    elif isinstance(data, list):
        before = len(data)
        data = [
            item
            for item in data
            if not (
                (isinstance(item, dict) and str(item.get("slug", "")) == slug)
                or (isinstance(item, str) and item == slug)
            )
        ]
        changed = len(data) != before

    # Caso 3: dict keyed-by-slug
    elif isinstance(data, dict):
        if slug in data:
            del data[slug]
            changed = True

    if not changed:
        print("ℹ️  Nessuna voce da rimuovere in clients_db/clients.yaml")
        return False

    new_text = yaml_dump(data)
    if dry_run:
        print(f"[dry-run] Aggiornerei {CLIENTS_DB} rimuovendo '{slug}'")
        return True

    safe_write_text(CLIENTS_DB, new_text)
    print(f"✅ Aggiornato file: {CLIENTS_DB} (rimossa voce '{slug}')")
    return True


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Delete local workspace and unregister client.")
    p.add_argument("--slug", help="Slug del cliente (kebab-case).")
    p.add_argument("--force", "-f", action="store_true", help="Salta la conferma.")
    p.add_argument("--dry-run", action="store_true", help="Non modifica nulla, mostra soltanto.")
    args = p.parse_args(argv)

    slug = args.slug or input("Inserisci lo slug del cliente: ").strip()
    _validate_slug(slug)

    if not args.force and not args.dry_run:
        ok = (
            input(f"Confermi eliminazione di output/timmy-kb-{slug} " f"e rimozione da {CLIENTS_DB.name}? [y/N]: ")
            .strip()
            .lower()
            == "y"
        )
        if not ok:
            print("Annullato.")
            return 0

    # 1) elimina cartella in output/
    _delete_workspace(slug, args.dry_run)

    # 2) rimuovi voce dal DB clienti (se presente)
    _remove_from_clients_db(slug, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
