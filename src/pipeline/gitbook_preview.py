# src/pipeline/gitbook_preview.py
from __future__ import annotations

"""
Preview GitBook/HonKit tramite Docker (no interattività nel modulo).

Cosa fa:
- Garantisce la presenza di `book.json` e `package.json` minimi (idempotente).
- Esegue la build statica (`honkit build`) in container Docker.
- Avvia la preview (`honkit serve`) in foreground o detached.
- Attende opzionalmente la disponibilità della porta (best-effort).
- Fornisce uno stop sicuro del container.

Linee guida applicate:
- Niente `print()` → solo logging strutturato (`get_structured_logger`).
- Scritture **atomiche** con `safe_write_text` (SSoT).
- **Path-safety STRONG** con `ensure_within(...)` prima di scrivere o montare.
- Comandi esterni con `proc_utils.run_cmd` (timeout/retry/capture).
"""

import json
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import redact_secrets, get_structured_logger
from pipeline.exceptions import PipelineError, PreviewError
from pipeline.path_utils import ensure_within  # STRONG guard per write/delete & validazioni
from pipeline.file_utils import safe_write_text  # ✅ scritture atomiche (SSoT)
from pipeline.env_utils import get_int
from pipeline.proc_utils import run_cmd, CmdError, wait_for_port
from pipeline.constants import (
    BOOK_JSON_NAME,
    PACKAGE_JSON_NAME,
    HONKIT_DOCKER_IMAGE,
)

logger = get_structured_logger("pipeline.gitbook_preview")


def _maybe_redact(text: str, redact: bool) -> str:
    """Applica redazione ai messaggi di log solo se richiesto."""
    return redact_secrets(text) if (redact and text) else text


# ----------------------------
# Helpers idempotenti di setup
# ----------------------------
def ensure_book_json(md_dir: Path, *, slug: Optional[str] = None, redact_logs: bool = False) -> None:
    """Crea un book.json minimo se mancante (idempotente)."""
    book_json_path = Path(md_dir) / BOOK_JSON_NAME
    try:
        # STRONG guard: validare sia la dir sia il file target prima di scrivere
        ensure_within(md_dir, book_json_path)
    except Exception as e:
        raise PreviewError(
            f"Percorso book.json non sicuro: {book_json_path} ({e})",
            slug=slug,
            file_path=book_json_path,
        )

    if not book_json_path.exists():
        data = {"title": "preview", "plugins": []}
        try:
            # ✅ scrittura atomica
            safe_write_text(book_json_path, json.dumps(data, indent=2), encoding="utf-8", atomic=True)
            logger.info(
                _maybe_redact("📖 book.json generato", redact_logs),
                extra={"slug": slug, "file_path": str(book_json_path)},
            )
        except Exception as e:
            raise PreviewError(
                f"Errore generazione book.json: {e}",
                slug=slug,
                file_path=book_json_path,
            )
    else:
        logger.info(
            _maybe_redact("📖 book.json già presente", redact_logs),
            extra={"slug": slug, "file_path": str(book_json_path)},
        )


def ensure_package_json(md_dir: Path, *, slug: Optional[str] = None, redact_logs: bool = False) -> None:
    """Crea un package.json minimo se mancante (idempotente)."""
    package_json_path = Path(md_dir) / PACKAGE_JSON_NAME
    try:
        # STRONG guard: validare sia la dir sia il file target prima di scrivere
        ensure_within(md_dir, package_json_path)
    except Exception as e:
        raise PreviewError(
            f"Percorso package.json non sicuro: {package_json_path} ({e})",
            slug=slug,
            file_path=package_json_path,
        )

    if not package_json_path.exists():
        data = {
            "name": "honkit-preview",
            "version": "0.0.0",
            "description": "HonKit preview",
            "main": "README.md",
            "license": "MIT",
            "scripts": {"build": "honkit build", "serve": "honkit serve"},
        }
        try:
            # ✅ scrittura atomica
            safe_write_text(package_json_path, json.dumps(data, indent=2), encoding="utf-8", atomic=True)
            logger.info(
                _maybe_redact("📦 package.json generato", redact_logs),
                extra={"slug": slug, "file_path": str(package_json_path)},
            )
        except Exception as e:
            raise PreviewError(
                f"Errore generazione package.json: {e}",
                slug=slug,
                file_path=package_json_path,
            )
    else:
        logger.info(
            _maybe_redact("📦 package.json già presente", redact_logs),
            extra={"slug": slug, "file_path": str(package_json_path)},
        )


