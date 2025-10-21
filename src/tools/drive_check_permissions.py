#!/usr/bin/env python3
# Diagnosi permessi/capabilities sulla cartella cliente in Shared Drive
from __future__ import annotations

import argparse
from typing import Any, Optional

from ..pipeline.context import ClientContext
from ..pipeline.drive_utils import get_drive_service

FOLDER_MIME = "application/vnd.google-apps.folder"


def _find_client_folder(service: Any, parent_id: str, slug: str) -> Optional[dict]:
    q = f"'{parent_id}' in parents and " f"name = '{slug}' and " f"mimeType = '{FOLDER_MIME}' and trashed = false"
    res = (
        service.files()
        .list(
            q=q,
            spaces="drive",
            fields="files(id,name,driveId)",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = res.get("files", [])
    return files[0] if files else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Check Drive delete permissions on client folder")
    ap.add_argument("--slug", required=True)
    args = ap.parse_args()

    # Carica env (senza forzare requisiti rigidi)
    ctx = ClientContext.load(slug=args.slug, interactive=False, require_env=False, run_id=None)
    parent_id = (ctx.env or {}).get("DRIVE_ID")
    if not parent_id:
        print("❌ DRIVE_ID non definito nell'ambiente.")
        return 2

    service = get_drive_service(ctx)
    folder = _find_client_folder(service, parent_id, args.slug)
    if not folder:
        print(f"❌ Cartella per slug '{args.slug}' non trovata sotto DRIVE_ID.")
        return 1

    meta = (
        service.files()
        .get(
            fileId=folder["id"],
            fields=(
                "id,name,driveId,"
                "capabilities(canDelete,canTrash,canMoveItemWithinDrive,canMoveChildrenWithinDrive),"
                "permissions(emailAddress,role,displayName,deleted)"
            ),
            supportsAllDrives=True,
        )
        .execute()
    )

    print(f"📁 Folder: {meta.get('name')} ({meta.get('id')})")
    print("🔐 Capabilities:", meta.get("capabilities"))
    print("👥 Permissions:")
    for p in meta.get("permissions", []):
        print(f" - {p.get('displayName') or p.get('emailAddress')} → role={p.get('role')} deleted={p.get('deleted')}")

    can_delete = (meta.get("capabilities") or {}).get("canDelete")
    print(f"\n➡️  canDelete = {can_delete}  (serve 'fileOrganizer' o 'organizer' su Shared Drive)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
