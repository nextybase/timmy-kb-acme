# src/pipeline/exceptions.py

"""
Definizione delle eccezioni custom per la pipeline NeXT/Timmy.
Tutte le eccezioni core devono ereditare da PipelineError.
Ogni eccezione ha una docstring specifica per l’auto-documentazione.
"""

class PipelineError(Exception):
    """Eccezione generica per errori bloccanti nella pipeline NeXT/Timmy."""
    pass

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
