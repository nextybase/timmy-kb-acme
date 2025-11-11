#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Diagnosi permessi/capabilities sulla cartella cliente in Shared Drive
from __future__ import annotations

import argparse
from typing import Any, Dict, Optional

from ..pipeline.context import ClientContext
from ..pipeline.drive_utils import get_drive_service
from ..pipeline.logging_utils import get_structured_logger

FOLDER_MIME = "application/vnd.google-apps.folder"
LOGGER = get_structured_logger("tools.drive_check_permissions")


def _find_client_folder(service: Any, parent_id: str, slug: str) -> Optional[Dict[str, Any]]:
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
        LOGGER.error(
            "tools.drive_check_permissions.missing_drive_id",
            extra={"slug": args.slug},
        )
        return 2

    service = get_drive_service(ctx)
    folder = _find_client_folder(service, parent_id, args.slug)
    if not folder:
        LOGGER.error(
            "tools.drive_check_permissions.folder_missing",
            extra={"slug": args.slug, "parent_id": parent_id},
        )
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

    LOGGER.info(
        "tools.drive_check_permissions.folder_meta",
        extra={
            "slug": args.slug,
            "folder_id": meta.get("id"),
            "folder_name": meta.get("name"),
            "capabilities": meta.get("capabilities"),
        },
    )

    permissions = []
    for perm in meta.get("permissions", []):
        permissions.append(
            {
                "display": perm.get("displayName") or perm.get("emailAddress"),
                "role": perm.get("role"),
                "deleted": perm.get("deleted"),
            }
        )
    if permissions:
        LOGGER.info(
            "tools.drive_check_permissions.permissions",
            extra={"slug": args.slug, "permissions": permissions},
        )

    can_delete = (meta.get("capabilities") or {}).get("canDelete")
    LOGGER.info(
        "tools.drive_check_permissions.can_delete",
        extra={"slug": args.slug, "can_delete": bool(can_delete)},
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
