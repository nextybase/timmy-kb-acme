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
import logging
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast

# SSoT percorsi registry clienti dalla UI
from timmykb.ui.clients_store import DB_DIR as CLIENTS_DB_DIR  # type: ignore
from timmykb.ui.clients_store import DB_FILE as CLIENTS_DB_FILE
from timmykb.ui.clients_store import load_clients as _load_clients
from timmykb.ui.clients_store import save_clients as _save_clients

from ..pipeline.context import ClientContext
from ..pipeline.drive_utils import MIME_FOLDER, delete_drive_file, get_drive_service, list_drive_files
from ..pipeline.exceptions import ConfigError
from ..pipeline.logging_utils import get_structured_logger
from ..pipeline.path_utils import ensure_within_and_resolve

MIME_FOLDER_CACHED = MIME_FOLDER


# --------------------------------------------------------------------------------------
# Costanti e utilità
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "output"

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


def _collect_drive_folder_candidates(
    service: Any,
    drive_parent_id: str,
    slug: str,
    client_name: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Ritorna una lista di possibili cartelle Drive da eliminare e i termini di ricerca utilizzati.
    """
    candidates: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    used_terms: List[str] = []

    def _record(item: Dict[str, Any]) -> None:
        file_id = cast(Optional[str], item.get("id"))
        if not file_id or file_id in seen_ids:
            return
        seen_ids.add(file_id)
        candidates.append({"id": file_id, "name": item.get("name"), "parents": item.get("parents")})

    sanitized_slug = slug.replace("'", "\\'")
    query = f"name = '{sanitized_slug}' and mimeType = '{MIME_FOLDER_CACHED}' and trashed = false"
    for item in list_drive_files(
        service,
        drive_parent_id,
        query=query,
        fields="files(id,name,mimeType,parents)",
    ):
        _record(item)
    used_terms.append(sanitized_slug)

    search_terms: List[str] = [
        slug,
        f"timmy-kb-{slug}",
        slug.replace("-", " "),
        slug.replace("-", "_"),
    ]
    if client_name:
        search_terms.append(client_name)
        search_terms.append(client_name.replace("-", " "))

    seen_terms: set[str] = set()
    for term in search_terms:
        clean = (term or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        sanitized = clean.replace("'", "\\'")
        resp = (
            service.files()
            .list(
                q=f"name contains '{sanitized}' and mimeType = '{MIME_FOLDER_CACHED}' and trashed = false",
                fields="files(id,name,parents)",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                driveId=drive_parent_id,
                corpora="drive",
                pageSize=100,
            )
            .execute()
        )
        used_terms.append(sanitized)
        for item in resp.get("files", []):
            _record(item)

    return candidates, used_terms


def _delete_on_drive_if_present(
    slug: str,
    logger=LOGGER,
    client_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Prova a eliminare la cartella cliente su Drive. Idempotente.
    Ritorna (ok, messaggio); ok=False solo per errori di permesso o dipendenze.
    """
    try:
        env_vars = ClientContext._load_env(require_env=True)  # type: ignore[attr-defined]
        drive_parent_id = (env_vars or {}).get("DRIVE_ID")
        if not drive_parent_id:
            logger.info("tools.clean_client_workspace.drive.no_parent", extra={"slug": slug})
            return True, "DRIVE_ID non impostato: nessuna cartella da rimuovere (skip)."

        ctx_stub = SimpleNamespace(
            slug=slug,
            env=env_vars,
            run_id=None,
            redact_logs=False,
            repo_root_dir=None,
            config_path=None,
            config_dir=None,
            log_dir=None,
        )
        service = get_drive_service(ctx_stub)

        matches, search_terms = _collect_drive_folder_candidates(
            service, drive_parent_id, slug, client_name=client_name
        )
        if not matches:
            logger.info(
                "tools.clean_client_workspace.drive.folder_absent",
                extra={"slug": slug, "drive_parent": _redact(drive_parent_id)},
            )
            terms_desc = ", ".join(search_terms[:5]) if search_terms else "n/d"
            return True, f"Cartella cliente su Drive assente (ok). Termini usati: {terms_desc}."

        deleted: list[Dict[str, Any]] = []
        failures: list[str] = []
        for item in matches:
            file_id = cast(Optional[str], item.get("id"))
            if not file_id:
                continue
            try:
                delete_drive_file(service, file_id)
                deleted.append(item)
            except Exception as e:  # pragma: no cover
                failures.append(str(e))

        if failures:
            logger.warning(
                "tools.clean_client_workspace.drive.partial",
                extra={
                    "slug": slug,
                    "errors": failures[:3],
                    "deleted": [_redact(cast(str, item.get("id"))) for item in deleted],
                    "search_terms": search_terms,
                },
            )
            return False, "Alcune cartelle Drive non sono state eliminate: verificare i log."

        logger.info(
            "tools.clean_client_workspace.drive.folder_deleted",
            extra={
                "slug": slug,
                "deleted": [_redact(cast(str, item.get("id"))) for item in deleted],
                "names": [item.get("name") for item in deleted],
                "search_terms": search_terms,
            },
        )
        deleted_names = ", ".join(filter(None, (str(item.get("name") or "").strip() for item in deleted)))
        if deleted_names:
            return True, f"Cartelle Drive eliminate: {deleted_names}."
        return True, "Cartella cliente su Drive eliminata."
    except ConfigError as e:
        logger.info("tools.clean_client_workspace.drive.ctx_error", extra={"slug": slug, "message": str(e)[:200]})
        # Non blocchiamo: continuiamo con la porzione locale/DB
        return True, "Contesto Drive non disponibile: salto rimozione Drive."
    except Exception as e:  # pragma: no cover
        logger.info("tools.clean_client_workspace.drive.unexpected", extra={"slug": slug, "detail": str(e)[:200]})
        return False, f"Errore inatteso Drive: {e}"


# --------------------------------------------------------------------------------------
# Local workspace deletion (Windows-safe)
# --------------------------------------------------------------------------------------


def _try_remove_readonly(
    func: Callable[[str], Any],
    path: str,
    exc_info: Tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    # Callback per shutil.rmtree onerror: rimuove readonly e riprova
    try:
        current_mode = os.stat(path).st_mode
        os.chmod(path, current_mode | stat.S_IWRITE)
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
    logger: logging.Logger = LOGGER,
    retries: int = 5,
    delay: float = 0.6,
) -> Tuple[bool, list[str]]:
    """
    Prova a eliminare target in modo robusto.
    In caso di lock (Windows), tenta retry; se persiste, prova a eliminare contenuti
    uno a uno e ritorna l'elenco dei residui.
    """
    resolved = ensure_within_and_resolve(base, target)
    residuals: list[str] = []

    for attempt in range(1, retries + 1):
        try:
            shutil.rmtree(resolved, onerror=_try_remove_readonly)
            return True, residuals
        except Exception as e:
            logger.info(
                "tools.clean_client_workspace.local.rmtree_retry",
                extra={
                    "slug": slug,
                    "attempt": attempt,
                    "retries": retries,
                    "delay": delay,
                    "path": str(resolved),
                    "message": str(e)[:120],
                },
            )
            time.sleep(delay)

    # Best-effort per pulire quasi tutto, isolando i file bloccati
    if resolved.exists():
        for p in sorted(resolved.rglob("*"), key=len, reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                residuals.append(str(p))
        # Ritenta la rimozione della root se vuota
        try:
            resolved.rmdir()
        except Exception:
            pass

    still_exists = resolved.exists()
    return (not still_exists), residuals


def _delete_local_workspace(slug: str, logger: logging.Logger = LOGGER) -> Tuple[bool, str]:
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


def _remove_from_clients_db(slug: str, logger: logging.Logger = LOGGER) -> Tuple[bool, str]:
    """
    Rimuove lo slug dal registry clienti delegando all'SSoT `ui.clients_store`.
    """
    try:
        db_dir = ensure_within_and_resolve(REPO_ROOT, CLIENTS_DB_DIR)
        db_file = ensure_within_and_resolve(db_dir, CLIENTS_DB_FILE)

        if not db_file.exists():
            logger.info("tools.clean_client_workspace.db.absent", extra={"slug": slug, "path": str(db_file)})
            return True, "DB clienti assente (ok)."

        entries = _load_clients()
        before = len(entries)
        remaining = [entry for entry in entries if entry.slug.strip().lower() != slug.strip().lower()]

        if len(remaining) == before:
            logger.info("tools.clean_client_workspace.db.no_entry", extra={"slug": slug})
            return True, "Record non presente nel DB (ok)."

        _save_clients(remaining)
        logger.info("tools.clean_client_workspace.db.entry_removed", extra={"slug": slug, "path": str(db_file)})
        return True, "Record rimosso dal DB clienti."
    except Exception as e:  # pragma: no cover
        logger.error("tools.clean_client_workspace.db.error", extra={"slug": slug, "message": str(e)[:200]})
        return False, f"Errore aggiornando il DB clienti: {e}"


def perform_cleanup(slug: str, client_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Esegue la sequenza di cleanup (Drive → locale → registry) e ritorna dettagli.
    """
    results: Dict[str, Any] = {}

    ok_drive, msg_drive = _delete_on_drive_if_present(slug, LOGGER, client_name=client_name)
    results["drive"] = {"ok": bool(ok_drive), "message": msg_drive}

    ok_local, msg_local = _delete_local_workspace(slug, LOGGER)
    results["local"] = {"ok": bool(ok_local), "message": msg_local}
    if not ok_local:
        results["exit_code"] = 4
        return results

    ok_db, msg_db = _remove_from_clients_db(slug, LOGGER)
    results["registry"] = {"ok": bool(ok_db), "message": msg_db}

    if not ok_db:
        results["exit_code"] = 1
    elif not ok_drive:
        results["exit_code"] = 3
    else:
        results["exit_code"] = 0

    return results


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

    entry_name: Optional[str] = None
    for entry in _load_clients():
        if entry.slug.strip().lower() == slug.strip().lower():
            entry_name = entry.nome
            break

    results = perform_cleanup(slug, client_name=entry_name)

    for key in ("drive", "local", "registry"):
        info = results.get(key) or {}
        message = info.get("message")
        if message:
            print(message)

    exit_code = int(results.get("exit_code", 1))
    if exit_code == 4:
        print("Errore: rimozione locale incompleta.")
    LOGGER.info("tools.clean_client_workspace.done", extra={"slug": slug, "exit_code": exit_code})
    return exit_code


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
        LOGGER.info("tools.clean_client_workspace.invalid_args", extra={"detail": str(e)[:200]})
        print(f"Argomenti non validi: {e}")
        return 2
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente.")
        return 1
    except Exception as e:  # pragma: no cover
        LOGGER.error("tools.clean_client_workspace.unexpected", extra={"detail": str(e)[:200]})
        print(f"Errore inatteso: {e}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
