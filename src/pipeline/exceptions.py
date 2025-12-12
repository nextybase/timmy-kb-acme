# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/exceptions.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

"""
Eccezioni SSoT per NeXT/Timmy.

Ruoli principali:
- `TimmyError`: base per errori applicativi “generici” fuori pipeline (es. retriever).
- `PipelineError`: base per eccezioni di dominio della pipeline (no I/O, no exit).
- Sottoclassi tipizzate per aree funzionali: Drive*, ConversionError, PushError,
  ForcePushError (governance), ConfigError, PreviewError, EnrichmentError,
  SemanticMappingError, PreOnboardingValidationError, ecc.
- Quick win input/slug: InputDirectoryMissing, InputFileMissing, InvalidSlug.
- `EXIT_CODES` + `exit_code_for`: tabella centralizzata per orchestratori.

Linee guida:
- Nessuna eccezione fa I/O o termina il processo.
- I messaggi includono contesto “safe” in __str__ (slug, tail(file), mask id).
- Se non esiste una tipizzata adatta → usa `PipelineError`.
"""

# ---------------------------------------------------------------------------
# Basi
# ---------------------------------------------------------------------------


class TimmyError(Exception):
    """Base per errori applicativi Timmy/NeXT non legati alla pipeline."""


class PipelineError(Exception):
    """Eccezione generica per errori bloccanti nella pipeline NeXT/Timmy.

    Accetta un messaggio e un payload contestuale opzionale (slug, file_path, drive_id, run_id)
    utile per logging strutturato e diagnosi.
    """

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        slug: Optional[str] = None,
        file_path: Optional[str | Path] = None,
        drive_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **_: Any,
    ) -> None:
        super().__init__(message or "")
        self.slug: Optional[str] = slug
        self.file_path: Optional[str | Path] = file_path
        self.drive_id: Optional[str] = drive_id
        self.run_id: Optional[str] = run_id

    @staticmethod
    def _safe_file_repr(fp: str | Path) -> str:
        """Mostra solo il nome (niente path assoluti)."""
        try:
            return Path(fp).name or str(fp)
        except Exception:
            return str(fp)

    @staticmethod
    def _mask_id(val: str, keep: int = 6) -> str:
        """Maschera l'ID (es.

        Drive) lasciando solo le ultime `keep` cifre.
        """
        try:
            s = str(val)
            if len(s) <= keep:
                return s
            return f"…{s[-keep:]}"
        except Exception:
            return "…"

    def __str__(self) -> str:
        base_msg = super().__str__() or self.__class__.__name__
        context_parts: list[str] = []
        if self.slug:
            context_parts.append(f"slug={self.slug}")
        if self.file_path:
            context_parts.append(f"file={self._safe_file_repr(self.file_path)}")
        if self.drive_id:
            context_parts.append(f"drive_id={self._mask_id(self.drive_id)}")
        if self.run_id:
            context_parts.append(f"run_id={self.run_id}")
        context_info = f" [{' | '.join(context_parts)}]" if context_parts else ""
        return f"{base_msg}{context_info}"


# ---------------------------------------------------------------------------
# Errori applicativi extra-pipeline
# ---------------------------------------------------------------------------


class RetrieverError(ValueError, TimmyError):
    """Errore di validazione/uso del retriever (parametri, limiti, ecc.)."""


# ---------------------------------------------------------------------------
# Errori tipizzati di pipeline
# ---------------------------------------------------------------------------


class DriveDownloadError(PipelineError):
    """Errore nel download di file/cartelle da Google Drive."""

    pass


class DriveUploadError(PipelineError):
    """Errore nel caricamento su Google Drive."""

    pass


class ConversionError(PipelineError):
    """Errore durante la conversione di file (PDF→Markdown, ecc.)."""

    pass


class PushError(PipelineError):
    """Errore durante il push su GitHub."""

    pass


class ForcePushError(PipelineError):
    """Violazioni della policy di force push (richiede flag + ACK)."""

    pass


class ConfigError(PipelineError):
    """Errore di caricamento o validazione della configurazione."""

    pass


class WorkspaceNotFound(ConfigError):
    """Workspace slug-specifico non trovato o radice non risolubile."""

    pass


class WorkspaceLayoutInvalid(ConfigError):
    """Layout presente ma privo di artefatti minimi obbligatori."""

    pass


class WorkspaceLayoutInconsistent(ConfigError):
    """Layout presente ma con configurazioni/versioni/asset semantic incoerenti."""

    pass


class PathTraversalError(ConfigError):
    """Path traversal rilevato rispetto al perimetro consentito."""

    pass


class CleanupError(PipelineError):
    """Errore durante la pulizia della cartella di output."""

    pass


class PreviewError(PipelineError):
    """Errore durante la preview GitBook/Honkit via Docker."""

    pass


class EnrichmentError(PipelineError):
    """Errore durante l'arricchimento semantico dei markdown."""

    pass


class SemanticMappingError(PipelineError):
    """Errore nel caricamento del mapping semantico delle cartelle."""

    pass


class GitBookPublishError(PipelineError):
    """Errore durante la pubblicazione GitBook automatica."""

    pass


class PreOnboardingValidationError(PipelineError):
    """Errore di validazione nella fase di pre-onboarding (config, env, file)."""

    pass


# --- Quick win: I/O input e slug ---------------------------------------------


class InputDirectoryMissing(PipelineError):
    """Directory di input attesa ma assente (es.

    raw/ o sottocartella richiesta).
    """

    pass


class InputFileMissing(PipelineError):
    """File di input atteso ma assente (es.

    singolo PDF o YAML richiesto).
    """

    pass


class InvalidSlug(PipelineError):
    """Slug non valido secondo il pattern configurato (vedi `path_utils.validate_slug`)."""

    pass


# ---------------------------------------------------------------------------
# Exit codes centralizzati (nessun side-effect)
# ---------------------------------------------------------------------------

EXIT_CODES = {
    "PipelineError": 1,
    "ConfigError": 2,
    "WorkspaceNotFound": 2,
    "WorkspaceLayoutInvalid": 2,
    "WorkspaceLayoutInconsistent": 2,
    "PreOnboardingValidationError": 3,
    "ConversionError": 10,
    "DriveDownloadError": 21,
    "DriveUploadError": 22,
    "PreviewError": 30,
    "PushError": 40,
    "ForcePushError": 41,
    "CleanupError": 50,
    "EnrichmentError": 60,
    "SemanticMappingError": 61,
}


def exit_code_for(exc: BaseException) -> int:
    """Restituisce il codice di uscita per un’eccezione (fallback a PipelineError=1)."""
    return EXIT_CODES.get(type(exc).__name__, EXIT_CODES["PipelineError"])


__all__ = [
    # basi
    "TimmyError",
    "PipelineError",
    # extra-pipeline
    "RetrieverError",
    # pipeline
    "DriveDownloadError",
    "DriveUploadError",
    "ConversionError",
    "PushError",
    "ForcePushError",
    "ConfigError",
    "PathTraversalError",
    "WorkspaceNotFound",
    "WorkspaceLayoutInvalid",
    "WorkspaceLayoutInconsistent",
    "CleanupError",
    "PreviewError",
    "EnrichmentError",
    "SemanticMappingError",
    "PreOnboardingValidationError",
    "InputDirectoryMissing",
    "InputFileMissing",
    "InvalidSlug",
    # exit codes
    "EXIT_CODES",
    "exit_code_for",
]
