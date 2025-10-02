# SPDX-License-Identifier: GPL-3.0-or-later
# src/tools/clean_client_workspace.py
from __future__ import annotations

"""
Tool CLI: rimozione workspace cliente (locale + DB + Drive).

- Rispetta SSoT e path-safety (ensure_within_and_resolve).
- Logging strutturato "event + extra".
- Idempotente: l'assenza di risorse non è errore.
- Compatibile Windows: gestisce file lock (log aperti) con retry e skip mirato.
- Evita side-effects a import-time (solo funzioni; l'esecuzione parte in main()).

Exit codes:
- 0: OK
- 2: Config/parametri non validi (es. slug mancante)
- 3: Drive non disponibile / permessi insufficienti
- 4: Rimozione locale fallita in modo non recuperabile
- 1: Errore generico inatteso
"""

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple, cast

import yaml
from googleapiclient.errors import HttpError

from src.pipeline.context import ClientContext
from src.pipeline.exceptions import ConfigError
from src.pipeline.logging_utils import get_structured_logger
from src.pipeline.path_utils import ensure_within, ensure_within_and_resolve

# Dipendenze Drive (opzionali; usate se disponibili)
try:
    from src.pipeline.drive.client import get_drive_service  # SSoT per service
except Exception:  # pragma: no cover
    get_drive_service = None  # type: ignore[assignment]


# --------------------------------------------------------------------------------------
# Costanti e utilità
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "output"
CLIENTS_DB_DIR = REPO_ROOT / "clients_db"
CLIENTS_DB_FILE = CLIENTS_DB_DIR / "clients.yaml"

LOGGER = get_structured_logger("tools.clean_client_workspace")


