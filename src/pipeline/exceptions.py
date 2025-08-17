# src/pipeline/exceptions.py

"""
Definizione delle eccezioni custom per la pipeline NeXT/Timmy.
Tutte le eccezioni core derivano da PipelineError.
Ogni eccezione ha una docstring specifica per l'auto-documentazione.
"""

class PipelineError(Exception):
    """Eccezione generica per errori bloccanti nella pipeline NeXT/Timmy."""
    def __init__(self, message=None, *, slug=None, file_path=None, drive_id=None):
        super().__init__(message)
        self.slug = slug
        self.file_path = file_path
        self.drive_id = drive_id

    def __str__(self):
        base_msg = super().__str__()
        context_parts = []
        if self.slug:
            context_parts.append(f"slug={self.slug}")
        if self.file_path:
            context_parts.append(f"file={self.file_path}")
        if self.drive_id:
            context_parts.append(f"drive_id={self.drive_id}")
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

# Utilizzo consigliato:
# from pipeline.exceptions import <ExcClass> e non importare direttamente PipelineError.

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
