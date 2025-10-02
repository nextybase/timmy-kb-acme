#!/usr/bin/env python3
# src/tools/clean_client_workspace.py
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Any, Optional

try:
    from googleapiclient.errors import HttpError  # type: ignore
except Exception:  # pragma: no cover

    class HttpError(Exception):
        """Fallback when googleapiclient is unavailable."""

        pass


import yaml

from src.pipeline.logging_utils import get_structured_logger, mask_partial
from src.pipeline.path_utils import ensure_within  # guard-rail path
from src.ui import clients_store  # per DB_FILE e formato YAML

LOG = get_structured_logger("tools.clean_client_workspace")


# ------------------------------- Helpers -------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _output_root() -> Path:
    return _repo_root() / "output"


def _workspace_dir(slug: str) -> Path:
    return _output_root() / f"timmy-kb-{slug}"


def _validate_slug(slug: str) -> None:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", slug):
        raise ValueError(
            f"Slug '{slug}' non valido. Usa minuscole, numeri e '-', senza spazi "
            f"e senza '-' iniziale/finale (es: 'acme-corp')."
        )


def _confirm(prompt: str, default: bool = False) -> bool:
    yn = " [Y/n] " if default else " [y/N] "
    ans = input(prompt + yn).strip().lower()
    if not ans:
        return default
    return ans in {"y", "yes", "s", "si", "sì"}


def _load_clients_yaml(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "clients": []}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "clients" not in data or not isinstance(data["clients"], list):
        data = {"version": data.get("version", 1), "clients": []}
    return data


def _write_clients_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
    tmp.replace(path)


def _find_drive_client_folder_id(service: Any, drive_id: str, slug: str) -> Optional[str]:
    """Find the client folder named `<slug>` at the Shared Drive root."""
    folder_mime = "application/vnd.google-apps.folder"
    q = f"name = '{slug}' and mimeType = '{folder_mime}' and trashed = false"
    resp = (
        service.files()
        .list(
            q=q,
            corpora="drive",
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields="files(id,name,parents,driveId)",
            spaces="drive",
        )
        .execute()
    )
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def _delete_on_drive_if_present(slug: str) -> None:
    """Se configurato, elimina l'intera cartella del cliente su Drive (idempotente)."""
    try:
        # Usiamo i wrapper esistenti; se non installati/settati, saltiamo senza fallire.
        from src.pipeline.context import ClientContext
        from src.pipeline.drive_utils import get_drive_service
    except Exception as exc:  # drive opzionale
        LOG.info("drive.skip.unavailable", extra={"reason": str(exc)})
        return

    # Carica env senza requisiti rigidi (non deve scrivere nulla in output/)
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    drive_id = (ctx.env or {}).get("DRIVE_ID")
    if not drive_id:
        LOG.info("drive.skip.no_parent_id")
        return

    try:
        service = get_drive_service(ctx)
    except Exception as exc:
        LOG.warning("drive.client.error", extra={"error": str(exc)})
        return

    folder_id = _find_drive_client_folder_id(service, drive_id, slug)
    if not folder_id:
        LOG.info("drive.folder.absent", extra={"slug": slug})
        return

    try:
        try:
            service.files().delete(fileId=folder_id, supportsAllDrives=True).execute()
            LOG.info("drive.folder.deleted", extra={"slug": slug, "folder_id": mask_partial(folder_id)})
        except HttpError as err:
            status = getattr(err, "status_code", None)
            if status is None:
                resp = getattr(err, "resp", None)
                status = getattr(resp, "status", None) if resp is not None else None
            if status == 403:
                service.files().update(
                    fileId=folder_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                ).execute()
                LOG.info("drive.folder.trashed", extra={"slug": slug, "folder_id": mask_partial(folder_id)})
            elif status == 404:
                LOG.info("drive.folder.absent", extra={"slug": slug})
            else:
                raise
    except Exception as exc:
        LOG.error(
            "drive.folder.delete_failed", extra={"slug": slug, "folder_id": mask_partial(folder_id), "error": str(exc)}
        )


# ------------------------------- Main ----------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Rimuove workspace su Drive (se configurato), poi cartella locale in output/ " "e l'entry nel DB clienti."
        )
    )
    p.add_argument("--slug", type=str, help="Slug cliente da cancellare (es. acme-srl)")
    p.add_argument("-y", "--yes", action="store_true", help="Non chiedere conferma interattiva")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    slug = (args.slug or input("Slug cliente da cancellare: ").strip()).lower()
    try:
        _validate_slug(slug)
    except Exception as exc:
        LOG.error("invalid.slug", extra={"slug": slug, "error": str(exc)})
        print(f"Slug non valido: {slug}")
        return 2

    ws_dir = _workspace_dir(slug)
    db_path = Path(clients_store.DB_FILE)

    # Riepilogo da confermare
    todo: list[str] = []
    todo.append("eventuale cartella su Google Drive (se configurato)")
    if ws_dir.exists():
        todo.append(f"cartella locale: {ws_dir}")
    if db_path.exists():
        db = _load_clients_yaml(db_path)
        if any((c or {}).get("slug") == slug for c in db.get("clients", [])):
            todo.append(f"entry in DB clienti: {db_path}")

    if not args.yes:
        print("ATTENZIONE: verranno rimossi/eliminati i seguenti elementi:")
        for item in todo:
            print(f" - {item}")
        if not _confirm("Procedo?", default=False):
            print("Operazione annullata.")
            return 0

    # 1) Elimina cartella cliente su Drive (prima, così non si ricrea config.yaml in locale)
    _delete_on_drive_if_present(slug)

    # 2) Elimina workspace locale (idempotente, con guardia di sicurezza)
    try:
        ensure_within(_output_root(), ws_dir)
        if ws_dir.exists():
            shutil.rmtree(ws_dir)
            LOG.info("local.workspace.deleted", extra={"slug": slug, "path": str(ws_dir)})
    except Exception as exc:
        LOG.error("local.workspace.delete_failed", extra={"slug": slug, "error": str(exc)})
        print(f"Errore durante la rimozione del workspace locale: {exc}")
        return 3

    # 3) Rimuovi dal DB clienti
    try:
        db = _load_clients_yaml(db_path)
        before = len(db.get("clients", []))
        db["clients"] = [c for c in db.get("clients", []) if (c or {}).get("slug") != slug]
        after = len(db.get("clients", []))
        if after != before:
            _write_clients_yaml(db_path, db)
            LOG.info("clients.db.updated", extra={"slug": slug, "path": str(db_path)})
    except Exception as exc:
        LOG.warning("clients.db.update_failed", extra={"slug": slug, "error": str(exc)})

    print("Pulizia completata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
