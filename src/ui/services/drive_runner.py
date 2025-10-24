# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/drive_runner.py
from __future__ import annotations

import io
import logging
from glob import glob
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from pipeline.config_utils import get_client_config
from pipeline.context import ClientContext  # Import pipeline (obbligatori in v1.8.0)
from pipeline.path_utils import ensure_within_and_resolve

create_drive_folder: Callable[..., Any] | None
create_drive_minimal_structure: Callable[..., Any] | None
create_drive_raw_children_from_yaml: Callable[..., Any] | None
create_drive_structure_from_yaml: Callable[..., Any] | None
download_drive_pdfs_to_local: Callable[..., Any] | None
get_drive_service: Callable[[ClientContext], Any] | None
upload_config_to_drive_folder: Callable[..., Any] | None
create_local_base_structure: Callable[..., Any] | None

try:
    import pipeline.drive_utils as _du

    create_drive_folder = _du.create_drive_folder
    create_drive_minimal_structure = _du.create_drive_minimal_structure
    create_drive_raw_children_from_yaml = _du.create_drive_raw_children_from_yaml
    create_drive_structure_from_yaml = _du.create_drive_structure_from_yaml
    download_drive_pdfs_to_local = _du.download_drive_pdfs_to_local
    get_drive_service = _du.get_drive_service
    upload_config_to_drive_folder = _du.upload_config_to_drive_folder
    create_local_base_structure = _du.create_local_base_structure
except Exception:  # pragma: no cover
    create_drive_folder = None
    create_drive_minimal_structure = None
    create_drive_raw_children_from_yaml = None
    create_drive_structure_from_yaml = None
    download_drive_pdfs_to_local = None
    get_drive_service = None
    upload_config_to_drive_folder = None
    create_local_base_structure = None

from pipeline.logging_utils import get_structured_logger, mask_id_map

# Import locali (dev UI)
from ..components.mapping_editor import mapping_to_raw_structure  # usato solo se ensure_structure=True
from ..components.mapping_editor import write_raw_structure_yaml  # usato solo se ensure_structure=True
from ..components.mapping_editor import load_semantic_mapping
from ..utils import to_kebab  # SSoT normalizzazione + path-safety
from ..utils.workspace import workspace_root

# ===== Logger =================================================================


def _get_logger(context: Optional[object] = None) -> Any:
    """Ritorna un logger strutturato del modulo pipeline.logging_utils."""
    return get_structured_logger("ui.services.drive_runner", context=context)


def _require_drive_utils_ui() -> None:
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_minimal_structure):
        missing.append("create_drive_minimal_structure")
    if not callable(create_drive_raw_children_from_yaml):
        missing.append("create_drive_raw_children_from_yaml")
    if not callable(upload_config_to_drive_folder):
        missing.append("upload_config_to_drive_folder")
    if missing:
        raise RuntimeError(
            "Funzionalita Google Drive non disponibili nella UI: "
            f"{', '.join(missing)}. Installa gli extra con: pip install .[drive]"
        )


def _require_drive_minimal_ui() -> None:
    """Prerequisiti minimi per creare cartella cliente + struttura base e caricare il config."""
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_folder):
        missing.append("create_drive_folder")
    if not callable(create_drive_minimal_structure):
        missing.append("create_drive_minimal_structure")
    if not callable(upload_config_to_drive_folder):
        missing.append("upload_config_to_drive_folder")
    if missing:
        raise RuntimeError(
            "Funzionalita Google Drive non disponibili (fase minima): "
            f"{', '.join(missing)}. Installa gli extra con: pip install .[drive]"
        )


def _require_drive_for_raw_only() -> None:
    """Prerequisiti minimi per creare le sottocartelle RAW da YAML."""
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_raw_children_from_yaml):
        missing.append("create_drive_raw_children_from_yaml")
    if missing:
        raise RuntimeError(
            "Funzionalità Google Drive non disponibili (RAW da YAML): "
            f"{', '.join(missing)}. Installa gli extra con: pip install .[drive]"
        )


