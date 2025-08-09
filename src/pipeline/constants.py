"""
Definizione delle costanti strutturali della pipeline Timmy-KB.
Tutti i nomi di cartelle, file e MIME type centrali vengono definiti qui.
Se devono cambiare, il cambiamento va considerato architetturale.
"""

# 📂 Directory e file standard
OUTPUT_DIR_NAME = "output"
LOGS_DIR_NAME = "logs"
CONFIG_FILE_NAME = "config.yaml"
SEMANTIC_MAPPING_FILE_NAME = "semantic_mapping.yaml"

# 📄 Suffissi di backup e temporanei
BACKUP_SUFFIX = ".bak"
TMP_SUFFIX = ".tmp"

# 📌 Base dir name (se usata per validazioni path)
BASE_DIR_NAME = "."

# 📦 Google Drive MIME Types
GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
GDRIVE_FILE_MIME = "application/vnd.google-apps.file"

# 📌 Altri nomi di directory specifici della pipeline
RAW_DIR_NAME = "raw"
BOOK_DIR_NAME = "book"
CONFIG_DIR_NAME = "config"

# 📄 MIME Types generici
PDF_MIME_TYPE = "application/pdf"

# 📄 File tipici di GitBook
BOOK_JSON_NAME = "book.json"
PACKAGE_JSON_NAME = "package.json"
