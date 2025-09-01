from __future__ import annotations

import importlib
import types

import pytest


def test_import_drive_utils_no_bom() -> None:
    """Il modulo deve potersi importare 'a freddo' (niente BOM/encoding strani)."""
    importlib.invalidate_caches()
    mod = importlib.import_module("pipeline.drive_utils")
    assert isinstance(mod, types.ModuleType)
    # sanity: il modulo ha una docstring e un __all__ significativo
    assert mod.__doc__ is not None and len(mod.__doc__) > 0
    assert hasattr(mod, "__all__")


def test_reexports_present() -> None:
    """Controlla che i simboli pubblici dichiarati siano realmente presenti."""
    mod = importlib.import_module("pipeline.drive_utils")
    expected = {
        "MIME_FOLDER",
        "MIME_PDF",
        "MediaIoBaseDownload",
        "get_drive_service",
        "list_drive_files",
        "get_file_metadata",
        "_retry",
        "create_drive_folder",
        "create_drive_structure_from_yaml",
        "upload_config_to_drive_folder",
        "delete_drive_file",
        "create_local_base_structure",
        "download_drive_pdfs_to_local",
    }
    missing = [name for name in expected if not hasattr(mod, name)]
    assert not missing, f"Simboli mancanti nella facciata drive_utils: {missing}"


def test_media_iobase_download_placeholder_behavior() -> None:
    """
    Se la dipendenza `google-api-python-client` non è installata,
    la classe riesportata deve essere un placeholder che solleva ImportError all'uso.
    Se è installata, verifichiamo solo che il simbolo esista (niente istanziazione).
    """
    mod = importlib.import_module("pipeline.drive_utils")
    cls = getattr(mod, "MediaIoBaseDownload", None)
    assert cls is not None

    # Caso placeholder: il nome classe è quello definito nel file della facciata.
    if getattr(cls, "__name__", "") == "_MediaIoBaseDownloadPlaceholder":
        with pytest.raises(ImportError):
            # Parametri arbitrari: il placeholder deve comunque sollevare.
            cls(object(), object())
