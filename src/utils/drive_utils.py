# src/utils/drive_utils.py

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
DRIVE_ID = os.getenv("DRIVE_ID")


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def create_folder(service, name, parent_id=None):
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id] if parent_id else [DRIVE_ID]
    }

    folder = service.files().create(
        body=metadata,
        fields='id',
        supportsAllDrives=True
    ).execute()

    return folder.get('id')


def share_folder_with_user(service, folder_id, email):
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


def find_folder_by_name(service, name, parent_id=None, drive_id=DRIVE_ID):
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
