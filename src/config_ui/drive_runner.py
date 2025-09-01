# src/config_ui/drive_runner.py
from __future__ import annotations

import io
import os
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

# Import locali (dev UI)
from .mapping_editor import (
    split_mapping,
    load_tags_reviewed,
    mapping_to_raw_structure,
    write_raw_structure_yaml,
)
from .utils import to_kebab, ensure_within_and_resolve  # SSoT normalizzazione + path-safety

# Import da pipeline (con fallback per ambienti dev)
# Annotazioni esplicite (mypy): nomi possono essere riassegnati a None nel fallback
ClientContext: Any
get_structured_logger: Optional[Callable[..., Any]]
get_drive_service: Optional[Callable[..., Any]]
create_drive_folder: Optional[Callable[..., Any]]
create_drive_structure_from_yaml: Optional[Callable[..., Any]]
upload_config_to_drive_folder: Optional[Callable[..., Any]]
try:
    import pipeline.context as _context
    import pipeline.logging_utils as _logging_utils
    import pipeline.drive_utils as _drive_utils

    ClientContext = _context.ClientContext
    get_structured_logger = _logging_utils.get_structured_logger
    get_drive_service = _drive_utils.get_drive_service
    create_drive_folder = _drive_utils.create_drive_folder
    create_drive_structure_from_yaml = _drive_utils.create_drive_structure_from_yaml
    upload_config_to_drive_folder = _drive_utils.upload_config_to_drive_folder
except Exception:  # pragma: no cover
    ClientContext = None
    get_structured_logger = None
    get_drive_service = None
    create_drive_folder = None
    create_drive_structure_from_yaml = None
    upload_config_to_drive_folder = None


# ===== Narrow helper per Optional[Callable] (fix Pylance: reportOptionalCall) =====

F = TypeVar("F", bound=Callable[..., object])


def _require_callable(fn: Optional[F], name: str) -> F:
    """
    Narrow di tipo: se la funzione è None, alza un errore chiaro.
    Dopo questo cast Pylance sa che 'fn' è Callable e non più Optional.
    """
    if fn is None:
        raise RuntimeError(
            f"Funzione '{name}' non disponibile: verifica dipendenze/credenziali Drive."
        )
    return fn


# ===== Logger =================================================================


def _get_logger(context: Optional[object] = None) -> Any:
    """Ritorna un logger strutturato; fallback no-op in assenza del modulo pipeline."""
    if get_structured_logger is None:

        class _Stub:
            def info(self, *a: Any, **k: Any) -> None:
                pass

            def warning(self, *a: Any, **k: Any) -> None:
                pass

            def error(self, *a: Any, **k: Any) -> None:
                pass

            def exception(self, *a: Any, **k: Any) -> None:
                pass

        return _Stub()
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
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = _require_callable(get_drive_service, "get_drive_service")(ctx)

    drive_parent_id = ctx.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise RuntimeError("DRIVE_ID non impostato nell'ambiente.")

    # Cartella cliente (sotto DRIVE_ID)
    total_steps = 3
    step = 0
    client_folder_id = _require_callable(create_drive_folder, "create_drive_folder")(
        svc, slug, parent_id=drive_parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    step += 1
    if progress:
        progress(step, total_steps, "Cartella cliente creata")

    # Upload config.yaml nella cartella cliente
    _require_callable(upload_config_to_drive_folder, "upload_config_to_drive_folder")(
        svc, ctx, parent_id=client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    step += 1
    if progress:
        progress(step, total_steps, "config.yaml caricato")

    # Struttura derivata dal mapping (locale -> YAML sintetico -> creazione su Drive)
    mapping = load_tags_reviewed(slug, base_root=base_root)
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)

    created_map = _require_callable(
        create_drive_structure_from_yaml, "create_drive_structure_from_yaml"
    )(svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False)))
    step += 1
    if progress:
        progress(step, total_steps, "Struttura RAW/ creata")

    raw_id = created_map.get("raw") or created_map.get("RAW")
    contr_id = created_map.get("contrattualistica") or created_map.get("CONTRATTUALISTICA")
    if not raw_id:
        raise RuntimeError("ID cartella 'raw' non reperito dalla creazione struttura.")

    out: Dict[str, str] = {"client_folder_id": client_folder_id, "raw_id": raw_id}
    if contr_id:
        out["contrattualistica_id"] = contr_id

    log.info({"event": "drive_structure_created", "ids": {k: v[:6] + "…" for k, v in out.items()}})
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
    slug: str, *, base_root: Path | str = "output", require_env: bool = True
) -> Dict[str, str]:
    """
    Per ogni categoria (sottocartella di raw) genera un README.pdf (o .txt fallback) con:
      - ambito (titolo), descrizione, esempi
    Upload in ciascuna sottocartella. Ritorna {category_name -> file_id}
    """
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = _require_callable(get_drive_service, "get_drive_service")(ctx)

    mapping = load_tags_reviewed(slug, base_root=base_root)
    cats, _ = split_mapping(mapping)

    # crea/recupera struttura
    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")
    client_folder_id = _require_callable(create_drive_folder, "create_drive_folder")(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)
    created_map = _require_callable(
        create_drive_structure_from_yaml, "create_drive_structure_from_yaml"
    )(svc, tmp_yaml, client_folder_id, redact_logs=bool(getattr(ctx, "redact_logs", False)))
    raw_id = created_map.get("raw") or created_map.get("RAW")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non trovata/creata.")

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


