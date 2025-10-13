# src/ui/services/drive_runner.py
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import pipeline (obbligatori in v1.8.0)
from pipeline.context import ClientContext

create_drive_folder: Callable[..., Any] | None
create_drive_structure_from_yaml: Callable[..., Any] | None
download_drive_pdfs_to_local: Callable[..., Any] | None
get_drive_service: Callable[[ClientContext], Any] | None
upload_config_to_drive_folder: Callable[..., Any] | None

try:
    import pipeline.drive_utils as _du

    create_drive_folder = _du.create_drive_folder
    create_drive_structure_from_yaml = _du.create_drive_structure_from_yaml
    download_drive_pdfs_to_local = _du.download_drive_pdfs_to_local
    get_drive_service = _du.get_drive_service
    upload_config_to_drive_folder = _du.upload_config_to_drive_folder
except Exception:  # pragma: no cover
    create_drive_folder = None
    create_drive_structure_from_yaml = None
    download_drive_pdfs_to_local = None
    get_drive_service = None
    upload_config_to_drive_folder = None
from pipeline.logging_utils import get_structured_logger, mask_id_map
from pipeline.path_utils import sanitize_filename

# Import locali (dev UI)
from ui.components.mapping_editor import (
    load_semantic_mapping,
    mapping_to_raw_structure,
    split_mapping,
    write_raw_structure_yaml,
)
from ui.utils import ensure_within_and_resolve, to_kebab  # SSoT normalizzazione + path-safety

# ===== Logger =================================================================


def _get_logger(context: Optional[object] = None) -> Any:
    """Ritorna un logger strutturato del modulo pipeline.logging_utils."""
    return get_structured_logger("ui.services.drive_runner", context=context)


