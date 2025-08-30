# src/pipeline/exceptions.py
from __future__ import annotations

from typing import Optional, Any
from pathlib import Path

"""
Eccezioni di dominio per la pipeline NeXT/Timmy.

Cosa trovi qui (ruoli principali):
- `PipelineError`: base class di tutte le eccezioni di dominio (no I/O, no exit).
- Sottoclassi tipizzate per aree funzionali: Drive*, ConversionError, PushError,
  ForcePushError (governance), ConfigError, PreviewError, EnrichmentError,
  SemanticMappingError, PreOnboardingValidationError.
- Quick win per input/slug: InputDirectoryMissing, InputFileMissing, InvalidSlug.
- `EXIT_CODES`: tabella centralizzata per la mappatura orchestratori → sys.exit.
- (Opz.) `exit_code_for(exc)`: helper di comodo per ottenere il codice.

Linee guida:
- Nessuna classe esegue I/O o termina il processo.
- I messaggi includono contesto “safe” in `__str__` (slug, tail(file), mask id).
- Se non esiste una tipizzata adatta → usa `PipelineError`.
"""


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
        """Maschera l'ID (es. Drive) lasciando solo le ultime `keep` cifre."""
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


class PreOnboardingValidationError(PipelineError):
    """Errore di validazione durante la fase di pre-onboarding (config, env, file)."""

    pass


# === Quick win: eccezioni tipizzate per I/O input e slug =====================


class InputDirectoryMissing(PipelineError):
    """Directory di input attesa ma assente (es. raw/ o sottocartella richieste)."""

    pass


class InputFileMissing(PipelineError):
    """File di input atteso ma assente (es. singolo PDF o YAML richiesto)."""

    pass


class InvalidSlug(PipelineError):
    """Slug non valido secondo il pattern configurato (vedi `path_utils.validate_slug`)."""

    pass


# ---------------------------------------------------------------------------
# Mappa centralizzata dei codici di uscita (nessun I/O, no side effects)
# Gli orchestratori useranno questa tabella per sys.exit() coerenti.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    "PipelineError": 1,
    "ConfigError": 2,
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
    """Restituisce il codice di uscita per un'eccezione (fallback a PipelineError=1)."""
    return EXIT_CODES.get(type(exc).__name__, EXIT_CODES["PipelineError"])


__all__ = [
    "PipelineError",
    "DriveDownloadError",
    "DriveUploadError",
    "ConversionError",
    "PushError",
    "ForcePushError",
    "ConfigError",
    "CleanupError",
    "PreviewError",
    "EnrichmentError",
    "SemanticMappingError",
    "PreOnboardingValidationError",
    "InputDirectoryMissing",
    "InputFileMissing",
    "InvalidSlug",
    "EXIT_CODES",
    "exit_code_for",
]