# ===== Download PDF da Drive → raw/ locale ====================================


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
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = logger or _get_logger(ctx)
    svc = _require_callable(get_drive_service, "get_drive_service")(ctx)

    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")

    # Trova/crea cartella cliente e RAW
    client_folder_id = _require_callable(create_drive_folder, "create_drive_folder")(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    sub = _drive_list_folders(svc, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw") or name_to_id.get("RAW")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non presente su Drive. Crea prima la struttura.")

    # Elenca le sottocartelle di RAW
    raw_subfolders = _drive_list_folders(svc, raw_id)

    # Base dir locale
    base_dir = Path(base_root) / f"timmy-kb-{slug}" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Import per download binario
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except Exception as e:  # pragma: no cover
        raise RuntimeError("googleapiclient non disponibile. Installa le dipendenze Drive.") from e

    written: List[Path] = []

    for folder in raw_subfolders:
        folder_name = folder["name"]  # già kebab-case dal provisioning
        folder_id = folder["id"]

        # Elenca i PDF in questa sottocartella
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

        # Destinazione locale
        dest_dir = ensure_within_and_resolve(base_dir, base_dir / folder_name)
        dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            file_id = f["id"]
            name = f["name"]
            # Normalizza nome file (evita path traversal)
            safe_name = name.replace("\\", "_").replace("/", "_").strip() or "file.pdf"
            dest = ensure_within_and_resolve(dest_dir, dest_dir / safe_name)

            if dest.exists() and not overwrite:
                log.info({"event": "raw_download_skip_exists", "path": str(dest)})
                continue

            request = svc.files().get_media(fileId=file_id)
            tmp = dest.with_suffix(dest.suffix + ".part")

            # Download chunked su file temporaneo
            with open(tmp, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

            # Commit atomico
            os.replace(tmp, dest)
            written.append(dest)
            log.info({"event": "raw_downloaded", "path": str(dest)})

    log.info({"event": "raw_download_summary", "count": len(written)})
    return written


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
    if ClientContext is None or get_drive_service is None:
        raise RuntimeError("API Drive/Context non disponibili nel repo.")

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = logger or _get_logger(ctx)
    svc = _require_callable(get_drive_service, "get_drive_service")(ctx)

    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")

    client_folder_id = _require_callable(create_drive_folder, "create_drive_folder")(
        svc, slug, parent_id=parent_id, redact_logs=bool(getattr(ctx, "redact_logs", False))
    )
    sub = _drive_list_folders(svc, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw") or name_to_id.get("RAW")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non presente su Drive. Crea prima la struttura.")

    raw_subfolders = _drive_list_folders(svc, raw_id)

    base_dir = Path(base_root) / f"timmy-kb-{slug}" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        from googleapiclient.http import MediaIoBaseDownload
    except Exception as e:  # pragma: no cover
        raise RuntimeError("googleapiclient non disponibile. Installa le dipendenze Drive.") from e

    # Preconta
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

    written: List[Path] = []
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
                if on_progress:
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
            if on_progress:
                on_progress(done, total, f"{folder_name}/{safe_name}")

    log.info({"event": "raw_download_summary", "count": len(written)})
    return written
