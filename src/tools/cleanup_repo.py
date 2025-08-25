#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

# --- PYTHONPATH bootstrap (consente import "pipeline.*" quando esegui da src/tools) ---
import sys as _sys
from pathlib import Path as _P
_SRC_DIR = _P(__file__).resolve().parents[1]  # .../src
if str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))
# --------------------------------------------------------------------------------------

from pathlib import Path
from typing import Iterable, List, Optional
import uuid  # per run_id
import logging

from pipeline.logging_utils import get_structured_logger, redact_secrets
from pipeline.path_utils import is_safe_subpath, is_valid_slug
from pipeline.exceptions import PipelineError, ConfigError, EXIT_CODES
from pipeline.proc_utils import run_cmd, CmdError  # ✅ timeout/retry/log

# Logger inizializzato in main() con run_id; qui solo la dichiarazione
logger: Optional[logging.Logger] = None  # verrà assegnato in main()


def _rm_path(p: Path) -> None:
    """Rimozione best-effort di file o directory (senza seguire link fuori scope)."""
    assert logger is not None
    try:
        if p.is_dir():
            # rimozione bottom-up per evitare errori su dir non vuote
            for child in sorted(p.rglob("*"), reverse=True):
                try:
                    if child.is_file() or child.is_symlink():
                        try:
                            child.unlink(missing_ok=True)  # Py>=3.8
                        except TypeError:
                            if child.exists() or child.is_symlink():
                                child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                except Exception:
                    # best-effort: continuiamo con gli altri
                    pass
            p.rmdir()
        elif p.exists() or p.is_symlink():
            try:
                p.unlink(missing_ok=True)
            except TypeError:
                p.unlink()
        logger.info("🗑️  Rimosso", extra={"file_path": str(p)})
    except Exception as e:
        logger.warning(f"Impossibile rimuovere {p}: {e}", extra={"file_path": str(p)})


def _gh_repo_delete(full_name: str) -> None:
    """Elimina un repository GitHub via gh CLI, se installata."""
    assert logger is not None
    try:
        # `gh` stampa messaggi su stderr/stdout: li catturiamo ma non li esponiamo
        run_cmd(["gh", "repo", "delete", full_name, "--yes"], capture=True, op="gh repo delete")
        logger.info("🗑️  Repo GitHub eliminato", extra={"repo": redact_secrets(full_name)})
    except FileNotFoundError:
        logger.warning("gh CLI non trovata: skip delete remoto", extra={"repo": full_name})
    except CmdError as e:
        # tail diagnostico compatto, con redazione
        tail = (e.stderr or e.stdout or "").strip()
        tail = tail[-1000:] if tail else ""
        logger.warning(
            "Delete repo fallito",
            extra={"repo": full_name, "stderr_tail": redact_secrets(tail)},
        )


def _ensure_safe(paths: Iterable[Path], base: Path) -> List[Path]:
    assert logger is not None
    safe: List[Path] = []
    for p in paths:
        if is_safe_subpath(p, base):
            safe.append(p)
        else:
            logger.warning("Path non sicuro: skip", extra={"file_path": str(p)})
    return safe


def cleanup_local_only_output(project_root: Path, slug: str) -> None:
    """
    Pulisce **solo** la cartella locale output/timmy-kb-<slug>.
    """
    assert logger is not None
    target = project_root / "output" / f"timmy-kb-{slug}"
    targets = _ensure_safe([target], project_root.resolve())
    for t in targets:
        if t.exists():
            _rm_path(t)
        else:
            logger.debug("Skip (path assente)", extra={"file_path": str(t)})


def cleanup_remote(slug: str, github_namespace: Optional[str] = None) -> None:
    """Elimina il repo remoto convenzionale timmy-kb-<slug> nel namespace indicato (o utente corrente)."""
    repo_name = f"timmy-kb-{slug}"
    full_name = f"{github_namespace}/{repo_name}" if github_namespace else repo_name
    _gh_repo_delete(full_name)


def _prompt_bool(question: str, default_no: bool = True) -> bool:
    """Prompt sì/no con default NO (invio vuoto = default)."""
    ans = input(f"{question} [{'Y/n' if not default_no else 'y/N'}]: ").strip().lower()
    if not ans:
        return not default_no
    return ans in ("y", "yes", "s", "si", "sí")


def _prompt_slug() -> Optional[str]:
    """Chiede all'utente lo slug finché valido; ritorna None se l’utente annulla (invio vuoto)."""
    assert logger is not None
    while True:
        s = input("Inserisci slug cliente (obbligatorio, invio per annullare): ").strip()
        if not s:
            return None
        if is_valid_slug(s):
            return s
        logger.warning("Slug non valido: minuscole/numeri/trattini soltanto (es: 'acme' o 'acme-2025').")


def main() -> int:
    global logger

    # run_id univoco per correlazione log
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("tools.cleanup", run_id=run_id)

    project_root = Path(__file__).resolve().parents[2]

    # 1) Slug (obbligatorio, interattivo)
    slug = _prompt_slug()
    if not slug:
        logger.info("Operazione annullata: slug non fornito")
        return 0

    # 2) Conferma distruttiva per la cancellazione locale (irreversibile)
    msg = (
        f"⚠️  Confermi la CANCELLAZIONE DEFINITIVA della cartella "
        f"'output/timmy-kb-{slug}'? L'operazione è distruttiva e NON è reversibile."
    )
    if _prompt_bool(msg, default_no=True):
        try:
            cleanup_local_only_output(project_root, slug)
        except Exception:
            if logger is not None:
                logger.exception("Errore durante la pulizia locale", extra={"slug": slug})
            return EXIT_CODES.get("PipelineError", 1)
    else:
        logger.info("Pulizia locale annullata dall'utente")
        return 0  # ⬅️ exit immediato: non chiedere del repo remoto

    # 3) (solo se sopra è stato confermato) opzione per cancellare il repo remoto
    try:
        do_remote = _prompt_bool(
            f"Eliminare anche il repository GitHub remoto 'timmy-kb-{slug}'?", default_no=True
        )
        if do_remote:
            namespace = input("Namespace GitHub (org o user) [invio per usare quello corrente]: ").strip()
            cleanup_remote(slug, github_namespace=(namespace or None))
        logger.info("✅ Cleanup completato", extra={"slug": slug})
        return 0
    except ConfigError:
        return EXIT_CODES.get("ConfigError", 2)
    except PipelineError:
        return EXIT_CODES.get("PipelineError", 1)
    except Exception:
        if logger is not None:
            logger.exception("Errore imprevisto durante il cleanup", extra={"slug": slug})
        return EXIT_CODES.get("PipelineError", 1)


if __name__ == "__main__":
    import sys
    sys.exit(main())
