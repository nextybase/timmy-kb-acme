"""
Definizione delle costanti strutturali della pipeline Timmy-KB.
Tutti i nomi di cartelle, file e MIME type centrali vengono definiti qui.
Se devono cambiare, il cambiamento va considerato architetturale.
"""

# 📂 Directory e file standard
OUTPUT_DIR_NAME = "output"
LOGS_DIR_NAME = "logs"
CONFIG_FILE_NAME = "config.yaml"
SEMANTIC_MAPPING_FILE = "semantic_mapping.yaml"

# 🪵 Logging
LOG_FILE_NAME = "onboarding.log"  # nome log usato dagli orchestratori

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

# 📄 File tipici di GitBook/HonKit
BOOK_JSON_NAME = "book.json"
PACKAGE_JSON_NAME = "package.json"
SUMMARY_MD_NAME = "SUMMARY.md"
README_MD_NAME = "README.md"

# 🐙 Git/GitHub
REPO_NAME_PREFIX = "timmy-kb-"
GIT_COMMIT_USER_NAME = "Timmy KB"
GIT_COMMIT_USER_EMAIL = "kb+noreply@local"
# Chiavi d'ambiente da cui risolvere il branch di default (in ordine di priorità)
DEFAULT_GIT_BRANCH_ENV_KEYS = ("GIT_DEFAULT_BRANCH", "GITHUB_BRANCH")

# 📚 HonKit/GitBook Preview
HONKIT_DOCKER_IMAGE = "honkit/honkit"
PREVIEW_DEFAULT_PORT = 4000
HONKIT_CONTAINER_NAME_PREFIX = "honkit_preview"

# ⚙️ Parametri di performance (tuning)
# Nota: default "morbidi" letti dai moduli; gli orchestratori possono override.
MAX_CONCURRENCY = 4           # Concorrenza consigliata per operazioni a grana grossa (es. per categoria)
SKIP_IF_UNCHANGED = True      # Abilita lo skip basato su fingerprint quando l'input non è cambiato
