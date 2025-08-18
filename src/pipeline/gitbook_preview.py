# src/pipeline/gitbook_preview.py
from __future__ import annotations

"""
Preview GitBook/HonKit tramite Docker, senza interattività nel modulo.

Modifiche (v1.0.4 - PATCH):
- Default non-interattivo: wait_on_exit=False.
- Rimosse dipendenze da input()/prompt: gli orchestratori decidono.
- Compatibilità: se wait_on_exit=True, il container viene eseguito in foreground
  (senza -d) e il controllo torna al termine del processo (nessun prompt qui).

Queste scelte rispettano le regole v1.0.3:
- Niente prompt nei moduli; l’interattività è solo negli orchestratori.
- Anteprima gestita/decisa dagli orchestratori (auto-skip o conferma).

Aggiornamento PATCH:
- Introduce parametro opzionale `redact_logs: bool = False`. Se True, applica
  la redazione dei messaggi di log potenzialmente sensibili tramite
  `pipeline.env_utils.redact_secrets`. Nessun impatto sui messaggi delle eccezioni.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, PreviewError
from pipeline.path_utils import is_safe_subpath
from pipeline.config_utils import safe_write_file  # ✅ scritture atomiche
from pipeline.env_utils import redact_secrets  # 🔐 redazione opzionale nei log

logger = get_structured_logger("pipeline.gitbook_preview")


def _maybe_redact(text: str, redact: bool) -> str:
    """Applica redazione ai messaggi di log solo se richiesto."""
    return redact_secrets(text) if (redact and text) else text


# ----------------------------
# Helpers idempotenti di setup
# ----------------------------
def ensure_book_json(md_dir: Path, *, slug: Optional[str] = None, redact_logs: bool = False) -> None:
    """
    Crea un book.json minimo se mancante (idempotente).
    """
    book_json_path = Path(md_dir) / "book.json"
    if not book_json_path.exists():
        data = {
            "title": "preview",
            "plugins": [],
        }
        try:
            # ✅ scrittura atomica
            safe_write_file(book_json_path, json.dumps(data, indent=2))
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
    """
    Crea un package.json minimo se mancante (idempotente).
    """
    package_json_path = Path(md_dir) / "package.json"
    if not package_json_path.exists():
        data = {
            "name": "honkit-preview",
            "version": "0.0.0",
            "description": "HonKit preview",
            "main": "README.md",
            "license": "MIT",
            "scripts": {
                "build": "honkit build",
                "serve": "honkit serve",
            },
        }
        try:
            # ✅ scrittura atomica
            safe_write_file(package_json_path, json.dumps(data, indent=2))
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
# Entry point modulo (no prompt)
# ----------------------------
def run_gitbook_docker_preview(
    context,
    port: int = 4000,
    container_name: str = "honkit_preview",
    wait_on_exit: bool = False,  # ← default non-interattivo
    *,
    redact_logs: bool = False,   # ← NOVITÀ: redazione opt-in dei messaggi di log
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

    # Path-safety
    if not is_safe_subpath(context.md_dir, context.base_dir):
        raise PreviewError(
            f"Percorso markdown non sicuro: {context.md_dir}",
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

    # Build statica
    build_cmd = [
        "docker",
        "run",
        "--rm",
        "--workdir",
        "/app",
        "-v",
        f"{md_output_path}:/app",
        "honkit/honkit",
        "npm",
        "run",
        "build",
    ]
    try:
        subprocess.run(build_cmd, check=True)
        logger.info(_maybe_redact("🔨 Build statica HonKit completata.", redact_logs), extra={"slug": context.slug})
    except subprocess.CalledProcessError as e:
        msg = "❌ Errore durante 'honkit build'"
        logger.error(_maybe_redact(msg, redact_logs), extra={"slug": context.slug})
        # Manteniamo i dettagli completi nell'eccezione (nessuna redazione qui)
        raise PreviewError(f"Errore 'honkit build': {e}", slug=context.slug)

    # Serve
    serve_base_cmd = [
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
        "honkit/honkit",
        "npm",
        "run",
        "serve",
    ]

    if wait_on_exit:
        # Foreground (nessun -d): blocca finché il processo serve non termina.
        # Nessun prompt qui; eventuale stop è responsabilità di chi avvia il processo.
        serve_cmd = ["docker", "rm", "-f", container_name]
        try:
            subprocess.run(
                [c for c in serve_base_cmd if c != "-d"],  # ensure no -d
                check=True,
            )
        except subprocess.CalledProcessError as e:
            # Se il container è già esistente/occupato, tentiamo una pulizia soft e rilanciamo.
            try:
                subprocess.run(serve_cmd, check=False)
            finally:
                # Nessun log aggiuntivo qui per non alterare la verbosità; eccezione come prima
                raise PreviewError(f"Errore 'honkit serve' (fg): {e}", slug=context.slug)
        finally:
            # Best-effort cleanup (se il container è rimasto in vita)
            subprocess.run(["docker", "rm", "-f", container_name], check=False)
            logger.info(
                _maybe_redact("🧹 Cleanup container (fg) completato", redact_logs),
                extra={"slug": context.slug, "file_path": container_name},
            )
    else:
        # Detached: ritorna subito. Cleanup e stop sono responsabilità esterne.
        serve_cmd = [
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
            "honkit/honkit",
            "npm",
            "run",
            "serve",
        ]
        try:
            subprocess.run(serve_cmd, check=True)
            logger.info(
                _maybe_redact("▶️ HonKit serve avviato (detached).", redact_logs),
                extra={
                    "slug": context.slug,
                    "file_path": f"{container_name}@{port}",
                },
            )
        except subprocess.CalledProcessError as e:
            # Se esiste già un container con lo stesso nome, tentiamo rimozione e retry una volta.
            subprocess.run(["docker", "rm", "-f", container_name], check=False)
            try:
                subprocess.run(serve_cmd, check=True)
                logger.info(
                    _maybe_redact("▶️ HonKit serve avviato (detached) dopo retry.", redact_logs),
                    extra={
                        "slug": context.slug,
                        "file_path": f"{container_name}@{port}",
                    },
                )
            except subprocess.CalledProcessError as e2:
                # Coerente con il comportamento precedente: eccezione senza log aggiuntivi
                raise PreviewError(f"Errore 'honkit serve' (bg): {e2}", slug=context.slug)