# =====================================================================
# Bootstrap minimo su Drive (+ upload config e aggiornamento config.yaml)
# =====================================================================
def ensure_drive_minimal_and_upload_config(slug: str, client_name: Optional[str] = None) -> Path:
    """
    Crea la struttura minima su Drive (cartella cliente + raw/ + contrattualistica/),
    carica il config su Drive e aggiorna `config.yaml` locale con gli ID Drive.
    Ritorna il path del config locale aggiornato.
    Richiede .env valido (SERVICE_ACCOUNT_FILE, DRIVE_ID, ecc.).
    """
    from timmykb.pre_onboarding import (  # import locale per evitare costi a import-time
        _create_local_structure,
        _drive_phase,
        _prepare_context_and_logger,
        _require_drive_utils,
    )

    ctx, logger, resolved_name = _prepare_context_and_logger(
        slug,
        interactive=False,
        require_env=True,  # necessari per accedere a Drive
        run_id=None,
        client_name=client_name,
    )
    cfg_path = cast(Path, _create_local_structure(ctx, logger, client_name=(resolved_name or slug)))

    # Verifica che le primitive Drive siano disponibili e configurate
    _require_drive_utils()

    # Esegue la fase Drive (creazione cartelle, upload config, aggiornamento ID locali)
    _drive_phase(
        ctx,
        logger,
        config_path=cfg_path,
        client_name=(resolved_name or slug),
        require_env=True,
    )
    return cfg_path


# ===== Creazione struttura Drive/Locale da cartelle_raw.yaml ==================


def build_drive_from_mapping(  # nome storico mantenuto per compatibilita UI
    slug: str,
    client_name: Optional[str],
    *,
    require_env: bool = True,
    base_root: Path | str = "output",
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, str]:
    """
    **Vision-first**:
      - legge `drive_raw_folder_id` (e gli altri ID) dal `config.yaml` del cliente;
      - legge `semantic/cartelle_raw.yaml` (derivato dal mapping Vision);
      - crea su Drive le sottocartelle di `raw/` secondo lo YAML;
      - allinea la struttura locale corrispondente.

    Ritorna: {'client_folder_id': ..., 'raw_id': ..., 'contrattualistica_id': ...}
    """
    _require_drive_for_raw_only()
    if get_drive_service is None or create_drive_raw_children_from_yaml is None:
        raise RuntimeError("Funzioni Drive non disponibili (RAW da YAML).")
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = get_drive_service(ctx)

    cfg = get_client_config(ctx) or {}
    client_folder_id = (cfg.get("drive_folder_id") or "").strip()
    raw_id = (cfg.get("drive_raw_folder_id") or "").strip()
    contr_id = (cfg.get("drive_contrattualistica_folder_id") or "").strip()
    if not raw_id:
        raise RuntimeError(
            "drive_raw_folder_id mancante nel config.yaml. " "Esegui prima la fase di bootstrap Drive (pre-Vision)."
        )

    root_dir = _resolve_workspace(base_root, slug)
    yaml_path = ensure_within_and_resolve(root_dir, Path(root_dir) / "semantic" / "cartelle_raw.yaml")
    if not yaml_path.exists():
        raise RuntimeError(f"File mancante: {yaml_path}. Esegui Vision o genera lo YAML e riprova.")

    raw_children_fn = create_drive_raw_children_from_yaml
    raw_children_fn(
        svc,
        yaml_path,
        raw_id,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
    )
    if progress:
        progress(1, 1, "Struttura RAW su Drive creata/aggiornata")

    if callable(create_local_base_structure):
        try:
            create_local_base_structure(context=ctx, yaml_structure_file=yaml_path)
        except Exception as exc:
            log.warning("local.structure.create_failed", extra={"error": str(exc)[:200]})
    else:
        log.debug("local.structure.skip", extra={"reason": "create_local_base_structure non disponibile"})

    result: Dict[str, str] = {
        "client_folder_id": client_folder_id,
        "raw_id": raw_id,
        "contrattualistica_id": contr_id,
    }
    log.info("drive.structure.created", extra={"ids": dict(mask_id_map(result))})
    return result


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


def _get_existing_client_folder_id(service: Any, parent_id: str, slug: str) -> Optional[str]:
    """
    Recupera l'id della cartella cliente senza crearla.
    Confronto casefold + normalizzazione kebab per tollerare varianti di naming.
    """
    slug_clean = slug.strip()
    target = to_kebab(slug_clean)
    accepted_names = {
        target,
        slug_clean.casefold(),
        f"timmy-kb-{target}",
    }
    for folder in _drive_list_folders(service, parent_id):
        name = (folder.get("name") or "").strip()
        folder_id = (folder.get("id") or "").strip()
        if not name or not folder_id:
            continue
        normalized = to_kebab(name)
        name_cf = name.casefold()
        if normalized in accepted_names or name_cf in accepted_names:
            return folder_id
    return None


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


