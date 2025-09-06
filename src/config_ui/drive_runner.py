# src/config_ui/drive_runner.py
from __future__ import annotations

import io
import os
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import locali (dev UI)
from .mapping_editor import (
    split_mapping,
    load_tags_reviewed,
    mapping_to_raw_structure,
    write_raw_structure_yaml,
)
from .utils import to_kebab, ensure_within_and_resolve  # SSoT normalizzazione + path-safety

# Import pipeline (obbligatori in v1.8.0)
from pipeline.context import ClientContext
from pipeline.logging_utils import get_structured_logger
from pipeline.drive_utils import (
    get_drive_service,
    create_drive_folder,
    create_drive_structure_from_yaml,
    upload_config_to_drive_folder,
)


# ===== Logger =================================================================


def _get_logger(context: Optional[object] = None) -> Any:
    """Ritorna un logger strutturato del modulo pipeline.logging_utils."""
    return get_structured_logger("config_ui.drive_runner", context=context)


# ===== Creazione struttura Drive da mapping ===================================


def build_drive_from_mapping(
    slug: str,
    client_name: Optional[str],
    *,
    require_env: bool = True,
    base_root: Path | str = "output",
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, str]:
    """
    Crea su Drive:
      - cartella cliente con nome = slug
      - upload config.yaml
      - crea 'raw/' (dalle categorie del mapping) + 'contrattualistica/'
    Ritorna: {'client_folder_id': ..., 'raw_id': ..., 'contrattualistica_id': ...?}
    """
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = get_drive_service(ctx)

    drive_parent_id = ctx.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise RuntimeError("DRIVE_ID non impostato nell'ambiente.")

    # Cartella cliente (sotto DRIVE_ID)
    total_steps = 3
    step = 0
    client_folder_id = create_drive_folder(
        svc, slug, parent_id=drive_parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    step += 1
    if progress:
        progress(step, total_steps, "Cartella cliente creata")

    # Upload config.yaml nella cartella cliente
    upload_config_to_drive_folder(
        svc, ctx, parent_id=client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    step += 1
    if progress:
        progress(step, total_steps, "config.yaml caricato")

    # Struttura derivata dal mapping (locale -> YAML sintetico -> creazione su Drive)
    mapping = load_tags_reviewed(slug, base_root=base_root)
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)

    created_map = create_drive_structure_from_yaml(
        svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    step += 1
    if progress:
        progress(step, total_steps, "Struttura RAW/ creata")

    raw_id = created_map.get("raw")
    contr_id = created_map.get("contrattualistica") or created_map.get("CONTRATTUALISTICA")
    if not raw_id:
        raise RuntimeError("ID cartella 'raw' non reperito dalla creazione struttura.")

    out: Dict[str, str] = {"client_folder_id": client_folder_id, "raw_id": raw_id}
    if contr_id:
        out["contrattualistica_id"] = contr_id

    log.info(
        {"event": "drive_structure_created", "ids": {k: v[:6] + "..." for k, v in out.items()}}
    )
    return out


# ===== Helpers Drive ===========================================================


def _drive_list_folders(service: Any, parent_id: str) -> List[Dict[str, str]]:
    """Elenca le sottocartelle (id, name) immediate sotto parent_id."""
    results: List[Dict[str, str]] = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                spaces="drive",
                fields="nextPageToken, files(id, name)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageToken=page_token,
            )
            .execute()
        )
        results.extend({"id": f["id"], "name": f["name"]} for f in resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def _render_readme_pdf_bytes(title: str, descr: str, examples: List[str]) -> Tuple[bytes, str]:
    """Tenta PDF via reportlab, altrimenti TXT (fallback)."""
    try:
        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore
        from reportlab.lib.units import cm  # type: ignore

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        x, y = 2 * cm, height - 2 * cm

        def draw_line(t: str, font: str = "Helvetica", size: int = 11, leading: int = 14) -> None:
            nonlocal y
            c.setFont(font, size)
            for line in (t or "").splitlines() or [""]:
                c.drawString(x, y, line[:120])
                y -= leading
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm

        c.setTitle(f"README - {title}")
        draw_line(f"README - {title}", font="Helvetica-Bold", size=14, leading=18)
        y -= 4
        draw_line("")
        draw_line("Ambito:", font="Helvetica-Bold", size=12, leading=16)
        draw_line(descr or "")
        draw_line("")
        draw_line("Esempi:", font="Helvetica-Bold", size=12, leading=16)
        for ex in examples or []:
            draw_line(f"- {ex}")
        c.showPage()
        c.save()
        data = buf.getvalue()
        buf.close()
        return data, "application/pdf"
    except Exception:
        # fallback TXT
        lines = [f"README - {title}", "", "Ambito:", descr or "", "", "Esempi:"]
        lines += [f"- {ex}" for ex in (examples or [])]
        data = ("\n".join(lines)).encode("utf-8")
        return data, "text/plain"


def _drive_upload_bytes(service: Any, parent_id: str, name: str, data: bytes, mime: str) -> str:
    """Carica un file (bytes) in una cartella Drive."""
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    body = {"name": name, "parents": [parent_id], "mimeType": mime}
    file = (
        service.files()
        .create(
            body=body,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return str(file.get("id"))


# ===== README per ogni categoria raw (PDF o TXT fallback) =====================


def emit_readmes_for_raw(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    ensure_structure: bool = False,
) -> Dict[str, str]:
    """
    Per ogni categoria (sottocartella di raw) genera un README.pdf (o .txt fallback) con:
      - ambito (titolo), descrizione, esempi
    Upload in ciascuna sottocartella. Ritorna {category_name -> file_id}
    """
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = get_drive_service(ctx)

    mapping = load_tags_reviewed(slug, base_root=base_root)
    cats, _ = split_mapping(mapping)

    # crea/recupera struttura cliente; opzionalmente crea albero RAW da mapping
    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")
    client_folder_id = create_drive_folder(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )

    raw_id: Optional[str] = None
    if ensure_structure:
        structure = mapping_to_raw_structure(mapping)
        tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)
        created_map = create_drive_structure_from_yaml(
            svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
        )
        raw_id = created_map.get("raw")
    else:
        # Non ricreare la struttura: cerca la cartella 'raw' esistente
        sub = _drive_list_folders(svc, client_folder_id)
        name_to_id = {d["name"]: d["id"] for d in sub}
        raw_id = name_to_id.get("raw")

    if not raw_id:
        raise RuntimeError(
            "Cartella 'raw' non trovata/creata. Esegui 'Crea/aggiorna struttura Drive' e riprova."
        )

    # sottocartelle RAW
    subfolders = _drive_list_folders(svc, raw_id)
    name_to_id = {d["name"]: d["id"] for d in subfolders}

    uploaded: Dict[str, str] = {}
    for cat_name, meta in cats.items():
        folder_k = to_kebab(cat_name)  # riuso SSoT (niente duplicazioni)
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
            svc,
            folder_id,
            "README.pdf" if mime == "application/pdf" else "README.txt",
            data,
            mime,
        )
        uploaded[folder_k] = file_id

    log.info({"event": "raw_readmes_uploaded", "count": len(uploaded)})
    return uploaded


# ===== Download PDF da Drive â†’ raw/ locale ====================================


def download_raw_from_drive(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
) -> List[Path]:
    """
    Scarica i PDF presenti nelle sottocartelle di 'raw/' su Drive nella struttura locale:
      output/timmy-kb-<slug>/raw/<categoria>/<file>.pdf

    Ritorna la lista dei percorsi scritti localmente.
    """
    return download_raw_from_drive_with_progress(
        slug,
        base_root=base_root,
        require_env=require_env,
        overwrite=overwrite,
        logger=logger,
        on_progress=None,
    )

    # Variante con progress callback (UI helper)


def download_raw_from_drive_with_progress(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[Path]:
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = logger or _get_logger(ctx)
    svc = get_drive_service(ctx)

    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")

    client_folder_id = create_drive_folder(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    sub = _drive_list_folders(svc, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non presente su Drive. Crea prima la struttura.")

    raw_subfolders = _drive_list_folders(svc, raw_id)

    base_dir = Path(base_root) / f"timmy-kb-{slug}" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        from googleapiclient.http import MediaIoBaseDownload
    except Exception as e:  # pragma: no cover
        raise RuntimeError("googleapiclient non disponibile. Installa le dipendenze Drive.") from e

    written: List[Path] = []

    if on_progress:
        # Preconta solo se necessario per progress globale
        total = 0
        by_folder: Dict[str, List[Dict[str, str]]] = {}
        for folder in raw_subfolders:
            folder_id = folder["id"]
            q = f"'{folder_id}' in parents and " f"mimeType = 'application/pdf' and trashed = false"
            resp = (
                svc.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            files = resp.get("files", [])
            by_folder[folder_id] = files
            total += len(files)
        done = 0

        for folder in raw_subfolders:
            folder_name = folder["name"]
            folder_id = folder["id"]
            files = by_folder.get(folder_id, [])
            dest_dir = ensure_within_and_resolve(base_dir, base_dir / folder_name)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                file_id = f["id"]
                name = f["name"]
                safe_name = name.replace("\\", "_").replace("/", "_").strip() or "file.pdf"
                dest = ensure_within_and_resolve(dest_dir, dest_dir / safe_name)

                if dest.exists() and not overwrite:
                    log.info({"event": "raw_download_skip_exists", "path": str(dest)})
                    done += 1
                    on_progress(done, total, f"{folder_name}/{safe_name}")
                    continue

                request = svc.files().get_media(fileId=file_id)
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    _done = False
                    while not _done:
                        status, _done = downloader.next_chunk()
                os.replace(tmp, dest)
                written.append(dest)
                log.info({"event": "raw_downloaded", "path": str(dest)})
                done += 1
                on_progress(done, total, f"{folder_name}/{safe_name}")
    else:
        # Nessun progress: singolo passaggio senza pre-scan
        for folder in raw_subfolders:
            folder_name = folder["name"]
            folder_id = folder["id"]
            q = f"'{folder_id}' in parents and " f"mimeType = 'application/pdf' and trashed = false"
            resp = (
                svc.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            files = resp.get("files", [])
            dest_dir = ensure_within_and_resolve(base_dir, base_dir / folder_name)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                file_id = f["id"]
                name = f["name"]
                safe_name = name.replace("\\", "_").replace("/", "_").strip() or "file.pdf"
                dest = ensure_within_and_resolve(dest_dir, dest_dir / safe_name)

                if dest.exists() and not overwrite:
                    log.info({"event": "raw_download_skip_exists", "path": str(dest)})
                    continue

                request = svc.files().get_media(fileId=file_id)
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    _done = False
                    while not _done:
                        status, _done = downloader.next_chunk()
                os.replace(tmp, dest)
                written.append(dest)
                log.info({"event": "raw_downloaded", "path": str(dest)})

    log.info({"event": "raw_download_summary", "count": len(written)})
    return written
