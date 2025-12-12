# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/services/drive_runner.py
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

from pipeline.config_utils import get_client_config
from pipeline.drive.download_steps import compute_created, discover_candidates, emit_progress, snapshot_existing
from pipeline.exceptions import WorkspaceLayoutInvalid
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.workspace_layout import WorkspaceLayout

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
from ..utils.context_cache import get_client_context

if TYPE_CHECKING:
    from pipeline.context import ClientContext
else:  # pragma: no cover
    ClientContext = Any  # type: ignore[misc]

# ===== Logger =================================================================


def _get_logger(context: Optional[object] = None) -> Any:
    """Ritorna un logger strutturato del modulo pipeline.logging_utils."""
    return get_structured_logger("ui.services.drive_runner", context=context)


def _ui_ensure_dest(base_dir: Path, local_root: Path, rel_parts: Sequence[str], filename: str) -> Path:
    target = local_root.joinpath(*rel_parts, filename)
    return cast(Path, ensure_within_and_resolve(base_dir, target))


def _require_layout_from_context(context: ClientContext) -> WorkspaceLayout:
    """Ottiene il layout fail-fast per il ClientContext corrente."""
    return WorkspaceLayout.from_context(context)


def _assert_directory_exists(path: Path, slug: str, description: str) -> None:
    if not path.exists() or not path.is_dir():
        raise WorkspaceLayoutInvalid(
            f"{description} mancante o non valida per il workspace {slug}",
            slug=slug,
            file_path=path,
        )


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
    from pre_onboarding import _create_local_structure, _drive_phase, _prepare_context_and_logger, _require_drive_utils

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
    ctx = get_client_context(slug, interactive=False, require_env=require_env)
    layout = _require_layout_from_context(ctx)
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

    yaml_path = ensure_within_and_resolve(layout.base_dir, layout.semantic_dir / "cartelle_raw.yaml")
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

    ctx = get_client_context(slug, interactive=False, require_env=require_env)
    layout = _require_layout_from_context(ctx)
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

    workspace_dir = layout.base_dir
    local_root_path = layout.raw_dir
    _assert_directory_exists(local_root_path, layout.slug, "raw directory")

    def _plan_safe_list_pdfs(service: Any, folder_id: str) -> Iterable[Dict[str, Any]]:
        for entry in _drive_list_pdfs(service, folder_id):
            if not entry:
                continue
            if entry.get("id"):
                yield entry
                continue
            patched = dict(entry)
            patched["id"] = f"plan-{patched.get('name') or 'unnamed'}"
            yield patched

    log = _get_logger(ctx)
    candidates = discover_candidates(
        service=service,
        raw_folder_id=raw_id,
        list_folders=_drive_list_folders,
        list_pdfs=_plan_safe_list_pdfs,
        ensure_dest=_ui_ensure_dest,
        base_dir=workspace_dir,
        local_root=local_root_path,
        logger=log,
    )

    labels = {cand.label for cand in candidates}
    conflicts = [cand.label for cand in candidates if cand.destination.exists()]

    return sorted(conflicts), sorted(labels)


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
    ctx = get_client_context(slug, interactive=False, require_env=require_env)
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
    overwrite: bool | None = None,
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
    overwrite: bool | None = None,
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
    ctx = get_client_context(slug, interactive=False, require_env=require_env)
    layout = _require_layout_from_context(ctx)
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
    workspace_dir = layout.base_dir
    local_root_dir = layout.raw_dir
    _assert_directory_exists(local_root_dir, layout.slug, "raw directory")
    local_root_path = local_root_dir

    log = logger or _get_logger(ctx)

    candidates = discover_candidates(
        service=svc,
        raw_folder_id=raw_id,
        list_folders=_drive_list_folders,
        list_pdfs=_drive_list_pdfs,
        ensure_dest=_ui_ensure_dest,
        base_dir=workspace_dir,
        local_root=local_root_path,
        logger=log,
    )

    emit_progress(candidates, on_progress)
    before = snapshot_existing(candidates)

    # Download dei PDF (progress disabilitato, gestito a monte)
    downloader = cast(Callable[..., Any], download_drive_pdfs_to_local)
    overwrite_flag = bool(overwrite)

    _ = downloader(
        svc,
        raw_id,
        str(local_root_dir),
        progress=(lambda *_a, **_k: None),
        context=ctx,
        redact_logs=bool(getattr(ctx, "redact_logs", False)),
        chunk_size=8 * 1024 * 1024,
        overwrite=overwrite_flag,
    )

    return cast(list[Path], compute_created(candidates, before))
