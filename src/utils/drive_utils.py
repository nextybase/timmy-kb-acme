import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Leggi parametri dal .env (con fallback ragionevoli)
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
DRIVE_ID = os.getenv("DRIVE_ID")  # Deve essere valorizzato nel .env

def get_drive_service():
    """
    Restituisce un client Google Drive autenticato.
    """
    if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(
            f"File di credenziali Google non trovato: {SERVICE_ACCOUNT_FILE}.\n"
            "Verifica la variabile SERVICE_ACCOUNT_FILE nel .env."
        )
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def create_folder(service, name, parent_id=None):
    """
    Crea una cartella su Google Drive.
    - service: oggetto client Drive
    - name: nome della cartella
    - parent_id: ID cartella padre (default: DRIVE_ID globale)
    """
    if not parent_id:
        if not DRIVE_ID:
            raise ValueError("DRIVE_ID non configurato nel .env")
        parent_id = DRIVE_ID

    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(
        body=metadata,
        fields='id',
        supportsAllDrives=True
    ).execute()
    return folder.get('id')

def share_folder_with_user(service, folder_id, email):
    """
    Condivide una cartella con un utente specifico (writer).
    """
    permission = {
        'type': 'user',
        'role': 'writer',
        'emailAddress': email
    }
    service.permissions().create(
        fileId=folder_id,
        body=permission,
        fields='id',
        sendNotificationEmail=True,
        supportsAllDrives=True
    ).execute()

def find_folder_by_name(service, name, parent_id=None, drive_id=None):
    """
    Cerca una cartella per nome all'interno di un genitore (parent_id o drive_id).
    Restituisce il primo risultato trovato (dict con id e name) oppure None.
    """
    if not drive_id:
        drive_id = DRIVE_ID
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    else:
        query += f" and '{drive_id}' in parents"
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="drive",
        driveId=drive_id
    ).execute()
    files = results.get('files', [])
    return files[0] if files else None

# (Altre utility future: rimozione cartelle, check permessi, ecc.)