# ----------------------------
#  Fasi operative (refactor)
# ----------------------------
def build_static_site(md_dir: Path, *, slug: Optional[str], redact_logs: bool) -> None:
    """Esegue `honkit build` dentro il container ufficiale (idempotente lato output)."""
    # STRONG guard sulla directory di lavoro
    try:
        ensure_within(md_dir, md_dir / "README.md")  # validazione che vincola a md_dir
    except Exception as e:
        raise PreviewError(f"Percorso md_dir non sicuro: {md_dir} ({e})", slug=slug, file_path=md_dir)

    md_output_path = Path(md_dir).resolve()
    cmd = [
        "docker",
        "run",
        "--rm",
        "--workdir",
        "/app",
        "-v",
        f"{md_output_path}:/app",
        HONKIT_DOCKER_IMAGE,
        "npm",
        "run",
        "build",
    ]
    try:
        run_cmd(cmd, op="docker run build", logger=logger)
        logger.info(_maybe_redact("🔨 Build statica HonKit completata.", redact_logs), extra={"slug": slug})
    except CmdError as e:
        raise PreviewError(f"Errore 'honkit build': {e}", slug=slug)


def run_container_detached(
    md_dir: Path, *, slug: Optional[str], container_name: str, port: int, redact_logs: bool
) -> str:
    """Avvia `honkit serve` in modalità detached e ritorna l'ID del container."""
    # STRONG guard sulla directory di lavoro
    try:
        ensure_within(md_dir, md_dir / "README.md")
    except Exception as e:
        raise PreviewError(f"Percorso md_dir non sicuro: {md_dir} ({e})", slug=slug, file_path=md_dir)

    md_output_path = Path(md_dir).resolve()
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "-p",
        f"{port}:4000",
        "--workdir",
        "/app",
        "-v",
        f"{md_output_path}:/app",
        HONKIT_DOCKER_IMAGE,
        "npm",
        "run",
        "serve",
    ]
    try:
        # Docker stampa l'ID del container su stdout
        cp = run_cmd(cmd, op="docker run serve (detached)", logger=logger, capture=True)
        container_id = (cp.stdout or "").strip()
        logger.info(
            _maybe_redact("▶️ HonKit serve avviato (detached).", redact_logs),
            extra={"slug": slug, "file_path": f"{container_name}@{port}", "container_id": container_id},
        )
        return container_id
    except CmdError:
        # Cleanup soft se un container con lo stesso nome esiste già
        try:
            run_cmd(["docker", "rm", "-f", container_name], op="docker rm -f (pre-retry)", logger=logger, capture=True)
            cp = run_cmd(cmd, op="docker run serve (detached retry)", logger=logger, capture=True)
            container_id = (cp.stdout or "").strip()
            logger.info(
                _maybe_redact("▶️ HonKit serve avviato (detached) dopo retry.", redact_logs),
                extra={"slug": slug, "file_path": f"{container_name}@{port}", "container_id": container_id},
            )
            return container_id
        except CmdError as e2:
            raise PreviewError(f"Errore 'honkit serve' (bg): {e2}", slug=slug)


def wait_until_ready(host: str, port: int, *, timeout_s: Optional[int], slug: Optional[str], redact_logs: bool) -> None:
    """Attende che la porta sia raggiungibile entro `timeout_s` secondi."""
    tout = float(timeout_s if timeout_s is not None else (get_int("PREVIEW_READY_TIMEOUT", 30) or 30))
    try:
        wait_for_port(host, int(port), timeout=tout, logger=logger)
    except TimeoutError as e:
        raise PreviewError(f"Preview non raggiungibile su {host}:{port} entro {tout:.0f}s", slug=slug) from e