def _require_drive_utils_ui() -> None:
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_folder):
        missing.append("create_drive_folder")
    if not callable(create_drive_structure_from_yaml):
        missing.append("create_drive_structure_from_yaml")
    if not callable(upload_config_to_drive_folder):
        missing.append("upload_config_to_drive_folder")
    if missing:
        raise RuntimeError(
            "Funzionalitâ”œÃ¡ Google Drive non disponibili nella UI: "
            f"{', '.join(missing)}. Installa gli extra con: pip install .[drive]"
        )


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
    _require_drive_utils_ui()
    if (
        get_drive_service is None
        or create_drive_folder is None
        or create_drive_structure_from_yaml is None
        or upload_config_to_drive_folder is None
    ):
        raise RuntimeError("Funzionalità Google Drive non disponibili. Installa gli extra `pip install .[drive]`.")
    # Carica .env se presente per popolare SERVICE_ACCOUNT_FILE/DRIVE_ID
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
        svc,
        slug,
        parent_id=drive_parent_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )
    step += 1
    if progress:
        progress(step, total_steps, "Cartella cliente creata")

    # Upload config.yaml nella cartella cliente (il 4° parametro è keyword-only)
    upload_config_to_drive_folder(
        svc,
        ctx,
        client_folder_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )
    step += 1
    if progress:
        progress(step, total_steps, "config.yaml caricato")

    # Struttura derivata dal mapping (locale -> YAML sintetico -> creazione su Drive)
    mapping = load_semantic_mapping(slug, base_root=base_root)
    structure = mapping_to_raw_structure(mapping)
    tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)

    created_map = create_drive_structure_from_yaml(
        svc,
        tmp_yaml,
        client_folder_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
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

    log.info("drive.structure.created", extra={"ids": dict(mask_id_map(out))})
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


def _drive_list_pdfs(service: Any, parent_id: str) -> List[Dict[str, str]]:
    """Elenca tutti i PDF (con paginazione) sotto una cartella Drive."""
    results: List[Dict[str, str]] = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=f"'{parent_id}' in parents and mimeType = 'application/pdf' and trashed = false",
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, size)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageToken=page_token,
            )
            .execute()
        )
        results.extend(resp.get("files", []) or [])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def _render_readme_pdf_bytes(title: str, descr: str, examples: List[str]) -> Tuple[bytes, str]:
    """Tenta PDF via reportlab, altrimenti TXT (fallback)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfgen import canvas

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
    from googleapiclient.http import MediaIoBaseUpload

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
    """Per ogni categoria (sottocartella di raw) genera un README.pdf (o .txt fallback) con:

    - ambito (titolo), descrizione, esempi
    Upload in ciascuna sottocartella. Ritorna {category_name -> file_id}
    """
    _require_drive_utils_ui()
    if get_drive_service is None or create_drive_folder is None:
        raise RuntimeError("Funzioni Drive non disponibili.")
    # Carica .env per SERVICE_ACCOUNT_FILE/DRIVE_ID se disponibile
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = get_drive_service(ctx)

    mapping = load_semantic_mapping(slug, base_root=base_root)
    cats, _ = split_mapping(mapping)

    # crea/recupera struttura cliente; opzionalmente crea albero RAW da mapping
    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")
    client_folder_id = create_drive_folder(
        svc,
        slug,
        parent_id=parent_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )

    raw_id: Optional[str] = None
    if ensure_structure:
        if create_drive_structure_from_yaml is None:
            raise RuntimeError("create_drive_structure_from_yaml non disponibile.")
        structure = mapping_to_raw_structure(mapping)
        tmp_yaml = write_raw_structure_yaml(slug, structure, base_root=base_root)
        created_map = create_drive_structure_from_yaml(
            svc, tmp_yaml, client_folder_id, bool(getattr(ctx, "redact_logs", False))
        )
        raw_id = created_map.get("raw")
    else:
        # Non ricreare la struttura: cerca la cartella 'raw' esistente
        sub = _drive_list_folders(svc, client_folder_id)
        name_to_id = {d["name"]: d["id"] for d in sub}
        raw_id = name_to_id.get("raw")

    if not raw_id:
        raise RuntimeError("Cartella 'raw' non trovata/creata. Esegui 'Crea/aggiorna struttura Drive' e riprova.")

    # sottocartelle RAW
    subfolders = _drive_list_folders(svc, raw_id)
    name_to_id = {d["name"]: d["id"] for d in subfolders}

    uploaded: Dict[str, str] = {}
    for cat_name, meta in cats.items():
        folder_k = to_kebab(cat_name)  # riuso SSoT (niente duplicazioni)
        folder_id = name_to_id.get(folder_k)
        if not folder_id:
            log.warning("raw.subfolder.missing", extra={"category": folder_k})
            continue
        raw_examples = meta.get("keywords")
        if raw_examples is None:
            raw_examples = []
        if not isinstance(raw_examples, list):
            raw_examples = [raw_examples]
        examples = [str(x).strip() for x in raw_examples if str(x).strip()]
        data, mime = _render_readme_pdf_bytes(
            title=meta.get("ambito") or folder_k,
            descr=meta.get("descrizione") or "",
            examples=examples,
        )
        file_id = _drive_upload_bytes(
            svc,
            folder_id,
            "README.pdf" if mime == "application/pdf" else "README.txt",
            data,
            mime,
        )
        uploaded[folder_k] = file_id

    log.info("raw.readmes.uploaded", extra={"count": len(uploaded)})
    return uploaded


# ===== Download PDF da Drive -> raw/ locale ====================================


def download_raw_from_drive(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
) -> List[Path]:
    """Scarica i PDF presenti nelle sottocartelle di 'raw/' su Drive nella struttura locale:
    output/timmy-kb-<slug>/raw/<categoria>/<file>.pdf.

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
    # Guard specifica per il download: richiede solo funzioni necessarie
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_folder):
        missing.append("create_drive_folder")
    if not callable(download_drive_pdfs_to_local):
        missing.append("download_drive_pdfs_to_local")
    if missing:
        raise RuntimeError(
            "FunzionalitÃ  Google Drive non disponibili nella UI (download): "
            f"{', '.join(missing)}. Installa gli extra con: pip install .[drive]"
        )
    if get_drive_service is None or create_drive_folder is None or download_drive_pdfs_to_local is None:
        raise RuntimeError("Funzioni Drive richieste per il download assenti nonostante i controlli preliminari.")
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = logger or _get_logger(ctx)
    svc = get_drive_service(ctx)

    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")

    client_folder_id = create_drive_folder(
        svc,
        slug,
        parent_id=parent_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )
    sub = _drive_list_folders(svc, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non presente su Drive. Crea prima la struttura.")

    raw_subfolders = _drive_list_folders(svc, raw_id)
    root_pdfs = _drive_list_pdfs(svc, raw_id)

    base_dir = Path(base_root) / f"timmy-kb-{slug}" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []

    if on_progress:
        # progress_cb: on_progress is guaranteed non-None here
        progress_cb: Callable[[int, int, str], None] = on_progress

        # Pre-scan: raccogli lista file per folder e calcola total una sola volta
        by_folder: Dict[str, List[Dict[str, str]]] = {}
        name_map: Dict[str, str] = {}
        for folder in raw_subfolders:
            folder_id = folder["id"]
            by_folder[folder_id] = _drive_list_pdfs(svc, folder_id)
            name_map[folder_id] = folder["name"]
        total = len(root_pdfs) + sum(len(v) for v in by_folder.values())
        pre_sizes: Dict[str, int] = {}
        label_map: Dict[str, str] = {}
        candidates: List[Path] = []
        done = 0

        # Secondo pass: prepara dir, registra skip deterministici e mappa etichette
        folder_specs = [
            ("", root_pdfs, base_dir),
            *[
                (
                    name_map[folder["id"]],
                    by_folder.get(folder["id"], []),
                    ensure_within_and_resolve(base_dir, base_dir / name_map[folder["id"]]),
                )
                for folder in raw_subfolders
            ],
        ]
        for folder_name, files, dest_dir in folder_specs:
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                name = f.get("name") or ""
                remote_size = int(f.get("size") or 0)
                safe_name = sanitize_filename(name) or "file"
                if not safe_name.lower().endswith(".pdf"):
                    safe_name += ".pdf"
                dest = ensure_within_and_resolve(dest_dir, dest_dir / safe_name)
                candidates.append(dest)
                label = f"{folder_name}/{safe_name}" if folder_name else safe_name
                label_map[str(dest)] = label
                if dest.exists():
                    try:
                        pre_sizes[str(dest)] = dest.stat().st_size
                    except OSError:
                        pre_sizes[str(dest)] = -1
                # Conta subito gli skip deterministici (stessa size e no overwrite)
                try:
                    if dest.exists() and not overwrite and remote_size > 0 and dest.stat().st_size == remote_size:
                        log.info("raw.download.skip.exists", extra={"file_path": str(dest)})
                        done += 1
                        progress_cb(done, total, label)
                except OSError:
                    # Non interrompere il flusso per errori di stat() su Windows
                    log.debug("pre-scan.stat.failed", extra={"file_path": str(dest)}, exc_info=True)

        # Adapter di progress: intercetta i log del downloader pipeline
        class _ProgressHandler(logging.Handler):
            def __init__(self, *, total: int, start_done: int, label_map: Dict[str, str]) -> None:
                super().__init__(level=logging.INFO)
                self.total = total
                self.done = start_done
                self.label_map = label_map

            def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
                try:
                    if record.name == "pipeline.drive.download" and record.getMessage() == "download.ok":
                        path = getattr(record, "file_path", None) or record.__dict__.get("file_path")
                        label = self.label_map.get(str(path), str(path) if path else "-")
                        self.done += 1
                        try:
                            progress_cb(self.done, self.total, label)
                        except Exception:
                            # Non deve mai spezzare il logging della pipeline
                            logging.getLogger("ui.services.drive_runner").debug(
                                "progress.callback.failed", exc_info=True
                            )
                except Exception:
                    # Evita try/except/pass silenziosi: traccia in debug
                    logging.getLogger("ui.services.drive_runner").debug("progress.emit.failed", exc_info=True)

        dl_logger = get_structured_logger("pipeline.drive.download", context=ctx)
        ph = _ProgressHandler(total=total, start_done=done, label_map=label_map)
        dl_logger.addHandler(ph)
        try:
            # Esegui il download delegato
            download_drive_pdfs_to_local(
                svc,
                raw_id,
                base_dir,
                progress=False,
                context=ctx,
                redact_logs=bool(getattr(ctx, "redact_logs", False)),
            )
        finally:
            dl_logger.removeHandler(ph)

        # Post-scan per comporre la lista dei file nuovi/aggiornati
        for dest in candidates:
            try:
                size_now = dest.stat().st_size
            except OSError:
                continue
            size_prev = pre_sizes.get(str(dest), None)
            if size_prev is None or size_prev != size_now:
                written.append(dest)
    else:
        # Nessun progress: singolo passaggio senza pre-scan
        # Pre-scan
        pre_sizes_noprog: Dict[str, int] = {}
        candidates_noprog: List[Path] = []
        # File direttamente sotto raw/
        for f in root_pdfs:
            name = f.get("name") or ""
            safe_name = sanitize_filename(name) or "file"
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"
            dest = ensure_within_and_resolve(base_dir, base_dir / safe_name)
            candidates_noprog.append(dest)
            if dest.exists():
                try:
                    pre_sizes_noprog[str(dest)] = dest.stat().st_size
                except OSError:
                    pre_sizes_noprog[str(dest)] = -1

        for folder in raw_subfolders:
            folder_name = folder["name"]
            folder_id = folder["id"]
            files = _drive_list_pdfs(svc, folder_id)
            dest_dir = ensure_within_and_resolve(base_dir, base_dir / folder_name)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                name = f.get("name") or ""
                safe_name = sanitize_filename(name) or "file"
                if not safe_name.lower().endswith(".pdf"):
                    safe_name += ".pdf"
                dest = ensure_within_and_resolve(dest_dir, dest_dir / safe_name)
                candidates_noprog.append(dest)
                if dest.exists():
                    try:
                        pre_sizes_noprog[str(dest)] = dest.stat().st_size
                    except OSError:
                        pre_sizes_noprog[str(dest)] = -1

        # Download via pipeline
        download_drive_pdfs_to_local(
            svc,
            raw_id,
            base_dir,
            progress=False,
            context=ctx,
            redact_logs=bool(getattr(ctx, "redact_logs", False)),
        )

        # Post-scan: costruisci lista dei file nuovi/aggiornati
        for dest in candidates_noprog:
            try:
                size_now = dest.stat().st_size
            except OSError:
                continue
            size_prev = pre_sizes_noprog.get(str(dest), None)
            if size_prev is None or size_prev != size_now:
                written.append(dest)

    log.info("raw.download.summary", extra={"count": len(written)})
    return written


# Verifica conflitti tra file su Drive e in locale


def plan_raw_download(slug: str, require_env: bool = True) -> Tuple[List[str], List[str]]:
    """
    Restituisce (conflicts, labels):
      - conflicts: path relativi (rispetto a output/timmy-kb-<slug>/raw) dei file che esistono giÃ  in locale
      - labels:   path relativi di TUTTE le destinazioni previste (preview del piano di download)

    Dipendenze interne a questo modulo:
      - ClientContext.load(...)
      - get_drive_service(ctx)
      - create_drive_folder(service, slug, parent_id, redact_logs)
      - _drive_list_folders(service, parent_id)
      - _drive_list_pdfs(service, parent_id)
      - sanitize_filename(name)
      - ensure_within_and_resolve(base_dir, path)

    Lancia RuntimeError in caso di prerequisiti mancanti (es. DRIVE_ID non impostato).
    """
    _require_drive_utils_ui()
    if not callable(get_drive_service) or not callable(create_drive_folder):
        raise RuntimeError("Funzioni Drive non disponibili.")
    if get_drive_service is None or create_drive_folder is None:
        raise RuntimeError("Funzioni Drive non disponibili.")

    folder_lister = _drive_list_folders
    pdf_lister = _drive_list_pdfs
    filename_sanitizer = sanitize_filename
    path_resolver = ensure_within_and_resolve

    # Carica contesto e service
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    except TypeError:
        # compat firma
        ctx = ClientContext.load(slug=slug, interactive=False)
    service = get_drive_service(ctx)

    parent_id = ctx.env.get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato.")

    client_folder_id = create_drive_folder(
        service,
        slug,
        parent_id=parent_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )

    # Individua cartella raw del cliente
    sub = folder_lister(service, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non presente su Drive. Crea prima la struttura di base.")

    # Listing PDF in raw/ e sottocartelle
    raw_subfolders = folder_lister(service, raw_id)
    root_pdfs = pdf_lister(service, raw_id)

    base_dir = Path("output") / f"timmy-kb-{slug}" / "raw"
    base_dir.mkdir(parents=True, exist_ok=True)

    conflicts: List[str] = []
    labels: List[str] = []

    # File direttamente in raw/
    for f in root_pdfs:
        name = (f.get("name") or "").strip()
        safe_name = filename_sanitizer(name) or "file"
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        dest = Path(path_resolver(base_dir, base_dir / safe_name))
        label = safe_name
        labels.append(label)
        if Path(dest).exists():
            conflicts.append(label)

    # File nelle sottocartelle
    for folder in raw_subfolders:
        folder_name = folder["name"]
        folder_id = folder["id"]
        files = pdf_lister(service, folder_id)
        dest_dir = Path(path_resolver(base_dir, base_dir / folder_name))
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        for f in files:
            name = (f.get("name") or "").strip()
            safe_name = filename_sanitizer(name) or "file"
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"
            dest = Path(path_resolver(dest_dir, Path(dest_dir) / safe_name))
            label = f"{folder_name}/{safe_name}"
            labels.append(label)
            if Path(dest).exists():
                conflicts.append(label)

    return conflicts, labels
