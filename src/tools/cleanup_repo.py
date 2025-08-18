# src/tools/cleanup_repo.py
from __future__ import annotations

# --- PYTHONPATH bootstrap (consente import "pipeline.*" quando esegui da src/tools) ---
import sys as _sys
from pathlib import Path as _P
_SRC_DIR = _P(__file__).resolve().parents[1]  # .../src
if str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))
# --------------------------------------------------------------------------------------

from pathlib import Path
import subprocess
from typing import Iterable, List, Optional
import uuid  # per run_id

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import is_safe_subpath, is_valid_slug
from pipeline.exceptions import PipelineError, ConfigError, EXIT_CODES

# Logger inizializzato in main() con run_id; qui solo la dichiarazione
logger = None  # verrà assegnato in main()


def _rm_path(p: Path) -> None:
    """Rimozione best-effort di file o directory."""
    try:
        if p.is_dir():
            for child in sorted(p.rglob("*"), reverse=True):
                try:
                    if child.is_file() or child.is_symlink():
                        try:
                            child.unlink(missing_ok=True)  # per Py>=3.8
                        except TypeError:
                            if child.exists() or child.is_symlink():
                                child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                except Exception:
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
    try:
        subprocess.run(
            ["gh", "repo", "delete", full_name, "--yes"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("🗑️  Repo GitHub eliminato", extra={"repo": full_name})
    except FileNotFoundError:
        logger.warning("gh CLI non trovata: skip delete remoto", extra={"repo": full_name})
    except subprocess.CalledProcessError as e:
        logger.warning(f"Delete repo fallito: {e}", extra={"repo": full_name})


def _ensure_safe(paths: Iterable[Path], base: Path) -> List[Path]:
    safe: List[Path] = []
    for p in paths:
        if is_safe_subpath(p, base):
            safe.append(p)
        else:
            logger.warning("Path non sicuro: skip", extra={"file_path": str(p)})
    return safe


def cleanup_local(project_root: Path, slug: str, include_global: bool) -> None:
    """Pulisce artefatti locali per lo slug indicato; opzionalmente rimuove anche artefatti globali."""
    targets: List[Path] = [
        project_root / "output" / f"timmy-kb-{slug}",
        project_root / "clienti" / slug,
    ]
    if include_global:
        targets += [
            project_root / "_book",
            project_root / "book.json",
            project_root / "package.json",
        ]
    targets = _ensure_safe(targets, project_root.resolve())
    for t in targets:
        if t.exists():
            _rm_path(t)
        else:
            # Log meno rumoroso: livello DEBUG + path esplicito
            logger.debug(f"Skip (path assente): {t}", extra={"file_path": str(t)})


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

    # 2) Opzioni interattive
    include_global = _prompt_bool("Includere anche artefatti globali (_book, book.json, package.json)?", default_no=True)
    do_remote = _prompt_bool("Eliminare anche il repository GitHub remoto timmy-kb-<slug>?", default_no=True)
    namespace = ""
    if do_remote:
        namespace = input("Namespace GitHub (org o user) [invio per usare quello corrente]: ").strip()

    # 3) Riepilogo + conferma
    summary = f"Pulizia per slug={slug} | global={'yes' if include_global else 'no'} | remote={'yes' if do_remote else 'no'}"
    ans = input(f"{summary}\nConfermi? [y/N]: ").strip().lower()
    if ans not in ("y", "yes", "s", "si", "sí"):
        logger.info("Operazione annullata dall'utente")
        return 0

    # 4) Esecuzione
    try:
        cleanup_local(project_root, slug, include_global=include_global)
        if do_remote:
            cleanup_remote(slug, github_namespace=(namespace or None))
        logger.info("✅ Cleanup completato", extra={"slug": slug})
        return 0
    except ConfigError:
        return EXIT_CODES.get("ConfigError", 2)
    except PipelineError:
        return EXIT_CODES.get("PipelineError", 1)
    except Exception:
        # Tracciamo stacktrace e mappiamo a EXIT_CODES
        logger.exception("Errore imprevisto durante il cleanup", extra={"slug": slug})
        return EXIT_CODES.get("PipelineError", 1)


if __name__ == "__main__":
    import sys
    sys.exit(main())
