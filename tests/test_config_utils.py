import sys
import os
import subprocess
from pathlib import Path
import pytest

# Fai vedere src/ come package root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from pipeline.config_utils import get_config, UnifiedConfig

SLUG = "dummy"

@pytest.fixture(scope="session", autouse=True)
def ensure_dummy_kb():
    """Crea la struttura dummy KB se non esiste."""
    kb_root = Path("output/timmy-kb-dummy/config/config.yaml")
    if not kb_root.exists():
        # Lancia lo script di generazione dummy (adatta il path se serve)
        subprocess.run(["python", "src/tools/genera_dummy_kb.py"], check=True)

def print_debug_config(unified):
    print("\n=== DEBUG CONFIG LOADED ===")
    print("[TimmyConfig]")
    for field in unified.config.__fields__:
        print(f"{field}: {getattr(unified.config, field)!r}")
    print("[TimmySecrets]")
    for field in unified.secrets.__fields__:
        print(f"{field}: {getattr(unified.secrets, field)!r}")
    print("\n[Shortcut properties]")
    print(f"drive_id: {unified.drive_id}")
    print(f"service_account_file: {unified.service_account_file}")
    print(f"raw_dir: {unified.raw_dir}")
    print(f"md_output_path: {unified.md_output_path}")
    print(f"base_drive: {unified.base_drive}")

def test_config_valid_load():
    """Verifica che la configurazione unificata venga caricata correttamente e override funzioni."""
    from pipeline import config_utils
    config_utils.get_config.cache_clear()
    unified = get_config(SLUG)

    # Debug completo (visibile in output verbose pytest -s)
    print_debug_config(unified)

    # Verifica presenza campi chiave
    assert isinstance(unified, UnifiedConfig)
    assert unified.drive_id, "drive_id mancante"
    assert unified.raw_dir, "raw_dir mancante"
    assert isinstance(unified.md_output_path, str)
    assert unified.config.slug == SLUG

def test_config_missing_yaml(tmp_path, monkeypatch):
    """Verifica che mancando il config.yaml venga sollevato FileNotFoundError."""
    fake_slug = "nonexistent_client_123"
    from pipeline import config_utils
    config_utils.get_config.cache_clear()
    with pytest.raises(FileNotFoundError):
        get_config(fake_slug)

def test_config_override_env(monkeypatch):
    """Verifica che l'override da .env prevale sui valori YAML."""
    monkeypatch.setenv("DRIVE_ID", "env_drive_override")
    monkeypatch.setenv("GITHUB_TOKEN", "env_token_override")
    from pipeline import config_utils
    config_utils.get_config.cache_clear()
    unified = get_config(SLUG)
    assert unified.drive_id == "env_drive_override"
    assert unified.secrets.GITHUB_TOKEN == "env_token_override"

def test_config_properties_consistency():
    """Verifica che le proprietà shortcut coincidano con i valori attesi."""
    from pipeline import config_utils
    config_utils.get_config.cache_clear()
    unified = get_config(SLUG)
    assert unified.drive_id == unified.secrets.DRIVE_ID
    assert unified.service_account_file == unified.secrets.SERVICE_ACCOUNT_FILE
    assert unified.raw_dir == unified.config.raw_dir
    assert unified.md_output_path == unified.config.md_output_path
    assert unified.base_drive == unified.secrets.BASE_DRIVE
