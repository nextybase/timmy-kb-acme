# src/pipeline/exceptions.py
from __future__ import annotations

from typing import Optional, Any
from pathlib import Path

"""
Definizione delle eccezioni custom per la pipeline NeXT/Timmy.

Linee guida:
- Tutte le eccezioni core derivano da `PipelineError`.
- NESSUNA di queste classi deve eseguire I/O (file/network) o terminare il processo.
- Gli orchestratori mappano le eccezioni in `EXIT_CODES` per produrre `sys.exit(<code>)`.
- Ogni eccezione ha una docstring specifica per l'auto-documentazione.
"""


class PipelineError(Exception):
    """Eccezione generica per errori bloccanti nella pipeline NeXT/Timmy.

    Questa è la base di tutte le eccezioni di dominio. Accetta un messaggio e
    un payload contestuale opzionale (slug, percorso file, id Drive) utile per
    il logging strutturato e la diagnosi.

    Args:
        message: Messaggio descrittivo dell'errore.
        slug: Slug del cliente coinvolto (se rilevante).
        file_path: Percorso del file coinvolto (Path o stringa).
        drive_id: ID di risorsa su Google Drive (cartella/file).

    Note:
        - Le sottoclassi non devono alterare la semantica del costruttore
          salvo aggiungere campi contestuali non funzionali.
        - Il metodo `__str__` include automaticamente un contesto *sicuro* se presente.
    """

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        slug: Optional[str] = None,
        file_path: Optional[str | Path] = None,
        drive_id: Optional[str] = None,
        **_: Any,
    ) -> None:
        super().__init__(message or "")
        self.slug: Optional[str] = slug
        self.file_path: Optional[str | Path] = file_path
        self.drive_id: Optional[str] = drive_id

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


# ------------------------------------------------------------
# Mappa centralizzata dei codici di uscita (nessun I/O, no side effects)
# Gli orchestratori useranno questa tabella per sys.exit() coerenti.
# ------------------------------------------------------------
EXIT_CODES = {
    "PipelineError": 1,
    "ConfigError": 2,
    "PreOnboardingValidationError": 3,
    "ConversionError": 10,
    "DriveDownloadError": 21,
    "DriveUploadError": 22,
    "PreviewError": 30,
    "PushError": 40,
    "CleanupError": 50,
    "EnrichmentError": 60,
    "SemanticMappingError": 61,
}

__all__ = [
    "PipelineError",
    "DriveDownloadError",
    "DriveUploadError",
    "ConversionError",
    "PushError",
    "ConfigError",
    "CleanupError",
    "PreviewError",
    "EnrichmentError",
    "SemanticMappingError",
    "PreOnboardingValidationError",
    "EXIT_CODES",
]
