# src/utils/config_writer.py

import yaml
import tempfile
from pathlib import Path
from googleapiclient.http import MediaFileUpload

def generate_config_yaml(slug: str, nome: str) -> dict:
    return {
        'cliente_id': slug,
        'cliente_nome': nome
    }

def upload_config_to_drive(service, folder_id: str, config_data: dict):
    """
    Carica il file config.yaml su Google Drive.
    """
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml", mode='w', encoding='utf-8') as temp_file:
            yaml.dump(config_data, temp_file, allow_unicode=True)
            temp_file_path = temp_file.name

        media = MediaFileUpload(temp_file_path, mimetype='application/x-yaml', resumable=False)
        file_metadata = {
            'name': 'config.yaml',
            'parents': [folder_id]
        }

        service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        print("✅ File config.yaml caricato con successo.")
        print(f"📄 Il file temporaneo resta disponibile: {temp_file_path}")

    except Exception as e:
        print(f"❌ Errore durante il caricamento su Drive: {e}")

def write_config(config_data: dict, path: Path) -> None:
    """
    Scrive il file config.yaml localmente per verifica/rollback.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
        print(f"✅ File di configurazione salvato in locale: {path}")
    except Exception as e:
        print(f"❌ Errore nella scrittura locale: {e}")
