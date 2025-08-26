#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tool interattivo di cleanup per la sandbox locale e (opzionale) per il repo GitHub.

Cosa fa (in breve)
------------------
- Chiede uno *slug* cliente valido.
- (Opzionale) elimina **in sicurezza** la cartella locale `output/timmy-kb-<slug>`
  applicando guard-rail STRONG con `ensure_within(...)` e rimozione bottom-up.
- (Opzionale) elimina il repository remoto `timmy-kb-<slug>`:
  1) prova via **API** (PyGithub + PAT in `GITHUB_TOKEN`);
  2) se la DELETE 401/403 → **fallback automatico** alla CLI `gh`.

Note importanti
---------------
- Per cancellare via API serve che il PAT appartenga al *proprietario* del repo e
  abbia lo scope **delete_repo** (per PAT classico) o permesso equivalente (fine-grained).
- La CLI `gh` deve essere autenticata con un account che abbia permessi “admin” sul repo.
"""

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
import os

from pipeline.logging_utils import get_structured_logger, redact_secrets
from pipeline.path_utils import ensure_within, is_valid_slug  # ✅ STRONG guard per delete
from pipeline.exceptions import PipelineError, ConfigError, EXIT_CODES
from pipeline.proc_utils import run_cmd, CmdError  # ✅ timeout/retry/log

# API GitHub (preferita per cancellazione remota)
from github import Github
from github.GithubException import GithubException, UnknownObjectException

# Logger inizializzato in main() con run_id; qui solo la dichiarazione
logger: Optional[logging.Logger] = None  # verrà assegnato in main()


# ------------------------- Helpers locali -------------------------

def _rm_path(p: Path) -> None:
    """Rimozione best-effort di file o directory (senza seguire symlink)."""
    assert logger is not None
    try:
        # Symlink: non seguire mai
        if p.is_symlink():
            try:
                p.unlink(missing_ok=True)
            except TypeError:
                if p.exists() or p.is_symlink():
                    p.unlink()
            logger.info("🗑️  Rimosso (symlink)", extra={"file_path": str(p)})
            return

        if p.is_dir():
            # rimozione bottom-up per evitare errori su dir non vuote
            for child in sorted(p.rglob("*"), reverse=True):
                try:
                    if child.is_symlink() or child.is_file():
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
        elif p.exists():
            try:
                p.unlink(missing_ok=True)
            except TypeError:
                p.unlink()
        logger.info("🗑️  Rimosso", extra={"file_path": str(p)})
    except Exception as e:
        logger.warning("Impossibile rimuovere", extra={"file_path": str(p), "error": str(e)})


def _ensure_safe(paths: Iterable[Path], base: Path) -> List[Path]:
    """Filtra i path mantenendo solo quelli *STRONGLY* dentro `base` (usa ensure_within)."""
    assert logger is not None
    safe: List[Path] = []
    for p in paths:
        try:
            ensure_within(base, p)
            safe.append(p)
        except Exception as e:
            logger.warning("Path non sicuro: skip", extra={"file_path": str(p), "error": str(e)})
    return safe


# -------------------- Cancellazione locale sandbox --------------------

def cleanup_local_only_output(project_root: Path, slug: str) -> None:
    """
    Pulisce **solo** la cartella locale output/timmy-kb-<slug>.
    Applica guard-rail STRONG vincolando l'operazione a `project_root/output`.
    """
    assert logger is not None
    output_root = (project_root / "output").resolve()
    target = (output_root / f"timmy-kb-{slug}").resolve()

    # STRONG: il bersaglio DEVE stare dentro output_root
    targets = _ensure_safe([target], output_root)
    for t in targets:
        if t.exists() or t.is_symlink():
            _rm_path(t)
        else:
            logger.debug("Skip (path assente)", extra={"file_path": str(t)})


# -------------------- Cancellazione remota GitHub --------------------

def _gh_repo_delete_cli(name_or_full: str) -> None:
    """
    Fallback: usa 'gh' per cancellare il repo. Accetta 'repo' o 'owner/repo'.
    Se non è 'owner/repo', ricava l'owner corrente via `gh api user`.
    """
    assert logger is not None
    repo_full = name_or_full
    if "/" not in repo_full:
        try:
            cp = run_cmd(["gh", "api", "user", "-q", ".login"], capture=True, op="gh api user", logger=logger)
            owner = (cp.stdout or "").strip()
            if owner:
                repo_full = f"{owner}/{name_or_full}"
        except CmdError:
            logger.warning("Impossibile ricavare l'owner dalla CLI gh.", extra={"repo": name_or_full})
            return

    # Prova a cancellare direttamente; se non esiste, gh fallisce → lo logghiamo come informativo
    try:
        run_cmd(["gh", "repo", "delete", repo_full, "-y"], capture=True, op="gh repo delete", logger=logger)
        logger.info("🗑️  Repo GitHub eliminato (gh)", extra={"repo": repo_full})
    except CmdError as e:
        tail = (e.stderr or e.stdout or "").strip()
        if "Not Found" in tail or "could not be found" in tail:
            logger.info("Repo remoto inesistente o non visibile per la CLI gh: niente da fare.", extra={"repo": repo_full})
        else:
            logger.warning("Delete via gh fallito", extra={"repo": repo_full, "stderr_tail": redact_secrets(tail)})


def cleanup_remote(slug: str) -> None:
    """
    Cancella il repo remoto 'timmy-kb-<slug>'.

    Strategia:
      1) se `GITHUB_TOKEN` è presente → API GitHub (PyGithub)
         - se 401/403 → fallback automatico a CLI `gh`
      2) se `GITHUB_TOKEN` assente → direttamente CLI `gh`
    """
    assert logger is not None
    repo_name = f"timmy-kb-{slug}"
    token = os.getenv("GITHUB_TOKEN")

    if not token:
        logger.warning("GITHUB_TOKEN assente: fallback alla CLI gh (best-effort).", extra={"repo": repo_name})
        _gh_repo_delete_cli(repo_name)
        return

    try:
        gh = Github(token)
        me = gh.get_user()
        owner = me.login
        full = f"{owner}/{repo_name}"

        # verifica esistenza/visibilità col token (404 → UnknownObjectException)
        try:
            repo = gh.get_repo(full)
        except UnknownObjectException:
            logger.info("Repo remoto inesistente o non visibile con il PAT: niente da fare.", extra={"repo": full})
            return

        try:
            repo.delete()
            logger.info("🗑️  Repo GitHub eliminato", extra={"repo": full})
        except GithubException as e:
            status = getattr(e, "status", None)
            details = getattr(e, "data", None) or str(e)
            if status in (401, 403):
                logger.error(
                    "Permesso negato a cancellare il repo via API. Fallback a CLI gh…",
                    extra={"repo": full, "status": status, "details": redact_secrets(str(details))},
                )
                _gh_repo_delete_cli(full)
            elif status == 404:
                logger.info("Repo remoto non trovato (API).", extra={"repo": full})
            else:
                logger.error("Errore GitHub API durante delete", extra={"repo": full, "status": status, "error": str(e)})

    except GithubException as e:
        logger.error("Errore autenticazione/API GitHub", extra={"error": str(e)})


# ------------------------- Prompt helpers -------------------------

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


# ------------------------------ Main ------------------------------

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
            f"Eliminare anche il repository GitHub remoto 'timmy-kb-{slug}' (utente corrente)?", default_no=True
        )
        if do_remote:
            logger.info("Cleanup remoto richiesto", extra={"slug": slug})
            cleanup_remote(slug)

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