def stop_container_safely(container_name: str) -> None:
    """Best-effort: prova a fermare/rimuovere il container; non solleva errori fatali."""
    try:
        run_cmd(["docker", "rm", "-f", container_name], op="docker rm -f (safe)", logger=logger, capture=True)
        logger.info("🧹 Cleanup container completato", extra={"container": container_name})
    except Exception:
        # non interrompere il flusso in caso di fallimento del cleanup
        logger.warning("Cleanup container non riuscito", extra={"container": container_name})


# ----------------------------
# Entry point modulo (no prompt)
# ----------------------------
def run_gitbook_docker_preview(
    context,
    port: int = 4000,
    container_name: str = "honkit_preview",
    wait_on_exit: bool = False,  # default non-interattivo
    *,
    redact_logs: bool = False,  # redazione opt-in dei messaggi di log
) -> None:
    """
    Avvia la preview GitBook/HonKit in Docker.

    Comportamento:
      - Genera `book.json` e `package.json` minimi se mancanti.
      - Esegue `honkit build` in container.
      - Avvia `honkit serve` mappando la porta locale.
      - Nessun prompt: interazione/decisione è responsabilità degli orchestratori.

    Args:
        context: Contesto con `slug`, `md_dir`, `base_dir`.
        port: Porta locale da esporre (default 4000).
        container_name: Nome del container Docker.
        wait_on_exit: Se True, esegue `serve` in foreground (senza -d).
        redact_logs: Se True, applica redazione ai messaggi di log (non alle eccezioni).

    Raises:
        PipelineError: se `slug` mancante nel contesto.
        PreviewError: path non sicuro o errori build/serve.
    """
    if not getattr(context, "slug", None):
        raise PipelineError("Slug cliente mancante nel contesto per preview", slug=None)

    # Path-safety STRONG: md_dir deve essere sotto base_dir
    try:
        ensure_within(context.base_dir, context.md_dir)
    except Exception as e:
        raise PreviewError(
            f"Percorso markdown non sicuro: {context.md_dir} ({e})",
            slug=context.slug,
            file_path=context.md_dir,
        )

    md_output_path = Path(context.md_dir).resolve()
    logger.info(
        _maybe_redact("📂 Directory per anteprima", redact_logs),
        extra={"slug": context.slug, "file_path": str(md_output_path)},
    )

    # File necessari (idempotente)
    ensure_book_json(md_output_path, slug=context.slug, redact_logs=redact_logs)
    ensure_package_json(md_output_path, slug=context.slug, redact_logs=redact_logs)

    # 1) Build statica
    build_static_site(md_output_path, slug=context.slug, redact_logs=redact_logs)

    # 2) Serve
    if wait_on_exit:
        # Foreground (senza -d): blocca finché il processo 'serve' non termina.
        cmd = [
            "docker",
            "run",
            "--name",
            container_name,
            "-p",
            f"{port}:4000",
            "--workdir",
            "/app",
            "-v",
            f"{md_output_path}:/app",
            HONKIT_DOCKER_IMAGE,
            "npm",
            "run",
            "serve",
        ]
        try:
            run_cmd(cmd, op="docker run serve (fg)", logger=logger)
        except CmdError as e:
            # tentativo cleanup best-effort e rilancio
            try:
                stop_container_safely(container_name)
            finally:
                raise PreviewError(f"Errore 'honkit serve' (fg): {e}", slug=context.slug)
        finally:
            # best-effort cleanup post-exec
            stop_container_safely(container_name)
    else:
        # Detached: avvia e ritorna subito; orchestratore gestirà lo stop a fine run.
        run_container_detached(
            md_output_path,
            slug=context.slug,
            container_name=container_name,
            port=port,
            redact_logs=redact_logs,
        )

        # 3) Attendi che la preview sia raggiungibile (best-effort, ma utile per early feedback)
        wait_until_ready("127.0.0.1", port, timeout_s=get_int("PREVIEW_READY_TIMEOUT", 30), slug=context.slug, redact_logs=redact_logs)
