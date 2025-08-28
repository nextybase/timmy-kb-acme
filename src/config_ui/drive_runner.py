# src/config_ui/drive_runner.py
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Import da pipeline
try:
    from pipeline.context import ClientContext  # type: ignore
    from pipeline.logging_utils import get_structured_logger  # type: ignore
    from pipeline.drive_utils import (  # type: ignore
        get_drive_service,
        create_drive_folder,
        create_drive_structure_from_yaml,
        upload_config_to_drive_folder,
    )
except Exception:  # pragma: no cover
    ClientContext = None  # type: ignore
    get_structured_logger = None  # type: ignore
    get_drive_service = None  # type: ignore
    create_drive_folder = None  # type: ignore
    create_drive_structure_from_yaml = None  # type: ignore
    upload_config_to_drive_folder = None  # type: ignore

from .mapping_editor import (
    split_mapping,
    load_tags_reviewed,
    mapping_to_raw_structure,
    write_raw_structure_yaml,
)

# Logger
def _logger():
    if get_structured_logger is None:
        class _Stub:
            def info(self, *a, **k): pass
            def warning(self, *a, **k): pass
            def error(self, *a, **k): pass
            def exception(self, *a, **k): pass
        return _Stub()
    return get_structured_logger("config_ui.drive_runner")


def build_drive_from_mapping(slug: str, client_name: Optional[str], *,
                             require_env: bool = True,
                             base_root: Path | str = "output") -> Dict[str, str]:
    """
    Crea su Drive:
      - cartella cliente con nome = slug
      - upload config.yaml
      - crea 'raw/' (dalle categorie del mapping) + 'contrattualistica/'
    Ritorna dict: {'client_folder_id': ..., 'raw_id': ..., 'contrattualistica_id': ...?}
    """
    log = _logger()
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    svc = get_drive_service(ctx)

    drive_parent_id = ctx.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise RuntimeError("DRIVE_ID non impostato nell'ambiente.")

    # Cartella cliente
    client_folder_id = create_drive_folder(
        svc, slug, parent_id=drive_parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )

    # Upload config.yaml
    upload_config_to_drive_folder(
        svc, ctx, parent_id=client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )

    # Struttura derivata dal mapping
    mapping = load_tags_reviewed(slug, base_root=base_root)
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)

    created_map = create_drive_structure_from_yaml(
        svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )

    raw_id = created_map.get("raw") or created_map.get("RAW")
    contr_id = created_map.get("contrattualistica") or created_map.get("CONTRATTUALISTICA")
    if not raw_id:
        raise RuntimeError("ID cartella 'raw' non reperito dalla creazione struttura.")

    out = {"client_folder_id": client_folder_id, "raw_id": raw_id}
    if contr_id:
        out["contrattualistica_id"] = contr_id

    log.info({"event": "drive_structure_created", "ids": {k: v[:6] + "…" for k, v in out.items()}})
    return out


# ===== README per ogni categoria raw (PDF o TXT fallback) =====

def _drive_list_folders(service, parent_id: str) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    page_token = None
    while True:
        resp = service.files().list(
            q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            spaces="drive",
            fields="nextPageToken, files(id, name)",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            pageToken=page_token,
        ).execute()
        results.extend({"id": f["id"], "name": f["name"]} for f in resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def _render_readme_pdf_bytes(title: str, descr: str, examples: List[str]) -> Tuple[bytes, str]:
    """Tenta PDF via reportlab, altrimenti TXT."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
        from reportlab.lib.units import cm  # type: ignore
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        x, y = 2 * cm, height - 2 * cm

        def draw_line(t: str, font="Helvetica", size=11, leading=14):
            nonlocal y
            c.setFont(font, size)
            for line in (t or "").splitlines() or [""]:
                c.drawString(x, y, line[:120])
                y -= leading
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm

        c.setTitle(f"README — {title}")
        draw_line(f"README — {title}", font="Helvetica-Bold", size=14, leading=18)
        y -= 4
        draw_line("")
        draw_line("Ambito:", font="Helvetica-Bold", size=12, leading=16)
        draw_line(descr or "")
        draw_line("")
        draw_line("Esempi:", font="Helvetica-Bold", size=12, leading=16)
        for ex in examples or []:
            draw_line(f"• {ex}")
        c.showPage()
        c.save()
        data = buf.getvalue()
        buf.close()
        return data, "application/pdf"
    except Exception:
        # fallback TXT
        lines = [f"README — {title}", "", "Ambito:", descr or "", "", "Esempi:"]
        lines += [f"- {ex}" for ex in (examples or [])]
        data = ("\n".join(lines)).encode("utf-8")
        return data, "text/plain"


def _drive_upload_bytes(service, parent_id: str, name: str, data: bytes, mime: str) -> str:
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    body = {"name": name, "parents": [parent_id], "mimeType": mime}
    file = service.files().create(
        body=body,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file.get("id")


def emit_readmes_for_raw(slug: str, *, base_root: Path | str = "output",
                         require_env: bool = True) -> Dict[str, str]:
    """
    Per ogni categoria (sottocartella di raw) genera un README.pdf (o .txt fallback) con:
      - ambito (titolo), descrizione, esempi
    Upload in ciascuna sottocartella. Ritorna {category_name -> file_id}
    """
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")
    log = _logger()

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    svc = get_drive_service(ctx)

    mapping = load_tags_reviewed(slug, base_root=base_root)
    cats, _ = split_mapping(mapping)

    # crea/recupera struttura
    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")
    client_folder_id = create_drive_folder(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)
    created_map = create_drive_structure_from_yaml(
        svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    raw_id = created_map.get("raw") or created_map.get("RAW")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non trovata/creata.")

    # sottocartelle RAW
    subfolders = _drive_list_folders(svc, raw_id)
    name_to_id = {d["name"]: d["id"] for d in subfolders}

    uploaded: Dict[str, str] = {}
    for cat_name, meta in cats.items():
        folder_k = _to_kebab(cat_name)
        folder_id = name_to_id.get(folder_k)
        if not folder_id:
            log.warning({"event": "raw_subfolder_missing", "category": folder_k})
            continue
        data, mime = _render_readme_pdf_bytes(
            title=meta.get("ambito") or folder_k,
            descr=meta.get("descrizione") or "",
            examples=[str(x) for x in (meta.get("esempio") or []) if str(x).strip()],
        )
        file_id = _drive_upload_bytes(
            svc, folder_id,
            "README.pdf" if mime == "application/pdf" else "README.txt",
            data, mime
        )
        uploaded[folder_k] = file_id

    log.info({"event": "raw_readmes_uploaded", "count": len(uploaded)})
    return uploaded


# Local helper (usato in emit_readmes_for_raw)
def _to_kebab(s: str) -> str:
    s = s.strip().lower().replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s