def _drive_find_child_by_name(service: Any, parent_id: str, name: str) -> Optional[str]:
    """Ritorna l'ID del file con 'name' dentro parent_id (se esiste)."""
    q_name = name.replace("'", "\\'")
    resp = (
        service.files()
        .list(
            q=f"'{parent_id}' in parents and name = '{q_name}' and trashed = false",
            spaces="drive",
            fields="files(id, name)",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )
    files = resp.get("files") or []
    return files[0]["id"] if files else None


def _drive_upload_or_update_bytes(service: Any, parent_id: str, name: str, data: bytes, mime: str) -> str:
    """Crea o aggiorna un file (bytes) in una cartella Drive in modo idempotente."""
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    existing_id = _drive_find_child_by_name(service, parent_id, name)
    if existing_id:
        file = (
            service.files()
            .update(
                fileId=existing_id,
                media_body=media,
                supportsAllDrives=True,
                fields="id",
            )
            .execute()
        )
        return str(file.get("id"))
    else:
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


# ===== Pre-analisi Download (dry-run per la UI) =================================


def plan_raw_download(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
) -> Tuple[List[str], List[str]]:
    """
    Costruisce il piano di download dei PDF Drive -> locale (dry-run).

    Returns:
        conflicts: elenco "categoria/file.pdf" già presenti in locale
        labels: tutte le destinazioni che il downloader processerebbe
    """
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_folder):
        missing.append("create_drive_folder")
    if missing:
        raise RuntimeError(
            "Funzionalità Google Drive non disponibili (plan): "
            + ", ".join(missing)
            + ". Installa gli extra con: pip install .[drive]"
        )

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    service = cast(Callable[[ClientContext], Any], get_drive_service)(ctx)
    parent_id = (ctx.env or {}).get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato nell'ambiente")

    client_folder_id = _get_existing_client_folder_id(service, parent_id, slug)
    if not client_folder_id:
        raise RuntimeError("Cartella cliente non trovata su Drive: esegui prima 'Apri workspace'.")
    folders = _drive_list_folders(service, client_folder_id)
    raw_id = {item["name"]: item["id"] for item in folders}.get("raw")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non trovata sotto la cartella cliente su Drive")

    workspace_dir = _resolve_workspace(base_root, slug)
    local_root = ensure_within_and_resolve(workspace_dir, workspace_dir / "raw")
    Path(local_root).mkdir(parents=True, exist_ok=True)

    conflicts: list[str] = []
    labels: list[str] = []

    for file_info in _drive_list_pdfs(service, raw_id):
        name = (file_info.get("name") or "").strip()
        if not name.lower().endswith(".pdf"):
            continue
        labels.append(name)
        if (local_root / name).exists():
            conflicts.append(name)

    for folder in _drive_list_folders(service, raw_id):
        folder_name = (folder.get("name") or "").strip()
        folder_id = (folder.get("id") or "").strip()
        if not folder_name or not folder_id:
            continue
        for file_info in _drive_list_pdfs(service, folder_id):
            name = (file_info.get("name") or "").strip()
            if not name.lower().endswith(".pdf"):
                continue
            label = f"{folder_name}/{name}"
            labels.append(label)
            if (local_root / folder_name / name).exists():
                conflicts.append(label)

    def _dedupe_sorted(entries: list[str]) -> list[str]:
        ordered = dict.fromkeys(entries)
        return sorted(ordered.keys())

    return _dedupe_sorted(conflicts), _dedupe_sorted(labels)


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
        lines = [f"README - {title}", "", "Ambito:", descr or "", "", "Esempi:"]
        lines += [f"- {ex}" for ex in (examples or [])]
        data = ("\n".join(lines)).encode("utf-8")
        return data, "text/plain"