def _redact(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    t = str(s)
    if len(t) <= 7:
        return "***"
    return f"{t[:3]}***{t[-3:]}"


def _ask_yes_no(prompt: str) -> bool:
    try:
        ans = input(prompt + " [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in {"y", "yes", "s", "si", "sí"}  # it/en compat


def _confirm_irreversible(slug: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    msg = (
        f"⚠️ Confermi l'eliminazione IRREVERSIBILE del workspace '{slug}'?\n"
        "- Cartella locale output/timmy-kb-<slug>\n"
        "- Record in clients_db/clients.yaml\n"
        "- Cartella cliente su Drive (se presente)\n"
    )
    return _ask_yes_no(msg)


# --------------------------------------------------------------------------------------
# Drive helpers
# --------------------------------------------------------------------------------------


def _drive_find_client_folder_id(service: Any, drive_parent_id: str, slug: str) -> Optional[str]:
    q = (
        f"name = '{slug}' and '{drive_parent_id}' in parents and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )

    def _call() -> Dict[str, Any]:
        return (
            service.files()
            .list(
                q=q,
                spaces="drive",
                fields="files(id,name)",
                pageSize=10,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            .execute()
        )

    resp = cast(Dict[str, Any], _call())
    files = cast(Iterable[Dict[str, Any]], resp.get("files", []))
    for f in files:
        return cast(str, f.get("id"))
    return None


def _drive_delete_by_id(service: Any, file_id: str) -> None:
    service.files().delete(fileId=file_id, supportsAllDrives=True).execute()


def _delete_on_drive_if_present(slug: str, logger=LOGGER) -> Tuple[bool, str]:
    """
    Prova a eliminare la cartella cliente su Drive. Idempotente.
    Ritorna (ok, messaggio); ok=False solo per errori di permesso o dipendenze.
    """
    if get_drive_service is None:
        logger.info("tools.clean_client_workspace.drive.unavailable")
        return False, "Funzionalità Drive non disponibili (dipendenze assenti)."

    try:
        # Carico il contesto per ottenere ENV e Drive service.
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        service = get_drive_service(ctx)
        drive_parent_id = (ctx.env or {}).get("DRIVE_ID")
        if not drive_parent_id:
            logger.info("tools.clean_client_workspace.drive.no_parent", extra={"slug": slug})
            return True, "DRIVE_ID non impostato: nessuna cartella da rimuovere (skip)."

        folder_id = _drive_find_client_folder_id(service, drive_parent_id, slug)
        if not folder_id:
            logger.info(
                "tools.clean_client_workspace.drive.folder_absent",
                extra={"slug": slug, "drive_parent": _redact(drive_parent_id)},
            )
            return True, "Cartella cliente su Drive assente (ok)."

        try:
            _drive_delete_by_id(service, folder_id)
            logger.info(
                "tools.clean_client_workspace.drive.folder_deleted",
                extra={"slug": slug, "folder_id": _redact(folder_id)},
            )
            return True, "Cartella cliente su Drive eliminata."
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            logger.info(
                "tools.clean_client_workspace.drive.delete_failed",
                extra={"slug": slug, "status": status, "folder_id": _redact(folder_id)},
            )
            if status in (401, 403):  # permesso mancante
                return False, "Permessi Drive insufficienti per eliminare la cartella."
            raise
    except ConfigError as e:
        logger.info("tools.clean_client_workspace.drive.ctx_error", extra={"slug": slug, "message": str(e)[:200]})
        # Non blocchiamo: continuiamo con la porzione locale/DB
        return True, "Contesto Drive non disponibile: salto rimozione Drive."
    except Exception as e:  # pragma: no cover
        logger.info("tools.clean_client_workspace.drive.unexpected", extra={"slug": slug, "message": str(e)[:200]})
        return False, f"Errore inatteso Drive: {e}"


# --------------------------------------------------------------------------------------
# Local workspace deletion (Windows-safe)
# --------------------------------------------------------------------------------------


def _try_remove_readonly(func, path, exc_info):  # noqa: ANN001
    # Callback per shutil.rmtree onerror: rimuove readonly e riprova
    try:
        os.chmod(path, 0o666)
    except Exception:
        pass
    try:
        func(path)
    except Exception:
        pass


def _rmtree_best_effort(
    base: Path,
    target: Path,
    slug: str,
    *,
    logger=LOGGER,
    retries: int = 5,
    delay: float = 0.6,
) -> Tuple[bool, list[str]]:
    """
    Prova a eliminare target in modo robusto.
    In caso di lock (Windows), tenta retry; se persiste, prova a eliminare contenuti
    uno a uno e ritorna l'elenco dei residui.
    """
    ensure_within(base, target)
    residuals: list[str] = []

    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(target, onerror=_try_remove_readonly)
            return True, residuals
        except Exception as e:
            logger.info(
                "tools.clean_client_workspace.local.rmtree_retry",
                extra={
                    "slug": slug,
                    "attempt": attempt,
                    "retries": retries,
                    "delay": delay,
                    "path": str(target),
                    "message": str(e)[:120],
                },
            )
            time.sleep(delay)

    # Best-effort per pulire quasi tutto, isolando i file bloccati
    if target.exists():
        for p in sorted(target.rglob("*"), key=len, reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                residuals.append(str(p))
        # Ritenta la rimozione della root se vuota
        try:
            target.rmdir()
        except Exception:
            pass

    still_exists = target.exists()
    return (not still_exists), residuals


def _delete_local_workspace(slug: str, logger=LOGGER) -> Tuple[bool, str]:
    """
    Elimina il workspace locale `output/timmy-kb-<slug>`.
    Non fallisce se la cartella non esiste. In caso di file lock residui,
    li segnala e ritorna comunque ok=True se tutto il resto è stato rimosso.
    """
    base = ensure_within_and_resolve(REPO_ROOT, OUTPUT_ROOT)
    work = ensure_within_and_resolve(base, base / f"timmy-kb-{slug}")

    if not work.exists():
        logger.info("tools.clean_client_workspace.local.absent", extra={"slug": slug, "path": str(work)})
        return True, "Workspace locale assente (ok)."

    logger.info("tools.clean_client_workspace.local.delete_start", extra={"slug": slug, "path": str(work)})
    ok, residuals = _rmtree_best_effort(base, work, slug, logger=logger)

    if ok:
        logger.info("tools.clean_client_workspace.local.delete_done", extra={"slug": slug})
        return True, "Workspace locale eliminato."

    # Se restano solo file di log bloccati, consideriamo l'operazione sufficiente
    locked_only_logs = all("logs" in r for r in residuals) and len(residuals) <= 3
    if locked_only_logs:
        logger.info(
            "tools.clean_client_workspace.local.residual_logs",
            extra={"slug": slug, "residual_count": len(residuals)},
        )
        return True, (
            "Workspace locale quasi eliminato; residui (log) bloccati da altri processi. "
            "Chiudi l'app e riprova per rimuovere i log."
        )

    logger.error(
        "tools.clean_client_workspace.local.delete_failed",
        extra={"slug": slug, "residual_count": len(residuals)},
    )
    return False, f"Rimozione locale non completa. Residui: {len(residuals)}"


# --------------------------------------------------------------------------------------
# DB (clients.yaml)
# --------------------------------------------------------------------------------------


def _remove_from_clients_db(slug: str, logger=LOGGER) -> Tuple[bool, str]:
    try:
        db_dir = ensure_within_and_resolve(REPO_ROOT, CLIENTS_DB_DIR)
        db_file = ensure_within_and_resolve(db_dir, CLIENTS_DB_FILE)

        if not db_file.exists():
            logger.info("tools.clean_client_workspace.db.absent", extra={"slug": slug, "path": str(db_file)})
            return True, "DB clienti assente (ok)."

        with db_file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            data = {}

        items = data.get("clients")
        if not isinstance(items, list):
            items = []

        new_items = [it for it in items if not (isinstance(it, dict) and it.get("slug") == slug)]

        if len(new_items) == len(items):
            logger.info("tools.clean_client_workspace.db.no_entry", extra={"slug": slug})
            return True, "Record non presente nel DB (ok)."

        data["clients"] = new_items
        tmp = db_file.with_suffix(".yaml.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        tmp.replace(db_file)

        logger.info("tools.clean_client_workspace.db.entry_removed", extra={"slug": slug, "path": str(db_file)})
        return True, "Record rimosso dal DB clienti."
    except Exception as e:  # pragma: no cover
        logger.error("tools.clean_client_workspace.db.error", extra={"slug": slug, "message": str(e)[:200]})
        return False, f"Errore aggiornando il DB clienti: {e}"


# --------------------------------------------------------------------------------------
# Orchestrazione
# --------------------------------------------------------------------------------------


def _resolve_slug(args_slug: Optional[str]) -> str:
    slug = (args_slug or "").strip()
    if not slug:
        slug = input("Inserisci lo slug del cliente (kebab-case): ").strip()
    if not slug:
        raise ConfigError("Slug mancante.")
    return slug


def run_cleanup(slug: str, assume_yes: bool = False) -> int:
    LOGGER.info("tools.clean_client_workspace.start", extra={"slug": slug})

    if not _confirm_irreversible(slug, assume_yes):
        LOGGER.info("tools.clean_client_workspace.cancelled", extra={"slug": slug})
        print("Operazione annullata.")
        return 0

    # 1) Drive
    ok_drive, msg_drive = _delete_on_drive_if_present(slug, LOGGER)
    if msg_drive:
        print(msg_drive)
    if not ok_drive:
        # Proseguiamo comunque con locale + DB, ma segnaliamo exit speciale se tutto il resto va bene
        drive_error = True
    else:
        drive_error = False

    # 2) Locale
    ok_local, msg_local = _delete_local_workspace(slug, LOGGER)
    if msg_local:
        print(msg_local)
    if not ok_local:
        print("Errore: rimozione locale incompleta.")
        # Non ha senso procedere: lo stato locale è incoerente
        return 4

    # 3) DB
    ok_db, msg_db = _remove_from_clients_db(slug, LOGGER)
    if msg_db:
        print(msg_db)
    if not ok_db:
        # Non blocchiamo: il workspace è stato rimosso, ma segnaliamo errore generico
        return 1

    LOGGER.info("tools.clean_client_workspace.done", extra={"slug": slug})

    if drive_error:
        # Locale + DB ok, Drive ko per permessi / dipendenze
        return 3
    return 0


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="clean_client_workspace",
        description="Elimina workspace cliente (locale + DB + Drive). Operazione irreversibile.",
    )
    parser.add_argument("--slug", type=str, help="Slug del cliente (kebab-case).")
    parser.add_argument("-y", "--yes", action="store_true", help="Non chiedere conferma (assume Yes).")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    try:
        ns = parse_args(argv or [])
        slug = _resolve_slug(ns.slug)
        return run_cleanup(slug=slug, assume_yes=bool(ns.yes))
    except ConfigError as e:
        LOGGER.info("tools.clean_client_workspace.invalid_args", extra={"message": str(e)[:200]})
        print(f"Argomenti non validi: {e}")
        return 2
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente.")
        return 1
    except Exception as e:  # pragma: no cover
        LOGGER.error("tools.clean_client_workspace.unexpected", extra={"message": str(e)[:200]})
        print(f"Errore inatteso: {e}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