# ===== Estrattori Mapping (Vision only) =======================================


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _extract_categories_from_mapping(mapping: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Vision-only:
      - areas: [...]  (obbligatorio)
      - system_folders: { identity, glossario, ... } (opzionale)
    Ritorna: {cat_key -> {"ambito": str, "descrizione": str, "keywords": [str, ...]}}
    """
    cats: Dict[str, Dict[str, Any]] = {}

    # 1) Vision (areas: [...]) - OBBLIGATORIO
    areas = mapping.get("areas")
    if not isinstance(areas, list) or not areas:
        raise RuntimeError(
            "semantic_mapping.yaml non conforme al formato Vision: manca 'areas'. " "Rigenera il mapping con Vision."
        )

    for a in areas:
        if not isinstance(a, dict):
            continue
        key_raw = a.get("key") or a.get("ambito") or a.get("title") or ""
        key = to_kebab(str(key_raw))
        if not key:
            continue
        descr = str(a.get("descrizione_breve") or a.get("descrizione") or "")
        ambito = str(a.get("ambito") or key)

        # esempi/keywords: documents -> artefatti -> chunking_hints -> descrizione_dettagliata.include
        docs = _listify(a.get("documents"))
        artefatti = _listify(a.get("artefatti"))
        hints = _listify(a.get("chunking_hints"))
        dd = a.get("descrizione_dettagliata") or {}
        include = _listify(dd.get("include"))

        keywords = [x for x in (docs + artefatti + hints + include) if x]
        cats[key] = {"ambito": ambito, "descrizione": descr, "keywords": keywords}

    # 2) System folders (identity, glossario, ...) se presenti
    sys = mapping.get("system_folders")
    if isinstance(sys, dict):
        for sys_key, sys_val in sys.items():
            if not isinstance(sys_val, dict):
                continue
            key = to_kebab(str(sys_key))
            docs = _listify(sys_val.get("documents"))
            artifacts = _listify(sys_val.get("artefatti"))
            terms = _listify(sys_val.get("terms_hint"))
            keywords = [x for x in (docs + artifacts + terms) if x]
            cats.setdefault(key, {"ambito": key, "descrizione": "", "keywords": keywords})

    return cats


# ===== README per ogni categoria raw (PDF o TXT fallback) =====================


def emit_readmes_for_raw(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    ensure_structure: bool = False,
) -> Dict[str, str]:
    """Per ogni categoria Vision (sottocartella di raw) genera un README.pdf (o .txt fallback):

    - legge **semantic/semantic_mapping.yaml** in formato Vision;
    - costruisce il set categorie da `areas` (+ `system_folders` se presenti);
    - carica/aggiorna i file nelle rispettive sottocartelle già esistenti di raw/ su Drive.

    Ritorna {category_name -> file_id}
    """
    _require_drive_utils_ui()
    if get_drive_service is None or create_drive_folder is None:
        raise RuntimeError("Funzioni Drive non disponibili.")

    # Context & service
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    log = _get_logger(ctx)
    svc = get_drive_service(ctx)

    # Mapping Vision -> categorie
    mapping = load_semantic_mapping(slug, base_root=base_root)
    cats = _extract_categories_from_mapping(mapping or {})

    # Cartella cliente; NON crea la struttura raw se non richiesto esplicitamente
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
            svc,
            tmp_yaml,
            client_folder_id,
            redact_logs=bool(getattr(ctx, "redact_logs", False)),
        )
        raw_id = created_map.get("raw")
    else:
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
        folder_k = to_kebab(cat_name)
        folder_id = name_to_id.get(folder_k)
        if not folder_id:
            log.warning("raw.subfolder.missing", extra={"category": folder_k})
            continue
        raw_examples = meta.get("keywords") or []
        if not isinstance(raw_examples, list):
            raw_examples = [raw_examples]
        examples = [str(x).strip() for x in raw_examples if str(x).strip()]
        data, mime = _render_readme_pdf_bytes(
            title=meta.get("ambito") or folder_k,
            descr=meta.get("descrizione") or "",
            examples=examples,
        )
        file_id = _drive_upload_or_update_bytes(
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


def download_raw_from_drive_with_progress(
    slug: str,
    *,
    base_root: Path | str = "output",
    require_env: bool = True,
    overwrite: bool = False,
    logger: Optional[logging.Logger] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> List[Path]:
    """
    Scarica i PDF presenti nelle sottocartelle di 'raw/' su Drive nella struttura locale:
      <base_root>/timmy-kb-<slug>/raw/<categoria>/<file>.pdf

    Comportamento atteso dai test:
    - calcola la lista *completa* dei candidati (inclusi quelli già presenti);
    - chiama on_progress(done, total, "cat-x/<file>.pdf") **una volta per ogni candidato**, nell'ordine;
    - affida il download al downloader sottostante (che può scrivere solo i mancanti);
    - ritorna la lista dei file **nuovi** creati localmente.
    """
    # Guard: tutte le dipendenze minime devono esistere
    missing = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(download_drive_pdfs_to_local):
        missing.append("download_drive_pdfs_to_local")
    if missing:
        raise RuntimeError(
            "Funzionalità Google Drive non disponibili (download): "
            + ", ".join(missing)
            + ". Installa gli extra con: pip install .[drive]"
        )

    # Context & service
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=require_env, run_id=None)
    svc = cast(Callable[[ClientContext], Any], get_drive_service)(ctx)
    parent_id = (ctx.env or {}).get("DRIVE_ID")
    if not parent_id:
        raise RuntimeError("DRIVE_ID non impostato nell'ambiente")

    # Cartella cliente e 'raw'
    client_folder_id = _get_existing_client_folder_id(svc, parent_id, slug)
    if not client_folder_id:
        raise RuntimeError("Cartella cliente non trovata su Drive: esegui prima 'Apri workspace'.")
    sub = _drive_list_folders(svc, client_folder_id)
    name_to_id = {d["name"]: d["id"] for d in sub}
    raw_id = name_to_id.get("raw")
    if not raw_id:
        raise RuntimeError("Cartella 'raw' non trovata sotto la cartella cliente su Drive")

    # Local root (raw/)
    workspace_dir = _resolve_workspace(base_root, slug)
    local_root_dir = ensure_within_and_resolve(workspace_dir, workspace_dir / "raw")
    Path(local_root_dir).mkdir(parents=True, exist_ok=True)

    # 1) Costruisci la lista dei candidati (categoria/nomefile) nell'ordine atteso
    candidates: List[Tuple[str, str]] = []
    for f in _drive_list_pdfs(svc, raw_id):
        fname = (f.get("name") or "").strip()
        if not fname.lower().endswith(".pdf"):
            continue
        candidates.append(("", fname))
    for cat in _drive_list_folders(svc, raw_id):
        cat_name = cat.get("name") or ""
        cat_id = cat.get("id") or ""
        if not cat_name or not cat_id:
            continue
        for f in _drive_list_pdfs(svc, cat_id):
            fname = (f.get("name") or "").strip()
            if not fname.lower().endswith(".pdf"):
                continue
            candidates.append((cat_name, fname))

    total = len(candidates)

    # 2) Emissione progress per OGNI candidato (inclusi quelli che risulteranno skippati)
    if callable(on_progress):
        done = 0
        for cat_name, fname in candidates:
            done += 1
            try:
                label = f"{cat_name}/{fname}" if cat_name else fname
                on_progress(done, total, label)
            except Exception:
                pass

    # 3) Snapshot dei file presenti PRIMA del download
    before = set(Path(p).resolve() for p in glob(str(local_root_dir / "**" / "*.pdf"), recursive=True))

    # 4) Chiamata al downloader sottostante (accetta 'progress', ma qui non lo usiamo per i test)
    downloader = cast(Callable[..., Any], download_drive_pdfs_to_local)
    _ = downloader(
        svc,
        raw_id,
        str(local_root_dir),
        progress=(lambda *_a, **_k: None),
        context=ctx,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
        chunk_size=8 * 1024 * 1024,
    )

    # 5) Diff -> solo file nuovi creati
    after = set(Path(p).resolve() for p in glob(str(local_root_dir / "**" / "*.pdf"), recursive=True))
    created = sorted(after - before)
    return created


def _resolve_workspace(base_root: Path | str, slug: str) -> Path:
    """
    Determina la radice locale del workspace rispettando eventuali override di base_root.
    - Se base_root corrisponde al valore di default ('output'), sfrutta workspace_root per
      ereditare eventuali configurazioni dal ClientContext.
    - In caso di override (es. test/tempdir) applica la guardia di path-safety locale.
    """
    default_root = Path("output")
    candidate_root = Path(base_root)
    workspace_from_context: Path = workspace_root(slug)
    if candidate_root == default_root:
        return workspace_from_context
    safe_override: Path = ensure_within_and_resolve(candidate_root, candidate_root / f"timmy-kb-{slug}")
    return safe_override
